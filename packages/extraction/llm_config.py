"""LLM provider settings for extraction — read from environment / .env only."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

PROVIDERS = frozenset({"gemini", "anthropic", "openai", "ollama"})

# Fixed defaults; override with LLM_BASE_URL when set.
DEFAULT_BASE_URLS: dict[str, str] = {
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "anthropic": "https://api.anthropic.com",
    "openai": "https://api.openai.com/v1",
    "ollama": "http://127.0.0.1:11434/v1",
}

# One key slot per cloud provider. Ollama uses a client placeholder, not a secret.
KEY_ENV_BY_PROVIDER: dict[str, str | None] = {
    "gemini": "GEMINI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "ollama": None,
}

_DOTENV_LOADED = False


@dataclass(frozen=True)
class LlmSettings:
    provider: str
    model: str
    api_key: str
    base_url: str


def get_llm_settings(environ: Mapping[str, str] | None = None) -> LlmSettings:
    """Return provider/model/key/base_url. No in-code defaults for provider or model."""

    if environ is None:
        _ensure_dotenv_loaded()
        env: Mapping[str, str] = os.environ
    else:
        env = environ

    provider = (env.get("LLM_PROVIDER") or "").strip().lower()
    if not provider:
        raise RuntimeError("LLM_PROVIDER is missing or empty")

    model = (env.get("LLM_MODEL") or "").strip()
    if not model:
        raise RuntimeError("LLM_MODEL is missing or empty")

    if provider not in PROVIDERS:
        raise RuntimeError(
            f"unsupported LLM_PROVIDER={provider!r}; "
            f"expected one of: {', '.join(sorted(PROVIDERS))}"
        )

    key_var = KEY_ENV_BY_PROVIDER[provider]
    if key_var is None:
        api_key = "ollama"
    else:
        api_key = (env.get(key_var) or "").strip()
        if not api_key:
            raise RuntimeError(f"{key_var} is missing or empty")

    override = (env.get("LLM_BASE_URL") or "").strip()
    base_url = override if override else DEFAULT_BASE_URLS[provider]

    return LlmSettings(
        provider=provider,
        model=model,
        api_key=api_key,
        base_url=base_url,
    )


def _ensure_dotenv_loaded() -> None:
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return
    env_path = ROOT / ".env"
    if env_path.is_file():
        from dotenv import load_dotenv

        load_dotenv(env_path, override=False)
    _DOTENV_LOADED = True
