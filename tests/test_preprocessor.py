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

    def test_top_level_dotted_py_demoted_as_bootstrap(self) -> None:
        """G8 (2026-05-06): 루트의 `.skill_analysis.py` 같은 dotted bootstrap
        스크립트가 라이브러리 코어를 selection 에서 밀어내는 회귀 차단."""
        files = [
            _make_file(".skill_analysis.py", role="api"),
            _make_file(".skill_analysis_v2.py", role="api"),
            _make_file(".skill_analysis_fastapi.py", role="api"),
            _make_file("mylib/core.py", role="other"),
            _make_file("mylib/router.py", role="api"),
        ]
        result = _make_result(files)
        selected = select_files_for_category(result, "architecture", max_files=3)
        paths = [f.path.as_posix() for f in selected]
        # 라이브러리 코어가 dotted bootstrap 보다 앞서야 함
        assert "mylib/router.py" in paths
        assert "mylib/core.py" in paths
        bootstrap_indices = [i for i, p in enumerate(paths) if p.startswith(".")]
        core_indices = [i for i, p in enumerate(paths) if p.startswith("mylib/")]
        if bootstrap_indices and core_indices:
            assert max(core_indices) < min(bootstrap_indices)


class TestDetectRepoNature:
    """T-032: detect_repo_nature 단위 테스트."""

    def test_scripts_present_returns_app_cli(self) -> None:
        from hijack.core.preprocessor import detect_repo_nature
        pyproject = {"project": {"scripts": {"my-cli": "mypkg.__main__:main"}}}
        result = detect_repo_nature(pyproject, set())
        assert result == "app/cli"

    def test_entry_points_present_returns_app_cli(self) -> None:
        from hijack.core.preprocessor import detect_repo_nature
        pyproject = {"project": {"entry-points": {"console_scripts": {"cmd": "pkg:main"}}}}
        result = detect_repo_nature(pyproject, set())
        assert result == "app/cli"

    def test_frontend_layer_returns_app(self) -> None:
        from hijack.core.preprocessor import detect_repo_nature
        result = detect_repo_nature(None, {"frontend", "backend"})
        assert result == "app"

    def test_no_scripts_no_frontend_returns_library(self) -> None:
        from hijack.core.preprocessor import detect_repo_nature
        result = detect_repo_nature(None, {"backend", "shared"})
        assert result == "library"

    def test_scripts_wins_over_frontend_layer(self) -> None:
        """scripts 있고 frontend layer 도 있으면 app/cli 우선 (T-032 스펙 (d))."""
        from hijack.core.preprocessor import detect_repo_nature
        pyproject = {"project": {"scripts": {"cmd": "pkg:main"}}}
        result = detect_repo_nature(pyproject, {"frontend", "backend"})
        assert result == "app/cli"

    def test_none_pyproject_no_frontend_returns_library(self) -> None:
        from hijack.core.preprocessor import detect_repo_nature
        result = detect_repo_nature(None, set())
        assert result == "library"


class TestPreprocessResultRepoNature:
    """PreprocessResult.repo_nature 필드가 build_preprocess_result 에서 채워지는지 검증."""

    def test_default_repo_nature_is_library(self) -> None:
        result = _make_result([_make_file("a.py")])
        assert result.repo_nature == "library"

    def test_repo_nature_app_cli_when_pyproject_has_scripts(self) -> None:
        pyproject = {"project": {"scripts": {"my-cli": "pkg:main"}}}
        files = [_make_file("a.py")]
        result = build_preprocess_result(files, Path("/repo"), pyproject_toml=pyproject)
        assert result.repo_nature == "app/cli"

    def test_repo_nature_app_when_frontend_files(self) -> None:
        files = [_make_file("app.tsx", layer="frontend")]
        result = build_preprocess_result(files, Path("/repo"))
        assert result.repo_nature == "app"


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


# ---------------------------------------------------------------------------
# barrel demotion — TS/JS index.ts 파일이 실제 구현 파일을 밀어내지 않도록
# ---------------------------------------------------------------------------

class TestReexportBarrelDemotion:
    """`export * from '...'` 만 있는 barrel 파일은 auxiliary 로 demote.

    실제 케이스: frontend 프로젝트의 `src/shared/components/index.ts` 식 1-7줄짜리
    re-export 파일이 architecture/coding_style 선별 12개 중 4개를 잡아먹어
    informative 파일이 밀려나는 회귀를 방지.
    """

    def _impl(self, name: str) -> SourceFile:
        """non-barrel TS 파일 — 충분히 큰 실제 구현."""
        return SourceFile(
            path=Path(name),
            content="export const x = 1\n" * 200,  # ~3800자
            layer="frontend",
            role="other",
            original_chars=3800,
        )

    def _barrel(self, name: str, body: str) -> SourceFile:
        return SourceFile(
            path=Path(name),
            content=body,
            layer="frontend",
            role="other",
            original_chars=len(body),
        )

    def test_pure_export_star_barrel_demoted(self) -> None:
        barrel = self._barrel("index.ts", "export * from './button'\nexport * from './card'\n")
        impl = self._impl("button.ts")
        result = _make_result([barrel, impl])
        selected = select_files_for_category(result, "architecture", max_files=2)
        paths = [f.path.as_posix() for f in selected]
        # impl 이 먼저, barrel 은 뒤
        assert paths.index("button.ts") < paths.index("index.ts")

    def test_named_reexport_barrel_demoted(self) -> None:
        barrel = self._barrel(
            "index.ts",
            "export { Button } from './button'\nexport { default as Card } from './card'\n",
        )
        impl = self._impl("button.ts")
        result = _make_result([barrel, impl])
        selected = select_files_for_category(result, "architecture", max_files=2)
        paths = [f.path.as_posix() for f in selected]
        assert paths.index("button.ts") < paths.index("index.ts")

    def test_barrel_with_line_comments_demoted(self) -> None:
        barrel = self._barrel(
            "index.ts",
            "// ui exports\nexport * from './button'\n// custom\nexport * from './card'\n",
        )
        impl = self._impl("button.ts")
        result = _make_result([barrel, impl])
        selected = select_files_for_category(result, "architecture", max_files=2)
        paths = [f.path.as_posix() for f in selected]
        assert paths.index("button.ts") < paths.index("index.ts")

    def test_barrel_with_block_comment_demoted(self) -> None:
        barrel = self._barrel(
            "index.ts",
            "/* ui barrel\n   multi-line */\nexport * from './button'\n",
        )
        impl = self._impl("button.ts")
        result = _make_result([barrel, impl])
        selected = select_files_for_category(result, "architecture", max_files=2)
        paths = [f.path.as_posix() for f in selected]
        assert paths.index("button.ts") < paths.index("index.ts")

    def test_index_with_real_implementation_not_demoted(self) -> None:
        # index.ts 이름이지만 실제 코드가 있으면 demote 하면 안 됨.
        real_index = self._barrel(
            "index.ts",
            "export * from './button'\nexport const VERSION = '1.0'\n",
        )
        impl = self._impl("button.ts")
        result = _make_result([real_index, impl])
        selected = select_files_for_category(result, "architecture", max_files=2)
        paths = [f.path.as_posix() for f in selected]
        # 두 파일 모두 primary — 정렬은 content size 기준이지만 demote 차이는 없음
        assert "index.ts" in paths and "button.ts" in paths

    def test_python_init_with_from_imports_not_demoted(self) -> None:
        # Python `from X import Y` 는 barrel 휴리스틱 대상 아님 (.py 제외).
        py_barrel = self._barrel(
            "__init__.py",
            "from .foo import Foo\nfrom .bar import Bar\n",
        )
        impl = SourceFile(
            path=Path("foo.py"),
            content="class Foo:\n    pass\n" * 100,
            layer="backend", role="other",
            original_chars=2000,
        )
        result = _make_result([py_barrel, impl])
        selected = select_files_for_category(result, "architecture", max_files=10)
        paths = [f.path.as_posix() for f in selected]
        # __init__.py 가 demote 되지 않고 둘 다 primary 에 들어가야 함
        # (실제 demote 발생 시 from-import 패턴까지 barrel 로 잡아 영향 받음)
        assert "__init__.py" in paths

    def test_empty_file_not_treated_as_barrel(self) -> None:
        # 빈 파일은 barrel 아님 — re-export 가 1개도 없으면 False
        empty = self._barrel("index.ts", "")
        impl = self._impl("button.ts")
        result = _make_result([empty, impl])
        selected = select_files_for_category(result, "architecture", max_files=2)
        # 빈 파일은 demote 대상 아니지만 content_rank_key 에서 shallow 로 후순위
        paths = [f.path.as_posix() for f in selected]
        assert "button.ts" in paths

    def test_barrel_demotion_keeps_impl_when_max_files_tight(self) -> None:
        # max_files=1 일 때 — barrel 4개 + impl 1개 중 impl 선택.
        # 회귀 방지: 우리 frontend 케이스의 정확한 시나리오.
        barrels = [
            self._barrel(f"src/{n}/index.ts", "export * from './x'\n")
            for n in ("a", "b", "c", "d")
        ]
        impl = self._impl("src/real.ts")
        result = _make_result(barrels + [impl])
        selected = select_files_for_category(result, "architecture", max_files=1)
        assert [f.path.as_posix() for f in selected] == ["src/real.ts"]
