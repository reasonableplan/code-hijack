from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hijack.core.analyzer import (
    _parse_json,
    _parse_regex_fallback,
    _rules_from_parsed,
    run_full_analysis,
)
from hijack.core.fetcher import SourceFile
from hijack.errors import LLM_002, LLMError


# ---------------------------------------------------------------------------
# _parse_json
# ---------------------------------------------------------------------------

class TestParseJson:
    def test_plain_json(self) -> None:
        data = {"design_intent": "test", "rules": []}
        result = _parse_json(json.dumps(data))
        assert result == data

    def test_code_fence_json(self) -> None:
        raw = '```json\n{"design_intent": "hi", "rules": []}\n```'
        result = _parse_json(raw)
        assert result is not None
        assert result["design_intent"] == "hi"

    def test_embedded_in_text(self) -> None:
        raw = 'Here is the result:\n{"design_intent": "ok", "rules": []}\nDone.'
        result = _parse_json(raw)
        assert result is not None
        assert result["design_intent"] == "ok"

    def test_invalid_returns_none(self) -> None:
        assert _parse_json("not json at all") is None

    def test_empty_string(self) -> None:
        assert _parse_json("") is None


# ---------------------------------------------------------------------------
# _parse_regex_fallback
# ---------------------------------------------------------------------------

class TestParseRegexFallback:
    def test_finds_json_block(self) -> None:
        raw = 'Some text {"design_intent": "x", "rules": []} more text'
        result = _parse_regex_fallback(raw)
        assert result is not None
        assert result["design_intent"] == "x"

    def test_no_json_returns_none(self) -> None:
        assert _parse_regex_fallback("no braces here") is None


# ---------------------------------------------------------------------------
# _rules_from_parsed
# ---------------------------------------------------------------------------

class TestRulesFromParsed:
    def test_valid_rule(self) -> None:
        raw = [{
            "rule": "Use type hints",
            "priority": "MUST",
            "confidence": "high",
            "ref_files": [],
            "good_example": "",
            "bad_example": "",
            "reason": "readability",
            "layer": "backend",
        }]
        rules = _rules_from_parsed(raw)
        assert len(rules) == 1
        assert rules[0].rule == "Use type hints"
        assert rules[0].layer == "backend"

    def test_missing_required_field_dropped(self) -> None:
        raw = [{"rule": "no layer field", "priority": "MUST"}]
        rules = _rules_from_parsed(raw)
        assert rules == []

    def test_defaults_applied(self) -> None:
        raw = [{"rule": "x", "priority": "MUST", "layer": "shared"}]
        rules = _rules_from_parsed(raw)
        assert rules[0].confidence == "medium"
        assert rules[0].ref_files == []

    def test_non_dict_items_skipped(self) -> None:
        rules = _rules_from_parsed(["not a dict", None, 42])  # type: ignore[list-item]
        assert rules == []


# ---------------------------------------------------------------------------
# run_full_analysis
# ---------------------------------------------------------------------------

def _make_llm_response(category: str) -> str:
    data = {
        "design_intent": f"{category} intent",
        "rules": [
            {
                "rule": f"Rule for {category}",
                "priority": "MUST",
                "confidence": "high",
                "ref_files": ["main.py"],
                "good_example": "x = 1",
                "bad_example": "x=1",
                "reason": "style",
                "layer": "backend",
            }
        ],
        "anti_patterns": [],
        "file_type_guides": {},
        "checklist": ["check 1"],
    }
    return json.dumps(data)


def _make_files() -> list[SourceFile]:
    return [
        SourceFile(path=Path("main.py"), content="def main(): pass", layer="backend", role="entry_point"),
        SourceFile(path=Path("service.py"), content="def svc(): pass", layer="backend", role="service"),
    ]


@pytest.mark.asyncio
async def test_run_full_analysis_success() -> None:
    llm = AsyncMock()
    llm.analyze.side_effect = lambda prompt, model: asyncio.coroutine(
        lambda: _make_llm_response("architecture")
    )()

    mock_resp = _make_llm_response("architecture")
    llm.analyze = AsyncMock(return_value=mock_resp)

    files = _make_files()
    result = await run_full_analysis(
        files,
        Path("/repo"),
        categories=["architecture"],
        llm=llm,
        target="https://github.com/test/repo",
    )

    assert result.session_id.endswith("_repo")
    assert len(result.categories) == 1
    cat = result.categories[0]
    assert cat.category == "architecture"
    assert cat.error is None
    assert len(cat.rules) == 1
    assert cat.rules[0].layer == "backend"


@pytest.mark.asyncio
async def test_run_full_analysis_llm_failure_records_error() -> None:
    llm = AsyncMock()
    llm.analyze.side_effect = LLMError(LLM_002, "API down")

    files = _make_files()
    result = await run_full_analysis(
        files,
        Path("/repo"),
        categories=["architecture"],
        llm=llm,
        target="/local/repo",
    )

    cat = result.categories[0]
    assert cat.error is not None
    assert LLM_002 in cat.error
    assert cat.rules == []


@pytest.mark.asyncio
async def test_run_full_analysis_parse_failure() -> None:
    llm = AsyncMock()
    llm.analyze = AsyncMock(return_value="not json at all, no braces")

    files = _make_files()
    result = await run_full_analysis(
        files,
        Path("/repo"),
        categories=["coding_style"],
        llm=llm,
        target="/local/repo",
    )

    cat = result.categories[0]
    assert cat.error is not None
    assert "LLM_003" in cat.error
    assert cat.raw_llm_output == "not json at all, no braces"


@pytest.mark.asyncio
async def test_run_full_analysis_multiple_categories() -> None:
    responses = {
        "architecture": _make_llm_response("architecture"),
        "coding_style": _make_llm_response("coding_style"),
    }

    call_count = 0

    async def fake_analyze(prompt: str, model: str) -> str:
        nonlocal call_count
        call_count += 1
        for cat in responses:
            if cat in prompt:
                return responses[cat]
        return responses["architecture"]

    llm = MagicMock()
    llm.analyze = fake_analyze

    files = _make_files()
    result = await run_full_analysis(
        files,
        Path("/repo"),
        categories=["architecture", "coding_style"],
        llm=llm,
        target="/local/repo",
    )

    assert len(result.categories) == 2
    assert call_count == 2


@pytest.mark.asyncio
async def test_run_full_analysis_session_metadata() -> None:
    llm = AsyncMock()
    llm.analyze = AsyncMock(return_value=_make_llm_response("architecture"))

    files = _make_files()
    result = await run_full_analysis(
        files,
        Path("/repo"),
        categories=["architecture"],
        llm=llm,
        model="claude-opus-4-7",
        target="https://github.com/org/myrepo",
    )

    assert result.model == "claude-opus-4-7"
    assert "myrepo" in result.session_id
    assert "main.py" in result.selected_files
    assert result.analysis_duration_seconds >= 0
    assert result.timestamp.endswith("+00:00") or result.timestamp.endswith("Z")
