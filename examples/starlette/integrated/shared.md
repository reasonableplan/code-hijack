# Shared Layer Rules

> 공통 규칙 (레이어 무관) → 모든 작업에 적용

**Total rules**: 16

## Architecture

### ASGI app 의 middleware stack 은 outermost(서버 오류 핸들러)와 innermost(예외 → 응답 변환) 의 두 위치를 framework-internal 로 잠그고, 사용자 등록 middleware 는 그 사이에만 들어간다. user_middleware 가 error/exception 핸들러를 우회/대체 불가.

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: [no-evidence] 사용자 middleware 가 잘못 짜이면 5xx 응답이 새거나 trace 가 노출. error/exception 위치가 강제돼야 framework 가 fault 격리를 책임진다.

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
self.middleware_stack = list(user_middleware)  # error/exception handler 가 사용자 middleware 에 의해 우회될 수 있음
for cls in self.middleware_stack:
    app = cls(app)
```

### Sync/async 전환은 한 곳 (런타임 추상화 계층) 에서만 일어난다. 사용자 endpoint 가 sync 함수면 자동으로 thread pool 로 dispatch 하고, async 함수면 그대로 호출. 사용자 코드에서 asyncio/anyio 직접 import 하지 않는다.

**Priority**: `MUST` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: Async runtime 추상화 한 곳에 모이지 않으면 endpoint 마다 sync/async 분기 + runtime 라이브러리 직접 import 가 새어 나간다.

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
    if asyncio.iscoroutinefunction(func):  # 사용자 코드가 매번 분기 — async runtime 에 결합
        response = await func(request)
    else:
        response = await asyncio.get_event_loop().run_in_executor(None, func, request)
```

**Evidence**:

1. [PREFERENCE] · COMMIT `42592d6` — anyio integration (#1157)
   > anyio integration — switched concurrency primitives so the framework supports both asyncio and trio backends through a single shim, instead of importing asyncio directly throughout the codebase.

### CORS 같은 cross-cutting 정책은 단일 middleware 클래스로 좁게 격리하고, 그 클래스가 preflight (OPTIONS + Access-Control-Request-Method) vs simple 요청을 명시적으로 분기 처리한다. wildcard `*` + credentials 충돌 같은 보안 가드도 같은 위치에서 처리.

**Priority**: `MUST` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: preflight 와 simple 요청 처리 분리 + wildcard/credentials 충돌 가드가 한 곳에 없으면 endpoint 별 보안 구멍이 생긴다.

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
    response.headers['Access-Control-Allow-Credentials'] = 'true'  # wildcard + credentials 충돌 — 브라우저가 거부
```

**Evidence**:

1. [PREFERENCE] · COMMIT `7a0f89a` — Respond to credentialed requests with specific origin (#1402)
   > Respond to credentialed requests with specific origin instead of wildcard — the spec forbids `Access-Control-Allow-Origin: *` together with `Access-Control-Allow-Credentials: true`, browsers will reject the response.

### Middleware 가 request body 에 접근할 때, body() (전체 메모리 캐시) 와 stream() (한 번 소비) 를 명시적으로 분기 처리해 downstream app 으로 안전히 전달. 둘을 모두 호출하면 stream consumed 또는 disconnect 처리.

**Priority**: `MUST` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: Body access 의 cache/stream 분기 가드 없으면 큰 request 업로드 시 메모리 폭발 또는 downstream hang.

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
    body = await request.body()  # 전체 메모리에 caching, 큰 upload 면 메모리 폭발
    ...
    return await call_next(request)  # downstream 는 body 가 이미 소비된 상태
```

**Evidence**:

1. [INCIDENT] · COMMIT `3d77a1c` — Fix high memory usage when using BaseHTTPMiddleware (#1745)
   > Fix high memory usage when using BaseHTTPMiddleware — middleware was buffering the entire response body before sending it on, which caused unbounded memory growth on large streamed responses. Stream the body through to avoid the buffer accumulation.

## Coding Style

### 모든 공개 모듈은 `from __future__ import annotations` 를 모듈 상단에 두고, ASGI 타입은 별도 단일 모듈 (types.py) 에서 정의해 다른 모듈에서 import 한다. type alias 를 두 곳에 정의하지 않는다.

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: [no-evidence] 같은 type alias 가 두 모듈에 정의되면 import path 따라 동작이 갈리고, 새 ASGI 스펙 변경 시 한 곳만 갱신되는 silent drift 발생.

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
Scope = dict  # 같은 alias 를 모듈마다 정의 — drift 위험
Receive = Callable[[], Awaitable[dict]]

# starlette/middleware/base.py
Scope = MutableMapping[str, Any]  # 다른 정의 — 사용자 코드가 어느 import 에 결합됐냐에 따라 깨짐
```

### Optional dependency 는 모듈 import 시점에 try/except ModuleNotFoundError → None fallback, 사용 시점에 assert 로 명시적으로 검증. import-time 에 의존성 강제하지 않는다.

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: [no-evidence] Import-time 강제 의존성은 사용자가 안 쓰는 기능 때문에 패키지 설치 비용 부담. lazy + assert 가 비용을 사용자 의도와 일치시킴.

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
import yaml  # import-time 에 강제 — 사용자가 OpenAPI 안 써도 yaml 설치 필요

class OpenAPIResponse(Response):
    def render(self, content):
        return yaml.dump(content).encode()
```

### Typing 정밀도가 필요한 callable (sync/async 분기, multi-signature factory) 은 `typing.overload` 로 시그니처를 분리해 호출 시 타입 추론이 정확하게 narrow 되도록 한다.

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: Static analyzer 가 sync/async 분기 후 narrow 된 타입 알아야 await 누락 같은 버그 잡음 — overload 가 그 hint.

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
def is_async_callable(obj):  # 호출자가 Any 받아 후속 코드의 타입 추론 망가짐
    return iscoroutinefunction(obj) or ...
```

**Evidence**:

1. [PREFERENCE] · COMMIT `48dea4d` — add typing overloads for Config.__call__ (#1097)
   > add typing overloads for Config.__call__ — without overloads, the return type collapsed to Any when callers passed a default, defeating type checking on the consumer side. Overloads narrow the return type per-signature.

### 예외/dataclass-like wrapper 클래스는 `__init__` 에서 status code/code 를 positional, detail/reason 을 keyword optional 로 받고, `__str__`/`__repr__` 를 명시적으로 정의해 디버깅 출력을 일관되게 만든다.

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: [no-evidence] Exception 의 __str__/__repr__ 명시 없으면 로그 출력이 "HTTPException(...)" 같은 default repr 로 깨짐. 명시적 정의가 디버깅 표면을 일관되게.

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
        super().__init__(*args, **kwargs)  # status_code/detail 접근 못 함, 에러 메시지 일관성 없음
```

## Api Design

### Public configuration 객체 (Application, Middleware) 는 모든 옵션을 keyword-only optional 로 받고, default 는 가장 보수적/안전한 값으로 설정 (debug=False, allow_origins=()).

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: [no-evidence] Public 옵션이 명시적 default 가지지 않으면 사용자 코드가 default 변경 시 silent breakage. 또 *args/**kwargs 시그니처는 type checker 가 안 잡음.

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
    def __init__(self, *args, **kwargs):  # 시그니처 모호, default 알 수 없음
        self.debug = kwargs.get('debug', True)  # 위험한 default
```

### Application 확장 (subclassing) 을 명시적으로 1급 지원하기 위해 generic TypeVar (`AppType = TypeVar('AppType', bound='Starlette')`) 를 두고, 그 generic 을 Lifespan 같은 callback 시그니처에 흘려보낸다.

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: [no-evidence] Generic TypeVar 없이 subclass 하면 subclass 의 추가 메서드/속성을 lifespan 콜백에서 type-safe 하게 못 씀. AppType 으로 subclass-friendly.

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
    def __init__(self, lifespan=None):  # subclass 의 lifespan 콜백이 Starlette 자체만 받음 — 추가 메서드 접근 못 함
        ...
```

### 변경할 수 없는 시점 (이미 시작된 application, 이미 닫힌 client) 의 mutating API 호출은 RuntimeError 로 명시적으로 거절한다. silent no-op 또는 lazy reset 금지.

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: [no-evidence] post-start mutation 을 silent 으로 받으면 첫 요청과 두 번째 요청이 다른 stack 으로 처리됨. RuntimeError 가 사용자에게 의도를 명확히.

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
    self.middleware_stack = None  # silent reset — 이미 받은 요청들은 어느 stack 으로 처리됐는지 모호
```

### Domain-specific exception (HTTPException, WebSocketException) 은 `__init__` 에서 status code/code 를 positional, detail/reason 을 optional 로 받고, detail 미제공 시 status code 의 standard phrase 를 자동 채운다.

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: [no-evidence] Status code 우선 + standard phrase auto-fill 이 사용자 boilerplate 줄이고 응답 일관성 보장.

**Reference**: `starlette/exceptions.py:7-13`

**✅ Good**:
```
class HTTPException(Exception):
    def __init__(self, status_code: int, detail: str | None = None, headers: Mapping[str, str] | None = None) -> None:
        if detail is None:
            detail = http.HTTPStatus(status_code).phrase  # 401 → 'Unauthorized' 자동
        self.status_code = status_code
        self.detail = detail
        self.headers = headers
```

**❌ Bad**:
```
raise HTTPException("unauthorized")  # status code 가 부수적이거나 누락
# 또는
raise HTTPException(401)  # detail 항상 사용자가 채워야 — boilerplate
```

## Testing

### 테스트 fixtures 의 공통 타입 (TestClientFactory, ASGI app stub 등) 은 별도 단일 모듈 (`tests/types.py`) 에 모으고, 다른 테스트 모듈은 거기서 import 한다. 테스트 모듈마다 같은 타입을 재정의하지 않는다.

**Priority**: `MUST` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: 테스트 타입을 모듈마다 재정의하면 fixture signature 가 silent drift — 한 군데 통과해도 다른 곳 type 불일치.

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
TestClientFactory = Callable[[ASGIApp], TestClient]  # 이 모듈에만

# tests/test_routing.py
TestClientFactory = Callable[[ASGIApp], TestClient]  # 또 정의 — drift
```

**Evidence**:

1. [PREFERENCE] · COMMIT `78fcd54` — Create types module inside tests (#2502)
   > Create types module inside tests * Apply suggestions from code review * Apply suggestions from code review * Fix check errors * Change testclientfactory due to autotest * No cover fix * Apply suggestions from code review * Skip code coverage for TestClientFactory protocol

### TestClient 같은 sync-test wrapper 는 async runtime backend (asyncio/trio) 와 그 옵션을 constructor 인자로 받는다. ClassVar 또는 module-global 로 backend 를 박지 않는다.

**Priority**: `MUST` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: ClassVar backend 는 trio + asyncio 동시 테스트 격리 깨짐 + 사용자가 backend 별 동작 못 검증.

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
    backend: ClassVar[str] = "asyncio"  # 모든 인스턴스 공유 — trio 격리 불가

    def __init__(self, app):
        super().__init__()
```

**Evidence**:

1. [PREFERENCE] · COMMIT `d222b87` — TestClient accepts backend and backend_options as arguments to constructor (#1211)
   > as opposed to ClassVar assignment

### Optional test-only 의존성 (httpx for TestClient 등) 은 `try: import` + `except ModuleNotFoundError: raise RuntimeError(...설치 가이드...)` 로 처리. 일반 코드의 lazy + None + assert 패턴과 달리 module-import time 에 즉시 명시적 에러.

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: [no-evidence] 사용자가 명시적으로 import 한 testclient 모듈은 의존성 없으면 즉시 RuntimeError + install hint 가 명확. lazy/None 은 production runtime 용.

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

# 또는
try:
    import httpx
except ModuleNotFoundError:
    httpx = None

class TestClient:
    def __init__(self):
        assert httpx is not None  # install hint 없는 AssertionError
```

### Endpoint 가 sync/async 자동 dispatch 라면, 테스트도 두 형태 모두 fixture 로 두고 같은 응답을 검증한다. 한쪽만 테스트하면 transparent dispatch regression 못 잡음.

**Priority**: `SHOULD` | **Confidence**: `medium` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: [no-evidence] Framework 의 transparent dispatch 가 broken 되면 한쪽만 테스트로는 못 잡음. fixture parametrize 로 둘 다 강제.

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
async def homepage(request):  # async only — sync dispatch regression 못 잡음
    return PlainTextResponse("Hello")

def test_homepage(test_client_factory):
    client = test_client_factory(Starlette(routes=[Route('/', homepage)]))
    assert client.get('/').text == 'Hello'
```
