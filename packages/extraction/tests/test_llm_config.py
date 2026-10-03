"""Offline tests for LLM provider settings (no network)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from packages.extraction.bg_extractor import _call_model
from packages.extraction.llm_config import DEFAULT_BASE_URLS, get_llm_settings


def test_each_cloud_provider_reads_only_its_own_key_slot() -> None:
    env = {
        "LLM_PROVIDER": "gemini",
        "LLM_MODEL": "gemini-2.5-flash",
        "GEMINI_API_KEY": "gemini-only-key",
        "ANTHROPIC_API_KEY": "anthropic-wrong-key",
        "OPENAI_API_KEY": "openai-wrong-key",
    }
    settings = get_llm_settings(env)
    assert settings.provider == "gemini"
    assert settings.api_key == "gemini-only-key"
    assert settings.base_url == DEFAULT_BASE_URLS["gemini"]

    env = {
        "LLM_PROVIDER": "openai",
        "LLM_MODEL": "gpt-4o",
        "GEMINI_API_KEY": "gemini-wrong-key",
        "ANTHROPIC_API_KEY": "anthropic-wrong-key",
        "OPENAI_API_KEY": "openai-only-key",
    }
    settings = get_llm_settings(env)
    assert settings.provider == "openai"
    assert settings.api_key == "openai-only-key"

    env = {
        "LLM_PROVIDER": "anthropic",
        "LLM_MODEL": "claude-sonnet-4-20250514",
        "GEMINI_API_KEY": "gemini-wrong-key",
        "ANTHROPIC_API_KEY": "anthropic-only-key",
        "OPENAI_API_KEY": "openai-wrong-key",
    }
    settings = get_llm_settings(env)
    assert settings.provider == "anthropic"
    assert settings.api_key == "anthropic-only-key"


def test_ollama_uses_placeholder_key_without_secret_slot() -> None:
    settings = get_llm_settings(
        {
            "LLM_PROVIDER": "ollama",
            "LLM_MODEL": "llama3:latest",
            "GEMINI_API_KEY": "",
            "OPENAI_API_KEY": "",
            "ANTHROPIC_API_KEY": "",
        }
    )
    assert settings.api_key == "ollama"
    assert settings.base_url == DEFAULT_BASE_URLS["ollama"]


def test_empty_key_for_chosen_provider_raises_named_error() -> None:
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY is missing or empty"):
        get_llm_settings(
            {
                "LLM_PROVIDER": "gemini",
                "LLM_MODEL": "gemini-2.5-flash",
                "GEMINI_API_KEY": "",
                "OPENAI_API_KEY": "should-not-be-used",
            }
        )
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY is missing or empty"):
        get_llm_settings(
            {
                "LLM_PROVIDER": "openai",
                "LLM_MODEL": "gpt-4o",
                "OPENAI_API_KEY": "   ",
                "GEMINI_API_KEY": "should-not-be-used",
            }
        )
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY is missing or empty"):
        get_llm_settings(
            {
                "LLM_PROVIDER": "anthropic",
                "LLM_MODEL": "claude-test",
                "ANTHROPIC_API_KEY": "",
            }
        )


def test_missing_provider_or_model_raises_clear_error() -> None:
    with pytest.raises(RuntimeError, match="LLM_PROVIDER is missing or empty"):
        get_llm_settings({"LLM_MODEL": "gemini-2.5-flash", "GEMINI_API_KEY": "k"})
    with pytest.raises(RuntimeError, match="LLM_PROVIDER is missing or empty"):
        get_llm_settings(
            {"LLM_PROVIDER": "  ", "LLM_MODEL": "m", "GEMINI_API_KEY": "k"}
        )
    with pytest.raises(RuntimeError, match="LLM_MODEL is missing or empty"):
        get_llm_settings(
            {"LLM_PROVIDER": "gemini", "LLM_MODEL": "", "GEMINI_API_KEY": "k"}
        )
    with pytest.raises(RuntimeError, match="LLM_MODEL is missing or empty"):
        get_llm_settings({"LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "k"})


def test_llm_base_url_override() -> None:
    settings = get_llm_settings(
        {
            "LLM_PROVIDER": "openai",
            "LLM_MODEL": "gpt-4o",
            "OPENAI_API_KEY": "k",
            "LLM_BASE_URL": "https://example.test/v1",
        }
    )
    assert settings.base_url == "https://example.test/v1"


def test_anthropic_routed_to_call_anthropic_with_settings_key_and_model() -> None:
    fake_message = SimpleNamespace(
        content=[SimpleNamespace(type="text", text='{"extracted": {}}')]
    )
    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_message
    fake_anthropic_mod = MagicMock()
    fake_anthropic_mod.Anthropic.return_value = fake_client

    environ = {
        "LLM_PROVIDER": "anthropic",
        "LLM_MODEL": "claude-test-model",
        "ANTHROPIC_API_KEY": "ant-test-key",
        "OPENAI_API_KEY": "must-not-use",
        "GEMINI_API_KEY": "must-not-use",
    }

    with (
        patch(
            "packages.extraction.bg_extractor.get_llm_settings",
            return_value=get_llm_settings(environ),
        ),
        patch.dict("sys.modules", {"anthropic": fake_anthropic_mod}),
    ):
        model, text = _call_model(system="sys", user="usr")

    assert model == "claude-test-model"
    assert text == '{"extracted": {}}'
    fake_anthropic_mod.Anthropic.assert_called_once_with(api_key="ant-test-key")
    kwargs: dict[str, Any] = fake_client.messages.create.call_args.kwargs
    assert kwargs["model"] == "claude-test-model"
    assert kwargs["system"] == "sys"
    assert kwargs["messages"] == [{"role": "user", "content": "usr"}]
