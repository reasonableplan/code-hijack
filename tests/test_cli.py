from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from hijack.cli import main
from hijack.core.models import AnalysisRule, CategoryResult, SessionResult
from hijack.errors import LLM_001, LLMError


def _make_session(target: str = "/local/repo") -> SessionResult:
    rule = AnalysisRule(
        rule="Use type hints",
        priority="MUST",
        confidence="high",
        ref_files=[],
        good_example="",
        bad_example="",
        reason="",
        layer="backend",
    )
    cat = CategoryResult(
        category="architecture",
        design_intent="clean",
        rules=[rule],
        anti_patterns=[],
        file_type_guides={},
        checklist=[],
        raw_llm_output="{}",
    )
    return SessionResult(
        session_id="2026-04-17_repo",
        target=target,
        model="claude-sonnet-4-6",
        timestamp="2026-04-17T00:00:00+00:00",
        selected_files=["main.py"],
        categories=[cat],
        analysis_duration_seconds=1.0,
        project_structure="repo/\n  main.py",
    )


class TestCliHelp:
    def test_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "TARGET" in result.output

    def test_version(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output


class TestCliDryRun:
    def test_dry_run_no_llm_call(self, tmp_path: Path) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            repo = tmp_path / "repo"
            repo.mkdir()
            (repo / "main.py").write_text("def main(): pass")

            result = runner.invoke(main, [str(repo), "--dry-run", "--quiet"])
        assert result.exit_code == 0
        assert "dry-run" in result.output

    def test_dry_run_shows_cost(self, tmp_path: Path) -> None:
        runner = CliRunner()
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "main.py").write_text("def main(): pass")

        result = runner.invoke(main, [str(repo), "--dry-run"])
        assert result.exit_code == 0
        assert "$" in result.output

    def test_dry_run_no_supported_files_exits_2(self, tmp_path: Path) -> None:
        runner = CliRunner()
        repo = tmp_path / "empty_repo"
        repo.mkdir()
        (repo / "readme.md").write_text("# hi")

        result = runner.invoke(main, [str(repo), "--dry-run"])
        assert result.exit_code == 2


class TestCliInvalidTarget:
    def test_nonexistent_path(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["/does/not/exist/path/xyz"])
        assert result.exit_code != 0

    def test_no_api_key_without_dry_run(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        runner = CliRunner()
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "main.py").write_text("x = 1")

        result = runner.invoke(main, [str(repo)], input="y\n")
        assert result.exit_code == 3


class TestCliFullRun:
    def test_full_run_writes_output(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "main.py").write_text("def main(): pass")

        mock_result = _make_session(target=str(repo))

        with patch("hijack.cli.ClaudeAPIClient") as mock_client_cls, \
             patch("hijack.cli.run_full_analysis", new_callable=AsyncMock) as mock_analyze, \
             patch("hijack.cli.write_output") as mock_write:

            mock_client_cls.return_value = MagicMock()
            mock_analyze.return_value = mock_result

            runner = CliRunner()
            result = runner.invoke(main, [str(repo), "--output", str(tmp_path / "out")], input="y\n")

        assert result.exit_code == 0
        mock_write.assert_called_once()

    def test_categories_option_parsed(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "main.py").write_text("x = 1")

        captured: list[list[str]] = []

        async def fake_analyze(files, repo_root, *, categories, llm, model, target):
            captured.append(categories)
            return _make_session()

        with patch("hijack.cli.ClaudeAPIClient"), \
             patch("hijack.cli.run_full_analysis", side_effect=fake_analyze), \
             patch("hijack.cli.write_output"):

            runner = CliRunner()
            runner.invoke(
                main,
                [str(repo), "--categories", "architecture,coding_style", "--output", str(tmp_path)],
                input="y\n",
            )

        assert captured == [["architecture", "coding_style"]]

    def test_user_cancels(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "main.py").write_text("x = 1")

        with patch("hijack.cli.ClaudeAPIClient"), \
             patch("hijack.cli.run_full_analysis", new_callable=AsyncMock) as mock_analyze:

            runner = CliRunner()
            runner.invoke(main, [str(repo)], input="n\n")

        mock_analyze.assert_not_called()
