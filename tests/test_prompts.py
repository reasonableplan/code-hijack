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
    """Phase D1: prompts demand structured `evidence` list with verbatim quotes."""

    def test_prompt_describes_structured_evidence_field(self) -> None:
        # Phase D1 moves citations from reason text into a structured field.
        result = build_category_prompt("architecture", ["sample"])
        assert "STRUCTURED CITATIONS" in result
        assert '"evidence"' in result
        assert "<history>" in result
        assert "[no-evidence]" in result

    def test_prompt_warns_against_paraphrased_filler(self) -> None:
        # Equivalent of "no generic justifications" guard, restated for the
        # structured field — drop a rule rather than inventing evidence.
        result = build_category_prompt("coding_style", ["sample"])
        assert "paraphrased filler" in result.lower()

    def test_few_shot_good_example_includes_evidence(self) -> None:
        # The few-shot good example should model the new evidence schema:
        # kind=commit, a real-looking ref, and a verbatim headline + quote.
        result = build_category_prompt("api_design", ["sample"])
        assert '"kind": "commit"' in result
        assert '"ref": "a1b2c3d"' in result
        assert '"headline":' in result
        assert '"quote":' in result

    def test_prompt_lists_adr_as_doc_evidence_kind(self) -> None:
        result = build_category_prompt("architecture", ["sample"])
        assert "<repo_context>" in result
        assert "ADR" in result
        assert '"kind"' in result and '"doc"' in result

    def test_prompt_demands_verbatim_quotes_in_evidence(self) -> None:
        # Verbatim is the entire point — ban paraphrase explicitly.
        result = build_category_prompt("coding_style", ["sample"])
        assert "VERBATIM" in result
        # Anti-hallucination — never invent SHAs / paths.
        assert "NEVER invent SHAs" in result

    def test_prompt_lists_intent_kind_enum_values(self) -> None:
        # All four intent kinds must appear so the LLM knows the closed set.
        result = build_category_prompt("coding_style", ["sample"])
        for value in ("rejection", "constraint", "incident", "preference"):
            assert f'"{value}"' in result

    def test_prompt_makes_reason_a_one_sentence_gist(self) -> None:
        # reason changed from "carry citations" to "1-sentence intent gist".
        result = build_category_prompt("coding_style", ["sample"])
        assert "1-SENTENCE INTENT GIST" in result
        assert "≤150 chars" in result


class TestCargoCultGuard:
    """Phase: rule body must describe the design principle, not prescribe a
    specific internal class/function/sentinel name unique to this repo."""

    def test_prompt_demands_principle_over_prescription(self) -> None:
        result = build_category_prompt("architecture", ["sample"])
        assert "PRINCIPLE OVER PRESCRIPTION" in result

    def test_prompt_explains_transferability_motivation(self) -> None:
        # The why: rules consumed in OTHER projects where the internal symbol
        # does not exist.
        result = build_category_prompt("api_design", ["sample"])
        assert "OTHER projects" in result

    def test_prompt_shows_principle_vs_cargo_cult_pair(self) -> None:
        # Concrete contrast — the prompt should include both a transferable
        # form and a cargo-cult form so the LLM can pattern-match.
        result = build_category_prompt("coding_style", ["sample"])
        assert "cargo-cult" in result.lower()

    def test_prompt_gives_identifier_collocation_heuristic(self) -> None:
        # Heuristic: identifier in rule body that also appears in good_example
        # → too prescriptive.
        result = build_category_prompt("architecture", ["sample"])
        assert "good_example" in result and "principle-level" in result.lower()


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
