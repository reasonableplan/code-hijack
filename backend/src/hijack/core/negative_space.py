"""Negative-space signal extractor — deterministic, stdlib-only.

Extracts 4 kinds of intentional-restraint signals from a Python repo:
  (a) dependency frugality  — runtime dep count + stdlib-only impl files
  (b) public API surface    — underscore-prefix ratio + __all__ discipline
  (c) deprecation trails    — DeprecationWarning occurrences in source files
  (d) boundary discipline   — cross-layer import direction violations

Pure/I-O split (same pattern as archaeology.py):
  - All AST/path/ratio analysis functions: pure (no I/O, testable from fixtures).
  - git history reading: `read_deprecation_history` (I/O, separate function,
    graceful skip when git is absent).

Consumers pass `py_files` already collected by the fetcher; no filesystem
discovery happens here. The caller (skill/cli, T-035) merges the output of
`read_deprecation_history` into `deprecation_patterns` before handing
`NegativeSpaceResult` to the LLM.
"""

from __future__ import annotations

import ast
import logging
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# stdlib module names — used to determine whether a file is "stdlib-only".
# Populated once at import time from sys.stdlib_module_names (Python 3.10+)
# with a small fallback set for older runtimes.
_STDLIB_MODULES: frozenset[str] = getattr(
    sys, "stdlib_module_names",
    frozenset({
        "abc", "ast", "asyncio", "builtins", "collections", "contextlib",
        "copy", "dataclasses", "datetime", "enum", "functools", "hashlib",
        "http", "io", "itertools", "json", "logging", "math", "operator",
        "os", "pathlib", "pickle", "queue", "re", "shutil", "signal",
        "socket", "sqlite3", "string", "struct", "subprocess", "sys",
        "tempfile", "threading", "time", "traceback", "types", "typing",
        "unittest", "urllib", "uuid", "warnings", "weakref",
    }),
)

_DEPRECATION_RE = re.compile(r"DeprecationWarning", re.MULTILINE)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class NegativeSpaceResult:
    dep_count: int                    # runtime dependency count
    direct_impl_hints: list[str]      # stdlib-only import files (repo-rel paths)
    public_ratio: float               # fraction of top-level symbols without _ prefix
    has_all_discipline: bool          # any module defines __all__
    deprecation_patterns: list[str]   # DeprecationWarning occurrence summaries
    layer_import_violations: list[str]  # cross-layer import descriptions


# ---------------------------------------------------------------------------
# Pure helper functions
# ---------------------------------------------------------------------------

def _calc_dep_count(pyproject_toml: dict | None) -> int:
    """Return length of [project.dependencies] array, or 0 if absent/None."""
    if pyproject_toml is None:
        return 0
    deps = pyproject_toml.get("project", {}).get("dependencies", None)
    if deps is None:
        return 0
    return len(deps)


def _read_path(path: Path, repo_root: Path | None) -> Path:
    """Resolve a repo-relative path against repo_root for file reads.

    SourceFile.path is relative to the repo root, which differs from cwd for
    cloned/cached repos. Absolute paths pass through unchanged.
    """
    if repo_root is None or path.is_absolute():
        return path
    return repo_root / path


def _find_direct_impls(
    py_files: list[Path], repo_root: Path | None = None
) -> list[str]:
    """Return paths of files that import *only* stdlib modules (no third-party).

    A file with zero import statements is skipped (no signal).
    Files that fail to parse are silently skipped.
    """
    hints: list[str] = []
    for path in py_files:
        try:
            source = _read_path(path, repo_root).read_text(
                encoding="utf-8", errors="replace"
            )
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            continue

        imported: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported.append(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module.split(".")[0])

        if not imported:
            continue

        if all(mod in _STDLIB_MODULES for mod in imported):
            hints.append(path.as_posix())

    return hints


def _calc_public_ratio(
    py_files: list[Path], repo_root: Path | None = None
) -> tuple[float, bool]:
    """Return (public_ratio, has_all_discipline) across all py_files.

    public_ratio: fraction of top-level function/class/async-function defs
        whose name does NOT start with `_`.
    has_all_discipline: True if at least one module defines __all__.

    Files that fail to parse are skipped. Returns (0.0, False) when no
    symbols are found.
    """
    total = 0
    public = 0
    has_all = False

    for path in py_files:
        try:
            source = _read_path(path, repo_root).read_text(
                encoding="utf-8", errors="replace"
            )
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            continue

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                total += 1
                if not node.name.startswith("_"):
                    public += 1
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "__all__":
                        has_all = True

    if total == 0:
        return 0.0, has_all
    return public / total, has_all


def _scan_deprecation_patterns(
    py_files: list[Path], repo_root: Path | None = None
) -> list[str]:
    """Return summary strings for files containing DeprecationWarning references.

    Pure — reads file content directly (no subprocess, no git).
    Each entry: "<path>: <count> occurrence(s)".
    """
    patterns: list[str] = []
    for path in py_files:
        try:
            source = _read_path(path, repo_root).read_text(
                encoding="utf-8", errors="replace"
            )
        except OSError:
            continue
        matches = _DEPRECATION_RE.findall(source)
        if matches:
            patterns.append(f"{path.as_posix()}: {len(matches)} occurrence(s)")
    return patterns


def _find_layer_violations(
    py_files: list[Path],
    layer_map: dict[Path, str],
    repo_root: Path | None = None,
) -> list[str]:
    """Detect cross-layer imports that violate expected direction.

    Expected direction: higher layers import from lower layers.
    A "violation" is when a lower-layer file imports from a higher-layer module
    (e.g. db→backend, backend→frontend).

    Uses AST import analysis + directory name heuristics to resolve import
    targets to layers. `shared` layer is neutral — imports to/from it are OK.

    Returns a list of human-readable violation descriptions.
    """
    # Build a lookup: directory stem → layer, so we can guess the layer of an
    # imported module by matching its top-level package name against known dirs.
    dir_to_layer: dict[str, str] = {}
    for path, layer in layer_map.items():
        if layer != "shared":
            # Use the first path component as the "package root" for the layer.
            parts = path.parts
            if len(parts) == 0:
                continue
            if len(parts) >= 2:
                dir_to_layer[parts[-2]] = layer   # parent dir name
            dir_to_layer[parts[-1].removesuffix(".py")] = layer  # stem

    violations: list[str] = []

    for path in py_files:
        src_layer = layer_map.get(path, "shared")
        if src_layer == "shared":
            continue

        try:
            source = _read_path(path, repo_root).read_text(
                encoding="utf-8", errors="replace"
            )
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.Import):
                    modules = [alias.name.split(".")[0] for alias in node.names]
                else:
                    module = node.module or ""
                    modules = [module.split(".")[0]] if module else []

                for mod in modules:
                    tgt_layer = dir_to_layer.get(mod)
                    if tgt_layer is None or tgt_layer == "shared":
                        continue
                    if tgt_layer == src_layer:
                        continue
                    # Any cross-layer import (between two distinct non-shared layers)
                    # is a boundary discipline signal worth flagging.
                    violations.append(
                        f"{path.as_posix()} ({src_layer}) imports "
                        f"'{mod}' ({tgt_layer})"
                    )

    return violations


# ---------------------------------------------------------------------------
# Top-level pure function
# ---------------------------------------------------------------------------

def extract_negative_space(
    repo_root: Path,
    py_files: list[Path],
    pyproject_toml: dict | None,
    layer_map: dict[Path, str],
) -> NegativeSpaceResult:
    """Extract negative-space signals from a Python repo.

    Pure — no I/O beyond reading file content already present on disk via
    `py_files`. Git history reading is handled separately by
    `read_deprecation_history`.
    """
    dep_count = _calc_dep_count(pyproject_toml)
    direct_impl_hints = _find_direct_impls(py_files, repo_root)
    public_ratio, has_all_discipline = _calc_public_ratio(py_files, repo_root)
    deprecation_patterns = _scan_deprecation_patterns(py_files, repo_root)
    layer_import_violations = _find_layer_violations(py_files, layer_map, repo_root)

    return NegativeSpaceResult(
        dep_count=dep_count,
        direct_impl_hints=direct_impl_hints,
        public_ratio=public_ratio,
        has_all_discipline=has_all_discipline,
        deprecation_patterns=deprecation_patterns,
        layer_import_violations=layer_import_violations,
    )


# ---------------------------------------------------------------------------
# I/O function — git history
# ---------------------------------------------------------------------------

def read_deprecation_history(repo_root: Path) -> list[str]:
    """Mine DeprecationWarning additions/removals from git log.

    I/O function — invokes `git log` via subprocess. Returns [] + logs a
    warning when git is absent or the path is not a git repo (graceful skip).

    Caller merges the returned list into NegativeSpaceResult.deprecation_patterns
    before handing the result to the LLM.
    """
    try:
        result = subprocess.run(
            [
                "git", "log",
                "--all",
                "--diff-filter=A",   # commits that Added lines matching pattern
                "-S", "DeprecationWarning",
                "--oneline",
                "--no-walk",
            ],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except FileNotFoundError:
        logger.warning("git not found — skipping deprecation history")
        return []
    except subprocess.TimeoutExpired:
        logger.warning("git log timed out — skipping deprecation history")
        return []

    if result.returncode != 0:
        logger.warning(
            "git log failed (rc=%d) — skipping deprecation history", result.returncode
        )
        return []

    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return lines
