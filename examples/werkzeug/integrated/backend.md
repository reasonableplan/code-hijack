# Backend Layer Rules

> These rules were extracted in a `library` context

> Backend files (.py, backend/) → this file + shared.md

**Total rules**: 5

## Architecture

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

## Api Design

### A path-joining helper that combines a trusted base directory with an untrusted, caller-supplied segment must reject any escape attempt (parent traversal, absolute path, drive letter, alternate path separator) by returning a sentinel value (`None`) rather than the unsafe path, forcing every caller to branch on failure before using the result; it must never silently substitute a 'safe-looking' fallback path.

**Priority**: `MUST` | **Confidence**: `high` | **Layer**: `backend` | **Scope**: `cross_project`

**Why**: returning a sentinel forces the caller to handle the escape case explicitly instead of accidentally serving an out-of-bounds file

**Reference**: `src/werkzeug/utils.py:574-577`, `tests/test_security.py:45-55`

**✅ Good**:
```
path_str = safe_join(os.fspath(directory), os.fspath(path))

if path_str is None:
    raise NotFound()
```

**❌ Bad**:
```
path_str = os.path.join(directory, path)  # untrusted `path` may contain '../' or an absolute path
return send_file(path_str, environ)
```

**Evidence**:

1. [INCIDENT] · PR `PR#3174` — safe_join Windows special device / relative path hardening attempt
   > My pull request improves 'safe_join' posture by blocking Windows 'nt' system' raletive paths. The changes prevent relative path segments that contain colons (`:`) on utilization of directory traversal elements (`..`), delimiters of various paths (`/`), and trailing termination stream.

### A builder/configuration object that supports two mutually-exclusive representations of the same data (e.g. raw stream vs. parsed form/files, or a literal query string vs. structured args) exposes both as properties, and accessing the representation that is not currently active raises `AttributeError` with a message naming which other attribute is set, rather than silently returning stale or empty data.

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `backend` | **Scope**: `cross_project`

**Why**: same mutually-exclusive-property-raises-AttributeError pattern repeats at src/werkzeug/test.py:512-527 (form/files vs input_stream) and src/werkzeug/test.py:589-628 (query_string vs args)

**Reference**: `src/werkzeug/test.py:512-527`, `src/werkzeug/test.py:589-628`

**✅ Good**:
```
@property
def form(self) -> MultiDict[str, str]:
    if self.input_stream is not None:
        raise AttributeError("Not available when 'input_stream' is set.")
    return self._form
```

**❌ Bad**:
```
@property
def form(self):
    return self._form  # silently empty/stale if input_stream was set instead
```
