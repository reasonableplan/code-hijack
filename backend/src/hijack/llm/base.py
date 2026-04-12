"""LLM 기본 인터페이스."""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseLLM(ABC):
    """코드 분석용 LLM 추상 인터페이스."""

    @abstractmethod
    async def analyze(self, system_prompt: str, user_prompt: str) -> str:
        """프롬프트를 전송하고 LLM 응답 텍스트를 반환한다."""
        ...
