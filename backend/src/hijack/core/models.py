"""분석 결과 데이터 모델 — skeleton Section 7 기반."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal


@dataclass
class AnalysisRule:
    """하나의 추출된 규칙."""

    rule: str
    priority: Literal["MUST", "SHOULD"] = "SHOULD"
    confidence: Literal["high", "medium", "low"] = "medium"
    ref_files: list[str] = field(default_factory=list)
    good_example: str = ""
    bad_example: str = ""
    reason: str = ""


@dataclass
class CategoryResult:
    """카테고리 하나의 분석 결과."""

    category: str
    design_intent: str = ""
    rules: list[AnalysisRule] = field(default_factory=list)
    anti_patterns: list[dict[str, str]] = field(default_factory=list)
    file_type_guides: dict[str, str] = field(default_factory=dict)
    checklist: list[str] = field(default_factory=list)
    raw_llm_output: str = ""


@dataclass
class SessionResult:
    """하나의 분석 세션 전체 결과."""

    session_id: str
    target: str
    model: str = ""
    timestamp: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
    )
    selected_files: list[str] = field(default_factory=list)
    categories: list[CategoryResult] = field(default_factory=list)
    analysis_duration_seconds: float = 0.0
    project_structure: str = ""

    def to_json(self) -> str:
        """세션 결과를 JSON 문자열로 직렬화."""
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, data: str) -> SessionResult:
        """JSON 문자열에서 SessionResult를 복원."""
        raw: dict[str, Any] = json.loads(data)
        categories: list[CategoryResult] = []
        for cat_raw in raw.pop("categories", []):
            rules = [AnalysisRule(**r) for r in cat_raw.pop("rules", [])]
            categories.append(CategoryResult(**cat_raw, rules=rules))
        return cls(**raw, categories=categories)
