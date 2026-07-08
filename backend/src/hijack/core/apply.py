"""apply — senior session → target-repo CLAUDE.md translator.

Pure-ish module: reads session + target filesystem, writes markdown.
No LLM calls, no subprocess, no network.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from hijack.core.generator import _render_rule
from hijack.core.models import AnalysisRule, SessionResult
from hijack.core.scope_critic import extract_top_level_packages
from hijack.core.target_stack import TargetStack, detect_target_stack

if TYPE_CHECKING:
    from hijack.core.archaeology import CommitDecisions
    from hijack.core.exemplars import Exemplar
    from hijack.core.pr_archaeology import PRDecisions
    from hijack.core.test_decisions import TestDecisions

# ---------------------------------------------------------------------------
# Framework relationship maps
# ---------------------------------------------------------------------------

# A "is built on" B: any rule referencing B's symbols transfers to A
# transparently because A's import surface includes B's. The reverse does
# NOT hold — A adds layers above B that B doesn't know about.
_FRAMEWORK_BASES: dict[str, frozenset[str]] = {
    "fastapi": frozenset({"starlette"}),
    "djangorestframework": frozenset({"django"}),
}

# A and B are sibling-compatible: rules transfer in either direction with
# minor adaptation. Use this for parallel frameworks that target the same
# problem space (sync vs async Flask), not for "built-on" inheritance.
_SIBLING_COMPAT: dict[str, frozenset[str]] = {
    "flask": frozenset({"quart"}),
    "quart": frozenset({"flask"}),
}


def _expand_target_deps(deps: frozenset[str]) -> frozenset[str]:
    """Add each dep's transitive bases to the set.

    target deps = {fastapi}     → {fastapi, starlette}
    target deps = {drf}         → {drf, django}
    target deps = {fastapi, sqlalchemy} → {fastapi, starlette, sqlalchemy}
    """
    expanded = set(deps)
    for dep in deps:
        expanded |= _FRAMEWORK_BASES.get(dep, frozenset())
    return frozenset(expanded)


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
    expanded_target = _expand_target_deps(target_stack.all_deps)

    # a. Direct or transitive match — target uses (or is built on) the framework
    direct_match = pkgs & expanded_target
    if direct_match:
        return AppliedRule(
            rule=rule,
            verdict="as_is",
            adaptation_note="",
            matched_packages=direct_match,
        )

    # b. Sibling-compat match — adapted with translation note
    for senior_pkg in pkgs:
        siblings = _SIBLING_COMPAT.get(senior_pkg, frozenset())
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
    # Exemplars from the senior session, passed through for downstream rendering.
    # Empty when the source session had no exemplars (pre-G1 or non-Python repos).
    exemplars: list[Exemplar] = field(default_factory=list)
    # Test-suite decisions (Phase B): edge cases, name themes, raises groups.
    # None when the source session predates Phase B or had no test files.
    test_decisions: TestDecisions | None = None
    # PR-history signals (Phase A1): vocabulary clusters, notable/rejected PRs,
    # recurring labels. None when Phase A1 was skipped (non-GitHub target or no auth).
    pr_decisions: PRDecisions | None = None
    # Commit-message decision trails (Phase C): "tried X / switched to Y" patterns
    # mined from commit bodies. None when no commit history was loaded.
    commit_decisions: CommitDecisions | None = None


def apply_session_to_target(
    session: SessionResult,
    target_root: Path,
    *,
    strict: bool = False,
    target_stack: TargetStack | None = None,
) -> ApplyResult:
    """Walk every rule in session, classify against target stack.

    strict=True: drop reference_only rules entirely.
    strict=False: keep them in their own bucket.
    target_stack: pre-built TargetStack to use instead of detecting from disk.
                  When None, detect_target_stack(target_root) is called.
    """
    if target_stack is None:
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
        exemplars=list(session.exemplars),
        test_decisions=session.test_decisions,
        pr_decisions=session.pr_decisions,
        commit_decisions=session.commit_decisions,
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
    callers (write_output, render_layer_md, system-prompt).
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
      ## Senior Exemplars (rhythm reference)      — when exemplars are non-empty
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

    if result.exemplars:
        from hijack.core.exemplars import render_exemplars_md
        exemplar_md = render_exemplars_md(result.exemplars, source_target=source_target)
        if exemplar_md:
            lines += [
                "",
                "## Senior Exemplars (rhythm reference)",
                "",
                "> Match the structure, annotation density, and docstring style of these"
                " representative functions from the senior repo.",
                "",
            ]
            # Append the rendered exemplars block (skip the top-level H1 header
            # since we already placed a section header above).
            exemplar_lines = exemplar_md.splitlines()
            # Drop the first H1 heading block (lines up to and including the blank
            # line after the blockquote preamble) so rendering nests cleanly.
            in_preamble = True
            for line in exemplar_lines:
                if in_preamble:
                    if line.startswith("#"):
                        continue
                    if line.startswith(">"):
                        continue
                    if line == "":
                        in_preamble = False
                        continue
                lines.append(line)

    if result.test_decisions is not None and result.test_decisions.has_signal:
        from hijack.core.test_decisions import render_tests_distilled_md
        td_md = render_tests_distilled_md(
            result.test_decisions, source_target=source_target
        )
        if td_md:
            lines += [
                "",
                "## Tests Distilled (defensive patterns from the senior test suite)",
                "",
            ]
            # Same preamble-stripping pattern as exemplars: drop the H1 +
            # blockquote so the rendered block nests under the H2 above.
            in_preamble = True
            for line in td_md.splitlines():
                if in_preamble:
                    if line.startswith("#"):
                        continue
                    if line.startswith(">"):
                        continue
                    if line == "":
                        in_preamble = False
                        continue
                lines.append(line)

    if result.pr_decisions is not None and result.pr_decisions.has_signal:
        from hijack.core.pr_archaeology import render_pr_decisions_md
        pr_md = render_pr_decisions_md(
            result.pr_decisions, source_target=source_target
        )
        if pr_md:
            lines += [
                "",
                "## PR Decisions (review concerns + rejected proposals from the senior team)",
                "",
            ]
            # Same preamble-stripping pattern: drop the H1 + blockquote so the
            # rendered block nests under the H2 above.
            in_preamble = True
            for line in pr_md.splitlines():
                if in_preamble:
                    if line.startswith("#"):
                        continue
                    if line.startswith(">"):
                        continue
                    if line == "":
                        in_preamble = False
                        continue
                lines.append(line)

    if result.commit_decisions is not None and result.commit_decisions.has_signal:
        from hijack.core.archaeology import render_commit_decisions_md
        cd_md = render_commit_decisions_md(
            result.commit_decisions, source_target=source_target
        )
        if cd_md:
            lines += [
                "",
                "## Commit Decisions (decision trails recorded in commit messages)",
                "",
            ]
            # Same preamble-stripping pattern as exemplars/test_decisions/pr_decisions:
            # drop the H1 + blockquote so the rendered block nests under the H2 above.
            in_preamble = True
            for line in cd_md.splitlines():
                if in_preamble:
                    if line.startswith("#"):
                        continue
                    if line.startswith(">"):
                        continue
                    if line == "":
                        in_preamble = False
                        continue
                lines.append(line)

    return "\n".join(lines)
