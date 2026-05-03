from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from hijack.core.analyzer import run_full_analysis
from hijack.core.fetcher import detect_layer, fetch_source
from hijack.core.generator import write_output

_FIXTURE_REPO = Path(__file__).parent / "fixtures" / "senior_wisdom" / "repo"


# ---------------------------------------------------------------------------
# Ground truth: 5 layer detection cases
# ---------------------------------------------------------------------------

class TestGroundTruthLayerDetection:
    """ground_truth.md 에 정의된 5개 파일의 레이어를 검증한다."""

    def _layer(self, rel: str) -> str:
        abs_path = _FIXTURE_REPO / rel
        return detect_layer(abs_path, _FIXTURE_REPO, set(), set())

    def test_rule1_tsx_is_frontend(self) -> None:
        assert self._layer("frontend/App.tsx") == "frontend"

    def test_rule2_ts_in_frontend_dir_is_frontend(self) -> None:
        assert self._layer("frontend/hooks/useAuth.ts") == "frontend"

    def test_rule3_backend_routes_py_is_backend(self) -> None:
        assert self._layer("backend/routes/users.py") == "backend"

    def test_rule4_migrations_py_is_db(self) -> None:
        assert self._layer("migrations/001_init.py") == "db"

    def test_rule5_utils_helpers_py_is_shared(self) -> None:
        assert self._layer("utils/helpers.py") == "shared"


# ---------------------------------------------------------------------------
# fetch_source integration
# ---------------------------------------------------------------------------

class TestFetchSourceIntegration:
    def test_fetches_all_fixture_files(self) -> None:
        files, repo_root = fetch_source(str(_FIXTURE_REPO))
        assert repo_root == _FIXTURE_REPO
        assert len(files) == 5

    def test_layers_match_ground_truth(self) -> None:
        files, _ = fetch_source(str(_FIXTURE_REPO))
        by_path = {f.path.as_posix(): f.layer for f in files}

        assert by_path["frontend/App.tsx"] == "frontend"
        assert by_path["frontend/hooks/useAuth.ts"] == "frontend"
        assert by_path["backend/routes/users.py"] == "backend"
        assert by_path["migrations/001_init.py"] == "db"
        assert by_path["utils/helpers.py"] == "shared"

    def test_all_files_have_valid_roles(self) -> None:
        valid_roles = {"entry_point", "model", "api", "test", "service", "other"}
        files, _ = fetch_source(str(_FIXTURE_REPO))
        for f in files:
            assert f.role in valid_roles, f"Unexpected role {f.role!r} for {f.path}"


# ---------------------------------------------------------------------------
# Full pipeline integration (mock LLM)
# ---------------------------------------------------------------------------

def _make_llm_response(layer: str = "backend") -> str:
    return json.dumps({
        "design_intent": "Senior developer patterns",
        "rules": [
            {
                "rule": "Always use type hints",
                "priority": "MUST",
                "confidence": "high",
                "ref_files": ["backend/routes/users.py"],
                "good_example": "def f(x: int) -> str: ...",
                "bad_example": "def f(x): ...",
                "reason": "Readability and tooling support",
                "layer": layer,
            }
        ],
        "anti_patterns": [{
            "pattern": "bare except",
            "reason": "swallows errors",
            "alternative": "except Exception as e",
        }],
        "file_type_guides": {"route": "Always annotate request/response types"},
        "checklist": ["Type hints present", "Error handling explicit"],
    })


@pytest.mark.asyncio
async def test_full_pipeline_with_fixture(tmp_path: Path) -> None:
    """픽스처 레포로 전체 파이프라인(fetch→analyze→generate)을 실행한다."""
    files, repo_root = fetch_source(str(_FIXTURE_REPO))

    llm = AsyncMock()
    llm.analyze = AsyncMock(return_value=_make_llm_response("backend"))

    result = await run_full_analysis(
        files,
        repo_root,
        categories=["architecture"],
        llm=llm,
        target=str(_FIXTURE_REPO),
    )

    assert result.session_id.endswith("_repo")
    assert len(result.categories) == 1
    cat = result.categories[0]
    assert cat.error is None
    assert len(cat.rules) == 1
    assert cat.rules[0].layer == "backend"
    assert "backend/routes/users.py" in result.selected_files

    write_output(result, tmp_path)

    assert (tmp_path / result.session_id / "meta.md").exists()
    assert (tmp_path / result.session_id / "architecture.md").exists()
    assert (tmp_path / result.session_id / "session.json").exists()
    assert (tmp_path / "integrated" / "CLAUDE.md").exists()
    assert (tmp_path / "integrated" / "backend.md").exists()
    assert (tmp_path / "integrated" / "system-prompt.md").exists()

    backend_md = (tmp_path / "integrated" / "backend.md").read_text(encoding="utf-8")
    assert "Always use type hints" in backend_md


# ---------------------------------------------------------------------------
# Archaeology integration — verifies git history flows into prompts
# ---------------------------------------------------------------------------

class TestArchaeologyIntegration:
    """Phase A: fetch_source attaches history; preprocessor renders it."""

    def test_history_attached_to_files_with_commits(
        self, senior_wisdom_with_git: Path
    ) -> None:
        files, _ = fetch_source(str(senior_wisdom_with_git))
        by_path = {f.path.as_posix(): f for f in files}

        # Every file got at least the scaffold commit.
        for f in files:
            assert f.history is not None
            assert len(f.history.commits) >= 1, f"no history for {f.path}"

        # The churned file has multiple commits, newest first.
        churned = by_path["backend/routes/users.py"]
        assert len(churned.history.commits) >= 3
        assert churned.history.commits[0].subject.startswith("fix: settle")

    def test_revert_detected_for_churned_file(
        self, senior_wisdom_with_git: Path
    ) -> None:
        files, _ = fetch_source(str(senior_wisdom_with_git))
        by_path = {f.path.as_posix(): f for f in files}

        churned = by_path["backend/routes/users.py"]
        assert len(churned.history.reverts) == 1
        assert "drop pydantic" in churned.history.reverts[0].subject

        # A file without revert noise should report no reverts.
        clean = by_path["frontend/App.tsx"]
        assert clean.history.reverts == []

    def test_history_block_appears_in_prompt_summary(
        self, senior_wisdom_with_git: Path
    ) -> None:
        from hijack.core.preprocessor import build_file_summary_for_llm

        files, _ = fetch_source(str(senior_wisdom_with_git))
        churned = next(f for f in files if f.path.as_posix() == "backend/routes/users.py")
        summary = build_file_summary_for_llm([churned])[0]

        assert "<history>" in summary
        assert "Revert" in summary or "drop pydantic" in summary

    def test_attach_history_false_skips_git(
        self, senior_wisdom_with_git: Path
    ) -> None:
        files, _ = fetch_source(str(senior_wisdom_with_git), attach_history=False)
        # All histories should be None when explicitly disabled.
        assert all(f.history is None for f in files)


@pytest.mark.asyncio
async def test_layer_distribution_in_output(tmp_path: Path) -> None:
    """레이어별 파일이 올바른 integrated/*.md에 배치되는지 검증한다."""
    files, repo_root = fetch_source(str(_FIXTURE_REPO))

    def make_response(layer: str) -> str:
        return _make_llm_response(layer)

    llm = AsyncMock()
    llm.analyze = AsyncMock(side_effect=[
        make_response("frontend"),
        make_response("db"),
        make_response("shared"),
    ])

    result = await run_full_analysis(
        files,
        repo_root,
        categories=["architecture", "coding_style", "api_design"],
        llm=llm,
        target=str(_FIXTURE_REPO),
    )

    write_output(result, tmp_path)

    frontend_md = (tmp_path / "integrated" / "frontend.md").read_text(encoding="utf-8")
    db_md = (tmp_path / "integrated" / "database.md").read_text(encoding="utf-8")
    shared_md = (tmp_path / "integrated" / "shared.md").read_text(encoding="utf-8")

    assert "Always use type hints" in frontend_md
    assert "Always use type hints" in db_md
    assert "Always use type hints" in shared_md
