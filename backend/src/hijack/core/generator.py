from __future__ import annotations

import json
from pathlib import Path

from hijack.core.evidence import compute_evidence_metrics, render_metrics_md
from hijack.core.models import AnalysisRule, CategoryResult, Evidence, SessionResult
from hijack.core.preprocessor import build_layer_stats

# Strength order for evidence — higher is stronger. Used both to pick the
# single citation surfaced as the system-prompt `because:` line and to break
# ties when sorting evidence chronologically (entries without a date fall back
# to this order, with stronger kinds shown first).
_KIND_PRIORITY: dict[str, int] = {"revert": 3, "doc": 2, "commit": 1}

# Display labels for the Evidence chain section. Plain text, no emojis —
# matches the project's no-emoji convention.
_INTENT_LABELS: dict[str, str] = {
    "rejection": "REJECTION",
    "constraint": "CONSTRAINT",
    "incident": "INCIDENT",
    "preference": "PREFERENCE",
}
_KIND_LABELS: dict[str, str] = {
    "commit": "COMMIT",
    "revert": "REVERT",
    "doc": "DOC",
}

_LAYERS = ["frontend", "backend", "db", "devops", "shared"]

_LAYER_FILE_NAMES: dict[str, str] = {
    "frontend": "frontend.md",
    "backend": "backend.md",
    "db": "database.md",
    "devops": "devops.md",
    "shared": "shared.md",
}

_LAYER_CONTEXT: dict[str, str] = {
    "frontend": "프론트엔드 파일 작업 (.tsx/.jsx, frontend/) → 이 파일 + shared.md",
    "backend": "백엔드 파일 작업 (.py, backend/) → 이 파일 + shared.md",
    "db": "DB 파일 작업 (migrations/, models/) → 이 파일 + shared.md",
    "devops": "CI/인프라 작업 (.github/, Dockerfile) → 이 파일 + shared.md",
    "shared": "공통 규칙 (레이어 무관) → 모든 작업에 적용",
}


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------

def render_meta_md(result: SessionResult) -> str:
    lines = [
        "# Analysis Metadata",
        "",
        f"- **Session ID**: `{result.session_id}`",
        f"- **Target**: {result.target}",
        f"- **Model**: `{result.model}`",
        f"- **Timestamp**: {result.timestamp}",
        f"- **Duration**: {result.analysis_duration_seconds:.1f}s",
        f"- **Files analyzed**: {len(result.selected_files)}",
        "",
        "## Selected Files",
        "",
    ]
    for f in result.selected_files:
        lines.append(f"- `{f}`")
    lines += [
        "",
        "## Layer Distribution",
        "",
        "```",
        build_layer_stats(result.files_by_layer),
        "```",
        "",
        "## Project Structure",
        "",
        "```",
        result.project_structure,
        "```",
        "",
        "## Category Results",
        "",
    ]
    for cat in result.categories:
        status = "✅" if cat.error is None else f"❌ {cat.error}"
        rule_count = len(cat.rules)
        lines.append(f"- **{cat.category}**: {rule_count} rules {status}")

    # Scope distribution — informs how much auto-applicable signal is in the
    # session (HarnessAI integration only auto-applies cross_project rules).
    scope_counts: dict[str, int] = {}
    for cat in result.categories:
        for rule in cat.rules:
            key = rule.scope or "cross_project"
            scope_counts[key] = scope_counts.get(key, 0) + 1
    if scope_counts:
        lines += ["", "## Scope Distribution", ""]
        total = sum(scope_counts.values())
        for scope_key in ("cross_project", "framework_internal", "domain_specific"):
            n = scope_counts.get(scope_key, 0)
            pct = (n * 100 // total) if total else 0
            lines.append(f"- **{scope_key}**: {n} ({pct}%)")

    # Evidence coverage — Phase A's reason field grounding visualised.
    metrics_block = render_metrics_md(compute_evidence_metrics(result))
    if metrics_block:
        lines += ["", metrics_block]

    return "\n".join(lines)


def render_category_md(cat: CategoryResult) -> str:
    lines = [
        f"# {cat.category.replace('_', ' ').title()} Analysis",
        "",
    ]
    if cat.error:
        lines += [f"> ⚠️ Analysis failed: {cat.error}", ""]
        if cat.raw_llm_output:
            lines += ["## Raw LLM Output", "", "```", cat.raw_llm_output[:2000], "```"]
        return "\n".join(lines)

    lines += [
        "## Design Intent",
        "",
        cat.design_intent,
        "",
        f"## Rules ({len(cat.rules)})",
        "",
    ]
    for rule in cat.rules:
        lines += _render_rule(rule)

    if cat.anti_patterns:
        lines += ["## Anti-Patterns", ""]
        for ap in cat.anti_patterns:
            lines += [
                f"### {ap.get('pattern', '?')}",
                "",
                f"**Why**: {ap.get('reason', '')}",
                "",
                f"**Alternative**: {ap.get('alternative', '')}",
                "",
            ]

    if cat.file_type_guides:
        lines += ["## File-Type Guides", ""]
        for ft, guide in cat.file_type_guides.items():
            lines += [f"### {ft}", "", guide, ""]

    if cat.checklist:
        lines += ["## Checklist", ""]
        for item in cat.checklist:
            lines.append(f"- [ ] {item}")
        lines.append("")

    return "\n".join(lines)


def render_layer_md(layer: str, categories: list[CategoryResult]) -> str:
    rules = [r for cat in categories for r in cat.rules if r.layer == layer]
    lines = [
        f"# {layer.title()} Layer Rules",
        "",
        f"> {_LAYER_CONTEXT.get(layer, '')}",
        "",
        f"**Total rules**: {len(rules)}",
        "",
    ]
    if not rules:
        lines += [f"*No rules tagged `{layer}` in this session.*", ""]
        return "\n".join(lines)

    by_category: dict[str, list[AnalysisRule]] = {}
    for cat in categories:
        for r in cat.rules:
            if r.layer == layer:
                by_category.setdefault(cat.category, []).append(r)

    for category, cat_rules in by_category.items():
        lines += [f"## {category.replace('_', ' ').title()}", ""]
        for rule in cat_rules:
            lines += _render_rule(rule)

    return "\n".join(lines)


def render_claude_md_entrypoint(result: SessionResult) -> str:
    must_rules = [
        r
        for cat in result.categories
        for r in cat.rules
        if r.priority == "MUST"
    ][:10]

    lines = [
        "# Code Style Rules",
        "",
        f"> Generated by code-hijack from `{result.target}`",
        f"> Session: `{result.session_id}` | Model: `{result.model}`",
        "",
        "## Layer Guide",
        "",
        "Load the relevant layer file based on what you're working on:",
        "",
    ]
    for layer, ctx in _LAYER_CONTEXT.items():
        fname = _LAYER_FILE_NAMES.get(layer, f"{layer}.md")
        lines.append(f"- **{layer}**: {ctx} ([{fname}]({fname}))")

    lines += [
        "",
        "## Top MUST Rules (All Layers)",
        "",
        f"*{len(must_rules)} most critical rules across all categories:*",
        "",
    ]
    for rule in must_rules:
        lines.append(f"- **[{rule.layer}/{rule.priority}]**{_scope_tag(rule)} {rule.rule}")

    if result.exemplars:
        lines += [
            "",
            "See `exemplars.md` for representative senior code to match.",
        ]

    return "\n".join(lines)


def render_system_prompt_md(result: SessionResult) -> str:
    must_rules = [r for cat in result.categories for r in cat.rules if r.priority == "MUST"]
    should_rules = [r for cat in result.categories for r in cat.rules if r.priority == "SHOULD"]

    lines = [
        "# System Prompt",
        "",
        f"You are a senior developer working on `{result.target}`.",
        "Follow these coding rules extracted from the codebase analysis.",
        "When writing code, treat MUST rules as non-negotiable constraints.",
        "",
        "Scope tags: rules without a tag are `cross_project` (apply broadly).",
        "`[framework_internal]` rules describe THIS codebase only — skip when reusing.",
        "`[domain_specific]` rules need re-evaluation in a different domain.",
        "",
        "## MUST Rules",
        "",
    ]
    for rule in must_rules:
        lines.extend(_render_rule_compact(rule))

    if should_rules:
        lines += ["", "## SHOULD Rules", ""]
        for rule in should_rules:
            lines.extend(_render_rule_compact(rule))

    lines += [
        "",
        "## Anti-Patterns to Avoid",
        "",
    ]
    for cat in result.categories:
        for ap in cat.anti_patterns:
            pattern = ap.get("pattern", "")
            if pattern:
                lines.append(f"- {pattern}")

    if result.exemplars:
        lines += [
            "",
            "Match the rhythm of `exemplars.md` (representative senior functions).",
        ]

    return "\n".join(lines)


def _render_rule_compact(rule: AnalysisRule) -> list[str]:
    """One system-prompt entry: rule header + inline ✅/❌/ref/because (only if present).

    The `because:` line surfaces the strongest verbatim quote so a downstream
    agent reading this prompt sees the senior's actual reasoning, not just
    the rule's paraphrased gist. SHA is intentionally omitted — the consumer
    can't follow it; they just need the why.
    """
    out = [f"- [{rule.layer}]{_scope_tag(rule)} {rule.rule}"]
    good = _signature_preview(rule.good_example)
    bad = _signature_preview(rule.bad_example)
    if good:
        out.append(f"  ✅ {good}")
    if bad:
        out.append(f"  ❌ {bad}")
    if rule.ref_files:
        out.append(f"  ref: {rule.ref_files[0]}")
    because_line = _because_line(rule)
    if because_line:
        out.append(because_line)
    return out


def _because_line(rule: AnalysisRule, *, max_quote_len: int = 100) -> str:
    """Build the inline `because:` summary, or "" when there's nothing to show."""
    strongest = _strongest_evidence(rule.evidence)
    if strongest is None:
        return ""
    quote = (strongest.quote or strongest.headline or "").strip()
    if not quote:
        return ""
    if len(quote) > max_quote_len:
        quote = quote[: max_quote_len - 1].rstrip() + "…"
    intent_tag = _INTENT_LABELS.get(strongest.intent_kind or "", "")
    suffix = f" [{intent_tag}]" if intent_tag else ""
    return f"  because: '{quote}'{suffix}"


def _signature_preview(code: str, max_len: int = 100) -> str:
    """Pick the first meaningful line of a code example for inline system-prompt use.

    Skips blank lines, comments, and docstring openers (\"\"\" / ''').
    Truncates with `…` past max_len. Returns "" so the caller can drop the line.
    """
    if not code:
        return ""
    for raw_line in code.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            continue
        if line.startswith('"""') or line.startswith("'''"):
            continue
        if len(line) > max_len:
            line = line[: max_len - 1] + "…"
        return line
    return ""


def _scope_tag(rule: AnalysisRule) -> str:
    """Return a leading-space tag like ` [framework_internal]`, or "" for cross_project.

    cross_project is the default — omitting the tag avoids visual noise.
    """
    scope = rule.scope or "cross_project"
    if scope == "cross_project":
        return ""
    return f" [{scope}]"


# ---------------------------------------------------------------------------
# File writing
# ---------------------------------------------------------------------------

def write_output(result: SessionResult, output_base: Path) -> None:
    """세션별 raw 파일 + integrated 통합 파일을 모두 작성한다."""
    session_dir = output_base / result.session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    _write_session_files(result, session_dir)
    _write_integrated_files(result, output_base / "integrated")


def _write_session_files(result: SessionResult, session_dir: Path) -> None:
    (session_dir / "meta.md").write_text(render_meta_md(result), encoding="utf-8")
    (session_dir / "session.json").write_text(
        json.dumps(result.to_json(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    for cat in result.categories:
        (session_dir / f"{cat.category}.md").write_text(
            render_category_md(cat), encoding="utf-8"
        )


def _write_integrated_files(result: SessionResult, integrated_dir: Path) -> None:
    integrated_dir.mkdir(parents=True, exist_ok=True)

    for layer in _LAYERS:
        fname = _LAYER_FILE_NAMES[layer]
        (integrated_dir / fname).write_text(
            render_layer_md(layer, result.categories), encoding="utf-8"
        )

    (integrated_dir / "CLAUDE.md").write_text(
        render_claude_md_entrypoint(result), encoding="utf-8"
    )
    (integrated_dir / "system-prompt.md").write_text(
        render_system_prompt_md(result), encoding="utf-8"
    )

    if result.exemplars:
        from hijack.core.exemplars import render_exemplars_md
        md = render_exemplars_md(result.exemplars, source_target=result.target)
        if md:
            (integrated_dir / "exemplars.md").write_text(md, encoding="utf-8")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _render_rule(rule: AnalysisRule) -> list[str]:
    scope = rule.scope or "cross_project"
    lines = [
        f"### {rule.rule}",
        "",
        f"**Priority**: `{rule.priority}` | **Confidence**: `{rule.confidence}`"
        f" | **Layer**: `{rule.layer}` | **Scope**: `{scope}`",
        "",
        f"**Why**: {rule.reason}",
        "",
    ]
    if rule.ref_files:
        lines += [f"**Reference**: {', '.join(f'`{f}`' for f in rule.ref_files)}", ""]
    if rule.good_example:
        lines += ["**✅ Good**:", "```", rule.good_example, "```", ""]
    if rule.bad_example:
        lines += ["**❌ Bad**:", "```", rule.bad_example, "```", ""]
    if rule.evidence:
        lines += render_evidence_chain(rule.evidence)
    return lines


def render_evidence_chain(evidence: list[Evidence]) -> list[str]:
    """Render the Evidence chain section under a rule.

    Sorted chronologically (oldest first) so the reader sees the *story arc*:
    a feature commit → revert → ADR sequence reads as a decision narrative.
    Entries without a date fall to the bottom, ordered by kind strength so
    the strongest signal (revert > doc > commit) still surfaces first there.
    """
    out = ["**Evidence**:", ""]
    for i, e in enumerate(_sort_evidence(evidence), start=1):
        intent_tag = _INTENT_LABELS.get(e.intent_kind or "", "")
        kind_tag = _KIND_LABELS.get(e.kind, e.kind.upper())
        header_tag = f"[{intent_tag}]" if intent_tag else f"[{kind_tag}]"
        date_part = f" ({e.date[:10]})" if e.date else ""
        ref_part = f"`{e.ref}`" if e.ref else ""
        headline = e.headline or "(no headline)"
        out.append(f"{i}. {header_tag} · {kind_tag} {ref_part}{date_part} — {headline}")
        if e.quote:
            for line in e.quote.splitlines():
                out.append(f"   > {line}" if line.strip() else "   >")
        out.append("")
    return out


def _sort_evidence(evidence: list[Evidence]) -> list[Evidence]:
    def key(e: Evidence) -> tuple[int, str, int]:
        # Primary sort: dated entries before undated. Among dated: ascending.
        # Among undated: by kind strength descending (negate priority).
        has_date = 0 if e.date else 1
        date_key = e.date or ""
        kind_rank = -_KIND_PRIORITY.get(e.kind, 0)
        return (has_date, date_key, kind_rank)

    return sorted(evidence, key=key)


def _strongest_evidence(evidence: list[Evidence]) -> Evidence | None:
    """Pick the single most informative entry for one-line summaries.

    Strength order: revert > doc > commit. Date is ignored — for the system-
    prompt `because:` line we want the strongest *signal*, not the latest one.
    """
    if not evidence:
        return None
    return max(evidence, key=lambda e: _KIND_PRIORITY.get(e.kind, 0))
