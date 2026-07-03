"""Tests for core/satd.py — SATD (self-admitted technical debt) mining (W2)."""
from __future__ import annotations

from pathlib import Path

from hijack.core.satd import _SATD_TOP_N, SatdItems, extract_satd


class _File:
    """Minimal SourceFile stand-in (satd only needs .path / .content)."""

    def __init__(self, path: str, content: str) -> None:
        self.path = Path(path)
        self.content = content


class TestExtractSatd:
    def test_python_todo(self) -> None:
        items = extract_satd([_File("src/foo.py", "x = 1\n# TODO: drop this shim\ny = 2\n")]).items
        assert len(items) == 1
        assert items[0].ref == "src/foo.py:2"
        assert items[0].tag == "TODO"
        assert items[0].text == "drop this shim"

    def test_c_family_and_block_markers(self) -> None:
        content = "// FIXME handle EOF\ncode;\n/* HACK: workaround */\n * XXX revisit\n"
        tags = [i.tag for i in extract_satd([_File("a.ts", content)]).items]
        assert tags == ["FIXME", "HACK", "XXX"]

    def test_tag_in_string_without_comment_marker_not_matched(self) -> None:
        # No comment marker before the tag → not SATD.
        items = extract_satd([_File("a.py", 'msg = "TODO later"\n')]).items
        assert items == []

    def test_tag_inside_identifier_not_matched(self) -> None:
        # \b guard: TODOLIST is not the TODO tag.
        items = extract_satd([_File("a.py", "# TODOLIST is a var\n")]).items
        assert items == []

    def test_ref_is_path_colon_line(self) -> None:
        content = "\n\n\n# HACK top of file offset\n"
        assert extract_satd([_File("pkg/mod.py", content)]).items[0].ref == "pkg/mod.py:4"

    def test_caps_at_top_n(self) -> None:
        content = "\n".join(f"# TODO item {i}" for i in range(_SATD_TOP_N + 10))
        assert len(extract_satd([_File("a.py", content)]).items) == _SATD_TOP_N

    def test_empty_files(self) -> None:
        result = extract_satd([_File("a.py", "x = 1\n")])
        assert result.items == []
        assert result.has_signal is False

    def test_roundtrip(self) -> None:
        original = extract_satd([_File("src/foo.py", "# FIXME: race condition here\n")])
        restored = SatdItems.from_json(original.to_json())
        assert restored.items[0].ref == "src/foo.py:1"
        assert restored.items[0].tag == "FIXME"
        assert restored.has_signal is True
