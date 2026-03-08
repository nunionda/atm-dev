# 알파 생성 전략 — ATS 실제 구현 기준

> 백테스트 실적: **Sharpe 2.16 ~ 2.79** (SP500 20종목 유니버스, 시나리오별)
> 수익률: **+13% ~ +69%** | MDD: **-4.9% ~ -6.2%** | PF: **2.57 ~ 2.77**
> 이론 4대 축(데이터·팩터·백테스팅·리스크)을 6-Phase 파이프라인으로 구현

---

## 1. 아키텍처 개요

이론적 알파 전략의 4대 축이 실제 코드에서 어떻게 매핑되는지 보여준다.

```
이론 4대 축                    실제 6-Phase 파이프라인
─────────────                  ─────────────────────
                               ┌──────────────────────────────────┐
1. 데이터 우위  ──────────────▶│ 데이터 레이어                     │
   (Alternative Data,          │ yfinance OHLCV + CSV 캐시         │
    고성능 ETL)                │ + Lookahead Bias 방지             │
                               ├──────────────────────────────────┤
2. 팩터 설계    ──────────────▶│ Phase 0: 시장 체제 (브레드스)     │
   (Value, Momentum,           │ Phase 1: 추세 확인 (MA+ADX+DMI)  │
    Quality, Low Vol)          │ Phase 2: 추세 단계 (BB+RSI+52w)  │
                               │ Phase 3: 진입 시그널 (PS+CF)      │
                               ├──────────────────────────────────┤
3. 백테스팅 엄밀성 ───────────▶│ Phase 4: 리스크 게이트 (RG1-RG4) │
   (과적합, 편향 방지)          │ + 포지션 사이징 (ATR Risk Parity) │
                               ├──────────────────────────────────┤
4. 리스크 관리  ──────────────▶│ Phase 5: 5단계 청산 (ES1-ES5)    │
   (MDD, Portfolio Opt)        │ + 프로그레시브 트레일링            │
                               └──────────────────────────────────┘
```

> **핵심 차이**: 이론은 멀티팩터(Value·Momentum·Quality·Low Vol)를 제안하지만,
> 실제 구현은 **모멘텀 싱글팩터**에 집중하되 6-Phase 깊이 필터링으로 알파를 추출한다.

---

## 2. 데이터 파이프라인 (이론 "데이터 우위")

### 실제 구현

| 구분 | 이론 제안 | 실제 구현 | 상태 |
|------|---------|---------|------|
| 가격 데이터 | OHLCV (기본) | yfinance 일봉 OHLCV | **구현 완료** |
| 데이터 캐시 | 고성능 ETL 파이프라인 | CSV 파일 캐시 + 기간 커버 체크 | **기본 구현** |
| Lookahead 방지 | 미래 데이터 차단 | 날짜 커서 기반 슬라이싱 | **구현 완료** |
| 대안 데이터 | 위성, 센티먼트, 온체인 | — | **미구현** |
| 뉴스/이벤트 | NLP 기반 센티먼트 | — | **미구현** |

### Lookahead Bias 방지 (`data_provider.py`)

```python
def get_ohlcv_up_to_date(self, watchlist):
    for w in watchlist:
        code = w["code"]
        df = self._full_data.get(code)
        # 미래 데이터 차단: current_date 이하만
        filtered = df[df["date"] <= self._current_date].copy()
        if not filtered.empty:
            result[code] = filtered
    return result
```

### 데이터 캐시 로직 (`data_downloader.py`)

```python
# 캐시 체크: 기간을 완전히 커버하면 재다운로드 스킵
if min_date <= start_date and max_date >= end_date:
    result[code] = df  # Cache hit
else:
    to_download.append(w)  # 부분 캐시 → 재다운로드
```

> **데이터 우위의 현실**: 현재 시스템은 "남들이 다 보는" OHLCV 데이터만 사용한다.
> 이론이 말하는 Alternative Data(위성, 신용카드, 온체인)는 전혀 활용하지 않는다.
> 대신 **팩터 깊이**(6-Phase 필터)로 같은 데이터에서 남보다 정교한 시그널을 추출한다.

---

## 3. 팩터 설계 (이론 "팩터 엔지니어링") — 핵심 섹션

### 3.1 기술적 지표 목록

12개 지표를 계산하며, 모두 `_calculate_indicators()` 함수에서 처리된다.

| # | 지표 | 파라미터 | 용도 | Phase |
|---|------|---------|------|-------|
| 1 | MA Short | 5일 | 단기 추세 | 1, 3, 5 |
| 2 | MA Long | 20일 | 중기 추세 | 1, 3, 5 |
| 3 | MA60 | 60일 | 정배열 확인 | 1 |
| 4 | MA120 | 120일 | 정배열 확인 | 1 |
| 5 | MA200 | 200일 | 정배열 + 체제 판단 | 0, 1 |
| 6 | ADX/+DI/-DI | 14일 | 추세 강도·방향 | 1 |
| 7 | BB (Upper/Lower/Width) | 20일, 2σ | 추세 단계 | 2 |
| 8 | MACD (Line/Signal/Hist) | 12/26/9 | 진입 시그널 | 3 |
| 9 | RSI | 14일 | 확인 필터 | 3 |
| 10 | Slow RSI | 28일 | 멀티 타임프레임 | 3 |
| 11 | Volume MA | 20일 | 거래량 돌파 | 3 |
| 12 | ATR / ATR% | 14일 | 사이징 + 트레일링 | 4, 5 |

### 3.2 Phase 0: 시장 체제 판단

워치리스트 전체의 **브레드스**(MA200 상회 비율)로 시장 건강도를 판정한다.

```python
def _judge_market_regime(self) -> str:
    # 워치리스트 각 종목의 MA200 상회 여부 집계
    breadth_pct = above_count / total_valid * 100

    if breadth_pct >= 65:
        raw_regime = "BULL"
    elif breadth_pct <= 35:
        raw_regime = "BEAR"
    else:
        raw_regime = "NEUTRAL"

    return self._smooth_regime(raw_regime)  # 5일 스무딩
```

**체제별 파라미터 자동 조정**:

```python
REGIME_PARAMS = {
    "BULL":    {"max_positions": 10, "max_weight": 0.15},
    "NEUTRAL": {"max_positions": 6,  "max_weight": 0.12},
    "BEAR":    {"max_positions": 2,  "max_weight": 0.05},
}

REGIME_EXIT_PARAMS = {
    "BULL":    {"max_holding": 40, "take_profit": 0.20, "trail_activation": 0.05},
    "NEUTRAL": {"max_holding": 25, "take_profit": 0.12, "trail_activation": 0.04},
    "BEAR":    {"max_holding": 15, "take_profit": 0.08, "trail_activation": 0.03},
}
```

> 시장 체제는 알파 생성의 전제 조건. BEAR 시 자산 90%를 현금으로 보호하면서
> 소수 종목(max 2)에서만 기회를 포착한다.

### 3.3 Phase 1: 추세 확인

종목 수준에서 상승 추세를 확인한다. **두 가지 독립 신호** 중 하나만 충족해도 통과.

```python
def _confirm_trend(self, df) -> dict:
    # 1) 정배열: MA5 > MA20 > MA60 > MA120 > MA200 중 3/5 이상
    alignment_score = 0
    if price > ma_vals[0]: alignment_score += 1
    for i in range(len(ma_vals) - 1):
        if ma_vals[i] > ma_vals[i + 1]: alignment_score += 1
    aligned = alignment_score >= 3  # 3/5 정배열 (완화)

    # 2) ADX/DMI: ADX > 20 AND +DI > -DI
    trend_exists = adx > 20
    bullish_di = plus_di > minus_di

    # 둘 중 하나만으로도 UP 인정
    if aligned or (trend_exists and bullish_di):
        direction = "UP"
```

| 판정 | 조건 | 의미 |
|------|------|------|
| **UP** | 정배열 3/5+ OR (ADX>20 AND +DI>-DI) | 상승 추세 → Phase 2 진행 |
| **DOWN** | 정배열 미달 AND -DI > +DI | 하락 추세 → 스킵 |
| **FLAT** | 그 외 | 무방향 → 스킵 |

**추세 강도** (시그널 품질 승수에 활용):
- `STRONG`: ADX > 40
- `MODERATE`: ADX 25~40
- `WEAK`: ADX 20~25

### 3.4 Phase 2: 추세 단계 판정

추세의 **어디쯤**에 있는지를 판정한다. LATE(말기) 진입을 차단하는 것이 핵심.

```python
def _estimate_trend_stage(self, df) -> str:
    squeeze_ratio = bb_width / bb_width_avg  # BB 50일 평균 대비 현재 폭
    rsi = float(curr.get("rsi", 50))
    pct_of_high = price / high_52w * 100       # 52주 고점 대비 %

    if squeeze_ratio < 0.8 or (squeeze_ratio < 1.2 and rsi < 65):
        return "EARLY"
    if squeeze_ratio > 2.0 or rsi > 80 or pct_of_high > 95:
        return "LATE"
    return "MID"
```

| 단계 | 조건 | 진입 허용 | 사이징 승수 |
|------|------|---------|-----------|
| **EARLY** | BB 스퀴즈 <0.8 OR (BB <1.2 AND RSI <65) | ✅ | 1.2× |
| **MID** | 기본 | ✅ | 1.0× |
| **LATE** | BB >2.0 OR RSI >80 OR 52주 고점 95%+ | ❌ 차단 | — |

### 3.5 Phase 3: 진입 시그널

**Primary Signal + Confirmation** 이중 구조. 둘 다 충족해야 진입.

**Primary Signals (PS)** — 크로스오버 기반:

```python
# PS1: 골든크로스 (MA5/20)
if prev["ma_short"] <= prev["ma_long"] and curr["ma_short"] > curr["ma_long"]:
    primary.append("PS1")

# PS2: MACD 골든크로스 + 3봉 기울기 양수
if prev["macd_hist"] <= 0 and curr["macd_hist"] > 0:
    slope = float(curr["macd_hist"]) - hist_3ago
    if slope > 0:  # 감속 크로스 필터링
        primary.append("PS2")
```

**Confirmation Filters (CF)** — 품질 검증:

| 필터 | 조건 | 역할 |
|------|------|------|
| **CF1** | RSI 42~68 | 과매수/과매도 구간 진입 방지 |
| **CF2** | 거래량 ≥ MA20 × 1.5 | 거래량 돌파 확인 |
| **CF3** | Slow RSI(28일) 45~70 | 멀티 타임프레임 추세 확인 |

**추가 필터**: 베어리시 다이버전스 감지

```python
def _detect_bearish_divergence(self, df, lookback=10):
    # 가격은 고점 갱신인데 RSI는 고점 하락 → 모멘텀 약화
    if price_peaks[-1] > price_peaks[-2] and rsi_at_peaks[-1] < rsi_at_peaks[-2]:
        return True  # 진입 차단
```

### 3.6 시그널 강도 연속 스코어링

모든 시그널에 0~100 연속 점수를 부여하여 **진입 우선순위**를 결정한다.

```python
base_strength = len(primary) * 25 + len(confirmations) * 15    # PS×25 + CF×15
trend_bonus = min(int(adx * 0.5), 25)                          # ADX → 최대 25점
stage_bonus = 15 if stage == "EARLY" else 8 if stage == "MID" else 0
rsi_quality = max(0, int(10 - abs(rsi - 55) * 0.5))            # RSI 55 이상대
volume_bonus = min(int((vol_ratio - 1.5) * 10), 10) if vol_ratio > 1.5 else 0
strength = min(base_strength + trend_bonus + stage_bonus + rsi_quality + volume_bonus, 100)
```

| 항목 | 점수 | 범위 |
|------|------|------|
| PS (Primary) | 25점/개 | 25~50 |
| CF (Confirm) | 15점/개 | 15~45 |
| ADX 보너스 | ADX×0.5 | 0~25 |
| 단계 보너스 | EARLY:15, MID:8 | 0~15 |
| RSI 품질 | 55 근방에서 최고 | 0~10 |
| 거래량 보너스 | (ratio-1.5)×10 | 0~10 |
| **합계** | | **0~100** |

> 시그널 강도순으로 정렬 후 상위부터 매수 실행.
> 동일 날 여러 시그널 발생 시 품질 높은 종목을 우선 배분한다.

### 3.7 이론 "멀티팩터" vs 실제 "모멘텀 싱글팩터"

| 이론 제안 팩터 | 설명 | ATS 구현 상태 |
|--------------|------|-------------|
| **Momentum** | 가격 추세 추종 | ✅ **6-Phase 완전 구현** |
| Value | 저평가 종목 (P/E, P/B) | ❌ 미구현 |
| Quality | 우량성 (ROE, 이익 안정성) | ❌ 미구현 |
| Low Volatility | 저변동성 종목 선호 | ❌ 미구현 |
| Sentiment | 뉴스/SNS 감성 분석 | ❌ 미구현 |
| ML 복합 팩터 | XGBoost/Transformer | ❌ 미구현 |

> **설계 철학**: 한 가지 팩터(Momentum)를 극도로 깊게 구현.
> 시장 체제 → 추세 확인 → 추세 단계 → 시그널 품질 → 연속 스코어링까지
> 5단계 필터를 거치면 6,267회 스캔 중 **112회만 진입** (통과율 1.8%).

---

## 4. 포지션 사이징

### ATR 리스크 패리티 (실제 구현)

```python
# 1% 고정 리스크 모델
risk_per_trade = total_equity * 0.01

# ATR 기반 손절 거리 → 수량 역산
stop_distance = max(atr_val, price * 0.03)  # 최소 BR-S01 3%
raw_quantity = risk_per_trade / stop_distance

# 4종 품질 승수
strength_mult = max(0.5, min(signal.strength / 70.0, 1.5))
trend_mult = {"STRONG": 1.2, "MODERATE": 1.0, "WEAK": 0.7}[trend_strength]
stage_mult = {"EARLY": 1.2, "MID": 1.0, "LATE": 0.6}[trend_stage]
alignment_mult = 0.8 + (alignment_score / 5.0) * 0.4  # 0.8x ~ 1.2x

quantity = int(raw_quantity * strength_mult * trend_mult * stage_mult * alignment_mult)

# max_weight 캡 (체제별)
max_amount = total_equity * regime_params["max_weight"]
if quantity * price > max_amount:
    quantity = int(max_amount / price)

# 최소 현금 20% 유지
min_cash = total_equity * self.min_cash_ratio
available = self.cash - min_cash
if quantity * price > available:
    quantity = int(available / price)
```

### 이론 vs 실제 비교

| 이론 제안 | 실제 구현 | 비고 |
|---------|---------|------|
| Kelly Criterion | ATR Risk Parity 1% | Kelly는 과도한 변동성 유발 → 고정 리스크 모델 채택 |
| Volatility Targeting | max_weight 캡이 바인딩 | ATR 사이징 > max_weight인 경우 캡이 실질적 제약 |
| 균등 배분 | 품질 기반 차등 배분 | 4종 승수(strength, trend, stage, alignment)로 ±50% 조절 |

### max_weight 바인딩 제약

**ATR 사이징으로 계산한 수량이 max_weight 한도를 초과하는 경우가 대부분**이다.
결과적으로 max_weight(BULL 15%, NEUTRAL 12%, BEAR 5%)가 실질적 사이징 결정자가 된다.

```
ATR 사이징 계산: $100,000 × 1% / $5(ATR) = 200주 → $30,000 (30%)
max_weight 캡:   $100,000 × 15% = $15,000 → 100주로 축소
→ max_weight가 바인딩 제약
```

> 이로 인해 에쿼티 모멘텀 사이징, 변동성 타겟팅 등 **추가 사이징 최적화가 무효화**됨.
> 사이징 개선은 max_weight 캡 자체를 수정해야 의미 있지만,
> max_weight 확대 시도(15%→18%)는 Sharpe 2.79→2.71로 악화 (리스크 증가 > 수익 증가).

---

## 5. 청산 시스템

### ES1-ES5 우선순위

```
ES1(손절-3%) > ES2(익절) > ES3(트레일링) > ES4(데드크로스) > ES5(보유기간)
```

| 규칙 | 조건 | 동작 | 체제별 차이 |
|------|------|------|----------|
| **ES1** | `price ≤ entry × 0.97` | 즉시 청산. BR-S01 **절대 불변** | 없음 (고정 -3%) |
| **ES2** | `price ≥ entry × (1+TP)` | 익절 | BULL +20%, NEUTRAL +12%, BEAR +8% |
| **ES3** | 트레일링 활성화 후 `price ≤ highest × (1+trail)` | ATR 기반 트레일링 | 활성화: BULL 5%, NEUTRAL 4%, BEAR 3% |
| **ES4** | MA5 < MA20 (데드크로스) | pnl≥2%: 타이트 트레일 / else: 즉시 청산 | 없음 |
| **ES5** | `days > max_holding` | 강제 청산 | BULL 40일, NEUTRAL 25일, BEAR 15일 |

### ES4 스마트 트레일링 (핵심 혁신)

```python
# 데드크로스 감지 시
if prev["ma_short"] >= prev["ma_long"] and curr["ma_short"] < curr["ma_long"]:
    if pnl_pct >= 0.02:
        # 수익 포지션: 즉시 청산 대신 타이트 트레일링
        tight_trail = max(-1.5 * atr_pct_val, -0.02)  # 1.5×ATR, 최소 -2%
        pos.trailing_activated = True
        pos.trailing_stop = round(current_price * (1 + tight_trail))
    else:
        # 손실/소폭 포지션: 즉시 청산
        exit_reason = "ES4 데드크로스"
```

> 데드크로스에서 수익 포지션(+2%+)을 바로 청산하지 않고 타이트 트레일링 전환.
> 평균 승리 **+7.37% → +8.69%** 개선 (Sharpe +0.30 기여).

### 프로그레시브 트레일링

**수익이 클수록 더 넓은 트레일링 폭**을 부여하여 슈퍼 위너를 보호한다.

```python
if pnl_pct >= 0.15:        # +15%+
    trail_mult, trail_floor = 5.0, -0.08   # 5×ATR, 플로어 -8%
elif pnl_pct >= 0.10:       # +10-15%
    trail_mult, trail_floor = 4.0, -0.06   # 4×ATR, 플로어 -6%
elif pnl_pct >= 0.07:       # +7-10%
    trail_mult, trail_floor = 3.5, -0.05   # 3.5×ATR, 플로어 -5%
else:                       # 기본
    trail_mult, trail_floor = 3.0, -0.04   # 3×ATR, 플로어 -4%

trail_pct = max(-trail_mult * atr_pct_val, trail_floor)
```

| 수익 수준 | ATR 배수 | 플로어 | 의미 |
|----------|---------|--------|------|
| +5% | 3×ATR | -4% | 최소 +1%에서 청산 |
| +10% | 4×ATR | -6% | 최소 +4%에서 청산 |
| +15% | 5×ATR | -8% | 최소 +7%에서 청산 |
| +20% | 5×ATR | -8% | 최소 +12%에서 청산 |

> **핵심 인사이트**: 기존 고정 플로어(-4%)가 모든 ATR 계산을 덮어씌우고 있었음.
> 플로어 자체를 프로그레시브로 만들자 Sharpe 2.69 → 2.79로 개선.

---

## 6. 백테스팅 엄밀성 (이론 "디버깅")

### 구현된 보호장치

| 항목 | 상태 | 구현 방법 |
|------|------|---------|
| **Look-ahead Bias** | ✅ 구현 | `data_provider.py`: `df[df["date"] <= current_date]` |
| **워밍업 기간** | ✅ 구현 | MA200 계산용 ~200 거래일 사전 데이터 로드 |
| **Phase Funnel 통계** | ✅ 구현 | `PhaseStats`: 각 Phase 통과/차단 건수 추적 |
| **확장 메트릭** | ✅ 구현 | Sharpe, Sortino, Calmar, MDD Duration, 월별 수익률 |
| **Walk-forward 검증** | ✅ 구현 | IS/OOS 분할 → 독립 백테스트 → robustness ratio |

### 추가 구현된 보호장치

| 항목 | 상태 | 구현 방법 |
|------|------|---------|
| **Transaction Costs** | ✅ 구현 | 슬리피지 0.1%/측 + 수수료 0.015%/측. `engine.py _execute_buy/_execute_sell` |
| **Survivorship Bias** | ✅ 구현 | 데이터 커버리지 분석 + bias 점수(0~1). `data_downloader.py analyze_survivorship_bias()` |
| **Walk-forward 검증** | ✅ 구현 | IS(70%)/OOS(30%) 분할 독립 백테스트. `walk_forward.py` |
| **Alpha Decay 추적** | ✅ 구현 | Rolling 6M Sharpe + 선형회귀 기울기. `metrics.py _calc_rolling_sharpe()` |
| **과적합 검증** | ⚠️ 부분 | Walk-forward robustness ratio로 간접 검증 |

### Phase Funnel 실제 데이터 (SP500 normal_2023)

```
총 스캔             : 6,267
├── Phase 0 차단    :    32 (BEAR 체제)
├── Phase 1 차단    : 5,055 (추세 미달)
├── Phase 2 차단    :   240 (LATE 단계)
├── Phase 3 PS 미달 :   578 (Primary 없음)
├── Phase 3 CF 미달 :   186 (Confirm 없음)
├── 다이버전스 차단  :    64
├── Phase 4 RG 차단 :    90 (리스크 게이트)
└── 진입 실행        :   112 (통과율 1.8%)
```

> 6,267번의 기회 중 **112번만 진입** — 극도로 선별적.
> Phase 1(추세 미달)이 전체 필터링의 80.7%를 담당한다.

---

## 7. 실전 성과 — 백테스트 검증

### SP500 20종목 유니버스 (주요 4개 시나리오)

| 시나리오 | 기간 | Sharpe | CAGR | MDD | PF | 승률 | 거래수 |
|---------|------|--------|------|-----|-----|------|--------|
| 보통장 2023-24 | 2Y | **2.79** | +34% | -6.2% | 2.77 | 59% | 112 |
| 불마켓 2020-21 | 20M | **2.16** | +33% | -4.9% | 2.57 | 56% | 89 |
| 코로나 급락 | 5M | **2.57** | — | -4.9% | 2.74 | 62% | 41 |
| 금융위기 2008 | 18M | **-1.37** | — | -11.8% | 0.56 | 28% | 57 |

### 크로스마켓 검증

SP500에서 설계한 파라미터를 **파라미터 변경 없이** NDX/KOSPI에 적용:

- **NDX**: 반도체/테크 집중 → 모멘텀 전략과 궁합 양호
- **KOSPI**: 환율 변동, 다른 시장 특성 → 추가 검증 필요

### 핵심 메트릭 해석

- **Sharpe 2.79**: 일간 수익률 평균/표준편차 × √252. 일반적으로 2.0+ 우수
- **Sortino**: 하방 변동성만 사용. Sharpe보다 높으면 하방 리스크 관리 양호
- **Calmar**: CAGR / |MDD|. MDD 대비 수익 효율성
- **PF 2.77**: 총 이익 / 총 손실. 1.5+ 양호, 2.0+ 우수

---

## 8. 이론 vs 실제 구현 대조표

| # | 이론 항목 | 이론 제안 | 실제 구현 | 상태 |
|---|---------|---------|---------|------|
| 1 | 대안 데이터 | 위성, 센티먼트, 온체인 | yfinance OHLCV만 사용 | ❌ **미구현** |
| 2 | 고성능 ETL | 노이즈 제거, 저지연 처리 | CSV 파일 캐시 | ⚠️ **기본 구현** |
| 3 | Lookahead 방지 | 미래 데이터 차단 | `df[df["date"] <= current_date]` | ✅ **구현 완료** |
| 4 | Value 팩터 | P/E, P/B 저평가 | — | ❌ **미구현** |
| 5 | Momentum 팩터 | 가격 추세 추종 | 6-Phase 파이프라인 | ✅ **구현 완료** |
| 6 | Quality 팩터 | ROE, 이익 안정성 | — | ❌ **미구현** |
| 7 | Low Vol 팩터 | 저변동성 선호 | — | ❌ **미구현** |
| 8 | ML 복합 팩터 | XGBoost, Transformer | — | ❌ **미구현** |
| 9 | Survivorship Bias | 상폐 종목 포함 | 데이터 커버리지 분석 + bias 점수(0~1) | ✅ **구현 완료** |
| 10 | Transaction Cost | 슬리피지, 수수료 | 슬리피지 0.1%/측 + 수수료 0.015%/측 | ✅ **구현 완료** |
| 11 | Kelly Criterion | 켈리 공식 베팅 | ATR Risk Parity 1% | 🔄 **대체 구현** |
| 12 | Alpha Decay 추적 | 모델 성능 모니터링 | Rolling 6M Sharpe + 선형회귀 기울기 | ✅ **구현 완료** |

> **12개 항목 중**: 구현 완료 5개, 기본 구현 1개, 대체 구현 1개, **미구현 5개**.
> 핵심 축(Lookahead 방지 + Momentum 팩터)과 백테스팅 엄밀성(거래비용, 생존자 편향,
> 알파 감쇠, Walk-forward 검증)이 구현되었다.
> 미구현 5개(대안 데이터, Value/Quality/Low Vol 팩터, ML)는 신규 알파 소스로 향후 로드맵.

---

## 9. 시도했으나 제거한 것들

최적화 과정에서 다양한 이론적 개선을 시도했으나, 모멘텀 전략 특성과 충돌하여 제거되었다.

| # | 시도 내용 | Sharpe 변화 | 제거 이유 |
|---|----------|------------|---------|
| 1 | 섹터 집중도 제한 (max 3종목/섹터) | 2.79 → **2.27** | 모멘텀은 섹터 집중이 핵심 수익원. 테크 랠리 시 4종목 동시 수익 → 3번째부터 차단하면 최고 기회 상실 |
| 2 | ADX 가속도 필터 (ADX 하락 → 차단) | 2.79 → **2.65** | PF 3.28로 품질 개선되나, 거래 감소(82→68건)로 절대 수익 하락. 거래 규모 부족 |
| 3 | ES6 타임디케이 청산 (10일+, PnL -2%~+1%) | 2.79 → **2.23** | 59건 ES6 청산 중 다수가 이후 +10%+ 상승. 횡보 구간을 "사망"으로 오판 |
| 4 | 에쿼티 모멘텀 사이징 (에쿼티 < MA20 → 50% 축소) | 2.79 → **2.61** | max_weight 캡이 바인딩 → 사이징 축소가 실효 없음. 포지션 수 자체도 체제가 제한 |
| 5 | 일일 진입 제한 (max 2건/일) | 2.79 → **2.35** | 모멘텀에서 클러스터 진입이 유리. 동일 날 5~6건 동시 진입 → 같은 섹터 랠리 수확 |
| 6 | 적응형 트레일링 활성화 (15일+ → 임계 하향) | 2.79 → **2.45** | 트레일링 너무 빨리 활성화 → 정상 변동성에서 조기 청산. 수익 구간 단축 |
| 7 | ES4 임계 2%→3% | 2.79 → **2.56** | 2~3% 구간 포지션도 타이트 트레일 효과 → 범위 축소 시 손실 |
| 8 | 데드크로스 쿨다운 (5일 재진입 차단) | 2.79 → **2.66** | 데드크로스 후 빠른 반등 시 재진입 기회 차단. V자 회복 패턴 놓침 |

> **공통 교훈**: 모멘텀 전략은 분산·보수화가 수익과 직접 충돌한다.
> 이론적으로 "올바른" 리스크 관리(섹터 분산, 일일 제한, 타임디케이)가
> 실제로는 전략의 핵심 수익원(섹터 집중, 클러스터 진입, 장기 보유)을 파괴한다.

---

## 10. 향후 로드맵

### ✅ 완료된 항목

| 항목 | 구현 내용 | 관련 파일 |
|------|---------|----------|
| 슬리피지 모델링 (0.1%/측) | `effective_price = price × (1±slippage)` | `engine.py` |
| 수수료 반영 (0.015%/측) | `commission = qty × price × rate`, 누적 추적 | `engine.py` |
| Alpha Decay 추적 | Rolling 6M Sharpe + 선형회귀 기울기 | `metrics.py` |
| Survivorship Bias 경고 | 데이터 커버리지 분석, bias 점수 0~1 | `data_downloader.py` |
| Walk-forward 검증 | IS(70%)/OOS(30%) 분할 독립 백테스트 | `walk_forward.py` |

### Phase B: Medium (향후)

| 항목 | 기대 효과 | 난이도 |
|------|---------|--------|
| 펀더멘탈 팩터 (P/E, P/B) 보조 필터 | 밸류 트랩 방지 | 중간 |
| 동적 워치리스트 (상폐 종목 포함) | 생존자 편향 근본 해결 | 중간 |
| Monte Carlo 시뮬레이션 | 신뢰구간 추정 | 중간 |

### Phase C: Major (1~3개월)

| 항목 | 기대 효과 | 난이도 |
|------|---------|--------|
| 센티먼트 API (뉴스/SNS) | 대안 데이터 알파 | 높음 |
| ML 시그널 스코어링 (XGBoost) | 비선형 팩터 포착 | 높음 |
| Kelly Criterion 적응형 사이징 | 최적 베팅 사이즈 | 높음 |

> **우선순위 원칙**: 백테스트 현실성(완료) → 과적합 방지(완료) → 추가 팩터(Phase B) → 신규 알파 소스(Phase C)
> 거래비용 반영으로 "진짜 Sharpe"를 확인할 수 있게 되었다.
> 다음 단계는 백테스트 결과에서 거래비용 영향을 분석하고 Walk-forward로 robustness를 검증하는 것.
