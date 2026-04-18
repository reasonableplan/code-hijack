# Coding Style Analysis

## Design Intent

The codebase treats the function signature as the primary documentation artifact. Types are PEP 604 unions, parameters are keyword-only, docs live in typing.Annotated via annotated_doc.Doc, deprecations are typing_extensions.deprecated + custom FastAPIDeprecationWarning. The signature should tell the entire story without a reader opening the docstring.

## Rules (5)

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

### Use Python 3.10+ PEP 604 union syntax (`X | None`) consistently, not `Optional[X]` or `Union[X, None]`.

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `shared`

**Why**: One syntax across the codebase keeps diffs small and keeps imports clean; FastAPI explicitly targets modern Python, so the legacy form is dead weight.

**Reference**: `fastapi/params.py:33-37`, `fastapi/exceptions.py:70-82`, `fastapi/dependencies/models.py:39-51`

**✅ Good**:
```
default_factory: Callable[[], Any] | None = _Unset,
alias: str | None = None,
validation_alias: str | AliasPath | AliasChoices | None = None,
```

**❌ Bad**:
```
from typing import Optional, Union
default_factory: Optional[Callable[[], Any]] = None
validation_alias: Union[str, AliasPath, AliasChoices, None] = None
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

## Anti-Patterns

### Docstring Args sections duplicating parameter types

**Why**: Goes stale silently; IDEs and OpenAPI do not read it

**Alternative**: typing.Annotated[T, Doc('...')] keeps the docs on the type

### Positional configuration parameters

**Why**: Couples call sites to parameter order; new options cannot be inserted safely

**Alternative**: Force keyword-only with `*,` and default every configuration option

### warnings.warn(...) without a custom category and without stacklevel

**Why**: Default DeprecationWarning is suppressed for libraries and the traceback points at framework internals

**Alternative**: Use a UserWarning subclass + stacklevel pointing at the caller

## File-Type Guides

### public_api

Every parameter: typed with `X | None`, keyword-only after `*`, documented via Annotated+Doc, deprecations wrapped in typing_extensions.deprecated.

### internal_helpers

_Unset sentinel for optional kwargs that need a 'not passed' distinction; filter `_Unset` before super().__init__.

## Checklist

- [ ] Every public parameter past `self` is keyword-only.
- [ ] Prefer `X | None` over Optional[X] / Union[X, None] in new code.
- [ ] Parameter docs live in Annotated[..., Doc(...)] rather than docstring Args.
- [ ] DeprecationWarning uses FastAPIDeprecationWarning + stacklevel pointing at the caller.
