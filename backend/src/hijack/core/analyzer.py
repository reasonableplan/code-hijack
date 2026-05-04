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
from hijack.core.models import (
    EVIDENCE_HEADLINE_MAX,
    EVIDENCE_KIND_VALUES,
    EVIDENCE_QUOTE_MAX,
    INTENT_KIND_VALUES,
    AnalysisRule,
    CategoryResult,
    Evidence,
    SessionResult,
)
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

def _rules_from_parsed(
    raw_rules: list[dict],
    *,
    valid_shas: set[str] | None = None,
    valid_doc_paths: set[str] | None = None,
    sha_to_date: dict[str, str] | None = None,
) -> list[AnalysisRule]:
    """파싱된 규칙 목록에서 유효한 AnalysisRule 만 추출한다.

    Per-rule, the embedded `evidence` list is filtered: entries whose `kind` /
    `intent_kind` are out of enum, or whose `ref` doesn't match the truth pool
    (SHA prefix-match for commit/revert; exact path match for doc) are dropped.
    Surviving evidence has its `date` populated by SHA lookup and its
    `headline` / `quote` truncated to the configured caps.

    Empty pools (no git history / no docs collected) disable the corresponding
    validation — useful for tests and non-git targets where any LLM-extracted
    citation is best-effort.
    """
    valid_shas = valid_shas if valid_shas is not None else set()
    valid_doc_paths = valid_doc_paths if valid_doc_paths is not None else set()
    sha_to_date = sha_to_date if sha_to_date is not None else {}

    rules: list[AnalysisRule] = []
    for item in raw_rules:
        if not isinstance(item, dict):
            continue
        missing = _REQUIRED_RULE_FIELDS - item.keys()
        if missing:
            logger.warning("규칙 필드 누락 %s — 드롭: %s", missing, item.get("rule", "?"))
            continue
        evidence = _evidence_from_parsed(
            item.get("evidence", []),
            valid_shas=valid_shas,
            valid_doc_paths=valid_doc_paths,
            sha_to_date=sha_to_date,
        )
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
                evidence=evidence,
            )
        )
    return rules


def _evidence_from_parsed(
    raw_evidence: list,
    *,
    valid_shas: set[str],
    valid_doc_paths: set[str],
    sha_to_date: dict[str, str],
) -> list[Evidence]:
    """Validate, truncate, and date-stamp evidence entries from LLM output.

    Validation order per entry:
      1. Must be a dict.
      2. `kind` ∈ EVIDENCE_KIND_VALUES (else drop).
      3. `intent_kind`: keep if ∈ INTENT_KIND_VALUES, else None.
         A `kind="revert"` entry is, by definition, a rejection — coerce its
         intent_kind to "rejection" regardless of what the LLM emitted.
      4. `ref` non-empty (else drop).
      5. `ref` matches truth pool — SHA prefix for commit/revert, exact path
         for doc. Empty pool disables the check (best-effort).
      6. Sanitize text:
         - headline: collapse whitespace runs (kills newlines that would break
           the single-line bullet rendering), then truncate to 120 chars.
         - quote: strip outer whitespace then truncate to 500 chars. A quote
           that's whitespace-only collapses to "" so the renderer's truthiness
           check skips emitting a hollow blockquote.
      7. Drop the entry if BOTH headline and quote are empty post-sanitize —
         nothing useful to render.
      8. Populate `date` from sha_to_date if commit/revert and known.
    """
    if not isinstance(raw_evidence, list):
        return []

    out: list[Evidence] = []
    for raw in raw_evidence:
        if not isinstance(raw, dict):
            continue
        kind = raw.get("kind")
        if kind not in EVIDENCE_KIND_VALUES:
            continue
        ref = (raw.get("ref") or "").strip()
        if not ref:
            continue

        date: str | None = None
        if kind in ("commit", "revert"):
            full_sha = _resolve_sha(ref, valid_shas)
            if valid_shas and full_sha is None:
                # Hallucinated SHA — drop. classify_rule will surface it as
                # fake_citation only if the whole rule's evidence collapses.
                continue
            if full_sha is not None:
                date = sha_to_date.get(full_sha)
                ref = full_sha[:12]  # normalise to a 12-char SHA prefix
        elif kind == "doc":
            if valid_doc_paths and ref not in valid_doc_paths:
                continue

        if kind == "revert":
            # A revert IS a rejection — definitional. Override LLM disagreement.
            intent_kind: str | None = "rejection"
        else:
            intent_kind_raw = raw.get("intent_kind")
            intent_kind = (
                intent_kind_raw if intent_kind_raw in INTENT_KIND_VALUES else None
            )

        # Collapse whitespace in headline so a multi-line subject can't break
        # the single-line bullet that wraps it during render.
        headline = " ".join((raw.get("headline") or "").split())[:EVIDENCE_HEADLINE_MAX]
        quote = (raw.get("quote") or "").strip()[:EVIDENCE_QUOTE_MAX]

        if not headline and not quote:
            continue

        out.append(
            Evidence(
                kind=kind,
                ref=ref,
                headline=headline,
                quote=quote,
                intent_kind=intent_kind,
                date=date,
            )
        )
    return out


def _resolve_sha(cited: str, valid_shas: set[str]) -> str | None:
    """Return the full SHA whose prefix is `cited`, or None if no match."""
    cited_lower = cited.lower()
    for full in valid_shas:
        if full.lower().startswith(cited_lower):
            return full
    return None


# ---------------------------------------------------------------------------
# Per-category analysis
# ---------------------------------------------------------------------------

async def _analyze_category(
    category: str,
    preprocess_result,
    llm: BaseLLM,
    model: str,
    *,
    valid_shas: set[str],
    valid_doc_paths: set[str],
    sha_to_date: dict[str, str],
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

    rules = _rules_from_parsed(
        parsed.get("rules", []),
        valid_shas=valid_shas,
        valid_doc_paths=valid_doc_paths,
        sha_to_date=sha_to_date,
    )
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

    # Build the validation pools once, before any LLM call. They feed both the
    # per-category evidence parser (which drops hallucinated refs) and the
    # SessionResult fields used for downstream metrics + diff.
    historic_shas: set[str] = set()
    sha_to_date: dict[str, str] = {}
    for f in files:
        if f.history is None:
            continue
        for c in (*f.history.commits, *f.history.reverts):
            if c.sha:
                historic_shas.add(c.sha)
                if c.date and c.sha not in sha_to_date:
                    sha_to_date[c.sha] = c.date
    valid_doc_paths: set[str] = {d.path for d in preprocess.repo_docs}

    # Select exemplars before the LLM loop — we still have source content here.
    # Pass repo_root so exemplars.py can re-read large senior files from disk
    # (the fetcher truncates past _MAX_LINES, which would hide e.g. params.py).
    from hijack.core.exemplars import select_exemplars
    exemplars = select_exemplars(files, repo_root=repo_root)

    category_results: list[CategoryResult] = []
    for category in categories:
        result = await _analyze_category(
            category,
            preprocess,
            llm,
            model,
            valid_shas=historic_shas,
            valid_doc_paths=valid_doc_paths,
            sha_to_date=sha_to_date,
        )
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
        historic_shas=sorted(historic_shas),
        repo_doc_paths=sorted(valid_doc_paths),
        exemplars=exemplars,
    )

    if critic and any(c.rules for c in category_results):
        from hijack.core.critic import refine
        logger.info("Critic 레이어 실행 중...")
        session = await refine(session, llm, model=model)

    return session
