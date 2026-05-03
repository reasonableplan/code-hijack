"""Integration tests for hijack.io.git — exercises real git subprocess.

Each test builds a throwaway git repo in tmp_path so behaviour is deterministic
without depending on the developer's working directory.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from hijack.io.git import (
    get_file_archaeology,
    get_file_history,
    get_reverts_touching,
    is_git_repo,
)

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None,
    reason="git binary not available",
)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "commit.gpgsign", "false")


def _commit(repo: Path, rel: str, content: str, message: str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    _git(repo, "add", rel)
    _git(repo, "commit", "-q", "-m", message)


class TestIsGitRepo:
    def test_true_inside_repo(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        _commit(tmp_path, "a.py", "x = 1\n", "init")
        assert is_git_repo(tmp_path) is True

    def test_false_outside_repo(self, tmp_path: Path) -> None:
        # tmp_path with no .git
        assert is_git_repo(tmp_path) is False


class TestGetFileHistory:
    def test_returns_commits_newest_first(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        _commit(tmp_path, "a.py", "v1\n", "first")
        _commit(tmp_path, "a.py", "v2\n", "second")
        _commit(tmp_path, "a.py", "v3\n", "third")

        commits = get_file_history(tmp_path, tmp_path / "a.py", depth=5)
        subjects = [c.subject for c in commits]
        # `git log` default is newest-first.
        assert subjects == ["third", "second", "first"]

    def test_respects_depth(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        for i in range(5):
            _commit(tmp_path, "a.py", f"v{i}\n", f"c{i}")

        commits = get_file_history(tmp_path, tmp_path / "a.py", depth=2)
        assert len(commits) == 2

    def test_path_outside_repo_returns_empty(self, tmp_path: Path, monkeypatch) -> None:
        _init_repo(tmp_path)
        _commit(tmp_path, "a.py", "x", "c")

        # A path that is not under repo_root.
        outside = tmp_path.parent
        commits = get_file_history(tmp_path, outside / "elsewhere.py", depth=3)
        assert commits == []

    def test_nonexistent_path_returns_empty(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        _commit(tmp_path, "a.py", "x", "c")

        commits = get_file_history(tmp_path, tmp_path / "missing.py", depth=3)
        # `git log -- missing.py` exits 0 with empty stdout — parser gives [].
        assert commits == []


class TestGetRevertsTouching:
    def test_finds_revert_commits(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        _commit(tmp_path, "a.py", "use pydantic\n", "feat: add pydantic")
        _commit(tmp_path, "a.py", "use dataclass\n", "Revert: drop pydantic — too heavy")

        reverts = get_reverts_touching(tmp_path, tmp_path / "a.py")
        assert len(reverts) == 1
        assert "drop pydantic" in reverts[0].subject

    def test_no_reverts_returns_empty(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        _commit(tmp_path, "a.py", "x", "feat: clean addition")
        assert get_reverts_touching(tmp_path, tmp_path / "a.py") == []


class TestGetFileArchaeology:
    def test_combines_history_and_reverts(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        _commit(tmp_path, "a.py", "v1", "feat: initial")
        _commit(tmp_path, "a.py", "v2", "Revert: rollback initial")
        _commit(tmp_path, "a.py", "v3", "fix: settle on v3")

        h = get_file_archaeology(tmp_path, tmp_path / "a.py", depth=5)
        assert len(h.commits) == 3
        assert len(h.reverts) == 1
        assert "rollback" in h.reverts[0].subject
