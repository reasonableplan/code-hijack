# code-hijack

> Extract senior coding style from a codebase into AI-agent-ready rules.

**한국어 README**: [README.ko.md](README.ko.md)

AI agents produce generic, inconsistent code. code-hijack analyzes a senior open-source repository with an LLM to extract **why** the code is written the way it is, then generates rule documents (`CLAUDE.md` + layer-specific `.md` + `system-prompt.md`) that make an agent code in that style.

## Highlights

Tags: ✅ validated with measurable data, ⚠️ partial / has known limits, ❓ implemented but not yet measured. See [Validation status](#validation-status) below for cycle data.

- ✅ **10 analysis categories** — architecture, coding_style, api_design, testing, dependencies, security, performance, devops, state_management, data_model. (3+1 categories matched-validated on starlette; remaining 6 implemented, dogfooding pending.)
- ✅ **5-layer deterministic classification** — frontend / backend / db / devops / shared (path + extension + dep-file heuristics, no LLM guessing). Calibration regression caught and fixed (e117c4c).
- ⚠️ **Evidence-based rules** — every rule includes `ref_files:line`, verbatim ✅/❌ examples from the actual repo, confidence + priority. **Evidence-chain (verbatim commit quotes) ceiling: ~38% matched on senior OSS (starlette), ~0% on individual repos with terse commit messages (HarnessAI)**. Quality-gap with no-evidence rules measured ~2x by external reviewer.
- ❓ **Scope-tagged rules** — every rule is classified `cross_project`, `framework_internal`, or `domain_specific`. Lets a downstream tool auto-apply the safe ones and quarantine the rest. (Code present, end-to-end downstream usage not yet measured.)
- ✅ **Critic layer** — second LLM pass that drops duplicates, downgrades inflated MUST, tags scope. Plus mechanical safeguards: MUST ratio auto-lint (`write_output` stderr warn if >40%), and **R6 auto-downgrade** of speculative MUSTs (no verified citation → SHOULD).
- ✅ **Two execution modes**:
  - **CLI mode** (`code-hijack analyze`) — direct Anthropic API, fully automatable
  - **Skill mode** (`/code-hijack`) — uses the current Claude Code session, no API key needed
- ❓ **HarnessAI integration** — `harness-export` subcommand converts a session into [HarnessAI](https://github.com/reasonableplan/harnessai)-shaped docs. Only `cross_project` rules auto-apply; the rest become reviewable candidates. (Implemented; downstream HarnessAI consumption not yet dogfooded.)
- ❓ **Session management** — `--resume` to skip completed categories, `diff` subcommand to compare rule changes across sessions. (Implemented; usage data thin.)
- ⚠️ **Decision mining from Git** — extracts senior reasoning from PR descriptions, review comments, commit bodies, and reverts; rule `evidence` field carries verbatim quotes with intent classification (rejection/constraint/incident/preference). **Effective when target repo has decision-pattern keywords ("instead of", "rather than", etc.); a typical busy-developer repo may yield close to zero.**
- ❓ **Style exemplars + statistical fingerprint** — beyond rules, surfaces concrete code samples and statistical style stats (test framework, naming, line lengths, ...) for higher-fidelity agent grounding. (Code present in `core/exemplars.py` + `core/style_fingerprint.py`; ROI not yet measured against rule-only output.)
- ✅ **Persistent repo cache** — git clones land in `~/.cache/code-hijack/repos/<hash>/` and reuse across runs; no double-clone overhead in skill mode (327fb1a).

## Validation status

Numbers from the 2026-05-06 measurement cycle on `encode/httpx`, `encode/starlette`, and a private-app dogfooding target. See `memory/project_validation_findings.md` for the full chain.

| What | Measured | Source |
|---|---|---|
| Evidence-chain matching rate (senior OSS, best case) | **38%** (starlette, 4 categories, depth=30) | v10 session |
| Same on a typical individual-developer repo | **~0%** (HarnessAI: 1 decision-signal commit / 61 scanned) | dogfood-harnessai session |
| External reviewer score (clean LLM session, no codebase context) | **6/10 user-learning, 5/10 AI-coding-guide** | C external eval |
| Evidence vs no-evidence rule quality gap | **~2x** (external reviewer judgement, intent-kind preserved verbatim helps) | C external eval |
| MUST calibration target | 30–40% MUST overall, ≤50% per category | `_check_must_calibration` |
| Auto-downgrade impact (R6) | starlette MUST 58%→25%, all surviving MUSTs are cited | v8 vs v7 |
| Decision-pattern keywords currently mined | 18 patterns (incl. `instead of`, `rather than`, `to avoid`, `to prevent`, `due to`, `motivated by`, `as opposed to`, `regression`, …) | `archaeology._DECISION_PATTERNS` |

**Honest read**: the tool's differentiator (verbatim-citation evidence chains) works as advertised on **well-curated senior repos** with PR-style commit bodies. For everyday repos with terse commits, it degrades to a "rule + ✅/❌ example" extractor — still useful, but no different from a generic LLM rule miner. The **R7** (commit-corpus-first rule derivation) and **G** (more analysis categories) directions are the candidates explored to lift the ceiling; dogfooding (D) is what tells us whether the current quality is already "good enough" for actual users.

## Example outputs

[`examples/fastapi/`](examples/fastapi/) — real analysis of [tiangolo/fastapi](https://github.com/tiangolo/fastapi) (1119 files, 17 rules, 35% MUST ratio, 100% line-number coverage).

Representative patterns captured:
- `DefaultPlaceholder` sentinel for "user passed None" vs "user didn't pass"
- `Annotated[T, Doc('''...''')]` for parameter docs that survive refactors
- Starlette subclassing strategy (reuse ASGI, add OpenAPI layer only)
- `auto_error=False` for composable authentication layers

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
│   ├── architecture.md         # rules per category (rule + ✅/❌ + scope + reason)
│   ├── coding_style.md
│   ├── api_design.md
│   └── session.json            # structured data, reused for diff / harness-export
├── integrated/                 # agent-ready combined view
│   ├── CLAUDE.md               # entry point + layer guide + top MUST rules
│   ├── backend.md              # backend-layer rules across all categories
│   ├── frontend.md
│   ├── database.md
│   ├── devops.md
│   ├── shared.md               # cross-cutting rules
│   └── system-prompt.md        # agent system prompt (rule + ✅/❌/ref inline)
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
  ↓ Preprocessor   — role classification + per-category file selection
                     (auxiliary path demote, truncate-aware ranking, near-dup dedup)
  ↓ Exemplars (G1) — concrete code samples extracted per category
  ↓ Style FP (G2)  — statistical style fingerprint (frameworks, naming, line lengths)
  ↓ Test decisions (B) — senior defense catalog from test code (parametrize edges, raises blocks)
  ↓ PR decisions (A1)  — GitHub PR signals (vocabulary, notable PRs, rejected PRs, labels)
  ↓ Commit decisions (C) — decision trails from commit bodies (tried/decided/instead/reverted)
  ↓ Analyzer       — per-category LLM calls with evidence prompts
  ↓ Critic         — drop duplicates, downgrade inflated MUST + scope tagging
  ↓ Generator      — per-layer .md + CLAUDE.md + system-prompt.md
                     + auto MUST calibration lint (stderr warn if >40%)
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
      pr_decisions.py                  # A1: GitHub PR judgment signals
      target_stack.py                  # target repo stack detection
    llm/
      base.py                          # BaseLLM ABC
      api.py                           # ClaudeAPIClient (anthropic SDK)
tests/                                 # pytest — 783 tests, ruff clean
  fixtures/senior_wisdom/              # mini repo for layer-detection tests
examples/                              # real analysis outputs
  fastapi/                             # latest fastapi analysis (17 rules)
```

## Honest limitations

This tool produces **"mid-level-senior-style consistent code"**, not **"senior-level design judgment"**. See [the honest assessment section in the Korean README](README.ko.md#한계) for details.

In short:
- ✅ Surface pattern consistency (agent follows the same idioms)
- ✅ Basic correctness (HTTP semantics, RFC compliance)
- ❌ Design judgment in novel situations
- ❌ Trade-off reasoning for context-specific exceptions

What's now mitigated (since 2026-04-17): Git history + PR discussion mining is implemented (exemplars, style fingerprint, test-defense catalog, PR signals, commit decision trails). Rules now carry verbatim evidence with intent classification.

Remaining gap: in skill mode, evidence chains are empty (the mechanical signal layers run only in CLI mode). Closing this requires injecting pre-computed signals into the skill-mode prompt — work in progress as "A2 LLM distillation".

## Roadmap

- ✅ **Phase 1 (MVP)** — 3 categories × 5 layers, CLI + Skill mode
- ✅ **Phase 2 (expansion)** — 10 categories, `--resume`, `diff` subcommand, SessionDiff
- ✅ **Phase 3a (quality)** — Few-shot prompts, Critic layer, content-density selection
- ✅ **Phase 3b (HarnessAI integration)** — `scope` field (cross_project / framework_internal / domain_specific), `harness-export` subcommand, system-prompt with inline ✅/❌/ref
- ✅ **Phase 4a (decision mining)** — Git history + PR discussion + commit body mining. Modules: `archaeology`, `exemplars` (G1), `style_fingerprint` (G2), `test_decisions` (B), `pr_decisions` (A1), commit-decision pattern mining (C).
- ✅ **Phase 4b (validation hardening, 2026-05-05)** — Layer detection false-positive guards, file selector docs_src demote + truncate-aware ranking, cargo-cult guard in rule extraction, MUST calibration auto-lint, persistent fetch cache.
- **Phase 4c (planned)** — A2 LLM distillation (inject mechanical signals into skill-mode prompt to populate evidence chains), ORM-aware layer detection, additional language support (Go/Rust).

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT — see [LICENSE](LICENSE).

## Background

Built using the harnessai + gstack workflow (plan → build → verify → review loop). Incremental commits, 783 passing tests, dogfooded on 4 repos with documented quality progression. Phase 4b added selector hardening, cargo-cult guards, MUST calibration auto-lint, and persistent fetch cache. Full design document: [`backend/docs/skeleton.md`](backend/docs/skeleton.md).
