---
harness_version: 2
schema_version: 1
project_name: code-hijack
created_at: '2026-04-17T03:13:41+00:00'
updated_at: '2026-06-11T00:12:57+00:00'
project_type: Python CLI 분석 도구 (개인용)
scale: small
scale_axes:
  user_scale: small
  data_sensitivity: none
  team_size: solo
  availability: standard
  monetization: none
  lifecycle: mvp
user_description_original: 시니어 코드베이스를 LLM으로 분석해 AI 에이전트용 코딩 규칙 자동 추출 도구
profiles:
- id: python-cli
  path: backend/
  status: confirmed
skeleton_sections:
  required:
  - overview
  - stack
  - errors
  - interface.cli
  - core.logic
  - tasks
  - notes
  optional:
  - requirements
  - configuration
  - persistence
  - integrations
  included:
  - overview
  - requirements
  - stack
  - configuration
  - errors
  - interface.cli
  - core.logic
  - integrations
  - tasks
  - notes
pipeline:
  steps:
  - ha-init
  - ha-design
  - ha-plan
  - ha-build
  - ha-verify
  - ha-review
  current_step: reviewed
  completed_steps:
  - ha-design
  - ha-plan
  - ha-build:T-001
  - ha-build:T-002
  - ha-build:T-003
  - ha-build:T-004
  - ha-build:T-006
  - ha-build:T-008
  - ha-build:T-005
  - ha-build:T-007
  - ha-build:T-009
  - ha-build:T-010
  - ha-build:T-011
  - ha-build:T-020
  - ha-build:T-021
  - ha-build:T-022
  - ha-build:all-done
  - ha-verify
  - ha-review
  - ha-build:T-030
  - ha-build:T-031
  - ha-build:T-032
  - ha-build:T-033
  - ha-build:T-034
  skipped_steps: []
  gstack_mode: manual
verify_history:
- step: ha-verify
  at: '2026-04-17T11:38:37+00:00'
  passed: true
  summary: pytest 127 passed, ruff clean (13 issues auto-fixed), pyright skipped (not
    installed)
- step: ha-review
  at: '2026-04-17T11:40:01+00:00'
  passed: true
  summary: Phase 1 MVP clean — 0 BLOCK, 1 WARN (skeleton.md TODO 가짜 양성), 4 권장사항 (OUTPUT_001/ctx
    미사용/build_layer_stats dead/진행표시)
- step: ha-verify
  at: '2026-04-17T11:59:11+00:00'
  passed: true
  summary: pytest 169 passed, ruff clean, pyright skipped (not installed) — Phase
    2 all tasks done
- step: ha-review
  at: '2026-04-17T12:00:33+00:00'
  passed: true
  summary: Phase 2 clean — 0 BLOCK, 0 WARN (source). 4 non-blocking 권장 (tests lint
    out-of-scope, MVP 상수 중복, diff 에러 래핑, 진행표시 [2/4] 지속 미반영)
- step: ha-verify
  at: '2026-06-11T00:11:11+00:00'
  passed: true
  summary: 'pytest 959 passed (root ../tests — profile test_dir_warning 우회), ruff
    clean, pyright: Phase 3 신규 코드 0 errors (negative_space.py 빈 tuple 가드 1건 이번에 수정).
    잔존 8 errors 는 전부 4월 코드 부채 (cli.py 7: TargetStack 어노테이션/all_deps, llm/api.py 1:
    anthropic optional import) — 4월 verify 는 pyright skipped 였고 이번에 처음 실행됨. 후속 정리
    후보'
- step: ha-review
  at: '2026-06-11T00:12:57+00:00'
  passed: true
  summary: 'Phase 3 (Foresight layer) clean — 0 BLOCK. WARN 28건 중 TRUE 1건: test-distribution
    (test_llm.py 3개 vs test_generator.py 86개 — 4월부터 존재, Phase 3 비관여). FP 27건: dependency-check
    25 (자기 패키지 hijack + stdlib 오인), print 3 (SKILL.md 인라인 스크립트 예시 — skill 모드 설계상 print
    가 출력 채널). LESSON-018/019/020 위반 없음 (negative_space subprocess 는 분류된 경고 + graceful
    skip)'
redesign_history:
- at: '2026-06-10T12:17:58+00:00'
  decision: 'Foresight inference layer: rationale 3-tier grading (cited/corroborated/speculative)
    + separate foresight.md hypothesis-card artifact + deterministic negative-space
    signal extractor; inferred foresight never MUST (cited-only MUST); system-prompt
    tone from non-negotiable to context-conditional'
  rationale: 'User feedback 2026-06-10: tool does not capture WHY senior wrote code
    that way, misses foresight (negative space), and over-coerces. Must work without
    senior available — LLM infers hypotheses, honestly graded, triangulated against
    repo signals. Validation data supports: intent_kind diversity win 0, external
    eval 5-6/10, HarnessAI commits=1 evidence ~0.'
  affected_sections: []
  affected_tasks: []
  status: proposed
- at: '2026-06-10T12:21:08+00:00'
  decision: 'Foresight inference layer: rationale 3-tier grading (cited/corroborated/speculative)
    + separate foresight.md hypothesis-card artifact + deterministic negative-space
    signal extractor; inferred foresight never MUST (cited-only MUST); system-prompt
    tone from non-negotiable to context-conditional'
  rationale: 'User feedback 2026-06-10: tool does not capture WHY senior wrote code
    that way, misses foresight (negative space), and over-coerces. Must work without
    senior available — LLM infers hypotheses, honestly graded, triangulated against
    repo signals. Validation data supports: intent_kind diversity win 0, external
    eval 5-6/10, HarnessAI commits=1 evidence ~0.'
  affected_sections:
  - §2
  - §7
  - §9
  - §10
  affected_tasks:
  - T-001
  - T-006
  - T-007
  - T-009
  - T-011
  status: approved
- at: '2026-06-10T12:28:06+00:00'
  decision: 'Foresight inference layer: rationale 3-tier grading (cited/corroborated/speculative)
    + separate foresight.md hypothesis-card artifact + deterministic negative-space
    signal extractor; inferred foresight never MUST (cited-only MUST); system-prompt
    tone from non-negotiable to context-conditional'
  rationale: 'User feedback 2026-06-10: tool does not capture WHY senior wrote code
    that way, misses foresight (negative space), and over-coerces. Must work without
    senior available — LLM infers hypotheses, honestly graded, triangulated against
    repo signals. Validation data supports: intent_kind diversity win 0, external
    eval 5-6/10, HarnessAI commits=1 evidence ~0.'
  affected_sections:
  - §2
  - §7
  - §9
  - §10
  affected_tasks:
  - T-001
  - T-006
  - T-007
  - T-009
  - T-011
  status: applied
backups: []
last_activity: '2026-06-11T00:12:57+00:00'
skeleton_hash: 9a1b54b2545eed458428b1bfb3adfa9e71290388fd0489d2c960bd2082252a72
section_hashes:
  configuration: b7d93666130ac209492d148947f10bb495f9250db1ece273b6282737ed972430
  core.logic: 2d7f6b040f661ea7a5c93ece446b8c4ee20d1666964a816cf345a016ae4655fe
  errors: 90bb84f912b90a84b7f0121f33430b1fbfde71a55453dd2f428bcaa7536668c7
  integrations: 2f61eea7f498d39fa178b8c394125cbec0845ef0c73c59b39fc06e06b6058a91
  interface.cli: 591cc8c586fe79ca11fdfecc3c254c52cd2d93c78606d1b07a73cef2b6eba6df
  notes: f800b05cd00134d3d061fcc3dece8db4ff6285cb27915ce703702e493fa370ad
  overview: 4bd7068545b0454951d81e41e55d6b55738ee6dedfb897a548d50231aa51e3a0
  requirements: 81597261ac193dee94948fce8beb1521da3334a4180e6fe7aad31ab866dced69
  stack: 29766c66eb9ae6960aaee80b410fc779257e2f9a6773cf022164c71efc2b1f2a
  tasks: f82b8dc40213b51a6bb121e879295cd3c28d85511d10644152826fd8a27fb64a
---

# code-hijack

## 원본 설명
시니어 코드베이스를 LLM으로 분석해 AI 에이전트용 코딩 규칙 자동 추출 도구

## 판단 근거
- 타입: Python CLI 분석 도구 (개인용)
- 규모: small
- 활성 프로파일: python-cli@backend/

## 다음 단계
- /ha-design — skeleton 채우기
