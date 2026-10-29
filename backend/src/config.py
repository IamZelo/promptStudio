"""Configuration and environment management.

Handles API keys, default model names, and GenAI client instantiation.
"""

from __future__ import annotations

import os
import json
from urllib import error, request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()


def _positive_env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


@dataclass
class AppConfig:
    """Application configuration values."""
    gemini_api_key: Optional[str] = os.getenv("GEMINI_API_KEY")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    llama_cpp_model: str = os.getenv("LLAMA_CPP_MODEL", "local-model")
    llama_cpp_base_url: str = os.getenv("LLAMA_CPP_BASE_URL", "http://localhost:8080")
    llama_cpp_timeout: int = _positive_env_int("LLAMA_CPP_TIMEOUT", 120)
    llama_cpp_max_tokens: int = _positive_env_int("LLAMA_CPP_MAX_TOKENS", 12000)
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

    from google import genai
    return genai.Client(api_key=key)


class LlamaCppClient:
    """Client for llama.cpp's OpenAI-compatible server API."""

    def __init__(self, base_url: str, timeout: int = 120, max_tokens: int = 12000):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_tokens = max(1024, max_tokens)

    def generate(self, model: str, system: str, prompt: str, schema: dict) -> str:
        schema_text = json.dumps(schema, indent=2)
        payload = json.dumps({
            "model": model,
            "stream": False,
            "temperature": 0.1,
            "max_tokens": self.max_tokens,
            "response_format": {"type": "json_object", "schema": schema},
            "messages": [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": (
                        f"{prompt}\n\nReturn only JSON matching this schema:\n{schema_text}"
                    ),
                },
            ],
        }).encode("utf-8")
        http_request = request.Request(
            f"{self.base_url}/v1/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(http_request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"llama.cpp request failed: {exc}") from exc

        if body.get("error"):
            raise RuntimeError(f"llama.cpp server error: {body['error']}")
        choices = body.get("choices", [])
        content = choices[0].get("message", {}).get("content") if choices else None
        if not content:
            raise RuntimeError("llama.cpp response did not contain message content")
        return content
