"""Subprocess wrappers around `git log` for archaeology.

Impure boundary: every function here invokes `git` via subprocess and returns the
parsed result from `core.archaeology`. Failure is non-fatal — git history is
optional context, so any error degrades to an empty result rather than raising.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from hijack.core.archaeology import (
    GIT_LOG_FORMAT,
    Commit,
    FileHistory,
    parse_git_log,
)

_log = logging.getLogger(__name__)

# Cap the subprocess wall time per call. `git log` on a single file is normally
# instant; this guards against pathological repos / network-stalled fetches when
# `--filter=blob:none` triggers a lazy blob download.
_GIT_TIMEOUT_SECONDS = 30


def _run_git_log(repo_root: Path, args: list[str]) -> str:
    """Invoke `git -C <root> log <args>`. Returns stdout, "" on failure."""
    cmd = ["git", "-C", str(repo_root), "log", *args]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_GIT_TIMEOUT_SECONDS,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        _log.debug("git log failed: %s", e)
        return ""

    if result.returncode != 0:
        _log.debug("git log non-zero exit: %s", result.stderr.strip())
        return ""
    return result.stdout


def get_file_history(
    repo_root: Path,
    file_path: Path,
    *,
    depth: int = 3,
) -> list[Commit]:
    """Last `depth` commits touching `file_path`, newest first.

    `--follow` traces across renames so a recently renamed file still surfaces
    its earlier history.
    """
    try:
        rel = file_path.relative_to(repo_root).as_posix()
    except ValueError:
        return []

    stdout = _run_git_log(
        repo_root,
        [
            "--follow",
            f"-n{depth}",
            f"--format={GIT_LOG_FORMAT}",
            "--",
            rel,
        ],
    )
    return parse_git_log(stdout)


def get_reverts_touching(repo_root: Path, file_path: Path) -> list[Commit]:
    """Commits whose subject indicates an intentional rollback of `file_path`.

    A revert in a file's history is strong negative evidence — the senior tried
    a pattern, then explicitly backed it out. The pattern is broadened beyond
    git's own `Revert "..."` subjects to catch the conventions teams use in
    practice: `rollback:`, `back out`, `back-out`, `undo:`. Anchored to the
    start of the subject (with `^`) to avoid matching the words mid-sentence.
    """
    try:
        rel = file_path.relative_to(repo_root).as_posix()
    except ValueError:
        return []

    stdout = _run_git_log(
        repo_root,
        [
            "--follow",
            "--extended-regexp",
            "--regexp-ignore-case",
            "--grep=^(revert|rollback|back[ -]out|undo)",
            f"--format={GIT_LOG_FORMAT}",
            "--",
            rel,
        ],
    )
    return parse_git_log(stdout)


def get_file_archaeology(
    repo_root: Path,
    file_path: Path,
    *,
    depth: int = 3,
) -> FileHistory:
    """Convenience: combine recent commits + reverts into a FileHistory."""
    commits = get_file_history(repo_root, file_path, depth=depth)
    reverts = get_reverts_touching(repo_root, file_path)
    return FileHistory(commits=commits, reverts=reverts)


def is_git_repo(repo_root: Path) -> bool:
    """Whether `repo_root` is inside a git work tree.

    Used by fetcher to decide whether archaeology is worth attempting at all.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and result.stdout.strip() == "true"
