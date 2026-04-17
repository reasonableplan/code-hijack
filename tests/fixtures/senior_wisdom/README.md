# Senior Wisdom Fixture

code-hijack 의 레이어 감지 로직을 검증하기 위한 미니 코드베이스.

- `repo/` — 샘플 레포 (Python + TypeScript)
- `ground_truth.md` — 각 파일의 예상 레이어 정의

## 검증 조건 (Phase 1.5 완료 기준)

`ground_truth.md` 에 정의된 5개 파일이 `detect_layer()` 함수에 의해 올바른 레이어로 분류돼야 한다.
