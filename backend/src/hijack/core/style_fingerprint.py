"""style_fingerprint — per-layer mechanical pattern extraction.

What this module captures that the rules and exemplars layers don't:

- **Negative space**: patterns the senior codebase NEVER emits. The rules
  layer encodes "don't do X" as advice, but A/B testing showed agents
  ignore textual anti-patterns. A *count* of zero across hundreds of
  files is a stronger signal than advice — the agent can't argue with data.
- **Symbol substitutions**: pairs (X, Y) where Y is the senior form and X
  is the legacy form. e.g. `Optional[T]` → `T | None`,
  `from typing import Sequence` → `from collections.abc import Sequence`.
  Agents ignore "use Y" rules when Y is unfamiliar, but ratios make the
  preference explicit and auditable.

Pure module: no LLM, no I/O, no network. Operates on the SourceFile
content already loaded by the fetcher.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from hijack.core.fetcher import SourceFile

# A layer needs at least this many .py files before "zero occurrences" is
# treated as a confident "never" — fewer files and the absence is just
# small-sample noise.
_MIN_FILES_FOR_NEGATIVE_CLAIM = 10

# Substitution confidence thresholds.
_HIGH_CONFIDENCE_RATIO = 0.95
_MEDIUM_CONFIDENCE_RATIO = 0.80


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _NegativeSpaceCheck:
    name: str
    pattern: re.Pattern[str]
    description: str


@dataclass(frozen=True)
class _SubstitutionCheck:
    name: str
    from_pattern: re.Pattern[str]
    to_pattern: re.Pattern[str]
    from_form: str
    to_form: str


# Python-focused checks. Frontend (TS/TSX) layers are skipped — different
# language, different idioms, different patterns to mine.
_NEGATIVE_SPACE: tuple[_NegativeSpaceCheck, ...] = (
    _NegativeSpaceCheck(
        name="legacy_typing_aliases",
        pattern=re.compile(
            r"^\s*from\s+typing\s+import\s.*\b"
            r"(?:List|Optional|Tuple|Dict|Set)\b",
            re.MULTILINE,
        ),
        description=(
            "never imports legacy generic aliases (List/Optional/Tuple/Dict/"
            "Set) from `typing` — uses built-in generics and `T | None` instead"
        ),
    ),
    _NegativeSpaceCheck(
        name="bare_type_ignore",
        pattern=re.compile(r"#\s*type:\s*ignore(?!\[)"),
        description=(
            "never uses bare `# type: ignore` — always pairs it with a rule "
            "code like `# type: ignore[misc]`"
        ),
    ),
    _NegativeSpaceCheck(
        name="bare_except",
        pattern=re.compile(r"^\s*except\s*:", re.MULTILINE),
        description="never catches all exceptions with a bare `except:` clause",
    ),
    _NegativeSpaceCheck(
        name="streaming_response_in_route_body",
        # `return StreamingResponse(...)` inside a route function — the
        # senior pattern uses `response_class=` instead.
        pattern=re.compile(
            r"^\s*return\s+StreamingResponse\s*\(",
            re.MULTILINE,
        ),
        description=(
            "never returns a manually-constructed `StreamingResponse` from "
            "inside a route body — uses `response_class=` on the decorator"
        ),
    ),
)

_SUBSTITUTIONS: tuple[_SubstitutionCheck, ...] = (
    _SubstitutionCheck(
        name="optional_to_union_none",
        from_pattern=re.compile(r"\bOptional\["),
        to_pattern=re.compile(r"\|\s*None\b"),
        from_form="Optional[T]",
        to_form="T | None",
    ),
    _SubstitutionCheck(
        name="typing_sequence_to_collections_abc",
        from_pattern=re.compile(
            r"^\s*from\s+typing\s+import\s.*\bSequence\b",
            re.MULTILINE,
        ),
        to_pattern=re.compile(
            r"^\s*from\s+collections\.abc\s+import\s.*\bSequence\b",
            re.MULTILINE,
        ),
        from_form="from typing import Sequence",
        to_form="from collections.abc import Sequence",
    ),
    _SubstitutionCheck(
        name="typing_mapping_to_collections_abc",
        from_pattern=re.compile(
            r"^\s*from\s+typing\s+import\s.*\bMapping\b",
            re.MULTILINE,
        ),
        to_pattern=re.compile(
            r"^\s*from\s+collections\.abc\s+import\s.*\bMapping\b",
            re.MULTILINE,
        ),
        from_form="from typing import Mapping",
        to_form="from collections.abc import Mapping",
    ),
    _SubstitutionCheck(
        name="typing_callable_to_collections_abc",
        from_pattern=re.compile(
            r"^\s*from\s+typing\s+import\s.*\bCallable\b",
            re.MULTILINE,
        ),
        to_pattern=re.compile(
            r"^\s*from\s+collections\.abc\s+import\s.*\bCallable\b",
            re.MULTILINE,
        ),
        from_form="from typing import Callable",
        to_form="from collections.abc import Callable",
    ),
)


# ---------------------------------------------------------------------------
# Findings (public dataclasses)
# ---------------------------------------------------------------------------

@dataclass
class NegativeSpaceFinding:
    """A pattern with zero observed occurrences across the layer."""

    name: str
    description: str
    occurrences: int  # always 0 when this finding is emitted
    file_count: int  # how many files we checked


@dataclass
class SubstitutionFinding:
    """A counted X-vs-Y pair for the layer."""

    name: str
    from_form: str
    to_form: str
    from_count: int
    to_count: int

    @property
    def total(self) -> int:
        return self.from_count + self.to_count

    @property
    def to_ratio(self) -> float:
        return self.to_count / self.total if self.total else 0.0

    @property
    def confidence(self) -> str:
        if self.total == 0:
            return "no-data"
        if self.to_ratio >= _HIGH_CONFIDENCE_RATIO:
            return "high"
        if self.to_ratio >= _MEDIUM_CONFIDENCE_RATIO:
            return "medium"
        return "weak"


@dataclass
class StyleFingerprint:
    """All mechanical findings for one layer."""

    layer: str
    file_count: int
    negative_space: list[NegativeSpaceFinding]
    substitutions: list[SubstitutionFinding]


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def extract_style(files: Iterable[SourceFile]) -> dict[str, StyleFingerprint]:
    """Compute per-layer style fingerprints.

    Returns a dict keyed by layer name. Only Python files contribute —
    frontend (TS/TSX) layers, if any, will appear as empty fingerprints
    or be omitted entirely.
    """
    by_layer: dict[str, list[SourceFile]] = {}
    for sf in files:
        if sf.path.suffix != ".py":
            continue
        if not sf.content or sf.content.startswith("# [TRUNCATED:"):
            # Truncated content has only signatures — not representative of
            # full statistical patterns, would skew counts.
            continue
        by_layer.setdefault(sf.layer, []).append(sf)

    return {
        layer: _fingerprint_layer(layer, layer_files)
        for layer, layer_files in by_layer.items()
    }


def _fingerprint_layer(layer: str, files: list[SourceFile]) -> StyleFingerprint:
    negs: list[NegativeSpaceFinding] = []
    for check in _NEGATIVE_SPACE:
        total = sum(len(check.pattern.findall(sf.content)) for sf in files)
        if total == 0 and len(files) >= _MIN_FILES_FOR_NEGATIVE_CLAIM:
            negs.append(
                NegativeSpaceFinding(
                    name=check.name,
                    description=check.description,
                    occurrences=0,
                    file_count=len(files),
                )
            )

    subs: list[SubstitutionFinding] = []
    for check in _SUBSTITUTIONS:
        from_count = sum(
            len(check.from_pattern.findall(sf.content)) for sf in files
        )
        to_count = sum(
            len(check.to_pattern.findall(sf.content)) for sf in files
        )
        if from_count + to_count > 0:
            subs.append(
                SubstitutionFinding(
                    name=check.name,
                    from_form=check.from_form,
                    to_form=check.to_form,
                    from_count=from_count,
                    to_count=to_count,
                )
            )

    return StyleFingerprint(
        layer=layer,
        file_count=len(files),
        negative_space=negs,
        substitutions=subs,
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render_layer_invariants_md(fp: StyleFingerprint) -> str:
    """Render a single layer's fingerprint as a Markdown section.

    Returns "" when the fingerprint has nothing to say — caller skips
    appending. The section is designed to drop into an existing layer.md
    (backend.md / frontend.md / shared.md / db.md) under a final "Codebase
    Invariants" heading.
    """
    high_conf_subs = [
        s for s in fp.substitutions if s.confidence in ("high", "medium")
    ]
    if not fp.negative_space and not high_conf_subs:
        return ""

    lines: list[str] = []
    lines.append("")
    lines.append("## Codebase Invariants")
    lines.append("")
    lines.append(
        f"> Statistical patterns observed across {fp.file_count} "
        f"`{fp.layer}` files. These are facts about how the senior codebase "
        f"actually behaves — follow them by default."
    )
    lines.append("")

    if fp.negative_space:
        lines.append("### Never (verified absent)")
        lines.append("")
        for ns in fp.negative_space:
            lines.append(
                f"- {ns.description} "
                f"_(0 occurrences in {ns.file_count} files)_"
            )
        lines.append("")

    if high_conf_subs:
        lines.append("### Use Y over X (observed preference)")
        lines.append("")
        for s in high_conf_subs:
            pct = round(s.to_ratio * 100)
            lines.append(
                f"- `{s.from_form}` → `{s.to_form}` "
                f"_({pct}% of {s.total} occurrences use `{s.to_form}`, "
                f"confidence: {s.confidence})_"
            )
        lines.append("")

    return "\n".join(lines)
