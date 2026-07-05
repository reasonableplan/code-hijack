# Api Design Analysis

## Design Intent

Public surfaces favor explicit failure over silent fallback (sentinel None for unsafe paths, AttributeError for wrong-mode access), precise typing for literal-dependent return shapes, resource objects are context-manager-safe, and a soft-landing path (module __getattr__ + DeprecationWarning) exists for renamed/removed names.

## Rules (6)

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

## Anti-Patterns

### A path-joining helper silently falling back to a 'safe-looking' path instead of returning None on escape

**Why**: callers won't notice the escape attempt

**Alternative**: return None and require the caller to check

### A builder property silently returning stale/empty data when a mutually-exclusive mode is active

**Why**: masks programmer error

**Alternative**: raise AttributeError naming the conflicting attribute

## Checklist

- [ ] Does a new sentinel-returning helper actually get checked by every caller before use?
- [ ] Do new mutually-exclusive builder properties raise instead of silently returning stale data?
- [ ] Is a removed/renamed public name kept reachable via module __getattr__ + DeprecationWarning?
