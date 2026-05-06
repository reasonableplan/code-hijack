# Testing Analysis

## Design Intent

테스트 fixtures 가 production 코드와 같은 정밀도로 관리된다 — `tests/types.py` 같은 단일 fixture-types 모듈에 TestClientFactory 등 테스트-specific 타입을 모으고, TestClient 가 backend/option arg 를 constructor 로 받아 multi-runtime (asyncio + trio) 검증을 1급으로 지원한다. Optional test-only 의존성 (httpx) 은 module-import time 에 명시적 RuntimeError + install hint 로 처리.

## Rules (4)

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

## Anti-Patterns

### 테스트 타입을 모듈마다 재정의

**Why**: fixture signature drift

**Alternative**: tests/types.py 단일 source

### TestClient backend 를 ClassVar 로 고정

**Why**: multi-backend 격리 깨짐

**Alternative**: constructor arg + per-instance

## File-Type Guides

### tests/types.py

테스트 fixture 의 공통 Protocol/TypeAlias 단일 source

### testclient.py

Optional test-only deps 는 module-import time RuntimeError + install hint

## Checklist

- [ ] 새 fixture 의 타입이 tests/types.py 에 있는가?
- [ ] TestClient/runner 의 backend/option 이 constructor arg 인가?
- [ ] Optional test-only 의존성이 명시적 RuntimeError 로 가이드되는가?
- [ ] sync/async transparent dispatch 두 형태 모두 fixture 로 검증하는가?
