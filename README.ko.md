# code-hijack

> 시니어 코드베이스를 LLM 으로 분석해 AI 에이전트용 코딩 규칙을 자동 추출하는 CLI 도구.

**English README**: [README.md](README.md)

AI 에이전트가 짜는 코드는 일반적이고 일관성 없다. code-hijack 은 탑 티어 시니어 레포의 **"왜 이렇게 짰는지"** 설계 의도까지 담은 규칙 문서 (`CLAUDE.md` + 레이어별 `.md` + `system-prompt.md`) 를 생성해 에이전트가 그 스타일로 코딩하게 만든다.

## 주요 특징

태그: ✅ 정량 검증됨, ⚠️ 부분 작동/한계 있음, ❓ 구현 됨 — 측정 데이터 아직 없음. [검증 현황](#검증-현황) 섹션에 cycle data.

- ✅ **10 카테고리 분석** — architecture, coding_style, api_design, testing, dependencies, security, performance, devops, state_management, data_model. (3+1 카테고리 starlette 에서 매칭 검증, 나머지 6 구현되어 있고 dogfooding 대기.)
- ✅ **5 레이어 결정론적 분류** — frontend / backend / db / devops / shared (경로/확장자/의존성, LLM 추측 없음). 분류 회귀 발견 후 fix (e117c4c).
- ⚠️ **실증적 규칙** — 각 규칙에 `ref_files:라인번호` + ✅/❌ 실제 코드 + 신뢰도/우선순위. **Evidence chain (verbatim commit 인용) 천장: 시니어 OSS (starlette) 38%, 일반 사용자 repo (HarnessAI 같은 짧은 commit) ~0%**. evidence 있는 rule 과 없는 rule 의 quality 격차 ~2x (외부 reviewer 측정).
- ❓ **Scope 태깅** — 모든 규칙이 `cross_project` / `framework_internal` / `domain_specific` 으로 분류. 다운스트림 도구가 안전한 것만 자동 적용. (코드 있음 — 다운스트림 실사용 데이터 아직 없음.)
- ✅ **Critic 레이어** — 2차 LLM 패스로 중복 제거 + MUST 인플레 강등 + scope 태깅. 추가 mechanical 가드: MUST 비율 자동 lint (`write_output` 시점 stderr 경고, >40%), **R6 자동 강등** (verified citation 없는 MUST → SHOULD).
- ✅ **2가지 실행 모드**:
  - **CLI 모드** (`code-hijack analyze`) — Anthropic API 직접 호출, 자동화 가능
  - **Skill 모드** (`/code-hijack`) — Claude Code 세션이 LLM 역할, API key 불필요
- ❓ **HarnessAI 통합** — `harness-export` 서브커맨드로 세션을 [HarnessAI](https://github.com/reasonableplan/harnessai) 형식 으로 변환. `cross_project` 규칙만 자동 적용. (구현됨; 다운스트림 HarnessAI 소비 dogfooding 미완.)
- ❓ **세션 관리** — `--resume` 재시작, `diff` 세션 간 비교. (구현됨; 사용 데이터 부족.)
- ⚠️ **Git 결정 마이닝** — PR description, 리뷰 코멘트, commit body, revert 에서 시니어 판단 흔적 추출. rule `evidence` 필드 verbatim 인용 + intent 분류 (rejection/constraint/incident/preference). **decision-pattern 키워드 ("instead of", "rather than" 등) 가 commit 에 있을 때만 작동; 일반 바쁜 개발자 repo 에선 거의 0.**
- ❓ **스타일 exemplar + 통계 fingerprint** — 규칙 외 구체 코드 sample + 통계 (테스트 프레임워크/네이밍/라인 길이/...). (`core/exemplars.py` + `core/style_fingerprint.py` 코드 있음 — rule-only 출력 대비 ROI 측정 안 됨.)
- ✅ **Persistent 레포 캐시** — `~/.cache/code-hijack/repos/<hash>/` 자동 캐시 (327fb1a).

## 검증 현황

2026-05-06 측정 사이클 — `encode/httpx`, `encode/starlette`, 사용자 본인 활성 repo dogfooding. 자세한 chain 은 `memory/project_validation_findings.md` 참조.

| 측정 항목 | 데이터 | Source |
|---|---|---|
| Evidence-chain 매칭율 (시니어 OSS, best case) | **38%** (starlette, 4 카테고리, depth=30) | v10 session |
| 일반 개발자 repo 매칭율 | **~0%** (HarnessAI: 1 decision-signal commit / 61 scanned) | dogfood-harnessai session |
| 외부 reviewer score (clean LLM session) | **6/10 사용자 학습, 5/10 AI 코드 가이드** | C external eval |
| Evidence vs no-evidence 규칙 quality 격차 | **~2x** (외부 reviewer 정성 평가) | C external eval |
| MUST 캘리브레이션 target | overall 30–40%, 카테고리당 ≤50% | `_check_must_calibration` |
| R6 자동 강등 효과 | starlette MUST 58%→25%, 살아남은 MUST 모두 cited | v8 vs v7 |
| Decision pattern 키워드 (현재) | 18개 (`instead of`, `rather than`, `to avoid`, `to prevent`, `due to`, `motivated by`, `as opposed to`, `regression` 등) | `archaeology._DECISION_PATTERNS` |

**정직한 평가**: 도구 차별점 (verbatim 인용 evidence chain) 은 **잘 정돈된 시니어 OSS** (PR-style commit body 풍부) 에서 광고대로 작동. 일반 짧은-commit repo 에선 "rule + ✅/❌ example" extractor 로 degrade — 여전히 유용하지만 일반 LLM rule miner 와 차이 없음. 천장 올리기 후보로 **R7** (commit corpus → rule 역도출) 과 **G** (카테고리 확장) 탐색 중. **D dogfooding** 이 현재 quality 가 진짜 사용자에게 "충분" 한지 답할 다음 데이터.

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

## 설정

환경 변수:

- `HIJACK_CACHE_DIR=/path` — 캐시 위치 지정 (기본값: `~/.cache/code-hijack/repos/`)
- `HIJACK_NO_CACHE=1` — 캐시 비활성화, 실행마다 `tempfile.mkdtemp` 사용 (`0`/`false`/빈 값으로 재활성화)
- `ANTHROPIC_API_KEY` — CLI 모드 (`code-hijack analyze`) 에 필수, skill 모드는 불필요
- `GH_TOKEN` — 선택, `gh` CLI 없을 때 PR 결정 마이닝에 사용

MUST 비율 캘리브레이션은 `write_output` 시점에 자동 실행되며, 전체 MUST > 40% 또는 카테고리별 > 50% 일 때 stderr 에 `[WARN]` 출력. 전체 규칙 5개 미만 또는 카테고리 3개 미만은 noise 방지를 위해 건너뜀.

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
  ↓ Fetcher        — git clone + persistent cache (`~/.cache/code-hijack/repos/<hash>/`)
  ↓ detect_layer   — 결정론적 레이어 태깅
  ↓ Preprocessor   — 역할 분류 + 카테고리별 파일 선별
                     (auxiliary path 강등, truncate-aware 정렬, near-dup dedup)
  ↓ Exemplars (G1) — 카테고리별 구체 코드 sample 추출
  ↓ Style FP (G2)  — 통계 스타일 fingerprint (프레임워크, 네이밍, 라인 길이)
  ↓ Test decisions (B) — 테스트 코드에서 시니어 방어 카탈로그 (parametrize edges, raises blocks)
  ↓ PR decisions (A1)  — GitHub PR 신호 (어휘, 주요 PR, 거절된 PR, 레이블)
  ↓ Commit decisions (C) — commit body 에서 결정 흔적 (tried/decided/instead/reverted)
  ↓ Analyzer       — evidence 프롬프트 포함 카테고리별 LLM 호출
  ↓ Critic         — 중복 제거 + MUST 강등 + scope 태깅
  ↓ Generator      — 레이어별 .md + CLAUDE.md + system-prompt.md 렌더링
                     + MUST 자동 캘리브레이션 lint (>40% 시 stderr 경고)
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

**Skill 모드 검증** (2026-05-05 selector / cargo-cult / MUST-lint / cache 수정 후):

| 레포 | 전체 규칙 | MUST% | 카고컬트* | 품질 |
|---|---|---|---|---|
| httpx (v1) | 18 | 39% | 4 | 8/10 |
| httpx (v2) | 19 | **32%** | **0** | **9/10** |
| fastapi (v1) | 18 | 44% | 5 | 7/10 |
| fastapi (v2) | 17 | **35%** | **0** | **8/10** |

\* 규칙 본문이 설계 원칙 대신 분석 레포의 내부 클래스/함수명 (예: `BaseTransport`, `USE_CLIENT_DEFAULT`, `EventSourceResponse`) 을 처방한 경우. v2 프롬프트는 원칙 레벨 규칙 본문을 요구하고 내부 심볼은 `good_example` 에만 인용.

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
      fetcher.py                       # git clone + cache, 파일 수집, detect_layer
      preprocessor.py                  # 역할 분류, 파일 선별 (auxiliary 강등, truncate-aware)
      prompts.py                       # 10 카테고리 프롬프트 + few-shot + cargo-cult 가드
      analyzer.py                      # LLM 루프 + 파싱 + 재시도
      critic.py                        # 규칙 정제 (drop / downgrade / scope-tag)
      scope_critic.py                  # scope 태깅 정제
      session.py                       # session_id, SessionDiff
      generator.py                     # 렌더링 + MUST 캘리브레이션 lint
      harness_export.py                # HarnessAI conventions/guidelines/lesson-candidate 어댑터
      archaeology.py                   # git 히스토리 마이닝 (파일 나이, revert, commit body)
      apply.py                         # integrated CLAUDE.md 렌더링
      docs.py                          # 레포 문서 수집 (README/ARCHITECTURE/ADR)
      evidence.py                      # evidence chain 렌더링 + 지표
      exemplars.py                     # G1: 시니어 코드 sample 카탈로그
      style_fingerprint.py             # G2: 통계 스타일 fingerprint
      test_decisions.py                # B: 테스트 코드에서 시니어 방어 카탈로그
      pr_decisions.py                  # A1: GitHub PR 판단 신호
      target_stack.py                  # 대상 레포 스택 감지
    llm/
      base.py                          # BaseLLM ABC
      api.py                           # ClaudeAPIClient (anthropic SDK)
tests/                                 # pytest — 783 tests, ruff clean
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

완화된 갭 (2026-04-17 이후): Git 히스토리 + PR 토론 마이닝이 구현됨 (exemplars, style fingerprint, 테스트 방어 카탈로그, PR 신호, commit 결정 흔적). 규칙에 verbatim evidence + intent 분류 포함.

잔존 갭: skill 모드에서 evidence chain 이 비어 있음 (기계적 신호 레이어는 CLI 모드에서만 실행). 해결을 위해 사전 계산된 신호를 skill 모드 프롬프트에 주입하는 "A2 LLM distillation" 작업 중.

## Roadmap

- ✅ **Phase 1 (MVP)** — 3 카테고리 × 5 레이어, CLI + Skill 모드
- ✅ **Phase 2 (확장)** — 10 카테고리, `--resume`, `diff` 서브커맨드, SessionDiff
- ✅ **Phase 3a (품질)** — Few-shot 프롬프트, Critic 레이어, 콘텐츠 밀도 기반 선별
- ✅ **Phase 3b (HarnessAI 통합)** — `scope` 필드 (cross_project / framework_internal / domain_specific), `harness-export` 서브커맨드, system-prompt 에 ✅/❌/ref 인라인
- ✅ **Phase 4a (결정 마이닝)** — Git 히스토리 + PR 토론 + commit body 마이닝. 모듈: `archaeology`, `exemplars` (G1), `style_fingerprint` (G2), `test_decisions` (B), `pr_decisions` (A1), commit 결정 패턴 마이닝 (C).
- ✅ **Phase 4b (검증 강화, 2026-05-05)** — 레이어 감지 false-positive 가드, 파일 selector docs_src 강등 + truncate-aware 정렬, 규칙 추출 cargo-cult 가드, MUST 자동 캘리브레이션 lint, persistent fetch 캐시.
- **Phase 4c (계획)** — A2 LLM distillation (기계적 신호를 skill 모드 프롬프트에 주입해 evidence chain 채우기), ORM-aware 레이어 감지, 언어 확장 (Go/Rust).

## 개발

[CONTRIBUTING.md](CONTRIBUTING.md) 참조.

## 라이선스

MIT — [LICENSE](LICENSE) 참조.

## 배경

harnessai + gstack 워크플로우 (계획 → 구현 → 검증 → 리뷰 루프) 로 개발. 점진적 커밋, 783 passing tests, 4 레포에 도그푸딩 + 품질 진화 기록. Phase 4b 에서 selector 강화, cargo-cult 가드, MUST 자동 캘리브레이션 lint, persistent fetch 캐시 추가. 상세 설계 문서: [`backend/docs/skeleton.md`](backend/docs/skeleton.md).
