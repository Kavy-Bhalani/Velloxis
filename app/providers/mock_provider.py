import base64
import time
from app.providers.base import AIProvider, GenerationInput, GenerationResult

# Minimal valid 1x1 WebP image byte array
TINY_WEBP_BASE64 = "UklGRhoAAABXRUJQVlA4TA0AAAAvAAAAEAcQERGIiP4HAA=="

class MockAIProvider(AIProvider):
    """
    Mock AI Provider for development and automated test suites.
    """
    def __init__(self, provider_name: str = "mock_provider", model_name: str = "mock-flux-schnell"):
        self.provider_name = provider_name
        self.model_name = model_name

    async def is_healthy(self) -> bool:
        return True

    async def generate(self, payload: GenerationInput) -> GenerationResult:
        time.sleep(0.05)  # Tiny artificial delay
        image_bytes = base64.b64decode(TINY_WEBP_BASE64)
        return GenerationResult(
            image_bytes=image_bytes,
            mime_type="image/webp",
            latency_ms=50,
            estimated_cost_usd=0.0005,
            provider_name=self.provider_name,
            model_name=self.model_name,
        )
