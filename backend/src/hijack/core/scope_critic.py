"""scope_critic — 기계적(rule-based) 스코프 보정 패스.

LLM 이 생성한 scope 값이 틀렸을 때, good_example 에서 import 구문을 파싱해
`framework_internal` / `cross_project` / `domain_specific` 으로 확정적으로
덮어쓴다.  signal 이 없으면 None 을 반환해 LLM 판단을 그대로 유지시킨다.

설계 원칙:
- 순수 함수 (I/O 없음, LLM 호출 없음)
- 보수적 override: LLM 이 `cross_project` 라고 했을 때만 덮어씀
  (`framework_internal` / `domain_specific` 은 이미 좁은 판단이므로 건드리지 않음)
"""
from __future__ import annotations

import re
from dataclasses import replace

from hijack.core.models import AnalysisRule, SessionResult

# ---------------------------------------------------------------------------
# 모듈 수준 상수 — ruff: noqa 없이 frozenset 리터럴로 선언
# ---------------------------------------------------------------------------

# 알려진 web/orm/validation 프레임워크 최상위 패키지명.
# `from fastapi.routing import X` → 첫 번째 컴포넌트 `fastapi` 로 매칭.
_FRAMEWORK_PACKAGES: frozenset[str] = frozenset({
    # web frameworks
    "fastapi", "starlette", "django", "flask", "sanic", "aiohttp",
    "tornado", "quart", "litestar",
    # ORM / db
    "sqlalchemy", "peewee", "tortoise", "beanie",
    # frontend
    "react", "vue",
})

# 표준 라이브러리 패키지명 (Python stdlib 범위에서 코딩 규칙에 자주 등장하는 것).
# 이 패키지들만 import 하면 `cross_project` 로 분류한다.
_STDLIB_PACKAGES: frozenset[str] = frozenset({
    "collections", "typing", "dataclasses", "pathlib", "contextlib",
    "os", "sys", "re", "json", "asyncio", "abc", "enum", "functools",
    "itertools", "warnings", "logging", "datetime", "decimal", "uuid",
    "copy", "time", "inspect", "types", "typing_extensions", "annotated_doc",
})

# 도메인-한정 식별자 패턴. 단어 경계로만 매칭 (부분 문자열 오탐 방지).
_DOMAIN_PATTERN: re.Pattern[str] = re.compile(
    r"\b(Issue|Order|Customer|Sprint|BillingPeriod|Tenant|Invoice|Subscription)\b"
)

# import 구문 추출 — `from X.Y.Z import ...` 또는 `import X.Y.Z` 형태.
# `[\w., ]+` 는 같은 줄만 — `\s` 대신 공백/탭만 허용해 개행 흡수 방지.
_IMPORT_RE: re.Pattern[str] = re.compile(
    r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w., \t]+))",
    re.MULTILINE,
)


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------

def _extract_top_level_packages(code: str) -> frozenset[str]:
    """good_example 에서 모든 import 의 최상위 패키지를 추출한다.

    `from fastapi.routing import APIRouter` → `fastapi`
    `import os, sys`                        → `os`, `sys`
    """
    pkgs: set[str] = set()
    for m in _IMPORT_RE.finditer(code):
        from_pkg, plain_pkg = m.group(1), m.group(2)
        if from_pkg:
            # `from X.Y import Z` — 첫 번째 컴포넌트만
            pkgs.add(from_pkg.split(".")[0])
        elif plain_pkg:
            # `import os, sys` or `import os.path` — 콤마 분리 후 첫 컴포넌트
            for part in plain_pkg.split(","):
                top = part.strip().split(".")[0]
                if top:
                    pkgs.add(top)
    return frozenset(pkgs)


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------

def mechanical_scope(rule: AnalysisRule) -> str | None:
    """good_example 을 기계적으로 분석해 scope 라벨을 추론한다.

    반환 값:
    - "framework_internal" : 프레임워크 패키지를 import 하는 경우
    - "cross_project"      : stdlib 패키지만 import 하는 경우
    - "domain_specific"    : 도메인 식별자가 등장하고 프레임워크 import 없는 경우
    - None                 : signal 없음 — LLM 판단 유지

    Detection order (우선순위 순):
    1. good_example 이 비어 있으면 → None
    2. 프레임워크 패키지 import 발견 → framework_internal
    3. stdlib 전용 import 발견 → cross_project
    4. 도메인 식별자 발견 → domain_specific (heuristic, 보수적)
    5. 나머지 → None
    """
    example = (rule.good_example or "").strip()
    if not example:
        return None

    packages = _extract_top_level_packages(example)

    # 1. 프레임워크 import 가 있으면 확정
    if packages & _FRAMEWORK_PACKAGES:
        return "framework_internal"

    # 2. import 가 있고 전부 stdlib 이면 cross_project
    if packages and packages <= _STDLIB_PACKAGES:
        return "cross_project"

    # 3. import 없거나 알 수 없는 패키지가 섞인 경우 — 도메인 식별자 heuristic
    #    (import 가 있고 알 수 없는 패키지가 섞였을 때는 None 을 반환해 LLM 유지)
    if not packages and _DOMAIN_PATTERN.search(example):
        return "domain_specific"

    return None


def reclassify_session_scopes(
    session: SessionResult,
) -> tuple[SessionResult, dict[str, int]]:
    """SessionResult 의 모든 규칙을 순회해 scope 를 기계적으로 보정한다.

    Conservative override 정책:
    - LLM 이 `cross_project` 라고 했을 때만 덮어씀.
    - `framework_internal` / `domain_specific` 는 이미 좁은 판단 → 건드리지 않음.
    - mechanical_scope 가 None 을 반환하면 → 현 scope 유지.

    반환: (new_session, change_counts)
    change_counts 키: "cross_project_to_framework_internal",
                      "cross_project_to_domain_specific", "unchanged"
    """
    counts: dict[str, int] = {
        "cross_project_to_framework_internal": 0,
        "cross_project_to_domain_specific": 0,
        "unchanged": 0,
    }

    new_categories = []
    for cat in session.categories:
        new_rules: list[AnalysisRule] = []
        for rule in cat.rules:
            mechanical = mechanical_scope(rule)
            if (
                rule.scope == "cross_project"
                and mechanical in ("framework_internal", "domain_specific")
            ):
                # replace() 는 dataclasses.replace — immutable-style 복사
                new_rule = replace(rule, scope=mechanical)
                key = f"cross_project_to_{mechanical}"
                counts[key] = counts.get(key, 0) + 1
            else:
                new_rule = rule
                counts["unchanged"] += 1
            new_rules.append(new_rule)

        new_categories.append(replace(cat, rules=new_rules))

    # SessionResult 자체도 replace 로 복사 (모든 필드 보존)
    new_session = replace(session, categories=new_categories)
    return new_session, counts
