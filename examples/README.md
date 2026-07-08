# Example outputs

Real senior open-source repositories analyzed with code-hijack. Skill mode (few-shot + critic) applied.

> Provenance note: the pluggy and starlette sessions were originally run in Korean; their rule prose was translated to English for publication. Evidence quotes (commit/PR/SATD) and code excerpts are verbatim from the analyzed repos and were never touched.

## [`pluggy/`](pluggy/) — pluggy (pytest-dev) — **2026-07-06 (latest, first probe-badged sample)**

> 📊 Best extraction metrics in the project (cited 100%, exemplar-verbatim 100%, foresight 3/3) + **the first published sample with behavioral probe badges** — 3 of 21 rules behaviorally tested with Haiku control/treatment, 2 discriminated (`behavior-confirmed` badge). Probe targets were selected by **shortcut-gap density**, not incident count (the werkzeug R4/R5 lesson).

- **Analyzed**: https://github.com/pytest-dev/pluggy (history depth 30, 216 commits scanned)
- **Total files scanned**: 30 (pure Python throughout)
- **Rules extracted**: 21 (8 architecture + 6 coding_style + 7 api_design)
- **Quality metrics**:
  - MUST ratio: 28.6% (all cited)
  - **Rationale tier: cited 21 / speculative 0 (100%)** — anchor split: **senior-quoted (commit/PR/SATD) 10 / code-anchored 11**. A code-anchored rule is a verbatim observation of existing code, not a WHY the seniors wrote down — this split is surfaced as-is in `measurement.json` and the generated CLAUDE.md header (zero invented citations in both buckets).
  - **exemplar_verbatim_ratio: 100%**
  - intent_kind: rejection 2 / satd_citation_ratio 0.2 (a SATD `XXX` comment sustains a MUST)
  - foresight: all 3 cards confirmed (zero-deps bottom-of-ecosystem dependency / hot-path performance / ecosystem backward compatibility)
  - **probe: 3 probed, 2 discriminated** (traceback preservation, rejection of incompatible option combos)

### Highlights

1. **Re-raising a stored exception must preserve the original traceback** (`with_traceback`) — probe discriminated: control accumulated tb frames 4→6→8, treatment stayed constant (evidence: commit `93ac1e9`, 1.1.0 regression)
2. **Incompatible option combinations are rejected in code, not documentation** — probe discriminated: control silently accepted firstresult+historic, treatment raised ValueError at declaration time with pluggy's original message verbatim (evidence: SATD `_hooks.py:613`)
3. **Behavior changes MUST ship with a test** — evidence is a real rejection comment where the maintainer closed a test-less PR without review (PR#648 rejection)
4. **Explicit hot-path (call) / cold-path (registration) cost trade** (evidence: commit `63b7e90`)
5. **Don't break legacy — DeprecationWarning plus a suppress list with explicit expiry conditions** (evidence: `dd20a85`, `0258484`)

### Side measurement (A/B in the same session)

On an exploration-type task (fixing the real, unfixed bug #649), the rule-injected arm used **−67% tool calls (30→10) and −62% wall time** (both arms produced a correct fix; N=1, directional). See the Positioning section of the main README for probe details.

### How to use

Copy [`pluggy/integrated/CLAUDE.md`](pluggy/integrated/CLAUDE.md) into your plugin-framework/library project's Claude Code context. Raw data: `2026-07-06_pluggy/session.json`; metrics: `measurement.json`.

---

## [`werkzeug/`](werkzeug/) — Werkzeug (pallets) — **2026-07-05 (second-best extraction metrics)**

> 📊 cited 94% (vs starlette v12's 50%), exemplar-verbatim 100%, incident evidence 11 items (project record). Selected from 4 candidates (uvicorn/attrs/structlog/werkzeug) by deterministic supply measurement — werkzeug dominated with 11 incidents.

- **Analyzed**: https://github.com/pallets/werkzeug (history depth 30, 768 commits scanned)
- **Total files scanned**: 138
- **Rules extracted**: 17 (6 architecture + 5 coding_style + 6 api_design)
- **Quality metrics**:
  - MUST ratio: 23.5% (all cited)
  - **Rationale tier: cited 16 / speculative 1 (94% cited)**
  - **exemplar_verbatim_ratio: 100%** — every good_example is a verbatim excerpt of existing source (W4a deterministic check)
  - intent_kind: **incident 11 + rejection 4** (most incidents of any session — rich security/regression history)
  - foresight: all 3 cards confirmed (min-deps / import=public-API / stdlib-only security module)

### Highlights

Representative senior patterns captured (all with verbatim evidence):

1. **Never trust the Host header without an allowlist** — security decisions on client-controlled host require an explicit allowlist; least-trusting failure when absent (evidence: commit `71b69df` trusted_hosts, PR#3143)
2. **Untrusted streams get an incremental hard cap** — don't trust declared Content-Length alone; check incrementally while reading (evidence: PR#3053 chunked Transfer-Encoding DoS)
3. **safe_join returns a None sentinel on escape** — rejects traversal/absolute paths/drive letters/alternate separators; no "safe-looking" fallback (evidence: PR#3174 Windows nt-path hardening, incident)
4. **Public API removal goes through a DeprecationWarning cycle** — name the replacement API, keep it for one release; a bare TODO alone is not enough
5. **sansio layer separation** — transport-agnostic parsing subclassed by the WSGI wrapper (evidence: `_SansIOResponse`)

### Honesty note — two honesty-guard catches in the wild

This session recorded the skill session **blocking itself from turning unmerged PRs into rules**: (a) it tried to use PR#3183's diff as a good_example, but the W4a exemplar-verbatim check returned `false` (current source `range.py:271` still contains the `assert` — PR unmerged) → rule dropped, demoted to anti-pattern. (b) PR#3182 (an O(n²) fix) was also confirmed absent from source → excluded. Live proof that the "verbatim only" design blocks hallucination.

### How to use

Copy [`werkzeug/integrated/CLAUDE.md`](werkzeug/integrated/CLAUDE.md) into your WSGI/HTTP-library project's Claude Code context. Raw data: `2026-07-05_werkzeug/session.json`.

---

## [`starlette/`](starlette/) — Starlette (encode) — **2026-05-06 v10 snapshot (4 categories)**

> 📊 This directory is the v10 4-category baseline. The same-day v11 (+security) → v12 (+performance) cycles raised the matching rate 38% → 45% → **50%**, but those two cycles live only in `hijack-output/validation-starlette-v{11,12}/` (gitignored). Use v10 to see the output shape; see the Validation status table in the main README for the matching-rate trajectory.

- **Analyzed**: https://github.com/encode/starlette (history depth 30)
- **Total files scanned**: 67
- **Rules extracted**: 16 (4 architecture + 4 coding_style + 4 api_design + 4 testing)
- **Quality metrics**:
  - MUST ratio: 31% (target 30-40% ✅, after R6 auto-downgrade)
  - **Evidence-chain matching: 6/16 (38%)** — matched commits: `42592d6` anyio integration, `7a0f89a` CORS credentials, `3d77a1c` BaseHTTPMiddleware memory regression, `48dea4d` Config typing overloads, `78fcd54` tests/types module, `d222b87` TestClient backend args
  - intent_kind diversity: incident:1, preference:5
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

Each layer file is scoped — load the one matching the files you work on (here it's mostly `shared.md`: all 16 rules classified layer=shared, since starlette is a library).

Pipeline reproducibility: raw analysis data in `2026-05-06_starlette/session.json`.
