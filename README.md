# code-hijack

> 시니어 개발자의 코드베이스를 LLM으로 심층 분석해, AI 에이전트가 동일한 스타일과 설계 철학으로 코드를 짜도록 규칙을 자동 추출하는 도구.

AI가 짜는 코드가 조잡하고 유지보수가 힘든 문제를 해결하기 위한 프로젝트입니다. 단순 패턴 추출이 아니라 "왜 이렇게 짰는지" 설계 의도까지 LLM으로 분석해, HarnessAI-호환 규칙 문서(`CLAUDE.md`, `system-prompt.md`)를 생성합니다.

## 특징

- **심층 분석** — 코드 스타일뿐 아니라 아키텍처 의도와 트레이드오프까지 파악
- **실증적 규칙** — 각 규칙마다 실제 파일 참조 + ✅/❌ 예시 코드 첨부
- **체크리스트** — AI가 코드 제출 전 스스로 검증할 수 있는 항목 생성
- **카테고리별 분석** — architecture / coding_style / api_design (Phase 1)

## Quickstart

```bash
# 설치 (Python 3.11+)
cd backend
pip install -e ".[dev,api]"

# CLI로 실행 (Anthropic API 키 필요)
export ANTHROPIC_API_KEY=sk-ant-...
code-hijack https://github.com/owner/repo --model claude-opus-4-6

# 테스트
pytest
```

## MVP 파이프라인

```
입력 (레포 URL / 로컬 경로)
  ↓ Fetcher        — .py, .ts/.tsx, 설정 파일 수집
  ↓ Preprocessor   — 구조 맵 생성 + LLM으로 핵심 파일 N개 선별
  ↓ Analyzer       — 카테고리별 순차 LLM 분석 (architecture / coding_style / api_design)
  ↓ Generator      — CLAUDE.md + system-prompt.md 렌더링
출력 (docs/hijacked/<세션>/)
```

## 프로젝트 구조

```
CLAUDE.md                         # 에이전트용 가이드
README.md                         # 이 파일
.gitignore
backend/
  pyproject.toml                  # Python 패키징 + pytest 설정
  docs/skeleton.md                # 상세 설계 문서
  src/hijack/
    cli.py, skill.py              # 진입점
    core/                         # fetcher, preprocessor, analyzer, generator, models, prompts, session
    llm/                          # Claude API 클라이언트
tests/                            # pytest (루트)
```

## 개발 원칙

- harnessai + gstack 워크플로우로 구축
- MVP 범위: 3개 카테고리만 먼저 — Phase 2에서 testing, security, performance 등 7개 확장
- 허용 라이브러리 화이트리스트: click / anthropic / httpx / pytest / ruff

## Roadmap

- **Phase 1 (MVP)** — ✅ architecture / coding_style / api_design, Claude Code skill + CLI
- **Phase 2** — 나머지 7개 카테고리, 세션 diff/비교, 규칙 위반 자동 감지
- **Phase 3** — 언어 확장 (Go, Rust), 팀 단위 규칙 관리

자세한 설계는 [`backend/docs/skeleton.md`](backend/docs/skeleton.md)를 참고하세요.
