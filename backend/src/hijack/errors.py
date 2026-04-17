from __future__ import annotations

import click

# ---------------------------------------------------------------------------
# Error code constants
# ---------------------------------------------------------------------------

INPUT_001 = "INPUT_001"   # 대상 경로/URL 유효하지 않음
INPUT_002 = "INPUT_002"   # 지원 언어 없음 (.py/.ts/.tsx 파일 0개)
FETCH_001 = "FETCH_001"   # 레포 클론 실패
FETCH_002 = "FETCH_002"   # 파일 0개 선별됨 (warn용, Error 아님)
LLM_001 = "LLM_001"      # API 인증 실패
LLM_002 = "LLM_002"      # API 호출 실패
LLM_003 = "LLM_003"      # 응답 파싱 실패
OUTPUT_001 = "OUTPUT_001" # 기존 통합 파일 덮어쓰기 거부


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------

class HijackError(click.ClickException):
    """Base exception for all code-hijack errors."""

    exit_code = 1

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code

    def format_message(self) -> str:
        return f"[{self.code}] {self.message}"


class InputError(HijackError):
    """Raised for invalid input paths/URLs or unsupported language targets."""

    exit_code = 2


class FetchError(HijackError):
    """Raised when repository fetching fails."""

    exit_code = 3


class LLMError(HijackError):
    """Raised for LLM API authentication, call, or parsing failures."""

    exit_code = 3


class OutputError(HijackError):
    """Raised when output file writing is refused."""

    exit_code = 3
