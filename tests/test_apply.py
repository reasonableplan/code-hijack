from __future__ import annotations

from pathlib import Path

from hijack.core.apply import (
    AppliedRule,
    ApplyResult,
    _expand_target_deps,
    apply_session_to_target,
    classify_rule_against_stack,
    render_applied_md,
)
from hijack.core.exemplars import Exemplar
from hijack.core.models import AnalysisRule, CategoryResult, SessionResult
from hijack.core.target_stack import TargetStack

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rule(
    text: str = "Use type hints",
    scope: str = "cross_project",
    good_example: str = "",
    priority: str = "MUST",
) -> AnalysisRule:
    return AnalysisRule(
        rule=text,
        priority=priority,
        confidence="high",
        ref_files=[],
        good_example=good_example,
        bad_example="",
        reason="test reason",
        layer="backend",
        scope=scope,
    )


def _stack(
    repo_root: Path | None = None,
    python_deps: frozenset[str] = frozenset(),
    js_deps: frozenset[str] = frozenset(),
) -> TargetStack:
    return TargetStack(
        repo_root=repo_root or Path("/tmp/target"),
        python_deps=python_deps,
        js_deps=js_deps,
        detected_files=[],
    )


def _session(rules: list[AnalysisRule], target: str = "senior-repo") -> SessionResult:
    cat = CategoryResult(
        category="architecture",
        design_intent="clean",
        rules=rules,
        anti_patterns=[],
        file_type_guides={},
        checklist=[],
        raw_llm_output="",
    )
    return SessionResult(
        session_id="test-2026",
        target=target,
        model="claude-test",
        timestamp="2026-01-01T00:00:00",
        selected_files=[],
        categories=[cat],
        analysis_duration_seconds=1.0,
        project_structure="",
    )


# ---------------------------------------------------------------------------
# classify_rule_against_stack
# ---------------------------------------------------------------------------

class TestClassifyRuleAgainstStack:
    def test_cross_project_always_as_is(self) -> None:
        rule = _rule(scope="cross_project")
        stack = _stack()  # empty stack
        applied = classify_rule_against_stack(rule, stack)
        assert applied.verdict == "as_is"
        assert applied.adaptation_note == ""

    def test_cross_project_as_is_regardless_of_stack(self) -> None:
        rule = _rule(scope="cross_project")
        stack = _stack(python_deps=frozenset({"django"}))
        applied = classify_rule_against_stack(rule, stack)
        assert applied.verdict == "as_is"

    def test_domain_specific_always_domain_adapt(self) -> None:
        rule = _rule(scope="domain_specific")
        stack = _stack()
        applied = classify_rule_against_stack(rule, stack)
        assert applied.verdict == "domain_adapt"
        assert "adapt" in applied.adaptation_note.lower()

    def test_domain_specific_domain_adapt_regardless_of_stack(self) -> None:
        rule = _rule(scope="domain_specific")
        stack = _stack(python_deps=frozenset({"fastapi"}))
        applied = classify_rule_against_stack(rule, stack)
        assert applied.verdict == "domain_adapt"

    def test_framework_internal_same_framework_as_is(self) -> None:
        rule = _rule(
            scope="framework_internal",
            good_example="from fastapi import FastAPI\napp = FastAPI()",
        )
        stack = _stack(python_deps=frozenset({"fastapi"}))
        applied = classify_rule_against_stack(rule, stack)
        assert applied.verdict == "as_is"
        assert "fastapi" in applied.matched_packages

    def test_framework_internal_fastapi_rule_starlette_target_reference_only(self) -> None:
        # FastAPI is built ON Starlette, not the other way around.
        # A rule about FastAPI does not apply to a plain Starlette project.
        rule = _rule(
            scope="framework_internal",
            good_example="from fastapi import FastAPI",
        )
        # target uses starlette only — fastapi features not available
        stack = _stack(python_deps=frozenset({"starlette"}))
        applied = classify_rule_against_stack(rule, stack)
        assert applied.verdict == "reference_only"

    def test_framework_internal_starlette_rule_fastapi_target_as_is(self) -> None:
        # FastAPI is built on Starlette — the fastapi target's expanded deps
        # include starlette, so a starlette rule applies as-is to a fastapi project.
        rule = _rule(
            scope="framework_internal",
            good_example="from starlette.requests import Request",
        )
        stack = _stack(python_deps=frozenset({"fastapi"}))
        applied = classify_rule_against_stack(rule, stack)
        assert applied.verdict == "as_is"
        assert "starlette" in applied.matched_packages

    def test_framework_internal_incompatible_stack_reference_only(self) -> None:
        rule = _rule(
            scope="framework_internal",
            good_example="from fastapi import FastAPI",
        )
        stack = _stack(python_deps=frozenset({"flask"}))
        applied = classify_rule_against_stack(rule, stack)
        assert applied.verdict == "reference_only"
        assert "fastapi" in applied.adaptation_note or "flask" in applied.adaptation_note

    def test_framework_internal_empty_stack_reference_only(self) -> None:
        rule = _rule(
            scope="framework_internal",
            good_example="from fastapi import APIRouter",
        )
        stack = _stack()
        applied = classify_rule_against_stack(rule, stack)
        assert applied.verdict == "reference_only"

    def test_framework_internal_multiple_imports_any_match(self) -> None:
        # rule uses both fastapi and pydantic; target only has pydantic
        rule = _rule(
            scope="framework_internal",
            good_example=(
                "from fastapi import FastAPI\n"
                "from pydantic import BaseModel\n"
            ),
        )
        stack = _stack(python_deps=frozenset({"pydantic"}))
        applied = classify_rule_against_stack(rule, stack)
        assert applied.verdict == "as_is"

    def test_flask_quart_sibling(self) -> None:
        rule = _rule(
            scope="framework_internal",
            good_example="from flask import Flask",
        )
        stack = _stack(python_deps=frozenset({"quart"}))
        applied = classify_rule_against_stack(rule, stack)
        assert applied.verdict == "adapted"
        assert "quart" in applied.adaptation_note

    def test_js_deps_matched(self) -> None:
        rule = _rule(
            scope="framework_internal",
            good_example="from react import Component",
        )
        stack = _stack(js_deps=frozenset({"react"}))
        applied = classify_rule_against_stack(rule, stack)
        assert applied.verdict == "as_is"

    def test_drf_rule_django_target_reference_only(self) -> None:
        # DRF is built ON Django, not the other way.
        # A rule about DRF does not apply to a plain Django project.
        rule = _rule(
            scope="framework_internal",
            good_example="from rest_framework.views import APIView",
        )
        stack = _stack(python_deps=frozenset({"django"}))
        applied = classify_rule_against_stack(rule, stack)
        assert applied.verdict == "reference_only"

    def test_django_rule_drf_target_as_is(self) -> None:
        # DRF target's expanded deps include django, so a django rule applies as-is.
        rule = _rule(
            scope="framework_internal",
            good_example="from django.db import models",
        )
        stack = _stack(python_deps=frozenset({"djangorestframework"}))
        applied = classify_rule_against_stack(rule, stack)
        assert applied.verdict == "as_is"
        assert "django" in applied.matched_packages

    def test_flask_rule_quart_target_adapted(self) -> None:
        # flask ↔ quart are genuine siblings (sync vs async Flask API)
        rule = _rule(
            scope="framework_internal",
            good_example="from flask import Flask",
        )
        stack = _stack(python_deps=frozenset({"quart"}))
        applied = classify_rule_against_stack(rule, stack)
        assert applied.verdict == "adapted"
        assert "quart" in applied.adaptation_note

    def test_quart_rule_flask_target_adapted(self) -> None:
        # Sibling relationship is symmetric — quart rule adapts to flask too.
        rule = _rule(
            scope="framework_internal",
            good_example="from quart import Quart",
        )
        stack = _stack(python_deps=frozenset({"flask"}))
        applied = classify_rule_against_stack(rule, stack)
        assert applied.verdict == "adapted"
        assert "flask" in applied.adaptation_note


# ---------------------------------------------------------------------------
# _expand_target_deps
# ---------------------------------------------------------------------------

class TestExpandTargetDeps:
    def test_fastapi_expands_to_include_starlette(self) -> None:
        result = _expand_target_deps(frozenset({"fastapi"}))
        assert result == frozenset({"fastapi", "starlette"})

    def test_drf_expands_to_include_django(self) -> None:
        result = _expand_target_deps(frozenset({"djangorestframework", "sqlalchemy"}))
        assert result == frozenset({"djangorestframework", "django", "sqlalchemy"})

    def test_plain_pkg_unchanged(self) -> None:
        result = _expand_target_deps(frozenset({"flask", "sqlalchemy"}))
        assert result == frozenset({"flask", "sqlalchemy"})

    def test_empty_set_unchanged(self) -> None:
        result = _expand_target_deps(frozenset())
        assert result == frozenset()


# ---------------------------------------------------------------------------
# apply_session_to_target
# ---------------------------------------------------------------------------

class TestApplySessionToTarget:
    def test_mixed_scope_correct_bucketing(self, tmp_path: Path) -> None:
        rules = [
            _rule("R1", scope="cross_project"),
            _rule("R2", scope="domain_specific"),
            _rule(
                "R3",
                scope="framework_internal",
                good_example="from fastapi import FastAPI",
            ),
        ]
        # target has fastapi
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname="t"\nversion="0.1"\ndependencies = ["fastapi"]',
            encoding="utf-8",
        )
        result = apply_session_to_target(_session(rules), tmp_path)
        as_is = result.by_verdict["as_is"]
        domain = result.by_verdict["domain_adapt"]
        assert len(as_is) == 2  # R1 (cross_project) + R3 (framework_internal, same stack)
        assert len(domain) == 1
        assert result.total_input_rules == 3

    def test_strict_drops_reference_only(self, tmp_path: Path) -> None:
        rules = [
            _rule("R1", scope="cross_project"),
            _rule(
                "R2",
                scope="framework_internal",
                good_example="from fastapi import FastAPI",
            ),
        ]
        # empty target — R2 will be reference_only
        result = apply_session_to_target(_session(rules), tmp_path, strict=True)
        assert result.by_verdict["reference_only"] == []
        assert result.total_input_rules == 2

    def test_strict_false_keeps_reference_only(self, tmp_path: Path) -> None:
        rules = [
            _rule(
                "R2",
                scope="framework_internal",
                good_example="from fastapi import FastAPI",
            ),
        ]
        result = apply_session_to_target(_session(rules), tmp_path, strict=False)
        assert len(result.by_verdict["reference_only"]) == 1

    def test_empty_session_zero_rules(self, tmp_path: Path) -> None:
        result = apply_session_to_target(_session([]), tmp_path)
        assert result.total_input_rules == 0
        assert all(len(v) == 0 for v in result.by_verdict.values())
        assert "0" in result.summary

    def test_summary_mentions_counts(self, tmp_path: Path) -> None:
        rules = [_rule("R1", scope="cross_project")]
        result = apply_session_to_target(_session(rules), tmp_path)
        # summary should have some numeric info
        assert any(c.isdigit() for c in result.summary)

    def test_prebuilt_target_stack_overrides_detection(self, tmp_path: Path) -> None:
        # tmp_path has no pyproject.toml, but we pass in a pre-built stack with fastapi
        rules = [
            _rule(
                "R1",
                scope="framework_internal",
                good_example="from fastapi import FastAPI",
            )
        ]
        prebuilt = TargetStack(
            repo_root=tmp_path,
            python_deps=frozenset({"fastapi"}),
            js_deps=frozenset(),
            detected_files=["<--stack override>"],
        )
        result = apply_session_to_target(_session(rules), tmp_path, target_stack=prebuilt)
        # Rule should be as_is because we provided fastapi in the override stack
        assert len(result.by_verdict["as_is"]) == 1
        assert result.target_stack is prebuilt


# ---------------------------------------------------------------------------
# render_applied_md
# ---------------------------------------------------------------------------

class TestRenderAppliedMd:
    def _make_result(
        self,
        tmp_path: Path,
        universal: int = 0,
        stack_specific: int = 0,
        adapted_count: int = 0,
        domain: int = 0,
        reference: int = 0,
    ) -> ApplyResult:
        stack = TargetStack(
            repo_root=tmp_path,
            python_deps=frozenset({"fastapi"}) if stack_specific or adapted_count else frozenset(),
            js_deps=frozenset(),
            detected_files=["pyproject.toml"] if stack_specific else [],
        )
        as_is_rules: list[AppliedRule] = []
        for i in range(universal):
            as_is_rules.append(AppliedRule(
                rule=_rule(f"UniversalRule{i}", scope="cross_project"),
                verdict="as_is",
                adaptation_note="",
                matched_packages=frozenset(),
            ))
        for i in range(stack_specific):
            as_is_rules.append(AppliedRule(
                rule=_rule(f"StackRule{i}", scope="framework_internal"),
                verdict="as_is",
                adaptation_note="",
                matched_packages=frozenset({"fastapi"}),
            ))
        adapted_rules = [
            AppliedRule(
                rule=_rule(f"AdaptedRule{i}", scope="framework_internal"),
                verdict="adapted",
                adaptation_note="Senior repo uses starlette; translate to your fastapi equivalent.",
                matched_packages=frozenset({"starlette"}),
            )
            for i in range(adapted_count)
        ]
        domain_rules = [
            AppliedRule(
                rule=_rule(f"DomainRule{i}", scope="domain_specific"),
                verdict="domain_adapt",
                adaptation_note="Domain-bound — adapt literal values/identifiers to your domain.",
                matched_packages=frozenset(),
            )
            for i in range(domain)
        ]
        ref_rules = [
            AppliedRule(
                rule=_rule(f"RefRule{i}", scope="framework_internal"),
                verdict="reference_only",
                adaptation_note="For reference only.",
                matched_packages=frozenset(),
            )
            for i in range(reference)
        ]
        return ApplyResult(
            target_stack=stack,
            by_verdict={
                "as_is": as_is_rules,
                "adapted": adapted_rules,
                "domain_adapt": domain_rules,
                "reference_only": ref_rules,
            },
            total_input_rules=universal + stack_specific + adapted_count + domain + reference,
            summary="Test summary.",
        )

    def test_header_contains_source_target(self, tmp_path: Path) -> None:
        result = self._make_result(tmp_path, universal=1)
        md = render_applied_md(result, source_target="my-senior-repo")
        assert "my-senior-repo" in md

    def test_all_sections_render_when_populated(self, tmp_path: Path) -> None:
        result = self._make_result(
            tmp_path, universal=1, stack_specific=1, adapted_count=1, domain=1, reference=1
        )
        md = render_applied_md(result, source_target="senior")
        assert "Universal Rules" in md
        assert "Stack-Specific Rules" in md
        assert "Adapted Rules" in md
        assert "Domain Rules" in md
        assert "For Reference" in md

    def test_empty_section_omitted(self, tmp_path: Path) -> None:
        # Only universal — no domain, no reference, no adapted, no stack-specific
        result = self._make_result(tmp_path, universal=2)
        md = render_applied_md(result, source_target="senior")
        assert "Universal Rules" in md
        assert "Domain Rules" not in md
        assert "Adapted Rules" not in md
        assert "For Reference" not in md

    def test_adaptation_note_as_blockquote(self, tmp_path: Path) -> None:
        result = self._make_result(tmp_path, adapted_count=1)
        md = render_applied_md(result, source_target="senior")
        # Adaptation note should appear as blockquote
        assert "> Adaptation note:" in md

    def test_target_stack_shown_in_header(self, tmp_path: Path) -> None:
        result = self._make_result(tmp_path, stack_specific=1)
        md = render_applied_md(result, source_target="senior")
        # The target stack line should mention fastapi
        assert "fastapi" in md

    def test_empty_result_no_section_headers(self, tmp_path: Path) -> None:
        stack = TargetStack(repo_root=tmp_path)
        result = ApplyResult(
            target_stack=stack,
            by_verdict={"as_is": [], "adapted": [], "domain_adapt": [], "reference_only": []},
            total_input_rules=0,
            summary="Applied 0 rules.",
        )
        md = render_applied_md(result, source_target="senior")
        assert "Code Style" in md
        assert "Universal Rules" not in md
        assert "Domain Rules" not in md


# ---------------------------------------------------------------------------
# Exemplars pass-through in apply (Phase G1)
# ---------------------------------------------------------------------------

def _exemplar_for_apply(name: str = "process") -> Exemplar:
    return Exemplar(
        file_path="backend/service.py",
        line_range=(1, 12),
        code="def process(x: int) -> str:\n    return str(x)",
        layer="backend",
        role="service",
        name=name,
        why_chosen="fully type-annotated",
    )


class TestExemplarsInApply:
    def test_apply_session_carries_exemplars_to_result(self, tmp_path: Path) -> None:
        ex = _exemplar_for_apply("get_user")
        session = _session([])
        session.exemplars = [ex]
        result = apply_session_to_target(session, tmp_path)
        assert len(result.exemplars) == 1
        assert result.exemplars[0].name == "get_user"

    def test_apply_session_empty_exemplars_passthrough(self, tmp_path: Path) -> None:
        session = _session([])
        session.exemplars = []
        result = apply_session_to_target(session, tmp_path)
        assert result.exemplars == []

    def test_render_applied_md_includes_exemplar_section(self, tmp_path: Path) -> None:
        stack = TargetStack(repo_root=tmp_path)
        result = ApplyResult(
            target_stack=stack,
            by_verdict={"as_is": [], "adapted": [], "domain_adapt": [], "reference_only": []},
            total_input_rules=0,
            summary="Applied 0 rules.",
            exemplars=[_exemplar_for_apply("some_func")],
        )
        md = render_applied_md(result, source_target="senior-repo")
        assert "Senior Exemplars" in md
        assert "some_func" in md

    def test_render_applied_md_no_exemplar_section_when_empty(self, tmp_path: Path) -> None:
        stack = TargetStack(repo_root=tmp_path)
        result = ApplyResult(
            target_stack=stack,
            by_verdict={"as_is": [], "adapted": [], "domain_adapt": [], "reference_only": []},
            total_input_rules=0,
            summary="Applied 0 rules.",
            exemplars=[],
        )
        md = render_applied_md(result, source_target="senior-repo")
        assert "Senior Exemplars" not in md

    def test_render_applied_md_exemplar_code_in_fence(self, tmp_path: Path) -> None:
        stack = TargetStack(repo_root=tmp_path)
        result = ApplyResult(
            target_stack=stack,
            by_verdict={"as_is": [], "adapted": [], "domain_adapt": [], "reference_only": []},
            total_input_rules=0,
            summary="Applied 0 rules.",
            exemplars=[_exemplar_for_apply("my_handler")],
        )
        md = render_applied_md(result, source_target="senior-repo")
        assert "```python" in md
        assert "my_handler" in md
