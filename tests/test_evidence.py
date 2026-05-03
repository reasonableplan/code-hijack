"""Tests for hijack.core.evidence — citation detection and session-level metrics."""

from __future__ import annotations

from hijack.core.evidence import (
    classify_rule,
    compute_evidence_metrics,
    render_metrics_md,
)
from hijack.core.models import (
    AnalysisRule,
    CategoryResult,
    Evidence,
    SessionResult,
)


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


class TestSHAVerification:
    """When valid_shas is provided, hallucinated commit SHAs land in fake_citation."""

    _REAL = {"a1b2c3d4e5f6789012345678901234567890abcd"}

    def test_real_sha_prefix_match_is_cited(self) -> None:
        # Short SHA "a1b2c3d" prefix-matches the real 40-char SHA above.
        assert (
            classify_rule(_rule("commit a1b2c3d explains it"), valid_shas=self._REAL)
            == "cited"
        )

    def test_unknown_sha_is_fake_citation(self) -> None:
        assert (
            classify_rule(_rule("commit deadbeef shows it"), valid_shas=self._REAL)
            == "fake_citation"
        )

    def test_no_valid_shas_disables_check(self) -> None:
        # Backward compatibility: valid_shas=None means accept all syntactically
        # valid commit citations. Phase A behaviour.
        assert classify_rule(_rule("commit deadbeef shows it"), valid_shas=None) == "cited"

    def test_empty_valid_shas_set_disables_check(self) -> None:
        # Empty set is treated like "no truth pool" — same as None, since the
        # session may have legitimately collected no history.
        assert (
            classify_rule(_rule("commit deadbeef shows it"), valid_shas=set())
            == "fake_citation"
        )

    def test_mixed_real_and_fake_shas_classified_cited(self) -> None:
        # Reason citing both a real and a fake SHA still has real grounding.
        reason = "commit a1b2c3d (real) and commit deadbeef (made up)"
        assert classify_rule(_rule(reason), valid_shas=self._REAL) == "cited"

    def test_fake_sha_with_adr_citation_falls_through_to_cited(self) -> None:
        # When the rule has BOTH a fake SHA AND a non-commit citation (ADR),
        # the non-commit citation wins — there's still real grounding.
        reason = "ADR 0003 documents this; see also commit deadbeef"
        assert classify_rule(_rule(reason), valid_shas=self._REAL) == "cited"

    def test_fake_sha_with_generic_phrase_is_fake_not_generic(self) -> None:
        # Bucket priority: fake_citation surfaces the hallucination signal.
        reason = "commit deadbeef — best practice for this codebase"
        assert (
            classify_rule(_rule(reason), valid_shas=self._REAL) == "fake_citation"
        )

    def test_compute_evidence_metrics_uses_session_historic_shas(self) -> None:
        s = _session(
            {
                "architecture": [
                    _rule("commit a1b2c3d shows it"),
                    _rule("commit deadbeef hallucinated"),
                ]
            }
        )
        s.historic_shas = list(self._REAL)
        m = compute_evidence_metrics(s)
        assert m.overall.cited == 1
        assert m.overall.fake_citation == 1

    def test_render_metrics_md_shows_fake_citation_row(self) -> None:
        s = _session(
            {"architecture": [_rule("commit deadbeef hallucinated")]}
        )
        s.historic_shas = list(self._REAL)
        out = render_metrics_md(compute_evidence_metrics(s))
        assert "Fake citation" in out
        assert "hallucinated" in out.lower() or "Fake citation" in out


# ---------------------------------------------------------------------------
# classify_rule via structured Evidence list (Phase D1, Path A)
# ---------------------------------------------------------------------------

def _ev(**kwargs) -> Evidence:
    defaults = dict(
        kind="commit",
        ref="a1b2c3d",
        headline="h",
        quote="q",
        intent_kind=None,
        date=None,
    )
    defaults.update(kwargs)
    return Evidence(**defaults)


def _rule_with_ev(evidence: list[Evidence], reason: str = "") -> AnalysisRule:
    return AnalysisRule(
        rule="r",
        priority="MUST",
        confidence="high",
        ref_files=[],
        good_example="",
        bad_example="",
        reason=reason,
        evidence=evidence,
    )


class TestClassifyViaEvidenceList:
    """When rule.evidence is non-empty, structured path takes priority."""

    _VALID_SHAS = {"a1b2c3d4e5f6789012345678901234567890abcd"}
    _VALID_DOCS = {"docs/adr/0001.md"}

    def test_valid_commit_evidence_is_cited(self) -> None:
        rule = _rule_with_ev([_ev(kind="commit", ref="a1b2c3d")])
        assert (
            classify_rule(rule, valid_shas=self._VALID_SHAS) == "cited"
        )

    def test_invalid_commit_evidence_is_fake_citation(self) -> None:
        rule = _rule_with_ev([_ev(kind="commit", ref="deadbeef")])
        assert (
            classify_rule(rule, valid_shas=self._VALID_SHAS) == "fake_citation"
        )

    def test_mixed_real_and_fake_resolves_to_cited(self) -> None:
        rule = _rule_with_ev(
            [
                _ev(kind="commit", ref="a1b2c3d"),
                _ev(kind="commit", ref="deadbeef"),
            ]
        )
        assert (
            classify_rule(rule, valid_shas=self._VALID_SHAS) == "cited"
        )

    def test_valid_doc_evidence_is_cited(self) -> None:
        rule = _rule_with_ev([_ev(kind="doc", ref="docs/adr/0001.md")])
        assert (
            classify_rule(rule, valid_doc_paths=self._VALID_DOCS) == "cited"
        )

    def test_unknown_doc_path_is_fake_citation(self) -> None:
        rule = _rule_with_ev([_ev(kind="doc", ref="docs/adr/9999.md")])
        assert (
            classify_rule(rule, valid_doc_paths=self._VALID_DOCS)
            == "fake_citation"
        )

    def test_evidence_path_overrides_reason_text(self) -> None:
        # Even if reason has [no-evidence] marker, a populated evidence list
        # takes priority — the structured field is the authoritative signal.
        rule = _rule_with_ev(
            [_ev(kind="commit", ref="a1b2c3d")],
            reason="[no-evidence] inferred",
        )
        assert (
            classify_rule(rule, valid_shas=self._VALID_SHAS) == "cited"
        )

    def test_empty_pools_disable_validation(self) -> None:
        # No truth pool → evidence accepted as-is (best-effort, e.g. the
        # repo had no git history at all).
        rule = _rule_with_ev([_ev(kind="commit", ref="anything")])
        assert classify_rule(rule, valid_shas=None) == "cited"
        assert classify_rule(rule, valid_shas=set()) == "cited"

    def test_empty_evidence_list_falls_through_to_reason_path(self) -> None:
        # Confirms backward compat with Phase A/B sessions.
        rule = _rule_with_ev([], reason="[no-evidence] inferred")
        assert classify_rule(rule) == "no_evidence"

        rule = _rule_with_ev([], reason="commit a1b2c3d shows it")
        assert classify_rule(rule, valid_shas=self._VALID_SHAS) == "cited"

    def test_compute_metrics_uses_session_repo_doc_paths(self) -> None:
        s = _session({"architecture": [_rule_with_ev([_ev(kind="doc", ref="docs/adr/0001.md")])]})
        s.repo_doc_paths = ["docs/adr/0001.md"]
        m = compute_evidence_metrics(s)
        assert m.overall.cited == 1

    def test_doc_evidence_with_unknown_path_via_session_paths_is_fake(self) -> None:
        s = _session({"architecture": [_rule_with_ev([_ev(kind="doc", ref="docs/adr/9999.md")])]})
        s.repo_doc_paths = ["docs/adr/0001.md"]
        m = compute_evidence_metrics(s)
        assert m.overall.fake_citation == 1


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
