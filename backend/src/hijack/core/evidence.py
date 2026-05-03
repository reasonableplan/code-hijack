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

    cited: int = 0           # mentions a real commit SHA / PR / Revert / ADR
    no_evidence: int = 0     # explicit [no-evidence] marker
    fake_citation: int = 0   # cited a commit SHA that wasn't in the input
    generic: int = 0         # generic-justification phrase, no citation
    other: int = 0           # neither cited nor flagged — silently uncited

    @property
    def total(self) -> int:
        return (
            self.cited
            + self.no_evidence
            + self.fake_citation
            + self.generic
            + self.other
        )

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
            "overall": _classification_to_json(self.overall),
            "by_category": {
                cat: _classification_to_json(c) for cat, c in self.by_category.items()
            },
        }


def classify_rule(
    rule: AnalysisRule,
    *,
    valid_shas: set[str] | None = None,
) -> str:
    """Return one of: 'cited' | 'no_evidence' | 'fake_citation' | 'generic' | 'other'.

    Priority order:
      1. Explicit [no-evidence] marker — most honest signal, beats everything.
      2. Any non-commit citation (PR / Revert / ADR / doc path) → cited.
         These citations don't have a verifiable SHA pool, so we accept them.
      3. Commit SHA mentions:
           - At least one matches `valid_shas` (or check skipped) → cited.
           - All commit SHAs in reason are unknown → fake_citation.
      4. Generic-justification phrase, no citation → generic.
      5. Otherwise → other.

    `valid_shas` is the set of full SHAs surfaced to the LLM. Pass None to
    skip verification (backward-compatible default).
    """
    reason = rule.reason or ""

    if _NO_EVIDENCE_PATTERN.search(reason):
        return "no_evidence"

    has_non_commit_citation = (
        _PR_PATTERN.search(reason)
        or _REVERT_PATTERN.search(reason)
        or _DOC_KEYWORD_PATTERN.search(reason)
        or _DOC_PATH_PATTERN.search(reason)
    )
    if has_non_commit_citation:
        return "cited"

    cited_shas = [m.group(1).lower() for m in _COMMIT_PATTERN.finditer(reason)]
    if cited_shas:
        if valid_shas is None or _any_sha_valid(cited_shas, valid_shas):
            return "cited"
        # All commit SHAs in this reason are unknown to the input pool.
        return "fake_citation"

    lowered = reason.lower()
    if any(phrase in lowered for phrase in _GENERIC_PHRASES):
        return "generic"

    return "other"


def compute_evidence_metrics(session: SessionResult) -> EvidenceMetrics:
    """Walk all rules in `session` and tally citation classifications.

    Uses `session.historic_shas` as the truth pool for SHA verification —
    sessions analysed without git history (or pre-Phase-A) carry an empty
    list, which disables the check.
    """
    metrics = EvidenceMetrics()
    valid_shas = {sha.lower() for sha in session.historic_shas} or None

    for cat in session.categories:
        bucket = metrics.by_category.setdefault(cat.category, RuleClassification())
        for rule in cat.rules:
            kind = classify_rule(rule, valid_shas=valid_shas)
            setattr(bucket, kind, getattr(bucket, kind) + 1)
            setattr(metrics.overall, kind, getattr(metrics.overall, kind) + 1)

    return metrics


def _any_sha_valid(cited_shas: list[str], valid_shas: set[str]) -> bool:
    """Whether any cited SHA is a prefix of (or equal to) a real full SHA.

    Cited SHAs are typically 7-12 hex chars; valid_shas hold full 40-char SHAs.
    A cited "a1b2c3d" matches valid "a1b2c3d4e5f6...".
    """
    for cited in cited_shas:
        for valid in valid_shas:
            if valid.startswith(cited):
                return True
    return False


def _classification_to_json(c: RuleClassification) -> dict[str, Any]:
    return {
        "cited": c.cited,
        "no_evidence": c.no_evidence,
        "fake_citation": c.fake_citation,
        "generic": c.generic,
        "other": c.other,
        "total": c.total,
        "cited_ratio": round(c.cited_ratio, 3),
    }


def render_metrics_md(metrics: EvidenceMetrics) -> str:
    """Markdown section for meta.md. Returns "" when there are no rules at all."""
    if metrics.overall.total == 0:
        return ""

    o = metrics.overall
    lines = [
        "## Evidence Coverage",
        "",
        "How many rules cite real artifacts (commit SHA / PR# / quoted revert / ADR)",
        "versus generic justifications. Higher cited-ratio = less LLM opinion.",
        "Fake citations are commit SHAs the LLM invented — they were not in the input.",
        "",
        f"- **Cited**: {o.cited} ({_pct(o.cited, o.total)}%)",
        f"- **No-evidence (flagged)**: {o.no_evidence} ({_pct(o.no_evidence, o.total)}%)",
        f"- **Fake citation (hallucinated SHA)**: {o.fake_citation} "
        f"({_pct(o.fake_citation, o.total)}%)",
        f"- **Generic justification**: {o.generic} ({_pct(o.generic, o.total)}%)",
        f"- **Other (uncited)**: {o.other} ({_pct(o.other, o.total)}%)",
        f"- **Total rules**: {o.total}",
        "",
    ]

    if metrics.by_category:
        lines += [
            "### By Category",
            "",
            "| Category | Cited | No-evidence | Fake | Generic | Other | Total | Cited % |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for cat, c in metrics.by_category.items():
            lines.append(
                f"| {cat} | {c.cited} | {c.no_evidence} | {c.fake_citation} | "
                f"{c.generic} | {c.other} | {c.total} | {_pct(c.cited, c.total)}% |"
            )

    return "\n".join(lines)


def _pct(n: int, total: int) -> int:
    return (n * 100) // total if total else 0
