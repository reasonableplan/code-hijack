from __future__ import annotations

import pytest

from hijack.core.prompts import MVP_CATEGORIES, build_category_prompt


def test_mvp_categories_has_three_items() -> None:
    assert len(MVP_CATEGORIES) == 3
    assert "architecture" in MVP_CATEGORIES
    assert "coding_style" in MVP_CATEGORIES
    assert "api_design" in MVP_CATEGORIES


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
