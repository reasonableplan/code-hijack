from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from hijack.core.analyzer import (
    _parse_json,
    _parse_regex_fallback,
    _rules_from_parsed,
    normalize_rationale_tier,
    run_full_analysis,
)
from hijack.core.fetcher import SourceFile
from hijack.core.models import AnalysisRule, Evidence
from hijack.core.preprocessor import (
    _CATEGORY_ROLES,
    build_preprocess_result,
    select_files_for_category,
)
from hijack.core.prompts import ALL_CATEGORIES
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


class TestEvidenceParsing:
    """Phase D1: validate Evidence list in LLM output."""

    _VALID_SHAS = {"a1b2c3d4e5f6789012345678901234567890abcd"}
    _SHA_TO_DATE = {"a1b2c3d4e5f6789012345678901234567890abcd": "2024-08-12 14:30:00 +0900"}
    _VALID_DOCS = {"README.md", "docs/adr/0001.md"}

    def _rule_with_evidence(self, evidence: list[dict]) -> dict:
        return {
            "rule": "Use dataclasses",
            "priority": "MUST",
            "confidence": "high",
            "ref_files": ["src/main.py:10"],
            "good_example": "@dataclass class X: ...",
            "bad_example": "class X(BaseModel): ...",
            "reason": "Minimise async-path runtime regressions.",
            "layer": "backend",
            "evidence": evidence,
        }

    def test_valid_commit_evidence_kept_with_date_populated(self) -> None:
        raw = [self._rule_with_evidence([{
            "kind": "commit",
            "ref": "a1b2c3d",
            "headline": "fix: drop pydantic",
            "quote": "runtime regressions in async paths",
            "intent_kind": "rejection",
        }])]
        rules = _rules_from_parsed(
            raw,
            valid_shas=self._VALID_SHAS,
            sha_to_date=self._SHA_TO_DATE,
        )
        assert len(rules) == 1
        assert len(rules[0].evidence) == 1
        e = rules[0].evidence[0]
        assert e.kind == "commit"
        # ref normalised to a 12-char prefix of the full SHA.
        assert e.ref == "a1b2c3d4e5f6"
        assert e.date == "2024-08-12 14:30:00 +0900"
        assert e.intent_kind == "rejection"

    def test_hallucinated_sha_evidence_dropped(self) -> None:
        raw = [self._rule_with_evidence([{
            "kind": "commit",
            "ref": "deadbeef",
            "headline": "made up",
            "quote": "made up",
            "intent_kind": None,
        }])]
        rules = _rules_from_parsed(raw, valid_shas=self._VALID_SHAS)
        # Rule survives but evidence list is empty.
        assert len(rules) == 1
        assert rules[0].evidence == []

    def test_unknown_kind_dropped(self) -> None:
        raw = [self._rule_with_evidence([{
            "kind": "tweet",  # not in EVIDENCE_KIND_VALUES
            "ref": "a1b2c3d",
            "headline": "x",
            "quote": "y",
        }])]
        rules = _rules_from_parsed(raw, valid_shas=self._VALID_SHAS)
        assert rules[0].evidence == []

    def test_unknown_intent_kind_normalised_to_none(self) -> None:
        raw = [self._rule_with_evidence([{
            "kind": "commit",
            "ref": "a1b2c3d",
            "headline": "x",
            "quote": "y",
            "intent_kind": "philosophy",  # was in old enum, removed in D1
        }])]
        rules = _rules_from_parsed(raw, valid_shas=self._VALID_SHAS)
        assert rules[0].evidence[0].intent_kind is None

    def test_doc_evidence_with_valid_path_kept(self) -> None:
        raw = [self._rule_with_evidence([{
            "kind": "doc",
            "ref": "docs/adr/0001.md",
            "headline": "ADR 0001",
            "quote": "We chose dataclasses.",
        }])]
        rules = _rules_from_parsed(raw, valid_doc_paths=self._VALID_DOCS)
        assert rules[0].evidence[0].kind == "doc"
        assert rules[0].evidence[0].ref == "docs/adr/0001.md"

    def test_doc_evidence_with_unknown_path_dropped(self) -> None:
        raw = [self._rule_with_evidence([{
            "kind": "doc",
            "ref": "docs/adr/9999-imaginary.md",
            "headline": "x",
            "quote": "y",
        }])]
        rules = _rules_from_parsed(raw, valid_doc_paths=self._VALID_DOCS)
        assert rules[0].evidence == []

    def test_headline_truncated_to_120_chars(self) -> None:
        long_headline = "x" * 200
        raw = [self._rule_with_evidence([{
            "kind": "commit",
            "ref": "a1b2c3d",
            "headline": long_headline,
            "quote": "y",
        }])]
        rules = _rules_from_parsed(raw, valid_shas=self._VALID_SHAS)
        assert len(rules[0].evidence[0].headline) == 120

    def test_quote_truncated_to_500_chars(self) -> None:
        long_quote = "y" * 1000
        raw = [self._rule_with_evidence([{
            "kind": "commit",
            "ref": "a1b2c3d",
            "headline": "h",
            "quote": long_quote,
        }])]
        rules = _rules_from_parsed(raw, valid_shas=self._VALID_SHAS)
        assert len(rules[0].evidence[0].quote) == 500

    def test_empty_pools_disable_validation_best_effort(self) -> None:
        # When the session has no git/docs context, accept LLM-extracted
        # citations as best-effort rather than dropping every entry.
        raw = [self._rule_with_evidence([{
            "kind": "commit",
            "ref": "anything",
            "headline": "h",
            "quote": "q",
        }])]
        rules = _rules_from_parsed(raw)  # all pools default to empty
        assert len(rules[0].evidence) == 1

    def test_revert_kind_coerces_intent_to_rejection(self) -> None:
        # D1 review fix: a revert IS, by definition, a rejection. Whatever
        # the LLM emitted for intent_kind gets overridden.
        raw = [self._rule_with_evidence([{
            "kind": "revert",
            "ref": "a1b2c3d",
            "headline": "Revert: drop pydantic",
            "quote": "Async path regressions",
            "intent_kind": "preference",  # LLM disagrees — we override
        }])]
        rules = _rules_from_parsed(raw, valid_shas=self._VALID_SHAS)
        assert rules[0].evidence[0].intent_kind == "rejection"

    def test_revert_with_no_intent_still_set_to_rejection(self) -> None:
        # Even when LLM omits intent_kind on a revert, we fill it.
        raw = [self._rule_with_evidence([{
            "kind": "revert",
            "ref": "a1b2c3d",
            "headline": "rollback: pydantic",
            "quote": "perf regression",
        }])]
        rules = _rules_from_parsed(raw, valid_shas=self._VALID_SHAS)
        assert rules[0].evidence[0].intent_kind == "rejection"

    def test_headline_newlines_collapsed_to_single_line(self) -> None:
        # Multi-line subjects would break the single-line bullet rendering.
        raw = [self._rule_with_evidence([{
            "kind": "commit",
            "ref": "a1b2c3d",
            "headline": "fix: drop pydantic\n\nMore explanation\nthird line",
            "quote": "body",
        }])]
        rules = _rules_from_parsed(raw, valid_shas=self._VALID_SHAS)
        headline = rules[0].evidence[0].headline
        assert "\n" not in headline
        # Whitespace runs collapse to single spaces.
        assert headline == "fix: drop pydantic More explanation third line"

    def test_whitespace_only_quote_becomes_empty(self) -> None:
        # Quote of "   \n  \t" must strip down to "" so the renderer's
        # truthiness check skips emitting a hollow blockquote section.
        raw = [self._rule_with_evidence([{
            "kind": "commit",
            "ref": "a1b2c3d",
            "headline": "fix: x",
            "quote": "   \n  \t  ",
        }])]
        rules = _rules_from_parsed(raw, valid_shas=self._VALID_SHAS)
        assert rules[0].evidence[0].quote == ""

    def test_entry_with_both_headline_and_quote_empty_dropped(self) -> None:
        # No useful info to render → drop the entry.
        raw = [self._rule_with_evidence([{
            "kind": "commit",
            "ref": "a1b2c3d",
            "headline": "   ",
            "quote": "\t\n",
        }])]
        rules = _rules_from_parsed(raw, valid_shas=self._VALID_SHAS)
        assert rules[0].evidence == []


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
        SourceFile(
            path=Path("main.py"), content="def main(): pass",
            layer="backend", role="entry_point",
        ),
        SourceFile(
            path=Path("service.py"), content="def svc(): pass",
            layer="backend", role="service",
        ),
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
        critic=False,
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


# ---------------------------------------------------------------------------
# _CATEGORY_ROLES — 7개 신규 카테고리 파일 역할 매핑 검증
# ---------------------------------------------------------------------------

class TestCategoryRoleMapping:
    """각 신규 카테고리가 올바른 파일 역할을 선택하는지 검증한다."""

    def _files_by_role(self) -> list[SourceFile]:
        roles = ["entry_point", "model", "api", "test", "service", "other"]
        return [
            SourceFile(
                path=Path(f"{role}.py"), content=f"# {role}", layer="backend", role=role
            )
            for role in roles
        ]

    def _selected_roles(self, category: str) -> list[str]:
        files = self._files_by_role()
        result = build_preprocess_result(files, Path("/repo"))
        selected = select_files_for_category(result, category)
        return [f.role for f in selected]

    def test_all_categories_covered_in_roles_map(self) -> None:
        for cat in ALL_CATEGORIES:
            assert cat in _CATEGORY_ROLES, f"{cat!r} missing from _CATEGORY_ROLES"

    def test_testing_category_prefers_test_role(self) -> None:
        roles = self._selected_roles("testing")
        assert roles[0] == "test"

    def test_dependencies_category_includes_entry_point(self) -> None:
        roles = self._selected_roles("dependencies")
        assert "entry_point" in roles

    def test_security_category_prefers_api_role(self) -> None:
        roles = self._selected_roles("security")
        assert roles[0] == "api"

    def test_performance_category_prefers_service_role(self) -> None:
        roles = self._selected_roles("performance")
        assert roles[0] == "service"

    def test_devops_category_selects_other_role(self) -> None:
        roles = self._selected_roles("devops")
        assert "other" in roles

    def test_state_management_category_includes_service_and_model(self) -> None:
        roles = self._selected_roles("state_management")
        assert "service" in roles
        assert "model" in roles

    def test_data_model_category_prefers_model_role(self) -> None:
        roles = self._selected_roles("data_model")
        assert roles[0] == "model"


@pytest.mark.asyncio
async def test_run_full_analysis_all_ten_categories() -> None:
    """ALL_CATEGORIES 10개를 분석해도 에러가 없어야 한다."""
    mock_resp = _make_llm_response("backend")
    llm = AsyncMock()
    llm.analyze = AsyncMock(return_value=mock_resp)

    files = _make_files()
    result = await run_full_analysis(
        files,
        Path("/repo"),
        categories=ALL_CATEGORIES,
        llm=llm,
        target="/local/repo",
        critic=False,
    )

    assert len(result.categories) == 10
    assert llm.analyze.call_count == 10
    for cat in result.categories:
        assert cat.error is None, f"{cat.category} returned error: {cat.error}"


@pytest.mark.asyncio
async def test_run_full_analysis_calls_critic_by_default() -> None:
    """critic=True 가 기본값 — 카테고리 호출 N 개 + critic 호출 1회 = N+1"""
    import json as _json
    mock_resp = _make_llm_response("backend")
    critic_resp = _json.dumps({"keep": [], "downgrade_to_should": [], "drop": [], "notes": "ok"})
    llm = AsyncMock()
    llm.analyze = AsyncMock(side_effect=[mock_resp, critic_resp])

    files = _make_files()
    await run_full_analysis(
        files, Path("/repo"), categories=["architecture"],
        llm=llm, target="/repo",
    )
    assert llm.analyze.call_count == 2  # 1 카테고리 + 1 critic


@pytest.mark.asyncio
async def test_files_by_layer_populated_in_session_result() -> None:
    """SessionResult.files_by_layer 가 preprocess 결과로 채워진다."""
    llm = AsyncMock()
    llm.analyze = AsyncMock(return_value=_make_llm_response("backend"))

    files = [
        SourceFile(path=Path("a.py"), content="x", layer="backend", role="service"),
        SourceFile(path=Path("b.tsx"), content="x", layer="frontend", role="other"),
        SourceFile(path=Path("c.py"), content="x", layer="shared", role="other"),
    ]
    result = await run_full_analysis(
        files, Path("/repo"), categories=["architecture"], llm=llm, target="/repo"
    )

    assert result.files_by_layer.get("backend") == 1
    assert result.files_by_layer.get("frontend") == 1
    assert result.files_by_layer.get("shared") == 1


# ---------------------------------------------------------------------------
# normalize_rationale_tier (T-033)
# ---------------------------------------------------------------------------

def _make_rule(priority: str, rationale_tier: str) -> AnalysisRule:
    return AnalysisRule(
        rule="test rule",
        priority=priority,
        confidence="high",
        ref_files=[],
        good_example="",
        bad_example="",
        reason="reason",
        layer="backend",
        rationale_tier=rationale_tier,
    )


class TestAssignRationaleTier:
    """assign_rationale_tier — classify_rule 결과를 tier 로 반영하는 누락됐던 단계."""

    def _rule_with_evidence(self, sha: str) -> AnalysisRule:
        return AnalysisRule(
            rule="evidence-backed rule",
            priority="MUST",
            confidence="high",
            ref_files=["src/a.py:10"],
            good_example="x = 1",
            bad_example="x = 2",
            reason="Because commit says so.",
            layer="backend",
            evidence=[
                Evidence(kind="commit", ref=sha, headline="fix: thing", quote="body"),
            ],
        )

    def test_valid_evidence_becomes_cited_and_keeps_must(self) -> None:
        from hijack.core.analyzer import assign_rationale_tier

        rule = self._rule_with_evidence("abc1234")
        tiered = assign_rationale_tier([rule], valid_shas={"abc1234def5678"})
        assert tiered[0].rationale_tier == "cited"
        result = normalize_rationale_tier(tiered)
        assert result[0].priority == "MUST"

    def test_no_evidence_stays_speculative_and_demoted(self) -> None:
        from hijack.core.analyzer import assign_rationale_tier

        rule = _make_rule("MUST", "speculative")
        tiered = assign_rationale_tier([rule], valid_shas={"abc1234def5678"})
        assert tiered[0].rationale_tier == "speculative"
        result = normalize_rationale_tier(tiered)
        assert result[0].priority == "SHOULD"

    def test_fake_sha_stays_speculative(self) -> None:
        from hijack.core.analyzer import assign_rationale_tier

        rule = self._rule_with_evidence("deadbeef")
        tiered = assign_rationale_tier([rule], valid_shas={"abc1234def5678"})
        assert tiered[0].rationale_tier == "speculative"

    def test_original_not_mutated(self) -> None:
        from hijack.core.analyzer import assign_rationale_tier

        rule = self._rule_with_evidence("abc1234")
        assign_rationale_tier([rule], valid_shas={"abc1234def5678"})
        assert rule.rationale_tier == "speculative"

    def test_valid_pr_ref_becomes_cited_via_passthrough(self) -> None:
        from hijack.core.analyzer import assign_rationale_tier

        rule = AnalysisRule(
            rule="rejected-pattern rule",
            priority="MUST",
            confidence="high",
            ref_files=["src/a.py:10"],
            good_example="x = 1",
            bad_example="x = 2",
            reason="Rejected in PR#3346.",
            layer="backend",
            evidence=[
                Evidence(kind="pr", ref="PR#3346", headline="h", quote="q"),
            ],
        )
        tiered = assign_rationale_tier([rule], valid_pr_refs={"pr#3346"})
        assert tiered[0].rationale_tier == "cited"
        result = normalize_rationale_tier(tiered)
        assert result[0].priority == "MUST"


class TestNormalizeRationaleTier:
    def test_cited_must_stays_must(self) -> None:
        rule = _make_rule("MUST", "cited")
        result = normalize_rationale_tier([rule])
        assert result[0].priority == "MUST"

    def test_corroborated_must_demoted_to_should(self) -> None:
        rule = _make_rule("MUST", "corroborated")
        result = normalize_rationale_tier([rule])
        assert result[0].priority == "SHOULD"

    def test_speculative_must_demoted_to_should(self) -> None:
        rule = _make_rule("MUST", "speculative")
        result = normalize_rationale_tier([rule])
        assert result[0].priority == "SHOULD"

    def test_speculative_should_stays_should(self) -> None:
        rule = _make_rule("SHOULD", "speculative")
        result = normalize_rationale_tier([rule])
        assert result[0].priority == "SHOULD"

    def test_original_object_not_mutated(self) -> None:
        rule = _make_rule("MUST", "speculative")
        result = normalize_rationale_tier([rule])
        # original unchanged
        assert rule.priority == "MUST"
        # new instance returned
        assert result[0] is not rule
        assert result[0].priority == "SHOULD"

    def test_empty_list_returns_empty(self) -> None:
        assert normalize_rationale_tier([]) == []

    def test_mixed_list_normalizes_selectively(self) -> None:
        rules = [
            _make_rule("MUST", "cited"),       # keep MUST
            _make_rule("MUST", "corroborated"), # demote to SHOULD
            _make_rule("MUST", "speculative"),  # demote to SHOULD
            _make_rule("SHOULD", "speculative"),# keep SHOULD
        ]
        result = normalize_rationale_tier(rules)
        assert result[0].priority == "MUST"
        assert result[1].priority == "SHOULD"
        assert result[2].priority == "SHOULD"
        assert result[3].priority == "SHOULD"


@pytest.mark.asyncio
async def test_run_full_analysis_normalize_applied_before_category_result() -> None:
    """normalize_rationale_tier がパース後に呼ばれ、MUST speculative → SHOULD になること."""
    import json as _json
    rules_payload = [
        {
            "rule": "speculative rule",
            "priority": "MUST",
            "confidence": "high",
            "ref_files": [],
            "good_example": "",
            "bad_example": "",
            "reason": "reason",
            "layer": "backend",
            "rationale_tier": "speculative",
        }
    ]
    mock_resp = _json.dumps({
        "design_intent": "intent",
        "rules": rules_payload,
        "anti_patterns": [],
        "file_type_guides": {},
        "checklist": [],
    })
    llm = AsyncMock()
    llm.analyze = AsyncMock(return_value=mock_resp)

    files = _make_files()
    result = await run_full_analysis(
        files, Path("/repo"), categories=["architecture"],
        llm=llm, target="/repo", critic=False,
    )

    assert result.categories[0].rules[0].priority == "SHOULD"
    assert result.categories[0].rules[0].rationale_tier == "speculative"
