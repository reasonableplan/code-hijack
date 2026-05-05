"""exemplars — canonical function/class selection from senior repo source files.

Pure module: no LLM, no I/O, no network. Uses ast (stdlib) to parse and score
Python function/class definitions. TypeScript / JSX files are skipped — AST-based
selection only works for Python.
"""
from __future__ import annotations

import ast
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hijack.core.fetcher import SourceFile

# Marker inserted by fetcher when a file exceeds _MAX_LINES.
_TRUNCATION_MARKER = "# [TRUNCATED:"

# Files below this composite score are rejected — prevents picking junk when
# a repo has only very small, untyped, or undocumented code.
_MIN_SCORE = 0.4

# Path prefixes excluded from exemplar selection. These directories typically
# hold pedagogical or auxiliary code (tutorials, fixtures, build scripts) whose
# style is not representative of the senior library code we want agents to
# imitate. Match is on the posix-style relative path with a trailing slash so
# "tests" never matches a top-level "tests.py" file.
_EXCLUDED_PATH_PREFIXES: tuple[str, ...] = (
    "tests/",
    "test/",
    "docs/",
    "docs_src/",
    "scripts/",
    "examples/",
    "examples_src/",
    "tutorial/",
    "tutorials/",
    "benchmarks/",
    "e2e/",
    # Dev/CI automation and explicitly-legacy code shouldn't represent
    # senior style. .github/ holds workflow scripts; deprecated/ and
    # legacy/ hold code the project itself flags as not-the-current-way.
    ".github/",
    "deprecated/",
    "legacy/",
)

# Scoring weights (must sum to 1.0).
_W_LENGTH = 0.30
_W_ANNOTATION = 0.30
_W_DOCSTRING = 0.25
_W_PUBLIC = 0.15


# ---------------------------------------------------------------------------
# Exemplar dataclass
# ---------------------------------------------------------------------------

@dataclass
class Exemplar:
    """A representative function/class selected from the senior repo."""

    file_path: str              # repo-relative posix path
    line_range: tuple[int, int]  # (start_line, end_line) — both inclusive
    code: str                   # the source — function or class body verbatim
    layer: str                  # frontend/backend/db/devops/shared
    role: str                   # entry_point/model/api/test/service/other
    name: str                   # function or class name
    why_chosen: str             # 1-line rationale

    def to_json(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "line_range": list(self.line_range),
            "code": self.code,
            "layer": self.layer,
            "role": self.role,
            "name": self.name,
            "why_chosen": self.why_chosen,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Exemplar:
        lr = data["line_range"]
        return cls(
            file_path=data["file_path"],
            line_range=(int(lr[0]), int(lr[1])),
            code=data["code"],
            layer=data["layer"],
            role=data["role"],
            name=data["name"],
            why_chosen=data["why_chosen"],
        )


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def _score_length(n_lines: int) -> float:
    """Map function line count to [0, 1] with a sweet spot at 8-30 lines."""
    if n_lines < 5:
        return 0.0
    if n_lines < 8:
        return 0.5
    if n_lines <= 30:
        return 1.0
    if n_lines <= 50:
        return 0.7
    return 0.3


def _score_length_class(n_lines: int) -> float:
    """Class line-count curve — separate from functions.

    Senior library classes routinely run 50-200 lines because typed __init__
    plus methods belong together; the same length signals "junk" for a
    function but "thoroughness" for a class. Reject only on the extremes.
    """
    if n_lines < 5:
        return 0.0
    if n_lines < 8:
        return 0.5
    if n_lines <= 200:
        return 1.0
    if n_lines <= 400:
        return 0.6
    return 0.3


def _score_annotation_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    return_implicit_none: bool = False,
) -> float:
    """Annotation density for a function node.

    `return_implicit_none=True` is set when scoring `__init__` (and similar
    void-by-convention methods) where authors routinely omit the `-> None`
    annotation. Without this flag a senior `__init__` with 50 fully-annotated
    parameters scores only 0.6 because of the missing trivial return type.
    """
    args = node.args
    # Collect all regular + keyword-only + positional-only args, excluding self/cls.
    all_args = [
        *args.posonlyargs,
        *args.args,
        *args.kwonlyargs,
    ]
    if args.vararg:
        all_args.append(args.vararg)
    if args.kwarg:
        all_args.append(args.kwarg)

    # Strip leading self/cls (not annotated by convention)
    if all_args and all_args[0].arg in ("self", "cls"):
        all_args = all_args[1:]

    returns_annotated = node.returns is not None or return_implicit_none
    returns_factor = 1.0 if returns_annotated else 0.6

    if not all_args:
        # No args — use returns alone
        return 1.0 if returns_annotated else 0.4

    annotated = sum(1 for a in all_args if a.annotation is not None)
    density = annotated / len(all_args)
    return density * returns_factor


def _score_annotation_class(node: ast.ClassDef) -> float:
    """Annotation density for a class node (looks at __init__ args)."""
    for item in node.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == "__init__":
            return _score_annotation_function(item, return_implicit_none=True)
    # No __init__ found
    return 0.7  # non-trivial dataclass / ABC / protocol style — give partial credit


def _score_docstring(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> float:
    """Richness of the leading docstring."""
    if not node.body:
        return 0.0
    first = node.body[0]
    if not (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)):
        return 0.0
    doc = first.value.value
    if not isinstance(doc, str):
        return 0.0
    lines = [ln for ln in doc.strip().splitlines() if ln.strip()]
    n = len(lines)
    if n == 0:
        return 0.0
    if n == 1:
        return 0.4
    if n <= 5:
        return 0.8
    return 1.0


def _score_public(name: str) -> float:
    return 1.0 if not name.startswith("_") else 0.3


def _composite_score(
    length_score: float,
    annotation_score: float,
    docstring_score: float,
    public_score: float,
) -> float:
    return (
        _W_LENGTH * length_score
        + _W_ANNOTATION * annotation_score
        + _W_DOCSTRING * docstring_score
        + _W_PUBLIC * public_score
    )


def _build_why_chosen(
    length_score: float,
    annotation_score: float,
    docstring_score: float,
    n_lines: int,
) -> str:
    """Build a short 1-line rationale from the strongest signals."""
    parts: list[str] = []

    if annotation_score >= 0.9:
        parts.append("fully type-annotated")
    elif annotation_score >= 0.6:
        parts.append("partially typed")

    if docstring_score >= 1.0:
        parts.append("rich multi-section docstring")
    elif docstring_score >= 0.8:
        parts.append("well-documented")
    elif docstring_score >= 0.4:
        parts.append("1-line docstring")

    if length_score == 1.0:
        parts.append(f"sweet-spot length ({n_lines} lines)")
    elif length_score >= 0.6:
        parts.append(f"moderate length ({n_lines} lines)")

    if not parts:
        parts.append("public API")

    return ", ".join(parts)


# ---------------------------------------------------------------------------
# Candidate extraction
# ---------------------------------------------------------------------------

@dataclass
class _Candidate:
    file_path: str
    layer: str
    role: str
    name: str
    start_line: int
    end_line: int
    code: str
    score: float
    why_chosen: str


def _is_excluded_path(path: Path) -> bool:
    """Return True for paths under tutorial/test/script directories.

    The senior library code we want to surface lives outside these areas;
    including them lets pedagogical or auxiliary files outscore the real API.
    """
    posix = path.as_posix()
    return any(
        posix.startswith(prefix) or f"/{prefix}" in posix
        for prefix in _EXCLUDED_PATH_PREFIXES
    )


def _has_private_dir_component(path: Path) -> bool:
    """Return True if any directory component starts with underscore.

    Python convention treats `_internal/`, `_private/` etc. as path-private —
    not part of the public API. Surfacing exemplars from these directories
    contradicts the goal of capturing canonical senior style. The filename
    itself is not checked — private functions inside public modules are
    already weighted down by `_score_public`.
    """
    return any(p.startswith("_") for p in path.parent.parts)


def _file_subdir(file_path: str) -> str:
    """Return the directory component of a posix-style relative path.

    Used by `select_exemplars` to spread picks across subpackages so a
    single subdirectory (e.g. fastapi/) doesn't crowd out a domain-specific
    one (e.g. fastapi/security/) that carries different patterns.
    """
    if "/" in file_path:
        return file_path.rsplit("/", 1)[0]
    return "."


def _refresh_content_from_disk(sf: SourceFile, repo_root: Path) -> SourceFile:
    """Re-read the source file from disk so AST extraction sees the full body.

    The fetcher truncates files past `_MAX_LINES` to keep LLM prompts bounded,
    but truncated files lose the bodies of long senior classes (e.g. FastAPI's
    `params.py` clocks in at 3500+ lines and demonstrates the canonical
    `_Unset` sentinel pattern). Reading fresh from disk bypasses that limit
    for AST consumers without changing the LLM prompt size.
    """
    full_path = repo_root / sf.path
    try:
        full = full_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return sf
    return SourceFile(
        path=sf.path,
        content=full,
        layer=sf.layer,
        role=sf.role,
        history=sf.history,
    )


def _extract_candidates(sf: SourceFile) -> list[_Candidate]:
    """Parse a Python SourceFile and score all top-level function/class defs."""
    # Only Python files
    if sf.path.suffix != ".py":
        return []

    if _is_excluded_path(sf.path):
        return []

    if _has_private_dir_component(sf.path):
        return []

    content = sf.content
    if not content or content.startswith(_TRUNCATION_MARKER):
        return []

    try:
        tree = ast.parse(content)
    except SyntaxError:
        return []

    source_lines = content.splitlines()
    candidates: list[_Candidate] = []
    file_path_str = sf.path.as_posix()

    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue

        start = node.lineno
        end = node.end_lineno if node.end_lineno is not None else node.lineno
        n_lines = end - start + 1

        # Extract source lines (1-indexed → 0-indexed slice)
        raw_lines = source_lines[start - 1 : end]
        code = textwrap.dedent("\n".join(raw_lines))

        if isinstance(node, ast.ClassDef):
            length_score = _score_length_class(n_lines)
            annotation_score = _score_annotation_class(node)
        else:
            length_score = _score_length(n_lines)
            annotation_score = _score_annotation_function(node)

        # Hard gate: fewer than 5 lines is always too trivial — skip before
        # annotation/docstring scores can rescue a stub.
        if length_score == 0.0:
            continue
        docstring_score = _score_docstring(node)
        public_score = _score_public(node.name)

        score = _composite_score(length_score, annotation_score, docstring_score, public_score)

        if score < _MIN_SCORE:
            continue

        why = _build_why_chosen(length_score, annotation_score, docstring_score, n_lines)

        candidates.append(
            _Candidate(
                file_path=file_path_str,
                layer=sf.layer,
                role=sf.role,
                name=node.name,
                start_line=start,
                end_line=end,
                code=code,
                score=score,
                why_chosen=why,
            )
        )

    return candidates


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

def select_exemplars(
    files: list[SourceFile],
    *,
    max_total: int = 8,
    max_per_layer: int = 4,
    max_per_file: int = 2,
    repo_root: Path | None = None,
) -> list[Exemplar]:
    """Pick 6-9 representative functions/classes across layers.

    For each Python SourceFile with parseable AST, walks top-level
    FunctionDef / AsyncFunctionDef / ClassDef nodes, scores each candidate,
    then selects across three passes:

    1. Pass 1 — top by score, capped at `max_per_layer` for diversity in
       multi-layer repos (frontend/backend/db split). At most `max_per_file`
       picks come from any single file across all passes.
    2. Pass 2a — fill remaining slots preferring candidates from
       subdirectories not yet represented. Surfaces e.g. fastapi/security/
       even when fastapi/ root has higher absolute scores.
    3. Pass 2b — fill any leftover slots by raw score.

    When `repo_root` is provided, content is re-read fresh from disk so the
    AST sees the full file body even for sources the fetcher truncated for
    LLM prompt budgeting. Required for capturing senior patterns from large
    files (FastAPI's `params.py`, `dependencies/utils.py`, `routing.py`).

    TypeScript / JSX files are skipped — AST-based selection only works for Python.
    Files with a truncation marker or syntax errors are silently skipped.
    Candidates below the _MIN_SCORE threshold are never picked.

    Returns an empty list when no candidates meet the quality threshold.
    """
    if repo_root is not None:
        files = [_refresh_content_from_disk(sf, repo_root) for sf in files]

    all_candidates: list[_Candidate] = []
    for sf in files:
        all_candidates.extend(_extract_candidates(sf))

    # Sort by score descending so best candidates are picked first
    all_candidates.sort(key=lambda c: c.score, reverse=True)

    layer_counts: dict[str, int] = {}
    file_counts: dict[str, int] = {}
    selected: list[Exemplar] = []
    picked: set[tuple[str, int, str]] = set()
    seen_buckets: set[tuple[str, str]] = set()

    def _make_exemplar(cand: _Candidate) -> Exemplar:
        return Exemplar(
            file_path=cand.file_path,
            line_range=(cand.start_line, cand.end_line),
            code=cand.code,
            layer=cand.layer,
            role=cand.role,
            name=cand.name,
            why_chosen=cand.why_chosen,
        )

    # Phase 1 — diversity guarantee: take the top *public* scorer from each
    # (layer, subdir) bucket. A single-layer repo with one dominant package
    # otherwise crowds out subpackages whose patterns differ (e.g.
    # fastapi/security/ holds the auth-scheme inheritance pattern that
    # fastapi/ root files don't carry). Stops at max_per_layer per layer.
    # Private names are deferred to phase 2/3 — a `_helper` shouldn't get
    # the slot reserved for "what this subpackage exports."
    for cand in all_candidates:
        if len(selected) >= max_total:
            break
        if cand.name.startswith("_"):
            continue
        bucket = (cand.layer, _file_subdir(cand.file_path))
        if bucket in seen_buckets:
            continue
        if layer_counts.get(cand.layer, 0) >= max_per_layer:
            continue
        if file_counts.get(cand.file_path, 0) >= max_per_file:
            continue
        seen_buckets.add(bucket)
        layer_counts[cand.layer] = layer_counts.get(cand.layer, 0) + 1
        file_counts[cand.file_path] = file_counts.get(cand.file_path, 0) + 1
        key = (cand.file_path, cand.start_line, cand.name)
        picked.add(key)
        selected.append(_make_exemplar(cand))

    # Phase 2 — fill by score, still respecting max_per_layer.
    if len(selected) < max_total:
        for cand in all_candidates:
            if len(selected) >= max_total:
                break
            key = (cand.file_path, cand.start_line, cand.name)
            if key in picked:
                continue
            if layer_counts.get(cand.layer, 0) >= max_per_layer:
                continue
            if file_counts.get(cand.file_path, 0) >= max_per_file:
                continue
            layer_counts[cand.layer] = layer_counts.get(cand.layer, 0) + 1
            file_counts[cand.file_path] = file_counts.get(cand.file_path, 0) + 1
            picked.add(key)
            selected.append(_make_exemplar(cand))

    # Phase 3 — relax the layer cap if we still have room. Single-layer
    # libraries (pure-Python frameworks) hit the per-layer cap before
    # max_total fills; without this they'd ship a half-empty exemplars.md.
    if len(selected) < max_total:
        for cand in all_candidates:
            if len(selected) >= max_total:
                break
            key = (cand.file_path, cand.start_line, cand.name)
            if key in picked:
                continue
            if file_counts.get(cand.file_path, 0) >= max_per_file:
                continue
            file_counts[cand.file_path] = file_counts.get(cand.file_path, 0) + 1
            picked.add(key)
            selected.append(_make_exemplar(cand))

    return selected


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render_exemplars_md(exemplars: list[Exemplar], *, source_target: str) -> str:
    """Render exemplars as Markdown.

    Returns "" when exemplars list is empty — caller skips writing the file.
    """
    if not exemplars:
        return ""

    lines: list[str] = [
        "# Senior Exemplars — Match the rhythm of these",
        "",
        f"> Selected from {source_target}: representative functions/classes that",
        "> demonstrate the codebase's typical structure, type annotation density,",
        "> and docstring style. Match this rhythm when generating new code.",
        "",
    ]

    for i, ex in enumerate(exemplars, start=1):
        start, end = ex.line_range
        lines += [
            f"## Exemplar {i}: `{ex.file_path}:{start}-{end}` (`{ex.name}`)",
            "",
            f"**Layer**: {ex.layer} | **Role**: {ex.role} | **Why chosen**: {ex.why_chosen}",
            "",
            "```python",
            ex.code,
            "```",
            "",
        ]

    return "\n".join(lines)
