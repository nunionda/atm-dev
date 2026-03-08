# 트레이딩 전략 & 시장 판단 지표 — 개발자 레퍼런스

> ATS 시스템 설계 시 참조하는 전략 분류, 시장 판단 로직, 실행 알고리즘 정리.
> 각 항목은 **의사코드(Pseudocode)** 또는 **조건식**으로 표현하여 구현에 바로 활용 가능.

---

## 1. 시간 지평(Timeframe)별 전략 분류

포지션 보유 기간에 따라 시스템 아키텍처와 리스크 관리 방식이 결정된다.

| 전략 유형 | 보유 기간 | 핵심 특징 | 개발 핵심 지표 |
|-----------|-----------|-----------|---------------|
| **HFT** (고빈도 매매) | 밀리초(ms) | 초당 수천 건 주문 실행 | Latency, Tick-to-Trade |
| **스캘핑** (Scalping) | 수초 ~ 수분 | 호가 스프레드 차익 | Order Flow, Slippage |
| **데이 트레이딩** | 당일 (오버나잇 X) | 당일 변동성 활용 | Intraday Volatility |
| **스윙 트레이딩** ⭐ | 2일 ~ 수주 | 단기 추세 및 파동 활용 | Swing High/Low, Momentum |
| **포지션 트레이딩** | 수개월 ~ 수년 | 매크로/펀더멘털 중심 | Long-term Trend, Drawdown |

> ⭐ ATS 시스템은 **스윙 트레이딩** 기반 (보유 최대 10일, 손절 -3%, 익절 +7%)

---

## 2. 매매 로직별 전략 분류

### 2-1. 추세 추종 (Trend Following) ⭐

> 핵심: "가는 말이 더 간다" — 추세가 형성되면 그 방향에 올라탄다.

- **사용 지표**: MA(이동평균선), MACD, 볼린저 밴드 돌파
- **의사코드**:
  ```
  IF price > MA(200) AND price CROSSES_ABOVE MA(50):
      signal = BUY
  ```

### 2-2. 역추세 / 평균 회귀 (Mean Reversion)

> 핵심: 가격이 평균에서 과도하게 이탈하면 회귀한다는 통계적 속성 이용.

- **사용 지표**: RSI (과매수/과매도), 볼린저 밴드 상/하단
- **의사코드**:
  ```
  IF RSI(14) < 30:       # Oversold → 매수
      signal = BUY
  IF RSI(14) > 70:       # Overbought → 매도
      signal = SELL
  ```

### 2-3. 차익거래 (Arbitrage)

> 핵심: 동일/유사 자산의 시장 간 가격 차이를 이용한 무위험 수익 추구.

- **종류**:
  - 시장 간 차익거래 (Cross-market)
  - 페어 트레이딩 (Pairs Trading) — 상관관계 높은 두 종목의 스프레드 활용
- **의사코드**:
  ```
  spread = price_A - beta * price_B
  IF spread > upper_threshold:
      SELL A, BUY B
  IF spread < lower_threshold:
      BUY A, SELL B
  ```

### 2-4. 이벤트 드리븐 (Event-Driven)

> 핵심: 실적 발표, M&A, 경제 지표 등 특정 이벤트에 따른 가격 변동 이용.

- **기술**: 뉴스 NLP 감성 분석 → 감성 점수(Sentiment Score) 기반 매매
- **의사코드**:
  ```
  sentiment = NLP_analyze(news_headline)
  IF sentiment > +0.7 AND volume_spike:
      signal = BUY
  ```

---

## 3. 주문 실행 전략 (Execution Algorithm)

대량 주문을 시장 충격(Market Impact) 없이 처리하기 위한 분할 집행 방식.

| 알고리즘 | 정식 명칭 | 로직 | 용도 |
|----------|-----------|------|------|
| **VWAP** | Volume Weighted Average Price | 거래량 가중 평균가에 맞춰 분할 매수/매도 | 기관 벤치마크 |
| **TWAP** | Time Weighted Average Price | 일정 시간 동안 균등하게 분할 집행 | 시간 균등 분배 |
| **POV** | Percentage of Volume | 전체 시장 거래량의 특정 비율만큼 참여 | 시장 영향 최소화 |

---

## 4. 시장 대세(Macro Trend) 판단 — 4대 핵심 필터

시장의 **구조적 전환**(대세 상승/하락)을 판단하는 알고리즘화 가능한 필터링 조건.
4개 조건이 **모두 True**일 때 강한 상승 추세로 판단한다.

### Filter 1: 이동평균선 정배열 (Trend Alignment)

> 가장 강력한 추세 지표. 모든 기간 투자자가 수익 구간에 있어 매도 압력이 최소화된 상태.

```python
def is_trend_aligned(price, ma20, ma60, ma120, ma200) -> bool:
    """정배열: 주가 > 단기 > 중기 > 장기 이평선 순서"""
    return price > ma20 > ma60 > ma120 > ma200
```

| 조건 | 의미 |
|------|------|
| `Price > MA(20) > MA(60) > MA(120) > MA(200)` | 전 구간 정배열 완성 |

### Filter 2: 거래량 동반 고점 돌파 (Breakout with Volume)

> 단순 가격 상승이 아닌 **신규 자금 유입**이 동반되어야 진정한 돌파.

```python
def is_volume_breakout(current_price, prev_high, volume, avg_volume) -> bool:
    """직전 고점 돌파 + 평균 거래량 2배 이상"""
    price_breakout = current_price > prev_high
    volume_confirm = volume > avg_volume * 2.0
    return price_breakout and volume_confirm
```

| 조건 | 의미 |
|------|------|
| `Price > Previous_High` | 저항선 돌파 |
| `Volume > Avg_Volume × 2` | 강력한 자금 유입 확인 |

### Filter 3: RSI & 모멘텀 지표 상향 (Momentum Convergence)

> 과매수 구간 진입을 두려워하지 말고, **강세 구역 유지**를 확인해야 한다.

```python
def is_momentum_bullish(rsi, macd, macd_signal) -> bool:
    """RSI 60 이상 유지 + MACD 시그널선 상향 돌파"""
    rsi_strong = rsi > 60
    macd_cross = macd > macd_signal  # 골든크로스
    return rsi_strong and macd_cross
```

| 조건 | 의미 |
|------|------|
| `RSI(14) > 60` 유지 | 상승 모멘텀 구간 |
| `MACD > Signal Line` | 추세 가속 확인 |

### Filter 4: 거시적 유동성 & 시장 심리 (Context Variable)

> 차트 밖의 외부 변수가 **True**여야 추세가 지속된다. 펀더멘털 백그라운드 확인.

```python
def is_macro_favorable(rate_policy, fear_greed_index) -> bool:
    """금리 정책 우호적 + 시장 심리 상향"""
    dovish = rate_policy in ("HOLD", "CUT")            # 금리 동결/인하
    sentiment_up = fear_greed_index > 50                # 탐욕 쪽 우세
    return dovish and sentiment_up
```

| 조건 | 의미 |
|------|------|
| 금리 동결/인하 기조 | 유동성 확장 → 주식시장 유리 |
| Fear & Greed Index 점진적 우상향 | 투자 심리 회복 |

---

## 5. 월봉 10선 기반 대세 판단 (Monthly MA10)

월봉 10개월 이동평균선은 **대세 전환의 기준선** 역할을 한다.

| 상태 | 조건 | 기술적 의미 | 대응 전략 |
|------|------|------------|-----------|
| **상향 돌파** 🟢 | `Price > Monthly_MA(10)` | 대세 상승 시작. 장기 매집 완료 후 우상향 전환 | 공격적 매수 & 보유 (Buy & Hold) |
| **하향 돌파** 🔴 | `Price < Monthly_MA(10)` | 대세 하락 징후. 장기 지지선 붕괴 | 비중 축소 & 현금화 (Risk Off) |
| **지지/저항** 🟡 | 터치 후 반등 또는 되돌림 | 10개월 평균 매수 단가 = 강력한 심리적 지지/저항선 | 추세 지속 확인용 보조 지표 |

```python
def monthly_ma10_signal(price, monthly_ma10, prev_price, prev_ma10) -> str:
    """월봉 10선 기반 대세 판단"""
    if prev_price <= prev_ma10 and price > monthly_ma10:
        return "BULLISH_BREAKOUT"   # 상향 돌파 → 매수
    elif prev_price >= prev_ma10 and price < monthly_ma10:
        return "BEARISH_BREAKDOWN"  # 하향 돌파 → 매도
    elif abs(price - monthly_ma10) / monthly_ma10 < 0.02:
        return "TESTING_SUPPORT"    # 지지/저항 테스트 중
    else:
        return "NEUTRAL"
```

---

## 6. 종합 — 대세 상승 확인 체크리스트

ATS 시스템에서 시장 진입 전 확인해야 할 **통합 판단 로직**.

```python
def is_bull_market(indicators: dict) -> tuple[bool, list[str]]:
    """
    4대 필터 + 월봉 기준을 종합하여 대세 상승 여부를 판단.
    Returns: (is_bull, list_of_passed_filters)
    """
    checks = {
        "F1_정배열":     is_trend_aligned(
                            indicators["price"],
                            indicators["ma20"], indicators["ma60"],
                            indicators["ma120"], indicators["ma200"]),
        "F2_거래량돌파":  is_volume_breakout(
                            indicators["price"], indicators["prev_high"],
                            indicators["volume"], indicators["avg_volume"]),
        "F3_모멘텀":     is_momentum_bullish(
                            indicators["rsi"], indicators["macd"],
                            indicators["macd_signal"]),
        "F4_매크로":     is_macro_favorable(
                            indicators["rate_policy"],
                            indicators["fear_greed"]),
    }

    passed = [name for name, result in checks.items() if result]
    is_bull = len(passed) >= 3  # 4개 중 3개 이상 통과 시 강세

    return is_bull, passed
```

| 통과 필터 수 | 판정 | 시스템 행동 |
|-------------|------|------------|
| **4/4** | 강한 상승 | 최대 포지션, 공격적 진입 |
| **3/4** | 상승 추세 | 정상 진입, 리스크 보통 |
| **2/4** | 중립/불확실 | 보수적 진입, 포지션 축소 |
| **1/4 이하** | 약세/하락 | 신규 진입 중단, 현금 비중 확대 |
