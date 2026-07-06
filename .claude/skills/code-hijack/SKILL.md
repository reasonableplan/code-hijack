---
name: code-hijack
description: 시니어 코드베이스를 분석해 AI 에이전트용 코딩 규칙 문서(CLAUDE.md + layer별 .md + system-prompt.md)를 자동 추출한다. ANTHROPIC_API_KEY 없이 현재 Claude Code 세션이 LLM 역할을 수행하는 skill 모드.
---

# code-hijack Skill Mode

너는 지금 **code-hijack 도구의 skill 모드 LLM** 역할을 수행한다.
CLI 모드(`code-hijack analyze`)가 Anthropic API를 호출해 하는 일을, 너의 현재 세션 컨텍스트 안에서 직접 처리한다.

**엔진 위치**: `C:\Users\juwon\OneDrive\Desktop\code-hijack` (아래 스크립트는 이 디렉토리에서 실행)

## 역할

입력된 TARGET 레포(로컬 경로 또는 GitHub URL)의 소스 파일을 수집·분류·분석하고, AI 에이전트가 해당 스타일로 코드를 짜게 하는 규칙 문서를 생성한다.

**이 도구의 존재 이유는 증거(evidence)다**: 그럴듯한 "베스트 프랙티스"를 지어내는 게 아니라, 시니어가 커밋 본문·거절된 PR·리버트·ADR 에 실제로 남긴 판단을 verbatim 으로 보존해 규칙에 인용하는 것. evidence 없는 규칙은 2급 취급된다. 특히 **거절된 대안 (rejected PR / wontfix issue)** 은 "왜 저렇게 하면 안 되는가"의 최고 농도 소스다.

## 입력

- **TARGET**: 사용자가 `/code-hijack <target>` 으로 전달한 인자. 로컬 경로 또는 GitHub URL.
- **옵션** (선택):
  - `--path <subdir>` — 모노레포 서브디렉토리 한정
  - `--categories <list>` — 분석 카테고리 콤마 구분 (기본: architecture,coding_style,api_design)
  - `--output <dir>` — 출력 디렉토리 (기본: `<target>/docs/hijacked/`)

지원 suffix: `.py .ts .tsx .kt .java .sql .prisma` (DB 스키마 추출 시 schema.prisma / 마이그레이션 SQL 포함됨)

## 출력

- `<output>/<session_id>/meta.md`, `<category>.md`, `session.json`
- `<output>/<session_id>/foresight.md` — ForesightCard 가설 목록 (foresight_cards 비면 미생성)
- `<output>/<session_id>/measurement.json` — cited/MUST 비율 + tier/intent 분포 + foresight 채점
- `<output>/integrated/CLAUDE.md` — 진입점 + Top MUST 규칙 + 레이어 가이드 (레포 성격 맥락 헤더 포함)
- `<output>/integrated/{frontend,backend,database,devops,shared}.md` — 레이어별 규칙 (+ 기계적 style invariants)
- `<output>/integrated/exemplars.md` — 시니어 레포의 대표 함수/클래스 원문 (Python 레포만; TS 는 자동 추출 미지원)
- `<output>/integrated/foresight.md` — ForesightCard 가설 목록 통합 사본 (있는 경우만)
- `<output>/integrated/system-prompt.md`

## 실행 순서

### 1. 파일 수집 + 선별 + 증거 풀 출력 (Bash tool)

```bash
cd <ENGINE_ROOT>
python -c "
import json, sys, tomllib
sys.path.insert(0, 'backend/src')
from hijack.core.fetcher import fetch_source
from hijack.core.preprocessor import build_preprocess_result, select_files_for_category
from hijack.core.docs import render_repo_context
from hijack.core.archaeology import render_history_for_prompt, extract_commit_decisions
from hijack.core.negative_space import extract_negative_space, read_deprecation_history
from hijack.core.pr_archaeology import fetch_pr_decisions
from hijack.core.satd import extract_satd

TARGET = '<TARGET>'
CATEGORIES = ['architecture', 'coding_style', 'api_design']  # 또는 사용자 지정

files, root = fetch_source(TARGET, history_depth=30)  # depth=30: depth=10 대비 매칭 가능 commits ~7배 (httpx v4). depth=50 부터 ROI 감쇠.

# pyproject.toml 로드 (있으면) — detect_repo_nature + extract_negative_space 에 전달
pyproject_path = root / 'pyproject.toml'
pyproject_toml = None
if pyproject_path.exists():
    with open(pyproject_path, 'rb') as f:
        pyproject_toml = tomllib.load(f)

pp = build_preprocess_result(files, root, pyproject_toml=pyproject_toml)
selected = {cat: [f.path.as_posix() for f in select_files_for_category(pp, cat, max_files=12)] for cat in CATEGORIES}
cd_ = extract_commit_decisions(files)
satd_ = extract_satd(files)  # W2: TODO/FIXME/XXX/HACK 주석 — 시니어 인라인 WHY. ref = "path:line"

# PR/issue 마이닝 (impure — gh CLI 필요; 부재 시 빈 PRDecisions 반환, 분석 계속)
pd = fetch_pr_decisions(TARGET)
if not pd.has_signal:
    print('[WARN] pr_decisions: no signal (gh CLI not installed or not a GitHub URL)', file=sys.stderr)

# negative-space 추출 (순수 함수 + I/O git history 병합)
py_files = [f.path for f in files if f.path.suffix == '.py']
layer_map = {f.path: f.layer for f in files}
ns = extract_negative_space(root, py_files, pyproject_toml, layer_map)
depr_history = read_deprecation_history(root)  # graceful skip (git 없으면 [])
ns_dict = {
    'dep_count': ns.dep_count,
    'direct_impl_hints': ns.direct_impl_hints,
    'public_ratio': round(ns.public_ratio, 3),
    'has_all_discipline': ns.has_all_discipline,
    'deprecation_patterns': ns.deprecation_patterns + depr_history,
    'layer_import_violations': ns.layer_import_violations,
}

print(json.dumps({
    'repo_root': root.as_posix(),
    'total_files': len(files),
    'by_layer': {k: len(v) for k, v in pp.by_layer.items()},
    'selected_per_category': selected,
    'repo_nature': pp.repo_nature,
    'commit_decisions': cd_.to_json() if cd_.has_signal else None,
    'pr_decisions': pd.to_json() if pd.has_signal else None,
    'satd_items': satd_.to_json() if satd_.has_signal else None,
    'negative_space': ns_dict,
}, indent=2, ensure_ascii=False))

# --- 증거 풀: 이 블록에 나온 SHA/문서 경로/PR ref 만 evidence 로 인용 가능 ---
print('===== REPO_CONTEXT =====')
print(render_repo_context(pp.repo_docs) or '(no repo docs)')

print('===== FILE_HISTORY (selected files only) =====')
sel_union = {p for paths in selected.values() for p in paths}
for f in files:
    if f.path.as_posix() in sel_union and f.history:
        block = render_history_for_prompt(f.history)
        if block:
            print(f'--- {f.path.as_posix()} ---')
            print(block)
"
```

위 출력에서 얻는 것:
- 각 카테고리의 선별 파일 목록 + `repo_nature` (`"app/cli"` / `"app"` / `"library"`)
- `commit_decisions` / `pr_decisions` / `satd_items` — step 3.5 evidence 의 병렬 소스, step 3.7 foresight 삼각측량 소스
- `negative_space` — 신호 4종, step 3.7 ForesightCard 생성 재료
- `REPO_CONTEXT` / `FILE_HISTORY` — verbatim 인용 가능한 SHA/문서 경로 풀

**step 3.8/4 를 위한 보존**: 위 출력의 **JSON 부분만** Write tool 로 `/tmp/step1_output.json` 에 저장하라 (`=====` 블록 제외). step 4 의 PR 검증 풀과 step 3.8 의 채점 스크립트가 이 파일에서 `pr_decisions` 를 복원한다.

`project_structure` 가 필요하면 `pp.project_structure` 를 추가 출력.

### 2. 카테고리별 파일 읽기 (Read tool)

각 카테고리의 `selected_per_category[<cat>]` 경로 리스트를 Read tool로 순회. 로컬 경로면 그대로, 원격이면 `<repo_root>/<path>` 로 읽는다.

**컨텍스트 절약**: 2,000줄 초과 파일은 fetcher 가 자동 축약한다 (코드 파일 = import/시그니처만, .sql/.prisma = 앞 2,000줄). Read 로 원문 재독이 필요하면 offset/limit 사용.

### 3. 카테고리별 수동 분석

각 카테고리마다 `backend/src/hijack/core/prompts.py` 의 `_CATEGORY_INSTRUCTIONS[<cat>]` 지시문을 참고해 규칙을 추출한다.

**출력 언어**: 생성하는 prose 필드 전부 — `rule`, `reason`, `design_intent`, `anti_patterns`, `file_type_guides`, `checklist`, foresight 카드, probe 기록 — 는 **영어로** 쓴다. 산출물은 examples/ 로 공개되는 글로벌 자산이다 (세션 대화 언어와 무관). evidence 의 headline/quote 와 코드 발췌는 언어 불문 원문 verbatim 유지.

각 **AnalysisRule** 은 다음 필드를 반드시 가진다:

- `rule`: 구체적 규칙 (1문장). **원리 수준으로** — 이 레포 내부 심볼명(클래스/센티널/헬퍼 이름)을 규칙 본문에 넣지 말 것. 심볼은 good_example 에서 인용하고, 규칙 본문은 "그 심볼이 만족시키는 설계 제약"을 기술한다. (다른 프로젝트로 전이 가능해야 함)
  - 휴리스틱: rule 본문에 들어간 식별자가 `good_example` 에도 똑같이 있으면 너무 처방적 — 이름을 example 로 옮기고 rule 은 동작/형태 제약으로 다시 써라.
- `priority`: `"MUST"` (위반 시 PR 거부 수준) 또는 `"SHOULD"`. 애매하면 SHOULD.
- `confidence`: `"high"` / `"medium"` / `"low"`
- `ref_files`: 실제 파일 경로 + **라인 번호**. `"path.py:42"` 또는 `"path.py:42-58"`. (Read 결과에 라인 번호 있음. 또는 `grep -n`.)
- `good_example`: ✅ ref_files 에서 **그대로 복사한 실제 코드** (3-10줄). paraphrase 금지.
- `bad_example`: ❌ **실제 안티패턴 코드**. `"# 이렇게 하지 말 것"` 식 주석 설명 금지.
- `reason`: 1문장 intent gist (≤150자). evidence 의 quote 를 재진술하지 말 것. evidence 가 없으면 `[no-evidence]` 접두.
- `layer`: step 1 출력의 `layer=` 값을 그대로 (추측 금지). 여러 레이어에 걸치면 `"shared"`.
- `rationale_tier`: `"cited"` / `"corroborated"` / `"speculative"`.
  - `"cited"`: evidence 배열이 비어 있지 않고 verbatim 인용 (step 4 에서 엔진이 ref 를 진실 풀과 대조해 재검증한다 — 가짜 ref 는 speculative 로 강등됨).
  - `"corroborated"`: 독립 코드 신호 2개 이상이 일관되게 뒷받침 (ref_files 2곳 이상 + 동일 패턴).
  - `"speculative"`: 그 외 LLM 추론.
  - **cited 만 MUST 유지 가능** — corroborated/speculative MUST 는 step 4 의 `normalize_rationale_tier` 가 기계적으로 SHOULD 강등한다.
- `evidence`: **이 도구의 핵심 필드.** 구조:

```json
"evidence": [
  {
    "kind": "commit" | "revert" | "doc" | "pr",
    "ref": "<FILE_HISTORY 의 short SHA | REPO_CONTEXT 의 문서 경로 | pr_decisions 의 PR#123·issue#456>",
    "headline": "<커밋 subject / 문서 섹션 제목 / PR title — verbatim, ≤120자>",
    "quote": "<커밋 body / 문서 문단 / PR body·maintainer 코멘트의 실질 문장 — verbatim, ≤500자>",
    "intent_kind": "rejection" | "constraint" | "incident" | "preference" | null
  }
]
```

**evidence 규칙 (위반 시 규칙 자체를 드롭하라)**:
- `ref` 는 step 1 출력에 실제로 등장한 SHA/경로/PR ref 만. **발명 = 최악의 실패.**
- headline/quote 는 verbatim 복사 — 시니어의 목소리를 보존하는 게 목적. paraphrase 금지.
- 증거가 없으면 `evidence: []` + `confidence: "low"` + reason 에 `[no-evidence]`. 패딩 금지 — 빈 증거가 가짜 인용보다 훨씬 낫다.
- 매칭 상세 절차는 step 3.5.

**MUST/SHOULD 캘리브레이션**: 목표 MUST 비율 30-40%. 초과 시 "위반해도 PR 거부까지는 아닌 것"부터 SHOULD 로 강등. evidence 없는 MUST 는 어차피 시스템이 SHOULD 로 자동 강등한다 — cited MUST 만 살아남는다.

**CategoryResult 부가 필드**: `design_intent` (2-3문장), `anti_patterns` (list[dict]: `{"pattern","reason","alternative"}`), `file_type_guides` (dict), `checklist` (list).

#### Few-shot — 이런 규칙을 만들어라

✅ **GOOD** (모양 학습용):

```json
{
  "rule": "subprocess.run 은 반드시 capture_output=True + text=True 조합으로 호출",
  "priority": "MUST",
  "confidence": "high",
  "ref_files": ["src/hijack/core/fetcher.py:229-237"],
  "good_example": "result = subprocess.run(\n    ['git', 'clone', '--depth=1', target, tmpdir],\n    capture_output=True,\n    text=True,\n)\nif result.returncode != 0:\n    raise FetchError(FETCH_001, f'git clone 실패: {result.stderr.strip()}')",
  "bad_example": "subprocess.run(['git', 'clone', target, tmpdir])",
  "reason": "returncode/stderr 접근 못하면 실패 원인 사용자 전달 불가 — 디버깅 블라인드",
  "layer": "backend"
}
```

❌ **BAD** (이렇게 쓰지 말 것):

```json
{
  "rule": "좋은 코드를 짜야 한다",                    // 너무 추상적
  "priority": "MUST",                              // 판단 불가한데 MUST
  "ref_files": ["src/main.py"],                    // 라인 번호 없음
  "good_example": "# 좋은 예시",                    // 주석 (실제 코드 아님)
  "bad_example": "# 이렇게 하지 말 것",              // 설명문
  "reason": "중요하니까"                            // 설계 의도 없음
}
```

원리 vs 카고컬트:

```
# ❌ 카고컬트 (특정 심볼 처방)
rule: "Use the USE_CLIENT_DEFAULT sentinel for unset request-level params"

# ✅ 원리
rule: "Per-call optional parameters must distinguish 'unset' from 'explicit None' via a dedicated sentinel object, so caller-level과 client-level 디폴트가 깔끔히 fall through"
```

### 3.5. Evidence chain 채우기 (commit_decisions + pr_decisions + satd_items 활용)

step 1 의 `commit_decisions` / `pr_decisions` / `satd_items` 중 하나라도 `null` 이 아니면, 각 규칙의 `evidence` 필드를 시니어의 실제 결정 인용으로 채워라. **이게 이 도구의 핵심 차별점** — rule 의 reason 을 LLM 이 paraphrase 하는 게 아니라 시니어가 직접 남긴 commit body / PR body / 거절 코멘트 / SATD 주석을 verbatim 으로 surface 한다.

셋은 **병렬 evidence 소스**다. 독립적으로 탐색하고, 같은 규칙에 여러 소스에서 evidence 가 발견되면 가장 강한 1-2개를 골라 `evidence` 배열에 담는다.

**소스별 가중치**:
- `pr_decisions.decisions` 중 `intent_kind == "rejection"` 또는 `"incident"` 는 특히 높은 가중치 (시니어가 실제로 거절하거나 사고 후 revert 한 결정 = 가장 직접적인 "하면 안 된다" 신호).
- `commit_decisions.commits` 는 채택된 결정의 이유 — "왜 이렇게 했는가" 소스.
- `pr_decisions` 의 `"rejection"` / `"incident"` 는 거절된 대안의 이유 — "왜 저렇게 하면 안 되는가" 소스.
- `satd_items` (TODO/FIXME/XXX/HACK) 는 시니어가 코드에 직접 남긴 인라인 한계/의도 — "여긴 이래서 이렇게 뒀다" 소스. 규칙의 의도와 같은 주석이 있을 때만 인용.

**`commit_decisions.commits` 구조** (각 entry):
- `sha` (12자), `subject`, `date` (ISO), `body_excerpt` (≤800자), `matched_patterns`, `file_paths`

**`pr_decisions.decisions` 구조** (각 entry):
- `ref` (`"PR#123"` / `"issue#456"`), `title`, `date`, `body_excerpt` (≤800자), `matched_patterns`, `maintainer_comment` (거절 코멘트 우선 선택됨), `intent_kind` (`"rejection"` | `"incident"` | `"preference"`), `diff_excerpt` — 거절/사고 PR 의 실제 diff 발췌 (rejection/incident 만, 빈 문자열 가능)

**`satd_items.items` 구조** (각 entry):
- `ref` (`"src/foo.py:42"` — 인용 시 이 문자열 그대로), `tag` (`"TODO"` | `"FIXME"` | `"XXX"` | `"HACK"`), `text` (주석 본문 ≤200자), `context` (주변 컨텍스트: 연속 주석 + 직후 코드, ≤700자 — 규칙 매칭 판단용. quote 는 여전히 text 또는 context 의 주석 부분에서 발췌)

**규칙 별 evidence 채우는 절차**:

1. 룰의 `ref_files` 에 등장한 파일들 (`path:line` 의 path 부분만) 추출
2. **commit 소스**: `commit_decisions.commits` 중 `file_paths` 와 교집합 있는 commit 필터
3. **PR/issue 소스**: `pr_decisions.decisions` 중 `title + body_excerpt + maintainer_comment` 가 이 규칙의 의도와 맞는 entry 필터. `rejection`/`incident` 우선.
4. 두 소스 합산, 가장 관련도 높은 1-2개 선택:

   - commit 소스: `{"kind": "commit", "ref": "<sha[:7]>", "headline": "<subject>", "quote": "<body_excerpt ≤500자>", "intent_kind": ...}`
   - PR/issue 소스: `{"kind": "pr", "ref": "<PR#123 그대로>", "headline": "<title>", "quote": "<body_excerpt 또는 maintainer_comment ≤500자>", "intent_kind": "<intent_kind 그대로>"}`
   - SATD 소스: `{"kind": "comment", "ref": "<path:line 그대로>", "headline": "<tag>", "quote": "<text 또는 context 의 주석 부분에서 발췌, ≤500자>"}` — `ref` 는 `satd_items` 의 값을 **그대로** 써라 (지어내면 fake_citation 으로 강등됨).

4.5. (file 매칭 실패 시 fallback — **SEMANTIC INTENT 매칭**) step 2 의 file_paths 교집합이 비었으면:
     `commit_decisions.commits` 의 `subject + body_excerpt` 를 직접 읽고, **시니어가 기록한 결정의 WHY 가 이 rule 의 reason 과 같은 의도**인 commit 을 1개 고른다. 같은 파일을 안 건드렸어도 OK. `pr_decisions.decisions` 도 동일하게 semantic intent 매칭 가능.

     예시 (의도 일치):
       rule reason: "한 번에 끊으면 사용자 마이그레이션 비용 폭발. warning + 명시적 대안 안내로 옮길 시간을 줘야 한다."
       commit body: "Deprecate `app=...` in favour of explicit `WSGITransport`... rather than rem[oving]"
       → 매칭 OK (둘 다 같은 deprecation discipline).

     ❌ 약한 매칭 / paraphrase 필요 / file 도 의도도 안 맞음 → **[no-evidence]**. 1초라도 망설여지면 skip.

5. 두 소스 모두 매칭 없으면 `evidence: []` 유지 + `reason` 앞에 `[no-evidence]` prefix

**`intent_kind` 매핑** (matched_patterns → intent_kind):

| matched_patterns 에 포함 | intent_kind |
|---|---|
| `rejected`, `abandoned`, `switched from` | `rejection` |
| `reverted because`, `regression` | `incident` |
| `instead of`, `rather than`, `decided to`, `tried`, `considered`, `decided not to`, `originally...now`, `switched to`, `as opposed to`, `to avoid`, `to prevent` | `preference` |
| `due to`, `motivated by` | `constraint` |

여러 패턴 매치 시 강한 것 우선: rejection > incident > preference. 모르면 `null`.

**가드레일**:
- `quote` 는 반드시 verbatim. 길면 `[…truncated]` 표시 후 잘라라.
- SHA/PR ref 만들지 마라. step 1 출력에 있는 것만.
- 매칭 없으면 evidence 비우고 [no-evidence]. 거짓 evidence > 빈 evidence 가 아니다 — 그 반대다.
- **evidence 로 채택한 entry 에 `diff_excerpt` 가 있으면, 그 규칙의 `bad_example` 은 LLM 이 창작하지 말고 diff 의 추가(+) 라인에서 verbatim 발췌하라** — "메인테이너가 실제로 거절한 코드" 표시(ref 인용)와 함께. diff 가 규칙 의도와 무관하면 발췌하지 않아도 된다 (강제 아님 — 의도 일치할 때만).

### 3.7. Foresight 가설 생성 + 삼각측량

step 1 의 `negative_space` 신호 4종과 `pr_decisions` 를 추측 재료로 **ForesightCard** 가설을 생성한다. 네(현재 세션 LLM)가 직접 수행하는 추론 절차다.

**입력 신호 (`negative_space`)**:
- `dep_count` — 런타임 의존성 수 (0이면 stdlib-only 의지 가능성)
- `direct_impl_hints` — stdlib만으로 구현된 파일 경로 목록
- `public_ratio` — public 심볼 비율 (낮으면 의도적 API 은닉 가능성)
- `has_all_discipline` — `__all__` 정의 여부
- `deprecation_patterns` — DeprecationWarning 패턴 + git history 항목
- `layer_import_violations` — 레이어 간 역방향 import

**추가 입력 신호 (`pr_decisions`)**:
- 각 entry 의 `title`, `body_excerpt`, `maintainer_comment`, `intent_kind`, `diff_excerpt`
- `rejection` entry → **rejection 패턴 가설**의 직접 원천, `incident` entry → **incident 패턴 가설**의 직접 원천

**가설 생성 절차**:

1. 각 신호에서 "왜 이렇게 짰는가?" 설계 의도 가설을 초안 작성. `pr_decisions` 가 있으면 rejection/incident entry 를 반드시 읽고 가설 소재로 쓸지 판단.
2. 각 가설에 **삼각측량** (필수):
   - "이 가설이 참이면 레포에 나타나야 할 독립 신호"를 최소 2개 나열
   - Read/Grep/Bash 로 실제 레포에서 확인. `pr_decisions` entry 도 독립 신호 출처 가능 (확인된 ref 인용).
   - **tier 판정**: 확인된 독립 신호 2개 이상 → `"corroborated"`, 1개 이하 → `"speculative"`. rejection/incident 1개 + 코드 신호 1개 조합도 `"corroborated"` 인정.
3. 각 카드에 `falsification` (반증 조건) 명시: "무엇이 발견되면 이 가설이 기각되는가?"

**가드레일**:
- `signals` 는 확인된 사실만. 해석("dep_count=2 이므로 stdlib 지향")은 신호가 아님 — 신호는 `"negative_space.py:1-18 — 외부 패키지 import 없음 (ast/pathlib/re만)"` 같은 관찰.
- 가설 날조 금지. 신호 불충분이면 카드를 만들지 마라 — **카드 0개도 정상 출력**.
- ForesightCard 는 **MUST 자격 없음**. foresight.md 에만 저장되는 고려 사항. CLAUDE.md / system-prompt.md 제약으로 격상 금지.

**ForesightCard 형식** (step 4 ANALYSIS JSON 의 `foresight` 섹션):

```json
{
  "hypothesis": "왜 이렇게 짰는지 추론 (1-2문장)",
  "signals": ["path.py:42-50 — 관찰된 사실", "other.py:10 — 두 번째 독립 신호"],
  "falsification": "외부 의존성 3개 이상 추가된 커밋이 발견되면 기각",
  "tier": "corroborated",
  "layer": "shared"
}
```

### 3.8. Foresight 채점 (score_foresight + LLM 보완 판단)

step 3.7 의 카드를 레포 docs 및 `pr_decisions` 와 대조해 채점하고 `measurement.json` 에 저장한다. step 4 저장 **이후** 수행해도 된다 (session_dir 필요).

사전 준비:
- Read tool 로 대상 레포 `README.md`, `docs/*.md`, `CHANGELOG.md` 를 수집해 `/tmp/repo_docs.txt` 에 저장 (없으면 빈 파일).
- step 1 JSON 이 `/tmp/step1_output.json` 에 저장돼 있어야 함.

1. **결정론 채점**:

```bash
cd <ENGINE_ROOT>
python -c "
import json, sys, pathlib
sys.path.insert(0, 'backend/src')
from hijack.core.measure import score_foresight
from hijack.core.pr_archaeology import PRDecisions
from hijack.core.models import ForesightCard

cards = [ForesightCard(**c) for c in json.load(open('/tmp/analysis.json', encoding='utf-8')).get('foresight', [])]
repo_docs = pathlib.Path('/tmp/repo_docs.txt').read_text(encoding='utf-8') if pathlib.Path('/tmp/repo_docs.txt').exists() else ''
pd_raw = json.loads(pathlib.Path('/tmp/step1_output.json').read_text(encoding='utf-8')).get('pr_decisions')
pd = PRDecisions.from_json(pd_raw) if pd_raw else None
print(json.dumps(score_foresight(cards, repo_docs, pd), ensure_ascii=False, indent=2))
"
```

2. **LLM 보완 판단** — `verdict == "unconfirmed"` 카드를 직접 검토: hypothesis + signals + falsification 을 읽고 레포 코드 또는 `pr_decisions` 에서 반증/확인 근거를 찾아 `"confirmed"` / `"refuted"` 로 갱신 (근거 없으면 유지). 결정론 채점은 `"refuted"` 를 반환하지 않는다 — refuted 는 이 단계에서만 부여 가능.

3. **저장** — verdict 를 카드에 심어 `session.json` 을 재저장한다 (measure 가 세션만으로 자급하도록; measurement.json 만 저장하고 흘리는 방식은 폐기):

```bash
cd <ENGINE_ROOT>
python -c "
import json, sys
sys.path.insert(0, 'backend/src')
from hijack.core.measure import calc_session_metrics, stamp_foresight_verdicts, write_measurement
from hijack.core.pr_archaeology import PRDecisions
from hijack.core.models import SessionResult
from pathlib import Path

session_dir = Path('<session_output_dir>')  # step 4 의 [DONE] 경로
session_path = session_dir / 'session.json'
session = SessionResult.from_json(json.loads(session_path.read_text(encoding='utf-8')))

final_scores = [
    # step 3.8-2 의 최종 verdict 목록으로 교체 (cards 와 같은 순서/개수):
    # {'hypothesis': '...', 'verdict': 'confirmed'},
]
session.foresight_cards = stamp_foresight_verdicts(session.foresight_cards, final_scores)
session_path.write_text(json.dumps(session.to_json(), indent=2, ensure_ascii=False), encoding='utf-8')

pd_raw = json.load(open('/tmp/step1_output.json', encoding='utf-8')).get('pr_decisions')
pd = PRDecisions.from_json(pd_raw) if pd_raw else None
result = calc_session_metrics(session, pr_decisions=pd)  # foresight_scores 는 카드 verdict 에서 자동 파생
write_measurement(result, session_dir)
print('[DONE] session.json verdict-stamped + measurement.json saved to', session_dir)
"
```

**가드레일**: verdict 는 `session.json` 의 `foresight_cards[].verdict` 필드(T-030 스키마 내 기존 필드)에 저장한다 — 새 top-level 키 추가가 아니므로 스키마 재확장이 아니다. `measurement.json` 의 `foresight_scores` 는 세션에서 파생되므로 수기 대입 불필요. `foresight_cards` 빈 리스트면 채점 생략 (`foresight_scores: []`).

### 4. SessionResult 조립 + 저장 (Bash tool)

분석 결과를 **임시 JSON 파일** (Write tool, `/tmp/analysis.json`)에 저장 후 실행. 구조:

```json
{
  "categories": [
    {
      "category": "architecture",
      "design_intent": "...",
      "rules": [ { "rule": "...", "priority": "MUST", "confidence": "high", "ref_files": ["path.py:42"], "good_example": "...", "bad_example": "...", "reason": "...", "layer": "shared", "evidence": [], "rationale_tier": "cited" } ],
      "anti_patterns": [],
      "file_type_guides": {},
      "checklist": []
    }
  ],
  "foresight": [ { "hypothesis": "...", "signals": ["path.py:10 — 사실"], "falsification": "...", "tier": "corroborated", "layer": "shared" } ]
}
```

```bash
cd <ENGINE_ROOT>
python -c "
import dataclasses, json, sys, datetime, tomllib
sys.path.insert(0, 'backend/src')
from pathlib import Path
from hijack.core.fetcher import fetch_source
from hijack.core.preprocessor import build_preprocess_result
from hijack.core.models import AnalysisRule, CategoryResult, ForesightCard, SessionResult
from hijack.core.analyzer import assign_rationale_tier, normalize_rationale_tier
from hijack.core.exemplar_check import is_verbatim_excerpt
from hijack.core.exemplars import select_exemplars
from hijack.core.style_fingerprint import extract_style
from hijack.core.pr_archaeology import PRDecisions
from hijack.core.satd import SatdItems
from hijack.core.generator import write_output
from hijack.core.session import create_session_id

TARGET = '<TARGET>'
OUTPUT = '<OUTPUT_DIR>'
ANALYSIS = json.load(open('/tmp/analysis.json', encoding='utf-8'))

# history_depth 는 step 1 과 반드시 동일하게 — 진실 풀(historic SHA)이 좁아지면
# step 1 에서 인용한 SHA 가 fake 로 오판된다. (캐시 덕에 재수집 비용 미미)
files, root = fetch_source(TARGET, history_depth=30)

pyproject_path = root / 'pyproject.toml'
pyproject_toml = None
if pyproject_path.exists():
    with open(pyproject_path, 'rb') as f:
        pyproject_toml = tomllib.load(f)

pp = build_preprocess_result(files, root, pyproject_toml=pyproject_toml)

# 증거 검증 풀 — evidence.classify_rule 이 가짜 인용을 걸러내는 데 사용
historic = set()
for f in files:
    if f.history:
        for c in (*f.history.commits, *f.history.reverts):
            if c.sha:
                historic.add(c.sha)

valid_files = {f.path.as_posix() for f in files}

# PR decision-trail — step 1 이 저장한 pr_decisions 를 복원.
# session.pr_decisions 에 실어 세션에 영구 저장(measurement/diff/regen 이 실데이터로 동작),
# 동시에 kind='pr' evidence 검증용 valid_pr_refs 풀을 파생한다.
pr_decisions = None
valid_pr_refs = None
# SATD (W2) — step 1 이 저장한 satd_items 를 복원. session 에 실어 영구 저장하고,
# kind='comment' evidence 검증용 valid_comment_refs 풀(정확 path:line)을 파생한다.
satd_items = None
valid_comment_refs = None
step1_path = Path('/tmp/step1_output.json')
if step1_path.exists():
    step1 = json.loads(step1_path.read_text(encoding='utf-8'))
    pd_raw = step1.get('pr_decisions')
    if pd_raw:
        pr_decisions = PRDecisions.from_json(pd_raw)
        valid_pr_refs = {d['ref'].casefold() for d in pd_raw.get('decisions', []) if d.get('ref')} or None
    satd_raw = step1.get('satd_items')
    if satd_raw:
        satd_items = SatdItems.from_json(satd_raw)
        valid_comment_refs = {i['ref'] for i in satd_raw.get('items', []) if i.get('ref')} or None

def _tiered(raw_rules):
    rules = [AnalysisRule.from_json(r) for r in raw_rules]  # (**r) 금지 — evidence dict 가 Evidence 로 변환 안 됨
    rules = assign_rationale_tier(
        rules,
        valid_shas=historic or None,
        valid_doc_paths={d.path for d in pp.repo_docs} or None,
        valid_file_paths=valid_files or None,
        valid_pr_refs=valid_pr_refs,
        valid_comment_refs=valid_comment_refs,
    )
    rules = normalize_rationale_tier(rules)  # cited 만 MUST 유지
    # W4a — good_example 이 실제 레포 코드의 verbatim 발췌인지 관찰 지표.
    return [
        dataclasses.replace(r, exemplar_verbatim=is_verbatim_excerpt(r.good_example, files))
        if r.good_example else r
        for r in rules
    ]

categories = [
    CategoryResult(
        category=cat['category'],
        design_intent=cat['design_intent'],
        rules=_tiered(cat['rules']),
        anti_patterns=cat['anti_patterns'],
        file_type_guides=cat.get('file_type_guides', {}),
        checklist=cat.get('checklist', []),
        raw_llm_output='(skill-mode)',
    )
    for cat in ANALYSIS['categories']
]

foresight_cards = [ForesightCard(**c) for c in ANALYSIS.get('foresight', [])]

session = SessionResult(
    session_id=create_session_id(TARGET),
    target=TARGET,
    model='claude-code-skill-mode',
    timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
    selected_files=[f.path.as_posix() for f in files],
    categories=categories,
    analysis_duration_seconds=0.0,
    project_structure=pp.project_structure,
    files_by_layer={k: len(v) for k, v in pp.by_layer.items()},
    historic_shas=sorted(historic),
    repo_doc_paths=[d.path for d in pp.repo_docs],
    exemplars=select_exemplars(files, repo_root=root),   # Python 레포만 결과 나옴
    style_fingerprints=extract_style(files),              # 레이어별 negative-space/치환 통계
    pr_decisions=pr_decisions,                            # 0.3.0 decision-trail — 세션에 영구 저장
    satd_items=satd_items,                                # W2 SATD — comment kind 진실 풀
    foresight_cards=foresight_cards,
    repo_nature=pp.repo_nature,
)
write_output(session, Path(OUTPUT))
print(f'[DONE] {Path(OUTPUT) / session.session_id}')
"
```

`write_output` 이 자동으로: evidence 없는 MUST 강등 → MUST 비율 lint → exemplars.md / 레이어별 invariants / foresight.md 렌더링까지 수행한다.

### 5. 행동 probe (선택)

evidence 만으로는 "규칙이 그럴듯하다"까지만 보장된다. probe 는 "규칙이 실제로 약모델의 행동을 바꾼다"를 재현 가능하게 확인하는 단계다. **엔진(models.py/generator.py/measure.py)은 기록+렌더만 담당** — 설계/실행은 이 세션의 일이다.

1. **대상 선정**: incident/rejection evidence 가 있는 MUST/SHOULD 규칙 중, **오용/경계 경로**(재진입, 잘못된 입력, 수명주기 위반)에서 행동이 갈릴 수 있는 것만 골라라. happy-path 규칙이나 상식 수준 함정은 probe 하지 마라 — 실측상 판별이 안 된다.
   - **지름길-갭 기준 (필수)**: 규칙이 없을 때 약모델의 *기본 구현이 지름길*인 규칙만 표적이다 (예: 전량 버퍼링, 경고 없는 alias, 무증상 진행). 약모델 기본이 이미 견고 패턴인 규칙(예: abspath-containment 방식 경로 검증)은 규칙이 행동적으로 잉여라 판별이 안 된다 — 반직관 함정이라도 견고 기본에 흡수되면 소용없다. **"이 태스크를 규칙 없이 시키면 약모델이 어떤 지름길을 택할까"를 먼저 예측하고, 지름길이 안 그려지면 그 규칙은 건너뛰어라.** 추출 품질(cited 비율, incident 수)과 판별력은 별개 축이다 — 하드닝 라이브러리 규칙은 추출 품질이 높아도 대부분 견고 패턴/보안 상식이라 probe 표적으로 나쁘다.
2. **프로토콜**:
   - 규칙을 모르는 상태로 풀 수 있는 중립 태스크를 설계한다 (함정 힌트 금지 — "재진입 주의" 같은 문구를 태스크에 넣지 말 것).
   - Agent tool 로 약모델(`haiku`) 2팔을 돌린다: control(규칙 미주입) / treatment(규칙 주입).
   - 결정론 하네스로 오용 경로를 자극해 채점한다 (예: 이중 enter, `float('inf')` 입력, 잘못된 타입).
   - **하네스 자기검증 (필수)**: 하네스 판정을 그대로 믿고 verdict 를 찍지 마라 — 실측상 2세션 연속 하네스 결함이 거짓 판별을 만들었다 (abspath 가 OS 드라이브를 붙여 startswith 오탐, base 안 경로를 escape 로 오분류). 가드 두 개: (a) 채점은 파일시스템/OS 상태에 닿지 말고 **반환값·예외만** 검사하라 — 경로 비교가 필요하면 실존 tmpdir 기준으로. (b) verdict 확정 전에 **양 팔의 solution 코드를 직접 읽고** 하네스 판정과 코드 로직이 일치하는지 확인하라. 불일치하면 하네스를 고치고 재채점한다.
   - 두 팔의 행동이 실제로 갈리면 `verdict="discriminated"`, 안 갈리면 `"not_discriminated"`.
3. **기록**: 해당 규칙의 `probe` 필드에 다음 구조의 dict 를 채우고 `SessionResult` 를 재저장 + `write_output` 을 재실행한다:

```json
{
  "task": "probe 태스크 한 줄 요약",
  "verdict": "discriminated",
  "control_behavior": "control 팔에서 관측된 행동 (짧게)",
  "treatment_behavior": "treatment 팔에서 관측된 행동",
  "model": "haiku"
}
```

4. **정직 가드**: 하네스 출력을 그대로 기록하라 — 요약을 각색하지 말 것. 판별 실패(`not_discriminated`)도 있는 그대로 기록해 "probe 를 안 돌림"과 구분되게 하라.

### 6. 자체 Critic 재평가 (권장 — 품질 향상)

모든 카테고리 규칙 생성이 끝난 뒤(= step 4 전에), 스스로 다시 훑어라:

**DROP** (규칙 제거):
- 너무 일반적 ("좋은 코드를 짜자", "일관성 유지")
- 카테고리 간 사실상 중복
- ref_files / good_example 이 약함 (근거 부족)

**DOWNGRADE MUST → SHOULD**:
- 위반해도 실제 PR 거부 수준 아님 (강한 선호에 불과) / 팀 관례 성격
- **목표 MUST 비율 30-40%**. 초과 시 재평가.
- **카테고리당 MUST > 50% 면 강제 강등**: 가장 PR-rejection 가능성 낮은 것부터 — (a) perf 최적화 (큰 입력에서만 의미), (b) readability/일관성, (c) 대안이 여전히 작동하는 layering 선호. 반대로 "어기면 5xx 누출 / OOM / 보안 boundary 침범" 같은 correctness/safety 는 MUST 유지.
- **cited MUST 도 자동 강등 대상 아님** — 시스템은 no-evidence MUST 만 강등한다. cited MUST 의 priority 검증은 이 단계가 유일한 방어선. 시니어가 "to avoid O(n²)" 라 한 perf rule 을 cited 라고 무비판적으로 MUST 로 두지 말 것 — commit 의 동기(perf vs 안전)와 priority 의 의미(PR 거부 vs 선호)는 별개.

**KEEP as-is**: 고품질 규칙은 그대로.

### 7. 완료 안내

```
[DONE] 분석 완료
세션: <output>/<session_id>/
통합: <output>/integrated/CLAUDE.md (+ exemplars.md, 레이어별 .md)
레포 성격: <repo_nature> (출력 파일 헤더에 맥락 명시됨)
Foresight: <output>/integrated/foresight.md  <- foresight_cards 있을 때만
측정: <output>/<session_id>/measurement.json  <- cited/MUST 비율 + foresight 채점

다음:
  - integrated/CLAUDE.md 를 대상 레포에 복사하면 에이전트가 해당 스타일로 코딩
  - foresight.md 는 강제 제약 아닌 설계 의도 추론 — 참고용
  - measurement.json 에서 cited 비율 / MUST 비율 / foresight 정답률 확인
  - 다른 세션과 비교: python -c "from hijack.cli import cli; cli()" diff <s1> <s2>
```

## 가드레일

- **컨텍스트 관리**: 카테고리당 12개 이하 파일. 초과 시 `--path` 서브디렉토리 권고.
- **필수 필드**: `rule`, `priority`, `layer` 누락 시 해당 규칙 드롭.
- **레이어 태깅**: step 1 이 출력한 `layer` 값이 권위. 추측으로 덮어쓰지 말 것.
- **evidence.ref**: step 1 출력에 등장한 SHA/문서 경로/PR ref 만. 발명 금지 — 가짜 인용 1개가 빈 인용 100개보다 나쁘다.
- **good/bad_example**: 실제 레포 코드에서 추출. 상상 금지 (이 프로젝트의 핵심 차별점). 단 rejection PR 의 `diff_excerpt` 는 "실제 거절된 코드"이므로 bad_example 소스로 최우선.
- **TS 레포 한계**: exemplars/negative-space 자동 추출은 Python 전용. TS 레포는 규칙+evidence 는 정상 동작하나 exemplars.md 가 비니, 필요 시 대표 함수 2-3개를 수동으로 골라 good_example 을 풍부하게 채워라.
- **덮어쓰기**: 기존 `<output>/integrated/` 존재 시 사용자 확인 후 진행.

## 트러블슈팅

**파일이 너무 많아 컨텍스트 초과 위험**: `fetch_source(TARGET, subpath='<subdir>')` 로 한정.

**분석 결과가 일반적/피상적**: good/bad_example 이 실제 코드가 아니라는 뜻. 파일을 다시 읽고 구체 코드 발췌.

**FILE_HISTORY 가 비어 있음**: 원격 clone 이 `--filter=blob:none` 이라 로그는 있음. 로컬 경로인데 비면 git 레포가 아닌 것 — evidence 는 REPO_CONTEXT (docs) 로만 채우고 나머지는 [no-evidence].

**pr_decisions 가 null**: gh CLI 미설치/미인증이거나 GitHub URL 이 아님. commit 마이닝만으로 계속 진행 (동작 저하 수용). `gh auth status` 로 확인.

**JSON 특수문자 이스케이프 실패**: 분석 결과는 반드시 임시 JSON 파일 (Write tool) 경유. Bash heredoc 에 코드 inline 금지.

**같은 URL 반복 분석 시 느림**: fetch_source 는 자동 캐시 (`~/.cache/code-hijack/repos/<hash>/`). 강제 refresh 는 `HIJACK_NO_CACHE=1`, 위치 override 는 `HIJACK_CACHE_DIR=/path`.

**Windows 터미널 mojibake**: Python `print()` 에 이모지/화살표 금지, ASCII 로 대체 (예: `[DONE]`).
