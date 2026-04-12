# Senior Wisdom Fixture

실제 시니어 프론트엔드 개발자와 협업하며 수집한 "설명 듣고 나서야 이해한" 규칙들.
code-hijack MVP 평가용 ground truth.

## 파일

- `ground_truth.md` — 정답 규칙 5개 (MVP가 포착해야 하는 목표)

## 사용법

1. 비슷한 스타일의 공개 레포를 대상으로 `code-hijack` 실행
2. 생성된 `CLAUDE.md` / `system-prompt.md`를 `ground_truth.md`와 비교
3. 5개 규칙 중 몇 개를 포착했는지, 이유의 깊이가 충분한지 평가
4. 갭이 Phase 2 설계의 근거

## 평가 루브릭

| 단계 | 기준 |
|------|------|
| 포착 | 규칙을 발견했는가 (yes/no) |
| 이유 | "일관성" 수준이 아닌 실질적 근거가 있는가 |
| AI trap | AI가 저지를 실수를 ❌ 예시로 짚었는가 |
| 실패 모드 | 규칙을 어기면 뭐가 터지는지 구체적인가 |

5개 중 3개 이상 통과 → Phase 1 MVP 성공.
