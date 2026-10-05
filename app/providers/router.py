import logging
from typing import Dict, Tuple
from app.providers.base import AIProvider, GenerationInput, GenerationResult
from app.providers.deepinfra import DeepInfraProvider
from app.providers.fal import FalProvider
from app.providers.mock_provider import MockAIProvider
from app.core.config import get_settings

logger = logging.getLogger("velloxis.airouter")
settings = get_settings()

ASPECT_RATIO_DIMENSIONS: Dict[str, Tuple[int, int]] = {
    "1:1": (1024, 1024),
    "16:9": (1344, 768),
    "9:16": (768, 1344),
    "4:3": (1152, 864),
    "3:4": (864, 1152),
}

class AIRouter:
    def __init__(self):
        # Configure primary and fallback providers based on environment
        if not settings.DEEPINFRA_API_KEY and not settings.FAL_KEY:
            logger.info("No provider API keys set. Using MockAIProvider for development.")
            self.fast_primary = MockAIProvider("mock_deepinfra", "black-forest-labs/FLUX-1-schnell")
            self.fast_fallback = MockAIProvider("mock_fal", "fal-ai/flux/schnell")
            self.quality_primary = MockAIProvider("mock_fal", "fal-ai/sana")
            self.quality_fallback = MockAIProvider("mock_deepinfra", "black-forest-labs/FLUX-1-schnell")
        else:
            self.fast_primary = DeepInfraProvider() if settings.DEEPINFRA_API_KEY else MockAIProvider()
            self.fast_fallback = FalProvider(model_id="fal-ai/flux/schnell") if settings.FAL_KEY else None
            self.quality_primary = FalProvider(model_id="fal-ai/sana") if settings.FAL_KEY else DeepInfraProvider()
            self.quality_fallback = DeepInfraProvider() if settings.DEEPINFRA_API_KEY else None

    def resolve_dimensions(self, aspect_ratio: str) -> Tuple[int, int]:
        return ASPECT_RATIO_DIMENSIONS.get(aspect_ratio, (1024, 1024))

    def get_provider_details(self, model_alias: str) -> Tuple[str, str]:
        """Returns (provider_name, provider_model_id)"""
        if model_alias.lower() == "quality":
            return "fal", "fal-ai/sana"
        return "deepinfra", "black-forest-labs/FLUX-1-schnell"

    async def execute(self, model_alias: str, payload: GenerationInput) -> GenerationResult:
        is_quality = model_alias.lower() == "quality"
        primary: AIProvider = self.quality_primary if is_quality else self.fast_primary
        fallback: AIProvider | None = self.quality_fallback if is_quality else self.fast_fallback

        try:
            logger.info(f"Routing request for alias '{model_alias}' to primary provider {primary.__class__.__name__}")
            return await primary.generate(payload)
        except Exception as e:
            logger.warning(f"Primary provider failed: {e}")
            if fallback:
                logger.info(f"Engaging fallback provider {fallback.__class__.__name__}")
                return await fallback.generate(payload)
            raise e

ai_router = AIRouter()
