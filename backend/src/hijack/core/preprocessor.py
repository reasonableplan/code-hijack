from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from hijack.core.archaeology import render_history_for_prompt
from hijack.core.docs import RepoDoc, collect_repo_docs
from hijack.core.fetcher import SourceFile

_MIN_MEANINGFUL_CHARS = 500
_MAX_NEAR_DUPLICATES_PER_PATTERN = 2
_DIGIT_RE = re.compile(r"\d+")

# ---------------------------------------------------------------------------
# Category → preferred roles mapping
# ---------------------------------------------------------------------------

_CATEGORY_ROLES: dict[str, list[str]] = {
    "architecture": ["entry_point", "service", "api", "other"],
    "coding_style": ["entry_point", "model", "api", "service", "test", "other"],
    "api_design": ["api", "entry_point", "service"],
    "testing": ["test"],
    "dependencies": ["entry_point", "other"],
    "security": ["api", "service", "entry_point"],
    "performance": ["service", "api", "entry_point"],
    "devops": ["other"],
    "state_management": ["service", "model", "other"],
    "data_model": ["model", "other"],
}

_DEFAULT_ROLES: list[str] = ["entry_point", "api", "model", "service", "test", "other"]


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class PreprocessResult:
    files: list[SourceFile]
    by_role: dict[str, list[SourceFile]] = field(default_factory=dict)
    by_layer: dict[str, list[SourceFile]] = field(default_factory=dict)
    by_role_layer: dict[str, dict[str, list[SourceFile]]] = field(default_factory=dict)
    project_structure: str = ""
    repo_docs: list[RepoDoc] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def build_preprocess_result(files: list[SourceFile], repo_root: Path) -> PreprocessResult:
    """SourceFile 목록으로 PreprocessResult를 생성한다.

    Also collects repo-level rationale docs (README/ARCHITECTURE/ADRs) once per
    session — they're prepended to every category prompt as <repo_context> so
    the LLM can ground rule reasons in real design notes.
    """
    by_role: dict[str, list[SourceFile]] = {}
    by_layer: dict[str, list[SourceFile]] = {}
    by_role_layer: dict[str, dict[str, list[SourceFile]]] = {}

    for f in files:
        by_role.setdefault(f.role, []).append(f)
        by_layer.setdefault(f.layer, []).append(f)
        by_role_layer.setdefault(f.role, {}).setdefault(f.layer, []).append(f)

    structure = _build_project_structure(files, repo_root)
    repo_docs = collect_repo_docs(repo_root)

    return PreprocessResult(
        files=files,
        by_role=by_role,
        by_layer=by_layer,
        by_role_layer=by_role_layer,
        project_structure=structure,
        repo_docs=repo_docs,
    )


def select_files_for_category(
    result: PreprocessResult,
    category: str,
    *,
    max_files: int = 30,
) -> list[SourceFile]:
    """카테고리에 관련된 파일을 우선순위 순으로 최대 max_files 개 반환한다.

    선별 규칙:
    1. 역할 우선순위에 따라 후보 수집
    2. 역할 내에서 콘텐츠 밀도로 정렬 (얕은 재-export 파일 뒤로)
    3. Near-duplicate (숫자만 다른 경로) 중복 제거 — 최대 2개만
    """
    preferred = _CATEGORY_ROLES.get(category, _DEFAULT_ROLES)
    candidates: list[SourceFile] = []
    seen: set[str] = set()

    for role in preferred:
        role_files = sorted(result.by_role.get(role, []), key=_content_rank_key)
        for f in role_files:
            key = f.path.as_posix()
            if key not in seen:
                seen.add(key)
                candidates.append(f)

    for f in result.files:
        key = f.path.as_posix()
        if key not in seen:
            seen.add(key)
            candidates.append(f)

    deduped = _dedupe_near_duplicates(candidates)
    return deduped[:max_files]


def _content_rank_key(f: SourceFile) -> tuple[bool, int]:
    """콘텐츠가 적은 파일을 뒤로 보내는 정렬 키. (얕음 flag, -크기)."""
    size = len(f.content)
    shallow = size < _MIN_MEANINGFUL_CHARS
    return (shallow, -size)


def _dedupe_near_duplicates(files: list[SourceFile]) -> list[SourceFile]:
    """숫자만 다른 경로 (app01/main.py, app02/main.py, ...) 를 최대 2개로 제한한다."""
    counts: dict[str, int] = defaultdict(int)
    result: list[SourceFile] = []
    for f in files:
        pattern = _DIGIT_RE.sub("#", f.path.as_posix())
        if counts[pattern] < _MAX_NEAR_DUPLICATES_PER_PATTERN:
            counts[pattern] += 1
            result.append(f)
    return result


def build_file_summary_for_llm(files: list[SourceFile]) -> list[str]:
    """각 SourceFile을 LLM에 전달할 문자열로 변환한다.

    Appends a <history> block when git archaeology is attached — recent commits
    + reverts. The block is omitted entirely when there is no history, so files
    in non-git contexts produce the same prompt as before.
    """
    summaries: list[str] = []
    for f in files:
        header = f"### {f.path.as_posix()} [role={f.role}, layer={f.layer}]"
        body = f"{header}\n```\n{f.content}\n```"
        history_block = render_history_for_prompt(f.history)
        if history_block:
            body = f"{body}\n{history_block}"
        summaries.append(body)
    return summaries


def build_layer_stats(by_layer: dict[str, int]) -> str:
    """레이어별 파일 수 요약 문자열을 반환한다."""
    lines: list[str] = ["Layer distribution:"]
    for layer in ["frontend", "backend", "db", "devops", "shared"]:
        lines.append(f"  {layer}: {by_layer.get(layer, 0)} files")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_project_structure(files: list[SourceFile], repo_root: Path) -> str:
    """파일 목록으로 간단한 디렉토리 트리 문자열을 생성한다."""
    dirs: set[str] = set()
    for f in files:
        parts = f.path.parts
        for i in range(1, len(parts)):
            dirs.add("/".join(parts[:i]))

    all_paths = sorted(dirs | {f.path.as_posix() for f in files})

    lines: list[str] = [f"{repo_root.name}/"]
    for p in all_paths:
        depth = p.count("/")
        name = p.split("/")[-1]
        lines.append("  " * depth + name + ("/" if p in dirs else ""))

    return "\n".join(lines)
