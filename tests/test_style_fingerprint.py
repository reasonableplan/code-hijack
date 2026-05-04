"""Tests for core/style_fingerprint.py — negative space, substitutions, render."""
from __future__ import annotations

from pathlib import Path

from hijack.core.fetcher import SourceFile
from hijack.core.style_fingerprint import (
    _MIN_FILES_FOR_NEGATIVE_CLAIM,
    NegativeSpaceFinding,
    StyleFingerprint,
    SubstitutionFinding,
    extract_style,
    render_layer_invariants_md,
)


def _sf(
    content: str,
    *,
    path: str = "backend/svc.py",
    layer: str = "backend",
    role: str = "service",
) -> SourceFile:
    return SourceFile(
        path=Path(path),
        content=content,
        layer=layer,
        role=role,
    )


# ---------------------------------------------------------------------------
# Helpers — generate "many files" with the same content shape
# ---------------------------------------------------------------------------

def _many(content: str, n: int, layer: str = "backend") -> list[SourceFile]:
    return [_sf(content, path=f"{layer}/f{i}.py", layer=layer) for i in range(n)]


# Snippets used in multiple tests
_USES_MODERN_TYPING = """\
from collections.abc import Mapping, Sequence
from typing import Annotated

def fetch(items: Sequence[int], headers: Mapping[str, str] | None = None) -> int | None:
    return items[0] if items else None
"""

_USES_LEGACY_TYPING = """\
from typing import List, Optional, Sequence

def fetch(items: Sequence[int], names: Optional[List[str]] = None) -> Optional[int]:
    return items[0] if items else None
"""

_USES_BARE_TYPE_IGNORE = """\
class Bad:  # type: ignore
    pass
"""

_USES_KEYED_TYPE_IGNORE = """\
class Good:  # type: ignore[misc]
    pass
"""

_USES_BARE_EXCEPT = """\
def caller():
    try:
        risky()
    except:
        pass
"""

_USES_KEYED_EXCEPT = """\
def caller():
    try:
        risky()
    except ValueError:
        pass
"""

_USES_STREAMING_RESPONSE_IN_BODY = """\
@router.get("/x")
async def x():
    return StreamingResponse(gen())
"""


# ---------------------------------------------------------------------------
# extract_style — layer split
# ---------------------------------------------------------------------------

class TestExtractStyleLayerSplit:
    def test_keys_by_layer(self) -> None:
        files = [
            _sf(_USES_MODERN_TYPING, layer="backend"),
            _sf(_USES_MODERN_TYPING, layer="db", path="db/x.py"),
        ]
        fps = extract_style(files)
        assert set(fps.keys()) == {"backend", "db"}

    def test_skips_non_python_files(self) -> None:
        ts_file = SourceFile(
            path=Path("frontend/App.tsx"),
            content="export const x = 1;",
            layer="frontend",
            role="entry_point",
        )
        fps = extract_style([ts_file])
        assert "frontend" not in fps  # TSX skipped → layer absent

    def test_skips_truncated_files(self) -> None:
        truncated = "# [TRUNCATED: 5000 lines → key signatures only]\ndef foo(): ..."
        files = [_sf(truncated)] * 20
        fps = extract_style(files)
        # All 20 files filtered → empty result, not a fingerprint with 20 files
        assert fps == {}


# ---------------------------------------------------------------------------
# Negative space
# ---------------------------------------------------------------------------

class TestNegativeSpace:
    def test_zero_legacy_typing_imports_emits_finding(self) -> None:
        files = _many(_USES_MODERN_TYPING, n=_MIN_FILES_FOR_NEGATIVE_CLAIM)
        fps = extract_style(files)
        names = {ns.name for ns in fps["backend"].negative_space}
        assert "legacy_typing_aliases" in names

    def test_one_legacy_import_blocks_finding(self) -> None:
        # Even a single legacy `from typing import List` voids the negative
        # space claim — "never" must mean *never*.
        files = (
            _many(_USES_MODERN_TYPING, n=_MIN_FILES_FOR_NEGATIVE_CLAIM - 1)
            + [_sf(_USES_LEGACY_TYPING)]
        )
        fps = extract_style(files)
        names = {ns.name for ns in fps["backend"].negative_space}
        assert "legacy_typing_aliases" not in names

    def test_below_threshold_no_negative_finding(self) -> None:
        # With fewer than _MIN_FILES_FOR_NEGATIVE_CLAIM files, "zero
        # occurrences" might just be small-sample noise — no claim emitted.
        files = _many(_USES_MODERN_TYPING, n=_MIN_FILES_FOR_NEGATIVE_CLAIM - 1)
        fps = extract_style(files)
        assert fps["backend"].negative_space == []

    def test_bare_type_ignore_caught(self) -> None:
        files = _many(_USES_KEYED_TYPE_IGNORE, n=_MIN_FILES_FOR_NEGATIVE_CLAIM)
        fps = extract_style(files)
        names = {ns.name for ns in fps["backend"].negative_space}
        assert "bare_type_ignore" in names

    def test_keyed_type_ignore_does_not_match_bare_pattern(self) -> None:
        # The bare-type-ignore regex must NOT match `# type: ignore[code]`.
        # Mix of keyed-only + extra files past threshold:
        files = _many(_USES_KEYED_TYPE_IGNORE, n=_MIN_FILES_FOR_NEGATIVE_CLAIM)
        fps = extract_style(files)
        names = {ns.name for ns in fps["backend"].negative_space}
        # The keyed form is fine — bare_type_ignore should still trigger
        # (no bare ones present).
        assert "bare_type_ignore" in names

    def test_bare_except_caught(self) -> None:
        files = _many(_USES_KEYED_EXCEPT, n=_MIN_FILES_FOR_NEGATIVE_CLAIM)
        fps = extract_style(files)
        names = {ns.name for ns in fps["backend"].negative_space}
        assert "bare_except" in names

    def test_streaming_response_in_route_body_caught(self) -> None:
        # Codebase that doesn't return raw StreamingResponse from routes
        # should emit the streaming_response_in_route_body finding.
        files = _many(_USES_MODERN_TYPING, n=_MIN_FILES_FOR_NEGATIVE_CLAIM)
        fps = extract_style(files)
        names = {ns.name for ns in fps["backend"].negative_space}
        assert "streaming_response_in_route_body" in names

    def test_streaming_response_finding_blocked_by_one_violation(self) -> None:
        # A single occurrence of `return StreamingResponse(...)` voids the
        # claim.
        files = (
            _many(_USES_MODERN_TYPING, n=_MIN_FILES_FOR_NEGATIVE_CLAIM - 1)
            + [_sf(_USES_STREAMING_RESPONSE_IN_BODY)]
        )
        fps = extract_style(files)
        names = {ns.name for ns in fps["backend"].negative_space}
        assert "streaming_response_in_route_body" not in names


# ---------------------------------------------------------------------------
# Substitutions
# ---------------------------------------------------------------------------

class TestSubstitutions:
    def test_optional_to_union_none_high_confidence(self) -> None:
        # Codebase exclusively uses `T | None` — Optional[...] count is 0.
        files = _many(_USES_MODERN_TYPING, n=20)
        fps = extract_style(files)
        subs = {s.name: s for s in fps["backend"].substitutions}
        assert "optional_to_union_none" in subs
        assert subs["optional_to_union_none"].confidence == "high"

    def test_optional_to_union_none_weak_when_mixed(self) -> None:
        files = (
            _many(_USES_MODERN_TYPING, n=5)
            + _many(_USES_LEGACY_TYPING, n=5)
        )
        fps = extract_style(files)
        subs = {s.name: s for s in fps["backend"].substitutions}
        # With roughly half-and-half, confidence is weak.
        assert subs["optional_to_union_none"].confidence == "weak"

    def test_no_data_when_neither_form_appears(self) -> None:
        # No Optional, no `| None` either — substitution emits no_data and
        # is filtered out at extraction time.
        empty_module = "x = 1\n"
        files = _many(empty_module, n=20)
        fps = extract_style(files)
        subs = {s.name for s in fps["backend"].substitutions}
        assert "optional_to_union_none" not in subs

    def test_typing_sequence_to_collections_abc(self) -> None:
        files = _many(_USES_MODERN_TYPING, n=20)
        fps = extract_style(files)
        subs = {s.name: s for s in fps["backend"].substitutions}
        assert "typing_sequence_to_collections_abc" in subs
        assert subs["typing_sequence_to_collections_abc"].confidence == "high"


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

class TestRenderLayerInvariantsMd:
    def test_empty_fingerprint_returns_empty(self) -> None:
        fp = StyleFingerprint(
            layer="backend", file_count=0, negative_space=[], substitutions=[]
        )
        assert render_layer_invariants_md(fp) == ""

    def test_renders_negative_space_section(self) -> None:
        fp = StyleFingerprint(
            layer="backend",
            file_count=42,
            negative_space=[
                NegativeSpaceFinding(
                    name="bare_except",
                    description="never uses bare `except:`",
                    occurrences=0,
                    file_count=42,
                )
            ],
            substitutions=[],
        )
        md = render_layer_invariants_md(fp)
        assert "## Codebase Invariants" in md
        assert "Never (verified absent)" in md
        assert "bare `except:`" in md
        assert "0 occurrences in 42 files" in md

    def test_renders_substitution_section_only_high_or_medium(self) -> None:
        fp = StyleFingerprint(
            layer="backend",
            file_count=20,
            negative_space=[],
            substitutions=[
                SubstitutionFinding(
                    name="x",
                    from_form="Optional[T]",
                    to_form="T | None",
                    from_count=0,
                    to_count=10,
                ),  # high
                SubstitutionFinding(
                    name="weak",
                    from_form="A",
                    to_form="B",
                    from_count=5,
                    to_count=5,
                ),  # weak — must be excluded
            ],
        )
        md = render_layer_invariants_md(fp)
        assert "Use Y over X" in md
        assert "Optional[T]" in md
        assert "T | None" in md
        # Weak substitution is excluded
        assert "`A` → `B`" not in md

    def test_layer_name_appears_in_header(self) -> None:
        fp = StyleFingerprint(
            layer="db",
            file_count=15,
            negative_space=[
                NegativeSpaceFinding(
                    name="x", description="never does X", occurrences=0,
                    file_count=15,
                )
            ],
            substitutions=[],
        )
        md = render_layer_invariants_md(fp)
        assert "`db` files" in md
