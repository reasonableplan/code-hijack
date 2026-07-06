# Shared Layer Rules

> 이 규칙들은 `library` 맥락에서 추출됨

> 공통 규칙 (레이어 무관) → 모든 작업에 적용

**Total rules**: 21

## Architecture

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

## Coding Style

### 동작을 바꾸는 변경은 그 동작을 고정하는 테스트를 동반해야 한다 — 회귀 수정이면 회귀를 노출하는 테스트를 먼저 추가한다

**Priority**: `MUST` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: 테스트 없는 동작 수정 PR 은 리뷰 없이 닫힌다 — 이 레포의 실제 게이트

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
(메인테이너가 실제로 닫은 PR#648 의 diff — 동작 수정이나 테스트 없음)
```

**Evidence**:

1. [INCIDENT] · COMMIT `f087c1e` — Add a test which verifies firstresult wrappers
   > This is to expose the regression from issue #71. Wrappers must return a single value not a list.

2. [REJECTION] · PR `PR#648` — Fix unregister skipping cleanup for falsy plugin objects
   > this looks like a fully agentic pr without tests, i'm jsut going to close it

### 타입 힌트는 최소 지원 파이썬 버전의 모던 문법으로 통일한다 — X | None (Optional 금지), collections.abc 제네릭, 타입 별칭에는 명시적 TypeAlias, 파일 상단 from __future__ import annotations

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: 버전 하한을 올릴 때 문법도 일괄 이주 — 별칭과 일반 대입의 구분, IDE/타입체커 정확도

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

### import 는 심볼당 한 줄로 쓴다 — from X import (A, B, C) 묶음 대신 from X import A 를 반복하고 알파벳 정렬한다

**Priority**: `SHOULD` | **Confidence**: `medium` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: 한 줄 한 심볼은 diff/충돌 단위를 최소화 — 레포 전체에서 일관 적용된 형태

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

### 경고를 검증하는 테스트는 경고 타입만이 아니라 메시지 정규식(match), 발생 횟수, 발생 위치(filename)까지 고정한다

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: 타입만 검사하면 무관한 경고가 테스트를 통과시켜 메시지 품질·발생 지점 회귀를 놓친다

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

### 경고가 나지 않아야 하는 경로는 통과를 암묵에 맡기지 말고 simplefilter("error") 로 경고를 에러로 승격해 명시적으로 고정한다

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: 부정 케이스(경고 없음)는 기본 필터에선 침묵 통과 — 에러 승격 없이는 회귀를 못 잡는다

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

### 순서가 계약인 컬렉션의 테스트는 부분 포함(in)이 아니라 기대 시퀀스 전체를 순서 포함해 일치 비교한다

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: 실행 순서(trylast/tryfirst/wrapper 배치)가 이 라이브러리의 핵심 계약 — 포함 검사로는 순서 회귀를 못 잡는다

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

### 레거시 사용 패턴은 즉시 깨지 말고 지원을 유지한 채 DeprecationWarning 으로 이주를 안내한다 — 경고 메시지에 구체적 대안과 '미래 버전에서 에러가 된다'는 예고를 포함하고, 업스트림 픽스가 아직 릴리스되지 않은 서드파티는 만료 조건을 주석으로 명시한 suppress 목록으로 예외 처리한다

**Priority**: `MUST` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: 수천 개 하위 플러그인이 의존 — 하드 브레이크 대신 경고로 이주 시간을 주는 게 이 레포의 반복 결정

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

### 양립 불가능한 옵션 조합은 문서가 아니라 코드로 거부한다 — 선언 시점(ValueError) 또는 등록 시점(전용 ValidationError)에 즉시 실패시키고, 런타임 깊숙한 곳에서 조용히 오동작하게 두지 않는다

**Priority**: `MUST` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: 비호환 조합(historic×firstresult, wrapper×hookwrapper 등)을 통과시키면 훅 실행 깊숙한 곳에서 무증상 오동작

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

**Probe**: behavior-confirmed — control: 비호환 조합 무증상 수용 — opts 저장 후 그대로 통과 / treatment: 선언 시점 ValueError 거부 — pluggy 원문 메시지 'cannot have a historic firstresult hook' verbatim 재현

### 공개 이름을 리네임할 때 옛 이름을 모듈 말미의 alias 로 유지하고, 어느 버전까지의 호환인지 주석으로 못박는다

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: 내부 심볼도 생태계가 이미 import 하고 있다 — 리네임의 비용을 라이브러리가 부담

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

# (_Result alias 제거 — 옛 이름 import 하던 하위 사용자 즉시 파손)
```

### 패키지 공개 표면은 __all__ 로 선언하고 구현은 전부 underscore 접두 모듈에 숨긴 뒤 패키지 루트에서 재노출한다; 모듈 __getattr__ 로 동적 속성을 제공할 때는 알 수 없는 이름에 명시적 AttributeError 를 raise 한다

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: 임포트 시점 비용(메타데이터 조회)은 지연 로딩으로 미루되, 오탈자 접근이 조용히 엉뚱한 값을 반환하지 않게 한다

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

### 매핑 값에 None 을 '차단됨' 같은 의미 있는 상태로 저장할 때, '항목 없음'과 구분하는 검사는 truthiness 가 아니라 별도 sentinel 기본값과 is None 비교로 한다

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: falsy 한 값 객체가 '차단' sentinel 과 충돌하면 무증상 상태 누수 — 레포의 unregister 경로에 실제로 잔존하는 결함 유형

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

### 프레임워크가 사용자 코드를 발견·해석하는 지점은 서브클래스가 오버라이드할 수 있는 명시적 parse_* 메서드로 분리하고, 옵션 스키마는 TypedDict 로 문서화하며 누락 키는 normalize 함수의 setdefault 로 보장한다

**Priority**: `SHOULD` | **Confidence**: `medium` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: 발견 로직을 메서드로 노출해 pytest 등 호스트가 관례를 커스텀 — 옵션 기본값은 한 곳에서 보장

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

### 호출 계약 위반은 가능한 가장 이른 시점에 진단한다 — 호출은 키워드 인자만 허용하고, 스펙 선언 인자가 빠지면 실행 전에 경고하며, 구현이 스펙에 없는 인자를 요구하면 등록 시점에 검증 에러를 낸다

**Priority**: `SHOULD` | **Confidence**: `high` | **Layer**: `shared` | **Scope**: `cross_project`

**Why**: 인자 불일치를 훅 실행 시점의 KeyError 로 미루면 어느 플러그인·어느 선언이 문제인지 추적 불가

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
