"""Tests for data models."""

from hijack.core.models import AnalysisRule, CategoryResult, SessionResult


def test_analysis_rule_defaults():
    rule = AnalysisRule(rule="Use snake_case")
    assert rule.priority == "SHOULD"
    assert rule.confidence == "medium"
    assert rule.ref_files == []


def test_category_result():
    rule = AnalysisRule(rule="test rule", priority="MUST")
    cat = CategoryResult(
        category="architecture",
        design_intent="Clean architecture",
        rules=[rule],
        checklist=["Check layers"],
    )
    assert cat.category == "architecture"
    assert len(cat.rules) == 1
    assert cat.rules[0].priority == "MUST"


def test_session_result_json_roundtrip():
    rule = AnalysisRule(
        rule="Use dataclass",
        priority="MUST",
        confidence="high",
        ref_files=["models.py"],
        good_example="@dataclass\nclass Foo: ...",
        bad_example="class Foo:\n    def __init__(self): ...",
        reason="Consistency",
    )
    cat = CategoryResult(
        category="coding_style",
        design_intent="Keep it simple",
        rules=[rule],
        checklist=["Check naming"],
    )
    session = SessionResult(
        session_id="2026-04-12_test",
        target="/tmp/test",
        model="claude-sonnet-4-6",
        categories=[cat],
        selected_files=["main.py", "models.py"],
    )

    json_str = session.to_json()
    restored = SessionResult.from_json(json_str)

    assert restored.session_id == "2026-04-12_test"
    assert restored.target == "/tmp/test"
    assert len(restored.categories) == 1
    assert len(restored.categories[0].rules) == 1
    assert restored.categories[0].rules[0].rule == "Use dataclass"
    assert restored.categories[0].rules[0].priority == "MUST"
