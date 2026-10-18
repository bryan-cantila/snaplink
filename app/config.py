"""Central configuration. Every value comes from the environment (or .env).

Nothing is hardcoded: a fresh clone only needs a .env (see .env.example)
or the equivalent environment variables to boot.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = (
        "postgresql+asyncpg://snaplink:snaplink@localhost:5432/snaplink"
    )
    JWT_SECRET: str  # required — the app refuses to boot without it
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60
    # Optional. When set and reachable, redirect lookups are cached in Redis
    # (1h TTL). When unset or unreachable, the API falls back to the database.
    REDIS_URL: str | None = None
    # Public base URL used to build `short_url` in API responses.
    BASE_URL: str = "http://localhost:8000"
    RATE_LIMIT_ENABLED: bool = True


settings = Settings()
