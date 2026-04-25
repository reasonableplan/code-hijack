# code-hijack

> 시니어 코드베이스를 LLM 으로 분석해 AI 에이전트용 코딩 규칙을 자동 추출하는 CLI 도구.

**English README**: [README.md](README.md)

AI 에이전트가 짜는 코드는 일반적이고 일관성 없다. code-hijack 은 탑 티어 시니어 레포의 **"왜 이렇게 짰는지"** 설계 의도까지 담은 규칙 문서 (`CLAUDE.md` + 레이어별 `.md` + `system-prompt.md`) 를 생성해 에이전트가 그 스타일로 코딩하게 만든다.

## 주요 특징

- **10 카테고리 분석** — architecture, coding_style, api_design, testing, dependencies, security, performance, devops, state_management, data_model
- **5 레이어 결정론적 분류** — frontend / backend / db / devops / shared (파일 경로/확장자/의존성 기반, LLM 추측 없음)
- **실증적 규칙** — 각 규칙에 `ref_files:라인번호` + ✅/❌ 실제 코드 예시 + 신뢰도 + 우선순위
- **Scope 태깅** — 모든 규칙이 `cross_project` (그대로 적용 가능) / `framework_internal` (소스 코드베이스 내부 결정 — 외부 무관) / `domain_specific` (도메인별 재평가 필요) 중 하나로 분류. 다운스트림 도구가 안전한 것만 자동 적용 가능.
- **Critic 레이어** — 2차 LLM 패스로 중복 제거 + MUST 인플레 강등 + scope 태깅 + 우선순위 보정
- **2가지 실행 모드**:
  - **CLI 모드** (`code-hijack analyze`) — Anthropic API 직접 호출, 자동화 가능
  - **Skill 모드** (`/code-hijack`) — Claude Code 세션이 LLM 역할, API key 불필요
- **HarnessAI 통합** — `harness-export` 서브커맨드로 세션을 [HarnessAI](https://github.com/reasonableplan/harnessai) 형식 (`conventions.md` + 영역별 `guidelines/` + `shared-lessons-candidates.md`) 으로 변환. `cross_project` 규칙만 자동 적용, 나머지는 검토 후보.
- **세션 관리** — `--resume` 으로 재시작, `diff` 서브커맨드로 세션 간 규칙 변경사항 비교

## Quickstart

### 설치
```bash
git clone https://github.com/reasonableplan/code-hijack.git
cd code-hijack/backend
pip install -e ".[dev,api]"
```
Python 3.12+ 필요.

### CLI 모드 (Anthropic API 키 필요)
```bash
export ANTHROPIC_API_KEY=sk-ant-...

code-hijack analyze https://github.com/tiangolo/fastapi
# 기본: 3 MVP 카테고리 (architecture, coding_style, api_design)

code-hijack analyze ./my-repo --categories architecture,security,testing
# 카테고리 지정

code-hijack analyze ./my-repo --dry-run
# 비용 추정만 (LLM 호출 없음)

code-hijack analyze ./my-repo --resume ./docs/hijacked/2026-04-10_my-repo/session.json
# 이전 세션의 완료 카테고리 자동 스킵

code-hijack diff old_session/ new_session/
# 규칙 added/removed/changed 마크다운 출력
```

### Skill 모드 (Claude Code 안에서)
```
/code-hijack https://github.com/tiangolo/fastapi
```
워크플로우는 [`.claude/skills/code-hijack/SKILL.md`](.claude/skills/code-hijack/SKILL.md) 에 정의. Claude Code 세션이 LLM 역할 — 추가 API 비용 없음.

### HarnessAI export (모든 세션)

```bash
# 기존 세션을 HarnessAI conventions/guidelines/lesson-candidate 형식으로 변환
code-hijack harness-export ./docs/hijacked/2026-04-17_fastapi --output ./harness-form
```

산출: `<output>/conventions.md`, `<output>/guidelines/<area>/<aspect>.md`, (있을 때) `<output>/shared-lessons-candidates.md`. 새 프로젝트의 `docs/` 에 복사하면 HarnessAI-식 에이전트가 그대로 사용.

## 출력 구조

```
<target>/docs/hijacked/
├── 2026-04-17_fastapi/         # 세션별 raw 분석
│   ├── meta.md                 # 메타데이터 (세션 ID, 선별 파일, 레이어 분포, scope 분포)
│   ├── architecture.md         # 카테고리별 규칙 (rule + ✅/❌ + scope + reason)
│   ├── coding_style.md
│   ├── api_design.md
│   └── session.json            # 구조화 데이터 (diff / harness-export 재사용)
├── integrated/                 # 통합 — AI 에이전트용
│   ├── CLAUDE.md               # 진입점 + 레이어 가이드 + Top MUST 규칙
│   ├── backend.md              # backend 레이어 규칙 (카테고리별 모음)
│   ├── frontend.md
│   ├── database.md
│   ├── devops.md
│   ├── shared.md               # 레이어 무관 공통 규칙
│   └── system-prompt.md        # 에이전트 시스템 프롬프트 (rule + ✅/❌/ref 인라인)
└── (harness-form/)             # 선택적: harness-export 가 생성
    ├── conventions.md          # HarnessAI 식 결정 표 (cross_project + dependencies)
    ├── guidelines/<area>/*.md  # 영역별 가이드 (✅/❌ + design intent)
    └── shared-lessons-candidates.md  # 안티패턴 + domain-specific 규칙 (검토용)
```

`integrated/CLAUDE.md` 를 해당 프로젝트의 Claude Code 컨텍스트로 복사하면 에이전트가 그 스타일로 코딩. HarnessAI 프로젝트는 `harness-form/` 내용을 `docs/` 에 직접 복사.

## 파이프라인

```
입력 (GitHub URL 또는 로컬 경로)
  ↓ Fetcher        — git clone, .py/.ts/.tsx 수집, _SKIP_DIRS 제외
  ↓ detect_layer   — 결정론적 레이어 태깅 (frontend/backend/db/devops/shared)
  ↓ Preprocessor   — 역할 분류 (entry_point/api/model/...) + 카테고리별 파일 선별
                     (콘텐츠 밀도 정렬, near-duplicate dedup)
  ↓ Analyzer       — BaseLLM 인터페이스 경유 카테고리별 호출
                     (few-shot 프롬프트 + JSON 출력 + regex 폴백, 2회 재시도)
  ↓ Critic         — 2차 LLM 패스: 중복 제거 + MUST 강등 + scope 태깅 (옵션, 기본 on)
  ↓ Generator      — 레이어별 .md + CLAUDE.md + system-prompt.md 렌더링
출력 (docs/hijacked/<세션>/ + integrated/ + 선택적 harness-form/)
```

## 검증

본 도구는 시니어 레포 4개에 대해 도그푸딩 — 프롬프트 엔지니어링으로 품질 향상이 측정됨:

| 버전 | 대상 | MUST% | line# 포함 ref | 실제 코드 bad_example |
|---|---|---|---|---|
| baseline | fastapi | 85% | 0% | 85% |
| +few-shot | fastapi | 57% | 100% | 100% |
| +critic | fastapi | **35%** | **100%** | **100%** |

목표: MUST 30-40% (실제 PR 차단용으로 보정), 100% ref 라인 커버리지, 100% 실제 코드 bad_examples.

## 프로젝트 구조

```
CLAUDE.md                              # 에이전트용 가이드 (요약)
README.md / README.ko.md               # 영어 / 한국어
LICENSE                                # MIT
CONTRIBUTING.md
.github/workflows/test.yml             # CI: pytest + ruff
.claude/skills/code-hijack/SKILL.md    # Skill 모드 워크플로우
backend/
  pyproject.toml                       # setuptools, Python 3.12+
  docs/skeleton.md                     # 상세 설계 문서
  src/hijack/
    cli.py                             # click 그룹 (analyze / diff / harness-export)
    skill.py                           # skill 모드 stub (실 로직은 SKILL.md)
    errors.py                          # HijackError(ClickException) 계층
    core/
      models.py                        # AnalysisRule / CategoryResult / SessionResult @dataclass
      fetcher.py                       # git clone, 파일 수집, detect_layer
      preprocessor.py                  # 역할 분류, 2D 그룹핑, 파일 선별
      prompts.py                       # 10 카테고리 프롬프트 + few-shot 예시
      analyzer.py                      # LLM 루프 + 파싱 + 재시도
      critic.py                        # 2차 패스 정제 (drop / downgrade / scope-tag)
      session.py                       # session_id, SessionDiff
      generator.py                     # 레이어별 .md + CLAUDE.md 렌더링
      harness_export.py                # HarnessAI conventions/guidelines/lesson-candidate 어댑터
    llm/
      base.py                          # BaseLLM ABC
      api.py                           # ClaudeAPIClient (anthropic SDK)
tests/                                 # pytest — 227 tests, ruff clean
  fixtures/senior_wisdom/              # 레이어 감지 검증용 미니 레포
examples/                              # 실제 분석 출력
  fastapi/                             # 최신 fastapi 분석 결과
```

## 정직한 한계

본 도구는 **"중급-시니어급 일관된 코드"** 를 만든다 — **"시니어 수준 설계 판단"** 은 아니다.

- ✅ 표면 패턴 일관성 (에이전트가 같은 관용구를 따름)
- ✅ 기본적인 정확성 (HTTP 시맨틱, RFC 준수)
- ❌ 새로운 상황에서의 설계 판단
- ❌ 컨텍스트별 예외에 대한 trade-off 추론

이 갭을 좁히는 향후 방향: **Git 히스토리 + PR 토론 마이닝** (Phase 4) — 패턴뿐 아니라 그 뒤의 결정까지 추출.

## Roadmap

- ✅ **Phase 1 (MVP)** — 3 카테고리 × 5 레이어, CLI + Skill 모드
- ✅ **Phase 2 (확장)** — 10 카테고리, `--resume`, `diff` 서브커맨드, SessionDiff
- ✅ **Phase 3a (품질)** — Few-shot 프롬프트, Critic 레이어, 콘텐츠 밀도 기반 선별
- ✅ **Phase 3b (HarnessAI 통합)** — `scope` 필드 (cross_project / framework_internal / domain_specific), `harness-export` 서브커맨드, system-prompt 에 ✅/❌/ref 인라인
- **Phase 4 (계획)** — Git 히스토리 마이닝, `design_decisions` 카테고리, RAG 통합

## 개발

[CONTRIBUTING.md](CONTRIBUTING.md) 참조.

## 라이선스

MIT — [LICENSE](LICENSE) 참조.

## 배경

harnessai + gstack 워크플로우 (계획 → 구현 → 검증 → 리뷰 루프) 로 개발. 점진적 커밋, 227 passing tests, 4 레포에 도그푸딩 + 품질 진화 기록. Phase 3b 에서 scope 태그 + `harness-export` 추가로 추출된 스타일을 HarnessAI 프로젝트에 round-trip 가능. 상세 설계 문서: [`backend/docs/skeleton.md`](backend/docs/skeleton.md).
