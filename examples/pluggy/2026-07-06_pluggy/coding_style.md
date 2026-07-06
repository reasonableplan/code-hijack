# Coding Style Analysis

## Design Intent

Tests are the single source of truth for behavioral contracts — a behavior fix is only accepted alongside a test that pins the regression, and behavior-changing PRs without tests get closed. Type hints are unified on the modern syntax of the minimum supported version (3.10+), and fine-grained contracts like warnings and ordering are pinned precisely in tests too.

## Rules (6)

### A change that alters behavior must come with a test that pins that behavior — for a regression fix, add a test that exposes the regression first

**Priority**: `MUST` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: Behavior-fix PRs without tests get closed without review — an actual gate in this repo

**Reference**: `testing/test_warnings.py:16-50`, `testing/test_invocations.py:1`

**✅ Good**:
```
with pytest.warns(
    PluggyTeardownRaisedWarning,
    match=r"\bplugin2\b.*\bmy_hook\b.*\n.*ZeroDivisionError",
) as wc:
    with pytest.raises(ZeroDivisionError):
        pm.hook.my_hook()
assert len(wc.list) == 1
```

**❌ Bad**:
```
--- src/pluggy/_manager.py
-        if self._name2plugin.get(name):
+        if self._name2plugin.get(name) is not None:
(the diff from PR#648, which the maintainer actually closed — a behavior fix with no tests)
```

**Evidence**:

1. [INCIDENT] · COMMIT `f087c1e` — Add a test which verifies firstresult wrappers
   > This is to expose the regression from issue #71. Wrappers must return a single value not a list.

2. [REJECTION] · PR `PR#648` — Fix unregister skipping cleanup for falsy plugin objects
   > this looks like a fully agentic pr without tests, i'm jsut going to close it

### Unify type hints on the modern syntax of the minimum supported Python version — X | None (no Optional), collections.abc generics, explicit TypeAlias for type aliases, and from __future__ import annotations at the top of the file

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: When raising the minimum version, migrate the syntax in bulk too — it distinguishes aliases from plain assignments and improves IDE/type-checker accuracy

**Reference**: `src/pluggy/_callers.py:5-24`, `src/pluggy/_manager.py:36-39`

**✅ Good**:
```
from __future__ import annotations

from collections.abc import Generator
from collections.abc import Mapping
from collections.abc import Sequence
...
Teardown: TypeAlias = Generator[None, object, object]
```

**❌ Bad**:
```
from typing import Generator, Mapping, Optional, Union

Teardown = Generator[None, object, object]
def exec(self, res: Optional[Union[int, str]]) -> None: ...
```

**Evidence**:

1. [PREFERENCE] · COMMIT `4dd2443` — Require Python 3.10+, modernize type annotations
   > Modernize type hints: Union → |, Optional → | None - Move Callable imports to collections.abc - Update pyupgrade to --py310-plus

2. [PREFERENCE] · COMMIT `009bdc3` — Add TypeAlias annotations for improved type clarity
   > Leverage TypeAlias (available in Python 3.10+) to explicitly mark type aliases throughout the codebase... This improves IDE support, type checker accuracy, and makes the distinction between type aliases and regular assignments clear.

### Write one import per symbol per line — repeat from X import A instead of grouping with from X import (A, B, C), and sort alphabetically

**Priority**: `SHOULD` | **Confidence**: `medium` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: One symbol per line minimizes the diff/conflict unit — applied consistently across the whole repo

**Reference**: `src/pluggy/__init__.py:17-29`, `src/pluggy/_manager.py:16-28`, `src/pluggy/_callers.py:7-19`

**✅ Good**:
```
from ._hooks import HookCaller
from ._hooks import HookImpl
from ._hooks import HookimplMarker
from ._hooks import HookimplOpts
```

**❌ Bad**:
```
from ._hooks import (HookCaller, HookImpl, HookimplMarker,
                     HookimplOpts, HookRelay, HookspecMarker)
```

### A test that verifies a warning pins not just the warning type but also the message regex (match), the occurrence count, and the emission location (filename)

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: Checking only the type lets an unrelated warning pass the test, missing regressions in message quality or emission site

**Reference**: `testing/test_warnings.py:43-50`, `testing/test_warnings.py:61-65`

**✅ Good**:
```
with pytest.warns(
    DeprecationWarning,
    match=r"is a method but its first parameter 'item' is not 'self'",
):
    pm.add_hookspecs(Api)
```

**❌ Bad**:
```
with pytest.warns(DeprecationWarning):
    pm.add_hookspecs(Api)
```

### For a path that must not emit a warning, don't let it pass implicitly — promote warnings to errors with simplefilter("error") and pin it explicitly

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: A negative case (no warning) passes silently under the default filter — without promoting to an error, you can't catch the regression

**Reference**: `testing/test_warnings.py:76-78`, `testing/test_warnings.py:90-92`

**✅ Good**:
```
with warnings.catch_warnings():
    warnings.simplefilter("error")
    pm.add_hookspecs(Api)
```

**❌ Bad**:
```
def test_hookspec_with_self_no_warning(pm):
    class Api:
        @hookspec
        def my_hook(self, item, extra):
            pass

    pm.add_hookspecs(Api)
```

### For a collection whose order is part of the contract, tests must compare the full expected sequence in order, not just partial containment (in)

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: Execution order (trylast/tryfirst/wrapper placement) is this library's core contract — a containment check can't catch an ordering regression

**Reference**: `testing/test_hookcaller.py:82`, `testing/test_hookcaller.py:118-123`

**✅ Good**:
```
assert funcs(hc.get_hookimpls()) == [
    he_method1_d,
    he_method1_b,
    he_method1_a,
    he_method1_c,
]
```

**❌ Bad**:
```
impls = funcs(hc.get_hookimpls())
assert he_method1_d in impls
assert len(impls) == 4
```

## Anti-Patterns

### A behavior-fix PR without an accompanying test

**Why**: The maintainer closes it without review (as in PR#648)

**Alternative**: Include, in the same PR, a test that exposes the behavior the fix addresses

### Using pytest.warns with only the type

**Why**: Passes even on an unrelated warning, missing message/count regressions

**Alternative**: Verify with a match regex + len(wc.list) (test_warnings.py:43-50)

## Checklist

- [ ] Does a behavior change come with a test that pins that behavior?
- [ ] Does it use | syntax instead of Optional/Union? Are type aliases marked with TypeAlias?
- [ ] Do warning tests pin the match and the count too? Does the no-warning path use simplefilter('error')?
- [ ] Do ordering-contract tests compare the full sequence for equality?
