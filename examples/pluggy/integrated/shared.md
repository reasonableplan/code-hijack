# Shared Layer Rules

> These rules were extracted in a `library` context

> Cross-cutting rules (any layer) → applies to all work

**Total rules**: 21

## Architecture

### When passing an exception across a generator boundary, explicitly undo the language runtime's exception transformation — throwing StopIteration into a generator turns it into a RuntimeError, so inspect the cause chain and resume with the original exception

**Priority**: `MUST` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: If StopIteration turns into a RuntimeError while passing through the wrapper chain, the caller never receives the original control-flow exception

**Reference**: `src/pluggy/_callers.py:140-155`

**✅ Good**:
```
try:
    teardown.throw(exception)
except RuntimeError as re:
    # StopIteration from generator causes RuntimeError
    # even for coroutine usage - see #544
    if (
        isinstance(exception, StopIteration)
        and re.__cause__ is exception
    ):
        teardown.close()
        continue
    else:
        raise
```

**❌ Bad**:
```
for teardown in reversed(teardowns):
    if exception is not None:
        teardown.throw(exception)
    else:
        teardown.send(result)
```

**Evidence**:

1. [PREFERENCE] · COMMIT `3875ea5` — fix #544: Correctly pass StopIteration trough wrappers
   > Raising a StopIteration in a generator triggers a RuntimeError. If the RuntimeError of a generator has the passed in StopIteration as cause resume with that StopIteration as normal exception instead of failing with the RuntimeError.

### For exceptions that may be stored and re-raised later, save their __traceback__ in a separate field at capture time, and always re-raise via raise exc.with_traceback(saved_tb) — an exception object's traceback mutates and accumulates every time it is raised

**Priority**: `MUST` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: Raising the same exception multiple times silently pollutes it as the traceback grows longer each time — an actual regression in 1.1.0

**Reference**: `src/pluggy/_result.py:39-40`, `src/pluggy/_result.py:97-103`

**✅ Good**:
```
# Exception __traceback__ is mutable, this keeps the original.
self._traceback = exception.__traceback__ if exception is not None else None
...
exc = self._exception
tb = self._traceback
if exc is None:
    return cast(ResultType, self._result)
else:
    raise exc.with_traceback(tb)
```

**❌ Bad**:
```
def get_result(self):
    if self._exception is not None:
        raise self._exception
    return self._result
```

**Evidence**:

1. [INCIDENT] · COMMIT `93ac1e9` — result: keep original traceback and reraise with it
   > The `Result` API allows the same exception to be raised multiple times. In Python, `Exception.__traceback__` becomes longer everytime an exception is raised. This means that on every raise, the exception's traceback gets longer and longer. To prevent this, save the original traceback and always raise using it. Regressed in pluggy 1.1.0 (fbc444218c442dd8cbe29bd68cde8fea52b56baf).

**Probe**: behavior-confirmed — control: naive `raise self._exception` — traceback grows 4->6->8 frames across 3 re-raises (silent pollution) / treatment: saves __traceback__ separately at capture + `raise exc.with_traceback(tb)` — stays at 4 frames after 3 re-raises (reproduces the _result.py 93ac1e9 pattern)

### Owner-scoped removal from a collection must not stop at the first match — remove every match in a single operation (raise an explicit error if none match), and owner-scoped lookup APIs must not return the same container as a duplicate — one owner can register multiple entries under the same key

**Priority**: `MUST` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: First-match removal leaves stale entries behind under multiple registrations, and combined with a duplicate-returning lookup it becomes a fragile structure that only works by accident

**Reference**: `src/pluggy/_hooks.py:471-476`, `src/pluggy/_manager.py:434-447`

**✅ Good**:
```
def _remove_plugin(self, plugin: _Plugin) -> None:
    """Remove all hook implementations registered by the given plugin."""
    remaining = [impl for impl in self._hookimpls if impl.plugin != plugin]
    if len(remaining) == len(self._hookimpls):
        raise ValueError(f"plugin {plugin!r} not found")
    self._hookimpls[:] = remaining
```

**❌ Bad**:
```
def _remove_plugin(self, plugin):
    for i, method in enumerate(self._hookimpls):
        if method.plugin == plugin:
            del self._hookimpls[i]
            return
    raise ValueError(f"plugin {plugin!r} not found")
```

**Evidence**:

1. [COMMIT] · COMMIT `20d8143` — Fix _remove_plugin to remove all hookimpls and get_hookcallers to deduplicate (#646)
   > When a plugin registers multiple hook implementations on the same hook (e.g. via specname), `_remove_plugin` only removed the first matching hookimpl. This worked because `get_hookcallers` returned duplicate HookCaller entries, causing `_remove_plugin` to be called multiple times. This was fragile and made `get_hookcallers` return unexpected duplicates to callers of the public API.

### The callback execution loop must run every already-set-up teardown in reverse order even if an exception occurs — store the exception in a variable, run through all teardowns in finally, then re-raise it last; each teardown may replace the result or the exception

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: Skipping teardown on exception defers wrapper resource cleanup to GC time, breaking the execution-order guarantee

**Reference**: `src/pluggy/_callers.py:131-141`, `src/pluggy/_callers.py:44-57`

**✅ Good**:
```
except BaseException as exc:
    exception = exc
finally:
    if firstresult:  # first result hooks return a single value
        result = results[0] if results else None
    else:
        result = results

    # run all wrapper post-yield blocks
    for teardown in reversed(teardowns):
```

**❌ Bad**:
```
results = []
for hook_impl in reversed(hook_impls):
    results.append(hook_impl.function(*args))
for teardown in reversed(teardowns):
    teardown.send(results)
```

### Since a callback can mutate the collection during execution (by registering a new entry), execution must run over a snapshot copy of the collection

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: If registration happens mid-call, iterating the live list causes entries to be skipped or executed twice

**Reference**: `src/pluggy/_hooks.py:541-543`, `src/pluggy/_hooks.py:563-565`

**✅ Good**:
```
# Copy because plugins may register other plugins during iteration (#438).
return self._hookexec(self.name, self._hookimpls.copy(), kwargs, firstresult)
```

**❌ Bad**:
```
return self._hookexec(self.name, self._hookimpls, kwargs, firstresult)
```

### Explicitly trade cost between the hot path (calling) and the cold path (registration) — don't assemble/concatenate the collection at call time; maintain a single collection sorted in execution order at registration time

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: Registration is far rarer than calling — a tradeoff that makes registration a bit slower in exchange for removing list concatenation from the hot call path

**Reference**: `src/pluggy/_hooks.py:433-440`, `src/pluggy/_hooks.py:482-504`

**✅ Good**:
```
# The hookimpls list. The caller iterates it *in reverse*. Format:
# 1. trylast nonwrappers
# 2. nonwrappers
# 3. tryfirst nonwrappers
# 4. trylast wrappers
# 5. wrappers
# 6. tryfirst wrappers
self._hookimpls: Final[list[HookImpl]] = []
```

**❌ Bad**:
```
def __call__(self, **kwargs):
    impls = self._nonwrappers + self._wrappers
    return self._hookexec(self.name, impls, kwargs, firstresult)
```

**Evidence**:

1. [PREFERENCE] · COMMIT `63b7e90` — hooks: keep hookimpls in a single list
   > The hookexec receives them in a single list (which is good), so make the HookCaller keep them in a single array as well, so can avoid the list concatenation in the hot call path. This makes adding a hookimpl a little slower, but not by much, and it is much colder than calling so the tradeoff makes sense.

### For runtime introspection on the hot path, use code object attributes (co_varnames, co_argcount, __defaults__) directly instead of inspect.signature — signature triggers annotation resolution, which is slow and fails on references to undefined types

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: Avoids annotation resolution — simple and fast, and it also prevents failures on undefined references under PEP 649 deferred evaluation

**Reference**: `src/pluggy/_hooks.py:343-359`

**✅ Good**:
```
code: types.CodeType = func.__code__  # type: ignore[attr-defined]
defaults: tuple[object, ...] | None = func.__defaults__  # type: ignore[attr-defined]
...
args: tuple[str, ...] = code.co_varnames[: code.co_argcount]
```

**❌ Bad**:
```
sig = inspect.signature(func)
args = [p.name for p in sig.parameters.values()
        if p.kind is p.POSITIONAL_OR_KEYWORD]
```

**Evidence**:

1. [PREFERENCE] · COMMIT `c4e254c` — Simplify varnames to use code object directly
   > Use code object attributes (co_varnames, co_argcount) and __defaults__ directly instead of inspect.signature(). This avoids annotation resolution entirely, which is simpler and more efficient.

2. [CONSTRAINT] · COMMIT `74876c4` — Fix varnames to handle Python 3.14 deferred annotations
   > In Python 3.14+, annotations are evaluated lazily per PEP 649/749. When inspect.signature() is called, it tries to resolve annotations by default, which fails if the annotation references an undefined type.

### When a filtered view of the original collection is needed, don't build a new object with copied data — implement a proxy that delegates data access to the original via a property

**Priority**: `SHOULD` | **Confidence**: `medium` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: A copy can't reflect later mutations to the original (registration/historic calls), and its entangled lifetime creates a memory leak

**Reference**: `src/pluggy/_hooks.py:622-653`, `src/pluggy/_manager.py:511-521`

**✅ Good**:
```
@property  # type: ignore[misc]
def _hookimpls(self) -> list[HookImpl]:
    return [
        impl
        for impl in self._orig._hookimpls
        if impl.plugin not in self._remove_plugins
    ]
```

**❌ Bad**:
```
subset = HookCaller(orig.name, orig._hookexec)
for impl in orig._hookimpls:
    if impl.plugin not in remove_plugins:
        subset._add_hookimpl(impl)
return subset
```

## Coding Style

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

## Api Design

### Don't break a legacy usage pattern immediately — keep support while guiding migration with a DeprecationWarning. Include a concrete alternative and a notice that 'this will become an error in a future version' in the warning message, and for third parties whose upstream fix hasn't shipped yet, exempt them via a suppress list with the expiry condition documented in a comment

**Priority**: `MUST` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: Thousands of downstream plugins depend on it — giving migration time via a warning instead of a hard break is this repo's recurring decision

**Reference**: `src/pluggy/_hooks.py:373-382`, `src/pluggy/_hooks.py:294-303`

**✅ Good**:
```
warnings.warn(
    f"{qualname} is a method but its first parameter"
    f" {args[0]!r} is not 'self'."
    f" Add 'self' as the first parameter or use @staticmethod."
    f" This will become an error in a future version of pluggy.",
    DeprecationWarning,
    stacklevel=2,
)
```

**❌ Bad**:
```
if _is_class_method and args[0] not in _IMPLICIT_NAMES:
    raise TypeError(f"{qualname} must declare 'self' as first parameter")
```

**Evidence**:

1. [PREFERENCE] · COMMIT `dd20a85` — Warn from varnames for hookspec methods missing self
   > HookSpec.__init__ passes legacy_noself=True for class-based non-static hookspecs to support the legacy pattern while warning about it.

2. [PREFERENCE] · COMMIT `0258484` — Address review: DeprecationWarning, add self to test, suppress pytest-timeout
   > Change FutureWarning to DeprecationWarning for hookspec methods missing self... Suppress the deprecation warning for pytest-timeout's TimeoutHooks (upstream fix exists but is unreleased)

### Reject incompatible option combinations in code, not just documentation — fail immediately at declaration time (ValueError) or registration time (a dedicated ValidationError), rather than letting it silently misbehave deep in runtime

**Priority**: `MUST` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: Letting an incompatible combination through (historic×firstresult, wrapper×hookwrapper, etc.) causes silent misbehavior deep inside hook execution

**Reference**: `src/pluggy/_hooks.py:147-149`, `src/pluggy/_manager.py:371-377`

**✅ Good**:
```
def setattr_hookspec_opts(func: _F) -> _F:
    if historic and firstresult:
        raise ValueError("cannot have a historic firstresult hook")
```

**❌ Bad**:
```
opts: HookspecOpts = {
    "firstresult": firstresult,
    "historic": historic,
}
setattr(func, self.project_name + "_spec", opts)
```

**Evidence**:

1. [COMMENT] · COMMENT `src/pluggy/_hooks.py:613` — XXX
   > remember firstresult isn't compat with historic

**Probe**: behavior-confirmed — control: silently accepts the incompatible combination — stores opts and passes it straight through / treatment: rejects with a ValueError at declaration time — reproduces pluggy's original message 'cannot have a historic firstresult hook' verbatim

### When renaming a public name, keep the old name as an alias at the end of the module, and pin down in a comment which version it stays compatible through

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: Even internal symbols are already imported by the ecosystem — the library absorbs the cost of the rename

**Reference**: `src/pluggy/_result.py:106-107`, `src/pluggy/_hooks.py:402-403`, `src/pluggy/_hooks.py:618-619`

**✅ Good**:
```
# Historical name (pluggy<=1.2), kept for backward compatibility.
_Result = Result
```

**❌ Bad**:
```
class Result(Generic[ResultType]):
    ...

# (the _Result alias removed — immediately breaks downstream users importing the old name)
```

### Declare the package's public surface via __all__, hide all implementation in underscore-prefixed modules, and re-export from the package root; when providing dynamic attributes via module __getattr__, raise an explicit AttributeError for unknown names

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: Defer the import-time cost (metadata lookup) via lazy loading, while making sure a typo'd access doesn't silently return the wrong value

**Reference**: `src/pluggy/__init__.py:1-16`, `src/pluggy/__init__.py:32-38`

**✅ Good**:
```
def __getattr__(name: str) -> str:
    if name == "__version__":
        from importlib.metadata import version

        return version("pluggy")

    raise AttributeError(f"module {__name__} has no attribute {name!r}")
```

**❌ Bad**:
```
def __getattr__(name):
    from importlib.metadata import version
    return version("pluggy")
```

**Evidence**:

1. [PREFERENCE] · COMMIT `96e05d6` — Remove version_file setting and migrate to lazy version loading
   > Remove setuptools-scm version_file setting and replace static version import with lazy loading via __getattr__ using importlib.metadata.version.

### When storing None in a mapping value to mean a meaningful state like 'blocked', distinguish it from 'no entry' using a separate sentinel default and an is None comparison, not truthiness

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: If a falsy value object collides with the 'blocked' sentinel, state silently leaks — a defect type that actually persists in this repo's unregister path

**Reference**: `src/pluggy/_manager.py:140-142`, `src/pluggy/_manager.py:247-250`

**✅ Good**:
```
if plugin_name in self._name2plugin:
    if self._name2plugin.get(plugin_name, -1) is None:
        return None  # blocked plugin, return None to indicate no registration
```

**❌ Bad**:
```
if self._name2plugin.get(name):
    del self._name2plugin[name]
```

### Separate the point where the framework discovers and interprets user code into an explicit parse_* method that subclasses can override; document the option schema with a TypedDict, and guarantee missing keys via setdefault in a normalize function

**Priority**: `SHOULD` | **Confidence**: `medium` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: Exposing the discovery logic as a method lets hosts like pytest customize the convention — option defaults are guaranteed in one place

**Reference**: `src/pluggy/_manager.py:176-199`, `src/pluggy/_hooks.py:282-288`, `src/pluggy/_hooks.py:41-75`

**✅ Good**:
```
def normalize_hookimpl_opts(opts: HookimplOpts) -> None:
    opts.setdefault("tryfirst", False)
    opts.setdefault("trylast", False)
    opts.setdefault("wrapper", False)
    opts.setdefault("hookwrapper", False)
    opts.setdefault("optionalhook", False)
    opts.setdefault("specname", None)
```

**❌ Bad**:
```
opts = getattr(method, "myproj_impl", {})
tryfirst = opts["tryfirst"] if "tryfirst" in opts else False
trylast = opts.get("trylast") or False
```

### Diagnose call-contract violations as early as possible — allow only keyword arguments in calls, warn before execution if a spec-declared argument is missing, and raise a validation error at registration time if an implementation requires an argument not in the spec

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: Deferring an argument mismatch to a KeyError at hook-execution time makes it impossible to trace which plugin or declaration is at fault

**Reference**: `src/pluggy/_hooks.py:528-543`, `src/pluggy/_manager.py:344-352`, `src/pluggy/_hooks.py:509-526`

**✅ Good**:
```
notinspec = set(hookimpl.argnames) - set(hook.spec.argnames)
if notinspec:
    raise PluginValidationError(
        hookimpl.plugin,
        f"Plugin {hookimpl.plugin_name!r} for hook {hook.name!r}\n"
        f"hookimpl definition: {_formatdef(hookimpl.function)}\n"
        f"Argument(s) {notinspec} are declared in the hookimpl but "
        "can not be found in the hookspec",
    )
```

**❌ Bad**:
```
def __call__(self, *args, **kwargs):
    return self._hookexec(self.name, self._hookimpls.copy(), kwargs, False)
```
