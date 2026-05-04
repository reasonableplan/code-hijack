from __future__ import annotations

import json
from pathlib import Path

from hijack.core.exemplars import Exemplar
from hijack.core.generator import (
    render_category_md,
    render_claude_md_entrypoint,
    render_layer_md,
    render_meta_md,
    render_system_prompt_md,
    write_output,
)
from hijack.core.models import AnalysisRule, CategoryResult, Evidence, SessionResult

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _rule(layer: str = "backend", priority: str = "MUST") -> AnalysisRule:
    return AnalysisRule(
        rule="Use type hints",
        priority=priority,
        confidence="high",
        ref_files=["main.py"],
        good_example="def f(x: int) -> str: ...",
        bad_example="def f(x): ...",
        reason="readability",
        layer=layer,
    )


def _category(name: str = "architecture", layer: str = "backend") -> CategoryResult:
    return CategoryResult(
        category=name,
        design_intent="Clean separation of concerns",
        rules=[_rule(layer=layer)],
        anti_patterns=[{"pattern": "global state", "reason": "bad", "alternative": "inject"}],
        file_type_guides={"model": "keep fields typed"},
        checklist=["check imports"],
        raw_llm_output='{"design_intent": "...", "rules": []}',
    )


def _session(target: str = "https://github.com/org/repo") -> SessionResult:
    return SessionResult(
        session_id="2026-04-17_repo",
        target=target,
        model="claude-sonnet-4-6",
        timestamp="2026-04-17T00:00:00+00:00",
        selected_files=["main.py", "service.py"],
        categories=[
            _category("architecture", layer="backend"),
            _category("coding_style", layer="shared"),
        ],
        analysis_duration_seconds=3.5,
        project_structure="repo/\n  main.py\n  service.py",
    )


# ---------------------------------------------------------------------------
# render_meta_md
# ---------------------------------------------------------------------------

class TestRenderMetaMd:
    def test_contains_session_id(self) -> None:
        md = render_meta_md(_session())
        assert "2026-04-17_repo" in md

    def test_contains_selected_files(self) -> None:
        md = render_meta_md(_session())
        assert "main.py" in md
        assert "service.py" in md

    def test_contains_project_structure(self) -> None:
        md = render_meta_md(_session())
        assert "repo/" in md

    def test_failed_category_shown(self) -> None:
        s = _session()
        s.categories[0].error = "LLM_002: timeout"
        md = render_meta_md(s)
        assert "LLM_002" in md

    def test_evidence_coverage_section_appears(self) -> None:
        # Default fixture rules use reason="readability" → classified as 'other'.
        # The metrics section should still render because there are rules.
        md = render_meta_md(_session())
        assert "## Evidence Coverage" in md
        assert "**Total rules**: 2" in md

    def test_evidence_coverage_section_omitted_when_no_rules(self) -> None:
        s = _session()
        for cat in s.categories:
            cat.rules = []
        md = render_meta_md(s)
        assert "## Evidence Coverage" not in md


# ---------------------------------------------------------------------------
# Evidence chain rendering (Phase D1)
# ---------------------------------------------------------------------------

def _ev(**kwargs) -> Evidence:
    defaults = dict(
        kind="commit",
        ref="a1b2c3d",
        headline="fix: drop pydantic",
        quote="Causes runtime regressions in async paths.",
        intent_kind="rejection",
        date="2024-08-12 14:30:00 +0900",
    )
    defaults.update(kwargs)
    return Evidence(**defaults)


class TestEvidenceChainRendering:
    def test_evidence_section_omitted_when_empty(self) -> None:
        rule = _rule()
        rule.evidence = []
        md = render_category_md(_category())
        # Default fixture has no evidence — section header must not appear.
        assert "**Evidence**:" not in md

    def test_evidence_chain_renders_label_ref_date_headline_quote(self) -> None:
        rule = _rule()
        rule.evidence = [_ev()]
        cat = _category()
        cat.rules = [rule]
        md = render_category_md(cat)

        assert "**Evidence**:" in md
        assert "[REJECTION]" in md           # intent label, not emoji
        assert "COMMIT" in md                # kind label
        assert "`a1b2c3d`" in md             # ref
        assert "(2024-08-12)" in md          # date trimmed
        assert "fix: drop pydantic" in md    # headline
        # Quote rendered as a markdown blockquote.
        assert "> Causes runtime regressions in async paths." in md

    def test_evidence_sorted_chronologically(self) -> None:
        rule = _rule()
        rule.evidence = [
            _ev(date="2024-08-12 14:30:00", headline="newer"),
            _ev(date="2023-01-01 09:00:00", headline="older"),
            _ev(date="2024-02-15 12:00:00", headline="middle"),
        ]
        cat = _category()
        cat.rules = [rule]
        md = render_category_md(cat)

        older_idx = md.index("older")
        middle_idx = md.index("middle")
        newer_idx = md.index("newer")
        assert older_idx < middle_idx < newer_idx

    def test_undated_evidence_falls_to_bottom_by_kind_strength(self) -> None:
        rule = _rule()
        # Three undated entries: revert > doc > commit by _KIND_PRIORITY.
        rule.evidence = [
            _ev(kind="commit", date=None, headline="commit-undated"),
            _ev(kind="doc", date=None, ref="README.md", headline="doc-undated"),
            _ev(kind="revert", date=None, headline="revert-undated"),
        ]
        cat = _category()
        cat.rules = [rule]
        md = render_category_md(cat)

        revert_idx = md.index("revert-undated")
        doc_idx = md.index("doc-undated")
        commit_idx = md.index("commit-undated")
        assert revert_idx < doc_idx < commit_idx

    def test_kind_label_used_when_intent_kind_missing(self) -> None:
        rule = _rule()
        rule.evidence = [_ev(intent_kind=None)]
        cat = _category()
        cat.rules = [rule]
        md = render_category_md(cat)
        # Without intent_kind, header tag falls back to the kind label.
        assert "[COMMIT]" in md


class TestBecauseLineInSystemPrompt:
    def test_because_line_appears_when_evidence_present(self) -> None:
        rule = _rule()
        rule.evidence = [_ev(quote="async-path runtime regression")]
        s = _session()
        s.categories[0].rules = [rule]
        md = render_system_prompt_md(s)
        assert "because: 'async-path runtime regression'" in md
        assert "[REJECTION]" in md

    def test_because_line_omitted_when_no_evidence(self) -> None:
        rule = _rule()
        rule.evidence = []
        s = _session()
        s.categories[0].rules = [rule]
        md = render_system_prompt_md(s)
        assert "because:" not in md

    def test_because_line_picks_strongest_evidence(self) -> None:
        rule = _rule()
        rule.evidence = [
            _ev(kind="commit", quote="weakest"),
            _ev(kind="revert", quote="strongest"),
            _ev(kind="doc", ref="README.md", quote="middle"),
        ]
        s = _session()
        s.categories[0].rules = [rule]
        md = render_system_prompt_md(s)
        assert "'strongest'" in md
        assert "'weakest'" not in md
        assert "'middle'" not in md

    def test_because_line_truncates_long_quote(self) -> None:
        rule = _rule()
        rule.evidence = [_ev(quote="x" * 500)]
        s = _session()
        s.categories[0].rules = [rule]
        md = render_system_prompt_md(s)
        # The because line caps at ~100 chars + ellipsis.
        because_lines = [line for line in md.splitlines() if "because:" in line]
        assert because_lines, "no because line emitted"
        assert any("…" in line for line in because_lines)
        assert "x" * 200 not in md  # full 500-char quote should not survive

    def test_because_line_drops_sha_for_consumer_brevity(self) -> None:
        rule = _rule()
        rule.evidence = [_ev(quote="reasoning text")]
        s = _session()
        s.categories[0].rules = [rule]
        md = render_system_prompt_md(s)
        because_line = next(line for line in md.splitlines() if "because:" in line)
        # SHA should not appear on the because line — consumer agents can't
        # follow it; it's pure noise.
        assert "a1b2c3d" not in because_line


# ---------------------------------------------------------------------------
# render_category_md
# ---------------------------------------------------------------------------

class TestRenderCategoryMd:
    def test_normal_category(self) -> None:
        md = render_category_md(_category())
        assert "Use type hints" in md
        assert "MUST" in md
        assert "def f(x: int)" in md  # good_example
        assert "global state" in md   # anti_pattern

    def test_error_category_shows_error(self) -> None:
        cat = _category()
        cat.error = "LLM_003: parse failed"
        cat.raw_llm_output = "raw output here"
        md = render_category_md(cat)
        assert "LLM_003" in md
        assert "raw output here" in md

    def test_checklist_present(self) -> None:
        md = render_category_md(_category())
        assert "check imports" in md


# ---------------------------------------------------------------------------
# render_layer_md
# ---------------------------------------------------------------------------

class TestRenderLayerMd:
    def test_backend_rules_shown(self) -> None:
        cats = [_category("architecture", layer="backend")]
        md = render_layer_md("backend", cats)
        assert "Use type hints" in md
        assert "backend" in md.lower()

    def test_empty_layer_shows_placeholder(self) -> None:
        cats = [_category("architecture", layer="backend")]
        md = render_layer_md("frontend", cats)
        assert "No rules tagged" in md

    def test_rule_count_in_header(self) -> None:
        cats = [
            _category("architecture", layer="shared"),
            _category("coding_style", layer="shared"),
        ]
        md = render_layer_md("shared", cats)
        assert "2" in md  # rule count appears in header


# ---------------------------------------------------------------------------
# render_claude_md_entrypoint
# ---------------------------------------------------------------------------

class TestRenderClaudeMdEntrypoint:
    def test_contains_layer_guide(self) -> None:
        md = render_claude_md_entrypoint(_session())
        assert "frontend" in md
        assert "backend" in md
        assert "shared" in md

    def test_contains_must_rules(self) -> None:
        md = render_claude_md_entrypoint(_session())
        assert "MUST" in md
        assert "Use type hints" in md

    def test_contains_target(self) -> None:
        md = render_claude_md_entrypoint(_session())
        assert "org/repo" in md


# ---------------------------------------------------------------------------
# render_system_prompt_md
# ---------------------------------------------------------------------------

class TestRenderSystemPromptMd:
    def test_must_rules_present(self) -> None:
        md = render_system_prompt_md(_session())
        assert "MUST Rules" in md
        assert "Use type hints" in md

    def test_anti_patterns_present(self) -> None:
        md = render_system_prompt_md(_session())
        assert "global state" in md


# ---------------------------------------------------------------------------
# write_output
# ---------------------------------------------------------------------------

class TestWriteOutput:
    def test_session_files_created(self, tmp_path: Path) -> None:
        s = _session()
        write_output(s, tmp_path)

        session_dir = tmp_path / "2026-04-17_repo"
        assert (session_dir / "meta.md").exists()
        assert (session_dir / "session.json").exists()
        assert (session_dir / "architecture.md").exists()
        assert (session_dir / "coding_style.md").exists()

    def test_integrated_files_created(self, tmp_path: Path) -> None:
        write_output(_session(), tmp_path)

        integrated = tmp_path / "integrated"
        assert (integrated / "CLAUDE.md").exists()
        assert (integrated / "system-prompt.md").exists()
        assert (integrated / "backend.md").exists()
        assert (integrated / "frontend.md").exists()
        assert (integrated / "database.md").exists()
        assert (integrated / "devops.md").exists()
        assert (integrated / "shared.md").exists()

    def test_session_json_parseable(self, tmp_path: Path) -> None:
        write_output(_session(), tmp_path)
        raw = (tmp_path / "2026-04-17_repo" / "session.json").read_text(encoding="utf-8")
        data = json.loads(raw)
        assert data["session_id"] == "2026-04-17_repo"
        assert len(data["categories"]) == 2

    def test_multiple_writes_do_not_error(self, tmp_path: Path) -> None:
        write_output(_session(), tmp_path)
        write_output(_session(), tmp_path)  # second write should not raise


# ---------------------------------------------------------------------------
# scope rendering (Q4)
# ---------------------------------------------------------------------------

def _rule_scoped(scope: str, priority: str = "MUST", layer: str = "backend") -> AnalysisRule:
    rule = _rule(layer=layer, priority=priority)
    rule.scope = scope
    return rule


class TestScopeRendering:
    def test_rule_renders_scope_field(self) -> None:
        cat = _category()
        cat.rules = [_rule_scoped("framework_internal")]
        md = render_category_md(cat)
        assert "**Scope**: `framework_internal`" in md

    def test_rule_renders_default_cross_project_scope(self) -> None:
        # Even without an explicit scope, the default (cross_project) is shown.
        cat = _category()
        md = render_category_md(cat)
        assert "**Scope**: `cross_project`" in md

    def test_system_prompt_omits_cross_project_tag(self) -> None:
        cat = _category()
        cat.rules = [_rule_scoped("cross_project")]
        s = _session()
        s.categories = [cat]
        md = render_system_prompt_md(s)
        # cross_project is the default tag — no visual noise.
        assert "[cross_project]" not in md

    def test_system_prompt_shows_non_default_scope_tag(self) -> None:
        cat = _category()
        cat.rules = [
            _rule_scoped("framework_internal"),
            _rule_scoped("domain_specific"),
        ]
        s = _session()
        s.categories = [cat]
        md = render_system_prompt_md(s)
        assert "[framework_internal]" in md
        assert "[domain_specific]" in md

    def test_meta_md_includes_scope_distribution(self) -> None:
        cat_a = _category(name="architecture")
        cat_a.rules = [_rule_scoped("cross_project"), _rule_scoped("cross_project")]
        cat_b = _category(name="api_design")
        cat_b.rules = [_rule_scoped("framework_internal")]
        s = _session()
        s.categories = [cat_a, cat_b]
        md = render_meta_md(s)
        assert "## Scope Distribution" in md
        assert "**cross_project**: 2" in md
        assert "**framework_internal**: 1" in md
        assert "**domain_specific**: 0" in md


# ---------------------------------------------------------------------------
# system-prompt ✅/❌/ref inline (Q3)
# ---------------------------------------------------------------------------

from hijack.core.generator import _signature_preview  # noqa: E402


class TestSignaturePreview:
    def test_returns_first_meaningful_line(self) -> None:
        code = "def foo(x: int) -> str:\n    return str(x)"
        assert _signature_preview(code) == "def foo(x: int) -> str:"

    def test_skips_blank_and_comment_lines(self) -> None:
        code = "\n# this is a comment\n\ndef bar(): pass"
        assert _signature_preview(code) == "def bar(): pass"

    def test_skips_docstring_opening(self) -> None:
        code = '"""module doc"""\nfrom x import y'
        assert _signature_preview(code) == "from x import y"

    def test_truncates_long_line(self) -> None:
        code = "x = " + ("a" * 200)
        out = _signature_preview(code, max_len=50)
        assert len(out) == 50
        assert out.endswith("…")

    def test_empty_input_returns_empty(self) -> None:
        assert _signature_preview("") == ""
        assert _signature_preview("\n\n#only comment\n") == ""


def _rule_with_examples(
    good: str = "def foo(*, x: int) -> str: ...",
    bad: str = "def foo(x): ...",
    ref: str = "src/main.py:10",
    layer: str = "backend",
    priority: str = "MUST",
) -> AnalysisRule:
    return AnalysisRule(
        rule="Use keyword-only params",
        priority=priority,
        confidence="high",
        ref_files=[ref] if ref else [],
        good_example=good,
        bad_example=bad,
        reason="explicit kw",
        layer=layer,
    )


class TestSystemPromptInlineExamples:
    def test_shows_good_bad_ref_lines(self) -> None:
        cat = _category()
        cat.rules = [_rule_with_examples()]
        s = _session()
        s.categories = [cat]
        md = render_system_prompt_md(s)
        assert "  ✅ def foo(*, x: int) -> str: ..." in md
        assert "  ❌ def foo(x): ..." in md
        assert "  ref: src/main.py:10" in md

    def test_omits_lines_when_examples_empty(self) -> None:
        cat = _category()
        cat.rules = [_rule_with_examples(good="", bad="", ref="")]
        s = _session()
        s.categories = [cat]
        md = render_system_prompt_md(s)
        assert "  ✅" not in md
        assert "  ❌" not in md
        assert "  ref:" not in md

    def test_keeps_rule_header_format(self) -> None:
        # The original "- [layer] rule" header format must be preserved.
        cat = _category()
        cat.rules = [_rule_with_examples(layer="frontend")]
        s = _session()
        s.categories = [cat]
        md = render_system_prompt_md(s)
        assert "- [frontend] Use keyword-only params" in md


# ---------------------------------------------------------------------------
# Exemplars wiring in generator (Phase G1)
# ---------------------------------------------------------------------------

def _exemplar_fixture(name: str = "process_user", layer: str = "backend") -> Exemplar:
    return Exemplar(
        file_path="backend/service.py",
        line_range=(1, 12),
        code="def process_user(user_id: int) -> dict:\n    ...",
        layer=layer,
        role="service",
        name=name,
        why_chosen="fully type-annotated, sweet-spot length",
    )


class TestExemplarsInGenerator:
    def test_write_output_creates_exemplars_md_when_present(self, tmp_path: Path) -> None:
        s = _session()
        s.exemplars = [_exemplar_fixture()]
        write_output(s, tmp_path)
        assert (tmp_path / "integrated" / "exemplars.md").exists()

    def test_write_output_no_exemplars_md_when_empty(self, tmp_path: Path) -> None:
        s = _session()
        s.exemplars = []
        write_output(s, tmp_path)
        assert not (tmp_path / "integrated" / "exemplars.md").exists()

    def test_claude_md_pointer_present_when_exemplars(self) -> None:
        s = _session()
        s.exemplars = [_exemplar_fixture()]
        md = render_claude_md_entrypoint(s)
        assert "exemplars.md" in md

    def test_claude_md_no_pointer_when_no_exemplars(self) -> None:
        s = _session()
        s.exemplars = []
        md = render_claude_md_entrypoint(s)
        assert "exemplars.md" not in md

    def test_system_prompt_pointer_present_when_exemplars(self) -> None:
        s = _session()
        s.exemplars = [_exemplar_fixture()]
        md = render_system_prompt_md(s)
        assert "exemplars.md" in md

    def test_system_prompt_no_pointer_when_no_exemplars(self) -> None:
        s = _session()
        s.exemplars = []
        md = render_system_prompt_md(s)
        assert "exemplars.md" not in md

    def test_exemplars_md_content_correct(self, tmp_path: Path) -> None:
        s = _session()
        s.exemplars = [_exemplar_fixture(name="my_func")]
        write_output(s, tmp_path)
        content = (tmp_path / "integrated" / "exemplars.md").read_text(encoding="utf-8")
        assert "my_func" in content
        assert "backend/service.py" in content
        assert "```python" in content
