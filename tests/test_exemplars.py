"""Tests for core/exemplars.py — selection, scoring, render."""
from __future__ import annotations

from pathlib import Path

from hijack.core.exemplars import (
    Exemplar,
    _score_length,
    _score_length_class,
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


class TestScoreLengthClass:
    def test_below_5_returns_zero(self) -> None:
        assert _score_length_class(4) == 0.0

    def test_5_to_7_returns_half(self) -> None:
        assert _score_length_class(5) == 0.5
        assert _score_length_class(7) == 0.5

    def test_sweet_spot_extends_to_200(self) -> None:
        assert _score_length_class(8) == 1.0
        assert _score_length_class(50) == 1.0
        assert _score_length_class(150) == 1.0
        assert _score_length_class(200) == 1.0

    def test_201_to_400_moderate(self) -> None:
        assert _score_length_class(201) == 0.6
        assert _score_length_class(400) == 0.6

    def test_over_400_low(self) -> None:
        assert _score_length_class(401) == 0.3
        assert _score_length_class(1000) == 0.3

    def test_class_sweet_spot_wider_than_function(self) -> None:
        # A 100-line class scores 1.0 but a 100-line function scores 0.3 —
        # the differentiation is the whole point of the separate curve.
        assert _score_length_class(100) == 1.0
        assert _score_length(100) == 0.3


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

    def test_skips_files_in_tests_dir(self) -> None:
        # Code that would otherwise score well, but lives under tests/
        files = [_sf(GOOD_FUNCTION, path="tests/test_user.py")]
        result = select_exemplars(files)
        assert result == []

    def test_skips_files_in_nested_tests_dir(self) -> None:
        files = [_sf(GOOD_FUNCTION, path="src/pkg/tests/helpers.py")]
        result = select_exemplars(files)
        assert result == []

    def test_skips_files_in_docs_src_dir(self) -> None:
        files = [_sf(GOOD_FUNCTION, path="docs_src/tutorial001.py")]
        result = select_exemplars(files)
        assert result == []

    def test_skips_files_in_scripts_dir(self) -> None:
        files = [_sf(GOOD_FUNCTION, path="scripts/build_helper.py")]
        result = select_exemplars(files)
        assert result == []

    def test_skips_files_in_examples_dir(self) -> None:
        files = [_sf(GOOD_FUNCTION, path="examples/quickstart.py")]
        result = select_exemplars(files)
        assert result == []

    def test_skips_files_in_tools_dir(self) -> None:
        # `tools/` typically holds dev/build/CI utilities (code generators,
        # release scripts). Exposed by SQLAlchemy where tools/toxnox.py
        # outscored real library APIs.
        files = [_sf(GOOD_FUNCTION, path="tools/generate_proxy_methods.py")]
        result = select_exemplars(files)
        assert result == []

    def test_skips_files_in_github_dir(self) -> None:
        # .github/ holds CI workflow scripts and automation, not library code.
        files = [_sf(GOOD_FUNCTION, path=".github/actions/people/people.py")]
        result = select_exemplars(files)
        assert result == []

    def test_skips_files_in_deprecated_dir(self) -> None:
        # `deprecated/` is a project's own marker that the code is no longer
        # the senior pattern.
        files = [_sf(GOOD_FUNCTION, path="pkg/deprecated/json.py")]
        result = select_exemplars(files)
        assert result == []

    def test_skips_files_in_legacy_dir(self) -> None:
        files = [_sf(GOOD_FUNCTION, path="pkg/legacy/v1.py")]
        result = select_exemplars(files)
        assert result == []

    def test_does_not_skip_top_level_tests_py_file(self) -> None:
        # A library file literally named "tests.py" at the top level should
        # NOT be excluded — only directory prefixes like tests/ count.
        files = [_sf(GOOD_FUNCTION, path="tests.py")]
        result = select_exemplars(files)
        assert len(result) == 1

    def test_max_per_layer_caps_first_pass_only(self) -> None:
        # max_per_layer is a soft cap: pass 1 enforces it for diversity, pass 2
        # fills remaining slots ignoring it so single-layer libraries don't
        # ship a half-empty exemplars.md.
        f1 = _sf(GOOD_FUNCTION, path="backend/a.py")
        f2 = _sf(TYPED_CLASS, path="backend/b.py")
        f3 = _sf(LONG_FUNCTION, path="backend/c.py")
        result = select_exemplars([f1, f2, f3], max_per_layer=2, max_total=8)
        # All three picked: pass 1 picks 2, pass 2 picks the remaining 1.
        assert len(result) == 3

    def test_max_per_layer_diversity_preserved_when_other_layers_present(
        self,
    ) -> None:
        # When multiple layers have candidates, pass 1 keeps each layer
        # represented up to its cap before pass 2 fills the rest by score.
        files = [
            _sf(GOOD_FUNCTION, path="backend/a.py", layer="backend"),
            _sf(TYPED_CLASS, path="backend/b.py", layer="backend"),
            _sf(LONG_FUNCTION, path="backend/c.py", layer="backend"),
            _sf(GOOD_FUNCTION, path="frontend/a.py", layer="frontend"),
        ]
        result = select_exemplars(files, max_per_layer=2, max_total=8)
        layers = {e.layer for e in result}
        # frontend candidate must appear — pass 1 guarantees it before
        # backend's third candidate fills via pass 2.
        assert "frontend" in layers
        assert "backend" in layers

    def test_max_total_is_hard_cap(self) -> None:
        # max_total caps the final result regardless of candidate count
        # or per-layer values. This is the hard ceiling.
        files = [
            _sf(GOOD_FUNCTION, path="backend/a.py", layer="backend"),
            _sf(TYPED_CLASS, path="backend/b.py", layer="backend"),
            _sf(GOOD_FUNCTION, path="shared/c.py", layer="shared"),
            _sf(TYPED_CLASS, path="shared/d.py", layer="shared"),
            _sf(GOOD_FUNCTION, path="db/e.py", layer="db"),
        ]
        result = select_exemplars(files, max_total=3)
        assert len(result) == 3

    def test_subdir_diversity_surfaces_new_subpackage(self) -> None:
        # 5 candidates in pkg/ root, 1 in pkg/security/ — without subdir
        # diversity the subpackage gets crowded out by the better-scoring
        # root candidates. With diversity (pass 2a) it must surface.
        files = [
            _sf(GOOD_FUNCTION, path=f"pkg/a{i}.py", layer="backend")
            for i in range(5)
        ]
        files.append(
            _sf(GOOD_FUNCTION, path="pkg/security/scheme.py", layer="backend")
        )
        result = select_exemplars(files, max_total=3, max_per_layer=4)
        subdirs = {e.file_path.rsplit("/", 1)[0] for e in result}
        assert "pkg/security" in subdirs

    def test_subdir_diversity_does_not_block_when_only_one_dir(self) -> None:
        # All candidates live in the same subdirectory — pass 2a finds no
        # new dirs to spread to, so pass 2b must fill the rest.
        files = [
            _sf(GOOD_FUNCTION, path=f"pkg/a{i}.py", layer="backend")
            for i in range(5)
        ]
        result = select_exemplars(files, max_total=4, max_per_layer=4)
        assert len(result) == 4

    def test_phase1_skips_private_names(self) -> None:
        # A new subdirectory whose top scorer is private (e.g. _helper) must
        # not steal phase-1's diversity slot — the slot is for "what this
        # subpackage exports." Private candidates can still surface in
        # phase 2/3 if they outscore public candidates.
        public_class = TYPED_CLASS  # public name (UserService)
        # GOOD_FUNCTION's func is `process_user` (public). Make a private
        # variant by tweaking the name in a separate fixture.
        private_func = GOOD_FUNCTION.replace("process_user", "_process_user")
        files = [
            _sf(public_class, path="pkg/main.py"),
            _sf(private_func, path="pkg/internal/helpers.py"),
        ]
        result = select_exemplars(files, max_total=1, max_per_layer=4)
        names = {e.name for e in result}
        # Phase 1 should pick the public class, not the private function,
        # even though `pkg/internal` is a "new" subdirectory.
        assert "UserService" in names
        assert "_process_user" not in names

    def test_init_without_return_annotation_not_penalised(self) -> None:
        # Senior `__init__` methods routinely omit the trivial `-> None`.
        # The class score must not be dragged down for that.
        init_no_return = """\
class TypedInit:
    \"\"\"A class with a fully typed __init__ but no `-> None` on it.\"\"\"
    def __init__(self, name: str, count: int = 0):
        self.name = name
        self.count = count
"""
        files = [_sf(init_no_return, path="pkg/typed.py")]
        result = select_exemplars(files)
        assert len(result) == 1
        assert result[0].name == "TypedInit"

    def test_repo_root_recovers_truncated_file(self, tmp_path: Path) -> None:
        # The fetcher prepends "# [TRUNCATED:" to large files. Without
        # repo_root, exemplars can't recover the body and skips the file.
        # With repo_root, content is re-read from disk.
        target_file = tmp_path / "big.py"
        target_file.write_text(GOOD_FUNCTION, encoding="utf-8")

        truncated = (
            "# [TRUNCATED: 5000 lines → key signatures only]\n"
            "def noop(): pass\n"
        )
        sf = _sf(truncated, path="big.py")

        # Without repo_root: skipped because content starts with marker.
        assert select_exemplars([sf]) == []

        # With repo_root: disk read recovers the real body.
        result = select_exemplars([sf], repo_root=tmp_path)
        assert len(result) == 1
        assert result[0].name == "process_user"

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

    def test_max_per_file_caps_picks_from_dominant_file(self) -> None:
        # A dominant file with 3 high-scoring candidates plus two other files
        # should contribute at most max_per_file=2 exemplars, preventing one
        # file from crowding out diversity across the repo.
        dominant = GOOD_FUNCTION + "\n" + TYPED_CLASS + "\n" + LONG_FUNCTION
        files = [
            _sf(dominant, path="pkg/dominant.py", layer="backend"),
            _sf(GOOD_FUNCTION, path="pkg/other1.py", layer="backend"),
            _sf(TYPED_CLASS, path="pkg/other2.py", layer="backend"),
        ]
        result = select_exemplars(files, max_per_file=2, max_total=8, max_per_layer=8)
        dominant_picks = sum(1 for e in result if e.file_path == "pkg/dominant.py")
        assert dominant_picks <= 2

    def test_max_per_file_default_is_two(self) -> None:
        # Without an explicit max_per_file, the default of 2 must hold — same
        # setup as above but relying solely on the default parameter value.
        dominant = GOOD_FUNCTION + "\n" + TYPED_CLASS + "\n" + LONG_FUNCTION
        files = [
            _sf(dominant, path="pkg/dominant.py", layer="backend"),
            _sf(GOOD_FUNCTION, path="pkg/other1.py", layer="backend"),
            _sf(TYPED_CLASS, path="pkg/other2.py", layer="backend"),
        ]
        result = select_exemplars(files, max_total=8, max_per_layer=8)
        dominant_picks = sum(1 for e in result if e.file_path == "pkg/dominant.py")
        assert dominant_picks <= 2

    def test_skips_paths_with_private_dir_component(self) -> None:
        # Any file whose directory path contains an underscore-prefixed
        # component (Python path-private convention) must be excluded entirely.
        files = [_sf(GOOD_FUNCTION, path="pkg/_internal/helpers.py")]
        result = select_exemplars(files)
        assert result == []

    def test_does_not_skip_dunder_init_filename(self) -> None:
        # A file named __init__.py at a public path should NOT be skipped —
        # only directory components are checked, not the filename itself.
        # This guards the `path.parent.parts` vs full-path distinction.
        files = [_sf(GOOD_FUNCTION, path="pkg/__init__.py")]
        result = select_exemplars(files)
        assert len(result) == 1


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
