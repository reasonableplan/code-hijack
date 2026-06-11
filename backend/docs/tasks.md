# Tasks — code-hijack

생성: 2026-04-17T11:15:02+00:00

### Phase 1 — MVP (3 카테고리 × 5 레이어, CLI + Skill)
| ID | 에이전트 | 의존성 | 설명 | 상태 |
|----|---------|--------|------|------|
| T-001 | backend_coder | - | core.logic (models.py): AnalysisRule/CategoryResult/SessionResult @dataclass + to_json/from_json. layer 필드 포함. [2026-06-10: T-030 이 rationale_tier·ForesightCard·foresight_cards·repo_nature 확장 흡수] | done |
| T-002 | backend_coder | - | errors + configuration: HijackError(ClickException) 계층 (Input/Fetch/LLM/Output) + 에러 코드 상수 + backend/.env.example 생성. | done      |
| T-003 | backend_coder | T-001,T-002 | core.logic (llm/base.py, llm/api.py): BaseLLM ABC (analyze 추상) + ClaudeAPIClient (anthropic SDK, asyncio.to_thread 래핑, 기본 모델 claude-sonnet-4-6, ANTHROPIC_API_KEY 로드). | done      |
| T-004 | backend_coder | T-001,T-002 | core.logic (fetcher.py): SourceFile + fetch_source (로컬 경로 + git clone), 파일 수집 + _SKIP_DIRS 제외 + detect_layer (frontend/backend/db/devops/shared). | done      |
| T-005 | backend_coder | T-001,T-004 | core.logic (preprocessor.py): 역할 분류 (entry_point/model/api/test/config/...), 2D(role×layer) 분류, PreprocessResult, build_file_summary_for_llm. | done      |
| T-006 | backend_coder | T-001 | core.logic (prompts.py): MVP 3 카테고리 프롬프트 (architecture, coding_style, api_design) + 레이어별 섹션 출력 지시 + MVP_CATEGORIES 상수. [2026-06-10: T-034 이 foresight 가설 프롬프트 추가 흡수] | done |
| T-007 | backend_coder | T-003,T-005,T-006 | core.logic (analyzer.py): run_full_analysis, 카테고리별 LLM 호출, JSON 파싱 + regex 폴백, 최대 2회 재시도, 레이어 파싱. [2026-06-10: T-033 이 normalize_rationale_tier MUST 강등 정규화 흡수] | done |
| T-008 | backend_coder | T-001 | core.logic (session.py): create_session_id (YYYY-MM-DD_<repo>), get_output_dir, SessionDiff (Phase 2 stub). | done      |
| T-009 | backend_coder | T-001,T-007,T-008 | core.logic (generator.py): 레이어별 .md 분리 렌더러 (frontend/backend/database/devops/shared) + CLAUDE.md 진입점 + system-prompt.md + write_output (세션별 raw + integrated). [2026-06-10: T-034 이 foresight.md 렌더 + 성격 헤더 + system-prompt 맥락 조건부 톤 흡수] | done |
| T-010 | backend_coder | T-002,T-003,T-007,T-009 | interface.cli (cli.py, skill.py): click 진입점 + --model/--path/--categories/--output/--dry-run/-v/-q, skill 엔트리, 비용 추정 + 사용자 확인 흐름. | done      |
| T-011 | backend_coder | T-001,T-004,T-005,T-007,T-008,T-009 | core.logic (tests): test_models/fetcher/preprocessor/analyzer/generator/session + tests/fixtures/senior_wisdom/ 복원 (ground_truth.md 5 규칙 레이어 검증). [2026-06-10: T-030~T-034 각 태스크가 자체 테스트 포함 — T-011 범위 외] | done |

### Phase 2 — 확장 (7 카테고리 + 세션 관리)
| ID | 에이전트 | 의존성 | 설명 | 상태 |
|----|---------|--------|------|------|
| T-020 | backend_coder | - | core.logic (prompts.py): 7 카테고리 프롬프트 추가 (testing, dependencies, security, performance, devops, state_management, data_model). | done      |
| T-021 | backend_coder | T-020 | core.logic (analyzer.py): _CATEGORY_ROLES 확장 (7 카테고리별 파일 역할 매핑). | done      |
| T-022 | backend_coder | - | core.logic (session.py): SessionDiff 구현 완성 (두 SessionResult 비교 → 변경/추가/삭제 규칙). | done      |
| T-023 | backend_coder | T-021,T-022 | interface.cli: --resume 옵션 (session.json 읽어 완료 카테고리 스킵) + diff 서브커맨드 + 7 카테고리/resume/diff 테스트 추가. | done      |

<!-- ha-redesign 2026-06-10: Foresight inference layer — affected via /ha-redesign -->
### Phase 3 — Foresight inference layer
| ID | 에이전트 | 의존성 | 설명 | 상태 |
|----|---------|--------|------|------|
| T-030 | backend_coder | - | core.logic (models.py): AnalysisRule rationale_tier 필드 + ForesightCard dataclass + SessionResult 확장 + 하위 호환 from_json + 테스트 | done      |
| T-031 | backend_coder | T-030 | core.logic (negative_space.py): 신규 모듈. NegativeSpaceResult + extract_negative_space 순수 함수 + read_deprecation_history I/O 함수 + 테스트 | done      |
| T-032 | backend_coder | T-030 | core.logic (preprocessor.py): detect_repo_nature 함수 + PreprocessResult.repo_nature 필드 + 테스트 | done      |
| T-033 | backend_coder | T-030 | core.logic (analyzer.py): normalize_rationale_tier 순수 함수 + run_full_analysis 내 호출 + 테스트 | done      |
| T-034 | backend_coder | T-030,T-032 | core.logic (generator.py): foresight.md 렌더 + write_output 에 foresight.md 추가 + 성격 헤더 + system-prompt 맥락 조건부 톤 + 테스트 | done      |
| T-035 | backend_coder | T-031,T-032,T-033,T-034 | .claude/skills/code-hijack/SKILL.md: negative_space 추출 단계 + foresight 가설 생성 + 삼각측량 절차 + 성격 헤더 단계 추가 | done      |

<!-- ha-redesign 2026-06-11: Evidence source expansion + measurement loop — affected via /ha-redesign -->
### Phase 4 — Evidence source expansion + measurement loop
| ID | 에이전트 | 의존성 | 설명 | 상태 |
|----|---------|--------|------|------|
| T-036 | backend_coder | - | core.logic (pr_archaeology.py): 신규 모듈 (impure). PRDecision/PRDecisions dataclass + gh CLI subprocess 수집 + graceful skip + 테스트 (gh 호출 mock) | done      |
| T-037 | backend_coder | - | core.logic (measure.py): 지표 산출 순수 함수 + 세션 비교 + foresight 채점 + measurement.json 저장 + 테스트 | done      |
| T-038 | backend_coder | T-037 | interface.cli (cli.py): measure 서브커맨드 배선 + §6 갱신 + 테스트 | done      |
| T-039 | backend_coder | T-036,T-037 | .claude/skills/code-hijack/SKILL.md: step 1 pr_decisions 추가 + step 3.5/3.7 소스 합류 + foresight 채점 절차 | done      |

---

#### T-036 스펙: pr_archaeology.py PR/issue 마이닝

**담당**: backend_coder
**생성·수정 파일**:
- `backend/src/hijack/core/pr_archaeology.py` (신규)
- `tests/test_pr_archaeology.py` (신규)

**skeleton 참조**: §7 데이터 모델 (`PRDecision`/`PRDecisions` 스키마), §7 순수/impure 분리표, §8 외부 통합 gh CLI 항목

**구현 세부**:
1. **데이터 모델** (`PRDecision`/`PRDecisions` — CommitDecision/CommitDecisions 와 동형):
   ```python
   @dataclass
   class PRDecision:
       ref: str              # "PR#123" 또는 "issue#456"
       title: str
       date: str             # ISO ("2024-08-12 14:30:00 +0900" 형식)
       body_excerpt: str     # 본문 첫 _BODY_EXCERPT_CHARS 자, 공백 정규화
       matched_patterns: list[str]  # 매칭 패턴 display name; sorted asc
       maintainer_comment: str      # 메인테이너 마지막 코멘트 (빈 문자열 허용)
       intent_kind: str      # "rejection" | "incident" | "preference"
       # to_json / from_json 구현

   @dataclass
   class PRDecisions:
       __test__ = False
       items_scanned: int
       patterns: list[DecisionPattern]  # archaeology.py 의 DecisionPattern 재사용
       decisions: list[PRDecision]      # date desc; cap 50
       # to_json / from_json / has_signal 구현
   ```
2. **import**: `from hijack.core.archaeology import _DECISION_PATTERNS, _COMPILED_PATTERNS, DecisionPattern` — 중복 정의 금지. `_BODY_EXCERPT_CHARS`, `_sanitize_body_excerpt` 등 필요한 내부 헬퍼도 archaeology.py 에서 import.
3. **gh 수집 함수** (impure — subprocess):
   - `fetch_pr_decisions(repo_url: str, *, timeout: int = 30) -> PRDecisions`
   - `gh api repos/{owner}/{repo}/pulls?state=closed&per_page=100` → closed-unmerged 필터 (merged_at is None)
   - `gh api repos/{owner}/{repo}/issues?state=closed&labels=wontfix&per_page=100` → wontfix issue
   - PR/issue 본문 + 메인테이너 마지막 코멘트에 `_COMPILED_PATTERNS` 적용
   - intent_kind 매핑: closed-unmerged PR + 메인테이너 거절 코멘트 (reviewed/closed without merge) → `"rejection"`, revert/rollback 언급 issue → `"incident"`, 그 외 → `"preference"`
4. **graceful skip**: gh 미설치 (`FileNotFoundError`) / 인증 실패 (returncode != 0) / rate-limit (JSON `message` 포함) / timeout (`subprocess.TimeoutExpired`) → `logger.warning(...)` + 빈 `PRDecisions(items_scanned=0, patterns=[], decisions=[])` 반환. 새 에러 코드 불필요.
5. **테스트**: gh subprocess 를 `unittest.mock.patch("subprocess.run")` 으로 mock. (a) 정상 케이스 — PRDecision 목록 파싱, (b) gh 미설치 → 빈 PRDecisions, (c) 인증 실패 → 빈 PRDecisions, (d) intent_kind 매핑 정확성.

**완료 기준**:
- `pytest tests/test_pr_archaeology.py` 전량 통과.
- `ruff check src ../tests` 경고 없음.
- gh 미설치 환경에서 예외 없이 빈 결과 반환 확인.

---

#### T-037 스펙: measure.py 지표 산출 + measurement.json 저장

**담당**: backend_coder
**생성·수정 파일**:
- `backend/src/hijack/core/measure.py` (신규)
- `tests/test_measure.py` (신규)

**skeleton 참조**: §7 데이터 모델 (`MeasurementResult` 스키마), §7 순수/impure 분리표, §2 측정 기능 요구사항

**구현 세부**:
1. **`MeasurementResult` dataclass**:
   ```python
   @dataclass
   class MeasurementResult:
       session_id: str
       cited_ratio: float
       must_ratio: float
       tier_distribution: dict[str, int]   # {"cited": N, "corroborated": N, "speculative": N}
       intent_kind_distribution: dict[str, int]  # {"rejection": N, "incident": N, "preference": N}
       foresight_scores: list[dict[str, str]]     # [{"hypothesis": ..., "verdict": "confirmed"|"unconfirmed"|"refuted"}]
       # to_json / from_json
   ```
2. **순수 함수**:
   - `calc_session_metrics(session: SessionResult, pr_decisions: PRDecisions | None = None) -> MeasurementResult` — 규칙 전체에서 cited/MUST 비율, tier/intent_kind 분포 산출. pr_decisions 있으면 intent_kind 분포에 포함.
   - `diff_sessions(m1: MeasurementResult, m2: MeasurementResult) -> dict[str, Any]` — 두 세션 지표 차이 딕셔너리 반환.
   - `score_foresight(cards: list[ForesightCard], repo_docs: str, pr_decisions: PRDecisions | None) -> list[dict[str, str]]` — 카드별 결정론 채점 (키워드 매칭 기반). LLM 판단 없이 결정론적으로 가능한 것만 채점. 매칭 안 되면 `"unconfirmed"`.
3. **I/O 함수**:
   - `write_measurement(result: MeasurementResult, session_dir: Path) -> None` — `session_dir / "measurement.json"` 에 저장. session.json 재확장 금지. stdout 저장 금지.
4. **stdout 요약**: `format_measurement_summary(result: MeasurementResult) -> str` 순수 함수로 사람이 읽는 요약 문자열 생성 (cli.py 에서 click.echo 로 출력).
5. **기존 diff 인프라 재사용**: session.py 의 SessionDiff 가 있으면 diff_sessions 구현 시 참고.

**완료 기준**:
- `pytest tests/test_measure.py` 전량 통과.
- `calc_session_metrics` 단위 테스트: cited 규칙만 있는 세션 → cited_ratio=1.0, mixed → 정확한 비율.
- `diff_sessions` 단위 테스트: 두 MeasurementResult 비교 → 차이값 딕셔너리.
- `write_measurement` 통합 테스트: 파일 생성 확인 + from_json 역직렬화 검증.

---

#### T-038 스펙: cli.py measure 서브커맨드

**담당**: backend_coder
**생성·수정 파일**:
- `backend/src/hijack/cli.py` (수정 — measure 서브커맨드 추가)
- `backend/docs/skeleton.md` §6 (수정 — measure 서브커맨드 등재)
- `tests/test_cli.py` (수정 — measure 커맨드 테스트 추가)

**skeleton 참조**: §6 CLI 커맨드 (diff 서브커맨드와 동일 패턴), §9 T-037 의존

**구현 세부**:
1. **measure 서브커맨드** (diff 서브커맨드 패턴 준수):
   ```
   code-hijack measure <session.json>
     → calc_session_metrics + write_measurement + stdout 요약 출력

   code-hijack measure <session1.json> <session2.json>
     → calc_session_metrics x2 + diff_sessions + stdout diff 출력
   ```
2. session.json 경로 인자 1개 또는 2개 수락. 1개면 단일 세션 측정, 2개면 비교 측정.
3. session.json 로드는 `SessionResult.from_json` 사용 (기존 인프라).
4. `write_measurement` 는 session.json 과 동일 디렉토리에 `measurement.json` 저장.
5. §6 skeleton.md 에 measure 서브커맨드 사용법/인자/예시 등재.

**완료 기준**:
- `click.testing.CliRunner` 로 `measure <session.json>` 호출 → measurement.json 생성 + 0 exit code.
- `measure <s1.json> <s2.json>` → diff 출력 + 0 exit code.
- `pytest tests/test_cli.py` 전량 통과.

---

#### T-039 스펙: SKILL.md PR/issue 마이닝 + foresight 채점 갱신

**담당**: backend_coder
**생성·수정 파일**:
- `.claude/skills/code-hijack/SKILL.md` (수정)

**skeleton 참조**: §2 PR/issue 마이닝 요구사항, §7 핵심 비즈니스 규칙 #12, §9 T-036/T-037 의존

**구현 세부**:
1. **step 1 수집 단계** 에 `pr_decisions` 추가:
   - `fetch_pr_decisions(repo_url)` 호출 명시 (gh CLI 없으면 빈 PRDecisions 로 계속 — 경고 출력).
   - 결과: `pr_decisions: PRDecisions` 를 이후 단계에 전달.
2. **step 3.5 evidence chain** 소스에 `pr_decisions` 합류:
   - commit_decisions 와 병렬 소스로 명시.
   - rejection/incident PRDecision 은 evidence chain 에서 높은 가중치 부여 안내.
3. **step 3.7 foresight 삼각측량** 에 `pr_decisions` 소스 추가:
   - ForesightCard.signals 교차 검증 시 pr_decisions.decisions 도 참조.
   - rejection 패턴과 일치하는 카드 → "rejection" intent_kind 로 분류 권장.
4. **foresight 채점 절차** 추가 (step 3.8 또는 적절한 단계로 삽입):
   - `score_foresight(cards, repo_docs, pr_decisions)` 호출 → 결정론적 채점.
   - LLM 이 unconfirmed 카드를 검토해 confirmed/refuted 판단 추가.
   - 최종 verdict 목록을 `write_measurement` 에 전달 → `measurement.json` 저장.

**완료 기준**:
- SKILL.md 가 위 4개 변경을 포함하는 워크플로우로 갱신됨.
- 각 단계에 입력/출력/판단 기준이 명시됨 (Coder 자율 결정 여지 없음).

---

#### T-030 스펙: models.py 스키마 확장

**담당**: backend_coder
**생성·수정 파일**:
- `backend/src/hijack/core/models.py` (수정)
- `tests/test_models.py` (수정 — 신규 필드 테스트 추가)

**skeleton 참조**: §7 데이터 모델 확장 (AnalysisRule, ForesightCard, SessionResult, NegativeSpaceResult 스키마)

**구현 세부**:
1. `AnalysisRule` 에 `rationale_tier: str = "speculative"` 필드 추가. 유효값: `"cited"` | `"corroborated"` | `"speculative"`.
2. `AnalysisRule.from_json` 에서 `"rationale_tier"` 키 없으면 기본값 `"speculative"` 로 역직렬화 (구버전 session.json 하위 호환).
3. `AnalysisRule.to_json` 에 `"rationale_tier"` 포함.
4. `ForesightCard` @dataclass 신규 추가:
   ```python
   @dataclass
   class ForesightCard:
       hypothesis: str
       signals: list[str]
       falsification: str
       tier: str              # "corroborated" | "speculative"
       layer: str
   ```
   `to_json` / `from_json` 구현.
5. `SessionResult` 에 두 필드 추가:
   - `foresight_cards: list[ForesightCard] = field(default_factory=list)`
   - `repo_nature: str = "library"`
   `from_json` 에서 각각 키 없으면 기본값 적용.
6. `NegativeSpaceResult` @dataclass 추가 (models.py 또는 negative_space.py 상단에 정의):
   ```python
   @dataclass
   class NegativeSpaceResult:
       dep_count: int
       direct_impl_hints: list[str]
       public_ratio: float
       has_all_discipline: bool
       deprecation_patterns: list[str]
       layer_import_violations: list[str]
   ```

**완료 기준**:
- `pytest tests/test_models.py` 전량 통과.
- 구버전 session.json fixture (rationale_tier/foresight_cards/repo_nature 없는 것) 로드 시 오류 없음 (하위 호환 테스트 포함).
- `ruff check src ../tests` 경고 없음.

---

#### T-031 스펙: negative_space.py 추출기

**담당**: backend_coder
**생성·수정 파일**:
- `backend/src/hijack/core/negative_space.py` (신규)
- `tests/test_negative_space.py` (신규)

**skeleton 참조**: §7 `extract_negative_space` 알고리즘, 순수 함수 vs I/O 분리 표

**구현 세부**:
1. **파일 위치**: `backend/src/hijack/core/negative_space.py`. preprocessor.py 확장 아님. 독립 모듈.
2. **의존성**: stdlib 전용 (ast, pathlib, re, subprocess). 외부 패키지 금지.
3. **순수 함수** (I/O 없음):
   - `extract_negative_space(repo_root: Path, py_files: list[Path], pyproject_toml: dict | None, layer_map: dict[Path, str]) -> NegativeSpaceResult`
   - `_calc_dep_count(pyproject_toml: dict | None) -> int` — `[project.dependencies]` 배열 길이
   - `_find_direct_impls(py_files: list[Path]) -> list[str]` — ast.parse 로 파일별 import 분석, stdlib-only import 파일 경로 수집
   - `_calc_public_ratio(py_files: list[Path]) -> tuple[float, bool]` — 모듈별 심볼에서 `_` prefix 없는 비율 + `__all__` 존재 여부
   - `_scan_deprecation_patterns(py_files: list[Path]) -> list[str]` — re 로 `DeprecationWarning` 패턴 스캔 (파일 내용 기반, git 미사용)
   - `_find_layer_violations(py_files: list[Path], layer_map: dict[Path, str]) -> list[str]` — ast import + layer_map 기반 역방향 import 탐지
4. **I/O 함수** (분리):
   - `read_deprecation_history(repo_root: Path) -> list[str]` — `git log` subprocess 호출. git 미존재 시 빈 리스트 + 경고 (graceful skip).
5. `extract_negative_space` 는 내부적으로 `_scan_deprecation_patterns` (순수) 를 호출. `read_deprecation_history` 는 호출자(skill/cli)가 별도 호출 후 결과를 `deprecation_patterns` 에 병합.

**완료 기준**:
- `pytest tests/test_negative_space.py` 전량 통과.
- `tests/fixtures/senior_wisdom/` 픽스처 레포에 대한 통합 테스트 — `NegativeSpaceResult` 필드 전부 채워짐 확인.
- git 없는 경로에서 `read_deprecation_history` 호출 시 빈 리스트 반환, 예외 없음.

---

#### T-032 스펙: 레포 성격 판별 (preprocessor)

**담당**: backend_coder
**생성·수정 파일**:
- `backend/src/hijack/core/preprocessor.py` (수정)
- `tests/test_preprocessor.py` (수정 — detect_repo_nature 테스트 추가)

**skeleton 참조**: §7 `detect_repo_nature` 알고리즘

**구현 세부**:
1. `detect_repo_nature(pyproject_toml: dict | None, detected_layers: set[str]) -> Literal["app/cli", "app", "library"]` 순수 함수 추가.
2. 판별 기준 (우선순위 순):
   - `pyproject_toml` 에 `[project.scripts]` 또는 `[project.entry-points]` 키 존재 → `"app/cli"`
   - `"frontend"` in `detected_layers` → `"app"`
   - 그 외 → `"library"`
3. `PreprocessResult` dataclass 에 `repo_nature: str = "library"` 필드 추가.
4. `preprocess` (또는 동등한 최상위 함수) 내에서 `detect_repo_nature` 를 호출해 `PreprocessResult.repo_nature` 채움.

**완료 기준**:
- `detect_repo_nature` 단위 테스트: (a) scripts 있음 → "app/cli", (b) frontend layer → "app", (c) 둘 다 없음 → "library", (d) scripts 있고 frontend layer 도 있음 → "app/cli" (scripts 우선).
- `pytest tests/test_preprocessor.py` 전량 통과.

---

#### T-033 스펙: cited-only MUST 정규화 (analyzer)

**담당**: backend_coder
**생성·수정 파일**:
- `backend/src/hijack/core/analyzer.py` (수정)
- `tests/test_analyzer.py` (수정 — normalize_rationale_tier 테스트 추가)

**skeleton 참조**: §7 핵심 비즈니스 규칙 #8 (rationale_tier 정규화)

**구현 세부**:
1. `normalize_rationale_tier(rules: list[AnalysisRule]) -> list[AnalysisRule]` 순수 함수 추가.
2. 로직:
   ```python
   for rule in rules:
       if rule.rationale_tier in ("corroborated", "speculative") and rule.priority == "MUST":
           rule = dataclasses.replace(rule, priority="SHOULD")
   ```
   원본 객체 수정 금지 — `dataclasses.replace` 사용해 새 인스턴스 반환.
3. `run_full_analysis` 내에서 LLM 응답 파싱 후, `CategoryResult` 생성 직전에 `rules = normalize_rationale_tier(rules)` 호출.
4. 기존 `evidence.downgrade_speculative_rules` (있다면) 와 중복되지 않도록 통합 또는 대체.

**완료 기준**:
- 단위 테스트 케이스: (a) cited + MUST → MUST 유지, (b) corroborated + MUST → SHOULD, (c) speculative + MUST → SHOULD, (d) speculative + SHOULD → SHOULD 유지 (이중 강등 없음).
- `pytest tests/test_analyzer.py` 전량 통과.

---

#### T-034 스펙: generator.py foresight.md 렌더 + system-prompt 톤 + 성격 헤더

**담당**: backend_coder
**생성·수정 파일**:
- `backend/src/hijack/core/generator.py` (수정)
- `tests/test_generator.py` (수정 — foresight.md 렌더 + 톤 + 헤더 테스트 추가)

**skeleton 참조**: §7 핵심 비즈니스 규칙 #11, 순수 함수 vs I/O 분리 표 (generator.py impure)

**구현 세부**:
1. `render_foresight_md(cards: list[ForesightCard], repo_nature: str) -> str` 순수 렌더러 추가.
   - 출력 헤더: `# Foresight — <repo_nature> 맥락에서 추론된 설계 의도`
   - corroborated 카드: `## [corroborated] <hypothesis>` 섹션
   - speculative 카드: `## [speculative — 강제 아님] <hypothesis>` 섹션
   - 각 카드에 `signals`, `falsification` 항목 포함.
2. `write_output` 에서 `SessionResult.foresight_cards` 가 비어있지 않으면 `foresight.md` 를 세션 raw 디렉토리 + `integrated/` 에 저장.
3. 레이어별 `.md` 및 `CLAUDE.md` 헤더에 "이 규칙들은 `<repo_nature>` 맥락에서 추출됨" 1줄 추가.
4. `system-prompt.md` 에서 "When writing code, treat MUST rules as non-negotiable constraints" 또는 유사 문구를 다음으로 교체:
   ```
   MUST 규칙은 추출 맥락(파일 헤더의 레포 성격 참조)이 성립할 때 적용하라.
   맥락이 다르면 일탈 가능하되 이유를 명시하라.
   corroborated/speculative rationale 규칙과 foresight 카드는 강제 아닌 고려 사항이다.
   ```

**완료 기준**:
- `render_foresight_md` 단위 테스트: corroborated 카드 → "강제 아님" 없음, speculative 카드 → "강제 아님" 표시.
- `write_output` 통합 테스트: foresight_cards 비어있으면 foresight.md 파일 미생성, 있으면 생성.
- system-prompt.md 내 "non-negotiable" 문구 없음 검증.
- `pytest tests/test_generator.py` 전량 통과.

---

#### T-035 스펙: SKILL.md skill-mode 워크플로우 갱신

**담당**: backend_coder
**생성·수정 파일**:
- `.claude/skills/code-hijack/SKILL.md` (수정)

**skeleton 참조**: §2 기능 요구사항 (foresight, negative_space, 레포 성격), §7 알고리즘

**구현 세부**:
1. Fetcher 단계 이후, Analyzer 단계 이전에 **negative_space 추출 단계** 추가:
   - `extract_negative_space` 호출 (순수 함수, py_files + layer_map 전달)
   - `read_deprecation_history` 호출 (I/O, graceful skip)
   - `NegativeSpaceResult` 를 Analyzer 컨텍스트에 전달
2. Analyzer 단계에 **foresight 가설 생성 절차** 추가:
   - LLM 에게 `NegativeSpaceResult` 신호를 제공하여 `ForesightCard` 목록 생성 지시
   - LLM 은 각 카드의 `tier` 를 자가 판정 (`"corroborated"` 또는 `"speculative"`)
   - `tier` 판정 기준을 프롬프트에 명시: 독립 신호 2개 이상 일관 → corroborated, 그 외 → speculative
3. **삼각측량 절차** 추가:
   - 각 `ForesightCard.signals` 항목이 `NegativeSpaceResult` 신호 중 어느 것과 대응하는지 교차 검증
   - 대응 신호 없는 카드는 tier 를 `"speculative"` 로 강제
4. **레포 성격 헤더 단계** 추가:
   - `detect_repo_nature` 결과를 Generator 에 전달, 출력 파일 헤더에 반영하는 단계 명시

**완료 기준**:
- SKILL.md 가 위 4단계를 포함하는 워크플로우로 갱신됨.
- 각 단계에 입력/출력/판단 기준이 명시됨 (Coder 자율 결정 여지 없음).

---

### 의존성 그래프
\`\`\`
Phase 1:
  T-001 (models) ─┬─► T-003 (llm)
                  ├─► T-004 (fetcher)
                  ├─► T-006 (prompts)
                  └─► T-008 (session)
  T-002 (errors) ─┤
                  └─► T-003, T-004, T-010

  T-004 ──► T-005 (preprocessor)
  T-003 + T-005 + T-006 ──► T-007 (analyzer)
  T-001 + T-007 + T-008 ──► T-009 (generator)
  T-002 + T-003 + T-007 + T-009 ──► T-010 (cli/skill)
  T-001 + T-004 + T-005 + T-007 + T-008 + T-009 ──► T-011 (tests)

Phase 2:
  T-020 ──► T-021
  T-022 (병렬)
  T-021 + T-022 ──► T-023

Phase 3 (Foresight inference layer):
  T-030 (models 확장) ─┬─► T-031 (negative_space — T-030 이후 병렬 가능)
                        ├─► T-032 (detect_repo_nature — T-030 이후 병렬 가능)
                        ├─► T-033 (normalize_rationale_tier)
                        └─► T-034 (generator, T-032 도 의존)
  T-031 + T-032 + T-033 + T-034 ──► T-035 (SKILL.md 갱신)

Phase 4 (Evidence source expansion + measurement loop):
  T-036 (pr_archaeology) 병렬 가능 (의존성 없음)
  T-037 (measure.py)     병렬 가능 (의존성 없음)
  T-037 ──► T-038 (cli measure 서브커맨드)
  T-036 + T-037 ──► T-039 (SKILL.md 갱신)
\`\`\`

### 병렬 실행 가능 조합
- **즉시 시작 가능**: T-001, T-002 (의존성 없음)
- **T-001 + T-002 완료 후 병렬**: T-003, T-004, T-006, T-008 (4개 동시)
- **T-004 완료 후**: T-005 추가
- **T-007 이후 병렬**: T-008(있었으면), T-009
- **Phase 2 즉시 병렬**: T-020, T-022 (독립)
- **Phase 4 즉시 병렬**: T-036, T-037 (독립 — 의존성 없음)

### 진행 상태
- \`pending\` — 아직 시작 안 함
- \`in-progress\` — \`/ha-build\` 실행 중
- \`done\` — 구현 + 검증 완료
- \`blocked\` — 의존성 미해결 또는 실패 지속
