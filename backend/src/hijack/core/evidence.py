"""Evidence coverage metrics — does the LLM cite history, or just opine?

The whole point of Phase A's prompt change is to make the LLM ground rule
reasons in real artifacts (commit SHAs, reverts, PR numbers) instead of
generating plausible-but-unsourced "best practice" rationales. This module
turns that goal into a number we can track session-to-session.

Detection is intentionally pattern-based and conservative — false-negatives
(missing a citation that's worded oddly) are fine; false-positives (calling
generic prose "cited") are not, because the metric would lie.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from hijack.core.models import AnalysisRule, SessionResult

# A short SHA between 6 and 40 hex chars. Word boundaries on both sides keep
# us from matching arbitrary hex inside identifiers like `0xdeadbeef_value`.
_COMMIT_PATTERN = re.compile(r"\bcommit\s+([0-9a-f]{6,40})\b", re.IGNORECASE)
# "PR #142", "pr#142", "pull/142", "PR 142" — common GitHub-style references.
_PR_PATTERN = re.compile(r"\b(?:pr|pull)\s*[/#]?\s*(\d{1,6})\b", re.IGNORECASE)
# Explicit no-evidence marker the prompt instructs the LLM to use.
_NO_EVIDENCE_PATTERN = re.compile(r"\[no-evidence\]", re.IGNORECASE)
# Heuristic: a literal "Revert" mention with quoting/punctuation is a citation
# of a revert subject. Bare-word "revert" is too noisy to treat as evidence.
_REVERT_PATTERN = re.compile(r"['\"`]\s*Revert", re.IGNORECASE)
# Doc citations from <repo_context>: ADR / README / ARCHITECTURE / CONTRIBUTING
# / DESIGN, either as the bare keyword (uppercase, distinctive) or as a markdown
# path in backticks (`docs/adr/0003-foo.md`, `ARCHITECTURE.md`).
_DOC_KEYWORD_PATTERN = re.compile(
    r"\b(?:ADR|README|ARCHITECTURE|CONTRIBUTING|DESIGN)\b"
)
_DOC_PATH_PATTERN = re.compile(r"`[^`]*\.(?:md|markdown|mdx|rst)`", re.IGNORECASE)

# Phrases that almost always signal LLM-generated rationale rather than
# real evidence. If a reason matches no citation pattern AND contains one of
# these, classify it as `generic`. Kept short on purpose — adding too many
# entries would over-flag legitimate reasons that happen to use these words.
_GENERIC_PHRASES = (
    "best practice",
    "best practices",
    "industry standard",
    "industry standards",
    "more readable",
    "improves readability",
    "clean code",
    "good practice",
    "follows convention",
    "following convention",
    "common pattern",
    "for clarity",
    "for maintainability",
)


@dataclass
class RuleClassification:
    """Per-rule classification — every rule belongs to exactly one bucket."""

    cited: int = 0          # mentions a commit SHA, PR#, or quoted Revert
    no_evidence: int = 0    # explicit [no-evidence] marker
    generic: int = 0        # generic-justification phrase, no citation
    other: int = 0          # neither cited nor flagged — silently uncited

    @property
    def total(self) -> int:
        return self.cited + self.no_evidence + self.generic + self.other

    @property
    def cited_ratio(self) -> float:
        return self.cited / self.total if self.total else 0.0


@dataclass
class EvidenceMetrics:
    """Whole-session evidence coverage."""

    overall: RuleClassification = field(default_factory=RuleClassification)
    by_category: dict[str, RuleClassification] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "overall": {
                "cited": self.overall.cited,
                "no_evidence": self.overall.no_evidence,
                "generic": self.overall.generic,
                "other": self.overall.other,
                "total": self.overall.total,
                "cited_ratio": round(self.overall.cited_ratio, 3),
            },
            "by_category": {
                cat: {
                    "cited": c.cited,
                    "no_evidence": c.no_evidence,
                    "generic": c.generic,
                    "other": c.other,
                    "total": c.total,
                    "cited_ratio": round(c.cited_ratio, 3),
                }
                for cat, c in self.by_category.items()
            },
        }


def classify_rule(rule: AnalysisRule) -> str:
    """Return one of: 'cited' | 'no_evidence' | 'generic' | 'other'.

    Order matters: we check explicit no-evidence marker first (it can co-exist
    with a generic phrase), then citation patterns (which trump generic), then
    generic-phrase detection.
    """
    reason = rule.reason or ""

    if _NO_EVIDENCE_PATTERN.search(reason):
        return "no_evidence"

    if (
        _COMMIT_PATTERN.search(reason)
        or _PR_PATTERN.search(reason)
        or _REVERT_PATTERN.search(reason)
        or _DOC_KEYWORD_PATTERN.search(reason)
        or _DOC_PATH_PATTERN.search(reason)
    ):
        return "cited"

    lowered = reason.lower()
    if any(phrase in lowered for phrase in _GENERIC_PHRASES):
        return "generic"

    return "other"


def compute_evidence_metrics(session: SessionResult) -> EvidenceMetrics:
    """Walk all rules in `session` and tally citation classifications."""
    metrics = EvidenceMetrics()

    for cat in session.categories:
        bucket = metrics.by_category.setdefault(cat.category, RuleClassification())
        for rule in cat.rules:
            kind = classify_rule(rule)
            setattr(bucket, kind, getattr(bucket, kind) + 1)
            setattr(metrics.overall, kind, getattr(metrics.overall, kind) + 1)

    return metrics


def render_metrics_md(metrics: EvidenceMetrics) -> str:
    """Markdown section for meta.md. Returns "" when there are no rules at all."""
    if metrics.overall.total == 0:
        return ""

    o = metrics.overall
    lines = [
        "## Evidence Coverage",
        "",
        "How many rules cite real artifacts (commit SHA / PR# / quoted revert)",
        "versus generic justifications. Higher cited-ratio = less LLM opinion.",
        "",
        f"- **Cited**: {o.cited} ({_pct(o.cited, o.total)}%)",
        f"- **No-evidence (flagged)**: {o.no_evidence} ({_pct(o.no_evidence, o.total)}%)",
        f"- **Generic justification**: {o.generic} ({_pct(o.generic, o.total)}%)",
        f"- **Other (uncited)**: {o.other} ({_pct(o.other, o.total)}%)",
        f"- **Total rules**: {o.total}",
        "",
    ]

    if metrics.by_category:
        lines += [
            "### By Category",
            "",
            "| Category | Cited | No-evidence | Generic | Other | Total | Cited % |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
        for cat, c in metrics.by_category.items():
            lines.append(
                f"| {cat} | {c.cited} | {c.no_evidence} | {c.generic} | "
                f"{c.other} | {c.total} | {_pct(c.cited, c.total)}% |"
            )

    return "\n".join(lines)


def _pct(n: int, total: int) -> int:
    return (n * 100) // total if total else 0
