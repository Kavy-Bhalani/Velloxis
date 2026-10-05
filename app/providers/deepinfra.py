import base64
import time
import logging
import httpx
from app.providers.base import AIProvider, GenerationInput, GenerationResult
from app.core.config import get_settings

logger = logging.getLogger("velloxis.provider.deepinfra")
settings = get_settings()

class DeepInfraProvider(AIProvider):
    def __init__(self, api_key: str | None = None, model_id: str = "black-forest-labs/FLUX-1-schnell"):
        self.api_key = api_key or settings.DEEPINFRA_API_KEY
        self.model_id = model_id
        self.base_url = f"https://api.deepinfra.com/v1/inference/{self.model_id}"

    async def is_healthy(self) -> bool:
        return bool(self.api_key)

    async def generate(self, payload: GenerationInput) -> GenerationResult:
        if not self.api_key:
            raise ValueError("DeepInfra API key is not configured.")

        start_time = time.time()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "prompt": payload.prompt,
            "width": payload.width,
            "height": payload.height,
            "num_inference_steps": payload.num_inference_steps,
        }
        if payload.seed is not None:
            body["seed"] = payload.seed

        async with httpx.AsyncClient(timeout=35.0) as client:
            resp = await client.post(self.base_url, headers=headers, json=body)
            if resp.status_code != 200:
                logger.error(f"DeepInfra API failed with status {resp.status_code}: {resp.text}")
                raise RuntimeError(f"DeepInfra inference error: HTTP {resp.status_code}")

            data = resp.json()

        latency_ms = int((time.time() - start_time) * 1000)

        # DeepInfra returns base64 image strings in "images" array
        images = data.get("images", [])
        if not images:
            raise RuntimeError("DeepInfra returned empty image payload.")

        raw_img = images[0]
        # Handle data:image/...;base64, prefix if present
        if "," in raw_img:
            raw_img = raw_img.split(",", 1)[1]

        image_bytes = base64.b64decode(raw_img)

        # Cost estimation: ~0.0006 per 4-step FLUX Schnell generation
        cost_info = data.get("inference_status", {})
        estimated_cost = float(cost_info.get("cost", 0.0006))

        return GenerationResult(
            image_bytes=image_bytes,
            mime_type="image/jpeg",
            latency_ms=latency_ms,
            estimated_cost_usd=estimated_cost,
            provider_name="deepinfra",
            model_name=self.model_id,
        )
