import time
import logging
import httpx
from app.providers.base import AIProvider, GenerationInput, GenerationResult
from app.core.config import get_settings

logger = logging.getLogger("velloxis.provider.fal")
settings = get_settings()

class FalProvider(AIProvider):
    def __init__(self, api_key: str | None = None, model_id: str = "fal-ai/sana"):
        self.api_key = api_key or settings.FAL_KEY
        self.model_id = model_id
        self.base_url = f"https://fal.run/{self.model_id}"

    async def is_healthy(self) -> bool:
        return bool(self.api_key)

    async def generate(self, payload: GenerationInput) -> GenerationResult:
        if not self.api_key:
            raise ValueError("fal.ai API key is not configured.")

        start_time = time.time()
        headers = {
            "Authorization": f"Key {self.api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "prompt": payload.prompt,
            "image_size": {
                "width": payload.width,
                "height": payload.height,
            },
            "num_inference_steps": payload.num_inference_steps,
        }
        if payload.seed is not None:
            body["seed"] = payload.seed

        async with httpx.AsyncClient(timeout=40.0) as client:
            resp = await client.post(self.base_url, headers=headers, json=body)
            if resp.status_code != 200:
                logger.error(f"fal.ai API error HTTP {resp.status_code}: {resp.text}")
                raise RuntimeError(f"fal.ai inference error: HTTP {resp.status_code}")

            data = resp.json()

            images = data.get("images", [])
            if not images:
                raise RuntimeError("fal.ai returned empty image array.")

            image_url = images[0].get("url")
            content_type = images[0].get("content_type", "image/jpeg")

            if not image_url:
                raise RuntimeError("fal.ai response did not contain image url.")

            # Ephemeral fetch of image bytes - server does NOT store it permanently
            img_resp = await client.get(image_url)
            if img_resp.status_code != 200:
                raise RuntimeError(f"Failed to fetch image bytes from fal CDN: HTTP {img_resp.status_code}")

            image_bytes = img_resp.content

        latency_ms = int((time.time() - start_time) * 1000)
        # Sana is ~$0.001 per megapixel; FLUX Schnell is ~$0.0015
        estimated_cost = 0.0010 if "sana" in self.model_id else 0.0015

        return GenerationResult(
            image_bytes=image_bytes,
            mime_type=content_type,
            latency_ms=latency_ms,
            estimated_cost_usd=estimated_cost,
            provider_name="fal",
            model_name=self.model_id,
        )
