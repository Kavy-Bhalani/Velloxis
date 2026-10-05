from pydantic import BaseModel, Field

class CreditBalanceResponse(BaseModel):
    balance: int = Field(..., description="Available generation credits")
    daily_generations_used: int = Field(..., description="Generations consumed today")
    max_daily_generations: int = Field(..., description="Daily generation cap")
    daily_rewards_used: int = Field(..., description="Rewarded ads watched today")
    max_daily_rewards: int = Field(..., description="Max rewarded ads allowed per day")

class RewardStatusResponse(BaseModel):
    success: bool
    balance: int
    message: str
