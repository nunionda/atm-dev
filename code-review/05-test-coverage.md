# 테스트 커버리지 현황

> 대상: `ats/tests/`, `run_tests.py`
> 리뷰 일자: 2026-03-14

---

## 현재 테스트 현황

### run_tests.py (자체 프레임워크, 43건)

| 테스트 모듈 | 건수 | 대상 |
|------------|------|------|
| `test_enums` | 4 | `common/enums.py` — MarketRegime, ExitReason, FuturesDirection |
| `test_types` | 6 | `common/types.py` — Signal, ExitSignal, FuturesSignal, PriceData |
| `test_state_manager` | 7 | `core/state_manager.py` — FSM 전이 (INIT→READY→TRADING) |
| `test_momentum` | 11 | `strategy/momentum_swing.py` — 진입/청산 시그널 |
| `test_risk` | 15 | `risk/risk_manager.py` — RG1-RG4 게이트 |
| **합계** | **43** | |

### test_sp500_futures.py (pytest, 20건)

| 테스트 | 건수 | 대상 |
|--------|------|------|
| SP500FuturesStrategy 초기화 | 2 | config 로딩, 기본값 |
| 지표 계산 | 4 | RSI, MACD, Z-Score, ATR |
| 4-Layer 스코어링 | 4 | 각 Layer 개별 + 합산 |
| SL/TP 계산 | 3 | 롱/숏/Dynamic ATR |
| 포지션 사이징 | 2 | Kelly, max_contracts |
| 트레일링 스탑 | 2 | 활성화, PnL 구간별 |
| 청산 cascade | 3 | ES1, ES_ATR, ES5 |
| **합계** | **20** | |

**총합: ~63건** (run_tests.py 43 + test_sp500_futures.py 20)

---

## 커버리지 매트릭스

### 커버된 모듈 (7개)

| 모듈 | 테스트 수 | 품질 | 비고 |
|------|----------|------|------|
| `common/enums.py` | 4 | ✅ 양호 | 열거형 값 검증 |
| `common/types.py` | 6 | ✅ 양호 | 데이터클래스 생성/검증 |
| `core/state_manager.py` | 7 | ✅ 양호 | FSM 전이 + 에러 케이스 |
| `strategy/momentum_swing.py` | 11 | ⚠️ 보통 | 기본 흐름만, edge case 부족 |
| `risk/risk_manager.py` | 15 | ✅ 양호 | RG1-4 + boundary 테스트 |
| `strategy/sp500_futures.py` | 20 | ⚠️ 보통 | e2e entry signal 누락 |
| `strategy/base.py` | — | ⚠️ 간접 | momentum 테스트에서 간접 커버 |

### 미커버 모듈 (17+개) — CRITICAL

| 모듈 | 중요도 | 이유 |
|------|--------|------|
| **`analytics/indicators.py`** | CRITICAL | 모든 전략의 기반 지표 계산 |
| **`api/app.py`** | CRITICAL | SSE, CORS, 라이프사이클 |
| **`api/routes.py`** | HIGH | `/analyze/{ticker}` 입력 검증 |
| **`api/backtest_routes.py`** | HIGH | 백테스트 실행 로직 |
| **`backtest/historical_engine.py`** | HIGH | 히스토리컬 백테스트 엔진 |
| **`simulation/engine.py`** | HIGH | 실시간 시뮬레이션 |
| **`data/config_manager.py`** | HIGH | YAML/env 로딩 (결함 포함) |
| **`infra/broker/kis_broker.py`** | HIGH | 실거래 API 연동 |
| `infra/db/models.py` | MEDIUM | ORM 모델 |
| `infra/db/repository.py` | MEDIUM | 데이터 접근 레이어 |
| `infra/notifier/telegram_notifier.py` | LOW | 알림 전송 |
| `core/main_loop.py` | HIGH | 매매 루프 (미존재) |
| `core/scheduler.py` | MEDIUM | 스케줄 관리 (미존재) |
| `position/position_manager.py` | HIGH | 포지션 관리 (미존재) |
| `order/order_executor.py` | HIGH | 주문 실행 (미존재) |
| `backtest/metrics.py` | MEDIUM | 성과 지표 (미존재) |

---

## 테스트 품질 평가

### 우수 사항

- 합성 OHLCV 데이터로 외부 의존성 없는 단위 테스트 ✅
- Boundary 테스트 존재 (RSI 범위, ATR 0 등) ✅
- FSM 상태 전이 에러 케이스 커버 ✅

### 개선 필요

| 항목 | 현재 | 권장 |
|------|------|------|
| 외부 의존성 mock | ❌ 없음 | yfinance, KIS API mock 필요 |
| 통합 테스트 | ❌ 없음 | 전략 → 주문 → 포지션 e2e |
| 프론트엔드 테스트 | ❌ 없음 | Jest/Vitest 기반 컴포넌트 테스트 |
| config 로딩 테스트 | ❌ 없음 | YAML 파싱, 타입 검증 |
| NaN/edge case | ⚠️ 부분 | 모든 지표에 NaN/Inf 입력 테스트 |
| 커스텀 프레임워크 | ⚠️ | pytest 통일 권장 |

---

## 권장 테스트 추가 (우선순위)

### Tier 1 (즉시)

| # | 대상 | 예상 건수 | 근거 |
|---|------|----------|------|
| T1 | `data/config_manager.py` | 15 | YAML 전체 섹션 로딩, .env, 타입 검증, 오타 경고 |
| T2 | `analytics/indicators.py` | 20 | RSI, MACD, BB, ATR, OBV 각 정상/NaN/edge |
| T3 | `sp500_futures.py` entry e2e | 5 | 지표→스코어→시그널 전체 흐름 |

### Tier 2 (백테스트 전)

| # | 대상 | 예상 건수 | 근거 |
|---|------|----------|------|
| T4 | `api/routes.py` | 10 | ticker 형식, 쿼리 파라미터, 에러 응답 |
| T5 | `backtest/historical_engine.py` | 10 | 수익률 계산, 포지션 관리 |
| T6 | `sp500_futures.py` 청산 e2e | 8 | 7단계 cascade 전체 흐름 |

### Tier 3 (프로덕션 전)

| # | 대상 | 예상 건수 | 근거 |
|---|------|----------|------|
| T7 | `infra/broker/kis_broker.py` (mock) | 10 | API 인증, 주문, 조회 |
| T8 | `simulation/engine.py` | 8 | SSE 이벤트, 에러 복구 |
| T9 | 프론트엔드 (Vitest) | 10 | 핵심 Hook, API 호출 |

---

## pytest vs run_tests.py

현재 두 개의 테스트 프레임워크가 혼재:

| 항목 | run_tests.py | pytest |
|------|-------------|--------|
| 파일 | `run_tests.py` | `ats/tests/test_*.py` |
| 실행 | `python3 run_tests.py` | `pytest ats/tests/ -v` |
| 기능 | 자체 assert/결과 출력 | fixture, parametrize, mock |
| 테스트 수 | 43건 | 20건 |

**권장**: pytest로 통일. run_tests.py의 43건을 `ats/tests/` 아래 pytest 형식으로 마이그레이션.
