# Example outputs

실제 시니어 오픈소스 레포를 code-hijack 으로 분석한 결과물. Skill 모드 (few-shot + critic) 적용.

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
