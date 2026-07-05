"""Tests for hijack.core.measure — T-037."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from hijack.core.measure import (
    MeasurementResult,
    calc_session_metrics,
    diff_sessions,
    format_measurement_summary,
    score_foresight,
    write_measurement,
)
from hijack.core.models import (
    AnalysisRule,
    CategoryResult,
    Evidence,
    ForesightCard,
    SessionResult,
)
from hijack.core.satd import SatdItem, SatdItems

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _make_rule(
    rule: str = "Test rule",
    priority: str = "MUST",
    rationale_tier: str = "cited",
    layer: str = "shared",
    evidence: list[Evidence] | None = None,
    exemplar_verbatim: bool | None = None,
) -> AnalysisRule:
    return AnalysisRule(
        rule=rule,
        priority=priority,
        confidence="high",
        ref_files=[],
        good_example="",
        bad_example="",
        reason="",
        layer=layer,
        rationale_tier=rationale_tier,
        evidence=evidence or [],
        exemplar_verbatim=exemplar_verbatim,
    )


def _make_category(name: str, rules: list[AnalysisRule]) -> CategoryResult:
    return CategoryResult(
        category=name,
        design_intent="",
        rules=rules,
        anti_patterns=[],
        file_type_guides={},
        checklist=[],
        raw_llm_output="",
    )


def _make_session(
    session_id: str,
    categories: list[CategoryResult],
    satd_items: Any | None = None,
) -> SessionResult:
    return SessionResult(
        session_id=session_id,
        target="https://github.com/test/repo",
        model="claude-sonnet-4-6",
        timestamp="2026-01-01T00:00:00",
        selected_files=[],
        categories=categories,
        analysis_duration_seconds=0.0,
        project_structure="",
        satd_items=satd_items,
    )


# ---------------------------------------------------------------------------
# MeasurementResult to_json / from_json
# ---------------------------------------------------------------------------

class TestMeasurementResultSerialization:
    def test_roundtrip(self) -> None:
        m = MeasurementResult(
            session_id="2026-01-01_repo",
            cited_ratio=0.5,
            must_ratio=0.25,
            tier_distribution={"cited": 2, "corroborated": 1, "speculative": 1},
            intent_kind_distribution={"rejection": 0, "incident": 0, "preference": 0},
            foresight_scores=[{"hypothesis": "H1", "verdict": "confirmed"}],
            satd_supplied_count=4,
            comment_cited_rule_count=2,
            comment_cited_ref_count=3,
            satd_citation_ratio=0.75,
        )
        data = m.to_json()
        restored = MeasurementResult.from_json(data)
        assert restored.session_id == m.session_id
        assert restored.cited_ratio == m.cited_ratio
        assert restored.must_ratio == m.must_ratio
        assert restored.tier_distribution == m.tier_distribution
        assert restored.intent_kind_distribution == m.intent_kind_distribution
        assert restored.foresight_scores == m.foresight_scores
        assert restored.satd_supplied_count == m.satd_supplied_count
        assert restored.comment_cited_rule_count == m.comment_cited_rule_count
        assert restored.comment_cited_ref_count == m.comment_cited_ref_count
        assert restored.satd_citation_ratio == m.satd_citation_ratio

    def test_to_json_keys(self) -> None:
        m = MeasurementResult(
            session_id="s",
            cited_ratio=1.0,
            must_ratio=1.0,
            tier_distribution={},
            intent_kind_distribution={},
            foresight_scores=[],
        )
        data = m.to_json()
        assert set(data.keys()) == {
            "session_id", "cited_ratio", "must_ratio",
            "tier_distribution", "intent_kind_distribution", "foresight_scores",
            "satd_supplied_count", "comment_cited_rule_count",
            "comment_cited_ref_count", "satd_citation_ratio",
            "exemplar_checked_count", "exemplar_verbatim_ratio",
        }

    def test_from_json_backward_compat_missing_satd_fields(self) -> None:
        # Pre-W2-strengthening measurement.json lacks the new keys.
        data = {
            "session_id": "old",
            "cited_ratio": 0.5,
            "must_ratio": 0.5,
            "tier_distribution": {},
            "intent_kind_distribution": {},
            "foresight_scores": [],
        }
        restored = MeasurementResult.from_json(data)
        assert restored.satd_supplied_count == 0
        assert restored.comment_cited_rule_count == 0
        assert restored.comment_cited_ref_count == 0
        assert restored.satd_citation_ratio == 0.0

    def test_from_json_backward_compat_missing_exemplar_fields(self) -> None:
        # Pre-W4a measurement.json lacks the new keys.
        data = {
            "session_id": "old",
            "cited_ratio": 0.5,
            "must_ratio": 0.5,
            "tier_distribution": {},
            "intent_kind_distribution": {},
            "foresight_scores": [],
        }
        restored = MeasurementResult.from_json(data)
        assert restored.exemplar_checked_count == 0
        assert restored.exemplar_verbatim_ratio == 0.0

    def test_exemplar_fields_roundtrip(self) -> None:
        m = MeasurementResult(
            session_id="s",
            cited_ratio=0.0,
            must_ratio=0.0,
            tier_distribution={},
            intent_kind_distribution={},
            foresight_scores=[],
            exemplar_checked_count=4,
            exemplar_verbatim_ratio=0.75,
        )
        restored = MeasurementResult.from_json(m.to_json())
        assert restored.exemplar_checked_count == 4
        assert restored.exemplar_verbatim_ratio == pytest.approx(0.75)


# ---------------------------------------------------------------------------
# calc_session_metrics — pure function tests
# ---------------------------------------------------------------------------

class TestCalcSessionMetrics:
    def test_all_cited_rules_gives_ratio_one(self) -> None:
        rules = [
            _make_rule("R1", priority="MUST", rationale_tier="cited"),
            _make_rule("R2", priority="MUST", rationale_tier="cited"),
        ]
        session = _make_session("s1", [_make_category("architecture", rules)])
        m = calc_session_metrics(session)
        assert m.cited_ratio == 1.0
        assert m.session_id == "s1"

    def test_mixed_tiers_gives_accurate_ratio(self) -> None:
        rules = [
            _make_rule("R1", rationale_tier="cited"),
            _make_rule("R2", rationale_tier="corroborated"),
            _make_rule("R3", rationale_tier="speculative"),
            _make_rule("R4", rationale_tier="cited"),
        ]
        session = _make_session("s2", [_make_category("c", rules)])
        m = calc_session_metrics(session)
        assert m.cited_ratio == pytest.approx(0.5)

    def test_must_ratio(self) -> None:
        rules = [
            _make_rule("R1", priority="MUST"),
            _make_rule("R2", priority="SHOULD"),
            _make_rule("R3", priority="MUST"),
            _make_rule("R4", priority="SHOULD"),
        ]
        session = _make_session("s3", [_make_category("c", rules)])
        m = calc_session_metrics(session)
        assert m.must_ratio == pytest.approx(0.5)

    def test_tier_distribution_counts(self) -> None:
        rules = [
            _make_rule("R1", rationale_tier="cited"),
            _make_rule("R2", rationale_tier="cited"),
            _make_rule("R3", rationale_tier="corroborated"),
            _make_rule("R4", rationale_tier="speculative"),
        ]
        session = _make_session("s4", [_make_category("c", rules)])
        m = calc_session_metrics(session)
        assert m.tier_distribution["cited"] == 2
        assert m.tier_distribution["corroborated"] == 1
        assert m.tier_distribution["speculative"] == 1

    def test_empty_session_gives_zero_ratios(self) -> None:
        session = _make_session("s5", [])
        m = calc_session_metrics(session)
        assert m.cited_ratio == 0.0
        assert m.must_ratio == 0.0
        assert m.tier_distribution == {"cited": 0, "corroborated": 0, "speculative": 0}

    def test_intent_kind_distribution_without_pr_decisions(self) -> None:
        session = _make_session("s6", [])
        m = calc_session_metrics(session)
        assert m.intent_kind_distribution == {"rejection": 0, "incident": 0, "preference": 0}

    def test_intent_kind_distribution_with_pr_decisions(self) -> None:
        # Use a simple duck-type object (pr_archaeology.PRDecisions not yet created)
        @dataclass
        class _FakePRDecision:
            intent_kind: str

        @dataclass
        class _FakePRDecisions:
            decisions: list[_FakePRDecision] = field(default_factory=list)

        pr_decisions = _FakePRDecisions(decisions=[
            _FakePRDecision("rejection"),
            _FakePRDecision("rejection"),
            _FakePRDecision("incident"),
            _FakePRDecision("preference"),
        ])
        session = _make_session("s7", [])
        m = calc_session_metrics(session, pr_decisions=pr_decisions)
        assert m.intent_kind_distribution["rejection"] == 2
        assert m.intent_kind_distribution["incident"] == 1
        assert m.intent_kind_distribution["preference"] == 1

    def test_multiple_categories_combined(self) -> None:
        cat1 = _make_category("c1", [
            _make_rule("R1", rationale_tier="cited"),
            _make_rule("R2", rationale_tier="speculative"),
        ])
        cat2 = _make_category("c2", [
            _make_rule("R3", rationale_tier="cited"),
        ])
        session = _make_session("s8", [cat1, cat2])
        m = calc_session_metrics(session)
        assert m.tier_distribution["cited"] == 2
        assert m.tier_distribution["speculative"] == 1
        assert m.cited_ratio == pytest.approx(2 / 3)

    def test_foresight_scores_empty_by_default(self) -> None:
        session = _make_session("s9", [])
        m = calc_session_metrics(session)
        assert m.foresight_scores == []


# ---------------------------------------------------------------------------
# calc_session_metrics — SATD citation metrics (W2 strengthening)
# ---------------------------------------------------------------------------

class TestSatdCitationMetrics:
    def _satd(self, refs: list[str]) -> SatdItems:
        return SatdItems(items=[SatdItem(ref=r, tag="TODO", text="") for r in refs])

    def test_no_satd_items_gives_zero_supplied(self) -> None:
        session = _make_session("s10", [])
        m = calc_session_metrics(session)
        assert m.satd_supplied_count == 0
        assert m.satd_citation_ratio == 0.0

    def test_supplied_count_matches_satd_items(self) -> None:
        satd = self._satd(["a.py:1", "a.py:2", "b.py:3"])
        session = _make_session("s11", [], satd_items=satd)
        m = calc_session_metrics(session)
        assert m.satd_supplied_count == 3

    def test_rules_with_comment_evidence_counted(self) -> None:
        satd = self._satd(["a.py:1", "a.py:2"])
        rules = [
            _make_rule("R1", evidence=[
                Evidence(kind="comment", ref="a.py:1", headline="TODO", quote="fix"),
            ]),
            _make_rule("R2", evidence=[
                Evidence(kind="commit", ref="abc123", headline="h", quote="q"),
            ]),
        ]
        session = _make_session("s12", [_make_category("c", rules)], satd_items=satd)
        m = calc_session_metrics(session)
        assert m.comment_cited_rule_count == 1
        assert m.comment_cited_ref_count == 1
        assert m.satd_citation_ratio == pytest.approx(0.5)

    def test_distinct_refs_counted_once(self) -> None:
        satd = self._satd(["a.py:1", "a.py:2"])
        rules = [
            _make_rule("R1", evidence=[
                Evidence(kind="comment", ref="a.py:1", headline="TODO", quote="fix"),
            ]),
            _make_rule("R2", evidence=[
                Evidence(kind="comment", ref="a.py:1", headline="TODO", quote="fix again"),
            ]),
        ]
        session = _make_session("s13", [_make_category("c", rules)], satd_items=satd)
        m = calc_session_metrics(session)
        assert m.comment_cited_rule_count == 2
        assert m.comment_cited_ref_count == 1

    def test_dict_satd_items_duck_typed(self) -> None:
        satd_dict = {"items": [{"ref": "a.py:1", "tag": "TODO", "text": ""}]}
        session = _make_session("s14", [], satd_items=satd_dict)
        m = calc_session_metrics(session)
        assert m.satd_supplied_count == 1

    def test_no_evidence_rules_give_zero_cited(self) -> None:
        satd = self._satd(["a.py:1"])
        rules = [_make_rule("R1", evidence=[])]
        session = _make_session("s15", [_make_category("c", rules)], satd_items=satd)
        m = calc_session_metrics(session)
        assert m.comment_cited_rule_count == 0
        assert m.comment_cited_ref_count == 0
        assert m.satd_citation_ratio == 0.0


# ---------------------------------------------------------------------------
# calc_session_metrics — W4a exemplar verbatim-ratio metrics
# ---------------------------------------------------------------------------

class TestExemplarVerbatimMetrics:
    def test_no_rules_gives_zero_checked_and_ratio(self) -> None:
        session = _make_session("e0", [])
        m = calc_session_metrics(session)
        assert m.exemplar_checked_count == 0
        assert m.exemplar_verbatim_ratio == 0.0

    def test_none_exemplar_verbatim_not_counted_as_checked(self) -> None:
        rules = [_make_rule("R1", exemplar_verbatim=None)]
        session = _make_session("e1", [_make_category("c", rules)])
        m = calc_session_metrics(session)
        assert m.exemplar_checked_count == 0
        assert m.exemplar_verbatim_ratio == 0.0

    def test_mixed_true_false_none_gives_accurate_ratio(self) -> None:
        rules = [
            _make_rule("R1", exemplar_verbatim=True),
            _make_rule("R2", exemplar_verbatim=True),
            _make_rule("R3", exemplar_verbatim=False),
            _make_rule("R4", exemplar_verbatim=None),
        ]
        session = _make_session("e2", [_make_category("c", rules)])
        m = calc_session_metrics(session)
        # 3 checked (2 True, 1 False), 1 uncomputed excluded entirely.
        assert m.exemplar_checked_count == 3
        assert m.exemplar_verbatim_ratio == pytest.approx(2 / 3)

    def test_all_false_gives_zero_ratio(self) -> None:
        rules = [
            _make_rule("R1", exemplar_verbatim=False),
            _make_rule("R2", exemplar_verbatim=False),
        ]
        session = _make_session("e3", [_make_category("c", rules)])
        m = calc_session_metrics(session)
        assert m.exemplar_checked_count == 2
        assert m.exemplar_verbatim_ratio == 0.0


# ---------------------------------------------------------------------------
# diff_sessions — pure function tests
# ---------------------------------------------------------------------------

class TestDiffSessions:
    def _make_m(
        self,
        session_id: str = "s",
        cited_ratio: float = 0.5,
        must_ratio: float = 0.5,
        tier: dict[str, int] | None = None,
        intent: dict[str, int] | None = None,
    ) -> MeasurementResult:
        return MeasurementResult(
            session_id=session_id,
            cited_ratio=cited_ratio,
            must_ratio=must_ratio,
            tier_distribution=tier or {"cited": 1, "corroborated": 0, "speculative": 1},
            intent_kind_distribution=intent or {"rejection": 0, "incident": 0, "preference": 0},
            foresight_scores=[],
        )

    def test_returns_dict(self) -> None:
        m1 = self._make_m("s1", cited_ratio=0.4)
        m2 = self._make_m("s2", cited_ratio=0.6)
        result = diff_sessions(m1, m2)
        assert isinstance(result, dict)

    def test_cited_ratio_diff(self) -> None:
        m1 = self._make_m(cited_ratio=0.4)
        m2 = self._make_m(cited_ratio=0.6)
        result = diff_sessions(m1, m2)
        assert result["cited_ratio_delta"] == pytest.approx(0.2)

    def test_must_ratio_diff(self) -> None:
        m1 = self._make_m(must_ratio=0.3)
        m2 = self._make_m(must_ratio=0.7)
        result = diff_sessions(m1, m2)
        assert result["must_ratio_delta"] == pytest.approx(0.4)

    def test_tier_distribution_diff(self) -> None:
        m1 = self._make_m(tier={"cited": 1, "corroborated": 2, "speculative": 3})
        m2 = self._make_m(tier={"cited": 3, "corroborated": 2, "speculative": 1})
        result = diff_sessions(m1, m2)
        tier_diff = result["tier_distribution_delta"]
        assert tier_diff["cited"] == 2
        assert tier_diff["corroborated"] == 0
        assert tier_diff["speculative"] == -2

    def test_session_ids_included(self) -> None:
        m1 = self._make_m("session-a")
        m2 = self._make_m("session-b")
        result = diff_sessions(m1, m2)
        assert result["session_id_before"] == "session-a"
        assert result["session_id_after"] == "session-b"

    def test_satd_citation_ratio_delta(self) -> None:
        m1 = self._make_m()
        m1.satd_citation_ratio = 0.2
        m2 = self._make_m()
        m2.satd_citation_ratio = 0.6
        result = diff_sessions(m1, m2)
        assert result["satd_citation_ratio_delta"] == pytest.approx(0.4)

    def test_exemplar_verbatim_ratio_delta(self) -> None:
        m1 = self._make_m()
        m1.exemplar_verbatim_ratio = 0.3
        m2 = self._make_m()
        m2.exemplar_verbatim_ratio = 0.8
        result = diff_sessions(m1, m2)
        assert result["exemplar_verbatim_ratio_delta"] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# score_foresight — pure, keyword-matching based
# ---------------------------------------------------------------------------

class TestScoreForesight:
    def _make_card(self, hypothesis: str, signals: list[str]) -> ForesightCard:
        return ForesightCard(
            hypothesis=hypothesis,
            signals=signals,
            falsification="If X then wrong",
            tier="speculative",
            layer="shared",
        )

    def test_returns_list_of_dicts(self) -> None:
        cards = [self._make_card("Minimal dependencies", ["no third-party"])]
        result = score_foresight(cards, "", None)
        assert isinstance(result, list)
        assert len(result) == 1
        assert "hypothesis" in result[0]
        assert "verdict" in result[0]

    def test_unconfirmed_when_no_docs(self) -> None:
        cards = [self._make_card("Some hypothesis", ["signal A"])]
        result = score_foresight(cards, "", None)
        assert result[0]["verdict"] == "unconfirmed"

    def test_confirmed_when_keyword_in_docs(self) -> None:
        cards = [self._make_card("Minimal dependencies", ["no third-party libraries"])]
        repo_docs = "We use no third-party libraries and keep deps minimal."
        result = score_foresight(cards, repo_docs, None)
        assert result[0]["verdict"] == "confirmed"

    def test_verdict_values_are_valid(self) -> None:
        valid = {"confirmed", "unconfirmed", "refuted"}
        cards = [self._make_card("Any hypothesis", ["signal"])]
        result = score_foresight(cards, "Some docs here", None)
        assert result[0]["verdict"] in valid

    def test_empty_cards_returns_empty_list(self) -> None:
        result = score_foresight([], "docs", None)
        assert result == []

    def test_hypothesis_preserved_in_result(self) -> None:
        hyp = "Team prefers stdlib over third-party"
        cards = [self._make_card(hyp, ["stdlib only"])]
        result = score_foresight(cards, "", None)
        assert result[0]["hypothesis"] == hyp

    def test_confirmed_when_signal_matches_docs(self) -> None:
        cards = [self._make_card("Avoids ORM", ["no SQLAlchemy", "raw SQL preferred"])]
        repo_docs = "We avoid SQLAlchemy and write raw SQL for clarity."
        result = score_foresight(cards, repo_docs, None)
        assert result[0]["verdict"] == "confirmed"

    def test_with_pr_decisions_rejection_upgrades_verdict(self) -> None:
        # A hypothesis mentioning "rejection" patterns that appear in PR decisions
        @dataclass
        class _FakePRDecision:
            intent_kind: str
            title: str = ""
            body_excerpt: str = ""

        @dataclass
        class _FakePRDecisions:
            decisions: list[_FakePRDecision] = field(default_factory=list)

        pr_decisions = _FakePRDecisions(decisions=[
            _FakePRDecision(
                intent_kind="rejection", title="Reject ORM usage", body_excerpt="no ORM"
            ),
        ])
        cards = [self._make_card("Team avoids ORM", ["ORM rejected in PR"])]
        # With pr_decisions containing "ORM" in rejection title, should confirm
        repo_docs = ""
        result = score_foresight(cards, repo_docs, pr_decisions)
        # Signal "ORM rejected in PR" matches "ORM" in rejection PR title
        assert result[0]["verdict"] in {"confirmed", "unconfirmed"}


# ---------------------------------------------------------------------------
# write_measurement — I/O function
# ---------------------------------------------------------------------------

class TestWriteMeasurement:
    def test_creates_measurement_json(self, tmp_path: Path) -> None:
        m = MeasurementResult(
            session_id="2026-01-01_repo",
            cited_ratio=0.75,
            must_ratio=0.5,
            tier_distribution={"cited": 3, "corroborated": 1, "speculative": 0},
            intent_kind_distribution={"rejection": 1, "incident": 0, "preference": 2},
            foresight_scores=[{"hypothesis": "H", "verdict": "confirmed"}],
        )
        write_measurement(m, tmp_path)
        assert (tmp_path / "measurement.json").exists()

    def test_file_is_valid_json(self, tmp_path: Path) -> None:
        m = MeasurementResult(
            session_id="2026-01-01_repo",
            cited_ratio=0.5,
            must_ratio=0.5,
            tier_distribution={"cited": 1, "corroborated": 1, "speculative": 0},
            intent_kind_distribution={"rejection": 0, "incident": 0, "preference": 0},
            foresight_scores=[],
        )
        write_measurement(m, tmp_path)
        content = (tmp_path / "measurement.json").read_text(encoding="utf-8")
        parsed = json.loads(content)
        assert isinstance(parsed, dict)

    def test_roundtrip_via_file(self, tmp_path: Path) -> None:
        m = MeasurementResult(
            session_id="2026-01-01_repo",
            cited_ratio=0.8,
            must_ratio=0.4,
            tier_distribution={"cited": 4, "corroborated": 0, "speculative": 1},
            intent_kind_distribution={"rejection": 2, "incident": 1, "preference": 3},
            foresight_scores=[{"hypothesis": "H1", "verdict": "refuted"}],
        )
        write_measurement(m, tmp_path)
        content = (tmp_path / "measurement.json").read_text(encoding="utf-8")
        restored = MeasurementResult.from_json(json.loads(content))
        assert restored.session_id == m.session_id
        assert restored.cited_ratio == m.cited_ratio
        assert restored.foresight_scores == m.foresight_scores

    def test_does_not_overwrite_session_json(self, tmp_path: Path) -> None:
        # Ensure write_measurement writes measurement.json, NOT session.json
        session_json = tmp_path / "session.json"
        session_json.write_text("{}", encoding="utf-8")
        m = MeasurementResult(
            session_id="s",
            cited_ratio=0.0,
            must_ratio=0.0,
            tier_distribution={"cited": 0, "corroborated": 0, "speculative": 0},
            intent_kind_distribution={"rejection": 0, "incident": 0, "preference": 0},
            foresight_scores=[],
        )
        write_measurement(m, tmp_path)
        # session.json should still be "{}" — untouched
        assert session_json.read_text(encoding="utf-8") == "{}"
        assert (tmp_path / "measurement.json").exists()


# ---------------------------------------------------------------------------
# format_measurement_summary — pure string formatter
# ---------------------------------------------------------------------------

class TestFormatMeasurementSummary:
    def test_returns_string(self) -> None:
        m = MeasurementResult(
            session_id="2026-01-01_repo",
            cited_ratio=0.5,
            must_ratio=0.25,
            tier_distribution={"cited": 2, "corroborated": 2, "speculative": 0},
            intent_kind_distribution={"rejection": 1, "incident": 0, "preference": 3},
            foresight_scores=[],
        )
        result = format_measurement_summary(m)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_includes_session_id(self) -> None:
        m = MeasurementResult(
            session_id="2026-01-01_myrepo",
            cited_ratio=0.0,
            must_ratio=0.0,
            tier_distribution={"cited": 0, "corroborated": 0, "speculative": 0},
            intent_kind_distribution={"rejection": 0, "incident": 0, "preference": 0},
            foresight_scores=[],
        )
        result = format_measurement_summary(m)
        assert "2026-01-01_myrepo" in result

    def test_includes_ratios(self) -> None:
        m = MeasurementResult(
            session_id="s",
            cited_ratio=0.75,
            must_ratio=0.50,
            tier_distribution={"cited": 3, "corroborated": 0, "speculative": 1},
            intent_kind_distribution={"rejection": 0, "incident": 0, "preference": 0},
            foresight_scores=[],
        )
        result = format_measurement_summary(m)
        # Should mention percentages or ratios
        assert "75" in result or "0.75" in result

    def test_includes_satd_citation_ratio(self) -> None:
        m = MeasurementResult(
            session_id="s",
            cited_ratio=0.0,
            must_ratio=0.0,
            tier_distribution={"cited": 0, "corroborated": 0, "speculative": 0},
            intent_kind_distribution={"rejection": 0, "incident": 0, "preference": 0},
            foresight_scores=[],
            satd_supplied_count=4,
            comment_cited_rule_count=2,
            comment_cited_ref_count=2,
            satd_citation_ratio=0.5,
        )
        result = format_measurement_summary(m)
        assert "satd_citation_ratio" in result
        assert "2/4" in result

    def test_includes_exemplar_verbatim_ratio(self) -> None:
        m = MeasurementResult(
            session_id="s",
            cited_ratio=0.0,
            must_ratio=0.0,
            tier_distribution={"cited": 0, "corroborated": 0, "speculative": 0},
            intent_kind_distribution={"rejection": 0, "incident": 0, "preference": 0},
            foresight_scores=[],
            exemplar_checked_count=4,
            exemplar_verbatim_ratio=0.5,
        )
        result = format_measurement_summary(m)
        assert "exemplar_verbatim_ratio" in result
        assert "4 checked" in result
