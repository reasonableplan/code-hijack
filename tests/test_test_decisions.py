"""Tests for core/test_decisions.py — path detection, signal extraction, render.

Mirrored after test_exemplars.py: class-based grouping with comments explaining
the *why* of each group (what invariant is being protected).
"""
from __future__ import annotations

import ast
from pathlib import Path

from hijack.core.fetcher import SourceFile
from hijack.core.test_decisions import (
    EdgeCase,
    NameTheme,
    RaisesGroup,
    TestDecisions,
    _edge_case_why,
    _extract_name_themes,
    _extract_raises_blocks,
    _is_test_path,
    extract_test_decisions,
    render_tests_distilled_md,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sf(
    content: str,
    path: str = "tests/test_foo.py",
    layer: str = "shared",
    role: str = "test",
) -> SourceFile:
    return SourceFile(
        path=Path(path),
        content=content,
        layer=layer,
        role=role,
    )


def _parse(src: str) -> ast.Module:
    return ast.parse(src)


def _empty_decisions() -> TestDecisions:
    return TestDecisions(
        edge_cases=[],
        name_themes=[],
        raises_groups=[],
        test_file_count=0,
    )


# ---------------------------------------------------------------------------
# TestIsTestPath — path detection
# ---------------------------------------------------------------------------

class TestIsTestPath:
    # The detector should accept both top-level and nested test directories.
    # Rejecting "tests.py" (a file, not a directory) is a subtle but important
    # distinction: some libraries ship a top-level tests.py that is production
    # code (e.g. a test-utilities module), not a test suite.

    def test_top_level_tests_dir_matches(self) -> None:
        assert _is_test_path(Path("tests/foo.py")) is True

    def test_top_level_test_dir_matches(self) -> None:
        assert _is_test_path(Path("test/foo.py")) is True

    def test_nested_tests_dir_matches(self) -> None:
        # src/pkg/tests/helpers.py — common in large repos that embed
        # test helpers alongside the code they test.
        assert _is_test_path(Path("src/pkg/tests/helpers.py")) is True

    def test_non_test_path_does_not_match(self) -> None:
        assert _is_test_path(Path("lib/foo.py")) is False

    def test_top_level_tests_py_file_does_not_match(self) -> None:
        # "tests.py" is a file, not a directory — the prefix check requires
        # a trailing slash so "tests.py" never matches "tests/".
        assert _is_test_path(Path("tests.py")) is False

    def test_source_file_with_test_in_name_but_wrong_dir_does_not_match(self) -> None:
        # A file named test_utils.py under src/ is production code, not a test file.
        assert _is_test_path(Path("src/test_utils.py")) is False

    def test_deeply_nested_test_dir_matches(self) -> None:
        assert _is_test_path(Path("packages/core/tests/unit/test_model.py")) is True


# ---------------------------------------------------------------------------
# TestEdgeCaseDetector — signal 1 heuristics
# ---------------------------------------------------------------------------

class TestEdgeCaseDetector:
    # Each individual heuristic is tested in isolation so regressions can be
    # pinpointed quickly. The heuristics are intentionally conservative —
    # false positives (surfacing a non-edge case) are worse than false negatives
    # (missing one), because the output trains AI agents.

    def _node(self, src: str) -> ast.expr:
        """Parse a single-expression Python snippet into an AST node."""
        return ast.parse(src, mode="eval").body  # type: ignore[return-value]

    def test_none_triggers(self) -> None:
        assert _edge_case_why(self._node("None")) == "contains None"

    def test_empty_string_triggers(self) -> None:
        assert _edge_case_why(self._node('""')) == "empty string"

    def test_single_space_triggers(self) -> None:
        # A single space is whitespace — editors normalise it away, making
        # tests that depend on it fragile and worth calling out explicitly.
        why = _edge_case_why(self._node('" "'))
        assert why is not None and "whitespace" in why

    def test_newline_triggers(self) -> None:
        why = _edge_case_why(self._node(r'"\n"'))
        assert why is not None and "whitespace" in why

    def test_zero_triggers(self) -> None:
        assert _edge_case_why(self._node("0")) == "numeric 0"

    def test_negative_one_triggers(self) -> None:
        # -1 is written as a UnaryOp(USub, Constant(1)) in the AST.
        assert _edge_case_why(self._node("-1")) == "numeric -1"

    def test_empty_list_triggers(self) -> None:
        assert _edge_case_why(self._node("[]")) == "empty list"

    def test_empty_dict_triggers(self) -> None:
        assert _edge_case_why(self._node("{}")) == "empty dict"

    def test_empty_tuple_triggers(self) -> None:
        assert _edge_case_why(self._node("()")) == "empty tuple"

    def test_oversize_string_triggers(self) -> None:
        big = '"' + "x" * 1001 + '"'
        assert _edge_case_why(self._node(big)) == "oversize string"

    def test_pytest_param_with_invalid_id_triggers(self) -> None:
        # pytest.param(..., id="invalid_input") — the id string contains
        # "invalid", which is an explicit edge-case label.
        src = 'pytest.param("value", id="invalid_input")'
        why = _edge_case_why(self._node(src))
        assert why is not None and "invalid" in why

    def test_pytest_param_with_empty_id_triggers(self) -> None:
        src = 'pytest.param(42, id="empty_case")'
        why = _edge_case_why(self._node(src))
        assert why is not None and "empty" in why

    def test_pytest_param_with_edge_id_triggers(self) -> None:
        src = 'pytest.param("x", id="edge_case")'
        why = _edge_case_why(self._node(src))
        assert why is not None and "edge" in why

    def test_normal_integer_does_not_trigger(self) -> None:
        assert _edge_case_why(self._node("42")) is None

    def test_normal_string_does_not_trigger(self) -> None:
        assert _edge_case_why(self._node('"hello"')) is None

    def test_normal_list_does_not_trigger(self) -> None:
        assert _edge_case_why(self._node("[1, 2, 3]")) is None

    def test_oversize_numeric_triggers(self) -> None:
        # Values >= 1_000_000 in parametrize are typically stress/capacity tests.
        assert _edge_case_why(self._node("1_000_000")) == "oversize numeric"

    def test_negative_oversize_numeric_triggers(self) -> None:
        why = _edge_case_why(self._node("-1_000_001"))
        assert why is not None and "oversize" in why


# ---------------------------------------------------------------------------
# TestNamePatternMatcher — signal 2
# ---------------------------------------------------------------------------

class TestNamePatternMatcher:
    # The pattern is restrictive by design: only tests whose names start with
    # a *semantic verb* are surfaced. Random `test_foo_bar` names carry no
    # intent signal and are intentionally excluded — the output would be noise.

    def _themes(self, src: str) -> list[tuple[str, str, str]]:
        return _extract_name_themes(_parse(src))

    def test_handles_verb_matches(self) -> None:
        src = "def test_handles_empty_dict(): pass"
        themes = self._themes(src)
        assert any(t[0] == "handles" and "empty" in t[1] for t in themes)

    def test_raises_verb_matches(self) -> None:
        src = "def test_raises_on_circular_input(): pass"
        themes = self._themes(src)
        assert any(t[0] == "raises" for t in themes)

    def test_with_verb_matches(self) -> None:
        src = "def test_with_none_value(): pass"
        themes = self._themes(src)
        assert any(t[0] == "with" and "none" in t[1] for t in themes)

    def test_rejects_verb_matches(self) -> None:
        src = "def test_rejects_invalid_token(): pass"
        themes = self._themes(src)
        assert any(t[0] == "rejects" for t in themes)

    def test_preserves_verb_matches(self) -> None:
        src = "def test_preserves_order_on_insert(): pass"
        themes = self._themes(src)
        assert any(t[0] == "preserves" for t in themes)

    def test_non_semantic_name_does_not_match(self) -> None:
        # test_user_can_login has no semantic verb prefix — this is intentional.
        # The pattern only captures defensive intent, not positive scenarios.
        src = "def test_user_can_login(): pass"
        themes = self._themes(src)
        assert themes == []

    def test_plain_test_function_does_not_match(self) -> None:
        src = "def test_foo_bar(): pass"
        themes = self._themes(src)
        assert themes == []

    def test_multiple_matching_functions_all_extracted(self) -> None:
        src = """
def test_handles_empty_dict(): pass
def test_handles_circular_reference(): pass
def test_raises_on_none(): pass
def test_not_matching(): pass
"""
        themes = self._themes(src)
        assert len(themes) == 3

    def test_async_test_function_also_matched(self) -> None:
        src = "async def test_handles_timeout_gracefully(): pass"
        themes = self._themes(src)
        assert any(t[0] == "handles" for t in themes)

    def test_subject_truncated_to_two_tokens(self) -> None:
        # "handles_empty_iterator_when_exhausted" → subject = "empty_iterator"
        src = "def test_handles_empty_iterator_when_exhausted(): pass"
        themes = self._themes(src)
        subjects = [t[1] for t in themes]
        assert "empty_iterator" in subjects


# ---------------------------------------------------------------------------
# TestRaisesExtractor — signal 3
# ---------------------------------------------------------------------------

class TestRaisesExtractor:
    # pytest.raises blocks are the most explicit signal in the test suite:
    # the maintainer is asserting "this exact exception must be raised."
    # We extract the exception type AND the triggering call so AI agents
    # understand both what fails and what causes it.

    def _raises(self, src: str) -> list[tuple[str, str]]:
        return _extract_raises_blocks(_parse(src))

    def test_simple_value_error(self) -> None:
        src = """
def test_something():
    with pytest.raises(ValueError):
        foo()
"""
        pairs = self._raises(src)
        assert any(exc == "ValueError" and "foo()" in trigger for exc, trigger in pairs)

    def test_custom_exception(self) -> None:
        src = """
def test_something():
    with pytest.raises(MyExc):
        obj.method(arg)
"""
        pairs = self._raises(src)
        assert any(exc == "MyExc" for exc, trigger in pairs)
        assert any("obj.method(arg)" in trigger for exc, trigger in pairs)

    def test_dotted_exception_type(self) -> None:
        # pydantic.ValidationError and similar dotted names must be preserved
        # as-is — they uniquely identify the exception across namespaces.
        src = """
def test_something():
    with pytest.raises(pkg.ExcType):
        risky_call()
"""
        pairs = self._raises(src)
        assert any(exc == "pkg.ExcType" for exc, trigger in pairs)

    def test_non_raises_with_block_ignored(self) -> None:
        src = """
def test_something():
    with open("file.txt") as f:
        data = f.read()
"""
        pairs = self._raises(src)
        assert pairs == []

    def test_multiple_raises_blocks_extracted(self) -> None:
        src = """
def test_a():
    with pytest.raises(ValueError):
        a()

def test_b():
    with pytest.raises(TypeError):
        b()
"""
        pairs = self._raises(src)
        exc_names = [exc for exc, _ in pairs]
        assert "ValueError" in exc_names
        assert "TypeError" in exc_names

    def test_empty_raises_body_handled(self) -> None:
        # A body with only `pass` should produce an empty trigger, not crash.
        src = """
def test_something():
    with pytest.raises(RuntimeError):
        pass
"""
        pairs = self._raises(src)
        assert len(pairs) == 1
        exc, trigger = pairs[0]
        assert exc == "RuntimeError"
        # trigger may be empty string but must not raise

    def test_raises_with_match_kwarg_still_extracted(self) -> None:
        # pytest.raises(ValueError, match=r"...") — the kwarg doesn't affect extraction.
        src = """
def test_something():
    with pytest.raises(ValueError, match=r"bad input"):
        parse(None)
"""
        pairs = self._raises(src)
        assert any(exc == "ValueError" for exc, _ in pairs)


# ---------------------------------------------------------------------------
# TestExtractTestDecisions — integration
# ---------------------------------------------------------------------------

class TestExtractTestDecisions:
    # Integration tests verify that the three signals compose correctly and
    # that all filtering (non-test paths, truncated files, syntax errors) is
    # applied before any extraction.

    def test_empty_input_returns_empty_decisions(self) -> None:
        result = extract_test_decisions([])
        assert result.edge_cases == []
        assert result.name_themes == []
        assert result.raises_groups == []
        assert result.test_file_count == 0
        assert result.has_signal is False

    def test_single_test_file_populates_all_signals(self) -> None:
        content = """
import pytest

@pytest.mark.parametrize("value", [None, "", -1, []])
def test_handles_empty_input(value):
    pass

def test_raises_on_invalid_type():
    with pytest.raises(TypeError):
        process(None)

def test_handles_none_gracefully():
    pass
"""
        files = [_sf(content)]
        result = extract_test_decisions(files)
        assert result.test_file_count == 1
        # Signal 1: None, "", -1, [] should all trigger
        assert len(result.edge_cases) >= 3
        # Signal 2: test_handles_empty_input and test_handles_none_gracefully match
        assert any(t.verb == "handles" for t in result.name_themes)
        # Signal 3: TypeError expected
        assert any(rg.exception == "TypeError" for rg in result.raises_groups)

    def test_files_outside_test_paths_ignored(self) -> None:
        content = """
@pytest.mark.parametrize("x", [None, ""])
def test_handles_empty(x):
    pass
"""
        # Under lib/ — not a test path
        files = [_sf(content, path="lib/helpers.py")]
        result = extract_test_decisions(files)
        assert result.test_file_count == 0
        assert result.edge_cases == []

    def test_truncated_files_skipped(self) -> None:
        truncated = "# [TRUNCATED: 5000 lines → key signatures only]\ndef test_foo(): pass"
        files = [_sf(truncated)]
        result = extract_test_decisions(files)
        assert result.test_file_count == 0

    def test_syntax_error_files_skipped_without_crashing(self) -> None:
        bad_syntax = "def test_foo(:\n    pass\n"
        files = [_sf(bad_syntax)]
        # Must not raise — silently skips
        result = extract_test_decisions(files)
        assert result.test_file_count == 0

    def test_test_file_count_counts_only_test_files(self) -> None:
        test_content = "def test_handles_empty(): pass"
        non_test_content = "def helper(): pass"
        files = [
            _sf(test_content, path="tests/test_a.py"),
            _sf(test_content, path="tests/test_b.py"),
            _sf(non_test_content, path="lib/utils.py"),
        ]
        result = extract_test_decisions(files)
        assert result.test_file_count == 2

    def test_non_python_test_files_skipped(self) -> None:
        files = [
            SourceFile(
                path=Path("tests/test_ui.spec.ts"),
                content="describe('foo', () => { it('bar', () => {}) })",
                layer="frontend",
                role="test",
            )
        ]
        result = extract_test_decisions(files)
        assert result.test_file_count == 0

    def test_edge_cases_sorted_by_file_then_name(self) -> None:
        # Sorting ensures deterministic output across runs with different file orderings.
        content_b = """
@pytest.mark.parametrize("x", [None])
def test_a_func(x): pass
"""
        content_a = """
@pytest.mark.parametrize("y", [None])
def test_z_func(y): pass
"""
        files = [
            _sf(content_b, path="tests/test_beta.py"),
            _sf(content_a, path="tests/test_alpha.py"),
        ]
        result = extract_test_decisions(files)
        if len(result.edge_cases) >= 2:
            assert result.edge_cases[0].test_file <= result.edge_cases[1].test_file

    def test_raises_groups_aggregated_by_exception(self) -> None:
        content = """
import pytest

def test_a():
    with pytest.raises(ValueError):
        a()

def test_b():
    with pytest.raises(ValueError):
        b()

def test_c():
    with pytest.raises(TypeError):
        c()
"""
        files = [_sf(content)]
        result = extract_test_decisions(files)
        exc_map = {rg.exception: rg for rg in result.raises_groups}
        assert "ValueError" in exc_map
        assert exc_map["ValueError"].count == 2
        assert "TypeError" in exc_map
        assert exc_map["TypeError"].count == 1

    def test_raises_groups_sorted_by_count_desc(self) -> None:
        content = """
import pytest

def test_a():
    with pytest.raises(RareError): x()

def test_b():
    with pytest.raises(CommonError): x()

def test_c():
    with pytest.raises(CommonError): y()
"""
        files = [_sf(content)]
        result = extract_test_decisions(files)
        if len(result.raises_groups) >= 2:
            assert result.raises_groups[0].count >= result.raises_groups[1].count

    def test_name_themes_sorted_by_count_desc(self) -> None:
        content = """
def test_handles_a(): pass
def test_handles_b(): pass
def test_handles_c(): pass
def test_raises_x(): pass
"""
        files = [_sf(content)]
        result = extract_test_decisions(files)
        # handles cluster (3) should appear before raises cluster (1)
        verbs = [t.verb for t in result.name_themes]
        if "handles" in verbs and "raises" in verbs:
            assert verbs.index("handles") < verbs.index("raises")

    def test_has_signal_false_when_all_empty(self) -> None:
        decisions = _empty_decisions()
        assert decisions.has_signal is False

    def test_has_signal_true_when_any_signal(self) -> None:
        decisions = TestDecisions(
            edge_cases=[
                EdgeCase(
                    test_file="tests/t.py",
                    test_name="test_x",
                    params="x",
                    case_repr="None",
                    why="contains None",
                )
            ],
            name_themes=[],
            raises_groups=[],
            test_file_count=1,
        )
        assert decisions.has_signal is True


# ---------------------------------------------------------------------------
# TestRenderTestsDistilledMd — renderer
# ---------------------------------------------------------------------------

class TestRenderTestsDistilledMd:
    # Render tests verify the output contract: sections present iff list
    # non-empty, specific strings appear, and empty TestDecisions returns "".

    def test_empty_decisions_returns_empty_string(self) -> None:
        assert render_tests_distilled_md(_empty_decisions(), source_target="myrepo") == ""

    def _theme(self, verb: str, subject: str, count: int, examples: list[str]) -> NameTheme:
        return NameTheme(verb=verb, subject=subject, count=count, examples=examples)

    def _ec(self, **kwargs: str) -> EdgeCase:
        defaults = dict(
            test_file="tests/t.py",
            test_name="test_x",
            params="x",
            case_repr="None",
            why="contains None",
        )
        defaults.update(kwargs)
        return EdgeCase(**defaults)  # type: ignore[arg-type]

    def test_source_target_appears_in_output(self) -> None:
        decisions = TestDecisions(
            edge_cases=[],
            name_themes=[self._theme("handles", "empty", 1, ["test_handles_empty"])],
            raises_groups=[],
            test_file_count=3,
        )
        md = render_tests_distilled_md(decisions, source_target="github.com/org/repo")
        assert "github.com/org/repo" in md

    def test_test_file_count_appears_in_output(self) -> None:
        decisions = TestDecisions(
            edge_cases=[],
            name_themes=[self._theme("raises", "error", 2, ["test_raises_error"])],
            raises_groups=[],
            test_file_count=42,
        )
        md = render_tests_distilled_md(decisions, source_target="repo")
        assert "42" in md

    def test_themes_section_present_when_name_themes_non_empty(self) -> None:
        decisions = TestDecisions(
            edge_cases=[],
            name_themes=[self._theme("handles", "empty", 5, ["test_handles_empty"])],
            raises_groups=[],
            test_file_count=1,
        )
        md = render_tests_distilled_md(decisions, source_target="repo")
        assert "## Top defensive themes" in md

    def test_themes_section_omitted_when_name_themes_empty(self) -> None:
        decisions = TestDecisions(
            edge_cases=[self._ec()],
            name_themes=[],
            raises_groups=[],
            test_file_count=1,
        )
        md = render_tests_distilled_md(decisions, source_target="repo")
        assert "## Top defensive themes" not in md

    def test_raises_section_present_when_raises_groups_non_empty(self) -> None:
        decisions = TestDecisions(
            edge_cases=[],
            name_themes=[],
            raises_groups=[RaisesGroup(exception="ValueError", count=3, triggers=["foo()"])],
            test_file_count=1,
        )
        md = render_tests_distilled_md(decisions, source_target="repo")
        assert "## Explicit failure expectations" in md
        assert "ValueError" in md

    def test_raises_section_omitted_when_raises_groups_empty(self) -> None:
        decisions = TestDecisions(
            edge_cases=[self._ec()],
            name_themes=[],
            raises_groups=[],
            test_file_count=1,
        )
        md = render_tests_distilled_md(decisions, source_target="repo")
        assert "## Explicit failure expectations" not in md

    def test_edge_cases_section_present_when_edge_cases_non_empty(self) -> None:
        decisions = TestDecisions(
            edge_cases=[self._ec(params="value")],
            name_themes=[],
            raises_groups=[],
            test_file_count=1,
        )
        md = render_tests_distilled_md(decisions, source_target="repo")
        assert "## Notable parametrize edge cases" in md

    def test_edge_cases_section_omitted_when_edge_cases_empty(self) -> None:
        decisions = TestDecisions(
            edge_cases=[],
            name_themes=[self._theme("handles", "empty", 1, ["test_handles_empty"])],
            raises_groups=[],
            test_file_count=1,
        )
        md = render_tests_distilled_md(decisions, source_target="repo")
        assert "## Notable parametrize edge cases" not in md

    def test_h1_header_present(self) -> None:
        decisions = TestDecisions(
            edge_cases=[],
            name_themes=[self._theme("handles", "empty", 1, ["test_handles_empty"])],
            raises_groups=[],
            test_file_count=1,
        )
        md = render_tests_distilled_md(decisions, source_target="repo")
        assert "# Tests Distilled" in md

    def test_all_three_sections_present(self) -> None:
        decisions = TestDecisions(
            edge_cases=[self._ec()],
            name_themes=[self._theme("handles", "empty", 1, ["test_handles_empty"])],
            raises_groups=[RaisesGroup(exception="ValueError", count=1, triggers=["foo()"])],
            test_file_count=2,
        )
        md = render_tests_distilled_md(decisions, source_target="repo")
        assert "## Top defensive themes" in md
        assert "## Explicit failure expectations" in md
        assert "## Notable parametrize edge cases" in md

    def test_trigger_lines_appear_under_exception(self) -> None:
        decisions = TestDecisions(
            edge_cases=[],
            name_themes=[],
            raises_groups=[
                RaisesGroup(
                    exception="ValueError",
                    count=2,
                    triggers=["process(None)", "parse('')"],
                )
            ],
            test_file_count=1,
        )
        md = render_tests_distilled_md(decisions, source_target="repo")
        assert "process(None)" in md
        assert "parse('')" in md


# ---------------------------------------------------------------------------
# TestJsonRoundtrip — serialization
# ---------------------------------------------------------------------------

class TestJsonRoundtrip:
    # to_json/from_json must be lossless so sessions saved to disk can be
    # reloaded into identical in-memory structures.

    def test_edge_case_roundtrip(self) -> None:
        ec = EdgeCase(
            test_file="tests/t.py",
            test_name="test_x",
            params="value",
            case_repr="None",
            why="contains None",
        )
        assert EdgeCase.from_json(ec.to_json()) == ec

    def test_name_theme_roundtrip(self) -> None:
        nt = NameTheme(verb="handles", subject="empty", count=5, examples=["test_handles_empty"])
        assert NameTheme.from_json(nt.to_json()) == nt

    def test_raises_group_roundtrip(self) -> None:
        rg = RaisesGroup(exception="ValueError", count=3, triggers=["foo()"])
        assert RaisesGroup.from_json(rg.to_json()) == rg

    def test_test_decisions_roundtrip(self) -> None:
        td = TestDecisions(
            edge_cases=[
                EdgeCase(
                    test_file="tests/t.py",
                    test_name="test_x",
                    params="x",
                    case_repr="None",
                    why="contains None",
                )
            ],
            name_themes=[
                NameTheme(
                    verb="handles", subject="empty", count=1, examples=["test_handles_empty"]
                )
            ],
            raises_groups=[RaisesGroup(exception="ValueError", count=1, triggers=["foo()"])],
            test_file_count=5,
        )
        assert TestDecisions.from_json(td.to_json()) == td

    def test_from_json_handles_missing_fields(self) -> None:
        # Older sessions without test_decisions key should deserialize gracefully.
        minimal = {}
        td = TestDecisions.from_json(minimal)
        assert td.edge_cases == []
        assert td.name_themes == []
        assert td.raises_groups == []
        assert td.test_file_count == 0


# ---------------------------------------------------------------------------
# TestPipelineIntegration — run_full_analysis wiring
# ---------------------------------------------------------------------------

class TestPipelineIntegration:
    # Verifies that test_decisions is populated on SessionResult after
    # run_full_analysis. Uses a tiny in-memory file set to avoid network calls
    # or disk access.

    def test_session_result_has_test_decisions_field(self) -> None:
        """TestDecisions is populated (even empty) after extraction."""
        from hijack.core.test_decisions import extract_test_decisions

        test_file = _sf(
            """
import pytest

@pytest.mark.parametrize("val", [None, "", -1])
def test_handles_edge_cases(val):
    pass

def test_raises_on_none():
    with pytest.raises(ValueError):
        process(val)

def test_handles_empty_input():
    pass
""",
            path="tests/test_pipeline.py",
        )
        non_test = _sf("def helper(): pass", path="src/utils.py")

        decisions = extract_test_decisions([test_file, non_test])

        # test_file_count: only the test file counted
        assert decisions.test_file_count == 1
        # Edge cases from None, "", -1
        assert len(decisions.edge_cases) >= 3
        # Name themes from test_handles_edge_cases and test_handles_empty_input
        assert any(t.verb == "handles" for t in decisions.name_themes)
        # Raises: ValueError
        assert any(rg.exception == "ValueError" for rg in decisions.raises_groups)
        assert decisions.has_signal is True

    def test_models_session_result_test_decisions_field_defaults_none(self) -> None:
        """SessionResult.test_decisions defaults to None (backward compat)."""
        from hijack.core.models import SessionResult

        session = SessionResult(
            session_id="test-session",
            target="repo",
            model="claude",
            timestamp="2026-01-01T00:00:00+00:00",
            selected_files=[],
            categories=[],
            analysis_duration_seconds=0.0,
            project_structure="",
        )
        assert session.test_decisions is None

    def test_session_result_to_json_omits_test_decisions_when_none(self) -> None:
        """When test_decisions is None, it is omitted from to_json output."""
        from hijack.core.models import SessionResult

        session = SessionResult(
            session_id="s",
            target="t",
            model="m",
            timestamp="ts",
            selected_files=[],
            categories=[],
            analysis_duration_seconds=0.0,
            project_structure="",
        )
        data = session.to_json()
        assert "test_decisions" not in data

    def test_session_result_to_json_includes_test_decisions_when_present(self) -> None:
        """When test_decisions is set, it appears in the JSON."""
        from hijack.core.models import SessionResult
        from hijack.core.test_decisions import TestDecisions

        td = TestDecisions(
            edge_cases=[],
            name_themes=[],
            raises_groups=[],
            test_file_count=3,
        )
        session = SessionResult(
            session_id="s",
            target="t",
            model="m",
            timestamp="ts",
            selected_files=[],
            categories=[],
            analysis_duration_seconds=0.0,
            project_structure="",
            test_decisions=td,
        )
        data = session.to_json()
        assert "test_decisions" in data
        assert data["test_decisions"]["test_file_count"] == 3

    def test_session_result_from_json_deserializes_test_decisions(self) -> None:
        """from_json reconstructs test_decisions when present in the data."""
        from hijack.core.models import SessionResult

        data = {
            "session_id": "s",
            "target": "t",
            "model": "m",
            "timestamp": "ts",
            "selected_files": [],
            "categories": [],
            "analysis_duration_seconds": 0.0,
            "project_structure": "",
            "test_decisions": {
                "edge_cases": [],
                "name_themes": [],
                "raises_groups": [],
                "test_file_count": 7,
            },
        }
        session = SessionResult.from_json(data)
        assert session.test_decisions is not None
        assert session.test_decisions.test_file_count == 7
