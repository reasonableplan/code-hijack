from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from hijack.core.evidence import (
    compute_evidence_metrics,
    downgrade_speculative_rules,
    render_metrics_md,
)
from hijack.core.models import AnalysisRule, CategoryResult, Evidence, ForesightCard, SessionResult
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


def render_layer_md(
    layer: str,
    categories: list[CategoryResult],
    style_fingerprint: Any = None,
    repo_nature: str = "library",
) -> str:
    """Render the per-layer markdown file.

    `style_fingerprint`, when provided, contributes a "Codebase Invariants"
    section appended after the rules — Phase G2 statistical patterns
    (negative space, symbol substitutions) that the rule extractor doesn't
    capture textually.
    """
    rules = [r for cat in categories for r in cat.rules if r.layer == layer]
    lines = [
        f"# {layer.title()} Layer Rules",
        "",
        f"> 이 규칙들은 `{repo_nature}` 맥락에서 추출됨",
        "",
        f"> {_LAYER_CONTEXT.get(layer, '')}",
        "",
        f"**Total rules**: {len(rules)}",
        "",
    ]
    if not rules:
        lines += [f"*No rules tagged `{layer}` in this session.*", ""]
    else:
        by_category: dict[str, list[AnalysisRule]] = {}
        for cat in categories:
            for r in cat.rules:
                if r.layer == layer:
                    by_category.setdefault(cat.category, []).append(r)

        for category, cat_rules in by_category.items():
            lines += [f"## {category.replace('_', ' ').title()}", ""]
            for rule in cat_rules:
                lines += _render_rule(rule)

    if style_fingerprint is not None:
        from hijack.core.style_fingerprint import render_layer_invariants_md
        invariants_md = render_layer_invariants_md(style_fingerprint)
        if invariants_md:
            lines.append(invariants_md)

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
        f"> 이 규칙들은 `{result.repo_nature}` 맥락에서 추출됨",
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
        f"이 규칙들은 `{result.repo_nature}` 맥락에서 추출됨 (파일 헤더 참조).",
        "",
        "MUST 규칙은 추출 맥락(파일 헤더의 레포 성격 참조)이 성립할 때 적용하라.",
        "맥락이 다르면 일탈 가능하되 이유를 명시하라.",
        "corroborated/speculative rationale 규칙과 foresight 카드는 강제 아닌 고려 사항이다.",
        "",
        "Scope tags: rules without a tag are `cross_project` (apply broadly).",
        "`[framework_internal]` rules describe THIS codebase only — skip when reusing.",
        "`[domain_specific]` rules need re-evaluation in a different domain.",
        "",
        "긴 세션 주의: 규칙 준수율은 세션 내 산출물이 쌓일수록 감쇠한다 (함수당 -5.6%,",
        "arxiv 2605.10039). 함수 여러 개를 연속 생성했다면 MUST 규칙을 재확인하고 작성하라.",
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


def render_foresight_md(cards: list[ForesightCard], repo_nature: str) -> str:
    """ForesightCard 목록을 foresight.md 마크다운으로 렌더링한다.

    speculative 카드에는 "강제 아님" 표시. corroborated 에는 없음.
    """
    lines = [
        f"# Foresight — `{repo_nature}` 맥락에서 추론된 설계 의도",
        "",
        "> ForesightCard 는 LLM 추론 기반 가설이다. 강제 제약이 아닌 고려 사항.",
        "",
    ]
    for card in cards:
        if card.tier == "corroborated":
            lines.append(f"## [corroborated] {card.hypothesis}")
        else:
            lines.append(f"## [speculative — 강제 아님] {card.hypothesis}")
        lines.append("")
        if card.signals:
            lines.append("**뒷받침 신호**:")
            for s in card.signals:
                lines.append(f"- {s}")
            lines.append("")
        lines.append(f"**반증 조건**: {card.falsification}")
        lines.append("")
    return "\n".join(lines)


def _render_rule_compact(rule: AnalysisRule) -> list[str]:
    """One system-prompt entry: rule header + inline ✅/❌/ref/because (only if present).

    The `because:` line surfaces the strongest verbatim quote so a downstream
    agent reading this prompt sees the senior's actual reasoning, not just
    the rule's paraphrased gist. SHA is intentionally omitted — the consumer
    can't follow it; they just need the why.
    """
    out = [f"- [{rule.layer}]{_scope_tag(rule)} {rule.rule}"]
    good, bad = _distinguishing_preview(rule.good_example, rule.bad_example)
    if good:
        out.append(f"  ✅ {good}")
    if bad:
        out.append(f"  ❌ {bad}")
    if rule.ref_files:
        out.append(f"  ref: {rule.ref_files[0]}")
    because_line = _because_line(rule)
    if because_line:
        out.append(because_line)
    if rule.probe is not None and rule.probe.verdict == "discriminated":
        out.append(f"  probe: behavior-confirmed ({rule.probe.model})")
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


def _meaningful_lines(code: str) -> list[str]:
    """blank / `#` / `//` / docstring opener 를 제외한 코드 라인 목록."""
    if not code:
        return []
    out: list[str] = []
    for raw in code.split("\n"):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#") or line.startswith("//"):
            continue
        if line.startswith('"""') or line.startswith("'''"):
            continue
        out.append(line)
    return out


def _truncate_line(line: str, max_len: int) -> str:
    if len(line) > max_len:
        return line[: max_len - 1] + "…"
    return line


def _distinguishing_preview(good: str, bad: str, max_len: int = 100) -> tuple[str, str]:
    """system-prompt 의 ✅/❌ 비교가 의미를 가지도록 차이나는 첫 줄을 선택.

    기존 `_signature_preview` 는 양쪽 모두 첫 의미 있는 라인만 추출 — 둘 다
    같은 시그니처 (`class XxxService:`, `class XxxRequest(BaseModel):`) 로 시작하면
    ✅/❌ 비교가 무의미해짐 (벤치마크에서 4-5 규칙이 같은 라인 출력). 이 함수는
    두 코드를 동시에 보고 처음으로 달라지는 라인을 선택해 비교 가치를 살린다.

    Returns: (good_preview, bad_preview). 둘 다 같은 시점의 차이나는 라인.
    공백/주석/docstring 은 양쪽 동기로 skip.
    """
    good_lines = _meaningful_lines(good)
    bad_lines = _meaningful_lines(bad)
    if not good_lines and not bad_lines:
        return "", ""
    if not good_lines:
        return "", _truncate_line(bad_lines[0], max_len)
    if not bad_lines:
        return _truncate_line(good_lines[0], max_len), ""
    # 첫 줄부터 다르면 그대로 사용 — 기존 동작과 동일
    if good_lines[0] != bad_lines[0]:
        return _truncate_line(good_lines[0], max_len), _truncate_line(bad_lines[0], max_len)
    # 같은 prefix — 처음 달라지는 줄까지 진행
    i = 0
    while (
        i < len(good_lines)
        and i < len(bad_lines)
        and good_lines[i] == bad_lines[i]
    ):
        i += 1
    # i 가 한쪽 끝에 닿았을 수도 있음 — 가능한 라인 선택
    good_line = good_lines[i] if i < len(good_lines) else good_lines[-1]
    bad_line = bad_lines[i] if i < len(bad_lines) else bad_lines[-1]
    return _truncate_line(good_line, max_len), _truncate_line(bad_line, max_len)


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

# MUST 캘리브레이션 임계값. 시니어 코드베이스에서 진짜 PR 거부 수준 규칙은
# 통상 30-40% 비율. 60% 초과면 LLM 이 SHOULD 도 MUST 로 부풀린 정황.
# 통계 안정 위해 작은 샘플은 검사 생략.
_MUST_RATIO_WARN = 0.40
_MUST_RATIO_CATEGORY_HIGH = 0.50
_MUST_CHECK_MIN_RULES = 5
_MUST_CHECK_MIN_CATEGORY_RULES = 3


def _check_must_calibration(result: SessionResult) -> None:
    """MUST 비율 lint — overall > 40% 거나 카테고리 > 50% 시 stderr 경고.

    skill 모드는 critic 단계가 optional 이라 calibration 표류 자동 감지 안 됨.
    write_output 시점에 체크해 표류가 즉시 가시화되도록 한다.
    """
    all_rules = [r for c in result.categories for r in c.rules]
    if len(all_rules) < _MUST_CHECK_MIN_RULES:
        return

    overall_must = sum(1 for r in all_rules if r.priority == "MUST")
    overall_ratio = overall_must / len(all_rules)

    high_cats: list[tuple[str, int, int, float]] = []
    for c in result.categories:
        cat_total = len(c.rules)
        if cat_total < _MUST_CHECK_MIN_CATEGORY_RULES:
            continue
        cat_must = sum(1 for r in c.rules if r.priority == "MUST")
        cat_ratio = cat_must / cat_total
        if cat_ratio > _MUST_RATIO_CATEGORY_HIGH:
            high_cats.append((c.category, cat_must, cat_total, cat_ratio))

    if overall_ratio <= _MUST_RATIO_WARN and not high_cats:
        return

    lines = ["[WARN] MUST 비율 캘리브레이션 — target 30-40%, MUST 는 위반 시 PR 거부 수준만"]
    lines.append(
        f"  overall: {overall_must}/{len(all_rules)} MUST ({overall_ratio:.0%})"
    )
    for cat, must, total, ratio in high_cats:
        lines.append(
            f"  {cat}: {must}/{total} MUST ({ratio:.0%}) — 일부 SHOULD 로 다운그레이드 검토"
        )
    print("\n".join(lines), file=sys.stderr)


def write_output(result: SessionResult, output_base: Path) -> None:
    """세션별 raw 파일 + integrated 통합 파일을 모두 작성한다.

    Auto-downgrades speculative MUST rules (evidence not verified-cited) to
    SHOULD before any rendering, so raw session.json and integrated docs agree.
    """
    downgraded = downgrade_speculative_rules(result)
    if downgraded:
        print(
            f"[INFO] {downgraded} non-cited MUST rule(s) auto-downgraded to SHOULD "
            "(evidence chain not verified)",
            file=sys.stderr,
        )

    session_dir = output_base / result.session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    _write_session_files(result, session_dir)
    _write_integrated_files(result, output_base / "integrated")
    _check_must_calibration(result)


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
    if result.foresight_cards:
        (session_dir / "foresight.md").write_text(
            render_foresight_md(result.foresight_cards, result.repo_nature),
            encoding="utf-8",
        )


def _write_integrated_files(result: SessionResult, integrated_dir: Path) -> None:
    integrated_dir.mkdir(parents=True, exist_ok=True)

    for layer in _LAYERS:
        fname = _LAYER_FILE_NAMES[layer]
        fp = result.style_fingerprints.get(layer) if result.style_fingerprints else None
        (integrated_dir / fname).write_text(
            render_layer_md(
                layer,
                result.categories,
                style_fingerprint=fp,
                repo_nature=result.repo_nature,
            ),
            encoding="utf-8",
        )

    (integrated_dir / "CLAUDE.md").write_text(
        render_claude_md_entrypoint(result), encoding="utf-8"
    )
    (integrated_dir / "system-prompt.md").write_text(
        render_system_prompt_md(result), encoding="utf-8"
    )

    if result.foresight_cards:
        (integrated_dir / "foresight.md").write_text(
            render_foresight_md(result.foresight_cards, result.repo_nature),
            encoding="utf-8",
        )

    if result.exemplars:
        from hijack.core.exemplars import render_exemplars_md
        md = render_exemplars_md(result.exemplars, source_target=result.target)
        if md:
            (integrated_dir / "exemplars.md").write_text(md, encoding="utf-8")

    if result.test_decisions is not None and result.test_decisions.has_signal:
        from hijack.core.test_decisions import render_tests_distilled_md
        md = render_tests_distilled_md(result.test_decisions, source_target=result.target)
        if md:
            (integrated_dir / "tests-distilled.md").write_text(md, encoding="utf-8")

    if result.pr_decisions is not None and result.pr_decisions.has_signal:
        from hijack.core.pr_archaeology import render_pr_decisions_md
        md = render_pr_decisions_md(result.pr_decisions, source_target=result.target)
        if md:
            (integrated_dir / "pr-decisions.md").write_text(md, encoding="utf-8")

    if result.commit_decisions is not None and result.commit_decisions.has_signal:
        from hijack.core.archaeology import render_commit_decisions_md
        md = render_commit_decisions_md(result.commit_decisions, source_target=result.target)
        if md:
            (integrated_dir / "commit-decisions.md").write_text(md, encoding="utf-8")


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
    if rule.probe is not None and rule.probe.verdict == "discriminated":
        lines += [
            f"**Probe**: behavior-confirmed — control: {rule.probe.control_behavior}"
            f" / treatment: {rule.probe.treatment_behavior}",
            "",
        ]
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
