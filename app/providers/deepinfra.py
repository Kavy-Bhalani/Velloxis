import base64
import time
import logging
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
        # Janus-Pro on DeepInfra uses the OpenAI images generations endpoint for text-to-image
        self.is_openai_endpoint = "Janus" in model_id
        if self.is_openai_endpoint:
            self.base_url = "https://api.deepinfra.com/v1/openai/images/generations"
        else:
            self.base_url = f"https://api.deepinfra.com/v1/inference/{self.model_id}"

    async def is_healthy(self) -> bool:
        return bool(self.api_key)

    async def generate(self, payload: GenerationInput) -> GenerationResult:
        if not self.api_key:
            raise ValueError(f"DeepInfra API key is not configured for {self.model_id}.")

        start_time = time.time()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        # Build payload according to endpoint type
        if self.is_openai_endpoint:
            body = {
                "model": self.model_id,
                "prompt": payload.prompt,
                "size": f"{payload.width}x{payload.height}",
                "response_format": "b64_json",
            }
        else:
            # Native inference endpoint (SDXL Turbo or FLUX Schnell)
            steps = min(payload.num_inference_steps, 4) if "turbo" in self.model_id.lower() else payload.num_inference_steps
            body = {
                "prompt": payload.prompt,
                "width": payload.width,
                "height": payload.height,
                "num_inference_steps": steps,
            }
            if payload.seed is not None:
                body["seed"] = payload.seed

        async with httpx.AsyncClient(timeout=40.0) as client:
            resp = await client.post(self.base_url, headers=headers, json=body)
            if resp.status_code != 200:
                logger.error(f"DeepInfra API ({self.model_id}) failed with status {resp.status_code}: {resp.text}")
                raise RuntimeError(f"DeepInfra inference error on {self.model_id}: HTTP {resp.status_code}")

            data = resp.json()

            # Handle both native DeepInfra schema ("images": [...]) and OpenAI schema ("data": [{"b64_json": ...}])
            image_bytes: bytes | None = None
            images = data.get("images", [])
            if images:
                raw_img = images[0]
                if "," in raw_img:
                    raw_img = raw_img.split(",", 1)[1]
                image_bytes = base64.b64decode(raw_img)
            elif "data" in data and len(data["data"]) > 0:
                first_item = data["data"][0]
                if "b64_json" in first_item:
                    image_bytes = base64.b64decode(first_item["b64_json"])
                elif "url" in first_item:
                    # Ephemeral download from URL if returned
                    img_resp = await client.get(first_item["url"])
                    if img_resp.status_code != 200:
                        raise RuntimeError(f"Failed to fetch image bytes from CDN: HTTP {img_resp.status_code}")
                    image_bytes = img_resp.content

            if not image_bytes:
                raise RuntimeError(f"DeepInfra ({self.model_id}) returned empty or unrecognized image payload.")

        latency_ms = int((time.time() - start_time) * 1000)

        # Cost estimation
        cost_info = data.get("inference_status", {})
        default_cost = self.MODEL_COSTS.get(self.model_id, 0.0005)
        estimated_cost = float(cost_info.get("cost", default_cost))

        return GenerationResult(
            image_bytes=image_bytes,
            mime_type="image/jpeg",
            latency_ms=latency_ms,
            estimated_cost_usd=estimated_cost,
            provider_name="deepinfra",
            model_name=self.model_id,
        )
