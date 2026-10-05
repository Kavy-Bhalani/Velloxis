import base64
import time
import logging
from typing import Optional, Dict, Any
import httpx
from app.providers.base import AIProvider, GenerationInput, GenerationResult
from app.core.config import get_settings

logger = logging.getLogger("velloxis.provider.deepinfra")
settings = get_settings()

class DeepInfraProvider(AIProvider):
    # Model Cost estimations per generation (USD)
    MODEL_COSTS = {
        "stabilityai/sdxl-turbo": 0.0003,
        "black-forest-labs/FLUX-1-schnell": 0.0006,
        "deepseek-ai/Janus-Pro-1B": 0.0005,
    }

    def __init__(self, api_key: str | None = None, model_id: str = "stabilityai/sdxl-turbo"):
        self.api_key = api_key or settings.DEEPINFRA_API_KEY
        self.model_id = model_id

    async def is_healthy(self) -> bool:
        return bool(self.api_key)

    async def _try_openai_images(self, client: httpx.AsyncClient, payload: GenerationInput) -> Optional[bytes]:
        """
        DeepInfra OpenAI-compatible endpoint: https://api.deepinfra.com/v1/openai/images/generations
        Official endpoint for black-forest-labs/FLUX-1-schnell and deepseek-ai/Janus-Pro-1B.
        """
        url = "https://api.deepinfra.com/v1/openai/images/generations"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        # Janus architecture natively runs on 384x384; FLUX supports multi-aspect resolutions
        size = "384x384" if "Janus" in self.model_id else f"{payload.width}x{payload.height}"

        body: dict = {
            "model": self.model_id,
            "prompt": payload.prompt,
            "size": size,
            "response_format": "b64_json",
            "n": 1,
        }

        resp = await client.post(url, headers=headers, json=body)
        if resp.status_code != 200:
            # If custom size was rejected for FLUX, retry once with standard 1024x1024
            if size != "1024x1024" and "Janus" not in self.model_id:
                logger.warning(f"DeepInfra OpenAI images failed with size {size} ({resp.status_code}). Retrying with 1024x1024...")
                body["size"] = "1024x1024"
                resp = await client.post(url, headers=headers, json=body)

        if resp.status_code != 200:
            logger.warning(f"DeepInfra OpenAI images ({self.model_id}) returned {resp.status_code}: {resp.text}")
            return None

        data = resp.json()
        data_items = data.get("data", [])
        if data_items:
            first = data_items[0]
            if "b64_json" in first and first["b64_json"]:
                return base64.b64decode(first["b64_json"])
            elif "url" in first and first["url"]:
                img_res = await client.get(first["url"])
                if img_res.status_code == 200:
                    return img_res.content

        images = data.get("images", [])
        if images:
            raw = images[0]
            if "," in raw:
                raw = raw.split(",", 1)[1]
            return base64.b64decode(raw)

        return None

    async def _try_native_inference(self, client: httpx.AsyncClient, payload: GenerationInput) -> Optional[bytes]:
        """
        DeepInfra native inference endpoint: https://api.deepinfra.com/v1/inference/{model_id}
        Direct endpoint for stabilityai/sdxl-turbo.
        """
        url = f"https://api.deepinfra.com/v1/inference/{self.model_id}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        steps = min(payload.num_inference_steps, 4) if "turbo" in self.model_id.lower() else payload.num_inference_steps
        body: dict = {
            "prompt": payload.prompt,
            "width": payload.width,
            "height": payload.height,
            "num_inference_steps": steps,
        }
        if payload.seed is not None:
            body["seed"] = payload.seed

        resp = await client.post(url, headers=headers, json=body)
        if resp.status_code != 200:
            logger.warning(f"DeepInfra native inference ({self.model_id}) returned {resp.status_code}: {resp.text}")
            return None

        data = resp.json()
        images = data.get("images", [])
        if images:
            raw = images[0]
            if "," in raw:
                raw = raw.split(",", 1)[1]
            return base64.b64decode(raw)

        data_items = data.get("data", [])
        if data_items:
            first = data_items[0]
            if "b64_json" in first and first["b64_json"]:
                return base64.b64decode(first["b64_json"])

        return None

    async def generate(self, payload: GenerationInput) -> GenerationResult:
        if not self.api_key:
            raise ValueError(f"DeepInfra API key is not configured for {self.model_id}.")

        start_time = time.time()
        image_bytes: Optional[bytes] = None

        async with httpx.AsyncClient(timeout=45.0) as client:
            # For FLUX and Janus, OpenAI images generations endpoint is primary
            if "FLUX" in self.model_id or "Janus" in self.model_id:
                image_bytes = await self._try_openai_images(client, payload)
                if not image_bytes:
                    logger.info(f"OpenAI endpoint unsuccessful for {self.model_id}. Trying native inference fallback...")
                    image_bytes = await self._try_native_inference(client, payload)
            else:
                # For SDXL-Turbo, native inference endpoint is primary
                image_bytes = await self._try_native_inference(client, payload)
                if not image_bytes:
                    logger.info(f"Native inference unsuccessful for {self.model_id}. Trying OpenAI images fallback...")
                    image_bytes = await self._try_openai_images(client, payload)

        if not image_bytes:
            raise RuntimeError(f"DeepInfra could not generate image for model {self.model_id}.")

        latency_ms = int((time.time() - start_time) * 1000)
        estimated_cost = self.MODEL_COSTS.get(self.model_id, 0.0005)

        return GenerationResult(
            image_bytes=image_bytes,
            mime_type="image/jpeg",
            latency_ms=latency_ms,
            estimated_cost_usd=estimated_cost,
            provider_name="deepinfra",
            model_name=self.model_id,
        )
