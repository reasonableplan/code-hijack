---
name: code-hijack
description: 시니어 코드베이스를 분석해 AI 에이전트용 코딩 규칙 문서(CLAUDE.md + layer별 .md + system-prompt.md)를 자동 추출한다. ANTHROPIC_API_KEY 없이 현재 Claude Code 세션이 LLM 역할을 수행하는 skill 모드.
---

# code-hijack Skill Mode

너는 지금 **code-hijack 도구의 skill 모드 LLM** 역할을 수행한다.
CLI 모드(`code-hijack analyze`)가 Anthropic API를 호출해 하는 일을, 너의 현재 세션 컨텍스트 안에서 직접 처리한다.

## 역할

입력된 TARGET 레포(로컬 경로 또는 GitHub URL)의 소스 파일을 수집·분류·분석하고, AI 에이전트가 해당 스타일로 코드를 짜게 하는 규칙 문서를 생성한다.

## 입력

- **TARGET**: 사용자가 `/code-hijack <target>` 으로 전달한 인자. 로컬 경로 또는 GitHub URL.
- **옵션** (선택):
  - `--path <subdir>` — 모노레포 서브디렉토리 한정
  - `--categories <list>` — 분석 카테고리 콤마 구분 (기본: architecture,coding_style,api_design)
  - `--output <dir>` — 출력 디렉토리 (기본: `<target>/docs/hijacked/`)

## 출력

- `<output>/<session_id>/meta.md` — 메타데이터 (세션 ID, 대상, 선별 파일, 레이어 분포)
- `<output>/<session_id>/<category>.md` — 카테고리별 raw 분석 (1 파일/카테고리)
- `<output>/<session_id>/session.json` — 구조화 데이터 (diff 재사용)
- `<output>/integrated/CLAUDE.md` — 진입점 + Top MUST 규칙 + 레이어 가이드
- `<output>/integrated/{frontend,backend,database,devops,shared}.md` — 레이어별 규칙
- `<output>/integrated/system-prompt.md` — 에이전트 시스템 프롬프트

## 실행 순서

### 1. 파일 수집 + 선별 (Bash tool)

```bash
cd <project_root>
python -c "
import json, sys
sys.path.insert(0, 'backend/src')
from hijack.core.fetcher import fetch_source
from hijack.core.preprocessor import build_preprocess_result, select_files_for_category
from hijack.core.archaeology import extract_commit_decisions

TARGET = '<TARGET>'
CATEGORIES = ['architecture', 'coding_style', 'api_design']  # 또는 사용자 지정

files, root = fetch_source(TARGET, history_depth=30)  # depth=30 (default 3) — depth=10 대비 매칭 가능 commits ~7배 ↑ 확인됨 (httpx v4, 2026-05-06). depth=50 부터는 ROI 떨어짐.
pp = build_preprocess_result(files, root)
selected = {cat: [f.path.as_posix() for f in select_files_for_category(pp, cat, max_files=12)] for cat in CATEGORIES}
cd = extract_commit_decisions(files)

print(json.dumps({
    'repo_root': root.as_posix(),
    'total_files': len(files),
    'by_layer': {k: len(v) for k, v in pp.by_layer.items()},
    'selected_per_category': selected,
    'project_structure': pp.project_structure,
    'commit_decisions': cd.to_json() if cd.has_signal else None,
}, indent=2, ensure_ascii=False))
"
```

위 JSON을 파싱해 각 카테고리의 선별 파일 목록 + `commit_decisions` (있으면) 을 얻는다. `commit_decisions` 는 step 3.5 에서 evidence 채울 때 사용.

### 2. 카테고리별 파일 읽기 (Read tool)

각 카테고리의 `selected_per_category[<cat>]` 경로 리스트를 Read tool로 순회. 로컬 경로면 그대로 읽고, git clone 된 tmp 경로면 `<repo_root>/<path>` 로 읽는다.

**컨텍스트 절약 팁**: 2,000줄 초과 파일은 `fetch_source` 가 이미 import/시그니처만 추출해 `SourceFile.content` 에 담아둔다. 필요 시 1번에서 `f.content` 를 함께 출력하도록 수정.

### 3. 카테고리별 수동 분석

각 카테고리마다 `backend/src/hijack/core/prompts.py` 의 `_CATEGORY_INSTRUCTIONS[<cat>]` 지시문을 참고해 규칙을 추출한다.

각 **AnalysisRule** 은 다음 필드를 반드시 가진다:

- `rule`: 구체적 규칙 (1문장)
- `priority`: `"MUST"` (위반 시 PR 거부 수준) 또는 `"SHOULD"` (강한 권장). 애매하면 SHOULD.
- `confidence`: `"high"` / `"medium"` / `"low"`
- `ref_files`: 근거가 된 실제 파일 경로 + **라인 번호**. 형식: `"path.py:42"` 또는 범위 `"path.py:42-58"`. 라인 번호 없이 파일명만 쓰지 말 것.
- `good_example`: ✅ `ref_files` 에서 **그대로 복사한 실제 코드** (3-10줄). 요약/paraphrase 금지.
- `bad_example`: ❌ **실제 안티패턴 코드**. 주석으로 "이렇게 하면 안 됨" 설명 금지. 구체적 위반 코드 형태로.
- `reason`: 이 규칙이 왜 존재하는지 (1문장 intent gist, ≤150자)
- `layer`: `"frontend"` / `"backend"` / `"db"` / `"devops"` / `"shared"`
- `evidence` (선택, 강력 권장): 시니어의 결정 흔적을 verbatim 인용. step 1 의 `commit_decisions` 에서 채움. step 3.5 참조. 못 채우면 `[]` + `reason` 에 `[no-evidence]` prefix.

**good/bad_example 품질 기준 (critical):**

```
# ✅ 올바른 bad_example — 실제 위반 코드
bad_example: 'eval(user_input)'

# ❌ 틀린 bad_example — 주석으로 설명
bad_example: '# user input 을 eval 로 실행 (금지)'
```

**MUST/SHOULD 캘리브레이션**: 10 규칙 중 MUST 는 3-4개가 정상. MUST 비율 60% 초과면 재평가 필수.

**rule 본문은 원리 (PRINCIPLE OVER PRESCRIPTION)** — 이 레포 내부 클래스/함수/센티넬/헬퍼 이름을 rule 본문에 그대로 박지 말 것. 규칙은 **다른 프로젝트** 에 있는 에이전트가 코드 짤 때 쓰는데, `BaseTransport`/`USE_CLIENT_DEFAULT`/`Auth.auth_flow`/`to_bytes` 같은 이름은 이 레포에만 존재해서 일반화 불가.

한 단계 추상화: 그 심볼이 **충족하는 설계 제약** 을 묘사. 내부 심볼은 `good_example` 과 `ref_files` 에 두고 (구체 evidence 자리), rule 본문은 원리 수준으로.

```
# ❌ 카고컬트 (특정 심볼 처방)
rule: "Use the USE_CLIENT_DEFAULT sentinel for unset request-level params"

# ✅ 원리
rule: "Per-call optional parameters must distinguish 'unset' from 'explicit None' via a dedicated sentinel object, so caller-level과 client-level 디폴트가 깔끔히 fall through"
```

```
# ❌ 카고컬트
rule: "Authentication must be implemented via the Auth.auth_flow generator method"

# ✅ 원리
rule: "Multi-round-trip auth schemes (Digest, OAuth challenge) must be modeled as a generator protocol yielding Request objects, so client transport와 auth 알고리즘이 decouple"
```

휴리스틱: rule 본문에 들어간 식별자 이름이 `good_example` 에도 똑같이 들어간다면 본문이 너무 처방적. 그 이름을 example 로 옮기고 rule 은 동작/형태에 대한 제약으로 다시 써라.

라인 번호 얻는 법: Read tool 결과에 line 번호가 포함돼 있음. 또는 Bash 로 `grep -n 'pattern' <file>` 실행.

### Few-shot 예시 — 이런 규칙을 만들어라

✅ **GOOD rule** (모양 학습용):

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

❌ **BAD rule** (이런 식으로 쓰지 말 것):

```json
{
  "rule": "좋은 코드를 짜야 한다",                    // 너무 추상적
  "priority": "MUST",                              // 판단 불가한데 MUST
  "ref_files": ["src/main.py"],                    // 라인 번호 없음
  "good_example": "# 좋은 예시",                    // 주석 (실제 코드 아님)
  "bad_example": "# 이렇게 하지 말 것",              // 설명문
  "reason": "중요하니까",                           // 설계 의도 없음
}
```

**AnalysisRule 외에 CategoryResult 가 가지는 것:**

- `design_intent` (str): 카테고리 전반의 설계 의도 (2-3문장)
- `anti_patterns` (list[dict]): `{"pattern": ..., "reason": ..., "alternative": ...}`
- `file_type_guides` (dict[str, str]): `{"model": "모델 파일 작성 시 지침...", ...}`
- `checklist` (list[str]): 코드 제출 전 자체 검증 항목

### 3.5. Evidence chain 채우기 (commit_decisions 활용)

step 1 의 `commit_decisions` 가 `null` 이 아니면, 각 규칙의 `evidence` 필드를 시니어의 실제 commit 인용으로 채워라. **이게 이 도구의 핵심 차별점** — rule 의 reason 을 LLM 이 paraphrase 하는 게 아니라 시니어가 직접 쓴 commit body 를 verbatim 으로 surface 한다.

**`commit_decisions.commits` 구조** (각 entry):
- `sha` (12자), `subject`, `date` (ISO), `body_excerpt` (≤800자), `matched_patterns` (예: `["instead of", "decided to"]`), `file_paths` (이 commit 이 touch 한 파일들)

**규칙 별 evidence 채우는 절차**:

1. 룰의 `ref_files` 에 등장한 파일들 (`path:line` 의 path 부분만) 추출
2. `commit_decisions.commits` 중 `file_paths` 와 교집합 있는 commit 들 필터
3. 그 중 1-2 개 가장 관련도 높은 (matched_patterns 풍부 / body_excerpt 가 룰의 의도와 맞는) commit 선택
4. evidence entry 생성:

```json
{
  "kind": "commit",
  "ref": "<sha[:7]>",
  "headline": "<subject 그대로>",
  "quote": "<body_excerpt 그대로, ≤500자>",
  "intent_kind": "<아래 매핑 참조>"
}
```

4.5. (file 매칭 실패 시 fallback — **SEMANTIC INTENT 매칭**) step 2 의 file_paths 교집합이 비었으면:
     `commit_decisions.commits` 의 모든 entry 의 `subject + body_excerpt` 를 직접 읽고,
     **시니어가 기록한 결정의 WHY 가 이 rule 의 reason 과 같은 의도** 인 commit 을
     1개 고른다. 같은 파일을 안 건드렸어도 OK — 같은 설계 원리/문제/해결 의도를
     명시적으로 표현한 commit 이면 매칭.

     예시 (의도 일치):
       rule reason: "한 번에 끊으면 사용자 마이그레이션 비용 폭발. warning + 명시적
                     대안 안내로 옮길 시간을 줘야 한다."
       commit body: "Deprecate `app=...` in favour of explicit `WSGITransport`/
                     `ASGITransport`... rather than rem[oving]"
       → 매칭 OK (둘 다 같은 deprecation discipline 표현).

     ❌ 약한 매칭 / paraphrase 필요 / file 도 의도도 안 맞음 → **[no-evidence]** 로.
     **거짓 evidence > 빈 evidence** — 1초라도 망설여지면 skip. verbatim 으로 인용
     가능한 commit 만 매칭하라.

     (참고: `from hijack.core.archaeology import find_semantic_candidates` 함수가 있어
     keyword Jaccard 후보 surface 가능. 단 한/영 mix + principle-level rule 환경에서는
     약한 신호 — LLM 인 너가 직접 commit body 읽고 의도 판단하는 게 더 정확.)

5. 매칭 commit 없으면 `evidence: []` 유지 + `reason` 앞에 `[no-evidence]` prefix

**`intent_kind` 매핑** (matched_patterns → intent_kind):

| matched_patterns 에 포함 | intent_kind |
|---|---|
| `rejected`, `abandoned`, `switched from` | `rejection` (시니어가 거절한 패턴) |
| `reverted because`, `regression` | `incident` (revert/사고 = 실제 실패 발생) |
| `instead of`, `rather than`, `decided to`, `tried`, `considered`, `decided not to`, `originally...now`, `switched to`, `as opposed to`, `to avoid`, `to prevent` | `preference` (의식적 선택) |
| `due to`, `motivated by` | `constraint` (외부 사유/스펙/제약) |

여러 패턴이 매치되면 가장 강한 것 우선: rejection > incident > preference. 모르면 `null`.

**evidence-rich rule 예시**:

```json
{
  "rule": "Multi-round-trip auth schemes must be modeled as a generator protocol yielding Request objects",
  "priority": "MUST",
  "ref_files": ["httpx/_auth.py:22-110"],
  "good_example": "...",
  "bad_example": "...",
  "reason": "Decouple client transport from auth algorithm — proven by past Digest auth refactor.",
  "layer": "shared",
  "evidence": [{
    "kind": "commit",
    "ref": "a1b2c3d",
    "headline": "Refactor Auth into generator-based flow",
    "quote": "Originally Auth was a simple Callable[[Request], Request], but Digest needs the response of the first request to compute the second. Switched to generator protocol so multi-round schemes don't require Client-internal hooks.",
    "intent_kind": "preference"
  }]
}
```

**가드레일**:
- `quote` 는 반드시 verbatim. 요약/paraphrase 금지. 길면 `[…truncated]` 표시 후 잘라라.
- SHA 만들지 마라. step 1 의 `commit_decisions.commits[*].sha` 에 있는 것만 사용.
- 매칭 commit 없으면 evidence 비우고 [no-evidence] 명시. 거짓 evidence 만드는 게 빈 evidence 보다 훨씬 나쁨.

### 4. SessionResult 조립 + 저장 (Bash tool)

분석 결과를 Python 데이터클래스로 조립해 `generator.write_output` 호출. 분석 내용을 inline Python 스크립트에 쓰지 말고, 임시 JSON 파일에 써서 로드하는 방식이 컨텍스트 효율적.

임시 파일 방식 예시:

```bash
# 분석 결과를 JSON 으로 ~/tmp/analysis.json 에 저장 (Write tool 사용)

python -c "
import json, sys, datetime
sys.path.insert(0, 'backend/src')
from hijack.core.fetcher import fetch_source
from hijack.core.preprocessor import build_preprocess_result
from hijack.core.models import AnalysisRule, CategoryResult, SessionResult
from hijack.core.generator import write_output
from hijack.core.session import create_session_id
from pathlib import Path

TARGET = '<TARGET>'
OUTPUT = '<OUTPUT_DIR>'
ANALYSIS = json.load(open('/tmp/analysis.json', encoding='utf-8'))

files, root = fetch_source(TARGET, attach_history=False)  # step 1 에서 이미 history 사용했음 — 재계산 skip
pp = build_preprocess_result(files, root)

categories = [
    CategoryResult(
        category=cat_data['category'],
        design_intent=cat_data['design_intent'],
        rules=[AnalysisRule(**r) for r in cat_data['rules']],
        anti_patterns=cat_data['anti_patterns'],
        file_type_guides=cat_data.get('file_type_guides', {}),
        checklist=cat_data.get('checklist', []),
        raw_llm_output='(skill-mode)',
    )
    for cat_data in ANALYSIS['categories']
]

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
)
write_output(session, Path(OUTPUT))
print(f'[DONE] {Path(OUTPUT) / session.session_id}')
"
```

### 5.5. 자체 Critic 재평가 (권장 — 품질 향상)

모든 카테고리 규칙 생성이 끝난 뒤, **스스로 다시 훑고 다음 작업을 수행**해라:

**DROP** (규칙 제거):
- 너무 일반적인 규칙 ("좋은 코드를 짜자", "일관성 유지")
- 카테고리 간 사실상 중복 (architecture 의 "BaseLLM 경유" == coding_style 의 "추상 인터페이스 사용")
- ref_files / good_example 이 약한 규칙 (근거 부족)

**DOWNGRADE MUST → SHOULD**:
- 위반해도 실제 PR 거부 수준 아닌 규칙 (강한 선호에 불과)
- 팀 관례 성격 (설계 correctness / security 아님)
- **목표 MUST 비율: 30-40%**. 초과하면 재평가.
- **카테고리당 MUST > 50% 면 강제 강등**: 가장 PR-rejection 가능성 낮은 1개를 SHOULD 로. 후보 우선순위: (a) perf 최적화 — 큰 입력에서만 의미 (작은 입력은 정상 동작), (b) readability/일관성 규칙, (c) 대안이 여전히 작동하는 layering 선호. 반대로 "이거 어기면 server 가 5xx 누출 / OOM / 보안 boundary 침범" 같은 correctness/safety 는 MUST 유지.
- **`evidence` 가 cited 인 MUST 도 자동 강등 안 됨** — `evidence.downgrade_speculative_rules` 는 no-evidence MUST 만 강등. cited MUST 의 priority 검증은 이 단계가 유일한 방어선. 시니어가 "to avoid O(n²)" 라 한 perf rule 을 cited 라고 무비판적으로 MUST 로 두지 말 것 — commit 의 동기 (perf 최적화 vs 안전) 와 priority 의 의미 (PR 거부 vs 강한 선호) 는 별개.

**KEEP as-is**: 고품질 규칙은 그대로.

이 단계는 skill 모드에서 생략 가능하지만, 하면 결과물 신호-잡음비가 유의미하게 개선된다.
API 모드 (`code-hijack analyze`) 는 기본 on (`--critic`).

### 6. 완료 안내

사용자에게 출력 경로 안내:

```
[DONE] 분석 완료
세션: <output>/<session_id>/
통합: <output>/integrated/CLAUDE.md

다음:
  - <output>/integrated/CLAUDE.md 를 분석 대상 레포에 복사하면 에이전트가 해당 스타일로 코딩
  - 다른 세션: /code-hijack <other_target> 후 diff 명령으로 비교
    python -c "from hijack.cli import cli; cli()" diff <session1> <session2>
```

## 가드레일

- **컨텍스트 관리**: 카테고리당 12개 이하 파일. 초과하면 대상 레포 크기 확인 후 `--path` 서브디렉토리 권고.
- **필수 필드**: `AnalysisRule` 의 `rule`, `priority`, `layer` 누락 시 해당 규칙 드롭 (analyzer 의 파싱 로직과 동일).
- **레이어 태깅**: `detect_layer` 가 이미 결정한 `SourceFile.layer` 를 존중. 추측으로 덮어쓰지 말 것.
- **priority 기준**: MUST = 위반 시 PR 거부 수준, SHOULD = 강한 권장. 애매하면 SHOULD. MUST 남발 금지.
- **ref_files**: 실제 존재하는 경로 + **라인 번호 필수**. 예: `"path/to/file.py:42"` 또는 `"path.py:42-58"`. 추상적 "the codebase" 금지. 라인 번호 없이 파일명만 쓰기 금지.
- **bad_example 는 실제 안티패턴 코드**: `"# 이렇게 하지 말 것"` 식 주석 설명 금지. 구체 위반 코드 형태여야 에이전트가 패턴 매칭 가능.
- **good/bad_example**: 실제 레포 코드에서 추출. 상상으로 만들지 말 것 (이 프로젝트의 핵심 차별점).
- **덮어쓰기**: 기존 `<output>/integrated/` 존재 시 사용자에게 확인받고 진행 (`OUTPUT_001` 에러 코드).

## 모범 작업 흐름 (self-analysis 실제 예시)

code-hijack 자기 자신을 분석한 결과가 `hijack-output/2026-04-17_unknown/` 에 남아있다.
참고 스크립트: 레포 루트의 `.skill_analysis.py` (일회성 부트스트랩).

## 트러블슈팅

**파일이 너무 많아 컨텍스트 초과 위험:**
`fetch_source` 에 `--path` 로 서브디렉토리 한정. 또는 Phase 2 문서에 적힌 "2단계 분석" (시그니처만 1차, 선별된 파일 2차) 패턴을 수동으로 적용.

**카테고리 분석 결과가 일반적/피상적:**
`good_example`/`bad_example` 가 실제 코드 라인 아님을 의미. 파일을 다시 읽고 구체 코드 2-3줄 추출 필수.

**JSON 에서 특수문자 이스케이프 실패:**
코드 예시는 큰따옴표 문자열에 이스케이프하지 말고, 임시 JSON 파일 (Write tool) 에 저장 후 로드. Bash heredoc 안에 복잡한 코드 inline 금지.

**같은 URL 반복 분석 시 느림:**
fetch_source 는 자동 캐시 (`~/.cache/code-hijack/repos/<hash>/`). 강제 refresh 는
`HIJACK_NO_CACHE=1` 환경변수 또는 캐시 dir 수동 삭제. 위치 override: `HIJACK_CACHE_DIR=/path`.

**Windows 터미널 mojibake:**
Python `print()` 에서 UTF-8 문자(이모지, 화살표) 출력 시 cp949 에러. ASCII 로 대체 (예: `✅` → `[DONE]`).
