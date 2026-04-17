# Ground Truth — Layer Detection

5개 규칙: 각 파일이 `detect_layer()` 에 의해 올바른 레이어로 분류되는지 검증한다.

| # | 파일 경로 | 예상 레이어 | 감지 근거 |
|---|---------|-----------|---------|
| 1 | `frontend/App.tsx` | `frontend` | suffix `.tsx` → rule 1 |
| 2 | `frontend/hooks/useAuth.ts` | `frontend` | path contains `frontend/` → rule 2 |
| 3 | `backend/routes/users.py` | `backend` | path contains `backend/` + suffix `.py` → rule 7 |
| 4 | `migrations/001_init.py` | `db` | path contains `migrations/` + suffix `.py` → rule 5 |
| 5 | `utils/helpers.py` | `shared` | 어떤 규칙에도 해당하지 않음 → rule 8 (fallback) |
