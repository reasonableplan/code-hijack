"""Tests for the pure git-log parser in hijack.core.archaeology."""

from __future__ import annotations

from hijack.core.archaeology import (
    GIT_LOG_FORMAT,
    RECORD_SEP,
    UNIT_SEP,
    Commit,
    FileHistory,
    parse_git_log,
    render_history_for_prompt,
)


def _record(sha: str, subject: str, author: str, date: str, body: str) -> str:
    """Build a single git-log record matching GIT_LOG_FORMAT."""
    rs, us = RECORD_SEP, UNIT_SEP
    return f"{sha}{rs}{subject}{rs}{author}{rs}{date}{rs}{body}{us}"


class TestParseGitLog:
    def test_empty_input_returns_empty_list(self) -> None:
        assert parse_git_log("") == []
        assert parse_git_log("   \n  ") == []

    def test_single_commit(self) -> None:
        stdout = _record(
            "a1b2c3d4e5f6",
            "fix: revert pydantic",
            "Alice",
            "2024-08-12 14:30:00 +0900",
            "Causes runtime regressions in async paths.",
        )
        commits = parse_git_log(stdout)
        assert len(commits) == 1
        c = commits[0]
        assert c.sha == "a1b2c3d4e5f6"
        assert c.short_sha == "a1b2c3d"
        assert c.subject == "fix: revert pydantic"
        assert c.author == "Alice"
        assert c.body.startswith("Causes runtime regressions")

    def test_multiple_commits(self) -> None:
        stdout = "".join(
            [
                _record("aaa1111", "first", "A", "2024-01-01", "body1"),
                _record("bbb2222", "second", "B", "2024-01-02", "body2"),
                _record("ccc3333", "third", "C", "2024-01-03", ""),
            ]
        )
        commits = parse_git_log(stdout)
        assert [c.sha for c in commits] == ["aaa1111", "bbb2222", "ccc3333"]
        assert commits[2].body == ""

    def test_body_with_newlines_preserved(self) -> None:
        body = "line1\nline2\n\nline4"
        stdout = _record("aaa", "subj", "A", "2024-01-01", body)
        commits = parse_git_log(stdout)
        assert "line1" in commits[0].body
        assert "line4" in commits[0].body

    def test_malformed_record_dropped(self) -> None:
        # Only 2 fields — should be silently skipped.
        bad = f"justasha{RECORD_SEP}only_subject{UNIT_SEP}"
        good = _record("aaa", "ok", "A", "2024-01-01", "")
        commits = parse_git_log(bad + good)
        assert len(commits) == 1
        assert commits[0].sha == "aaa"

    def test_format_string_constant_matches_separators(self) -> None:
        # Sanity check the wrapper module relies on.
        assert RECORD_SEP in GIT_LOG_FORMAT
        assert UNIT_SEP in GIT_LOG_FORMAT
        assert GIT_LOG_FORMAT.endswith(UNIT_SEP)


class TestRenderHistoryForPrompt:
    def test_none_returns_empty_string(self) -> None:
        assert render_history_for_prompt(None) == ""

    def test_empty_history_returns_empty_string(self) -> None:
        assert render_history_for_prompt(FileHistory()) == ""

    def test_single_commit_block(self) -> None:
        h = FileHistory(
            commits=[
                Commit(
                    sha="a1b2c3d4e5f6",
                    subject="refactor: drop pydantic",
                    author="Alice",
                    date="2024-08-12 14:30:00 +0900",
                    body="dataclasses are simpler.",
                )
            ]
        )
        out = render_history_for_prompt(h)
        assert out.startswith("<history>")
        assert out.endswith("</history>")
        assert "a1b2c3d" in out
        assert "refactor: drop pydantic" in out
        assert "2024-08-12" in out
        assert "dataclasses are simpler" in out

    def test_caps_commits_at_max(self) -> None:
        commits = [
            Commit(sha=f"sha{i:07d}", subject=f"s{i}", author="A", date="2024-01-01", body="")
            for i in range(10)
        ]
        out = render_history_for_prompt(FileHistory(commits=commits), max_commits=2)
        assert "s0" in out and "s1" in out
        assert "s2" not in out

    def test_truncates_long_body(self) -> None:
        body = "x" * 1000
        h = FileHistory(commits=[Commit(sha="aaa", subject="s", author="A", date="d", body=body)])
        out = render_history_for_prompt(h, max_body_chars=50)
        # 50 chars of body + framing — never the full 1000.
        assert "x" * 1000 not in out
        assert "x" * 50 in out
        assert "[…truncated]" in out

    def test_default_body_cap_is_generous(self) -> None:
        # Phase A review fix: 200-char cap was clipping the actual WHY text.
        # Default should comfortably fit a real revert rationale (~500-800 chars).
        body = "First sentence about pydantic. " * 30  # ~900 chars
        h = FileHistory(commits=[Commit(sha="aaa", subject="s", author="A", date="d", body=body)])
        out = render_history_for_prompt(h)  # default max_body_chars
        # At least 600 chars of body should make it through.
        assert out.count("First sentence about pydantic.") >= 20

    def test_multi_line_body_preserved(self) -> None:
        body = "Line one of rationale.\n\n- bullet a\n- bullet b\n\nFinal line."
        h = FileHistory(commits=[Commit(sha="aaa", subject="s", author="A", date="d", body=body)])
        out = render_history_for_prompt(h)
        # Each line must survive with its leading indent — no single-line collapse.
        assert "    Line one of rationale." in out
        assert "    - bullet a" in out
        assert "    - bullet b" in out
        assert "    Final line." in out

    def test_reverts_section_appears(self) -> None:
        h = FileHistory(
            commits=[Commit(sha="aaa", subject="ok", author="A", date="d", body="")],
            reverts=[Commit(sha="bbb1234", subject="Revert: foo", author="A", date="d", body="")],
        )
        out = render_history_for_prompt(h)
        assert "reverts touching this file" in out
        assert "bbb1234" in out


class TestRoundTrip:
    def test_commit_to_json_from_json(self) -> None:
        c = Commit(sha="aaa", subject="s", author="A", date="d", body="b")
        assert Commit.from_json(c.to_json()) == c

    def test_file_history_to_json_from_json(self) -> None:
        h = FileHistory(
            commits=[Commit(sha="aaa", subject="s", author="A", date="d", body="b")],
            reverts=[Commit(sha="bbb", subject="Revert", author="A", date="d", body="")],
        )
        assert FileHistory.from_json(h.to_json()) == h
