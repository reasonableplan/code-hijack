"""Repo-level document collection — README, ARCHITECTURE, ADRs, etc.

Why a separate module from `fetcher`?
- The source-file fetcher is `.py/.ts/.tsx`-only by design. README and ADR
  files travel a different path: collected once per session, prepended to every
  category prompt as <repo_context>, never tagged with role/layer.
- Keeping doc collection out of the source pipeline avoids polluting layer
  detection (ARCHITECTURE.md is not "frontend") or role classification.

The "why" of senior decisions lives in these documents far more often than in
code comments. Surfacing them to the LLM is the cheapest grounding lever
available — pure file I/O, no subprocess, no API.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Top-level filename stems that almost certainly contain rationale.
# We match case-insensitively. The trailing wildcard is implicit — README.md,
# README.rst, README, README.ko.md all qualify.
_FILENAME_ALLOWLIST = (
    "readme",
    "architecture",
    "contributing",
    "design",
    "rationale",
    "decisions",
)

# Directory globs that typically house decision records and design notes.
# Both the dir name and any .md/.markdown/.rst file inside it count.
_DOC_DIRS = (
    "docs/adr",
    "docs/architecture",
    "docs/decisions",
    "docs/design",
    "adr",  # some repos keep ADRs at root
)

# Per-doc and total budget caps. Doc context is global (one block prepended to
# every category prompt), so total cost = total_cap × num_categories. Keep the
# total tight; individual long ADRs will be truncated.
_PER_DOC_CHAR_CAP = 2000
_TOTAL_CHAR_CAP = 5000

_SUPPORTED_DOC_SUFFIXES = frozenset({".md", ".markdown", ".mdx", ".rst", ".txt"})

# Directories we never recurse into — same skip set as the source fetcher,
# duplicated locally so this module doesn't depend on fetcher internals.
_SKIP_DIRS = frozenset(
    {
        ".git",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        "dist",
        "build",
        "target",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
    }
)


@dataclass
class RepoDoc:
    """A single collected document. `path` is repo-root-relative."""

    path: str
    content: str


def collect_repo_docs(repo_root: Path) -> list[RepoDoc]:
    """Return rationale-bearing docs from `repo_root`, capped to TOTAL_CHAR_CAP.

    Order of inclusion (each preserved up to the running budget):
      1. Top-level allowlisted files (README, ARCHITECTURE, CONTRIBUTING, ...)
      2. Files inside _DOC_DIRS (ADRs, design notes)

    A truncated doc has "[...truncated]" appended so the LLM is aware the
    section is incomplete.
    """
    results: list[RepoDoc] = []
    seen: set[str] = set()
    used_chars = 0

    def _try_add(abs_path: Path) -> bool:
        """Append `abs_path` if it fits in the remaining budget. Returns False
        when the total cap is hit and no more docs should be added."""
        nonlocal used_chars
        rel = abs_path.relative_to(repo_root).as_posix()
        if rel in seen:
            return True
        seen.add(rel)

        try:
            content = abs_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return True  # unreadable; skip but keep going

        if not content.strip():
            return True

        truncated = content[:_PER_DOC_CHAR_CAP]
        if len(content) > _PER_DOC_CHAR_CAP:
            truncated = truncated.rstrip() + "\n[...truncated]"

        remaining = _TOTAL_CHAR_CAP - used_chars
        if remaining <= 0:
            return False
        if len(truncated) > remaining:
            truncated = truncated[:remaining].rstrip() + "\n[...truncated]"

        results.append(RepoDoc(path=rel, content=truncated))
        used_chars += len(truncated)
        return used_chars < _TOTAL_CHAR_CAP

    # 1. Top-level allowlist.
    for entry in sorted(repo_root.iterdir() if repo_root.exists() else []):
        if not entry.is_file():
            continue
        if entry.suffix.lower() not in _SUPPORTED_DOC_SUFFIXES:
            continue
        if not _matches_filename(entry.stem):
            continue
        if not _try_add(entry):
            return results

    # 2. ADR / design-note directories.
    for dir_rel in _DOC_DIRS:
        dir_path = repo_root / dir_rel
        if not dir_path.is_dir():
            continue
        for p in sorted(dir_path.rglob("*")):
            if not p.is_file():
                continue
            if any(part in _SKIP_DIRS for part in p.parts):
                continue
            if p.suffix.lower() not in _SUPPORTED_DOC_SUFFIXES:
                continue
            if not _try_add(p):
                return results

    return results


def render_repo_context(docs: list[RepoDoc]) -> str:
    """Format collected docs as a <repo_context> prompt block.

    Returns "" when there are no docs — caller should drop the block entirely
    rather than emit an empty placeholder.
    """
    if not docs:
        return ""

    parts = ["<repo_context>"]
    for d in docs:
        parts.append(f"### {d.path}")
        parts.append(d.content.strip())
        parts.append("")  # blank separator
    parts.append("</repo_context>")
    return "\n".join(parts)


def _matches_filename(stem: str) -> bool:
    """Whether `stem` (filename without extension) starts with any allowlisted name.

    Case-insensitive. Allows README.ko, README.en, ARCHITECTURE-v2 etc.
    """
    lowered = stem.lower()
    return any(lowered.startswith(name) for name in _FILENAME_ALLOWLIST)
