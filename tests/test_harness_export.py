"""harness_export — code-hijack 세션 → HarnessAI conventions/guidelines 변환 테스트."""
from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from hijack.cli import cli
from hijack.core.harness_export import export_session
from hijack.core.models import AnalysisRule, CategoryResult, SessionResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _rule(
    text: str = "Use type hints",
    *,
    layer: str = "backend",
    priority: str = "MUST",
    scope: str = "cross_project",
    good: str = "def f(x: int) -> str: ...",
    bad: str = "def f(x): ...",
) -> AnalysisRule:
    return AnalysisRule(
        rule=text,
        priority=priority,
        confidence="high",
        ref_files=["src/main.py:10"],
        good_example=good,
        bad_example=bad,
        reason=f"reason for {text}",
        layer=layer,
        scope=scope,
    )


def _category(
    name: str = "architecture",
    rules: list[AnalysisRule] | None = None,
    anti_patterns: list[dict[str, str]] | None = None,
) -> CategoryResult:
    return CategoryResult(
        category=name,
        design_intent=f"intent for {name}",
        rules=rules if rules is not None else [_rule()],
        anti_patterns=anti_patterns if anti_patterns is not None else [],
        file_type_guides={},
        checklist=[],
        raw_llm_output="",
    )


def _session(*categories: CategoryResult) -> SessionResult:
    return SessionResult(
        session_id="2026-04-24_test",
        target="https://github.com/x/y",
        model="m",
        timestamp="2026-04-24T00:00:00+00:00",
        selected_files=[],
        categories=list(categories) if categories else [_category()],
        analysis_duration_seconds=0.0,
        project_structure="",
        files_by_layer={},
    )


# ---------------------------------------------------------------------------
# export_session — 기본 흐름
# ---------------------------------------------------------------------------

class TestExportSession:
    def test_creates_conventions_md(self, tmp_path: Path) -> None:
        summary = export_session(_session(), tmp_path)
        assert summary.conventions_path.exists()
        assert summary.conventions_path == tmp_path / "conventions.md"
        body = summary.conventions_path.read_text(encoding="utf-8")
        assert "프로젝트 컨벤션" in body
        assert "https://github.com/x/y" in body  # target 명시

    def test_cross_project_rule_in_guidelines(self, tmp_path: Path) -> None:
        s = _session(_category(rules=[_rule(layer="backend", scope="cross_project")]))
        summary = export_session(s, tmp_path)
        target = tmp_path / "guidelines" / "backend" / "structure.md"
        assert target in summary.guideline_paths
        assert target.exists()
        body = target.read_text(encoding="utf-8")
        assert "Use type hints" in body
        assert "✅ Good" in body
        assert "❌ Bad" in body

    def test_framework_internal_excluded(self, tmp_path: Path) -> None:
        s = _session(_category(rules=[
            _rule("internal only", layer="backend", scope="framework_internal"),
        ]))
        summary = export_session(s, tmp_path)
        # guidelines 파일 자체가 안 만들어짐.
        assert summary.guideline_paths == []
        # conventions.md 의 결정 표에도 안 들어감.
        body = summary.conventions_path.read_text(encoding="utf-8")
        assert "internal only" not in body

    def test_domain_specific_goes_to_lesson_candidates(self, tmp_path: Path) -> None:
        s = _session(_category(rules=[
            _rule("domain rule", layer="backend", scope="domain_specific"),
        ]))
        summary = export_session(s, tmp_path)
        assert summary.lesson_candidates_path is not None
        body = summary.lesson_candidates_path.read_text(encoding="utf-8")
        assert "domain rule" in body
        assert "Domain-Specific Rules" in body
        # guidelines 에는 안 들어감 (cross_project 만).
        assert summary.guideline_paths == []

    def test_shared_layer_only_in_conventions(self, tmp_path: Path) -> None:
        # shared layer 의 cross_project rule 은 conventions 의 "공통 원칙" 섹션에만.
        s = _session(_category(rules=[
            _rule("shared rule", layer="shared", scope="cross_project"),
        ]))
        summary = export_session(s, tmp_path)
        # guidelines 파일 없음.
        assert summary.guideline_paths == []
        body = summary.conventions_path.read_text(encoding="utf-8")
        assert "shared rule" in body
        assert "## 핵심 원칙 (모든 레이어 공통)" in body

    def test_db_layer_files_use_db_prefix(self, tmp_path: Path) -> None:
        s = _session(_category("data_model", rules=[
            _rule("db schema rule", layer="db", scope="cross_project"),
        ]))
        summary = export_session(s, tmp_path)
        target = tmp_path / "guidelines" / "backend" / "db-models.md"
        assert target in summary.guideline_paths
        assert target.exists()

    def test_anti_patterns_in_lesson_candidates(self, tmp_path: Path) -> None:
        s = _session(_category(
            rules=[_rule()],
            anti_patterns=[{
                "pattern": "Global state singleton",
                "reason": "Hard to test",
                "alternative": "Inject dependency",
            }],
        ))
        summary = export_session(s, tmp_path)
        assert summary.lesson_candidates_path is not None
        body = summary.lesson_candidates_path.read_text(encoding="utf-8")
        assert "Global state singleton" in body
        assert "Anti-Patterns" in body

    def test_dependencies_category_in_conventions_section(self, tmp_path: Path) -> None:
        # dependencies 카테고리는 별도 guidelines 파일을 만들지 않고 conventions 의
        # "의존성 정책" 섹션으로 들어감.
        s = _session(_category("dependencies", rules=[
            _rule("Use uv for Python deps", layer="backend", scope="cross_project"),
        ]))
        summary = export_session(s, tmp_path)
        body = summary.conventions_path.read_text(encoding="utf-8")
        assert "## 의존성 정책 (dependencies)" in body
        assert "Use uv for Python deps" in body
        # guidelines 파일은 안 만들어짐.
        assert summary.guideline_paths == []

    def test_no_lesson_file_when_nothing_to_report(self, tmp_path: Path) -> None:
        # cross_project rule 만 있고 anti_patterns / domain_specific 없으면 lesson 파일 X.
        s = _session(_category(rules=[_rule(scope="cross_project")]))
        summary = export_session(s, tmp_path)
        assert summary.lesson_candidates_path is None
        assert not (tmp_path / "shared-lessons-candidates.md").exists()


class TestExportSummaryCounts:
    def test_scope_counts(self, tmp_path: Path) -> None:
        s = _session(_category(rules=[
            _rule("a", scope="cross_project"),
            _rule("b", scope="cross_project"),
            _rule("c", scope="framework_internal"),
            _rule("d", scope="domain_specific"),
        ]))
        summary = export_session(s, tmp_path)
        assert summary.cross_project_count == 2
        assert summary.framework_internal_count == 1
        assert summary.domain_specific_count == 1

    def test_anti_pattern_count(self, tmp_path: Path) -> None:
        s = _session(
            _category("architecture", anti_patterns=[
                {"pattern": "ap1", "reason": "r", "alternative": "a"},
                {"pattern": "ap2", "reason": "r", "alternative": "a"},
            ]),
            _category("coding_style", anti_patterns=[
                {"pattern": "ap3", "reason": "r", "alternative": "a"},
            ]),
        )
        summary = export_session(s, tmp_path)
        assert summary.anti_pattern_count == 3


class TestConventionsContent:
    def test_authority_order_section(self, tmp_path: Path) -> None:
        summary = export_session(_session(), tmp_path)
        body = summary.conventions_path.read_text(encoding="utf-8")
        assert "## 권위 순서" in body
        assert "conventions.md" in body
        assert "guidelines" in body

    def test_scope_distribution_section(self, tmp_path: Path) -> None:
        s = _session(_category(rules=[
            _rule("a", scope="cross_project"),
            _rule("b", scope="framework_internal"),
        ]))
        summary = export_session(s, tmp_path)
        body = summary.conventions_path.read_text(encoding="utf-8")
        assert "## Scope 분포" in body

    def test_index_lists_generated_files(self, tmp_path: Path) -> None:
        s = _session(_category("architecture", rules=[
            _rule("backend rule", layer="backend", scope="cross_project"),
        ]))
        summary = export_session(s, tmp_path)
        body = summary.conventions_path.read_text(encoding="utf-8")
        assert "guidelines/backend/structure.md" in body


# ---------------------------------------------------------------------------
# CLI 통합
# ---------------------------------------------------------------------------

class TestCliHarnessExport:
    def test_command_runs_and_writes_files(self, tmp_path: Path) -> None:
        # 미리 session.json 작성
        session = _session(_category(rules=[
            _rule("cli test rule", layer="backend", scope="cross_project"),
        ]))
        session_dir = tmp_path / "raw"
        session_dir.mkdir()
        (session_dir / "session.json").write_text(
            __import__("json").dumps(session.to_json(), ensure_ascii=False),
            encoding="utf-8",
        )

        output_dir = tmp_path / "harness-out"
        runner = CliRunner()
        res = runner.invoke(
            cli,
            ["harness-export", str(session_dir), "--output", str(output_dir)],
        )
        assert res.exit_code == 0, res.output
        assert (output_dir / "conventions.md").exists()
        assert (output_dir / "guidelines" / "backend" / "structure.md").exists()
        assert "cli test rule" in (
            output_dir / "guidelines" / "backend" / "structure.md"
        ).read_text(encoding="utf-8")

    def test_command_fails_on_missing_session(self, tmp_path: Path) -> None:
        runner = CliRunner()
        res = runner.invoke(
            cli,
            ["harness-export", str(tmp_path / "nope"), "--output", str(tmp_path / "out")],
        )
        assert res.exit_code != 0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_legacy_rule_without_scope_treated_as_cross_project(self, tmp_path: Path) -> None:
        # Backward compat: 기존 session.json 의 scope 누락 rule 도 cross_project 로 처리.
        rule = _rule("legacy")
        rule.scope = ""  # 빈 문자열 — None 또는 missing 케이스
        s = _session(_category(rules=[rule]))
        summary = export_session(s, tmp_path)
        assert summary.cross_project_count == 1
        target = tmp_path / "guidelines" / "backend" / "structure.md"
        assert target.exists()

    def test_unknown_category_skipped(self, tmp_path: Path) -> None:
        # 카테고리 매핑에 없는 항목은 guidelines 에서 건너뛰고 conventions 에는 들어가지 않음.
        s = _session(_category("unknown_category", rules=[
            _rule("orphan", layer="backend", scope="cross_project"),
        ]))
        summary = export_session(s, tmp_path)
        assert summary.guideline_paths == []

    def test_multiple_categories_per_layer(self, tmp_path: Path) -> None:
        s = _session(
            _category("architecture", rules=[_rule("arch1", layer="backend")]),
            _category("api_design", rules=[_rule("api1", layer="backend")]),
        )
        summary = export_session(s, tmp_path)
        files = {p.name for p in summary.guideline_paths}
        assert "structure.md" in files
        assert "api.md" in files
