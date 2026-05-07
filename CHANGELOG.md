# Changelog

All notable changes to this project will be documented in this file.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), versioning via [SemVer](https://semver.org/spec/v2.0.0.html).

Until 1.0.0, the surface contract is the **rule schema** (`AnalysisRule` /
`CategoryResult` / `SessionResult` JSON shape) and the **CLI** (`code-hijack
analyze` / `diff` / `harness-export`). Adding a field to the schema or a flag
to a subcommand is a minor bump; breaking either is a major bump.

## [0.2.0] — 2026-05-06

Phase 4b validation hardening (2026-05-05) + Phase 4c skill-mode parity and
calibration (2026-05-06). Validation matching rate on starlette improved from
17% (v3) to **50%** (v12) over the cycle.

### Added

- **Decision-mining mechanical signal layers** that populate the `evidence`
  field on each rule with verbatim senior reasoning:
  - `archaeology.py` (Phase C) — commit-body decision-trail mining (18 patterns
    incl. `instead of`, `rather than`, `to avoid`, `to prevent`, `due to`,
    `motivated by`, `as opposed to`, `regression`)
  - `pr_decisions.py` (Phase A1) — GitHub PR signals (vocabulary clusters,
    notable/rejected PRs, recurring labels)
  - `test_decisions.py` (Phase B) — senior defense catalog from test code
    (parametrize edge cases, `pytest.raises` groupings)
  - `exemplars.py` (Phase G1) — concrete code samples per category
  - `style_fingerprint.py` (Phase G2) — statistical style fingerprint
    (frameworks, naming conventions, line-length distribution)
- **Skill-mode parity** (A2.1): `commit_decisions` injection into the
  skill-mode prompt so skill-mode runs populate the same evidence chain as
  CLI mode. Closes the long-standing skill-mode evidence gap.
- **R6 auto-downgrade** of speculative MUST rules in `evidence.py` —
  rules without verified citation are demoted MUST→SHOULD at `write_output`
  time. R6 is the only mechanical defence against MUST inflation; cited
  MUSTs are never auto-demoted (writer-side priority self-check is the only
  safeguard there — see G7).
- **G7 priority self-check** guidance in `prompts.py` + `SKILL.md` — heuristic
  for distinguishing perf-optimisation MUSTs (downgrade to SHOULD) from
  correctness/safety MUSTs (keep as MUST), with explicit category-MUST > 50%
  forced-downgrade rule.
- **G8 feature-doc noise filter** in `archaeology.py` — commit bodies with
  4+ matched decision patterns are filtered as feature-documentation
  (verified across starlette/httpx/fastapi: narrative bodies use 1-3
  patterns).
- **G9 top-level dotted-py demote** in `preprocessor.py` — repo-root files
  named `.skill_analysis.py` / `.bootstrap.py` etc. are treated as
  auxiliary, preventing them from displacing library core files in
  selection.
- **R7 phase 1 — intent_clusterer** (`core/intent_clusterer.py`): bucketing
  of `CommitDecision` records by `(intent_kind, primary_path)`. Phase 1 of
  the [R7 pipeline-reversal design](backend/docs/r7_pipeline_reversal.md);
  produces `IntentCluster` objects ready for phase 2 LLM rule derivation.
  Phase 2-4 (LLM derivation + verify + external eval) ungated.
- **`harness-export` subcommand** — converts a session into HarnessAI-shaped
  conventions / guidelines / lesson-candidate format. Only `cross_project`
  rules auto-apply; rest become reviewable candidates.
- **`scope` field** on every rule — `cross_project` / `framework_internal` /
  `domain_specific`. Enables downstream auto-apply vs review-quarantine.
- **Persistent fetch cache** (`~/.cache/code-hijack/repos/<hash>/`) +
  `HIJACK_CACHE_DIR` / `HIJACK_NO_CACHE` env knobs — eliminates double-clone
  overhead in skill mode.
- **MUST calibration auto-lint** in `generator.py:write_output` — emits
  stderr `[WARN]` when overall MUST > 40% or any category > 50%.
- **`E1` body excerpt 240 → 800 chars** in `archaeology.py` — long
  PR-style commit bodies now survive truncation (verified win on
  starlette `48dea4d` typing-overloads commit).
- **R7 design document**: `backend/docs/r7_pipeline_reversal.md`
  (commit-corpus-first rule derivation: 4-phase plan, trade-offs, abort
  criteria for phase 4 external eval).

### Changed

- **CLI `--categories` default**: still 3 MVP cats, but full 10-cat run is
  documented and validated (5 cats matching-validated on starlette through
  v12).
- **`bad_example` requirement**: must be actual anti-pattern code, never a
  comment description (cargo-cult guard added in `prompts.py`; checked
  end-to-end on httpx v2 / fastapi v2 with quality 7→9/10).
- **Rule body principle level**: `_OUTPUT_FORMAT` `#7 PRINCIPLE OVER
  PRESCRIPTION` enforces that rule bodies describe the design constraint, not
  prescribe internal symbol names. Internal identifiers belong in
  `good_example` and `ref_files`.
- **Layer detection false-positive guards**: `client/`, `models/`,
  `framework-package` paths no longer false-positive into the wrong layer.
- **File selector**: `docs_src/` / `examples/` / `scripts/` demoted below
  library core; `original_chars` ranking fixes truncated-large-file
  ranking under file-size sort.

### Fixed

- **Skill-mode multi-clone race**: persistent cache replaces per-process
  `tempfile.mkdtemp` clones (`327fb1a`).
- **Layer detect false-positives** (`client/`, `models/` heuristic
  hardening, fastapi `db` count 79 → 0).
- **Selector regression**: `_AUXILIARY_PATH_PREFIXES` + `original_chars`
  fix where truncated large files were ranked below small full files
  (`e117c4c`).
- **Cargo-cult drift**: `_OUTPUT_FORMAT #7` + matching `SKILL.md` guidance
  prevents internal-symbol prescriptions in rule bodies (`e874e14`).

### Validation

| Cycle | Target | Categories | Rules | MUST% | Cited% | Notes |
|---|---|---|---|---|---|---|
| v3 | starlette | 3 | 12 | 25% | 17% | depth=10 baseline |
| v4 | starlette | 3 | 12 | 25% | 25% | depth=30 (E1 precursor) |
| v6 | httpx | 3 | 12 | 25% | 25% | httpx-specific commit-pool ceiling |
| v7 | starlette | 3 | 12 | 25% | 33% | +D pattern set |
| v10 | starlette | 4 | 16 | 31% | 38% | +testing |
| v11 | starlette | 5 | 20 | 35% | 45% | +security |
| **v12** | **starlette** | **6** | **24** | **38%** | **50%** | **+performance** |

External-reviewer evaluation (clean Claude Code session, v8): user-learning
6/10, AI-coding-guide 5/10. Quality gap between evidence-cited rules and
no-evidence rules: ~2x.

intent_kind diversity (cumulative across v10/v11/v12 + R7 phase 1):
`incident: 0` in expanded categories — senior OSS frames perf/security
decisions as `to avoid` / `as opposed to` (preference), not `regression` /
`reverted because` (incident).

### Test suite

783 (0.1.0) → **839** passing tests, ruff clean. Highlight additions:
- `test_commit_decisions.py` (Phase C) — 54 tests
- `test_pr_decisions.py` (Phase A1)
- `test_test_decisions.py` (Phase B)
- `test_exemplars.py` (Phase G1)
- `test_intent_clusterer.py` (R7 phase 1) — 20 tests
- `test_evidence.py` extensions (R6 auto-downgrade)

## [0.1.0] — 2026-04-17

Initial public skeleton.

### Added

- **Phase 1 (MVP)** — 3 categories (architecture / coding_style /
  api_design) × 5 layers (frontend / backend / db / devops / shared),
  CLI mode (`code-hijack analyze`) and skill mode (`/code-hijack`).
- **Phase 2 expansion** — full 10 categories (+testing / dependencies /
  security / performance / devops / state_management / data_model),
  `--resume` flag, `diff` subcommand, `SessionDiff`.
- **Phase 3 quality** — Few-shot prompts, Critic layer (drop duplicates,
  downgrade inflated MUST, scope-tag), content-density file selection.
- **Phase 3b HarnessAI integration** — `scope` field on rules,
  `harness-export` subcommand, system-prompt with inline ✅/❌/ref.
- **Layer detection** — deterministic, path + extension + dep-file
  heuristics, no LLM guessing.
- **Self-analysis** baseline at `hijack-output/2026-04-17_unknown/`.
