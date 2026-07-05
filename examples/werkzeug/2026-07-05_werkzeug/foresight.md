# Foresight — `library` 맥락에서 추론된 설계 의도

> ForesightCard 는 LLM 추론 기반 가설이다. 강제 제약이 아닌 고려 사항.

## [corroborated] Werkzeug deliberately keeps runtime dependencies to an absolute minimum (a single required dependency) so it can remain an embeddable low-level WSGI toolkit that frameworks like Flask build on, without forcing template-engine/database/etc. choices onto downstream applications.

**뒷받침 신호**:
- pyproject.toml:23-25 — dependencies = ["markupsafe>=3.0.3"] (only one required runtime dependency)
- README.md — "Werkzeug doesn't enforce any dependencies. It is up to the developer to choose a template engine, database adapter, and even how to handle requests."

**반증 조건**: If a future release adds several new required runtime dependencies without an unavoidable security/standards justification, this hypothesis is refuted.

## [corroborated] The maintainers intentionally treat 'importable from the module' as the de facto public API contract instead of curating an explicit `__all__` export list, accepting that most module-level names are effectively public and must be handled through docstring/versionchanged discipline rather than access control.

**뒷받침 신호**:
- grep '^__all__' over src/werkzeug/**/*.py returns zero matches (verified via Grep tool during this analysis)
- negative_space.public_ratio = 0.913 (public_ratio measured directly from the codebase during step 1)

**반증 조건**: If a future version introduces `__all__` in a majority of modules to curate the public surface, this hypothesis is refuted.

## [corroborated] Security-sensitive modules (password hashing, safe path joining) are deliberately implemented using only the Python standard library, avoiding third-party crypto/path dependencies, to minimize the supply-chain attack surface of the most safety-critical code paths.

**뒷받침 신호**:
- src/werkzeug/security.py:1-7 imports only hashlib, hmac, os, posixpath, secrets (verified by direct Read during this analysis)
- negative_space.direct_impl_hints includes 'src/werkzeug/security.py' (stdlib-only implementation flagged by the step 1 tool)

**반증 조건**: If security.py adds a runtime dependency on a third-party crypto or path-handling library in a future version, this hypothesis is refuted.
