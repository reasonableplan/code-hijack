"""전처리기 — 휴리스틱 파일 분류 + 프로젝트 구조 맵."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from hijack.core.fetcher import SourceFile

logger = logging.getLogger(__name__)

# 휴리스틱 역할 패턴 (skeleton Section 4)
_ROLE_PATTERNS: dict[str, list[str]] = {
    "entry_point": [
        "main.py", "app.py", "server.py", "index.ts", "index.tsx",
        "server.ts", "main.ts", "__main__.py",
    ],
    "model": [
        "models/", "schemas/", "types/", "entities/",
    ],
    "api": [
        "routes/", "api/", "controllers/", "routers/", "endpoints/",
    ],
    "service": [
        "services/", "lib/", "utils/", "helpers/", "core/",
    ],
    "test": [
        "tests/", "test/", "__tests__/", "spec/",
    ],
    "config": [
        "config/", "settings/",
    ],
    "state": [
        "store/", "state/", "context/", "stores/",
    ],
    "auth": [
        "auth/", "middleware/", "security/",
    ],
    "devops": [
        ".github/", "Dockerfile", "docker-compose",
    ],
}

# 선별 우선순위 — 인덱스가 낮을수록 높은 우선순위
_ROLE_PRIORITY = [
    "entry_point", "model", "api", "service", "config",
    "auth", "state", "test", "devops",
]


@dataclass
class ClassifiedFile:
    """역할이 분류된 소스 파일."""

    file: SourceFile
    role: str
    priority: int  # 낮을수록 높은 우선순위


@dataclass
class PreprocessResult:
    """전처리 결과."""

    classified: list[ClassifiedFile] = field(default_factory=list)
    structure_map: str = ""
    total_files: int = 0
    python_count: int = 0
    typescript_count: int = 0


def _classify_file(src: SourceFile) -> tuple[str, int]:
    """파일을 역할로 분류하고 우선순위를 반환."""
    path_str = str(src.path)
    name = PurePosixPath(src.path).name

    # config 언어 파일은 config 역할로 직접 분류
    if src.language == "config":
        return "config", _ROLE_PRIORITY.index("config")

    for priority, role in enumerate(_ROLE_PRIORITY):
        patterns = _ROLE_PATTERNS[role]
        for pattern in patterns:
            if pattern.endswith("/"):
                # 디렉토리 패턴
                if f"/{pattern}" in f"/{path_str}" or path_str.startswith(pattern):
                    return role, priority
            else:
                # 파일명 패턴
                if name == pattern or pattern in path_str:
                    return role, priority

    return "other", len(_ROLE_PRIORITY)


def preprocess(
    files: list[SourceFile],
    structure_map: str,
    max_candidates: int = 80,
) -> PreprocessResult:
    """파일을 역할별로 분류하고 후보를 선별한다.

    Args:
        files: 수집된 전체 소스 파일.
        structure_map: 디렉토리 트리 문자열.
        max_candidates: 최대 후보 파일 수.
    """
    classified: list[ClassifiedFile] = []
    for src in files:
        role, priority = _classify_file(src)
        classified.append(ClassifiedFile(file=src, role=role, priority=priority))

    # 우선순위 정렬 (낮은 값 = 높은 중요도)
    classified.sort(key=lambda c: (c.priority, str(c.file.path)))

    if len(classified) > max_candidates:
        classified = classified[:max_candidates]

    python_count = sum(1 for f in files if f.language == "python")
    ts_count = sum(1 for f in files if f.language == "typescript")

    return PreprocessResult(
        classified=classified,
        structure_map=structure_map,
        total_files=len(files),
        python_count=python_count,
        typescript_count=ts_count,
    )


def build_file_summary_for_llm(result: PreprocessResult) -> str:
    """LLM 파일 선정 프롬프트용 요약 문자열을 생성한다."""
    lines = [
        f"전체: {result.total_files}개 파일 "
        f"(Python {result.python_count}개, TypeScript {result.typescript_count}개)\n",
        "## 프로젝트 구조",
        result.structure_map,
        "",
        "## 역할별 후보 파일",
    ]

    by_role: dict[str, list[ClassifiedFile]] = {}
    for cf in result.classified:
        by_role.setdefault(cf.role, []).append(cf)

    for role in _ROLE_PRIORITY + ["other"]:
        role_files = by_role.get(role, [])
        if not role_files:
            continue
        lines.append(f"\n### {role} ({len(role_files)}개)")
        for cf in role_files[:15]:
            size = len(cf.file.content)
            lines.append(f"  - {cf.file.path} ({size:,}자, {cf.file.language})")

    return "\n".join(lines)
