# code-hijack

> 시니어 코드베이스를 LLM 으로 분석해 AI 에이전트용 코딩 규칙을 자동 추출하는 CLI 도구.

**English README**: [README.md](README.md)

AI 에이전트가 짜는 코드는 일반적이고 일관성 없다. code-hijack 은 탑 티어 시니어 레포의 **"왜 이렇게 짰는지"** 설계 의도까지 담은 규칙 문서 (`CLAUDE.md` + 레이어별 `.md` + `system-prompt.md`) 를 생성해 에이전트가 그 스타일로 코딩하게 만든다.

## 주요 특징

태그: ✅ 정량 검증됨, ⚠️ 부분 작동/한계 있음, ❓ 구현 됨 — 측정 데이터 아직 없음. [검증 현황](#검증-현황) 섹션에 cycle data.

- ✅ **10 카테고리 분석** — architecture, coding_style, api_design, testing, dependencies, security, performance, devops, state_management, data_model. (5 카테고리 starlette v12 까지 매칭 검증, 나머지 5 구현되어 있고 dogfooding 대기.)
- ✅ **5 레이어 결정론적 분류** — frontend / backend / db / devops / shared (경로/확장자/의존성, LLM 추측 없음). 분류 회귀 발견 후 fix (e117c4c).
- ⚠️ **3-tier rationale 등급 + 실증적 규칙** — 각 규칙에 `rationale_tier` 부여: `cited` (시니어 verbatim 증거), `corroborated` (2개 이상 독립 코드 신호), `speculative` (LLM 추론). **cited 규칙만 MUST 가능** — corroborated/speculative 는 파싱 시 기계적으로 SHOULD 강등. Evidence-chain cited 천장: 시니어 OSS (starlette v12, 5 카테고리) 50%, 일반 개발자 repo (HarnessAI) ~0%. evidence 있는 rule 과 없는 rule 의 quality 격차 ~2x (외부 reviewer 측정).
- ❓ **Scope 태깅** — 모든 규칙이 `cross_project` / `framework_internal` / `domain_specific` 으로 분류. 다운스트림 도구가 안전한 것만 자동 적용. (코드 있음 — 다운스트림 실사용 데이터 아직 없음.)
- ✅ **Critic 레이어** — 2차 LLM 패스로 중복 제거 + MUST 인플레 강등 + scope 태깅. 추가 mechanical 가드: MUST 비율 자동 lint (`write_output` 시점 stderr 경고, >40%), **R6 자동 강등** (verified citation 없는 MUST → SHOULD).
- ✅ **Foresight 추론 레이어** — `ForesightCard` 아티팩트 (가설 + 검증 신호 + 반증 조건 + tier) 를 세션별 `foresight.md` 로 렌더링. MUST 절대 불가. 가설은 2개 이상 독립 repo 신호로 삼각 검증. `core/negative_space.py` 가 결정론적 신호 공급 (dep_count, stdlib-only 힌트, public_ratio, deprecation 패턴, 레이어 import 위반).
- ✅ **2가지 실행 모드**:
  - **CLI 모드** (`code-hijack analyze`) — Anthropic API 직접 호출, 자동화 가능
  - **Skill 모드** (`/code-hijack`) — Claude Code 세션이 LLM 역할, API key 불필요
- ❓ **HarnessAI 통합** — `harness-export` 서브커맨드로 세션을 [HarnessAI](https://github.com/reasonableplan/harnessai) 형식 으로 변환. `cross_project` 규칙만 자동 적용. (구현됨; 다운스트림 HarnessAI 소비 dogfooding 미완.)
- ❓ **세션 관리** — `--resume` 재시작, `diff` 세션 간 비교. (구현됨; 사용 데이터 부족.)
- ✅ **PR/이슈 마이닝** — `core/pr_archaeology.py` 가 `gh` CLI 로 closed-unmerged PR (rejection) + wontfix 이슈 + maintainer 코멘트를 채굴. commit 마이닝과 같은 decision-pattern 세트 사용. `gh` 없으면 graceful skip. starlette 최초 비-제로 rejection/incident 신호 달성 (100건 스캔 → 32 decisions: rejection 22, incident 10).
- ⚠️ **Git commit 결정 마이닝** — PR description, 리뷰 코멘트, commit body, revert 에서 시니어 판단 흔적 추출. rule `evidence` 필드 verbatim 인용 + intent 분류 (rejection/constraint/incident/preference). **decision-pattern 키워드 ("instead of", "rather than" 등) 가 commit 에 있을 때만 작동; 일반 바쁜 개발자 repo 에선 거의 0 — PR/이슈 마이닝이 이 격차를 보완.**
- ✅ **측정 루프** — `core/measure.py` + `code-hijack measure` 서브커맨드가 `cited_ratio`, `must_ratio`, tier/intent 분포를 계산해 세션별 `measurement.json` 으로 저장. 향후 개선은 수동 평가 대신 수치로 채점.
- ❓ **스타일 exemplar + 통계 fingerprint** — 규칙 외 구체 코드 sample + 통계 (테스트 프레임워크/네이밍/라인 길이/...). (`core/exemplars.py` + `core/style_fingerprint.py` 코드 있음 — rule-only 출력 대비 ROI 측정 안 됨.)
- ✅ **Persistent 레포 캐시** — `~/.cache/code-hijack/repos/<hash>/` 자동 캐시 (327fb1a).

## 검증 현황

2026-06-11 측정 사이클 — `encode/starlette` (skill 모드). 이전 사이클은 `encode/httpx` + 사용자 활성 repo dogfooding. 자세한 chain 은 `memory/project_validation_findings.md` 참조.

| 측정 항목 | 데이터 | Source |
|---|---|---|
| Evidence-chain cited 율 (시니어 OSS, best case) | **50%** (starlette v12, 5 카테고리: architecture+coding_style+api_design+testing+security+performance, depth=30) | v12 session |
| 일반 개발자 repo cited 율 | **~0%** (HarnessAI: 1 decision-signal commit / 61 scanned) | dogfood-harnessai session |
| 외부 reviewer score (clean LLM session) | **6/10 사용자 학습, 5/10 AI 코드 가이드** | C external eval (v8) |
| Evidence vs no-evidence 규칙 quality 격차 | **~2x** (외부 reviewer 정성 평가) | C external eval |
| MUST 캘리브레이션 target | overall 30–40%, 카테고리당 ≤50% | `_check_must_calibration` |
| R6 자동 강등 효과 | starlette MUST 58%→25%, 살아남은 MUST 모두 cited | v8 vs v7 |
| Decision pattern 키워드 (현재) | 18개 (`instead of`, `rather than`, `to avoid`, `to prevent`, `due to`, `motivated by`, `as opposed to`, `regression` 등) | `archaeology._DECISION_PATTERNS` |
| G 카테고리 확장 ROI (검증) | **+5%p evidence per 카테고리** (testing→38%, security→45%, performance→50%) | v10/v11/v12 chain |
| intent_kind 다양성 — commit 마이닝만 | **rejection/incident: 0** — 시니어 OSS 가 perf/security 결정을 `to avoid`/`as opposed to` (preference) 로 표현, `regression`/`reverted because` (incident) 아님 | v10/v11/v12 + R7 phase 1 |
| intent_kind 다양성 — PR/이슈 마이닝 후 (2026-06-11) | **32 decisions: rejection 22, incident 10** (starlette, 100건 스캔) — 프로젝트 측정 역사상 최초의 비-제로 rejection/incident | 0.3.0 starlette 사이클 |
| 규칙 honesty 등급 (2026-06-11, starlette) | 14개 규칙: cited 7 / corroborated 5 / speculative 2; **MUST 5/14 (35.7%), 전원 cited** | 0.3.0 starlette 사이클 |
| Foresight 정확도 (2026-06-11, starlette) | 4개 카드: **3/4 confirmed** (repo docs + rejection corpus 대조); 1개 미확인 (정직 유지) | 0.3.0 starlette 사이클 |
| 테스트 | **1136 passed** (0.3.0 에서 1020) | 현재 main |
| Downstream A/B — 규칙 주입 3라운드 (2026-07-04) | **규칙이 약한 모델을 구조**: Haiku control 은 시니어가 거절한 버퍼링 안티패턴(PR#1745)에 그대로 빠짐(9/9 청크 전체 버퍼 실측); treatment 은 스트리밍(1/9) + 커밋 인용. frontier(Sonnet)는 규칙 유무 무관 시니어 구조 재현 | 첫 downstream A/B |
| SATD 공급→소비 (W2, 2026-07-05) | typer: 공급 26 → 2 ref 가 1 규칙에 인용 (`satd_citation_ratio` 7.7%, directional). **SATD 가 cited MUST 를 지탱** — 결정 커밋 2개뿐인 squash-merge 레포에서 | typer W2 사이클 |

**정직한 평가**: 도구 차별점 (verbatim 인용 evidence chain) 은 **잘 정돈된 시니어 OSS** (PR-style commit body 풍부) 에서 광고대로 작동. 일반 짧은-commit repo 에선 commit 마이닝만으로는 "rule + ✅/❌ example" extractor 로 degrade; PR/이슈 마이닝이 이슈 트래커가 활성화된 레포에서 이 격차를 보완한다.

방향성 현황 (2026-06-11):
- **G (카테고리 확장)** — 검증 완료: +5%p evidence per 카테고리, starlette 천장 50% 도달. 5 카테고리 이상은 diminishing returns; commit-pool 풍부함이 진짜 lever 임 (카테고리 수 아님).
- **R7 (commit corpus → rule 역도출)** — Phase 1 완료 (`backend/docs/r7_pipeline_reversal.md`). multi-commit cluster (CORS preflight: 3 commits → 1 cluster) 에서 가설 viable, 그러나 **starlette cluster 의 21% 만 multi-commit** — 단일-commit cluster 는 forward pipeline 대비 advantage 없음. Phase 2-4 (LLM derivation + verify + 외부 평가) ungated; hybrid forward+inversion 모드로 갈 가능성.
- **D dogfooding** — ceiling vs good-enough 질문. HarnessAI 에서 2026-05-06 시작 (1주일 horizon); "에이전트가 `.code-hijack/CLAUDE.md` 적용 시 측정 가능한 코드 품질 향상이 있나" 가 결론.

## Positioning (실측 기반, 2026-07)

첫 downstream A/B (2026-07-04) 가 가린 실제 수혜자:

1. **약한/싼 모델이 알려진 안티패턴에서 구조된다.** 규칙 주입 시 Haiku 는 시니어가 명시적으로 거절한 전체-바디 버퍼링을 회피; 규칙 없이는 그대로 빠짐 (자체 rationale 에서 "must accumulate first" 자백). frontier 모델은 규칙 없이도 시니어 구조를 재현 — 이 도구는 frontier 의 correctness 를 사주지 않는다.
2. **사람 학습자가 추적 가능한 WHY-provenance 를 얻는다.** 규칙 주입 세션은 결정 뒤의 특정 커밋/사고를 인용; control 은 출처 없는 일반론. 이 축은 모델 강도와 무관하며, 측정된 이득 중 더 크다 (학습 독자 > 코드품질 독자).

3라운드 A/B (6 태스크, starlette + anyio) 후 정밀화: **규칙은 happy path 가 아니라 오용/경계 경로의 행동을 바꾼다.** 판별된 태스크(거절된 버퍼링 패턴, deprecation 수명주기, 컨텍스트 매니저 재진입 가드)는 전부 경계/오용 처리에서 갈렸다 — 시니어가 사고로 배운 부분. 함정이 상식이거나 자연 회피되는 태스크는 판별하지 못했다. 효율(토큰/턴)은 self-contained 생성 태스크에서 일관된 이득 없음.

R4~R6 (werkzeug + pluggy, 2026-07-05/06) 후 2축 확정:

- **행동 축 — 판별 조건은 '지름길-갭'.** 규칙은 약모델의 기본 구현이 *지름길*일 때만 행동을 바꾼다 (naive `raise` 로 traceback 오염, 비호환 옵션 무증상 수용). 기본이 이미 견고 패턴이거나 함정이 보안 상식이면 규칙은 행동적으로 잉여 — werkzeug(하드닝 규칙, probe 0/3)와 pluggy(지름길-갭 규칙, probe 2/3)가 이 기준을 실측으로 갈랐다. **추출 품질과 행동 판별력은 다른 축이다** (werkzeug 는 cited 94% 인데 probe 최악 표적).
- **효율 축 — 이득은 탐색형 태스크에 한정.** 실존 버그를 레포에서 찾아 고치는 태스크에서 규칙 주입 팔이 툴콜 −67%, 시간 −62% (pluggy #649, N=1 directional) — 2601.20404 의 스코프와 일치. self-contained 생성 태스크에선 규칙 입력 오버헤드(토큰 +20% 안팎)만 남는다.

2026 문헌 대비:

- LLM 이 rationale 을 **생성**하면 precision ~0.27, 오도성 주장 1.6–3.2% ([arxiv 2504.20781](https://arxiv.org/abs/2504.20781)). code-hijack 이 WHY 를 LLM 에게 짓게 하지 않는 이유 — 시니어의 **verbatim** 증거(커밋, 거절 PR, SATD 주석)만 surface 하고, 검증 인용 없는 MUST 는 기계적으로 강등한다. 같은 기준을 자기 headline 지표에도 적용한다: `cited` 는 **시니어 인용** vs **코드 앵커**로 분리 보고 — 코드의 verbatim 관찰은 시니어가 남긴 WHY 가 아니므로 그걸로 세지 않는다.
- 최근접 접근 Probe-and-Refine ([arxiv 2606.20512](https://arxiv.org/abs/2606.20512)) 은 synthetic probe *행동*으로 레포 가이드를 튜닝 (+7.5pp SWE-bench) 하지만 provenance 가 없다 — *무엇이* 되는지는 말해도 *시니어가 왜 그렇게 골랐는지*는 못 말한다. code-hijack 은 이제 둘 다 든다: 기록된 WHY(verbatim evidence) + 규칙 단위 행동 probe 배지 (`behavior-confirmed` — [examples/pluggy](examples/pluggy/) 가 첫 배지 샘플, 3 probed / 2 discriminated).
- 컨텍스트 파일은 동일 완성도에서 에이전트 **비용**을 실측으로 줄인다: runtime −28.6%, 출력 토큰 −16.6% ([arxiv 2601.20404](https://arxiv.org/abs/2601.20404)) — 단 저 논문의 태스크는 레포 탐색형. 자체 A/B 도 같은 스코프에서만 재현 (탐색형 툴콜 −67% vs self-contained 생성 태스크 이득 없음, 위 2축 참조).
- 같은 계열의 2026 재평가([2601.20404v2](https://arxiv.org/html/2601.20404v2), [ETH 연구 보도](https://www.infoq.com/news/2026/03/agents-context-file-value-review/))는 **LLM 이 자동 생성한 컨텍스트 파일이 평균적으로 중복**임을 밝혔다 — 에이전트가 레포에서 같은 정보를 어차피 재발견하므로, 자동 생성 파일은 추론 비용 +20% 에 성공률은 오히려 -3%. **에이전트가 스스로 발견할 수 없는 내용만 효과가 있다.** 그 기준이 정확히 code-hijack 이 추출하는 것이다: 거절된 PR·인시던트·SATD·커밋 rationale 같은 verbatim 결정 이력은 워킹 트리 밖에 있고, 에이전트는 태스크 중에 git/PR 아카이브를 마이닝하지 않는다. 자체 probe 데이터와도 정합 — 발견 가능한 패턴을 재진술한 규칙은 행동적으로 잉여였고, 행동을 바꾼 규칙은 발견 불가능한 인시던트/거절 지식(지름길-갭)을 담고 있었다. 커밋 rationale 추출은 활발한 연구 축이다 (cf. [CoMRAT, arxiv 2506.10986](https://arxiv.org/pdf/2506.10986)).

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

code-hijack measure ./docs/hijacked/2026-04-10_my-repo/session.json
# cited_ratio, must_ratio, tier/intent 분포 계산 → measurement.json
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
│   ├── architecture.md         # 카테고리별 규칙 (rule + ✅/❌ + scope + reason + rationale_tier)
│   ├── coding_style.md
│   ├── api_design.md
│   ├── foresight.md            # 추론된 설계 가설 (가설 + 신호 + 반증 조건 + tier); MUST 절대 불가
│   ├── measurement.json        # cited_ratio, must_ratio, tier/intent 분포 (세션별)
│   └── session.json            # 구조화 데이터 (diff / harness-export / measure 재사용)
├── integrated/                 # 통합 — AI 에이전트용
│   ├── CLAUDE.md               # 진입점 + 레이어 가이드 + Top MUST 규칙
│   ├── backend.md              # backend 레이어 규칙 (카테고리별 모음)
│   ├── frontend.md
│   ├── database.md
│   ├── devops.md
│   ├── shared.md               # 레이어 무관 공통 규칙
│   ├── foresight.md            # 카테고리 전체 통합 foresight 카드
│   └── system-prompt.md        # 에이전트 시스템 프롬프트 (rule + ✅/❌/ref 인라인; 컨텍스트 조건부 톤)
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
  ↓ repo_nature    — library / app / app-cli 감지 (system-prompt 톤 결정)
  ↓ Preprocessor   — 역할 분류 + 카테고리별 파일 선별
                     (auxiliary path 강등, barrel 강등, truncate-aware 정렬, near-dup dedup)
  ↓ Negative space — 결정론적 신호 (dep_count, stdlib 힌트, public_ratio, deprecation 패턴)
  ↓ Exemplars (G1) — 카테고리별 구체 코드 sample 추출
  ↓ Style FP (G2)  — 통계 스타일 fingerprint (프레임워크, 네이밍, 라인 길이)
  ↓ Test decisions (B)   — 테스트 코드에서 시니어 방어 카탈로그 (parametrize edges, raises blocks)
  ↓ PR/이슈 마이닝       — closed-unmerged PR (rejection) + wontfix 이슈 + maintainer 코멘트
                           gh CLI 사용; gh 없으면 graceful skip (core/pr_archaeology.py)
  ↓ Commit decisions (C) — commit body 에서 결정 흔적 (tried/decided/instead/reverted)
  ↓ Analyzer       — evidence 프롬프트 포함 카테고리별 LLM 호출
                     + rationale_tier 부여 (cited/corroborated/speculative)
                     + corroborated/speculative MUST → 파싱 시 SHOULD 강등
  ↓ Foresight      — ForesightCard 생성 (가설 + 삼각 검증 신호 + 반증 조건)
                     + 결정론적 foresight 채점 → foresight.md 렌더링
  ↓ Critic         — 중복 제거 + MUST 강등 + scope 태깅
  ↓ Generator      — 레이어별 .md + CLAUDE.md + system-prompt.md + foresight.md 렌더링
                     + MUST 자동 캘리브레이션 lint (>40% 시 stderr 경고)
  ↓ Measure        — measurement.json (cited_ratio, must_ratio, tier/intent 분포)
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
      pr_archaeology.py                # PR/이슈 마이닝 via gh CLI (rejection + wontfix + maintainer 코멘트)
      negative_space.py                # 결정론적 negative-space 신호 (dep_count, public_ratio 등)
      measure.py                       # calc_session_metrics / diff_sessions / score_foresight / write_measurement
      target_stack.py                  # 대상 레포 스택 감지
    llm/
      base.py                          # BaseLLM ABC
      api.py                           # ClaudeAPIClient (anthropic SDK)
tests/                                 # pytest — 1136 tests, ruff clean
  fixtures/senior_wisdom/              # 레이어 감지 검증용 미니 레포
examples/                              # 실제 분석 출력 (pluggy / werkzeug / starlette / fastapi)
```

## 정직한 한계

본 도구는 **"중급-시니어급 일관된 코드"** 를 만든다 — **"시니어 수준 설계 판단"** 은 아니다.

- ✅ 표면 패턴 일관성 (에이전트가 같은 관용구를 따름)
- ✅ 기본적인 정확성 (HTTP 시맨틱, RFC 준수)
- ❌ 새로운 상황에서의 설계 판단
- ❌ 컨텍스트별 예외에 대한 trade-off 추론

완화된 갭 (2026-04-17 이후): Git 히스토리 + PR 토론 마이닝이 구현됨 (exemplars, style fingerprint, 테스트 방어 카탈로그, PR 신호, commit 결정 흔적). 규칙에 verbatim evidence + intent 분류 포함.

Skill 모드 evidence 채워짐 (2026-05-06 close): A2.1 가 `commit_decisions` 를 skill 모드 프롬프트에 주입 → skill 모드 실행도 CLI 모드와 같은 evidence chain 생성. starlette v3→v12 cycle 에서 매칭율 17%→50% 검증됨.

PR/이슈 마이닝 (0.3.0): `pr_archaeology.py` 가 commit 마이닝만으로는 도달할 수 없던 rejection/incident 신호를 발굴. **알려진 노이즈**: dependabot bump 가 incident 로 오분류 (~starlette incident 10건 중 4-5건); 스팸 PR 1건이 rejection 으로 분류. 마이닝 정밀도 불완전 — rejection/incident 수치는 방향성 지표로 해석할 것.

`score_foresight` 키워드 매칭 한계: 4자 미만 토큰은 매칭하지 않으므로 짧은 연산자/심볼명이 확인 신호로 등록되지 않을 수 있음. 매우 짧은 식별자가 포함된 foresight 카드는 근거가 있어도 `speculative` 로 남을 수 있음.

잔존 갭: **incident-kind evidence** (외부 reviewer 가 hallucination 방지에 가장 가치 있다 평가한 종류) 가 PR/이슈 마이닝으로 부분 해소됐으나 dependabot 노이즈가 정밀도를 낮춤. 추가 해결: (a) cross-repo CVE-DB 식 reference 마이닝, 또는 (b) post-mortem 풍부한 다른 부류 repo (인프라 프로젝트 등).

## Roadmap

- ✅ **Phase 1 (MVP)** — 3 카테고리 × 5 레이어, CLI + Skill 모드
- ✅ **Phase 2 (확장)** — 10 카테고리, `--resume`, `diff` 서브커맨드, SessionDiff
- ✅ **Phase 3a (품질)** — Few-shot 프롬프트, Critic 레이어, 콘텐츠 밀도 기반 선별
- ✅ **Phase 3b (HarnessAI 통합)** — `scope` 필드 (cross_project / framework_internal / domain_specific), `harness-export` 서브커맨드, system-prompt 에 ✅/❌/ref 인라인
- ✅ **Phase 4a (결정 마이닝)** — Git 히스토리 + PR 토론 + commit body 마이닝. 모듈: `archaeology`, `exemplars` (G1), `style_fingerprint` (G2), `test_decisions` (B), `pr_decisions` (A1), commit 결정 패턴 마이닝 (C).
- ✅ **Phase 4b (검증 강화, 2026-05-05)** — 레이어 감지 false-positive 가드, 파일 selector docs_src 강등 + truncate-aware 정렬, 규칙 추출 cargo-cult 가드, MUST 자동 캘리브레이션 lint, persistent fetch 캐시.
- ✅ **Phase 4c (skill-mode parity + calibration, 2026-05-06)** — A2.1 commit_decisions 주입 (skill 모드 evidence chain 이 CLI 모드와 동등), R6 speculative MUST 자동 강등, E1 body excerpt 800 chars, D pattern set 6→18, G7 cited-MUST self-check 가이드, G8 feature-doc noise 필터, G9 top-level dotted-py demote.
- ✅ **Phase 3 foresight + Phase 4 evidence 확장 (0.3.0, 2026-06-11)** — 3-tier rationale 등급 (cited/corroborated/speculative), 파싱 시 cited-only MUST 기계적 강제, ForesightCard + foresight.md, `core/negative_space.py` 결정론적 신호, `repo_nature` 감지 (library/app/app-cli), gh CLI PR/이슈 마이닝 (`core/pr_archaeology.py`: 프로젝트 최초 비-제로 rejection/incident 신호), 측정 루프 (`core/measure.py` + `code-hijack measure` 서브커맨드, measurement.json). 1020 테스트.
- **Phase 5a (계획)** — R7 phase 2-4 (commit-corpus-first rule 역도출, hybrid forward+inversion 모드).
- **Phase 5b (계획)** — ORM-aware 레이어 감지, 언어 확장 (Go/Rust), incident-kind cross-repo reference 마이닝 (dependabot 노이즈 필터 포함).

## 개발

[CONTRIBUTING.md](CONTRIBUTING.md) 참조.

## 라이선스

MIT — [LICENSE](LICENSE) 참조.

## 배경

harnessai + gstack 워크플로우 (계획 → 구현 → 검증 → 리뷰 루프) 로 개발. 점진적 커밋, 1136 passing tests, 5 레포에 도그푸딩 + 품질 진화 기록 (httpx, fastapi, starlette OSS + HarnessAI + code-hijack self). Phase 4b 에서 selector 강화, cargo-cult 가드, MUST 자동 캘리브레이션 lint, persistent fetch 캐시 추가. Phase 4c (2026-05-06) 가 카테고리 확장 + skill-mode parity 로 starlette evidence-chain 매칭율을 17% → 50% 로 끌어올림. 0.3.0 (2026-06-11) 에서 foresight 추론 레이어, 3-tier rationale 등급 + cited-only MUST 기계적 강제, PR/이슈 마이닝 (최초 비-제로 rejection/incident), 수치 측정 루프 추가. 상세 설계 문서: [`backend/docs/skeleton.md`](backend/docs/skeleton.md), [`backend/docs/r7_pipeline_reversal.md`](backend/docs/r7_pipeline_reversal.md).
