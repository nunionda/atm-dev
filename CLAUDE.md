# ATS — Automated Trading System

## Project Overview

KOSPI200 / S&P500 / NASDAQ100 멀티마켓 자동매매 시스템.
모멘텀 스윙 + SMC(Smart Money Concepts) 듀얼 전략 엔진.

- **Backend**: Python 3.11+, FastAPI, SQLite (SQLAlchemy ORM)
- **Frontend**: React 19 + TypeScript, Vite, lightweight-charts
- **Broker**: 한국투자증권 (KIS) API, 모의/실전 전환
- **Notification**: Telegram Bot
- **Data**: yfinance (글로벌), Naver Finance (KRX 파생)

---

## Architecture

### 3-Layer Monolith

```
Orchestrator   core/main_loop.py, state_manager.py, scheduler.py
     ↓
Domain         strategy/, risk/, order/, position/
     ↓
Infrastructure infra/broker/, infra/db/, infra/notifier/, infra/logger.py
```

### Backend Module Map (`ats/`)

| Layer | Module | Purpose |
|-------|--------|---------|
| API | `api/app.py` | FastAPI + CORS + SSE lifespan |
| API | `api/routes.py` | `/analyze/{ticker}` 기술적 분석 |
| API | `api/sim_routes.py` | 실시간 시뮬레이션 |
| API | `api/rebalance_routes.py` | 포트폴리오 리밸런싱 |
| API | `api/backtest_routes.py` | 백테스트 실행/결과 |
| API | `api/market_overview.py` | 마켓 오버뷰 집계 |
| API | `api/ticker_list.py` | 티커 검색/해석 |
| Core | `core/main_loop.py` | 4-Phase 매매 루프 |
| Core | `core/state_manager.py` | FSM 상태관리 (INIT→READY→TRADING→STOPPED→ERROR) |
| Core | `core/scheduler.py` | 매매 스케줄 관리 |
| Strategy | `strategy/base.py` | 전략 추상 인터페이스 |
| Strategy | `strategy/momentum_swing.py` | 모멘텀 스윙 전략 |
| Strategy | `strategy/smc_strategy.py` | SMC 4-Layer 스코어링 전략 |
| Risk | `risk/risk_manager.py` | 리스크 게이트 (RG1-RG4) |
| Order | `order/order_executor.py` | 주문 제출/추적 |
| Position | `position/position_manager.py` | 포지션 라이프사이클 |
| Simulation | `simulation/engine.py` | 실시간 시뮬레이션 엔진 |
| Simulation | `simulation/event_bus.py` | SSE 이벤트 버스 |
| Simulation | `simulation/universe.py` | 유니버스 관리 |
| Backtest | `backtest/historical_engine.py` | 히스토리컬 백테스트 |
| Backtest | `backtest/metrics.py` | 성과 지표 (ExtendedMetrics, PhaseStats) |
| Backtest | `backtest/rebalancer.py` | 리밸런싱 로직 |
| Analytics | `analytics/indicators.py` | 기술 지표 계산 (RSI, MACD, BB, Volume) |
| Data | `data/config_manager.py` | YAML 설정 + .env 로드 |
| Data | `data/market_data.py` | 시장 데이터 제공 |
| Infra | `infra/broker/kis_broker.py` | 한투 API 브로커 |
| Infra | `infra/db/models.py` | ORM 모델 (7 테이블) |
| Infra | `infra/db/repository.py` | 데이터 접근 계층 |
| Infra | `infra/notifier/telegram_notifier.py` | 텔레그램 알림 |

### Frontend Component Map (`web/src/`)

| Directory | Components | Purpose |
|-----------|-----------|---------|
| `pages/` | Dashboard, Operations, Performance, Risk, Rebalance, ScalpAnalyzer, FabioStrategy, OptionCalculator, Theory | 주요 페이지 |
| `components/dashboard/` | TechnicalChart, DrawingOverlay, SignalAnalysis, MarketRegimePanel, TickerSearch, VolumeProfile | 차트/분석 |
| `components/operations/` | PositionTable, OrderLog, SignalList, SystemStatusBar | 운영 모니터링 |
| `components/rebalance/` | BacktestSection | 백테스트 UI (전략 선택, 결과 표시) |
| `hooks/` | useSSE, useAnalyticsData, usePolling | 커스텀 훅 |
| `lib/` | api, chartUtils, signalEngine, strategyEngine, scalpEngine, fabioEngine, futuresEngine, smcZonePrimitive | 유틸리티 |

---

## Business Rules (절대 불변)

| ID | Rule | Value | Description |
|----|------|-------|-------------|
| BR-S01 | 손절 | **-10%** | 개별 종목 손절. 절대 변경 불가 |
| BR-R01 | 일일 손실 한도 | **-5%** | 도달 시 당일 매매 중단 |
| BR-R02 | MDD 한도 | **-15%** | 도달 시 시스템 정지 (Circuit Breaker) |
| BR-P01 | 최대 보유 종목 | **10** (BULL) / 6 (NEUTRAL) / 2 (BEAR) | 마켓 레짐별 차등 |
| BR-P02 | 종목당 최대 비중 | **15%** (BULL) / 12% (NEUTRAL) / 5% (BEAR) | |
| BR-P03 | 최소 현금 비율 | **30%** | 항상 유지 |
| BR-P04 | 트레이드당 리스크 | **1.5%** of equity | ATR 기반 포지션 사이징 |
| BR-P05 | 연속 손절 정지 | **3회** 연속 → 자동 정지 | |

---

## Strategy 1: Momentum Swing (6-Phase Pipeline)

> 참조: `stock_theory/alphaStrategy.md`, `stock_theory/TradingLogicFlow.md`

### Phase 0 — Market Regime

MA200 위 종목 비율(Breadth)로 판단. 5일 스무딩.
- **BULL** ≥ 65% → max position 10, max weight 15%
- **BEAR** ≤ 35% → max position 2, max weight 5%
- **NEUTRAL** 그 외 → max position 6, max weight 12%

### Phase 1 — Trend Confirm

MA 정렬 3/5 이상 OR (ADX > 25 AND +DI > -DI)
- STRONG: ADX > 50 | MODERATE: 25-40 | WEAK: 20-25
- **필터율: ~80.7%** (6,267 스캔 → 1,208 통과)

### Phase 2 — Trend Stage

BB squeeze_ratio, RSI, 52주 고점 %로 단계 판단:
- **EARLY**: squeeze < 0.8 OR (< 1.2 AND RSI < 65) → 사이징 1.2x
- **LATE**: BB > 2.0 OR RSI > 80 OR 52w high > 95% → 진입 차단
- **MID**: 나머지 → 표준 사이징

### Phase 3 — Entry Signal

**Primary (둘 다 필요)**:
- PS1: MA5/MA20 골든 크로스
- PS2: MACD 히스토그램 양전환 + 기울기 > 0

**Confirm (둘 다 필요)**:
- CF1: RSI 52-78 범위
- CF2: 거래량 ≥ MA20 × 1.5
- CF3 (optional): Slow RSI(28) 45-70

**Block**: Bearish divergence 감지 시 진입 차단

**Signal Strength Score (0-100)**:
PS × 25 + CF × 15 + ADX bonus (max 25) + Stage bonus (EARLY:15, MID:8) + RSI quality (max 10) + Volume bonus (max 10)

### Phase 4 — Risk Gate

- RG1: 일일 손실 ≥ -10% → 매매 중단
- RG2: MDD ≥ -15% → 시스템 정지
- RG3: 현재 보유 < 레짐별 max positions
- RG4: 현금 비율 ≥ 30%

### Phase 5 — Exit (우선순위 순)

| ID | Exit | Condition | Priority |
|----|------|-----------|----------|
| ES1 | 손절 | -5% (absolute) | 1 (최고) |
| ES2 | 익절 | BULL +20%, NEUTRAL +12%, BEAR +8% | 2 |
| ES3 | 트레일링 | Progressive ATR 기반 (아래 표 참조) | 3 |
| ES4 | 데드크로스 | MA5 < MA20, pnl ≥ 2%: tight trail 1.5×ATR min -2%; else 즉시 청산 | 4 |
| ES5 | 최대 보유 | BULL 40일, NEUTRAL 25일, BEAR 15일 | 5 |
| ES6 | 시간 감쇄 | 보유 기간 대비 수익률 체크 | 6 |
| ES7 | 리밸런스 | 리밸런싱 주기 청산 | 21 |

**Progressive Trailing Stop (ES3)**:

| PnL 구간 | ATR 배수 | 최소 floor |
|----------|---------|-----------|
| ≥ 15% | 5 × ATR | -8% |
| ≥ 10% | 4 × ATR | -6% |
| ≥ 7% | 3.5 × ATR | -5% |
| default | 3 × ATR | -4% |

### Position Sizing

```
raw_qty = equity × 0.01 / max(ATR, price × 0.03)
final_qty = raw_qty × strength_mult × trend_mult × stage_mult × alignment_mult
```

Quality multipliers: strength (0.5-1.5), trend (STRONG:1.2, MODERATE:1.0, WEAK:0.7), stage (EARLY:1.2, MID:1.0, LATE:0.6), alignment (0.8-1.2).
Cash floor 20% 및 레짐별 max_weight로 최종 cap.

---

## Strategy 2: SMC 4-Layer Scoring

> 참조: `stock_theory/smcTheory.md`, `ats/strategy/smc_strategy.py`

### Market Structure

- **BOS (Break of Structure)**: 추세 지속 확인. `Close > Previous_HH` (강세) / `Close < Previous_LL` (약세). 반드시 봉 몸통 마감 기준.
- **CHoCH (Change of Character)**: 최초 반전 신호. 상승 추세에서 마지막 HL 하향 돌파 = 약세 CHoCH.
- **Swing Point**: N-candle 프랙탈 (config: `swing_length=3`).
- **Lifecycle**: Impulse → Retracement → Mitigation → Expansion

### 4-Layer Architecture

**Layer 1 — SMC Bias (40점)**

BOS/CHoCH 기반 시장 방향 판단:
- Long bias: BOS bullish detected
- Short bias: BOS bearish detected
- Neutral: No clear structure

**Layer 2 — BB Squeeze + ATR (20점)**

변동성 수축 → 확장 전환 포착:
- BB squeeze_ratio < 0.8: 수축 (잠재 폭발)
- ATR 증가 추세: 확장 확인

**Layer 3 — Volume + Momentum (20 + 20점)**

- OBV (20점): On-Balance Volume 추세 확인
- ADX + MACD (20점): 추세 강도 + 방향 일치 확인

**Entry Threshold**: 총점 ≥ 60/100

### SMC Exit Rules

| ID | Exit | Condition |
|----|------|-----------|
| ES_SMC_SL | ATR 손절 | Entry - ATR × `atr_sl_mult` (default 2.0) |
| ES_SMC_TP | ATR 익절 | Entry + ATR × `atr_tp_mult` (default 3.0) |
| ES_CHOCH | CHoCH 반전 | 보유 중 반대 방향 CHoCH 발생 시 청산 (config: `choch_exit=true`) |

### SMC Config (`config.yaml` → `smc_strategy`)

```yaml
smc_strategy:
  swing_length: 3           # Swing Point 프랙탈 길이
  entry_threshold: 60       # 최소 진입 점수 (0-100)
  atr_sl_mult: 2.0          # ATR × 배수 = Stop Loss
  atr_tp_mult: 3.0          # ATR × 배수 = Take Profit
  choch_exit: true           # CHoCH 발생 시 청산 여부
  ob_lookback: 20            # Order Block 탐색 범위
  fvg_mitigation: true       # FVG 미티게이션 추적
  weight_smc: 40             # Layer 1 가중치
  weight_bb: 20              # Layer 2 가중치
  weight_obv: 20             # Layer 3a 가중치
  weight_momentum: 20        # Layer 3b 가중치
```

---

## Technical Indicators Reference

> 참조: `stock_theory/trendTheory.md`, `stock_theory/TrendingJudgeIndex.md`

| Indicator | Period | Parameters | Usage |
|-----------|--------|-----------|-------|
| MA (SMA) | 5, 20, 60, 120, 200 | — | 추세 방향, 골든/데드 크로스 |
| ADX/DMI | 14 | +DI, -DI threshold 20-25 | 추세 강도 |
| MACD | 12, 26, 9 | Fast, Slow, Signal | 모멘텀 |
| RSI | 14 | Entry range 42-68 | 과매수/과매도 |
| Slow RSI | 28 | Confirm range 45-70 | 장기 확인 |
| BB | 20, 2σ | squeeze_ratio | 변동성 |
| ATR | 14 | Stop/trail 기준 | 리스크 관리 |
| Volume MA | 20 | Confirm ≥ 1.5× | 거래량 확인 |
| OBV | — | — | 매집/분산 |

### Macro Trend Filters (4 필터 동시 충족 = 강세)

- F1: MA 정렬 `Price > MA20 > MA60 > MA120 > MA200`
- F2: 거래량 돌파 `Price > prev_high AND Volume > avg × 2.0`
- F3: 모멘텀 `RSI > 60 AND MACD > Signal`
- F4: 매크로 `rate_policy ∈ {HOLD, CUT} AND fear_greed > 50`

Combined: 4/4 = 강세(풀 포지션), 3/4 = 일반, 2/4 = 보수적, 1/4 = 매매 중단

---

## MDD Defence — 7-Layer Architecture

> 참조: `stock_theory/mddDefenceStrategy.md`

| Layer | Defence | Detail |
|-------|---------|--------|
| 1 | Market Regime | BULL 80%, NEUTRAL 72%, BEAR 10% 투자 상한 |
| 2 | Trend Filter | Phase 1-2 → 나쁜 진입 80.7% 필터링 |
| 3 | Signal Quality | Phase 3 고품질 시그널만 |
| 4 | Risk Gates | RG1-RG4 (daily -3%, MDD -10%, positions, cash 20%) |
| 5 | ATR Position Sizing | 1% risk/trade, 동시 10 손절 = 이론 최대 -10% |
| 6 | 5-Stage Exit Priority | ES1-ES5 cascade |
| 7 | Progressive Trailing | 슈퍼 위너 수익 보호 |

**실적**: 정상 조건 MDD -4.9% ~ -6.2%, 2008 위기 -11.8% (RG2 Circuit Breaker 작동)
**레짐 전환 스무딩**: 5일 확인 후 전환 (채터링 방지)

---

## Exit Strategy Reference

> 참조: `stock_theory/ExitStrategyIndex.md`

### Stop-Loss Methods

- **ATR Stop**: Chandelier = High - ATR(22)×3.0, Keltner = Entry - ATR(14)×2.0
- **Structural Stop**: Swing low / OB 무효화 아래
- **MA-based**: Short-term 10-20 EMA, Swing 50 MA, Position 200 MA
- **Fixed Risk**: Capital × Risk% / (Entry - Stop) = Position Size

### Take-Profit Methods

- **R-Multiple**: 2R/3R 목표. 분할 청산: 50% at 1R + 나머지 trailing
- **Fibonacci**: 1.0 (보수), 1.618 (표준), 2.618 (강추세)
- **BB Upper Band** 터치, **RSI/Stochastic Divergence** 확인

**원칙**: R:R 최소 1:2. 분할 청산 선호. 일관성 > 최적화.

---

## Kelly Criterion & Position Sizing

> 참조: `stock_theory/Kelly Criterion.md`

```
f* = (b × p - q) / b
```

- b = 평균 수익 / 평균 손실, p = 승률, q = 1 - p

| Asset Type | Kelly Coefficient | 적용 |
|-----------|------------------|------|
| 현물/주식 | 0.5 (Half-Kelly) | ATS 기본 |
| 선물 | 0.2-0.3 | 레버리지 보정 |
| 옵션 | ≤ 0.1 | 고위험 보정 |

Final weight = `f* × kelly_coeff`, [0, max_cap] 클램핑. 현금 20% 예비.

---

## Futures & Options Specifications

> 참조: `stock_theory/kospi200_futures.md`, `stock_theory/kospi200_options.md`

### KOSPI200 선물

| Spec | Value |
|------|-------|
| 계약 승수 | 250,000 원/pt |
| 호가 단위 | 0.05pt = 12,500원 |
| 결제월 | 3, 6, 9, 12월 (3년 내 7개월) |
| 거래 시간 | 정규 08:45-15:45, 야간 18:00-06:00 |
| 최종 거래일 | 결제월 2째 목요일 |
| 가격 제한 | 3단계: ±8%, ±15%, ±20% |
| 결제 | 현금결제 |

### KOSPI200 옵션

| Spec | Value |
|------|-------|
| 계약 승수 | 250,000 원/pt |
| 호가 단위 | 프리미엄 < 10pt: 0.01pt (2,500원), ≥ 10pt: 0.05pt (12,500원) |
| 행사가 간격 | 근월 3개월 ATM±80pt at 2.5pt, 4-8월 ATM±120pt at 5pt |
| 행사 방식 | European (만기일만 행사) |
| Weekly 옵션 | ATM±40pt at 2.5pt, 월/목 만기 |

### Black-Scholes Formula

> 참조: `stock_theory/BlackScholesEquation.md`

```
C = S₀ × N(d₁) - K × e^(-rT) × N(d₂)
P = K × e^(-rT) × N(-d₂) - S₀ × N(-d₁)
d₁ = [ln(S₀/K) + (r + σ²/2)T] / (σ√T)
d₂ = d₁ - σ√T
```

Greeks: Delta (dC/dS), Gamma (dΔ/dS), Theta (dC/dT, 일반적으로 음수), Vega (dC/dσ, 항상 양수), Rho (dC/dr)

---

## Scalping Playbook (Fabio Strategy)

> 참조: `stock_theory/scalpingPlaybook.md`

### AMT 3-Stage Filter

1. **Market State**: Balance vs Imbalance 판별
2. **Location**: Volume Profile (LVN/POC/VAH/VAL) 기반 위치
3. **Aggression**: Footprint order flow (delta spike, CVD 압력) 확인

3가지 모두 정렬 = 진입. Multi-TF: 30m (bias) → 5m (staging) → 1m (execution).

### Triple-A Model

Absorption (고거래량 + 좁은 범위) → Accumulation (감소 거래량 + 수렴) → Aggression (delta spike + stacked imbalance)
3단계 모두 정렬 = Grade A (풀 리스크). Grade B = 50%, Grade C = 25%.

### 스캘핑 리스크

- 트레이드당 0.25-0.5%
- 3회 연속 손절 → 매매 중단
- 일일 손실 하드 한도
- 최대 1 포지션
- Stop buffer 1-2 ticks

---

## Futures Trading Strategy

> 참조: `stock_theory/futuresStrategy.md`, `stock_theory/future_trading_stratedy.md`

### Z-Score 기반 통계적 진입

```
Z = (x - μ) / σ
```
Z < -2.0 = 통계적 과매도 (매수), Z > +2.0 = 과매수 (매도)

### Expected Value Engine

```
EV = P(W) × Avg.W - P(L) × Avg.L
```
EV > 0 일 때만 진입.

### ATR 기반 진입/청산

- Breakout filter: `(High - PrevClose) > 0.5 × ATR` = 유효 돌파
- Trend following: `Close > PrevClose + 1.5-2 × ATR` = 추세 진입
- Trailing stop: `Entry - 1.5-2 × ATR`, 가격 상승 시 래칫 업
- Chandelier exit: `Highest - 3 × ATR`

### Dynamic ATR Multiplier

```
mult = 2.0 if ADX < 20 else 1.5
```

---

## Database Schema

7 main tables (SQLAlchemy ORM, `infra/db/models.py`):

| Table | Key Fields | Purpose |
|-------|-----------|---------|
| Universe | stock_code (PK), stock_name, market, sector | 종목 마스터 |
| Positions | position_id (PK), entry/exit price+date, stop_loss, trailing_high, pnl | 포지션 관리 |
| Orders | order_id (PK), side, type, status, filled_price, broker_order_id | 주문 이력 |
| TradeLog | log_id (PK), event_type, detail (JSON) | 이벤트 감사 추적 |
| DailyReport | report_id (PK), trade_date (unique), pnl, mdd, positions | 일간 성과 |
| ConfigHistory | history_id (PK), param_key, old/new_value | 설정 변경 감사 |
| SystemLog | log_id (PK), level, module, message, extra (JSON) | 시스템 로그 |

---

## Configuration

### `config.yaml` — 전략 파라미터

System, schedule, universe, strategy (momentum), smc_strategy, exit, portfolio, risk, order 섹션.
모든 전략 파라미터는 코드가 아닌 설정 파일로 관리.

### `.env` — 시크릿 (절대 커밋 금지)

```
KIS_APP_KEY=
KIS_APP_SECRET=
KIS_ACCOUNT_NO=
KIS_IS_PAPER=true
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
DB_PATH=data_store/ats.db
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/analyze/{ticker}` | 기술적 분석 (period, interval) |
| POST | `/rebalance/backtest` | 백테스트 실행 (market, start_date, end_date, strategy) |
| GET | `/rebalance/backtest/status` | 백테스트 진행 상태 |
| GET | `/rebalance/backtest/result` | 캐시된 백테스트 결과 |
| GET | `/stream/{market_id}` | SSE 실시간 시뮬레이션 스트림 |

---

## Transaction Costs

| Item | Value |
|------|-------|
| Slippage | 0.1% / side |
| Commission | 0.015% / side |
| Total round-trip | ~0.23% |

---

## Commands

```bash
# Backend (프로젝트 루트에서 실행)
python3 main.py start                # 시스템 시작
python3 main.py api                  # API 서버 실행 (FastAPI)
python3 main.py status               # 상태 확인
python3 main.py init-db              # DB 초기화

# Tests
python3 run_tests.py                 # 독립 단위 테스트 43건
pytest ats/tests/ -v                 # pytest 전체 (SQLAlchemy 필요)

# Frontend
cd web && npm run dev                # 개발 서버 (port 5173)
cd web && npx tsc --noEmit           # TypeScript 타입 체크
cd web && npm run build              # 프로덕션 빌드

# Scripts
python3 ats/scripts/health_check.py      # 헬스체크
python3 ats/scripts/paper_trade_test.py  # 모의투자 연동 테스트
```

---

## Development Rules

### UI Changes

When modifying HTML/JSX files that render UI, always verify the page renders correctly after changes by checking for syntax errors, unclosed tags, and runtime errors before considering the task complete.

### Data & Charts

For chart/visualization work: always verify that displayed data uses real API data (real dates, real prices) rather than synthetic/placeholder data. Never assume hardcoded sample data is acceptable unless explicitly requested.

### Pre-Commit Checklist

After making multi-file changes, run the build/dev server and confirm no runtime errors before committing.
- TypeScript: `cd web && npx tsc --noEmit`
- Python: `python3 run_tests.py` or `pytest ats/tests/ -v`

### yfinance API Constraints

Intraday intervals (1m, 5m, 15m, 30m, 1h) only support period values of `1d`, `5d`, `1mo`, or `7d`. Never use `2mo` or longer periods with intraday intervals.

### Tool Limitations

Do not attempt interactive CLI authentication flows (e.g., `gh auth login`, interactive menus). Instead, instruct the user to run those commands in their own terminal, or use token-based auth.

### Git Workflow

Before attempting `git push` or `gh pr create`, verify a git remote is configured with `git remote -v`. If none exists, ask the user for the remote URL before proceeding.

---

## Key File Paths

```
main.py                           # 엔트리포인트 (sys.path → ats/)
run_tests.py                      # 독립 테스트 러너 (43건)
config.yaml                       # 전략 설정
ats/
├── api/app.py                    # FastAPI 엔트리포인트
├── api/backtest_routes.py        # 백테스트 라우트
├── strategy/momentum_swing.py    # 모멘텀 전략
├── strategy/smc_strategy.py      # SMC 전략
├── simulation/engine.py          # 시뮬레이션 엔진
├── backtest/historical_engine.py # 히스토리컬 백테스터
├── backtest/metrics.py           # 성과 지표
├── data/config_manager.py        # 설정 관리
├── risk/risk_manager.py          # 리스크 관리
├── infra/broker/kis_broker.py    # KIS API
├── infra/db/models.py            # DB 모델
├── scripts/                      # 유틸리티 스크립트 (7개)
├── tests/                        # pytest 테스트
web/
├── src/lib/api.ts                # API 클라이언트
├── src/pages/Rebalance.tsx       # 리밸런싱 페이지
├── src/components/rebalance/BacktestSection.tsx  # 백테스트 UI
├── src/components/dashboard/TechnicalChart.tsx   # 차트 컴포넌트
stock_theory/                     # 트레이딩 이론 문서 (17개 파일)
```

---

## Theory Documentation (`stock_theory/`)

| File | Content |
|------|---------|
| `alphaStrategy.md` | Alpha 생성 전략 — 6-Phase 파이프라인 전체 스펙, 백테스트 결과 (Sharpe 2.16-2.79) |
| `smcTheory.md` | SMC 이론 — BOS/CHoCH, Order Block, FVG, 4-Layer 스코어링 |
| `TradingLogicFlow.md` | 이론 → 구현 매핑 (Dow Theory, Wyckoff, Elliott Wave → Phase 0-5) |
| `ExitStrategyIndex.md` | 청산 전략 총람 — ATR/Structural/MA/SAR Stop, R-Multiple/Fib TP |
| `mddDefenceStrategy.md` | MDD 방어 7-Layer 아키텍처 |
| `trendTheory.md` | 추세 판단 지표 — 매크로 4필터, 전략 분류, MA/ADX/BB |
| `TrendingJudgeIndex.md` | 추세 판단 인덱스 (trendTheory와 동일 내용) |
| `Kelly Criterion.md` | Kelly 공식 & 자산 배분 프레임워크 |
| `scalpingPlaybook.md` | Fabio Valentini 스캘핑 — AMT 3-Stage, Triple-A Model |
| `futuresStrategy.md` | 확률 기반 선물 기술분석 — Z-Score, EV Engine |
| `future_trading_stratedy.md` | ATR 기반 선물 매매 전략 |
| `kospi200_futures.md` | KOSPI200 선물 상품 규격 |
| `kospi200_options.md` | KOSPI200 옵션 상품 규격 |
| `kospi200_futures_simulation.md` | KOSPI200 선물 시뮬레이션 결과 |
| `kospi200_sim_report.md` | 옵션 전략 백테스트 리포트 (Black-Scholes 시뮬레이션) |
| `optionCalculator.md` | 옵션 계산기 아키텍처 (BS forward/inverse/Greeks) |
| `BlackScholesEquation.md` | Black-Scholes 방정식 레퍼런스 |

---

## Backtest Performance Summary

> `alphaStrategy.md` 기준. SP500 20-stock universe.

| Metric | Value Range |
|--------|-------------|
| Sharpe Ratio | 2.16 - 2.79 |
| CAGR | +13% ~ +69% |
| MDD | -4.9% ~ -6.2% |
| Profit Factor | 2.57 - 2.77 |
| Win Rate | ~55-60% |
| Phase Funnel | 6,267 스캔 → 112 진입 (1.8% 통과율) |

### Removed Features (성능 저하로 제거)

| Feature | 결과 | Sharpe 변화 |
|---------|------|-------------|
| Sector concentration limit | 다양성은 좋으나 성과 하락 | 2.79 → 2.27 |
| ADX acceleration filter | 과도한 필터링 | → 2.65 |
| ES6 time decay | 조기 청산 | → 2.23 |
| Equity momentum sizing | 불안정 | → 2.61 |
| Daily entry limit | 기회 상실 | → 2.35 |
| Adaptive trailing activation | 복잡성 대비 효과 미미 | → 2.45 |
