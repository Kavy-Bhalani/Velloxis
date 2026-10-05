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
                "name": "Fast",
                "badge": "⚡ Schnell",
                "credit_cost": settings.FAST_MODEL_CREDIT_COST,
                "description": "Lightning-fast generation for daily creative iterations.",
            },
            "quality": {
                "name": "Quality",
                "badge": "✨ Sana",
                "credit_cost": settings.QUALITY_MODEL_CREDIT_COST,
                "description": "Enhanced detail, typography, and artistic rendering.",
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
