# 주식 매매 로직 흐름도 — 이론 × 구현 통합 레퍼런스

> 시장 판단 이론과 ATS 구현 로직을 **하나의 의사결정 파이프라인**으로 통합.
> 위에서 아래로 흐르는 **Top-Down 필터링** 구조.

```
┌─────────────────────────────────────────────────────────────┐
│                    PHASE 0. 시장 체제 판단                     │
│              "지금 시장은 상승장인가, 하락장인가?"                  │
│         다우 이론 · 와이코프 사이클 · 월봉 MA10                  │
└──────────────────────┬──────────────────────────────────────┘
                       ▼ BULL / BEAR / NEUTRAL
┌─────────────────────────────────────────────────────────────┐
│                    PHASE 1. 추세 확인                         │
│              "추세가 존재하는가? 방향과 강도는?"                   │
│         이평선 정배열 · ADX/DMI · 시장 구조(BOS/CHoCH)          │
└──────────────────────┬──────────────────────────────────────┘
                       ▼ TREND_UP / TREND_DOWN / NO_TREND
┌─────────────────────────────────────────────────────────────┐
│                    PHASE 2. 추세 위치 파악                     │
│              "추세의 초기인가? 중기인가? 말기인가?"                 │
│         엘리어트 파동 · 와이코프 단계 · 볼린저 스퀴즈             │
└──────────────────────┬──────────────────────────────────────┘
                       ▼ EARLY / MID / LATE
┌─────────────────────────────────────────────────────────────┐
│                    PHASE 3. 진입 시그널                        │
│              "언제, 어디서 들어갈 것인가?"                        │
│         골든크로스 · RSI · MACD · 거래량 돌파 · 오더블록          │
└──────────────────────┬──────────────────────────────────────┘
                       ▼ BUY / SELL / HOLD
┌─────────────────────────────────────────────────────────────┐
│                    PHASE 4. 리스크 게이트                      │
│              "이 매매를 실행해도 안전한가?"                        │
│         손절 -3% · 일일 손실 한도 · MDD · 포지션 비중            │
└──────────────────────┬──────────────────────────────────────┘
                       ▼ PASS / BLOCK
┌─────────────────────────────────────────────────────────────┐
│                    PHASE 5. 주문 실행 & 청산                   │
│              "어떻게 집행하고, 언제 나갈 것인가?"                   │
│         VWAP/TWAP · 트레일링 스톱 · 익절 · 보유일 한도           │
└─────────────────────────────────────────────────────────────┘
```

---

## PHASE 0. 시장 체제 판단 (Market Regime)

> **질문: "지금 시장은 상승장인가, 하락장인가?"**
> 개별 종목을 보기 전에 시장 전체의 방향을 먼저 판단한다.

### 이론적 근거

| 이론 | 핵심 원리 | 적용 방법 |
|------|-----------|-----------|
| **다우 이론** | 시장은 주추세(Primary) → 중기조정(Secondary) → 단기변동(Minor) 3단계 | HH/HL 패턴이면 상승, LH/LL 패턴이면 하락 |
| **와이코프 사이클** | 축적(Accumulation) → 마크업 → 분배(Distribution) → 마크다운 | 현재 사이클 위치로 체제 판단 |
| **월봉 10선** | 10개월 평균 매수 단가 = 대세 전환 기준선 | 월봉 종가 vs MA(10) 비교 |

### 구현 로직

```python
def judge_market_regime(price, monthly_ma10, prev_price, prev_ma10,
                        rate_policy, fear_greed_index) -> str:
    """
    PHASE 0: 시장 체제를 BULL / BEAR / NEUTRAL로 판정.
    월봉 MA10 크로스 + 거시 환경을 종합.
    """
    # 월봉 10선 크로스 판단
    if prev_price <= prev_ma10 and price > monthly_ma10:
        ma_signal = "BULL"
    elif prev_price >= prev_ma10 and price < monthly_ma10:
        ma_signal = "BEAR"
    else:
        ma_signal = "NEUTRAL"

    # 거시 환경 (금리 + 심리)
    macro_ok = (rate_policy in ("HOLD", "CUT")) and (fear_greed_index > 50)

    # 종합
    if ma_signal == "BULL" and macro_ok:
        return "BULL"          # 대세 상승 → 공격적 진입 허용
    elif ma_signal == "BEAR":
        return "BEAR"          # 대세 하락 → 신규 진입 차단
    else:
        return "NEUTRAL"       # 보수적 진입만 허용
```

| 판정 | 시스템 행동 |
|------|------------|
| `BULL` | 최대 10종목, 종목당 15%까지 공격적 진입 |
| `NEUTRAL` | 최대 5종목, 종목당 10%까지 보수적 진입 |
| `BEAR` | 신규 진입 중단, 기존 포지션 트레일링 스톱 강화 |

---

## PHASE 1. 추세 확인 (Trend Identification)

> **질문: "추세가 존재하는가? 방향과 강도는?"**
> 종목 수준에서 추세의 존재 여부와 방향을 확인한다.

### 이론적 근거

| 이론 | 핵심 원리 | 판단 기준 |
|------|-----------|-----------|
| **이동평균 정배열** | 전 기간 투자자가 수익 구간 → 매도 압력 최소 | `Price > MA20 > MA60 > MA120 > MA200` |
| **ADX/DMI** | 추세 존재 여부 + 강도를 수치화 | ADX > 25 = 추세 존재, +DI > -DI = 상승 우위 |
| **시장 구조 (SMC)** | 다우 이론의 현대적 재해석 | BOS = 추세 지속, CHoCH = 추세 전환 |
| **추세선/채널** | 저점 연결 = 상승 추세선, 이탈 시 전환 | 가격이 추세선 위 유지 = 추세 유효 |

### 구현 로직

```python
def confirm_trend(price, ma20, ma60, ma120, ma200,
                  adx, plus_di, minus_di,
                  prev_high, prev_low) -> dict:
    """
    PHASE 1: 추세 방향(direction)과 강도(strength)를 반환.
    """
    # 1-1. 이평선 정배열 체크
    aligned = price > ma20 > ma60 > ma120 > ma200

    # 1-2. ADX/DMI 추세 강도
    trend_exists = adx > 25
    bullish_di = plus_di > minus_di

    # 1-3. 시장 구조 (Higher High / Higher Low)
    # prev_high, prev_low는 직전 스윙 고점/저점
    higher_high = price > prev_high
    higher_low = price > prev_low  # 저점이 높아지고 있는가

    # 종합 판정
    bull_count = sum([aligned, trend_exists and bullish_di, higher_high and higher_low])

    if bull_count >= 2:
        direction = "UP"
    elif not aligned and minus_di > plus_di:
        direction = "DOWN"
    else:
        direction = "FLAT"

    strength = "STRONG" if adx > 40 else "MODERATE" if adx > 25 else "WEAK"

    return {
        "direction": direction,       # UP / DOWN / FLAT
        "strength": strength,         # STRONG / MODERATE / WEAK
        "aligned": aligned,           # 정배열 여부
        "adx": adx,
    }
```

| direction | strength | 시스템 행동 |
|-----------|----------|------------|
| `UP` | `STRONG` | 진입 시그널 대기, 풀 사이즈 포지션 |
| `UP` | `MODERATE` | 진입 시그널 대기, 절반 사이즈 |
| `FLAT` | `WEAK` | 진입 스킵 (횡보 구간 = 추세 전략 불리) |
| `DOWN` | any | 신규 매수 차단 |

---

## PHASE 2. 추세 위치 파악 (Trend Stage)

> **질문: "추세의 초기인가? 중기인가? 말기인가?"**
> 같은 상승 추세라도 진입 시점에 따라 리스크가 다르다.

### 이론적 근거

| 이론 | 초기 (진입 유리) | 중기 | 말기 (진입 위험) |
|------|-----------------|------|-----------------|
| **엘리어트 파동** | 1파, 3파 초입 | 3파 중반~후반 | 5파 (마지막 충격파) |
| **와이코프** | 축적 완료 → 마크업 시작 | 마크업 중 | 분배 진입 (마크다운 직전) |
| **볼린저 밴드** | 스퀴즈 해소 직후 | 밴드워킹 중 | 밴드 폭 극대 + 이탈 |

### 구현 로직

```python
def estimate_trend_stage(bb_width, bb_width_avg, bb_width_max,
                         rsi, price_vs_52w_high_pct) -> str:
    """
    PHASE 2: 추세의 위치를 EARLY / MID / LATE로 추정.
    볼린저 밴드 폭 + RSI + 52주 신고가 근접도를 종합.
    """
    squeeze_ratio = bb_width / bb_width_avg if bb_width_avg > 0 else 1.0

    # 스퀴즈 직후 해소 = 초기
    if squeeze_ratio < 0.8 or (squeeze_ratio < 1.2 and rsi < 65):
        return "EARLY"

    # 밴드워킹 + RSI 60~75 = 중기 (가장 안전한 진입 구간)
    if 1.0 <= squeeze_ratio <= 2.0 and 55 <= rsi <= 75:
        return "MID"

    # 밴드 극대 + RSI 과열 + 52주 고점 근접 = 말기
    if squeeze_ratio > 2.0 or rsi > 80 or price_vs_52w_high_pct > 95:
        return "LATE"

    return "MID"  # 기본값
```

| 단계 | 리스크 수준 | 시스템 행동 |
|------|------------|------------|
| `EARLY` | 낮음 | 적극 진입 + 넓은 손절폭 허용 |
| `MID` | 보통 | 정상 진입 + 표준 손절 (-3%) |
| `LATE` | 높음 | 진입 스킵 또는 절반 사이즈 + 타이트 손절 |

---

## PHASE 3. 진입 시그널 (Entry Signal)

> **질문: "구체적으로 언제, 어디서 들어갈 것인가?"**
> Phase 0~2를 통과한 종목에 대해서만 진입 시그널을 평가한다.

### 이론적 근거

| 전략 유형 | 원리 | 진입 조건 |
|-----------|------|-----------|
| **추세 추종** ⭐ | "가는 말이 더 간다" | 골든크로스, 정배열 내 눌림목 매수 |
| **평균 회귀** | 과매도 반등 | RSI < 30에서 반등 시작 |
| **돌파 매매** | 저항선 돌파 + 거래량 확인 | 고점 돌파 + Volume × 2 |
| **오더블록** | 기관 매집 가격대 리테스트 | FVG/OB 영역 터치 후 반등 |

> ⭐ ATS 시스템은 **추세 추종 + 돌파 매매** 조합을 사용

### ATS 진입 시그널 파이프라인

```python
def generate_entry_signal(indicators: dict) -> dict | None:
    """
    PHASE 3: ATS 진입 시그널 생성.
    PS1(골든크로스) + PS2(MACD) → CF1(RSI) + CF2(거래량) 순서로 필터링.
    """
    # ── Primary Signal 1: 골든크로스 ──
    ps1 = indicators["sma5"] > indicators["sma20"]  # 단기 MA 상향 돌파

    # ── Primary Signal 2: MACD 골든크로스 ──
    ps2 = indicators["macd"] > indicators["macd_signal"]

    if not (ps1 and ps2):
        return None  # 1차 시그널 미충족 → 스킵

    # ── Confirm Filter 1: RSI 구간 확인 ──
    cf1 = 40 < indicators["rsi"] < 75  # 과매도도 아니고 과매수도 아닌 구간

    # ── Confirm Filter 2: 거래량 동반 ──
    cf2 = indicators["volume"] > indicators["avg_volume"] * 1.5

    if not (cf1 and cf2):
        return None  # 확인 필터 미충족 → 스킵

    return {
        "signal": "BUY",
        "price": indicators["price"],
        "strength": sum([ps1, ps2, cf1, cf2]) * 25,  # 0~100
        "reason": "PS1(골든크로스) + PS2(MACD) + CF1(RSI) + CF2(거래량)",
    }
```

---

## PHASE 4. 리스크 게이트 (Risk Gate)

> **질문: "이 매매를 실행해도 안전한가?"**
> 진입 시그널이 발생해도 리스크 조건에 걸리면 **무조건 차단**한다.

### 리스크 게이트 체크리스트

```python
def risk_gate_check(portfolio: dict, new_order: dict) -> tuple[bool, str | None]:
    """
    PHASE 4: 4개 리스크 게이트를 순서대로 통과해야 주문 실행 가능.
    하나라도 실패하면 (False, 사유) 반환.
    """
    # RG1. 일일 손실 한도 (-3%)
    if portfolio["daily_pnl_pct"] <= -3.0:
        return False, "BR-R01: 일일 손실 -3% 도달, 금일 매매 중단"

    # RG2. MDD 한도 (-10%)
    if portfolio["mdd"] <= -10.0:
        return False, "BR-R02: MDD -10% 도달, 시스템 정지"

    # RG3. 최대 포지션 수 (10종목)
    if portfolio["position_count"] >= 10:
        return False, "BR-R03: 최대 보유 종목 10개 초과"

    # RG4. 최소 현금 비율 (20%)
    new_cash_ratio = (portfolio["cash"] - new_order["amount"]) / portfolio["equity"] * 100
    if new_cash_ratio < 20:
        return False, "BR-R04: 현금 비율 20% 미만"

    return True, None
```

| 게이트 | 코드 | 조건 | 위반 시 행동 |
|--------|------|------|-------------|
| **RG1** | BR-R01 | 일일 손실 ≥ -3% | 금일 매매 전면 중단 |
| **RG2** | BR-R02 | MDD ≥ -10% | 시스템 정지 (수동 복구 필요) |
| **RG3** | BR-R03 | 보유 종목 ≥ 10개 | 신규 매수 차단 |
| **RG4** | BR-R04 | 현금 비율 < 20% | 신규 매수 차단 |

---

## PHASE 5. 주문 실행 & 청산 (Execution & Exit)

> **질문: "어떻게 집행하고, 언제 나갈 것인가?"**

### 5-1. 실행 알고리즘

| 알고리즘 | 로직 | ATS 적용 |
|----------|------|----------|
| **VWAP** | 거래량 가중 평균가에 분할 집행 | 대형주 진입 시 슬리피지 최소화 |
| **TWAP** | 시간 균등 분할 집행 | 일정 시간 내 목표 수량 체결 |
| **POV** | 시장 거래량의 N% 참여 | 시장 충격 최소화 |

### 5-2. 청산 우선순위 (Exit Signal)

> 번호가 낮을수록 우선순위가 높다. **손절은 절대 불변.**

```python
def check_exit_signals(position: dict, current_price: float) -> dict | None:
    """
    PHASE 5: 청산 시그널을 우선순위 순서대로 체크.
    첫 번째로 발동된 시그널이 최종 청산 사유.
    """
    entry = position["entry_price"]
    highest = position["highest_price"]
    pnl_pct = (current_price - entry) / entry * 100
    drawdown_from_high = (current_price - highest) / highest * 100

    # ES1. 손절 -3% (절대 불변 — BR-S01)
    if pnl_pct <= -3.0:
        return {"signal": "SELL", "reason": "ES1: 손절 -3%", "priority": 1}

    # ES2. 익절 +7%
    if pnl_pct >= 7.0:
        return {"signal": "SELL", "reason": "ES2: 익절 +7%", "priority": 2}

    # ES3. 트레일링 스톱 -3% (고점 대비)
    if drawdown_from_high <= -3.0 and pnl_pct > 0:
        return {"signal": "SELL", "reason": "ES3: 트레일링 스톱 -3%", "priority": 3}

    # ES4. 데드크로스 (기술적 추세 전환)
    if position.get("dead_cross"):
        return {"signal": "SELL", "reason": "ES4: 데드크로스", "priority": 4}

    # ES5. 보유일 한도 (10일)
    if position["days_held"] >= 10:
        return {"signal": "SELL", "reason": "ES5: 보유 10일 초과", "priority": 5}

    return None  # 청산 조건 미충족 → 보유 유지
```

| 우선순위 | 코드 | 조건 | 성격 |
|---------|------|------|------|
| **1** (최고) | ES1 | 진입가 대비 -3% | 절대 손절 (불변) |
| **2** | ES2 | 진입가 대비 +7% | 목표 익절 |
| **3** | ES3 | 고점 대비 -3% 하락 | 수익 보호 |
| **4** | ES4 | 단기 MA 데드크로스 | 추세 전환 |
| **5** (최저) | ES5 | 보유 10일 초과 | 시간 기반 강제 청산 |

---

## 종합 — 전체 파이프라인 요약

```
[시장 데이터 수신]
       │
       ▼
  PHASE 0. 시장 체제 ──── BEAR? ──→ 신규 진입 차단, 기존 포지션만 관리
       │
       ▼ BULL / NEUTRAL
  PHASE 1. 추세 확인 ──── FLAT/DOWN? ──→ 해당 종목 스킵
       │
       ▼ direction=UP
  PHASE 2. 추세 위치 ──── LATE? ──→ 스킵 또는 절반 사이즈
       │
       ▼ EARLY / MID
  PHASE 3. 진입 시그널 ── 미충족? ──→ 대기 (다음 사이클)
       │
       ▼ BUY 시그널 발생
  PHASE 4. 리스크 게이트 ─ 차단? ──→ 주문 취소 + 사유 로깅
       │
       ▼ PASS
  [주문 실행] → 포지션 생성
       │
       ▼ (매 사이클마다)
  PHASE 5. 청산 체크 ──── ES1~ES5 발동? ──→ 매도 주문 실행
       │
       ▼ 미발동
  [포지션 유지] → 다음 사이클로
```

### 이론 ↔ Phase 매핑

| 이론 | 적용 Phase | 역할 |
|------|-----------|------|
| 다우 이론 | Phase 0, 1 | 추세 방향 (HH/HL vs LH/LL) |
| 와이코프 | Phase 0, 2 | 사이클 위치 (축적/분배) |
| 엘리어트 파동 | Phase 2 | 파동 위치 (1파~5파) |
| 이동평균선 | Phase 1, 3 | 정배열 확인 + 골든크로스 진입 |
| ADX/DMI | Phase 1 | 추세 존재 여부 + 강도 수치화 |
| 볼린저 밴드 | Phase 2, 3 | 스퀴즈(타이밍) + 밴드워킹(추세 확인) |
| 시장 구조 (SMC) | Phase 1, 3 | BOS/CHoCH + 오더블록 진입 |
| RSI / MACD | Phase 3 | 진입 확인 필터 |
| 추세선/채널 | Phase 1, 3 | 지지/저항 + 리테스트 진입 |

---

## 부록 A. ATS 시스템 파라미터 요약

| 파라미터 | 값 | 설명 |
|---------|-----|------|
| 전략 유형 | 모멘텀 스윙 | 추세 추종 + 돌파 매매 |
| 보유 기간 | 최대 10일 | 스윙 트레이딩 |
| 손절 | -3% (절대) | BR-S01 |
| 익절 | +7% | 목표가 도달 시 |
| 트레일링 스톱 | 고점 대비 -3% | 수익 보호 |
| 최대 종목 수 | 10개 | 분산 투자 |
| 종목당 비중 | 최대 15% | 집중 리스크 방지 |
| 최소 현금 | 20% | 유동성 확보 |
| 일일 손실 한도 | -3% | 금일 매매 중단 |
| MDD 한도 | -10% | 시스템 정지 |

## 부록 B. 시간 지평별 전략 비교

| 전략 유형 | 보유 기간 | 핵심 지표 | ATS 해당 |
|-----------|-----------|-----------|---------|
| HFT | 밀리초 | Latency | ✗ |
| 스캘핑 | 수초~수분 | Order Flow, Slippage | ✗ |
| 데이 트레이딩 | 당일 | Intraday Volatility | ✗ |
| **스윙 트레이딩** | **2일~수주** | **Momentum, Swing H/L** | **⭐ ATS** |
| 포지션 트레이딩 | 수개월~수년 | Long-term Trend | ✗ |

## 부록 C. 매매 로직 유형 비교

| 로직 | 핵심 | ATS 적용 |
|------|------|---------|
| **추세 추종** | 추세 방향에 올라탐 | ⭐ 메인 전략 |
| 평균 회귀 | 과이탈 후 복귀 매매 | RSI 필터로 간접 활용 |
| 차익거래 | 가격 차이 무위험 수익 | ✗ |
| 이벤트 드리븐 | 뉴스/실적 기반 | ✗ |
