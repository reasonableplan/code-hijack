"""Tests for Phase C — commit-message decision trail mining.

Mirrored after test_test_decisions.py: class-based grouping with comments
explaining the *why* of each group (what invariant is being protected).

Phase C operates purely on already-loaded Commit.body strings: no subprocess,
no I/O, no LLM. All fixtures are built from Commit / FileHistory dataclasses
directly — no git repo needed.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from hijack.core.archaeology import (
    _COMMITS_TOP_N,
    _PATTERN_MIN_COUNT,
    Commit,
    CommitDecision,
    CommitDecisions,
    DecisionPattern,
    FileHistory,
    _sanitize_excerpt,
    _truncate_at_word,
    extract_commit_decisions,
    render_commit_decisions_md,
)
from hijack.core.fetcher import SourceFile

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _commit(
    body: str,
    sha: str = "abc1234567890abc1234567890abc1234567890ab",
    subject: str = "fix: something",
    date: str = "2024-09-21 10:00:00 +0000",
) -> Commit:
    return Commit(sha=sha, subject=subject, author="dev", date=date, body=body)


def _sf(
    commits: list[Commit] | None = None,
    reverts: list[Commit] | None = None,
    path: str = "src/module.py",
) -> SourceFile:
    history = FileHistory(
        commits=commits or [],
        reverts=reverts or [],
    )
    return SourceFile(
        path=Path(path),
        content="",
        layer="backend",
        role="service",
        history=history,
    )


def _empty_decisions() -> CommitDecisions:
    return CommitDecisions(commits_scanned=0, patterns=[], commits=[])


# ---------------------------------------------------------------------------
# TestPatternMatching — pattern regex behavior
# ---------------------------------------------------------------------------


class TestPatternMatching:
    # These tests protect the correctness of _COMPILED_PATTERNS.
    # We test individual patterns via extract_commit_decisions to confirm the
    # end-to-end pipeline produces CommitDecision records correctly.

    def _extract_single(self, body: str, sha: str = "aaa" + "0" * 37) -> CommitDecisions:
        """Helper: run extract on a single file with one commit."""
        sf = _sf(commits=[_commit(body=body, sha=sha)])
        return extract_commit_decisions([sf])

    def test_decided_to_matches(self) -> None:
        result = self._extract_single("We decided to use dataclasses instead.")
        matched = result.commits[0].matched_patterns if result.commits else []
        assert "decided to" in matched

    def test_decided_to_case_insensitive(self) -> None:
        # Patterns are compiled with re.IGNORECASE — capital D must still match.
        result = self._extract_single("Decided to use X here.")
        matched = result.commits[0].matched_patterns if result.commits else []
        assert "decided to" in matched

    def test_tried_hard_does_not_match(self) -> None:
        # The negative lookahead (?!\s+(?:hard|to\s+keep)) should suppress
        # "tried hard" — an idiom, not a decision trail.
        result = self._extract_single("We tried hard to optimize the cache.")
        matched = result.commits[0].matched_patterns if result.commits else []
        assert "tried" not in matched

    def test_tried_to_keep_does_not_match(self) -> None:
        # "tried to keep" is also excluded by the negative lookahead.
        result = self._extract_single("We tried to keep the API stable.")
        matched = result.commits[0].matched_patterns if result.commits else []
        assert "tried" not in matched

    def test_tried_to_fix_does_match(self) -> None:
        # "tried to fix" IS a decision signal. The negative lookahead only
        # excludes "hard" and "to keep" — "to fix" is intentional decision
        # language and should be captured.
        result = self._extract_single("tried to fix the auth flow, ended up rewriting it.")
        matched = result.commits[0].matched_patterns if result.commits else []
        assert "tried" in matched, (
            "'tried to fix' should match 'tried' because 'to fix' is not "
            "in the excluded idiom list (only 'hard' and 'to keep' are excluded)"
        )

    def test_instead_of_matches(self) -> None:
        result = self._extract_single("use composition instead of inheritance here.")
        matched = result.commits[0].matched_patterns if result.commits else []
        assert "instead of" in matched

    def test_reverted_because_matches(self) -> None:
        body = "Reverted the pydantic migration because it caused regressions."
        result = self._extract_single(body)
        matched = result.commits[0].matched_patterns if result.commits else []
        assert "reverted because" in matched

    def test_originally_now_matches(self) -> None:
        body = "originally stored in Redis, now using Postgres for durability."
        result = self._extract_single(body)
        matched = result.commits[0].matched_patterns if result.commits else []
        assert "originally...now" in matched

    def test_multiple_patterns_in_one_body_both_recorded(self) -> None:
        # A body matching two patterns should produce BOTH in matched_patterns,
        # sorted ascending. This protects against short-circuit logic.
        body = "decided to use dataclasses instead of pydantic"
        result = self._extract_single(body)
        assert result.commits, "Expected at least one matching commit"
        matched = result.commits[0].matched_patterns
        assert "decided to" in matched
        assert "instead of" in matched
        # Sorted ascending
        assert matched == sorted(matched)

    def test_body_with_no_patterns_produces_no_commit_decision(self) -> None:
        # Plain commit bodies without decision vocabulary must not produce
        # CommitDecision records (avoids noise).
        result = self._extract_single("Add unit tests for the user model.")
        assert result.commits == []


# ---------------------------------------------------------------------------
# TestSanitization — excerpt sanitization helpers
# ---------------------------------------------------------------------------


class TestSanitization:
    # Sanitization correctness is critical: we anonymize contributors and
    # ensure word-boundary truncation doesn't expose private usernames or
    # split mid-word (making excerpts unreadable).

    def test_at_mention_replaced(self) -> None:
        result = _sanitize_excerpt("reviewed by @alice and approved.", 200)
        assert "@alice" not in result
        assert "@<contributor>" in result

    def test_multiple_at_mentions_all_replaced(self) -> None:
        result = _sanitize_excerpt("cc @alice @bob @charlie for review.", 200)
        assert "@alice" not in result
        assert "@bob" not in result
        assert "@charlie" not in result
        assert result.count("@<contributor>") == 3

    def test_whitespace_runs_collapsed(self) -> None:
        # Newlines, tabs, and multiple spaces should all collapse to single space.
        body = "decided\n\tto  use   dataclasses\ninstead\tof pydantic"
        result = _sanitize_excerpt(body, 200)
        assert "\n" not in result
        assert "\t" not in result
        assert "  " not in result  # no double spaces

    def test_word_boundary_truncation_no_mid_word_cut(self) -> None:
        # A long body truncated to 120 should not break in the middle of a word.
        body = (
            "decided to switch from the old inheritance-based plugin system to a"
            " composition-based one because it made testing much easier and"
            " reduced coupling between components"
        )
        result = _truncate_at_word(body, 120)
        assert len(result) <= 120
        # Result should not end mid-word (next char in original should be space or end)
        if len(result) < len(body):
            next_idx = len(result)
            assert body[next_idx] == " " or result[-1] == " " or result == body[:next_idx]

    def test_hard_cut_when_no_whitespace_in_window(self) -> None:
        # When the text has no whitespace within max_chars, fall back to hard cut.
        no_space = "a" * 200
        result = _truncate_at_word(no_space, 120)
        assert len(result) == 120
        assert result == "a" * 120


# ---------------------------------------------------------------------------
# TestDedupe — SHA deduplication across files
# ---------------------------------------------------------------------------


class TestDedupe:
    # The same commit can touch multiple files in the repo. We must count it
    # once in commits_scanned and union all file paths into one CommitDecision.

    def test_same_sha_in_two_files_counted_once(self) -> None:
        sha = "dedup" + "x" * 35
        commit = _commit(
            body="decided to use composition instead of inheritance",
            sha=sha,
        )
        sf1 = _sf(commits=[commit], path="src/a.py")
        sf2 = _sf(commits=[commit], path="src/b.py")
        result = extract_commit_decisions([sf1, sf2])
        assert result.commits_scanned == 1

    def test_same_sha_both_file_paths_in_result(self) -> None:
        sha = "dedup" + "y" * 35
        commit = _commit(
            body="decided to use composition instead of inheritance",
            sha=sha,
        )
        sf1 = _sf(commits=[commit], path="src/a.py")
        sf2 = _sf(commits=[commit], path="src/b.py")
        result = extract_commit_decisions([sf1, sf2])
        assert result.commits, "Expected matching commit decision"
        file_paths = result.commits[0].file_paths
        assert "src/a.py" in file_paths
        assert "src/b.py" in file_paths
        # Sorted
        assert file_paths == sorted(file_paths)


# ---------------------------------------------------------------------------
# TestCaps — ceiling enforcement
# ---------------------------------------------------------------------------


class TestCaps:
    # Cap enforcement protects against OOM and excessive output size on large repos.

    def test_pattern_with_fewer_than_min_count_dropped(self) -> None:
        # A pattern hit only _PATTERN_MIN_COUNT - 1 times must not appear in output.
        # Use "abandoned" which needs ≥ _PATTERN_MIN_COUNT to survive.
        count = _PATTERN_MIN_COUNT - 1
        files = []
        for i in range(count):
            sha = f"aban{i:036d}"
            date = f"2024-0{i+1}-01 00:00:00 +0000"
            c = _commit(body="abandoned the old approach", sha=sha, date=date)
            files.append(_sf(commits=[c], path=f"src/file{i}.py"))
        result = extract_commit_decisions(files)
        pattern_names = [p.pattern for p in result.patterns]
        assert "abandoned" not in pattern_names

    def test_pattern_at_exactly_min_count_is_included(self) -> None:
        # Exactly _PATTERN_MIN_COUNT hits must survive the threshold.
        count = _PATTERN_MIN_COUNT
        files = []
        for i in range(count):
            sha = f"minc{i:036d}"
            date = f"2024-0{i+1}-01 00:00:00 +0000"
            c = _commit(body="abandoned the old approach here", sha=sha, date=date)
            files.append(_sf(commits=[c], path=f"src/file{i}.py"))
        result = extract_commit_decisions(files)
        pattern_names = [p.pattern for p in result.patterns]
        assert "abandoned" in pattern_names

    def test_commits_output_capped_at_top_n(self) -> None:
        # Even if more than _COMMITS_TOP_N commits match, output is capped.
        files = []
        n = _COMMITS_TOP_N + 10
        for i in range(n):
            sha = f"cap{i:037d}"
            c = _commit(
                body="decided to use composition instead of inheritance",
                sha=sha,
                date=f"2024-09-{(i % 28) + 1:02d} 00:00:00 +0000",
            )
            files.append(_sf(commits=[c], path=f"src/file{i}.py"))
        result = extract_commit_decisions(files)
        assert len(result.commits) <= _COMMITS_TOP_N

    def test_max_commits_to_scan_cap(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # When more than _MAX_COMMITS_TO_SCAN distinct SHAs are present, only
        # the first N are inspected for new SHAs (file paths still update for seen).
        # Monkeypatch the cap to a small value to make the test tractable.
        monkeypatch.setattr("hijack.core.archaeology._MAX_COMMITS_TO_SCAN", 5)
        files = []
        for i in range(10):
            sha = f"scan{i:036d}"
            c = _commit(body="decided to use X", sha=sha)
            files.append(_sf(commits=[c], path=f"src/file{i}.py"))
        result = extract_commit_decisions(files)
        assert result.commits_scanned == 5


# ---------------------------------------------------------------------------
# TestSorting — sort order guarantees
# ---------------------------------------------------------------------------


class TestSorting:
    # Sort order is a contract: callers rendering to markdown depend on
    # patterns appearing most-frequent-first and commits appearing most-recent-first.

    def test_patterns_sorted_by_count_desc_then_name_asc(self) -> None:
        # Build commits so "instead of" has more hits than "abandoned".
        files = []
        for i in range(3):
            sha = f"inof{i:036d}"
            date = f"2024-0{i+1}-01 00:00:00 +0000"
            c = _commit(body="use this instead of that", sha=sha, date=date)
            files.append(_sf(commits=[c], path=f"src/a{i}.py"))
        for i in range(2):
            sha = f"abn0{i:036d}"
            date = f"2024-0{i+1}-02 00:00:00 +0000"
            c = _commit(body="abandoned the old approach", sha=sha, date=date)
            files.append(_sf(commits=[c], path=f"src/b{i}.py"))
        result = extract_commit_decisions(files)
        names = [p.pattern for p in result.patterns]
        # "instead of" (3 commits) should come before "abandoned" (2 commits)
        assert names.index("instead of") < names.index("abandoned")

    def test_commits_sorted_by_date_desc_then_sha_asc(self) -> None:
        # Three commits: two on same date (sha order matters), one earlier.
        sha_a = "aaa" + "0" * 37
        sha_b = "bbb" + "0" * 37
        sha_c = "ccc" + "0" * 37
        c_a = _commit(body="decided to use X", sha=sha_a, date="2024-09-20 00:00:00 +0000")
        c_b = _commit(body="decided to use Y", sha=sha_b, date="2024-09-21 00:00:00 +0000")
        c_c = _commit(body="decided to use Z", sha=sha_c, date="2024-09-21 00:00:00 +0000")
        sf = _sf(commits=[c_a, c_b, c_c])
        result = extract_commit_decisions([sf])
        dates_shas = [(cd.date[:10], cd.sha) for cd in result.commits]
        # Most recent date first
        assert dates_shas[0][0] == "2024-09-21"
        assert dates_shas[1][0] == "2024-09-21"
        # Same date: sha ascending
        assert dates_shas[0][1] <= dates_shas[1][1]
        # Oldest last
        assert dates_shas[-1][0] == "2024-09-20"


# ---------------------------------------------------------------------------
# TestExtractCommitDecisions — top-level extractor behavior
# ---------------------------------------------------------------------------


class TestExtractCommitDecisions:
    # These tests protect the extractor's handling of boundary conditions and
    # correctness across a realistic multi-file scenario.

    def test_empty_files_list_returns_zero_scanned(self) -> None:
        result = extract_commit_decisions([])
        assert result.commits_scanned == 0
        assert not result.has_signal

    def test_files_with_no_history_skipped_silently(self) -> None:
        sf = SourceFile(
            path=Path("src/foo.py"), content="", layer="backend", role="service", history=None
        )
        result = extract_commit_decisions([sf])
        assert result.commits_scanned == 0

    def test_files_with_empty_commits_and_reverts_no_error(self) -> None:
        sf = _sf(commits=[], reverts=[])
        result = extract_commit_decisions([sf])
        assert result.commits_scanned == 0

    def test_reverts_are_also_mined(self) -> None:
        # Reverts carry decision signals — a revert commit body often contains
        # "reverted because" or "switched back" language.
        revert = _commit(
            body="Reverted the pydantic experiment because it caused import errors.",
            sha="rev0" + "0" * 36,
        )
        sf = _sf(commits=[], reverts=[revert])
        result = extract_commit_decisions([sf])
        assert result.commits_scanned == 1

    def test_realistic_multi_file_fixture(self) -> None:
        # 5 files with overlapping commit history; verify pattern counts.
        shared_sha = "shared" + "0" * 34
        shared_commit = _commit(
            body="decided to use composition instead of inheritance for plugin loading",
            sha=shared_sha,
            date="2024-08-01 00:00:00 +0000",
        )
        unique_commits = [
            _commit(
                body="switched to a streaming approach instead of buffering the entire response",
                sha=f"uniq{i:036d}",
                date=f"2024-09-0{i+1} 00:00:00 +0000",
            )
            for i in range(4)
        ]
        files = [
            _sf(commits=[shared_commit, unique_commits[i]], path=f"src/module{i}.py")
            for i in range(4)
        ]
        files.append(_sf(commits=[shared_commit], path="src/base.py"))

        result = extract_commit_decisions(files)
        # shared_sha deduped: 5 files but only 5 unique SHAs total (1 shared + 4 unique)
        assert result.commits_scanned == 5
        # "instead of" should appear in both shared and unique commits → 5 hits
        inof = next((p for p in result.patterns if p.pattern == "instead of"), None)
        assert inof is not None
        assert inof.count == 5


# ---------------------------------------------------------------------------
# TestRenderCommitDecisionsMd — renderer output
# ---------------------------------------------------------------------------


class TestRenderCommitDecisionsMd:
    # The renderer is the boundary between our data model and the AI agent's
    # context. Structural correctness (headers, presence of data) is critical.

    def test_empty_decisions_returns_empty_string(self) -> None:
        result = render_commit_decisions_md(_empty_decisions(), source_target="test/repo")
        assert result == ""

    def test_no_signal_returns_empty_string(self) -> None:
        decisions = CommitDecisions(commits_scanned=5, patterns=[], commits=[])
        assert not decisions.has_signal
        assert render_commit_decisions_md(decisions, source_target="test/repo") == ""

    def test_source_target_in_output(self) -> None:
        decisions = CommitDecisions(
            commits_scanned=10,
            patterns=[DecisionPattern(pattern="instead of", count=3, examples=["ex1"])],
            commits=[],
        )
        md = render_commit_decisions_md(decisions, source_target="pydantic/pydantic")
        assert "pydantic/pydantic" in md

    def test_commits_scanned_in_output(self) -> None:
        decisions = CommitDecisions(
            commits_scanned=42,
            patterns=[DecisionPattern(pattern="instead of", count=3, examples=["ex"])],
            commits=[],
        )
        md = render_commit_decisions_md(decisions, source_target="test/repo")
        assert "42" in md

    def test_pattern_section_header_present_when_patterns_nonempty(self) -> None:
        decisions = CommitDecisions(
            commits_scanned=5,
            patterns=[DecisionPattern(pattern="instead of", count=3, examples=["ex"])],
            commits=[],
        )
        md = render_commit_decisions_md(decisions, source_target="test/repo")
        assert "Recurring decision patterns" in md

    def test_pattern_examples_appear_in_output(self) -> None:
        decisions = CommitDecisions(
            commits_scanned=5,
            patterns=[DecisionPattern(
                pattern="instead of", count=3, examples=["switched approach instead of old way"]
            )],
            commits=[],
        )
        md = render_commit_decisions_md(decisions, source_target="test/repo")
        assert "switched approach instead of old way" in md

    def test_commit_section_header_present_when_commits_nonempty(self) -> None:
        cd = CommitDecision(
            sha="abc123456789",
            subject="fix: switch validation",
            date="2024-09-21 10:00:00 +0000",
            body_excerpt="decided to use dataclasses",
            matched_patterns=["decided to"],
            file_paths=["src/models.py"],
        )
        decisions = CommitDecisions(
            commits_scanned=5,
            patterns=[DecisionPattern(pattern="decided to", count=2, examples=["ex"])],
            commits=[cd],
        )
        md = render_commit_decisions_md(decisions, source_target="test/repo")
        assert "Notable decision commits" in md

    def test_commit_sha_and_subject_in_output(self) -> None:
        cd = CommitDecision(
            sha="abc123456789",
            subject="fix: switch validation to dataclasses",
            date="2024-09-21 10:00:00 +0000",
            body_excerpt="decided to use dataclasses",
            matched_patterns=["decided to"],
            file_paths=["src/models.py"],
        )
        decisions = CommitDecisions(
            commits_scanned=5,
            patterns=[DecisionPattern(pattern="decided to", count=2, examples=["ex"])],
            commits=[cd],
        )
        md = render_commit_decisions_md(decisions, source_target="test/repo")
        assert "abc123456789" in md
        assert "fix: switch validation to dataclasses" in md

    def test_pattern_section_absent_when_no_patterns(self) -> None:
        cd = CommitDecision(
            sha="abc123456789",
            subject="fix: something",
            date="2024-09-21 10:00:00 +0000",
            body_excerpt="decided to",
            matched_patterns=["decided to"],
            file_paths=["src/a.py"],
        )
        decisions = CommitDecisions(commits_scanned=1, patterns=[], commits=[cd])
        md = render_commit_decisions_md(decisions, source_target="test/repo")
        assert "Recurring decision patterns" not in md

    def test_commit_section_absent_when_no_commits(self) -> None:
        decisions = CommitDecisions(
            commits_scanned=5,
            patterns=[DecisionPattern(pattern="instead of", count=3, examples=["ex"])],
            commits=[],
        )
        md = render_commit_decisions_md(decisions, source_target="test/repo")
        assert "Notable decision commits" not in md


# ---------------------------------------------------------------------------
# TestJsonRoundtrip — serialization fidelity
# ---------------------------------------------------------------------------


class TestJsonRoundtrip:
    # to_json + from_json must be lossless. AI agents may persist session.json
    # and reload it; any loss would silently omit historical decision context.

    def test_commit_decision_roundtrip(self) -> None:
        cd = CommitDecision(
            sha="abc123456789",
            subject="fix: use dataclasses",
            date="2024-09-21 10:00:00 +0000",
            body_excerpt="decided to use dataclasses instead of pydantic",
            matched_patterns=["decided to", "instead of"],
            file_paths=["src/models.py", "src/users.py"],
        )
        rt = CommitDecision.from_json(cd.to_json())
        assert rt.sha == cd.sha
        assert rt.subject == cd.subject
        assert rt.date == cd.date
        assert rt.body_excerpt == cd.body_excerpt
        assert rt.matched_patterns == cd.matched_patterns
        assert rt.file_paths == cd.file_paths

    def test_decision_pattern_roundtrip(self) -> None:
        dp = DecisionPattern(
            pattern="instead of",
            count=7,
            examples=["ex1", "ex2"],
        )
        rt = DecisionPattern.from_json(dp.to_json())
        assert rt.pattern == dp.pattern
        assert rt.count == dp.count
        assert rt.examples == dp.examples

    def test_commit_decisions_full_roundtrip(self) -> None:
        dp = DecisionPattern(pattern="instead of", count=3, examples=["ex"])
        cd = CommitDecision(
            sha="abc123456789",
            subject="feat: refactor plugin system",
            date="2024-09-21 10:00:00 +0000",
            body_excerpt="use composition instead of inheritance",
            matched_patterns=["instead of"],
            file_paths=["src/plugins.py"],
        )
        decisions = CommitDecisions(commits_scanned=42, patterns=[dp], commits=[cd])
        rt = CommitDecisions.from_json(decisions.to_json())
        assert rt.commits_scanned == 42
        assert len(rt.patterns) == 1
        assert rt.patterns[0].pattern == "instead of"
        assert rt.patterns[0].count == 3
        assert len(rt.commits) == 1
        assert rt.commits[0].sha == "abc123456789"

    def test_empty_commit_decisions_roundtrip(self) -> None:
        decisions = CommitDecisions(commits_scanned=0, patterns=[], commits=[])
        rt = CommitDecisions.from_json(decisions.to_json())
        assert rt.commits_scanned == 0
        assert rt.patterns == []
        assert rt.commits == []


# ---------------------------------------------------------------------------
# TestPipelineIntegration — apply.py + render_applied_md integration
# ---------------------------------------------------------------------------


class TestPipelineIntegration:
    # These tests protect the wiring from SessionResult → ApplyResult →
    # rendered markdown. A broken wire means AI agents never see Phase C context.

    def _minimal_session(
        self,
        commit_decisions: CommitDecisions | None = None,
    ) -> Any:
        """Build a minimal SessionResult with optional commit_decisions."""
        from hijack.core.models import SessionResult
        return SessionResult(
            session_id="test-session",
            target="test/repo",
            model="claude-test",
            timestamp="2024-09-21T10:00:00+00:00",
            selected_files=[],
            categories=[],
            analysis_duration_seconds=0.0,
            project_structure="",
            commit_decisions=commit_decisions,
        )

    def _minimal_target(self, tmp_path: Path) -> Path:
        return tmp_path

    def test_apply_session_carries_commit_decisions(self, tmp_path: Path) -> None:
        from hijack.core.apply import apply_session_to_target
        from hijack.core.target_stack import TargetStack

        dp = DecisionPattern(pattern="instead of", count=3, examples=["ex"])
        decisions = CommitDecisions(commits_scanned=10, patterns=[dp], commits=[])
        session = self._minimal_session(commit_decisions=decisions)
        stack = TargetStack(
            repo_root=tmp_path, python_deps=frozenset(), js_deps=frozenset(), detected_files=[]
        )
        result = apply_session_to_target(session, tmp_path, target_stack=stack)
        assert result.commit_decisions is decisions

    def test_render_applied_md_includes_commit_decisions_section(self, tmp_path: Path) -> None:
        from hijack.core.apply import ApplyResult, render_applied_md
        from hijack.core.target_stack import TargetStack

        dp = DecisionPattern(pattern="instead of", count=3, examples=["instead of that"])
        decisions = CommitDecisions(commits_scanned=10, patterns=[dp], commits=[])
        stack = TargetStack(
            repo_root=tmp_path, python_deps=frozenset(), js_deps=frozenset(), detected_files=[]
        )
        result = ApplyResult(
            target_stack=stack,
            commit_decisions=decisions,
        )
        md = render_applied_md(result, source_target="test/repo")
        assert "Commit Decisions" in md
        assert "instead of that" in md

    def test_render_applied_md_omits_section_when_commit_decisions_none(
        self, tmp_path: Path
    ) -> None:
        from hijack.core.apply import ApplyResult, render_applied_md
        from hijack.core.target_stack import TargetStack

        stack = TargetStack(
            repo_root=tmp_path, python_deps=frozenset(), js_deps=frozenset(), detected_files=[]
        )
        result = ApplyResult(target_stack=stack, commit_decisions=None)
        md = render_applied_md(result, source_target="test/repo")
        assert "Commit Decisions" not in md

    def test_render_applied_md_omits_section_when_no_signal(self, tmp_path: Path) -> None:
        from hijack.core.apply import ApplyResult, render_applied_md
        from hijack.core.target_stack import TargetStack

        decisions = CommitDecisions(commits_scanned=0, patterns=[], commits=[])
        assert not decisions.has_signal
        stack = TargetStack(
            repo_root=tmp_path, python_deps=frozenset(), js_deps=frozenset(), detected_files=[]
        )
        result = ApplyResult(target_stack=stack, commit_decisions=decisions)
        md = render_applied_md(result, source_target="test/repo")
        assert "Commit Decisions" not in md
