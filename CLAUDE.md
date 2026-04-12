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
README.md
.gitignore
backend/
  pyproject.toml
  docs/skeleton.md
  src/hijack/          # Python 패키지
    cli.py             # Click 기반 CLI 진입점
    skill.py           # Claude Code skill 엔트리
    core/              # 분석 파이프라인 (fetcher → preprocessor → analyzer → generator)
    llm/               # Claude API 클라이언트
tests/                 # pytest 테스트 (루트에 위치)
```

## MVP 범위 (Phase 1)

- **카테고리**: architecture, coding_style, api_design (3개)
- **출력**: CLAUDE.md + system-prompt.md (docs/hijacked/ 하위)
- **인터페이스**: Claude Code skill + CLI (Claude API)
- 상세 내용은 `backend/docs/skeleton.md` 참조

## 개발 워크플로우

- harnessai + gstack 스킬 워크플로우로 개발 (계획 → 구현 → 리뷰 순회)
- 커밋 전 `pytest`, `ruff check src tests` 실행
- Phase 2에서 나머지 7개 카테고리, 세션 diff, 여러 레포 비교 등 확장 예정
