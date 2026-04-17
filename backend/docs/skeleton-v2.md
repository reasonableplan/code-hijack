# Project Skeleton — code-hijack (v2 PoC)

## 1. 프로젝트 개요

- **프로젝트명**: <PROJECT_NAME>
- **한 줄 설명**: <ONE_LINE_DESCRIPTION>
- **목적**: <WHY — 어떤 문제를 해결하는가>
- **타겟 사용자**: <WHO — 누가 쓰는가>
- **범위**: <SCOPE — 이 버전에서 다루는 것/다루지 않는 것>

> 작성 가이드:
> - 한 줄 설명은 25자 이내. 기술 용어 금지.
> - 목적은 사용자 관점 문제 정의. 구현 방법 아님.
> - 타겟 사용자는 구체적 페르소나. "모두" 금지.

## 2. 기술 스택

### 런타임 / 언어
- <예: Python 3.12 / Node.js 20 / Rust 1.75>

### 프레임워크 / 주요 라이브러리
- <예: FastAPI, SQLAlchemy / React 19, Vite>

### 빌드 / 패키지 관리
- <예: uv / pnpm / cargo>

### 테스트
- <예: pytest + httpx / vitest / cargo test>

### 린트 / 포맷 / 타입체크
- <예: ruff + pyright / eslint + tsc>

### 허용 라이브러리 화이트리스트
> 프로파일의 `whitelist.runtime/dev` 에서 가져온다. 여기는 프로젝트 특화 추가만 명시.

**추가 허용 (프로파일 기본 + 이 목록)**:
- <패키지 이름>: <사유>

> 작성 가이드:
> - 프로파일 화이트리스트와 중복 나열 금지 — 오직 프로젝트 특화 추가만.
> - 각 추가는 반드시 사유 (왜 필요한가) 명시.

## 3. 에러 핸들링

### 에러 분류 체계
프로젝트에서 발생할 수 있는 에러 범주 + 식별 코드.

| 코드 | 의미 | 발생 조건 |
|------|------|----------|
| `<DOMAIN>_NNN` | <한 줄 설명> | <언제 던지는가> |

### 에러 전달 방식
이 프로젝트가 **외부로 에러를 전달하는 형식**. 인터페이스 타입에 따라 다름:

- **HTTP 서버**: HTTP 상태 코드 + JSON 래퍼 (세부 규격은 `interface.http` 섹션)
- **CLI**: `stderr` + exit code (세부 규격은 `interface.cli` 섹션)
- **IPC 채널**: Main→Renderer 에러 메시지 포맷 (세부 규격은 `interface.ipc` 섹션)
- **Library/SDK**: 커스텀 예외 raise (세부 규격은 `interface.sdk` 섹션)

### 예외/에러 계층
언어 관례에 따른 베이스 예외 + 세부 계층.

```
<BaseError>
├─ <SubError 1>
├─ <SubError 2>
└─ <SubError 3>
```

### 내부 ↔ 외부 경계

- **내부 전용**: 스택 트레이스, 원시 예외 메시지 → 로그로만
- **외부 노출**: 에러 코드 + 사람이 읽는 메시지 + (optional) 상세 객체
- **절대 노출 금지**: 내부 경로, 시크릿, DB 연결 문자열, 스택 트레이스

### 재시도 / 복구 정책 (해당 시)
- 어떤 에러가 재시도 가능한가?
- backoff 전략?
- 최대 재시도 횟수?

> 작성 가이드:
> - 코드 네이밍: `<DOMAIN>_NNN` 형식 권장 (예: `PARSE_001`, `NETWORK_003`, `<도메인>_NNN`)
> - 실제 응답 포맷은 해당 인터페이스 섹션에 기술 (여기는 분류 체계만)
> - 언어별 예외 패턴은 프로파일 본문 가이드 참조
> - 내부 에러 메시지가 외부 응답에 유출되지 않도록 명시적 변환 레이어 필요

## 4. CLI 커맨드

### 엔트리포인트
- 실행 명령: `<예: hijack>` 또는 `python -m <package>`
- 프레임워크: `<click / argparse / typer>`

### 공통 옵션
| 옵션 | 축약 | 설명 |
|------|-----|------|
| `--verbose` | `-v` | 상세 로그 |
| `--quiet` | `-q` | 출력 최소화 |
| `--help` | `-h` | 도움말 |
| `--version` | | 버전 표시 |

### 커맨드

#### `<cmd_1>`
```
사용법: <app> <cmd_1> [옵션] <인자>

인자:
  <ARG>    <설명 — 필수/선택>

옵션:
  --<opt> <type>  <설명>

예시:
  <app> <cmd_1> foo --bar=1
  → <기대 출력>

에러:
  exit 2: 인자 누락 / 형식 오류
  exit 3: 내부 처리 실패
```

#### `<cmd_2>`
...

### 서브커맨드 그룹 (있을 때)
```
<app>
├─ <group_a>
│   ├─ list
│   ├─ add
│   └─ remove
└─ <group_b>
```

### 출력 형식
- 기본: 사람이 읽는 텍스트 (rich/컬러 OK)
- `--json` 옵션 시: JSON (스크립트 연동용)
- 에러: stderr, 결과: stdout (파이프 호환성)

> 작성 가이드:
> - 모든 커맨드에 최소 1개 실행 예시
> - exit code는 `errors` 섹션과 일치
> - `print()` 직접 호출 대신 click.echo 등 프레임워크 API 사용

## 5. 도메인 로직

### 핵심 비즈니스 규칙
번호 붙은 규칙 목록:
1. <예: "완료 기록은 `completed_date`가 오늘 이전일 수 없다">
2. <예: "습관 삭제는 소프트 딜리트 — is_active=false, 데이터 보존">

### 알고리즘
각 핵심 알고리즘에 대해:

#### `<알고리즘 이름>`
- **입력**: `<type>`
- **출력**: `<type>`
- **전제조건**: <precondition>
- **사후조건**: <postcondition>
- **복잡도**: `<O(n)>`

**의사 코드**:
```
<pseudocode>
```

### 순수 함수 vs I/O 분리

**pure (core/)** — I/O 없음, 테스트 쉬움:
- `calculate_streak(completions: List[Date], today: Date) -> int`
- `validate_email(email: str) -> bool`

**impure (io/)** — DB/네트워크/파일:
- `save_habit(habit: Habit) -> None`  [DB]
- `fetch_user(id: int) -> User`       [DB]
- `send_notification(...) -> None`    [HTTP]

### 에지 케이스 목록
- <예: 빈 완료 기록 → streak = 0>
- <예: 미래 날짜 요청 → ValidationError>
- <예: 음수 나이 → ValidationError>

### 테스트 전략
- **단위 테스트**: pure 함수는 property-based test (hypothesis/fast-check) 권장
- **통합 테스트**: impure 함수는 실제 DB/파일로
- **커버리지 목표**: core/ 모듈 ≥ 90%, io/ 모듈 ≥ 70%

> 작성 가이드:
> - 비즈니스 규칙은 "<조건>이면 <결과>" 형식
> - 알고리즘은 의사 코드로 — 실제 언어 코드는 구현 단계에서
> - 순수/비순수 분리를 파일 레벨로 명시 (core/ vs io/)

## 6. 태스크 분해

> 이 섹션은 `/ha-plan` 스킬이 자동으로 채웁니다. 직접 편집하지 마세요.
> 수동 변경이 필요하면 `/ha-plan --reset` 후 재생성하세요.

### 태스크 목록
| ID | Component | Path | Depends | Description | Status |
|----|-----------|------|---------|-------------|--------|
| T-001 | <component_id> | <path> | — | <한 줄 설명> | pending |

### 의존성 그래프
```
(ha-plan이 생성)
```

### 병렬 실행 가능 조합
(ha-plan이 생성)

### 진행 상태
- `pending` — 아직 시작 안 함
- `in-progress` — `/ha-build` 실행 중
- `done` — 구현 + 검증 완료
- `blocked` — 의존성 미해결 또는 실패 지속

## 7. 구현 노트

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
- <시드 스크립트 위치, 실행 방법>

> 작성 가이드:
> - 결정은 반드시 "사유" 포함 — 1년 후 나도 이해할 수 있게
> - TODO는 완수 시점과 담당자 명시 (`CLAUDE.md §5`)
> - 여기 기록된 TODO가 많으면 다음 Phase에서 skeleton 섹션으로 승급
