"""tests/test_scope_critic.py — mechanical_scope + reclassify_session_scopes 테스트."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from hijack.core.critic import refine
from hijack.core.models import AnalysisRule, CategoryResult, SessionResult
from hijack.core.scope_critic import mechanical_scope, reclassify_session_scopes

# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------

def _rule(
    text: str,
    good_example: str = "",
    scope: str = "cross_project",
    priority: str = "MUST",
) -> AnalysisRule:
    return AnalysisRule(
        rule=text,
        priority=priority,
        confidence="high",
        ref_files=[],
        good_example=good_example,
        bad_example="",
        reason=text,
        layer="backend",
        scope=scope,
    )


def _category(name: str, rules: list[AnalysisRule]) -> CategoryResult:
    return CategoryResult(
        category=name,
        design_intent="",
        rules=rules,
        anti_patterns=[],
        file_type_guides={},
        checklist=[],
        raw_llm_output="",
    )


def _session(*categories: CategoryResult) -> SessionResult:
    return SessionResult(
        session_id="test-session",
        target="t",
        model="m",
        timestamp="2026-01-01T00:00:00+00:00",
        selected_files=[],
        categories=list(categories),
        analysis_duration_seconds=0.0,
        project_structure="",
    )


# ---------------------------------------------------------------------------
# mechanical_scope 단위 테스트
# ---------------------------------------------------------------------------

class TestMechanicalScope:
    def test_fastapi_import_is_framework_internal(self) -> None:
        rule = _rule(
            "use APIRouter",
            good_example="from fastapi.routing import APIRouter\n\nrouter = APIRouter()",
        )
        assert mechanical_scope(rule) == "framework_internal"

    def test_django_import_is_framework_internal(self) -> None:
        rule = _rule(
            "use django models",
            good_example="from django.db import models\n\nclass User(models.Model):\n    pass",
        )
        assert mechanical_scope(rule) == "framework_internal"

    def test_sqlalchemy_import_is_framework_internal(self) -> None:
        rule = _rule(
            "use sqlalchemy session",
            good_example="import sqlalchemy\nfrom sqlalchemy.orm import Session",
        )
        assert mechanical_scope(rule) == "framework_internal"

    def test_stdlib_only_is_cross_project(self) -> None:
        rule = _rule(
            "use dataclasses",
            good_example=(
                "from collections.abc import Mapping\n"
                "from typing import Any\n"
                "from dataclasses import dataclass\n\n"
                "@dataclass\nclass Config:\n    name: str"
            ),
        )
        assert mechanical_scope(rule) == "cross_project"

    def test_no_imports_short_snippet_is_none(self) -> None:
        rule = _rule(
            "use X | None syntax",
            good_example="def foo(x: int | None) -> str:\n    return str(x)",
        )
        assert mechanical_scope(rule) is None

    def test_mixed_framework_and_stdlib_framework_wins(self) -> None:
        rule = _rule(
            "type-safe fastapi",
            good_example=(
                "from typing import Any\n"
                "from fastapi import FastAPI\n\n"
                "app = FastAPI()\n"
            ),
        )
        assert mechanical_scope(rule) == "framework_internal"

    def test_domain_identifier_no_framework_is_domain_specific(self) -> None:
        rule = _rule(
            "issue priority",
            good_example=(
                "def close_issue(issue: Issue) -> None:\n"
                "    issue.priority = 0\n"
                "    issue.status = 'closed'\n"
            ),
        )
        assert mechanical_scope(rule) == "domain_specific"

    def test_domain_identifier_with_framework_is_framework_internal(self) -> None:
        # 프레임워크 import 가 있으면 domain_specific 이 아닌 framework_internal
        rule = _rule(
            "fastapi order endpoint",
            good_example=(
                "from fastapi import APIRouter\n\n"
                "router = APIRouter()\n\n"
                "@router.get('/orders/{id}')\n"
                "def get_order(order: Order) -> dict:\n"
                "    return {'id': order.id}\n"
            ),
        )
        assert mechanical_scope(rule) == "framework_internal"

    def test_empty_good_example_is_none(self) -> None:
        rule = _rule("some rule", good_example="")
        assert mechanical_scope(rule) is None

    def test_whitespace_only_good_example_is_none(self) -> None:
        rule = _rule("some rule", good_example="   \n\t  ")
        assert mechanical_scope(rule) is None

    def test_other_domain_identifiers(self) -> None:
        domain_idents = (
            "Order", "Customer", "Sprint", "BillingPeriod",
            "Tenant", "Invoice", "Subscription",
        )
        for ident in domain_idents:
            rule = _rule(
                "domain rule",
                good_example=f"def process(x: {ident}) -> None:\n    pass",
            )
            assert mechanical_scope(rule) == "domain_specific", f"failed for {ident}"

    def test_stdlib_typing_and_enum(self) -> None:
        rule = _rule(
            "use enum",
            good_example=(
                "import enum\nfrom typing import ClassVar\n\n"
                "class Color(enum.Enum):\n    RED = 1"
            ),
        )
        assert mechanical_scope(rule) == "cross_project"

    def test_unknown_package_no_domain_is_none(self) -> None:
        # 알 수 없는 서드파티 패키지 (signal 없음) → None
        rule = _rule(
            "use some lib",
            good_example="import some_obscure_library\n\nsome_obscure_library.do_thing()",
        )
        assert mechanical_scope(rule) is None


# ---------------------------------------------------------------------------
# reclassify_session_scopes 단위 테스트
# ---------------------------------------------------------------------------

class TestReclassifySessionScopes:
    def test_overrides_cross_project_to_framework_internal(self) -> None:
        rule = _rule(
            "use fastapi router",
            good_example="from fastapi import APIRouter\nrouter = APIRouter()",
            scope="cross_project",
        )
        session = _session(_category("api", [rule]))
        new_session, counts = reclassify_session_scopes(session)
        assert new_session.categories[0].rules[0].scope == "framework_internal"
        assert counts["cross_project_to_framework_internal"] == 1
        assert counts["cross_project_to_domain_specific"] == 0
        assert counts["unchanged"] == 0

    def test_overrides_cross_project_to_domain_specific(self) -> None:
        rule = _rule(
            "issue model",
            good_example="class Issue:\n    priority: int\n",
            scope="cross_project",
        )
        session = _session(_category("domain", [rule]))
        new_session, counts = reclassify_session_scopes(session)
        assert new_session.categories[0].rules[0].scope == "domain_specific"
        assert counts["cross_project_to_domain_specific"] == 1
        assert counts["unchanged"] == 0

    def test_does_not_override_framework_internal(self) -> None:
        # LLM 이 이미 framework_internal 로 태깅 → 건드리지 않음
        rule = _rule(
            "fastapi sub",
            good_example="from fastapi import FastAPI\napp = FastAPI()",
            scope="framework_internal",
        )
        session = _session(_category("fw", [rule]))
        new_session, counts = reclassify_session_scopes(session)
        assert new_session.categories[0].rules[0].scope == "framework_internal"
        assert counts["unchanged"] == 1
        assert counts["cross_project_to_framework_internal"] == 0

    def test_does_not_override_domain_specific(self) -> None:
        rule = _rule(
            "domain rule",
            good_example="def get_customer(c: Customer) -> str: return c.name",
            scope="domain_specific",
        )
        session = _session(_category("domain", [rule]))
        new_session, counts = reclassify_session_scopes(session)
        assert new_session.categories[0].rules[0].scope == "domain_specific"
        assert counts["unchanged"] == 1

    def test_no_override_when_no_signal(self) -> None:
        rule = _rule(
            "type hint rule",
            good_example="def foo(x: int | None) -> str:\n    return str(x)",
            scope="cross_project",
        )
        session = _session(_category("style", [rule]))
        new_session, counts = reclassify_session_scopes(session)
        assert new_session.categories[0].rules[0].scope == "cross_project"
        assert counts["unchanged"] == 1

    def test_change_counts_across_multiple_rules(self) -> None:
        rules = [
            _rule(
                "fw1",
                good_example="from flask import Flask\napp = Flask(__name__)",
                scope="cross_project",
            ),
            _rule(
                "fw2",
                good_example="from django.db import models\n",
                scope="cross_project",
            ),
            _rule(
                "domain1",
                good_example="class Sprint:\n    pass",
                scope="cross_project",
            ),
            _rule(
                "stdlib1",
                good_example="from dataclasses import dataclass\n",
                scope="cross_project",
            ),
            _rule(
                "already_fw",
                good_example="from starlette.responses import Response\n",
                scope="framework_internal",
            ),
        ]
        session = _session(_category("mixed", rules))
        _, counts = reclassify_session_scopes(session)
        assert counts["cross_project_to_framework_internal"] == 2
        assert counts["cross_project_to_domain_specific"] == 1
        # stdlib1 (cross_project → cross_project signal) + already_fw (not overridden)
        assert counts["unchanged"] == 2

    def test_original_session_not_mutated(self) -> None:
        rule = _rule(
            "fastapi rule",
            good_example="from fastapi import FastAPI\n",
            scope="cross_project",
        )
        session = _session(_category("api", [rule]))
        reclassify_session_scopes(session)
        # 원본 rule scope 는 변경되지 않아야 함
        assert session.categories[0].rules[0].scope == "cross_project"

    def test_all_fields_preserved_on_session(self) -> None:
        rule = _rule("r", scope="cross_project")
        session = SessionResult(
            session_id="abc",
            target="/tmp/repo",
            model="claude-3",
            timestamp="2026-01-01T00:00:00+00:00",
            selected_files=["a.py"],
            categories=[_category("c", [rule])],
            analysis_duration_seconds=1.5,
            project_structure="proj",
            files_by_layer={"backend": 3},
            historic_shas=["abc123", "def456"],
            repo_doc_paths=["docs/adr.md"],
        )
        new_session, _ = reclassify_session_scopes(session)
        assert new_session.session_id == "abc"
        assert new_session.historic_shas == ["abc123", "def456"]
        assert new_session.repo_doc_paths == ["docs/adr.md"]
        assert new_session.files_by_layer == {"backend": 3}


# ---------------------------------------------------------------------------
# critic.refine 회귀 테스트 — D1 필드 보존 (bugfix)
# ---------------------------------------------------------------------------

def _critic_response(keep: list[str], downgrade: list[str], drop: list[str]) -> str:
    return json.dumps({
        "keep": keep,
        "downgrade_to_should": downgrade,
        "drop": drop,
        "notes": "test",
    })


class TestRefinePreservesD1Fields:
    @pytest.mark.asyncio
    async def test_preserves_historic_shas(self) -> None:
        rule = _rule("some rule")
        session = SessionResult(
            session_id="s1",
            target="t",
            model="m",
            timestamp="2026-01-01T00:00:00+00:00",
            selected_files=[],
            categories=[_category("arch", [rule])],
            analysis_duration_seconds=0.0,
            project_structure="",
            historic_shas=["aabbccdd" * 8, "11223344" * 8],
            repo_doc_paths=["docs/adr/0001.md"],
        )
        llm = AsyncMock()
        llm.analyze = AsyncMock(return_value=_critic_response(
            keep=["some rule"], downgrade=[], drop=[]
        ))
        result = await refine(session, llm, model="m")
        assert result.historic_shas == session.historic_shas

    @pytest.mark.asyncio
    async def test_preserves_repo_doc_paths(self) -> None:
        rule = _rule("another rule")
        session = SessionResult(
            session_id="s2",
            target="t",
            model="m",
            timestamp="2026-01-01T00:00:00+00:00",
            selected_files=[],
            categories=[_category("arch", [rule])],
            analysis_duration_seconds=0.0,
            project_structure="",
            historic_shas=[],
            repo_doc_paths=["README.md", "docs/design.md"],
        )
        llm = AsyncMock()
        llm.analyze = AsyncMock(return_value=_critic_response(
            keep=["another rule"], downgrade=[], drop=[]
        ))
        result = await refine(session, llm, model="m")
        assert result.repo_doc_paths == ["README.md", "docs/design.md"]

    @pytest.mark.asyncio
    async def test_preserves_both_d1_fields_together(self) -> None:
        rule = _rule("rule x")
        shas = ["aabbcc" + "0" * 34, "ddeeff" + "1" * 34]
        doc_paths = ["docs/adr/0001.md", "ARCHITECTURE.md"]
        session = SessionResult(
            session_id="s3",
            target="t",
            model="m",
            timestamp="2026-01-01T00:00:00+00:00",
            selected_files=[],
            categories=[_category("arch", [rule])],
            analysis_duration_seconds=0.0,
            project_structure="",
            historic_shas=shas,
            repo_doc_paths=doc_paths,
        )
        llm = AsyncMock()
        llm.analyze = AsyncMock(return_value=_critic_response(
            keep=["rule x"], downgrade=[], drop=[]
        ))
        result = await refine(session, llm, model="m")
        assert result.historic_shas == shas
        assert result.repo_doc_paths == doc_paths
