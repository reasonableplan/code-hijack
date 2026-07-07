# code-hijack

> Extract senior coding style from a codebase into AI-agent-ready rules.

**한국어 README**: [README.ko.md](README.ko.md)

AI agents produce generic, inconsistent code. code-hijack analyzes a senior open-source repository with an LLM to extract **why** the code is written the way it is, then generates rule documents (`CLAUDE.md` + layer-specific `.md` + `system-prompt.md`) that make an agent code in that style.

## Highlights

Tags: ✅ validated with measurable data, ⚠️ partial / has known limits, ❓ implemented but not yet measured. See [Validation status](#validation-status) below for cycle data.

- ✅ **10 analysis categories** — architecture, coding_style, api_design, testing, dependencies, security, performance, devops, state_management, data_model. (5 categories matched-validated on starlette through v12; remaining 5 implemented, dogfooding pending.)
- ✅ **5-layer deterministic classification** — frontend / backend / db / devops / shared (path + extension + dep-file heuristics, no LLM guessing). Calibration regression caught and fixed (e117c4c).
- ⚠️ **Evidence-based rules with 3-tier rationale grading** — every rule carries `rationale_tier`: `cited` (verbatim senior evidence), `corroborated` (2+ independent code signals), or `speculative` (LLM inference). **Only `cited` rules can be MUST** — corroborated/speculative are mechanically demoted to SHOULD at parse time. Evidence-chain ceiling: ~50% cited on senior OSS (starlette v12, 5 categories); ~0% on individual repos with terse commit messages. Quality-gap with no-evidence rules measured ~2x by external reviewer.
- ❓ **Scope-tagged rules** — every rule is classified `cross_project`, `framework_internal`, or `domain_specific`. Lets a downstream tool auto-apply the safe ones and quarantine the rest. (Code present, end-to-end downstream usage not yet measured.)
- ✅ **Critic layer** — second LLM pass that drops duplicates, downgrades inflated MUST, tags scope. Plus mechanical safeguards: MUST ratio auto-lint (`write_output` stderr warn if >40%), and **R6 auto-downgrade** of speculative MUSTs (no verified citation → SHOULD).
- ✅ **Foresight inference layer** — `ForesightCard` artifact (hypothesis + verified signals + falsification conditions + tier) rendered per session into `foresight.md`. Never MUST-eligible. Hypotheses are triangulated against 2+ independent repo signals. `core/negative_space.py` feeds deterministic signals (dep_count, stdlib-only hints, public_ratio, deprecation patterns, layer import violations).
- ✅ **Two execution modes**:
  - **CLI mode** (`code-hijack analyze`) — direct Anthropic API, fully automatable
  - **Skill mode** (`/code-hijack`) — uses the current Claude Code session, no API key needed
- ❓ **HarnessAI integration** — `harness-export` subcommand converts a session into [HarnessAI](https://github.com/reasonableplan/harnessai)-shaped docs. Only `cross_project` rules auto-apply; the rest become reviewable candidates. (Implemented; downstream HarnessAI consumption not yet dogfooded.)
- ❓ **Session management** — `--resume` to skip completed categories, `diff` subcommand to compare rule changes across sessions. (Implemented; usage data thin.)
- ✅ **PR/issue mining** — `core/pr_archaeology.py` mines closed-unmerged PRs (rejection), wontfix/discussion issues, and maintainer comments via `gh` CLI. Same decision-pattern set as commit mining. Graceful skip when `gh` is unavailable. First unlocked rejection/incident signals on starlette (32 decisions: 22 rejection + 10 incident from 100 items scanned).
- ⚠️ **Decision mining from Git** — extracts senior reasoning from PR descriptions, review comments, commit bodies, and reverts; rule `evidence` field carries verbatim quotes with intent classification (rejection/constraint/incident/preference). **Effective when target repo has decision-pattern keywords ("instead of", "rather than", etc.); a typical busy-developer repo may yield close to zero from commit mining alone — PR/issue mining now supplements this gap.**
- ✅ **Measurement loop** — `core/measure.py` + `code-hijack measure` subcommand computes `cited_ratio`, `must_ratio`, tier/intent distributions and writes `measurement.json` per session. Future improvements are scored numerically instead of manually.
- ❓ **Style exemplars + statistical fingerprint** — beyond rules, surfaces concrete code samples and statistical style stats (test framework, naming, line lengths, ...) for higher-fidelity agent grounding. (Code present in `core/exemplars.py` + `core/style_fingerprint.py`; ROI not yet measured against rule-only output.)
- ✅ **Persistent repo cache** — git clones land in `~/.cache/code-hijack/repos/<hash>/` and reuse across runs; no double-clone overhead in skill mode (327fb1a).

## Validation status

Numbers from the 2026-06-11 measurement cycle on `encode/starlette` (skill mode). Earlier cycles on `encode/httpx` and a private-app dogfooding target; see `memory/project_validation_findings.md` for the full chain.

| What | Measured | Source |
|---|---|---|
| Evidence-chain cited rate (senior OSS, best case) | **50%** (starlette v12, 5 categories: architecture+coding_style+api_design+testing+security+performance, depth=30) | v12 session |
| Same on a typical individual-developer repo | **~0%** (HarnessAI: 1 decision-signal commit / 61 scanned) | dogfood-harnessai session |
| External reviewer score (clean LLM session, no codebase context) | **6/10 user-learning, 5/10 AI-coding-guide** | C external eval (v8) |
| Evidence vs no-evidence rule quality gap | **~2x** (external reviewer judgement, intent-kind preserved verbatim helps) | C external eval |
| MUST calibration target | 30–40% MUST overall, ≤50% per category | `_check_must_calibration` |
| Auto-downgrade impact (R6) | starlette MUST 58%→25%, all surviving MUSTs are cited | v8 vs v7 |
| Decision-pattern keywords currently mined | 18 patterns (incl. `instead of`, `rather than`, `to avoid`, `to prevent`, `due to`, `motivated by`, `as opposed to`, `regression`, …) | `archaeology._DECISION_PATTERNS` |
| G category-expansion ROI (verified) | **+5%p evidence per added category** (testing→38%, security→45%, performance→50%) | v10/v11/v12 chain |
| intent_kind diversity — commit mining alone | **rejection/incident: 0** across all prior cycles — senior OSS frames perf/security decisions as `to avoid`/`as opposed to` (preference), not `regression`/`reverted because` (incident) | v10/v11/v12 + R7 phase 1 |
| intent_kind diversity — after PR/issue mining (2026-06-11) | **32 decisions: rejection 22, incident 10** (100 items scanned, starlette) — first non-zero rejection/incident signal in the project's measurement history | 0.3.0 starlette cycle |
| Rule honesty grading (2026-06-11, starlette) | 14 rules: cited 7 / corroborated 5 / speculative 2; **MUST 5/14 (35.7%), all 5 cited** | 0.3.0 starlette cycle |
| Foresight accuracy (2026-06-11, starlette) | 4 cards: **3/4 confirmed** (repo docs + rejection corpus); 1 unconfirmed (honest) | 0.3.0 starlette cycle |
| Tests | **1136 passed** (1020 in 0.3.0) | current main |
| Downstream A/B — rule injection, 3 rounds (2026-07-04) | **Rules rescued the weak model**: Haiku control fell into the buffering anti-pattern the seniors had rejected (PR#1745, full-body buffering measured 9/9 chunks); treatment streamed (1/9) and cited the commit. Frontier (Sonnet) reproduced senior structure with or without rules | first downstream A/B |
| SATD supply→consumption (W2, 2026-07-05) | typer: 26 SATD supplied → 2 refs cited by 1 rule (`satd_citation_ratio` 7.7%, directional). **SATD sustained a cited MUST** on a squash-merge repo with only 2 decision commits | typer W2 cycle |

**Honest read**: the tool's differentiator (verbatim-citation evidence chains) works as advertised on **well-curated senior repos** with PR-style commit bodies. For everyday repos with terse commits, commit mining alone degrades to a "rule + ✅/❌ example" extractor; PR/issue mining now supplements this gap for repos with active issue trackers.

Direction status (2026-06-11):
- **G (more categories)** — verified: +5%p evidence per added category, ceiling now 50% on starlette. Diminishing returns past 5 categories; commit-pool richness, not category count, is the real lever.
- **R7 (commit-corpus-first rule derivation)** — phase 1 complete (`backend/docs/r7_pipeline_reversal.md`). Hypothesis viable on multi-commit clusters (CORS preflight: 3 commits → 1 cluster) but **only 21% of starlette clusters are multi-commit** — single-commit clusters get no advantage over forward pipeline. Phase 2-4 (LLM derivation + verify + external eval) still ungated; will likely become a hybrid forward+inversion mode.
- **D (dogfooding)** — the ceiling-vs-good-enough question. Started on HarnessAI 2026-05-06 (1-week horizon); resolution comes from "did the agent code measurably better with `.code-hijack/CLAUDE.md` than without".

## Positioning (measured, 2026-07)

Who actually benefits, per the first downstream A/B (2026-07-04):

1. **Weak/cheap models get rescued from known anti-patterns.** With rules injected, Haiku avoided the full-body-buffering approach the senior repo had explicitly rejected; without rules it fell straight into it (and its own rationale admitted "must accumulate first"). Frontier models already reproduce senior structure without rules — the tool does not buy them correctness.
2. **Human learners get traceable WHY-provenance.** Rule-injected sessions cite the specific commits/incidents behind each decision; control sessions produce generic reasoning with no sources. This axis holds regardless of model strength, and is the larger measured benefit (learning reader > code-quality reader).

Refinement after 3 A/B rounds (6 tasks, starlette + anyio): **rules change misuse-path behavior, not the happy path.** Every task that discriminated (rejected buffering pattern, deprecation lifecycle, context-manager re-entry guard) diverged on boundary/misuse handling — the part seniors learned from incidents; tasks whose trap was common knowledge or naturally avoided did not discriminate. Efficiency (tokens/turns) showed no consistent gain on self-contained generation tasks.

Two axes settled after R4–R6 (werkzeug + pluggy, 2026-07-05/06):

- **Behavior axis — discrimination requires a "shortcut gap."** Rules change behavior only where the weak model's default implementation is a *shortcut* (naive re-raise polluting tracebacks, silently accepting incompatible options). Where the default is already a robust pattern, or the trap is security common sense, rules are behaviorally redundant — werkzeug (hardening rules, probes 0/3) vs pluggy (shortcut-gap rules, probes 2/3) split exactly on this criterion. **Extraction quality and behavioral discrimination are different axes** (werkzeug: 94% cited yet the worst probe target).
- **Efficiency axis — gains are confined to exploration-type tasks.** On a locate-and-fix task against a real unfixed bug, the rule-injected arm used −67% tool calls and −62% wall time (pluggy #649, N=1 directional) — matching the scope of 2601.20404. On self-contained generation tasks, only the rule-input token overhead (~+20%) remains.

Context against the 2026 literature:

- LLM-**generated** design rationale reaches precision ~0.27 with 1.6–3.2% actively misleading claims ([arxiv 2504.20781](https://arxiv.org/abs/2504.20781)). This is why code-hijack never asks the LLM to author the WHY — it surfaces the senior's **verbatim** evidence (commits, rejected PRs, SATD comments) and mechanically demotes any MUST without a verified citation. The same discipline applies to our own headline metric: `cited` is reported split into **senior-quoted** vs **code-anchored** — a verbatim code observation is not a WHY the seniors wrote down, and we don't count it as one.
- The nearest-neighbor approach, Probe-and-Refine ([arxiv 2606.20512](https://arxiv.org/abs/2606.20512)), tunes repo guidance from synthetic-probe *behavior* (+7.5pp SWE-bench) but carries no provenance — it can say *what* works, not *why the seniors chose it*. code-hijack now carries both: the recorded WHY (verbatim evidence) plus per-rule behavioral probe badges (`behavior-confirmed` — [examples/pluggy](examples/pluggy/) is the first badged sample, 3 probed / 2 discriminated).
- Context files measurably cut agent **cost** at equal completion: −28.6% runtime, −16.6% output tokens ([arxiv 2601.20404](https://arxiv.org/abs/2601.20404)) — but that paper's tasks are repo-exploration shaped. Our own A/B reproduces the gain only in that same scope (−67% tool calls on exploration vs no gain on self-contained generation; see the two axes above).
- The 2026 reassessment of that line of work ([2601.20404v2](https://arxiv.org/html/2601.20404v2) and the [ETH study coverage](https://www.infoq.com/news/2026/03/agents-context-file-value-review/)) found that **LLM-generated context files are on average redundant** — agents rediscover the same information from the repo, so auto-generated files cost ~20% more inference for a ~3% *lower* success rate; only content the agent **cannot discover independently** pays off. That criterion is exactly what code-hijack extracts: verbatim decision history (rejected PRs, incidents, SATD, commit rationale) lives outside the working tree, and agents do not mine git/PR archives mid-task. It also matches our own probe data — rules restating discoverable patterns are behaviorally redundant; the rules that changed behavior encode non-discoverable incident/rejection knowledge (the "shortcut gap"). Commit-rationale extraction is an active research axis (cf. [CoMRAT, arxiv 2506.10986](https://arxiv.org/pdf/2506.10986)).

## Example outputs

**Latest** — [`examples/pluggy/`](examples/pluggy/) (2026-07-06): [pytest-dev/pluggy](https://github.com/pytest-dev/pluggy), 30 files, 21 rules, **100% cited (senior-quoted 10 / code-anchored 11, zero invented citations) / 100% exemplar-verbatim**, 28.6% MUST ratio, foresight 3/3 confirmed, and the first sample with behavioral probe badges (3 probed / 2 discriminated, Haiku control-vs-treatment). The senior-quoted vs code-anchored split is surfaced in `measurement.json` and the generated CLAUDE.md header — a code-anchored rule is a verbatim observation of the code, not a WHY the seniors wrote down.

Earlier — [`examples/starlette/`](examples/starlette/) (2026-05-06, v10 snapshot): [encode/starlette](https://github.com/encode/starlette), 67 files, 16 rules, **38% evidence-chain coverage** (6 verbatim citations including incident-grade evidence on a memory-regression PR), 31% MUST ratio after R6 auto-downgrade. The v11 (+security) and v12 (+performance) cycles ran 2026-05-06 in `hijack-output/validation-starlette-v{11,12}/` (gitignored); the published example reflects the 4-category v10 baseline.

Representative patterns captured:
- Locked middleware positions (ServerError outermost / Exception innermost framework-enforced)
- `anyio` runtime abstraction (`run_in_threadpool` hides sync/async)
- CORS preflight + wildcard/credentials guard (browser-spec compliance enforced at one location)
- `_CachedRequest` body cache vs stream split (memory-regression incident encoded as evidence)
- TestClient backend as constructor arg, not ClassVar
- `tests/types.py` for shared fixture Protocols

Older — [`examples/fastapi/`](examples/fastapi/) (2026-04-17, **stale** — predates 5 tool improvements): tiangolo/fastapi, 17 rules, 35% MUST. Re-run with current tool to refresh.

## Quickstart

### Install

```bash
git clone https://github.com/reasonableplan/code-hijack.git
cd code-hijack/backend
pip install -e ".[dev,api]"
```

Python 3.12+ required.

### CLI mode (requires Anthropic API key)

```bash
export ANTHROPIC_API_KEY=sk-ant-...

# Analyze a repo with the 3 MVP categories
code-hijack analyze https://github.com/tiangolo/fastapi

# Pick specific categories
code-hijack analyze ./my-repo --categories architecture,security,testing

# Preview cost only (no LLM call)
code-hijack analyze ./my-repo --dry-run

# Resume a previous session, skipping completed categories
code-hijack analyze ./my-repo \
    --resume ./docs/hijacked/2026-04-10_my-repo/session.json

# Compare two sessions
code-hijack diff old_session/ new_session/

# Score a session: cited_ratio, must_ratio, tier/intent distributions → measurement.json
code-hijack measure ./docs/hijacked/2026-04-10_my-repo/session.json
```

### Skill mode (inside Claude Code)

```
/code-hijack https://github.com/tiangolo/fastapi
```

Workflow defined in [`.claude/skills/code-hijack/SKILL.md`](.claude/skills/code-hijack/SKILL.md). No API key consumed — the current Claude Code session acts as the LLM.

### HarnessAI export (any session)

```bash
# Convert an existing session into HarnessAI conventions/guidelines/lesson-candidate format
code-hijack harness-export ./docs/hijacked/2026-04-17_fastapi --output ./harness-form
```

Output goes to `<output>/conventions.md`, `<output>/guidelines/<area>/<aspect>.md`, and (if any) `<output>/shared-lessons-candidates.md`. Drop these into a new project's `docs/` and a HarnessAI-style agent will pick up the rules.

## Configuration

Environment variables:

- `HIJACK_CACHE_DIR=/path` — override cache location (default: `~/.cache/code-hijack/repos/`)
- `HIJACK_NO_CACHE=1` — disable cache, fall back to per-run `tempfile.mkdtemp` (set to `0`/`false`/empty to keep cache enabled)
- `ANTHROPIC_API_KEY` — required for CLI mode (`code-hijack analyze`); skill mode does not need it
- `GH_TOKEN` — optional, used by PR-decision mining when the `gh` CLI is unavailable

The MUST-ratio calibration runs automatically on `write_output` and prints a `[WARN]` line to stderr when overall MUST > 40% or any category > 50%. Sample sizes below 5 rules total or 3 per category are skipped to avoid noise.

## Output structure

```
<target>/docs/hijacked/
├── 2026-04-17_fastapi/         # per-session raw analysis
│   ├── meta.md                 # metadata: session ID, selected files, layer distribution, scope distribution
│   ├── architecture.md         # rules per category (rule + ✅/❌ + scope + reason + rationale_tier)
│   ├── coding_style.md
│   ├── api_design.md
│   ├── foresight.md            # inferred design hypotheses (hypothesis + signals + falsification + tier); never MUST
│   ├── pr_decisions.json       # raw PR/issue mining output (rejection + incident decisions)
│   ├── measurement.json        # cited_ratio, must_ratio, tier/intent distributions per session
│   └── session.json            # structured data, reused for diff / harness-export / measure
├── integrated/                 # agent-ready combined view
│   ├── CLAUDE.md               # entry point + layer guide + top MUST rules
│   ├── backend.md              # backend-layer rules across all categories
│   ├── frontend.md
│   ├── database.md
│   ├── devops.md
│   ├── shared.md               # cross-cutting rules
│   ├── foresight.md            # integrated foresight cards across categories
│   └── system-prompt.md        # agent system prompt (rule + ✅/❌/ref inline; context-conditional tone)
└── (harness-form/)             # optional: produced by `harness-export`
    ├── conventions.md          # HarnessAI-style decision tables (cross_project + dependencies)
    ├── guidelines/<area>/*.md  # per-area guides (✅/❌ + design intent)
    └── shared-lessons-candidates.md  # anti-patterns + domain-specific rules (review-only)
```

Copy `integrated/CLAUDE.md` into your own project's Claude Code context, and your agent will follow the extracted style. For HarnessAI projects, copy `harness-form/` contents into the project's `docs/` directly.

## Pipeline

```
input (GitHub URL or local path)
  ↓ Fetcher        — git clone + persistent cache (`~/.cache/code-hijack/repos/<hash>/`)
  ↓ detect_layer   — deterministic layer tagging
  ↓ repo_nature    — library / app / app-cli detection (sets system-prompt tone)
  ↓ Preprocessor   — role classification + per-category file selection
                     (auxiliary path demote, barrel demote, truncate-aware ranking, near-dup dedup)
  ↓ Negative space — deterministic signals (dep_count, stdlib hints, public_ratio, deprecation patterns)
  ↓ Exemplars (G1) — concrete code samples extracted per category
  ↓ Style FP (G2)  — statistical style fingerprint (frameworks, naming, line lengths)
  ↓ Test decisions (B)   — senior defense catalog from test code (parametrize edges, raises blocks)
  ↓ PR/issue mining      — closed-unmerged PRs (rejection) + wontfix issues + maintainer comments
                           via gh CLI; graceful skip if gh unavailable (core/pr_archaeology.py)
  ↓ Commit decisions (C) — decision trails from commit bodies (tried/decided/instead/reverted)
  ↓ Analyzer       — per-category LLM calls with evidence prompts
                     + rationale_tier assignment (cited/corroborated/speculative)
                     + corroborated/speculative MUST → SHOULD at parse time
  ↓ Foresight      — ForesightCard generation (hypothesis + triangulation signals + falsification)
                     + deterministic foresight scoring; rendered to foresight.md
  ↓ Critic         — drop duplicates, downgrade inflated MUST + scope tagging
  ↓ Generator      — per-layer .md + CLAUDE.md + system-prompt.md + foresight.md
                     + auto MUST calibration lint (stderr warn if >40%)
  ↓ Measure        — measurement.json (cited_ratio, must_ratio, tier/intent distributions)
output
```

## Validation

The tool has been dogfooded on 4 real repositories with measured quality improvements from prompt engineering:

| Version | Target | MUST% | ref_files w/ line# | bad_example real code |
|---|---|---|---|---|
| baseline | fastapi | 85% | 0% | 85% |
| +few-shot | fastapi | 57% | 100% | 100% |
| +critic | fastapi | **35%** | **100%** | **100%** |

Target: MUST 30-40% (calibrated for real PR-blocking rules), 100% ref-file line coverage, 100% real-code bad_examples.

**Skill mode validation** (after 2026-05-05 selector / cargo-cult / MUST-lint / cache fixes):

| Repo | Total rules | MUST% | Cargo-cult* | Quality |
|---|---|---|---|---|
| httpx (v1) | 18 | 39% | 4 | 8/10 |
| httpx (v2) | 19 | **32%** | **0** | **9/10** |
| fastapi (v1) | 18 | 44% | 5 | 7/10 |
| fastapi (v2) | 17 | **35%** | **0** | **8/10** |

\* Rules whose body prescribed a specific internal class/function name from the analyzed repo (e.g. `BaseTransport`, `USE_CLIENT_DEFAULT`, `EventSourceResponse`) instead of the underlying design principle. v2 prompts demand principle-level rule bodies with the internal symbol cited in `good_example` only.

## Project structure

```
CLAUDE.md                              # agent-facing guide (short)
README.md / README.ko.md               # English / Korean
LICENSE                                # MIT
CONTRIBUTING.md
.github/workflows/test.yml             # CI: pytest + ruff
.claude/skills/code-hijack/SKILL.md    # Skill mode workflow
backend/
  pyproject.toml                       # setuptools, Python 3.12+
  docs/skeleton.md                     # full design doc
  src/hijack/
    cli.py                             # click group (analyze/diff)
    skill.py                           # skill mode stub (logic lives in SKILL.md)
    errors.py                          # HijackError(ClickException) hierarchy
    core/
      models.py                        # AnalysisRule / CategoryResult / SessionResult @dataclass
      fetcher.py                       # git clone + cache, file collection, detect_layer
      preprocessor.py                  # role classification, file selection (auxiliary demote, truncate-aware)
      prompts.py                       # 10 category prompts + few-shot + cargo-cult guard
      analyzer.py                      # LLM loop + parse + retry
      critic.py                        # rule refinement (drop / downgrade / scope-tag)
      scope_critic.py                  # scope tagging refinement
      session.py                       # session_id, SessionDiff
      generator.py                     # rendering + MUST calibration lint
      harness_export.py                # HarnessAI conventions/guidelines/lesson-candidate adapter
      archaeology.py                   # git history mining (file ages, reverts, commit bodies)
      apply.py                         # render integrated CLAUDE.md
      docs.py                          # repo-level doc ingestion (README/ARCHITECTURE/ADRs)
      evidence.py                      # evidence chain rendering + metrics
      exemplars.py                     # G1: senior code sample catalog
      style_fingerprint.py             # G2: statistical style fingerprint
      test_decisions.py                # B: senior defense catalog from tests
      pr_archaeology.py                # PR/issue mining via gh CLI (rejection + wontfix + maintainer comments)
      negative_space.py                # deterministic negative-space signals (dep_count, public_ratio, …)
      measure.py                       # calc_session_metrics / diff_sessions / score_foresight / write_measurement
      target_stack.py                  # target repo stack detection
    llm/
      base.py                          # BaseLLM ABC
      api.py                           # ClaudeAPIClient (anthropic SDK)
tests/                                 # pytest — 1136 tests, ruff clean
  fixtures/senior_wisdom/              # mini repo for layer-detection tests
examples/                              # real analysis outputs (pluggy / werkzeug / starlette / fastapi)
```

## Honest limitations

This tool produces **"mid-level-senior-style consistent code"**, not **"senior-level design judgment"**. See [the honest assessment section in the Korean README](README.ko.md#한계) for details.

In short:
- ✅ Surface pattern consistency (agent follows the same idioms)
- ✅ Basic correctness (HTTP semantics, RFC compliance)
- ❌ Design judgment in novel situations
- ❌ Trade-off reasoning for context-specific exceptions

What's now mitigated (since 2026-04-17): Git history + PR discussion mining is implemented (exemplars, style fingerprint, test-defense catalog, PR signals, commit decision trails). Rules now carry verbatim evidence with intent classification.

Skill-mode evidence chains (closed 2026-05-06): A2.1 ships `commit_decisions` injection into the skill-mode prompt, so skill-mode runs now populate the same evidence chain as CLI mode. Verified on starlette v3→v12 cycle: matching rate 17%→50%.

PR/issue mining (0.3.0): `pr_archaeology.py` unlocked rejection/incident signals that commit mining alone could not reach. **Known noise**: dependabot bump commits are misclassified as incident (~4-5 of 10 incident signals on starlette); 1 spam PR was classified as rejection. Mining precision is imperfect — treat incident/rejection counts as directional, not exact.

`score_foresight` keyword matching: tokens shorter than 4 characters are not matched, so short operator/symbol names may not register as confirmed signals. Foresight cards involving very short identifiers may stay `speculative` even when corroborating evidence exists.

Remaining gap: **incident-kind evidence** (the most valuable for hallucination prevention per external review) is only partially filled by PR/issue mining — dependabot noise reduces precision. Closing the gap further requires either (a) cross-repo CVE-DB style reference mining, or (b) a different repo class (post-mortem-heavy infra projects).

## Roadmap

- ✅ **Phase 1 (MVP)** — 3 categories × 5 layers, CLI + Skill mode
- ✅ **Phase 2 (expansion)** — 10 categories, `--resume`, `diff` subcommand, SessionDiff
- ✅ **Phase 3a (quality)** — Few-shot prompts, Critic layer, content-density selection
- ✅ **Phase 3b (HarnessAI integration)** — `scope` field (cross_project / framework_internal / domain_specific), `harness-export` subcommand, system-prompt with inline ✅/❌/ref
- ✅ **Phase 4a (decision mining)** — Git history + PR discussion + commit body mining. Modules: `archaeology`, `exemplars` (G1), `style_fingerprint` (G2), `test_decisions` (B), `pr_decisions` (A1), commit-decision pattern mining (C).
- ✅ **Phase 4b (validation hardening, 2026-05-05)** — Layer detection false-positive guards, file selector docs_src demote + truncate-aware ranking, cargo-cult guard in rule extraction, MUST calibration auto-lint, persistent fetch cache.
- ✅ **Phase 4c (skill-mode parity + calibration, 2026-05-06)** — A2.1 commit_decisions injection (skill-mode evidence chains now match CLI mode), R6 auto-downgrade of speculative MUSTs, E1 body-excerpt 800 chars, D pattern set 6→18, G7 cited-MUST self-check guidance, G8 feature-doc noise filter, G9 top-level dotted-py demote.
- ✅ **Phase 3 foresight + Phase 4 evidence expansion (0.3.0, 2026-06-11)** — 3-tier rationale grading (cited/corroborated/speculative), cited-only MUST enforced at parse time, ForesightCard + foresight.md, `core/negative_space.py` deterministic signals, `repo_nature` detection (library/app/app-cli), PR/issue mining via gh CLI (`core/pr_archaeology.py`: first non-zero rejection/incident signals), measurement loop (`core/measure.py` + `code-hijack measure` subcommand, measurement.json). 1020 tests.
- **Phase 5a (planned)** — R7 phase 2-4 (commit-corpus-first rule derivation, hybrid forward+inversion mode).
- **Phase 5b (planned)** — ORM-aware layer detection, additional language support (Go/Rust), incident-kind cross-repo reference mining with improved precision (dependabot noise filter).

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT — see [LICENSE](LICENSE).

## Background

Built using the harnessai + gstack workflow (plan → build → verify → review loop). Incremental commits, 1136 passing tests, dogfooded on 5 repos with documented quality progression (httpx, fastapi, starlette OSS + HarnessAI + code-hijack self). Phase 4b added selector hardening, cargo-cult guards, MUST calibration auto-lint, and persistent fetch cache. Phase 4c (2026-05-06) lifted starlette evidence-chain matching from 17% to 50% via category expansion + skill-mode parity. 0.3.0 (2026-06-11) added foresight inference layer, 3-tier rationale grading with cited-only MUST enforcement, PR/issue mining (first non-zero rejection/incident signals), and numeric measurement loop. Full design documents: [`backend/docs/skeleton.md`](backend/docs/skeleton.md), [`backend/docs/r7_pipeline_reversal.md`](backend/docs/r7_pipeline_reversal.md).
