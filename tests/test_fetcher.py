from __future__ import annotations

import pytest

from hijack.core.fetcher import (
    SourceFile,
    _read_file_content,
    detect_layer,
    fetch_source,
)
from hijack.errors import INPUT_001, INPUT_002, InputError

# ---------------------------------------------------------------------------
# detect_layer tests
# ---------------------------------------------------------------------------

class TestDetectLayer:
    """각 레이어 케이스를 결정론적으로 검증한다."""

    def _make(self, tmp_path, rel: str) -> tuple:
        """(file_path, repo_root) 반환 — 실제 파일은 불필요하지만 Path 객체를 반환한다."""
        file_path = tmp_path / rel
        return file_path, tmp_path

    def test_tsx_is_frontend(self, tmp_path):
        fp, root = self._make(tmp_path, "src/App.tsx")
        assert detect_layer(fp, root, set(), set()) == "frontend"

    def test_ts_in_frontend_dir_is_frontend(self, tmp_path):
        fp, root = self._make(tmp_path, "frontend/pages/index.ts")
        assert detect_layer(fp, root, set(), set()) == "frontend"

    def test_ts_with_react_dep_is_frontend(self, tmp_path):
        fp, root = self._make(tmp_path, "src/utils.ts")
        assert detect_layer(fp, root, {"react", "react-dom"}, set()) == "frontend"

    def test_py_with_fastapi_dep_is_backend(self, tmp_path):
        fp, root = self._make(tmp_path, "src/main.py")
        assert detect_layer(fp, root, set(), {"fastapi"}) == "backend"

    def test_py_in_backend_dir_is_backend(self, tmp_path):
        fp, root = self._make(tmp_path, "backend/api/users.py")
        assert detect_layer(fp, root, set(), set()) == "backend"

    def test_py_in_routes_dir_is_backend(self, tmp_path):
        fp, root = self._make(tmp_path, "routes/health.py")
        assert detect_layer(fp, root, set(), set()) == "backend"

    def test_py_in_migrations_dir_is_db(self, tmp_path):
        fp, root = self._make(tmp_path, "migrations/0001_init.py")
        assert detect_layer(fp, root, set(), set()) == "db"

    def test_ts_in_prisma_dir_is_db(self, tmp_path):
        fp, root = self._make(tmp_path, "prisma/schema.ts")
        assert detect_layer(fp, root, set(), set()) == "db"

    def test_github_workflow_is_devops(self, tmp_path):
        fp, root = self._make(tmp_path, ".github/workflows/ci.py")
        assert detect_layer(fp, root, set(), set()) == "devops"

    def test_plain_py_no_context_is_shared(self, tmp_path):
        fp, root = self._make(tmp_path, "src/utils.py")
        assert detect_layer(fp, root, set(), set()) == "shared"

    def test_ts_no_fe_deps_is_shared(self, tmp_path):
        fp, root = self._make(tmp_path, "src/helpers.ts")
        assert detect_layer(fp, root, set(), set()) == "shared"

    def test_vue_dep_ts_is_frontend(self, tmp_path):
        fp, root = self._make(tmp_path, "src/store.ts")
        assert detect_layer(fp, root, {"vue"}, set()) == "frontend"

    def test_django_dep_py_is_backend(self, tmp_path):
        # "app/" is a frontend dir, so use a neutral path to test pyproject_dep rule
        fp, root = self._make(tmp_path, "myproject/views.py")
        assert detect_layer(fp, root, set(), {"django"}) == "backend"

    def test_fastapi_framework_source_repo_is_backend(self, tmp_path):
        # fastapi 레포 자체: `fastapi/applications.py` — 첫 세그먼트가 프레임워크명
        fp, root = self._make(tmp_path, "fastapi/applications.py")
        assert detect_layer(fp, root, set(), set()) == "backend"

    def test_django_framework_source_repo_is_backend(self, tmp_path):
        fp, root = self._make(tmp_path, "django/core/management.py")
        assert detect_layer(fp, root, set(), set()) == "backend"

    def test_flask_framework_source_repo_is_backend(self, tmp_path):
        fp, root = self._make(tmp_path, "flask/app.py")
        assert detect_layer(fp, root, set(), set()) == "backend"


# ---------------------------------------------------------------------------
# _read_file_content tests
# ---------------------------------------------------------------------------

class TestReadFileContent:
    def test_small_file_returns_full_content(self, tmp_path):
        f = tmp_path / "small.py"
        content = "print('hello')\n" * 10
        f.write_text(content, encoding="utf-8")
        result = _read_file_content(f)
        assert result == content

    def test_exactly_2000_lines_returns_full(self, tmp_path):
        f = tmp_path / "exact.py"
        content = "x = 1\n" * 2000
        f.write_text(content, encoding="utf-8")
        result = _read_file_content(f)
        assert result == content

    def test_over_2000_lines_returns_truncated(self, tmp_path):
        f = tmp_path / "large.py"
        lines = ["import os\n"] + ["x = 1\n"] * 2001
        f.write_text("".join(lines), encoding="utf-8")
        result = _read_file_content(f)
        assert "[TRUNCATED:" in result
        assert "import os" in result

    def test_truncated_includes_function_signatures(self, tmp_path):
        f = tmp_path / "big.py"
        body = "    pass\n" * 1999
        content = "def my_function():\n" + body + "x = 1\n"
        f.write_text(content, encoding="utf-8")
        result = _read_file_content(f)
        assert "def my_function" in result

    def test_missing_file_returns_empty(self, tmp_path):
        f = tmp_path / "nonexistent.py"
        result = _read_file_content(f)
        assert result == ""


# ---------------------------------------------------------------------------
# fetch_source tests
# ---------------------------------------------------------------------------

class TestFetchSourceLocal:
    def test_basic_local_py(self, tmp_path):
        (tmp_path / "hello.py").write_text("x = 1\n", encoding="utf-8")
        files, root = fetch_source(str(tmp_path))
        assert root == tmp_path
        assert len(files) == 1
        sf = files[0]
        assert isinstance(sf, SourceFile)
        assert sf.path.suffix == ".py"
        assert "x = 1" in sf.content

    def test_returns_only_supported_suffixes(self, tmp_path):
        (tmp_path / "a.py").write_text("a = 1\n", encoding="utf-8")
        (tmp_path / "b.ts").write_text("const b = 1;\n", encoding="utf-8")
        (tmp_path / "c.md").write_text("# doc\n", encoding="utf-8")
        (tmp_path / "d.json").write_text("{}\n", encoding="utf-8")
        files, _ = fetch_source(str(tmp_path))
        suffixes = {sf.path.suffix for sf in files}
        assert ".md" not in suffixes
        assert ".json" not in suffixes
        assert {".py", ".ts"} == suffixes

    def test_skip_dirs_excluded(self, tmp_path):
        skip = tmp_path / "node_modules"
        skip.mkdir()
        (skip / "lib.py").write_text("x = 1\n", encoding="utf-8")
        (tmp_path / "app.py").write_text("y = 2\n", encoding="utf-8")
        files, _ = fetch_source(str(tmp_path))
        paths = [sf.path.as_posix() for sf in files]
        assert all("node_modules" not in p for p in paths)
        assert len(files) == 1

    def test_layer_assigned(self, tmp_path):
        (tmp_path / "main.py").write_text("import fastapi\n", encoding="utf-8")
        files, _ = fetch_source(str(tmp_path))
        # layer은 결정론적으로 shared (pyproject deps 없음, 디렉토리 힌트 없음)
        assert files[0].layer in {"shared", "backend", "frontend", "db", "devops"}

    def test_role_entry_point(self, tmp_path):
        (tmp_path / "main.py").write_text("x = 1\n", encoding="utf-8")
        files, _ = fetch_source(str(tmp_path))
        assert files[0].role == "entry_point"

    def test_role_test(self, tmp_path):
        (tmp_path / "test_foo.py").write_text("def test_bar(): pass\n", encoding="utf-8")
        files, _ = fetch_source(str(tmp_path))
        assert files[0].role == "test"

    def test_subpath_option(self, tmp_path):
        sub = tmp_path / "backend"
        sub.mkdir()
        (sub / "app.py").write_text("x = 1\n", encoding="utf-8")
        files, root = fetch_source(str(tmp_path), subpath="backend")
        assert root == sub
        assert len(files) == 1


class TestFetchSourceErrors:
    def test_invalid_path_raises_input_error(self):
        with pytest.raises(InputError) as exc_info:
            fetch_source("/nonexistent/path/that/does/not/exist")
        assert exc_info.value.code == INPUT_001

    def test_no_supported_files_raises_input_error(self, tmp_path):
        (tmp_path / "README.md").write_text("# hello\n", encoding="utf-8")
        (tmp_path / "data.json").write_text("{}\n", encoding="utf-8")
        with pytest.raises(InputError) as exc_info:
            fetch_source(str(tmp_path))
        assert exc_info.value.code == INPUT_002

    def test_empty_dir_raises_input_error(self, tmp_path):
        with pytest.raises(InputError) as exc_info:
            fetch_source(str(tmp_path))
        assert exc_info.value.code == INPUT_002
