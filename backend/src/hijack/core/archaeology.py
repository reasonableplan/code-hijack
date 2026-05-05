"""Git archaeology — turn `git log` output into structured history per file.

Pure module: no subprocess, no I/O. The wrapper in `hijack.io.git` invokes git and
hands the stdout string to `parse_git_log` here. Keeping the parser pure makes it
testable from string fixtures and isolates the subprocess seam.

Why ASCII separators (RS / US) over tab/newline?
- Commit subjects and bodies routinely contain tabs and newlines.
- 0x1e (RS) and 0x1f (US) almost never appear in human-written messages, so
  splitting on them is unambiguous without fragile escaping.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# Field separator inside a commit record.
RECORD_SEP = "\x1e"
# Terminator at the end of each commit record.
UNIT_SEP = "\x1f"

# Matches the format string used by io.git: %H<RS>%s<RS>%an<RS>%ai<RS>%b<US>
GIT_LOG_FORMAT = f"%H{RECORD_SEP}%s{RECORD_SEP}%an{RECORD_SEP}%ai{RECORD_SEP}%b{UNIT_SEP}"


@dataclass
class Commit:
    sha: str
    subject: str
    author: str
    date: str  # ISO-like: "2024-08-12 14:30:00 +0900"
    body: str

    @property
    def short_sha(self) -> str:
        return self.sha[:7]

    def to_json(self) -> dict[str, Any]:
        return {
            "sha": self.sha,
            "subject": self.subject,
            "author": self.author,
            "date": self.date,
            "body": self.body,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Commit:
        return cls(
            sha=data["sha"],
            subject=data["subject"],
            author=data["author"],
            date=data["date"],
            body=data.get("body", ""),
        )


@dataclass
class FileHistory:
    commits: list[Commit] = field(default_factory=list)
    reverts: list[Commit] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.commits and not self.reverts

    def to_json(self) -> dict[str, Any]:
        return {
            "commits": [c.to_json() for c in self.commits],
            "reverts": [c.to_json() for c in self.reverts],
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> FileHistory:
        return cls(
            commits=[Commit.from_json(c) for c in data.get("commits", [])],
            reverts=[Commit.from_json(c) for c in data.get("reverts", [])],
        )


def parse_git_log(stdout: str) -> list[Commit]:
    """Parse stdout produced with GIT_LOG_FORMAT into Commit objects.

    Drops malformed records silently — git history is best-effort context.

    Note: don't call `str.strip()` on whole records here. Python's default strip
    treats the ASCII separators \\x1e/\\x1f as whitespace, which would erase the
    trailing RECORD_SEP that delimits an empty body, collapsing the field count
    from 5 to 4 and dropping the commit. Split first, strip fields individually.
    """
    if not stdout:
        return []

    commits: list[Commit] = []
    for raw_record in stdout.split(UNIT_SEP):
        # Skip empty / whitespace-only chunks (the trailing chunk after the last
        # UNIT_SEP, plus any blank lines git may emit).
        if not raw_record or raw_record.strip("\n\r\t ") == "":
            continue
        # Drop a leading newline that git inserts between records, but preserve
        # \x1e separators inside the record.
        record = raw_record.lstrip("\n\r")
        fields = record.split(RECORD_SEP)
        if len(fields) < 5:
            continue
        # %b can itself contain RECORD_SEP if a commit message is pathological;
        # rejoin trailing fields back into the body.
        sha = fields[0].strip()
        subject = fields[1].strip()
        author = fields[2].strip()
        date = fields[3].strip()
        body = RECORD_SEP.join(fields[4:]).strip()
        if not sha:
            continue
        commits.append(
            Commit(sha=sha, subject=subject, author=author, date=date, body=body)
        )
    return commits


def render_history_for_prompt(
    history: FileHistory | None,
    *,
    max_commits: int = 3,
    max_body_chars: int = 800,
) -> str:
    """Render a FileHistory as a compact <history> block for prompt injection.

    Returns "" when there is nothing to show — caller can drop the block entirely.

    Body cap is generous (800 chars) on purpose: the senior's actual rationale
    often lives in commit bodies, not subjects. Cutting at 200 chars erased the
    very evidence we want the LLM to cite. Multi-line bodies are preserved
    (each line indented two spaces) so bullet-point reasoning survives intact.
    """
    if history is None or history.is_empty():
        return ""

    lines: list[str] = ["<history>"]
    for c in history.commits[:max_commits]:
        date_short = c.date[:10] if c.date else "?"
        body = c.body.strip()
        if len(body) > max_body_chars:
            body = body[:max_body_chars].rstrip() + " […truncated]"
        lines.append(f"- commit {c.short_sha} ({date_short}): {c.subject}")
        if body:
            lines.append("  body:")
            for body_line in body.splitlines():
                lines.append(f"    {body_line.rstrip()}" if body_line.strip() else "")

    if history.reverts:
        revs = ", ".join(c.short_sha for c in history.reverts[:3])
        lines.append(f"- reverts touching this file: {revs}")

    lines.append("</history>")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Phase C — Commit-message decision trail mining
# ---------------------------------------------------------------------------
# These are purely mechanical: regex over Commit.body strings already loaded
# into SourceFile.history. No LLM, no I/O, no subprocess, no network.
# ---------------------------------------------------------------------------

# Caps on extraction output.
_MAX_COMMITS_TO_SCAN = 1000    # ceiling on distinct commits inspected (after SHA dedupe)
_COMMITS_TOP_N = 50            # output cap on the per-commit list
# _PATTERN_MIN_COUNT = 2: less aggressive than B/A1's 3, because commit decision
# signals are inherently a noisier sample than PR vocab — single-occurrence
# patterns are likely typos or anomalies, but 2+ recurrences are meaningful.
_PATTERN_MIN_COUNT = 2         # patterns with fewer hits are dropped
_BODY_EXCERPT_CHARS = 240      # chars of body to store in CommitDecision
_PATTERN_EXAMPLE_CHARS = 120   # chars per example in DecisionPattern

# Pattern set: (display_name, regex). Pre-compiled below with re.IGNORECASE.
# The negative lookahead in "tried" (`(?!\s+(?:hard|to\s+keep))`) excludes
# idiomatic phrases like "tried hard" or "tried to keep" that aren't decision
# signals — only narrow idioms are rejected; "tried to fix" still matches.
_DECISION_PATTERNS: tuple[tuple[str, str], ...] = (
    ("decided to",        r"\bdecided\s+to\b"),
    ("decided not to",    r"\bdecided\s+not\s+to\b"),
    ("instead of",        r"\binstead\s+of\b"),
    ("rather than",       r"\brather\s+than\b"),
    ("tried",             r"\btried\b(?!\s+(?:hard|to\s+keep))"),
    ("switched to",       r"\bswitched\s+to\b"),
    ("switched from",     r"\bswitched\s+from\b"),
    ("rejected",          r"\brejected\b"),
    ("considered",        r"\bconsidered\b"),
    ("reverted because",  r"\breverted?\b[^\n.]{0,40}?\bbecause\b"),
    ("abandoned",         r"\babandoned\b"),
    ("originally...now",  r"\boriginally\b[^\n.]{0,80}?\bnow\b"),
)

# Pre-compile at module import time for cheap test inspection and fast matching.
_COMPILED_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (name, re.compile(pattern, re.IGNORECASE))
    for name, pattern in _DECISION_PATTERNS
]

# Anonymization: strip @username mentions (same convention as pr_decisions.py).
_AT_MENTION_RE = re.compile(r"@[A-Za-z0-9_-]+")


# ---------------------------------------------------------------------------
# Sanitization helpers
# ---------------------------------------------------------------------------

def _sanitize_excerpt(text: str, max_chars: int) -> str:
    """Sanitize a body excerpt for use as a pattern example.

    Steps:
    1. Strip @username mentions → @<contributor>
    2. Collapse all whitespace runs (newlines, tabs, multi-spaces) → single space
    3. Truncate at word boundary using _truncate_at_word, falling back to hard-cut
    """
    # 1. Anonymize contributor mentions
    text = _AT_MENTION_RE.sub("@<contributor>", text)
    # 2. Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    # 3. Word-boundary truncation
    return _truncate_at_word(text, max_chars)


def _truncate_at_word(text: str, max_chars: int) -> str:
    """Truncate `text` to at most `max_chars` characters at a word boundary.

    If there is whitespace within the window, cuts at the last such boundary.
    Falls back to a hard cut when no whitespace appears in the window (e.g. a
    very long unbroken token like a URL).
    """
    if len(text) <= max_chars:
        return text
    window = text[:max_chars]
    # Find last whitespace in the window for a clean word boundary
    last_space = window.rfind(" ")
    if last_space > 0:
        return window[:last_space]
    # No whitespace found — hard cut
    return window


def _sanitize_body_excerpt(body: str) -> str:
    """Collapse whitespace in body and truncate to _BODY_EXCERPT_CHARS (hard cut).

    Used for CommitDecision.body_excerpt — not word-boundary truncated because
    we want to preserve as much of the decision context as possible.
    """
    cleaned = re.sub(r"\s+", " ", body).strip()
    return cleaned[:_BODY_EXCERPT_CHARS]


# ---------------------------------------------------------------------------
# Internal helper — commit with file paths accumulator
# ---------------------------------------------------------------------------

@dataclass
class _CommitWithFiles:
    """Internal: a deduped commit together with the file paths that surface it."""
    commit: Commit
    file_paths: set[str]  # mutable during accumulation


# ---------------------------------------------------------------------------
# Public dataclasses
# ---------------------------------------------------------------------------

@dataclass
class CommitDecision:
    """A single commit whose body contains one or more decision-trail signals."""

    sha: str             # short SHA (12 chars, matches Commit.sha[:12])
    subject: str
    date: str            # ISO from Commit.date
    body_excerpt: str    # first _BODY_EXCERPT_CHARS chars of body, sanitized whitespace
    matched_patterns: list[str]  # display names of all patterns hit; sorted asc
    file_paths: list[str]        # repo-relative paths whose history surfaced this commit; sorted

    def to_json(self) -> dict[str, Any]:
        return {
            "sha": self.sha,
            "subject": self.subject,
            "date": self.date,
            "body_excerpt": self.body_excerpt,
            "matched_patterns": self.matched_patterns,
            "file_paths": self.file_paths,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> CommitDecision:
        return cls(
            sha=data["sha"],
            subject=data["subject"],
            date=data["date"],
            body_excerpt=data.get("body_excerpt", ""),
            matched_patterns=data.get("matched_patterns", []),
            file_paths=data.get("file_paths", []),
        )


@dataclass
class DecisionPattern:
    """Aggregated stats for one decision-signal pattern across all matching commits."""

    pattern: str        # display name, e.g. "instead of"
    count: int          # number of distinct commits containing this pattern
    examples: list[str]  # up to 3 short body excerpts (anonymized, ≤_PATTERN_EXAMPLE_CHARS chars)

    def to_json(self) -> dict[str, Any]:
        return {
            "pattern": self.pattern,
            "count": self.count,
            "examples": self.examples,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> DecisionPattern:
        return cls(
            pattern=data["pattern"],
            count=data["count"],
            examples=data.get("examples", []),
        )


@dataclass
class CommitDecisions:
    """Aggregated decision-trail signals mined from commit message bodies."""

    # Tell pytest this is a data class, not a test class. Without this, pytest
    # tries to collect it (sees 'Commit' + no __init__ issue) and emits warnings.
    __test__ = False

    commits_scanned: int           # how many distinct (deduped) commits were inspected
    patterns: list[DecisionPattern]  # by count desc, then pattern asc
    commits: list[CommitDecision]    # by date desc, then sha asc; capped at _COMMITS_TOP_N

    def to_json(self) -> dict[str, Any]:
        return {
            "commits_scanned": self.commits_scanned,
            "patterns": [p.to_json() for p in self.patterns],
            "commits": [c.to_json() for c in self.commits],
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> CommitDecisions:
        return cls(
            commits_scanned=data.get("commits_scanned", 0),
            patterns=[DecisionPattern.from_json(p) for p in data.get("patterns", [])],
            commits=[CommitDecision.from_json(c) for c in data.get("commits", [])],
        )

    @property
    def has_signal(self) -> bool:
        return bool(self.patterns or self.commits)


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------

def extract_commit_decisions(files: list[Any]) -> CommitDecisions:
    """Mine decision-trail signals from commit message bodies already in SourceFile.history.

    Iterates files, then for each file iterates f.history.commits and
    f.history.reverts. Dedupes by full SHA across files (the same commit can
    touch multiple files). Matches each unique commit's body against
    _COMPILED_PATTERNS and builds aggregated output.

    No subprocess, no I/O, no network — operates purely on already-loaded
    Commit.body strings.
    """
    # SHA → _CommitWithFiles: dedupe across files, accumulate file paths.
    seen_shas: dict[str, _CommitWithFiles] = {}

    for sf in files:
        history = sf.history
        if history is None:
            continue
        if not history.commits and not history.reverts:
            continue

        # Repo-relative path for this file
        try:
            file_path = sf.path.as_posix()
        except AttributeError:
            file_path = str(sf.path)

        all_commits = list(history.commits) + list(history.reverts)
        for commit in all_commits:
            sha = commit.sha
            if sha in seen_shas:
                # Still update file paths for already-seen SHAs
                seen_shas[sha].file_paths.add(file_path)
            else:
                # Only add new SHAs up to the cap
                if len(seen_shas) >= _MAX_COMMITS_TO_SCAN:
                    continue
                seen_shas[sha] = _CommitWithFiles(
                    commit=commit,
                    file_paths={file_path},
                )

    # Per-pattern aggregation: count + up to 3 example excerpts
    # pattern_name → (count, list[example_str])
    pattern_agg: dict[str, tuple[int, list[str]]] = {}

    # Matching commits to build CommitDecision records
    matched_commit_records: list[CommitDecision] = []

    for sha, cwf in seen_shas.items():
        commit = cwf.commit
        body = commit.body or ""
        if not body.strip():
            continue

        # Find all matching patterns
        matched: list[str] = []
        for pattern_name, compiled_re in _COMPILED_PATTERNS:
            if compiled_re.search(body):
                matched.append(pattern_name)

        if not matched:
            continue

        # Build CommitDecision (short SHA = first 12 chars)
        matched.sort()
        matched_commit_records.append(CommitDecision(
            sha=sha[:12],
            subject=commit.subject,
            date=commit.date,
            body_excerpt=_sanitize_body_excerpt(body),
            matched_patterns=matched,
            file_paths=sorted(cwf.file_paths),
        ))

        # Accumulate per-pattern aggregation
        for pattern_name in matched:
            if pattern_name not in pattern_agg:
                pattern_agg[pattern_name] = (0, [])
            count, examples = pattern_agg[pattern_name]
            count += 1
            if len(examples) < 3:
                ex = _sanitize_excerpt(body, _PATTERN_EXAMPLE_CHARS)
                if ex:
                    examples.append(ex)
            pattern_agg[pattern_name] = (count, examples)

    # Build DecisionPattern list, drop patterns below _PATTERN_MIN_COUNT
    patterns: list[DecisionPattern] = []
    for pattern_name, (count, examples) in pattern_agg.items():
        if count < _PATTERN_MIN_COUNT:
            continue
        patterns.append(DecisionPattern(
            pattern=pattern_name,
            count=count,
            examples=examples,
        ))

    # Sort patterns: count desc, then name asc
    patterns.sort(key=lambda p: (-p.count, p.pattern))

    # Sort commits: date desc (lexicographic on ISO is fine), sha asc for tiebreak.
    # Use groupby after a descending-date sort to preserve sha-asc order within
    # same-date groups while keeping the overall list date-desc.
    from itertools import groupby
    matched_commit_records.sort(key=lambda c: c.date, reverse=True)
    sorted_commits: list[CommitDecision] = []
    for _date, group in groupby(matched_commit_records, key=lambda c: c.date):
        sorted_commits.extend(sorted(group, key=lambda c: c.sha))
    commits = sorted_commits[:_COMMITS_TOP_N]

    return CommitDecisions(
        commits_scanned=len(seen_shas),
        patterns=patterns,
        commits=commits,
    )


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

def render_commit_decisions_md(
    decisions: CommitDecisions, *, source_target: str
) -> str:
    """Render CommitDecisions as Markdown.

    Returns '' when has_signal is False — caller skips writing the file.

    Output sections:
    - Preamble blockquote with commits_scanned + source_target
    - Recurring decision patterns (by occurrence)
    - Notable decision commits (most recent)

    Sections are only rendered when their lists are non-empty — no "(none)"
    placeholders are emitted.
    """
    if not decisions.has_signal:
        return ""

    lines: list[str] = [
        "# Commit Decisions — what the senior team recorded as decisions",
        "",
        f"> Mined from {decisions.commits_scanned} commits of {source_target}: explicit",
        "> decision trails (tried X, switched to Y, rejected because Z) recorded",
        "> in commit message bodies. Captures the *narrative* of evolving choices",
        "> that PR descriptions and inline comments often miss.",
        "",
    ]

    # --- Section: recurring decision patterns ---
    if decisions.patterns:
        lines += ["## Recurring decision patterns (by occurrence)", ""]
        for i, dp in enumerate(decisions.patterns, start=1):
            lines.append(f"{i}. **{dp.pattern}** ({dp.count} commits)")
            for ex in dp.examples:
                lines.append(f'   - "{ex}"')
        lines.append("")

    # --- Section: notable decision commits ---
    if decisions.commits:
        lines += ["## Notable decision commits (most recent)", ""]
        for cd in decisions.commits:
            date_short = cd.date[:10] if cd.date else "?"
            # Paths: truncate to first 3 for readability
            paths_display = cd.file_paths[:3]
            paths_str = ", ".join(f"`{p}`" for p in paths_display)
            if len(cd.file_paths) > 3:
                paths_str += f", +{len(cd.file_paths) - 3} more"
            pattern_str = ", ".join(f"`{p}`" for p in cd.matched_patterns)
            lines.append(
                f"- `{cd.sha}` ({date_short})"
                f" **{cd.subject}**"
                f" — paths: {paths_str}"
            )
            lines.append(f"  matched: {pattern_str}")
            if cd.body_excerpt:
                lines.append(f"  > {cd.body_excerpt}")
        lines.append("")

    return "\n".join(lines)
