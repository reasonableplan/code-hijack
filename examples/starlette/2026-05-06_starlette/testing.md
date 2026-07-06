# Testing Analysis

## Design Intent

Test fixtures are managed with the same rigor as production code — test-specific types like TestClientFactory are collected in a single fixture-types module (`tests/types.py`), and TestClient takes backend/option args in its constructor to support multi-runtime (asyncio + trio) verification as a first-class citizen. Optional test-only dependencies (httpx) are handled with an explicit RuntimeError + install hint at module-import time.

## Rules (4)

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

## Anti-Patterns

### Redefining test types per module

**Why**: fixture signature drift

**Alternative**: Single source in tests/types.py

### Pinning TestClient backend as a ClassVar

**Why**: Breaks multi-backend isolation

**Alternative**: constructor arg + per-instance

## File-Type Guides

### tests/types.py

Single source for common Protocol/TypeAlias used by test fixtures

### testclient.py

Optional test-only deps raise RuntimeError + install hint at module-import time

## Checklist

- [ ] Is the new fixture's type in tests/types.py?
- [ ] Is the TestClient/runner's backend/option a constructor arg?
- [ ] Is the optional test-only dependency guided by an explicit RuntimeError?
- [ ] Are both forms of sync/async transparent dispatch verified via fixtures?
