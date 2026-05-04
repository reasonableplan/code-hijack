"""LocalLLM — BaseLLM implementation that talks to a Claude Code session via files.

This is the "skill mode" backend: rather than calling the Anthropic API, every
LLM round writes the prompt to disk, blocks until a sibling response file
appears, then returns the response. The Claude Code session running the
analysis acts as the LLM by reading the prompt and writing the JSON response.

Why file IPC instead of stdin/stdout?
- The CLI runs as one process; the responding agent (Claude Code) operates
  through tool calls in a separate process. Stream multiplexing would require
  custom plumbing.
- File-based IPC is trivial to inspect: every prompt and response is
  recoverable from `comms_dir` for debugging, retry, or auditing.

Trust model: this backend assumes the responding agent follows the prompt's
JSON schema. The downstream `_rules_from_parsed` validation catches
hallucinated SHAs / malformed evidence regardless, so a misbehaving responder
yields fewer rules — not corrupted state.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from hijack.errors import LLM_002, LLMError
from hijack.llm.base import BaseLLM

_log = logging.getLogger(__name__)

# Polling cadence for response file. Short enough that interactive use feels
# responsive; long enough that idle CPU cost is negligible.
_POLL_INTERVAL_SECONDS = 1.0
# Hard ceiling per LLM round. The responding agent may take minutes for large
# prompts; we don't want to wait forever if they bail out without leaving a
# response file. Default 1h is generous but bounded.
_DEFAULT_TIMEOUT_SECONDS = float(os.environ.get("HIJACK_LOCAL_TIMEOUT", "3600"))


class LocalLLM(BaseLLM):
    """File-IPC BaseLLM. Each analyze() round produces a fresh prompt/response pair.

    Layout under `comms_dir`:
        prompt_001.txt   prompt_002.txt   ...
        response_001.json response_002.json ...

    Numbering is monotonic across the lifetime of the LocalLLM instance so the
    responding agent can match prompts to responses unambiguously.
    """

    def __init__(
        self,
        comms_dir: Path,
        *,
        poll_interval: float = _POLL_INTERVAL_SECONDS,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.comms_dir = comms_dir
        self.comms_dir.mkdir(parents=True, exist_ok=True)
        self._round = 0
        self._poll_interval = poll_interval
        self._timeout_seconds = timeout_seconds

    async def analyze(self, prompt: str, *, model: str = "local") -> str:
        self._round += 1
        prompt_path = self.comms_dir / f"prompt_{self._round:03d}.txt"
        response_path = self.comms_dir / f"response_{self._round:03d}.json"

        # Stale file from a previous run could be mistaken for a fresh response;
        # clear it explicitly so the polling loop only resolves on real input.
        if response_path.exists():
            response_path.unlink()

        prompt_path.write_text(prompt, encoding="utf-8")

        # Print is the orchestration signal — the responder watches stdout for
        # this marker, then reads `prompt_path` and writes `response_path`.
        # Use a stable, greppable prefix so external tooling can parse it.
        print(
            f"[LocalLLM] WAITING round={self._round:03d} "
            f"prompt={prompt_path.as_posix()} response={response_path.as_posix()}",
            flush=True,
        )

        elapsed = 0.0
        while not response_path.exists():
            await asyncio.sleep(self._poll_interval)
            elapsed += self._poll_interval
            if elapsed >= self._timeout_seconds:
                raise LLMError(
                    LLM_002,
                    f"LocalLLM timeout ({self._timeout_seconds}s) waiting for "
                    f"{response_path.as_posix()}",
                )

        try:
            return response_path.read_text(encoding="utf-8")
        except OSError as e:
            raise LLMError(LLM_002, f"LocalLLM response read failed: {e}") from e
