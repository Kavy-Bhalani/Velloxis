import asyncio
import base64
from typing import Optional
from app.providers.base import AIProvider, GenerationInput, GenerationResult

# Minimal valid 1x1 WebP image byte array
TINY_WEBP_BASE64 = "UklGRhoAAABXRUJQVlA4TA0AAAAvAAAAEAcQERGIiP4HAA=="

class MockAIProvider(AIProvider):
    """
    Mock AI Provider for development and automated test suites.
    """
    def __init__(
        self,
        provider_name: str = "mock_provider",
        model_name: str = "stabilityai/sdxl-turbo",
        should_fail: bool = False,
    ):
        self.provider_name = provider_name
        self.model_name = model_name
        self.should_fail = should_fail

    async def is_healthy(self) -> bool:
        return not self.should_fail

    async def generate(self, payload: GenerationInput) -> GenerationResult:
        await asyncio.sleep(0.02)  # Tiny artificial async delay
        if self.should_fail:
            raise RuntimeError(f"Simulated failure from {self.provider_name} ({self.model_name})")

        image_bytes = base64.b64decode(TINY_WEBP_BASE64)
        return GenerationResult(
            image_bytes=image_bytes,
            mime_type="image/webp",
            latency_ms=20,
            estimated_cost_usd=0.0003,
            provider_name=self.provider_name,
            model_name=self.model_name,
        )
