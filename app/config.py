"""Runtime settings, read from environment variables (and a local .env file)."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _split(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    openai_api_key: str | None = field(default_factory=lambda: os.getenv("OPENAI_API_KEY") or None)
    openai_model: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    database_url: str = field(
        default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///budget_buddy.db")
    )
    receipt_dir: Path = field(default_factory=lambda: Path(os.getenv("RECEIPT_DIR", "receipts")))
    cors_origins: list[str] = field(default_factory=lambda: _split(os.getenv("CORS_ORIGINS", "*")))
    max_upload_bytes: int = 10 * 1024 * 1024
    default_budget: float = 1500.0
    default_currency: str = "USD"


settings = Settings()
