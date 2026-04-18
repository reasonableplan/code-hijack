# Contributing to code-hijack

Contributions welcome — issues, PRs, feedback from real dogfooding.

## Development setup

```bash
git clone https://github.com/reasonableplan/code-hijack.git
cd code-hijack/backend
pip install -e ".[dev,api]"
pytest ../tests/                 # 188 tests, ~2s
ruff check src/ ../tests/        # must be clean
```

Python 3.12+ required.

## Before submitting a PR

1. All tests pass: `pytest ../tests/`
2. Lint clean: `ruff check src/ ../tests/`
3. New features have tests (see `tests/test_*.py` for conventions)
4. Commit messages follow the style in `git log` (scope: short summary + body with rationale)

## Project structure

See [README.md](README.md#프로젝트-구조) for the directory layout.

## Core design principles

Documented in [`backend/docs/skeleton.md`](backend/docs/skeleton.md) §7:

- Single-direction pipeline (Fetcher → Preprocessor → Analyzer → Generator)
- LLM calls must go through `BaseLLM` ABC — mockable in tests
- `@dataclass` only — Pydantic excluded intentionally
- Deterministic layer tagging — no LLM guessing
- Windows/macOS/Linux compatible — use `Path.as_posix()`, never `str(path)`

## What would be a great contribution

- **Dogfooding reports** — real analysis on a new repo + qualitative feedback
- **New language support** — currently Python + TypeScript. Go/Rust welcome.
- **Critic layer improvements** — better MUST/SHOULD calibration prompts
- **2-pass analysis** — signatures → deep file selection (documented as Phase 3 in README)
- **Git history mining** — extract design decisions from commit/PR history (Phase 3)

## Questions?

Open an issue. Honest feedback > silence.
