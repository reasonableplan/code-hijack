from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Portability tag — does this rule transfer to a new project?
# - cross_project: applies to other similar projects directly (PEP 604, BaseResponse wrappers, ...)
# - framework_internal: internal decision of THIS framework/library — irrelevant downstream
#                       (e.g. "FastAPI subclasses Starlette" — only meaningful inside FastAPI)
# - domain_specific: domain-bound choice that another domain would change
#                    (e.g. "issue.priority is a 4-level enum")
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
