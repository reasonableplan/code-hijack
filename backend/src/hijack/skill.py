"""Claude Code skill 모드 진입점.

실제 skill 워크플로우는 `.claude/skills/code-hijack/SKILL.md` 에 정의돼 있다.
이 파일은 Python import 호환용 껍데기다 — `/code-hijack <target>` 호출 시
Claude Code 는 SKILL.md 를 읽고 거기 지시를 따른다.

API key 를 가진 사용자는 CLI 모드 (`code-hijack analyze`) 를 사용한다 (cli.py).
Skill 모드는 현재 Claude Code 세션을 LLM 으로 재사용해 API 비용을 피한다.
"""

from __future__ import annotations

from hijack.cli import cli

__all__ = ["cli"]
