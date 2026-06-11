# 작업 일지

> Append-only. 최신이 위. 사람-AI 공동 작성.
> 자동: /ha-design, /ha-build, /ha-redesign commit 시 박힘.
> 수동: /ha-log "..." 명령.

## 2026-06-11

### 변경






- ha-verify 중 negative_space.py 빈 path.parts 가드 추가 (pyright tuple 내로잉 — len()==0 체크). Phase 3 코드 pyright clean 달성
- Foresight E2E 1차 (starlette): 실 버그 2건 발견·수정 — (1) negative_space 상대경로를 cwd 기준으로 읽어 클론 레포에서 FileNotFoundError (repo_root resolve + 회귀 테스트), (2) SKILL.md step4 예시 AnalysisRule(**r) 이 evidence dict 미변환 → from_json 으로 정정. 산출물: 규칙 14 (cited 7/corroborated 5/speculative 2, MUST 5 전원 cited 36%), foresight 카드 4 (corroborated 3 + speculative 1, 반증 조건 포함), library 헤더 + 맥락 조건부 톤 정상 렌더. intent_kind 는 여전히 preference 위주 (incident/rejection 0 — commit 마이닝 한계 재확인, PR/issue 마이닝 P1 유효)
- /ha-redesign applied -- decision=Evidence source expansion + measurement loop: (1) PR/issue m, sections=5, tasks=0
- 재도출 (Sonnet 위임): skeleton §2/§7/§8/§9/§10 갱신 + tasks.md 에 Phase 4 T-036~T-039 신설 (스펙 블록 포함). PRDecision 스키마는 archaeology.py 의 CommitDecision 실 필드에서 도출, §6 CLI 갱신은 T-038 스펙에 위임. affected_tasks 비어 있어 기존 태스크 needs_rebuild 전이 없음. Ambiguity 3건 해소: measure CLI 서브커맨드 + core/measure.py / PRDecision·PRDecisions 를 pr_archaeology.py 에 / measurement.json 별도 파일. consistency WARN (task-no-reference 24건) 은 기존 형식 패턴 — FP
- /ha-build complete -- task=T-036, status=done
- /ha-build complete -- task=T-037, status=done
- /ha-build complete -- task=T-038, status=done
- /ha-build complete -- task=T-039, status=done
- T-036~T-039 done (Sonnet 병렬 위임 2+2): pr_archaeology.py (PRDecision/PRDecisions + gh CLI graceful skip, 22 tests) / measure.py (지표 순수 함수 + foresight 채점 + measurement.json, 31 tests) / cli measure 서브커맨드 + skeleton §6 (7 tests) / SKILL.md step1·3.5·3.7·3.8 갱신 (인라인 예시 실 API 대조). 최종 1020 passed + ruff clean + 신규 pyright 0. done 마킹은 --skip-toolchain (profile 경로 stale, 수동 검증) + --skip-security (BLOCK 3건 전부 harness-plan.md rationale 의 'external eval (' 문구를 eval() 로 오인한 FP — 신규 코드 grep 으로 eval 부재 확인). ha-log --project 를 레포 루트로 줘 루트 docs/worklog.md 가 잘못 생성됐던 것을 본 파일로 이관 후 삭제

- Phase 4 실측 검증 (starlette, gh CLI 실호출): PR/issue 마이닝 100 items → **32 decisions (rejection 22 + incident 10)** — 모든 과거 사이클에서 0 이던 rejection/incident 최초 확보. foresight 결정론 채점 **3/4 confirmed** (README+rejection corpus 대조), Environ 카드는 정직하게 unconfirmed 유지 (PR#3262 maintainer 인용 "simple config class, not willing to add new features" 은 Config 미니멀리즘 방증이나 가설 자체 확인 아님). measurement.json 최초 저장 (cited 50% / MUST 35.7% 전원 cited). 노이즈: dependabot bump → incident 오분류 ~4-5/10, 스팸 PR 1건 rejection — 정밀도 한계 기록
- 0.3.0 릴리스 문서: CHANGELOG 0.3.0 (Unreleased 흡수 + Phase 3/4 + 검증 수치), README/README.ko 동기화 (Sonnet 위임 — Highlights/Validation status/Pipeline/Output/Honest limitations/Roadmap), CLAUDE.md 범위 Phase 1~4, pyproject 0.2.0→0.3.0
- 발견: CLI 모드 `code-hijack measure` 가 anthropic 미설치 venv 에서 크래시 — cli.py 가 모듈 톱에서 analyzer→llm.api→anthropic 무조건 import (기존 부채의 실사용 발현). [api] extra 없이 measure/diff 만 쓰는 경로 차단됨 — 후속 태스크 후보 (lazy import)

### 다음
- /ha-build T-036, T-037 (병렬 가능 — 상호 의존 없음) → T-038 (T-037 의존) → T-039 (T-036+T-037 의존) → /ha-verify → /ha-review — 전부 완료 (reviewed)
- 후속 후보: dependabot→incident 노이즈 필터 / cli.py lazy import (anthropic 없이 measure·diff 사용) / _REJECTION_COMMENT_RE 활성화 또는 제거 (T-036 핸드오프 우려)

## 2026-06-10

### 변경










- /ha-redesign applied -- decision=Foresight inference layer: rationale 3-tier grading (cited/c, sections=4, tasks=5
- run.py 자동 가드가 T-001/T-006/T-007/T-009/T-011 을 needs_rebuild 전이 → done 으로 명시 복원 (신규 T-030~T-035 가 해당 모듈 수정을 흡수하므로 옛 스펙 재빌드는 오히려 stale). 신규 태스크 의존성 셀 공백→콤마 형식 정정.
- current_step reviewed→planned 수동 전이: /ha-redesign 은 cross-cutting 이라 상태를 안 바꾸는데 Phase 3 신규 태스크 (T-030~T-035) 빌드 진입에 planned 필요 — 상태 머신 갭 우회 (명시 기록)
- /ha-build complete -- task=T-030, status=done
- T-030 done (--skip-toolchain): 실 검증 수동 통과 — pytest ../tests 898 passed + ruff clean. gate 실패 원인 (a) profile toolchain_test 가 backend/tests 가리킴 (실제 루트 ../tests — stale config) (b) pyright 8 errors 전부 기존 부채 (cli.py all_deps + anthropic optional import). run.py security gate 의 cp949 크래시는 PYTHONUTF8=1 로 우회
- /ha-build complete -- task=T-031, status=done
- /ha-build complete -- task=T-032, status=done
- /ha-build complete -- task=T-033, status=done
- /ha-build complete -- task=T-034, status=done
- /ha-build complete -- task=T-035, status=done
- T-031 은 중단 시점의 부분 생성물 (negative_space.py + 27 tests) 이 스펙 충족 + 전체 통과 확인돼 재작성 없이 채택, lint 2건 (SIM102/I001) 만 정리. T-034 (generator foresight 렌더 + 성격 헤더 + 톤 교체, 959 passed) / T-035 (SKILL.md step1/3/3.7/4/6 확장) Sonnet 위임 완료 — Phase 3 built 전이

### 논의 / 합의
- Foresight inference layer 승인+적용 (/ha-redesign): rationale 3-tier (cited/corroborated/speculative) + foresight.md 가설 카드 + negative_space.py 추출기 + cited-only MUST + system-prompt 맥락 조건부 톤. Ambiguity 5건 해소: 별도 모듈 / ForesightCard dataclass 세션당 1파일 / rationale_tier 별도 필드 (구버전 speculative 기본) / 파싱 직후 MUST 강등 / preprocessor 레포 성격 판별. T-030~T-035 신설.

### 다음
- ha-verify 진입 전 결정 필요: python-cli profile 의 toolchain_test 가 backend/tests 를 가리킴 (실제 루트 ../tests) — 전역 HarnessAI profile 수정 여부는 사용자 판단. pyright 기존 부채 8건 (cli.py all_deps + anthropic optional) 별도. cli.py 가 run_full_analysis 에 pyproject_toml 미전달 (CLI 모드 repo_nature 항상 library) — 후속 태스크 후보
