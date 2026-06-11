from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from hijack.core.archaeology import render_history_for_prompt
from hijack.core.docs import RepoDoc, collect_repo_docs
from hijack.core.fetcher import SourceFile

_MIN_MEANINGFUL_CHARS = 500
_MAX_NEAR_DUPLICATES_PER_PATTERN = 2
_DIGIT_RE = re.compile(r"\d+")

_AUXILIARY_PATH_PREFIXES: tuple[str, ...] = (
    "docs_src/",
    "docs/",
    "examples/",
    "example/",
    "tutorial/",
    "tutorials/",
    "samples/",
    "sample/",
    "demos/",
    "demo/",
    "scripts/",
)


def _is_auxiliary(rel: Path) -> bool:
    """라이브러리 핵심이 아닌 보조 경로 (튜토리얼/예제/문서/스크립트) 인지 판정.

    선별 시 같은 점수의 파일이 있을 때 후순위로 demote 해서 라이브러리 코어가
    예제 코드에 밀려 빠지는 것을 방지한다.

    보조 path:
    - 명시적 prefix (docs_src/, examples/, scripts/ 등 — _AUXILIARY_PATH_PREFIXES)
    - repo 루트의 dotted `.py` 파일 (e.g. `.skill_analysis.py`, `.bootstrap.py`) —
      관례적으로 일회성 dev/bootstrap 스크립트. 본 라이브러리 코드보다 후순위.
    """
    p = rel.as_posix()
    if any(p.startswith(prefix) for prefix in _AUXILIARY_PATH_PREFIXES):
        return True
    # Top-level dotted .py = bootstrap/dev script convention.
    return "/" not in p and p.startswith(".") and p.endswith(".py")


# `export * from '<path>'` / `export { Name } from '<path>'` 식의 re-export 라인.
# barrel 검출 휴리스틱에서 사용 — line 단위로 매칭하므로 anchor 필요.
_REEXPORT_LINE_PATTERN = re.compile(r"^\s*export\b.*\bfrom\s+['\"]")

# barrel 검출은 JS/TS suffix 한정. Python `from X import Y` 는 barrel 의미가
# 약하고 (`__all__` / 부수효과 가능), Kotlin / Java 는 re-export 패턴이 다름.
_BARREL_SUFFIXES = frozenset({".ts", ".tsx", ".js", ".jsx"})


def _is_reexport_barrel(content: str, suffix: str) -> bool:
    """JS/TS 파일이 순수 re-export barrel (`index.ts` 식) 인지 판정.

    `export * from '...'` / `export { Name } from '...'` 만 있고 실제 구현이
    없는 파일을 가려낸다. barrel 은 정보 가치가 거의 0 (재선언일 뿐) 이지만
    역할 분류상 `other` 로 들어가 선별 자리를 차지하는 경우가 잦다 — 우리
    벤치마크에서 frontend `index.ts` 4-5개가 architecture/coding_style 선별
    12개 중 절반을 잡아먹었음. demote 해서 실제 구현 파일에 자리를 양보.

    공백 / 라인 주석 (`//`) / 블록 주석 (`/* */`) 은 무시. re-export 가 1개
    이상 있고, 그 외 코드 라인이 0 이면 barrel.
    """
    if suffix.lower() not in _BARREL_SUFFIXES:
        return False
    if not content:
        return False
    saw_reexport = False
    in_block_comment = False
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if in_block_comment:
            if "*/" in line:
                in_block_comment = False
            continue
        if line.startswith("/*"):
            if "*/" not in line[2:]:
                in_block_comment = True
            continue
        if line.startswith("//"):
            continue
        if _REEXPORT_LINE_PATTERN.match(line):
            saw_reexport = True
            continue
        # re-export 도 코멘트도 아닌 실제 코드 → barrel 아님
        return False
    return saw_reexport


def _should_demote(f: SourceFile) -> bool:
    """선별 시 auxiliary 로 demote 할 파일인지. path 휴리스틱과 barrel 휴리스틱 통합."""
    if _is_auxiliary(f.path):
        return True
    return _is_reexport_barrel(f.content, f.path.suffix)

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
    repo_nature: str = "library"


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def detect_repo_nature(
    pyproject_toml: dict | None,
    detected_layers: set[str],
) -> Literal["app/cli", "app", "library"]:
    """결정론적으로 레포 성격을 분류한다.

    우선순위:
    1. [project.scripts] 또는 [project.entry-points] 존재 → "app/cli"
    2. "frontend" in detected_layers → "app"
    3. 그 외 → "library"
    """
    if pyproject_toml is not None:
        project = pyproject_toml.get("project", {})
        if project.get("scripts") or project.get("entry-points"):
            return "app/cli"
    if "frontend" in detected_layers:
        return "app"
    return "library"


def build_preprocess_result(
    files: list[SourceFile],
    repo_root: Path,
    pyproject_toml: dict | None = None,
) -> PreprocessResult:
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
    nature = detect_repo_nature(pyproject_toml, set(by_layer.keys()))

    return PreprocessResult(
        files=files,
        by_role=by_role,
        by_layer=by_layer,
        by_role_layer=by_role_layer,
        project_structure=structure,
        repo_docs=repo_docs,
        repo_nature=nature,
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
    3. 보조 경로 (docs_src/, examples/, ...) 는 라이브러리 소스 뒤로 demote —
       라이브러리 코어가 docs/예제 코드에 밀려서 선별에서 빠지는 것 방지
    4. Near-duplicate (숫자만 다른 경로) 중복 제거 — 최대 2개만
    """
    preferred = _CATEGORY_ROLES.get(category, _DEFAULT_ROLES)
    ordered: list[SourceFile] = []
    seen: set[str] = set()

    def _add(f: SourceFile) -> None:
        key = f.path.as_posix()
        if key not in seen:
            seen.add(key)
            ordered.append(f)

    for role in preferred:
        for f in sorted(result.by_role.get(role, []), key=_content_rank_key):
            _add(f)

    for f in result.files:
        _add(f)

    primary = [f for f in ordered if not _should_demote(f)]
    auxiliary = [f for f in ordered if _should_demote(f)]

    deduped = _dedupe_near_duplicates(primary + auxiliary)
    return deduped[:max_files]


def _content_rank_key(f: SourceFile) -> tuple[bool, int]:
    """콘텐츠가 적은 파일을 뒤로 보내는 정렬 키.

    truncate 된 파일도 raw 원본 크기 기준으로 점수를 매겨, 시그니처만 남아
    짧아진 상태로 후순위 밀리는 문제 방지.
    original_chars=0 (default, 테스트 fixture 등) 은 기존처럼 len(content) fallback.
    """
    size = f.original_chars or len(f.content)
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
