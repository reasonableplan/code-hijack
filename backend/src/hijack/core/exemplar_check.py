"""exemplar_check.py — W4a: verbatim-excerpt detection for AnalysisRule.good_example.

Few-shot performance depends on exemplar selection (arxiv 2412.02906) — a
`good_example` invented by the LLM rather than lifted from the senior repo is
a cargo-cult risk. This is a deterministic, observational measurement: it
does not gate or demote rules, only records whether good_example looks like a
verbatim excerpt of the fetched source.

Pure module: no LLM, no I/O — operates on already-fetched SourceFile content.
"""
from __future__ import annotations

_MIN_LINE_CHARS = 10
_VERBATIM_THRESHOLD = 0.5


def is_verbatim_excerpt(example: str, files: list) -> bool:
    """Return True if `example` looks like a verbatim excerpt of `files`.

    `files` is a list of fetcher.SourceFile (duck-typed: `.content`). Only
    lines stripped to >= _MIN_LINE_CHARS chars are eligible for matching —
    this excludes short noise lines (e.g. a lone ")"). A match is any
    eligible line found (after strip) in the union of all files' stripped
    lines — not required to come from a single file. True when the matched
    fraction of eligible lines is >= _VERBATIM_THRESHOLD (partial matches
    count, since an LLM may excerpt then lightly edit).
    """
    eligible = [
        stripped
        for line in example.splitlines()
        if len(stripped := line.strip()) >= _MIN_LINE_CHARS
    ]
    if not eligible:
        return False

    source_lines: set[str] = set()
    for f in files:
        content = getattr(f, "content", "") or ""
        source_lines.update(line.strip() for line in content.splitlines())

    matched = sum(1 for line in eligible if line in source_lines)
    return (matched / len(eligible)) >= _VERBATIM_THRESHOLD
