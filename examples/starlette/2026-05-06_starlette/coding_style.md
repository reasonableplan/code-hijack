# Coding Style Analysis

## Design Intent

모든 모듈이 `from __future__ import annotations` + 모듈 상단 import 정렬을 따른다. ASGI 타입은 단일 모듈 (types.py) 에서 정의하고 다른 모듈은 거기서 import. Optional 의존성은 try/import + None fallback + 사용 시 assert 패턴. Typing 정밀도가 필요한 곳 (async 감지, Config callable 등) 은 `@overload` 로 표현.

## Rules (4)

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

## Anti-Patterns

### type alias 를 여러 모듈에 정의

**Why**: import path 따른 silent drift

**Alternative**: 단일 types.py 모듈

### Optional dependency 의 import-time 강제 import

**Why**: 사용자가 안 쓰는 기능에 강제 의존

**Alternative**: try/import + None + 사용 시 assert

## File-Type Guides

### types.py

ASGI/도메인 타입 alias 단일 source. 다른 모듈은 import 만.

### module 상단

from __future__ import annotations + import 정렬 (stdlib → third-party → local)

## Checklist

- [ ] 모든 새 모듈에 `from __future__ import annotations` 가 있는가?
- [ ] 새 type alias 가 types.py (또는 동치) 에 정의됐는가?
- [ ] Optional dependency 가 import-time 에 강제되지 않는가?
- [ ] Sync/async 분기 callable 에 @overload 가 적절한가?
