# Architecture Analysis

## Design Intent

starlette 는 ASGI middleware stack 을 framework-internal 로 잠그고 (error/exception handler 위치 강제) 사용자 미들웨어를 그 사이에 끼우는 sandwich 모델을 채택한다. 모든 sync/async 차이는 anyio + run_in_threadpool 한 곳에서 추상화되고, 모든 cross-cutting 정책 (CORS, body caching) 은 middleware 한 클래스로 좁게 분리된다.

## Rules (4)

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

## Anti-Patterns

### 사용자 middleware 가 error/exception handler 와 같은 layer 에 등록

**Why**: 잘못된 사용자 middleware 가 fault 격리를 깰 수 있음

**Alternative**: framework 가 outermost/innermost 위치를 잠그고 사용자 middleware 는 그 사이에만

### endpoint 마다 sync/async 분기 코드

**Why**: async runtime 에 결합도 폭발

**Alternative**: framework 의 단일 추상화 (anyio/run_in_threadpool) 한 곳에서만

### wildcard `*` Allow-Origin 과 credentials 동시 사용

**Why**: 브라우저 CORS spec 위반

**Alternative**: credentials 일 때 explicit origin echo

## File-Type Guides

### middleware

단일 클래스가 cross-cutting 정책 1개를 책임. __call__(scope, receive, send) 시그니처 + 정책별 분기.

### applications

build_middleware_stack 으로 stack 조립. 사용자 등록은 user_middleware 리스트에만.

## Checklist

- [ ] 새 middleware 가 error/exception handler 위치를 우회하지 않는가?
- [ ] endpoint 등록 시 sync/async 분기를 endpoint 코드 안에 두지 않았는가?
- [ ] cross-cutting 정책이 단일 middleware 클래스로 격리됐는가?
- [ ] Middleware 가 body 를 소비할 때 cache/stream 분기 가드가 있는가?
