from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from hijack.errors import LLM_001, LLM_002, LLMError
from hijack.llm.api import DEFAULT_MODEL, ClaudeAPIClient

# ---------------------------------------------------------------------------
# LLM_001: ANTHROPIC_API_KEY 없을 때 ClaudeAPIClient() 가 LLMError raise
# ---------------------------------------------------------------------------

def test_missing_api_key_raises_llm_001(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(LLMError) as exc_info:
        ClaudeAPIClient()
    assert exc_info.value.code == LLM_001


# ---------------------------------------------------------------------------
# analyze가 _sync_analyze mock을 통해 string 반환
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_analyze_returns_string(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-fake")

    with patch("anthropic.Anthropic"):
        client = ClaudeAPIClient(api_key="test-key-fake")

    client._sync_analyze = MagicMock(return_value="mocked response")  # type: ignore[method-assign]

    result = await client.analyze("hello", model=DEFAULT_MODEL)
    assert result == "mocked response"
    client._sync_analyze.assert_called_once_with("hello", DEFAULT_MODEL)


# ---------------------------------------------------------------------------
# anthropic.APIStatusError → LLMError (LLM_002) 변환
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_api_status_error_converts_to_llm_002(monkeypatch: pytest.MonkeyPatch) -> None:
    import anthropic

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-fake")

    with patch("anthropic.Anthropic"):
        client = ClaudeAPIClient(api_key="test-key-fake")

    # anthropic.APIStatusError requires a `response` kwarg; use MagicMock for it
    fake_response = MagicMock()
    fake_response.status_code = 401
    api_error = anthropic.APIStatusError(
        "Unauthorized",
        response=fake_response,
        body={"error": {"message": "Unauthorized"}},
    )

    client._sync_analyze = MagicMock(side_effect=api_error)  # type: ignore[method-assign]

    with pytest.raises(LLMError) as exc_info:
        await client.analyze("test prompt", model=DEFAULT_MODEL)

    assert exc_info.value.code == LLM_002
