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

# Source kind for an Evidence entry. Kept narrow on purpose — these are the
# three artefact types we currently surface to the LLM (git history + docs).
# Future kinds (in-code comments, external refs) are additive in D2+.
EVIDENCE_KIND_VALUES = ("commit", "revert", "doc")

# What KIND of why does this evidence support?
# - rejection : tried a pattern, rolled it back (strongest negative signal)
# - constraint: external force — perf SLA, security, compliance, tool requirement
# - incident  : past failure / post-mortem driving the choice
# - preference: internal philosophy / tradeoff / consistency choice
# Deliberately 4 well-separated buckets — fewer fuzzy categories than the
# initial 7-value sketch produced cleaner LLM classification.
INTENT_KIND_VALUES = ("rejection", "constraint", "incident", "preference")

# Per-Evidence text caps. Enforced post-LLM in analyzer to bound prompt tokens
# and keep rendered output readable.
EVIDENCE_HEADLINE_MAX = 120
EVIDENCE_QUOTE_MAX = 500


@dataclass
class Evidence:
    """A single source-grounded citation backing a rule.

    The senior's actual reasoning lives here verbatim — `headline` and `quote`
    are copied from the source (commit subject/body, ADR heading/paragraph),
    not paraphrased. The downstream renderer reproduces them as quoted text so
    the output preserves the senior's voice rather than the LLM's summary.

    Field provenance:
      - LLM-provided : kind, ref, headline, quote, intent_kind
      - System-populated post-LLM (analyzer): date
    """

    kind: str                # one of EVIDENCE_KIND_VALUES
    ref: str                 # SHA (commit/revert) or repo-rel path (doc)
    headline: str            # ≤120 chars, verbatim subject/heading
    quote: str               # ≤500 chars, verbatim body/paragraph
    intent_kind: str | None = None  # one of INTENT_KIND_VALUES, or None
    date: str | None = None  # ISO date, populated by system from SHA lookup

    def to_json(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "ref": self.ref,
            "headline": self.headline,
            "quote": self.quote,
            "intent_kind": self.intent_kind,
            "date": self.date,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Evidence:
        return cls(
            kind=data["kind"],
            ref=data["ref"],
            headline=data["headline"],
            quote=data["quote"],
            intent_kind=data.get("intent_kind"),
            date=data.get("date"),
        )


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
    # Structured citations backing the rule. When non-empty, the renderer emits
    # an Evidence chain section and `evidence.classify_rule` switches from text-
    # based to structure-based classification. Empty list = pre-D1 behaviour.
    evidence: list[Evidence] = field(default_factory=list)

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
            "evidence": [e.to_json() for e in self.evidence],
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
            evidence=[Evidence.from_json(e) for e in data.get("evidence", [])],
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
    # Sorted list of full SHAs surfaced to the LLM via <history> blocks.
    # Used by evidence.classify_rule to detect hallucinated commit citations:
    # if a rule's `reason` cites "commit XXX" and XXX prefix-matches no entry
    # here, the citation was invented and the rule lands in `fake_citation`.
    historic_shas: list[str] = field(default_factory=list)
    # Repo-relative paths of docs surfaced via <repo_context>. Same role as
    # historic_shas but for `kind=doc` Evidence entries: a doc citation whose
    # ref isn't in this list was hallucinated.
    repo_doc_paths: list[str] = field(default_factory=list)
    # Representative functions/classes selected from the senior repo source.
    # Populated by select_exemplars() in run_full_analysis() (Phase G1).
    # Pre-G1 session.json files omit this key — from_json defaults to [].
    # list[Exemplar] — typed as Any to avoid circular import with exemplars module.
    exemplars: list[Any] = field(default_factory=list)
    # Per-layer mechanical style fingerprints (negative space + symbol
    # substitution map). Populated by extract_style() in run_full_analysis()
    # (Phase G2). Not persisted to session.json — the data is derived from
    # source content and can be recomputed; storing it would couple session
    # files to fingerprint catalog versions.
    # dict[str, StyleFingerprint] — typed as Any to avoid circular import.
    style_fingerprints: dict[str, Any] = field(default_factory=dict)
    # Test-suite defensive signals (Phase B): parametrize edge cases, test name
    # themes, and pytest.raises groups. Populated by extract_test_decisions()
    # in run_full_analysis(). None for older sessions or repos with no test files.
    # TestDecisions | None — typed as Any to avoid circular import.
    test_decisions: Any | None = None
    # PR-history signals (Phase A1): vocabulary clusters, notable/rejected PRs,
    # recurring labels. Populated by extract_pr_decisions() in run_full_analysis().
    # None when the target is not a GitHub repo, when auth is unavailable, or
    # when the network call fails. PRDecisions | None — typed as Any to avoid
    # circular import.
    pr_decisions: Any | None = None

    def to_json(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "session_id": self.session_id,
            "target": self.target,
            "model": self.model,
            "timestamp": self.timestamp,
            "selected_files": self.selected_files,
            "categories": [c.to_json() for c in self.categories],
            "analysis_duration_seconds": self.analysis_duration_seconds,
            "project_structure": self.project_structure,
            "files_by_layer": self.files_by_layer,
            "historic_shas": self.historic_shas,
            "repo_doc_paths": self.repo_doc_paths,
            "exemplars": [e.to_json() for e in self.exemplars],
        }
        if self.test_decisions is not None:
            result["test_decisions"] = self.test_decisions.to_json()
        if self.pr_decisions is not None:
            result["pr_decisions"] = self.pr_decisions.to_json()
        return result

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> SessionResult:
        from hijack.core.exemplars import Exemplar  # local import to avoid circular
        test_decisions = None
        if "test_decisions" in data and data["test_decisions"] is not None:
            from hijack.core.test_decisions import TestDecisions
            test_decisions = TestDecisions.from_json(data["test_decisions"])
        pr_decisions = None
        if "pr_decisions" in data and data["pr_decisions"] is not None:
            from hijack.core.pr_decisions import PRDecisions
            pr_decisions = PRDecisions.from_json(data["pr_decisions"])
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
            historic_shas=data.get("historic_shas", []),
            repo_doc_paths=data.get("repo_doc_paths", []),
            exemplars=[Exemplar.from_json(e) for e in data.get("exemplars", [])],
            test_decisions=test_decisions,
            pr_decisions=pr_decisions,
        )
