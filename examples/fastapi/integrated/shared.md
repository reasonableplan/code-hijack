# Shared Layer Rules

> Cross-cutting rules (any layer) → applies to all work

**Total rules**: 1

## Coding Style

### Use Python 3.10+ PEP 604 union syntax (`X | None`) consistently, not `Optional[X]` or `Union[X, None]`.

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `shared`

**Why**: One syntax across the codebase keeps diffs small and keeps imports clean; FastAPI explicitly targets modern Python, so the legacy form is dead weight.

**Reference**: `fastapi/params.py:33-37`, `fastapi/exceptions.py:70-82`, `fastapi/dependencies/models.py:39-51`

**✅ Good**:
```
default_factory: Callable[[], Any] | None = _Unset,
alias: str | None = None,
validation_alias: str | AliasPath | AliasChoices | None = None,
```

**❌ Bad**:
```
from typing import Optional, Union
default_factory: Optional[Callable[[], Any]] = None
validation_alias: Union[str, AliasPath, AliasChoices, None] = None
```
