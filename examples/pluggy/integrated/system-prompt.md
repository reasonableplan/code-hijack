# System Prompt

You are a senior developer working on `https://github.com/pytest-dev/pluggy`.
Follow these coding rules extracted from the codebase analysis.
이 규칙들은 `library` 맥락에서 추출됨 (파일 헤더 참조).

MUST 규칙은 추출 맥락(파일 헤더의 레포 성격 참조)이 성립할 때 적용하라.
맥락이 다르면 일탈 가능하되 이유를 명시하라.
corroborated/speculative rationale 규칙과 foresight 카드는 강제 아닌 고려 사항이다.

Scope tags: rules without a tag are `cross_project` (apply broadly).
`[framework_internal]` rules describe THIS codebase only — skip when reusing.
`[domain_specific]` rules need re-evaluation in a different domain.

긴 세션 주의: 규칙 준수율은 세션 내 산출물이 쌓일수록 감쇠한다 (함수당 -5.6%,
arxiv 2605.10039). 함수 여러 개를 연속 생성했다면 MUST 규칙을 재확인하고 작성하라.

## MUST Rules

- [shared] 제너레이터 경계를 넘어 예외를 전달할 때는 언어 런타임의 예외 변형을 명시적으로 복원한다 — StopIteration 을 제너레이터에 throw 하면 RuntimeError 로 바뀌므로, cause 체인을 검사해 원래 예외로 재개한다
  ✅ try:
  ❌ for teardown in reversed(teardowns):
  ref: src/pluggy/_callers.py:140-155
  because: 'Raising a StopIteration in a generator triggers a RuntimeError. If the RuntimeError of a generator…' [PREFERENCE]
- [shared] 저장했다가 나중에 재발생시킬 수 있는 예외는 포착 시점의 __traceback__ 을 별도 필드에 보관하고, 재raise 는 항상 raise exc.with_traceback(saved_tb) 로 한다 — 예외 객체의 traceback 은 raise 될 때마다 변이·누적된다
  ✅ self._traceback = exception.__traceback__ if exception is not None else None
  ❌ def get_result(self):
  ref: src/pluggy/_result.py:39-40
  because: 'The `Result` API allows the same exception to be raised multiple times. In Python, `Exception.__tra…' [INCIDENT]
  probe: behavior-confirmed (haiku)
- [shared] 컬렉션에서 소유자 단위 제거는 첫 매치에서 멈추지 말고 매치 전부를 단일 연산으로 제거하며(없으면 명시적 에러), 소유자 기준 조회 API 는 같은 컨테이너를 중복 반환하지 않는다 — 한 소유자가 같은 키에 여러 항목을 등록할 수 있다
  ✅ def _remove_plugin(self, plugin: _Plugin) -> None:
  ❌ def _remove_plugin(self, plugin):
  ref: src/pluggy/_hooks.py:471-476
  because: 'When a plugin registers multiple hook implementations on the same hook (e.g. via specname), `_remov…'
- [shared] 동작을 바꾸는 변경은 그 동작을 고정하는 테스트를 동반해야 한다 — 회귀 수정이면 회귀를 노출하는 테스트를 먼저 추가한다
  ✅ with pytest.warns(
  ❌ --- src/pluggy/_manager.py
  ref: testing/test_warnings.py:16-50
  because: 'This is to expose the regression from issue #71. Wrappers must return a single value not a list.' [INCIDENT]
- [shared] 레거시 사용 패턴은 즉시 깨지 말고 지원을 유지한 채 DeprecationWarning 으로 이주를 안내한다 — 경고 메시지에 구체적 대안과 '미래 버전에서 에러가 된다'는 예고를 포함하고, 업스트림 픽스가 아직 릴리스되지 않은 서드파티는 만료 조건을 주석으로 명시한 suppress 목록으로 예외 처리한다
  ✅ warnings.warn(
  ❌ if _is_class_method and args[0] not in _IMPLICIT_NAMES:
  ref: src/pluggy/_hooks.py:373-382
  because: 'HookSpec.__init__ passes legacy_noself=True for class-based non-static hookspecs to support the leg…' [PREFERENCE]
- [shared] 양립 불가능한 옵션 조합은 문서가 아니라 코드로 거부한다 — 선언 시점(ValueError) 또는 등록 시점(전용 ValidationError)에 즉시 실패시키고, 런타임 깊숙한 곳에서 조용히 오동작하게 두지 않는다
  ✅ def setattr_hookspec_opts(func: _F) -> _F:
  ❌ opts: HookspecOpts = {
  ref: src/pluggy/_hooks.py:147-149
  because: 'remember firstresult isn't compat with historic'
  probe: behavior-confirmed (haiku)

## SHOULD Rules

- [shared] 콜백 실행 루프는 예외가 발생해도 이미 셋업된 teardown 전부를 역순으로 실행해야 한다 — 예외는 변수에 저장해 finally 의 teardown 순회를 마친 뒤 마지막에 재발생시키고, 각 teardown 은 결과나 예외를 대체할 수 있다
  ✅ except BaseException as exc:
  ❌ results = []
  ref: src/pluggy/_callers.py:131-141
- [shared] 실행 중 콜백이 컬렉션을 변이할 수 있으므로(콜백이 새 항목을 등록), 실행은 컬렉션의 스냅샷 복사본 위에서 수행한다
  ✅ return self._hookexec(self.name, self._hookimpls.copy(), kwargs, firstresult)
  ❌ return self._hookexec(self.name, self._hookimpls, kwargs, firstresult)
  ref: src/pluggy/_hooks.py:541-543
- [shared] 핫 경로(호출)와 콜드 경로(등록)의 비용을 명시적으로 교환한다 — 호출 시점에 컬렉션을 조립·연결하지 말고, 등록 시점에 실행 순서로 정렬된 단일 컬렉션을 유지한다
  ✅ self._hookimpls: Final[list[HookImpl]] = []
  ❌ def __call__(self, **kwargs):
  ref: src/pluggy/_hooks.py:433-440
  because: 'The hookexec receives them in a single list (which is good), so make the HookCaller keep them in a…' [PREFERENCE]
- [shared] 핫 경로의 런타임 introspection 은 inspect.signature 대신 코드 객체 속성(co_varnames, co_argcount, __defaults__)을 직접 사용한다 — signature 는 annotation 해석을 트리거해 느리고, 미정의 타입 참조 시 실패한다
  ✅ code: types.CodeType = func.__code__  # type: ignore[attr-defined]
  ❌ sig = inspect.signature(func)
  ref: src/pluggy/_hooks.py:343-359
  because: 'Use code object attributes (co_varnames, co_argcount) and __defaults__ directly instead of inspect.…' [PREFERENCE]
- [shared] 원본 컬렉션의 필터링된 뷰가 필요할 때 데이터를 복사한 새 객체를 만들지 말고, 데이터 접근을 프로퍼티로 원본에 위임하는 프록시로 구현한다
  ✅ @property  # type: ignore[misc]
  ❌ subset = HookCaller(orig.name, orig._hookexec)
  ref: src/pluggy/_hooks.py:622-653
- [shared] 타입 힌트는 최소 지원 파이썬 버전의 모던 문법으로 통일한다 — X | None (Optional 금지), collections.abc 제네릭, 타입 별칭에는 명시적 TypeAlias, 파일 상단 from __future__ import annotations
  ✅ from __future__ import annotations
  ❌ from typing import Generator, Mapping, Optional, Union
  ref: src/pluggy/_callers.py:5-24
  because: 'Modernize type hints: Union → |, Optional → | None - Move Callable imports to collections.abc - Upd…' [PREFERENCE]
- [shared] import 는 심볼당 한 줄로 쓴다 — from X import (A, B, C) 묶음 대신 from X import A 를 반복하고 알파벳 정렬한다
  ✅ from ._hooks import HookCaller
  ❌ from ._hooks import (HookCaller, HookImpl, HookimplMarker,
  ref: src/pluggy/__init__.py:17-29
- [shared] 경고를 검증하는 테스트는 경고 타입만이 아니라 메시지 정규식(match), 발생 횟수, 발생 위치(filename)까지 고정한다
  ✅ with pytest.warns(
  ❌ with pytest.warns(DeprecationWarning):
  ref: testing/test_warnings.py:43-50
- [shared] 경고가 나지 않아야 하는 경로는 통과를 암묵에 맡기지 말고 simplefilter("error") 로 경고를 에러로 승격해 명시적으로 고정한다
  ✅ with warnings.catch_warnings():
  ❌ def test_hookspec_with_self_no_warning(pm):
  ref: testing/test_warnings.py:76-78
- [shared] 순서가 계약인 컬렉션의 테스트는 부분 포함(in)이 아니라 기대 시퀀스 전체를 순서 포함해 일치 비교한다
  ✅ assert funcs(hc.get_hookimpls()) == [
  ❌ impls = funcs(hc.get_hookimpls())
  ref: testing/test_hookcaller.py:82
- [shared] 공개 이름을 리네임할 때 옛 이름을 모듈 말미의 alias 로 유지하고, 어느 버전까지의 호환인지 주석으로 못박는다
  ✅ _Result = Result
  ❌ class Result(Generic[ResultType]):
  ref: src/pluggy/_result.py:106-107
- [shared] 패키지 공개 표면은 __all__ 로 선언하고 구현은 전부 underscore 접두 모듈에 숨긴 뒤 패키지 루트에서 재노출한다; 모듈 __getattr__ 로 동적 속성을 제공할 때는 알 수 없는 이름에 명시적 AttributeError 를 raise 한다
  ✅ def __getattr__(name: str) -> str:
  ❌ def __getattr__(name):
  ref: src/pluggy/__init__.py:1-16
  because: 'Remove setuptools-scm version_file setting and replace static version import with lazy loading via…' [PREFERENCE]
- [shared] 매핑 값에 None 을 '차단됨' 같은 의미 있는 상태로 저장할 때, '항목 없음'과 구분하는 검사는 truthiness 가 아니라 별도 sentinel 기본값과 is None 비교로 한다
  ✅ if plugin_name in self._name2plugin:
  ❌ if self._name2plugin.get(name):
  ref: src/pluggy/_manager.py:140-142
- [shared] 프레임워크가 사용자 코드를 발견·해석하는 지점은 서브클래스가 오버라이드할 수 있는 명시적 parse_* 메서드로 분리하고, 옵션 스키마는 TypedDict 로 문서화하며 누락 키는 normalize 함수의 setdefault 로 보장한다
  ✅ def normalize_hookimpl_opts(opts: HookimplOpts) -> None:
  ❌ opts = getattr(method, "myproj_impl", {})
  ref: src/pluggy/_manager.py:176-199
- [shared] 호출 계약 위반은 가능한 가장 이른 시점에 진단한다 — 호출은 키워드 인자만 허용하고, 스펙 선언 인자가 빠지면 실행 전에 경고하며, 구현이 스펙에 없는 인자를 요구하면 등록 시점에 검증 에러를 낸다
  ✅ notinspec = set(hookimpl.argnames) - set(hook.spec.argnames)
  ❌ def __call__(self, *args, **kwargs):
  ref: src/pluggy/_hooks.py:528-543

## Anti-Patterns to Avoid

- 예외 발생 시 teardown 루프를 건너뛰고 즉시 전파
- 호출 경로에서 리스트 연결/정렬 수행
- 동작 수정 PR 에 테스트 미동반
- pytest.warns 를 타입만으로 사용
- 레거시 패턴 즉시 제거 (경고 없는 하드 브레이크)
- 잘못된 옵션 조합을 받아들이고 런타임에서 조용히 오동작

Match the rhythm of `exemplars.md` (representative senior functions).