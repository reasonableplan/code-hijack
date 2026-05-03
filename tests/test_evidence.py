"""Tests for hijack.core.evidence — citation detection and session-level metrics."""

from __future__ import annotations

from hijack.core.evidence import (
    classify_rule,
    compute_evidence_metrics,
    render_metrics_md,
)
from hijack.core.models import AnalysisRule, CategoryResult, SessionResult


def _rule(reason: str) -> AnalysisRule:
    return AnalysisRule(
        rule="x",
        priority="MUST",
        confidence="high",
        ref_files=["a.py:1"],
        good_example="g",
        bad_example="b",
        reason=reason,
    )


def _session(rules_by_category: dict[str, list[AnalysisRule]]) -> SessionResult:
    cats = [
        CategoryResult(
            category=name,
            design_intent="",
            rules=rules,
            anti_patterns=[],
            file_type_guides={},
            checklist=[],
            raw_llm_output="",
        )
        for name, rules in rules_by_category.items()
    ]
    return SessionResult(
        session_id="2026-05-04_test",
        target="t",
        model="m",
        timestamp="2026-05-04T00:00:00",
        selected_files=[],
        categories=cats,
        analysis_duration_seconds=0.0,
        project_structure="",
    )


# ---------------------------------------------------------------------------
# classify_rule — every reason ends up in exactly one bucket
# ---------------------------------------------------------------------------

class TestClassifyCited:
    def test_commit_short_sha(self) -> None:
        assert classify_rule(_rule("commit a1b2c3d showed this fails")) == "cited"

    def test_commit_full_sha(self) -> None:
        assert (
            classify_rule(_rule("commit a1b2c3d4e5f6789012345678901234567890abcd"))
            == "cited"
        )

    def test_commit_uppercase(self) -> None:
        assert classify_rule(_rule("COMMIT ABC1234: rolled back")) == "cited"

    def test_pr_with_hash(self) -> None:
        assert classify_rule(_rule("see PR #142 for context")) == "cited"

    def test_pr_pull_form(self) -> None:
        assert classify_rule(_rule("rationale in pull/142")) == "cited"

    def test_quoted_revert_subject(self) -> None:
        assert classify_rule(_rule("'Revert: drop pydantic' showed why")) == "cited"

    def test_citation_beats_generic_phrase(self) -> None:
        # A reason that includes both a citation AND a generic phrase is cited —
        # the citation provides real grounding even if the phrasing is fluffy.
        reason = "commit a1b2c3d — best practice for this codebase"
        assert classify_rule(_rule(reason)) == "cited"

    def test_adr_keyword_cited(self) -> None:
        assert classify_rule(_rule("ADR 0003 documented this choice")) == "cited"

    def test_readme_keyword_cited(self) -> None:
        assert classify_rule(_rule("README explains the dataclass-only stance")) == "cited"

    def test_architecture_keyword_cited(self) -> None:
        assert classify_rule(_rule("per ARCHITECTURE.md section 4")) == "cited"

    def test_md_path_in_backticks_cited(self) -> None:
        assert (
            classify_rule(_rule("see `docs/adr/0003-drop-pydantic.md` for context"))
            == "cited"
        )


class TestClassifyNoEvidence:
    def test_marker_lowercase(self) -> None:
        assert classify_rule(_rule("[no-evidence] inferred from style")) == "no_evidence"

    def test_marker_uppercase(self) -> None:
        assert classify_rule(_rule("[NO-EVIDENCE] generic")) == "no_evidence"

    def test_marker_beats_generic_phrase(self) -> None:
        # Explicit no-evidence wins even if generic phrases also appear.
        assert classify_rule(_rule("[no-evidence] best practice")) == "no_evidence"


class TestClassifyGeneric:
    def test_best_practice(self) -> None:
        assert classify_rule(_rule("This is a best practice")) == "generic"

    def test_industry_standard(self) -> None:
        assert classify_rule(_rule("Industry standard convention")) == "generic"

    def test_more_readable(self) -> None:
        assert classify_rule(_rule("makes the code more readable")) == "generic"


class TestClassifyOther:
    def test_specific_technical_reason_uncited(self) -> None:
        # Real-sounding technical reason but no citation, no generic phrase —
        # falls through to 'other'. Honest classification.
        reason = "subprocess without capture_output drops stderr on failure"
        assert classify_rule(_rule(reason)) == "other"

    def test_empty_reason(self) -> None:
        assert classify_rule(_rule("")) == "other"


class TestNotCommitFalsePositives:
    def test_word_committed_not_a_citation(self) -> None:
        # 'commit' must be followed by hex — the word "committed" should not match.
        assert classify_rule(_rule("the team committed to this style")) == "other"

    def test_short_hex_below_threshold(self) -> None:
        # 5 hex chars is below the 6-char minimum.
        assert classify_rule(_rule("commit abcde failed")) == "other"


# ---------------------------------------------------------------------------
# compute_evidence_metrics
# ---------------------------------------------------------------------------

class TestComputeEvidenceMetrics:
    def test_empty_session(self) -> None:
        m = compute_evidence_metrics(_session({}))
        assert m.overall.total == 0
        assert m.by_category == {}

    def test_overall_and_per_category_tally(self) -> None:
        m = compute_evidence_metrics(
            _session(
                {
                    "architecture": [
                        _rule("commit a1b2c3d: rationale"),
                        _rule("[no-evidence] guess"),
                    ],
                    "coding_style": [
                        _rule("best practice"),
                        _rule("commit f00ba12: shown"),
                        _rule("just because"),
                    ],
                }
            )
        )
        assert m.overall.cited == 2
        assert m.overall.no_evidence == 1
        assert m.overall.generic == 1
        assert m.overall.other == 1
        assert m.overall.total == 5

        arch = m.by_category["architecture"]
        assert (arch.cited, arch.no_evidence, arch.generic, arch.other) == (1, 1, 0, 0)

        style = m.by_category["coding_style"]
        assert (style.cited, style.no_evidence, style.generic, style.other) == (1, 0, 1, 1)

    def test_cited_ratio_computation(self) -> None:
        m = compute_evidence_metrics(
            _session(
                {
                    "architecture": [
                        _rule("commit a1b2c3d"),
                        _rule("commit b2c3d4e"),
                        _rule("just words"),
                        _rule("more words"),
                    ],
                }
            )
        )
        assert m.overall.cited_ratio == 0.5


# ---------------------------------------------------------------------------
# render_metrics_md
# ---------------------------------------------------------------------------

class TestRenderMetricsMd:
    def test_empty_metrics_returns_empty_string(self) -> None:
        m = compute_evidence_metrics(_session({}))
        assert render_metrics_md(m) == ""

    def test_renders_overall_and_per_category(self) -> None:
        m = compute_evidence_metrics(
            _session(
                {
                    "architecture": [
                        _rule("commit a1b2c3d"),
                        _rule("[no-evidence] x"),
                    ]
                }
            )
        )
        out = render_metrics_md(m)
        assert "## Evidence Coverage" in out
        assert "**Cited**: 1 (50%)" in out
        assert "**No-evidence (flagged)**: 1 (50%)" in out
        assert "### By Category" in out
        assert "| architecture |" in out

    def test_metrics_to_json_roundtrip_safe(self) -> None:
        # Defensive: to_json must produce primitives only, for embedding in
        # session.json down the line.
        import json
        m = compute_evidence_metrics(
            _session({"architecture": [_rule("commit a1b2c3d")]})
        )
        # Should not raise.
        json.dumps(m.to_json())
