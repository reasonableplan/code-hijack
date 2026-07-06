# Example outputs

실제 시니어 오픈소스 레포를 code-hijack 으로 분석한 결과물. Skill 모드 (few-shot + critic) 적용.

## [`pluggy/`](pluggy/) — pluggy (pytest-dev) — **2026-07-06 (최신, 첫 probe 배지 샘플)**

> 📊 추출 지표 프로젝트 최고 (cited 100%, exemplar-verbatim 100%, foresight 3/3) + **행동 probe 배지가 실린 첫 공개 샘플** — 규칙 21개 중 3개를 Haiku control/treatment 로 행동 검증, 2개 discriminated (`behavior-confirmed` 배지). 표적 선정은 'incident 수'가 아니라 **지름길-갭 밀도** 기준 (werkzeug R4/R5 교훈).

- **Analyzed**: https://github.com/pytest-dev/pluggy (history depth 30, 216 commits scanned)
- **Total files scanned**: 30 (전량 순수 Python)
- **Rules extracted**: 21 (8 architecture + 6 coding_style + 7 api_design)
- **Quality metrics**:
  - MUST ratio: 28.6% (전원 cited)
  - **Rationale tier: cited 21 / speculative 0 (100%)** — 앵커 분리: **시니어 인용(commit/PR/SATD) 10 / 코드 앵커 11**. 코드 앵커는 실존 코드의 verbatim 관찰이지 시니어가 남긴 WHY 가 아님 — 이 구분을 measurement.json 과 CLAUDE.md 헤더에 그대로 노출한다 (발명된 인용 0 은 두 버킷 공통).
  - **exemplar_verbatim_ratio: 100%**
  - intent_kind: rejection 2 / satd_citation_ratio 0.2 (SATD `XXX` 주석이 MUST 지탱)
  - foresight: 3 카드 전원 confirmed (zero-deps 최하부 의존성 / hot-path 성능 / 생태계 하위호환)
  - **probe: 3 probed, 2 discriminated** (traceback 보존, 비호환 옵션 선언 거부)

### Highlights

1. **저장 예외 재raise 는 원본 traceback 보존** (`with_traceback`) — probe 판별: control 은 tb 4→6→8 프레임 누적, treatment 는 불변 (evidence: commit `93ac1e9`, 1.1.0 회귀)
2. **양립 불가능한 옵션 조합은 코드로 거부** — probe 판별: control 은 firstresult+historic 무증상 수용, treatment 는 선언 시점 ValueError + pluggy 원문 메시지 verbatim (evidence: SATD `_hooks.py:613`)
3. **동작 변경은 테스트 동반 MUST** — 메인테이너가 테스트 없는 PR 을 리뷰 없이 닫은 실제 거절 코멘트가 evidence (PR#648 rejection)
4. **핫 경로(호출)/콜드 경로(등록) 비용 명시적 교환** (evidence: commit `63b7e90`)
5. **레거시는 깨지 말고 DeprecationWarning + 만료 조건 명시 suppress 목록** (evidence: `dd20a85`, `0258484`)

### 부수 실측 (같은 세션의 A/B)

탐색형 태스크(실존 미수정 버그 #649 수정)에서 규칙 주입 팔이 **툴콜 30→10 (−67%), 시간 −62%** (둘 다 정확한 수정, N=1 directional). 행동 probe 상세는 메인 README Positioning 참조.

### How to use

Copy [`pluggy/integrated/CLAUDE.md`](pluggy/integrated/CLAUDE.md) into your plugin-framework/library project's Claude Code context. Raw 데이터는 `2026-07-06_pluggy/session.json`, 지표는 `measurement.json`.

---

## [`werkzeug/`](werkzeug/) — Werkzeug (pallets) — **2026-07-05 (추출 지표 2위 샘플)**

> 📊 cited 94% (starlette v12 50% 대비), exemplar-verbatim 100%, incident evidence 11건 (프로젝트 최다). 결정론 공급 측정으로 후보 4개(uvicorn/attrs/structlog/werkzeug) 중 선정 — werkzeug 가 incident 11 로 압도적.

- **Analyzed**: https://github.com/pallets/werkzeug (history depth 30, 768 commits scanned)
- **Total files scanned**: 138
- **Rules extracted**: 17 (6 architecture + 5 coding_style + 6 api_design)
- **Quality metrics**:
  - MUST ratio: 23.5% (전원 cited)
  - **Rationale tier: cited 16 / speculative 1 (94% cited)**
  - **exemplar_verbatim_ratio: 100%** — 모든 good_example 이 실존 소스의 verbatim 발췌 (W4a 결정론 검증)
  - intent_kind: **incident 11 + rejection 4** (incident 최다 — 보안/회귀 사고 이력 풍부)
  - foresight: 3 카드 전원 confirmed (min-deps / import=public-API / stdlib-only 보안모듈)

### Highlights

Representative senior patterns captured (전원 verbatim evidence):

1. **Host header는 allowlist 없이 신뢰 금지** — client-controlled host 로 보안 결정 시 explicit allowlist, 없으면 least-trusting fail (evidence: commit `71b69df` trusted_hosts, PR#3143)
2. **untrusted stream은 incremental hard cap** — declared Content-Length 만 믿지 말고 읽는 중 증분 체크 (evidence: PR#3053 chunked Transfer-Encoding DoS)
3. **safe_join은 escape 시 None sentinel** — traversal/절대경로/드라이브문자/대체구분자 거부, 'safe-looking' fallback 금지 (evidence: PR#3174 Windows nt-path hardening, incident)
4. **public 제거는 DeprecationWarning 사이클** — replacement API 명시 + 1릴리스 유지, bare TODO 단독 금지
5. **sansio 계층 분리** — transport-agnostic 파싱을 WSGI wrapper 가 subclass (evidence: `_SansIOResponse`)

### 정직 노트 — 실전에서 잡힌 정직성 가드 2건

이 세션은 skill 세션이 **미머지 PR 을 규칙으로 만들려다 스스로 차단한** 사례를 남겼다: (a) PR#3183 의 diff 를 good_example 로 쓰려 했으나 W4a exemplar-verbatim 이 `false` (현 소스 `range.py:271` 에 여전히 `assert` 존재 — PR 미머지) → 규칙 드롭, anti-pattern 으로 강등. (b) PR#3182 (O(n²) 픽스) 도 소스 미반영 확인 → 제외. 도구의 "verbatim only" 설계가 hallucination 을 막는 실증.

### How to use

Copy [`werkzeug/integrated/CLAUDE.md`](werkzeug/integrated/CLAUDE.md) into your WSGI/HTTP-library project's Claude Code context. Raw 데이터는 `2026-07-05_werkzeug/session.json`.

---

## [`starlette/`](starlette/) — Starlette (encode) — **2026-05-06 v10 snapshot (4 categories)**

> 📊 이 디렉토리는 v10 4-category baseline. 같은 날 v11 (+security) → v12 (+performance) 까지 진행되어 매칭율 38% → 45% → **50%** 으로 상승했으나, 그 두 사이클은 `hijack-output/validation-starlette-v{11,12}/` (gitignored) 에만 보관. v10 으로 도구 출력 형태를 보고, 매칭율 추이는 메인 README 의 Validation status 표 참조.

- **Analyzed**: https://github.com/encode/starlette (history depth 30)
- **Total files scanned**: 67
- **Rules extracted**: 16 (4 architecture + 4 coding_style + 4 api_design + 4 testing)
- **Quality metrics**:
  - MUST ratio: 31% (target 30-40% ✅, R6 자동 강등 후)
  - **Evidence-chain matching: 6/16 (38%)** — 매칭된 commits: `42592d6` anyio integration, `7a0f89a` CORS credentials, `3d77a1c` BaseHTTPMiddleware memory regression, `48dea4d` Config typing overloads, `78fcd54` tests/types module, `d222b87` TestClient backend args
  - intent_kind 다양성: incident:1, preference:5
  - `ref_files` with line numbers: 100%

### Highlights

Representative senior patterns captured:

1. **Locked middleware positions** — ServerError outermost / Exception innermost is framework-internal; user middleware sandwiched between
2. **anyio runtime abstraction** — `is_async_callable` + `run_in_threadpool` hide sync/async difference at framework layer (evidence: PR #1157 anyio integration)
3. **CORS preflight + wildcard/credentials guard** — `Access-Control-Allow-Origin: *` + credentials forbidden by spec; framework enforces at one location (evidence: PR #1402)
4. **Body cache vs stream split** — `_CachedRequest.wrapped_receive` handles body() vs stream() semantics; high-memory regression once shipped (evidence: PR #1745)
5. **TestClient backend constructor arg** — backend/options as constructor params, not ClassVar — preserves multi-runtime test isolation (evidence: PR #1211)
6. **`tests/types.py` shared fixture types** — single source for TestClientFactory Protocol; prevents per-test-module drift (evidence: PR #2502)

### How to use

Copy [`starlette/integrated/CLAUDE.md`](starlette/integrated/CLAUDE.md) into your own ASGI project's Claude Code context. Your agent will follow these patterns.

Each layer file (`shared.md` 위주, 16 rules 모두 layer=shared 로 분류됨 — starlette 가 라이브러리이므로) 는 scoped — 작업 파일 종류에 맞는 것만 로드.

Pipeline reproducibility: `2026-05-06_starlette/session.json` 에 raw 분석 데이터.

---

## [`fastapi/`](fastapi/) — FastAPI (tiangolo) — **2026-04-17 (stale)**

> ⚠️ 2026-04-17 분석. 이후 도구 변경 (P0~P4 가이드 정확성, R6 speculative MUST 강등, D pattern 6 확장, E1 body excerpt 240→800) 미반영. fresh 분석은 `code-hijack analyze https://github.com/tiangolo/fastapi` 로 재돌릴 것.

- **Analyzed**: https://github.com/tiangolo/fastapi (commit from 2026-04-17)
- **Total files scanned**: 1119
- **Rules extracted**: 17 (6 architecture + 5 coding_style + 6 api_design)
- **Quality metrics** (도구 변경 전 측정):
  - MUST ratio: 35%
  - `ref_files` with line numbers: 100%
  - `bad_example` as real anti-pattern code: 100%

### Highlights

Representative senior patterns captured:

1. **Starlette subclassing strategy** — `FastAPI(Starlette)`, `HTTPException(StarletteHTTPException)` — reuse ASGI ecosystem, add OpenAPI layer only
2. **`DefaultPlaceholder` sentinel** — distinguish "user passed None" vs "user didn't pass"; critical for `include_router` merge semantics
3. **`Annotated[T, Doc('''...''')]`** — parameter docs on the type itself, survives refactors, feeds OpenAPI generation
4. **keyword-only params for API stability** — positional breaks are silent; keyword-only forces explicit migration
5. **`auto_error=False` for composable auth** — allows layering multiple security schemes on one endpoint

### How to use

Copy [`fastapi/integrated/CLAUDE.md`](fastapi/integrated/CLAUDE.md) into your own FastAPI project's Claude Code context. Your agent will follow these patterns.

Each layer file (`backend.md`, `shared.md`) is scoped — only load what's relevant to the file you're editing.
