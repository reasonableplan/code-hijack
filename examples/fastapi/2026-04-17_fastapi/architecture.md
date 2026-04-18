# Architecture Analysis

## Design Intent

FastAPI is architecturally a typed, declarative layer atop Starlette (HTTP/ASGI) and Pydantic (validation). Public surface is composed of small class hierarchies (FastAPI<-Starlette, HTTPException<-StarletteHTTPException, Param<-FieldInfo) that subclass rather than wrap, and dependency injection is materialized into immutable Dependant dataclasses with cached-property derivations so per-request cost is minimal.

## Rules (6)

### Subclass Starlette/Pydantic primitives instead of wrapping them; expose FastAPI as a thin typed layer on top of lower-level ASGI framework.

**Priority**: `MUST` | **Confidence**: `high` | **Layer**: `backend`

**Why**: Inheritance keeps Starlette's isinstance checks, middleware chain, and ASGI interface intact; a wrapper would desync the surface as Starlette evolves.

**Reference**: `fastapi/applications.py:41-55`, `fastapi/exceptions.py:17-43`

**✅ Good**:
```
class FastAPI(Starlette):
    """
    `FastAPI` app class, the main entrypoint to use FastAPI.
    """
    def __init__(
        self: AppType,
        *,
        debug: Annotated[bool, Doc(...)] = False,
```

**❌ Bad**:
```
class FastAPI:
    def __init__(self, debug=False):
        self._app = Starlette(debug=debug)
    def __getattr__(self, name):
        return getattr(self._app, name)
```

### Keep exception type hierarchy distinct by audience: HTTPException for client errors, FastAPIError (RuntimeError) for developer/framework misuse, plus separate WebSocket and Validation branches.

**Priority**: `MUST` | **Confidence**: `high` | **Layer**: `backend`

**Why**: Conflating client-facing HTTP errors with programmer errors prevents middleware from distinguishing 'return 400' vs 'crash the worker'; FastAPIError as RuntimeError signals it should surface in logs, not responses.

**Reference**: `fastapi/exceptions.py:17-19`, `fastapi/exceptions.py:161-172`, `fastapi/exceptions.py:174-189`

**✅ Good**:
```
class FastAPIError(RuntimeError):
    """
    A generic, FastAPI-specific error.
    """

class DependencyScopeError(FastAPIError):
    """
    A dependency declared that it depends on another dependency with an invalid
    (narrower) scope.
    """
```

**❌ Bad**:
```
class FastAPIError(Exception):
    pass

class HTTPException(FastAPIError):
    def __init__(self, status_code, detail):
        self.status_code = status_code
        self.detail = detail
```

### Build public security/auth as class instances (__call__ makes them dependencies) that inherit a common SecurityBase marker, not as ad-hoc functions.

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `backend`

**Why**: SecurityBase subclass detection (dependencies/models.py _is_security_scheme) powers automatic OpenAPI scheme generation and scope merging; plain functions are invisible to that machinery.

**Reference**: `fastapi/security/http.py:69-102`, `fastapi/security/oauth2.py:330-430`

**✅ Good**:
```
class HTTPBase(SecurityBase):
    model: HTTPBaseModel

    def __init__(self, *, scheme: str, scheme_name: str | None = None,
                 description: str | None = None, auto_error: bool = True):
        self.model = HTTPBaseModel(scheme=scheme, description=description)
        self.scheme_name = scheme_name or self.__class__.__name__
        self.auto_error = auto_error

    async def __call__(self, request: Request) -> HTTPAuthorizationCredentials | None:
        ...
```

**❌ Bad**:
```
def http_basic(request: Request):
    authorization = request.headers.get('Authorization')
    if not authorization:
        raise HTTPException(status_code=401)
    return authorization
```

### Model dependency graph results as a frozen dataclass (Dependant) with @cached_property for derived booleans (is_coroutine_callable, is_gen_callable, oauth_scopes); do not recompute on each request.

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `backend`

**Why**: Dependency resolution runs on every request; recomputing inspect.iscoroutinefunction each time is expensive. cached_property + dataclass gives cheap equality/cache keys for use_cache.

**Reference**: `fastapi/dependencies/models.py:31-72`, `fastapi/dependencies/models.py:157-185`

**✅ Good**:
```
@dataclass
class Dependant:
    path_params: list[ModelField] = field(default_factory=list)
    query_params: list[ModelField] = field(default_factory=list)
    call: Callable[..., Any] | None = None
    use_cache: bool = True

    @cached_property
    def is_coroutine_callable(self) -> bool:
        if self.call is None:
            return False
```

**❌ Bad**:
```
def solve_dependencies(request, dependant):
    for sub in dependant['dependencies']:
        if inspect.iscoroutinefunction(sub['call']):
            result = await sub['call'](request)
        else:
            result = sub['call'](request)
```

### Register serializer implementations via a module-level dict[type, Callable] (ENCODERS_BY_TYPE) plus a precomputed inverted tuple lookup, not a chain of isinstance branches.

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `backend`

**Why**: Dict lookup on type(obj) is O(1) and extendable without editing control flow; the tuple form preserves subclass matching for types that actually need isinstance.

**Reference**: `fastapi/encoders.py:68-109`, `fastapi/encoders.py:317-321`

**✅ Good**:
```
ENCODERS_BY_TYPE: dict[type[Any], Callable[[Any], Any]] = {
    bytes: lambda o: o.decode(),
    datetime.datetime: isoformat,
    Decimal: decimal_encoder,
    UUID: str,
}
encoders_by_class_tuples = generate_encoders_by_class_tuples(ENCODERS_BY_TYPE)
# later:
if type(obj) in ENCODERS_BY_TYPE:
    return ENCODERS_BY_TYPE[type(obj)](obj)
```

**❌ Bad**:
```
def encode(obj):
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return decimal_encoder(obj)
    if isinstance(obj, UUID):
        return str(obj)
```

### Flatten nested dependency trees into a single Dependant via get_flat_dependant rather than recursing at request time; compute scopes and params during app startup.

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `backend`

**Why**: OpenAPI schema + validation needs the flattened view once; request path needs structured view. Flattening eagerly means the request path stays structured and the docs path stays fast.

**Reference**: `fastapi/dependencies/utils.py:138-189`

**✅ Good**:
```
def get_flat_dependant(dependant, *, skip_repeats=False, visited=None, parent_oauth_scopes=None):
    flat_dependant = Dependant(
        path_params=dependant.path_params.copy(),
        query_params=dependant.query_params.copy(),
        ...
    )
    for sub_dependant in dependant.dependencies:
        flat_sub = get_flat_dependant(sub_dependant, ...)
        flat_dependant.path_params.extend(flat_sub.path_params)
```

**❌ Bad**:
```
def collect_params(dependant, out):
    out.extend(dependant.path_params)
    for sub in dependant.dependencies:
        collect_params(sub, out)
# called from every request
```

## Anti-Patterns

### Wrapping Starlette/Pydantic instead of subclassing

**Why**: Desyncs the surface when the underlying library evolves; breaks isinstance checks in middleware chain

**Alternative**: Subclass and override only what FastAPI enriches (declarative types, OpenAPI metadata)

### Resolving the full dependency tree recursively on every request

**Why**: inspect.iscoroutinefunction and scope merging are expensive and invariant per route

**Alternative**: Freeze derivations into @cached_property on a Dependant dataclass, flatten once with get_flat_dependant

### isinstance-chain serializers scattered across the codebase

**Why**: Adding a new type means editing control flow and retesting unrelated branches

**Alternative**: Centralize in ENCODERS_BY_TYPE dict with a precomputed inverted tuple map

## File-Type Guides

### exceptions

Keep audience-distinct hierarchies: client-visible errors (HTTPException) inherit from Starlette; framework-misuse errors (FastAPIError) inherit from RuntimeError.

### security

Implementations subclass SecurityBase and expose behavior via async __call__ so dependency resolver can pick them up automatically.

### dependencies

Model dependency graph as a frozen dataclass; put all derived booleans behind @cached_property to amortize inspect cost.

## Checklist

- [ ] If adding a new first-class primitive, is it a subclass of the Starlette/Pydantic equivalent (not a wrapper)?
- [ ] Does the new error inherit from the correct parent (HTTPException for client, FastAPIError for framework)?
- [ ] Is per-request work cached via @cached_property or precomputed at app startup?
- [ ] Are new serializer mappings registered in ENCODERS_BY_TYPE, not in new isinstance branches?
