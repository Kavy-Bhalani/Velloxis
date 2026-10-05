import hashlib
import uuid
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Header, Response, status
from app.core.config import get_settings
from app.core.security import verify_firebase_token, verify_app_check_token
from app.core.moderation import check_prompt_safety
from app.core.rate_limiter import generation_rate_limiter
from app.schemas.generation import GenerationRequest
from app.providers.base import GenerationInput
from app.providers.router import ai_router
from app.db import queries

logger = logging.getLogger("velloxis.api.generation")
settings = get_settings()

router = APIRouter()

# Style prompt enhancement modifiers
STYLE_PROMPTS = {
    "photorealistic": "hyper-realistic 8k resolution photo, natural cinematic lighting, highly detailed, photorealistic",
    "anime": "anime aesthetic, vibrant studio anime art style, detailed line art, masterpiece",
    "cinematic": "cinematic movie scene, dramatic atmospheric lighting, 35mm film grain, 8k",
    "3d": "3D render style, octane render, soft ambient lighting, smooth clay/pixar aesthetic",
    "fantasy": "epic high fantasy art, magical atmosphere, intricate detailing, ethereal glow",
    "minimalist": "minimalist art, clean compositions, elegant simple color palette, modern design",
}

@router.post("/generations")
async def generate_image(
    payload: GenerationRequest,
    firebase_uid: str = Depends(verify_firebase_token),
    x_firebase_appcheck: Optional[str] = Header(None, alias="X-Firebase-AppCheck"),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    """
    Core Generation Endpoint protected by the 8-Gate Cost Firewall.
    Returns: Binary image payload (image/jpeg or image/webp) with metadata headers.
    """
    # Gate 1 & 2 are handled via dependencies (Firebase Token & App Check)
    await verify_app_check_token(x_firebase_appcheck)

    # Gate 3: Rate Limiting
    if not generation_rate_limiter.is_allowed(firebase_uid):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please wait a moment before generating again."
        )

    # Gate 4: Prompt Safety & Content Policy
    is_safe, safety_error = check_prompt_safety(payload.prompt, max_length=settings.MAX_PROMPT_LENGTH)
    if not is_safe:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safety_error
        )

    # Gate 5: Configuration & Kill Switch
    if not settings.GENERATION_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Image generation is temporarily disabled for maintenance. Please check back shortly."
        )

    # Sync / Get internal user UUID
    user_id, balance = await queries.sync_user(firebase_uid)

    # Determine credit cost
    credit_cost = (
        settings.QUALITY_MODEL_CREDIT_COST
        if payload.model == "quality"
        else settings.FAST_MODEL_CREDIT_COST
    )

    # Generation ID
    gen_id = idempotency_key if idempotency_key else str(uuid.uuid4())
    provider_name, provider_model_id = ai_router.get_provider_details(payload.model)
    prompt_hash = hashlib.sha256(payload.prompt.encode("utf-8")).hexdigest()

    # Gate 6 & 7: Daily Allowance & Atomic Credit Reservation
    try:
        reserved = await queries.reserve_credit(
            user_id=user_id,
            cost=credit_cost,
            gen_id=gen_id,
            model_alias=payload.model,
            provider=provider_name,
            provider_model_id=provider_model_id,
            prompt_hash=prompt_hash,
            max_daily_generations=settings.MAX_DAILY_GENERATIONS
        )
    except Exception as e:
        if "DAILY_LIMIT_EXCEEDED" in str(e):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Daily generation limit of {settings.MAX_DAILY_GENERATIONS} reached. Resets at midnight UTC."
            )
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database transaction error.")

    if not reserved:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Insufficient credits. Watch a rewarded ad to earn more credits!"
        )

    # Resolve dimensions
    width, height = ai_router.resolve_dimensions(payload.aspect_ratio)

    # Apply style modifier if requested
    effective_prompt = payload.prompt
    if payload.style and payload.style.lower() in STYLE_PROMPTS:
        effective_prompt = f"{payload.prompt}, {STYLE_PROMPTS[payload.style.lower()]}"

    gen_input = GenerationInput(
        prompt=effective_prompt,
        aspect_ratio=payload.aspect_ratio,
        width=width,
        height=height,
        seed=payload.seed,
    )

    # Gate 8: Inference Execution with Automatic Fallback
    try:
        result = await ai_router.execute(payload.model, gen_input)
    except Exception as e:
        logger.error(f"Generation failed across all providers: {e}. Executing atomic refund.")
        try:
            await queries.refund_credit(
                user_id=user_id,
                cost=credit_cost,
                gen_id=gen_id,
                error_code=str(e)[:60]
            )
        except Exception as refund_err:
            logger.error(f"Refund credit execution error: {refund_err}")

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Inference provider encountered an error. Your credit has been automatically refunded."
        )

    # Finalize generation record in database
    await queries.finalize_generation(
        gen_id=gen_id,
        estimated_cost_usd=result.estimated_cost_usd,
        latency_ms=result.latency_ms
    )

    # Return binary image stream directly to Flutter client
    return Response(
        content=result.image_bytes,
        media_type=result.mime_type,
        headers={
            "X-Generation-ID": gen_id,
            "X-Model-Used": payload.model,
            "X-Provider-Used": result.provider_name,
            "X-Latency-Ms": str(result.latency_ms),
            "Cache-Control": "no-store, must-revalidate",
        }
    )
