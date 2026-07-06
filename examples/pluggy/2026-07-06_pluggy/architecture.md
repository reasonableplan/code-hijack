# Architecture Analysis

## Design Intent

실행 파이프라인(등록 → 정렬 → multicall → teardown)은 플러그인 콜백이 무엇을 하든 — 예외를 던지든, 실행 중 새 플러그인을 등록하든, StopIteration 같은 제어흐름 예외를 쓰든 — 호출 계약이 유지되도록 방어적으로 설계됐다. 비용은 콜드 경로(등록)에 배치하고 핫 경로(호출)는 사전 정렬된 단일 리스트 순회로 유지한다.

## Rules (8)

### 제너레이터 경계를 넘어 예외를 전달할 때는 언어 런타임의 예외 변형을 명시적으로 복원한다 — StopIteration 을 제너레이터에 throw 하면 RuntimeError 로 바뀌므로, cause 체인을 검사해 원래 예외로 재개한다

**Priority**: `MUST` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: 래퍼 체인 통과 중 StopIteration 이 RuntimeError 로 둔갑하면 호출자가 원래 제어흐름 예외를 받지 못한다

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

### 저장했다가 나중에 재발생시킬 수 있는 예외는 포착 시점의 __traceback__ 을 별도 필드에 보관하고, 재raise 는 항상 raise exc.with_traceback(saved_tb) 로 한다 — 예외 객체의 traceback 은 raise 될 때마다 변이·누적된다

**Priority**: `MUST` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: 같은 예외를 여러 번 raise 하면 traceback 이 매번 길어지는 무증상 오염 — 1.1.0 에서 실제 회귀

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

**Probe**: behavior-confirmed — control: naive `raise self._exception` — 3회 재raise 시 traceback 4->6->8 프레임 누적 성장 (무증상 오염) / treatment: 포착 시 __traceback__ 별도 저장 + `raise exc.with_traceback(tb)` — 3회 재raise 후 4 프레임 불변 (_result.py 93ac1e9 패턴 재현)

### 컬렉션에서 소유자 단위 제거는 첫 매치에서 멈추지 말고 매치 전부를 단일 연산으로 제거하며(없으면 명시적 에러), 소유자 기준 조회 API 는 같은 컨테이너를 중복 반환하지 않는다 — 한 소유자가 같은 키에 여러 항목을 등록할 수 있다

**Priority**: `MUST` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: 첫 매치 제거는 다중 등록 시 잔존 항목을 남기고, 중복 반환 조회와 결합하면 우연히만 동작하는 취약 구조가 된다

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

### 콜백 실행 루프는 예외가 발생해도 이미 셋업된 teardown 전부를 역순으로 실행해야 한다 — 예외는 변수에 저장해 finally 의 teardown 순회를 마친 뒤 마지막에 재발생시키고, 각 teardown 은 결과나 예외를 대체할 수 있다

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: 예외 시 teardown 스킵은 래퍼 자원 정리를 GC 시점으로 미뤄 실행 순서 보장이 깨진다

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

### 실행 중 콜백이 컬렉션을 변이할 수 있으므로(콜백이 새 항목을 등록), 실행은 컬렉션의 스냅샷 복사본 위에서 수행한다

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: 호출 도중 등록이 일어나면 라이브 리스트 순회는 항목 스킵/중복 실행을 일으킨다

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

### 핫 경로(호출)와 콜드 경로(등록)의 비용을 명시적으로 교환한다 — 호출 시점에 컬렉션을 조립·연결하지 말고, 등록 시점에 실행 순서로 정렬된 단일 컬렉션을 유지한다

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: 등록은 호출보다 훨씬 드물다 — 리스트 연결을 핫 콜 경로에서 제거하는 대신 등록을 약간 느리게 하는 교환

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

### 핫 경로의 런타임 introspection 은 inspect.signature 대신 코드 객체 속성(co_varnames, co_argcount, __defaults__)을 직접 사용한다 — signature 는 annotation 해석을 트리거해 느리고, 미정의 타입 참조 시 실패한다

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: annotation 해석 회피 — 단순·고속이며 PEP 649 지연 평가 환경에서 미정의 참조 실패까지 차단

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

### 원본 컬렉션의 필터링된 뷰가 필요할 때 데이터를 복사한 새 객체를 만들지 말고, 데이터 접근을 프로퍼티로 원본에 위임하는 프록시로 구현한다

**Priority**: `SHOULD` | **Confidence**: `medium` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: 복사본은 원본의 이후 변이(등록/역사적 호출)를 반영 못하고 수명이 얽혀 메모리 누수를 만든다

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

### 예외 발생 시 teardown 루프를 건너뛰고 즉시 전파

**Why**: 이미 셋업된 래퍼들의 post-yield 블록이 실행되지 않아 자원 정리가 GC 시점으로 밀린다

**Alternative**: 예외를 저장하고 finally 에서 teardown 전원 역순 실행 후 재발생 (_callers.py:131-172)

### 호출 경로에서 리스트 연결/정렬 수행

**Why**: 훅 호출은 등록보다 압도적으로 빈번한 핫 경로

**Alternative**: 등록 시점에 splitpoint 삽입으로 사전 정렬된 단일 리스트 유지 (_hooks.py:482-504)

## Checklist

- [ ] 저장된 예외를 재raise 하는 코드가 with_traceback(saved_tb) 을 쓰는가?
- [ ] 제너레이터에 throw 하는 코드가 StopIteration→RuntimeError 변형을 복원하는가?
- [ ] 실행 루프가 컬렉션 스냅샷 복사본을 사용하는가?
- [ ] 소유자 단위 제거가 전체 매치를 제거하는가 (첫 매치 아님)?
