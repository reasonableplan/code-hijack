from __future__ import annotations

from hijack.core.models import AnalysisRule, CategoryResult, SessionResult


def make_rule(**kwargs) -> AnalysisRule:
    defaults = dict(
        rule="Use dependency injection",
        priority="MUST",
        confidence="high",
        ref_files=["src/main.py"],
        good_example="def create(db: Session = Depends(get_db)): ...",
        bad_example="def create(): db = SessionLocal() ...",
        reason="Testability and loose coupling",
    )
    defaults.update(kwargs)
    return AnalysisRule(**defaults)


def make_category(**kwargs) -> CategoryResult:
    defaults = dict(
        category="architecture",
        design_intent="Layered architecture with clear separation",
        rules=[make_rule()],
        anti_patterns=[{"pattern": "God object", "reason": "Too much responsibility", "alternative": "Split into services"}],
        file_type_guides={"model": "Only data, no business logic", "router": "Only routing, delegate to service"},
        checklist=["No business logic in routers", "Services are stateless"],
        raw_llm_output='{"rules": []}',
    )
    defaults.update(kwargs)
    return CategoryResult(**defaults)


def make_session(**kwargs) -> SessionResult:
    defaults = dict(
        session_id="2026-04-12_fastapi",
        target="https://github.com/example/repo",
        model="claude-sonnet-4-6",
        timestamp="2026-04-12T10:00:00Z",
        selected_files=["src/main.py", "src/models.py"],
        categories=[make_category()],
        analysis_duration_seconds=12.5,
        project_structure=".\n├── src\n│   └── main.py\n└── tests",
    )
    defaults.update(kwargs)
    return SessionResult(**defaults)


def test_analysis_rule_default_layer() -> None:
    rule = make_rule()
    assert rule.layer == "shared"


def test_analysis_rule_custom_layer() -> None:
    rule = make_rule(layer="backend")
    assert rule.layer == "backend"


def test_analysis_rule_roundtrip() -> None:
    rule = make_rule()
    assert AnalysisRule.from_json(rule.to_json()) == rule


def test_category_result_roundtrip() -> None:
    cat = make_category()
    assert CategoryResult.from_json(cat.to_json()) == cat


def test_category_result_error_none() -> None:
    cat = make_category()
    assert cat.error is None
    data = cat.to_json()
    assert data["error"] is None
    restored = CategoryResult.from_json(data)
    assert restored.error is None


def test_category_result_error_string() -> None:
    cat = make_category(error="LLM timeout")
    assert cat.error == "LLM timeout"
    restored = CategoryResult.from_json(cat.to_json())
    assert restored.error == "LLM timeout"


def test_session_result_roundtrip() -> None:
    session = make_session()
    assert SessionResult.from_json(session.to_json()) == session


def test_session_result_nested_roundtrip() -> None:
    rule = make_rule(layer="frontend")
    cat = make_category(rules=[rule, make_rule(layer="db")])
    session = make_session(categories=[cat])
    restored = SessionResult.from_json(session.to_json())
    assert restored.categories[0].rules[0].layer == "frontend"
    assert restored.categories[0].rules[1].layer == "db"
