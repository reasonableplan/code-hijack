"""소스 파일 수집기 — 로컬 경로 또는 Git 레포에서 파일을 읽는다."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_LANGUAGE_MAP: dict[str, str] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
}

# 언어와 무관하게 항상 수집하는 설정 파일
_CONFIG_FILES = {
    "pyproject.toml", "setup.py", "setup.cfg", "requirements.txt",
    "package.json", "tsconfig.json", "docker-compose.yml", "docker-compose.yaml",
    "Dockerfile", ".env.example", "Makefile",
}

_SKIP_DIRS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "dist", "build",
    ".eggs", ".tox", ".next", ".nuxt", ".turbo", "coverage",
}

_MAX_FILE_SIZE = 512 * 1024  # 512 KB


@dataclass
class SourceFile:
    """수집된 소스 파일 하나."""

    path: Path          # 프로젝트 루트 기준 상대 경로
    content: str
    language: str       # "python", "typescript", "javascript", "config"


def _detect_language(path: Path) -> str | None:
    """파일 확장자 또는 이름으로 언어를 감지."""
    if path.name in _CONFIG_FILES:
        return "config"
    return _LANGUAGE_MAP.get(path.suffix.lower())


def _is_skippable(rel_path: Path) -> bool:
    """건너뛸 디렉토리 내 파일인지 확인."""
    return any(part in _SKIP_DIRS for part in rel_path.parts)


def collect_files(
    root: Path,
    languages: set[str] | None = None,
) -> list[SourceFile]:
    """디렉토리를 순회하며 소스 파일을 수집한다.

    Args:
        root: 스캔할 루트 디렉토리.
        languages: 수집할 언어 집합. None이면 인식 가능한 모든 언어.
                   "config" 파일은 항상 수집.
    """
    files: list[SourceFile] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if _is_skippable(rel):
            continue
        lang = _detect_language(path)
        if lang is None:
            continue
        if languages and lang not in languages and lang != "config":
            continue
        if path.stat().st_size > _MAX_FILE_SIZE:
            logger.debug("대형 파일 건너뜀: %s", rel)
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            logger.warning("파일 읽기 실패 %s: %s", rel, exc)
            continue
        files.append(SourceFile(path=rel, content=content, language=lang))
    return files


def build_structure_map(root: Path) -> str:
    """프로젝트 디렉토리 트리 문자열을 생성한다.

    os.walk + topdown=True로 _SKIP_DIRS를 조기 제거하여
    node_modules 등 대형 디렉토리 순회를 방지한다.
    """
    lines: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        rel = Path(dirpath).relative_to(root)
        # 건너뛸 디렉토리를 in-place 제거 — os.walk가 하위로 내려가지 않음
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        depth = len(rel.parts)
        if depth == 0:
            continue  # 루트 자체는 생략
        if depth > 4:
            dirnames.clear()  # 4단계 이상은 순회 중단
            continue
        indent = "  " * (depth - 1)
        lines.append(f"{indent}{rel.name}/ ({len(filenames)} files)")
    return "\n".join(lines)


def clone_repo(url: str) -> tuple[Path, Path]:
    """Git 레포를 임시 디렉토리에 클론한다.

    Returns:
        (repo_path, temp_dir) — 호출자가 temp_dir를 정리해야 함.
    """
    tmpdir = Path(tempfile.mkdtemp(prefix="code-hijack-"))
    repo_path = tmpdir / "repo"
    try:
        subprocess.run(
            ["git", "clone", "--depth=1", "--single-branch", url, str(repo_path)],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise RuntimeError(f"레포 클론 실패 {url}: {exc}") from exc
    return repo_path, tmpdir


def fetch_source(target: str) -> tuple[list[SourceFile], str, Path | None]:
    """로컬 경로 또는 Git URL에서 소스 파일을 가져온다.

    Returns:
        (파일 목록, 구조 맵, 임시 디렉토리)
        임시 디렉토리는 클론한 경우에만 설정됨 (호출자가 정리).
    """
    local = Path(target)
    if local.is_dir():
        files = collect_files(local)
        structure = build_structure_map(local)
        return files, structure, None

    repo_path, tmpdir = clone_repo(target)
    files = collect_files(repo_path)
    structure = build_structure_map(repo_path)
    return files, structure, tmpdir
