from __future__ import annotations

import datetime
import re
from dataclasses import dataclass, field
from pathlib import Path

from hijack.core.models import SessionResult


def create_session_id(target: str) -> str:
    """'YYYY-MM-DD_<repo_name>' 형식 세션 ID를 반환한다."""
    date_str = datetime.date.today().strftime("%Y-%m-%d")

    # URL 여부 판단: http:// 또는 https:// 또는 git@ 로 시작
    if re.match(r"^(https?://|git@)", target):
        # 마지막 경로 세그먼트 추출 후 .git 제거
        segment = target.rstrip("/").split("/")[-1]
        repo_name = re.sub(r"\.git$", "", segment)
    else:
        repo_name = Path(target).name

    if not repo_name:
        repo_name = "unknown"

    return f"{date_str}_{repo_name}"


def get_output_dir(base_dir: Path, session_id: str) -> Path:
    """세션 출력 디렉토리 Path를 반환한다. 디렉토리를 생성한다."""
    output_dir = base_dir / session_id
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def get_integrated_dir(base_dir: Path) -> Path:
    """통합 출력 디렉토리 Path를 반환한다. 디렉토리를 생성하지 않는다."""
    return base_dir / "integrated"


@dataclass
class SessionDiff:
    """두 세션 간 규칙 변경사항. Phase 2에서 구현."""

    added: list = field(default_factory=list)    # 추가된 규칙
    removed: list = field(default_factory=list)  # 제거된 규칙
    changed: list = field(default_factory=list)  # 변경된 규칙

    @classmethod
    def compare(cls, old: SessionResult, new: SessionResult) -> SessionDiff:
        """Phase 2 stub — 항상 빈 diff 반환."""
        return cls(added=[], removed=[], changed=[])
