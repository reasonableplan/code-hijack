---
harness_version: 2
schema_version: 1
project_name: code-hijack
created_at: '2026-04-17T03:13:41+00:00'
updated_at: '2026-04-17T11:40:01+00:00'
project_type: Python CLI 분석 도구 (개인용)
scale: small
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
  current_step: building
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
backups: []
last_activity: '2026-04-17T11:40:01+00:00'
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
