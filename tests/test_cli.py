from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from hijack.cli import cli
from hijack.core.models import AnalysisRule, CategoryResult, SessionResult


def _make_session(
    target: str = "/local/repo",
    categories: list[str] | None = None,
    include_error: bool = False,
) -> SessionResult:
    rule = AnalysisRule(
        rule="Use type hints", priority="MUST", confidence="high",
        ref_files=[], good_example="", bad_example="", reason="", layer="backend",
    )
    cats = []
    for cat_name in (categories or ["architecture"]):
        cats.append(CategoryResult(
            category=cat_name,
            design_intent="clean",
            rules=[rule],
            anti_patterns=[], file_type_guides={}, checklist=[],
            raw_llm_output="{}",
            error="LLM_002: fail" if include_error else None,
        ))
    return SessionResult(
        session_id="2026-04-17_repo", target=target, model="claude-sonnet-4-6",
        timestamp="2026-04-17T00:00:00+00:00", selected_files=["main.py"],
        categories=cats, analysis_duration_seconds=1.0,
        project_structure="repo/\n  main.py",
    )


# ---------------------------------------------------------------------------
# Group-level tests
# ---------------------------------------------------------------------------

class TestCliGroupHelp:
    def test_group_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "analyze" in result.output
        assert "diff" in result.output

    def test_version(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output

    def test_analyze_help_shows_target(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["analyze", "--help"])
        assert result.exit_code == 0
        assert "TARGET" in result.output

    def test_diff_help_shows_sessions(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["diff", "--help"])
        assert result.exit_code == 0
        assert "SESSION1" in result.output
        assert "SESSION2" in result.output


# ---------------------------------------------------------------------------
# analyze subcommand — dry-run
# ---------------------------------------------------------------------------

class TestAnalyzeDryRun:
    def test_dry_run_no_llm_call(self, tmp_path: Path) -> None:
        runner = CliRunner()
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "main.py").write_text("def main(): pass")
        result = runner.invoke(cli, ["analyze", str(repo), "--dry-run", "--quiet"])
        assert result.exit_code == 0
        assert "dry-run" in result.output

    def test_dry_run_shows_cost(self, tmp_path: Path) -> None:
        runner = CliRunner()
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "main.py").write_text("def main(): pass")
        result = runner.invoke(cli, ["analyze", str(repo), "--dry-run"])
        assert result.exit_code == 0
        assert "$" in result.output

    def test_dry_run_no_supported_files_exits_2(self, tmp_path: Path) -> None:
        runner = CliRunner()
        repo = tmp_path / "empty_repo"
        repo.mkdir()
        (repo / "readme.md").write_text("# hi")
        result = runner.invoke(cli, ["analyze", str(repo), "--dry-run"])
        assert result.exit_code == 2


# ---------------------------------------------------------------------------
# analyze subcommand — invalid inputs
# ---------------------------------------------------------------------------

class TestAnalyzeInvalidTarget:
    def test_nonexistent_path(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["analyze", "/does/not/exist/path/xyz"])
        assert result.exit_code != 0

    def test_no_api_key_without_dry_run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        runner = CliRunner()
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "main.py").write_text("x = 1")
        result = runner.invoke(cli, ["analyze", str(repo)], input="y\n")
        assert result.exit_code == 3


# ---------------------------------------------------------------------------
# analyze subcommand — full run
# ---------------------------------------------------------------------------

class TestAnalyzeLocalMode:
    """`--llm-mode local` skips the API key requirement and instantiates LocalLLM."""

    def test_local_mode_does_not_require_api_key(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "main.py").write_text("def main(): pass")
        mock_result = _make_session(target=str(repo))

        with patch("hijack.cli.LocalLLM") as mock_local_cls, \
             patch("hijack.cli.run_full_analysis", new_callable=AsyncMock) as mock_analyze, \
             patch("hijack.cli.write_output"):
            mock_local_cls.return_value = MagicMock()
            mock_analyze.return_value = mock_result
            runner = CliRunner()
            result = runner.invoke(
                cli,
                [
                    "analyze",
                    str(repo),
                    "--llm-mode",
                    "local",
                    "--output",
                    str(tmp_path / "out"),
                ],
            )
        assert result.exit_code == 0, result.output
        mock_local_cls.assert_called_once()
        # No interactive confirm prompt in local mode — just runs.
        assert "분석을 시작할까요" not in result.output

    def test_local_mode_uses_default_comms_dir_under_output(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "main.py").write_text("def main(): pass")
        mock_result = _make_session(target=str(repo))
        out = tmp_path / "out"

        captured_comms: list[Path] = []

        def capture_comms(comms_path: Path):
            captured_comms.append(comms_path)
            return MagicMock()

        with patch("hijack.cli.LocalLLM", side_effect=capture_comms), \
             patch("hijack.cli.run_full_analysis", new_callable=AsyncMock) as mock_analyze, \
             patch("hijack.cli.write_output"):
            mock_analyze.return_value = mock_result
            runner = CliRunner()
            runner.invoke(
                cli,
                [
                    "analyze",
                    str(repo),
                    "--llm-mode",
                    "local",
                    "--output",
                    str(out),
                ],
            )

        assert len(captured_comms) == 1
        assert captured_comms[0] == out / "comms"
        assert captured_comms[0].is_dir()

    def test_local_mode_respects_explicit_comms_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "main.py").write_text("def main(): pass")
        mock_result = _make_session(target=str(repo))
        explicit = tmp_path / "my-comms"

        captured: list[Path] = []

        def capture(p: Path):
            captured.append(p)
            return MagicMock()

        with patch("hijack.cli.LocalLLM", side_effect=capture), \
             patch("hijack.cli.run_full_analysis", new_callable=AsyncMock) as mock_analyze, \
             patch("hijack.cli.write_output"):
            mock_analyze.return_value = mock_result
            runner = CliRunner()
            runner.invoke(
                cli,
                [
                    "analyze",
                    str(repo),
                    "--llm-mode",
                    "local",
                    "--comms-dir",
                    str(explicit),
                    "--output",
                    str(tmp_path / "out"),
                ],
            )
        assert captured == [explicit]


class TestAnalyzeFullRun:
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
            result = runner.invoke(
                cli,
                ["analyze", str(repo), "--output", str(tmp_path / "out")],
                input="y\n",
            )
        assert result.exit_code == 0
        mock_write.assert_called_once()

    def test_categories_option_parsed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "main.py").write_text("x = 1")
        captured: list[list[str]] = []

        async def fake_analyze(files, repo_root, *, categories, llm, model, target, critic=True):
            captured.append(categories)
            return _make_session()

        with patch("hijack.cli.ClaudeAPIClient"), \
             patch("hijack.cli.run_full_analysis", side_effect=fake_analyze), \
             patch("hijack.cli.write_output"):
            runner = CliRunner()
            runner.invoke(
                cli,
                ["analyze", str(repo), "--categories", "architecture,coding_style",
                 "--output", str(tmp_path)],
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
            runner.invoke(cli, ["analyze", str(repo)], input="n\n")
        mock_analyze.assert_not_called()


# ---------------------------------------------------------------------------
# --resume option
# ---------------------------------------------------------------------------

class TestAnalyzeResume:
    def _write_session_json(self, path: Path, categories: list[str],
                             include_error: bool = False) -> Path:
        session = _make_session(categories=categories, include_error=include_error)
        session_dir = path / session.session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        (session_dir / "session.json").write_text(
            json.dumps(session.to_json()), encoding="utf-8"
        )
        return session_dir / "session.json"

    def test_resume_skips_completed_categories(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "main.py").write_text("x = 1")

        session_json = self._write_session_json(tmp_path / "sessions", ["architecture"])
        captured: list[list[str]] = []

        async def fake_analyze(files, repo_root, *, categories, llm, model, target, critic=True):
            captured.append(categories)
            return _make_session(categories=categories)

        with patch("hijack.cli.ClaudeAPIClient"), \
             patch("hijack.cli.run_full_analysis", side_effect=fake_analyze), \
             patch("hijack.cli.write_output"):
            runner = CliRunner()
            runner.invoke(
                cli,
                ["analyze", str(repo),
                 "--categories", "architecture,coding_style",
                 "--resume", str(session_json),
                 "--output", str(tmp_path / "out")],
                input="y\n",
            )

        assert captured == [["coding_style"]]

    def test_resume_all_done_exits_early(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "main.py").write_text("x = 1")

        session_json = self._write_session_json(
            tmp_path / "sessions", ["architecture", "coding_style"]
        )
        with patch("hijack.cli.run_full_analysis", new_callable=AsyncMock) as mock_analyze:
            runner = CliRunner()
            result = runner.invoke(
                cli,
                ["analyze", str(repo),
                 "--categories", "architecture,coding_style",
                 "--resume", str(session_json)],
            )
        assert result.exit_code == 0
        output_lower = result.output.lower()
        assert ("모두" in result.output or "completed" in output_lower
                or "완료" in result.output)
        mock_analyze.assert_not_called()

    def test_resume_from_directory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "main.py").write_text("x = 1")

        session_json = self._write_session_json(tmp_path / "sessions", ["architecture"])
        session_dir = session_json.parent
        captured: list[list[str]] = []

        async def fake_analyze(files, repo_root, *, categories, llm, model, target, critic=True):
            captured.append(categories)
            return _make_session(categories=categories)

        with patch("hijack.cli.ClaudeAPIClient"), \
             patch("hijack.cli.run_full_analysis", side_effect=fake_analyze), \
             patch("hijack.cli.write_output"):
            runner = CliRunner()
            runner.invoke(
                cli,
                ["analyze", str(repo),
                 "--categories", "architecture,coding_style",
                 "--resume", str(session_dir),
                 "--output", str(tmp_path / "out")],
                input="y\n",
            )
        assert captured == [["coding_style"]]

    def test_resume_failed_category_not_skipped(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "main.py").write_text("x = 1")

        session_json = self._write_session_json(
            tmp_path / "sessions", ["architecture"], include_error=True
        )
        captured: list[list[str]] = []

        async def fake_analyze(files, repo_root, *, categories, llm, model, target, critic=True):
            captured.append(categories)
            return _make_session(categories=categories)

        with patch("hijack.cli.ClaudeAPIClient"), \
             patch("hijack.cli.run_full_analysis", side_effect=fake_analyze), \
             patch("hijack.cli.write_output"):
            runner = CliRunner()
            runner.invoke(
                cli,
                ["analyze", str(repo),
                 "--categories", "architecture",
                 "--resume", str(session_json),
                 "--output", str(tmp_path / "out")],
                input="y\n",
            )
        assert captured == [["architecture"]]


# ---------------------------------------------------------------------------
# diff subcommand
# ---------------------------------------------------------------------------

class TestDiffCommand:
    def _session_json(self, path: Path, category: str, rule_text: str) -> Path:
        rule = AnalysisRule(
            rule=rule_text, priority="MUST", confidence="high",
            ref_files=[], good_example="", bad_example="", reason="", layer="backend",
        )
        cat = CategoryResult(
            category=category, design_intent="", rules=[rule],
            anti_patterns=[], file_type_guides={}, checklist=[], raw_llm_output="",
        )
        session = SessionResult(
            session_id=f"2026-04-17_{path.name}", target="t", model="m",
            timestamp="t", selected_files=[], categories=[cat],
            analysis_duration_seconds=0.0, project_structure="",
        )
        path.mkdir(parents=True, exist_ok=True)
        json_path = path / "session.json"
        json_path.write_text(json.dumps(session.to_json()), encoding="utf-8")
        return json_path

    def test_diff_shows_added_rule(self, tmp_path: Path) -> None:
        old_json = self._session_json(tmp_path / "old", "architecture", "Rule A")
        new_json = self._session_json(tmp_path / "new", "architecture", "Rule B")
        runner = CliRunner()
        result = runner.invoke(cli, ["diff", str(old_json), str(new_json)])
        assert result.exit_code == 0
        assert "Added" in result.output or "Rule B" in result.output

    def test_diff_empty_shows_no_changes(self, tmp_path: Path) -> None:
        old_json = self._session_json(tmp_path / "old", "architecture", "Rule A")
        new_json = self._session_json(tmp_path / "new", "architecture", "Rule A")
        runner = CliRunner()
        result = runner.invoke(cli, ["diff", str(old_json), str(new_json)])
        assert result.exit_code == 0
        assert "No changes" in result.output

    def test_diff_writes_to_file(self, tmp_path: Path) -> None:
        old_json = self._session_json(tmp_path / "old", "architecture", "Rule A")
        new_json = self._session_json(tmp_path / "new", "architecture", "Rule B")
        out_file = tmp_path / "diff.md"
        runner = CliRunner()
        result = runner.invoke(
            cli, ["diff", str(old_json), str(new_json), "--output", str(out_file)]
        )
        assert result.exit_code == 0
        assert out_file.exists()
        content = out_file.read_text(encoding="utf-8")
        assert "Rule B" in content or "Added" in content

    def test_diff_from_directories(self, tmp_path: Path) -> None:
        old_json = self._session_json(tmp_path / "old", "architecture", "Rule A")
        new_json = self._session_json(tmp_path / "new", "architecture", "Rule B")
        runner = CliRunner()
        result = runner.invoke(cli, ["diff", str(old_json.parent), str(new_json.parent)])
        assert result.exit_code == 0

    def test_diff_missing_session_errors(self, tmp_path: Path) -> None:
        existing = self._session_json(tmp_path / "old", "architecture", "Rule A")
        runner = CliRunner()
        result = runner.invoke(cli, ["diff", str(existing), "/does/not/exist.json"])
        assert result.exit_code != 0
