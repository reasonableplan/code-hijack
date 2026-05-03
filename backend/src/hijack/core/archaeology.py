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
