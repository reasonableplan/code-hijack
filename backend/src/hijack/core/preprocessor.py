from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from hijack.core.fetcher import SourceFile

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


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def build_preprocess_result(files: list[SourceFile], repo_root: Path) -> PreprocessResult:
    """SourceFile 목록으로 PreprocessResult를 생성한다."""
    by_role: dict[str, list[SourceFile]] = {}
    by_layer: dict[str, list[SourceFile]] = {}
    by_role_layer: dict[str, dict[str, list[SourceFile]]] = {}

    for f in files:
        by_role.setdefault(f.role, []).append(f)
        by_layer.setdefault(f.layer, []).append(f)
        by_role_layer.setdefault(f.role, {}).setdefault(f.layer, []).append(f)

    structure = _build_project_structure(files, repo_root)

    return PreprocessResult(
        files=files,
        by_role=by_role,
        by_layer=by_layer,
        by_role_layer=by_role_layer,
        project_structure=structure,
    )


def select_files_for_category(
    result: PreprocessResult,
    category: str,
    *,
    max_files: int = 30,
) -> list[SourceFile]:
    """카테고리에 관련된 파일을 우선순위 순으로 최대 max_files 개 반환한다."""
    preferred = _CATEGORY_ROLES.get(category, _DEFAULT_ROLES)
    selected: list[SourceFile] = []
    seen: set[str] = set()

    for role in preferred:
        for f in result.by_role.get(role, []):
            key = f.path.as_posix()
            if key not in seen:
                seen.add(key)
                selected.append(f)
            if len(selected) >= max_files:
                return selected

    for f in result.files:
        key = f.path.as_posix()
        if key not in seen:
            seen.add(key)
            selected.append(f)
        if len(selected) >= max_files:
            return selected

    return selected


def build_file_summary_for_llm(files: list[SourceFile]) -> list[str]:
    """각 SourceFile을 LLM에 전달할 문자열로 변환한다."""
    summaries: list[str] = []
    for f in files:
        header = f"### {f.path.as_posix()} [role={f.role}, layer={f.layer}]"
        summaries.append(f"{header}\n```\n{f.content}\n```")
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
