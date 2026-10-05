from fastapi import APIRouter
from app.core.config import get_settings

router = APIRouter()
settings = get_settings()

@router.get("/config")
async def get_app_config():
    """
    Returns public backend configuration, model costs, and aspect ratio definitions.
    Allows dynamic app tuning without requiring an immediate APK update.
    """
    return {
        "generation_enabled": settings.GENERATION_ENABLED,
        "models": {
            "fast": {
                "name": "SDXL Turbo",
                "badge": "⚡ Turbo (Default)",
                "provider": "deepinfra",
                "model_id": "stabilityai/sdxl-turbo",
                "credit_cost": settings.FAST_MODEL_CREDIT_COST,
                "description": "Ultra-fast real-time synthesis (1-4 steps). Primary default model.",
                "fallback_chain": ["FLUX.1 [schnell]"],
            },
            "flux": {
                "name": "FLUX.1 Schnell",
                "badge": "🔥 FLUX",
                "provider": "deepinfra",
                "model_id": "black-forest-labs/FLUX-1-schnell",
                "credit_cost": settings.FLUX_MODEL_CREDIT_COST,
                "description": "State-of-the-art fast diffusion with high detail and text adherence.",
                "fallback_chain": ["fal.ai FLUX"],
            },
            "janus": {
                "name": "Janus-Pro 1B",
                "badge": "🧠 DeepSeek",
                "provider": "deepinfra",
                "model_id": "deepseek-ai/Janus-Pro-1B",
                "credit_cost": settings.JANUS_MODEL_CREDIT_COST,
                "description": "DeepSeek's unified multimodal autoregressive generation architecture.",
                "fallback_chain": [],
            },
            "quality": {
                "name": "Quality Sana",
                "badge": "✨ Sana",
                "provider": "fal",
                "model_id": "fal-ai/sana",
                "credit_cost": settings.QUALITY_MODEL_CREDIT_COST,
                "description": "Enhanced detail, typography, and artistic rendering.",
                "fallback_chain": ["FLUX.1 [schnell]"],
            }
        },
        "aspect_ratios": [
            {"id": "1:1", "label": "Square (1:1)", "icon": "crop_square"},
            {"id": "9:16", "label": "Story / Reel (9:16)", "icon": "crop_portrait"},
            {"id": "16:9", "label": "Landscape (16:9)", "icon": "crop_landscape"},
            {"id": "4:3", "label": "Classic (4:3)", "icon": "crop_3_2"},
            {"id": "3:4", "label": "Portrait (3:4)", "icon": "crop_5_4"},
        ],
        "styles": [
            {"id": "photorealistic", "label": "Photorealistic", "icon": "camera_alt"},
            {"id": "anime", "label": "Anime", "icon": "palette"},
            {"id": "cinematic", "label": "Cinematic", "icon": "movie"},
            {"id": "3d", "label": "3D Render", "icon": "view_in_ar"},
            {"id": "fantasy", "label": "Fantasy Art", "icon": "auto_awesome"},
            {"id": "minimalist", "label": "Minimalist", "icon": "brush"},
        ],
        "limits": {
            "max_prompt_length": settings.MAX_PROMPT_LENGTH,
            "max_daily_generations": settings.MAX_DAILY_GENERATIONS,
            "max_daily_rewards": settings.MAX_DAILY_REWARDS,
        }
    }
