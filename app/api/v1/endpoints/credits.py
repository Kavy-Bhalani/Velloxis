from fastapi import APIRouter, Depends
from app.core.security import verify_firebase_token
from app.schemas.credits import CreditBalanceResponse
from app.db import queries

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
