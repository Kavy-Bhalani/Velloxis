import logging
from typing import Dict, List, Tuple
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
        # Configure DeepInfra models:
        # 1. Main/Default: stabilityai/sdxl-turbo
        # 2. Secondary: black-forest-labs/FLUX-1-schnell
        # 3. Tertiary: deepseek-ai/Janus-Pro-1B
        if settings.DEEPINFRA_API_KEY:
            self.deepinfra_sdxl = DeepInfraProvider(model_id="stabilityai/sdxl-turbo")
            self.deepinfra_flux = DeepInfraProvider(model_id="black-forest-labs/FLUX-1-schnell")
            self.deepinfra_janus = DeepInfraProvider(model_id="deepseek-ai/Janus-Pro-1B")
        else:
            logger.info("DeepInfra API key not configured. Using MockAIProvider for DeepInfra models.")
            self.deepinfra_sdxl = MockAIProvider("mock_deepinfra", "stabilityai/sdxl-turbo")
            self.deepinfra_flux = MockAIProvider("mock_deepinfra", "black-forest-labs/FLUX-1-schnell")
            self.deepinfra_janus = MockAIProvider("mock_deepinfra", "deepseek-ai/Janus-Pro-1B")

        # Configure fal.ai fallback models:
        if settings.FAL_KEY:
            self.fal_flux = FalProvider(model_id="fal-ai/flux/schnell")
            self.fal_sana = FalProvider(model_id="fal-ai/sana")
        elif not settings.DEEPINFRA_API_KEY:
            self.fal_flux = MockAIProvider("mock_fal", "fal-ai/flux/schnell")
            self.fal_sana = MockAIProvider("mock_fal", "fal-ai/sana")
        else:
            self.fal_flux = None
            self.fal_sana = None

    def resolve_dimensions(self, aspect_ratio: str) -> Tuple[int, int]:
        return ASPECT_RATIO_DIMENSIONS.get(aspect_ratio, (1024, 1024))

    def get_provider_details(self, model_alias: str) -> Tuple[str, str]:
        """Returns (provider_name, provider_model_id) for credit reservation & logging."""
        alias = model_alias.lower()
        if alias in ("quality", "sana"):
            return "fal", "fal-ai/sana"
        elif alias in ("flux", "flux-schnell"):
            return "deepinfra", "black-forest-labs/FLUX-1-schnell"
        elif alias in ("janus", "janus-pro"):
            return "deepinfra", "deepseek-ai/Janus-Pro-1B"
        # Default is SDXL-Turbo
        return "deepinfra", "stabilityai/sdxl-turbo"

    def get_fallback_chain(self, model_alias: str) -> List[AIProvider]:
        """
        Builds the fallback execution chain strictly respecting the user's selected model:
        1. Flux: DeepInfra FLUX.1 [schnell] -> fal.ai FLUX (Keeps FLUX fidelity; NEVER downgrades to SDXL Turbo)
        2. Janus: DeepInfra Janus-Pro-1B (NEVER downgrades to SDXL Turbo)
        3. Quality: fal.ai Sana -> DeepInfra FLUX (Preserves high quality; NEVER downgrades to SDXL Turbo)
        4. Turbo: DeepInfra SDXL Turbo
        5. Fast (Default): DeepInfra SDXL Turbo -> DeepInfra FLUX
        """
        alias = model_alias.lower()
        if alias in ("flux", "flux-schnell"):
            chain = [self.deepinfra_flux, self.fal_flux]
        elif alias in ("janus", "janus-pro"):
            chain = [self.deepinfra_janus]
        elif alias in ("quality", "sana"):
            primary = self.fal_sana if self.fal_sana else self.deepinfra_flux
            chain = [primary, self.fal_flux]
        elif alias in ("turbo", "sdxl", "sdxl-turbo"):
            chain = [self.deepinfra_sdxl, self.deepinfra_flux]
        else:
            # Default "fast" (SDXL Turbo with FLUX fallback)
            chain = [self.deepinfra_sdxl, self.deepinfra_flux]

        # Filter out None providers (e.g. if fal.ai key not configured)
        return [p for p in chain if p is not None]

    async def execute(self, model_alias: str, payload: GenerationInput) -> GenerationResult:
        chain = self.get_fallback_chain(model_alias)
        errors: List[str] = []

        for provider in chain:
            provider_name = getattr(provider, "provider_name", provider.__class__.__name__)
            model_id = getattr(provider, "model_id", getattr(provider, "model_name", "unknown"))
            try:
                logger.info(f"Routing '{model_alias}' to {provider_name} [{model_id}]")
                result = await provider.generate(payload)
                logger.info(f"Generation succeeded using {result.provider_name} [{result.model_name}] in {result.latency_ms}ms")
                return result
            except Exception as e:
                logger.warning(f"Provider {provider_name} [{model_id}] failed: {e}. Attempting next fallback in chain...")
                errors.append(f"{model_id}: {str(e)}")

        error_summary = "; ".join(errors)
        logger.error(f"All models in fallback chain failed for alias '{model_alias}': {error_summary}")
        raise RuntimeError(f"All inference providers failed in fallback chain: {error_summary}")

ai_router = AIRouter()
