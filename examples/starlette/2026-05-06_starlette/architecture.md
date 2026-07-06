# Architecture Analysis

## Design Intent

Starlette locks the ASGI middleware stack as framework-internal (forcing the error/exception handler position) and adopts a sandwich model where user middleware is inserted in between. All sync/async differences are abstracted in one place (anyio + run_in_threadpool), and every cross-cutting policy (CORS, body caching) is narrowly isolated into a single middleware class.

## Rules (4)

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

## Anti-Patterns

### User middleware registered at the same layer as the error/exception handler

**Why**: A broken user middleware can break fault isolation

**Alternative**: Framework locks the outermost/innermost positions; user middleware only goes in between

### Sync/async branching code in every endpoint

**Why**: Coupling to the async runtime explodes

**Alternative**: Only through the framework's single abstraction (anyio/run_in_threadpool)

### Using wildcard `*` Allow-Origin together with credentials

**Why**: Violates the browser CORS spec

**Alternative**: Echo the explicit origin when credentials are used

## File-Type Guides

### middleware

A single class owns one cross-cutting policy. __call__(scope, receive, send) signature + per-policy branching.

### applications

Stack assembled via build_middleware_stack. User registration only goes into the user_middleware list.

## Checklist

- [ ] Does the new middleware avoid bypassing the error/exception handler position?
- [ ] Does endpoint registration avoid putting sync/async branching inside endpoint code?
- [ ] Is the cross-cutting policy isolated into a single middleware class?
- [ ] Is there a cache/stream branch guard when middleware consumes the body?
