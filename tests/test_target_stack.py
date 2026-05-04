from __future__ import annotations

import json
from pathlib import Path

import pytest

from hijack.core.target_stack import detect_target_stack

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_pyproject(
    path: Path, deps: list[str], optional: dict[str, list[str]] | None = None
) -> None:
    sections = ["[project]", 'name = "test"', 'version = "0.1.0"']
    if deps:
        dep_lines = ", ".join(f'"{d}"' for d in deps)
        sections.append(f"dependencies = [{dep_lines}]")
    if optional:
        sections.append("")
        sections.append("[project.optional-dependencies]")
        for extra, extra_deps in optional.items():
            extra_lines = ", ".join(f'"{d}"' for d in extra_deps)
            sections.append(f'{extra} = [{extra_lines}]')
    (path / "pyproject.toml").write_text("\n".join(sections), encoding="utf-8")


def _write_package_json(
    path: Path, deps: dict[str, str], dev_deps: dict[str, str] | None = None
) -> None:
    data: dict = {"name": "test", "version": "0.1.0", "dependencies": deps}
    if dev_deps is not None:
        data["devDependencies"] = dev_deps
    (path / "package.json").write_text(json.dumps(data), encoding="utf-8")


# ---------------------------------------------------------------------------
# pyproject.toml tests
# ---------------------------------------------------------------------------

class TestPyprojectParsing:
    def test_pyproject_only_populates_python_deps(self, tmp_path: Path) -> None:
        _write_pyproject(tmp_path, ["fastapi>=0.100", "pydantic"])
        stack = detect_target_stack(tmp_path)
        assert "fastapi" in stack.python_deps
        assert "pydantic" in stack.python_deps
        assert stack.js_deps == frozenset()
        assert stack.detected_files == ["pyproject.toml"]

    def test_strips_version_specifiers(self, tmp_path: Path) -> None:
        _write_pyproject(tmp_path, ["fastapi>=0.100,<1.0", "sqlalchemy==2.0.0"])
        stack = detect_target_stack(tmp_path)
        assert "fastapi" in stack.python_deps
        assert "sqlalchemy" in stack.python_deps
        # No version suffix in the stored name
        for dep in stack.python_deps:
            assert ">" not in dep
            assert "<" not in dep
            assert "=" not in dep

    def test_strips_extras_from_package_name(self, tmp_path: Path) -> None:
        _write_pyproject(tmp_path, ["pydantic[email]", "fastapi[standard]"])
        stack = detect_target_stack(tmp_path)
        assert "pydantic" in stack.python_deps
        assert "fastapi" in stack.python_deps
        # Extras should NOT appear in stored name
        for dep in stack.python_deps:
            assert "[" not in dep

    def test_optional_dependencies_included(self, tmp_path: Path) -> None:
        _write_pyproject(
            tmp_path,
            ["fastapi"],
            optional={"dev": ["pytest>=7", "ruff"], "docs": ["mkdocs"]},
        )
        stack = detect_target_stack(tmp_path)
        assert "fastapi" in stack.python_deps
        assert "pytest" in stack.python_deps
        assert "ruff" in stack.python_deps
        assert "mkdocs" in stack.python_deps

    def test_underscore_normalized_to_hyphen(self, tmp_path: Path) -> None:
        _write_pyproject(tmp_path, ["some_package"])
        stack = detect_target_stack(tmp_path)
        assert "some-package" in stack.python_deps

    def test_malformed_pyproject_logged_and_skipped(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        (tmp_path / "pyproject.toml").write_text("NOT VALID TOML }{{{", encoding="utf-8")
        import logging
        with caplog.at_level(logging.WARNING, logger="hijack.core.target_stack"):
            stack = detect_target_stack(tmp_path)
        assert stack.python_deps == frozenset()
        assert stack.detected_files == []
        # Warning was logged
        assert any("pyproject" in r.message.lower() or "failed" in r.message.lower()
                   for r in caplog.records)


# ---------------------------------------------------------------------------
# package.json tests
# ---------------------------------------------------------------------------

class TestPackageJsonParsing:
    def test_package_json_only_populates_js_deps(self, tmp_path: Path) -> None:
        _write_package_json(tmp_path, {"react": "^18.0.0", "axios": "^1.0.0"})
        stack = detect_target_stack(tmp_path)
        assert "react" in stack.js_deps
        assert "axios" in stack.js_deps
        assert stack.python_deps == frozenset()
        assert "package.json" in stack.detected_files

    def test_dev_dependencies_included(self, tmp_path: Path) -> None:
        _write_package_json(
            tmp_path,
            {"react": "^18"},
            dev_deps={"typescript": "^5", "vitest": "^1"},
        )
        stack = detect_target_stack(tmp_path)
        assert "react" in stack.js_deps
        assert "typescript" in stack.js_deps
        assert "vitest" in stack.js_deps

    def test_malformed_package_json_logged_and_skipped(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        (tmp_path / "package.json").write_text("{not valid json", encoding="utf-8")
        import logging
        with caplog.at_level(logging.WARNING, logger="hijack.core.target_stack"):
            stack = detect_target_stack(tmp_path)
        assert stack.js_deps == frozenset()
        assert "package.json" not in stack.detected_files
        assert any("package" in r.message.lower() or "failed" in r.message.lower()
                   for r in caplog.records)


# ---------------------------------------------------------------------------
# Combined + edge cases
# ---------------------------------------------------------------------------

class TestBothManifests:
    def test_both_manifests_union_deps(self, tmp_path: Path) -> None:
        _write_pyproject(tmp_path, ["fastapi"])
        _write_package_json(tmp_path, {"react": "^18"})
        stack = detect_target_stack(tmp_path)
        assert "fastapi" in stack.python_deps
        assert "react" in stack.js_deps
        assert "fastapi" in stack.all_deps
        assert "react" in stack.all_deps
        assert set(stack.detected_files) == {"pyproject.toml", "package.json"}

    def test_malformed_pyproject_still_parses_package_json(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "pyproject.toml").write_text("NOT VALID }{", encoding="utf-8")
        _write_package_json(tmp_path, {"react": "^18"})
        stack = detect_target_stack(tmp_path)
        # pyproject failed, package.json succeeded
        assert stack.python_deps == frozenset()
        assert "react" in stack.js_deps
        assert stack.detected_files == ["package.json"]

    def test_no_manifests_empty_stack(self, tmp_path: Path) -> None:
        stack = detect_target_stack(tmp_path)
        assert stack.is_empty
        assert stack.python_deps == frozenset()
        assert stack.js_deps == frozenset()
        assert stack.detected_files == []
        assert stack.all_deps == frozenset()

    def test_is_empty_false_when_has_deps(self, tmp_path: Path) -> None:
        _write_pyproject(tmp_path, ["fastapi"])
        stack = detect_target_stack(tmp_path)
        assert not stack.is_empty

    def test_repo_root_stored(self, tmp_path: Path) -> None:
        stack = detect_target_stack(tmp_path)
        assert stack.repo_root == tmp_path
