"""LLM 기반 코드 분석기 — 카테고리별 순차 심층 분석."""

from __future__ import annotations

import logging
import re
import time

from hijack.core.fetcher import SourceFile
from hijack.core.models import AnalysisRule, CategoryResult
from hijack.core.preprocessor import ClassifiedFile, PreprocessResult
from hijack.core.prompts import MVP_CATEGORIES, SYSTEM_PROMPT, build_analysis_prompt
from hijack.llm.base import BaseLLM

logger = logging.getLogger(__name__)

# 카테고리별 관련 파일 역할 매핑
_CATEGORY_ROLES: dict[str, list[str]] = {
    "architecture": ["entry_point", "config", "service", "model", "api"],
    "coding_style": ["service", "model", "api", "entry_point", "other"],
    "api_design": ["api", "auth", "model", "entry_point", "config"],
}

_MAX_FILES_PER_CATEGORY = 15
_MAX_CHARS_PER_FILE = 8000


def _select_files_for_category(
    category: str,
    classified: list[ClassifiedFile],
) -> list[SourceFile]:
    """카테고리에 관련된 파일만 선별한다."""
    roles = _CATEGORY_ROLES.get(category, ["other"])

    scored: list[tuple[int, ClassifiedFile]] = []
    for cf in classified:
        score = roles.index(cf.role) if cf.role in roles else len(roles) + 1
        scored.append((score, cf))

    scored.sort(key=lambda x: x[0])
    return [cf.file for _, cf in scored[:_MAX_FILES_PER_CATEGORY]]


def _format_files_for_prompt(files: list[SourceFile]) -> str:
    """소스 파일을 LLM 프롬프트에 포함할 형식으로 변환."""
    parts: list[str] = []
    for f in files:
        content = f.content
        if len(content) > _MAX_CHARS_PER_FILE:
            content = content[:_MAX_CHARS_PER_FILE] + "\n... (잘림)"
        parts.append(
            f"### {f.path} ({f.language})\n"
            f"```{f.language}\n{content}\n```\n"
        )
    return "\n".join(parts)


def _parse_rules_from_markdown(text: str) -> list[AnalysisRule]:
    """LLM 마크다운 출력에서 규칙을 추출한다."""
    rules: list[AnalysisRule] = []

    rule_pattern = re.compile(
        r'\d+\.\s+\*\*\[(MUST|SHOULD)\]\s*(.*?)\*\*',
        re.MULTILINE,
    )
    matches = list(rule_pattern.finditer(text))

    for i, match in enumerate(matches):
        priority = match.group(1)
        rule_text = match.group(2).strip()

        # 이 규칙과 다음 규칙 사이의 섹션 추출
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        section = text[start:end]

        # 참조 파일 추출
        ref_files: list[str] = []
        for ref_match in re.finditer(r'📁\s*(?:Reference|참조):\s*(.+)', section):
            ref_files.append(ref_match.group(1).strip())

        # ✅/❌ 예시 코드 추출
        good = ""
        bad = ""
        good_match = re.search(r'✅.*?```\w*\n(.*?)```', section, re.DOTALL)
        bad_match = re.search(r'❌.*?```\w*\n(.*?)```', section, re.DOTALL)
        if good_match:
            good = good_match.group(1).strip()
        if bad_match:
            bad = bad_match.group(1).strip()

        # 이유 추출
        reason = ""
        reason_match = re.search(r'(?:Reason|이유):\s*(.+)', section)
        if reason_match:
            reason = reason_match.group(1).strip()

        rules.append(AnalysisRule(
            rule=rule_text,
            priority=priority,
            ref_files=ref_files,
            good_example=good,
            bad_example=bad,
            reason=reason,
        ))

    return rules


def _parse_checklist(text: str) -> list[str]:
    """마크다운에서 체크리스트 항목을 추출한다."""
    return [m.group(1).strip() for m in re.finditer(r'- \[ \]\s*(.+)', text)]


def _parse_design_intent(text: str) -> str:
    """설계 의도 섹션을 추출한다."""
    match = re.search(
        r'###?\s*(?:Design Intent|설계 의도)\s*\n(.*?)(?=\n###?\s|\Z)',
        text,
        re.DOTALL,
    )
    return match.group(1).strip() if match else ""


async def analyze_category(
    category: str,
    llm: BaseLLM,
    preprocess_result: PreprocessResult,
) -> CategoryResult:
    """하나의 카테고리를 LLM으로 분석한다.

    Args:
        category: MVP_CATEGORIES 중 하나.
        llm: 사용할 LLM 클라이언트.
        preprocess_result: 전처리된 파일 데이터.

    Returns:
        구조화된 분석 결과.
    """
    files = _select_files_for_category(category, preprocess_result.classified)
    files_content = _format_files_for_prompt(files)

    prompt = build_analysis_prompt(
        category=category,
        files_content=files_content,
        structure_map=preprocess_result.structure_map,
    )

    logger.info("%s 분석 중 (%d개 파일)...", category, len(files))
    start = time.time()
    raw_output = await llm.analyze(SYSTEM_PROMPT, prompt)
    duration = time.time() - start
    logger.info("  %s 분석 완료 (%.1f초)", category, duration)

    # LLM 출력에서 구조화 데이터 파싱
    rules = _parse_rules_from_markdown(raw_output)
    checklist = _parse_checklist(raw_output)
    design_intent = _parse_design_intent(raw_output)

    if not rules:
        logger.warning(
            "%s 분석에서 규칙을 추출하지 못함 (%d자). raw 출력은 디버깅용으로 저장됨.",
            category, len(raw_output),
        )

    return CategoryResult(
        category=category,
        design_intent=design_intent,
        rules=rules,
        checklist=checklist,
        raw_llm_output=raw_output,
    )


async def run_full_analysis(
    llm: BaseLLM,
    preprocess_result: PreprocessResult,
    categories: list[str] | None = None,
) -> list[CategoryResult]:
    """전체 카테고리를 순차적으로 분석한다.

    Args:
        llm: LLM 클라이언트.
        preprocess_result: 전처리 데이터.
        categories: 분석할 카테고리 목록 (기본: MVP_CATEGORIES).
    """
    cats = categories or MVP_CATEGORIES
    results: list[CategoryResult] = []
    for cat in cats:
        result = await analyze_category(cat, llm, preprocess_result)
        results.append(result)
    return results
