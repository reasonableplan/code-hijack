"""Tests for hijack.llm.local — file-IPC LLM backend."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from hijack.errors import LLMError
from hijack.llm.local import LocalLLM


def test_analyze_returns_response_when_file_appears(tmp_path: Path) -> None:
    """Happy path: write the response file before calling, analyze returns it."""
    llm = LocalLLM(tmp_path, poll_interval=0.05, timeout_seconds=5)

    async def write_response_after_delay() -> None:
        # Wait a tick so analyze() starts polling first, mimicking the realistic
        # ordering: CLI writes prompt → agent reads → agent writes response.
        await asyncio.sleep(0.1)
        (tmp_path / "response_001.json").write_text(
            '{"design_intent": "x", "rules": []}', encoding="utf-8"
        )

    async def main() -> str:
        # Run both concurrently so analyze() actually has to wait.
        responder = asyncio.create_task(write_response_after_delay())
        result = await llm.analyze("test prompt")
        await responder
        return result

    result = asyncio.run(main())
    assert "design_intent" in result


def test_prompt_file_written_with_correct_content(tmp_path: Path) -> None:
    llm = LocalLLM(tmp_path, poll_interval=0.05, timeout_seconds=5)

    async def respond_immediately() -> None:
        await asyncio.sleep(0.05)
        (tmp_path / "response_001.json").write_text("{}", encoding="utf-8")

    async def main() -> None:
        responder = asyncio.create_task(respond_immediately())
        await llm.analyze("hello world\n특수문자 테스트")
        await responder

    asyncio.run(main())
    written = (tmp_path / "prompt_001.txt").read_text(encoding="utf-8")
    assert "hello world" in written
    assert "특수문자 테스트" in written


def test_round_counter_monotonic_across_calls(tmp_path: Path) -> None:
    """Each analyze() bumps the counter so the responder can disambiguate rounds."""
    llm = LocalLLM(tmp_path, poll_interval=0.05, timeout_seconds=5)

    async def respond(round_id: int) -> None:
        await asyncio.sleep(0.05)
        (tmp_path / f"response_{round_id:03d}.json").write_text("{}", encoding="utf-8")

    async def main() -> None:
        for i in range(1, 4):
            responder = asyncio.create_task(respond(i))
            await llm.analyze(f"round {i}")
            await responder

    asyncio.run(main())
    for i in range(1, 4):
        assert (tmp_path / f"prompt_{i:03d}.txt").exists()
        assert (tmp_path / f"response_{i:03d}.json").exists()


def test_timeout_raises_llm_error(tmp_path: Path) -> None:
    """If no response file appears within timeout, raise LLMError (not hang)."""
    llm = LocalLLM(tmp_path, poll_interval=0.05, timeout_seconds=0.2)

    async def main() -> None:
        await llm.analyze("test")

    with pytest.raises(LLMError, match="timeout"):
        asyncio.run(main())


def test_stale_response_file_cleared_before_polling(tmp_path: Path) -> None:
    """A leftover response file from a previous run must not leak into the new
    round — analyze() should clear it and wait for a fresh write."""
    # Pre-seed a stale response.
    (tmp_path / "response_001.json").write_text("STALE", encoding="utf-8")

    llm = LocalLLM(tmp_path, poll_interval=0.05, timeout_seconds=5)

    async def write_fresh() -> None:
        await asyncio.sleep(0.1)
        (tmp_path / "response_001.json").write_text("FRESH", encoding="utf-8")

    async def main() -> str:
        responder = asyncio.create_task(write_fresh())
        result = await llm.analyze("test")
        await responder
        return result

    result = asyncio.run(main())
    assert result == "FRESH"


def test_comms_dir_created_if_missing(tmp_path: Path) -> None:
    nested = tmp_path / "deeply" / "nested" / "comms"
    assert not nested.exists()
    LocalLLM(nested)
    assert nested.is_dir()
