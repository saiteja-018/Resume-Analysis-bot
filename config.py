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
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
TOKENROUTER_API_KEY = os.getenv("TOKENROUTER_API_KEY", "")

# AI settings
AI_API_KEY = GROQ_API_KEY or TOKENROUTER_API_KEY
AI_PROVIDER = "groq" if GROQ_API_KEY else "tokenrouter"
AI_MODEL = os.getenv("AI_MODEL", "openai/gpt-oss-120b" if GROQ_API_KEY else "z-ai/glm-5.3-free")
AI_BASE_URL = os.getenv(
    "AI_BASE_URL",
    "https://api.groq.com/openai/v1" if GROQ_API_KEY else "https://api.tokenrouter.com/v1",
)
AI_TIMEOUT = 60  # seconds
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
    if not AI_API_KEY:
        errors.append("Neither GROQ_API_KEY nor TOKENROUTER_API_KEY is set in .env")
    if errors:
        for error in errors:
            print(f"[CONFIG ERROR] {error}")
        sys.exit(1)
