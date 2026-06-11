"""Tests for negative_space.py — deterministic signal extraction."""

from __future__ import annotations

from pathlib import Path

import pytest

from hijack.core.negative_space import (
    NegativeSpaceResult,
    _calc_dep_count,
    _calc_public_ratio,
    _find_direct_impls,
    _find_layer_violations,
    _scan_deprecation_patterns,
    extract_negative_space,
    read_deprecation_history,
)

# ---------------------------------------------------------------------------
# _calc_dep_count
# ---------------------------------------------------------------------------

class TestCalcDepCount:
    def test_none_pyproject_returns_zero(self) -> None:
        assert _calc_dep_count(None) == 0

    def test_empty_dependencies(self) -> None:
        assert _calc_dep_count({"project": {"dependencies": []}}) == 0

    def test_counts_dependencies(self) -> None:
        toml = {"project": {"dependencies": ["httpx>=0.24", "click", "anthropic"]}}
        assert _calc_dep_count(toml) == 3

    def test_missing_project_key_returns_zero(self) -> None:
        assert _calc_dep_count({"tool": {"ruff": {}}}) == 0

    def test_missing_dependencies_key_returns_zero(self) -> None:
        assert _calc_dep_count({"project": {"name": "foo"}}) == 0


# ---------------------------------------------------------------------------
# _find_direct_impls
# ---------------------------------------------------------------------------

class TestFindDirectImpls:
    def test_stdlib_only_file_detected(self, tmp_path: Path) -> None:
        f = tmp_path / "pure.py"
        f.write_text("import os\nimport re\nimport pathlib\n")
        result = _find_direct_impls([f])
        assert len(result) == 1
        assert "pure.py" in result[0]

    def test_third_party_import_not_detected(self, tmp_path: Path) -> None:
        f = tmp_path / "lib.py"
        f.write_text("import httpx\nimport click\n")
        result = _find_direct_impls([f])
        assert result == []

    def test_mixed_imports_not_detected(self, tmp_path: Path) -> None:
        # stdlib + third-party → not stdlib-only
        f = tmp_path / "mixed.py"
        f.write_text("import os\nimport httpx\n")
        result = _find_direct_impls([f])
        assert result == []

    def test_empty_file_not_detected(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.py"
        f.write_text("")
        result = _find_direct_impls([f])
        assert result == []

    def test_multiple_stdlib_only_files(self, tmp_path: Path) -> None:
        f1 = tmp_path / "a.py"
        f1.write_text("import os\nimport sys\n")
        f2 = tmp_path / "b.py"
        f2.write_text("import re\nimport collections\n")
        result = _find_direct_impls([f1, f2])
        assert len(result) == 2


# ---------------------------------------------------------------------------
# _calc_public_ratio
# ---------------------------------------------------------------------------

class TestCalcPublicRatio:
    def test_all_public_symbols(self, tmp_path: Path) -> None:
        f = tmp_path / "mod.py"
        f.write_text("def foo(): pass\ndef bar(): pass\n")
        ratio, has_all = _calc_public_ratio([f])
        assert ratio == 1.0
        assert has_all is False

    def test_all_private_symbols(self, tmp_path: Path) -> None:
        f = tmp_path / "mod.py"
        f.write_text("def _foo(): pass\ndef _bar(): pass\n")
        ratio, has_all = _calc_public_ratio([f])
        assert ratio == 0.0
        assert has_all is False

    def test_mixed_symbols(self, tmp_path: Path) -> None:
        f = tmp_path / "mod.py"
        f.write_text("def pub(): pass\ndef _priv(): pass\n")
        ratio, has_all = _calc_public_ratio([f])
        assert ratio == pytest.approx(0.5)

    def test_all_export_detected(self, tmp_path: Path) -> None:
        f = tmp_path / "mod.py"
        f.write_text('__all__ = ["foo"]\ndef foo(): pass\n')
        _, has_all = _calc_public_ratio([f])
        assert has_all is True

    def test_no_symbols_returns_zero(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.py"
        f.write_text("# comment only\n")
        ratio, has_all = _calc_public_ratio([f])
        assert ratio == 0.0
        assert has_all is False


# ---------------------------------------------------------------------------
# _scan_deprecation_patterns
# ---------------------------------------------------------------------------

class TestScanDeprecationPatterns:
    def test_deprecation_warning_detected(self, tmp_path: Path) -> None:
        f = tmp_path / "legacy.py"
        f.write_text('import warnings\nwarnings.warn("old", DeprecationWarning)\n')
        result = _scan_deprecation_patterns([f])
        assert len(result) >= 1
        assert any("legacy.py" in r for r in result)

    def test_no_deprecation_returns_empty(self, tmp_path: Path) -> None:
        f = tmp_path / "clean.py"
        f.write_text("def foo(): pass\n")
        result = _scan_deprecation_patterns([f])
        assert result == []

    def test_multiple_files(self, tmp_path: Path) -> None:
        f1 = tmp_path / "old.py"
        f1.write_text("warnings.warn('v1', DeprecationWarning)\n")
        f2 = tmp_path / "new.py"
        f2.write_text("def fresh(): pass\n")
        result = _scan_deprecation_patterns([f1, f2])
        assert len(result) == 1


# ---------------------------------------------------------------------------
# _find_layer_violations
# ---------------------------------------------------------------------------

class TestFindLayerViolations:
    def test_no_violations_when_same_layer(self, tmp_path: Path) -> None:
        f = tmp_path / "backend" / "service.py"
        f.parent.mkdir()
        f.write_text("from backend.models import User\n")
        layer_map = {f: "backend"}
        result = _find_layer_violations([f], layer_map)
        assert result == []

    def test_frontend_importing_backend_detected(self, tmp_path: Path) -> None:
        # frontend file importing a backend module
        fe_dir = tmp_path / "frontend"
        fe_dir.mkdir()
        fe_file = fe_dir / "component.py"
        fe_file.write_text("from backend.service import process\n")

        be_dir = tmp_path / "backend"
        be_dir.mkdir()
        be_file = be_dir / "service.py"
        be_file.write_text("def process(): pass\n")

        layer_map = {fe_file: "frontend", be_file: "backend"}
        result = _find_layer_violations([fe_file, be_file], layer_map)
        # frontend→backend is a cross-layer import — should be flagged
        assert len(result) >= 1

    def test_db_importing_backend_detected(self, tmp_path: Path) -> None:
        # db layer importing backend is a violation
        db_dir = tmp_path / "db"
        db_dir.mkdir()
        db_file = db_dir / "schema.py"
        db_file.write_text("from backend.service import something\n")

        be_dir = tmp_path / "backend"
        be_dir.mkdir()
        be_file = be_dir / "service.py"
        be_file.write_text("def something(): pass\n")

        layer_map = {db_file: "db", be_file: "backend"}
        result = _find_layer_violations([db_file, be_file], layer_map)
        assert len(result) >= 1


# ---------------------------------------------------------------------------
# extract_negative_space — integration
# ---------------------------------------------------------------------------

class TestExtractNegativeSpace:
    def test_result_type(self, tmp_path: Path) -> None:
        f = tmp_path / "mod.py"
        f.write_text("def foo(): pass\n")
        result = extract_negative_space(tmp_path, [f], None, {f: "shared"})
        assert isinstance(result, NegativeSpaceResult)

    def test_all_fields_present(self, tmp_path: Path) -> None:
        f = tmp_path / "mod.py"
        f.write_text("def pub(): pass\ndef _priv(): pass\n")
        result = extract_negative_space(tmp_path, [f], None, {f: "shared"})
        # All fields should be populated (values may be zero/empty but not missing)
        assert isinstance(result.dep_count, int)
        assert isinstance(result.direct_impl_hints, list)
        assert isinstance(result.public_ratio, float)
        assert isinstance(result.has_all_discipline, bool)
        assert isinstance(result.deprecation_patterns, list)
        assert isinstance(result.layer_import_violations, list)

    def test_dep_count_from_pyproject(self, tmp_path: Path) -> None:
        f = tmp_path / "mod.py"
        f.write_text("def foo(): pass\n")
        pyproject = {"project": {"dependencies": ["click", "httpx"]}}
        result = extract_negative_space(tmp_path, [f], pyproject, {f: "shared"})
        assert result.dep_count == 2

    def test_senior_wisdom_fixture(self) -> None:
        """Integration test: NegativeSpaceResult fills all fields on real fixture."""
        fixture_root = (
            Path(__file__).parent / "fixtures" / "senior_wisdom" / "repo"
        )
        py_files = list(fixture_root.rglob("*.py"))
        assert py_files, "fixture .py files must exist"

        # Build a simple layer_map from path heuristics
        layer_map: dict[Path, str] = {}
        for f in py_files:
            rel = f.relative_to(fixture_root).as_posix()
            if "frontend" in rel:
                layer_map[f] = "frontend"
            elif "migrations" in rel:
                layer_map[f] = "db"
            elif "backend" in rel:
                layer_map[f] = "backend"
            else:
                layer_map[f] = "shared"

        result = extract_negative_space(fixture_root, py_files, None, layer_map)

        assert isinstance(result, NegativeSpaceResult)
        assert isinstance(result.dep_count, int)
        assert isinstance(result.public_ratio, float)
        assert 0.0 <= result.public_ratio <= 1.0
        assert isinstance(result.has_all_discipline, bool)
        assert isinstance(result.direct_impl_hints, list)
        assert isinstance(result.deprecation_patterns, list)
        assert isinstance(result.layer_import_violations, list)


# ---------------------------------------------------------------------------
# read_deprecation_history — I/O function
# ---------------------------------------------------------------------------

class TestReadDeprecationHistory:
    def test_non_git_repo_returns_empty_list(self, tmp_path: Path) -> None:
        """Non-git directory must return [] without raising."""
        result = read_deprecation_history(tmp_path)
        assert result == []

    def test_returns_list_type(self, tmp_path: Path) -> None:
        result = read_deprecation_history(tmp_path)
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Relative-path resolution (regression: cloned repos pass repo-relative paths)
# ---------------------------------------------------------------------------

class TestRelativePathResolution:
    def test_extract_resolves_relative_paths_against_repo_root(
        self, tmp_path: Path
    ) -> None:
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "mod.py").write_text("import json\n", encoding="utf-8")
        rel = Path("pkg/mod.py")

        result = extract_negative_space(tmp_path, [rel], None, {rel: "backend"})

        assert "pkg/mod.py" in result.direct_impl_hints
