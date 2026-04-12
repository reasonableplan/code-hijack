"""Tests for generator module."""

import tempfile
from pathlib import Path

from hijack.core.generator import generate_claude_md, generate_system_prompt, write_output
from hijack.core.models import AnalysisRule, CategoryResult, SessionResult


def _make_session() -> SessionResult:
    rules = [
        AnalysisRule(
            rule="Use APIRouter for routes",
            priority="MUST",
            ref_files=["routes/users.py"],
            good_example="router = APIRouter()",
            bad_example="@app.get('/')",
            reason="Separation of concerns",
        ),
        AnalysisRule(
            rule="Use type hints",
            priority="SHOULD",
            ref_files=["models/user.py"],
        ),
    ]
    cat = CategoryResult(
        category="architecture",
        design_intent="Clean layered architecture",
        rules=rules,
        checklist=["Check route registration", "Verify type hints"],
        raw_llm_output="## Architecture\n...",
    )
    return SessionResult(
        session_id="2026-04-12_test",
        target="https://github.com/test/repo",
        model="claude-sonnet-4-6",
        categories=[cat],
        selected_files=["main.py", "routes/users.py"],
    )


def test_generate_claude_md():
    session = _make_session()
    result = generate_claude_md(session)

    assert "MUST" in result
    assert "SHOULD" in result
    assert "APIRouter" in result
    assert "routes/users.py" in result
    assert "체크리스트" in result


def test_generate_system_prompt():
    session = _make_session()
    result = generate_system_prompt(session)

    assert "시니어 개발자" in result
    assert "architecture" in result
    assert "APIRouter" in result


def test_write_output():
    session = _make_session()
    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir) / "docs" / "hijacked"
        created = write_output(session, output_dir)

        assert len(created) > 0
        # Check session files exist
        assert (output_dir / "2026-04-12_test" / "meta.md").exists()
        assert (output_dir / "2026-04-12_test" / "architecture.md").exists()
        assert (output_dir / "2026-04-12_test" / "session.json").exists()
        # Check integrated files
        assert (output_dir / "integrated" / "CLAUDE.md").exists()
        assert (output_dir / "integrated" / "system-prompt.md").exists()
