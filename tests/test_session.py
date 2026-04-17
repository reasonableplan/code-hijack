from __future__ import annotations

import re

import pytest

from hijack.core.models import AnalysisRule, CategoryResult, SessionResult
from hijack.core.session import RuleChange, SessionDiff, create_session_id, get_output_dir


def _make_session_result(session_id: str = "2026-04-17_test") -> SessionResult:
    """테스트용 최소 SessionResult 생성."""
    return SessionResult(
        session_id=session_id,
        target="https://github.com/test/repo",
        model="claude-sonnet-4-6",
        timestamp="2026-04-17T00:00:00",
        selected_files=[],
        categories=[],
        analysis_duration_seconds=0.0,
        project_structure="",
    )


class TestCreateSessionId:
    def test_github_url_extracts_repo_name(self) -> None:
        result = create_session_id("https://github.com/fastapi/fastapi")
        assert re.match(r"^\d{4}-\d{2}-\d{2}_fastapi$", result), f"Got: {result}"

    def test_github_url_with_git_suffix(self) -> None:
        result = create_session_id("https://github.com/org/my-repo.git")
        assert result.endswith("_my-repo"), f"Got: {result}"

    def test_local_path(self) -> None:
        result = create_session_id("/local/path/to/myproject")
        assert result.endswith("_myproject"), f"Got: {result}"

    def test_date_format(self) -> None:
        result = create_session_id("https://github.com/fastapi/fastapi")
        date_part = result.split("_")[0]
        assert re.match(r"^\d{4}-\d{2}-\d{2}$", date_part), f"Date part: {date_part}"

    def test_trailing_slash_url(self) -> None:
        result = create_session_id("https://github.com/org/somerepo/")
        assert result.endswith("_somerepo"), f"Got: {result}"


class TestGetOutputDir:
    def test_creates_directory(self, tmp_path: pytest.TempPathFactory) -> None:
        session_id = "2026-04-17_fastapi"
        output_dir = get_output_dir(tmp_path, session_id)
        assert output_dir.exists()
        assert output_dir.is_dir()

    def test_returns_correct_path(self, tmp_path: pytest.TempPathFactory) -> None:
        session_id = "2026-04-17_fastapi"
        output_dir = get_output_dir(tmp_path, session_id)
        assert output_dir == tmp_path / session_id

    def test_idempotent(self, tmp_path: pytest.TempPathFactory) -> None:
        session_id = "2026-04-17_fastapi"
        # 두 번 호출해도 에러 없음
        get_output_dir(tmp_path, session_id)
        output_dir = get_output_dir(tmp_path, session_id)
        assert output_dir.exists()


class TestSessionDiff:
    def test_compare_returns_empty_diff(self) -> None:
        old = _make_session_result("2026-04-10_test")
        new = _make_session_result("2026-04-17_test")
        diff = SessionDiff.compare(old, new)
        assert diff.added == []
        assert diff.removed == []
        assert diff.changed == []

    def test_compare_returns_session_diff_instance(self) -> None:
        old = _make_session_result()
        new = _make_session_result()
        diff = SessionDiff.compare(old, new)
        assert isinstance(diff, SessionDiff)

    def test_is_empty_on_identical_sessions(self) -> None:
        old = _make_session_result()
        new = _make_session_result()
        assert SessionDiff.compare(old, new).is_empty


def _rule(text: str, priority: str = "MUST", layer: str = "backend") -> AnalysisRule:
    return AnalysisRule(
        rule=text, priority=priority, confidence="high",
        ref_files=[], good_example="", bad_example="", reason="", layer=layer,
    )


def _session_with_rules(*rules: AnalysisRule) -> SessionResult:
    cat = CategoryResult(
        category="architecture", design_intent="",
        rules=list(rules), anti_patterns=[], file_type_guides={},
        checklist=[], raw_llm_output="",
    )
    return SessionResult(
        session_id="2026-04-17_test", target="t", model="m",
        timestamp="2026-04-17T00:00:00", selected_files=[],
        categories=[cat], analysis_duration_seconds=0.0, project_structure="",
    )


class TestSessionDiffCompare:
    def test_added_rules_detected(self) -> None:
        old = _session_with_rules(_rule("Rule A"))
        new = _session_with_rules(_rule("Rule A"), _rule("Rule B"))
        diff = SessionDiff.compare(old, new)
        assert len(diff.added) == 1
        assert diff.added[0].rule == "Rule B"
        assert diff.removed == []

    def test_removed_rules_detected(self) -> None:
        old = _session_with_rules(_rule("Rule A"), _rule("Rule B"))
        new = _session_with_rules(_rule("Rule A"))
        diff = SessionDiff.compare(old, new)
        assert len(diff.removed) == 1
        assert diff.removed[0].rule == "Rule B"
        assert diff.added == []

    def test_changed_rules_detected(self) -> None:
        old = _session_with_rules(_rule("Rule A", priority="SHOULD"))
        new = _session_with_rules(_rule("Rule A", priority="MUST"))
        diff = SessionDiff.compare(old, new)
        assert len(diff.changed) == 1
        change = diff.changed[0]
        assert isinstance(change, RuleChange)
        assert change.rule == "Rule A"
        assert "priority" in change.changed_fields
        assert change.old.priority == "SHOULD"
        assert change.new.priority == "MUST"

    def test_unchanged_rules_not_in_diff(self) -> None:
        r = _rule("Stable Rule")
        old = _session_with_rules(r)
        new = _session_with_rules(r)
        diff = SessionDiff.compare(old, new)
        assert diff.is_empty

    def test_layer_change_detected(self) -> None:
        old = _session_with_rules(_rule("Rule X", layer="backend"))
        new = _session_with_rules(_rule("Rule X", layer="frontend"))
        diff = SessionDiff.compare(old, new)
        assert len(diff.changed) == 1
        assert "layer" in diff.changed[0].changed_fields

    def test_multiple_changes_in_one_rule(self) -> None:
        old = _session_with_rules(_rule("Rule Z", priority="SHOULD", layer="db"))
        new = _session_with_rules(_rule("Rule Z", priority="MUST", layer="backend"))
        diff = SessionDiff.compare(old, new)
        fields = diff.changed[0].changed_fields
        assert "priority" in fields
        assert "layer" in fields

    def test_to_markdown_empty_diff(self) -> None:
        diff = SessionDiff()
        assert "No changes" in diff.to_markdown()

    def test_to_markdown_shows_added(self) -> None:
        old = _session_with_rules()
        new = _session_with_rules(_rule("New Rule"))
        diff = SessionDiff.compare(old, new)
        md = diff.to_markdown()
        assert "Added" in md
        assert "New Rule" in md

    def test_to_markdown_shows_removed(self) -> None:
        old = _session_with_rules(_rule("Old Rule"))
        new = _session_with_rules()
        diff = SessionDiff.compare(old, new)
        md = diff.to_markdown()
        assert "Removed" in md
        assert "Old Rule" in md
