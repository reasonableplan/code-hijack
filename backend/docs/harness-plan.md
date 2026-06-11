---
harness_version: 2
schema_version: 1
project_name: code-hijack
created_at: '2026-04-17T03:13:41+00:00'
updated_at: '2026-06-11T06:00:40+00:00'
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
  - ha-build:T-036
  - ha-build:T-037
  - ha-build:T-038
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
- step: ha-verify
  at: '2026-06-11T05:58:22+00:00'
  passed: true
  summary: 'Phase 4 (Evidence expansion + measurement): pytest 1020 passed (root ../tests
    — profile test_dir_warning 우회), ruff clean, pyright 신규 코드 (pr_archaeology.py/measure.py/cli
    measure) 0 errors. 잔존 8 errors 는 기존 4월 부채 동일 (cli.py 7 + llm/api.py 1). integrity
    WARN 2건 FP: skeleton <repo> 는 T-008 설명의 세션 ID 패턴 리터럴, hash mismatch 는 T-038 의
    의도된 §6 갱신'
- step: ha-review
  at: '2026-06-11T06:00:40+00:00'
  passed: true
  summary: 'Phase 4 (Evidence expansion + measurement) APPROVE. BLOCK 3건 전부 FP (--allow-block
    사유): command-guard 가 harness-plan.md rationale 산문 ''external eval (matching rate...''
    를 eval() 로 오인 — 신규/변경 코드 전체 grep 으로 eval 부재 확인 (유일 매치는 기존 prompts.py bad_example
    문자열). WARN 16건도 전부 FP: dependency-check 11 (SKILL.md 인라인 예시의 자기 패키지 hijack + stdlib
    pathlib/tomllib), print 5 (SKILL.md skill 모드 출력 채널 설계). TRUE WARN 1건: test-distribution
    test_llm.py 3 vs test_generator.py 86 — 4월부터 존재, Phase 4 비관여 (기존 부채). 신규 subprocess
    (pr_archaeology gh 호출) LESSON-018/019/020 준수 (분류 예외 + logger.warning + graceful
    skip). untracked 신규 모듈은 diff 스캔 누락이라 수동 grep 점검 완료. LESSON-030 pending 추출 (문서
    diff 훅 FP 패턴)'
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
- at: '2026-06-11T00:40:12+00:00'
  decision: 'Evidence source expansion + measurement loop: (1) PR/issue mining via
    gh CLI — closed-unmerged PRs (rejection reasons), wontfix/discussion issues, review
    comments mined with archaeology-style patterns into evidence sources; unlocks
    rejection/incident intent_kind + foresight card cited-promotion path; graceful
    skip without gh. (2) Measurement scripts — codify existing matching-rate methodology
    (session-to-session rule comparison) + foresight card accuracy rate (cross-checked
    against target repo official docs/issue answers) so every future improvement is
    scored numerically.'
  rationale: 'Starlette foresight E2E (2026-06-11) reconfirmed commit-mining ceiling:
    intent_kind diversity 0 (18 commits all preference/constraint, no rejection/incident).
    Rejected PRs and wontfix issues are where senior judgment is densest. Measurement
    loop needed because external eval (matching rate 50%, 5-6/10) remains manual —
    improvements cannot be claimed without numbers.'
  affected_sections: []
  affected_tasks: []
  status: proposed
- at: '2026-06-11T00:45:24+00:00'
  decision: 'Evidence source expansion + measurement loop: (1) PR/issue mining via
    gh CLI — closed-unmerged PRs (rejection reasons), wontfix/discussion issues, review
    comments mined with archaeology-style patterns into evidence sources; unlocks
    rejection/incident intent_kind + foresight card cited-promotion path; graceful
    skip without gh. (2) Measurement scripts — codify existing matching-rate methodology
    (session-to-session rule comparison) + foresight card accuracy rate (cross-checked
    against target repo official docs/issue answers) so every future improvement is
    scored numerically.'
  rationale: 'Starlette foresight E2E (2026-06-11) reconfirmed commit-mining ceiling:
    intent_kind diversity 0 (18 commits all preference/constraint, no rejection/incident).
    Rejected PRs and wontfix issues are where senior judgment is densest. Measurement
    loop needed because external eval (matching rate 50%, 5-6/10) remains manual —
    improvements cannot be claimed without numbers.'
  affected_sections:
  - §2
  - §7
  - §8
  - §9
  - §10
  affected_tasks: []
  status: approved
- at: '2026-06-11T05:41:46+00:00'
  decision: 'Evidence source expansion + measurement loop: (1) PR/issue mining via
    gh CLI — closed-unmerged PRs (rejection reasons), wontfix/discussion issues, review
    comments mined with archaeology-style patterns into evidence sources; unlocks
    rejection/incident intent_kind + foresight card cited-promotion path; graceful
    skip without gh. (2) Measurement scripts — codify existing matching-rate methodology
    (session-to-session rule comparison) + foresight card accuracy rate (cross-checked
    against target repo official docs/issue answers) so every future improvement is
    scored numerically.'
  rationale: 'Starlette foresight E2E (2026-06-11) reconfirmed commit-mining ceiling:
    intent_kind diversity 0 (18 commits all preference/constraint, no rejection/incident).
    Rejected PRs and wontfix issues are where senior judgment is densest. Measurement
    loop needed because external eval (matching rate 50%, 5-6/10) remains manual —
    improvements cannot be claimed without numbers.'
  affected_sections:
  - §2
  - §7
  - §8
  - §9
  - §10
  affected_tasks: []
  status: applied
backups: []
last_activity: '2026-06-11T06:00:40+00:00'
skeleton_hash: 0429d0881b87833f78ee7234914573e6adfe71776214eff488f4faca51d0078c
section_hashes:
  configuration: b7d93666130ac209492d148947f10bb495f9250db1ece273b6282737ed972430
  core.logic: 37228bb3f69bb6c6dcbd9849669644faf7f23cdd15181a1d4a557661cb9d64dd
  errors: 90bb84f912b90a84b7f0121f33430b1fbfde71a55453dd2f428bcaa7536668c7
  integrations: 41b22c52a5438c8db84d3ecee3c02823a77a18d3f27420d9883cec6324df2124
  interface.cli: 654447020ae823865fb0ecedc2e4778f1ece33314620af254776f619c0b63517
  notes: 45f4be5b53c1ee0fef4fde90cd6147544047bf7e756f01af9090c8ed23e94f8e
  overview: 4ad86d218b8e81f1f676358d59d48febd09cdb4a105ba945f22b68f607a60859
  requirements: 5a658e8a17938ed6b01b365f4edb34dbaeee975e5e2de4815145ff3b67bf382c
  stack: 29766c66eb9ae6960aaee80b410fc779257e2f9a6773cf022164c71efc2b1f2a
  tasks: 7c85e30e8e2639b597b62173ce40734c1e08cb24f592b9574a5c89b172ed5be1
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
