from __future__ import annotations

from pathlib import Path

from hijack.core.fetcher import SourceFile
from hijack.core.preprocessor import (
    PreprocessResult,
    build_file_summary_for_llm,
    build_layer_stats,
    build_preprocess_result,
    select_files_for_category,
)


def _make_file(rel: str, role: str = "other", layer: str = "shared") -> SourceFile:
    return SourceFile(path=Path(rel), content=f"# {rel}", layer=layer, role=role)


def _make_result(files: list[SourceFile], repo_root: Path | None = None) -> PreprocessResult:
    return build_preprocess_result(files, repo_root or Path("/repo"))


class TestBuildPreprocessResult:
    def test_by_role_grouping(self) -> None:
        files = [
            _make_file("a.py", role="api"),
            _make_file("b.py", role="api"),
            _make_file("c.py", role="model"),
        ]
        result = _make_result(files)
        assert len(result.by_role["api"]) == 2
        assert len(result.by_role["model"]) == 1

    def test_by_layer_grouping(self) -> None:
        files = [
            _make_file("a.py", layer="backend"),
            _make_file("b.tsx", layer="frontend"),
            _make_file("c.py", layer="backend"),
        ]
        result = _make_result(files)
        assert len(result.by_layer["backend"]) == 2
        assert len(result.by_layer["frontend"]) == 1

    def test_by_role_layer_2d(self) -> None:
        files = [
            _make_file("a.py", role="api", layer="backend"),
            _make_file("b.py", role="api", layer="shared"),
            _make_file("c.py", role="model", layer="db"),
        ]
        result = _make_result(files)
        assert len(result.by_role_layer["api"]["backend"]) == 1
        assert len(result.by_role_layer["api"]["shared"]) == 1
        assert len(result.by_role_layer["model"]["db"]) == 1

    def test_project_structure_contains_filenames(self) -> None:
        files = [_make_file("src/main.py"), _make_file("src/utils.py")]
        result = _make_result(files)
        assert "main.py" in result.project_structure
        assert "utils.py" in result.project_structure

    def test_empty_files(self) -> None:
        result = _make_result([])
        assert result.by_role == {}
        assert result.by_layer == {}


class TestSelectFilesForCategory:
    def test_architecture_prefers_entry_point(self) -> None:
        files = [
            _make_file("main.py", role="entry_point"),
            _make_file("test_a.py", role="test"),
            _make_file("service.py", role="service"),
        ]
        result = _make_result(files)
        selected = select_files_for_category(result, "architecture")
        assert selected[0].role == "entry_point"

    def test_max_files_limit(self) -> None:
        files = [_make_file(f"f{i}.py", role="other") for i in range(50)]
        result = _make_result(files)
        selected = select_files_for_category(result, "architecture", max_files=10)
        assert len(selected) == 10

    def test_no_duplicates(self) -> None:
        files = [_make_file("a.py", role="api")]
        result = _make_result(files)
        selected = select_files_for_category(result, "api_design", max_files=100)
        paths = [f.path.as_posix() for f in selected]
        assert len(paths) == len(set(paths))

    def test_unknown_category_falls_back(self) -> None:
        files = [_make_file("a.py", role="other")]
        result = _make_result(files)
        selected = select_files_for_category(result, "nonexistent_category")
        assert len(selected) == 1


class TestBuildFileSummaryForLlm:
    def test_includes_path_and_content(self) -> None:
        f = _make_file("src/main.py", role="entry_point", layer="backend")
        summaries = build_file_summary_for_llm([f])
        assert len(summaries) == 1
        assert "src/main.py" in summaries[0]
        assert "role=entry_point" in summaries[0]
        assert "layer=backend" in summaries[0]
        assert "# src/main.py" in summaries[0]

    def test_empty_files(self) -> None:
        assert build_file_summary_for_llm([]) == []


class TestBuildLayerStats:
    def test_all_layers_present(self) -> None:
        stats = build_layer_stats({"backend": 1, "frontend": 1})
        assert "backend: 1" in stats
        assert "frontend: 1" in stats
        assert "db: 0" in stats

    def test_empty_dict(self) -> None:
        stats = build_layer_stats({})
        assert "backend: 0" in stats
        assert "shared: 0" in stats
