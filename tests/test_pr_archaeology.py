"""Tests for core/pr_archaeology.py — PR/issue mining via gh CLI.

TDD: tests written first, then implementation.
All subprocess.run calls are mocked — no real gh/network calls.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from hijack.core.pr_archaeology import (
    _DIFF_EXCERPT_CHARS,
    _MAX_DIFF_FETCHES,
    PRDecision,
    PRDecisions,
    _build_decision_from_pr,
    _get_maintainer_comment,
    _get_pr_diff_excerpt,
    _is_bot_pr,
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

    def test_from_json_missing_diff_excerpt_defaults_empty(self) -> None:
        # Backward compat: sessions saved before diff_excerpt existed.
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
        assert d.diff_excerpt == ""

    def test_to_json_roundtrip_includes_diff_excerpt(self) -> None:
        d = PRDecision(
            ref="PR#1",
            title="Rejected approach",
            date="2024-01-01 00:00:00 +0000",
            body_excerpt="decided not to use this",
            matched_patterns=["decided not to"],
            maintainer_comment="rejected",
            intent_kind="rejection",
            diff_excerpt="--- src/foo.py\n+bad code",
        )
        data = d.to_json()
        assert data["diff_excerpt"] == "--- src/foo.py\n+bad code"
        assert PRDecision.from_json(data) == d


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


# ---------------------------------------------------------------------------
# TestIsBotPr
# ---------------------------------------------------------------------------

class TestIsBotPr:
    def test_user_type_bot_is_true(self) -> None:
        assert _is_bot_pr({"user": {"type": "Bot", "login": "some-bot"}}) is True

    def test_login_bot_suffix_is_true(self) -> None:
        assert _is_bot_pr({"user": {"type": "User", "login": "dependabot[bot]"}}) is True

    def test_regular_user_is_false(self) -> None:
        assert _is_bot_pr({"user": {"type": "User", "login": "octocat"}}) is False

    def test_missing_user_is_false(self) -> None:
        assert _is_bot_pr({}) is False

    def test_bot_pr_excluded_from_build_decision(self) -> None:
        item = _pr_item(number=5, body="decided not to use this approach", merged_at=None)
        item["user"] = {"type": "Bot", "login": "dependabot[bot]"}
        result = _build_decision_from_pr(item, "owner", "repo", timeout=30)
        assert result is None


# ---------------------------------------------------------------------------
# TestGetPrDiffExcerpt
# ---------------------------------------------------------------------------

class TestGetPrDiffExcerpt:
    def test_concatenates_patches_across_files(self) -> None:
        files = [
            {"filename": "src/foo.py", "patch": "+bad line"},
            {"filename": "src/bar.py", "patch": "+another change"},
        ]
        with patch("subprocess.run", return_value=_make_gh_result(json.dumps(files))):
            result = _get_pr_diff_excerpt("owner", "repo", 1, timeout=30)
        assert "--- src/foo.py" in result
        assert "+bad line" in result
        assert "--- src/bar.py" in result
        assert "+another change" in result

    def test_skips_test_files(self) -> None:
        files = [
            {"filename": "tests/test_foo.py", "patch": "+test change"},
            {"filename": "src/foo.py", "patch": "+real change"},
        ]
        with patch("subprocess.run", return_value=_make_gh_result(json.dumps(files))):
            result = _get_pr_diff_excerpt("owner", "repo", 1, timeout=30)
        assert "test_foo" not in result
        assert "+real change" in result

    def test_missing_patch_key_defended(self) -> None:
        # Binary/large files have no "patch" key
        files = [{"filename": "image.png"}]
        with patch("subprocess.run", return_value=_make_gh_result(json.dumps(files))):
            result = _get_pr_diff_excerpt("owner", "repo", 1, timeout=30)
        assert result == ""

    def test_gh_api_failure_returns_empty(self) -> None:
        with patch("subprocess.run", return_value=_make_gh_result("", returncode=1)):
            result = _get_pr_diff_excerpt("owner", "repo", 1, timeout=30)
        assert result == ""

    def test_truncated_to_diff_excerpt_chars_cap(self) -> None:
        big_patch = "+" + ("x" * 3000)
        files = [{"filename": "src/foo.py", "patch": big_patch}]
        with patch("subprocess.run", return_value=_make_gh_result(json.dumps(files))):
            result = _get_pr_diff_excerpt("owner", "repo", 1, timeout=30)
        assert len(result) <= _DIFF_EXCERPT_CHARS


# ---------------------------------------------------------------------------
# TestGetMaintainerCommentRejectionPreference
# ---------------------------------------------------------------------------

class TestGetMaintainerCommentRejectionPreference:
    def test_prefers_rejection_matching_comment_over_later_non_match(self) -> None:
        comments = [
            {"body": "Closing this — out of scope for this project"},
            {"body": "thanks for contributing anyway"},
        ]
        with patch("subprocess.run", return_value=_make_gh_result(json.dumps(comments))):
            result = _get_maintainer_comment("owner", "repo", 1, timeout=30)
        assert result == "Closing this — out of scope for this project"

    def test_falls_back_to_last_comment_when_no_rejection_match(self) -> None:
        comments = [
            {"body": "looks good"},
            {"body": "thanks!"},
        ]
        with patch("subprocess.run", return_value=_make_gh_result(json.dumps(comments))):
            result = _get_maintainer_comment("owner", "repo", 1, timeout=30)
        assert result == "thanks!"

    def test_prefers_last_matching_comment_when_multiple_match(self) -> None:
        comments = [
            {"body": "rejected initially"},
            {"body": "actually not a good fit after all"},
        ]
        with patch("subprocess.run", return_value=_make_gh_result(json.dumps(comments))):
            result = _get_maintainer_comment("owner", "repo", 1, timeout=30)
        assert result == "actually not a good fit after all"


# ---------------------------------------------------------------------------
# TestFetchPrDecisionsDiffSecondPass
# ---------------------------------------------------------------------------

class TestFetchPrDecisionsDiffSecondPass:
    def test_diff_attached_only_to_rejection_not_preference(self) -> None:
        prs = [_pr_item(
            number=1,
            title="Rejected",
            body="decided not to use this approach",
            merged_at=None,
        )]
        issues = [_issue_item(
            number=10,
            title="Pref",
            body="decided to use a naming convention",
        )]
        files_calls: list[str] = []

        def fake_run(args, **kwargs):
            cmd = " ".join(str(a) for a in args)
            if "/files" in cmd:
                files_calls.append(cmd)
                if "/pulls/1/files" in cmd:
                    return _make_gh_result(
                        json.dumps([{"filename": "src/foo.py", "patch": "+bad"}])
                    )
                return _make_gh_result("[]")
            if "/comments" in cmd:
                return _make_gh_result("[]")
            if "pulls" in cmd and "issues" not in cmd:
                return _make_gh_result(json.dumps(prs))
            if "issues" in cmd:
                return _make_gh_result(json.dumps(issues))
            return _make_gh_result("[]")

        with patch("subprocess.run", side_effect=fake_run):
            result = fetch_pr_decisions("https://github.com/owner/repo")

        by_ref = {d.ref: d for d in result.decisions}
        assert by_ref["PR#1"].intent_kind == "rejection"
        assert "bad" in by_ref["PR#1"].diff_excerpt
        assert by_ref["issue#10"].intent_kind == "preference"
        assert by_ref["issue#10"].diff_excerpt == ""
        # Only the rejection PR triggers a diff fetch — issues have no diff.
        assert len(files_calls) == 1

    def test_max_diff_fetches_cap(self) -> None:
        n = _MAX_DIFF_FETCHES + 5
        prs = [
            _pr_item(
                number=i,
                body="decided not to use this approach",
                merged_at=None,
                created_at=f"2024-01-{i + 1:02d}T00:00:00Z",
            )
            for i in range(n)
        ]
        files_calls: list[str] = []

        def fake_run(args, **kwargs):
            cmd = " ".join(str(a) for a in args)
            if "/files" in cmd:
                files_calls.append(cmd)
                return _make_gh_result(
                    json.dumps([{"filename": "src/foo.py", "patch": "+x"}])
                )
            if "/comments" in cmd:
                return _make_gh_result("[]")
            if "pulls" in cmd and "issues" not in cmd:
                return _make_gh_result(json.dumps(prs))
            if "issues" in cmd:
                return _make_gh_result("[]")
            return _make_gh_result("[]")

        with patch("subprocess.run", side_effect=fake_run):
            fetch_pr_decisions("https://github.com/owner/repo")

        assert len(files_calls) == _MAX_DIFF_FETCHES
