from abc import ABC, abstractmethod
from typing import Optional
from pydantic import BaseModel

class GenerationInput(BaseModel):
    prompt: str
    aspect_ratio: str = "1:1"  # "1:1", "16:9", "9:16", "4:3", "3:4"
    width: int = 1024
    height: int = 1024
    seed: Optional[int] = None
    num_inference_steps: int = 4

class GenerationResult(BaseModel):
    image_bytes: bytes
    mime_type: str = "image/webp"
    latency_ms: int
    estimated_cost_usd: float
    provider_name: str
    model_name: str

class AIProvider(ABC):
    @abstractmethod
    async def generate(self, payload: GenerationInput) -> GenerationResult:
        """Call AI inference provider and return standard GenerationResult."""
        pass

    @abstractmethod
    async def is_healthy(self) -> bool:
        """Check provider health and availability."""
        pass
