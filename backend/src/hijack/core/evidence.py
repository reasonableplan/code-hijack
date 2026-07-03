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

# ref_files entry shape: "<repo-relative-path>:<N>" or "<path>:<N>-<M>".
# Used to distinguish ref_files entries that actually point at a line
# (concrete grounding) from bare path-only strings (too vague to count).
_REF_FILE_LINE_PATTERN = re.compile(r":(\d+)(?:-\d+)?$")


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
    valid_doc_paths: set[str] | None = None,
    valid_file_paths: set[str] | None = None,
    valid_pr_refs: set[str] | None = None,
) -> str:
    """Return one of: 'cited' | 'no_evidence' | 'fake_citation' | 'generic' | 'other'.

    Two paths, picked by whether the rule carries structured Evidence:

    Path A — `rule.evidence` is non-empty (Phase D1 default):
      Validate each entry's `ref` against the truth pools. If at least one
      entry has a valid ref (or pool is None/empty, which disables the check),
      the rule is `cited`. If every entry's ref is invalid (and we have pools
      to check against), classify as `fake_citation` — the LLM populated the
      structured field but every citation was hallucinated. `valid_pr_refs`
      is the truth pool for `kind="pr"` entries (PR#123 / issue#456 refs
      mined by pr_archaeology.py) — same accept-if-no-pool best-effort rule
      as `valid_shas`/`valid_doc_paths`.

    Path B — `rule.evidence` is empty (Phase A/B / pre-D1 sessions):
      Fall back to scanning `rule.reason` for citation patterns. Priority:
      [no-evidence] marker > non-commit citation > commit SHA (validated) >
      ref_files line-anchor (when `valid_file_paths` is provided) >
      generic phrase > other. The ref_files step grounds skill-mode sessions
      where the LLM writes prose reasons but populates `ref_files` with real
      `path:line` anchors — without it, every such rule lands in 'other' and
      gets downgraded.
    """
    if rule.evidence:
        return _classify_via_evidence(
            rule.evidence,
            valid_shas=valid_shas,
            valid_doc_paths=valid_doc_paths,
            valid_pr_refs=valid_pr_refs,
        )

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
        return "fake_citation"

    if _has_valid_ref_files(rule.ref_files, valid_file_paths):
        return "cited"

    lowered = reason.lower()
    if any(phrase in lowered for phrase in _GENERIC_PHRASES):
        return "generic"

    return "other"


def _classify_via_evidence(
    evidence_list: list,  # list[Evidence] — typed loose to avoid circular import
    *,
    valid_shas: set[str] | None,
    valid_doc_paths: set[str] | None,
    valid_pr_refs: set[str] | None = None,
) -> str:
    """Score a non-empty Evidence list as 'cited' or 'fake_citation'."""
    saw_real = False
    saw_fake = False
    for e in evidence_list:
        if e.kind in ("commit", "revert"):
            ref = (e.ref or "").lower()
            if not ref:
                saw_fake = True
                continue
            if valid_shas is None or not valid_shas:
                # No truth pool → can't verify; accept as real (best-effort).
                saw_real = True
            elif _any_sha_valid([ref], valid_shas):
                saw_real = True
            else:
                saw_fake = True
        elif e.kind == "doc":
            if valid_doc_paths is None or not valid_doc_paths or e.ref in valid_doc_paths:
                saw_real = True
            else:
                saw_fake = True
        elif e.kind == "pr":
            ref = (e.ref or "").strip()
            if not ref:
                saw_fake = True
            elif valid_pr_refs is None or not valid_pr_refs:
                # No truth pool → can't verify; accept as real (best-effort).
                saw_real = True
            elif ref.casefold() in valid_pr_refs:
                saw_real = True
            else:
                saw_fake = True
        else:
            # Unknown kind shouldn't survive analyzer validation, but be safe.
            saw_fake = True

    if saw_real:
        return "cited"
    if saw_fake:
        return "fake_citation"
    return "other"


def downgrade_speculative_rules(session: SessionResult) -> int:
    """MUST rules whose evidence isn't verified-cited get downgraded to SHOULD.

    A rule is "speculative" when `classify_rule` returns anything except 'cited' —
    no_evidence (rule.evidence empty + [no-evidence] reason), fake_citation
    (Evidence entries with invalid SHAs / doc paths), generic ("best practice"-
    style filler), or other (no citation pattern detected at all).

    Mutates `session` in place. Returns the count of rules downgraded so the
    caller can log a stderr notice. Cited MUSTs are untouched; existing SHOULDs
    are also untouched (only MUST → SHOULD transitions happen here).

    Why: the tool's whole differentiator is verbatim evidence chains. A MUST
    without evidence is indistinguishable from generic LLM-generated rules and
    erodes the priority signal. The downgrade preserves the rule (sometimes
    speculative rules are correct intuition) but stops it from claiming
    PR-blocker authority it can't back.
    """
    valid_shas = {sha.lower() for sha in session.historic_shas} or None
    valid_doc_paths = set(session.repo_doc_paths) or None
    valid_file_paths = set(session.selected_files) or None
    valid_pr_refs = _valid_pr_refs_from_session(session)

    count = 0
    for cat in session.categories:
        for rule in cat.rules:
            if rule.priority != "MUST":
                continue
            kind = classify_rule(
                rule,
                valid_shas=valid_shas,
                valid_doc_paths=valid_doc_paths,
                valid_file_paths=valid_file_paths,
                valid_pr_refs=valid_pr_refs,
            )
            if kind != "cited":
                rule.priority = "SHOULD"
                count += 1
    return count


def _valid_pr_refs_from_session(session: SessionResult) -> set[str] | None:
    """Build the truth pool of PR/issue refs surfaced to the LLM.

    `session.pr_decisions` is duck-typed (Any) — it may be a pr_archaeology
    PRDecisions dataclass (`.decisions[*].ref`) or a raw dict deserialized
    from session.json (`["decisions"][*]["ref"]`). Refs are casefolded so
    "PR#123" from the LLM matches "pr#123" in the pool. Returns None when
    pr_decisions is falsy or yields no refs — best-effort accept, same
    principle as the commit/doc truth pools above.
    """
    pr_decisions = session.pr_decisions
    if not pr_decisions:
        return None
    if isinstance(pr_decisions, dict):
        raw_decisions = pr_decisions.get("decisions", [])
        refs = [d.get("ref", "") for d in raw_decisions if isinstance(d, dict)]
    else:
        refs = [getattr(d, "ref", "") for d in getattr(pr_decisions, "decisions", [])]
    return {ref.casefold() for ref in refs if ref} or None


def compute_evidence_metrics(session: SessionResult) -> EvidenceMetrics:
    """Walk all rules in `session` and tally citation classifications.

    Uses `session.historic_shas`, `session.repo_doc_paths`, and the PR/issue
    refs in `session.pr_decisions` as truth pools for ref verification.
    Sessions analysed without git history / docs / PR mining (or pre-Phase-A/B)
    carry empty pools, which disable the corresponding check.
    """
    metrics = EvidenceMetrics()
    valid_shas = {sha.lower() for sha in session.historic_shas} or None
    valid_doc_paths = set(session.repo_doc_paths) or None
    valid_file_paths = set(session.selected_files) or None
    valid_pr_refs = _valid_pr_refs_from_session(session)

    for cat in session.categories:
        bucket = metrics.by_category.setdefault(cat.category, RuleClassification())
        for rule in cat.rules:
            kind = classify_rule(
                rule,
                valid_shas=valid_shas,
                valid_doc_paths=valid_doc_paths,
                valid_file_paths=valid_file_paths,
                valid_pr_refs=valid_pr_refs,
            )
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


def _has_valid_ref_files(
    ref_files: list[str],
    valid_file_paths: set[str] | None,
) -> bool:
    """Whether ref_files contains at least one entry that:
    - has a line-number suffix (`path:N` or `path:N-M`), AND
    - whose file part is in valid_file_paths.

    Returns False when ref_files is empty OR valid_file_paths is None/empty.
    The latter makes this check opt-in: existing callers that don't pass
    `valid_file_paths` (tests, older code) keep their previous behaviour.
    A bare path entry without a line number is also rejected — the whole
    point is concrete grounding, not "the file exists somewhere".
    """
    if not ref_files or not valid_file_paths:
        return False
    for ref in ref_files:
        m = _REF_FILE_LINE_PATTERN.search(ref)
        if m is None:
            continue
        path = ref[:m.start()]
        if path in valid_file_paths:
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
