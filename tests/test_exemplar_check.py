"""Tests for core/exemplar_check.py — W4a exemplar verbatim-ratio detection."""
from __future__ import annotations

from pathlib import Path

from hijack.core.exemplar_check import (
    _MIN_LINE_CHARS,
    _VERBATIM_THRESHOLD,
    is_verbatim_excerpt,
)


class _File:
    """Minimal SourceFile stand-in (exemplar_check only needs .content)."""

    def __init__(self, content: str) -> None:
        self.path = Path("a.py")
        self.content = content


class TestIsVerbatimExcerpt:
    def test_fully_matching_example_is_verbatim(self) -> None:
        source = "def create(db: Session = Depends(get_db)):\n    return db.query(User).all()\n"
        example = "def create(db: Session = Depends(get_db)):\n    return db.query(User).all()"
        assert is_verbatim_excerpt(example, [_File(source)]) is True

    def test_partial_match_at_or_above_threshold_is_verbatim(self) -> None:
        # 2 of 3 eligible lines match == 2/3 >= 0.5 threshold.
        source = (
            "def create(db: Session = Depends(get_db)):\n"
            "    return db.query(User).all()\n"
        )
        example = (
            "def create(db: Session = Depends(get_db)):\n"
            "    return db.query(User).all()\n"
            "    # a line invented by the LLM that is not in source\n"
        )
        assert is_verbatim_excerpt(example, [_File(source)]) is True

    def test_below_threshold_is_not_verbatim(self) -> None:
        # Only 1 of 3 eligible lines match == 1/3 < 0.5 threshold.
        source = "def create(db: Session = Depends(get_db)):\n"
        example = (
            "def create(db: Session = Depends(get_db)):\n"
            "    # entirely invented continuation line one\n"
            "    # entirely invented continuation line two\n"
        )
        assert is_verbatim_excerpt(example, [_File(source)]) is False

    def test_boundary_exactly_half_is_verbatim(self) -> None:
        # 1 of 2 eligible lines match == exactly 0.5 == threshold, inclusive.
        source = "def create(db: Session = Depends(get_db)):\n"
        example = (
            "def create(db: Session = Depends(get_db)):\n"
            "    invented_line_not_in_source_at_all()\n"
        )
        assert is_verbatim_excerpt(example, [_File(source)]) is True

    def test_fully_invented_example_is_false(self) -> None:
        source = "class Foo:\n    def bar(self):\n        pass\n"
        example = "def totally_made_up_function(argument_one, argument_two):\n    return None\n"
        assert is_verbatim_excerpt(example, [_File(source)]) is False

    def test_short_lines_filtered_as_noise(self) -> None:
        # Only short (< _MIN_LINE_CHARS) lines — none eligible, so False even
        # though they'd trivially "match" a source containing just ")".
        example = ")\n}\n)\n"
        source = ")\n}\n)\n"
        assert is_verbatim_excerpt(example, [_File(source)]) is False

    def test_empty_example_is_false(self) -> None:
        assert is_verbatim_excerpt("", [_File("def create(): pass\n")]) is False

    def test_whitespace_only_example_is_false(self) -> None:
        assert is_verbatim_excerpt("   \n  \n", [_File("def create(): pass\n")]) is False

    def test_no_files_is_false(self) -> None:
        assert is_verbatim_excerpt("def create(db: Session = Depends(get_db)):", []) is False

    def test_match_across_union_of_multiple_files(self) -> None:
        # The matching line lives in the second file, not the first — union
        # matching (not single-file matching) should still find it.
        f1 = _File("class Unrelated:\n    pass\n")
        f2 = _File("def create(db: Session = Depends(get_db)):\n    return None\n")
        example = "def create(db: Session = Depends(get_db)):\n    return None"
        assert is_verbatim_excerpt(example, [f1, f2]) is True

    def test_matching_ignores_leading_trailing_whitespace(self) -> None:
        source = "    def create(db: Session = Depends(get_db)):\n"
        example = "def create(db: Session = Depends(get_db)):\n"
        assert is_verbatim_excerpt(example, [_File(source)]) is True

    def test_constants_are_expected_values(self) -> None:
        assert _MIN_LINE_CHARS == 10
        assert _VERBATIM_THRESHOLD == 0.5
