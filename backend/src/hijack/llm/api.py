"""Claude API 클라이언트 — 독립 CLI 모드용."""

from __future__ import annotations

import asyncio

import anthropic

from hijack.llm.base import BaseLLM


class ClaudeAPIClient(BaseLLM):
    """anthropic SDK를 사용하는 Claude API 클라이언트."""

    def __init__(self, model: str = "claude-sonnet-4-6", max_tokens: int = 8192) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self._client = anthropic.Anthropic()

    async def analyze(self, system_prompt: str, user_prompt: str) -> str:
        """프롬프트를 전송하고 LLM 응답을 반환한다.

        sync SDK를 asyncio.to_thread로 감싸서 이벤트 루프를 블로킹하지 않는다.
        """
        response = await asyncio.to_thread(
            self._client.messages.create,
            model=self.model,
            max_tokens=self.max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return response.content[0].text
