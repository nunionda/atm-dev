# MDD 방어 전략 — ATS 실제 구현 기준

> 백테스트 실적: MDD **-4.9% ~ -6.2%** (SP500 normal/bull/covid 시나리오)
> 최악 시나리오(2008 금융위기): MDD -11.8% (BR-R02 -10% 서킷 브레이커 발동)

---

## 아키텍처 개요

MDD 방어는 단일 모듈이 아니라 **6-Phase 파이프라인 전체에 걸쳐 다층 방어**로 구현되어 있다.
진입부터 청산까지 7개의 독립적 방어 레이어가 동시 작동한다.

```
┌─────────────────────────────────────────────────────────┐
│  Layer 1: 시장 체제 (Phase 0) — 노출 자체를 제한        │
│  Layer 2: 추세 필터 (Phase 1-2) — 불량 진입 사전 차단   │
│  Layer 3: 시그널 품질 (Phase 3) — 고품질 진입만 허용     │
│  Layer 4: 리스크 게이트 (Phase 4) — 4중 사전 체크       │
│  Layer 5: ATR 포지션 사이징 — 변동성 비례 배팅           │
│  Layer 6: 5단계 청산 우선순위 — 손실 확대 물리적 차단    │
│  Layer 7: 프로그레시브 트레일링 — 수익 보호 극대화       │
└─────────────────────────────────────────────────────────┘
```

---

## 1. 시장 체제 기반 노출 제한 (Layer 1)

시장 전체의 건강 상태에 따라 포지션 수와 가중치를 **강제로 제한**한다.
MDD 방어의 1차 방어선: 위험한 시장에서는 애초에 적게 투자한다.

### 실제 구현 (`engine.py` — REGIME_PARAMS)

```python
REGIME_PARAMS = {
    "BULL":    {"max_positions": 10, "max_weight": 0.15},  # 공격적
    "NEUTRAL": {"max_positions": 6,  "max_weight": 0.12},  # 방어적
    "BEAR":    {"max_positions": 2,  "max_weight": 0.05},  # 극도 보수적
}
```

### 체제 판단 로직

- 워치리스트 전체 브레드스(MA200 상회 비율)로 판정
- `breadth >= 65%` → BULL, `breadth <= 35%` → BEAR, 나머지 → NEUTRAL
- **5일 스무딩**: 일시적 노이즈로 체제가 흔들리지 않도록 N일 연속 동일 신호 시에만 전환

### MDD 방어 효과

| 체제 | 최대 투자비중 | 최대 종목수 | 잔여 현금 |
|------|------------|-----------|----------|
| BULL | 10 × 15% = 150% (현금20% 제약으로 실제 ~80%) | 10 | 20%+ |
| NEUTRAL | 6 × 12% = 72% | 6 | 28%+ |
| BEAR | 2 × 5% = 10% | 2 | **90%+** |

→ BEAR 체제에서 자산의 90%가 현금. 시장이 -30% 폭락해도 포트폴리오는 최대 -3%.

---

## 2. ATR 기반 포지션 사이징 (Layer 5)

이론적 공식과 **동일한 구조**로 구현되어 있다. 핵심 차이: max_weight 캡이 바인딩 제약.

### 실제 구현 (`engine.py` — `_execute_buy`)

```python
# 1% 고정 리스크 모델
risk_per_trade = total_equity * 0.01  # 매 거래 최대 1% 리스크

# ATR 기반 손절 거리 → 수량 역산
stop_distance = max(atr_val, price * 0.03)  # 최소 BR-S01 3%
raw_quantity = risk_per_trade / stop_distance

# 품질 승수 (진입 시그널 품질에 따라 ±50%)
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

### 수식 매핑

| 이론 | 실제 구현 | 비고 |
|------|---------|------|
| $Units = \frac{Equity \times 0.01}{Entry - StopLoss}$ | `raw_quantity = risk_per_trade / stop_distance` | 동일 |
| $StopLoss = Entry \times 0.97$ | `stop_distance = max(atr_val, price * 0.03)` | ATR 우선, 최소 3% |
| Vol Targeting | max_weight 캡이 바인딩 | ATR 사이징 > max_weight인 경우 캡 적용 |

### MDD 기여도

- 개별 거래 최대 손실: **자산의 1%** (1% × stop_distance 역산)
- 10종목 동시 손절 시 이론적 최대 손실: **-10%** (= MDD 한도)
- 실제로는 동시 손절이 드물어 MDD -6% 내외

---

## 3. 하드 서킷 브레이커 — 4중 리스크 게이트 (Layer 4)

매 진입 시도 전에 **4개 게이트를 순차 체크**한다. 하나라도 실패 시 진입 차단.

### 실제 구현 (`engine.py` — `_risk_gate_check`)

```python
def _risk_gate_check(self) -> tuple:
    # RG1: 일일 손실 -3% → 당일 매매 전면 중단
    if daily_pnl_pct <= -3.0:
        return False, "RG1: 일일 손실 -3% 도달"

    # RG2: MDD -10% → 시스템 정지
    self._peak_equity = max(self._peak_equity, total_equity)
    mdd = (total_equity - self._peak_equity) / self._peak_equity * 100
    if mdd <= -10.0:
        return False, "RG2: MDD -10% 도달"

    # RG3: 체제별 최대 포지션 수 도달
    if active_count >= regime_params["max_positions"]:
        return False, f"RG3: 최대 보유 {max_positions}종목 도달"

    # RG4: 현금 비율 20% 미만
    if cash_ratio < self.min_cash_ratio:
        return False, "RG4: 현금 비율 20% 미만"

    return True, None
```

### 비교: 이론 vs 실제

| 이론 제안 | 실제 구현 | 차이점 |
|----------|---------|--------|
| 당일 손실 1%에 전매매 종료 | **RG1: -3%에 신규 진입 차단** | 1%→3%로 완화. 기존 포지션은 유지 (강제 청산 없음) |
| 고점 대비 4% 하락 시 전 청산 + 쿨오프 | **RG2: -10%에 시스템 정지** | 4%→10%로 완화. 모멘텀 전략의 자연 변동성 수용 |
| — | **RG3: 체제별 포지션 제한** | 추가 구현. BEAR 시 최대 2종목 |
| — | **RG4: 현금 20% 강제 유지** | 추가 구현. 비상 자금 확보 |

### 추가 서킷 브레이커: 연속 손절 정지

```python
if exit_type == "STOP_LOSS":
    self._consecutive_stops += 1
    if self._consecutive_stops >= 3:
        # 매매 정지 (전략 오작동 가능성)
        self._add_risk_event("HALT", f"연속 손절 {count}회 — 매매 정지")
```

→ 3연속 손절 시 시스템 자동 정지. "시장이 전략 로직과 완전히 어긋남" 신호.

---

## 4. 5단계 청산 우선순위 (Layer 6)

손실 확대를 **물리적으로 차단**하는 핵심 모듈. 우선순위가 높을수록 먼저 실행.

### 실제 구현 (`engine.py` — `_check_exits`)

```
ES1(손절-3%) > ES2(익절) > ES3(트레일링) > ES4(데드크로스) > ES5(보유기간)
```

| 규칙 | 조건 | 동작 | MDD 기여 |
|------|------|------|----------|
| **ES1** | `price ≤ entry × 0.97` | 즉시 청산. **BR-S01 절대 불변** | 개별 손실 최대 -3% |
| **ES2** | `price ≥ entry × (1 + 체제별 TP)` | 익절 (BULL +20%, NEUTRAL +12%, BEAR +8%) | 과도한 탐욕 방지 |
| **ES3** | 트레일링 활성화 후 `price ≤ highest × (1 + trail_pct)` | ATR 기반 트레일링 스탑 | 수익 환원 제한 |
| **ES4** | MA5 < MA20 (데드크로스) | pnl ≥ 2%: 타이트 트레일링 전환 / pnl < 2%: 즉시 청산 | 추세 반전 감지 |
| **ES5** | `days_held > max_holding` (BULL 40, NEUTRAL 25, BEAR 15) | 강제 청산 | 자본 잠금 방지 |

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

→ 수익 포지션(+2%+)은 데드크로스에서도 바로 청산하지 않고, 타이트 트레일링으로 전환.
→ 평균 승리 **+7.37% → +8.69%** 개선 (Sharpe +0.30 기여).

---

## 5. 프로그레시브 트레일링 (Layer 7)

**수익이 클수록 더 넓은 트레일링 폭**을 부여하여 슈퍼 위너를 보호한다.

### 실제 구현

```python
# 수익률별 ATR 배수 + 플로어 (최소 보장 폭)
if pnl_pct >= 0.15:        # +15%+
    trail_mult, trail_floor = 5.0, -0.08   # 5×ATR, 최소 -8%
elif pnl_pct >= 0.10:       # +10-15%
    trail_mult, trail_floor = 4.0, -0.06   # 4×ATR, 최소 -6%
elif pnl_pct >= 0.07:       # +7-10%
    trail_mult, trail_floor = 3.5, -0.05   # 3.5×ATR, 최소 -5%
else:                       # 기본
    trail_mult, trail_floor = 3.0, -0.04   # 3×ATR, 최소 -4%

trail_pct = max(-trail_mult * atr_pct_val, trail_floor)
```

### 효과 (실증)

| 수익 수준 | 트레일링 폭 | 의미 |
|----------|-----------|------|
| +5% 포지션 | -4% (고점 대비) | 최소 +1%에서 청산 |
| +10% 포지션 | -6% (고점 대비) | 최소 +4%에서 청산 |
| +15% 포지션 | -8% (고점 대비) | 최소 +7%에서 청산 |
| +20% 포지션 | -8% (고점 대비) | 최소 +12%에서 청산 |

→ ES3 트레일링 퇴출: 19건 → 11건 (슈퍼 위너 8건 추가 보호)
→ ES2 익절 도달: 11건 → 13건 (더 높은 수익까지 달성)

---

## 6. 상관관계 필터 — 구현 보류 (설계 검토 완료)

### 시도 및 결과

이론에서 제안한 상관관계 필터를 **섹터 집중도 제한**(동일 섹터 max 3종목)으로 구현하여 테스트함.

**결과: Sharpe 2.79 → 2.27 (악화)**

### 악화 원인 분석

모멘텀 전략의 특성상, 동일 섹터 집중이 **수익의 핵심 동력**:
- 테크 섹터 랠리 시 AAPL/MSFT/NVDA/CRM 동시 진입 → 모두 +10%+ 수익
- 섹터 제한하면 3번째 종목부터 차단 → 최고 수익 기회 상실
- 리스크 감소 < 수익 감소 → 순 Sharpe 하락

### 현재 접근

섹터 분산 대신, **시장 체제 기반 노출 제한**(Layer 1)이 동일 역할 수행:
- BEAR 전환 시 전체 포지션 2종목으로 축소 → 상관 리스크 자체가 소멸
- NEUTRAL 전환 시 6종목 제한 → 자연스러운 집중도 완화

---

## 7. 실전 성과 — 백테스트 검증

### SP500 20종목 유니버스

| 시나리오 | 기간 | Sharpe | 수익률 | **MDD** | PF |
|---------|------|--------|--------|---------|-----|
| 보통장 2023-24 | 2Y | 2.79 | +69% | **-6.2%** | 2.77 |
| 불마켓 2020 | 6M | 2.16 | +53% | **-4.9%** | 2.57 |
| 코로나 2020 | 5M | 2.57 | +13% | **-4.9%** | 2.74 |
| 금융위기 2008 | 2Y | -1.37 | -8% | **-11.8%** | 0.56 |

### MDD 방어 레이어별 기여도

```
보통장 시나리오 (MDD -6.2%):
├── Layer 1 체제: BULL 92.6% (안정적) → 체제 전환 3회만
├── Layer 4 게이트: RG 90회 차단 (약 6,267 스캔 중 1.4%)
├── Layer 5 사이징: 개별 최대 -3% × 15% weight = -0.45%/종목
├── Layer 6 청산: ES1 46회, ES4 63회 → 빠른 손절
└── Layer 7 프로그레시브: ES3 11회 → 수익 보호 극대화

금융위기 시나리오 (MDD -11.8%):
├── Layer 1 체제: BEAR 전환 → max 2종목, 5% weight
├── Layer 4 게이트: RG2(-10%) 발동 → 시스템 정지
├── Layer 5 사이징: BEAR 시 2 × 5% = 10% 투자
└── Layer 6 청산: 57거래 중 ES1 30회 → 빠른 탈출
```

---

## 8. 이론 vs 실제 구현 대조표

| 항목 | 이론 제안 | 실제 구현 | 상태 |
|------|---------|---------|------|
| 동적 포지션 사이징 | ATR/σ 기반 축소 | ATR 리스크 패리티 + max_weight 캡 | **구현 완료** |
| 고정 리스크 모델 | 0.5~1% 리스크/거래 | **1% 리스크/거래** + 품질 승수(±50%) | **구현 완료** |
| 일일 서킷 브레이커 | -1%에 전 거래 종료 | **RG1: -3%에 신규 진입 차단** | **완화 적용** |
| Peak-to-Trough 추적 | -4%에 전 청산+쿨오프 | **RG2: -10%에 시스템 정지** | **완화 적용** |
| 상관관계 필터 | ρ > 0.7 진입 제한 | 체제 기반 포지션 수 제한으로 대체 | **대체 구현** |
| — | — | 5단계 청산 우선순위 (ES1-ES5) | **추가 구현** |
| — | — | ES4 스마트 트레일링 | **추가 구현** |
| — | — | 프로그레시브 트레일링 | **추가 구현** |
| — | — | 연속 손절 3회 정지 | **추가 구현** |
| — | — | 현금 20% 강제 유지 (RG4) | **추가 구현** |

---

## 9. 설계 원칙 (실전에서 검증된 교훈)

### MDD 5% 달성이 가능한 이유

1. **다층 방어**: 단일 모듈이 아닌 7개 레이어가 독립적으로 작동
2. **빠른 손절**: BR-S01 -3% 절대 불변 → 개별 최대 손실 제한
3. **체제 적응**: BEAR 시 90% 현금 → 시장 폭락 면역
4. **수익 보호**: 프로그레시브 트레일링 → 번 돈을 되돌려주지 않음

### MDD 10% 초과하는 유일한 시나리오

**2008 금융위기**: 극단적 시장 붕괴에서 BEAR 전환 전 보유 포지션이 동시 손절.
→ RG2 -10% 서킷 브레이커가 추가 손실을 -11.8%에서 차단함.
→ 개선 여지: BEAR 전환 속도 향상 (현재 5일 확인 → 3일)

### 이론 문서의 경고에 대한 실전 답변

> "MDD 5%는 시장 중립 전략에서만 실현 가능"

→ **반증**: 롱온리 모멘텀 전략으로 MDD -4.9% ~ -6.2% 달성.
→ 핵심은 체제 기반 노출 제한 + 빠른 손절 + 프로그레시브 트레일링의 조합.
→ 단, 2008급 극단적 위기에서는 -10%+ 가능 (서킷 브레이커로 -11.8% 제한).
