"""Общие константы и загрузка конфигурации."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

SCRIPTS_DIR = Path(__file__).resolve().parent
INTEL_DIR = SCRIPTS_DIR.parent
RAW_DIR = INTEL_DIR / "raw"
DIGEST_DIR = INTEL_DIR / "digest"
LOGS_DIR = INTEL_DIR / "logs"
SESSION_PATH = SCRIPTS_DIR / "telegram.session"
DB_PATH = INTEL_DIR / "intel.db"
SOURCES_PATH = INTEL_DIR / "sources.yaml"

load_dotenv(SCRIPTS_DIR / ".env")


def env(key: str, default: str | None = None, required: bool = False) -> str | None:
    value = os.getenv(key, default)
    if required and not value:
        raise RuntimeError(f"Не задана переменная окружения {key} (см. dotenv.example → .env)")
    return value


def env_list(key: str) -> list[str]:
    raw = os.getenv(key, "") or ""
    return [x.strip() for x in raw.split(",") if x.strip()]
