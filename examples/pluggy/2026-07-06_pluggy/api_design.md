# Api Design Analysis

## Design Intent

pytest/tox/devpi 생태계의 최하부 라이브러리로서 하위호환이 최우선이다 — 레거시 패턴은 깨는 대신 지원을 유지한 채 DeprecationWarning 으로 이주를 안내하고, 옛 공개 이름은 alias 로 남긴다. 반대로 잘못된 사용은 가능한 가장 이른 시점(선언/등록)에 명시적 에러로 거부해 런타임 무증상 오동작을 차단한다.

## Rules (7)

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

## Anti-Patterns

### 레거시 패턴 즉시 제거 (경고 없는 하드 브레이크)

**Why**: 수천 개 하위 플러그인 파손 — 이 레포는 예외 없이 warn-then-error 경로를 쓴다

**Alternative**: 지원 유지 + DeprecationWarning(대안·예고 포함) + 만료 조건 명시 suppress 목록

### 잘못된 옵션 조합을 받아들이고 런타임에서 조용히 오동작

**Why**: 훅 실행 깊숙한 곳의 무증상 오류는 플러그인 작성자가 추적 불가

**Alternative**: 선언/등록 시점 ValueError·PluginValidationError (plugin 객체 첨부)

## Checklist

- [ ] 공개 표면 변경에 deprecation 경로(경고+대안+예고)가 있는가?
- [ ] 비호환 옵션 조합이 선언/등록 시점에 거부되는가?
- [ ] 리네임에 historical alias + 버전 주석이 남는가?
- [ ] None-sentinel 상태 구분에 truthiness 를 쓰지 않았는가?
