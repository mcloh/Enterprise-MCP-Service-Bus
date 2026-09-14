"""LLM client factory (EP-13-T01).

A real OpenAI-compatible client -- verified 2026-09-14 against OCI
Generative AI's OpenAI-compatible endpoint (`meta.llama-3.3-70b-instruct`,
real tool-calling confirmed), but works against any OpenAI-compatible
provider (OpenAI itself, Anthropic's compatible surface, a self-hosted
gateway) by construction: only `base_url`/`api_key`/`model` change.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from openai import AsyncOpenAI


class LLMConfigError(Exception):
    pass


@dataclass(frozen=True)
class LLMConfig:
    base_url: str
    api_key: str
    model: str


def load_llm_config_from_env() -> LLMConfig:
    base_url = os.environ.get("LLM_BASE_URL")
    api_key = os.environ.get("LLM_API_KEY")
    model = os.environ.get("LLM_MODEL")
    if not base_url or not api_key or not model:
        raise LLMConfigError(
            "LLM_BASE_URL, LLM_API_KEY and LLM_MODEL must all be set (see RI/.env.example)"
        )
    return LLMConfig(base_url=base_url, api_key=api_key, model=model)


def build_llm_client(config: LLMConfig) -> AsyncOpenAI:
    return AsyncOpenAI(base_url=config.base_url, api_key=config.api_key)
