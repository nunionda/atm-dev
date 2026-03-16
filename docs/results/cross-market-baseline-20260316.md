# Cross-Market 5-Year Baseline Comparison

**Date:** 2026-03-16
**Period:** 2021-03-16 ~ 2026-03-16
**Strategy:** multi (all strategies)
**Engine Version:** Pre-upgrade (before B1-B8 adaptive regime)

---

## Summary Comparison

| Metric | SP500 | NDX | KOSPI |
|--------|-------|-----|-------|
| **Return** | -11.73% | **+10.22%** | 0.0% |
| **Sharpe** | -0.15 | **0.27** | 0.0 |
| **MDD** | -15.83% | **-11.50%** | 0.0% |
| **Trades** | 304 | **334** | 0 |
| **Win Rate** | 38.2% | 38.6% | N/A |
| **Profit Factor** | 0.85 | **1.02** | N/A |
| **Final Value** | $88,269 | **$110,215** | ₩100M |
| **ES1 fires** | 79 (26%) | **118 (35%)** | N/A |
| **ES1 PnL** | -407.6% | **-682.2%** | N/A |

## Regime Distribution

| Regime | SP500 | NDX | KOSPI |
|--------|-------|-----|-------|
| BULL | 50.4% | **57.3%** | 26.8% |
| NEUTRAL | 46.5% | 37.1% | **69.1%** |
| BEAR | 3.1% | **5.6%** | 4.1% |

## Key Insights

### 1. NDX > SP500 > KOSPI
- NDX의 기술주 중심 구성이 모멘텀/추세 전략에 유리
- SP500은 섹터 분산으로 모멘텀 신호 약화
- KOSPI는 데이터/리스크 게이트 문제로 거래 불가

### 2. ES1 Stop-Loss: 공통 최대 손실 원인
- SP500: 26% of trades → -407.6% total PnL
- NDX: 35% of trades → -682.2% total PnL (더 심각)
- NDX 변동성이 높아 ES1 발생률 더 높음

### 3. Bear Market Detection Gap (공통)
- SP500 BEAR 3.1%, NDX BEAR 5.6% — 실제 2022 약세장 대비 과소 감지
- KOSPI BEAR 4.1% — 유사 패턴

### 4. KOSPI Data Limitations
- yfinance KRX 데이터 품질 낮음 → 200봉 미만 종목 다수
- KIS API 또는 Naver Finance로 데이터 보완 필요
- KOSPI는 별도 데이터 파이프라인 구축 후 재검증 필요

---

## Engine Upgrade (B1-B8) 적용 후 예상 개선

| 개선 항목 | 대상 | 기대 효과 |
|-----------|------|-----------|
| B1: 5-level stock regime | SP500, NDX | RANGE_BOUND 83% → 분산 개선 |
| B2: OBV score | SP500, NDX | 볼륨 확인으로 거짓 신호 감소 |
| B3: Regime smoothing | SP500, NDX | 채터링 방지, 안정적 전환 |
| B4: Strategy routing | SP500, NDX | 종목-전략 매칭 최적화 |
| B6: Bear detection | SP500, NDX | BEAR 인식률 향상 (3%→10%+) |
| B8: ATR stop + min strength | SP500, NDX | ES1 발생률 26%→<17% 목표 |

---

## Verification Plan

엔진 업그레이드(B1-B8) 후 동일 조건 5-year 백테스트 실행하여 비교:

### Success Criteria (SP500 기준)

| Metric | Baseline | Target |
|--------|----------|--------|
| Sharpe | -0.15 | > 0.0 |
| ES1 fires | 79 (26%) | < 50 (< 17%) |
| Bear-year WR | 32-35% | > 40% |
| MDD | -15.83% | ≤ -15% |
| Stock regime dist | 83% RANGE_BOUND | No single > 45% |
| 2024 bull perf | +7.4% | ≥ +5% |

### Regression Check
2-year backtest (2024-01 ~ 2026-02): Sharpe ≥ 1.0 (baseline 1.18)
