"""Application configuration.

A single source of truth for environment-driven settings. Reads from the
process environment (populated via docker-compose `env_file`) with sensible
defaults so the app can run locally without a full environment.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Constants that govern the scanning/upload business rules. Kept here so both
# the API (upload limit) and the worker (scan threshold) read from one place.
MAX_UPLOAD_SIZE = 100 * 1024 * 1024  # 100 MB hard upload cap
SCAN_SIZE_LIMIT = 10 * 1024 * 1024  # 10 MB "suspicious" threshold used by the scanner

# Default redis used both as the Celery broker and result backend.
_DEFAULT_REDIS_URL = "redis://backend-redis:6379/0"


class Settings:
    """Environment-driven settings. Constructed once at import time."""

    def __init__(self) -> None:
        # Postgres connection parts (compose host `backend-db`).
        self.postgres_user: str = os.environ.get("POSTGRES_USER", "postgres")
        self.postgres_password: str = os.environ.get("POSTGRES_PASSWORD", "postgres")
        self.postgres_db: str = os.environ.get("POSTGRES_DB", "test")
        self.postgres_host: str = os.environ.get("POSTGRES_HOST", "backend-db")
        # Official postgres image listens on 5432 inside the container.
        self.pgport: str = os.environ.get("PGPORT", "5432")

        # Redis / Celery: honour either REDIS_URL or CELERY_BROKER_URL to avoid
        # the previous inconsistency between the two variables.
        self.redis_url: str = (
            os.environ.get("REDIS_URL")
            or os.environ.get("CELERY_BROKER_URL")
            or _DEFAULT_REDIS_URL
        )

        # Local file storage. Defaults to /data/files (a dedicated volume mount
        # in docker-compose), keeping uploads out of the code directory.
        self.storage_dir: Path = Path(
            os.environ.get("STORAGE_DIR", "/data/files")
        )

        # CORS origins for the API (frontend runs on :3000 under /test).
        self.cors_origins: list[str] = [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]

    @property
    def database_url(self) -> str:
        """Async SQLAlchemy URL built from the Postgres settings."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.pgport}/{self.postgres_db}"
        )


settings = Settings()
