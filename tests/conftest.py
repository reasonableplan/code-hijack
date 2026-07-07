"""Shared pytest fixtures.

Currently provides `senior_wisdom_with_git` — a session-scoped temporary copy of
the static senior_wisdom fixture, but with a real `.git/` and hand-crafted
history. Tests that exercise archaeology (`fetch_source` with history attached,
prompt rendering of `<history>` blocks, etc.) use this instead of the static
path so the on-disk fixture stays clean.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

_STATIC_FIXTURE = Path(__file__).parent / "fixtures" / "senior_wisdom" / "repo"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _commit_file(repo: Path, rel: str, content: str, message: str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    _git(repo, "add", rel)
    _git(repo, "commit", "-q", "-m", message)


@pytest.fixture(scope="session")
def senior_wisdom_with_git(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Copy senior_wisdom/repo into a tmp dir and bake a real git history into it.

    The history is hand-crafted to surface meaningful archaeology signals:
      - `backend/routes/users.py`: feat → Revert → fix sequence (revert detection)
      - `frontend/App.tsx`: a single initial commit (sparse-history case)
      - other files: shared "scaffold" commit

    Tests assert on the SHA-bearing structure, not the SHAs themselves, since
    the SHA depends on author/timestamp/git version.
    """
    if shutil.which("git") is None:
        pytest.skip("git binary not available")

    dst = tmp_path_factory.mktemp("senior_wisdom_git") / "repo"
    shutil.copytree(_STATIC_FIXTURE, dst)

    # Repo-level rationale docs the doc fetcher should discover.
    (dst / "README.md").write_text(
        "# Senior Wisdom\n\nWe favour dataclasses over pydantic.\n",
        encoding="utf-8",
    )
    (dst / "docs" / "adr").mkdir(parents=True, exist_ok=True)
    (dst / "docs" / "adr" / "0001-drop-pydantic.md").write_text(
        "# ADR 0001 — Drop pydantic from user routes\n\n"
        "Pydantic v2 caused runtime regressions; dataclasses keep the surface\n"
        "area smaller. Decided after the Revert documented in commit history.\n",
        encoding="utf-8",
    )

    _git(dst, "init", "-q", "-b", "main")
    _git(dst, "config", "user.email", "senior@example.com")
    _git(dst, "config", "user.name", "Senior Dev")
    _git(dst, "config", "commit.gpgsign", "false")

    # Round 1: scaffold everything so each file has at least one commit.
    _git(dst, "add", "-A")
    _git(dst, "commit", "-q", "-m", "feat: initial scaffold")

    # Round 2 — backend/routes/users.py gets a churn sequence with a revert.
    target = "backend/routes/users.py"
    original = (dst / target).read_text(encoding="utf-8")

    _commit_file(
        dst,
        target,
        original + "\n# experimental: pydantic-based validation\n",
        "feat: try pydantic validation for user routes",
    )
    _commit_file(
        dst,
        target,
        original + "\n# rolled back: dataclasses are simpler here\n",
        "Revert: drop pydantic from user routes — dataclasses keep the surface area smaller",
    )
    _commit_file(
        dst,
        target,
        original + "\n# stable: dataclass-only\n",
        "fix: settle on dataclass-only validation",
    )

    return dst


@pytest.fixture(autouse=True)
def _block_pr_mining(monkeypatch: pytest.MonkeyPatch) -> None:
    """Block PR mining by default in every test.

    Why: PR mining shells out to `gh`. In CI or unauthenticated dev
    environments, those calls either fail or trigger Python 3.13 reader-thread
    exceptions that surface as PytestUnhandledThreadExceptionWarning. Tests
    that exercise PR mining explicitly use the injectable `gh_runner`
    parameter, mock subprocess directly, or import `fetch_pr_decisions` at
    module scope before this per-test patch applies — none of those need
    this guard.

    analyzer.py's `run_full_analysis` resolves a local clone target to its
    GitHub remote (via `pr_archaeology.resolve_github_target` — harmless local
    `git remote` call, left unmocked) and then calls
    `pr_archaeology.fetch_pr_decisions` (0.3.0, the live pipeline's PR source)
    with the resolved URL.
    """
    from hijack.core.pr_archaeology import PRDecisions as _PRDecisions
    monkeypatch.setattr(
        "hijack.core.pr_archaeology.fetch_pr_decisions",
        lambda *args, **kwargs: _PRDecisions(items_scanned=0, patterns=[], decisions=[]),
    )
