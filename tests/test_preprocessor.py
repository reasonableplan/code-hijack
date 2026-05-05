from __future__ import annotations

from pathlib import Path

from hijack.core.archaeology import Commit, FileHistory
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
        # 숫자 변화 파일은 near-duplicate dedup 에 걸리므로 고유 이름 사용
        names = [chr(ord("a") + i) for i in range(15)]
        files = [_make_file(f"{n}.py", role="other") for n in names]
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

    def test_no_history_block_when_history_is_none(self) -> None:
        f = _make_file("src/main.py")
        summary = build_file_summary_for_llm([f])[0]
        assert "<history>" not in summary

    def test_history_block_appended_when_present(self) -> None:
        f = _make_file("src/main.py", role="entry_point", layer="backend")
        f.history = FileHistory(
            commits=[
                Commit(
                    sha="a1b2c3d4e5f6",
                    subject="refactor: drop pydantic",
                    author="Alice",
                    date="2024-08-12 14:30:00 +0900",
                    body="dataclasses are simpler.",
                )
            ]
        )
        summary = build_file_summary_for_llm([f])[0]
        assert "<history>" in summary
        assert "a1b2c3d" in summary
        assert "drop pydantic" in summary


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


class TestContentDensityRanking:
    def _file(self, rel: str, content: str, role: str = "other") -> SourceFile:
        return SourceFile(path=Path(rel), content=content, layer="shared", role=role)

    def test_meaningful_file_ranked_before_shallow(self) -> None:
        shallow = self._file("a.py", "x = 1", role="api")
        meaningful = self._file("b.py", "x" * 1000, role="api")
        result = _make_result([shallow, meaningful])
        selected = select_files_for_category(result, "api_design", max_files=10)
        assert selected[0].path.name == "b.py"
        assert selected[1].path.name == "a.py"

    def test_within_role_sorted_by_size_desc(self) -> None:
        medium = self._file("a.py", "x" * 1000, role="api")
        large = self._file("b.py", "x" * 3000, role="api")
        result = _make_result([medium, large])
        selected = select_files_for_category(result, "api_design", max_files=10)
        assert selected[0].path.name == "b.py"
        assert selected[1].path.name == "a.py"


class TestNearDuplicateDedup:
    def _file(self, rel: str, role: str = "other") -> SourceFile:
        return SourceFile(path=Path(rel), content="x" * 1000, layer="shared", role=role)

    def test_digit_varying_paths_capped_at_two(self) -> None:
        files = [
            self._file(f"docs_src/settings/app{i:02d}_py310/main.py", role="entry_point")
            for i in range(1, 7)
        ]
        result = _make_result(files)
        selected = select_files_for_category(result, "architecture", max_files=10)
        assert len(selected) == 2, f"Expected 2 from near-duplicates, got {len(selected)}"

    def test_distinct_paths_not_deduplicated(self) -> None:
        files = [
            self._file("a/main.py", role="entry_point"),
            self._file("b/main.py", role="entry_point"),
            self._file("c/main.py", role="entry_point"),
        ]
        result = _make_result(files)
        selected = select_files_for_category(result, "architecture", max_files=10)
        assert len(selected) == 3

    def test_mix_of_duplicates_and_distinct(self) -> None:
        files = [
            self._file("apps/v1/main.py", role="entry_point"),
            self._file("apps/v2/main.py", role="entry_point"),
            self._file("apps/v3/main.py", role="entry_point"),
            self._file("cli/main.py", role="entry_point"),
        ]
        result = _make_result(files)
        selected = select_files_for_category(result, "architecture", max_files=10)
        paths = {f.path.as_posix() for f in selected}
        assert "cli/main.py" in paths
        apps_count = sum(1 for p in paths if p.startswith("apps/"))
        assert apps_count == 2


class TestAuxiliaryDemote:
    def test_auxiliary_paths_demoted_below_library_source(self) -> None:
        """docs_src/ 의 main.py 가 fastapi/applications.py 같은 코어 파일을 밀어내면 안 된다."""
        files = [
            # 보조 경로 entry_point 들 (실 fastapi 패턴 모방)
            _make_file("docs_src/bigger_applications/app/main.py", role="entry_point"),
            _make_file("docs_src/settings/app02/main.py", role="entry_point"),
            _make_file("docs_src/security/app01/main.py", role="entry_point"),
            # 라이브러리 코어 (role="other" 라서 원래 entry_point 뒤로 밀림)
            _make_file("fastapi/applications.py", role="other"),
            _make_file("fastapi/routing.py", role="api"),
        ]
        result = _make_result(files)
        selected = select_files_for_category(result, "architecture", max_files=3)
        paths = [f.path.as_posix() for f in selected]
        # 라이브러리 코어 (fastapi/) 가 docs_src/ 보다 앞서야 함
        assert "fastapi/applications.py" in paths
        assert "fastapi/routing.py" in paths
        # docs_src/ 가 budget 안에 있다면 코어 뒤에만
        library_indices = [i for i, p in enumerate(paths) if p.startswith("fastapi/")]
        aux_indices = [i for i, p in enumerate(paths) if p.startswith("docs_src/")]
        if library_indices and aux_indices:
            assert max(library_indices) < min(aux_indices), \
                f"보조 경로가 코어보다 앞: {paths}"

    def test_auxiliary_only_repo_still_returned(self) -> None:
        """라이브러리 코어가 없고 docs_src/ 만 있으면 fallback 으로 그대로 반환."""
        files = [
            _make_file("docs_src/a/main.py", role="entry_point"),
            _make_file("docs_src/b/main.py", role="entry_point"),
        ]
        result = _make_result(files)
        selected = select_files_for_category(result, "architecture", max_files=10)
        assert len(selected) == 2
        assert all(f.path.as_posix().startswith("docs_src/") for f in selected)

    def test_auxiliary_fills_remaining_budget(self) -> None:
        """라이브러리 코어가 budget 보다 적으면 docs_src/ 가 나머지 채움."""
        files = [
            _make_file("fastapi/applications.py", role="other"),
            _make_file("docs_src/a/main.py", role="entry_point"),
            _make_file("docs_src/b/main.py", role="entry_point"),
        ]
        result = _make_result(files)
        selected = select_files_for_category(result, "architecture", max_files=10)
        paths = [f.path.as_posix() for f in selected]
        assert paths[0] == "fastapi/applications.py"
        # 나머지는 docs_src
        assert all(p.startswith("docs_src/") for p in paths[1:])

    def test_examples_dir_also_auxiliary(self) -> None:
        """examples/ 도 보조 경로로 demote."""
        files = [
            _make_file("examples/quickstart/main.py", role="entry_point"),
            _make_file("mylib/core.py", role="other"),
        ]
        result = _make_result(files)
        selected = select_files_for_category(result, "architecture", max_files=10)
        paths = [f.path.as_posix() for f in selected]
        assert paths[0] == "mylib/core.py"
        assert paths[1] == "examples/quickstart/main.py"


class TestOriginalCharsRanking:
    def test_truncated_large_file_ranked_above_full_small_file(self) -> None:
        """truncate 된 큰 파일이 full 인 작은 파일보다 우선해야 한다."""
        # truncate 된 큰 파일: content 는 짧지만 original_chars 는 큼
        truncated_big = SourceFile(
            path=Path("core.py"),
            content="# [TRUNCATED: 4000 lines]\nimport x\n",  # ~30자
            layer="backend",
            role="api",
            original_chars=150_000,  # 실제로는 거대
        )
        # full 작은 파일: content 자체가 그대로
        full_small = SourceFile(
            path=Path("compat.py"),
            content="x" * 5000,
            layer="backend",
            role="api",
            original_chars=5000,
        )
        result = _make_result([full_small, truncated_big])
        selected = select_files_for_category(result, "architecture", max_files=10)
        paths = [f.path.as_posix() for f in selected]
        assert paths.index("core.py") < paths.index("compat.py"), \
            f"truncate 된 큰 파일이 full 작은 파일보다 앞이어야 함: {paths}"

    def test_legacy_zero_original_chars_falls_back_to_content_len(self) -> None:
        """original_chars=0 (default) 인 fixture 는 기존처럼 len(content) 로 정렬."""
        big = SourceFile(path=Path("a.py"), content="x" * 3000, layer="backend", role="api")
        small = SourceFile(path=Path("b.py"), content="x" * 100, layer="backend", role="api")
        result = _make_result([small, big])
        selected = select_files_for_category(result, "architecture", max_files=10)
        paths = [f.path.as_posix() for f in selected]
        assert paths.index("a.py") < paths.index("b.py")
