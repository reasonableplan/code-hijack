# Api Design Analysis

## Design Intent

Public APIs stabilize their signatures with keyword-only optionals + explicit defaults, and never expose internal framework decisions (middleware position, runtime abstraction) to the user. Extension hooks support subclassing as a first-class citizen via a generic TypeVar (`AppType`), and mutation at a point where it's no longer valid (start after middleware registration) is explicitly rejected with RuntimeError.

## Rules (4)

### Public configuration objects (Application, Middleware) take all options as keyword-only optionals, with defaults set to the most conservative/safe value (debug=False, allow_origins=()).

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: [no-evidence] If a public option lacks an explicit default, user code silently breaks whenever the default changes. Also, a *args/**kwargs signature isn't caught by the type checker.

**Reference**: `starlette/applications.py:22-29`, `starlette/middleware/cors.py:16-27`

**✅ Good**:
```
class Starlette:
    def __init__(
        self: AppType,
        debug: bool = False,
        routes: Sequence[BaseRoute] | None = None,
        middleware: Sequence[Middleware] | None = None,
        exception_handlers: Mapping[Any, ExceptionHandler] | None = None,
        lifespan: Lifespan[AppType] | None = None,
    ) -> None: ...

class CORSMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        allow_origins: Sequence[str] = (),
        allow_methods: Sequence[str] = ("GET",),
        allow_headers: Sequence[str] = (),
        allow_credentials: bool = False,
        max_age: int = 600,
    ) -> None: ...
```

**❌ Bad**:
```
class Starlette:
    def __init__(self, *args, **kwargs):  # ambiguous signature, defaults unknowable
        self.debug = kwargs.get('debug', True)  # dangerous default
```

### To explicitly support Application extension (subclassing) as a first-class citizen, a generic TypeVar (`AppType = TypeVar('AppType', bound='Starlette')`) is defined and threaded through callback signatures like Lifespan.

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: [no-evidence] Without a generic TypeVar, subclassing means the subclass's extra methods/attributes can't be used type-safely in the lifespan callback. AppType makes it subclass-friendly.

**Reference**: `starlette/applications.py:15-22`, `starlette/types.py:10-22`

**✅ Good**:
```
AppType = TypeVar("AppType", bound="Starlette")

class Starlette:
    def __init__(
        self: AppType,
        ...
        lifespan: Lifespan[AppType] | None = None,
    ) -> None: ...

# types.py
StatelessLifespan = Callable[[AppType], AbstractAsyncContextManager[None]]
StatefulLifespan = Callable[[AppType], AbstractAsyncContextManager[Mapping[str, Any]]]
Lifespan = StatelessLifespan[AppType] | StatefulLifespan[AppType]
```

**❌ Bad**:
```
class Starlette:
    def __init__(self, lifespan=None):  # subclass's lifespan callback only receives Starlette itself — no access to extra methods
        ...
```

### Calling a mutating API at a point where change is no longer valid (an application that's already started, a client that's already closed) is explicitly rejected with RuntimeError. No silent no-op or lazy reset.

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: [no-evidence] Silently accepting a post-start mutation means the first and second requests get processed by different stacks. RuntimeError makes the intent clear to the user.

**Reference**: `starlette/applications.py:98-101`

**✅ Good**:
```
def add_middleware(self, middleware_class: _MiddlewareFactory[P], *args: P.args, **kwargs: P.kwargs) -> None:
    if self.middleware_stack is not None:  # pragma: no cover
        raise RuntimeError("Cannot add middleware after an application has started")
    self.user_middleware.insert(0, Middleware(middleware_class, *args, **kwargs))
```

**❌ Bad**:
```
def add_middleware(self, middleware_class, *args, **kwargs):
    self.user_middleware.append(Middleware(middleware_class, *args, **kwargs))
    self.middleware_stack = None  # silent reset — unclear which stack handled requests already received
```

### Domain-specific exceptions (HTTPException, WebSocketException) take status code/code as positional in `__init__` and detail/reason as optional, auto-filling the standard phrase for the status code when detail isn't provided.

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: [no-evidence] Status-code-first + standard phrase auto-fill reduces user boilerplate and guarantees response consistency.

**Reference**: `starlette/exceptions.py:7-13`

**✅ Good**:
```
class HTTPException(Exception):
    def __init__(self, status_code: int, detail: str | None = None, headers: Mapping[str, str] | None = None) -> None:
        if detail is None:
            detail = http.HTTPStatus(status_code).phrase  # 401 → 'Unauthorized' automatically
        self.status_code = status_code
        self.detail = detail
        self.headers = headers
```

**❌ Bad**:
```
raise HTTPException("unauthorized")  # status code incidental or missing
# or
raise HTTPException(401)  # user must always fill in detail — boilerplate
```

## Anti-Patterns

### Public __init__ taking *args/**kwargs

**Why**: Evades the type checker, defaults are ambiguous

**Alternative**: Explicit keyword-only optional + conservative default

### Silently handling post-start mutation

**Why**: Breaks consistency between the first and second request's stack

**Alternative**: Reject with RuntimeError

## File-Type Guides

### applications.py

Top-level Application class. Public init options use conservative defaults + AppType generic.

### exceptions.py

Domain exception hierarchy. status code positional + detail optional + auto-phrase.

## Checklist

- [ ] Does the new public API use keyword-only optionals with explicit defaults?
- [ ] Does a subclass-friendly generic TypeVar flow through callback signatures?
- [ ] Is post-start mutation rejected with RuntimeError?
- [ ] Does the domain exception follow the status-code-positional + auto-phrase pattern?
