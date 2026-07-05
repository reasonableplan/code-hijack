# Architecture Analysis

## Design Intent

Werkzeug separates transport-agnostic HTTP semantics (sansio) from the WSGI transport binding, keeps context-local request state on contextvars rather than globals, and treats client-controlled input (hosts, streams) as hostile by default, requiring explicit allowlists/caps before trusting it.

## Rules (6)

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

### Per-request/context-local mutable state must be built on `contextvars.ContextVar`-backed wrappers rather than raw thread-locals or module globals, and must expose an explicit release/cleanup hook the host application (or test harness) calls between requests, so state never leaks across async tasks or threads.

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `backend` | **Scope**: `cross_project`

**Why**: ContextVar-backed storage isolates state per async task/thread automatically; plain module state does not

**Reference**: `src/werkzeug/local.py:35-105`, `src/werkzeug/local.py:186-249`

**✅ Good**:
```
class Local:
    __slots__ = ("__storage",)

    def __init__(self, context_var: ContextVar[dict[str, t.Any]] | None = None) -> None:
        if context_var is None:
            context_var = ContextVar(f"werkzeug.Local<{id(self)}>.storage")
        object.__setattr__(self, "_Local__storage", context_var)

    def __setattr__(self, name: str, value: t.Any) -> None:
        values = self.__storage.get({}).copy()
        values[name] = value
        self.__storage.set(values)
```

**❌ Bad**:
```
class Local:
    def __init__(self):
        self._data = {}  # plain dict shared across threads/tasks, no isolation

    def __setattr__(self, name, value):
        self._data[name] = value
```

**Evidence**:

1. [PREFERENCE] · COMMIT `9741ea9` — refactor LocalProxy, LocalStack, and Local
   > - ContextVar can be proxied with LocalProxy - LocalStack uses a ContextVar directly instead of a Local - name can be used with any proxied object, not only Local - LocalProxy can show a custom error message for unbound objects - a ContextVar can be passed to LocalStack and Local to use instead of creating one internally - use unique names for internal ContextVars

### The URL-matching engine (which path wins for a given request) should be implemented as a separate component from rule definition and URL-building, so that changes to matching performance/correctness do not require touching the public rule-declaration API.

**Priority**: `SHOULD` | **Confidence**: `medium` | **Layer**: `backend` | **Scope**: `cross_project`

**Why**: matcher rewritten from a regex table to a state machine without changing the public Rule/Map API surface

**Reference**: `src/werkzeug/routing/map.py:28`, `src/werkzeug/routing/rules.py:698-731`

**✅ Good**:
```
from .matcher import StateMachineMatcher
...
class Map:
    def __init__(self, ...):
        self._matcher = StateMachineMatcher(merge_slashes)
```

**❌ Bad**:
```
class Rule:
    def matches(self, path):
        # matching priority/backtracking logic implemented inline on Rule,
        # entangled with regex-building and URL-building code
```

**Evidence**:

1. [PREFERENCE] · COMMIT `f01c6cd` — Allow the router to cope with nested groups
   > The previous, regex table, version of the router wrapped each converter's regex in a named capturing group... The new, state machine, version of the router couldn't use this approach as the variable names are likely unique and hence the same rule with different variable names would have separate states, rather than the same.

### Any stream/body read from an untrusted client must enforce a hard cap (bytes, part count, or time) before or during the read, rather than buffering until a downstream limit is hit or relying on the client to behave; the cap must be checked incrementally, not only against a declared Content-Length.

**Priority**: `MUST` | **Confidence**: `high` | **Layer**: `backend` | **Scope**: `cross_project`

**Why**: unbounded chunked/multipart parsing lets a client exhaust server memory even when Content-Length is absent or lies

**Reference**: `src/werkzeug/wrappers/request.py:80-99`

**✅ Good**:
```
#: .. versionchanged:: 3.1
#:     Defaults to 500kB instead of unlimited.
max_form_memory_size: int | None = 500_000

#: The maximum number of multipart parts to parse
max_form_parts = 1000
```

**❌ Bad**:
```
def __init__(self, rfile):
    self._rfile = rfile
    self._done = False
    self._len = 0
    # no max_content_length: chunk length is trusted as-is, request body
    # can grow unbounded across many small chunks
```

**Evidence**:

1. [REJECTION] · PR `PR#3053` — This pull request fixes a Denial of Service (DoS) vulnerability in Werkzeug's handling of HTTP requests with chunked Transfer-Encoding.
   > When handling chunked Transfer-Encoding requests, Werkzeug's previous `DechunkedInput` implementation did not properly enforce limits or validate the chunked data stream. This allowed malicious clients to send malformed or infinite chunked data streams that caused the server to hang or exhaust resources.

## Anti-Patterns

### Trusting the Host header directly for URL/redirect construction

**Why**: enables host-header injection

**Alternative**: validate against an explicit trusted_hosts allowlist, fail closed

### Reading a client stream to EOF without any size/part cap

**Why**: unbounded memory/CPU use, DoS

**Alternative**: enforce max_content_length / max_form_parts incrementally

## Checklist

- [ ] Does new HTTP-semantics code belong in sansio/ instead of wrappers/?
- [ ] Is every use of a client-controlled host value gated by trusted_hosts?
- [ ] Does new stream-consuming code enforce an explicit size/part cap?
