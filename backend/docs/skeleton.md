# Project Skeleton — code-hijack

## 1. Overview
- **프로젝트명**: code-hijack
- **한 줄 설명**: 시니어 개발자의 코드베이스를 LLM으로 심층 분석하여, AI 에이전트가 동일한 스타일/구조/설계 철학으로 코드를 짜도록 규칙을 자동 추출하는 도구
- **목적**: AI가 짜는 코드가 조잡하고 유지보수 힘든 문제 해결. 탑 티어 개발자의 선구안과 코드 스타일을 자동 추출하여 에이전트에 적용
- **타겟 사용자**: AI 에이전트로 코드를 작성하는 개인 개발자, 팀, 회사 모두
- **차별화**: 단순 패턴 추출이 아닌 **심층 분석** — "왜 이렇게 짰는지" 설계 의도까지 파악

## 2. 기능 요구사항

### 핵심 기능 (MVP)

#### 2-1. 입력
- [ ] GitHub 레포 URL 또는 로컬 경로 (Python + TypeScript)

#### 2-2. LLM 심층 분석 — 10개 카테고리
  1. **architecture** — 전체 구조, 레이어 분리, 모듈 의존성, "왜 이 구조인지"
  2. **api_design** — API 연결 방식, 엔드포인트 패턴, 요청/응답 형식, 에러 처리
  3. **data_model** — DB/모델 설계, state vs DB 결정 이유, 관계 설계
  4. **coding_style** — 네이밍 컨벤션, 코드 포매팅, 함수/클래스 작성 패턴
  5. **testing** — 테스트 프레임워크, 커버리지 전략, fixture/mock 패턴
  6. **dependencies** — 라이브러리 선택 근거, 버전 호환성, 의존성 관리
  7. **security** — 인증/인가 구조, 시크릿 관리, 입력 검증 패턴
  8. **performance** — 캐싱, 비동기 패턴, DB 인덱싱, 동시성 전략
  9. **devops** — CI/CD, Docker, 환경변수, 배포 전략
  10. **state_management** — 전역/로컬/서버 상태 분리, 데이터 흐름 패턴

#### 2-3. 적용력 강화 기능
- [ ] **참조 파일 지정**: 각 규칙에 "이 파일을 먼저 읽어라" 지정 (추상적 규칙이 아닌 실제 파일)
- [ ] **✅/❌ 예시 코드**: 대상 프로젝트의 실제 코드로 올바른 방식 vs 틀린 방식 비교
- [ ] **안티패턴 목록**: "이 프로젝트에서 절대 하지 않는 것" 목록 + 이유
- [ ] **파일 유형별 지침**: "모델 파일 작성 시", "테스트 파일 작성 시" 등 상황별 규칙
- [ ] **체크리스트**: 코드 제출 전 AI가 자체 검증할 수 있는 체크리스트
- [ ] **신뢰도 점수**: 각 규칙에 일관성 점수 (높음/중간/낮음)
- [ ] **규칙 우선순위**: "필수(MUST)" vs "권장(SHOULD)" 구분

#### 2-4. 출력 구조
- [ ] 세션별 개별 분석 + 통합 버전 (docs/hijacked/ 하위)
- [ ] 소스 레포 메타데이터 기록 (분석 대상, 시간, 파일 목록)
- [ ] 세션 간 diff 비교 지원

#### 2-5. 인터페이스
- [ ] CLI: `code-hijack <target>` (독립 실행, Claude API 사용)
- [ ] Claude Code skill: `/code-hijack <target>` (세션 내 실행)
- [ ] 대화형 분석: 카테고리별 순차 진행 + 사용자 피드백

### MVP 범위 (/plan-ceo-review 반영 — 범위 축소)

| 항목 | MVP (Phase 1) | Phase 1.5 (layer 축) | Phase 2 |
|------|--------------|---------------------|---------|
| 카테고리 (aspect) | architecture, coding_style, api_design | 동일 | 나머지 7개 |
| 레이어 (layer) | 없음 (혼합 출력) | **frontend / backend / db / devops / shared** | — |
| 적용력 강화 | ✅/❌ 예시, 참조 파일, 체크리스트 | + 레이어별 스코프 | 안티패턴, 신뢰도, 우선순위, 파일유형별 |
| 출력 | CLAUDE.md + system-prompt.md | **레이어별 파일 분리** (frontend.md, backend.md 등) | conventions, architecture, checklist 등 |
| 인터페이스 | Claude Code Skill | 동일 | CLI (API 호출) |
| 세션 | 단일 세션 | 단일 세션 | 세션 관리, diff, 통합 |

### Phase 1.5 — 레이어 축 도입 (결정됨)

**문제**: Phase 1 MVP는 aspect 축(architecture/coding_style/api_design)만 있음. 프론트/백엔드/DB 규칙이 한 CLAUDE.md에 뒤섞여서 AI가 프론트 파일 수정할 때 DB 규칙까지 로드. 또한 일부 규칙은 특정 레이어 전용(예: `.data` 래퍼 = 프론트, 마이그레이션 네이밍 = DB)인데 구분 안 됨.

**해결**: 5개 레이어 태깅 + 레이어별 출력 파일 분리.

| 레이어 | 감지 규칙 | 포함 예시 |
|--------|----------|----------|
| `frontend` | `.tsx/.jsx`, 경로에 `frontend/`, `client/`, `web/`, `app/`, `ui/`, `components/`; `package.json`에 react/vue/svelte/next | React 컴포넌트, 페이지, 스타일, 프론트 훅 |
| `backend` | `.py` + 경로에 `backend/`, `server/`, `api/`, `routes/`; `package.json`에 express/fastify; `pyproject.toml`에 fastapi/django | API 핸들러, 서비스 로직, 서버 엔트리 |
| `db` | 경로에 `migrations/`, `schemas/`, `models/`, `prisma/`; 확장자 `.sql`, `.prisma`; SQLAlchemy/TypeORM 패턴 | 마이그레이션, ORM 모델, 스키마 정의 |
| `devops` | `Dockerfile`, `docker-compose*`, `.github/`, `.gitlab-ci*`, `terraform/`, `k8s/`, `Makefile`, `.env*` | CI/CD, 인프라, 배포 스크립트 |
| `shared` | 위 4개 어디에도 속하지 않음 or 경로에 `shared/`, `common/`, `lib/`, `utils/` (단일 레이어 종속 아닌 경우) | 공통 타입, 유틸, 상수, 커밋 규칙 등 |

**LLM 호출 전략 (비용 절충)**:
- 호출 수는 Phase 1과 동일하게 **카테고리당 1회 유지** (3 카테고리 = 3 호출)
- 각 호출 시 5개 레이어 파일을 모두 제공하되, 프롬프트가 **레이어별 섹션으로 나눠서 출력**하도록 강제
- 레이어별 파일이 적거나 없으면 해당 섹션은 "N/A — 이 레이어 파일 없음" 표기

**출력 구조**:
```
docs/hijacked/<session-id>/
  meta.md
  architecture.md                # raw LLM 출력 (카테고리별)
  coding_style.md
  api_design.md
  session.json
  integrated/
    CLAUDE.md                    # 진입점 + 전체 개요 + layer 네비게이션
    frontend.md                  # frontend 전용 규칙 (3 카테고리 합본)
    backend.md                   # backend 전용 규칙
    database.md                  # db 전용 규칙
    devops.md                    # devops 전용 규칙
    shared.md                    # 공통 규칙
    system-prompt.md             # 레이어 구분 없는 통합 에이전트 프롬프트
```

**CLAUDE.md 진입점 역할**:
```markdown
# 코드 스타일 규칙
> 프로젝트/파일에 따라 해당 레이어 문서만 로드하라.

## 레이어 가이드
- 프론트 파일 작업 (.tsx/.jsx, frontend/) → frontend.md + shared.md
- 백엔드 파일 작업 (.py, backend/) → backend.md + shared.md
- DB 파일 작업 (migrations/, models/) → database.md + shared.md
- CI/인프라 작업 (.github/, Dockerfile) → devops.md + shared.md

## 최우선 규칙 (레이어 무관)
[모든 레이어의 MUST 규칙 요약 5~7개]
```

**구현 임팩트**:
- `fetcher.py`: `SourceFile`에 `layer: str` 필드 추가, 감지 함수 추가
- `preprocessor.py`: 2D 분류 (role × layer), 레이어별 파일 수 요약
- `prompts.py`: 카테고리 프롬프트에 "각 레이어별 섹션으로 출력" 지시 추가
- `analyzer.py`: LLM 출력 파싱 시 `layer` 필드 추출
- `models.py`: `AnalysisRule`에 `layer: str` 필드 추가
- `generator.py`: 레이어별 파일 분리 렌더러 + CLAUDE.md 진입점 재작성

**평가 기준**: `tests/fixtures/senior_wisdom/ground_truth.md`의 5개 규칙이 올바른 레이어에 배치되는지 확인.

### 추가 기능 (후순위)
- [ ] 나머지 7개 카테고리 (testing, dependencies, security, performance, devops, state_management, data_model)
- [ ] CLI 독립 실행 (Claude API)
- [ ] 세션 관리 + diff
- [ ] 여러 레포 비교 분석
- [ ] 언어 확장 (Go, Rust 등)
- [ ] 규칙 위반 자동 감지/경고
- [ ] Critic 레이어 (뽑은 규칙의 타당성 재평가)
- [ ] AI trap score (AI가 규칙을 어길 위험도 태깅)
- [ ] Git/PR 히스토리 마이닝 (시니어의 실제 설명 추출)

## 3. 기술 스택

### 백엔드 (Python 3.12+)
- **패키지 매니저**: uv
- **CLI**: click
- **LLM**: anthropic SDK (Claude API) — 모델은 사용자 선택 (--model)
- **HTTP 클라이언트**: httpx
- **AST 보조 분석**: ast (stdlib) — Python 정량 데이터 추출
- **TS 분석**: LLM 우선, AST는 보조
- **테스트**: pytest, pytest-asyncio
- **린터**: ruff

### 허용 라이브러리 화이트리스트
- click
- anthropic
- httpx
- pytest, pytest-asyncio
- ruff

## 4. 핵심 아키텍처

### 분석 파이프라인
```
입력 (레포 URL/경로)
    ↓
[1. Fetcher] — 레포 클론 + 파일 수집
  - Python (.py) + TypeScript (.ts/.tsx) + 설정 파일 수집
  - .gitignore, node_modules, __pycache__ 등 제외
    ↓
[2. Preprocessor] — 핵심 파일 선별
  - 휴리스틱 기반 후보 선별 (역할별 파일 분류)
  - 프로젝트 구조 맵 생성 (디렉토리 트리)
  - LLM에 구조 맵 전달 → "분석할 핵심 파일 N개 선정" 요청
    ↓
[3. LLM Analyzer] — 카테고리별 순차 심층 분석
  - 카테고리마다 구조화된 프롬프트 + 관련 파일 제공
  - 각 분석에 포함:
    - 설계 의도 추론 ("왜 이렇게 짰는지")
    - 참조 파일 지정 ("이 파일을 먼저 읽어라")
    - ✅/❌ 예시 코드 (실제 코드에서 추출)
    - 안티패턴 식별
    - 신뢰도 + 우선순위 태깅
  - 각 카테고리 분석 후 사용자에게 결과 표시, 피드백 반영
    ↓
[4. Generator] — 다중 형식 출력
  - 세션별 개별 파일 생성 (10개 카테고리)
  - 통합 버전 생성 (CLAUDE.md, conventions.md 등)
  - 메타데이터 기록
```

### 파일 선별 전략 (대규모 레포 대응)

**Phase 1 — 휴리스틱 선별:**
| 역할 | 파일 패턴 | 우선순위 |
|------|----------|---------|
| Entry point | main.py, app.py, index.ts, server.ts | 최고 |
| 모델/스키마 | models/, schemas/, types/ | 높음 |
| API/라우터 | routes/, api/, controllers/ | 높음 |
| 서비스/로직 | services/, lib/, utils/ | 중간 |
| 테스트 | tests/, __tests__/, *.test.ts | 중간 |
| 설정 | config/, *.config.ts, pyproject.toml | 중간 |
| 상태 관리 | store/, state/, context/ | 중간 |
| 보안 | auth/, middleware/ | 중간 |
| DevOps | Dockerfile, docker-compose, .github/ | 낮음 |

**Phase 2 — LLM 최종 선정:**
- 프로젝트 구조 맵 + 휴리스틱 후보 목록을 LLM에 제공
- "이 프로젝트의 설계 철학을 이해하기 위해 읽어야 할 핵심 파일을 선정하라"
- LLM이 프로젝트 성격에 맞게 최종 선정

### LLM 분석 프롬프트 전략

각 카테고리별 프롬프트에 공통으로 요구하는 출력 구조:
```
## [카테고리명] 분석 결과

### 설계 의도
(왜 이렇게 짰는지 추론)

### 규칙 목록
각 규칙은 아래 형식을 따른다:
- **규칙**: [구체적 규칙]
- **우선순위**: MUST / SHOULD
- **신뢰도**: 높음 / 중간 / 낮음
- **참조 파일**: [실제 파일 경로]
- **✅ 올바른 예시**: (실제 코드)
- **❌ 틀린 예시**: (이렇게 하면 안 됨)

### 안티패턴
(이 프로젝트에서 절대 하지 않는 것)

### 파일 유형별 지침
(모델 파일 작성 시 / API 파일 작성 시 / 테스트 파일 작성 시)

### 체크리스트
- [ ] 코드 제출 전 확인 항목
```

## 5. 출력 형식

### 파일 구조
대상 프로젝트 내 `docs/hijacked/` 하위에 생성:
```
target-project/
└── docs/hijacked/
    ├── 2026-04-12_fastapi/           # 세션 1: fastapi 레포 분석
    │   ├── meta.md                   # 분석 메타데이터
    │   │   - 대상 레포: fastapi/fastapi
    │   │   - 분석 시간: 2026-04-12 14:30
    │   │   - 모델: claude-opus-4-6
    │   │   - 선별된 파일 목록 (30개)
    │   │   - 분석 소요 시간
    │   ├── architecture.md
    │   ├── api_design.md
    │   ├── data_model.md
    │   ├── coding_style.md
    │   ├── testing.md
    │   ├── dependencies.md
    │   ├── security.md
    │   ├── performance.md
    │   ├── devops.md
    │   └── state_management.md
    │
    ├── 2026-04-15_nextjs/            # 세션 2: next.js 레포 분석
    │   ├── meta.md
    │   ├── architecture.md
    │   └── ...
    │
    └── integrated/                    # 통합 버전 (모든 세션 종합)
        ├── CLAUDE.md                  # 핵심 규칙 요약 (에이전트가 가장 먼저 읽는 파일)
        ├── conventions.md             # 코딩 컨벤션 상세
        ├── architecture.md            # 아키텍처 분석 + 설계 의도
        ├── system-prompt.md           # AI 에이전트용 시스템 프롬프트
        ├── checklist.md               # 코드 제출 전 체크리스트
        └── anti-patterns.md           # 안티패턴 종합
```

### 통합 버전 각 파일 내용

**CLAUDE.md** (에이전트가 가장 먼저 읽는 파일):
- 프로젝트 빌드/실행 명령
- 10개 카테고리 핵심 규칙 요약 (MUST 항목만)
- "절대 하지 말 것" 목록 (top 10)
- 참조 파일 맵 ("새 라우터 → routes/users.py 먼저 읽어라")
- 사용 가능한 라이브러리 화이트리스트

**conventions.md**:
- 네이밍 규칙 + ✅/❌ 예시 코드
- 파일/폴더 구조 규칙
- API 설계 규칙 + 예시
- 에러 처리 규칙 + 예시
- 테스트 규칙 + 예시
- 각 규칙에 신뢰도/우선순위 태그

**architecture.md**:
- 전체 구조 다이어그램
- 레이어별 역할과 의존성
- "왜 이렇게 설계했는지" 추론
- 데이터 흐름
- 파일 유형별 지침 ("모델 파일 작성 시", "서비스 파일 작성 시" 등)

**system-prompt.md**:
- AI 에이전트가 이 프로젝트에서 코딩할 때 사용할 시스템 프롬프트
- "너는 이 프로젝트의 시니어 개발자처럼 코드를 짜야 한다" 형식
- 각 파일 유형별 구체적 지침 포함

**checklist.md**:
- 코드 제출 전 AI가 자체 검증할 체크리스트
- 카테고리별 체크 항목
- MUST 항목은 통과 필수

**anti-patterns.md**:
- "이 프로젝트에서 절대 하지 않는 것" 종합
- 각 안티패턴에 이유 + 올바른 대안 코드

## 6. 세션 관리

### 세션 간 diff
- 새 세션 실행 시 이전 세션과 비교
- 변경된 규칙, 추가된 규칙, 제거된 규칙 표시
- 통합 버전 자동 업데이트

### 세션 네이밍
- `YYYY-MM-DD_<레포명>` 형식
- 같은 레포 재분석 시 새 세션 생성 (이전 세션 보존)

## 7. 중간 데이터 모델 (/plan-eng-review 반영)

분석 결과를 구조화된 데이터로 저장하여 파싱 안정성과 세션 간 diff를 보장한다.

### 핵심 데이터 모델
```python
@dataclass
class AnalysisRule:
    """하나의 규칙."""
    rule: str                          # 규칙 설명
    priority: Literal["MUST", "SHOULD"]  # 필수 vs 권장
    confidence: Literal["high", "medium", "low"]  # 신뢰도
    ref_files: list[str]               # 참조 파일 경로
    good_example: str                  # ✅ 올바른 예시 코드
    bad_example: str                   # ❌ 틀린 예시 코드
    reason: str                        # 왜 이 규칙인지

@dataclass
class CategoryResult:
    """하나의 카테고리 분석 결과."""
    category: str                      # "architecture", "api_design", ...
    design_intent: str                 # 설계 의도 설명
    rules: list[AnalysisRule]
    anti_patterns: list[dict]          # {"pattern": str, "reason": str, "alternative": str}
    file_type_guides: dict[str, str]   # {"model": "지침...", "router": "지침..."}
    checklist: list[str]               # 체크리스트 항목
    raw_llm_output: str                # LLM 원본 출력 (디버깅용)

@dataclass
class SessionResult:
    """하나의 분석 세션 전체 결과."""
    session_id: str                    # "2026-04-12_fastapi"
    target: str                        # 레포 URL 또는 경로
    model: str                         # "claude-opus-4-6"
    timestamp: str                     # ISO 8601
    selected_files: list[str]          # 선별된 파일 목록
    categories: list[CategoryResult]
    analysis_duration_seconds: float
```

### 저장 형식
- 세션별 `session.json`으로 구조화 저장 (diff/통합용)
- 사람이 읽을 수 있는 .md 파일도 함께 생성

### LLM 출력 파싱 전략
1. **구조화된 프롬프트**: LLM에 JSON 출력을 요청 (tool_use 활용 가능)
2. **폴백**: JSON 파싱 실패 시 Markdown에서 regex 추출
3. **검증**: 필수 필드 누락 시 해당 카테고리 재분석 요청 (최대 2회)

## 8. 컨텍스트 관리 전략 (/plan-eng-review 반영)

LLM 컨텍스트 윈도우 한계에 대응하는 전략.

### 카테고리별 파일 배정
각 카테고리에 관련 파일만 선별하여 컨텍스트를 절약한다:

| 카테고리 | 주입 파일 |
|---------|----------|
| architecture | entry point, 최상위 __init__, config, 디렉토리 구조 맵 |
| api_design | routes/, api/, controllers/, middleware/ |
| data_model | models/, schemas/, types/, migrations/ |
| coding_style | 대표 소스 파일 5-10개 (다양한 모듈에서) |
| testing | tests/ 대표 파일 5개 + conftest.py |
| dependencies | pyproject.toml, package.json, requirements.txt, import 요약 |
| security | auth/, middleware/, config 중 시크릿 관련 |
| performance | 비동기 코드, DB 쿼리 코드, 캐싱 관련 |
| devops | Dockerfile, docker-compose, .github/, CI 설정 |
| state_management | store/, state/, context/, 전역 상태 파일 |

### 파일 크기 제어
- 단일 파일 500줄 초과 시 → 핵심 부분만 추출:
  - import 문
  - 클래스/함수 시그니처
  - 데코레이터
  - 주석/docstring
- 전체 카테고리 컨텍스트: 최대 50,000 토큰 목표

### 2단계 분석 (대규모 레포)
```
Step 1 — 요약 분석:
  파일 시그니처만 LLM에 제공 → 각 카테고리의 핵심 패턴 파악
  
Step 2 — 심층 분석:
  Step 1에서 식별된 핵심 파일의 전체 코드를 LLM에 제공
  → 구체적 규칙/예시/안티패턴 추출
```

### CLI vs Skill 공유 아키텍처
```
hijack/
├── core/              # 공유 로직 (CLI와 Skill 둘 다 사용)
│   ├── fetcher.py     # 레포 클론/파일 수집
│   ├── preprocessor.py # 파일 선별 + 구조 맵
│   ├── analyzer.py    # LLM 분석 (프롬프트 + 파싱)
│   ├── generator.py   # 출력 생성
│   ├── models.py      # 데이터 모델 (Section 7)
│   └── session.py     # 세션 관리
├── llm/               # LLM 호출 추상화
│   ├── base.py        # LLM 인터페이스
│   ├── api.py         # Claude API 호출 (CLI용)
│   └── session.py     # Claude Code 세션 내 분석 (Skill용)
├── cli.py             # CLI 진입점
└── skill.py           # Claude Code skill 진입점
```

## 9. 엣지케이스 (/plan-eng-review 반영)

| 케이스 | 대응 |
|--------|------|
| 레포에 Python도 TS도 없음 | 에러: "Python 또는 TypeScript 파일이 없습니다. 지원 언어: Python, TypeScript" |
| 파일 0개 선별됨 | 전체 파일 목록으로 폴백, 경고 메시지 표시 |
| LLM 분석 중 API 에러 | 최대 2회 재시도, 실패 시 해당 카테고리 스킵 + 사유 기록 |
| 기존 docs/hijacked/ 존재 | 새 세션 폴더 추가, 통합 버전은 업데이트 여부 사용자에게 확인 |
| 모노레포 (여러 프로젝트) | `--path` 옵션으로 서브디렉토리 지정 |
| 컨텍스트 초과 | 파일 요약 모드로 전환 (시그니처만 추출) |
| LLM 출력 파싱 실패 | 재시도 1회, 실패 시 raw 출력을 .md로 저장 + 경고 |
| 비용 초과 우려 | 분석 시작 전 예상 토큰/비용 표시, 사용자 확인 후 진행 |

## 10. CLI/UX 설계 (Designer)

### CLI 명령어 구조
```
code-hijack <target> [OPTIONS]

Arguments:
  target              GitHub URL 또는 로컬 경로

Options:
  --model, -m TEXT    LLM 모델 선택 (기본: claude-sonnet-4-6)
  --path, -p PATH     모노레포 시 서브디렉토리 지정
  --categories TEXT    분석할 카테고리 콤마 구분 (기본: all)
  --output, -o PATH   출력 디렉토리 (기본: <target>/docs/hijacked/)
  --resume            이전 세션 이어서 분석
  --dry-run           비용 추정만 하고 실행 안 함
  --verbose, -v       상세 로그
```

### 대화형 분석 흐름 (UX 시나리오)

```
$ code-hijack https://github.com/fastapi/fastapi

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 code-hijack — fastapi/fastapi
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[1/4] 파일 수집
  Cloning repository...
  Found 342 Python files, 0 TypeScript files
  Total: 342 source files

[2/4] 핵심 파일 선별
  Heuristic candidates: 87 files
  LLM selected: 32 key files

  Selected files:
    fastapi/applications.py (entry point)
    fastapi/routing.py (router)
    fastapi/params.py (models)
    ... (29 more)

  Estimated cost: ~$8 (claude-opus-4-6) / ~$2 (claude-sonnet-4-6)
  Estimated time: ~5 min
  
  Continue? [Y/n] █

[3/4] 카테고리별 분석

  ┌─────────────────────────────────────┐
  │ 1/10  architecture                  │
  └─────────────────────────────────────┘

  ## 설계 의도
  FastAPI는 Starlette 위에 구축된 3레이어 아키텍처...
  라우팅 → 의존성 주입 → 응답 직렬화 순서로 처리...

  ## 규칙 (7개)
  1. [MUST] 라우터는 APIRouter로 분리, app에 include
     📁 참조: fastapi/routing.py
     ✅ router = APIRouter(prefix="/users")
     ❌ @app.get("/users") 직접 등록

  2. [MUST] 의존성은 Depends()로 주입
     📁 참조: fastapi/dependencies/utils.py
     ...

  ## 안티패턴
  - 글로벌 변수로 상태 공유 금지
  - 라우터 함수에서 직접 DB 세션 생성 금지

  ## 체크리스트
  - [ ] 새 엔드포인트가 APIRouter에 등록되었는가?
  - [ ] Depends()로 의존성을 주입했는가?

  피드백이 있으신가요? (Enter로 다음 카테고리) █

  ┌─────────────────────────────────────┐
  │ 2/10  api_design                    │
  └─────────────────────────────────────┘
  ...
  (10개 카테고리 반복)

[4/4] 통합 문서 생성

  Generating integrated documents...

  ✅ 분석 완료!

  세션 파일:
    docs/hijacked/2026-04-12_fastapi/
    ├── meta.md
    ├── architecture.md
    ├── api_design.md
    ├── data_model.md
    ├── coding_style.md
    ├── testing.md
    ├── dependencies.md
    ├── security.md
    ├── performance.md
    ├── devops.md
    ├── state_management.md
    └── session.json

  통합 파일:
    docs/hijacked/integrated/
    ├── CLAUDE.md
    ├── conventions.md
    ├── architecture.md
    ├── system-prompt.md
    ├── checklist.md
    └── anti-patterns.md
```

### 에러/경고 메시지

| 상황 | 메시지 |
|------|--------|
| Python/TS 없음 | `Error: No Python or TypeScript files found. Supported: .py, .ts, .tsx` |
| 클론 실패 | `Error: Failed to clone repository. Check URL and network.` |
| API 키 없음 | `Error: ANTHROPIC_API_KEY not set. Set it or use Claude Code skill mode.` |
| 파일 선별 0개 | `Warning: No key files identified. Analyzing all files (may be slow).` |
| 카테고리 분석 실패 | `Warning: [architecture] analysis failed. Skipping. (Retry with --resume)` |
| 기존 세션 존재 | `Note: Previous session found. Creating new session. Use --resume to continue.` |
| 비용 높음 | `Warning: Estimated cost exceeds $20. Consider using --model claude-sonnet-4-6` |

### Claude Code Skill 모드 차이점

Skill(`/code-hijack`)로 실행 시:
- API 호출 대신 현재 세션의 Claude가 직접 분석
- 추가 비용 없음
- 대화형 피드백이 자연스러움 (채팅 형태)
- `--model` 옵션 불필요 (현재 세션 모델 사용)
- 컨텍스트 윈도우 제한 → 파일 요약 모드가 더 자주 활성화될 수 있음

## 11. 비용/시간 추정 (/plan-eng-review 반영)

### LLM 호출 횟수
| 단계 | 호출 수 | 설명 |
|------|--------|------|
| 파일 선정 | 1 | 구조 맵 → LLM이 핵심 파일 선정 |
| 카테고리 분석 | 10~20 | 10개 카테고리 × (요약 1 + 심층 1) |
| 통합 생성 | 1 | 전체 결과를 통합 문서로 |
| **합계** | **12~22** | |

### 예상 비용 (Opus 기준)
- 소규모 레포: ~$2-5
- 중규모 레포: ~$5-15
- 대규모 레포: ~$15-30

→ **분석 시작 전 예상 비용을 사용자에게 표시하고 확인 후 진행**

### 세션 내 분석 (Skill)
- Claude Code 세션을 사용하므로 추가 API 비용 없음
- 대신 세션 컨텍스트 윈도우 내에서 처리해야 함
