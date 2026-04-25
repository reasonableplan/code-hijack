from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# 새 프로젝트로 옮길 수 있는 규칙인지 판단하는 태그.
# - cross_project: 다른 프로젝트에 그대로 적용 가능 (PEP 604, BaseResponse 래퍼 등)
# - framework_internal: 특정 프레임워크/라이브러리 내부 결정. 외부에서 의미 없음
#                       (예: "FastAPI 가 Starlette 상속" — FastAPI 만의 결정)
# - domain_specific: 도메인 특화 결정. 다른 도메인에서 그대로 쓰면 부적합
#                    (예: "issue.priority 는 4단계 enum")
SCOPE_VALUES = ("cross_project", "framework_internal", "domain_specific")


@dataclass
class AnalysisRule:
    rule: str
    priority: str
    confidence: str
    ref_files: list[str]
    good_example: str
    bad_example: str
    reason: str
    layer: str = "shared"
    scope: str = "cross_project"

    def to_json(self) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "priority": self.priority,
            "confidence": self.confidence,
            "ref_files": self.ref_files,
            "good_example": self.good_example,
            "bad_example": self.bad_example,
            "reason": self.reason,
            "layer": self.layer,
            "scope": self.scope,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> AnalysisRule:
        return cls(
            rule=data["rule"],
            priority=data["priority"],
            confidence=data["confidence"],
            ref_files=data["ref_files"],
            good_example=data["good_example"],
            bad_example=data["bad_example"],
            reason=data["reason"],
            layer=data.get("layer", "shared"),
            scope=data.get("scope", "cross_project"),
        )


@dataclass
class CategoryResult:
    category: str
    design_intent: str
    rules: list[AnalysisRule]
    anti_patterns: list[dict[str, str]]
    file_type_guides: dict[str, str]
    checklist: list[str]
    raw_llm_output: str
    error: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "design_intent": self.design_intent,
            "rules": [r.to_json() for r in self.rules],
            "anti_patterns": self.anti_patterns,
            "file_type_guides": self.file_type_guides,
            "checklist": self.checklist,
            "raw_llm_output": self.raw_llm_output,
            "error": self.error,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> CategoryResult:
        return cls(
            category=data["category"],
            design_intent=data["design_intent"],
            rules=[AnalysisRule.from_json(r) for r in data["rules"]],
            anti_patterns=data["anti_patterns"],
            file_type_guides=data["file_type_guides"],
            checklist=data["checklist"],
            raw_llm_output=data["raw_llm_output"],
            error=data.get("error"),
        )


@dataclass
class SessionResult:
    session_id: str
    target: str
    model: str
    timestamp: str
    selected_files: list[str]
    categories: list[CategoryResult]
    analysis_duration_seconds: float
    project_structure: str
    files_by_layer: dict[str, int] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "target": self.target,
            "model": self.model,
            "timestamp": self.timestamp,
            "selected_files": self.selected_files,
            "categories": [c.to_json() for c in self.categories],
            "analysis_duration_seconds": self.analysis_duration_seconds,
            "project_structure": self.project_structure,
            "files_by_layer": self.files_by_layer,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> SessionResult:
        return cls(
            session_id=data["session_id"],
            target=data["target"],
            model=data["model"],
            timestamp=data["timestamp"],
            selected_files=data["selected_files"],
            categories=[CategoryResult.from_json(c) for c in data["categories"]],
            analysis_duration_seconds=data["analysis_duration_seconds"],
            project_structure=data["project_structure"],
            files_by_layer=data.get("files_by_layer", {}),
        )
