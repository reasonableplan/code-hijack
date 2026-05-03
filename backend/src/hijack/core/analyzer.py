from __future__ import annotations

import asyncio
import datetime
import json
import logging
import re
import time
from pathlib import Path

from hijack.core.docs import render_repo_context
from hijack.core.fetcher import SourceFile
from hijack.core.models import AnalysisRule, CategoryResult, SessionResult
from hijack.core.preprocessor import (
    build_file_summary_for_llm,
    build_preprocess_result,
    select_files_for_category,
)
from hijack.core.prompts import MVP_CATEGORIES, build_category_prompt
from hijack.core.session import create_session_id
from hijack.errors import LLM_002, LLM_003, LLMError
from hijack.llm.api import DEFAULT_MODEL
from hijack.llm.base import BaseLLM

logger = logging.getLogger(__name__)

_BACKOFF_SECONDS = (1.0, 2.0, 4.0)
_REQUIRED_RULE_FIELDS = {"rule", "priority", "layer"}


# ---------------------------------------------------------------------------
# JSON parsing
# ---------------------------------------------------------------------------

def _parse_json(raw: str) -> dict | None:
    """LLM 응답에서 JSON 객체를 파싱한다."""
    raw = raw.strip()
    # 코드 펜스 제거
    if raw.startswith("```"):
        lines = raw.splitlines()
        raw = "\n".join(lines[1:])
        if raw.endswith("```"):
            raw = raw[: raw.rfind("```")]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # 첫 번째 { 부터 마지막 } 까지 추출
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            pass
    return None


def _parse_regex_fallback(raw: str) -> dict | None:
    """JSON 파싱 실패 시 regex 로 JSON 블록을 찾아 재시도한다."""
    match = re.search(r"\{[\s\S]+\}", raw)
    if not match:
        return None
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------------------
# Rule extraction
# ---------------------------------------------------------------------------

def _rules_from_parsed(raw_rules: list[dict]) -> list[AnalysisRule]:
    """파싱된 규칙 목록에서 유효한 AnalysisRule 만 추출한다."""
    rules: list[AnalysisRule] = []
    for item in raw_rules:
        if not isinstance(item, dict):
            continue
        missing = _REQUIRED_RULE_FIELDS - item.keys()
        if missing:
            logger.warning("규칙 필드 누락 %s — 드롭: %s", missing, item.get("rule", "?"))
            continue
        rules.append(
            AnalysisRule(
                rule=item["rule"],
                priority=item.get("priority", "SHOULD"),
                confidence=item.get("confidence", "medium"),
                ref_files=item.get("ref_files", []),
                good_example=item.get("good_example", ""),
                bad_example=item.get("bad_example", ""),
                reason=item.get("reason", ""),
                layer=item.get("layer", "shared"),
            )
        )
    return rules


# ---------------------------------------------------------------------------
# Per-category analysis
# ---------------------------------------------------------------------------

async def _analyze_category(
    category: str,
    preprocess_result,
    llm: BaseLLM,
    model: str,
) -> CategoryResult:
    selected = select_files_for_category(preprocess_result, category)
    summaries = build_file_summary_for_llm(selected)
    repo_context = render_repo_context(preprocess_result.repo_docs)

    try:
        prompt = build_category_prompt(category, summaries, repo_context=repo_context)
    except ValueError as e:
        return _error_result(category, "", str(e))

    raw = ""
    last_error = ""

    for attempt in range(2):
        try:
            raw = await llm.analyze(prompt, model=model)
            last_error = ""
            break
        except LLMError as e:
            last_error = str(e)
            logger.warning("[%s] LLM 호출 실패 (attempt %d): %s", category, attempt + 1, e)
            if attempt < 1:
                await asyncio.sleep(_BACKOFF_SECONDS[attempt])
    else:
        return _error_result(category, raw, f"{LLM_002}: {last_error}")

    parsed = _parse_json(raw) or _parse_regex_fallback(raw)
    if parsed is None:
        logger.warning("[%s] JSON 파싱 실패 — raw 출력 보존", category)
        return _error_result(category, raw, f"{LLM_003}: JSON 및 regex 파싱 실패")

    rules = _rules_from_parsed(parsed.get("rules", []))
    return CategoryResult(
        category=category,
        design_intent=parsed.get("design_intent", ""),
        rules=rules,
        anti_patterns=parsed.get("anti_patterns", []),
        file_type_guides=parsed.get("file_type_guides", {}),
        checklist=parsed.get("checklist", []),
        raw_llm_output=raw,
        error=None,
    )


def _error_result(category: str, raw: str, error: str) -> CategoryResult:
    return CategoryResult(
        category=category,
        design_intent="",
        rules=[],
        anti_patterns=[],
        file_type_guides={},
        checklist=[],
        raw_llm_output=raw,
        error=error,
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def run_full_analysis(
    files: list[SourceFile],
    repo_root: Path,
    *,
    categories: list[str] = MVP_CATEGORIES,
    llm: BaseLLM,
    model: str = DEFAULT_MODEL,
    target: str = "",
    critic: bool = True,
) -> SessionResult:
    """카테고리별 LLM 분석을 실행하고 SessionResult를 반환한다.

    critic=True (기본) 이면 분석 후 critic 레이어가 중복/MUST 인플레를 정제한다.
    실패해도 원본 결과는 보존됨.
    """
    start = time.monotonic()
    preprocess = build_preprocess_result(files, repo_root)

    category_results: list[CategoryResult] = []
    for category in categories:
        result = await _analyze_category(category, preprocess, llm, model)
        category_results.append(result)

    duration = time.monotonic() - start
    session_id = create_session_id(target or str(repo_root))
    files_by_layer = {layer: len(flist) for layer, flist in preprocess.by_layer.items()}

    session = SessionResult(
        session_id=session_id,
        target=target or repo_root.as_posix(),
        model=model,
        timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
        selected_files=[f.path.as_posix() for f in files],
        categories=category_results,
        analysis_duration_seconds=round(duration, 3),
        project_structure=preprocess.project_structure,
        files_by_layer=files_by_layer,
    )

    if critic and any(c.rules for c in category_results):
        from hijack.core.critic import refine
        logger.info("Critic 레이어 실행 중...")
        session = await refine(session, llm, model=model)

    return session
