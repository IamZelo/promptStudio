"""Configuration and environment management.

Handles API keys, default model names, and GenAI client instantiation.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()


@dataclass
class AppConfig:
    """Application configuration values."""
    gemini_api_key: Optional[str] = os.getenv("GEMINI_API_KEY")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
    default_output_dir: Path = Path(os.getenv("OUTPUT_DIR", "output"))

    @property
    def has_valid_api_key(self) -> bool:
        """Returns True if a non-placeholder API key is configured."""
        if not self.gemini_api_key:
            return False
        return self.gemini_api_key.strip() != "your_gemini_api_key_here"


def get_genai_client(api_key: Optional[str] = None):
    """Instantiates and returns the official Google GenAI SDK client.

    Returns:
        google.genai.Client instance or None if key is missing/invalid.
    """
    key = api_key or os.getenv("GEMINI_API_KEY")
    if not key or key.strip() == "your_gemini_api_key_here":
        return None

    try:
        from google import genai
        return genai.Client(api_key=key)
    except Exception:
        return None
