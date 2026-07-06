# Shared Layer Rules

> These rules were extracted in a `library` context

> Cross-cutting rules (any layer) → applies to all work

**Total rules**: 16

## Architecture

### The ASGI app's middleware stack locks two positions — outermost (server error handler) and innermost (exception → response conversion) — as framework-internal; user-registered middleware only goes in between. user_middleware cannot bypass or replace the error/exception handlers.

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: [no-evidence] A poorly written user middleware can leak 5xx responses or expose tracebacks. The error/exception position must be enforced so the framework can own fault isolation.

**Reference**: `starlette/applications.py:57-77`

**✅ Good**:
```
def build_middleware_stack(self) -> ASGIApp:
    debug = self.debug
    error_handler = None
    exception_handlers: dict[Any, ExceptionHandler] = {}
    for key, value in self.exception_handlers.items():
        if key in (500, Exception):
            error_handler = value
        else:
            exception_handlers[key] = value
    middleware = (
        [Middleware(ServerErrorMiddleware, handler=error_handler, debug=debug)]
        + self.user_middleware
        + [Middleware(ExceptionMiddleware, handlers=exception_handlers, debug=debug)]
    )
    app = self.router
    for cls, args, kwargs in reversed(middleware):
        app = cls(app, *args, **kwargs)
    return app
```

**❌ Bad**:
```
self.middleware_stack = list(user_middleware)  # error/exception handler can be bypassed by user middleware
for cls in self.middleware_stack:
    app = cls(app)
```

### Sync/async conversion happens in exactly one place (the runtime abstraction layer). If the user endpoint is a sync function, it's automatically dispatched to a thread pool; if async, it's called directly. User code never imports asyncio/anyio directly.

**Priority**: `MUST` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: Without a single async runtime abstraction, sync/async branching and direct runtime-library imports leak into every endpoint.

**Reference**: `starlette/routing.py:46-66`, `starlette/_utils.py:38-42`, `starlette/concurrency.py`

**✅ Good**:
```
def request_response(
    func: Callable[[Request], Awaitable[Response] | Response],
) -> ASGIApp:
    f: Callable[[Request], Awaitable[Response]] = (
        func if is_async_callable(func) else functools.partial(run_in_threadpool, func)
    )

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        request = Request(scope, receive, send)
        async def app(scope, receive, send):
            response = await f(request)
            await response(scope, receive, send)
        await wrap_app_handling_exceptions(app, request)(scope, receive, send)
    return app
```

**❌ Bad**:
```
async def app(scope, receive, send):
    if asyncio.iscoroutinefunction(func):  # user code branches every time — coupled to the async runtime
        response = await func(request)
    else:
        response = await asyncio.get_event_loop().run_in_executor(None, func, request)
```

**Evidence**:

1. [PREFERENCE] · COMMIT `42592d6` — anyio integration (#1157)
   > anyio integration — switched concurrency primitives so the framework supports both asyncio and trio backends through a single shim, instead of importing asyncio directly throughout the codebase.

### Cross-cutting policies like CORS are narrowly isolated into a single middleware class, and that class explicitly branches preflight (OPTIONS + Access-Control-Request-Method) vs simple requests. Security guards such as the wildcard `*` + credentials conflict are also handled in the same place.

**Priority**: `MUST` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: Without separating preflight from simple request handling and centralizing the wildcard/credentials conflict guard, security holes appear per endpoint.

**Reference**: `starlette/middleware/cors.py:35-76`, `starlette/middleware/cors.py:78-96`

**✅ Good**:
```
preflight_explicit_allow_origin = not allow_all_origins or allow_credentials

if preflight_explicit_allow_origin:
    # The origin value will be set in preflight_response() if it is allowed.
    preflight_headers["Vary"] = "Origin"
else:
    preflight_headers["Access-Control-Allow-Origin"] = "*"

async def __call__(self, scope, receive, send):
    method = scope["method"]
    headers = Headers(scope=scope)
    origin = headers.get("origin")
    if origin is None:
        await self.app(scope, receive, send)
        return
    if method == "OPTIONS" and "access-control-request-method" in headers:
        response = self.preflight_response(request_headers=headers)
        await response(scope, receive, send)
        return
    await self.simple_response(scope, receive, send, request_headers=headers)
```

**❌ Bad**:
```
if request.headers.get('origin'):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Credentials'] = 'true'  # wildcard + credentials conflict — browsers reject this
```

**Evidence**:

1. [PREFERENCE] · COMMIT `7a0f89a` — Respond to credentialed requests with specific origin (#1402)
   > Respond to credentialed requests with specific origin instead of wildcard — the spec forbids `Access-Control-Allow-Origin: *` together with `Access-Control-Allow-Credentials: true`, browsers will reject the response.

### When middleware accesses the request body, explicitly branch between body() (caches the entire thing in memory) and stream() (consumed once) to pass it safely to the downstream app. If both are called, handle it as stream-consumed or disconnect.

**Priority**: `MUST` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: Without a cache/stream branch guard on body access, large request uploads cause a memory blowup or a downstream hang.

**Reference**: `starlette/middleware/base.py:20-93`

**✅ Good**:
```
class _CachedRequest(Request):
    """
    If the user calls Request.body() from their dispatch function
    we cache the entire request body in memory and pass that to downstream middlewares,
    but if they call Request.stream() then all we do is send an
    empty body so that downstream things don't hang forever.
    """

    async def wrapped_receive(self) -> Message:
        if self._wrapped_rcv_disconnected:
            return {"type": "http.disconnect"}
        if self._wrapped_rcv_consumed:
            ...
        if getattr(self, "_body", None) is not None:
            return {"type": "http.request", "body": self._body, "more_body": False}
        elif self._stream_consumed:
            return {"type": "http.request", "body": b"", "more_body": False}
```

**❌ Bad**:
```
async def dispatch(self, request, call_next):
    body = await request.body()  # caches everything in memory, blows up on large uploads
    ...
    return await call_next(request)  # downstream sees the body already consumed
```

**Evidence**:

1. [INCIDENT] · COMMIT `3d77a1c` — Fix high memory usage when using BaseHTTPMiddleware (#1745)
   > Fix high memory usage when using BaseHTTPMiddleware — middleware was buffering the entire response body before sending it on, which caused unbounded memory growth on large streamed responses. Stream the body through to avoid the buffer accumulation.

## Coding Style

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

## Api Design

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

## Testing

### Common types for test fixtures (TestClientFactory, ASGI app stub, etc.) are collected in a separate single module (`tests/types.py`), and other test modules import from there. Never redefine the same type in every test module.

**Priority**: `MUST` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: Redefining test types per module lets the fixture signature silently drift — passing in one place doesn't guarantee type consistency elsewhere.

**Reference**: `tests/middleware/test_base.py:23`, `tests/test_applications.py:25`

**✅ Good**:
```
# tests/types.py
from typing import Protocol


class TestClientFactory(Protocol):
    def __call__(self, app: ASGIApp, *, backend: str = ...) -> TestClient: ...


# tests/middleware/test_base.py
from tests.types import TestClientFactory

def test_middleware(test_client_factory: TestClientFactory) -> None:
    client = test_client_factory(app)
```

**❌ Bad**:
```
# tests/middleware/test_base.py
TestClientFactory = Callable[[ASGIApp], TestClient]  # only in this module

# tests/test_routing.py
TestClientFactory = Callable[[ASGIApp], TestClient]  # defined again — drift
```

**Evidence**:

1. [PREFERENCE] · COMMIT `78fcd54` — Create types module inside tests (#2502)
   > Create types module inside tests * Apply suggestions from code review * Apply suggestions from code review * Fix check errors * Change testclientfactory due to autotest * No cover fix * Apply suggestions from code review * Skip code coverage for TestClientFactory protocol

### A sync-test wrapper like TestClient takes the async runtime backend (asyncio/trio) and its options as constructor arguments. Never hardcode the backend as a ClassVar or module-global.

**Priority**: `MUST` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: A ClassVar backend breaks isolation between concurrent trio + asyncio tests, and prevents the user from verifying backend-specific behavior.

**Reference**: `starlette/testclient.py:1-50`

**✅ Good**:
```
class TestClient(httpx.Client):
    def __init__(
        self,
        app: ASGIApp,
        base_url: str = "http://testserver",
        backend: Literal["asyncio", "trio"] = "asyncio",
        backend_options: dict[str, Any] | None = None,
    ) -> None:
        self.async_backend = _AsyncBackend(
            backend=backend,
            backend_options=backend_options or {},
        )
```

**❌ Bad**:
```
class TestClient(httpx.Client):
    backend: ClassVar[str] = "asyncio"  # shared by all instances — no trio isolation

    def __init__(self, app):
        super().__init__()
```

**Evidence**:

1. [PREFERENCE] · COMMIT `d222b87` — TestClient accepts backend and backend_options as arguments to constructor (#1211)
   > as opposed to ClassVar assignment

### Optional test-only dependencies (httpx for TestClient, etc.) are handled with `try: import` + `except ModuleNotFoundError: raise RuntimeError(...install guide...)`. Unlike the lazy + None + assert pattern used in regular code, this raises an immediate, explicit error at module-import time.

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: [no-evidence] For a testclient module the user explicitly imported, an immediate RuntimeError + install hint is clear when the dependency is missing. lazy/None is for the production runtime.

**Reference**: `starlette/testclient.py:37-44`

**✅ Good**:
```
try:
    import httpx
except ModuleNotFoundError:  # pragma: no cover
    raise RuntimeError(
        "The starlette.testclient module requires the httpx package to be installed.\n"
        "You can install this with:\n"
        "    $ pip install httpx\n"
    )
```

**❌ Bad**:
```
import httpx  # cryptic ImportError traceback

# or
try:
    import httpx
except ModuleNotFoundError:
    httpx = None

class TestClient:
    def __init__(self):
        assert httpx is not None  # AssertionError with no install hint
```

### If an endpoint auto-dispatches sync/async, the test also keeps both forms as fixtures and verifies the same response. Testing only one form misses transparent-dispatch regressions.

**Priority**: `SHOULD` | **Confidence**: `medium` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: [no-evidence] If the framework's transparent dispatch breaks, testing only one side won't catch it. Fixture parametrization forces both.

**Reference**: `tests/test_applications.py:40-50`

**✅ Good**:
```
def func_homepage(request: Request) -> PlainTextResponse:
    return PlainTextResponse("Hello, world!")


async def async_homepage(request: Request) -> PlainTextResponse:
    return PlainTextResponse("Hello, world!")


class Homepage(HTTPEndpoint):
    def get(self, request: Request) -> PlainTextResponse:
        return PlainTextResponse("Hello, world!")


@pytest.fixture(params=[func_homepage, async_homepage, Homepage])
def homepage_endpoint(request):
    return request.param
```

**❌ Bad**:
```
async def homepage(request):  # async only — misses sync dispatch regressions
    return PlainTextResponse("Hello")

def test_homepage(test_client_factory):
    client = test_client_factory(Starlette(routes=[Route('/', homepage)]))
    assert client.get('/').text == 'Hello'
```
