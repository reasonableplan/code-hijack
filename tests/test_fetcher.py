"""Tests for fetcher module."""

import tempfile
from pathlib import Path

from hijack.core.fetcher import SourceFile, build_structure_map, collect_files


def test_collect_files_python(tmp_path: Path):
    (tmp_path / "main.py").write_text("print('hello')")
    (tmp_path / "utils.py").write_text("def helper(): pass")
    (tmp_path / "readme.md").write_text("# Readme")  # should be skipped

    files = collect_files(tmp_path)
    assert len(files) == 2
    assert all(f.language == "python" for f in files)


def test_collect_files_typescript(tmp_path: Path):
    (tmp_path / "index.ts").write_text("const x = 1;")
    (tmp_path / "app.tsx").write_text("export default App;")

    files = collect_files(tmp_path)
    assert len(files) == 2
    assert all(f.language == "typescript" for f in files)


def test_collect_files_config(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'")
    (tmp_path / "package.json").write_text('{"name": "test"}')

    files = collect_files(tmp_path)
    assert len(files) == 2
    assert all(f.language == "config" for f in files)


def test_skip_dirs(tmp_path: Path):
    venv = tmp_path / ".venv"
    venv.mkdir()
    (venv / "lib.py").write_text("# should be skipped")

    (tmp_path / "main.py").write_text("# should be collected")

    files = collect_files(tmp_path)
    assert len(files) == 1
    assert files[0].path == Path("main.py")


def test_build_structure_map(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_main.py").write_text("")

    result = build_structure_map(tmp_path)
    assert "src/" in result
    assert "tests/" in result
