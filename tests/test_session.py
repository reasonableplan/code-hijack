from __future__ import annotations

import re

import pytest

from hijack.core.models import CategoryResult, SessionResult
from hijack.core.session import SessionDiff, create_session_id, get_output_dir


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
