"""PR/issue archaeology — mine closed-unmerged PRs and wontfix issues via gh CLI.

Impure module: calls `gh api` via subprocess. Pure parsing/pattern-matching
logic is imported from archaeology.py to avoid duplication.

Pure/I-O split:
  - Pattern matching and dataclass construction: pure helpers.
  - `fetch_pr_decisions`: impure — subprocess, gh CLI dependency.

Graceful skip:
  gh not installed (FileNotFoundError), auth failure (returncode != 0),
  rate-limit (JSON "message" key), timeout (TimeoutExpired) → logger.warning
  + empty PRDecisions(items_scanned=0, patterns=[], decisions=[]).
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from dataclasses import dataclass
from typing import Any

from hijack.core.archaeology import (
    _COMPILED_PATTERNS,
    DecisionPattern,
    _sanitize_body_excerpt,
)

logger = logging.getLogger(__name__)

# Cap on decisions output list.
_DECISIONS_TOP_N = 50

# Cap on diff excerpt length (chars) per decision.
_DIFF_EXCERPT_CHARS = 1500

# Cap on number of diff-fetch API calls per fetch_pr_decisions run (network budget).
_MAX_DIFF_FETCHES = 15

# Patterns that indicate an incident (revert/rollback in the body).
_INCIDENT_RE = re.compile(r"\b(revert|rollback|roll[-\s]back|regression)\b", re.IGNORECASE)

# Patterns indicating explicit maintainer rejection in a comment.
_REJECTION_COMMENT_RE = re.compile(
    r"\b(won't\s+merge|closing\s+without\s+merge|not\s+going\s+to\s+merge|"
    r"closing\s+this|rejected|not\s+a\s+good\s+fit|out\s+of\s+scope)\b",
    re.IGNORECASE,
)

# GitHub URL pattern: extract owner/repo.
_GITHUB_URL_RE = re.compile(
    r"(?:https?://github\.com/|git@github\.com:)([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$"
)


# ---------------------------------------------------------------------------
# Public dataclasses
# ---------------------------------------------------------------------------

@dataclass
class PRDecision:
    """A single PR or issue that contains decision-trail signals."""

    ref: str              # "PR#123" or "issue#456"
    title: str
    date: str             # ISO ("2024-08-12 14:30:00 +0900" format)
    body_excerpt: str     # first _BODY_EXCERPT_CHARS chars, whitespace-normalised
    matched_patterns: list[str]  # matched pattern display names; sorted asc
    maintainer_comment: str      # last maintainer comment (empty string if none)
    intent_kind: str      # "rejection" | "incident" | "preference"
    diff_excerpt: str = ""       # rejection/incident PR diff excerpt (empty if unavailable)

    def to_json(self) -> dict[str, Any]:
        return {
            "ref": self.ref,
            "title": self.title,
            "date": self.date,
            "body_excerpt": self.body_excerpt,
            "matched_patterns": self.matched_patterns,
            "maintainer_comment": self.maintainer_comment,
            "intent_kind": self.intent_kind,
            "diff_excerpt": self.diff_excerpt,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> PRDecision:
        return cls(
            ref=data["ref"],
            title=data["title"],
            date=data["date"],
            body_excerpt=data.get("body_excerpt", ""),
            matched_patterns=data.get("matched_patterns", []),
            maintainer_comment=data.get("maintainer_comment", ""),
            intent_kind=data.get("intent_kind", "preference"),
            diff_excerpt=data.get("diff_excerpt", ""),
        )


@dataclass
class PRDecisions:
    """Aggregated PR/issue decision-trail mining results."""

    __test__ = False

    items_scanned: int
    patterns: list[DecisionPattern]
    decisions: list[PRDecision]     # date desc; capped at _DECISIONS_TOP_N

    def to_json(self) -> dict[str, Any]:
        return {
            "items_scanned": self.items_scanned,
            "patterns": [p.to_json() for p in self.patterns],
            "decisions": [d.to_json() for d in self.decisions],
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> PRDecisions:
        return cls(
            items_scanned=data.get("items_scanned", 0),
            patterns=[DecisionPattern.from_json(p) for p in data.get("patterns", [])],
            decisions=[PRDecision.from_json(d) for d in data.get("decisions", [])],
        )

    @property
    def has_signal(self) -> bool:
        return bool(self.patterns or self.decisions)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_github_url(repo_url: str) -> tuple[str, str] | None:
    """Extract (owner, repo) from a GitHub URL. Returns None for non-GitHub URLs."""
    m = _GITHUB_URL_RE.match(repo_url.strip())
    if m is None:
        return None
    return m.group(1), m.group(2)


def _iso_to_date_str(iso: str) -> str:
    """Convert ISO 8601 timestamp to archaeology.py date format.

    Input:  "2024-08-12T14:30:00Z" or "2024-08-12T14:30:00+09:00"
    Output: "2024-08-12 14:30:00 +0000" (approximate — no tz conversion)
    """
    # Replace T with space, strip trailing Z or +HH:MM
    cleaned = iso.replace("T", " ")
    # Normalise timezone part
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + " +0000"
    elif "+" in cleaned[10:]:
        # already has offset
        cleaned = cleaned.replace("+", " +", 1) if " +" not in cleaned else cleaned
    elif cleaned.count("-") > 2:
        # negative offset like 2024-08-12 14:30:00-05:00
        idx = cleaned.rfind("-")
        cleaned = cleaned[:idx] + " -" + cleaned[idx + 1:]
    return cleaned


def _gh_api(
    path: str,
    *,
    timeout: int,
) -> list[dict] | None:
    """Call `gh api <path>` and return parsed JSON list.

    Returns None on:
      - FileNotFoundError (gh not installed)
      - TimeoutExpired
      - Non-zero returncode
      - Response with a "message" key (rate-limit or error)
    """
    try:
        result = subprocess.run(
            ["gh", "api", path],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except FileNotFoundError:
        logger.warning("gh CLI not found — skipping PR/issue mining")
        return None
    except subprocess.TimeoutExpired:
        logger.warning("gh api timed out for %s — skipping", path)
        return None

    if result.returncode != 0:
        logger.warning(
            "gh api failed (rc=%d) for %s — skipping PR/issue mining",
            result.returncode,
            path,
        )
        return None

    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError:
        logger.warning("gh api returned non-JSON for %s — skipping", path)
        return None

    # Rate-limit or error response is a dict with "message"
    if isinstance(parsed, dict) and "message" in parsed:
        logger.warning(
            "gh api returned error message for %s: %s — skipping",
            path,
            parsed["message"],
        )
        return None

    if not isinstance(parsed, list):
        logger.warning("gh api returned unexpected type for %s — skipping", path)
        return None

    return parsed


def _get_maintainer_comment(
    owner: str, repo: str, pr_number: int, *, timeout: int
) -> str:
    """Fetch the maintainer comment on a PR. Returns empty string on failure.

    Prefers the last comment matching _REJECTION_COMMENT_RE (explicit rejection
    language); falls back to the last comment overall if none match.
    """
    path = f"repos/{owner}/{repo}/issues/{pr_number}/comments"
    comments = _gh_api(path, timeout=timeout)
    if not comments:
        return ""
    for comment in reversed(comments):
        body = comment.get("body", "")
        if _REJECTION_COMMENT_RE.search(body):
            return body
    # No rejection-language comment — fall back to the last comment overall
    return comments[-1].get("body", "")


def _determine_intent_kind(
    merged_at: str | None,
    body: str,
    maintainer_comment: str,
    ref: str,
) -> str:
    """Classify intent: "rejection" | "incident" | "preference".

    Rules (priority order):
    1. revert/rollback/regression in body or it's a wontfix issue → "incident"
    2. closed-unmerged PR (merged_at is None) → "rejection"
    3. everything else → "preference"
    """
    combined = (body or "") + " " + (maintainer_comment or "")

    # Incident: revert/rollback/regression signals
    if _INCIDENT_RE.search(combined):
        return "incident"

    # Rejection: closed without merge
    if merged_at is None and ref.startswith("PR#"):
        return "rejection"

    return "preference"


def _match_patterns(text: str) -> list[str]:
    """Return sorted list of _DECISION_PATTERNS display names matched in text."""
    matched: list[str] = []
    for name, compiled_re in _COMPILED_PATTERNS:
        if compiled_re.search(text):
            matched.append(name)
    matched.sort()
    return matched


def _is_bot_pr(item: dict) -> bool:
    """True if the PR author is a bot (e.g. dependabot).

    Bot bump PRs pollute intent_kind classification — "regression" in a
    dependency-bump body reads as "incident" even though nothing failed
    (~4-5/10 measured noise). Filtering here also saves a diff-fetch API call.
    """
    user = item.get("user") or {}
    return user.get("type") == "Bot" or str(user.get("login", "")).endswith("[bot]")


def _get_pr_diff_excerpt(
    owner: str, repo: str, pr_number: int, *, timeout: int
) -> str:
    """Fetch a diff excerpt for a PR's changed files. Returns "" on failure.

    Skips test files (path segment/filename containing "test"). Concatenates
    each file's patch as "--- {filename}\\n{patch}" and truncates to
    _DIFF_EXCERPT_CHARS.
    """
    path = f"repos/{owner}/{repo}/pulls/{pr_number}/files"
    files = _gh_api(path, timeout=timeout)
    if not files:
        return ""

    chunks: list[str] = []
    for f in files:
        filename = f.get("filename", "")
        if "test" in filename.lower():
            continue
        patch = f.get("patch")
        if not patch:
            continue
        chunks.append(f"--- {filename}\n{patch}")

    if not chunks:
        return ""

    return "\n".join(chunks)[:_DIFF_EXCERPT_CHARS]


def _build_decision_from_pr(
    item: dict,
    owner: str,
    repo: str,
    *,
    timeout: int,
) -> PRDecision | None:
    """Build a PRDecision from a closed-unmerged PR item. Returns None if no pattern match."""
    if _is_bot_pr(item):
        return None

    merged_at = item.get("merged_at")
    # Only process closed-unmerged PRs
    if merged_at is not None:
        return None

    number = item.get("number", 0)
    title = item.get("title", "")
    body = item.get("body") or ""
    created_at = item.get("created_at", "")

    matched = _match_patterns(body)
    if not matched:
        return None

    maintainer_comment = _get_maintainer_comment(owner, repo, number, timeout=timeout)
    intent_kind = _determine_intent_kind(merged_at, body, maintainer_comment, f"PR#{number}")

    return PRDecision(
        ref=f"PR#{number}",
        title=title,
        date=_iso_to_date_str(created_at),
        body_excerpt=_sanitize_body_excerpt(body),
        matched_patterns=matched,
        maintainer_comment=maintainer_comment,
        intent_kind=intent_kind,
    )


def _build_decision_from_issue(item: dict) -> PRDecision | None:
    """Build a PRDecision from a wontfix issue item. Returns None if no pattern match."""
    number = item.get("number", 0)
    title = item.get("title", "")
    body = item.get("body") or ""
    created_at = item.get("created_at", "")

    matched = _match_patterns(body)
    if not matched:
        return None

    intent_kind = _determine_intent_kind(None, body, "", f"issue#{number}")

    return PRDecision(
        ref=f"issue#{number}",
        title=title,
        date=_iso_to_date_str(created_at),
        body_excerpt=_sanitize_body_excerpt(body),
        matched_patterns=matched,
        maintainer_comment="",
        intent_kind=intent_kind,
    )


def _aggregate_patterns(decisions: list[PRDecision]) -> list[DecisionPattern]:
    """Build DecisionPattern aggregates from a list of PRDecision objects."""
    pattern_agg: dict[str, tuple[int, list[str]]] = {}
    for d in decisions:
        for name in d.matched_patterns:
            if name not in pattern_agg:
                pattern_agg[name] = (0, [])
            count, examples = pattern_agg[name]
            count += 1
            if len(examples) < 3 and d.body_excerpt:
                examples.append(d.body_excerpt[:120])
            pattern_agg[name] = (count, examples)

    patterns: list[DecisionPattern] = [
        DecisionPattern(pattern=name, count=count, examples=examples)
        for name, (count, examples) in pattern_agg.items()
    ]
    patterns.sort(key=lambda p: (-p.count, p.pattern))
    return patterns


# ---------------------------------------------------------------------------
# Public impure function
# ---------------------------------------------------------------------------

def fetch_pr_decisions(repo_url: str, *, timeout: int = 30) -> PRDecisions:
    """Mine closed-unmerged PRs and wontfix issues from a GitHub repo via gh CLI.

    Returns an empty PRDecisions on any failure (gh not installed, auth failure,
    rate-limit, timeout, non-GitHub URL) — never raises.
    """
    _empty = PRDecisions(items_scanned=0, patterns=[], decisions=[])

    parsed_url = _parse_github_url(repo_url)
    if parsed_url is None:
        return _empty

    owner, repo = parsed_url

    # Fetch closed PRs (will filter merged_at later)
    pr_path = f"repos/{owner}/{repo}/pulls?state=closed&per_page=100"
    pr_items = _gh_api(pr_path, timeout=timeout)
    if pr_items is None:
        return _empty

    # Fetch wontfix issues
    issue_path = f"repos/{owner}/{repo}/issues?state=closed&labels=wontfix&per_page=100"
    issue_items = _gh_api(issue_path, timeout=timeout)
    if issue_items is None:
        # Partial graceful: issues failed but PRs succeeded — still return empty
        # to be consistent (can't have complete picture)
        logger.warning("gh api failed for issues endpoint — returning empty PRDecisions")
        return _empty

    items_scanned = len(pr_items) + len(issue_items)

    all_decisions: list[PRDecision] = []

    for item in pr_items:
        decision = _build_decision_from_pr(item, owner, repo, timeout=timeout)
        if decision is not None:
            all_decisions.append(decision)

    for item in issue_items:
        decision = _build_decision_from_issue(item)
        if decision is not None:
            all_decisions.append(decision)

    # Sort by date desc (ISO lexicographic is fine for same-format strings)
    all_decisions.sort(key=lambda d: d.date, reverse=True)
    all_decisions = all_decisions[:_DECISIONS_TOP_N]

    # Second pass: fetch diff excerpts for rejection/incident PRs only (issues
    # have no diff). Capped at _MAX_DIFF_FETCHES — network budget.
    diff_fetches = 0
    for decision in all_decisions:
        if diff_fetches >= _MAX_DIFF_FETCHES:
            break
        if not decision.ref.startswith("PR#"):
            continue
        if decision.intent_kind not in ("rejection", "incident"):
            continue
        pr_number = int(decision.ref[len("PR#"):])
        decision.diff_excerpt = _get_pr_diff_excerpt(
            owner, repo, pr_number, timeout=timeout
        )
        diff_fetches += 1

    patterns = _aggregate_patterns(all_decisions)

    return PRDecisions(
        items_scanned=items_scanned,
        patterns=patterns,
        decisions=all_decisions,
    )


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

# Section order + titles, aligned with the tool's mission (rejection/incident
# PRs are WHY-evidence; preference is supplementary context).
_SECTION_TITLES: dict[str, str] = {
    "rejection": "Rejected proposals (closed without merge)",
    "incident": "Incidents (revert/rollback signals)",
    "preference": "Reviewer preferences",
}


def render_pr_decisions_md(decisions: PRDecisions, *, source_target: str) -> str:
    """Render PRDecisions as Markdown.

    Returns '' when has_signal is False — caller skips writing the file.

    Output sections:
    - Preamble blockquote with items_scanned + source_target
    - Recurring decision patterns (by occurrence)
    - Decisions grouped by intent_kind, in rejection -> incident -> preference
      order (rejection/incident are cited-evidence-grade; preference is not)

    Sections are only rendered when their lists are non-empty — no "(none)"
    placeholders are emitted (same convention as render_commit_decisions_md).
    """
    if not decisions.has_signal:
        return ""

    lines: list[str] = [
        "# PR Decisions -- what the senior team explicitly rejected or reverted",
        "",
        f"> Mined from {decisions.items_scanned} PRs/issues of {source_target}:"
        " closed-unmerged proposals, incident reverts, and reviewer preferences",
        "> recorded in GitHub PR/issue history. Rejection and incident decisions",
        "> are cited-evidence-grade -- MUST rules may cite them directly.",
        "",
    ]

    # --- Section: recurring decision patterns ---
    if decisions.patterns:
        lines += ["## Recurring decision patterns (by occurrence)", ""]
        for i, dp in enumerate(decisions.patterns, start=1):
            lines.append(f"{i}. **{dp.pattern}** ({dp.count} items)")
            for ex in dp.examples:
                lines.append(f'   - "{ex}"')
        lines.append("")

    # --- Sections: decisions grouped by intent_kind ---
    by_kind: dict[str, list[PRDecision]] = {"rejection": [], "incident": [], "preference": []}
    for d in decisions.decisions:
        by_kind.setdefault(d.intent_kind, []).append(d)

    for kind in ("rejection", "incident", "preference"):
        items = by_kind.get(kind, [])
        if not items:
            continue
        lines += [f"## {_SECTION_TITLES[kind]}", ""]
        for d in items:
            date_short = d.date[:10] if d.date else "?"
            lines.append(f"- `{d.ref}` ({date_short}) **{d.title}**")
            if d.matched_patterns:
                pattern_str = ", ".join(f"`{p}`" for p in d.matched_patterns)
                lines.append(f"  matched: {pattern_str}")
            if d.maintainer_comment:
                comment = " ".join(d.maintainer_comment.split())
                lines.append(f'  maintainer: "{comment[:200]}"')
            if d.body_excerpt:
                lines.append(f"  > {d.body_excerpt}")
            if d.diff_excerpt:
                lines.append("  Rejected code:")
                lines.append("  ```diff")
                for diff_line in d.diff_excerpt.splitlines():
                    lines.append(f"  {diff_line}")
                lines.append("  ```")
        lines.append("")

    return "\n".join(lines)
