# Analysis Metadata

- **Session ID**: `2026-07-06_pluggy`
- **Target**: https://github.com/pytest-dev/pluggy
- **Model**: `claude-code-skill-mode`
- **Timestamp**: 2026-07-06T03:09:21.636342+00:00
- **Duration**: 0.0s
- **Files analyzed**: 30

## Selected Files

- `docs/conf.py`
- `downstream/run_downstream.py`
- `scripts/release.py`
- `scripts/towncrier-draft-to-file.py`
- `testing/benchmark.py`
- `testing/conftest.py`
- `testing/test_details.py`
- `testing/test_helpers.py`
- `testing/test_hookcaller.py`
- `testing/test_invocations.py`
- `testing/test_multicall.py`
- `testing/test_pluginmanager.py`
- `testing/test_result.py`
- `testing/test_tracer.py`
- `testing/test_warnings.py`
- `src/pluggy/_callers.py`
- `src/pluggy/_hooks.py`
- `src/pluggy/_manager.py`
- `src/pluggy/_result.py`
- `src/pluggy/_tracing.py`
- `src/pluggy/_warnings.py`
- `src/pluggy/__init__.py`
- `docs/examples/toy-example.py`
- `docs/examples/eggsample/setup.py`
- `docs/examples/eggsample-spam/eggsample_spam.py`
- `docs/examples/eggsample-spam/setup.py`
- `docs/examples/eggsample/eggsample/hookspecs.py`
- `docs/examples/eggsample/eggsample/host.py`
- `docs/examples/eggsample/eggsample/lib.py`
- `docs/examples/eggsample/eggsample/__init__.py`

## Layer Distribution

```
Layer distribution:
  frontend: 0 files
  backend: 0 files
  db: 0 files
  devops: 0 files
  shared: 30 files
```

## Project Structure

```
8935d2002c98813f/
docs/
  conf.py
  examples/
    eggsample/
    eggsample-spam/
      eggsample_spam.py
      setup.py
      eggsample/
        __init__.py
        hookspecs.py
        host.py
        lib.py
      setup.py
    toy-example.py
downstream/
  run_downstream.py
scripts/
  release.py
  towncrier-draft-to-file.py
src/
  pluggy/
    __init__.py
    _callers.py
    _hooks.py
    _manager.py
    _result.py
    _tracing.py
    _warnings.py
testing/
  benchmark.py
  conftest.py
  test_details.py
  test_helpers.py
  test_hookcaller.py
  test_invocations.py
  test_multicall.py
  test_pluginmanager.py
  test_result.py
  test_tracer.py
  test_warnings.py
```

## Category Results

- **architecture**: 8 rules ✅
- **coding_style**: 6 rules ✅
- **api_design**: 7 rules ✅

## Scope Distribution

- **cross_project**: 21 (100%)
- **framework_internal**: 0 (0%)
- **domain_specific**: 0 (0%)

## Evidence Coverage

How many rules cite real artifacts (commit SHA / PR# / quoted revert / ADR)
versus generic justifications. Higher cited-ratio = less LLM opinion.
Cited splits into history-anchored (a decision record) and code-anchored
(only a ref_files path:line) — history is the stronger WHY signal.
Fake citations are commit SHAs the LLM invented — they were not in the input.

- **Cited**: 21 (100%) — history 10 (47%), code 11 (52%)
- **No-evidence (flagged)**: 0 (0%)
- **Fake citation (hallucinated SHA)**: 0 (0%)
- **Generic justification**: 0 (0%)
- **Other (uncited)**: 0 (0%)
- **Total rules**: 21

### By Category

| Category | Cited | No-evidence | Fake | Generic | Other | Total | Cited % |
|---|---:|---:|---:|---:|---:|---:|---:|
| architecture | 8 | 0 | 0 | 0 | 0 | 8 | 100% |
| coding_style | 6 | 0 | 0 | 0 | 0 | 6 | 100% |
| api_design | 7 | 0 | 0 | 0 | 0 | 7 | 100% |