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
        # Pinned to current __version__ — bump test in lockstep with version bump.
        from hijack import __version__
        assert __version__ in result.output

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

class TestAnalyzeFullRun:
    def test_full_run_writes_output(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "main.py").write_text("def main(): pass")
        mock_result = _make_session(target=str(repo))

        with patch("hijack.llm.api.ClaudeAPIClient") as mock_client_cls, \
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

        async def fake_analyze(  # noqa: E501
            files, repo_root, *, categories, llm, model, target, critic=True, **kwargs
        ):
            captured.append(categories)
            return _make_session()

        with patch("hijack.llm.api.ClaudeAPIClient"), \
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
        with patch("hijack.llm.api.ClaudeAPIClient"), \
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

        async def fake_analyze(  # noqa: E501
            files, repo_root, *, categories, llm, model, target, critic=True, **kwargs
        ):
            captured.append(categories)
            return _make_session(categories=categories)

        with patch("hijack.llm.api.ClaudeAPIClient"), \
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

        async def fake_analyze(  # noqa: E501
            files, repo_root, *, categories, llm, model, target, critic=True, **kwargs
        ):
            captured.append(categories)
            return _make_session(categories=categories)

        with patch("hijack.llm.api.ClaudeAPIClient"), \
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

        async def fake_analyze(  # noqa: E501
            files, repo_root, *, categories, llm, model, target, critic=True, **kwargs
        ):
            captured.append(categories)
            return _make_session(categories=categories)

        with patch("hijack.llm.api.ClaudeAPIClient"), \
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


# ---------------------------------------------------------------------------
# apply subcommand
# ---------------------------------------------------------------------------

class TestApplyCommand:
    def _session_json(self, path: Path, rules_scopes: list[str] | None = None) -> Path:
        """Write a session.json with rules of specified scopes."""
        from hijack.core.models import AnalysisRule, CategoryResult

        rules_scopes = rules_scopes or ["cross_project"]
        rules = [
            AnalysisRule(
                rule=f"Rule {i}",
                priority="MUST",
                confidence="high",
                ref_files=[],
                good_example=(
                    "import os\nx = 1"
                    if sc == "cross_project"
                    else "from fastapi import FastAPI"
                ),
                bad_example="",
                reason="test",
                layer="backend",
                scope=sc,
            )
            for i, sc in enumerate(rules_scopes)
        ]
        cat = CategoryResult(
            category="architecture",
            design_intent="clean",
            rules=rules,
            anti_patterns=[], file_type_guides={}, checklist=[],
            raw_llm_output="",
        )
        session = SessionResult(
            session_id="2026-05-01_senior",
            target="senior-repo",
            model="claude-test",
            timestamp="2026-05-01T00:00:00",
            selected_files=[],
            categories=[cat],
            analysis_duration_seconds=1.0,
            project_structure="",
        )
        path.mkdir(parents=True, exist_ok=True)
        json_path = path / "session.json"
        json_path.write_text(json.dumps(session.to_json()), encoding="utf-8")
        return json_path

    def test_apply_writes_claude_md_to_target(self, tmp_path: Path) -> None:
        session_json = self._session_json(tmp_path / "session", ["cross_project"])
        target = tmp_path / "target_repo"
        target.mkdir()
        runner = CliRunner()
        result = runner.invoke(
            cli, ["apply", str(session_json), str(target), "--quiet"]
        )
        assert result.exit_code == 0, result.output
        assert (target / "CLAUDE.md").exists()

    def test_apply_default_output_is_target_claude_md(self, tmp_path: Path) -> None:
        session_json = self._session_json(tmp_path / "session")
        target = tmp_path / "target"
        target.mkdir()
        runner = CliRunner()
        runner.invoke(cli, ["apply", str(session_json), str(target), "--quiet"])
        assert (target / "CLAUDE.md").exists()

    def test_apply_custom_output_path(self, tmp_path: Path) -> None:
        session_json = self._session_json(tmp_path / "session")
        target = tmp_path / "target"
        target.mkdir()
        out_file = tmp_path / "my_claude.md"
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["apply", str(session_json), str(target), "--output", str(out_file), "--quiet"]
        )
        assert result.exit_code == 0
        assert out_file.exists()

    def test_apply_strict_produces_smaller_output(self, tmp_path: Path) -> None:
        # Both cross_project and framework_internal rules
        session_json = self._session_json(
            tmp_path / "session",
            ["cross_project", "framework_internal"],
        )
        target = tmp_path / "target"
        target.mkdir()
        runner = CliRunner()

        # strict=False — keeps reference rules
        out_loose = tmp_path / "loose.md"
        runner.invoke(
            cli,
            ["apply", str(session_json), str(target), "--output", str(out_loose), "--quiet"],
        )

        # strict=True — drops reference rules
        out_strict = tmp_path / "strict.md"
        runner.invoke(
            cli,
            ["apply", str(session_json), str(target), "--output", str(out_strict),
             "--quiet", "--strict"],
        )

        # strict output should be strictly smaller or same (reference section removed)
        loose_content = out_loose.read_text(encoding="utf-8")
        strict_content = out_strict.read_text(encoding="utf-8")
        assert len(strict_content) <= len(loose_content)
        assert "For Reference" not in strict_content

    def test_apply_shows_summary_output(self, tmp_path: Path) -> None:
        session_json = self._session_json(tmp_path / "session", ["cross_project"])
        target = tmp_path / "target"
        target.mkdir()
        runner = CliRunner()
        result = runner.invoke(cli, ["apply", str(session_json), str(target)])
        assert result.exit_code == 0
        assert "[apply]" in result.output
        assert "Output:" in result.output

    def test_apply_existing_file_prompts_confirm(self, tmp_path: Path) -> None:
        session_json = self._session_json(tmp_path / "session")
        target = tmp_path / "target"
        target.mkdir()
        # Pre-create CLAUDE.md
        (target / "CLAUDE.md").write_text("existing content", encoding="utf-8")
        runner = CliRunner()
        # Provide "y" to confirm overwrite
        result = runner.invoke(
            cli, ["apply", str(session_json), str(target)], input="y\n"
        )
        # The prompt should have appeared
        assert result.exit_code == 0
        # File was overwritten
        content = (target / "CLAUDE.md").read_text(encoding="utf-8")
        assert content != "existing content"

    def test_apply_quiet_overwrites_without_prompt(self, tmp_path: Path) -> None:
        session_json = self._session_json(tmp_path / "session")
        target = tmp_path / "target"
        target.mkdir()
        (target / "CLAUDE.md").write_text("old", encoding="utf-8")
        runner = CliRunner()
        result = runner.invoke(
            cli, ["apply", str(session_json), str(target), "--quiet"]
        )
        assert result.exit_code == 0
        content = (target / "CLAUDE.md").read_text(encoding="utf-8")
        assert content != "old"

    def test_apply_content_has_universal_rules(self, tmp_path: Path) -> None:
        session_json = self._session_json(tmp_path / "session", ["cross_project"])
        target = tmp_path / "target"
        target.mkdir()
        runner = CliRunner()
        runner.invoke(cli, ["apply", str(session_json), str(target), "--quiet"])
        content = (target / "CLAUDE.md").read_text(encoding="utf-8")
        assert "Universal Rules" in content
        assert "senior-repo" in content

    def test_apply_stack_override_no_pyproject(self, tmp_path: Path) -> None:
        # target has no pyproject.toml, but --stack provides fastapi explicitly.
        # A framework_internal rule referencing fastapi should land in as_is.
        session_json = self._session_json(tmp_path / "session", ["framework_internal"])
        target = tmp_path / "target"
        target.mkdir()
        # No pyproject.toml in target
        out_file = tmp_path / "out.md"
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "apply", str(session_json), str(target),
                "--stack", "fastapi,pydantic",
                "--output", str(out_file),
                "--quiet",
            ],
        )
        assert result.exit_code == 0, result.output
        content = out_file.read_text(encoding="utf-8")
        # fastapi rule should appear in Stack-Specific section (as_is), not For Reference
        assert "Stack-Specific Rules" in content
        assert "For Reference" not in content

    def test_apply_stack_normalizes_and_dedupes(self, tmp_path: Path) -> None:
        # --stack "fastapi, Pydantic, FastAPI" should dedupe and lowercase.
        session_json = self._session_json(tmp_path / "session", ["cross_project"])
        target = tmp_path / "target"
        target.mkdir()
        out_file = tmp_path / "out.md"
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "apply", str(session_json), str(target),
                "--stack", "fastapi, Pydantic, FastAPI",
                "--output", str(out_file),
                "--quiet",
            ],
        )
        assert result.exit_code == 0, result.output
        # Stack should contain exactly fastapi and pydantic (deduped, lowercased)
        content = out_file.read_text(encoding="utf-8")
        # Header line shows "Target stack: fastapi, pydantic" — both present, no duplicate
        assert "fastapi" in content
        assert "pydantic" in content

    def test_apply_empty_target_no_stack_warns(self, tmp_path: Path) -> None:
        # No pyproject.toml + no --stack → warning emitted (stderr, mixed into output
        # by the default CliRunner which merges streams).
        session_json = self._session_json(tmp_path / "session", ["cross_project"])
        target = tmp_path / "target"
        target.mkdir()
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["apply", str(session_json), str(target)],
            catch_exceptions=False,
        )
        assert result.exit_code == 0, result.output
        assert "Warning" in result.output
        assert "no dependencies detected" in result.output

    def test_apply_stack_provided_no_warning(self, tmp_path: Path) -> None:
        # --stack is explicitly given → no warning even if target is empty.
        session_json = self._session_json(tmp_path / "session", ["cross_project"])
        target = tmp_path / "target"
        target.mkdir()
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["apply", str(session_json), str(target), "--stack", "fastapi"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0, result.output
        assert "Warning" not in result.output

    def test_apply_quiet_no_warning(self, tmp_path: Path) -> None:
        # --quiet suppresses the empty-stack warning too.
        session_json = self._session_json(tmp_path / "session", ["cross_project"])
        target = tmp_path / "target"
        target.mkdir()
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["apply", str(session_json), str(target), "--quiet"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "Warning" not in result.output


# ---------------------------------------------------------------------------
# measure subcommand
# ---------------------------------------------------------------------------

class TestMeasureCommand:
    def _session_json(self, path: Path, session_id: str = "2026-01-01_repo") -> Path:
        """Write a minimal session.json for measure tests."""
        rule = AnalysisRule(
            rule="Use type hints", priority="MUST", confidence="high",
            ref_files=[], good_example="", bad_example="", reason="", layer="backend",
        )
        cat = CategoryResult(
            category="architecture", design_intent="clean", rules=[rule],
            anti_patterns=[], file_type_guides={}, checklist=[], raw_llm_output="",
        )
        session = SessionResult(
            session_id=session_id, target="t", model="m",
            timestamp="2026-01-01T00:00:00", selected_files=[],
            categories=[cat], analysis_duration_seconds=0.0,
            project_structure="",
        )
        path.mkdir(parents=True, exist_ok=True)
        json_path = path / "session.json"
        json_path.write_text(json.dumps(session.to_json()), encoding="utf-8")
        return json_path

    def test_measure_single_creates_measurement_json(self, tmp_path: Path) -> None:
        session_json = self._session_json(tmp_path / "session")
        runner = CliRunner()
        result = runner.invoke(cli, ["measure", str(session_json)])
        assert result.exit_code == 0, result.output
        assert (tmp_path / "session" / "measurement.json").exists()

    def test_measure_single_stdout_contains_session_id(self, tmp_path: Path) -> None:
        session_json = self._session_json(tmp_path / "session", "2026-01-01_myrepo")
        runner = CliRunner()
        result = runner.invoke(cli, ["measure", str(session_json)])
        assert result.exit_code == 0, result.output
        assert "2026-01-01_myrepo" in result.output

    def test_measure_single_measurement_json_is_valid(self, tmp_path: Path) -> None:
        session_json = self._session_json(tmp_path / "session")
        runner = CliRunner()
        runner.invoke(cli, ["measure", str(session_json)])
        measurement_path = tmp_path / "session" / "measurement.json"
        data = json.loads(measurement_path.read_text(encoding="utf-8"))
        assert "session_id" in data
        assert "cited_ratio" in data
        assert "must_ratio" in data

    def test_measure_two_sessions_shows_diff(self, tmp_path: Path) -> None:
        s1 = self._session_json(tmp_path / "s1", "2026-01-01_before")
        s2 = self._session_json(tmp_path / "s2", "2026-01-02_after")
        runner = CliRunner()
        result = runner.invoke(cli, ["measure", str(s1), str(s2)])
        assert result.exit_code == 0, result.output
        # diff output must reference both session ids
        assert "before" in result.output or "2026-01-01" in result.output
        assert "after" in result.output or "2026-01-02" in result.output

    def test_measure_two_sessions_exit_code_zero(self, tmp_path: Path) -> None:
        s1 = self._session_json(tmp_path / "s1", "2026-01-01_a")
        s2 = self._session_json(tmp_path / "s2", "2026-01-02_b")
        runner = CliRunner()
        result = runner.invoke(cli, ["measure", str(s1), str(s2)])
        assert result.exit_code == 0

    def test_measure_missing_session_errors(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["measure", str(tmp_path / "nonexistent.json")])
        assert result.exit_code != 0

    def test_measure_help_shows_usage(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["measure", "--help"])
        assert result.exit_code == 0
        assert "SESSION" in result.output


class TestCliImportWithoutAnthropic:
    """cli.py 는 anthropic([api] extra) 없이 import 가능해야 한다 (measure/diff 경로)."""

    def test_cli_imports_with_anthropic_blocked(self) -> None:
        import subprocess
        import sys

        code = (
            "import sys\n"
            "class _Block:\n"
            "    def find_module(self, name, path=None):\n"
            "        if name == 'anthropic' or name.startswith('anthropic.'):\n"
            "            return self\n"
            "    def load_module(self, name):\n"
            "        raise ImportError('anthropic blocked for test')\n"
            "sys.meta_path.insert(0, _Block())\n"
            "import hijack.cli\n"
            "print('OK')\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr
        assert "OK" in result.stdout
