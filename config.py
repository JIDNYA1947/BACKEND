"""
Central configuration module.

All configuration is read from environment variables (optionally loaded
from a local .env file via python-dotenv). Nothing here is hardcoded
that should be a secret, and the app must never crash if .env is missing.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env if present. Silent no-op if the file doesn't exist -
# the app must still run using OS environment variables / defaults.
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=False)


def _get_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _get_int(name: str, default: int) -> int:
    val = os.getenv(name)
    if val is None or val.strip() == "":
        return default
    try:
        return int(val)
    except ValueError:
        return default


class Settings:
    """Runtime settings, all sourced from environment variables."""

    # --- General ---
    APP_NAME: str = "Schemes & Integrations Backend"
    APP_DIR: Path = Path(__file__).resolve().parent
    DATA_DIR: Path = APP_DIR / "data"
    SCHEMES_FILE: Path = DATA_DIR / "schemes.json"

    # --- Database ---
    DATABASE_PATH: str = os.getenv("DATABASE_PATH", str(BASE_DIR / "app_data.db"))

    # --- Demo / Twilio ---
    DEMO_MODE: bool = _get_bool("DEMO_MODE", True)
    TWILIO_ACCOUNT_SID: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    TWILIO_WHATSAPP_FROM: str = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")

    # --- Scheduler ---
    SURVEY_INTERVAL_MINUTES: int = _get_int("SURVEY_INTERVAL_MINUTES", 3)

    # --- Mentor alert rule ---
    CONCERNING_ANSWER_ALERT_THRESHOLD: int = _get_int("CONCERNING_ANSWER_ALERT_THRESHOLD", 2)

    MANDATORY_DISCLAIMER: str = "Final eligibility is subject to government/lender verification."


settings = Settings()
