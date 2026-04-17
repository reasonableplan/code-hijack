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

TARGET = '<TARGET>'
CATEGORIES = ['architecture', 'coding_style', 'api_design']  # 또는 사용자 지정

files, root = fetch_source(TARGET)
pp = build_preprocess_result(files, root)
selected = {cat: [f.path.as_posix() for f in select_files_for_category(pp, cat, max_files=12)] for cat in CATEGORIES}

print(json.dumps({
    'repo_root': root.as_posix(),
    'total_files': len(files),
    'by_layer': {k: len(v) for k, v in pp.by_layer.items()},
    'selected_per_category': selected,
    'project_structure': pp.project_structure,
}, indent=2, ensure_ascii=False))
"
```

위 JSON을 파싱해 각 카테고리의 선별 파일 목록을 얻는다.

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
- `reason`: 이 규칙이 왜 존재하는지
- `layer`: `"frontend"` / `"backend"` / `"db"` / `"devops"` / `"shared"`

**good/bad_example 품질 기준 (critical):**

```
# ✅ 올바른 bad_example — 실제 위반 코드
bad_example: 'eval(user_input)'

# ❌ 틀린 bad_example — 주석으로 설명
bad_example: '# user input 을 eval 로 실행 (금지)'
```

라인 번호 얻는 법: Read tool 결과에 line 번호가 포함돼 있음. 또는 Bash 로 `grep -n 'pattern' <file>` 실행.

**AnalysisRule 외에 CategoryResult 가 가지는 것:**

- `design_intent` (str): 카테고리 전반의 설계 의도 (2-3문장)
- `anti_patterns` (list[dict]): `{"pattern": ..., "reason": ..., "alternative": ...}`
- `file_type_guides` (dict[str, str]): `{"model": "모델 파일 작성 시 지침...", ...}`
- `checklist` (list[str]): 코드 제출 전 자체 검증 항목

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

files, root = fetch_source(TARGET)
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

### 5. 완료 안내

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

**Windows 터미널 mojibake:**
Python `print()` 에서 UTF-8 문자(이모지, 화살표) 출력 시 cp949 에러. ASCII 로 대체 (예: `✅` → `[DONE]`).
