"""LLM factory — returns a BaseChatModel based on environment configuration.

Supported providers (LLM_PROVIDER env var):
  anthropic (default) — Claude via langchain-anthropic, requires ANTHROPIC_API_KEY
  nebius              — OpenAI-compatible endpoint, requires NEBIUS_API_KEY and LLM_MODEL
"""
from __future__ import annotations

import os

from langchain_core.language_models import BaseChatModel


def create_llm() -> BaseChatModel:
    """Instantiate and return the configured LLM.

    Reads LLM_PROVIDER, LLM_MODEL, and provider-specific key env vars.
    Raises ValueError with a clear message if a required variable is missing.
    """
    provider = os.environ.get("LLM_PROVIDER", "anthropic").lower()

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY is not set. "
                "Export it or add it to your .env file."
            )
        model = os.environ.get("LLM_MODEL", "claude-sonnet-4-6")
        return ChatAnthropic(model=model, api_key=api_key)

    if provider == "nebius":
        from langchain_openai import ChatOpenAI

        api_key = os.environ.get("NEBIUS_API_KEY", "")
        if not api_key:
            raise ValueError(
                "NEBIUS_API_KEY is not set. "
                "Export it or add it to your .env file."
            )
        model = os.environ.get("LLM_MODEL", "")
        if not model:
            raise ValueError(
                "LLM_MODEL is not set. "
                "Set it to the Nebius model name, e.g. "
                "meta-llama/Meta-Llama-3.1-70B-Instruct-fast"
            )
        base_url = os.environ.get(
            "NEBIUS_API_BASE", "https://api.tokenfactory.nebius.com/v1/"
        )
        return ChatOpenAI(model=model, api_key=api_key, base_url=base_url)

    raise ValueError(
        f"Unknown LLM_PROVIDER '{provider}'. "
        "Supported values: anthropic, nebius"
    )
