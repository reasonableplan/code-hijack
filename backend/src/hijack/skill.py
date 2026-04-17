"""Claude Code skill 진입점 — `/code-hijack <target>` 호출 시 실행된다.

Skill 모드에서는 ANTHROPIC_API_KEY 없이 현재 Claude Code 세션을 사용한다.
CLI 모드와 동일한 파이프라인을 실행하되, LLM 호출은 세션 컨텍스트 내에서 처리된다.
"""

from __future__ import annotations

from hijack.cli import main

if __name__ == "__main__":
    main()
