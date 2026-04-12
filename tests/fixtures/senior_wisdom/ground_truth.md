# Senior Wisdom — Golden Fixture

> code-hijack 평가용 ground truth.
> 실제 시니어 프론트엔드 개발자와 협업하면서 **말로 설명 듣고 나서야 이해한** 규칙들.
> MVP가 이 규칙들을 얼마나 재현하는지 측정하는 기준.

## 이 픽스처가 왜 중요한가

이 규칙들의 공통점:
1. **AI가 쉽게 "최적화"해서 망가뜨림** — 겉보기엔 불필요해 보임
2. **실패 모드가 즉각 드러나지 않음** — 런타임, 프로덕션, 디버깅 중에야 발견
3. **시니어가 설명 안 해주면 이유를 모름** — 단순 패턴 모방으로는 전달 불가

code-hijack이 진짜 가치 있으려면 이런 규칙을 **이유까지** 추출해야 함.

## 평가 기준

MVP (또는 Phase 1.5) 실행 후 생성된 출력을 이 문서와 비교:

| 체크 항목 | 통과 조건 |
|-----------|-----------|
| 규칙 포착 | 5개 규칙 중 몇 개를 발견했나 |
| 이유 깊이 | 단순 "일관성" 이상의 실질적 사유가 있나 |
| AI trap 경고 | AI가 저지를 실수를 ❌ 예시로 짚었나 |
| 참조 파일 | 실제 파일 경로를 인용했나 |
| 우선순위 | MUST/SHOULD가 합리적인가 |
| **레이어 배치** | Phase 1.5 — 올바른 레이어 파일에 배치됐나 (Rule 1,2 → frontend.md / Rule 3 → devops.md / Rule 4,5 → shared.md) |

## 레이어 매핑 요약

| 규칙 | 예상 레이어 | 예상 출력 파일 |
|------|------------|---------------|
| 1. `.data` 래퍼 | frontend | `frontend.md` |
| 2. TS 스타일 분리 | frontend | `frontend.md` |
| 3. pnpm | devops + shared | `devops.md` + `shared.md` 교차 노출 또는 `devops.md` 주요 기록 |
| 4. 내장 메서드 우선 | shared | `shared.md` |
| 5. 설계 먼저 | shared | `shared.md` |

---

# Ground Truth Rules

## Rule 1: `.data` 응답 래퍼 유지

**Layer**: frontend
**Priority**: MUST
**AI trap score**: 9/10 (AI가 거의 항상 평탄화해버림)

### 설계 의도
서버 응답은 `response.data.X` 형태로 접근한다. fetcher/axios 인터셉터에서 `.data`를 벗겨내 평탄화하지 않는다.

### ✅ Good
```typescript
const response = await api.get('/users/me');
const user = response.data.user;
```

### ❌ AI-trap (AI가 '개선'이라 착각하는 패턴)
```typescript
// fetcher.ts에서 response.data만 반환하도록 래핑
api.interceptors.response.use(res => res.data);

// 호출부
const user = await api.get('/users/me');  // 평탄화됨
```

### Reason (시니어가 실제로 설명한 이유)
- 에러 발생 시 **어느 레이어에서 터졌는지** 즉시 구분 가능
  - `response === undefined` → 네트워크 레이어 실패
  - `response.data === undefined` → HTTP 래핑 실패
  - `response.data.user === undefined` → 비즈니스 로직 실패
- 401 vs 404 vs 500 에러 핸들러가 응답 구조에 의존
- 평탄화하면 디버깅 시 스택 trace로 경계 구분 불가

### Failure mode
AI가 fetcher에서 `.data`를 벗기면 → 프로덕션 에러 로그에서 "undefined of undefined" 류 에러가 쏟아지고 원인 레이어 추적에 수 시간 소요.

### Checklist
- [ ] fetcher/인터셉터에서 `.data`를 벗겨내지 않았는가
- [ ] 호출부에서 `response.data.X` 패턴을 유지하는가

---

## Rule 2: TypeScript 스타일 파일 분리

**Layer**: frontend
**Priority**: MUST
**AI trap score**: 6/10 (AI는 한 파일에 다 몰아 쓰려는 경향)

### 설계 의도
분리 가능한 것은 **전부 분리**한다. 하나의 파일은 하나의 책임만. 가독성이 유지보수성보다 우선.

### ✅ Good
```
components/UserCard/
  UserCard.tsx           # 컴포넌트 로직
  UserCard.styles.ts     # styled 정의
  UserCard.types.ts      # 타입 정의
  UserCard.hooks.ts      # 커스텀 훅
  index.ts               # 재노출
```

### ❌ AI-trap
```typescript
// UserCard.tsx — 한 파일에 전부
import styled from 'styled-components';

type UserCardProps = { ... };          // 타입
const Container = styled.div`...`;      // 스타일
const Title = styled.h2`...`;           // 스타일
function useUserData() { ... }          // 훅
export function UserCard(props) { ... } // 컴포넌트
```

### Reason
- 한 파일을 열었을 때 **뭘 보고 있는지 즉시 명확**
- diff 리뷰 시 "스타일 변경" vs "로직 변경"이 파일 단위로 분리됨
- 스타일만 수정하려 할 때 컴포넌트 로직과 격리되어 안전
- 파일 이름이 곧 문서

### Failure mode
AI가 한 파일에 모든 걸 섞어 쓰면 → PR 리뷰 시 "이게 스타일 수정인지 로직 수정인지" 파악에 시간 소요, 머지 충돌 증가.

### Checklist
- [ ] 스타일, 타입, 훅, 컴포넌트가 각각 별도 파일인가
- [ ] `index.ts`로 깔끔하게 재노출하는가

---

## Rule 3: 패키지 매니저 = pnpm

**Layer**: devops (+ shared — 프론트/백 모두 영향)
**Priority**: MUST
**AI trap score**: 4/10 (AI는 `npm install` 명령을 먼저 제안함)

### 설계 의도
pnpm을 사용한다. npm/yarn 명령어를 섞지 않는다.

### ✅ Good
```bash
pnpm install
pnpm add react
pnpm dev
```

### ❌ AI-trap
```bash
npm install          # lockfile 충돌
yarn add react       # node_modules 구조 망가뜨림
```

### Reason (추론 — 시니어 실제 설명 미확인)
- 디스크 공간 절약 (하드링크 기반 content-addressable store)
- workspace/monorepo 지원이 npm보다 견고
- lockfile 형식 차이로 팀 내 혼용 시 의존성 깨짐
- CI에서 `pnpm-lock.yaml`을 단일 소스로 사용

### Failure mode
AI가 `npm install`로 설치 → `package-lock.json`과 `pnpm-lock.yaml` 동시 존재 → 팀원 간 의존성 버전 불일치 → "내 머신에선 되는데" 문제.

### Checklist
- [ ] `pnpm-lock.yaml`만 있고 다른 lockfile은 없는가
- [ ] 문서/스크립트에서 pnpm 명령어만 사용하는가

---

## Rule 4: 내장 메서드 우선, 함수 남발 금지

**Layer**: shared (프론트/백 모두 적용)
**Priority**: SHOULD
**AI trap score**: 8/10 (AI는 "재사용성"이라며 래퍼 함수를 만들려 함)

### 설계 의도
언어/라이브러리가 제공하는 메서드로 가능하면 **헬퍼 함수를 만들지 않는다**. 추상화는 최소 2회 반복 패턴이 확인된 뒤 도입.

### ✅ Good
```typescript
// Array.prototype.map 그대로 사용
const names = users.map(u => u.name);

// Optional chaining 그대로 사용
const city = user?.address?.city;
```

### ❌ AI-trap
```typescript
// 불필요한 헬퍼
function extractNames(users: User[]): string[] {
  return users.map(u => u.name);
}

function safeGet<T, K>(obj: T, path: K): unknown {
  // 커스텀 safe-get 함수... 이미 ?. 있는데
}
```

### Reason
- 표준 메서드는 **모든 개발자가 이미 앎** — 추가 학습 비용 없음
- 래퍼 함수는 한 번 정의하면 추적 비용이 누적됨 (정의 찾기, 테스트, 문서)
- "재사용될 수도 있다"는 가정은 **대부분 틀림** — YAGNI
- 추상화는 *패턴이 드러난 후* 추출하는 것이지, *예상해서* 만드는 게 아님

### Failure mode
AI가 헬퍼를 남발하면 → 코드베이스에 비슷한 이름의 유틸 10개 (`extractNames`, `getNames`, `pickName`) → 어느 걸 써야 할지 팀원이 혼란.

### Checklist
- [ ] 표준 메서드/문법으로 해결 가능한데 헬퍼를 만들지 않았는가
- [ ] 새 유틸 함수 추가 시 동일 패턴이 2회 이상 반복됐는가

---

## Rule 5: 설계 먼저, 구현은 그 안에서

**Layer**: shared (워크플로우 규칙이라 전체 레이어 적용)
**Priority**: MUST
**AI trap score**: 7/10 (AI는 요구사항 받자마자 코드부터 씀)

### 설계 의도
코드를 짜기 전에 **설계를 확실히 잡는다**. 데이터 흐름, 타입, 컴포넌트 경계, 에러 처리 경로를 먼저 정의한 뒤 그 **틀 안에서만** 구현한다.

### ✅ Good (워크플로우)
```
1. 요구사항 분석 → 유스케이스 목록
2. 데이터 모델 설계 → 타입 정의
3. 컴포넌트/모듈 경계 그리기 → 파일 구조
4. 에러/로딩/엣지 케이스 열거
5. ── 여기서부터 ── 구현 시작
```

### ❌ AI-trap
```
1. "UserCard 컴포넌트 만들어줘" 요청 받음
2. 즉시 tsx 파일 생성, 코드 타이핑 시작
3. props 타입 즉흥적으로 정의
4. API 호출 위치, 에러 처리, 로딩 상태 중 뭘 부모에서 뭘 자식에서 할지 안 정한 채 진행
5. 나중에 "아 이건 부모에서 해야 하네" → 전면 재작성
```

### Reason
- **재작성 비용 > 설계 비용** — 코드 지우는 것보다 설계 수정이 훨씬 쌈
- AI는 즉흥적으로 짜면 **같은 결정을 여러 번 번복** (어느 레이어에서 에러 처리할지 등)
- 설계가 먼저 있으면 구현 시 **"이건 틀을 벗어나니 멈춰야 함"** 판단 가능
- 코드 리뷰에서 "왜 이렇게 짰나"에 답변 가능 (설계 문서 참조)

### Failure mode
AI가 설계 없이 바로 코드를 쓰면 → 파일 구조가 즉흥적, 같은 책임이 여러 곳에 중복, PR 리뷰에서 "구조부터 다시" 반복 → 형님 시간 3배 소요.

### Checklist
- [ ] 코드 작성 전 데이터 흐름/타입/컴포넌트 경계가 문서로 존재하는가
- [ ] 구현 중 설계 범위를 벗어나려 할 때 멈추고 설계를 먼저 수정했는가

---

# 정리 — 이 5개 규칙의 공통 교훈

AI에게 단순히 "이 규칙을 지켜라"라고 하면 다음 번에 또 어깁니다. 이유를 납득시켜야 지속.

**code-hijack이 반드시 추출해야 할 것**:
1. **규칙** — 패턴 자체
2. **이유** — 왜 이게 중요한지 (디버깅 편의, 리뷰 비용, YAGNI 등 **실질적 근거**)
3. **AI 함정** — AI가 "개선"이라 오해할 안티패턴
4. **실패 모드** — 안 지키면 구체적으로 뭐가 터지는가
5. **우선순위** — MUST/SHOULD 구분

MVP 출력이 이 다섯 중 **3개 이상**을 포함하면 Phase 1 성공으로 본다.

---

## 메타 — 이 문서의 상태

- Rule 1, 2, 5: 형님이 경험 기반 설명
- Rule 3: 이유 부분은 Claude 추론 (시니어 실제 설명 미확인) — **검증 필요**
- Rule 4: "불필요한 함수 안 만듦"에서 Claude가 YAGNI/추상화 원칙으로 확장 — **범위 확인 필요**

형님이 시간 될 때 확인해서 틀린 부분 알려주시면 수정할게요.
