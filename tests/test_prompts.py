from __future__ import annotations

import pytest

from hijack.core.prompts import ALL_CATEGORIES, MVP_CATEGORIES, build_category_prompt


def test_mvp_categories_has_three_items() -> None:
    assert len(MVP_CATEGORIES) == 3
    assert "architecture" in MVP_CATEGORIES
    assert "coding_style" in MVP_CATEGORIES
    assert "api_design" in MVP_CATEGORIES


def test_all_categories_has_ten_items() -> None:
    assert len(ALL_CATEGORIES) == 10
    new_seven = [
        "testing", "dependencies", "security", "performance",
        "devops", "state_management", "data_model",
    ]
    for cat in new_seven:
        assert cat in ALL_CATEGORIES


def test_all_categories_is_superset_of_mvp() -> None:
    for cat in MVP_CATEGORIES:
        assert cat in ALL_CATEGORIES


def test_architecture_prompt_contains_json() -> None:
    result = build_category_prompt("architecture", ["file content"])
    assert "JSON" in result


def test_coding_style_prompt_contains_layer() -> None:
    result = build_category_prompt("coding_style", [])
    assert "layer" in result


def test_api_design_prompt_contains_must() -> None:
    result = build_category_prompt("api_design", ["content"])
    assert "MUST" in result


def test_invalid_category_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Unknown category"):
        build_category_prompt("invalid_category", ["some content"])


class TestEvidenceCitationRequirement:
    """Phase A: prompts must steer the LLM toward citing git history in `reason`."""

    def test_prompt_demands_evidence_in_reason(self) -> None:
        result = build_category_prompt("architecture", ["sample"])
        assert "EVIDENCE OVER OPINION" in result
        assert "<history>" in result
        assert "[no-evidence]" in result

    def test_prompt_warns_against_generic_justifications(self) -> None:
        result = build_category_prompt("coding_style", ["sample"])
        assert "best practice" in result.lower() or "industry standard" in result.lower()

    def test_few_shot_good_example_cites_a_commit(self) -> None:
        # The few-shot example should model the citation pattern, not LLM opinion.
        result = build_category_prompt("api_design", ["sample"])
        assert "commit a1b2c3d" in result

    def test_prompt_lists_adr_as_third_citation_form(self) -> None:
        result = build_category_prompt("architecture", ["sample"])
        assert "<repo_context>" in result
        assert "ADR" in result

    def test_prompt_demands_verbatim_quoted_subjects(self) -> None:
        # Review fix: paraphrasing erases the senior's voice. Citations must
        # include the actual subject/heading copied verbatim from the input.
        result = build_category_prompt("coding_style", ["sample"])
        assert "verbatim" in result.lower()
        assert "single quotes" in result.lower()
        # Reinforces anti-hallucination directive (line breaks may sit between
        # words in the prompt, so match a tight substring).
        assert "invent shas" in result.lower()

    def test_prompt_asks_to_quote_a_key_sentence(self) -> None:
        # When the senior wrote a substantive body, that prose must reach the
        # output — instruction explicitly demands a quoted sentence.
        result = build_category_prompt("coding_style", ["sample"])
        assert "QUOTE A KEY SENTENCE" in result


class TestRepoContextInjection:
    def test_repo_context_block_prepended_when_provided(self) -> None:
        ctx = "<repo_context>\n### ARCHITECTURE.md\nWe use dataclasses.\n</repo_context>"
        result = build_category_prompt("architecture", ["sample"], repo_context=ctx)
        assert "<repo_context>" in result
        assert "ARCHITECTURE.md" in result
        # repo_context should appear BEFORE <files>, not after.
        assert result.index("<repo_context>") < result.index("<files>")

    def test_no_block_when_repo_context_empty(self) -> None:
        result = build_category_prompt("architecture", ["sample"], repo_context="")
        # The instruction text mentions <repo_context> as a doc-citation source,
        # but no actual injected block should appear before <files>.
        files_idx = result.index("<files>")
        # If a <repo_context> open tag occurred before <files>, it would come from
        # an actual injected block. Verify none is there.
        assert "<repo_context>\n" not in result[:files_idx]


class TestNewCategoryPrompts:
    """7개 신규 카테고리 프롬프트 기본 동작 검증."""

    def test_testing_prompt_mentions_framework(self) -> None:
        result = build_category_prompt("testing", ["test content"])
        assert "test" in result.lower()
        assert "JSON" in result

    def test_dependencies_prompt_mentions_library(self) -> None:
        result = build_category_prompt("dependencies", [])
        assert "JSON" in result
        assert "layer" in result

    def test_security_prompt_mentions_auth(self) -> None:
        result = build_category_prompt("security", ["auth code"])
        assert "auth" in result.lower()

    def test_performance_prompt_mentions_caching(self) -> None:
        result = build_category_prompt("performance", [])
        assert "cach" in result.lower()

    def test_devops_prompt_mentions_ci(self) -> None:
        result = build_category_prompt("devops", [])
        assert "CI" in result or "deploy" in result.lower()

    def test_state_management_prompt_mentions_state(self) -> None:
        result = build_category_prompt("state_management", [])
        assert "state" in result.lower()

    def test_data_model_prompt_mentions_migration(self) -> None:
        result = build_category_prompt("data_model", [])
        assert "migrat" in result.lower()

    def test_all_new_categories_return_non_empty(self) -> None:
        for cat in ["testing", "dependencies", "security", "performance",
                    "devops", "state_management", "data_model"]:
            result = build_category_prompt(cat, ["sample"])
            assert len(result) > 100, f"Prompt too short for {cat}"
