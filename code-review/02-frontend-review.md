# 프론트엔드 코드리뷰

> 대상: `web/src/` (React 19 + TypeScript, Vite)
> 리뷰 일자: 2026-03-14

---

## 스코어카드

| 영역 | 점수 | 비고 |
|------|------|------|
| 코드 품질 | 8.5/10 | SSE/폴링 패턴 우수, 대형 파일 분리 필요 |
| TypeScript 타입 안전 | 8.0/10 | `any` 5건만 존재 |
| Hook 품질 | 9.5/10 | AbortController/cleanup 완비 |
| 컴포넌트 구조 | 7.0/10 | 2개 파일 1,600+ LOC |
| 보안 | 8.0/10 | 시크릿 노출 없음, localhost 하드코딩 |

---

## 우수 사항

### 1. AbortController 패턴 (useSSE.ts, usePolling.ts)

```typescript
// useSSE.ts — SSE 연결 cleanup 완비
useEffect(() => {
    const controller = new AbortController();
    // ... SSE 연결 ...
    return () => controller.abort();
}, []);
```

모든 Hook에서 cleanup 패턴이 일관되게 적용됨.

### 2. SSE → REST 폴링 자동 폴백

SSE 연결 실패 시 REST API 폴링으로 자동 전환. 지수 백오프 적용.

### 3. TypeScript 타입 안전

전체 코드베이스에서 `any` 사용 5건만 존재 (아래 참조). 대부분 적절한 타입 지정.

---

## 이슈

### F1. `any` 타입 사용 (5건)

| 파일:라인 | 코드 | 수정 제안 |
|-----------|------|----------|
| `smcZonePrimitive.ts:97-98` | `private _chart: any = null` | `IChartApi \| null` |
| `TechnicalChart.tsx:261` | `const markers: any[] = []` | `SeriesMarker<Time>[]` |
| `api.ts:199` | `catch (error: any)` | `catch (error: unknown)` |
| `useAnalyticsData.ts:22` | `catch (err: any)` | `catch (err: unknown)` |

---

### F2. 대형 파일 분리 필요

| 파일 | LOC | 권장 |
|------|-----|------|
| `ScalpAnalyzer.tsx` | 1,658 | 차트/패널/설정 3개 컴포넌트로 분리 |
| `FabioStrategy.tsx` | 1,613 | AMT/Triple-A/실행 3개 컴포넌트로 분리 |
| `api.ts` | 883 | 도메인별 모듈 분리 (market, backtest, rebalance) |

나머지 페이지는 100-300 LOC로 적절.

---

### F3. 하드코딩 URL (2건)

| 파일:라인 | 코드 |
|-----------|------|
| `api.ts:42` | `const API_BASE_URL = 'http://localhost:8000/api/v1'` |
| `useSSE.ts:9` | `const API_BASE_URL = 'http://localhost:8000/api/v1'` |

**영향**: 프로덕션 배포 시 URL 변경 불가.

**수정**: `import.meta.env.VITE_API_URL` 환경변수 사용.

---

### F4. 중복 UI 패턴

`ScalpAnalyzer.tsx`와 `FabioStrategy.tsx`에 동일한 인라인 atom 컴포넌트 패턴 존재:

- `NIn` (숫자 입력) — 거의 동일 코드
- `Pill` (라벨+값 표시) — 동일 코드
- `Met` (메트릭 표시) — 동일 코드
- `Sec` (섹션 래퍼) — 동일 코드

**수정**: `components/common/` 디렉토리에 공유 컴포넌트로 추출.

---

### F5. SSE heartbeat 미감지

`useSSE.ts`에 서버 무응답 감지 로직 없음. 서버가 SSE 연결을 유지하면서 데이터 전송을 중단하면 클라이언트는 무한 대기.

**수정**: heartbeat 타임아웃 (30-60초) 추가, 초과 시 재연결.

---

## 파일별 LOC 분포

```
ScalpAnalyzer.tsx    1,658 ████████████████████ (28%)
FabioStrategy.tsx    1,613 ███████████████████▌ (27%)
api.ts                 883 ██████████▊          (15%)
Dashboard.tsx          305 ███▊                 (5%)
Risk.tsx               238 ███                  (4%)
useSSE.ts              233 ██▊                  (4%)
OptionCalculator.tsx   189 ██▍                  (3%)
usePolling.ts          171 ██                   (3%)
기타 7개 파일          577 ███████              (10%)
```

상위 2개 파일이 전체의 55%를 차지 → 분리 우선순위 높음.

---

## 보안 리뷰

| 항목 | 상태 | 비고 |
|------|------|------|
| 하드코딩 시크릿 | ✅ 안전 | API 키 등 노출 없음 |
| XSS | ✅ 안전 | React JSX 자동 이스케이프 |
| CORS | ⚠️ 확인 필요 | 백엔드 `allow_origins` 설정 확인 |
| 환경변수 URL | ❌ 미적용 | localhost 하드코딩 |
