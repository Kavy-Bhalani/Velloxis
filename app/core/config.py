from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from functools import lru_cache

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    APP_NAME: str = "Velloxis Control Plane"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    PORT: int = 8080

    # Database
    DATABASE_URL: str = Field(default="postgresql://postgres:postgres@localhost:5432/velloxis")
    DB_POOL_MIN_SIZE: int = 1
    DB_POOL_MAX_SIZE: int = 10

    # AI Provider Keys
    FAL_KEY: str = Field(default="")
    DEEPINFRA_API_KEY: str = Field(default="")

    # Security & Firebase
    FIREBASE_PROJECT_ID: str = Field(default="velloxis-app")
    DEV_BYPASS_AUTH: bool = Field(default=False)
    ENFORCE_APP_CHECK: bool = Field(default=False)

    # AdMob SSV
    ADMOB_KEY_URL: str = Field(default="https://gstatic.com/admob/reward/verifier-keys.json")

    # Guardrails & Cost Controls
    GENERATION_ENABLED: bool = True
    MAX_PROMPT_LENGTH: int = 1000
    MAX_DAILY_GENERATIONS: int = 20
    MAX_DAILY_REWARDS: int = 10
    RATE_LIMIT_PER_MINUTE: int = 10

    # Model Cost mapping (credits)
    FAST_MODEL_CREDIT_COST: int = 1
    QUALITY_MODEL_CREDIT_COST: int = 2
    TURBO_MODEL_CREDIT_COST: int = 1
    FLUX_MODEL_CREDIT_COST: int = 1
    JANUS_MODEL_CREDIT_COST: int = 1

@lru_cache
def get_settings() -> Settings:
    return Settings()
