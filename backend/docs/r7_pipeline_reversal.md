# R7 — Pipeline Reversal (Evidence-First 도구 정체성)

> Status: **Phase 1 + PR-decision 프로브 완료, Phase 2 보류** (2026-07-03). commit 축(21%)·PR 축(4%) 모두 multi-item leverage 미확인 → 풀 inversion 데이터 미지지. 상세는 아래 "PR-decision 프로브 결과".

## Problem (forward pipeline 의 한계)

현재 (v12 기준) 파이프라인은 forward 흐름이다:

```
[1] CATEGORIES (architecture / coding_style / api_design / testing / security / performance / ...)
        ↓
[2] PREPROCESSOR — select files for each category (role/layer 휴리스틱)
        ↓
[3] LLM — read selected files, write rules (principle-level, intent: "good_example/bad_example/reason")
        ↓
[4] MATCHER — for each rule, search commit_decisions for evidence (file overlap → fallback semantic intent)
        ↓
[5] R6 — no-evidence MUST 자동 SHOULD 강등
```

**측정된 한계**: starlette v12 evidence 매칭율 50%. **commit pool 자체에 매칭 가능한 commit 수 보다 rule pool 의도 mismatch 가 ceiling 의 진짜 원인** (memory `project_validation_findings` 누적 결론). principle-level rules 는 현재 코드의 구조를 묘사하는데, commit 들은 시니어가 바꾼 결정의 narrative 라 의도 축이 직각이다.

**External reviewer 평가** (2026-05-06): **evidence chain 가치 ≈ 2x quality 격차**. evidence 있는 rule 의 incident kind ("왜 안 되는지" 실패 모드) 는 hallucination 방지하지만, no-evidence rule 의 Why 는 모두 LLM 사후 정당화. 따라서 **도구 차별점은 evidence 그 자체**.

**누적 데이터** (2026-05-06): 카테고리 확장 (G testing/security/performance) 으로 매칭율 38% → 50% (+12%p). 여전히 50% 는 **rule 의 절반은 LLM 짜내기**. cumulative incident kind = 1/13 evidence (8%) — incident 가 가장 가치 있다는 reviewer 평가와 ROI 격차.

## R7 Inversion: commit-first

```
[1] FETCH — commit_decisions 만 우선 (이미 archaeology + G8 이 함)
        ↓
[2] CLUSTER — commits 를 의도 그룹으로 묶음 (intent_kind × 영향받은 파일 의미 클러스터)
        ↓
[3] DERIVE — 각 클러스터마다 "이 commits 가 공통으로 입증하는 rule 이 무엇인가?" — rule 본문은 클러스터 의도의 abstraction, evidence 는 already there
        ↓
[4] VERIFY — derived rule 을 현재 코드에 grep — good_example 추출 가능한지 확인. 매칭 0 이면 drop (시니어가 한 번 결정했지만 이후 코드에서 흔적 사라진 케이스 — 가치 낮음)
        ↓
[5] CATEGORIZE — derived rule 을 기존 10 카테고리 중 하나로 후속 태깅 (또는 emergent cat 허용)
```

핵심 변화: **evidence 가 rule 의 origin** — 후속 매칭 단계 자체가 사라짐. 매칭율 = 100% by construction.

## Trade-offs

| | Forward (현재) | Inversion (R7) |
|---|---|---|
| 매칭율 | ≤50% (천장 데이터) | 100% by construction |
| Rule volume | 카테고리당 ~4 (24 total at 6 cats) | commit cluster 수에 비례 (starlette 18 → 8-12) |
| 누락 위험 | low (현재 코드에서 쉽게 추출) | high (시니어가 commit 으로 narrate 안 한 obvious patterns 누락) |
| Hallucination | high (LLM 짜내기 + post-hoc evidence) | low (evidence 가 origin) |
| 카테고리 coverage | guaranteed (입력에 명시) | emergent (intent 분포에 의존 — testing/devops 가 commits 에 안 보일 수도) |

**가설**: forward 의 "쉬운 obvious rule" 누락은 도구 차별점 손실이 아니라 **시그널 강화**. 시니어가 commit 에 narrate 안 한 rule 은 정의상 generic Python advice 와 구분 안 되며, 외부 reviewer 가 "노이즈" 라고 표시한 3 rules 모두 그 부류였다 (`__future__` 묶음, exception repr, AppType generic).

## Pipeline Architecture (제안)

신규 파일:
- `backend/src/hijack/core/inverter.py` — cluster_commits / derive_rule_from_cluster / verify_rule_against_source
- `backend/src/hijack/core/intent_clusterer.py` — intent_kind + file_path 기반 클러스터링 (간단: 같은 intent_kind + 파일 디렉토리 overlap 으로 group, k-means 같은 거 NO)

수정 파일:
- `analyzer.py` — `run_full_analysis` 의 카테고리 루프 옆에 `--mode=inversion` flag 추가. 둘 다 emit 가능 (병렬 검증용).
- `prompts.py` — `_INVERSION_PROMPT` 신설 (forward `_OUTPUT_FORMAT` 와 별도). 입력: commit cluster (subject + body + file_paths). 출력: AnalysisRule (rule + good_example 는 verify 단계에서 채움).
- `models.py` — AnalysisRule 에 `derivation_mode: "forward" | "inversion"` 필드 추가 (선택).

신규 테스트:
- `tests/test_intent_clusterer.py` — 같은 intent_kind + 파일 overlap commits 가 1 cluster 로 묶이는지
- `tests/test_inverter.py` — derive_rule_from_cluster 가 cluster 의 공통 의도를 포착하는지 (mock LLM)
- `tests/test_inversion_e2e.py` — starlette commits → derived rules → verify 단계까지 (slow integration)

## Phases

**Phase 1 — clustering only (1일)**
- intent_clusterer.py + tests
- skill-mode dry-run: starlette commits → cluster output (markdown)
- 사용자 검토: 클러스터링이 의미 있는지 eyeball

**Phase 2 — derivation prompt (1일)**
- _INVERSION_PROMPT 작성
- skill-mode: cluster → rule (LLM 이 한 cluster 당 rule 1개 derive)
- starlette 실측: forward v12 vs inversion 출력 비교 quality

**Phase 3 — verify + integration (1-2일)**
- verify_rule_against_source: derived rule 의 good_example 을 현재 코드에서 grep
- analyzer.py `--mode=inversion` flag
- write_output 호환

**Phase 4 — external eval (반나절)**
- forward (v12) vs inversion 출력을 clean Claude session 에게 평가
- 도구 학습/AI 가이드 score 비교
- 결정: inversion 이 forward 보다 quality ↑ 면 default 전환, 동등 또는 ↓ 면 보류

총 3-5일 베팅. 모든 phase 가 독립적으로 검증되므로 중도 abort 가능.

## Open Questions / Risks

1. **클러스터링 알고리즘 선택**: file_path overlap 만으로 충분? intent_kind 가 압도적으로 preference 이면 클러스터가 mega-cluster 로 묶여서 rule abstraction 이 너무 일반적이 될 수 있음. starlette 18 commits 의 클러스터 분포를 phase 1 에서 직접 측정해야.

2. **카테고리 coverage 누락**: emergent cat 분포가 거의 architecture/api_design 으로 쏠리고 testing/devops/security 는 commit 흔적 적어서 누락될 수 있음. fallback: forward + inversion 둘 다 emit, inversion 이 cite 한 cat 은 그대로 사용, 안 cite 한 cat 만 forward fallback. **하이브리드 모드** — 매칭율 기준 합리적.

3. **verify 단계 false negative**: 시니어가 옛 commit 으로 결정 → 이후 code 가 refactor 돼서 grep 가 표면적으로 매칭 안 함 (개념은 같아도 식별자 변경). LLM 에 verify 위임할지, 단순 keyword grep 로 충분할지. 단순 grep 으로 시작 (속도/cost) → false negative 측정 후 결정.

4. **R7 ↔ G7 (priority self-check) 호환**: derived rule 의 priority 도 cluster 의 evidence intent (incident → MUST, preference → SHOULD 같은 default 매핑) 으로 정해질 가능성. forward 의 priority self-check (G7) 와 일관성 유지 가이드 필요.

5. **R7 자체 ROI 검증**: 만약 phase 4 외부 평가에서 inversion 이 forward 와 동등하면 — 도구 정체성 strengthening 효과 (claim: "evidence-first") 는 있지만 quality 차이 없음. 그 경우 R7 = marketing 이지 quality lever 아님. abort 기준 명시.

## 시작점 (오늘 안에 할 수 있는 것)

- intent_clusterer.py 의 minimum scaffolding (클러스터 함수 시그너처 + 1 test)
- starlette 18 commits 직접 read 해서 손으로 클러스터링 1회 — 알고리즘 휴리스틱 영감 얻기

이 design doc 는 alive — phase 1 시작 전에 사용자 ↔ Claude 합의 한 번 필요.

## Phase 1 결과 (2026-05-06)

`backend/src/hijack/core/intent_clusterer.py` + `tests/test_intent_clusterer.py` 작성 완료. 알고리즘: `(intent_kind, primary_path)` 버킷, primary_path = 첫 non-test file_path. 정렬: 클러스터 size DESC → intent priority → path ASC.

**starlette smoke 결과** (artifact: `r7_phase1_starlette_clusters.md`):

| 지표 | 값 |
|---|---|
| Commits w/ signal | 18 |
| Clusters | 14 |
| Multi-commit clusters | 3 (3 + 2 + 2 commits) |
| Single-commit clusters | 11 |
| by_kind | preference 12, rejection 1, constraint 1, **incident 0** |

**가설 viable 입증** ✅ — Cluster #1 (CORS preflight, 3 commits 모두 `middleware/cors.py` 터치) 이 하나로 묶임. Phase 2 LLM 이 이 클러스터로 1 rule + 3 evidence entries 도출 → forward pipeline 의 v11 security rule (현재 simple+preflight 두 commit 직접 인용) 와 동등 또는 우위.

**클러스터 false positive 발견** ⚠️ — Cluster #2 `starlette/config.py` (2 commits): 48dea4d (typing overloads) + b95acea (CI scripts update) 가 같은 클러스터로 묶임. b95acea 가 multi-file commit 인데 sorted 첫 non-test 가 우연히 config.py. 의도 mismatch. **Phase 2 LLM 가이드 필요**: 클러스터 내 commits 의 의도가 align 안 되면 rule emit skip + cluster 분해 또는 폐기.

**Cluster #4 의 rejection 패턴 false positive** ⚠️ — 93e74a4d "WebSocket Denial Response" 의 'rejected' 매칭은 feature 이름이지 narrative rejection 아님. archaeology 의 패턴 매칭이 narrative vs subject 구분 안 함.

**Single-commit-cluster ratio 11/14**: forward pipeline 의 1-rule-per-commit 매칭과 동등. R7 의 진짜 leverage 는 multi-commit 클러스터 (3개 — 14개 중 21%). 천장: 21% rule 들에 대해서만 R7 가 forward 대비 evidence richness ↑ 효과.

**incident 0 (4th datapoint)**: 누적 4 측정 (testing v10, security v11, perf v12, 그리고 R7 phase 1) 모두 incident 0. starlette 시니어 commit 자체가 incident framing 안 씀이 강하게 입증. 외부 reviewer 가 incident 가장 가치 있다 한 평가와 ROI 격차 — R7 도 이 격차 못 메움.

**Phase 2 가이드라인 (이 결과 기반)**:
- 클러스터 size ≥ 2 인 multi-commit cluster 만 우선 inversion 적용 (R7 leverage 핵심)
- size = 1 클러스터는 forward pipeline 으로 fallback
- LLM 프롬프트에 "이 cluster commits 의 의도가 align 안 되면 'no rule' 응답해라" 명시
- 클러스터 false positive (config.py 같은) 는 LLM 의 의도 검증 단계가 잡음

**Open question 1 (클러스터링 알고리즘) partial answer**: file_path overlap 단독으로는 multi-file commit 의 anchor 노이즈 발생. 향후 개선: commit 의 subject 키워드도 클러스터링에 반영 (e.g. "CORS" subject 가 같은 cluster, "CI" subject 가 별도 cluster).

## PR-decision 프로브 결과 (2026-07-03)

Phase 1 은 commit_decisions(incident 0)만 봤다. 이후 0.3.0 PR 마이닝(pr_archaeology)이 rejection/incident 를 직접 공급하므로, `cluster_pr_decisions`(intent_clusterer.py) 로 "PR 을 먹이면 R7 천장이 깨지나?" 를 실측했다. PRDecision 은 intent_kind 를 직접 보유(classify 불필요), file_paths 없음(diff_excerpt `--- {file}` 헤더에서 앵커, 없으면 ref fallback).

**실측 (starlette 24 decisions, 저장된 session.json):**

| 지표 | 값 |
|---|---|
| by intent_kind | rejection 19, **incident 5** |
| clusters | 23 |
| **multi-item clusters** | **1 (4%)** |
| 그 1개 | `[rejection] README.md` ×2 (PR#3275+#3250) — 약한 docs 앵커, #3275 은 minimalism 과 부호 반대라 이미 제외한 PR = 노이즈 |
| rejection/incident multi-item | 1 (그 노이즈 하나) |

**두 결론이 갈림:**
1. **intent-diversity 천장은 깨짐** ✅ — PR 마이닝이 incident 5 + rejection 19 를 공급(commit-mining incident-0 대비). 그러나 **이 가치는 forward 파이프라인이 이미 소비** 중 (pr_decisions → rule-matching + 거절 diff verbatim ❌ 렌더, 커밋 969e3d2/72f5dbe). R7 없이도 확보됨.
2. **R7 특유의 leverage(multi-item 클러스터 역도출)는 데이터 미지지** ❌ — 96% 단일 클러스터(Phase-1 doc 이 "forward 와 동등"이라 규정), 유일한 multi-item 은 노이즈. commit 축 21%보다도 얇다. rejection PR 은 각기 다른 제안을 다른 파일에서 거절 → 같은 (intent, file) 로 안 뭉침.

**Abort 판정 (doc §Open-Q5 기준)**: PR 축에서도 inversion leverage 미확인. **풀 Phase 2(=_INVERSION_PROMPT + derivation + quality eval) 보류를 데이터로 뒷받침.** R7 은 marketing 정체성(evidence-first, 매칭율 100% by construction) 효과만 있고 quality lever 로서의 근거가 commit·PR 두 축 모두에서 약하다. `cluster_pr_decisions` 는 측정 도구로 보존(재측정용). 향후 다른 레포에서 multi-item 비율이 유의미하게 높게 나오면 재검토.
