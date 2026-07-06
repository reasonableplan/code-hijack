# Backend Layer Rules

> Backend files (.py, backend/) → this file + shared.md

**Total rules**: 16

## Architecture

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

## Coding Style

### Document every public parameter inline with typing.Annotated + annotated_doc.Doc, not with a docstring Args section.

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `backend`

**Why**: Annotated+Doc keeps metadata next to the type where IDEs/OpenAPI can read it; docstring Args blocks rot silently when signatures change.

**Reference**: `fastapi/exceptions.py:45-82`, `fastapi/security/http.py:140-195`

**✅ Good**:
```
def __init__(
    self,
    status_code: Annotated[
        int,
        Doc(
            """
            HTTP status code to send to the client.
            """
        ),
    ],
    detail: Annotated[Any, Doc("""...""")] = None,
) -> None:
```

**❌ Bad**:
```
def __init__(self, status_code, detail=None, headers=None):
    """
    Args:
        status_code: HTTP status code.
        detail: Data for the detail key.
    """
```

### All public constructor/function parameters past `self` must be keyword-only (use `*,` separator); do not accept positional arguments for configuration options.

**Priority**: `MUST` | **Confidence**: `high` | **Layer**: `backend`

**Why**: Positional configuration couples call sites to parameter order and blocks inserting new options without breakage; keyword-only makes every option self-documenting at the call site.

**Reference**: `fastapi/params.py:29-73`, `fastapi/security/http.py:140-191`, `fastapi/security/api_key.py:87-133`

**✅ Good**:
```
def __init__(
    self,
    default: Any = Undefined,
    *,
    default_factory: Callable[[], Any] | None = _Unset,
    annotation: Any | None = None,
    alias: str | None = None,
):
```

**❌ Bad**:
```
def __init__(self, default=Undefined, default_factory=None,
             annotation=None, alias=None, alias_priority=None):
```

### Use `_Unset` (a distinct sentinel) rather than `None` as a default when None is itself a meaningful value, and filter sentinels out before passing kwargs to super().__init__.

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `backend`

**Why**: Many Pydantic fields distinguish 'user did not pass' from 'user passed None'. A dedicated sentinel + filter makes that distinction explicit and forwards-compatible.

**Reference**: `fastapi/params.py:33-55`, `fastapi/params.py:129-131`

**✅ Good**:
```
default_factory: Callable[[], Any] | None = _Unset,
alias_priority: int | None = _Unset,
...
use_kwargs = {k: v for k, v in kwargs.items() if v is not _Unset}
super().__init__(**use_kwargs)
```

**❌ Bad**:
```
def __init__(self, default_factory=None, alias_priority=None):
    super().__init__(default_factory=default_factory,
                     alias_priority=alias_priority)
```

### Issue deprecation warnings via a custom UserWarning subclass (FastAPIDeprecationWarning) with `stacklevel=4`, and wrap the deprecated parameter in typing_extensions.deprecated so type checkers also flag it.

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `backend`

**Why**: Default DeprecationWarning is silenced for libraries (see comment at exceptions.py:252); UserWarning subclass surfaces in app logs. stacklevel=4 blames the user's call site, not the framework internals.

**Reference**: `fastapi/params.py:48-53`, `fastapi/params.py:74-79`, `fastapi/exceptions.py:252-256`

**✅ Good**:
```
regex: Annotated[
    str | None,
    deprecated(
        "Deprecated in FastAPI 0.100.0 and Pydantic v2, use `pattern` instead."
    ),
] = None,
...
if example is not _Unset:
    warnings.warn(
        "`example` has been deprecated, please use `examples` instead",
        category=FastAPIDeprecationWarning,
        stacklevel=4,
    )
```

**❌ Bad**:
```
def __init__(self, regex=None, example=None):
    if example:
        print('warning: example is deprecated')
```

## Api Design

### Every authentication dependency must accept `auto_error: bool = True` and honor it: raise HTTPException(401) when True, return None when False.

**Priority**: `MUST` | **Confidence**: `high` | **Layer**: `backend`

**Why**: Composable auth (bearer OR cookie OR API key) requires an optional path. Hardcoding raise makes the dependency impossible to use in multi-scheme flows.

**Reference**: `fastapi/security/oauth2.py:423-430`, `fastapi/security/http.py:94-102`, `fastapi/security/api_key.py:47-52`

**✅ Good**:
```
async def __call__(self, request: Request) -> str | None:
    authorization = request.headers.get("Authorization")
    if not authorization:
        if self.auto_error:
            raise self.make_not_authenticated_error()
        else:
            return None
    return authorization
```

**❌ Bad**:
```
async def __call__(self, request: Request) -> str:
    authorization = request.headers.get("Authorization")
    if not authorization:
        raise HTTPException(401, "Not authenticated")
    return authorization
```

### HTTP 401 responses must always attach a WWW-Authenticate header with the correct challenge scheme (Bearer / Basic / APIKey), not just a JSON detail.

**Priority**: `MUST` | **Confidence**: `high` | **Layer**: `backend`

**Why**: RFC 9110 requires WWW-Authenticate on 401; browsers and OAuth clients rely on the challenge to know which scheme to prompt for.

**Reference**: `fastapi/security/oauth2.py:417-421`, `fastapi/security/http.py:84-92`, `fastapi/security/api_key.py:31-45`

**✅ Good**:
```
return HTTPException(
    status_code=HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)
```

**❌ Bad**:
```
raise HTTPException(
    status_code=401,
    detail="Not authenticated",
)
```

### Use `from starlette.status import HTTP_xxx_NAME` named constants rather than magic integers for HTTP status codes.

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `backend`

**Why**: Named constants make grep-for-auth-failures trivial and eliminate the 401/403/404 typo class; review consistency across the codebase.

**Reference**: `fastapi/security/oauth2.py:11`, `fastapi/security/oauth2.py:418`, `fastapi/security/http.py:13`, `fastapi/security/api_key.py:8`

**✅ Good**:
```
from starlette.status import HTTP_401_UNAUTHORIZED
...
return HTTPException(
    status_code=HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)
```

**❌ Bad**:
```
return HTTPException(
    status_code=401,
    detail="Not authenticated",
)
```

### Compose routes with APIRouter (prefix, tags, dependencies, responses set at construction) and mount via app.include_router rather than attaching all routes directly to the FastAPI app.

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `backend`

**Why**: Router-level prefix/tags/dependencies remove per-route duplication and keep cross-cutting concerns (auth, prefix) in one declaration; the alternative DRY-violates and diverges as the module grows.

**Reference**: `docs_src/bigger_applications/app_an_py310/routers/items.py:5-10`, `docs_src/bigger_applications/app_an_py310/main.py:10-18`

**✅ Good**:
```
router = APIRouter(
    prefix="/items",
    tags=["items"],
    dependencies=[Depends(get_token_header)],
    responses={404: {"description": "Not found"}},
)

@router.get("/{item_id}")
async def read_item(item_id: str):
    if item_id not in fake_items_db:
        raise HTTPException(status_code=404, detail="Item not found")
```

**❌ Bad**:
```
@app.get("/items/{item_id}", tags=["items"], dependencies=[Depends(get_token_header)])
async def read_item(item_id: str):
    ...

@app.get("/items/", tags=["items"], dependencies=[Depends(get_token_header)])
async def read_items():
    ...
```

### Inject request-scoped state (settings, db session) via `Annotated[T, Depends(factory)]` with an `@lru_cache` factory for singletons, rather than module-level globals.

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `backend`

**Why**: DI-injected settings are overridable in tests via app.dependency_overrides; module-level globals are not. @lru_cache gives the singleton property without sacrificing testability.

**Reference**: `docs_src/settings/app03_an_py310/main.py:11-17`

**✅ Good**:
```
@lru_cache
def get_settings():
    return config.Settings()

@app.get("/info")
async def info(settings: Annotated[config.Settings, Depends(get_settings)]):
    return {"app_name": settings.app_name}
```

**❌ Bad**:
```
settings = config.Settings()

@app.get("/info")
async def info():
    return {"app_name": settings.app_name}
```

### Raise HTTPException with a specific status code and short human-readable `detail`; do not return a dict with an error key or a 200 response carrying error semantics.

**Priority**: `MUST` | **Confidence**: `high` | **Layer**: `backend`

**Why**: Errors returned as 200 bodies break client retry logic, monitoring, and OpenAPI schema accuracy; HTTPException produces correct status + JSON structure that all FastAPI tooling understands.

**Reference**: `fastapi/exceptions.py:36-42`, `docs_src/bigger_applications/app_an_py310/routers/items.py:22-25`

**✅ Good**:
```
@router.get("/{item_id}")
async def read_item(item_id: str):
    if item_id not in fake_items_db:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"name": fake_items_db[item_id]["name"], "item_id": item_id}
```

**❌ Bad**:
```
@router.get("/{item_id}")
async def read_item(item_id: str):
    if item_id not in fake_items_db:
        return {"error": "Item not found", "ok": False}
    return fake_items_db[item_id]
```
