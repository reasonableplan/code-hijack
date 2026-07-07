"""Tests for core/satd.py — SATD (self-admitted technical debt) mining (W2)."""
from __future__ import annotations

from pathlib import Path

from hijack.core.satd import (
    _CONTEXT_CHAR_CAP,
    _CONTEXT_CODE_LINES,
    _CONTEXT_COMMENT_LINES,
    _PROMPT_CONTEXT_CHARS,
    _SATD_TOP_N,
    SatdItem,
    SatdItems,
    extract_satd,
    render_satd_for_prompt,
)


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


class TestSatdContext:
    def test_includes_tag_line(self) -> None:
        items = extract_satd([_File("a.py", "# TODO: fix this\n")]).items
        assert items[0].context.startswith("# TODO: fix this")

    def test_collects_continuation_comments(self) -> None:
        content = (
            "# TODO: fix this\n"
            "# it breaks under load\n"
            "# see issue #42\n"
            "x = 1\n"
        )
        items = extract_satd([_File("a.py", content)]).items
        assert "# it breaks under load" in items[0].context
        assert "# see issue #42" in items[0].context
        assert "x = 1" in items[0].context

    def test_continuation_capped_at_four_lines(self) -> None:
        # 10 candidate comment-continuation lines available; continuation caps
        # at 4, then the code-lines slot (cap 5) picks up the next 5 — so the
        # 10th ("comment 9") falls outside both caps and is excluded entirely.
        content = "# TODO: start\n" + "".join(f"# comment {i}\n" for i in range(10))
        items = extract_satd([_File("a.py", content)]).items
        context_lines = items[0].context.splitlines()
        assert len(context_lines) == 1 + _CONTEXT_COMMENT_LINES + _CONTEXT_CODE_LINES
        assert "# comment 9" not in items[0].context

    def test_new_satd_tag_stops_continuation_and_becomes_own_item(self) -> None:
        content = (
            "# TODO: first\n"
            "# still about first\n"
            "# FIXME: second\n"
            "code_after_second()\n"
        )
        items = extract_satd([_File("a.py", content)]).items
        assert len(items) == 2
        assert items[0].tag == "TODO"
        assert "still about first" in items[0].context
        assert "FIXME" not in items[0].context
        assert items[1].tag == "FIXME"
        assert items[1].ref == "a.py:3"
        assert "code_after_second()" in items[1].context

    def test_code_lines_capped_at_five(self) -> None:
        content = "# TODO: x\n" + "".join(f"line{i} = {i}\n" for i in range(10))
        items = extract_satd([_File("a.py", content)]).items
        code_lines = [
            line for line in items[0].context.splitlines() if line.startswith("line")
        ]
        assert len(code_lines) == _CONTEXT_CODE_LINES

    def test_trailing_blank_code_lines_removed(self) -> None:
        content = "# TODO: x\ncode_line = 1\n\n\n"
        items = extract_satd([_File("a.py", content)]).items
        assert items[0].context.splitlines()[-1] == "code_line = 1"

    def test_end_of_file_boundary(self) -> None:
        # Tag on the last line — no continuation comments, no code lines available.
        items = extract_satd([_File("a.py", "x = 1\n# TODO: last line\n")]).items
        assert items[0].context == "# TODO: last line"

    def test_char_cap(self) -> None:
        long_comment = "# " + ("word " * 300)
        content = "# TODO: start\n" + long_comment + "\ncode()\n"
        items = extract_satd([_File("a.py", content)]).items
        assert len(items[0].context) <= _CONTEXT_CHAR_CAP

    def test_from_json_backward_compat_missing_context(self) -> None:
        data = {"items": [{"ref": "a.py:1", "tag": "TODO", "text": "old session"}]}
        restored = SatdItems.from_json(data)
        assert restored.items[0].context == ""


class TestRenderSatdForPrompt:
    """CLI-mode evidence parity: compact <satd> block for prompt injection."""

    def test_none_returns_empty_string(self) -> None:
        assert render_satd_for_prompt(None) == ""

    def test_no_signal_returns_empty_string(self) -> None:
        assert render_satd_for_prompt(SatdItems(items=[])) == ""

    def test_block_tags_and_entry_fields(self) -> None:
        items = SatdItems(items=[SatdItem(
            ref="src/foo.py:42",
            tag="FIXME",
            text="race condition here",
            context="# FIXME: race condition here\nlock.acquire()",
        )])
        out = render_satd_for_prompt(items)
        assert out.startswith("<satd>")
        assert out.endswith("</satd>")
        assert "src/foo.py:42" in out
        assert "[FIXME]" in out
        assert "race condition here" in out
        assert "lock.acquire()" in out
        # Header comment instructs exact path:line refs for kind="comment".
        assert 'kind="comment"' in out
        assert "path:line" in out

    def test_context_omitted_when_empty(self) -> None:
        items = SatdItems(items=[SatdItem(ref="a.py:1", tag="TODO", text="x")])
        out = render_satd_for_prompt(items)
        assert "context:" not in out

    def test_context_trimmed_for_prompt(self) -> None:
        items = SatdItems(items=[SatdItem(
            ref="a.py:1", tag="TODO", text="x",
            context="# TODO: x\n" + "word " * 200,
        )])
        out = render_satd_for_prompt(items)
        # Stored context can run to _CONTEXT_CHAR_CAP; the prompt block trims
        # to the tighter _PROMPT_CONTEXT_CHARS.
        context_part = out[out.index("context:"):]
        assert len(context_part) < _PROMPT_CONTEXT_CHARS + 100

    def test_caps_at_max_items(self) -> None:
        items = SatdItems(items=[
            SatdItem(ref=f"a.py:{i}", tag="TODO", text=f"item {i}") for i in range(30)
        ])
        out = render_satd_for_prompt(items, max_items=20)
        assert "a.py:19" in out
        assert "a.py:20" not in out
