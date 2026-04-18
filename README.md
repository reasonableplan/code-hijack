# code-hijack

> Extract senior coding style from a codebase into AI-agent-ready rules.

**한국어 README**: [README.ko.md](README.ko.md)

AI agents produce generic, inconsistent code. code-hijack analyzes a senior open-source repository with an LLM to extract **why** the code is written the way it is, then generates rule documents (`CLAUDE.md` + layer-specific `.md` + `system-prompt.md`) that make an agent code in that style.

## Highlights

- **10 analysis categories** — architecture, coding_style, api_design, testing, dependencies, security, performance, devops, state_management, data_model
- **5-layer deterministic classification** — frontend / backend / db / devops / shared (path + extension + dep-file heuristics, no LLM guessing)
- **Evidence-based rules** — every rule includes `ref_files:line`, verbatim ✅/❌ examples from the actual repo, confidence + priority
- **Critic layer** — second LLM pass that drops duplicates, downgrades inflated MUST, calibrates priority ratio
- **Two execution modes**:
  - **CLI mode** (`code-hijack analyze`) — direct Anthropic API, fully automatable
  - **Skill mode** (`/code-hijack`) — uses the current Claude Code session, no API key needed
- **Session management** — `--resume` to skip completed categories, `diff` subcommand to compare rule changes across sessions

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

## Output structure

```
<target>/docs/hijacked/
├── 2026-04-17_fastapi/         # per-session raw analysis
│   ├── meta.md                 # metadata: session ID, selected files, layer distribution
│   ├── architecture.md         # rules per category (rule + ✅/❌ + reason)
│   ├── coding_style.md
│   ├── api_design.md
│   └── session.json            # structured data, reused for diff
└── integrated/                 # agent-ready combined view
    ├── CLAUDE.md               # entry point + layer guide + top MUST rules
    ├── backend.md              # backend-layer rules across all categories
    ├── frontend.md
    ├── database.md
    ├── devops.md
    ├── shared.md               # cross-cutting rules
    └── system-prompt.md        # agent system prompt
```

Copy `integrated/CLAUDE.md` into your own project's Claude Code context, and your agent will follow the extracted style.

## Pipeline

```
input (GitHub URL or local path)
  ↓ Fetcher        — git clone, collect .py/.ts/.tsx, skip _SKIP_DIRS
  ↓ detect_layer   — deterministic layer tagging (path + ext + dep-file rules)
  ↓ Preprocessor   — role classification (entry_point/api/model/…) + per-category file selection
                     (content-density ranking, near-duplicate dedup)
  ↓ Analyzer       — per-category LLM calls via BaseLLM ABC
                     (few-shot-enhanced JSON output + regex fallback, 2 retries)
  ↓ Critic         — second LLM pass: drop duplicates, downgrade inflated MUST (optional)
  ↓ Generator      — per-layer .md + entry-point CLAUDE.md + system-prompt.md
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
      fetcher.py                       # git clone, file collection, detect_layer
      preprocessor.py                  # role classification, 2D grouping, file selection
      prompts.py                       # 10 category prompts + few-shot examples
      analyzer.py                      # LLM loop + parse + retry
      critic.py                        # second-pass rule refinement
      session.py                       # session_id, SessionDiff
      generator.py                     # layer .md + CLAUDE.md rendering
    llm/
      base.py                          # BaseLLM ABC
      api.py                           # ClaudeAPIClient (anthropic SDK)
tests/                                 # pytest — 188 tests, ruff clean
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

Future direction to narrow this gap: **Git history + PR discussion mining** (Phase 3) to extract not just patterns but the decisions behind them.

## Roadmap

- ✅ **Phase 1 (MVP)** — 3 categories × 5 layers, CLI + Skill mode
- ✅ **Phase 2 (expansion)** — 10 categories, `--resume`, `diff` subcommand, SessionDiff
- ✅ **Phase 3a (quality)** — Few-shot prompts, Critic layer, content-density selection
- **Phase 3b (planned)** — Git history mining, `design_decisions` category, RAG integration

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT — see [LICENSE](LICENSE).

## Background

Built over ~1 week using the harnessai + gstack workflow (plan → build → verify → review loop). 8 incremental commits, 188 passing tests, dogfooded on 4 repos with documented quality progression. Full design document: [`backend/docs/skeleton.md`](backend/docs/skeleton.md).
