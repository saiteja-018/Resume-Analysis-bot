"""
Configuration module for CareerMatch AI bot.
Loads environment variables from .env and exposes them as module-level constants.
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

# =============================================================================
# Required settings
# =============================================================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TOKENROUTER_API_KEY = os.getenv("TOKENROUTER_API_KEY", "")

# =============================================================================
# AI settings
# =============================================================================

AI_MODEL = os.getenv("AI_MODEL", "z-ai/glm-5.3-free")
AI_BASE_URL = "https://api.tokenrouter.com/v1"
AI_TIMEOUT = 120  # seconds
AI_MAX_RETRIES = 2

# =============================================================================
# Text limits
# =============================================================================

MAX_RESUME_LENGTH = int(os.getenv("MAX_RESUME_LENGTH", "8000"))
MAX_JD_LENGTH = int(os.getenv("MAX_JD_LENGTH", "4000"))

# =============================================================================
# Session settings
# =============================================================================

SESSION_TIMEOUT = int(os.getenv("SESSION_TIMEOUT", "3600"))

# =============================================================================
# Telegram limits
# =============================================================================

TELEGRAM_MAX_MESSAGE_LENGTH = 4096

# =============================================================================
# Supported file types
# =============================================================================

SUPPORTED_MIME_TYPES = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
}

MAX_FILE_SIZE_MB = 10


def validate_config():
    """Validate that all required configuration is present."""
    errors = []
    if not TELEGRAM_BOT_TOKEN:
        errors.append("TELEGRAM_BOT_TOKEN is not set in .env")
    if not TOKENROUTER_API_KEY:
        errors.append("TOKENROUTER_API_KEY is not set in .env")
    if errors:
        for error in errors:
            print(f"[CONFIG ERROR] {error}")
        sys.exit(1)
