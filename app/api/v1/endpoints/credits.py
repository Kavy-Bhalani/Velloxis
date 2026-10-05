import uuid
import logging
from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, status
from app.core.security import verify_firebase_token
from app.core.config import get_settings
from app.schemas.credits import CreditBalanceResponse
from app.db import queries

logger = logging.getLogger("velloxis.api.credits")
settings = get_settings()

router = APIRouter()

@router.get("/credits", response_model=CreditBalanceResponse)
async def get_user_credits(firebase_uid: str = Depends(verify_firebase_token)):
    """
    Returns the authoritative credit balance and daily allowance counters.
    """
    data = await queries.get_credit_balance(firebase_uid)
    return CreditBalanceResponse(
        balance=data["balance"],
        daily_generations_used=data["daily_generations_used"],
        max_daily_generations=data["max_daily_generations"],
        daily_rewards_used=data["daily_rewards_used"],
        max_daily_rewards=data["max_daily_rewards"],
    )

@router.post("/rewards/claim")
async def claim_reward(
    firebase_uid: str = Depends(verify_firebase_token),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    """
    Claims a reward credit (when user watches an ad or completes a reward task).
    Atomically updates the user's credit account in Supabase.
    """
    tx_id = idempotency_key if idempotency_key else str(uuid.uuid4())
    logger.info(f"User {firebase_uid} claiming reward credit (tx_id={tx_id})")

    result = await queries.process_admob_reward(
        firebase_uid=firebase_uid,
        ssv_transaction_id=f"client_claim_{tx_id}",
        reward_amount=1,
        max_daily_rewards=settings.MAX_DAILY_REWARDS
    )

    if not result.get("success"):
        error_msg = result.get("error", "Daily reward limit reached.")
        logger.warning(f"Reward claim failed for {firebase_uid}: {error_msg}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=error_msg
        )

    logger.info(f"User {firebase_uid} successfully credited. New balance: {result.get('balance')}")
    return {
        "success": True,
        "balance": result.get("balance"),
        "message": "Reward claimed successfully! +1 generation credit added."
    }

@router.post("/credits/grant-welcome")
async def grant_welcome_bonus(
    firebase_uid: str = Depends(verify_firebase_token),
):
    """
    Ensures user has at least 2 credits if their balance is currently 0 (for onboarding/testing).
    """
    data = await queries.get_credit_balance(firebase_uid)
    if data["balance"] == 0:
        result = await queries.process_admob_reward(
            firebase_uid=firebase_uid,
            ssv_transaction_id=f"welcome_reset_{uuid.uuid4()}",
            reward_amount=2,
            max_daily_rewards=settings.MAX_DAILY_REWARDS
        )
        return {
            "success": True,
            "balance": result.get("balance", 2),
            "message": "Welcome credits granted!"
        }
    return {
        "success": True,
        "balance": data["balance"],
        "message": "Existing balance active."
    }
