# Api Design Analysis

## Design Intent

Public contracts are expressed as declarative dependencies (Depends/Security) with auto_error opt-out for composable auth, status codes via named constants, and routes grouped into APIRouter with prefix/tags/dependencies set at construction. Errors flow as HTTPException with status_code+detail (and correct WWW-Authenticate for 401s), never as 200 dicts with error keys. State is injected, not imported.

## Rules (6)

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

## Anti-Patterns

### Returning errors in 200 response bodies

**Why**: Breaks HTTP semantics for retry, monitoring, and OpenAPI

**Alternative**: raise HTTPException(status_code=..., detail=...)

### 401 response without WWW-Authenticate header

**Why**: Violates RFC 9110 and breaks browser/OAuth client auto-retry

**Alternative**: Always add headers={'WWW-Authenticate': scheme} on 401

### Module-level globals for settings/db/clients

**Why**: Not overridable in tests via app.dependency_overrides

**Alternative**: @lru_cache factory + Annotated[T, Depends(factory)]

## File-Type Guides

### routers

One APIRouter per domain module with prefix/tags/dependencies set in the constructor; mount via app.include_router.

### security

Subclass the appropriate base (OAuth2, HTTPBase, APIKeyBase), expose auto_error, return None in permissive mode.

### errors

HTTPException at the point of failure; WWW-Authenticate header on every 401.

## Checklist

- [ ] All 401 responses carry WWW-Authenticate header with correct scheme.
- [ ] All auth dependencies accept auto_error=True/False.
- [ ] Status codes use starlette.status.HTTP_xxx_NAME constants.
- [ ] Routes are on APIRouter instances when the app exceeds a single module.
- [ ] Settings/DB/clients are injected via Depends, not module globals.
- [ ] Errors raise HTTPException with status_code+detail.
