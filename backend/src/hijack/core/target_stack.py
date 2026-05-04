from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

try:
    import tomllib
except ImportError:
    import tomllib  # type: ignore[no-redef]

logger = logging.getLogger(__name__)


@dataclass
class TargetStack:
    """Dependency snapshot of a target repo."""

    repo_root: Path
    python_deps: frozenset[str] = field(default_factory=frozenset)
    js_deps: frozenset[str] = field(default_factory=frozenset)
    detected_files: list[str] = field(default_factory=list)  # relative paths

    @property
    def all_deps(self) -> frozenset[str]:
        return self.python_deps | self.js_deps

    @property
    def is_empty(self) -> bool:
        return not self.all_deps


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _normalize_pkg_name(raw: str) -> str:
    """PEP 503 normalization: lowercase + replace _ with -.

    Also strips version specifiers, extras, and environment markers:
      "fastapi>=0.100,<1.0" → "fastapi"
      "pydantic[email]"     → "pydantic"
    """
    # Strip at the first version specifier, extra marker, env marker, or space
    name = re.split(r"[><=!\[;@ ]", raw)[0]
    return name.lower().replace("_", "-").strip()


def _parse_pyproject_deps(pyproject_path: Path) -> frozenset[str] | None:
    """Parse [project].dependencies + [project.optional-dependencies].

    Returns frozenset of normalized package names, or None on parse failure.
    """
    try:
        data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("target_stack: failed to parse %s: %s", pyproject_path, exc)
        return None

    raw: list[str] = data.get("project", {}).get("dependencies", [])

    # optional-dependencies is a dict[str, list[str]]
    opt_deps: dict[str, list[str]] = (
        data.get("project", {}).get("optional-dependencies", {})
    )
    for extra_list in opt_deps.values():
        raw.extend(extra_list)

    deps: set[str] = set()
    for dep in raw:
        name = _normalize_pkg_name(dep)
        if name:
            deps.add(name)
    return frozenset(deps)


def _parse_package_json_deps(pkg_json_path: Path) -> frozenset[str] | None:
    """Parse dependencies + devDependencies from package.json.

    Returns frozenset of package names (keys are already names), or None on failure.
    """
    try:
        data = json.loads(pkg_json_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("target_stack: failed to parse %s: %s", pkg_json_path, exc)
        return None

    deps: set[str] = set()
    deps.update(data.get("dependencies", {}).keys())
    deps.update(data.get("devDependencies", {}).keys())
    return frozenset(deps)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_target_stack(repo_root: Path) -> TargetStack:
    """Walk repo_root looking for pyproject.toml / package.json (top-level only).

    Python: parse [project] dependencies and [project.optional-dependencies].
    JS/TS: parse "dependencies" and "devDependencies" objects.

    Malformed manifests produce a warning and are skipped (no raise).
    Missing manifests → empty TargetStack.
    """
    python_deps: frozenset[str] = frozenset()
    js_deps: frozenset[str] = frozenset()
    detected_files: list[str] = []

    pyproject = repo_root / "pyproject.toml"
    if pyproject.exists():
        result = _parse_pyproject_deps(pyproject)
        if result is not None:
            python_deps = result
            detected_files.append("pyproject.toml")

    pkg_json = repo_root / "package.json"
    if pkg_json.exists():
        result = _parse_package_json_deps(pkg_json)
        if result is not None:
            js_deps = result
            detected_files.append("package.json")

    return TargetStack(
        repo_root=repo_root,
        python_deps=python_deps,
        js_deps=js_deps,
        detected_files=detected_files,
    )
