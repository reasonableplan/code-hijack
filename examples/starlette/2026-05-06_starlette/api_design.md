# Api Design Analysis

## Design Intent

Public API 는 keyword-only optional + 명시적 default 로 시그니처를 안정화하고, 내부 framework 결정 (middleware 위치, runtime 추상화) 은 사용자에게 노출하지 않는다. 확장 hook 은 generic TypeVar (`AppType`) 으로 subclassing 을 1급으로 지원하고, 변경할 수 없는 시점 (middleware 등록 후 start) 은 RuntimeError 로 명시적으로 거절한다.

## Rules (4)

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

## Anti-Patterns

### Public __init__ 가 *args/**kwargs

**Why**: type checker 회피, default 모호

**Alternative**: 명시적 keyword-only optional + 보수적 default

### post-start mutation silent 처리

**Why**: first vs second request stack 일관성 깨짐

**Alternative**: RuntimeError 로 거절

## File-Type Guides

### applications.py

최상위 Application 클래스. Public init 옵션은 보수적 default + AppType generic.

### exceptions.py

Domain exception 계층. status code positional + detail optional + auto-phrase.

## Checklist

- [ ] 새 public API 가 명시적 default 가진 keyword-only optional 인가?
- [ ] Subclass 친화적 generic TypeVar 가 콜백 시그니처에 흐르는가?
- [ ] post-start mutation 은 RuntimeError 로 거절되는가?
- [ ] Domain exception 이 status code positional + auto-phrase 패턴인가?
