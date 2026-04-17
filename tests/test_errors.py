from __future__ import annotations

import click
import pytest

from hijack.errors import (
    FETCH_001,
    INPUT_001,
    LLM_001,
    OUTPUT_001,
    FetchError,
    HijackError,
    InputError,
    LLMError,
    OutputError,
)


def test_input_error_exit_code() -> None:
    err = InputError(INPUT_001, "bad path")
    assert err.exit_code == 2


def test_fetch_error_exit_code() -> None:
    err = FetchError(FETCH_001, "clone failed")
    assert err.exit_code == 3


def test_llm_error_exit_code() -> None:
    err = LLMError(LLM_001, "no key")
    assert err.exit_code == 3


def test_output_error_exit_code() -> None:
    err = OutputError(OUTPUT_001, "refused")
    assert err.exit_code == 3


def test_format_message_contains_code() -> None:
    err = InputError(INPUT_001, "bad path")
    assert "[INPUT_001]" in err.format_message()


def test_hijack_error_is_click_exception_subclass() -> None:
    assert issubclass(HijackError, click.ClickException)
