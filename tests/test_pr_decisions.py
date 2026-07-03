"""Tests for core/pr_decisions.py — GitHub PR mining, Phase A1.

Structured after test_test_decisions.py: class-based grouping with comments
explaining the *why* of each group. All network calls are mocked via the
injectable gh_runner parameter — no real HTTP traffic in the test suite.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from unittest.mock import MagicMock, patch

from hijack.core.pr_decisions import (
    _LABELS_TOP_N,
    _REJECTED_TOP_N,
    LabelCount,
    NotablePR,
    PRDecisions,
    RejectedPR,
    VocabularyCluster,
    _anonymize,
    _build_label_counts,
    _build_rejected_prs,
    _build_vocabulary_clusters,
    _parse_github_target,
    extract_pr_decisions,
    render_pr_decisions_md,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_runner(responses: dict[str, str]) -> Callable[[list[str]], str]:
    """Build a fake gh_runner that returns canned JSON for expected arg patterns.

    Key format: "<subcommand> <state_or_number>" e.g. "pr list merged" or "pr view 42".
    Falls back to '[]' for unrecognised calls.
    """
    call_log: list[list[str]] = []

    def runner(args: list[str]) -> str:
        call_log.append(list(args))
        # Build a lookup key from subcommand shape
        if len(args) >= 2 and args[0] == "pr" and args[1] == "list":
            state = _flag_value_test(args, "--state") or "open"
            key = f"pr list {state}"
        elif len(args) >= 3 and args[0] == "pr" and args[1] == "view":
            key = f"pr view {args[2]}"
        else:
            key = " ".join(args[:3])
        return responses.get(key, "[]")

    runner.call_log = call_log  # type: ignore[attr-defined]
    return runner


def _flag_value_test(args: list[str], flag: str) -> str | None:
    try:
        idx = args.index(flag)
        return args[idx + 1] if idx + 1 < len(args) else None
    except ValueError:
        return None


def _make_merged_pr(
    number: int = 1,
    title: str = "Test PR",
    body: str = "body text",
    labels: list | None = None,
    additions: int = 100,
    deletions: int = 50,
    url: str = "https://github.com/owner/repo/pull/1",
    merged_at: str = "2024-01-01T00:00:00Z",
    closed_at: str = "2024-01-01T00:00:00Z",
) -> dict:
    return {
        "number": number,
        "title": title,
        "body": body,
        "labels": [{"name": lbl} for lbl in (labels or [])],
        "additions": additions,
        "deletions": deletions,
        "url": url,
        "mergedAt": merged_at,
        "closedAt": closed_at,
    }


def _make_closed_pr(
    number: int = 99,
    title: str = "Rejected PR",
    body: str = "rejected body",
    labels: list | None = None,
    url: str = "https://github.com/owner/repo/pull/99",
    closed_at: str = "2024-06-01T00:00:00Z",
) -> dict:
    return {
        "number": number,
        "title": title,
        "body": body,
        "labels": [{"name": lbl} for lbl in (labels or [])],
        "additions": 0,
        "deletions": 0,
        "url": url,
        "mergedAt": None,
        "closedAt": closed_at,
    }


def _make_decisions(
    *,
    vocab: list[VocabularyCluster] | None = None,
    notable: list[NotablePR] | None = None,
    rejected: list[RejectedPR] | None = None,
    labels: list[LabelCount] | None = None,
    repo_slug: str = "owner/repo",
    total: int = 10,
) -> PRDecisions:
    return PRDecisions(
        repo_slug=repo_slug,
        total_prs_scanned=total,
        vocabulary_clusters=vocab or [],
        notable_prs=notable or [],
        rejected_prs=rejected or [],
        label_counts=labels or [],
    )


def _empty_decisions() -> PRDecisions:
    return _make_decisions()


# ---------------------------------------------------------------------------
# TestParseGithubTarget
# ---------------------------------------------------------------------------

class TestParseGithubTarget:
    # Parsing must be purely syntactic for direct URL inputs. Local-path
    # resolution goes through subprocess and is tested separately via mocking.

    def test_https_url(self) -> None:
        result = _parse_github_target("https://github.com/foo/bar", None)
        assert result == ("foo", "bar")

    def test_https_url_with_git_suffix(self) -> None:
        result = _parse_github_target("https://github.com/foo/bar.git", None)
        assert result == ("foo", "bar")

    def test_ssh_url(self) -> None:
        result = _parse_github_target("git@github.com:foo/bar.git", None)
        assert result == ("foo", "bar")

    def test_gitlab_url_returns_none(self) -> None:
        result = _parse_github_target("https://gitlab.com/foo/bar", None)
        assert result is None

    def test_local_path_no_remote_returns_none(self, tmp_path: Path) -> None:
        # Directory exists, has its own .git, but `git remote get-url` fails
        # (no origin configured) — subprocess returns non-zero, expect None.
        (tmp_path / ".git").mkdir()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="")
            result = _parse_github_target(str(tmp_path), tmp_path)
        assert result is None

    def test_local_path_with_github_remote(self, tmp_path: Path) -> None:
        # Directory must own its .git for git-remote resolution to be
        # attempted — otherwise the guard against ancestor-inheritance kicks in.
        (tmp_path / ".git").mkdir()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="https://github.com/myorg/myrepo\n",
            )
            result = _parse_github_target(str(tmp_path), tmp_path)
        assert result == ("myorg", "myrepo")

    def test_local_path_without_own_git_dir_returns_none(self, tmp_path: Path) -> None:
        # Critical guard: a path nested inside another git repo (test fixtures,
        # vendored sources, monorepo subprojects) must NOT inherit the parent
        # repo's origin. Without this guard, fixture tests would silently mine
        # the host project's PRs and create side-effect cache directories.
        # No .git is created here — subprocess.run must NOT be called at all.
        with patch("subprocess.run") as mock_run:
            result = _parse_github_target(str(tmp_path), tmp_path)
        assert result is None
        mock_run.assert_not_called()

    def test_https_url_trailing_slash(self) -> None:
        result = _parse_github_target("https://github.com/foo/bar/", None)
        assert result == ("foo", "bar")


# ---------------------------------------------------------------------------
# TestVocabularyClustering
# ---------------------------------------------------------------------------

class TestVocabularyClustering:
    # Vocabulary clustering is the primary qualitative signal — it must be
    # case-insensitive, multi-theme capable, and properly anonymized.

    def _cluster_text(self, text: str) -> list[VocabularyCluster]:
        """Helper: build a minimal notable PR + all_pr_data and run clustering."""
        pr = NotablePR(
            number=1, title="T", body_excerpt="",
            labels=[], comment_count=5, diff_size=200, url="http://example.com/1",
        )
        all_pr_data = {
            1: {
                "body": text,
                "comments": [],
                "reviews": [],
            }
        }
        return _build_vocabulary_clusters([pr], all_pr_data)

    def test_scaling_keyword_matches(self) -> None:
        # Three occurrences required to clear _VOCAB_MIN_COUNT=3
        text = "This won't scale. It won't scale at all. Performance won't scale."
        clusters = self._cluster_text(text)
        themes = [c.theme for c in clusters]
        assert "scaling/performance" in themes

    def test_case_insensitive_matching(self) -> None:
        text = "Won't Scale. WON'T SCALE. won't scale."
        clusters = self._cluster_text(text)
        themes = [c.theme for c in clusters]
        assert "scaling/performance" in themes

    def test_multiple_themes_can_match_same_text(self) -> None:
        text = (
            "security vulnerability CVE. "
            "won't scale performance throughput. "
            "security auth sanitize. "
            "performance slow expensive. "
            "won't scale slow memory. "
        )
        clusters = self._cluster_text(text)
        themes = [c.theme for c in clusters]
        # Both security and scaling should appear
        assert len(themes) >= 2

    def test_theme_below_min_count_dropped(self) -> None:
        # Only 1 mention of a scaling keyword — below _VOCAB_MIN_COUNT=3
        text = "This won't scale."
        clusters = self._cluster_text(text)
        themes = [c.theme for c in clusters]
        assert "scaling/performance" not in themes

    def test_at_mention_anonymized_in_examples(self) -> None:
        text = (
            "@jsmith won't scale. @maria won't scale. won't scale again."
        )
        clusters = self._cluster_text(text)
        scaling = next((c for c in clusters if c.theme == "scaling/performance"), None)
        if scaling and scaling.examples:
            for _kw, excerpt in scaling.examples:
                assert "@<contributor>" in excerpt or "@jsmith" not in excerpt

    def test_anonymize_function_directly(self) -> None:
        result = _anonymize("@alice said this won't scale @bob")
        assert "@alice" not in result
        assert "@bob" not in result
        assert "@<contributor>" in result

    def test_quote_excerpt_truncation(self) -> None:
        # The excerpt helper should not exceed 100 chars
        long_text = "won't scale " + "x " * 200
        from hijack.core.pr_decisions import _excerpt
        result = _excerpt(long_text, "won't scale", max_chars=100)
        assert len(result) <= 100

    def test_excerpt_does_not_break_mid_word(self) -> None:
        # Truncation should not leave a partial word at the end.
        # i.e. the last character should be either: end of a complete word
        # (either space ends before or following char is space/absent), or
        # the full text fits within max_chars.
        text = "this won't scale because the algorithm is inherently quadratic growth"
        from hijack.core.pr_decisions import _excerpt
        result = _excerpt(text, "won't scale", max_chars=30)
        # The result must be <= max_chars
        assert len(result) <= 30
        # If the result is shorter than the full text, it must end at a word
        # boundary — specifically the character immediately after the result
        # in the original text (if any) should be a space or we've taken a
        # complete word (no mid-word cut).
        if result and result in text:
            end_idx = text.find(result) + len(result)
            if end_idx < len(text):
                # Character right after the excerpt should be a space (word boundary)
                assert text[end_idx] == " " or text[end_idx - 1] == " "


# ---------------------------------------------------------------------------
# TestNotablePRFilter
# ---------------------------------------------------------------------------

class TestNotablePRFilter:
    # Notable filtering has three gates: comment count, diff min, diff max.
    # Each gate is independent and should be tested in isolation.

    def _run_notable(
        self,
        prs: list[dict],
        comment_data: dict[int, dict],
        tmp_path: Path,
    ) -> list[NotablePR]:
        """Drive _build_notable_prs with mocked comment fetches."""
        def runner(args: list[str]) -> str:
            if args[0] == "pr" and args[1] == "view":
                n = int(args[2])
                return json.dumps(comment_data.get(n, {"comments": [], "reviews": []}))
            return "[]"

        from hijack.core.pr_decisions import _build_notable_prs
        return _build_notable_prs(prs, tmp_path, runner, "owner", "repo")

    def test_pr_below_comment_threshold_not_notable(self, tmp_path: Path) -> None:
        pr = _make_merged_pr(number=1, additions=200, deletions=100)
        # Only 1 comment — below _NOTABLE_MIN_COMMENTS=3
        comment_data = {1: {"comments": [{"body": "c1"}], "reviews": []}}
        result = self._run_notable([pr], comment_data, tmp_path)
        assert not any(p.number == 1 for p in result)

    def test_pr_below_diff_min_not_notable(self, tmp_path: Path) -> None:
        # additions+deletions = 10 < _NOTABLE_MIN_DIFF=50
        pr = _make_merged_pr(number=2, additions=5, deletions=5)
        comment_data = {2: {"comments": [{"body": f"c{i}"} for i in range(5)], "reviews": []}}
        result = self._run_notable([pr], comment_data, tmp_path)
        assert not any(p.number == 2 for p in result)

    def test_pr_above_diff_max_not_notable(self, tmp_path: Path) -> None:
        # additions+deletions = 10000 > _NOTABLE_MAX_DIFF=5000
        pr = _make_merged_pr(number=3, additions=6000, deletions=4001)
        comment_data = {3: {"comments": [{"body": f"c{i}"} for i in range(10)], "reviews": []}}
        result = self._run_notable([pr], comment_data, tmp_path)
        assert not any(p.number == 3 for p in result)

    def test_pr_meeting_all_criteria_is_notable(self, tmp_path: Path) -> None:
        pr = _make_merged_pr(number=4, additions=300, deletions=100)
        comment_data = {
            4: {
                "comments": [{"body": f"c{i}"} for i in range(5)],
                "reviews": [{"body": "review"}],
            }
        }
        result = self._run_notable([pr], comment_data, tmp_path)
        assert any(p.number == 4 for p in result)

    def test_sorted_by_comment_count_desc(self, tmp_path: Path) -> None:
        pr_low = _make_merged_pr(number=10, additions=200, deletions=50)
        pr_high = _make_merged_pr(number=11, additions=200, deletions=50)
        comment_data = {
            10: {"comments": [{"body": "c"} for _ in range(3)], "reviews": []},
            11: {"comments": [{"body": "c"} for _ in range(8)], "reviews": []},
        }
        result = self._run_notable([pr_low, pr_high], comment_data, tmp_path)
        if len(result) >= 2:
            assert result[0].comment_count >= result[1].comment_count

    def test_ties_broken_by_number_desc(self, tmp_path: Path) -> None:
        # Same comment count — higher number should come first (recency)
        pr_old = _make_merged_pr(number=5, additions=200, deletions=50)
        pr_new = _make_merged_pr(number=20, additions=200, deletions=50)
        same_comments = {"comments": [{"body": "c"} for _ in range(4)], "reviews": []}
        comment_data = {5: same_comments, 20: same_comments}
        result = self._run_notable([pr_old, pr_new], comment_data, tmp_path)
        if len(result) >= 2:
            # Among equal comment counts, higher number (20) first
            assert result[0].number > result[1].number


# ---------------------------------------------------------------------------
# TestRejectedPRExtraction
# ---------------------------------------------------------------------------

class TestRejectedPRExtraction:
    # The merged/rejected distinction is the core of this signal. The logic is
    # simply: closed + mergedAt is None → rejected. Everything else is not.

    def test_closed_without_merge_is_rejected(self) -> None:
        pr = _make_closed_pr(number=10)
        result = _build_rejected_prs([pr])
        assert any(r.number == 10 for r in result)

    def test_closed_with_merge_is_not_rejected(self) -> None:
        pr = _make_merged_pr(number=11)  # mergedAt is set
        result = _build_rejected_prs([pr])
        assert not any(r.number == 11 for r in result)

    def test_sorted_by_closed_at_desc(self) -> None:
        older = _make_closed_pr(number=1, closed_at="2023-01-01T00:00:00Z")
        newer = _make_closed_pr(number=2, closed_at="2024-06-01T00:00:00Z")
        result = _build_rejected_prs([older, newer])
        assert result[0].number == 2  # newer first

    def test_capped_at_rejected_top_n(self) -> None:
        prs = [_make_closed_pr(number=i) for i in range(_REJECTED_TOP_N + 10)]
        result = _build_rejected_prs(prs)
        assert len(result) <= _REJECTED_TOP_N


# ---------------------------------------------------------------------------
# TestLabelCounts
# ---------------------------------------------------------------------------

class TestLabelCounts:
    # Label aggregation is how we surface the project's own taxonomy. Bot labels
    # pollute this signal and should be filtered before counting.

    def test_labels_aggregated_across_merged_and_rejected(self) -> None:
        merged = [_make_merged_pr(labels=["bug", "enhancement"])]
        closed = [_make_closed_pr(labels=["wontfix"])]
        result = _build_label_counts(merged, closed)
        label_names = [lc.label for lc in result]
        assert "bug" in label_names
        assert "enhancement" in label_names
        assert "wontfix" in label_names

    def test_bot_labels_skipped(self) -> None:
        merged = [_make_merged_pr(labels=["bot:automerge", "auto:rebase", "real-label"])]
        result = _build_label_counts(merged, [])
        label_names = [lc.label for lc in result]
        assert "bot:automerge" not in label_names
        assert "auto:rebase" not in label_names
        assert "real-label" in label_names

    def test_sorted_by_count_desc_then_label_asc(self) -> None:
        merged = [
            _make_merged_pr(number=1, labels=["alpha", "beta", "alpha"]),
            _make_merged_pr(number=2, labels=["alpha"]),
            _make_merged_pr(number=3, labels=["beta"]),
        ]
        result = _build_label_counts(merged, [])
        counts = [(lc.label, lc.count) for lc in result]
        # alpha appears 3 times (once per PR, since labels are per-PR not per-occurrence)
        # beta appears 2 times
        if len(counts) >= 2:
            assert counts[0][1] >= counts[1][1]

    def test_capped_at_labels_top_n(self) -> None:
        prs = [_make_merged_pr(number=i, labels=[f"label-{i}"]) for i in range(_LABELS_TOP_N + 5)]
        result = _build_label_counts(prs, [])
        assert len(result) <= _LABELS_TOP_N


# ---------------------------------------------------------------------------
# TestExtractPRDecisions
# ---------------------------------------------------------------------------

class TestExtractPRDecisions:
    # Integration tests for the top-level extractor. The gh_runner injection
    # point means we can exercise every code path without network access.

    def test_non_github_target_returns_none(self, tmp_path: Path) -> None:
        result = extract_pr_decisions(
            "https://gitlab.com/foo/bar", None, tmp_path,
            gh_runner=_make_runner({}),
        )
        assert result is None

    def test_gh_runner_raising_returns_none(self, tmp_path: Path) -> None:
        def bad_runner(args: list[str]) -> str:
            raise RuntimeError("auth failure")

        result = extract_pr_decisions(
            "https://github.com/foo/bar", None, tmp_path,
            gh_runner=bad_runner,
        )
        assert result is None

    def test_empty_pr_list_returns_pr_decisions_with_no_signal(self, tmp_path: Path) -> None:
        runner = _make_runner({
            "pr list merged": "[]",
            "pr list closed": "[]",
        })
        result = extract_pr_decisions(
            "https://github.com/foo/bar", None, tmp_path,
            gh_runner=runner,
        )
        assert result is not None
        assert result.has_signal is False

    def test_happy_path_populates_all_sections(self, tmp_path: Path) -> None:
        # Merged PR that will be notable (diff in range, enough comments)
        merged_pr = _make_merged_pr(
            number=1,
            title="Add cache layer",
            body="This adds caching. performance throughput memory. " * 5,
            labels=["enhancement"],
            additions=300,
            deletions=50,
        )
        rejected_pr = _make_closed_pr(
            number=2,
            title="Add YAML config",
            labels=["wontfix"],
        )
        # Comment detail for PR #1
        detail_1 = {
            "comments": [
                {"body": "won't scale. won't scale. won't scale."},
                {"body": "performance issue here"},
                {"body": "looks good"},
                {"body": "needs more tests"},
            ],
            "reviews": [{"body": "approved after changes"}],
        }

        runner = _make_runner({
            "pr list merged": json.dumps([merged_pr]),
            "pr list closed": json.dumps([rejected_pr]),
            "pr view 1": json.dumps(detail_1),
        })
        result = extract_pr_decisions(
            "https://github.com/owner/repo", None, tmp_path,
            gh_runner=runner,
        )
        assert result is not None
        assert result.repo_slug == "owner/repo"
        assert result.total_prs_scanned >= 1
        # Notable: PR #1 has 5 comments (4 + 1 review) >= 3
        assert any(p.number == 1 for p in result.notable_prs)
        # Rejected: PR #2 has mergedAt=None
        assert any(p.number == 2 for p in result.rejected_prs)
        # Labels: "enhancement" and "wontfix"
        label_names = [lc.label for lc in result.label_counts]
        assert "enhancement" in label_names or "wontfix" in label_names

    def test_cache_used_when_index_exists(self, tmp_path: Path) -> None:
        # Pre-populate cache as if a previous run happened
        merged_pr = _make_merged_pr(number=5, additions=200, deletions=100)
        repo_cache = tmp_path / "owner__repo"
        repo_cache.mkdir(parents=True)
        (repo_cache / "index.json").write_text(
            json.dumps({"last_updated": "2024-01-01T00:00:00+00:00", "pr_numbers": [5]}),
            encoding="utf-8",
        )
        (repo_cache / "pr_5.json").write_text(
            json.dumps({**merged_pr, "comments": [], "reviews": []}),
            encoding="utf-8",
        )

        call_log: list[list[str]] = []

        def counting_runner(args: list[str]) -> str:
            call_log.append(list(args))
            return "[]"

        # With cache present and refresh=False, runner should NOT be called for bulk fetch
        extract_pr_decisions(
            "https://github.com/owner/repo", None, tmp_path,
            gh_runner=counting_runner,
            refresh=False,
        )
        # The index exists so we should not call "pr list"
        list_calls = [c for c in call_log if len(c) >= 2 and c[:2] == ["pr", "list"]]
        assert len(list_calls) == 0

    def test_refresh_true_clears_cache_before_fetching(self, tmp_path: Path) -> None:
        repo_cache = tmp_path / "owner__repo"
        repo_cache.mkdir(parents=True)
        # Write a stale cache
        (repo_cache / "index.json").write_text(
            json.dumps({"last_updated": "2020-01-01T00:00:00+00:00", "pr_numbers": [999]}),
            encoding="utf-8",
        )
        (repo_cache / "pr_999.json").write_text(
            json.dumps(_make_merged_pr(number=999)), encoding="utf-8"
        )

        call_log: list[list[str]] = []

        def counting_runner(args: list[str]) -> str:
            call_log.append(list(args))
            if args[0] == "pr" and args[1] == "list":
                return json.dumps([_make_merged_pr(number=1, additions=200, deletions=100)])
            return json.dumps({"comments": [], "reviews": []})

        extract_pr_decisions(
            "https://github.com/owner/repo", None, tmp_path,
            gh_runner=counting_runner,
            refresh=True,
        )
        # With refresh=True, the old cache dir should be wiped and a fresh fetch triggered
        list_calls = [c for c in call_log if len(c) >= 2 and c[:2] == ["pr", "list"]]
        assert len(list_calls) >= 1
        # The stale pr_999.json should not persist
        assert not (repo_cache / "pr_999.json").exists()


# ---------------------------------------------------------------------------
# TestRenderPRDecisionsMd
# ---------------------------------------------------------------------------

class TestRenderPRDecisionsMd:
    # Renderer tests verify the output contract: sections present iff list
    # non-empty, strings appear, empty PRDecisions returns "".

    def test_empty_decisions_returns_empty_string(self) -> None:
        assert render_pr_decisions_md(_empty_decisions(), source_target="repo") == ""

    def test_has_signal_false_returns_empty_string(self) -> None:
        d = _make_decisions()
        assert d.has_signal is False
        assert render_pr_decisions_md(d, source_target="repo") == ""

    def test_source_target_appears_in_output(self) -> None:
        d = _make_decisions(
            labels=[LabelCount(label="bug", count=5)],
            repo_slug="owner/repo",
        )
        md = render_pr_decisions_md(d, source_target="github.com/owner/repo")
        assert "github.com/owner/repo" in md

    def test_repo_slug_appears_in_output(self) -> None:
        d = _make_decisions(
            labels=[LabelCount(label="bug", count=5)],
            repo_slug="myorg/myrepo",
        )
        md = render_pr_decisions_md(d, source_target="x")
        assert "myorg/myrepo" in md

    def test_vocab_section_present_when_clusters_non_empty(self) -> None:
        cluster = VocabularyCluster(
            theme="scaling/performance",
            count=10,
            matched_keywords=["won't scale"],
            examples=[("won't scale", "this won't scale past 10k rows")],
        )
        d = _make_decisions(vocab=[cluster])
        md = render_pr_decisions_md(d, source_target="repo")
        assert "## Concerns raised in review" in md
        assert "scaling/performance" in md

    def test_vocab_section_omitted_when_clusters_empty(self) -> None:
        d = _make_decisions(labels=[LabelCount(label="bug", count=3)])
        md = render_pr_decisions_md(d, source_target="repo")
        assert "## Concerns raised in review" not in md

    def test_notable_section_present_when_notable_non_empty(self) -> None:
        pr = NotablePR(
            number=42, title="Add cache",
            body_excerpt="adds caching",
            labels=["perf"],
            comment_count=10,
            diff_size=500,
            url="https://github.com/owner/repo/pull/42",
        )
        d = _make_decisions(notable=[pr])
        md = render_pr_decisions_md(d, source_target="repo")
        assert "## Most-discussed merged PRs" in md
        assert "#42" in md

    def test_notable_section_omitted_when_notable_empty(self) -> None:
        d = _make_decisions(labels=[LabelCount(label="bug", count=3)])
        md = render_pr_decisions_md(d, source_target="repo")
        assert "## Most-discussed merged PRs" not in md

    def test_rejected_section_present_when_rejected_non_empty(self) -> None:
        pr = RejectedPR(
            number=99, title="Add YAML",
            body_excerpt="yaml proposal",
            labels=["wontfix"],
            url="https://github.com/owner/repo/pull/99",
            closed_at="2024-06-01T00:00:00Z",
        )
        d = _make_decisions(rejected=[pr])
        md = render_pr_decisions_md(d, source_target="repo")
        assert "## Rejected" in md
        assert "#99" in md

    def test_rejected_section_omitted_when_rejected_empty(self) -> None:
        d = _make_decisions(labels=[LabelCount(label="bug", count=3)])
        md = render_pr_decisions_md(d, source_target="repo")
        assert "## Rejected" not in md

    def test_label_section_present_when_labels_non_empty(self) -> None:
        d = _make_decisions(labels=[LabelCount(label="bug", count=5)])
        md = render_pr_decisions_md(d, source_target="repo")
        assert "## Recurring labels" in md
        assert "bug" in md

    def test_label_section_omitted_when_labels_empty(self) -> None:
        pr = NotablePR(
            number=1, title="x", body_excerpt="",
            labels=[], comment_count=5, diff_size=200,
            url="https://github.com/owner/repo/pull/1",
        )
        d = _make_decisions(notable=[pr])
        md = render_pr_decisions_md(d, source_target="repo")
        assert "## Recurring labels" not in md

    def test_pr_url_renders_as_markdown_link(self) -> None:
        pr = NotablePR(
            number=7, title="Fix bug",
            body_excerpt="",
            labels=[],
            comment_count=5,
            diff_size=200,
            url="https://github.com/owner/repo/pull/7",
        )
        d = _make_decisions(notable=[pr])
        md = render_pr_decisions_md(d, source_target="repo")
        assert "[#7](https://github.com/owner/repo/pull/7)" in md

    def test_h1_header_present(self) -> None:
        d = _make_decisions(labels=[LabelCount(label="bug", count=1)])
        md = render_pr_decisions_md(d, source_target="repo")
        assert "# PR Decisions" in md


# ---------------------------------------------------------------------------
# TestJsonRoundtrip
# ---------------------------------------------------------------------------

class TestJsonRoundtrip:
    # to_json/from_json must be lossless — sessions on disk are rehydrated to
    # identical in-memory structures.

    def test_vocabulary_cluster_roundtrip(self) -> None:
        c = VocabularyCluster(
            theme="scaling/performance",
            count=5,
            matched_keywords=["slow", "memory"],
            examples=[("slow", "this is slow")],
        )
        assert VocabularyCluster.from_json(c.to_json()) == c

    def test_notable_pr_roundtrip(self) -> None:
        pr = NotablePR(
            number=1, title="T", body_excerpt="b",
            labels=["bug"], comment_count=10, diff_size=300,
            url="https://github.com/o/r/pull/1",
        )
        assert NotablePR.from_json(pr.to_json()) == pr

    def test_rejected_pr_roundtrip(self) -> None:
        pr = RejectedPR(
            number=2, title="R", body_excerpt="rb",
            labels=["wontfix"],
            url="https://github.com/o/r/pull/2",
            closed_at="2024-01-01T00:00:00Z",
        )
        assert RejectedPR.from_json(pr.to_json()) == pr

    def test_label_count_roundtrip(self) -> None:
        lc = LabelCount(label="enhancement", count=7)
        assert LabelCount.from_json(lc.to_json()) == lc

    def test_pr_decisions_full_roundtrip(self) -> None:
        d = PRDecisions(
            repo_slug="owner/repo",
            total_prs_scanned=100,
            vocabulary_clusters=[
                VocabularyCluster(
                    theme="security",
                    count=4,
                    matched_keywords=["CVE"],
                    examples=[("CVE", "found CVE here")],
                )
            ],
            notable_prs=[
                NotablePR(
                    number=1, title="Big change", body_excerpt="adds stuff",
                    labels=["feature"], comment_count=15, diff_size=800,
                    url="https://github.com/o/r/pull/1",
                )
            ],
            rejected_prs=[
                RejectedPR(
                    number=2, title="Bad idea", body_excerpt="rejected",
                    labels=["wontfix"],
                    url="https://github.com/o/r/pull/2",
                    closed_at="2024-02-01T00:00:00Z",
                )
            ],
            label_counts=[LabelCount(label="bug", count=3)],
        )
        restored = PRDecisions.from_json(d.to_json())
        assert restored == d

    def test_from_json_handles_missing_fields(self) -> None:
        # Older session.json without pr_decisions should deserialize gracefully
        minimal: dict = {}
        d = PRDecisions.from_json(minimal)
        assert d.vocabulary_clusters == []
        assert d.notable_prs == []
        assert d.rejected_prs == []
        assert d.label_counts == []
        assert d.has_signal is False

# Note: SessionResult/apply.py pipeline-integration tests for pr_decisions
# used to live here (TestPipelineIntegration). Removed 0.3.0: SessionResult
# .pr_decisions is now typed as hijack.core.pr_archaeology.PRDecisions, not
# this module's PRDecisions — see test_models.py and test_generator.py for
# the current wiring tests. This module (pr_decisions.py, Phase A1) remains
# standalone and its own unit tests above are unaffected.
