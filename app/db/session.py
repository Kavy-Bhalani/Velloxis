import logging
from typing import Optional
import asyncpg
from app.core.config import get_settings

logger = logging.getLogger("velloxis.db")
settings = get_settings()

class DatabaseSessionManager:
    def __init__(self):
        self._pool: Optional[asyncpg.Pool] = None

    async def init(self):
        if not self._pool:
            logger.info("Initializing asyncpg connection pool...")
            try:
                self._pool = await asyncpg.create_pool(
                    dsn=settings.DATABASE_URL,
                    min_size=settings.DB_POOL_MIN_SIZE,
                    max_size=settings.DB_POOL_MAX_SIZE,
                    command_timeout=15.0,
                )
                logger.info("Database connection pool established.")
            except Exception as e:
                logger.warning(f"Database connection pool failed to initialize (running in disconnected mode?): {e}")

    async def close(self):
        if self._pool:
            logger.info("Closing asyncpg connection pool...")
            await self._pool.close()
            self._pool = None

    @property
    def pool(self) -> Optional[asyncpg.Pool]:
        return self._pool

db_manager = DatabaseSessionManager()
