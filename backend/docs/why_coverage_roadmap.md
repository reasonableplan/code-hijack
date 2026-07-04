# WHY Coverage Roadmap — code-hijack 0.4.0 방향 설계

> Status: **proposal** (2026-07-03, Fable). 웹 리서치 + 이번 사이클 실측 기반.
> 선행 문서: `r7_pipeline_reversal.md` (Phase 2 보류 판정), memory `project_validation_findings`.

## 1. 문제 정의 — 실측이 가리키는 곳

도구의 목표: **시니어의 스타일(WHAT)과 의도(WHY)를 함께 뽑아** 두 독자(사용자 학습 + AI 코드 품질)에게 전달.

2026-07-03 starlette 실측 (cited_ratio history/code 분해, commit af79fb0):

| 지표 | 값 | 의미 |
|---|---|---|
| cited | 7/7 (100%) | 헤드라인은 만점 |
| **history-anchored** | **4/7 (57%)** | 결정 기록(commit/PR/revert/ADR) 인용 = 진짜 WHY |
| **code-anchored** | **3/7 (43%)** | ref_files 코드 라인만 = WHY 부재, 스타일만 |

즉 **규칙의 43%가 "왜"를 못 답한다.** 이게 0.4.0 이 공략할 단일 지표다:
**history-anchored ratio 57% → 75%+ (starlette 재분석 기준).**

연구가 같은 방향을 가리킨다:
- diff/코드만 보면 style/syntax 까지만 잡힌다. intent 는 PR/issue 설명문 등 텍스트에 있다 ([2511.07017](https://arxiv.org/html/2511.07017), [2606.01859](https://arxiv.org/html/2606.01859v1)).
- rationale 은 구조 요소에 대개 없거나 암묵적 — 텍스트에서 복구해야 한다 ([1704.04798](https://arxiv.org/pdf/1704.04798)).
- 컨텍스트 파일에 rationale/intent 포함 시 agent 성능↑ hallucination↓ ([2511.12884](https://arxiv.org/pdf/2511.12884)).
- **규칙 파일의 길이/구조/포맷은 AI 준수율에 영향 미미. 내용(태스크 적합성)이 좌우** ([2606.12231](https://arxiv.org/pdf/2606.12231)) — 출력 포맷 다듬기는 낮은 레버, 규칙 내용의 증거성이 높은 레버.

## 2. 제안 항목 (우선순위순)

### W1 — 머지 PR description 바인딩 (~~최대 레버~~ **제거됨 2026-07-04: net-new 0, 전제 false**)

> **결론 먼저 (2026-07-04)**: W1 은 코드에서 **제거**됨(commit 이력 참조). 전제("squash-merge 가 accepted rationale 을 커밋 body 밖으로 collapse")가 실측으로 **틀림** — GitHub squash 는 PR body 를 커밋 body 에 **복사**하므로 rationale 이 커밋에 남고 commit-mining 이 이미 잡는다. 3개 레포(starlette/typer/pydantic) net-new 공급 **0**. 아래는 히스토리 보존용 기록.

**갭**: 현 PR 마이닝(pr_archaeology)은 *거절* PR + wontfix issue 만 캔다. 그런데 **채택된 패턴의 WHY 는 머지 PR 의 설명문**에 있다 — code-anchored 43% 는 대부분 "머지된 결정" 인데 그 결정문을 안 읽고 있음.

**메커니즘**: GitHub squash-merge 는 기본으로 subject 에 `(#NNNN)` 을 박는다 ([GitHub Docs](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/incorporating-changes-from-a-pull-request/about-pull-request-merges)). starlette 도 이 관행 [verified — 세션 데이터의 commit subject 들].
1. `archaeology.py` 가 이미 뽑는 commit_decisions 의 subject 에서 `\(#(\d+)\)$` 추출
2. **commit_decisions 에 오른 커밋만** (통상 10~30개, bounded) gh api 로 해당 PR body fetch — `_MAX_DIFF_FETCHES` 와 같은 캡 패턴
3. PR body 를 그 CommitDecision 의 rich body 로 병합 (squash 로 잘린 rationale 복원) → 규칙 매칭 시 `pr` kind evidence 로 승격

**예상 효과**: commit body 가 얇아 매칭 실패하던 결정들이 PR 설명문으로 살아남 → history-anchored 직접 상승. 기존 pr kind 인프라(72f5dbe) 재사용이라 신규 개념 없음.

**검증**: starlette 재분석 → measurement.json 의 history-anchored ratio 비교. **+10%p 미만이면 W1 은 이 레포에서 소진으로 기록** (레포별 편차 가능).

**구현 완료 (2026-07-03, commit 1e2fae6)**: `fetch_merged_pr_decisions` + `merge_pr_decisions` + `_build_merged_pr_decision`, analyzer 병합. tests 1082.
- **부수 발견·근본픽스 `_strip_pr_template`**: GitHub PR 템플릿 체크리스트(`- [x] ... I tried ...`)가 **모든** PR 에서 `tried` 패턴 오매칭 → 머지+거절 두 경로 정밀도 결함이었음. 매칭 전 제거. (거절-PR 마이닝의 기존 노이즈도 이걸로 감소.)
- **소스 검증 (라이브 gh)**: raw 최근 커밋 스모크는 7건 전부 docs-grammar 템플릿 노이즈 → strip 후 0. **결정-필터 커밋 subject**(파이프라인 실입력 근사)로는 머지 PR 3건 verbatim rationale: PR#3179 `to avoid O(n²)`(FormParser perf, 메모리 789b9269 규칙과 일치), PR#2648 `rather than`, PR#2149 `instead of`.

**⚠️ 정정 (2026-07-04): W1 은 1e2fae6 시점에 파이프라인에서 실동작하지 않았다.** 위 "소스 검증" 은 `fetch_merged_pr_decisions` 를 **직접 호출**한 결과였고, analyzer 경로는 3중 결함으로 한 번도 W1 을 돌리지 못했다:
1. **crash [verified]**: `analyzer.py` 가 `[c.subject for c in commit_decisions]` 로 `CommitDecisions`(`__iter__` 없음)를 순회 → `TypeError` 매 호출 발생 + 아래 `except` 가 삼킴. `.commits` 누락.
2. **coupling**: PR 번호를 결정-커밋 subject 에서만 소싱 → squash-merge 레포(커밋 얇음)에서 정확히 가장 필요할 때 병목.
3. **skill 미배선**: `fetch_merged_pr_decisions` 가 CLI(analyzer)에만, SKILL.md step1 엔 없었음.

**중간 수정 (2026-07-04, 이후 제거)**: 3중 결함을 먼저 고침 — 신규 헬퍼 `merged_pr_candidate_subjects` 로 decouple + analyzer 호출부 교체 + SKILL.md 배선. E2E: starlette OLD 7 = NEW 7 (무회귀), typer OLD 1 → NEW 2.

**제거 (2026-07-04)**: 수정된 W1 의 **net-new** 공급을 측정 → 폐기 판정. net-new = "W1 이 가져온 머지 PR 의 backing 커밋 body 에 이미 decision signal 이 없어서 W1 이 rationale 을 복원한" 건수.

| 레포 | commit-mining | W1 total | **W1 net-new** | W2 SATD | 거절PR |
|---|---|---|---|---|---|
| starlette | 18 | 7 | **0** (커밋 두툼) | 1 | 9 |
| typer | 2 | 2 | **~0** (얇은 커밋=docs/CI) | 26 | 4 |
| pydantic | 26 | 9 | **0** | 50 | 35 |

**전제 반증 (pydantic 직접 확인)**: PR#12536 커밋 body(682b)에 `to avoid` rationale 전문 有, PR#11212 커밋 body(92b) `instead of` 전문 有. GitHub squash-merge 가 PR body 를 커밋 body 에 **복사** → rationale 이 collapse 되는 게 아니라 커밋에 그대로 남음 → commit-mining 이 이미 잡음 → W1 복원분 = 0. **W1 코드 전량 제거** (`fetch_merged_pr_decisions`/`merge_pr_decisions`/`merged_pr_candidate_subjects`/`_build_merged_pr_decision` + analyzer/SKILL 배선 + 테스트 18개). tests 1101→1083, ruff clean. **소스 서열 역전 확정: W2(SATD) > 거절/incident PR(0.3.0) > ~~W1~~.**

### W2 — SATD 주석 마이닝 (저비용 인라인 WHY)

**갭**: 코드 안의 `TODO/FIXME/XXX/HACK` + 주변 문장은 시니어가 남긴 self-admitted 의도/한계인데 안 캐고 있음.

**메커니즘**: **MAT 방식** — 4개 태그 키워드 매칭만으로 ML 접근과 동등~우수 ([1910.13238](https://arxiv.org/pdf/1910.13238)). 학습 불필요, 오프라인, 결정론적 — archaeology.py 와 같은 철학.
- 신규 pure 모듈 `satd.py`: 이미 fetch 된 SourceFile 위 regex 패스, `(path:line, tag, comment_text)` 수집
- LLM 입력에 "시니어의 self-admitted 한계/의도" 풀로 제공. 규칙이 인용 시 evidence 처리

**열린 결정 (구현 전 확정 필요, §3)**: SATD 인용의 evidence kind — 기존 `doc`(path 검증 재사용) vs 신규 `comment`. 그리고 tier — 코드 앵커이자 시니어 육성이므로 history 로 칠지. **초안: 신규 kind 없이 `doc` 재사용 + history 로 분류** (개발자 자신의 서술 = 결정 기록). 반론 있으면 여기서 멈춤.

**검증**: starlette + httpx 에서 SATD 수집량/규칙 인용률 측정. 인용 0 이면 LLM 프롬프트 배선 재검토.

**구현 완료 (2026-07-03, commit 92e8f64) — `comment` kind 채택**: 초안의 `doc` 재사용은 폐기 (doc 진실 풀 = repo_doc_paths 라 SATD 의 `src/foo.py:42` ref 가 fake 로 오분류됨). 신규 `comment` kind + valid_comment_refs 풀(정확 path:line). `satd.py`(MAT regex) + models/evidence/analyzer/SKILL 배관은 pr kind(72f5dbe) 미러. **부수 이득**: CLI 모드 assign_rationale_tier 에 pr 풀이 안 넘어가던 기존 갭도 함께 해소. tests 1097.
- **실측**: starlette 34 .py → SATD **1건**(`middleware/exceptions.py:26 [TODO] handle 404 if debug`). 성숙 라이브러리라 희소(W1 처럼 레포 의존). 엔진 E2E(추출→세션→comment 분류→history) 작동 확인. history-anchored 실개선치는 skill-mode 풀 재분석 필요.

### W3 — 명시적/암묵적 스타일 층 분리 (43% 의 정직한 재해석)

**근거**: MPCODER 가 스타일을 2층으로 분리 — **명시적**(문법 표준: naming/포맷/구조, 기계 검증 가능) vs **암묵적**(의미론적 컨벤션: 분해 방식/idiom) ([2406.17255](https://arxiv.org/pdf/2406.17255)).

**통찰**: code-anchored 43% 가 전부 갭은 아니다. **명시적 스타일 규칙은 코드 앵커로 충분** (naming 컨벤션은 세어보면 검증됨 — WHY 가 원래 얇음). 갭은 **암묵적/아키텍처 규칙인데 코드 앵커뿐인 것** — 이건 히스토리가 필요.

**메커니즘**: AnalysisRule 에 `style_layer: explicit | implicit` (LLM 태깅 + 가이드). 지표를 4분면으로:

| | history-anchored | code-anchored |
|---|---|---|
| explicit | 과잉 (괜찮음) | **적정** ✅ |
| implicit | **적정** ✅ | **갭** ❌ ← 진짜 타깃 |

**검증**: implicit×code-anchored 칸의 규칙 수가 W1/W2 후 감소하는지. 지표 이름: `implicit_uncited_count`.

### W4 — 측정·출력 소폭 (backlog, 각 반나절 이하)

- **W4a exemplar 선별 지표**: few-shot 은 예시 선별이 성능을 좌우 ([2412.02906](https://arxiv.org/abs/2412.02906)). good_example 이 실존 코드 verbatim 인지(fetch 파일과 부분 매칭) 비율을 measurement.json 에 추가 — 카고컬트/창작 예시 감지.
- **W4b 중복 lint**: cursor rules 실증에서 28.7% 줄이 중복 ([2512.18925](https://arxiv.org/html/2512.18925v1)) — integrated 출력의 layer 간 중복 규칙 비율 lint.
- **W4c reason 의 ADR 3단(Context/Decision/Consequences) 구조화**: 인간 독자(학습)용. **정직 노트: AI 준수율엔 포맷 효과 미미** ([2606.12231](https://arxiv.org/pdf/2606.12231)) — 두 독자 중 사용자 쪽 개선으로만 주장할 것.

### 부채 (roadmap 외 트래킹)

- cli.py lazy import (`[api]` extra 없이 measure/diff 불가 — 실사용 발현 확인됨)
- 마이닝 노이즈 잔여 (dependabot→incident 은 `_is_bot_pr` 로 부분 해소, 스팸 PR rejection 잔존)
- test_llm.py 커버리지 (3 vs 86)

## 3. 우선순위 논거

1. ~~**W1 이 첫째**~~ **[폐기 2026-07-04]**: 전제("머지 PR 이 미개척 신규 소스")가 틀림 — squash 가 PR body 를 커밋 body 에 복사하므로 commit-mining 이 이미 잡는다. net-new 0, 코드 제거. **실제 첫째는 W2.**
2. **W2 (실질 1순위)**: 네트워크 불필요·결정론적·연구 검증된(MAT) 최저비용 소스. **유일하게 commit/PR 마이닝이 구조적으로 못 닿는 인라인 WHY** (net-new 검증됨: pydantic 50, typer 26).
3. **W3 셋째**: 코드가 아니라 *지표의 의미*를 고치는 작업 — W1/W2 효과를 올바르게 읽기 위해 필요하지만 그 자체로 WHY 를 늘리지 않음.
4. **R7 재확인**: inversion 은 commit 축 21%·PR 축 4% 로 데이터 미지지 (보류 유지). W1 은 R7 과 달리 파이프라인 방향을 안 바꾸고 소스만 늘린다.

## 4. 측정 계획

**⚠️ 개정 (2026-07-04): history-anchored ratio 를 주 지표에서 폐기한다.** 두 가지가 실측으로 드러남:
1. **baseline 57% 복구 불가**: 저장된 starlette 세션 6개(v7/v8/v10/v11/v12/foresight) 전부 cited 규칙 **100% history-anchored** (code-anchored=0). 57%/43% 는 2026-07-03 transient/gitignored 세션 값으로 비교 대상이 없음.
2. **지표가 confound**: `_cited_anchor` 는 `rule.evidence` 가 비어있지 않으면 곧 `cited_history` 로 분류. 즉 지표는 "W1/W2 가 새 인용거리를 **공급**했나"가 아니라 "skill 세션 LLM 이 evidence 배열을 **채웠나**"를 잰다. 작성 성실도가 지표를 지배 → W1/W2 소스 효과를 분리 못 함.

**대체 주 지표: 결정론적 net-new citable 공급** (LLM 무관, 재현 가능). `scratchpad/supply_measure.py` 방식 — 소스별 citable 근거 단위를 세고, W1/W2 가 commit-mining 대비 **순-신규**로 공급하는 양을 측정.

| 지표 | 성격 | 판정 기준 |
|---|---|---|
| **소스별 공급량** (commit / W1 머지PR / W2 SATD / 거절PR) | 결정론, 레포별 | W1/W2 순-신규 > 0 이면 유효 |
| fake_citation | 결정론 | 0 유지 |
| exemplar verbatim ratio (W4a) | 관찰 지표 | 기록만 |
| history-anchored ratio | **참고용 강등** | LLM 성실도 confound — 추이만 관찰, 목표 아님 |

측정 실적 (2026-07-04) — **net-new** = commit-mining 이 이미 못 잡은 순수 추가분:

| 소스 | starlette | typer | pydantic |
|---|---|---|---|
| commit-mining 결정커밋 | 18 | 2 | 26 |
| ~~W1 머지PR~~ **net-new** | **0** (제거됨) | **~0** | **0** |
| **W2 SATD** (net-new) | 1 | **26** | **50** |
| 거절/incident PR | 9 | 4 | 35 |

프로토콜: 레포마다 `supply_measure.py` 1회 (네트워크, bounded). skill-mode 풀 재분석은 downstream A/B (규칙 주입 효과 실측, 2026-07-04) 용도로만 — 공급 측정에는 불필요(confound).

## 5. Open Questions

1. **W1 fetch 예산**: commit_decisions 만 enrich 하면 통상 10~30 호출. rate-limit 环경(무인증 gh)에서의 graceful skip 은 기존 패턴 재사용 — 확인만.
2. **W2 evidence kind**: `doc` 재사용 초안에 대한 사용자 확인 필요 (데이터 모델 결정, §3).
3. **W3 의 explicit 판정 주체**: LLM 태깅으로 시작 (결정론 분류기는 과설계 위험). 태깅 신뢰도 낮으면 AST 기반 재검토.
4. **abort 기준 (2026-07-04 최종)**: 원안("+10%p history-anchored 미만이면 소진")은 지표 폐기로 무효. 결정론 net-new 공급 기반 최종 판정:
   - **W1 = dead end, 제거됨** (net-new 0 × 3레포, 전제 false). "머지 PR 미개척" 가정이 squash 실동작으로 반증.
   - **W2 = 유효** (SATD net-new: pydantic 50 / typer 26 / starlette 1), skill 배선 완료. **유일한 확실 net-new 소스.**
   - **거절/incident PR (0.3.0) = 최강 차별 WHY** (pydantic 35 / starlette 9), 이미 파이프라인 소비 중.
   - **다음 레버**: (i) SATD 강화 (W2 주변 컨텍스트 확장 + 규칙 인용률 측정), (ii) downstream A/B — 도구 가치 축이 "WHY 공급 + 약한 모델 안티패턴 구조"임이 실증됨 (2026-07-04 A/B). **소스 확장은 W2 로 수렴; W1 류 "머지 PR" 확장은 재시도하지 말 것 (squash 복사로 무효).**

## 6. 참고

- [Benchmarking LLMs for Fine-Grained Code Review with Enriched Context (2511.07017)](https://arxiv.org/html/2511.07017) — intent 는 PR/issue 텍스트에
- [Agent READMEs: Empirical Study of Context Files (2511.12884)](https://arxiv.org/pdf/2511.12884) — rationale 포함 시 agent 성능↑
- [Rule Taxonomy and Evolution in AI IDEs (2606.12231)](https://arxiv.org/pdf/2606.12231) — 포맷≠준수율, 내용이 레버
- [MAT: simple yet strong baseline for SATD (1910.13238)](https://arxiv.org/pdf/1910.13238) — 키워드 매칭으로 충분
- [MPCODER: explicit/implicit style representation (2406.17255)](https://arxiv.org/pdf/2406.17255) — 스타일 2층 분리
- [Does Few-Shot Learning Help LLM Code Synthesis? (2412.02906)](https://arxiv.org/abs/2412.02906) — 예시 선별이 좌우
- [Developer-Provided Context for AI Coding Assistants (2512.18925)](https://arxiv.org/html/2512.18925v1) — 규칙 파일 28.7% 중복
- [About pull request merges — GitHub Docs](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/incorporating-changes-from-a-pull-request/about-pull-request-merges) — squash `(#NNNN)` 관행
- [Uncovering Architectural Design Decisions (1704.04798)](https://arxiv.org/pdf/1704.04798) — rationale 은 구조에 없음
