# Foresight — design intent inferred in a `library` context

> ForesightCards are LLM-inferred hypotheses — considerations, not mandates.

## [corroborated] pluggy is the bottommost dependency of the entire pytest/tox/devpi ecosystem, so it deliberately maintains zero runtime dependencies — because a single dependency here propagates to the whole ecosystem

**Supporting signals**:
- negative_space dep_count=0 — pyproject.toml [project.dependencies] is empty
- src/pluggy/_result.py, _tracing.py, _warnings.py — implemented directly with stdlib only (direct_impl_hints)
- README.rst — 'This is the core framework used by the pytest, tox, and devpi projects.'

**Falsification**: Rejected if a commit/PR adding a runtime dependency gets merged

## [corroborated] Performance of the hook-call hot path is an explicit design priority — since pytest calls hooks tens of thousands of times, the tradeoff of raising registration (cold) cost to lower call (hot) cost is repeated

**Supporting signals**:
- 63b7e90 — 'avoid the list concatenation in the hot call path... it is much colder than calling so the tradeoff makes sense'
- 1288091 — removes a runtime cast() call: 'It actually adds measurable overhead here -- ~15% according to testing/benchmark.py'
- testing/benchmark.py — a benchmark comparing varnames __code__ vs inspect.signature lives here (fd62ef8)

**Falsification**: Rejected if a change adding convenience overhead to the hot call path without benchmark evidence gets merged

## [corroborated] Maintaining backward compatibility dictates even architectural decisions — keeping a separate resident function for the old-style hookwrapper executor, and even maintaining a suppress list waiting for third-party fix releases, reflects the principle that 'the library bears the cost until the ecosystem migrates'

**Supporting signals**:
- src/pluggy/_callers.py:27-57 — keeps a dedicated executor function for old-style hookwrapper
- src/pluggy/_hooks.py:294-303 — _NOSELF_WARN_SUPPRESS: 'pytest-timeout >=2.3.2 has the fix, but is unreleased as of 2026-05'
- src/pluggy/_result.py:106-107 and 3 other places — 'Historical name (pluggy<=1.2), kept for backward compatibility.'

**Falsification**: Rejected if releases repeatedly remove legacy support immediately with no deprecation period
