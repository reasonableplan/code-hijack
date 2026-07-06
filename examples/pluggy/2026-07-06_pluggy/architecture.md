# Architecture Analysis

## Design Intent

The execution pipeline (register → sort → multicall → teardown) is defensively designed so the call contract holds no matter what a plugin callback does — raises an exception, registers a new plugin mid-run, or uses a control-flow exception like StopIteration. Cost is pushed onto the cold path (registration), keeping the hot path (calling) a single pre-sorted list traversal.

## Rules (8)

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

## Anti-Patterns

### Skipping the teardown loop and propagating immediately on exception

**Why**: The post-yield blocks of already-set-up wrappers never run, pushing resource cleanup to GC time

**Alternative**: Store the exception, run all teardowns in reverse order in finally, then re-raise (_callers.py:131-172)

### Doing list concatenation/sorting on the call path

**Why**: Hook calling is the hot path, overwhelmingly more frequent than registration

**Alternative**: Maintain a single pre-sorted list via splitpoint insertion at registration time (_hooks.py:482-504)

## Checklist

- [ ] Does code that re-raises a stored exception use with_traceback(saved_tb)?
- [ ] Does code that throws into a generator undo the StopIteration→RuntimeError transformation?
- [ ] Does the execution loop use a snapshot copy of the collection?
- [ ] Does owner-scoped removal remove every match (not just the first)?
