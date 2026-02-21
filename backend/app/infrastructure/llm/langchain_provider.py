"""
LangChain LLM provider — centralised factory for the chat model.
Validates API key at import time.
"""

from __future__ import annotations

import logging

from langchain_openai import ChatOpenAI

from app.config import get_settings

logger = logging.getLogger(__name__)


def get_llm() -> ChatOpenAI:
    """
    Return a configured ChatOpenAI instance.
    Raises a clear error if the API key is not set.
    """
    settings = get_settings()

    if not settings.openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. "
            "Please add it to your .env file before starting the server."
        )

    # Auto-detect OpenRouter keys
    kwargs = {}
    if settings.openai_api_key.startswith("sk-or-v1-"):
        kwargs["base_url"] = "https://openrouter.ai/api/v1"
        logger.info("OpenRouter key detected. Using OpenRouter base URL.")

    return ChatOpenAI(
        model=settings.llm_model_name,
        openai_api_key=settings.openai_api_key,
        temperature=0.3,
        max_tokens=2048,
        request_timeout=60,
        **kwargs
    )
