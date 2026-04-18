# Example outputs

실제 시니어 오픈소스 레포를 code-hijack 으로 분석한 결과물. Skill 모드 (few-shot + critic) 적용.

## [`fastapi/`](fastapi/) — FastAPI (tiangolo)

- **Analyzed**: https://github.com/tiangolo/fastapi (commit from 2026-04-17)
- **Total files scanned**: 1119
- **Rules extracted**: 17 (6 architecture + 5 coding_style + 6 api_design)
- **Quality metrics**:
  - MUST ratio: 35% (target 30-40% — critic layer passed)
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
