from __future__ import annotations

from abc import ABC, abstractmethod

# api.py 가 아닌 여기 두는 이유: CLI 의 measure/diff 등 API 불필요 경로가
# anthropic 미설치 환경에서도 import 가능해야 함 ([api] extra 없이).
DEFAULT_MODEL = "claude-sonnet-5"


class BaseLLM(ABC):
    @abstractmethod
    async def analyze(self, prompt: str, *, model: str) -> str:
        """프롬프트를 받아 LLM 응답(문자열)을 반환한다."""
        ...
