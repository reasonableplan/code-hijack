# ruff: noqa: E501
# 이 파일은 LLM 프롬프트 템플릿을 포함하므로 긴 문자열 리터럴이 본질적.
"""Critic 레이어 — 전체 규칙을 재평가해 중복 제거 + MUST 인플레 보정.

run_full_analysis 뒤에 optional 로 실행된다. 카테고리별로 독립 생성된 규칙들이
(1) 서로 중복되거나 (2) 과장된 MUST 이거나 (3) 너무 일반적이면 제거/강등.

설계 원칙:
- 실패 시 원본 SessionResult 를 그대로 반환 (degradation gracefully)
- 새 규칙을 만들지 않음 — drop / downgrade 만
"""
from __future__ import annotations

import json
import logging

from hijack.core.models import AnalysisRule, CategoryResult, SessionResult
from hijack.llm.base import BaseLLM

logger = logging.getLogger(__name__)


_CRITIC_PROMPT_TEMPLATE = """\
You are a senior reviewer auditing coding rules extracted from a codebase.

Here are all rules extracted across multiple categories:

<rules>
{rules_json}
</rules>

Your job: refine this rule set. Apply three operations:

1. DROP rules that are:
   - Too generic ("write clean code", "be consistent", "write tests")
   - Near-duplicates across categories (same concept phrased differently)
   - Unsupported by concrete ref_files / real examples
   - Subjective preferences without clear design intent

2. DOWNGRADE MUST → SHOULD when:
   - Violation wouldn't actually block a PR (it's a strong preference, not a hard rule)
   - The rule reflects a team convention, not a correctness/security concern
   - MUST should be reserved for ~30-40% of final rules. Inflation suggests weak signal.

3. KEEP high-quality rules as-is (neither drop nor downgrade).

Return a JSON object with this exact structure:

{{
  "keep": ["<exact rule text>", "<exact rule text>", ...],
  "downgrade_to_should": ["<exact rule text>", ...],
  "drop": ["<exact rule text>", ...],
  "notes": "<1-3 sentences of reasoning>"
}}

Rules:
- Every rule in the input MUST appear in exactly one of keep/downgrade_to_should/drop.
- Use the rule text VERBATIM (first line of each rule) — do not paraphrase.
- If you are uncertain about a rule, put it in "keep" (conservative default)."""


async def refine(result: SessionResult, llm: BaseLLM, *, model: str) -> SessionResult:
    """Critic 레이어 — SessionResult 를 받아 정제된 SessionResult 를 반환한다.

    실패 (LLM 호출 실패, JSON 파싱 실패) 시 원본을 그대로 반환.
    """
    all_rules = [
        {"category": cat.category, "rule": rule.rule, "priority": rule.priority}
        for cat in result.categories
        for rule in cat.rules
    ]
    if not all_rules:
        return result

    rules_json = json.dumps(all_rules, ensure_ascii=False, indent=2)
    prompt = _CRITIC_PROMPT_TEMPLATE.format(rules_json=rules_json)

    try:
        raw = await llm.analyze(prompt, model=model)
    except Exception as e:  # noqa: BLE001
        logger.warning("critic LLM 호출 실패 — 원본 반환: %s", e)
        return result

    parsed = _parse_critic_response(raw)
    if parsed is None:
        logger.warning("critic 응답 파싱 실패 — 원본 반환")
        return result

    drop_set = set(parsed.get("drop", []))
    downgrade_set = set(parsed.get("downgrade_to_should", []))

    refined_categories = []
    for cat in result.categories:
        refined_rules: list[AnalysisRule] = []
        for rule in cat.rules:
            if rule.rule in drop_set:
                continue
            if rule.rule in downgrade_set and rule.priority == "MUST":
                rule = AnalysisRule(
                    rule=rule.rule,
                    priority="SHOULD",
                    confidence=rule.confidence,
                    ref_files=rule.ref_files,
                    good_example=rule.good_example,
                    bad_example=rule.bad_example,
                    reason=rule.reason,
                    layer=rule.layer,
                )
            refined_rules.append(rule)

        refined_categories.append(CategoryResult(
            category=cat.category,
            design_intent=cat.design_intent,
            rules=refined_rules,
            anti_patterns=cat.anti_patterns,
            file_type_guides=cat.file_type_guides,
            checklist=cat.checklist,
            raw_llm_output=cat.raw_llm_output,
            error=cat.error,
        ))

    dropped = len(drop_set)
    downgraded = sum(1 for s in downgrade_set if s not in drop_set)
    logger.info(
        "critic: 원본 %d → 최종 %d (drop %d, downgrade %d)",
        len(all_rules),
        sum(len(c.rules) for c in refined_categories),
        dropped,
        downgraded,
    )

    return SessionResult(
        session_id=result.session_id,
        target=result.target,
        model=result.model,
        timestamp=result.timestamp,
        selected_files=result.selected_files,
        categories=refined_categories,
        analysis_duration_seconds=result.analysis_duration_seconds,
        project_structure=result.project_structure,
        files_by_layer=result.files_by_layer,
    )


def _parse_critic_response(raw: str) -> dict | None:
    """critic 응답을 파싱. 실패 시 None."""
    from hijack.core.analyzer import _parse_json, _parse_regex_fallback
    return _parse_json(raw) or _parse_regex_fallback(raw)
