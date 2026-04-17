# Tasks — code-hijack

생성: 2026-04-17T11:15:02+00:00

### Phase 1 — MVP (3 카테고리 × 5 레이어, CLI + Skill)
| ID | 에이전트 | 의존성 | 설명 | 상태 |
|----|---------|--------|------|------|
| T-001 | backend_coder | - | core.logic (models.py): AnalysisRule/CategoryResult/SessionResult @dataclass + to_json/from_json. layer 필드 포함. | done      |
| T-002 | backend_coder | - | errors + configuration: HijackError(ClickException) 계층 (Input/Fetch/LLM/Output) + 에러 코드 상수 + backend/.env.example 생성. | done      |
| T-003 | backend_coder | T-001,T-002 | core.logic (llm/base.py, llm/api.py): BaseLLM ABC (analyze 추상) + ClaudeAPIClient (anthropic SDK, asyncio.to_thread 래핑, 기본 모델 claude-sonnet-4-6, ANTHROPIC_API_KEY 로드). | done      |
| T-004 | backend_coder | T-001,T-002 | core.logic (fetcher.py): SourceFile + fetch_source (로컬 경로 + git clone), 파일 수집 + _SKIP_DIRS 제외 + detect_layer (frontend/backend/db/devops/shared). | done      |
| T-005 | backend_coder | T-001,T-004 | core.logic (preprocessor.py): 역할 분류 (entry_point/model/api/test/config/...), 2D(role×layer) 분류, PreprocessResult, build_file_summary_for_llm. | done      |
| T-006 | backend_coder | T-001 | core.logic (prompts.py): MVP 3 카테고리 프롬프트 (architecture, coding_style, api_design) + 레이어별 섹션 출력 지시 + MVP_CATEGORIES 상수. | done      |
| T-007 | backend_coder | T-003,T-005,T-006 | core.logic (analyzer.py): run_full_analysis, 카테고리별 LLM 호출, JSON 파싱 + regex 폴백, 최대 2회 재시도, 레이어 파싱. | done      |
| T-008 | backend_coder | T-001 | core.logic (session.py): create_session_id (YYYY-MM-DD_<repo>), get_output_dir, SessionDiff (Phase 2 stub). | done      |
| T-009 | backend_coder | T-001,T-007,T-008 | core.logic (generator.py): 레이어별 .md 분리 렌더러 (frontend/backend/database/devops/shared) + CLAUDE.md 진입점 + system-prompt.md + write_output (세션별 raw + integrated). | done      |
| T-010 | backend_coder | T-002,T-003,T-007,T-009 | interface.cli (cli.py, skill.py): click 진입점 + --model/--path/--categories/--output/--dry-run/-v/-q, skill 엔트리, 비용 추정 + 사용자 확인 흐름. | done      |
| T-011 | backend_coder | T-001,T-004,T-005,T-007,T-008,T-009 | core.logic (tests): test_models/fetcher/preprocessor/analyzer/generator/session + tests/fixtures/senior_wisdom/ 복원 (ground_truth.md 5 규칙 레이어 검증). | done      |

### Phase 2 — 확장 (7 카테고리 + 세션 관리)
| ID | 에이전트 | 의존성 | 설명 | 상태 |
|----|---------|--------|------|------|
| T-020 | backend_coder | - | core.logic (prompts.py): 7 카테고리 프롬프트 추가 (testing, dependencies, security, performance, devops, state_management, data_model). | 대기 |
| T-021 | backend_coder | T-020 | core.logic (analyzer.py): _CATEGORY_ROLES 확장 (7 카테고리별 파일 역할 매핑). | 대기 |
| T-022 | backend_coder | - | core.logic (session.py): SessionDiff 구현 완성 (두 SessionResult 비교 → 변경/추가/삭제 규칙). | 대기 |
| T-023 | backend_coder | T-021,T-022 | interface.cli: --resume 옵션 (session.json 읽어 완료 카테고리 스킵) + diff 서브커맨드 + 7 카테고리/resume/diff 테스트 추가. | 대기 |

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
\`\`\`

### 병렬 실행 가능 조합
- **즉시 시작 가능**: T-001, T-002 (의존성 없음)
- **T-001 + T-002 완료 후 병렬**: T-003, T-004, T-006, T-008 (4개 동시)
- **T-004 완료 후**: T-005 추가
- **T-007 이후 병렬**: T-008(있었으면), T-009
- **Phase 2 즉시 병렬**: T-020, T-022 (독립)

### 진행 상태
- \`pending\` — 아직 시작 안 함
- \`in-progress\` — \`/ha-build\` 실행 중
- \`done\` — 구현 + 검증 완료
- \`blocked\` — 의존성 미해결 또는 실패 지속
