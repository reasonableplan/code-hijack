# Foresight — `library` 맥락에서 추론된 설계 의도

> ForesightCard 는 LLM 추론 기반 가설이다. 강제 제약이 아닌 고려 사항.

## [corroborated] pluggy 는 pytest/tox/devpi 생태계 전체의 최하부 의존성이므로 런타임 의존성 0 을 의도적으로 유지한다 — 여기서의 의존성 하나가 생태계 전체에 전이되기 때문

**뒷받침 신호**:
- negative_space dep_count=0 — pyproject.toml [project.dependencies] 비어 있음
- src/pluggy/_result.py, _tracing.py, _warnings.py — stdlib 만으로 직접 구현 (direct_impl_hints)
- README.rst — 'This is the core framework used by the pytest, tox, and devpi projects.'

**반증 조건**: 런타임 의존성을 추가하는 커밋/PR 이 머지되면 기각

## [corroborated] 훅 호출 핫 경로의 성능이 명시적 설계 우선순위다 — pytest 가 훅을 수만 번 호출하므로, 등록(콜드) 비용을 올려서라도 호출(핫) 비용을 낮추는 교환을 반복한다

**뒷받침 신호**:
- 63b7e90 — 'avoid the list concatenation in the hot call path... it is much colder than calling so the tradeoff makes sense'
- 1288091 — 런타임 cast() 호출 제거: 'It actually adds measurable overhead here -- ~15% according to testing/benchmark.py'
- testing/benchmark.py — varnames __code__ vs inspect.signature 비교 벤치마크 상주 (fd62ef8)

**반증 조건**: 핫 콜 경로에 벤치마크 근거 없이 편의성 오버헤드를 추가하는 변경이 머지되면 기각

## [corroborated] 하위호환 유지가 아키텍처 결정까지 지배한다 — 구식 hookwrapper 실행기를 별도 함수로 상주시키고, 서드파티 픽스 릴리스를 기다리는 suppress 목록까지 두는 것은 '생태계가 이주할 때까지 라이브러리가 비용을 부담한다'는 원칙

**뒷받침 신호**:
- src/pluggy/_callers.py:27-57 — old-style hookwrapper 전용 실행기 함수 유지
- src/pluggy/_hooks.py:294-303 — _NOSELF_WARN_SUPPRESS: 'pytest-timeout >=2.3.2 has the fix, but is unreleased as of 2026-05'
- src/pluggy/_result.py:106-107 외 3곳 — 'Historical name (pluggy<=1.2), kept for backward compatibility.'

**반증 조건**: deprecation 기간 없이 레거시 지원을 즉시 제거하는 릴리스가 반복되면 기각
