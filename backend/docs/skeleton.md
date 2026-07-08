# Project Skeleton — code-hijack

## 1. 프로젝트 개요

- **프로젝트명**: code-hijack
- **한 줄 설명**: 시니어 코드 스타일을 LLM으로 자동 추출
- **목적**: AI 에이전트가 조잡한 코드를 짜는 문제 해결. 탑 티어 시니어 레포를 LLM으로 분석해 "왜 이렇게 짰는지" 설계 의도까지 담은 규칙 문서(CLAUDE.md + system-prompt.md)를 자동 생성. 에이전트가 해당 레포 스타일로 코드를 짜게 만든다.
- **타겟 사용자**: AI 에이전트로 코드를 작성하는 개인 개발자 (본인 포함). Phase 2에서 팀/회사용 확장.
- **범위**:
  - **Phase 1 (MVP)**: GitHub URL/로컬 경로 입력 → 3개 카테고리(architecture, coding_style, api_design) × 5개 레이어(frontend/backend/db/devops/shared) 분석 → 레이어별 `.md` + CLAUDE.md 진입점 + system-prompt.md 출력. Claude Code skill 모드 + CLI 모드 모두 지원.
  - **Out-of-scope (Phase 2+로 이월)**: 나머지 7개 카테고리, 세션 간 diff, 여러 레포 통합 분석, 언어 확장(Go/Rust), MCP 서버 노출.

<!-- ha-redesign 2026-06-10: Foresight inference layer — affected via /ha-redesign -->
<!-- ha-redesign 2026-06-11: Evidence source expansion + measurement loop — affected via /ha-redesign -->
## 2. 기능 요구사항

### 핵심 기능 (MVP — Phase 1)
- [ ] GitHub URL 또는 로컬 경로를 받아 Python/TypeScript 소스 파일을 수집한다
- [ ] 휴리스틱 + LLM 협업으로 분석할 핵심 파일을 선별한다
- [ ] 3개 카테고리(architecture, coding_style, api_design) × 5개 레이어(frontend/backend/db/devops/shared) 분석을 수행한다
- [ ] 각 규칙에 참조 파일, ✅/❌ 예시 코드, 우선순위(MUST/SHOULD), **3-tier rationale 등급(cited/corroborated/speculative)** 을 태깅한다
  - `cited`: evidence 가 코드에서 verbatim 인용 가능한 수준
  - `corroborated`: 독립 코드 신호 2개 이상이 일관적으로 뒷받침
  - `speculative`: 그 외 LLM 추론 기반
  - `cited` tier 인 규칙만 MUST 유지 가능. `corroborated`/`speculative` MUST 는 SHOULD 로 자동 강등 (데이터 정규화 시점 적용)
- [ ] **negative-space 신호 추출**: 레포에서 의도적 절제 패턴 4종을 결정론적으로 추출한다 (의존성 절제, public API surface, deprecation 흔적, 경계 규율)
- [ ] **foresight 가설 카드 생성**: LLM이 "왜 이렇게 짰는지"를 추론한 `ForesightCard` 목록을 세션당 `foresight.md` 1개 파일로 저장한다. inferred foresight 는 강제 아닌 고려 사항.
- [ ] **레포 성격 판별**: 결정론 함수로 레포를 `app/cli` / `app` / `library` 로 분류, generator 출력 헤더에 맥락 명시
- [ ] 대상 레포의 `docs/hijacked/` 하위에 세션별 raw 분석 + 통합 CLAUDE.md/system-prompt.md + `foresight.md` 를 저장한다
- [ ] **PR/issue 마이닝**: 대상 레포의 closed-unmerged PR, wontfix 라벨 issue, PR 리뷰 코멘트를 `gh api` CLI 로 수집해 거절/취소된 결정 패턴을 evidence chain 에 추가한다. rejection/incident intent_kind 의 실제 공급 경로.
- [ ] **세션 측정**: `code-hijack measure` 서브커맨드로 단일 세션의 cited 비율 / MUST 비율 / tier 분포 / intent_kind 분포를 산출하고 `measurement.json` 에 저장한다
- [ ] **세션 비교 측정**: 두 세션의 위 지표를 diff 비교해 개선/회귀 여부를 수치로 확인한다
- [ ] **foresight 정답률 채점**: 세션의 ForesightCard 가설·신호를 대상 레포 docs 및 PR/issue 답변과 대조해 confirmed/unconfirmed/refuted 채점 결과를 `measurement.json` 에 저장한다

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

#### `code-hijack measure <session.json> [session2.json]`

```
사용법: code-hijack measure SESSION1 [SESSION2]

인자:
  SESSION1    session.json 또는 세션 디렉토리 (필수)
  SESSION2    session.json 또는 세션 디렉토리 (선택 — 지정 시 SESSION1과 비교)

동작:
  SESSION2 없음: SESSION1 지표 산출 + measurement.json 저장 + stdout 요약 출력
  SESSION2 있음: 두 세션 지표 산출 + diff_sessions 결과 stdout 출력

출력 파일:
  <SESSION1 디렉토리>/measurement.json  — MeasurementResult JSON

예시:
  code-hijack measure docs/hijacked/2026-04-17_fastapi/session.json
  → cited_ratio, must_ratio, tier_distribution 등 측정 결과 출력
  → docs/hijacked/2026-04-17_fastapi/measurement.json 생성

  code-hijack measure docs/hijacked/2026-04-17_v1/session.json \
                      docs/hijacked/2026-04-17_v2/session.json
  → 두 세션 간 cited_ratio_delta, must_ratio_delta 등 비교 출력

에러:
  exit 0: 성공
  exit 2: 인자 누락 / session.json 없음 / 파싱 실패
```

### 서브커맨드 그룹
`analyze`, `diff`, `measure`, `apply` 서브커맨드 그룹으로 운영.

### 출력 형식
- 기본: 사람이 읽는 텍스트 (click.echo, 필요 시 색상). 진행률은 stderr에 짧게.
- 에러: stderr. 최종 출력 파일 경로 및 요약은 stdout.
- `--json` 옵션: 현재 없음 (Phase 2 검토).

### Skill 모드
- `/code-hijack <target>` — `skill.py` 엔트리를 통해 현재 Claude Code 세션의 컨텍스트로 실행.
- `--model` 옵션 불필요 (세션 모델 사용).
- API 호출 대신 세션 내 LLM 사용 → 추가 비용 없음.

<!-- ha-redesign 2026-06-10: Foresight inference layer — affected via /ha-redesign -->
<!-- ha-redesign 2026-06-11: Evidence source expansion + measurement loop — affected via /ha-redesign -->
## 7. 도메인 로직

### 핵심 비즈니스 규칙
1. 분석 파이프라인은 **Fetcher → Preprocessor → Analyzer → Generator** 순서. 각 단계는 독립 테스트 가능.
2. `core/`의 모든 함수는 순수 — 파일/네트워크 I/O 금지. I/O는 `io/` 또는 어댑터 계층에서만.
3. LLM 호출은 **반드시 `BaseLLM` 인터페이스를 거친다**. 테스트에서 `AsyncMock`으로 대체 가능.
4. 레이어 태깅은 결정론적 — 경로/확장자/의존성 파일(package.json, pyproject.toml) 기반 감지 함수로. LLM이 추측하지 않는다.
5. LLM이 반환한 규칙 중 필수 필드(`rule`, `priority`, `layer`) 누락 시 해당 규칙 드롭 + 경고. 카테고리 전체는 유효.
6. `dataclass` only — Pydantic 금지. 직렬화는 `to_json` / `from_json` 수동 구현.
7. 윈도우/macOS/리눅스 호환 — 경로 비교는 `Path.as_posix()` 사용, `str(path)` 금지.
8. **rationale_tier 정규화**: 분석 파싱 직후 정규화 단계에서, `corroborated`/`speculative` tier 의 `MUST` 규칙은 `SHOULD` 로 강등. `cited` tier 만 `MUST` 유지 가능. 이 정규화는 generator 렌더링 이전, `AnalysisRule` 객체 생성 직후에 적용해 객체 정합성 보장.
9. **negative_space 추출**: `negative_space.py` 는 보조 신호 추출기 (archaeology.py 와 동일 역할 분담). stdlib(ast, pathlib, re) 만 사용. 추출 결과는 `NegativeSpaceResult` dataclass. Skill 모드와 CLI 모드 양쪽에서 소비.
10. **레포 성격 판별**: preprocessor 의 결정론 함수 `detect_repo_nature` 가 `"app/cli"` / `"app"` / `"library"` 셋 중 하나 반환. 판별 기준: `[project.scripts]`/entry_points 존재 → `"app/cli"`, frontend 레이어 파일 존재 → `"app"`, 그 외 → `"library"`.
11. **ForesightCard 는 강제 아닌 고려 사항**: generator 가 `foresight.md` 를 렌더링할 때, 카드의 tier 가 `speculative` 이면 "강제 아님" 표시. system-prompt 에서 foresight 카드는 제약이 아닌 고려 사항으로 기술.
12. **PR/issue 마이닝**: `pr_archaeology.py` (impure — gh CLI subprocess) 가 closed-unmerged PR, wontfix issue, PR 리뷰 코멘트를 수집. archaeology.py 의 `_DECISION_PATTERNS` 정규식 재사용 (import — 중복 정의 금지). gh CLI 부재/인증 실패/rate-limit/타임아웃 → logger.warning + 빈 결과 (graceful skip). 결과(`PRDecisions`)는 commit_decisions 와 병렬로 evidence chain(SKILL step 3.5) + foresight 삼각측량(step 3.7) 소스에 합류.
13. **측정 루프**: `core/measure.py` (순수 지표 계산 + measurement.json I/O) 가 세션 지표 산출, 세션 간 비교, foresight 채점 결과 저장을 담당. LLM 판단이 필요한 채점 부분은 skill 모드 워크플로우에 위임하고 measure.py 는 결정론 지표 + 채점 결과 저장만 수행.

### 데이터 모델 확장 (Foresight inference layer)

#### `AnalysisRule` 확장 필드
```python
@dataclass
class AnalysisRule:
    # 기존 필드 유지
    rule: str
    priority: str          # "MUST" | "SHOULD"
    layer: str
    reason: str            # 자유문자열, 유지
    evidence: list[str]
    # 신규 필드
    rationale_tier: str    # "cited" | "corroborated" | "speculative" (기본값: "speculative")
```
- `from_json` 역직렬화 시 `rationale_tier` 키 없으면 기본값 `"speculative"` (하위 호환).
- 판정 기준: evidence 가 verbatim cited → `"cited"`, 독립 코드 신호 2개 이상 일관 → `"corroborated"`, 그 외 → `"speculative"`.

#### `ForesightCard` (신규 dataclass, `models.py` 추가)
```python
@dataclass
class ForesightCard:
    hypothesis: str        # "왜 이렇게 짰는지" LLM 추론 가설
    signals: list[str]     # 뒷받침하는 검증된 사실 목록 (각 항목은 구체 파일/패턴 레퍼런스)
    falsification: str     # 이 가설이 틀렸음을 보여줄 조건
    tier: str              # "corroborated" | "speculative" (cited 이면 일반 rule evidence 영역)
    layer: str
```
- `ForesightCard` 는 `foresight.md` 에만 출력. 일반 규칙 문서(`CLAUDE.md`, system-prompt.md)에는 포함되지 않음.

#### `SessionResult` 확장
```python
@dataclass
class SessionResult:
    # 기존 필드 유지
    ...
    # 신규 필드
    foresight_cards: list[ForesightCard] = field(default_factory=list)  # 기본 빈 리스트
    repo_nature: str = "library"  # "app/cli" | "app" | "library"
```
- `from_json` 에서 `foresight_cards` 없으면 빈 리스트, `repo_nature` 없으면 `"library"` (하위 호환).

#### `NegativeSpaceResult` (`negative_space.py` 에 정의)
```python
@dataclass
class NegativeSpaceResult:
    dep_count: int                    # 런타임 의존성 수
    direct_impl_hints: list[str]      # stdlib 로 직접 구현한 흔적 (파일 경로)
    public_ratio: float               # underscore-prefix 없는 public 심볼 비율
    has_all_discipline: bool          # __all__ 정의 여부
    deprecation_patterns: list[str]   # DeprecationWarning 추가/제거 패턴 요약
    layer_import_violations: list[str] # 레이어 간 역방향 import (기존 detect_layer 결과 소비)
```

#### `PRDecision` / `PRDecisions` (`pr_archaeology.py` 에 정의 — archaeology.py 의 CommitDecision/CommitDecisions 와 동형)
```python
@dataclass
class PRDecision:
    """단일 PR/issue 에서 추출한 결정 신호."""
    ref: str              # "PR#123" 또는 "issue#456"
    title: str            # PR/issue 제목
    date: str             # ISO 날짜 ("2024-08-12 14:30:00 +0900" 형식 유지)
    body_excerpt: str     # PR/issue 본문 첫 _BODY_EXCERPT_CHARS 자, 공백 정규화
    matched_patterns: list[str]  # 매칭된 패턴 display name 목록; sorted asc
    maintainer_comment: str      # 메인테이너 마지막 코멘트 요약 (빈 문자열 허용)
    intent_kind: str      # "rejection" | "incident" | "preference" — 하위 intent 분류
    diff_excerpt: str = ""       # rejection/incident PR 의 실제 diff 발췌 (≤1500자, 빈 문자열 허용)

    def to_json(self) -> dict[str, Any]: ...
    @classmethod
    def from_json(cls, data: dict[str, Any]) -> PRDecision: ...

@dataclass
class PRDecisions:
    """대상 레포 PR/issue 마이닝 집계 결과."""
    __test__ = False

    items_scanned: int             # 조사한 PR/issue 수
    patterns: list[DecisionPattern]  # archaeology.py 의 DecisionPattern 재사용; count desc
    decisions: list[PRDecision]      # date desc; capped at 50

    def to_json(self) -> dict[str, Any]: ...
    @classmethod
    def from_json(cls, data: dict[str, Any]) -> PRDecisions: ...

    @property
    def has_signal(self) -> bool: ...
```
- `archaeology.py` 의 `_DECISION_PATTERNS` / `_COMPILED_PATTERNS` / `DecisionPattern` 을 import 해 재사용. 중복 정의 금지.
- intent_kind 매핑: closed-unmerged PR + 메인테이너 거절 코멘트 → `"rejection"`, revert/rollback 언급 issue → `"incident"`, 그 외 → `"preference"`.

#### `MeasurementResult` (`measure.py` 에 정의)
```python
@dataclass
class MeasurementResult:
    """단일 세션 측정 결과."""
    session_id: str
    cited_ratio: float           # cited 규칙 수 / 전체 규칙 수
    must_ratio: float            # MUST 규칙 수 / 전체 규칙 수
    tier_distribution: dict[str, int]   # {"cited": N, "corroborated": N, "speculative": N}
    intent_kind_distribution: dict[str, int]  # {"rejection": N, "incident": N, "preference": N}
    foresight_scores: list[dict[str, str]]    # [{"hypothesis": ..., "verdict": "confirmed"|"unconfirmed"|"refuted"}]

    def to_json(self) -> dict[str, Any]: ...
    @classmethod
    def from_json(cls, data: dict[str, Any]) -> MeasurementResult: ...
```
- `measurement.json` 은 세션 디렉토리 내 저장. `session.json` 스키마 재확장 금지.

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

#### `detect_repo_nature` (preprocessor.py 에 추가)
- **입력**: `pyproject_toml: dict | None`, `detected_layers: set[str]`
- **출력**: `Literal["app/cli", "app", "library"]`
- **판별 로직**:
```
if pyproject_toml has [project.scripts] or entry_points: return "app/cli"
if "frontend" in detected_layers: return "app"
return "library"
```
- **복잡도**: `O(1)`

#### `extract_negative_space` (negative_space.py — 순수 함수들의 집합)
- **입력**: `repo_root: Path`, `py_files: list[Path]`, `pyproject_toml: dict | None`, `layer_map: dict[Path, str]`
- **출력**: `NegativeSpaceResult`
- **추출 신호 4종** (모두 stdlib: ast, pathlib, re):
  1. **의존성 절제**: `pyproject_toml` 의 `[project.dependencies]` 배열 길이 → `dep_count`. `ast.parse` 로 stdlib-only 패턴 파일 탐색 → `direct_impl_hints`.
  2. **public API surface**: `ast.parse` 로 모듈별 `_` prefix 심볼 vs 전체 심볼 비율 → `public_ratio`. `__all__` 존재 여부 → `has_all_discipline`.
  3. **deprecation 흔적**: `re` 로 `DeprecationWarning` 패턴 스캔 → `deprecation_patterns` 요약 문자열 리스트 (git history 읽기는 별도 I/O 함수 `read_deprecation_history(repo_root)` 로 분리).
  4. **경계 규율**: `ast` import 분석 + `layer_map` (기존 `detect_layer` 결과) → 역방향 import → `layer_import_violations`.
- **순수/I/O 분리**: AST 분석·경로 분석·비율 계산 = 순수. git history 읽기 (`read_deprecation_history`) = I/O (별도 함수, `core/fetcher.py` 또는 `negative_space.py` 말미에 분리 표시).

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
- `models.py`: 데이터 모델 (`AnalysisRule`, `CategoryResult`, `SessionResult`, `ForesightCard`, `NegativeSpaceResult`) + `to_json` / `from_json`
- `preprocessor.py`: 역할 분류, 2D(role×layer) 분류, 구조 맵 생성, `detect_repo_nature` — 순수 함수
- `prompts.py`: 카테고리별 프롬프트 빌더 — 순수 문자열 조립
- `analyzer.py` 의 파싱 함수 (`parse_json`, `parse_regex_fallback`), `normalize_rationale_tier` (MUST 강등 정규화) — LLM 호출부는 impure로 분리
- `session.py` 의 ID 생성/diff 로직 — 순수
- `negative_space.py` 의 AST/경로/비율 분석 함수 (`extract_negative_space`, `_calc_public_ratio`, `_find_direct_impls`, `_find_layer_violations`) — 순수 [stdlib: ast, pathlib, re]
- `measure.py` 의 지표 산출 함수 (`calc_session_metrics`, `diff_sessions`, `score_foresight`) — 순수. `write_measurement` (measurement.json 저장) 는 I/O 이므로 분리.

**impure (파이프라인 진입/출력 레이어)** — 파일/네트워크:
- `core/fetcher.py`: 레포 클론 (`git` subprocess) + 파일 수집 [FS/NET]
- `core/analyzer.py` 의 `run_full_analysis`: LLM 호출 [NET]
- `core/generator.py`: `write_output` 파일 저장 (레이어별 .md + CLAUDE.md + system-prompt.md + foresight.md) [FS]
- `core/session.py` 의 `get_output_dir`: 디렉토리 생성 [FS]
- `core/negative_space.py` 의 `read_deprecation_history`: git history 읽기 [FS/subprocess]
- `core/pr_archaeology.py`: gh CLI subprocess 로 PR/issue 수집 [NET/subprocess] — gh 부재/인증 실패/rate-limit/타임아웃 → logger.warning + 빈 `PRDecisions` (graceful skip). `_DECISION_PATTERNS` 는 archaeology.py 에서 import.
- `core/measure.py` 의 `write_measurement`: measurement.json 파일 저장 [FS]
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

<!-- ha-redesign 2026-06-11: Evidence source expansion + measurement loop — affected via /ha-redesign -->
## 8. 외부 통합

### 3rd Party API
| 서비스 | 목적 | 인증 방식 | 요금제 |
|--------|------|----------|--------|
| Anthropic Claude API | 카테고리별 LLM 분석 | API key (env: `ANTHROPIC_API_KEY`) | pay-as-you-go (사용자가 `--model` 로 비용 제어) |
| GitHub (공개 레포) | `git clone` 으로 클론 | 공개 레포는 인증 불필요. 사설 레포는 Phase 2 검토 | 무료 |
| GitHub API (gh CLI) | PR/issue 마이닝 (`pr_archaeology.py`) — closed-unmerged PR, wontfix issue, PR 리뷰 코멘트 수집 | gh CLI 자체 인증 위임 (`gh auth login`). `ANTHROPIC_API_KEY` 와 별개. | GitHub 공개 API 무료 (rate limit: 5,000 req/hr 인증 시) |

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
- **gh CLI (PR/issue 마이닝)**:
  - gh CLI 미설치: `logger.warning` + 빈 `PRDecisions` 반환. 분석 파이프라인은 commit 마이닝만으로 계속 진행 (동작 저하 수용).
  - 인증 실패 (`gh auth status` 실패): 동일하게 graceful skip. 새 에러 코드 불필요.
  - Rate limit (HTTP 429/403): 동일하게 graceful skip + 경고.
  - 타임아웃 (subprocess timeout): 동일하게 graceful skip + 경고.
  - 원칙: negative_space.py 의 `read_deprecation_history` graceful skip 과 동일 패턴.

### Rate Limit
- Anthropic: 모델별 RPM/TPM 한도 → 429 에러 시 `LLM_002` 로 묶어 재시도. 사용자에게 "잠시 후 재실행" 안내.
- GitHub: 공개 레포 클론은 실무상 제한 없음 (Phase 1 기준).
- GitHub API (gh CLI): 인증 상태에서 5,000 req/hr. 마이닝 쿼리는 수십 건 이내 — 실무상 문제 없음. 429 수신 시 graceful skip.

## 9. 태스크 분해

### Phase 1 — MVP (3 카테고리 × 5 레이어, CLI + Skill)
| ID | 에이전트 | 의존성 | 설명 | 상태 |
|----|---------|--------|------|------|
| T-001 | backend_coder | - | core.logic (models.py): AnalysisRule/CategoryResult/SessionResult @dataclass + to_json/from_json. layer 필드 포함. [2026-06-10: T-030 이 rationale_tier·ForesightCard·foresight_cards·repo_nature 확장 흡수] | 대기 |
| T-002 | backend_coder | - | errors + configuration: HijackError(ClickException) 계층 (Input/Fetch/LLM/Output) + 에러 코드 상수 + backend/.env.example 생성. | 대기 |
| T-003 | backend_coder | T-001 T-002 | core.logic (llm/base.py, llm/api.py): BaseLLM ABC (analyze 추상) + ClaudeAPIClient (anthropic SDK, asyncio.to_thread 래핑, 기본 모델 claude-sonnet-4-6, ANTHROPIC_API_KEY 로드). | 대기 |
| T-004 | backend_coder | T-001 T-002 | core.logic (fetcher.py): SourceFile + fetch_source (로컬 경로 + git clone), 파일 수집 + _SKIP_DIRS 제외 + detect_layer (frontend/backend/db/devops/shared). | 대기 |
| T-005 | backend_coder | T-001 T-004 | core.logic (preprocessor.py): 역할 분류 (entry_point/model/api/test/config/...), 2D(role×layer) 분류, PreprocessResult, build_file_summary_for_llm. | 대기 |
| T-006 | backend_coder | T-001 | core.logic (prompts.py): MVP 3 카테고리 프롬프트 (architecture, coding_style, api_design) + 레이어별 섹션 출력 지시 + MVP_CATEGORIES 상수. [2026-06-10: T-034 이 foresight 가설 프롬프트 추가 흡수] | 대기 |
| T-007 | backend_coder | T-003 T-005 T-006 | core.logic (analyzer.py): run_full_analysis, 카테고리별 LLM 호출, JSON 파싱 + regex 폴백, 최대 2회 재시도, 레이어 파싱. [2026-06-10: T-033 이 normalize_rationale_tier MUST 강등 정규화 흡수] | 대기 |
| T-008 | backend_coder | T-001 | core.logic (session.py): create_session_id (YYYY-MM-DD_<repo>), get_output_dir, SessionDiff (Phase 2 stub). | 대기 |
| T-009 | backend_coder | T-001 T-007 T-008 | core.logic (generator.py): 레이어별 .md 분리 렌더러 (frontend/backend/database/devops/shared) + CLAUDE.md 진입점 + system-prompt.md + write_output (세션별 raw + integrated). [2026-06-10: T-034 이 foresight.md 렌더 + 성격 헤더 + system-prompt 맥락 조건부 톤 흡수] | 대기 |
| T-010 | backend_coder | T-002 T-003 T-007 T-009 | interface.cli (cli.py, skill.py): click 진입점 + --model/--path/--categories/--output/--dry-run/-v/-q, skill 엔트리, 비용 추정 + 사용자 확인 흐름. | 대기 |
| T-011 | backend_coder | T-001 T-004 T-005 T-007 T-008 T-009 | core.logic (tests): test_models/fetcher/preprocessor/analyzer/generator/session + tests/fixtures/senior_wisdom/ 복원 (ground_truth.md 5 규칙 레이어 검증). [2026-06-10: T-030~T-034 각 태스크가 자체 테스트 포함 — T-011 범위 외] | 대기 |

### Phase 2 — 확장 (7 카테고리 + 세션 관리)
| ID | 에이전트 | 의존성 | 설명 | 상태 |
|----|---------|--------|------|------|
| T-020 | backend_coder | - | core.logic (prompts.py): 7 카테고리 프롬프트 추가 (testing, dependencies, security, performance, devops, state_management, data_model). | 대기 |
| T-021 | backend_coder | T-020 | core.logic (analyzer.py): _CATEGORY_ROLES 확장 (7 카테고리별 파일 역할 매핑). | 대기 |
| T-022 | backend_coder | - | core.logic (session.py): SessionDiff 구현 완성 (두 SessionResult 비교 → 변경/추가/삭제 규칙). | 대기 |
| T-023 | backend_coder | T-021 T-022 | interface.cli: --resume 옵션 (session.json 읽어 완료 카테고리 스킵) + diff 서브커맨드 + 7 카테고리/resume/diff 테스트 추가. | 대기 |

<!-- ha-redesign 2026-06-10: Foresight inference layer — affected via /ha-redesign -->
### Phase 3 — Foresight inference layer
| ID | 에이전트 | 의존성 | 설명 | 상태 |
|----|---------|--------|------|------|
| T-030 | backend_coder | - | core.logic (models.py): AnalysisRule 에 `rationale_tier: str` 필드 추가 + `ForesightCard` dataclass 추가 + `SessionResult` 에 `foresight_cards: list[ForesightCard]` / `repo_nature: str` 필드 추가 + `from_json` 기본값 처리 (구버전 하위 호환) + 단위 테스트. | 대기 |
| T-031 | backend_coder | T-030 | core.logic (negative_space.py): 신규 모듈. `NegativeSpaceResult` dataclass + `extract_negative_space(repo_root, py_files, pyproject_toml, layer_map) → NegativeSpaceResult` (순수, stdlib 전용: ast/pathlib/re). 4종 신호 추출: (a) 의존성 절제 — pyproject dependencies 수 + ast로 직접구현 흔적, (b) public API surface — underscore prefix 비율 + __all__ 규율, (c) deprecation 흔적 — re로 DeprecationWarning 패턴 스캔 (git history 읽기는 `read_deprecation_history(repo_root)` I/O 함수로 분리), (d) 경계 규율 — ast import + layer_map 역방향 import 탐지. 단위 테스트 포함. | 대기 |
| T-032 | backend_coder | T-030 | core.logic (preprocessor.py): `detect_repo_nature(pyproject_toml, detected_layers) → Literal["app/cli","app","library"]` 순수 함수 추가. 판별: [project.scripts]/entry_points 존재 → "app/cli", "frontend" in detected_layers → "app", 그 외 → "library". `PreprocessResult` 에 `repo_nature` 필드 추가. 단위 테스트 포함. | 대기 |
| T-033 | backend_coder | T-030 | core.logic (analyzer.py): `normalize_rationale_tier(rules: list[AnalysisRule]) → list[AnalysisRule]` 순수 함수 추가. 로직: `rationale_tier` 가 `"corroborated"` 또는 `"speculative"` 이고 `priority == "MUST"` 인 경우 `priority = "SHOULD"` 로 강등. 정규화 시점은 파싱 직후 `run_full_analysis` 내에서 `CategoryResult` 생성 전 호출 (generator 렌더 시점 아님). 단위 테스트: cited-MUST 유지, corroborated-MUST→SHOULD, speculative-MUST→SHOULD 케이스. | 대기 |
| T-034 | backend_coder | T-030,T-032 | core.logic (generator.py): (1) `render_foresight_md(cards: list[ForesightCard]) → str` 순수 렌더러 추가 — tier별 섹션 구분, speculative 카드에 "강제 아님" 표시. (2) `write_output` 에서 `foresight.md` 를 세션별 raw + integrated/ 에 복사. (3) 출력 파일 헤더에 "이 규칙들은 `<repo_nature>` 맥락에서 추출됨" 명시. (4) system-prompt.md 의 "MUST rules are non-negotiable" 류 문구 → "MUST 규칙은 추출 맥락(레포 성격 헤더 참조)이 성립할 때 적용. 맥락이 다르면 일탈 가능하되 이유 명시. corroborated/speculative rationale 규칙과 foresight 카드는 강제 아닌 고려 사항." 단위 테스트: foresight.md 렌더 출력 구조 + system-prompt 톤 검증. | 대기 |
| T-035 | backend_coder | T-031,T-032,T-033,T-034 | `.claude/skills/code-hijack/SKILL.md` Skill 모드 워크플로우 갱신. (1) negative_space 추출 단계 추가 (Fetcher 이후, Analyzer 이전). (2) foresight 가설 생성 절차 — LLM이 `NegativeSpaceResult` 신호를 보고 `ForesightCard` 목록 생성, tier 자가 판정. (3) 삼각측량 절차 — 각 ForesightCard 의 `signals` 가 `NegativeSpaceResult` 신호와 교차 검증되는지 확인. (4) 레포 성격 헤더를 출력 파일에 포함하는 단계 명시. | 대기 |

<!-- ha-redesign 2026-06-11: Evidence source expansion + measurement loop — affected via /ha-redesign -->
### Phase 4 — Evidence source expansion + measurement loop
| ID | 에이전트 | 의존성 | 설명 | 상태 |
|----|---------|--------|------|------|
| T-036 | backend_coder | - | core.logic (pr_archaeology.py): 신규 모듈 (impure). `PRDecision`/`PRDecisions` dataclass 자체 정의 (CommitDecision/CommitDecisions 와 동형 필드 — 상세 스키마는 §7 데이터 모델 참조). `_DECISION_PATTERNS`/`_COMPILED_PATTERNS`/`DecisionPattern` 은 archaeology.py 에서 import (중복 정의 금지). gh CLI subprocess 로 수집: (a) closed-unmerged PR 제목/본문/메인테이너 마지막 코멘트, (b) wontfix 등 거절 라벨 issue 본문/메인테이너 답변, (c) 결정 패턴 매칭 PR 리뷰 코멘트. intent_kind 매핑: closed-unmerged PR + 메인테이너 거절 코멘트 → "rejection", revert/rollback 언급 issue → "incident", 그 외 → "preference". gh CLI 부재/인증 실패/rate-limit/타임아웃 → logger.warning + 빈 PRDecisions 반환 (graceful skip — negative_space.read_deprecation_history 와 동일 원칙). 단위 테스트: gh 호출은 subprocess mock 처리. | 대기 |
| T-037 | backend_coder | - | core.logic (measure.py): 신규 모듈. 순수 함수: (a) `calc_session_metrics(session: SessionResult) → MeasurementResult` — cited 비율/MUST 비율/tier 분포/intent_kind 분포 산출. (b) `diff_sessions(m1: MeasurementResult, m2: MeasurementResult) → dict` — 두 세션 지표 diff (기존 diff 인프라 재사용 가능하면 재사용). (c) `score_foresight(cards: list[ForesightCard], repo_docs: str, pr_decisions: PRDecisions) → list[dict]` — 카드별 confirmed/unconfirmed/refuted 채점 (결정론 지표만, LLM 판단 부분은 skill 모드 위임). I/O 함수: `write_measurement(result: MeasurementResult, session_dir: Path) → None` — 세션 디렉토리 내 `measurement.json` 저장 (session.json 스키마 재확장 금지, stdout 전용 금지). `MeasurementResult` dataclass 도 이 모듈에 정의 (§7 데이터 모델 참조). 단위 테스트: 순수 함수 전부 커버. | 대기 |
| T-038 | backend_coder | T-037 | interface.cli (cli.py): `measure` 서브커맨드 추가 (diff 서브커맨드와 동일 패턴). 서브커맨드 배선: (a) `code-hijack measure <session.json>` — 단일 세션 지표 산출 + stdout 요약 + measurement.json 저장. (b) `code-hijack measure <session1.json> <session2.json>` — 두 세션 지표 diff. §6 CLI 커맨드 섹션 갱신 (measure 서브커맨드 등재). 단위 테스트: click CliRunner 로 커맨드 호출 + 출력 검증. | 대기 |
| T-039 | backend_coder | T-036,T-037 | `.claude/skills/code-hijack/SKILL.md` 갱신. (1) step 1 수집 단계에 `pr_decisions` 추가 — `fetch_pr_decisions(repo_url)` 호출, gh CLI 없으면 빈 PRDecisions 로 계속. (2) step 3.5 evidence chain 소스에 `pr_decisions` 합류 — commit_decisions 와 병렬 소스로 명시. (3) step 3.7 foresight 삼각측량에 `pr_decisions` 소스 추가 — rejection/incident 카드 우선 검증. (4) foresight 채점 절차 추가 — `score_foresight` 호출 후 LLM 이 unconfirmed 카드 보완 판단, 최종 verdict 를 measure.py 에 전달해 measurement.json 에 저장. | 대기 |

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

Phase 3 (Foresight inference layer):
  T-030 (models 확장) ─┬─► T-031 (negative_space — 병렬 가능)
                        ├─► T-032 (detect_repo_nature — 병렬 가능)
                        ├─► T-033 (normalize_rationale_tier)
                        └─► T-034 (generator foresight+톤, T-032 도 의존)
  T-031 + T-032 + T-033 + T-034 ──► T-035 (SKILL.md 갱신)

Phase 4 (Evidence source expansion + measurement loop):
  T-036 (pr_archaeology) 병렬 가능 (의존성 없음)
  T-037 (measure.py)     병렬 가능 (의존성 없음)
  T-037 ──► T-038 (cli measure 서브커맨드)
  T-036 + T-037 ──► T-039 (SKILL.md 갱신)
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

<!-- ha-redesign 2026-06-10: Foresight inference layer — affected via /ha-redesign -->
<!-- ha-redesign 2026-06-11: Evidence source expansion + measurement loop — affected via /ha-redesign -->
## 10. 구현 노트

> 이 섹션은 `/ha-build`가 구현 중 발견한 것을 기록합니다.
> 설계 시점에 예측 못한 이슈, 의사결정, TODO를 남깁니다.

### 결정 로그
| 날짜 | 태스크 | 결정 | 사유 | 영향 |
|------|--------|------|------|------|
| `<YYYY-MM-DD>` | `<T-XXX>` | <결정 내용> | <사유> | <영향 범위> |
| `2026-06-10` | `T-030~T-035` | Foresight inference layer: rationale 3-tier 등급(cited/corroborated/speculative) + 별도 foresight.md 가설 카드 산출물 + 결정론적 negative-space 신호 추출기; inferred foresight 는 MUST 불가(cited-only MUST); system-prompt 톤을 non-negotiable → context-conditional 로 변경 | 사용자 피드백 2026-06-10: 도구가 "왜 이렇게 짰는지" 설계 의도(foresight/negative space)를 미포착, 과도 강제. 시니어 없이도 LLM 이 가설을 정직하게 등급 매겨 삼각측량 | §2 요구사항, §7 도메인 로직(모델/알고리즘/pure-impure 표), §9 태스크(T-030~T-035 신규), §10 결정 로그 |
| `2026-06-11` | `T-036~T-039` | Evidence source expansion + measurement loop: (1) PR/issue 마이닝 via gh CLI (`pr_archaeology.py`) — closed-unmerged PR / wontfix issue 에서 rejection/incident intent_kind 공급. (2) 측정 루프 (`core/measure.py` + `code-hijack measure` CLI 서브커맨드) — cited 비율/MUST 비율/tier 분포/intent_kind 분포 + foresight 정답률 채점 + `measurement.json` 저장. | Starlette foresight E2E 2026-06-11: intent_kind diversity 0 — commit-mining ceiling. Rejected PR/wontfix issue 가 시니어 판단의 가장 밀도 높은 소스. 외부 평가 여전히 수동 — 개선을 숫자로 확인하는 측정 루프 필요. | §2 기능 요구사항(PR 마이닝 + 측정 항목), §7 도메인 로직(PRDecision/PRDecisions/MeasurementResult 모델 + pr_archaeology.py/measure.py pure-impure 표 등재), §8 외부 통합(gh CLI 항목 + 실패 대응), §9 태스크(T-036~T-039 신규 + 의존성 그래프 Phase 4), §10 결정 로그 |

### 트레이드오프 / 타협
- AnalysisRule 에 `rationale_tier` 필드 추가는 session.json 스키마 확장. `from_json` 기본값 `"speculative"` 으로 하위 호환 유지. 단, 구세션(rationale_tier 없음)과 신세션(rationale_tier 있음)을 `code-hijack diff` 로 비교할 때 tier 비교는 무의미함 — 구세션 결과는 모두 `"speculative"` 로 취급되므로 diff 보고서에 "구세션은 tier 비교 불가" 경고를 명시할 것.
- negative_space 추출 4종 중 deprecation 흔적(git history 패턴)은 I/O 함수(`read_deprecation_history`) 로 분리 — git 이 없는 로컬 경로(압축 해제 디렉토리 등)에서 호출 시 graceful skip + 경고 처리 필요.
- gh CLI 는 외부 도구 의존 (필수 아님) — 없으면 commit 마이닝만으로 동작 저하 수용. 새 에러 코드 불필요. pr_archaeology.py 전체가 graceful skip 경로.
- 측정 채점(`score_foresight`)의 LLM 판단 부분은 skill 모드 워크플로우 책임. `measure.py` 는 결정론 지표 + skill 이 전달한 채점 결과 저장만 담당 (순수/I/O 경계 유지).

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
