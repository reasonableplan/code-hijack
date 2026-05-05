"""test_decisions — Phase B: what the senior repo's test suite defends against.

Senior maintainers' test code is a frozen record of "things we got burned by
once." This module extracts three mechanical signals from test files:

  1. pytest.mark.parametrize edge cases — the boundary values the maintainers
     explicitly reached for (None, -1, empty strings, oversized inputs, etc.).
  2. Test function name patterns — semantic verbs (handles/raises/rejects/…)
     reveal the *threat model* the test suite covers.
  3. pytest.raises blocks — which exception types the suite explicitly asserts,
     and what triggers each one.

Pure module: stdlib ast + re only. No LLM, no I/O, no network.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hijack.core.fetcher import SourceFile

# ---------------------------------------------------------------------------
# Constants — path detection
# ---------------------------------------------------------------------------

# Top-level test directory prefixes (posix-style, trailing slash).
# Phase B is the *opposite* of exemplars.py: we ONLY process these.
_TEST_PATH_PREFIXES: tuple[str, ...] = ("tests/", "test/")

# Truncation marker written by the fetcher — files starting with this are
# signature-only stubs and can't be reliably AST-walked for test bodies.
_TRUNCATION_MARKER = "# [TRUNCATED:"

# Semantic verb prefixes that signal a *defensive* test intent.
# Order matters for display (most common first as a reasonable default).
_NAME_PATTERN = re.compile(
    r"^test_(?P<verb>handles|raises|rejects|allows|preserves|with|when|after|during|on)_(?P<rest>.+)$"
)

# ID substrings that flag a pytest.param as an edge-case by its label.
_EDGE_ID_KEYWORDS = ("edge", "invalid", "empty", "weird", "malformed", "boundary", "extreme")

# Cap on collected edge cases — long-tail parametrize suites would otherwise
# generate thousands of records. 50 is enough to surface the *kinds* of
# edge cases the senior suite is sensitive to.
_MAX_EDGE_CASES = 50

# Cap on raises groups — exceptions used once or twice are noise; the top 30
# represent the intentional failure-mode catalog.
_MAX_RAISES_GROUPS = 30

# Maximum repr length for a single edge-case value.
_CASE_REPR_MAX = 120

# Maximum length for a trigger line extracted from a with pytest.raises block.
_TRIGGER_MAX = 200

# Maximum examples per NameTheme (full test names to illustrate the cluster).
_MAX_THEME_EXAMPLES = 3

# Maximum triggers stored per RaisesGroup (distinct trigger lines).
_MAX_TRIGGERS_PER_GROUP = 3

# Minimum number of tokens in test name suffix to surface in clustering.
# test_handles_empty → rest="empty" (1 token) — still useful.
_SUBJECT_TOKENS = 2  # take first 2 tokens of `rest` as subject key


# ---------------------------------------------------------------------------
# Public dataclasses
# ---------------------------------------------------------------------------

@dataclass
class EdgeCase:
    """One edge-case parameter value extracted from pytest.mark.parametrize."""

    test_file: str     # repo-relative posix path
    test_name: str     # the decorated function's name
    params: str        # the parametrize spec string, e.g. "input,expected"
    case_repr: str     # short repr of the matching case value (≤120 chars)
    why: str           # which heuristic triggered, e.g. "contains None"

    def to_json(self) -> dict[str, Any]:
        return {
            "test_file": self.test_file,
            "test_name": self.test_name,
            "params": self.params,
            "case_repr": self.case_repr,
            "why": self.why,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> EdgeCase:
        return cls(
            test_file=data["test_file"],
            test_name=data["test_name"],
            params=data["params"],
            case_repr=data["case_repr"],
            why=data["why"],
        )


@dataclass
class NameTheme:
    """A cluster of test names sharing the same semantic verb + subject prefix."""

    verb: str            # one of the verbs from _NAME_PATTERN
    subject: str         # first 1-2 tokens of `rest`, e.g. "empty" or "circular_reference"
    count: int           # total tests in this cluster
    examples: list[str]  # up to 3 full test names

    def to_json(self) -> dict[str, Any]:
        return {
            "verb": self.verb,
            "subject": self.subject,
            "count": self.count,
            "examples": self.examples,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> NameTheme:
        return cls(
            verb=data["verb"],
            subject=data["subject"],
            count=data["count"],
            examples=data["examples"],
        )


@dataclass
class RaisesGroup:
    """All pytest.raises(X) occurrences aggregated by exception type."""

    exception: str       # exception type name, e.g. "ValueError" or "pydantic.ValidationError"
    count: int           # total occurrences across the suite
    triggers: list[str]  # up to 3 distinct trigger lines (ast.unparse of the first stmt)

    def to_json(self) -> dict[str, Any]:
        return {
            "exception": self.exception,
            "count": self.count,
            "triggers": self.triggers,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> RaisesGroup:
        return cls(
            exception=data["exception"],
            count=data["count"],
            triggers=data["triggers"],
        )


@dataclass
class TestDecisions:
    """Aggregated mechanical signals extracted from a repo's test suite."""

    # Tell pytest this is a data class, not a test class. Without this, pytest
    # tries to collect it (sees the `Test` prefix) and emits a warning because
    # dataclasses have an __init__.
    __test__ = False

    edge_cases: list[EdgeCase]
    name_themes: list[NameTheme]
    raises_groups: list[RaisesGroup]
    test_file_count: int  # how many test files were actually scanned

    def to_json(self) -> dict[str, Any]:
        return {
            "edge_cases": [e.to_json() for e in self.edge_cases],
            "name_themes": [t.to_json() for t in self.name_themes],
            "raises_groups": [r.to_json() for r in self.raises_groups],
            "test_file_count": self.test_file_count,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> TestDecisions:
        return cls(
            edge_cases=[EdgeCase.from_json(e) for e in data.get("edge_cases", [])],
            name_themes=[NameTheme.from_json(t) for t in data.get("name_themes", [])],
            raises_groups=[RaisesGroup.from_json(r) for r in data.get("raises_groups", [])],
            test_file_count=data.get("test_file_count", 0),
        )

    @property
    def has_signal(self) -> bool:
        return bool(self.edge_cases or self.name_themes or self.raises_groups)


# ---------------------------------------------------------------------------
# Path detection
# ---------------------------------------------------------------------------

def _is_test_path(path: Path) -> bool:
    """Return True for both top-level and nested test directories.

    Examples:
      tests/test_color.py         → True  (top-level prefix)
      src/pkg/tests/helpers.py    → True  (nested /tests/ component)
      tests.py                    → False (file, not directory)
      lib/foo.py                  → False
    """
    posix = path.as_posix()
    return any(
        posix.startswith(prefix) or f"/{prefix}" in posix
        for prefix in _TEST_PATH_PREFIXES
    )


# ---------------------------------------------------------------------------
# Signal 1 — parametrize edge cases
# ---------------------------------------------------------------------------

def _ast_name(node: ast.expr) -> str:
    """Return the dotted name of an ast.Name or ast.Attribute chain, or ''."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _ast_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def _is_pytest_param_call(node: ast.expr) -> bool:
    """Return True when node is a call to pytest.param(...)."""
    if not isinstance(node, ast.Call):
        return False
    return _ast_name(node.func) in ("pytest.param", "param")


def _edge_case_why(node: ast.expr) -> str | None:
    """Return a reason string if the AST node represents an edge-case value.

    Checks both the value itself (None, "", 0, empty collections, oversize)
    and, for pytest.param(..., id="..."), the id keyword.
    """
    # pytest.param(...) — check its id keyword first, then recurse on values
    if _is_pytest_param_call(node):
        assert isinstance(node, ast.Call)
        for kw in node.keywords:
            if kw.arg == "id" and isinstance(kw.value, ast.Constant):
                id_str = str(kw.value.value).lower()
                for keyword in _EDGE_ID_KEYWORDS:
                    if keyword in id_str:
                        return f"id contains '{keyword}'"
            if kw.arg == "marks":
                # marks=pytest.mark.xfail or marks=[pytest.mark.skip, ...]
                mark_names = _collect_mark_names(kw.value)
                for mark in mark_names:
                    if mark in ("xfail", "skip"):
                        return f"pytest.param marked {mark}"
        # Also check the positional value args of pytest.param
        for arg in node.args:
            why = _edge_case_why(arg)
            if why:
                return why
        return None

    # None literal
    if isinstance(node, ast.Constant):
        v = node.value
        if v is None:
            return "contains None"
        if isinstance(v, str):
            if v == "":
                return "empty string"
            if v.strip() == "" and v != "":
                return f"whitespace string {v!r}"
            if len(v) > 1000:
                return "oversize string"
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            if v == 0:
                return "numeric 0"
            if v == -1:
                return "numeric -1"
            if isinstance(v, float) and v == -0.0:
                return "numeric -0.0"
            if abs(v) >= 1_000_000:
                return "oversize numeric"
        return None

    # UnaryOp handles -1, -0.0 written as -<Constant>
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        if isinstance(node.operand, ast.Constant):
            v = node.operand.value
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                neg = -v
                if neg == -1:
                    return "numeric -1"
                if isinstance(v, float) and neg == -0.0:
                    return "numeric -0.0"
                if abs(neg) >= 1_000_000:
                    return "oversize numeric"
        return None

    # Empty collection literals
    if isinstance(node, ast.List) and not node.elts:
        return "empty list"
    if isinstance(node, ast.Dict) and not node.keys:
        return "empty dict"
    if isinstance(node, ast.Tuple) and not node.elts:
        return "empty tuple"
    if isinstance(node, ast.Set) and not node.elts:
        return "empty set"

    return None


def _collect_mark_names(node: ast.expr) -> list[str]:
    """Collect mark names from a marks= value (single mark or list of marks)."""
    names: list[str] = []
    if isinstance(node, ast.List):
        for elt in node.elts:
            names.extend(_collect_mark_names(elt))
    else:
        name = _ast_name(node)
        # pytest.mark.xfail → last component
        if name:
            parts = name.split(".")
            names.append(parts[-1])
    return names


def _short_repr(node: ast.expr) -> str:
    """Return a short literal-style repr of the case value, truncated."""
    try:
        text = ast.unparse(node)
    except Exception:
        text = repr(node)
    if len(text) > _CASE_REPR_MAX:
        text = text[: _CASE_REPR_MAX - 1] + "…"
    return text


def _extract_parametrize_calls(
    tree: ast.Module,
    file_path_str: str,
) -> list[EdgeCase]:
    """Walk all function definitions and extract parametrize edge cases."""
    results: list[EdgeCase] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        func_name = node.name
        for decorator in node.decorator_list:
            # Accept both `pytest.mark.parametrize(...)` and `mark.parametrize(...)`
            if not isinstance(decorator, ast.Call):
                continue
            deco_name = _ast_name(decorator.func)
            if not deco_name.endswith("parametrize"):
                continue
            args = decorator.args
            if len(args) < 2:
                continue
            # First arg: parameter spec string
            if not isinstance(args[0], ast.Constant) or not isinstance(args[0].value, str):
                continue
            params_str: str = args[0].value

            # Second arg: the case list/tuple
            case_list_node = args[1]
            if isinstance(case_list_node, (ast.List, ast.Tuple)):
                case_nodes = case_list_node.elts
            else:
                # Not a literal list/tuple — skip (e.g. variable reference)
                continue

            for case_node in case_nodes:
                why = _edge_case_why(case_node)
                if why:
                    results.append(
                        EdgeCase(
                            test_file=file_path_str,
                            test_name=func_name,
                            params=params_str,
                            case_repr=_short_repr(case_node),
                            why=why,
                        )
                    )
    return results


# ---------------------------------------------------------------------------
# Signal 2 — test function name patterns
# ---------------------------------------------------------------------------

def _subject_key(rest: str) -> str:
    """Derive the cluster subject from the `rest` part of a test name.

    Takes the first _SUBJECT_TOKENS tokens joined by underscore, so
    "empty_iterator_when_exhausted" → "empty_iterator".
    Single-token rests (e.g. "empty") are kept as-is.
    """
    tokens = rest.split("_")
    return "_".join(tokens[:_SUBJECT_TOKENS])


def _extract_name_themes(tree: ast.Module) -> list[tuple[str, str, str]]:
    """Return (verb, subject, full_name) for each matching test function."""
    results: list[tuple[str, str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        name = node.name
        m = _NAME_PATTERN.match(name)
        if m:
            verb = m.group("verb")
            rest = m.group("rest")
            subject = _subject_key(rest)
            results.append((verb, subject, name))
    return results


# ---------------------------------------------------------------------------
# Signal 3 — pytest.raises blocks
# ---------------------------------------------------------------------------

def _raises_exception_name(call: ast.Call) -> str | None:
    """Extract the exception name from a pytest.raises(ExcType) call.

    Returns a dotted string like "ValueError" or "pydantic.ValidationError",
    or None when the first argument isn't a name/attribute (e.g. it's a
    variable or expression we can't statically name).
    """
    if not call.args:
        return None
    first = call.args[0]
    name = _ast_name(first)
    return name if name else None


def _is_pytest_raises_call(node: ast.expr) -> bool:
    """Return True for pytest.raises(...) or raises(...) calls."""
    if not isinstance(node, ast.Call):
        return False
    name = _ast_name(node.func)
    return name in ("pytest.raises", "raises")


def _extract_trigger(body: list[ast.stmt]) -> str:
    """Extract the first non-pass statement from a with-raises body as a string."""
    for stmt in body:
        if isinstance(stmt, ast.Pass):
            continue
        try:
            text = ast.unparse(stmt).strip()
        except Exception:
            continue
        if len(text) > _TRIGGER_MAX:
            text = text[:_TRIGGER_MAX - 1] + "…"
        return text
    return ""


def _extract_raises_blocks(tree: ast.Module) -> list[tuple[str, str]]:
    """Return (exception_name, trigger_line) for each with pytest.raises block."""
    results: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.With):
            continue
        for item in node.items:
            ctx = item.context_expr
            if not _is_pytest_raises_call(ctx):
                continue
            assert isinstance(ctx, ast.Call)
            exc_name = _raises_exception_name(ctx)
            if not exc_name:
                continue
            trigger = _extract_trigger(node.body)
            results.append((exc_name, trigger))
    return results


# ---------------------------------------------------------------------------
# Top-level extractor
# ---------------------------------------------------------------------------

def extract_test_decisions(files: list[SourceFile]) -> TestDecisions:
    """Extract all three signals from the test files in `files`.

    Filters to files matching `_is_test_path` and `.py` suffix only.
    Skips truncated files (start with _TRUNCATION_MARKER) and files with
    syntax errors (SyntaxError in ast.parse is caught silently).

    Post-processing:
    - edge_cases sorted by (test_file, test_name) for determinism, capped at 50.
    - name_themes sorted by count desc, then verb asc, then subject asc.
    - raises_groups sorted by count desc, then exception asc, capped at 30.
    """
    # Accumulators
    all_edge_cases: list[EdgeCase] = []
    # (verb, subject) → (count, list[str examples])
    theme_map: dict[tuple[str, str], list[str]] = {}
    # exception_name → (count, list[str triggers seen])
    raises_map: dict[str, tuple[int, list[str]]] = {}

    test_file_count = 0

    for sf in files:
        # Only .py test files
        if sf.path.suffix != ".py":
            continue
        if not _is_test_path(sf.path):
            continue

        content = sf.content or ""
        if content.startswith(_TRUNCATION_MARKER):
            continue

        try:
            tree = ast.parse(content)
        except SyntaxError:
            continue

        test_file_count += 1
        file_path_str = sf.path.as_posix()

        # Signal 1
        all_edge_cases.extend(_extract_parametrize_calls(tree, file_path_str))

        # Signal 2
        for verb, subject, full_name in _extract_name_themes(tree):
            key = (verb, subject)
            if key not in theme_map:
                theme_map[key] = []
            theme_map[key].append(full_name)

        # Signal 3
        for exc_name, trigger in _extract_raises_blocks(tree):
            if exc_name in raises_map:
                count, triggers = raises_map[exc_name]
                raises_map[exc_name] = (count + 1, triggers)
                if trigger and trigger not in triggers and len(triggers) < _MAX_TRIGGERS_PER_GROUP:
                    triggers.append(trigger)
            else:
                raises_map[exc_name] = (1, [trigger] if trigger else [])

    # --- Post-process signal 1 ---
    all_edge_cases.sort(key=lambda e: (e.test_file, e.test_name))
    edge_cases = all_edge_cases[:_MAX_EDGE_CASES]

    # --- Post-process signal 2 ---
    name_themes: list[NameTheme] = []
    for (verb, subject), names in theme_map.items():
        name_themes.append(
            NameTheme(
                verb=verb,
                subject=subject,
                count=len(names),
                examples=names[:_MAX_THEME_EXAMPLES],
            )
        )
    name_themes.sort(key=lambda t: (-t.count, t.verb, t.subject))

    # --- Post-process signal 3 ---
    raises_groups: list[RaisesGroup] = []
    for exc_name, (count, triggers) in raises_map.items():
        raises_groups.append(
            RaisesGroup(
                exception=exc_name,
                count=count,
                triggers=triggers,
            )
        )
    raises_groups.sort(key=lambda r: (-r.count, r.exception))
    raises_groups = raises_groups[:_MAX_RAISES_GROUPS]

    return TestDecisions(
        edge_cases=edge_cases,
        name_themes=name_themes,
        raises_groups=raises_groups,
        test_file_count=test_file_count,
    )


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

def render_tests_distilled_md(decisions: TestDecisions, *, source_target: str) -> str:
    """Render TestDecisions as Markdown.

    Returns '' when has_signal is False — caller skips writing the file.
    """
    if not decisions.has_signal:
        return ""

    lines: list[str] = [
        "# Tests Distilled — what this library defends against",
        "",
        f"> Selected from {source_target}: edge cases, exception expectations, and",
        f"> defensive test patterns extracted from {decisions.test_file_count} test files.",
        "> These represent invariants the senior maintainers explicitly chose to",
        "> protect against.",
        "",
    ]

    # --- Section: top defensive themes ---
    if decisions.name_themes:
        lines += ["## Top defensive themes (by test count)", ""]

        # Group themes by verb for hierarchical display
        by_verb: dict[str, list[NameTheme]] = {}
        for theme in decisions.name_themes:
            by_verb.setdefault(theme.verb, []).append(theme)

        # Verb order: sort by total count desc within the grouped display
        verb_totals = {
            verb: sum(t.count for t in themes)
            for verb, themes in by_verb.items()
        }
        sorted_verbs = sorted(by_verb.keys(), key=lambda v: (-verb_totals[v], v))

        for i, verb in enumerate(sorted_verbs, start=1):
            themes = by_verb[verb]
            total = verb_totals[verb]
            lines.append(f"{i}. **{verb}** ({total} tests)")
            for theme in themes:
                ex_str = ", ".join(f"`{n}`" for n in theme.examples)
                lines.append(
                    f"   - `{verb}_{theme.subject}` ({theme.count} tests)"
                    f" — examples: {ex_str}"
                )
        lines.append("")

    # --- Section: explicit failure expectations ---
    if decisions.raises_groups:
        lines += ["## Explicit failure expectations (pytest.raises)", ""]
        for rg in decisions.raises_groups:
            lines.append(f"- `{rg.exception}` ({rg.count} occurrences)")
            for trigger in rg.triggers:
                lines.append(f"  - `{trigger}`")
        lines.append("")

    # --- Section: notable parametrize edge cases ---
    if decisions.edge_cases:
        lines += ["## Notable parametrize edge cases", ""]
        for ec in decisions.edge_cases:
            lines.append(
                f"- `{ec.test_file}::{ec.test_name}` — `{ec.case_repr}`"
                f" (param: `{ec.params}`) — {ec.why}"
            )
        lines.append("")

    return "\n".join(lines)
