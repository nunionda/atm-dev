# 선물 차트 Overlay 11개 × 4-Layer Scoring 매핑

`/futures` 페이지(ESFuturesScalping)의 lightweight-charts overlay 11개가 ESF Intraday Strategy의 4-Layer scoring에 어떻게 입력되는지 정리한 매핑 문서. backend/strategy/esf_intraday.py 코드 라인 참조 + 자산별 의미 차이.

---

# 전략별 지표 사용 기준 (Cognitive Map)

차트에 11개 overlay가 동시 표시되면 시각적 과부하 + 의사결정 혼란 발생. 시간대·전략별로 **핵심 지표 셋**과 **무시할 지표**를 명확히 분리해 사용한다.

## A. 터틀 트레이딩 (Turtle Trading — 스윙·추세 추종)

**시간대**: 일봉(1D) ~ 주봉. **타임프레임 전환**: 차트 `Period: 5D/1M`, `Interval: 1h/1D` 사용.

**원칙**:
- **Entry**: Donchian Channel 돌파 — 20일(System 1) 또는 55일(System 2) 고가/저가 돌파
- **Stop**: **Entry ± 2N** (N = 20일 ATR) — 사용자 명시 표준 ±2 ATR
- **Position Size**: `1% × Equity / (2N × multiplier)` — N(ATR) 기반 volatility sizing
- **Trail**: 10일 반대 방향 돌파 시 청산 (또는 Chandelier `High - 3N`)
- **Time Scale**: 수일 ~ 수주 보유

**사용 Overlay** (5개로 압축):
| Overlay | 역할 |
|---------|------|
| **EMA55** | 장기 추세 방향 (close > EMA55 = uptrend 환경) |
| **ATR** (subchart) | N 값 계산 — Stop/Sizing 핵심 |
| **VAH / VAL** (월간) | 균형 구간 이탈 = 추세 시작 신호 |
| **POC** (월간) | 평균회귀 vs 추세 돌파 분기점 |
| **MA200** (별도 표시 시) | 거시 추세 필터 |

**무시할 Overlay** (스윙에선 노이즈):
- EMA8, EMA21 — 단기 노이즈 (스윙 무관)
- BB, Mag MA — 평균회귀 신호 (Turtle은 추세 추종)
- VWATR S/R — intraday zone (스윙 시간대 무의미)
- LVN — intraday 균형 공백 (일봉 기준 의미 약함)

**예시 — 터틀 Long Entry (ES=F)**:
```
조건:
  1. close > 20일 high (Donchian 돌파)
  2. close > EMA55 (장기 uptrend 확인)
  3. ATR(20) = N → Stop = entry - 2N
  4. Equity 1% / 2N = position size
  5. Exit: close < 10일 low OR pnl = +6N (R:R 3:1)
```

---

## B. 단타 스캘핑 (Fabio + AMT — Intraday)

**시간대**: 1m ~ 15m. **타임프레임**: 차트 `Period: 1D/5D`, `Interval: 1m/5m/15m`.

**원칙**:
- **Entry**: AMT 3-Stage Filter — (1) Market State(Balance/Imbalance) → (2) Location(POC/VAH/VAL/LVN) → (3) Aggression(footprint delta + range expansion)
- **Stop**: 1-2 tick (매우 좁음) 또는 LVN edge / Mag MA reversion line
- **Take Profit**: R:R 2:1 (스캘프 Grade A) ~ 3:1 (Grade A 풀 포지션)
- **Position Size**: 0.25% ~ 0.5% risk / trade — Grade A 풀, B 50%, C 25%
- **Time Scale**: 수분 ~ 1시간 보유, EOD 청산
- **Daily Limits**: 3연속 손절 → 매매 중단 / max 5 trades/day

**사용 Overlay** (8개 — 풀 활용):
| Overlay | 역할 |
|---------|------|
| **EMA8 / EMA21** | 단기 추세 + direction veto (EMA55는 너무 느림) |
| **Mag MA** | 평균회귀 자석 — 가격이 best MA로 수렴하는 강도 (가장 reversion strength 높은 MA 자동 선택) |
| **VWATR S** | 매수 지지 zone — Mag MA - VWATR×mult, zone 진입 시 long bias |
| **VWATR R** | 매도 저항 zone — Mag MA + VWATR×mult, zone 진입 시 short bias |
| **POC** | Auction 균형점 — AT_POC = mean-reversion 진입 |
| **VAH** | Value Area High — ABOVE_VAH = imbalance bullish breakout |
| **VAL** | Value Area Low — BELOW_VAL = imbalance bearish breakout |
| **LVN** | Low Volume Node — AT_LVN = 가격 빠르게 통과 (Layer1 최고 점수 +10) |
| **BB** | 변동성 수축 + vol surge → breakout (BB squeeze < 0.75 + vol ≥ 1.5 → L4 +3pt) |

**무시할 Overlay**:
- **EMA55** — 스캘프 시간대(15m bars)에선 55-period가 너무 느림 → 추세 확인 외 불필요
- **ATR** (subchart) — 스캘프 stop은 tick 단위, ATR mult는 ESF 내부 SL/TP만 사용

**예시 — Fabio Long Scalp (MES=F, 15m)**:
```
조건 (Grade A = 50+ score):
  1. Market State: IMBALANCE_BULL (Z-Score > 1, 연속 상승 3봉)
  2. Location: AT_LVN OR ABOVE_VAH (L1 +10 또는 +3)
  3. Aggression: body_ratio > 0.65 + range_exp > 1.5 (L4 +10)
  4. EMA8 > EMA21 (단기 정배열, veto 통과)
  5. Vol surge (vol_ratio ≥ 1.5) + BB squeeze < 0.75 → L4 +3 보너스
Entry: market or 1-tick above signal bar
Stop: signal bar low - 1 tick (or LVN edge)
TP: R:R 2:1 (1차) / R:R 3:1 (2차 분할 청산)
```

---

## C. Decision Matrix — 언제 어느 전략을 쓰나

| 상황 | 권장 전략 | 사용 Overlay | 무시 Overlay |
|------|----------|------------|------------|
| 일봉 분석, 1주+ 보유 의도 | **Turtle** | EMA55, ATR, VAH/VAL(월간), POC, MA200 | EMA8/21, Mag MA, VWATR, LVN, BB |
| 15m intraday, 당일 청산 | **Scalping** | EMA8/21, Mag MA, VWATR S/R, POC/VAH/VAL/LVN, BB | EMA55, ATR(subchart) |
| 5m 데이트레이드, 수시간 보유 | **Scalping (조정)** | EMA8/21, Mag MA, POC/VAH/VAL | EMA55, BB(노이즈), LVN(과민) |
| Walk-Forward 전략 검증 | 자동(ESF 4-Layer) | 모든 11개 (backend 자동 가중) | — |

---

## D. UI 사용 가이드 — Cognitive Load 줄이는 법

**현재 차트는 11개 overlay 모두 동시 표시 → 혼란.** 사용자가 수동으로 끄고 볼 수 있는 방법:

1. **Turtle 모드 시야**:
   - 차트 Interval = `1h` 또는 `1D`로 변경
   - 차트 Period = `1M` 또는 `5D` 이상
   - EMA55, VAH/VAL, POC만 시각적으로 추적 (다른 overlay는 무시)
   - ATR 서브차트 활성화 (RSI/MACD/ZSCORE 끄기)

2. **Scalping 모드 시야**:
   - 차트 Interval = `5m` 또는 `15m`
   - 차트 Period = `1D` 또는 `5D`
   - EMA8, EMA21, Mag MA, VWATR S/R, POC/VAH/VAL/LVN, BB 모두 활용
   - EMA55는 화면에 있어도 추세 확인용 (entry 결정엔 영향 적음)

3. **빠른 판단 체크리스트**:
   - **"지금 보유 의도가 분 단위인가, 일 단위인가?"** 분 → 단타 / 일 → Turtle
   - **단타**라면 Mag MA + POC + VWATR 3개만 보면 됨 (entry 결정 핵심)
   - **Turtle**이라면 EMA55 + ATR + VAH/VAL 3개만 보면 됨 (entry/stop 결정 핵심)
   - 나머지 overlay는 **참고 정보**이지 **결정 입력**이 아니다.

---

## E. ESF 4-Layer Scoring과의 관계

backend의 `ESFIntradayStrategy` 4-Layer scoring은 **Fabio Scalping 전략**을 구현한 것. Turtle Trading은 별도 전략 (현재 코드 미구현, 일봉 `SP500FuturesStrategy`가 일부 유사 로직 보유).

| 항목 | Turtle (수동/Daily) | Scalping (ESF L1-L4 자동) |
|------|---------------------|---------------------------|
| 진입 신호원 | Donchian + EMA55 | AMT (POC/VAH/VAL/LVN) + Z-Score + Momentum + Volume |
| 손절 룰 | Entry - 2N (N=ATR) | tick-tight OR ATR×1.5 |
| 익절 룰 | 10일 반대 돌파 OR +6N | ATR×2.0 (R:R 2:1) |
| 보유 시간 | days~weeks | minutes~hours (EOD 청산) |
| 차트 사용 overlay | EMA55 + ATR + VAH/VAL | EMA8/21 + Mag MA + VWATR S/R + POC/VAH/VAL/LVN + BB |
| 자동화 위치 | 별도 strategy 신규 필요 | `backend/strategy/esf_intraday.py` 구현됨 |

---

## 4-Layer Scoring 구조 (총 100점)

| Layer | 가중 | 의미 |
|-------|------|------|
| L1 — AMT Location | 30 | Auction Market Theory — VP zone(POC/VAH/VAL/LVN) + Mag MA + VWATR S/R 위치 |
| L2 — Z-Score | 20 | 통계적 위치 (mean-reversion 잠재성) |
| L3 — Momentum | 25 | MACD + ADX/DMI + RSI + 연속 봉 |
| L4 — Volume + Aggression | 25 | Volume surge + OBV + Aggression + BB squeeze breakout |

Grade 임계값: A ≥ 50 / B ≥ 40 / C ≥ 20 (NEUTRAL 기준).

---

## 11 Overlay × Layer 매핑

| # | Overlay | 역할 | Layer | 기여 pt | 코드 위치 |
|---|---------|------|-------|---------|-----------|
| 1 | **EMA8** | 단기 추세 — direction veto | (veto) | — | `esf_intraday.py:196` |
| 2 | **EMA21** | 중기 추세 — direction veto | (veto) | — | `esf_intraday.py:197` |
| 3 | **EMA55** | 장기 추세 — direction veto | (veto) | — | `esf_intraday.py:198` |
| 4 | **BB (Bollinger Bands)** | 변동성 수축/확장 — BB squeeze breakout 보너스 | L4 | +3 | `esf_intraday.py:1328` (F2 추가) |
| 5 | **Mag MA (Magnetic MA)** | 평균회귀 강도 best MA 자동 선택 — VWATR zone 강도 입력 | L1 | 0-8 (간접) | `compute_magnetic_ma:290` |
| 6 | **VWATR S** | Volume-weighted ATR 지지 zone — Mag MA ± VWATR×mult | L1 | 0-8 | `compute_vwatr_zones:391`, `_score_vwatr_proximity:527` |
| 7 | **VWATR R** | Volume-weighted ATR 저항 zone — 동일 수식 | L1 | 0-8 | 동일 |
| 8 | **POC (Point of Control)** | 최대 거래량 가격 — AMT_AT_POC +7 | L1 | 0-10 | `build_volume_profile:571`, `_score_amt_location:1026` |
| 9 | **VAH (Value Area High)** | 70% volume 상단 — ABOVE_VAH +3, AT_VAH +5 | L1 | 0-10 | 동일 |
| 10 | **VAL (Value Area Low)** | 70% volume 하단 — BELOW_VAL +3, AT_VAL +5 | L1 | 0-10 | 동일 |
| 11 | **LVN (Low Volume Node)** | 거래량 공백 (POC×30% 이하) — AT_LVN +10 (최고 점수) | L1 | 0-10 | `build_volume_profile:663` |

### 추가 (overlay 아니지만 scoring 입력)

| 지표 | Layer | 기여 | 코드 |
|------|-------|------|------|
| MACD(12,26,9) | L3 | 0-8 (cross/hist) | `_score_momentum:1163` |
| ADX/DMI(14) | L3 | 0-7 | 동일 |
| RSI(14) | L3 | 0-5 | 동일 |
| 연속 봉 | L3 | 0-5 | 동일 |
| Z-Score(40) | L2 | 0-20 | `_score_zscore:1099` |
| Volume Ratio | L4 | 0-8 (vol surge) | `_score_volume_aggression:1320` |
| OBV EMA(5/20) | L4 | 0-7 (방향 일치) | `_score_volume_aggression:1329` |
| Aggression(body/range/consec) | L4 | 0-10 | `_score_volume_aggression:1349` |
| ATR(20) | (entry) | — | SL/TP 계산 입력 |

---

## EMA Direction Veto 로직

EMA 정/역배열은 scoring에 직접 점수는 안 주지만 진입 차단(veto)으로 작동.

`esf_intraday.py:1006-1018`:
```
ema_bullish = ema_fast > ema_mid > ema_slow
ema_bearish = ema_fast < ema_mid < ema_slow

if score >= 2 and ema_bearish and score < 3:  # SHORT bias veto for LONG
    return NEUTRAL
if score <= -2 and ema_bullish and score > -3:  # LONG bias veto for SHORT
    return NEUTRAL
```

abs(score) ≥ 3 (강한 신호) 시 EMA 역방향 진입 허용 (Phase E 완화).

---

## Ticker별 의미 차이 — EMA Period Override (F3)

`backend/strategy/intraday_ticker_specs.py` `INTRADAY_SPECS` 에서 commodity 자산은 짧은 pit 세션 보정을 위해 Fibonacci 단축 EMA 사용:

| Ticker | Pit Hours | 세션 길이 | EMA period (fast/mid/slow) |
|--------|-----------|-----------|----------------------------|
| ES/MES/NQ/MNQ | 09:30-16:00 ET | 6.5h | 8 / 21 / 55 (ic 기본값) |
| CL/MCL | 09:00-14:30 ET | 5.5h | **5 / 13 / 34** (override) |
| GC/MGC | 08:20-13:30 ET | 5.2h | **5 / 13 / 34** (override) |

근거: 동일 8/21/55 적용 시 짧은 세션에선 EMA가 세션 후반에야 안정 → 시그널 지연. Fibonacci 단축으로 commodity에서 EMA 반응성 보정. `IntradayBacktester.__init__` (line 144-150) 에서 spec 조회 후 `self.ema_fast/mid/slow` instance attr로 저장 + `_calculate_indicators` 가 self attr 사용.

`ESFIntradayStrategy.calculate_indicators(df, ticker=None)` 도 동일 패턴 — ticker 인자 받아 spec 조회. 미지정 시 `self.fc.ema_*` (config 기본) fallback. 호출자 (intraday_backtester, esf_intraday_routes 4개 endpoint) 모두 ticker 전달.

---

## BB Squeeze Breakout (F2)

`bb_squeeze_ratio = bb_width / bb_width_ma` 가 < 0.75 (매우 압축) AND `volume_ratio` ≥ 1.5 (서지) 동시 발생 시 Layer 4 +3pt. 

`esf_intraday.py:1327-1332`:
```python
bb_sq = float(curr.get("bb_squeeze_ratio", 1.0))
if bb_sq < 0.75 and vol_ratio >= 1.5:
    score += 3.0
    signals.append("BB_SQUEEZE_BREAKOUT")
```

이전 ESF는 `bb_squeeze_ratio`를 계산만 하고 scoring에 미사용 (사장된 신호). F2 통합 이후 변동성 수축 → 폭발 setup이 L4 점수에 기여. `max_score 25` cap (line 1379)이 유지되어 다른 신호와 합산 시 잘림.

보수적 임계 (squeeze<0.75, vol≥1.5 둘 다 충족)로 false positive 최소화.

---

## 자산별 4-Layer Calibration 현황

| 자산 | L1 AMT (POC/VAH/VAL/LVN) | L2 Z-Score | L3 Momentum | L4 Vol/Aggr/BB | EMA Period |
|------|--------------------------|-----------|-------------|----------------|------------|
| ES/NQ | ES 15m bars calibrated | 동일 | 동일 | 동일 | 8/21/55 |
| CL/GC | tick_size·VP bin 자동 적응 | 동일 | 동일 | 동일 | 5/13/34 (F3) |

**미해결 calibration 항목** (이번 plan 범위 아님):
- Grade 임계값(A 50/ B 40/ C 20)은 ES 기준. 자산별 변동성 differential → CL/GC는 동일 임계에서 시그널 빈도 비정상 가능
- ATR multiplier (SL/TP) ic 기본값 사용 — 자산별 ATR 변동성 보정 미적용
- RSI/MACD period — 모든 ticker 14/12·26·9 공통
- Z-Score window 40 모든 ticker 공통

---

## Backend → Frontend 데이터 흐름

```
yfinance 15m candle
  ↓
backend/strategy/esf_intraday.py:calculate_indicators(df, ticker)
  ↓ (per-ticker EMA period 적용)
  ↓ compute_magnetic_ma → compute_vwatr_zones
  ↓ build_volume_profile (50-bin histogram)
  ↓
GET /api/v1/esf/analyze/{ticker}    → direction, total_score, grade, amt_state, magnetic_ma
GET /api/v1/esf/candles/{ticker}    → candles[] with ema_*, bb_*, magnetic_ma, vwatr
GET /api/v1/esf/volume-profile/{ticker} → poc, vah, val, lvn_levels[]
GET /api/v1/esf/regime/{ticker}     → regime, trend_score
  ↓
frontend/src/components/esf/ESFIntradayChart.tsx
  ↓ chart.addLineSeries() — EMA/BB/MagMA (line 233-306)
  ↓ mainSeries.createPriceLine() — VWATR S/R (line 308-354), POC/VAH/VAL/LVN (line 366-414)
  ↓ legend 표시 (line 756-772)
```

모든 데이터는 **backend 동적 계산** — frontend는 렌더링만. ticker 변경 시 새 API 호출로 갱신.

---

## 검증 스크립트

```bash
# 24-combo backtest (8 ticker × 3 mode)
python3 backend/scripts/verify_four_tickers.py

# 32-call overlay sanity (8 ticker × 4 endpoint)
python3 backend/scripts/verify_four_tickers.py --overlays

# 단위 테스트
python3 -m pytest backend/tests/unit/test_intraday_ticker_specs.py \
  backend/tests/unit/test_bb_squeeze_l4.py \
  backend/tests/unit/test_ticker_ema_override.py -v
```

---

## 참고

- `backend/strategy/esf_intraday.py` — 4-Layer scoring 엔진 (2000+ lines)
- `backend/strategy/intraday_ticker_specs.py` — per-ticker spec table (Phase 3 + F3)
- `frontend/src/components/esf/ESFIntradayChart.tsx` — 차트 렌더링
- `frontend/src/components/esf/scalping/BacktestTabContent.tsx` — Backtest 탭 + ticker 셀렉터
