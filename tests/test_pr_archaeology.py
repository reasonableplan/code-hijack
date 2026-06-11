"""Tests for core/pr_archaeology.py — PR/issue mining via gh CLI.

TDD: tests written first, then implementation.
All subprocess.run calls are mocked — no real gh/network calls.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from hijack.core.pr_archaeology import (
    PRDecision,
    PRDecisions,
    fetch_pr_decisions,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_gh_result(stdout: str, returncode: int = 0) -> MagicMock:
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    return m


def _pr_item(
    number: int = 1,
    title: str = "Test PR",
    body: str = "decided to switch to new approach",
    merged_at: str | None = None,
    created_at: str = "2024-08-12T14:30:00Z",
) -> dict:
    return {
        "number": number,
        "title": title,
        "body": body,
        "merged_at": merged_at,
        "created_at": created_at,
    }


def _issue_item(
    number: int = 10,
    title: str = "Test Issue",
    body: str = "regression after upgrade",
    created_at: str = "2024-08-12T14:30:00Z",
) -> dict:
    return {
        "number": number,
        "title": title,
        "body": body,
        "created_at": created_at,
    }


def _comment_item(body: str = "Closing without merge", login: str = "maintainer") -> dict:
    return {
        "body": body,
        "user": {"login": login},
    }


# ---------------------------------------------------------------------------
# TestPRDecisionDataclass
# ---------------------------------------------------------------------------

class TestPRDecisionDataclass:
    def test_to_json_includes_all_fields(self) -> None:
        d = PRDecision(
            ref="PR#1",
            title="Add feature",
            date="2024-08-12 14:30:00 +0900",
            body_excerpt="decided to switch approach",
            matched_patterns=["decided to"],
            maintainer_comment="Closing: won't merge",
            intent_kind="rejection",
        )
        data = d.to_json()
        assert data["ref"] == "PR#1"
        assert data["title"] == "Add feature"
        assert data["date"] == "2024-08-12 14:30:00 +0900"
        assert data["body_excerpt"] == "decided to switch approach"
        assert data["matched_patterns"] == ["decided to"]
        assert data["maintainer_comment"] == "Closing: won't merge"
        assert data["intent_kind"] == "rejection"

    def test_from_json_roundtrip(self) -> None:
        d = PRDecision(
            ref="issue#5",
            title="Bug report",
            date="2024-01-01 00:00:00 +0000",
            body_excerpt="regression in v2",
            matched_patterns=["regression"],
            maintainer_comment="",
            intent_kind="incident",
        )
        assert PRDecision.from_json(d.to_json()) == d

    def test_from_json_missing_optional_defaults(self) -> None:
        data = {
            "ref": "PR#9",
            "title": "T",
            "date": "2024-01-01 00:00:00 +0000",
            "body_excerpt": "",
            "matched_patterns": [],
            "maintainer_comment": "",
            "intent_kind": "preference",
        }
        d = PRDecision.from_json(data)
        assert d.ref == "PR#9"
        assert d.intent_kind == "preference"


# ---------------------------------------------------------------------------
# TestPRDecisionsDataclass
# ---------------------------------------------------------------------------

class TestPRDecisionsDataclass:
    def test_has_signal_false_when_empty(self) -> None:
        decisions = PRDecisions(items_scanned=0, patterns=[], decisions=[])
        assert decisions.has_signal is False

    def test_has_signal_true_when_decisions_present(self) -> None:
        d = PRDecision(
            ref="PR#1", title="T", date="2024-01-01 00:00:00 +0000",
            body_excerpt="decided to switch",
            matched_patterns=["decided to"],
            maintainer_comment="",
            intent_kind="rejection",
        )
        decisions = PRDecisions(items_scanned=1, patterns=[], decisions=[d])
        assert decisions.has_signal is True

    def test_to_json_from_json_roundtrip(self) -> None:
        from hijack.core.archaeology import DecisionPattern
        d = PRDecision(
            ref="PR#2", title="Fix", date="2024-06-01 00:00:00 +0000",
            body_excerpt="tried to improve",
            matched_patterns=["tried"],
            maintainer_comment="LGTM",
            intent_kind="preference",
        )
        dp = DecisionPattern(pattern="tried", count=1, examples=["tried to improve"])
        decisions = PRDecisions(items_scanned=5, patterns=[dp], decisions=[d])
        restored = PRDecisions.from_json(decisions.to_json())
        assert restored.items_scanned == 5
        assert len(restored.patterns) == 1
        assert restored.patterns[0].pattern == "tried"
        assert len(restored.decisions) == 1
        assert restored.decisions[0].ref == "PR#2"


# ---------------------------------------------------------------------------
# TestFetchPRDecisionsGracefulSkip
# ---------------------------------------------------------------------------

class TestFetchPRDecisionsGracefulSkip:
    def test_gh_not_installed_returns_empty(self) -> None:
        with patch("subprocess.run", side_effect=FileNotFoundError("gh not found")):
            result = fetch_pr_decisions("https://github.com/owner/repo")
        assert result.items_scanned == 0
        assert result.decisions == []
        assert result.patterns == []

    def test_auth_failure_returns_empty(self) -> None:
        # Non-zero returncode simulates authentication failure
        with patch("subprocess.run", return_value=_make_gh_result("", returncode=1)):
            result = fetch_pr_decisions("https://github.com/owner/repo")
        assert result.items_scanned == 0
        assert result.decisions == []

    def test_rate_limit_returns_empty(self) -> None:
        # GitHub API rate-limit response contains "message" key
        rate_limit_body = json.dumps({"message": "API rate limit exceeded"})
        with patch("subprocess.run", return_value=_make_gh_result(rate_limit_body, returncode=0)):
            result = fetch_pr_decisions("https://github.com/owner/repo")
        assert result.items_scanned == 0
        assert result.decisions == []

    def test_timeout_returns_empty(self) -> None:
        import subprocess
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("gh", 30)):
            result = fetch_pr_decisions("https://github.com/owner/repo")
        assert result.items_scanned == 0
        assert result.decisions == []

    def test_invalid_url_returns_empty(self) -> None:
        # Non-GitHub URL should return empty gracefully
        result = fetch_pr_decisions("https://gitlab.com/owner/repo")
        assert result.items_scanned == 0
        assert result.decisions == []


# ---------------------------------------------------------------------------
# TestFetchPRDecisionsHappyPath
# ---------------------------------------------------------------------------

class TestFetchPRDecisionsHappyPath:
    def _run_fetch(
        self, pr_items: list, issue_items: list, comments_by_pr: dict | None = None
    ) -> PRDecisions:
        """Helper: mock subprocess.run to return canned data for gh api calls."""
        comments_by_pr = comments_by_pr or {}

        call_count = [0]

        def fake_run(args, **kwargs):
            call_count[0] += 1
            cmd = " ".join(str(a) for a in args)
            # PR comments endpoint
            for pr_num, comments in comments_by_pr.items():
                if f"/pulls/{pr_num}/comments" in cmd or f"/issues/{pr_num}/comments" in cmd:
                    return _make_gh_result(json.dumps(comments))
            if "pulls" in cmd and "issues" not in cmd:
                return _make_gh_result(json.dumps(pr_items))
            if "issues" in cmd:
                return _make_gh_result(json.dumps(issue_items))
            return _make_gh_result("[]")

        with patch("subprocess.run", side_effect=fake_run):
            return fetch_pr_decisions("https://github.com/owner/repo")

    def test_closed_unmerged_pr_with_decision_pattern_creates_decision(self) -> None:
        prs = [_pr_item(
            number=1,
            title="Rejected approach",
            body="decided not to use this approach instead of the old one",
            merged_at=None,
        )]
        result = self._run_fetch(prs, [])
        decisions = result.decisions
        assert any(d.ref == "PR#1" for d in decisions)

    def test_merged_pr_excluded_from_decisions(self) -> None:
        # Merged PRs (merged_at is set) should be filtered out
        prs = [_pr_item(
            number=2,
            body="decided to use this approach",
            merged_at="2024-08-12T14:30:00Z",
        )]
        result = self._run_fetch(prs, [])
        assert not any(d.ref == "PR#2" for d in result.decisions)

    def test_wontfix_issue_creates_decision(self) -> None:
        issues = [_issue_item(
            number=10,
            body="regression: decided not to fix this",
        )]
        result = self._run_fetch([], issues)
        assert any(d.ref == "issue#10" for d in result.decisions)

    def test_pr_without_pattern_not_included(self) -> None:
        prs = [_pr_item(
            number=3,
            body="just a regular update with no decision language",
            merged_at=None,
        )]
        result = self._run_fetch(prs, [])
        assert not any(d.ref == "PR#3" for d in result.decisions)

    def test_items_scanned_counts_prs_and_issues(self) -> None:
        prs = [_pr_item(number=i, merged_at=None) for i in range(3)]
        issues = [_issue_item(number=i + 10) for i in range(2)]
        result = self._run_fetch(prs, issues)
        assert result.items_scanned == 5

    def test_decisions_capped_at_50(self) -> None:
        # Create 60 closed PRs each with a matching pattern
        prs = [
            _pr_item(
                number=i,
                body="decided to use a different strategy",
                merged_at=None,
            )
            for i in range(60)
        ]
        result = self._run_fetch(prs, [])
        assert len(result.decisions) <= 50

    def test_matched_patterns_sorted_asc(self) -> None:
        prs = [_pr_item(
            number=1,
            body="tried to fix regression decided not to continue",
            merged_at=None,
        )]
        result = self._run_fetch(prs, [])
        if result.decisions:
            d = result.decisions[0]
            assert d.matched_patterns == sorted(d.matched_patterns)

    def test_body_excerpt_whitespace_normalized(self) -> None:
        prs = [_pr_item(
            number=1,
            body="decided   to\n\nuse   new\t\tapproach",
            merged_at=None,
        )]
        result = self._run_fetch(prs, [])
        if result.decisions:
            d = result.decisions[0]
            assert "\n" not in d.body_excerpt
            assert "\t" not in d.body_excerpt
            assert "  " not in d.body_excerpt


# ---------------------------------------------------------------------------
# TestIntentKindMapping
# ---------------------------------------------------------------------------

class TestIntentKindMapping:
    def _fetch_single_pr(
        self, body: str, merged_at: str | None = None, maintainer_comment: str = ""
    ) -> PRDecision | None:
        prs = [_pr_item(number=1, body=body, merged_at=merged_at)]
        comments = [_comment_item(body=maintainer_comment)] if maintainer_comment else []

        def fake_run(args, **kwargs):
            cmd = " ".join(str(a) for a in args)
            if "pulls/1/comments" in cmd:
                return _make_gh_result(json.dumps(comments))
            if "pulls" in cmd and "issues" not in cmd:
                return _make_gh_result(json.dumps(prs))
            return _make_gh_result("[]")

        with patch("subprocess.run", side_effect=fake_run):
            result = fetch_pr_decisions("https://github.com/owner/repo")
        decisions = [d for d in result.decisions if d.ref == "PR#1"]
        return decisions[0] if decisions else None

    def test_closed_unmerged_pr_is_rejection(self) -> None:
        d = self._fetch_single_pr(
            body="decided not to use this approach",
            merged_at=None,
        )
        assert d is not None
        assert d.intent_kind == "rejection"

    def test_issue_with_revert_is_incident(self) -> None:
        issues = [_issue_item(
            number=20,
            body="regression after rollback decided not to proceed",
        )]

        def fake_run(args, **kwargs):
            cmd = " ".join(str(a) for a in args)
            if "issues" in cmd:
                return _make_gh_result(json.dumps(issues))
            return _make_gh_result("[]")

        with patch("subprocess.run", side_effect=fake_run):
            result = fetch_pr_decisions("https://github.com/owner/repo")
        incidents = [d for d in result.decisions if d.intent_kind == "incident"]
        assert len(incidents) >= 1

    def test_preference_intent_kind_for_other_patterns(self) -> None:
        # A PR with "decided to" (positive decision) without rejection signals
        # should map to "preference" or "rejection" — but not "incident"
        d = self._fetch_single_pr(
            body="decided to use async instead of sync",
            merged_at=None,
        )
        assert d is not None
        assert d.intent_kind in ("rejection", "preference")
