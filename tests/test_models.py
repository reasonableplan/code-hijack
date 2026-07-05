from __future__ import annotations

from hijack.core.exemplars import Exemplar
from hijack.core.models import (
    AnalysisRule,
    CategoryResult,
    Evidence,
    ForesightCard,
    ProbeRecord,
    SessionResult,
)


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


# ---------------------------------------------------------------------------
# Exemplar dataclass + SessionResult.exemplars (Phase G1)
# ---------------------------------------------------------------------------

def _exemplar(**kwargs) -> Exemplar:
    defaults = dict(
        file_path="backend/service.py",
        line_range=(5, 20),
        code="def process(x: int) -> str:\n    return str(x)",
        layer="backend",
        role="service",
        name="process",
        why_chosen="fully type-annotated, sweet-spot length (16 lines)",
    )
    defaults.update(kwargs)
    return Exemplar(**defaults)


def test_exemplar_roundtrip() -> None:
    ex = _exemplar()
    restored = Exemplar.from_json(ex.to_json())
    assert restored == ex


def test_exemplar_line_range_stored_as_tuple() -> None:
    ex = _exemplar(line_range=(3, 17))
    assert ex.line_range == (3, 17)
    # JSON stores it as list, from_json restores it as tuple
    data = ex.to_json()
    assert data["line_range"] == [3, 17]
    restored = Exemplar.from_json(data)
    assert restored.line_range == (3, 17)


def test_session_result_exemplars_default_empty() -> None:
    session = make_session()
    assert session.exemplars == []


def test_session_result_exemplars_roundtrip() -> None:
    ex = _exemplar()
    session = make_session(exemplars=[ex])
    restored = SessionResult.from_json(session.to_json())
    assert len(restored.exemplars) == 1
    assert restored.exemplars[0] == ex


def test_session_result_exemplars_backward_compat_when_key_missing() -> None:
    # Pre-G1 session.json files don't have an exemplars key.
    payload = make_session().to_json()
    payload.pop("exemplars", None)
    restored = SessionResult.from_json(payload)
    assert restored.exemplars == []


def test_session_result_exemplars_multiple_roundtrip() -> None:
    exs = [
        _exemplar(name="func_a", layer="backend"),
        _exemplar(name="func_b", layer="shared", file_path="shared/util.py"),
    ]
    session = make_session(exemplars=exs)
    restored = SessionResult.from_json(session.to_json())
    assert len(restored.exemplars) == 2
    assert restored.exemplars[0].name == "func_a"
    assert restored.exemplars[1].layer == "shared"


# ---------------------------------------------------------------------------
# T-030: AnalysisRule.rationale_tier (Phase 3 — Foresight inference layer)
# ---------------------------------------------------------------------------

def test_rule_default_rationale_tier() -> None:
    rule = make_rule()
    assert rule.rationale_tier == "speculative"


def test_rule_rationale_tier_roundtrip() -> None:
    for tier in ("cited", "corroborated", "speculative"):
        rule = make_rule(rationale_tier=tier)
        data = rule.to_json()
        assert data["rationale_tier"] == tier
        assert AnalysisRule.from_json(data).rationale_tier == tier


def test_rule_rationale_tier_backward_compat_when_key_missing() -> None:
    # Older session.json files (pre-T-030) won't have rationale_tier.
    payload = make_rule().to_json()
    payload.pop("rationale_tier", None)
    restored = AnalysisRule.from_json(payload)
    assert restored.rationale_tier == "speculative"


# ---------------------------------------------------------------------------
# W4a: AnalysisRule.exemplar_verbatim
# ---------------------------------------------------------------------------

def test_rule_default_exemplar_verbatim_is_none() -> None:
    rule = make_rule()
    assert rule.exemplar_verbatim is None


def test_rule_exemplar_verbatim_omitted_from_json_when_none() -> None:
    rule = make_rule()
    assert "exemplar_verbatim" not in rule.to_json()


def test_rule_exemplar_verbatim_roundtrip() -> None:
    for value in (True, False):
        rule = make_rule(exemplar_verbatim=value)
        data = rule.to_json()
        assert data["exemplar_verbatim"] == value
        assert AnalysisRule.from_json(data).exemplar_verbatim == value


def test_rule_exemplar_verbatim_backward_compat_when_key_missing() -> None:
    # Older session.json files (pre-W4a) won't have exemplar_verbatim.
    payload = make_rule().to_json()
    payload.pop("exemplar_verbatim", None)
    restored = AnalysisRule.from_json(payload)
    assert restored.exemplar_verbatim is None


# ---------------------------------------------------------------------------
# T-030: ForesightCard dataclass
# ---------------------------------------------------------------------------

def _foresight_card(**kwargs) -> ForesightCard:
    defaults = dict(
        hypothesis="The author avoids ORMs to keep the DB layer transparent",
        signals=["sqlalchemy not in dependencies", "direct sql/ directory with .sql files"],
        falsification="If pyproject.toml ever lists sqlalchemy, this hypothesis is wrong",
        tier="corroborated",
        layer="db",
    )
    defaults.update(kwargs)
    return ForesightCard(**defaults)


def test_foresight_card_roundtrip() -> None:
    card = _foresight_card()
    restored = ForesightCard.from_json(card.to_json())
    assert restored == card


def test_foresight_card_speculative_tier() -> None:
    card = _foresight_card(tier="speculative", layer="shared")
    data = card.to_json()
    assert data["tier"] == "speculative"
    restored = ForesightCard.from_json(data)
    assert restored.tier == "speculative"
    assert restored.layer == "shared"


def test_foresight_card_signals_list() -> None:
    card = _foresight_card(signals=["signal_a", "signal_b", "signal_c"])
    data = card.to_json()
    assert data["signals"] == ["signal_a", "signal_b", "signal_c"]
    restored = ForesightCard.from_json(data)
    assert restored.signals == ["signal_a", "signal_b", "signal_c"]


def test_foresight_card_empty_signals() -> None:
    card = _foresight_card(signals=[])
    restored = ForesightCard.from_json(card.to_json())
    assert restored.signals == []


# ---------------------------------------------------------------------------
# T-030: SessionResult.foresight_cards + repo_nature
# ---------------------------------------------------------------------------

def test_session_result_foresight_cards_default_empty() -> None:
    session = make_session()
    assert session.foresight_cards == []


def test_session_result_foresight_cards_roundtrip() -> None:
    card = _foresight_card()
    session = make_session(foresight_cards=[card])
    restored = SessionResult.from_json(session.to_json())
    assert len(restored.foresight_cards) == 1
    assert restored.foresight_cards[0] == card


def test_session_result_foresight_cards_backward_compat_when_key_missing() -> None:
    # Pre-T-030 session.json files don't have foresight_cards.
    payload = make_session().to_json()
    payload.pop("foresight_cards", None)
    restored = SessionResult.from_json(payload)
    assert restored.foresight_cards == []


def test_session_result_repo_nature_default_library() -> None:
    session = make_session()
    assert session.repo_nature == "library"


def test_session_result_repo_nature_roundtrip() -> None:
    for nature in ("app/cli", "app", "library"):
        session = make_session(repo_nature=nature)
        data = session.to_json()
        assert data["repo_nature"] == nature
        restored = SessionResult.from_json(data)
        assert restored.repo_nature == nature


def test_session_result_repo_nature_backward_compat_when_key_missing() -> None:
    # Older session.json files won't have repo_nature.
    payload = make_session().to_json()
    payload.pop("repo_nature", None)
    restored = SessionResult.from_json(payload)
    assert restored.repo_nature == "library"


def test_session_result_full_roundtrip_with_new_fields() -> None:
    # Verify the full object serialization round-trips cleanly with all new fields.
    cards = [
        _foresight_card(tier="corroborated"),
        _foresight_card(tier="speculative", layer="backend"),
    ]
    session = make_session(foresight_cards=cards, repo_nature="app/cli")
    restored = SessionResult.from_json(session.to_json())
    assert restored.repo_nature == "app/cli"
    assert len(restored.foresight_cards) == 2
    assert restored.foresight_cards[0].tier == "corroborated"
    assert restored.foresight_cards[1].layer == "backend"


# ---------------------------------------------------------------------------
# 0.3.0: SessionResult.pr_decisions holds pr_archaeology.PRDecisions
# ---------------------------------------------------------------------------

def test_session_result_pr_decisions_roundtrip_with_diff_excerpt() -> None:
    from hijack.core.pr_archaeology import PRDecision, PRDecisions

    decisions = PRDecisions(
        items_scanned=5,
        patterns=[],
        decisions=[
            PRDecision(
                ref="PR#42",
                title="Add sync wrapper",
                date="2024-08-12 14:30:00 +0000",
                body_excerpt="This adds a sync wrapper around the async client.",
                matched_patterns=["instead of"],
                maintainer_comment="Won't merge — breaks the async contract.",
                intent_kind="rejection",
                diff_excerpt="+def sync_wrapper():\n+    return asyncio.run(...)",
            )
        ],
    )
    session = make_session(pr_decisions=decisions)
    restored = SessionResult.from_json(session.to_json())
    assert restored.pr_decisions is not None
    assert len(restored.pr_decisions.decisions) == 1
    restored_decision = restored.pr_decisions.decisions[0]
    assert restored_decision.ref == "PR#42"
    assert restored_decision.intent_kind == "rejection"
    assert restored_decision.diff_excerpt == "+def sync_wrapper():\n+    return asyncio.run(...)"


# ---------------------------------------------------------------------------
# ProbeRecord dataclass + AnalysisRule.probe (behavior probe)
# ---------------------------------------------------------------------------

def _probe(**kwargs) -> ProbeRecord:
    defaults = dict(
        task="Parse a config file and merge overrides",
        verdict="discriminated",
        control_behavior="crashes on double-enter (re-entrant call)",
        treatment_behavior="raises a clear guard error before corrupting state",
        model="haiku",
    )
    defaults.update(kwargs)
    return ProbeRecord(**defaults)


def test_probe_record_roundtrip() -> None:
    p = _probe()
    assert ProbeRecord.from_json(p.to_json()) == p


def test_probe_record_verdict_out_of_range_demoted() -> None:
    # Machine-check, not fail-fast: an out-of-range verdict is demoted to
    # "not_discriminated" (conservative direction) rather than dropped/raised.
    payload = _probe().to_json()
    payload["verdict"] = "bogus_verdict"
    restored = ProbeRecord.from_json(payload)
    assert restored.verdict == "not_discriminated"


def test_rule_default_probe_is_none() -> None:
    rule = make_rule()
    assert rule.probe is None


def test_rule_probe_omitted_from_json_when_none() -> None:
    rule = make_rule()
    assert "probe" not in rule.to_json()


def test_rule_probe_roundtrip() -> None:
    rule = make_rule(probe=_probe())
    data = rule.to_json()
    assert data["probe"]["verdict"] == "discriminated"
    restored = AnalysisRule.from_json(data)
    assert restored.probe == _probe()


def test_rule_probe_backward_compat_when_key_missing() -> None:
    # Older session.json files (pre-probe-slice) won't have a probe key.
    payload = make_rule().to_json()
    payload.pop("probe", None)
    restored = AnalysisRule.from_json(payload)
    assert restored.probe is None


def test_session_result_satd_items_roundtrip() -> None:
    from hijack.core.satd import SatdItem, SatdItems

    items = SatdItems(items=[SatdItem(ref="src/foo.py:42", tag="FIXME", text="race condition")])
    session = make_session(satd_items=items)
    restored = SessionResult.from_json(session.to_json())
    assert restored.satd_items is not None
    assert len(restored.satd_items.items) == 1
    assert restored.satd_items.items[0].ref == "src/foo.py:42"
    assert restored.satd_items.items[0].tag == "FIXME"
    assert restored.satd_items.items[0].text == "race condition"
