# Coding Style Analysis

## Design Intent

Every module follows `from __future__ import annotations` plus sorted imports at the top of the module. ASGI types are defined in a single module (types.py) and other modules import from there. Optional dependencies follow the try/import + None fallback + assert-on-use pattern. Wherever typing precision is needed (async detection, Config callable, etc.), it's expressed with `@overload`.

## Rules (4)

### Every public module puts `from __future__ import annotations` at the top, and ASGI types are defined in a separate single module (types.py) for other modules to import. Never define a type alias in two places.

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: [no-evidence] If the same type alias is defined in two modules, behavior diverges depending on import path, and a new ASGI spec change updating only one location causes silent drift.

**Reference**: `starlette/types.py:1-26`, `starlette/applications.py:1-13`, `starlette/middleware/base.py:1-11`

**✅ Good**:
```
# starlette/types.py
from collections.abc import Awaitable, Callable, Mapping, MutableMapping
from contextlib import AbstractAsyncContextManager
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

# starlette/applications.py
from starlette.types import ASGIApp, ExceptionHandler, Lifespan, Receive, Scope, Send
```

**❌ Bad**:
```
# starlette/applications.py
Scope = dict  # same alias defined per module — drift risk
Receive = Callable[[], Awaitable[dict]]

# starlette/middleware/base.py
Scope = MutableMapping[str, Any]  # different definition — user code breaks depending on which import it's coupled to
```

### Optional dependencies use try/except ModuleNotFoundError → None fallback at module import time, and are explicitly verified with assert at point of use. Never force the dependency at import time.

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: [no-evidence] Forcing the dependency at import time burdens the user with install cost for a feature they don't use. Lazy + assert aligns the cost with user intent.

**Reference**: `starlette/schemas.py:12-24`, `starlette/_utils.py:11-23`

**✅ Good**:
```
try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]


class OpenAPIResponse(Response):
    media_type = "application/vnd.oai.openapi"

    def render(self, content: Any) -> bytes:
        assert yaml is not None, "`pyyaml` must be installed to use OpenAPIResponse."
        assert isinstance(content, dict), "The schema passed to OpenAPIResponse should be a dictionary."
        return yaml.dump(content, default_flow_style=False).encode("utf-8")
```

**❌ Bad**:
```
import yaml  # forced at import time — yaml must be installed even if the user never uses OpenAPI

class OpenAPIResponse(Response):
    def render(self, content):
        return yaml.dump(content).encode()
```

### Callables that need typing precision (sync/async branching, multi-signature factories) split their signatures with `typing.overload` so type inference narrows correctly at the call site.

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: The static analyzer needs to know the narrowed type after sync/async branching to catch bugs like a missing await — overload provides that hint.

**Reference**: `starlette/_utils.py:30-42`, `starlette/config.py`

**✅ Good**:
```
@overload
def is_async_callable(obj: AwaitableCallable[T]) -> TypeIs[AwaitableCallable[T]]: ...


@overload
def is_async_callable(obj: Any) -> TypeIs[AwaitableCallable[Any]]: ...


def is_async_callable(obj: Any) -> Any:
    while isinstance(obj, functools.partial):
        obj = obj.func
    return iscoroutinefunction(obj) or (callable(obj) and iscoroutinefunction(obj.__call__))
```

**❌ Bad**:
```
def is_async_callable(obj):  # caller gets Any, wrecking type inference in downstream code
    return iscoroutinefunction(obj) or ...
```

**Evidence**:

1. [PREFERENCE] · COMMIT `48dea4d` — add typing overloads for Config.__call__ (#1097)
   > add typing overloads for Config.__call__ — without overloads, the return type collapsed to Any when callers passed a default, defeating type checking on the consumer side. Overloads narrow the return type per-signature.

### Exception / dataclass-like wrapper classes take status code/code as positional in `__init__`, detail/reason as keyword optional, and explicitly define `__str__`/`__repr__` to make debugging output consistent.

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: [no-evidence] Without explicit __str__/__repr__ on the exception, log output degrades to a default repr like "HTTPException(...)". Explicit definitions keep the debugging surface consistent.

**Reference**: `starlette/exceptions.py:7-33`

**✅ Good**:
```
class HTTPException(Exception):
    def __init__(self, status_code: int, detail: str | None = None, headers: Mapping[str, str] | None = None) -> None:
        if detail is None:
            detail = http.HTTPStatus(status_code).phrase
        self.status_code = status_code
        self.detail = detail
        self.headers = headers

    def __str__(self) -> str:
        return f"{self.status_code}: {self.detail}"

    def __repr__(self) -> str:
        class_name = self.__class__.__name__
        return f"{class_name}(status_code={self.status_code!r}, detail={self.detail!r})"
```

**❌ Bad**:
```
class HTTPException(Exception):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)  # no access to status_code/detail, inconsistent error messages
```

## Anti-Patterns

### Defining a type alias across multiple modules

**Why**: Silent drift depending on import path

**Alternative**: A single types.py module

### Import-time forced import of an optional dependency

**Why**: Forces a dependency for a feature the user doesn't use

**Alternative**: try/import + None + assert at point of use

## File-Type Guides

### types.py

Single source for ASGI/domain type aliases. Other modules only import.

### top of module

from __future__ import annotations + sorted imports (stdlib → third-party → local)

## Checklist

- [ ] Does every new module have `from __future__ import annotations`?
- [ ] Is the new type alias defined in types.py (or equivalent)?
- [ ] Is the optional dependency not forced at import time?
- [ ] Is @overload appropriate for the sync/async branching callable?
