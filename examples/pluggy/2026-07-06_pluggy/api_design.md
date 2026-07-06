# Api Design Analysis

## Design Intent

As the bottommost library in the pytest/tox/devpi ecosystem, backward compatibility comes first — instead of breaking legacy patterns, support is kept while DeprecationWarning guides migration, and old public names remain as aliases. Conversely, invalid usage is rejected with an explicit error at the earliest possible point (declaration/registration), to block silent runtime misbehavior.

## Rules (7)

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

## Anti-Patterns

### Removing a legacy pattern immediately (a hard break with no warning)

**Why**: Breaks thousands of downstream plugins — this repo uses the warn-then-error path without exception

**Alternative**: Keep support + DeprecationWarning (with alternative and notice) + a suppress list with an explicit expiry condition

### Accepting an invalid option combination and silently misbehaving at runtime

**Why**: A silent error deep inside hook execution is untraceable for plugin authors

**Alternative**: A ValueError/PluginValidationError at declaration/registration time (with the plugin object attached)

## Checklist

- [ ] Does a public-surface change have a deprecation path (warning + alternative + notice)?
- [ ] Is an incompatible option combination rejected at declaration/registration time?
- [ ] Does a rename leave a historical alias + a version comment?
- [ ] Does distinguishing a None-sentinel state avoid using truthiness?
