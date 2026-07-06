# Coding Style Analysis

## Design Intent

테스트가 행동 계약의 단일 진실이다 — 동작 수정은 그 회귀를 고정하는 테스트와 함께만 받아들여지고, 테스트 없는 동작 변경 PR 은 닫힌다. 타입 힌트는 최소 지원 버전(3.10+)의 모던 문법으로 통일하고, 경고·순서 같은 미세 계약도 테스트에서 정밀하게 고정한다.

## Rules (6)

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

## Anti-Patterns

### 동작 수정 PR 에 테스트 미동반

**Why**: 메인테이너가 리뷰 없이 닫는다 (PR#648 실례)

**Alternative**: 수정이 고치는 동작을 노출하는 테스트를 같은 PR 에 포함

### pytest.warns 를 타입만으로 사용

**Why**: 무관한 경고로도 통과해 메시지·횟수 회귀를 놓침

**Alternative**: match 정규식 + len(wc.list) 검증 (test_warnings.py:43-50)

## Checklist

- [ ] 동작 변경에 그 동작을 고정하는 테스트가 동반되는가?
- [ ] Optional/Union 대신 | 문법을 쓰는가? 타입 별칭에 TypeAlias 를 붙였는가?
- [ ] 경고 테스트가 match·횟수까지 고정하는가? 무경고 경로는 simplefilter('error')?
- [ ] 순서 계약 테스트가 전체 시퀀스 일치 비교인가?
