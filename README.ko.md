# code-hijack

> 시니어 코드베이스를 LLM으로 분석해 AI 에이전트용 코딩 규칙을 자동 추출하는 CLI 도구.

AI 에이전트가 짜는 코드가 조잡한 문제 해결. 탑 티어 시니어 레포의 **"왜 이렇게 짰는지"** 설계 의도까지 담은 규칙 문서 (`CLAUDE.md` + 레이어별 `.md` + `system-prompt.md`) 를 생성해 에이전트가 해당 스타일로 코딩하게 만든다.

## 주요 특징

- **10 카테고리 분석** — architecture, coding_style, api_design, testing, dependencies, security, performance, devops, state_management, data_model
- **5 레이어 결정론적 분류** — frontend / backend / db / devops / shared (파일 경로/확장자 기반, LLM 추측 없음)
- **실증적 규칙** — 각 규칙에 `ref_files:라인번호` + ✅/❌ 실제 코드 예시 + 신뢰도 + 우선순위
- **2가지 실행 모드**:
  - **CLI 모드** (`code-hijack analyze`) — Anthropic API 직접 호출, 자동화 가능
  - **Skill 모드** (`/code-hijack`) — Claude Code 세션이 LLM 역할, API key 불필요
- **세션 관리** — `--resume` 으로 재시작, `diff` 서브커맨드로 세션 간 규칙 변경사항 비교

## Quickstart

### 설치
```bash
cd backend
pip install -e ".[dev,api]"
```
Python 3.12+ 필요.

### CLI 모드 (Anthropic API)
```bash
export ANTHROPIC_API_KEY=sk-ant-...

code-hijack analyze https://github.com/tiangolo/fastapi
# 기본: 3 MVP 카테고리 (architecture, coding_style, api_design)

code-hijack analyze ./my-repo --categories architecture,security,testing
# 카테고리 지정

code-hijack analyze ./my-repo --dry-run
# 비용 추정만 (클론 + 파일 수집까지만 수행, LLM 호출 없음)

code-hijack analyze ./my-repo --resume ./docs/hijacked/2026-04-10_my-repo/session.json
# 이전 세션의 완료 카테고리 자동 스킵

code-hijack diff old_session/ new_session/
# 규칙 added/removed/changed 마크다운 출력
```

### Skill 모드 (Claude Code 내)
Claude Code 세션에서:
```
/code-hijack https://github.com/tiangolo/fastapi
```
워크플로우는 [`.claude/skills/code-hijack/SKILL.md`](.claude/skills/code-hijack/SKILL.md) 에 정의. Claude 가 직접 fetcher/preprocessor 호출 → 파일 읽기 → 수동 분석 → `generator.write_output` 호출. 추가 API 비용 없음.

## 출력 구조

```
<target>/docs/hijacked/
├── 2026-04-17_fastapi/         # 세션별 raw 분석
│   ├── meta.md                 # 메타데이터 (세션 ID, 선별 파일, 레이어 분포)
│   ├── architecture.md         # 카테고리별 규칙 (rule + ✅/❌ 예시 + reason)
│   ├── coding_style.md
│   ├── api_design.md
│   └── session.json            # 구조화 데이터 (diff 재사용)
└── integrated/                 # 통합 — AI 에이전트용
    ├── CLAUDE.md               # 진입점 + 레이어 가이드 + Top MUST 규칙
    ├── backend.md              # backend 레이어 규칙 (카테고리별 모음)
    ├── frontend.md
    ├── database.md
    ├── devops.md
    ├── shared.md               # 레이어 무관 공통 규칙
    └── system-prompt.md        # 에이전트 시스템 프롬프트
```

대상 레포의 `integrated/CLAUDE.md` 를 해당 프로젝트의 Claude Code 컨텍스트로 복사하면 에이전트가 그 스타일로 코딩.

## 파이프라인

```
입력 (GitHub URL 또는 로컬 경로)
  ↓ Fetcher        — git clone, .py/.ts/.tsx 수집, _SKIP_DIRS 제외
  ↓ detect_layer   — 결정론적 레이어 태깅 (frontend/backend/db/devops/shared)
  ↓ Preprocessor   — 역할 분류 (entry_point/api/model/...) + 카테고리별 파일 선별
                     (콘텐츠 밀도 정렬, near-duplicate dedup)
  ↓ Analyzer       — BaseLLM 인터페이스 경유 카테고리별 호출
                     (JSON 출력 + regex 폴백, 2회 재시도)
  ↓ Generator      — 레이어별 .md + CLAUDE.md + system-prompt.md 렌더링
출력 (docs/hijacked/<세션>/ + integrated/)
```

## 실제 Dogfooding 결과

본 도구로 시니어 레포 4개를 분석한 결과 (2026-04-17):

| 레포 | 총 파일 | 규칙 | 포착한 비자명 패턴 |
|------|--------|------|-----|
| [tiangolo/fastapi](https://github.com/tiangolo/fastapi) | 1119 | 20 | `DefaultPlaceholder` sentinel (`None` vs 명시적 `None` 구분), `Annotated[T, Doc('''...''')]` 인라인 문서 |
| [vercel/ai](https://github.com/vercel/ai) | 3871 | 20 | `Symbol.for` cross-realm 에러 마커 (Next.js edge/worker 대응), `.nullish()` forward-compat 스키마 |
| [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) | 970 | 20 | 모듈 임포트 **전** env 오버라이드 (모듈 레벨 캐싱 대응), jittered backoff |
| code-hijack (self) | 31 | 19 | dataclass-only 철학, 단방향 파이프라인, BaseLLM DI |

각 분석 결과 품질은 **참고용 OK, 그대로 복붙은 권장 X** 수준. 자세한 한계 → [섹션 하단](#한계).

## 프로젝트 구조

```
CLAUDE.md                              # 에이전트용 가이드 (요약)
README.md                              # 이 파일
.claude/skills/code-hijack/SKILL.md    # Skill 모드 워크플로우
backend/
  pyproject.toml                       # setuptools, Python 3.12+
  docs/skeleton.md                     # 상세 설계 (skeleton-v2.md 원본 보존)
  src/hijack/
    cli.py                             # click group (analyze/diff 서브커맨드)
    skill.py                           # Skill 모드 stub (실 로직은 SKILL.md)
    errors.py                          # HijackError(ClickException) 계층
    core/
      models.py                        # AnalysisRule, CategoryResult, SessionResult @dataclass
      fetcher.py                       # git clone, 파일 수집, detect_layer
      preprocessor.py                  # 역할 분류, 2D 그룹핑, 파일 선별
      prompts.py                       # 10 카테고리 프롬프트 + 품질 기준
      analyzer.py                      # LLM 호출 + 2회 재시도 + JSON/regex 파싱
      session.py                       # session_id, SessionDiff
      generator.py                     # 레이어별 .md + CLAUDE.md 렌더링
    llm/
      base.py                          # BaseLLM ABC
      api.py                           # ClaudeAPIClient (anthropic SDK)
tests/                                 # pytest — 177 tests, ruff clean
  fixtures/senior_wisdom/              # 레이어 감지 검증용 미니 레포
```

## 개발

```bash
cd backend
pip install -e ".[dev,api]"
pytest                                 # 177 tests
ruff check src/ ../tests/              # lint
```

**설계 원칙** (자기 적용 분석으로 검증됨):
- 단방향 파이프라인 (Fetcher → Preprocessor → Analyzer → Generator) — 각 단계 독립 테스트
- LLM 호출은 반드시 `BaseLLM` ABC 경유 — 테스트에서 `AsyncMock` 대체 가능
- `@dataclass` only — Pydantic 의도적 배제 (stdlib 우선)
- 결정론적 레이어 태깅 — 경로/확장자/의존성 기반 룰, LLM 추측 금지
- `click.ClickException` 서브클래스 계층 — `sys.exit()` 금지

## 에러 코드

| 코드 | 의미 | Exit |
|------|------|------|
| `INPUT_001` | 대상 경로/URL 유효하지 않음 | 2 |
| `INPUT_002` | 지원 언어 파일 없음 (.py/.ts/.tsx) | 2 |
| `FETCH_001` | 레포 클론 실패 | 3 |
| `LLM_001` | API 인증 실패 (ANTHROPIC_API_KEY 미설정/잘못됨) | 3 |
| `LLM_002` | API 호출 실패 (rate limit, 네트워크 등) | 3 |
| `LLM_003` | 응답 JSON 파싱 실패 | 3 |
| `OUTPUT_001` | 기존 integrated/ 덮어쓰기 거부 | 3 |

`LLM_002` 는 카테고리당 최대 2회 재시도 (exponential backoff).
`LLM_003` 은 JSON 파싱 실패 시 regex 폴백 1회.

## 한계

도그푸딩에서 확인된 실제 한계 (정직한 평가):

1. **bad_example 품질 편차** — skill 모드 초기 결과물에서 일부 bad_example 이 실제 안티패턴 코드 대신 설명 주석으로 생성됨. 프롬프트 강화로 해결 진행 중 (`prompts.py` _OUTPUT_FORMAT 의 QUALITY REQUIREMENTS 참조).
2. **선별 편향** — `docs_src/`, `examples/`, `samples/` 등 튜토리얼 디렉토리가 실제 프레임워크 소스를 밀어내는 경우. 향후 개선 가능 (현재 콘텐츠 밀도 정렬 + near-duplicate dedup 으로 일부 완화).
3. **카테고리 교차 중복** — architecture 와 coding_style 의 규칙이 겹치는 경우. 카테고리 경계 더 명확하게.
4. **MUST 남발** — 프롬프트 제약에도 MUST 비율 높음. 신호-잡음비 개선 여지.

"참고 수준 OK, 자동화 수준 아직 아님" — 생성된 CLAUDE.md 는 사람이 한 번 훑어 정리하는 게 현실적.

## Roadmap

- ✅ **Phase 1 (MVP)** — 3 카테고리 × 5 레이어, CLI + Skill 모드
- ✅ **Phase 2 (확장)** — 10 카테고리, `--resume`, `diff` 서브커맨드, SessionDiff
- **Phase 3 (후순위)** — 언어 확장 (Go, Rust), Critic 레이어 (뽑힌 규칙 재평가), AI trap score, Git PR 히스토리 마이닝, MCP 서버 노출

자세한 설계 문서: [`backend/docs/skeleton.md`](backend/docs/skeleton.md)
