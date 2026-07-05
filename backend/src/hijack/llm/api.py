from __future__ import annotations

import asyncio
import os

import anthropic

from hijack.errors import LLM_001, LLM_002, LLMError
from hijack.llm.base import BaseLLM

DEFAULT_MODEL = "claude-sonnet-5"
MAX_TOKENS = 8192


class ClaudeAPIClient(BaseLLM):
    def __init__(self, api_key: str | None = None) -> None:
        resolved_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not resolved_key:
            raise LLMError(LLM_001, "ANTHROPIC_API_KEY not set")
        self._client = anthropic.Anthropic(api_key=resolved_key)

    async def analyze(self, prompt: str, *, model: str = DEFAULT_MODEL) -> str:
        try:
            return await asyncio.to_thread(self._sync_analyze, prompt, model)
        except anthropic.APIError as e:
            raise LLMError(LLM_002, str(e)) from e

    def _sync_analyze(self, prompt: str, model: str) -> str:
        response = self._client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text
