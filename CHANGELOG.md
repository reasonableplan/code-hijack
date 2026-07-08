# Changelog

All notable changes to this project will be documented in this file.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), versioning via [SemVer](https://semver.org/spec/v2.0.0.html).

Until 1.0.0, the surface contract is the **rule schema** (`AnalysisRule` /
`CategoryResult` / `SessionResult` JSON shape) and the **CLI** (`code-hijack
analyze` / `diff` / `measure` / `apply`). Adding a field to the schema or a flag
to a subcommand is a minor bump; breaking either is a major bump.

## [Unreleased]

### Added
- **CLI-mode evidence parity**: `analyze` prompts now carry compact
  `<pr_decisions>`, `<satd>`, and `<commit_decisions>` blocks, and the output
  format documents evidence kinds `pr` / `comment` — CLI sessions can cite
  rejection/incident PRs and SATD comments with the same fidelity as skill
  mode (previously the pools were mined and validated but never shown to the
  CLI-mode LLM).
- **Doc-size metrics + lint**: `measurement.json` gains `doc_entry_lines`,
  `doc_max_layer_lines`, `doc_max_layer_file` (populated via `calc_session_metrics(...,
  integrated_dir=...)`, wired through `code-hijack measure`'s `<session_dir>/../integrated`
  lookup), and `write_output` prints a `[WARN] doc size` block to stderr when
  `integrated/CLAUDE.md` exceeds 60 lines or any written layer file exceeds
  300 lines — thresholds from the ETH context-file study (arxiv 2602.11988).

### Changed
- Rule-0 layer `.md` files are no longer written under `integrated/`, and the
  `CLAUDE.md` Layer Guide lists only layers with ≥1 rule (falls back to a
  single "No rules in this session." line when every layer is empty) —
  removes the 9-line "Total rules: 0" noise files.
- All user-facing output is now English: generated artifact templates
  (generator.py), CLI help/progress/errors (cli.py), prompt few-shot content
  (prompts.py, including a new OUTPUT LANGUAGE requirement), and the published
  `examples/` samples. Skill mode gained the same output-language directive in
  SKILL.md.
- `--dry-run` cost estimate now uses separate input/output token rates
  ($3/$15 per MTok for claude-sonnet-5) instead of a flat $3/MTok.
- Docs: the `apply` subcommand is now documented (README features/usage/tree,
  CLAUDE.md interface list, CLI contract line above); R7 and dogfooding
  direction status synced to their July 2026 verdicts (R7 Phase 2 shelved
  after the PR-axis probe; dogfooding pivoted to drift monitoring).
- Docs: positioning literature updated — direct link to the ETH context-file
  study (arxiv 2602.11988), CommitDistill's deterministic-only null result
  (arxiv 2605.18284) as hybrid-design corroboration, and Learning to
  Commit / Meta tool-call reductions as independent replications of the
  exploration-efficiency axis.

### Removed
- **Breaking (CLI)**: `--llm-mode local` and `--comms-dir` options plus
  `llm/local.py` (file-IPC mode). The mode was orphaned — skill mode drives
  the engine directly via SKILL.md and never used it.
- **Breaking (CLI)**: `harness-export` subcommand + `core/harness_export.py`
  + its tests. The downstream HarnessAI consumption path was terminated
  after dogfooding concluded (2026-07-06); restore from git history if ever
  needed.
- Retired Phase-A1 `core/pr_decisions.py`, its tests, and
  `scripts/check_pr_decisions.py`. The live pipeline moved to
  `core/pr_archaeology.py` decision-trails in 0.3.x; the dashboard-style A1
  module had no remaining pipeline callers.
- Retired `core/intent_clusterer.py` and its tests — an internal R7 phase-1
  probe module never wired into the analysis pipeline; R7 Phase 2 is
  shelved (`backend/docs/r7_pipeline_reversal.md`). Restore from git
  history (`dd51957`/`498b9aa`) if re-measurement is ever needed.
- Stale `examples/fastapi/` sample (2026-04-17) — predates PR/issue mining,
  probe badges, and the cited-anchor split; superseded by
  `examples/{starlette,werkzeug,pluggy}`.
- One-off Phase B/C/G diagnostic and retrofit scripts
  (`scripts/check_commit_decisions.py`, `scripts/check_test_decisions.py`,
  `scripts/diagnose_exemplar_scores.py`, `scripts/fresh_g1g2_retrofit.py`,
  `scripts/retrofit_g1_exemplars.py`), superseded by the `measure`
  subcommand, plus the unused `backend/docs/skeleton-v2.md` placeholder
  scaffold (`skeleton.md` is the maintained design doc).

## [0.3.0] — 2026-06-11

Foresight inference layer (Phase 3) + evidence source expansion & measurement
loop (Phase 4). User feedback driving the cycle: the tool captured *what*
seniors wrote but not *why* (rationale), missed foresight (negative space),
and over-coerced (every MUST treated as non-negotiable).

Validation on `encode/starlette` (2026-06-11, skill mode):

- **intent_kind diversity unlocked**: commit mining alone yielded
  rejection/incident **0** across every prior measurement cycle. PR/issue
  mining (gh CLI, 100 items scanned) yielded **32 decisions — rejection 22,
  incident 10** on the same repo. First non-zero rejection/incident signal
  in the project's measurement history. Citable maintainer evidence now
  reachable (e.g. PR#3262: "I'm happy to maintain Config … as a simple
  config class, but I'm not willing to add new features").
- **Rule honesty grading**: 14 rules — cited 7 / corroborated 5 /
  speculative 2. MUST 5/14 (35.7%), **all 5 cited** (cited-only MUST
  enforced mechanically at parse time).
- **Foresight accuracy now measurable**: 4 hypothesis cards, deterministic
  scoring **3/4 confirmed** against repo docs + rejection corpus; 1 honest
  unconfirmed (Environ read-after-write card — PR#3262 corroborates Config
  minimalism but not the specific hypothesis).
- **measurement.json codified** — cited_ratio 50%, must_ratio 35.7%,
  tier/intent distributions persisted per session; future improvements are
  scored numerically instead of manually.
- Known noise (honest limit): dependabot bumps misclassified as incident
  (~4-5 of 10), 1 spam PR as rejection — mining precision is imperfect.

### Added

- **3-tier rationale grading** (`rationale_tier` on `AnalysisRule`):
  `cited` (senior verbatim evidence) / `corroborated` (2+ independent code
  signals) / `speculative` (LLM inference). `normalize_rationale_tier` in
  `analyzer.py` demotes corroborated/speculative MUST → SHOULD at parse
  time — **only cited rules can be MUST**. Backward compatible
  (`from_json` defaults old sessions to `speculative`).
- **ForesightCard + foresight.md** — separate artifact for inferred design
  intent: hypothesis + verified signals + falsification conditions + tier.
  Never MUST-eligible; rendered per session and integrated. Hypotheses are
  triangulated (2+ independent repo signals verified before grading above
  speculative).
- **`core/negative_space.py`** — deterministic negative-space extractor:
  dep_count, stdlib-only direct-impl hints, public_ratio + `__all__`
  discipline, deprecation patterns, layer import violations. Feeds
  triangulation signals.
- **`repo_nature` detection** (`preprocessor.py`) — `library` / `app` /
  `app/cli` context header on outputs; system-prompt tone changed from
  "non-negotiable constraints" to context-conditional ("apply when the
  extraction context holds; deviate with stated reason").
- **`core/pr_archaeology.py`** — PR/issue mining via gh CLI:
  closed-unmerged PRs (rejection), wontfix/discussion issues, maintainer
  comments, mined with the same decision patterns as `archaeology.py`.
  Graceful skip without gh (classified warnings, empty result).
- **`core/measure.py` + `code-hijack measure` subcommand** —
  `calc_session_metrics` / `diff_sessions` / `score_foresight` /
  `write_measurement`; measurement.json per session.
- **SKILL.md steps 3.7/3.8** — foresight hypothesis generation +
  triangulation, deterministic foresight scoring + LLM verdict pass;
  steps 1/3.5 merge pr_decisions into the evidence chain.

### Changed

Skill-mode 결과물 품질 회복 (2026-06 초). 실측 케이스(skn21-final-1team
frontend+backend combined, 263 files / 23 rules) 에서 세 회귀를 차단:

- **`evidence.classify_rule`**: 새 `valid_file_paths` kwarg 추가 — ref_files
  엔트리가 `path:N` / `path:N-M` 라인 anchor 를 갖고 그 경로가 분석 대상의
  실제 파일에 매치하면 'cited' 로 분류. skill-mode 가 commit SHA / PR# 패턴
  없이 한국어 산문 reason 만 적을 때 모든 MUST 가 'other' 로 떨어져 자동
  downgrade 되던 회귀 차단. `downgrade_speculative_rules` /
  `compute_evidence_metrics` 가 `session.selected_files` 를 truth pool 로
  자동 전달. **결과: 우리 벤치마크에서 0/23 MUST → 9/23 MUST (39%, 캘리브레이션
  목표 30-40% 안), CLAUDE.md "Top MUST Rules" 가 0개 → 9개로 채워짐.**
  `valid_file_paths` 는 opt-in (default None — 기존 호출 영향 없음).

- **`preprocessor.select_files_for_category`**: TS/JS 의 re-export only barrel
  파일 (`export * from '...'`, `export { Name } from '...'` 만 있는 `index.ts`)
  을 auxiliary 로 demote. 실제 구현 파일이 선별 자리에 우선 진입. Python
  `__init__.py` (`from X import Y`) 는 barrel 의미가 약하므로 영향 없음 — JS/TS
  suffix 한정. **결과: architecture/coding_style 각 12개 선별 중 4자리씩 (총 8)
  을 차지하던 1-7줄짜리 barrel 이 모두 informative 파일로 대체.**

- **`generator._render_rule_compact`**: system-prompt 의 ✅/❌ 인라인 미리보기가
  같은 첫 줄로 시작할 때 (`class XxxService:`, `class XxxRequest(BaseModel):`
  등) 처음 달라지는 줄까지 자동 확장. 양쪽이 같은 prefix 의 공백/주석/docstring
  은 동기로 skip. **결과: ✅/❌ 비교가 무의미했던 4개 규칙 (Service singleton,
  Pydantic ConfigDict, `_method` 표기, Pydantic Field 한국어) 모두 실제 차이
  라인을 노출.**

### Internal

- `evidence._has_valid_ref_files` (skill-mode ref_files truth pool 검증)
- `preprocessor._is_reexport_barrel` (TS/JS barrel 검출, 블록 주석 / `//` 라인
  주석 처리), `preprocessor._should_demote` (auxiliary path + barrel 통합)
- `generator._distinguishing_preview` / `_meaningful_lines` / `_truncate_line`
  (✅/❌ diff-line 추출)

위 skill-mode 회귀 차단 분은 공개 API / CLI / 스키마 변경 없음 (backward
compatible). 0.3.0 전체로는 스키마 추가 (`rationale_tier`, `ForesightCard`,
`repo_nature`) + CLI 추가 (`measure`) — minor bump 사유.

테스트: 884 → **1020 passed** (foresight 28 + pr_archaeology 22 + measure 31
+ cli 7 + 기타), ruff clean, 신규 코드 pyright 0 errors.

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
