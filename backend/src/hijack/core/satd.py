"""SATD (self-admitted technical debt) comment mining — W2.

MAT baseline (arxiv 1910.13238): matching the task tags TODO/FIXME/XXX/HACK in
comments identifies SATD about as well as trained ML models, with no training
data. These tags are the senior's own recorded intent/limitation — an inline
WHY source that survives even when there is no commit/PR trail.

Pure module: regex over already-fetched SourceFile.content — no I/O. Each item's
`ref` is a "path:line" anchor that becomes the truth pool for evidence
`kind="comment"` (see evidence.classify_rule).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# A SATD task tag that follows a comment marker on a line. Markers: # (py/sh),
# // (c-family), /* or leading * (block comments). The \b guards keep the tag
# from matching inside longer identifiers.
_SATD_RE = re.compile(r"(?://|#|/\*|\*)\s*(TODO|FIXME|XXX|HACK)\b[:\s-]*(.*)")

# Trailing comment text kept per item.
_TEXT_CAP = 200

# Cap on items surfaced to the LLM / persisted (bounds prompt size).
_SATD_TOP_N = 50


@dataclass
class SatdItem:
    """One self-admitted technical-debt comment. `ref` is a "path:line" anchor."""

    ref: str          # e.g. "src/foo.py:42" — the evidence truth-pool anchor
    tag: str          # TODO | FIXME | XXX | HACK
    text: str         # trailing comment text (≤_TEXT_CAP chars)

    def to_json(self) -> dict[str, Any]:
        return {"ref": self.ref, "tag": self.tag, "text": self.text}

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> SatdItem:
        return cls(ref=data["ref"], tag=data["tag"], text=data.get("text", ""))


@dataclass
class SatdItems:
    """Aggregated SATD mining results — attached to SessionResult as a truth source."""

    items: list[SatdItem]

    def to_json(self) -> dict[str, Any]:
        return {"items": [i.to_json() for i in self.items]}

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> SatdItems:
        return cls(items=[SatdItem.from_json(d) for d in data.get("items", [])])

    @property
    def has_signal(self) -> bool:
        return bool(self.items)


def extract_satd(files: list) -> SatdItems:
    """Scan each SourceFile.content for SATD task tags; return up to _SATD_TOP_N.

    `files` is a list of fetcher.SourceFile (duck-typed: `.path`, `.content`).
    """
    items: list[SatdItem] = []
    for f in files:
        content = getattr(f, "content", "") or ""
        path = f.path.as_posix() if hasattr(f.path, "as_posix") else str(f.path)
        for lineno, line in enumerate(content.splitlines(), start=1):
            m = _SATD_RE.search(line)
            if m is None:
                continue
            items.append(
                SatdItem(
                    ref=f"{path}:{lineno}",
                    tag=m.group(1),
                    text=m.group(2).strip()[:_TEXT_CAP],
                )
            )
            if len(items) >= _SATD_TOP_N:
                return SatdItems(items=items)
    return SatdItems(items=items)
