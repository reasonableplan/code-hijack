from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from hijack.core.critic import refine
from hijack.core.models import AnalysisRule, CategoryResult, SessionResult
from hijack.errors import LLM_002, LLMError


def _rule(text: str, priority: str = "MUST", layer: str = "backend") -> AnalysisRule:
    return AnalysisRule(
        rule=text, priority=priority, confidence="high",
        ref_files=[f"{text}.py:10"], good_example="x=1", bad_example="x =1",
        reason=text, layer=layer,
    )


def _category(name: str, rules: list[AnalysisRule]) -> CategoryResult:
    return CategoryResult(
        category=name, design_intent="", rules=rules,
        anti_patterns=[], file_type_guides={}, checklist=[], raw_llm_output="",
    )


def _session(*categories: CategoryResult) -> SessionResult:
    return SessionResult(
        session_id="2026-04-17_test", target="t", model="m",
        timestamp="2026-04-17T00:00:00+00:00", selected_files=[],
        categories=list(categories), analysis_duration_seconds=0.0,
        project_structure="", files_by_layer={"backend": 1},
    )


def _critic_response(keep: list[str], downgrade: list[str], drop: list[str]) -> str:
    return json.dumps({
        "keep": keep,
        "downgrade_to_should": downgrade,
        "drop": drop,
        "notes": "test",
    })


class TestRefine:
    @pytest.mark.asyncio
    async def test_drops_rules(self) -> None:
        s = _session(_category("arch", [_rule("keep me"), _rule("drop me")]))
        llm = AsyncMock()
        llm.analyze = AsyncMock(return_value=_critic_response(
            keep=["keep me"], downgrade=[], drop=["drop me"]
        ))
        result = await refine(s, llm, model="m")
        assert len(result.categories[0].rules) == 1
        assert result.categories[0].rules[0].rule == "keep me"

    @pytest.mark.asyncio
    async def test_downgrades_must_to_should(self) -> None:
        s = _session(_category("arch", [_rule("inflated MUST", priority="MUST")]))
        llm = AsyncMock()
        llm.analyze = AsyncMock(return_value=_critic_response(
            keep=[], downgrade=["inflated MUST"], drop=[]
        ))
        result = await refine(s, llm, model="m")
        assert result.categories[0].rules[0].priority == "SHOULD"
        assert result.categories[0].rules[0].rule == "inflated MUST"

    @pytest.mark.asyncio
    async def test_downgrade_does_not_touch_should(self) -> None:
        s = _session(_category("arch", [_rule("already SHOULD", priority="SHOULD")]))
        llm = AsyncMock()
        llm.analyze = AsyncMock(return_value=_critic_response(
            keep=[], downgrade=["already SHOULD"], drop=[]
        ))
        result = await refine(s, llm, model="m")
        assert result.categories[0].rules[0].priority == "SHOULD"

    @pytest.mark.asyncio
    async def test_preserves_category_metadata(self) -> None:
        cat = CategoryResult(
            category="arch", design_intent="D",
            rules=[_rule("keep")], anti_patterns=[{"pattern": "P"}],
            file_type_guides={"m": "g"}, checklist=["c1"],
            raw_llm_output="RAW",
        )
        s = _session(cat)
        llm = AsyncMock()
        llm.analyze = AsyncMock(return_value=_critic_response(
            keep=["keep"], downgrade=[], drop=[]
        ))
        result = await refine(s, llm, model="m")
        refined = result.categories[0]
        assert refined.design_intent == "D"
        assert refined.anti_patterns == [{"pattern": "P"}]
        assert refined.file_type_guides == {"m": "g"}
        assert refined.checklist == ["c1"]
        assert refined.raw_llm_output == "RAW"

    @pytest.mark.asyncio
    async def test_preserves_session_metadata(self) -> None:
        s = _session(_category("arch", [_rule("keep")]))
        llm = AsyncMock()
        llm.analyze = AsyncMock(return_value=_critic_response(
            keep=["keep"], downgrade=[], drop=[]
        ))
        result = await refine(s, llm, model="m")
        assert result.session_id == s.session_id
        assert result.target == s.target
        assert result.files_by_layer == s.files_by_layer

    @pytest.mark.asyncio
    async def test_cross_category_drop(self) -> None:
        s = _session(
            _category("arch", [_rule("duplicate rule")]),
            _category("style", [_rule("duplicate rule"), _rule("unique")]),
        )
        llm = AsyncMock()
        llm.analyze = AsyncMock(return_value=_critic_response(
            keep=["duplicate rule", "unique"], downgrade=[], drop=[]
        ))
        result = await refine(s, llm, model="m")
        assert len(result.categories[0].rules) == 1
        assert len(result.categories[1].rules) == 2

    @pytest.mark.asyncio
    async def test_llm_error_returns_original(self) -> None:
        s = _session(_category("arch", [_rule("r1"), _rule("r2")]))
        llm = AsyncMock()
        llm.analyze = AsyncMock(side_effect=LLMError(LLM_002, "API down"))
        result = await refine(s, llm, model="m")
        assert result is s  # 같은 객체 그대로

    @pytest.mark.asyncio
    async def test_parse_failure_returns_original(self) -> None:
        s = _session(_category("arch", [_rule("r1")]))
        llm = AsyncMock()
        llm.analyze = AsyncMock(return_value="not json, no braces either")
        result = await refine(s, llm, model="m")
        assert result is s

    @pytest.mark.asyncio
    async def test_empty_session_not_called(self) -> None:
        s = _session(_category("empty", []))
        llm = AsyncMock()
        llm.analyze = AsyncMock()
        result = await refine(s, llm, model="m")
        assert result is s
        llm.analyze.assert_not_called()

    @pytest.mark.asyncio
    async def test_rules_not_in_any_bucket_are_preserved(self) -> None:
        # Critic 응답이 불완전해서 규칙 하나가 keep/drop/downgrade 어디에도 없으면
        # conservative default: 보존 (기본 동작 — drop/downgrade 셋에 없으니 유지)
        s = _session(_category("arch", [_rule("r1"), _rule("r2"), _rule("r3")]))
        llm = AsyncMock()
        llm.analyze = AsyncMock(return_value=_critic_response(
            keep=["r1"], downgrade=[], drop=["r2"]  # r3 누락
        ))
        result = await refine(s, llm, model="m")
        rule_names = {r.rule for r in result.categories[0].rules}
        assert "r1" in rule_names
        assert "r2" not in rule_names
        assert "r3" in rule_names  # 누락된 규칙은 보존됨


# ---------------------------------------------------------------------------
# scope tagging (Q4)
# ---------------------------------------------------------------------------

def _critic_response_with_scopes(
    keep: list[str],
    downgrade: list[str],
    drop: list[str],
    scopes: dict[str, str],
) -> str:
    return json.dumps({
        "keep": keep,
        "downgrade_to_should": downgrade,
        "drop": drop,
        "scopes": scopes,
        "notes": "test",
    })


class TestScopeTagging:
    @pytest.mark.asyncio
    async def test_applies_scope_from_critic_response(self) -> None:
        s = _session(_category("arch", [
            _rule("public"), _rule("internal"), _rule("domain"),
        ]))
        llm = AsyncMock()
        llm.analyze = AsyncMock(return_value=_critic_response_with_scopes(
            keep=["public", "internal", "domain"],
            downgrade=[],
            drop=[],
            scopes={
                "public": "cross_project",
                "internal": "framework_internal",
                "domain": "domain_specific",
            },
        ))
        result = await refine(s, llm, model="m")
        scopes = {r.rule: r.scope for r in result.categories[0].rules}
        assert scopes == {
            "public": "cross_project",
            "internal": "framework_internal",
            "domain": "domain_specific",
        }

    @pytest.mark.asyncio
    async def test_invalid_scope_value_falls_back_to_default(self) -> None:
        # When the LLM hallucinates a non-canonical label, fall back to default.
        s = _session(_category("arch", [_rule("r1")]))
        llm = AsyncMock()
        llm.analyze = AsyncMock(return_value=_critic_response_with_scopes(
            keep=["r1"], downgrade=[], drop=[],
            scopes={"r1": "totally_invalid_label"},
        ))
        result = await refine(s, llm, model="m")
        assert result.categories[0].rules[0].scope == "cross_project"

    @pytest.mark.asyncio
    async def test_missing_scopes_field_keeps_existing_scope(self) -> None:
        # Older critic responses omit the `scopes` field — preserve the rule's existing scope.
        existing = _rule("r1")
        existing.scope = "domain_specific"
        s = _session(_category("arch", [existing]))
        llm = AsyncMock()
        llm.analyze = AsyncMock(return_value=_critic_response(
            keep=["r1"], downgrade=[], drop=[],
        ))
        result = await refine(s, llm, model="m")
        assert result.categories[0].rules[0].scope == "domain_specific"

    @pytest.mark.asyncio
    async def test_downgrade_and_scope_apply_together(self) -> None:
        s = _session(_category("arch", [_rule("r1", priority="MUST")]))
        llm = AsyncMock()
        llm.analyze = AsyncMock(return_value=_critic_response_with_scopes(
            keep=["r1"], downgrade=["r1"], drop=[],
            scopes={"r1": "framework_internal"},
        ))
        result = await refine(s, llm, model="m")
        rule = result.categories[0].rules[0]
        assert rule.priority == "SHOULD"
        assert rule.scope == "framework_internal"
