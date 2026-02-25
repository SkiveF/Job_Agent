"""
Configuration centralisée du projet Job Agent.
"""

from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field
import yaml
from loguru import logger
import sys


# ── Paths ──────────────────────────────────────────────────────────
ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT_DIR / "config"
CRITERIA_PATH = CONFIG_DIR / "criteria.yaml"
PROFILE_PATH = CONFIG_DIR / "profile.yaml"
CV_DIR = ROOT_DIR / "cv"


# ── Logger ─────────────────────────────────────────────────────────
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | <cyan>{name}</cyan> - {message}",
    level="INFO",
)
logger.add(
    ROOT_DIR / "logs" / "job_agent.log",
    rotation="1 day",
    retention="7 days",
    level="DEBUG",
)


# ── Settings (.env) ───────────────────────────────────────────────
class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./job_agent.db"
    application_mode: str = Field(default="semi-auto", pattern="^(semi-auto|full-auto)$")
    min_delay: int = 3
    max_delay: int = 8
    proxy_url: str | None = None
    discord_webhook: str | None = None
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None

    class Config:
        env_file = str(ROOT_DIR / ".env")
        env_file_encoding = "utf-8"


settings = Settings()


# ── YAML loaders ──────────────────────────────────────────────────
def load_criteria() -> dict:
    """Charge les critères de recherche depuis criteria.yaml."""
    if not CRITERIA_PATH.exists():
        logger.error(f"Fichier critères introuvable : {CRITERIA_PATH}")
        raise FileNotFoundError(f"{CRITERIA_PATH} manquant")
    with open(CRITERIA_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    logger.info("Critères de recherche chargés")
    return data


def load_profile() -> dict:
    """Charge le profil utilisateur depuis profile.yaml."""
    if not PROFILE_PATH.exists():
        logger.error(f"Fichier profil introuvable : {PROFILE_PATH}")
        raise FileNotFoundError(f"{PROFILE_PATH} manquant")
    with open(PROFILE_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    logger.info("Profil utilisateur chargé")
    return data
