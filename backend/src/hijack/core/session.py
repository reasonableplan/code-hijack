"""세션 관리 — 세션 ID 생성 및 출력 디렉토리 관리."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath


def _extract_repo_name(target: str) -> str:
    """URL 또는 경로에서 짧은 레포 이름을 추출한다."""
    # GitHub URL: https://github.com/owner/repo.git
    match = re.search(r'github\.com/[\w-]+/([\w.-]+?)(?:\.git)?$', target)
    if match:
        return match.group(1)
    # 로컬 경로: 마지막 디렉토리 이름
    return PurePosixPath(target).name or "unknown"


def create_session_id(target: str) -> str:
    """세션 ID를 생성한다. 형식: '2026-04-12_fastapi'."""
    date = datetime.now(UTC).strftime("%Y-%m-%d")
    name = _extract_repo_name(target)
    return f"{date}_{name}"


def get_output_dir(target_path: Path) -> Path:
    """대상 프로젝트의 출력 디렉토리를 반환한다."""
    return target_path / "docs" / "hijacked"
