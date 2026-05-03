from __future__ import annotations

from hijack.core.models import AnalysisRule, CategoryResult, Evidence, SessionResult


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
        anti_patterns=[{
            "pattern": "God object",
            "reason": "Too much responsibility",
            "alternative": "Split into services",
        }],
        file_type_guides={
            "model": "Only data, no business logic",
            "router": "Only routing, delegate to service",
        },
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


# ---------------------------------------------------------------------------
# scope (Q4)
# ---------------------------------------------------------------------------

def test_rule_default_scope_is_cross_project() -> None:
    rule = make_rule()
    assert rule.scope == "cross_project"


def test_rule_scope_roundtrip() -> None:
    for scope in ("cross_project", "framework_internal", "domain_specific"):
        rule = make_rule(scope=scope)
        data = rule.to_json()
        assert data["scope"] == scope
        assert AnalysisRule.from_json(data).scope == scope


def test_rule_scope_backward_compat_when_key_missing() -> None:
    # An older session.json without a `scope` key must still load via the default.
    payload = make_rule().to_json()
    payload.pop("scope", None)
    restored = AnalysisRule.from_json(payload)
    assert restored.scope == "cross_project"


# ---------------------------------------------------------------------------
# historic_shas — Phase A review fix: SHA verification truth pool
# ---------------------------------------------------------------------------

def test_session_result_historic_shas_default_empty() -> None:
    session = make_session()
    assert session.historic_shas == []


def test_session_result_historic_shas_roundtrip() -> None:
    session = make_session(
        historic_shas=["a1b2c3d4e5f6", "deadbeef1234567890"]
    )
    restored = SessionResult.from_json(session.to_json())
    assert restored.historic_shas == ["a1b2c3d4e5f6", "deadbeef1234567890"]


def test_session_result_historic_shas_backward_compat_when_key_missing() -> None:
    # Older session.json files (pre-Phase-A-review) won't have the field.
    payload = make_session().to_json()
    payload.pop("historic_shas", None)
    restored = SessionResult.from_json(payload)
    assert restored.historic_shas == []


def test_session_result_repo_doc_paths_default_empty() -> None:
    assert make_session().repo_doc_paths == []


def test_session_result_repo_doc_paths_roundtrip() -> None:
    s = make_session(repo_doc_paths=["README.md", "docs/adr/0001.md"])
    restored = SessionResult.from_json(s.to_json())
    assert restored.repo_doc_paths == ["README.md", "docs/adr/0001.md"]


def test_session_result_repo_doc_paths_backward_compat_when_key_missing() -> None:
    payload = make_session().to_json()
    payload.pop("repo_doc_paths", None)
    restored = SessionResult.from_json(payload)
    assert restored.repo_doc_paths == []


# ---------------------------------------------------------------------------
# Evidence dataclass + AnalysisRule.evidence (Phase D1)
# ---------------------------------------------------------------------------

def _evidence(**kwargs) -> Evidence:
    defaults = dict(
        kind="commit",
        ref="a1b2c3d",
        headline="fix: drop pydantic",
        quote="Causes runtime regressions in async paths.",
        intent_kind="rejection",
        date="2024-08-12 14:30:00 +0900",
    )
    defaults.update(kwargs)
    return Evidence(**defaults)


def test_evidence_roundtrip() -> None:
    e = _evidence()
    assert Evidence.from_json(e.to_json()) == e


def test_evidence_optional_fields_default_to_none() -> None:
    e = Evidence(kind="commit", ref="aaa", headline="h", quote="q")
    assert e.intent_kind is None
    assert e.date is None
    # JSON survives None.
    restored = Evidence.from_json(e.to_json())
    assert restored == e


def test_rule_evidence_default_empty() -> None:
    assert make_rule().evidence == []


def test_rule_evidence_roundtrip() -> None:
    rule = make_rule(evidence=[_evidence(), _evidence(kind="doc", ref="README.md")])
    restored = AnalysisRule.from_json(rule.to_json())
    assert len(restored.evidence) == 2
    assert restored.evidence[0].kind == "commit"
    assert restored.evidence[1].kind == "doc"


def test_rule_evidence_backward_compat_when_key_missing() -> None:
    # Pre-D1 session.json files don't have an evidence key on rules.
    payload = make_rule().to_json()
    payload.pop("evidence", None)
    restored = AnalysisRule.from_json(payload)
    assert restored.evidence == []
