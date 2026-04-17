# code-hijack

시니어 개발자의 코드베이스를 LLM으로 심층 분석해, AI 에이전트가 동일한 스타일/구조/설계 철학으로 코드를 짜도록 규칙을 자동 추출하는 도구.

## Build & Test

```bash
cd backend
pip install -e ".[dev,api]"
pytest
```

- 패키지 레이아웃: `backend/src/hijack/`
- 테스트 디렉토리: 레포 루트의 `tests/` (pytest는 `backend/`에서 실행)
- 모델은 사용자가 `--model` 옵션으로 선택

## 디렉토리 구조

```
CLAUDE.md
.claude/skills/code-hijack/SKILL.md   # Claude Code skill 모드 워크플로우
.gitignore
backend/
  pyproject.toml
  docs/skeleton.md, tasks.md, harness-plan.md
  src/hijack/          # Python 패키지
    cli.py             # Click 그룹 (analyze/diff 서브커맨드) — CLI 모드
    skill.py           # cli 재노출 (실 워크플로우는 SKILL.md)
    errors.py          # HijackError 계층 + 에러 코드 상수
    core/              # 분석 파이프라인 (fetcher → preprocessor → analyzer → generator)
    llm/               # BaseLLM ABC + ClaudeAPIClient
tests/                 # pytest 테스트 (루트에 위치)
  fixtures/senior_wisdom/   # 레이어 감지 검증용 미니 레포
```

## 범위 (Phase 1 + 2 완료)

- **카테고리** (10): architecture, coding_style, api_design + testing, dependencies, security, performance, devops, state_management, data_model
- **레이어** (5): frontend / backend / db / devops / shared — 결정론적 감지
- **출력**: docs/hijacked/ 하위 세션별 raw + integrated (CLAUDE.md 진입점 + layer별 .md + system-prompt.md)
- **인터페이스**:
  - **CLI 모드**: `code-hijack analyze <target>` — `ANTHROPIC_API_KEY` 필요, Claude API 호출
  - **Skill 모드**: `/code-hijack <target>` — API key 불필요, 현재 Claude Code 세션이 LLM 역할. 워크플로우는 `.claude/skills/code-hijack/SKILL.md`
  - **diff**: `code-hijack diff <session1> <session2>` — 두 세션 규칙 변경 비교
  - **resume**: `code-hijack analyze ... --resume <session.json>` — 이전 세션 완료 카테고리 스킵
- 상세 내용은 `backend/docs/skeleton.md` 참조

## 개발 워크플로우

- harnessai + gstack 스킬 워크플로우로 개발 (계획 → 구현 → 리뷰 순회)
- 커밋 전 `pytest`, `ruff check src ../tests` 실행
- 향후 방향: 언어 확장 (Go/Rust), Critic 레이어, AI trap score, Git 히스토리 마이닝
