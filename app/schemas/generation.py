from typing import Optional, Literal
from pydantic import BaseModel, Field

class GenerationRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=1000, description="User descriptive prompt")
    model: Literal["fast", "quality"] = Field(default="fast", description="Model speed/quality tier")
    aspect_ratio: Literal["1:1", "16:9", "9:16", "4:3", "3:4"] = Field(default="1:1")
    style: Optional[str] = Field(default=None, description="Optional style preset modifier (e.g. 'anime', 'cinematic')")
    seed: Optional[int] = Field(default=None, description="Optional seed for reproducibility")

class GenerationMetadata(BaseModel):
    generation_id: str
    status: str
    model: str
    aspect_ratio: str
    latency_ms: int
    created_at: str
