from __future__ import annotations

from abc import ABC, abstractmethod


class BaseLLM(ABC):
    @abstractmethod
    async def analyze(self, prompt: str, *, model: str) -> str:
        """프롬프트를 받아 LLM 응답(문자열)을 반환한다."""
        ...
