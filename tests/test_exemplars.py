"""Tests for core/exemplars.py — selection, scoring, render."""
from __future__ import annotations

from pathlib import Path

from hijack.core.exemplars import (
    Exemplar,
    _score_length,
    _score_public,
    render_exemplars_md,
    select_exemplars,
)
from hijack.core.fetcher import SourceFile

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sf(
    content: str,
    path: str = "backend/service.py",
    layer: str = "backend",
    role: str = "service",
) -> SourceFile:
    return SourceFile(
        path=Path(path),
        content=content,
        layer=layer,
        role=role,
    )


def _exemplar(**kwargs) -> Exemplar:
    defaults = dict(
        file_path="backend/service.py",
        line_range=(1, 10),
        code="def foo(x: int) -> str:\n    return str(x)",
        layer="backend",
        role="service",
        name="foo",
        why_chosen="fully type-annotated, sweet-spot length (10 lines)",
    )
    defaults.update(kwargs)
    return Exemplar(**defaults)


# ---------------------------------------------------------------------------
# Unit tests: scoring helpers
# ---------------------------------------------------------------------------

class TestScoreLength:
    def test_below_5_returns_zero(self) -> None:
        assert _score_length(4) == 0.0
        assert _score_length(1) == 0.0

    def test_5_to_7_returns_half(self) -> None:
        assert _score_length(5) == 0.5
        assert _score_length(7) == 0.5

    def test_sweet_spot_8_to_30(self) -> None:
        assert _score_length(8) == 1.0
        assert _score_length(15) == 1.0
        assert _score_length(30) == 1.0

    def test_31_to_50_moderate(self) -> None:
        assert _score_length(31) == 0.7
        assert _score_length(50) == 0.7

    def test_over_50_low(self) -> None:
        assert _score_length(51) == 0.3
        assert _score_length(200) == 0.3


class TestScorePublic:
    def test_public_returns_1(self) -> None:
        assert _score_public("my_func") == 1.0
        assert _score_public("MyClass") == 1.0

    def test_private_returns_03(self) -> None:
        assert _score_public("_private") == 0.3
        assert _score_public("__dunder__") == 0.3


# ---------------------------------------------------------------------------
# select_exemplars — integration tests using SourceFile fixtures
# ---------------------------------------------------------------------------

# A well-scored function: typed, docstring, sweet-spot length
GOOD_FUNCTION = """\
def process_user(user_id: int, name: str) -> dict[str, str]:
    \"\"\"Build a user record dict.

    Args:
        user_id: numeric identifier
        name: display name

    Returns:
        Mapping with id and name keys.
    \"\"\"
    return {"id": str(user_id), "name": name}
"""

# A tiny stub — too short to be useful
TINY_STUB = """\
def noop() -> None:
    pass
"""

# A very long function (>50 lines)
LONG_FUNCTION = "\n".join(
    ["def big_func(x: int) -> int:", '    """Long docstring."""']
    + [f"    x = x + {i}" for i in range(60)]
    + ["    return x"]
)

# Private function
PRIVATE_FUNCTION = """\
def _internal_helper(x: int) -> int:
    \"\"\"Used internally.\"\"\"
    return x * 2
"""

# Typed class
TYPED_CLASS = """\
class UserService:
    \"\"\"Service layer for user operations.

    Handles creation and retrieval.
    \"\"\"
    def __init__(self, db_url: str, timeout: int) -> None:
        self.db_url = db_url
        self.timeout = timeout

    def get_user(self, user_id: int) -> dict[str, str] | None:
        return None
"""


class TestSelectExemplars:
    def test_picks_well_scored_function(self) -> None:
        files = [_sf(GOOD_FUNCTION)]
        result = select_exemplars(files)
        assert len(result) == 1
        assert result[0].name == "process_user"

    def test_ignores_tiny_stubs(self) -> None:
        files = [_sf(TINY_STUB)]
        result = select_exemplars(files)
        # noop() is 2 lines — falls below _MIN_SCORE
        assert result == []

    def test_long_function_beats_tiny_stub(self) -> None:
        files = [_sf(LONG_FUNCTION + "\n" + TINY_STUB)]
        result = select_exemplars(files)
        names = [e.name for e in result]
        # big_func has a docstring and length 63 lines → score higher than noop
        assert "big_func" in names

    def test_skips_truncated_files(self) -> None:
        truncated = "# [TRUNCATED: 3000 lines → key signatures only]\ndef foo(): pass"
        files = [_sf(truncated)]
        result = select_exemplars(files)
        assert result == []

    def test_skips_non_python_files(self) -> None:
        ts_file = SourceFile(
            path=Path("frontend/App.tsx"),
            content="export function App() { return <div/>; }",
            layer="frontend",
            role="entry_point",
        )
        result = select_exemplars([ts_file])
        assert result == []

    def test_skips_files_with_syntax_errors(self) -> None:
        bad_py = "def broken(:\n    pass\n"
        files = [_sf(bad_py)]
        result = select_exemplars(files)
        assert result == []

    def test_skips_empty_files(self) -> None:
        files = [_sf("")]
        result = select_exemplars(files)
        assert result == []

    def test_max_per_layer_enforced(self) -> None:
        # Three backend files, each with a scoreable function
        f1 = _sf(GOOD_FUNCTION, path="backend/a.py")
        f2 = _sf(TYPED_CLASS, path="backend/b.py")
        f3 = _sf(LONG_FUNCTION, path="backend/c.py")
        result = select_exemplars([f1, f2, f3], max_per_layer=2)
        backend_count = sum(1 for e in result if e.layer == "backend")
        assert backend_count <= 2

    def test_max_total_enforced(self) -> None:
        # Five files across different layers
        files = [
            _sf(GOOD_FUNCTION, path="backend/a.py", layer="backend"),
            _sf(TYPED_CLASS, path="backend/b.py", layer="backend"),
            _sf(GOOD_FUNCTION, path="shared/c.py", layer="shared"),
            _sf(TYPED_CLASS, path="shared/d.py", layer="shared"),
            _sf(GOOD_FUNCTION, path="db/e.py", layer="db"),
        ]
        result = select_exemplars(files, max_total=3)
        assert len(result) <= 3

    def test_all_below_threshold_returns_empty(self) -> None:
        # Only tiny stubs → all below _MIN_SCORE
        files = [
            _sf(TINY_STUB, path="a.py"),
            _sf(TINY_STUB, path="b.py"),
        ]
        result = select_exemplars(files)
        assert result == []

    def test_private_function_not_picked_when_public_available(self) -> None:
        combined = GOOD_FUNCTION + "\n" + PRIVATE_FUNCTION
        files = [_sf(combined)]
        result = select_exemplars(files, max_per_layer=1)
        # Public function should rank higher
        assert result[0].name == "process_user"

    def test_exemplar_has_correct_file_path(self) -> None:
        files = [_sf(GOOD_FUNCTION, path="utils/format.py")]
        result = select_exemplars(files)
        assert result[0].file_path == "utils/format.py"

    def test_exemplar_line_range_is_correct(self) -> None:
        files = [_sf(GOOD_FUNCTION)]
        result = select_exemplars(files)
        start, end = result[0].line_range
        assert start == 1
        assert end >= start

    def test_exemplar_layer_and_role_propagated(self) -> None:
        files = [_sf(GOOD_FUNCTION, layer="db", role="model")]
        result = select_exemplars(files)
        assert result[0].layer == "db"
        assert result[0].role == "model"

    def test_class_candidate_selected(self) -> None:
        files = [_sf(TYPED_CLASS, path="backend/services.py")]
        result = select_exemplars(files)
        assert any(e.name == "UserService" for e in result)

    def test_why_chosen_not_empty(self) -> None:
        files = [_sf(GOOD_FUNCTION)]
        result = select_exemplars(files)
        assert result[0].why_chosen != ""


# ---------------------------------------------------------------------------
# render_exemplars_md
# ---------------------------------------------------------------------------

class TestRenderExemplarsMd:
    def test_empty_list_returns_empty_string(self) -> None:
        assert render_exemplars_md([], source_target="myrepo") == ""

    def test_contains_source_target(self) -> None:
        ex = _exemplar()
        md = render_exemplars_md([ex], source_target="github.com/org/repo")
        assert "github.com/org/repo" in md

    def test_contains_file_path_and_line_range(self) -> None:
        ex = _exemplar(file_path="backend/service.py", line_range=(5, 20))
        md = render_exemplars_md([ex], source_target="repo")
        assert "backend/service.py:5-20" in md

    def test_contains_name(self) -> None:
        ex = _exemplar(name="process_user")
        md = render_exemplars_md([ex], source_target="repo")
        assert "`process_user`" in md

    def test_contains_layer_and_role_and_why(self) -> None:
        ex = _exemplar(layer="backend", role="service", why_chosen="fully typed")
        md = render_exemplars_md([ex], source_target="repo")
        assert "**Layer**: backend" in md
        assert "**Role**: service" in md
        assert "**Why chosen**: fully typed" in md

    def test_code_in_python_fence(self) -> None:
        code = "def foo(x: int) -> str:\n    return str(x)"
        ex = _exemplar(code=code)
        md = render_exemplars_md([ex], source_target="repo")
        assert "```python" in md
        assert code in md

    def test_multiple_exemplars_numbered(self) -> None:
        ex1 = _exemplar(name="func_a")
        ex2 = _exemplar(name="func_b", file_path="shared/util.py")
        md = render_exemplars_md([ex1, ex2], source_target="repo")
        assert "## Exemplar 1:" in md
        assert "## Exemplar 2:" in md

    def test_h1_header_present(self) -> None:
        ex = _exemplar()
        md = render_exemplars_md([ex], source_target="repo")
        assert "# Senior Exemplars" in md
