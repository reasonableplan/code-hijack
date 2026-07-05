# Coding Style Analysis

## Design Intent

Style favors precise, PEP604-typed, docstring-self-documenting code where every change is traceable in-place, parsers stay allocation/compile-cheap via module-level precompiled regexes, and backward-compat cleanups are TODO-marked but gated behind real DeprecationWarning cycles.

## Rules (5)

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

## Anti-Patterns

### Using bare `assert` to validate caller-supplied arguments (still present at src/werkzeug/datastructures/range.py:271: `assert is_byte_range_valid(start, stop, length), "Bad range provided"`)

**Why**: stripped under -O, silently skips validation in optimized builds; PR#3183 proposed raising ValueError instead but is not merged at the analyzed commit

**Alternative**: raise ValueError/TypeError explicitly, as the sibling Range class already does

### Removing/renaming a public API without a DeprecationWarning cycle

**Why**: breaks downstream code without notice

**Alternative**: warn with stacklevel=2 naming the replacement, remove next major version

## Checklist

- [ ] New optional/union type written with `|` syntax, not Optional/Union?
- [ ] New regex compiled once at module scope, not per-call?
- [ ] Any removed/changed public behavior gated behind a DeprecationWarning?
