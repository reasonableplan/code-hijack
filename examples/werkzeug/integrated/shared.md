# Shared Layer Rules

> 이 규칙들은 `library` 맥락에서 추출됨

> 공통 규칙 (레이어 무관) → 모든 작업에 적용

**Total rules**: 12

## Architecture

### Protocol-version-independent parsing/validation logic (headers, cookies, host resolution, request/response state) must live in a transport-agnostic layer that the transport-specific (e.g. WSGI) wrapper subclasses, so the same logic can serve multiple transport implementations without duplication.

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: keeping WSGI/ASGI-specific glue thin over a shared sansio core avoids re-implementing HTTP semantics per transport

**Reference**: `src/werkzeug/wrappers/response.py:39`, `src/werkzeug/sansio/response.py:60-66`

**✅ Good**:
```
class Response(_SansIOResponse):
    """Represents an outgoing WSGI HTTP response with body, status, and
    headers. Has properties and methods for using the functionality
    defined by various HTTP specs.
```

**❌ Bad**:
```
class Response:
    """WSGI response."""
    def __init__(self, status=None, headers=None):
        # host resolution, cookie parsing, cache-control parsing all
        # implemented directly here, duplicated again in the ASGI wrapper
```

**Evidence**:

1. [PREFERENCE] · COMMIT `3bc4bd0` — Move sansio code to a sansio module
   > This makes the naming a little easier (called request and response), and allows the sansio module to be considered private/development. The latter is desired as it isn't clear (yet) how to specify the IO interface - in an abstract manner so that both sync and async implementations exist. This also allows further sansio, rather than WSGI based code, to be added in a clear location

2. [PREFERENCE] · COMMIT `4dc084f` — Move the url functions to sans-io
   > This allows ASGI frameworks to also utilise the get_current_url functionality. Note that the trusted host function is part of the wsgi module public API, hence the import without usage. It is not defined in the module to avoid a circular import.

### A host/origin value derived from a client-controlled header must never be trusted for security-relevant decisions (subdomain matching, redirect construction, debugger access) unless checked against an explicit allowlist; without a configured allowlist the code must fail toward the least-trusting safe behavior, not implicit trust.

**Priority**: `MUST` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: Host header is attacker-controlled; using it unchecked for links/redirects enables host-header injection and cache poisoning

**Reference**: `src/werkzeug/sansio/utils.py:78-155`

**✅ Good**:
```
def get_host(
    scheme: str,
    host_header: str | None,
    server: tuple[str, int | None] | None = None,
    trusted_hosts: t.Collection[str] | None = None,
) -> str:
    ...
    if not host_is_trusted(host, trusted_hosts):
        if trusted_hosts:
            raise SecurityError(f"Host {host!r} is not trusted.")
        # Invalid characters, treat as empty.
        return ""
    return host
```

**❌ Bad**:
```
def get_host(environ):
    return environ.get("HTTP_HOST", environ["SERVER_NAME"])  # used directly for redirects/links, no allowlist check
```

**Evidence**:

1. [REJECTION] · COMMIT `71b69df` — restrict debugger trusted hosts
   > Add a list of `trusted_hosts` to the `DebuggedApplication` middleware. It defaults to only allowing `localhost`, `.localhost` subdomains, and `127.0.0.1`. `run_simple(use_debugger=True)` adds its `hostname` argument to the trusted list as well.

2. [REJECTION] · PR `PR#3143` — fix: allow empty host when trusted_hosts is not set
   > Previously, an empty host would always raise, even when was not set. Now, when is not set, empty or invalid hosts are returned as empty string rather than raising an error. This matches the expected behavior described in issue #3142.

### When two modules need each other's types only for type-checking (not runtime), the dependency must be broken with `if t.TYPE_CHECKING:` guarded imports; when a true runtime circular dependency is unavoidable, the import is deferred to the bottom of the defining module with an explicit marker comment, rather than restructuring the whole module boundary.

**Priority**: `SHOULD` | **Confidence**: `medium` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: observed twice independently (deferred-import marker + repeated TYPE_CHECKING guards across wrappers/sansio modules) at src/werkzeug/http.py:1502-1504 and src/werkzeug/wrappers/request.py:26-29

**Reference**: `src/werkzeug/http.py:1502-1504`, `src/werkzeug/wrappers/request.py:26-29`

**✅ Good**:
```
# circular dependencies
from . import datastructures as ds  # noqa: E402
from .sansio import http as _sansio_http  # noqa: E402
```

**❌ Bad**:
```
from .datastructures import Headers  # top-level import that would actually create an import cycle

class Request:
    headers: Headers
```

## Coding Style

### Every module opts into postponed evaluation of annotations and expresses optional/union types with the `X | None` / `A | B` operator syntax, never the `Optional[X]`/`Union[A, B]` generic forms.

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: observed uniformly at src/werkzeug/utils.py:1 and src/werkzeug/utils.py:235-237 across every file read (http.py, wrappers/*, local.py, routing/*)

**Reference**: `src/werkzeug/utils.py:1`, `src/werkzeug/utils.py:235-237`

**✅ Good**:
```
from __future__ import annotations
...
def redirect(
    location: str, code: int = 303, Response: type[Response] | None = None
) -> Response:
```

**❌ Bad**:
```
from typing import Optional

def redirect(location, code=303, Response=None):
    # type: (str, int, Optional[type]) -> Response
```

### Shared test behavior for a family of related implementations is factored into a private, non-collected mixin class holding a class-level attribute naming the concrete type under test; each concrete `Test*` class inherits the mixin and only binds that attribute, instead of duplicating test bodies or using a fixture-parametrize per test.

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: pattern repeats for _MutableMultiDictTests and _ImmutableDictTests independently at tests/test_datastructures.py:17-19 and tests/test_datastructures.py:332-333

**Reference**: `tests/test_datastructures.py:17-19`, `tests/test_datastructures.py:332-333`

**✅ Good**:
```
class _MutableMultiDictTests:
    storage_class: type[ds.MultiDict]
    def test_pickle(self):
        cls = self.storage_class
        ...

class TestMultiDict(_MutableMultiDictTests):
    storage_class = ds.MultiDict
```

**❌ Bad**:
```
class TestMultiDict:
    def test_pickle(self):
        cls = ds.MultiDict
        ...

class TestImmutableMultiDict:
    def test_pickle(self):
        cls = ds.ImmutableMultiDict
        # near-identical body copy-pasted
```

### Removing or changing public behavior must go through a visible `warnings.warn(message, DeprecationWarning, stacklevel=2)` call that names the exact replacement API, kept for at least one release before the old behavior is deleted; a bare TODO marking the eventual removal is acceptable only alongside such a warning, never as the sole signal.

**Priority**: `MUST` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: no-warning removal breaks downstream code silently between versions

**Reference**: `src/werkzeug/http.py:389-397`, `src/werkzeug/wrappers/request.py:253-264`

**✅ Good**:
```
warnings.warn(
    "The 'dump_csp_header' function is deprecated and will be removed in"
    " Werkzeug 3.3. Use the 'ContentSecurityPolicy.to_header' method instead.",
    DeprecationWarning,
    stacklevel=2,
)
```

**❌ Bad**:
```
def dump_csp_header(header):
    # old behavior silently swapped for new behavior, no warning emitted
    return header.to_header()
```

**Evidence**:

1. [COMMENT] · COMMENT `src/werkzeug/wrappers/request.py:482` — TODO
   > TODO remove with parameter_storage_class

2. [COMMENT] · COMMENT `src/werkzeug/http.py:1442` — TODO
   > TODO Remove encoding dance, it seems like clients accept UTF-8 keys

### Regular expressions used by a parser are compiled exactly once at module scope, bound to a name with a leading underscore and a `_re` suffix, and reused by every call; they are never compiled inside the function that uses them.

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: same module-scope-compiled-regex convention repeats at src/werkzeug/http.py:537-549 and src/werkzeug/routing/rules.py:45-84

**Reference**: `src/werkzeug/http.py:537-549`, `src/werkzeug/routing/rules.py:45-84`

**✅ Good**:
```
# https://httpwg.org/specs/rfc9110.html#parameter
_parameter_key_re = re.compile(r"([\w!#$%&'*+\-.^`|~]+)=", flags=re.ASCII)
_parameter_token_value_re = re.compile(r"[\w!#$%&'*+\-.^`|~]+", flags=re.ASCII)
```

**❌ Bad**:
```
def parse_options_header(value):
    key_re = re.compile(r"([\w!#$%&'*+\-.^`|~]+)=")  # recompiled on every call
    ...
```

### Every behavior change to a public function/method is documented in that function's own docstring via a `.. versionchanged::`/`.. versionadded::` block naming the version, colocated with the code, in addition to (not instead of) any external changelog entry.

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: versionchanged/versionadded blocks appear at src/werkzeug/utils.py:390-413 and src/werkzeug/sansio/utils.py:113-125, and nearly every other public docstring read across http.py and wrappers/response.py

**Reference**: `src/werkzeug/utils.py:390-413`, `src/werkzeug/sansio/utils.py:113-125`

**✅ Good**:
```
"""...
.. versionchanged:: 2.0.2
    ``send_file`` only sets a detected ``Content-Encoding`` if
    ``as_attachment`` is disabled.

.. versionadded:: 2.0
    Adapted from Flask's implementation.
"""
```

**❌ Bad**:
```
"""Send the contents of a file to the client."""
# behavior change made silently, only mentioned in CHANGES.rst
```

## Api Design

### Objects that own closable resources (open file handles, temp files, streams) implement the context manager protocol (`__enter__`/`__exit__`) delegating to an explicit `close()`, so callers get deterministic cleanup under both normal return and exception, whether or not they remember to call close directly.

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: same __enter__/close pairing repeats independently at src/werkzeug/wrappers/request.py:321-336, src/werkzeug/wrappers/response.py:407-411, and src/werkzeug/test.py:649-667

**Reference**: `src/werkzeug/wrappers/request.py:321-336`, `src/werkzeug/wrappers/response.py:407-411`, `src/werkzeug/test.py:649-667`

**✅ Good**:
```
def __enter__(self) -> Request:
    return self

def __exit__(self, exc_type, exc_value, tb) -> None:
    self.close()
```

**❌ Bad**:
```
req = Request.from_values(data=data, method="POST")
result = req.files["foo"].read()
# no with-block, no close(): temp files opened for large uploads leak
```

### A module that renames or removes a public top-level name keeps the old name reachable for at least one release by implementing a module-level `__getattr__` (PEP 562) that emits a DeprecationWarning naming the replacement and returns the legacy value, instead of deleting the name outright.

**Priority**: `SHOULD` | **Confidence**: `medium` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: [no-evidence] direct code observation only, no matching commit/PR found in evidence pool

**Reference**: `src/werkzeug/http.py:1506-1543`

**✅ Good**:
```
if not t.TYPE_CHECKING:
    def __getattr__(name: str) -> t.Any:
        if name == "HTTP_STATUS_CODES":
            warnings.warn(
                "The 'HTTP_STATUS_CODES' data is deprecated ...",
                DeprecationWarning,
                stacklevel=2,
            )
            return _HTTP_STATUS_CODES
        ...
```

**❌ Bad**:
```
# HTTP_STATUS_CODES = {...}  # just deleted; any importer gets ImportError with no guidance
```

### When a method's return type depends on a caller-supplied literal flag (e.g. `as_text`, `silent`, `force`), the method is given paired `@t.overload` signatures narrowing the return type per literal value, rather than one signature with a loosely-typed union return that forces every caller to re-check the type.

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: same overload-per-literal-flag idiom repeats at src/werkzeug/wrappers/response.py:262-268 and src/werkzeug/wrappers/request.py:395-413

**Reference**: `src/werkzeug/wrappers/response.py:262-268`, `src/werkzeug/wrappers/request.py:395-413`

**✅ Good**:
```
@t.overload
def get_data(self, as_text: t.Literal[False] = False) -> bytes: ...
@t.overload
def get_data(self, as_text: t.Literal[True]) -> str: ...
def get_data(self, as_text: bool = False) -> bytes | str:
```

**❌ Bad**:
```
def get_data(self, as_text=False):
    # type: (bool) -> Union[bytes, str]
    ...  # every call site needs an isinstance check or cast
```

### A pair of encode/decode (or dump/parse) helper functions that are meant to round-trip must say so explicitly in each other's docstrings ('This is the reverse of :func:`...`'), so a caller reading either one can trust the round-trip contract without re-deriving the wire format from both implementations.

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: the exact phrase 'This is the reverse of' repeats at src/werkzeug/http.py:281-291, src/werkzeug/http.py:400-412, and src/werkzeug/http.py:552-564 across at least 4 independent function pairs

**Reference**: `src/werkzeug/http.py:281-291`, `src/werkzeug/http.py:400-412`, `src/werkzeug/http.py:552-564`

**✅ Good**:
```
def dump_options_header(header: str | None, options: t.Mapping[str, t.Any]) -> str:
    """Produce a header value and ``key=value`` parameters separated by semicolons
    ``;``. For example, the ``Content-Type`` header.

    .. code-block:: python

        dump_options_header("text/html", {"charset": "UTF-8"})
        'text/html; charset=UTF-8'

    This is the reverse of :func:`parse_options_header`.
```

**❌ Bad**:
```
def dump_options_header(header, options):
    """Produce a header value."""
    # caller has no documented guarantee this round-trips with parse_options_header
```
