"""apply — senior session → target-repo CLAUDE.md translator.

Pure-ish module: reads session + target filesystem, writes markdown.
No LLM calls, no subprocess, no network.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from hijack.core.generator import _render_rule
from hijack.core.models import AnalysisRule, SessionResult
from hijack.core.scope_critic import extract_top_level_packages
from hijack.core.target_stack import TargetStack, detect_target_stack

# ---------------------------------------------------------------------------
# Compatible framework families
# When the senior repo uses A and the target uses B from the same family,
# the rule applies with a minor adaptation note.
# ---------------------------------------------------------------------------

_COMPATIBLE_FAMILIES: dict[str, frozenset[str]] = {
    "fastapi": frozenset({"starlette"}),
    "starlette": frozenset({"fastapi"}),
    "flask": frozenset({"quart"}),
    "quart": frozenset({"flask"}),
    "django": frozenset({"djangorestframework"}),
    "djangorestframework": frozenset({"django"}),
}


# ---------------------------------------------------------------------------
# Per-rule classification
# ---------------------------------------------------------------------------

@dataclass
class AppliedRule:
    """A senior rule's verdict against a target stack."""

    rule: AnalysisRule
    verdict: str            # "as_is" | "adapted" | "domain_adapt" | "reference_only"
    adaptation_note: str    # empty string when verdict is as_is
    matched_packages: frozenset[str]  # which framework packages this rule depends on


def classify_rule_against_stack(
    rule: AnalysisRule,
    target_stack: TargetStack,
) -> AppliedRule:
    """Decide how this rule applies to the target stack.

    Logic:
    1. cross_project → as_is
    2. domain_specific → domain_adapt
    3. framework_internal:
       a. Extract top-level packages from rule.good_example.
       b. Any package in target_stack.all_deps → as_is (same framework)
       c. Any has compatible sibling in target deps → adapted, translation hint
       d. Else → reference_only
    """
    scope = rule.scope or "cross_project"

    if scope == "cross_project":
        return AppliedRule(
            rule=rule,
            verdict="as_is",
            adaptation_note="",
            matched_packages=frozenset(),
        )

    if scope == "domain_specific":
        return AppliedRule(
            rule=rule,
            verdict="domain_adapt",
            adaptation_note="Domain-bound — adapt literal values/identifiers to your domain.",
            matched_packages=frozenset(),
        )

    # scope == "framework_internal"
    pkgs = extract_top_level_packages(rule.good_example or "")

    # a. Direct match — target uses the same framework
    direct_match = pkgs & target_stack.all_deps
    if direct_match:
        return AppliedRule(
            rule=rule,
            verdict="as_is",
            adaptation_note="",
            matched_packages=direct_match,
        )

    # b. Compatible sibling match
    for senior_pkg in pkgs:
        siblings = _COMPATIBLE_FAMILIES.get(senior_pkg, frozenset())
        matching_siblings = siblings & target_stack.all_deps
        if matching_siblings:
            sibling_list = ", ".join(sorted(matching_siblings))
            note = (
                f"Senior repo uses {senior_pkg}; translate to your "
                f"{sibling_list} equivalent (the rule's principle holds across the family)."
            )
            return AppliedRule(
                rule=rule,
                verdict="adapted",
                adaptation_note=note,
                matched_packages=frozenset({senior_pkg}),
            )

    # c. No match at all
    if pkgs:
        senior_pkgs_str = ", ".join(sorted(pkgs))
        target_deps_str = (
            ", ".join(sorted(target_stack.all_deps)) if target_stack.all_deps else "none"
        )
        note = (
            f"For reference only — target stack ({target_deps_str}) "
            f"doesn't use {senior_pkgs_str}."
        )
    else:
        # No import signal at all — no packages found in good_example
        target_deps_str = (
            ", ".join(sorted(target_stack.all_deps)) if target_stack.all_deps else "none"
        )
        note = (
            f"For reference only — target stack ({target_deps_str}) "
            "doesn't match this framework rule."
        )
    return AppliedRule(
        rule=rule,
        verdict="reference_only",
        adaptation_note=note,
        matched_packages=frozenset(),
    )


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------

@dataclass
class ApplyResult:
    target_stack: TargetStack
    by_verdict: dict[str, list[AppliedRule]] = field(default_factory=dict)
    total_input_rules: int = 0
    summary: str = ""


def apply_session_to_target(
    session: SessionResult,
    target_root: Path,
    *,
    strict: bool = False,
) -> ApplyResult:
    """Walk every rule in session, classify against target stack.

    strict=True: drop reference_only rules entirely.
    strict=False: keep them in their own bucket.
    """
    target_stack = detect_target_stack(target_root)

    by_verdict: dict[str, list[AppliedRule]] = {
        "as_is": [],
        "adapted": [],
        "domain_adapt": [],
        "reference_only": [],
    }

    total = 0
    for cat in session.categories:
        for rule in cat.rules:
            applied = classify_rule_against_stack(rule, target_stack)
            total += 1
            if strict and applied.verdict == "reference_only":
                continue
            by_verdict[applied.verdict].append(applied)

    # Build human-readable summary
    n_as_is = len(by_verdict["as_is"])
    n_adapted = len(by_verdict["adapted"])
    n_domain = len(by_verdict["domain_adapt"])
    n_ref = len(by_verdict["reference_only"])
    summary = (
        f"Applied {total} rules: "
        f"{n_as_is} universal/stack-specific, "
        f"{n_adapted} adapted, "
        f"{n_domain} domain, "
        f"{n_ref} reference-only"
    )

    return ApplyResult(
        target_stack=target_stack,
        by_verdict=by_verdict,
        total_input_rules=total,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

def _render_applied_rule(applied: AppliedRule) -> list[str]:
    """Render a single AppliedRule.

    Reuses generator._render_rule and post-processes the output to insert
    the adaptation_note as a blockquote directly after the **Why**: line.

    Rationale for post-processing rather than extending _render_rule's
    signature: the generator is a stable internal module used by multiple
    callers (write_output, render_layer_md, system-prompt, harness_export).
    Adding an optional `adaptation_note` parameter would leak apply-layer
    concerns into core rendering. Post-processing keeps both modules
    independently clean — apply.py owns the injection site logic.
    """
    lines = _render_rule(applied.rule)
    if not applied.adaptation_note:
        return lines

    # Find the **Why**: line and insert the note blockquote right after it
    for i, line in enumerate(lines):
        if line.startswith("**Why**:"):
            # Insert after the Why line and the blank line that follows it
            # Lines layout: [..., "**Why**: ...", "", ...]
            # Insert blockquote between "**Why**:" line and the next blank line
            insert_at = i + 1  # right after "**Why**: ..."
            lines.insert(insert_at, f"> Adaptation note: {applied.adaptation_note}")
            lines.insert(insert_at + 1, "")
            break

    return lines


def render_applied_md(result: ApplyResult, *, source_target: str) -> str:
    """Render ApplyResult as a target-tuned CLAUDE.md.

    Layout (empty sections are omitted):
      # Code Style — Adapted from {source_target}
      > Target stack: {detected packages}
      > {summary line}

      ## Universal Rules (apply directly)        — cross_project as_is
      ## Stack-Specific Rules (your project uses these) — framework_internal as_is
      ## Adapted Rules                            — adapted
      ## Domain Rules                             — domain_adapt
      ## For Reference (incompatible)             — reference_only
    """
    stack = result.target_stack
    dep_str = ", ".join(sorted(stack.all_deps)) if stack.all_deps else "none detected"

    lines: list[str] = [
        f"# Code Style — Adapted from {source_target}",
        "",
        f"> Target stack: {dep_str}",
        f"> {result.summary}",
        "",
    ]

    # Split as_is bucket into cross_project vs framework_internal
    universal: list[AppliedRule] = []
    stack_specific: list[AppliedRule] = []
    for applied in result.by_verdict.get("as_is", []):
        scope = applied.rule.scope or "cross_project"
        if scope == "cross_project":
            universal.append(applied)
        else:
            stack_specific.append(applied)

    adapted = result.by_verdict.get("adapted", [])
    domain = result.by_verdict.get("domain_adapt", [])
    reference = result.by_verdict.get("reference_only", [])

    if universal:
        lines += ["## Universal Rules (apply directly)", ""]
        for applied in universal:
            lines += _render_applied_rule(applied)

    if stack_specific:
        pkg_names = sorted(
            {p for a in stack_specific for p in a.matched_packages}
        )
        pkg_str = ", ".join(pkg_names) if pkg_names else "detected frameworks"
        lines += [f"## Stack-Specific Rules (your project uses {pkg_str})", ""]
        for applied in stack_specific:
            lines += _render_applied_rule(applied)

    if adapted:
        lines += ["## Adapted Rules (translate from senior framework to yours)", ""]
        for applied in adapted:
            lines += _render_applied_rule(applied)

    if domain:
        lines += ["## Domain Rules (adapt literal values)", ""]
        for applied in domain:
            lines += _render_applied_rule(applied)

    if reference:
        lines += ["## For Reference (incompatible — manual translation needed)", ""]
        for applied in reference:
            lines += _render_applied_rule(applied)

    return "\n".join(lines)
