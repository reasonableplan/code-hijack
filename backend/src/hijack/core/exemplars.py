"""exemplars — canonical function/class selection from senior repo source files.

Pure module: no LLM, no I/O, no network. Uses ast (stdlib) to parse and score
Python function/class definitions. TypeScript / JSX files are skipped — AST-based
selection only works for Python.
"""
from __future__ import annotations

import ast
import textwrap
from dataclasses import dataclass
from typing import Any

from hijack.core.fetcher import SourceFile

# Marker inserted by fetcher when a file exceeds _MAX_LINES.
_TRUNCATION_MARKER = "# [TRUNCATED:"

# Files below this composite score are rejected — prevents picking junk when
# a repo has only very small, untyped, or undocumented code.
_MIN_SCORE = 0.4

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
    """Map line count to [0, 1] with a sweet spot at 8-30 lines."""
    if n_lines < 5:
        return 0.0
    if n_lines < 8:
        return 0.5
    if n_lines <= 30:
        return 1.0
    if n_lines <= 50:
        return 0.7
    return 0.3


def _score_annotation_function(node: ast.FunctionDef | ast.AsyncFunctionDef) -> float:
    """Annotation density for a function node."""
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

    returns_annotated = node.returns is not None
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
            return _score_annotation_function(item)
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
    elif length_score == 0.7:
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


def _extract_candidates(sf: SourceFile) -> list[_Candidate]:
    """Parse a Python SourceFile and score all top-level function/class defs."""
    # Only Python files
    if sf.path.suffix != ".py":
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

        length_score = _score_length(n_lines)
        # Hard gate: fewer than 5 lines is always too trivial — skip before
        # annotation/docstring scores can rescue a stub.
        if length_score == 0.0:
            continue

        if isinstance(node, ast.ClassDef):
            annotation_score = _score_annotation_class(node)
        else:
            annotation_score = _score_annotation_function(node)
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
    max_per_layer: int = 2,
) -> list[Exemplar]:
    """Pick 6-9 representative functions/classes across layers.

    For each Python SourceFile with parseable AST, walks top-level
    FunctionDef / AsyncFunctionDef / ClassDef nodes, scores each candidate,
    then selects up to max_per_layer per layer until max_total reached.

    TypeScript / JSX files are skipped — AST-based selection only works for Python.
    Files with a truncation marker or syntax errors are silently skipped.
    Candidates below the _MIN_SCORE threshold are never picked.

    Returns an empty list when no candidates meet the quality threshold.
    """
    all_candidates: list[_Candidate] = []
    for sf in files:
        all_candidates.extend(_extract_candidates(sf))

    # Sort by score descending so best candidates are picked first
    all_candidates.sort(key=lambda c: c.score, reverse=True)

    layer_counts: dict[str, int] = {}
    selected: list[Exemplar] = []

    for cand in all_candidates:
        if len(selected) >= max_total:
            break
        layer_count = layer_counts.get(cand.layer, 0)
        if layer_count >= max_per_layer:
            continue
        layer_counts[cand.layer] = layer_count + 1
        selected.append(
            Exemplar(
                file_path=cand.file_path,
                line_range=(cand.start_line, cand.end_line),
                code=cand.code,
                layer=cand.layer,
                role=cand.role,
                name=cand.name,
                why_chosen=cand.why_chosen,
            )
        )

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
