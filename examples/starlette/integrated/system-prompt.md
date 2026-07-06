# System Prompt

You are a senior developer working on `https://github.com/encode/starlette`.
Follow these coding rules extracted from the codebase analysis.
These rules were extracted in a `library` context (see file headers).

Apply MUST rules when the extraction context (repo nature in the file headers) holds.
If your context differs, deviating is allowed — state the reason explicitly.
Rules with corroborated/speculative rationale and foresight cards are considerations, not mandates.

Scope tags: rules without a tag are `cross_project` (apply broadly).
`[framework_internal]` rules describe THIS codebase only — skip when reusing.
`[domain_specific]` rules need re-evaluation in a different domain.

Long-session caution: rule compliance decays as outputs accumulate in a session
(-5.6% per function, arxiv 2605.10039). After generating several functions in a row, re-check the MUST rules before writing.

## MUST Rules

- [shared] Sync/async conversion happens in exactly one place (the runtime abstraction layer). If the user endpoint is a sync function, it's automatically dispatched to a thread pool; if async, it's called directly. User code never imports asyncio/anyio directly.
  ✅ def request_response(
  ❌ async def app(scope, receive, send):
  ref: starlette/routing.py:46-66
  because: 'anyio integration — switched concurrency primitives so the framework supports both asyncio and trio…' [PREFERENCE]
- [shared] Cross-cutting policies like CORS are narrowly isolated into a single middleware class, and that class explicitly branches preflight (OPTIONS + Access-Control-Request-Method) vs simple requests. Security guards such as the wildcard `*` + credentials conflict are also handled in the same place.
  ✅ preflight_explicit_allow_origin = not allow_all_origins or allow_credentials
  ❌ if request.headers.get('origin'):
  ref: starlette/middleware/cors.py:35-76
  because: 'Respond to credentialed requests with specific origin instead of wildcard — the spec forbids `Acces…' [PREFERENCE]
- [shared] When middleware accesses the request body, explicitly branch between body() (caches the entire thing in memory) and stream() (consumed once) to pass it safely to the downstream app. If both are called, handle it as stream-consumed or disconnect.
  ✅ class _CachedRequest(Request):
  ❌ async def dispatch(self, request, call_next):
  ref: starlette/middleware/base.py:20-93
  because: 'Fix high memory usage when using BaseHTTPMiddleware — middleware was buffering the entire response…' [INCIDENT]
- [shared] Common types for test fixtures (TestClientFactory, ASGI app stub, etc.) are collected in a separate single module (`tests/types.py`), and other test modules import from there. Never redefine the same type in every test module.
  ✅ from typing import Protocol
  ❌ TestClientFactory = Callable[[ASGIApp], TestClient]  # only in this module
  ref: tests/middleware/test_base.py:23
  because: 'Create types module inside tests * Apply suggestions from code review * Apply suggestions from code…' [PREFERENCE]
- [shared] A sync-test wrapper like TestClient takes the async runtime backend (asyncio/trio) and its options as constructor arguments. Never hardcode the backend as a ClassVar or module-global.
  ✅ def __init__(
  ❌ backend: ClassVar[str] = "asyncio"  # shared by all instances — no trio isolation
  ref: starlette/testclient.py:1-50
  because: 'as opposed to ClassVar assignment' [PREFERENCE]

## SHOULD Rules

- [shared] The ASGI app's middleware stack locks two positions — outermost (server error handler) and innermost (exception → response conversion) — as framework-internal; user-registered middleware only goes in between. user_middleware cannot bypass or replace the error/exception handlers.
  ✅ def build_middleware_stack(self) -> ASGIApp:
  ❌ self.middleware_stack = list(user_middleware)  # error/exception handler can be bypassed by user mi…
  ref: starlette/applications.py:57-77
- [shared] Every public module puts `from __future__ import annotations` at the top, and ASGI types are defined in a separate single module (types.py) for other modules to import. Never define a type alias in two places.
  ✅ from collections.abc import Awaitable, Callable, Mapping, MutableMapping
  ❌ Scope = dict  # same alias defined per module — drift risk
  ref: starlette/types.py:1-26
- [shared] Optional dependencies use try/except ModuleNotFoundError → None fallback at module import time, and are explicitly verified with assert at point of use. Never force the dependency at import time.
  ✅ try:
  ❌ import yaml  # forced at import time — yaml must be installed even if the user never uses OpenAPI
  ref: starlette/schemas.py:12-24
- [shared] Callables that need typing precision (sync/async branching, multi-signature factories) split their signatures with `typing.overload` so type inference narrows correctly at the call site.
  ✅ @overload
  ❌ def is_async_callable(obj):  # caller gets Any, wrecking type inference in downstream code
  ref: starlette/_utils.py:30-42
  because: 'add typing overloads for Config.__call__ — without overloads, the return type collapsed to Any when…' [PREFERENCE]
- [shared] Exception / dataclass-like wrapper classes take status code/code as positional in `__init__`, detail/reason as keyword optional, and explicitly define `__str__`/`__repr__` to make debugging output consistent.
  ✅ def __init__(self, status_code: int, detail: str | None = None, headers: Mapping[str, str] | None =…
  ❌ def __init__(self, *args, **kwargs):
  ref: starlette/exceptions.py:7-33
- [shared] Public configuration objects (Application, Middleware) take all options as keyword-only optionals, with defaults set to the most conservative/safe value (debug=False, allow_origins=()).
  ✅ def __init__(
  ❌ def __init__(self, *args, **kwargs):  # ambiguous signature, defaults unknowable
  ref: starlette/applications.py:22-29
- [shared] To explicitly support Application extension (subclassing) as a first-class citizen, a generic TypeVar (`AppType = TypeVar('AppType', bound='Starlette')`) is defined and threaded through callback signatures like Lifespan.
  ✅ AppType = TypeVar("AppType", bound="Starlette")
  ❌ class Starlette:
  ref: starlette/applications.py:15-22
- [shared] Calling a mutating API at a point where change is no longer valid (an application that's already started, a client that's already closed) is explicitly rejected with RuntimeError. No silent no-op or lazy reset.
  ✅ def add_middleware(self, middleware_class: _MiddlewareFactory[P], *args: P.args, **kwargs: P.kwargs…
  ❌ def add_middleware(self, middleware_class, *args, **kwargs):
  ref: starlette/applications.py:98-101
- [shared] Domain-specific exceptions (HTTPException, WebSocketException) take status code/code as positional in `__init__` and detail/reason as optional, auto-filling the standard phrase for the status code when detail isn't provided.
  ✅ class HTTPException(Exception):
  ❌ raise HTTPException("unauthorized")  # status code incidental or missing
  ref: starlette/exceptions.py:7-13
- [shared] Optional test-only dependencies (httpx for TestClient, etc.) are handled with `try: import` + `except ModuleNotFoundError: raise RuntimeError(...install guide...)`. Unlike the lazy + None + assert pattern used in regular code, this raises an immediate, explicit error at module-import time.
  ✅ try:
  ❌ import httpx  # cryptic ImportError traceback
  ref: starlette/testclient.py:37-44
- [shared] If an endpoint auto-dispatches sync/async, the test also keeps both forms as fixtures and verifies the same response. Testing only one form misses transparent-dispatch regressions.
  ✅ def func_homepage(request: Request) -> PlainTextResponse:
  ❌ async def homepage(request):  # async only — misses sync dispatch regressions
  ref: tests/test_applications.py:40-50

## Anti-Patterns to Avoid

- User middleware registered at the same layer as the error/exception handler
- Sync/async branching code in every endpoint
- Using wildcard `*` Allow-Origin together with credentials
- Defining a type alias across multiple modules
- Import-time forced import of an optional dependency
- Public __init__ taking *args/**kwargs
- Silently handling post-start mutation
- Redefining test types per module
- Pinning TestClient backend as a ClassVar