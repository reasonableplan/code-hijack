# Project Skeleton — code-hijack

## 1. 프로젝트 개요

- **프로젝트명**: code-hijack
- **한 줄 설명**: 시니어 코드 스타일을 LLM으로 자동 추출
- **목적**: AI 에이전트가 조잡한 코드를 짜는 문제 해결. 탑 티어 시니어 레포를 LLM으로 분석해 "왜 이렇게 짰는지" 설계 의도까지 담은 규칙 문서(CLAUDE.md + system-prompt.md)를 자동 생성. 에이전트가 해당 레포 스타일로 코드를 짜게 만든다.
- **타겟 사용자**: AI 에이전트로 코드를 작성하는 개인 개발자 (본인 포함). Phase 2에서 팀/회사용 확장.
- **범위**:
  - **Phase 1 (MVP)**: GitHub URL/로컬 경로 입력 → 3개 카테고리(architecture, coding_style, api_design) × 5개 레이어(frontend/backend/db/devops/shared) 분석 → 레이어별 `.md` + CLAUDE.md 진입점 + system-prompt.md 출력. Claude Code skill 모드 + CLI 모드 모두 지원.
  - **Out-of-scope (Phase 2+로 이월)**: 나머지 7개 카테고리, 세션 간 diff, 여러 레포 통합 분석, 언어 확장(Go/Rust), MCP 서버 노출.

## 2. 기능 요구사항

### 핵심 기능 (MVP — Phase 1)
- [ ] GitHub URL 또는 로컬 경로를 받아 Python/TypeScript 소스 파일을 수집한다
- [ ] 휴리스틱 + LLM 협업으로 분석할 핵심 파일을 선별한다
- [ ] 3개 카테고리(architecture, coding_style, api_design) × 5개 레이어(frontend/backend/db/devops/shared) 분석을 수행한다
- [ ] 각 규칙에 참조 파일, ✅/❌ 예시 코드, 신뢰도, 우선순위(MUST/SHOULD)를 태깅한다
- [ ] 대상 레포의 `docs/hijacked/` 하위에 세션별 raw 분석 + 통합 CLAUDE.md/system-prompt.md를 저장한다

### 추가 기능 (Phase 2+)
- [ ] 나머지 7개 카테고리 (testing, dependencies, security, performance, devops, state_management, data_model)
- [ ] `--resume` (이전 세션 이어서 분석)
- [ ] 세션 diff (이전 세션 대비 변경/추가/삭제 규칙 표시)
- [ ] 여러 레포 통합 분석
- [ ] 언어 확장 (Go, Rust)

### 비즈니스 규칙
- 분석 대상 언어는 Python(.py)과 TypeScript(.ts/.tsx)만. 그 외 언어 파일은 제외한다.
- 제외 디렉토리: `.git/`, `node_modules/`, `__pycache__/`, `.venv/`, `dist/`, `build/`, `target/`.
- 세션 ID는 `YYYY-MM-DD_<레포명>` 형식. 같은 레포 재분석 시 새 세션 폴더를 생성 (이전 세션 보존).
- LLM 분석 중 카테고리 실패 시 최대 2회 재시도. 실패 시 해당 카테고리 스킵 + `meta.md`에 사유 기록.
- 레이어 태깅은 결정론적 감지 함수로 (경로/확장자/의존성 기반). LLM이 추측하지 않는다.
- CLI 모드는 `ANTHROPIC_API_KEY` 환경변수 필수. Skill 모드는 현재 Claude Code 세션을 사용하므로 불필요.
- 비용 추정을 분석 시작 전에 표시하고 사용자 확인(`Y/n`) 후 진행한다.

### 명시적 Out-of-scope
- **DB 영속화 없음** — sqlite/duckdb 사용하지 않는다. 세션 데이터는 `session.json` 파일로 저장.
- **프론트엔드 UI 없음** — 웹/데스크탑 GUI 없음. CLI + Claude Code skill만.
- **인증/권한 없음** — 단일 사용자 로컬 도구.
- **백그라운드 분석 없음** — 모든 분석은 동기적 실행, 진행률은 stdout에 표시.

## 3. 기술 스택

### 런타임 / 언어
- Python 3.12+

### 프레임워크 / 주요 라이브러리
- `click` — CLI 프레임워크
- `anthropic` — Claude API 호출 (CLI 모드)
- `httpx` — GitHub 레포 메타데이터 조회
- `asyncio` (stdlib) — LLM 호출 병렬 처리

### 빌드 / 패키지 관리
- `pip install -e ".[dev,api]"` (setuptools 기반, `backend/pyproject.toml` 참조)

### 테스트
- `pytest` + `pytest-asyncio` (asyncio_mode=auto)
- 실행: `cd backend && pytest` (testpaths → `../tests/`)

### 린트 / 포맷 / 타입체크
- `ruff check src tests` (E, F, I, UP, B, SIM 규칙)
- 타입체커: 현재 Phase 1에선 미도입 (pyright 추가는 Phase 2 검토)

### 허용 라이브러리 화이트리스트

**추가 허용 (프로파일 기본 + 이 목록)**:
- `anthropic`: Claude API SDK — LLM 분석의 핵심 호출 경로
- `httpx`: GitHub URL 정규화/메타데이터 조회 + anthropic SDK 내부 의존성
- `pytest-asyncio`: async LLM 호출 테스트

**화이트리스트 외 금지**:
- `pydantic` — 데이터 모델은 `@dataclass`로 통일 (프로파일 whitelist에 있지만 이 프로젝트는 의도적으로 배제)
- `rich`, `platformdirs`, `tomli` — Phase 1 불필요. 필요해지면 그때 추가 + 사유 명시.

## 4. 설정 / 환경변수

### 환경변수
| 이름 | 타입 | 필수 | 기본값 | 설명 |
|------|------|:---:|--------|------|
| `ANTHROPIC_API_KEY` | `str` | ✅ (CLI 모드) | — | Claude API 키. Skill 모드에서는 불필요. |

### 피처 플래그
현재 없음. Phase 1 동작은 모두 CLI 옵션으로 제어.

### `.env.example` 위치
- `backend/.env.example` — `ANTHROPIC_API_KEY=` 한 줄만.

### 런타임 설정
- 현재 런타임 설정 파일 없음. 모든 설정은 CLI 옵션 또는 환경변수로 전달.
- 로드 우선순위: CLI 옵션 > 환경변수 > 코드 기본값.

## 5. 에러 핸들링

### 에러 분류 체계

| 코드 | 의미 | 발생 조건 |
|------|------|----------|
| `INPUT_001` | 대상 경로/URL 유효하지 않음 | 로컬 경로 존재하지 않거나 URL 형식 오류 |
| `INPUT_002` | 지원 언어 없음 | 대상 레포에 .py/.ts/.tsx 파일 0개 |
| `FETCH_001` | 레포 클론 실패 | `git clone` 실패 (네트워크/권한) |
| `FETCH_002` | 파일 0개 선별됨 | 휴리스틱 + LLM 선정 결과 0개 (폴백 경로 진입) |
| `LLM_001` | API 인증 실패 | `ANTHROPIC_API_KEY` 미설정 또는 잘못됨 (CLI 모드만) |
| `LLM_002` | API 호출 실패 | anthropic SDK 예외 (rate limit, 네트워크 등) |
| `LLM_003` | 응답 파싱 실패 | JSON 파싱 실패 + regex 폴백도 실패 |
| `OUTPUT_001` | 기존 통합 파일 덮어쓰기 거부 | `docs/hijacked/integrated/` 존재 + 사용자 확인에 `n` |

### 에러 전달 방식
- **CLI**: `click.ClickException` 서브클래스 raise → `stderr`에 사람이 읽는 메시지 + 적절한 exit code.
- **Skill 모드**: 예외를 그대로 Claude Code에 전파 (Claude가 대화로 설명).

### 예외/에러 계층

```
HijackError (baseclass, ClickException 상속)
├─ InputError          (INPUT_001, INPUT_002) — exit 2
├─ FetchError          (FETCH_001, FETCH_002) — exit 3
├─ LLMError            (LLM_001, LLM_002, LLM_003) — exit 3
└─ OutputError         (OUTPUT_001) — exit 3
```

### 내부 ↔ 외부 경계
- **내부 전용**: 스택 트레이스, anthropic SDK 원시 에러 메시지 → `logging` 로만.
- **외부 노출 (stderr)**: 에러 코드 + 사람이 읽는 메시지 + (LLM_002만) 재시도 횟수.
- **절대 노출 금지**: `ANTHROPIC_API_KEY` 값, 내부 절대 경로, 스택 트레이스.

### 재시도 / 복구 정책
- `LLM_002` (API 호출 실패): 카테고리당 최대 2회 재시도. exponential backoff (1s → 2s → 4s). 2회 실패 시 해당 카테고리 스킵 + `meta.md`에 사유 기록.
- `LLM_003` (파싱 실패): JSON 파싱 실패 시 regex 폴백 1회. 그것도 실패 시 raw 출력을 `<category>.md`에 저장 + 경고.
- `FETCH_001`: 재시도 안 함. 즉시 에러.

## 6. CLI 커맨드

### 엔트리포인트
- 실행 명령: `code-hijack` (pyproject.toml `[project.scripts]`에 등록) 또는 `python -m hijack`
- 프레임워크: `click`

### 공통 옵션
| 옵션 | 축약 | 설명 |
|------|-----|------|
| `--verbose` | `-v` | 상세 로그 (logging DEBUG) |
| `--quiet` | `-q` | 진행 메시지 억제 |
| `--help` | `-h` | 도움말 |
| `--version` | | 버전 표시 |

### 커맨드

#### `code-hijack <target>`

```
사용법: code-hijack <target> [옵션]

인자:
  target             GitHub URL 또는 로컬 경로 (필수)

옵션:
  --model, -m TEXT    LLM 모델 ID (기본: claude-sonnet-4-6)
  --path, -p PATH     모노레포 시 서브디렉토리 지정
  --categories TEXT   분석할 카테고리 콤마 구분 (기본: architecture,coding_style,api_design)
  --output, -o PATH   출력 디렉토리 (기본: <target>/docs/hijacked/)
  --dry-run           비용 추정만 하고 실행 안 함 (LLM 호출 없음)

예시:
  code-hijack https://github.com/fastapi/fastapi
  → 분석 진행률 출력 + docs/hijacked/2026-04-17_fastapi/ 생성

  code-hijack ./my-repo --dry-run
  → 선별 파일 수 + 예상 토큰/비용만 출력, 종료

에러:
  exit 0: 성공
  exit 2: 인자 누락 / 형식 오류 / INPUT_001, INPUT_002
  exit 3: FETCH_*, LLM_*, OUTPUT_* 내부 처리 실패
```

### 서브커맨드 그룹
현재 없음 (단일 커맨드). Phase 2에서 `--resume`, `diff` 등을 서브커맨드로 승급 검토.

### 출력 형식
- 기본: 사람이 읽는 텍스트 (click.echo, 필요 시 색상). 진행률은 stderr에 짧게.
- 에러: stderr. 최종 출력 파일 경로 및 요약은 stdout.
- `--json` 옵션: 현재 없음 (Phase 2 검토).

### Skill 모드
- `/code-hijack <target>` — `skill.py` 엔트리를 통해 현재 Claude Code 세션의 컨텍스트로 실행.
- `--model` 옵션 불필요 (세션 모델 사용).
- API 호출 대신 세션 내 LLM 사용 → 추가 비용 없음.

## 7. 도메인 로직

### 핵심 비즈니스 규칙
1. 분석 파이프라인은 **Fetcher → Preprocessor → Analyzer → Generator** 순서. 각 단계는 독립 테스트 가능.
2. `core/`의 모든 함수는 순수 — 파일/네트워크 I/O 금지. I/O는 `io/` 또는 어댑터 계층에서만.
3. LLM 호출은 **반드시 `BaseLLM` 인터페이스를 거친다**. 테스트에서 `AsyncMock`으로 대체 가능.
4. 레이어 태깅은 결정론적 — 경로/확장자/의존성 파일(package.json, pyproject.toml) 기반 감지 함수로. LLM이 추측하지 않는다.
5. LLM이 반환한 규칙 중 필수 필드(`rule`, `priority`, `layer`) 누락 시 해당 규칙 드롭 + 경고. 카테고리 전체는 유효.
6. `dataclass` only — Pydantic 금지. 직렬화는 `to_json` / `from_json` 수동 구현.
7. 윈도우/macOS/리눅스 호환 — 경로 비교는 `Path.as_posix()` 사용, `str(path)` 금지.

### 알고리즘

#### `detect_layer`
- **입력**: `file_path: Path`, `repo_root: Path`, `package_jsons: dict[Path, dict]`, `pyproject_toml: dict | None`
- **출력**: `Literal["frontend", "backend", "db", "devops", "shared"]`
- **전제조건**: `file_path`가 `repo_root` 하위
- **사후조건**: 반드시 5개 중 하나 반환. 불확실할 때 `"shared"`.
- **복잡도**: `O(1)` (경로 단편 비교 + dict 조회)

**의사 코드**:
```
rel = file_path.relative_to(repo_root).as_posix()
suffix = file_path.suffix

if suffix in {".tsx", ".jsx"}: return "frontend"
if any(seg in rel for seg in ["frontend/", "client/", "web/", "app/", "ui/", "components/"]): return "frontend"
if suffix in {".sql", ".prisma"} or any(seg in rel for seg in ["migrations/", "schemas/", "prisma/", "models/"]): return "db"
if file_path.name in {"Dockerfile"} or any(seg in rel for seg in [".github/", "k8s/", "terraform/"]): return "devops"
if suffix == ".py" and any(seg in rel for seg in ["backend/", "server/", "api/", "routes/"]): return "backend"
if suffix == ".py" and pyproject_toml has "fastapi"|"django"|"flask": return "backend"
return "shared"
```

#### `run_full_analysis`
- **입력**: `files: list[SourceFile]`, `categories: list[str]`, `llm: BaseLLM`, `model: str`
- **출력**: `SessionResult`
- **전제조건**: `files`는 Preprocessor가 선별한 핵심 파일. `llm`은 `BaseLLM` 구현체.
- **사후조건**: 카테고리마다 `CategoryResult` 생성. 실패한 카테고리는 `error` 필드에 사유 기록.
- **복잡도**: `O(C × F)` (C=카테고리 수, F=카테고리당 관련 파일 수)

**의사 코드**:
```
for category in categories:
    files_for_cat = filter_by_role(files, _CATEGORY_ROLES[category])
    prompt = build_category_prompt(category, files_for_cat)
    for attempt in range(2):
        try:
            raw = await llm.analyze(prompt, model=model)
            parsed = parse_json(raw) or parse_regex(raw)
            result = CategoryResult(category, ..., rules=[AnalysisRule(..., layer=r["layer"]) for r in parsed["rules"]])
            results.append(result); break
        except (APIError, ParseError) as e:
            backoff(attempt); continue
    else:
        results.append(CategoryResult(category, error=str(e)))
return SessionResult(categories=results, ...)
```

### 순수 함수 vs I/O 분리

**pure (`src/hijack/core/`)** — I/O 없음, 테스트 쉬움:
- `models.py`: 데이터 모델 (`AnalysisRule`, `CategoryResult`, `SessionResult`) + `to_json` / `from_json`
- `preprocessor.py`: 역할 분류, 2D(role×layer) 분류, 구조 맵 생성 — 순수 함수
- `prompts.py`: 카테고리별 프롬프트 빌더 — 순수 문자열 조립
- `analyzer.py` 의 파싱 함수 (`parse_json`, `parse_regex_fallback`) — LLM 호출부는 impure로 분리
- `session.py` 의 ID 생성/diff 로직 — 순수

**impure (파이프라인 진입/출력 레이어)** — 파일/네트워크:
- `core/fetcher.py`: 레포 클론 (`git` subprocess) + 파일 수집 [FS/NET]
- `core/analyzer.py` 의 `run_full_analysis`: LLM 호출 [NET]
- `core/generator.py`: `write_output` 파일 저장 [FS]
- `core/session.py` 의 `get_output_dir`: 디렉토리 생성 [FS]
- `llm/api.py`: `ClaudeAPIClient.analyze` — anthropic SDK 호출 [NET]
- `cli.py`: click 진입점 — stdin/stdout/exit

### 에지 케이스 목록
- 레포에 `.py` 도 `.ts/.tsx` 도 없음 → `InputError(INPUT_002)`
- 휴리스틱 선정 결과 0개 → 전체 파일로 폴백 + 경고 (`FETCH_002` 는 에러 아닌 warn)
- 단일 파일이 2,000줄 초과 → `import` / 시그니처 / 주석만 추출 (컨텍스트 절약)
- 모노레포 (루트에 여러 프로젝트) → `--path` 옵션으로 서브디렉토리 지정
- 기존 `docs/hijacked/integrated/` 존재 → 덮어쓸지 사용자 확인 (`y/n`). 거부 시 `OutputError(OUTPUT_001)`
- LLM 응답이 JSON 아님 → regex 폴백 시도. 그것도 실패 시 raw 저장 + 경고.
- `--dry-run` 모드 → Fetcher + Preprocessor 까지만 실행, LLM 호출 없이 예상 토큰/비용 출력.

### 테스트 전략
- **단위 테스트**: 순수 함수 (`detect_layer`, `preprocessor`, `parse_json`, `parse_regex_fallback`, `create_session_id`) → 고정 입력/출력.
- **통합 테스트**: `tests/fixtures/senior_wisdom/` 픽스처 레포로 전체 파이프라인 실행. LLM은 `AsyncMock` 또는 미리 녹음된 응답 사용.
- **검증 픽스처**: `ground_truth.md`에 정의된 5개 규칙이 올바른 레이어에 배치되는지 검증 (Phase 1.5 완료 조건).
- **커버리지 목표**: `core/` 모듈 ≥ 90%, `cli.py` / `llm/api.py` ≥ 70% (I/O 경계는 mock).

## 8. 외부 통합

### 3rd Party API
| 서비스 | 목적 | 인증 방식 | 요금제 |
|--------|------|----------|--------|
| Anthropic Claude API | 카테고리별 LLM 분석 | API key (env: `ANTHROPIC_API_KEY`) | pay-as-you-go (사용자가 `--model` 로 비용 제어) |
| GitHub (공개 레포) | `git clone` 으로 클론 | 공개 레포는 인증 불필요. 사설 레포는 Phase 2 검토 | 무료 |

### OAuth 공급자
해당 없음 (단일 사용자 로컬 도구).

### 웹훅
**수신**: 없음. **발신**: 없음.

### 실패 대응
- **Anthropic Claude API**:
  - Retry: 카테고리당 최대 2회, exponential backoff (1s → 2s → 4s)
  - Circuit breaker: 없음 (Phase 2 검토)
  - Fallback: 카테고리 스킵 + `meta.md`에 사유 기록. 나머지 카테고리는 계속 진행.
- **GitHub 클론**:
  - Retry: 없음 (네트워크 문제는 사용자가 재실행)
  - Fallback: 로컬 경로 지정 권유 메시지.

### Rate Limit
- Anthropic: 모델별 RPM/TPM 한도 → 429 에러 시 `LLM_002` 로 묶어 재시도. 사용자에게 "잠시 후 재실행" 안내.
- GitHub: 공개 레포 클론은 실무상 제한 없음 (Phase 1 기준).

## 9. 태스크 분해

### Phase 1 — MVP (3 카테고리 × 5 레이어, CLI + Skill)
| ID | 에이전트 | 의존성 | 설명 | 상태 |
|----|---------|--------|------|------|
| T-001 | backend_coder | - | core.logic (models.py): AnalysisRule/CategoryResult/SessionResult @dataclass + to_json/from_json. layer 필드 포함. | 대기 |
| T-002 | backend_coder | - | errors + configuration: HijackError(ClickException) 계층 (Input/Fetch/LLM/Output) + 에러 코드 상수 + backend/.env.example 생성. | 대기 |
| T-003 | backend_coder | T-001 T-002 | core.logic (llm/base.py, llm/api.py): BaseLLM ABC (analyze 추상) + ClaudeAPIClient (anthropic SDK, asyncio.to_thread 래핑, 기본 모델 claude-sonnet-4-6, ANTHROPIC_API_KEY 로드). | 대기 |
| T-004 | backend_coder | T-001 T-002 | core.logic (fetcher.py): SourceFile + fetch_source (로컬 경로 + git clone), 파일 수집 + _SKIP_DIRS 제외 + detect_layer (frontend/backend/db/devops/shared). | 대기 |
| T-005 | backend_coder | T-001 T-004 | core.logic (preprocessor.py): 역할 분류 (entry_point/model/api/test/config/...), 2D(role×layer) 분류, PreprocessResult, build_file_summary_for_llm. | 대기 |
| T-006 | backend_coder | T-001 | core.logic (prompts.py): MVP 3 카테고리 프롬프트 (architecture, coding_style, api_design) + 레이어별 섹션 출력 지시 + MVP_CATEGORIES 상수. | 대기 |
| T-007 | backend_coder | T-003 T-005 T-006 | core.logic (analyzer.py): run_full_analysis, 카테고리별 LLM 호출, JSON 파싱 + regex 폴백, 최대 2회 재시도, 레이어 파싱. | 대기 |
| T-008 | backend_coder | T-001 | core.logic (session.py): create_session_id (YYYY-MM-DD_<repo>), get_output_dir, SessionDiff (Phase 2 stub). | 대기 |
| T-009 | backend_coder | T-001 T-007 T-008 | core.logic (generator.py): 레이어별 .md 분리 렌더러 (frontend/backend/database/devops/shared) + CLAUDE.md 진입점 + system-prompt.md + write_output (세션별 raw + integrated). | 대기 |
| T-010 | backend_coder | T-002 T-003 T-007 T-009 | interface.cli (cli.py, skill.py): click 진입점 + --model/--path/--categories/--output/--dry-run/-v/-q, skill 엔트리, 비용 추정 + 사용자 확인 흐름. | 대기 |
| T-011 | backend_coder | T-001 T-004 T-005 T-007 T-008 T-009 | core.logic (tests): test_models/fetcher/preprocessor/analyzer/generator/session + tests/fixtures/senior_wisdom/ 복원 (ground_truth.md 5 규칙 레이어 검증). | 대기 |

### Phase 2 — 확장 (7 카테고리 + 세션 관리)
| ID | 에이전트 | 의존성 | 설명 | 상태 |
|----|---------|--------|------|------|
| T-020 | backend_coder | - | core.logic (prompts.py): 7 카테고리 프롬프트 추가 (testing, dependencies, security, performance, devops, state_management, data_model). | 대기 |
| T-021 | backend_coder | T-020 | core.logic (analyzer.py): _CATEGORY_ROLES 확장 (7 카테고리별 파일 역할 매핑). | 대기 |
| T-022 | backend_coder | - | core.logic (session.py): SessionDiff 구현 완성 (두 SessionResult 비교 → 변경/추가/삭제 규칙). | 대기 |
| T-023 | backend_coder | T-021 T-022 | interface.cli: --resume 옵션 (session.json 읽어 완료 카테고리 스킵) + diff 서브커맨드 + 7 카테고리/resume/diff 테스트 추가. | 대기 |

### 의존성 그래프
\`\`\`
Phase 1:
  T-001 (models) ─┬─► T-003 (llm)
                  ├─► T-004 (fetcher)
                  ├─► T-006 (prompts)
                  └─► T-008 (session)
  T-002 (errors) ─┤
                  └─► T-003, T-004, T-010

  T-004 ──► T-005 (preprocessor)
  T-003 + T-005 + T-006 ──► T-007 (analyzer)
  T-001 + T-007 + T-008 ──► T-009 (generator)
  T-002 + T-003 + T-007 + T-009 ──► T-010 (cli/skill)
  T-001 + T-004 + T-005 + T-007 + T-008 + T-009 ──► T-011 (tests)

Phase 2:
  T-020 ──► T-021
  T-022 (병렬)
  T-021 + T-022 ──► T-023
\`\`\`

### 병렬 실행 가능 조합
- **즉시 시작 가능**: T-001, T-002 (의존성 없음)
- **T-001 + T-002 완료 후 병렬**: T-003, T-004, T-006, T-008 (4개 동시)
- **T-004 완료 후**: T-005 추가
- **T-007 이후 병렬**: T-008(있었으면), T-009
- **Phase 2 즉시 병렬**: T-020, T-022 (독립)

### 진행 상태
- \`pending\` — 아직 시작 안 함
- \`in-progress\` — \`/ha-build\` 실행 중
- \`done\` — 구현 + 검증 완료
- \`blocked\` — 의존성 미해결 또는 실패 지속

## 10. 구현 노트

> 이 섹션은 `/ha-build`가 구현 중 발견한 것을 기록합니다.
> 설계 시점에 예측 못한 이슈, 의사결정, TODO를 남깁니다.

### 결정 로그
| 날짜 | 태스크 | 결정 | 사유 | 영향 |
|------|--------|------|------|------|
| `<YYYY-MM-DD>` | `<T-XXX>` | <결정 내용> | <사유> | <영향 범위> |

### 트레이드오프 / 타협
- <예: "페이지네이션은 offset 방식 사용. cursor 방식이 더 좋지만 MVP 범위 외.">

### 발견된 엣지 케이스 (skeleton 반영 미완)
- <예: "Unicode 정규화 충돌 — 다음 릴리스에서 `core.logic`에 규칙 추가 예정">

### TODO (이슈 트래커로 이관 예정)
- [ ] <예: 성능: N+1 쿼리 최적화 필요 — issue #42>
- [ ] <예: 테스트: 동시성 테스트 커버리지 확대>

### 의존성 변경
| 날짜 | 패키지 | 변경 | 사유 |
|------|--------|------|------|
| `<YYYY-MM-DD>` | `<pkg>` | `<v1 → v2>` | <사유> |

### 테스트 데이터 / 시드
- `tests/fixtures/senior_wisdom/` — 미니 시니어 레포 픽스처 + `ground_truth.md` 검증 데이터.
