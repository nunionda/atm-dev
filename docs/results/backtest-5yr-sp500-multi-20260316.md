# 5-Year S&P 500 Multi-Strategy Backtest Report

**Date:** 2026-03-16
**Period:** 2021-03-16 ~ 2026-03-16 (1,255 trading days)
**Strategy:** multi (all strategies)
**Universe:** sp500_full (110 stocks, 14-day rebalancing)
**Initial Capital:** $100,000
**Raw Data:** `data_store/backtest_5yr_sp500_multi_20210316_20260316.json`

---

## 1. Summary Metrics

| Metric | Value |
|--------|-------|
| Total Return | **-11.73%** |
| CAGR | -2.47% |
| Sharpe Ratio | **-0.15** |
| Sortino Ratio | -0.14 |
| Calmar Ratio | -0.16 |
| MDD | **-15.83%** (2023-12-07) |
| Profit Factor | 0.85 |
| Win Rate | 38.2% |
| Total Trades | 304 |
| Avg Holding Days | 11.8 |
| Max Consecutive Wins | 6 |
| Max Consecutive Losses | 11 |
| Final Value | $88,269 |
| Total Rebalances | 90 |
| Avg Turnover | 4.0% |

---

## 2. Yearly Performance

| Year | Return | Intra-Year DD | Trades | WR | Total PnL |
|------|--------|---------------|--------|-----|-----------|
| 2021 | 0.0% | 0.0% | 0 | - | - |
| 2022 | -1.4% | -8.9% | 68 | 32% | -59.3% |
| 2023 | -9.5% | -12.2% | 60 | 35% | -20.4% |
| **2024** | **+7.4%** | -10.0% | 74 | **51%** | **+82.8%** |
| 2025 | -9.3% | -12.3% | 83 | 34% | -78.0% |
| 2026 (Q1) | +1.6% | -5.5% | 19 | 37% | -4.9% |

---

## 3. Regime Distribution

| Regime | Time % |
|--------|--------|
| BULL | 50.4% |
| NEUTRAL | 46.5% |
| BEAR | 3.1% |

---

## 4. Exit Reason Analysis (Top 10)

| Exit Reason | Count | Avg PnL | Total PnL | Comment |
|-------------|-------|---------|-----------|---------|
| **ES1 손절 -5%** | **79** | **-5.16%** | **-407.6%** | 최대 손실 원인 |
| ES_SMC ATR TP | 30 | +7.03% | +210.9% | 최대 수익 원인 |
| ES_CHOCH 추세반전 | 28 | -1.93% | -53.9% | 약세장 반전 신호 |
| ES5 보유기간 초과 | 26 | +5.73% | +148.9% | 장기 보유 수익 |
| ES_MR TP (MA20) | 22 | +6.61% | +145.4% | MR 전략 TP |
| ES4 데드크로스 | 22 | -3.30% | -72.5% | 추세 약화 |
| ES_MR ATR SL | 17 | -4.38% | -74.5% | MR 손절 |
| ES_SMC ATR SL | 17 | -4.40% | -74.8% | SMC 손절 |
| ES3 트레일링스탑 | 12 | +6.47% | +77.7% | 트레일링 수익 확보 |
| ES_MR TP (MA50) | 6 | +4.28% | +25.7% | MR 확장 TP |

---

## 5. Monthly Returns Heatmap

```
2021: (no trades — data accumulation period)

2022: Jan  0.0 | Feb +2.4 | Mar -3.7 | Apr -1.7 | May -0.5 | Jun -0.1
      Jul -0.2 | Aug -0.3 | Sep -1.5 | Oct  0.0 | Nov +5.9 | Dec -1.4
      → Annual: -1.4%

2023: Jan -4.4 | Feb -2.7 | Mar +1.2 | Apr -2.9 | May -0.9 | Jun +1.5
      Jul +1.5 | Aug -0.6 | Sep +0.9 | Oct -5.8 | Nov +0.4 | Dec +2.2
      → Annual: -9.5%

2024: Jan +0.2 | Feb +0.1 | Mar +1.9 | Apr -1.2 | May +2.2 | Jun -2.1
      Jul +1.6 | Aug +3.1 | Sep +1.1 | Oct -0.7 | Nov +4.3 | Dec -3.0
      → Annual: +7.4%

2025: Jan +2.2 | Feb -1.2 | Mar -5.2 | Apr +1.0 | May -0.5 | Jun +2.4
      Jul -3.6 | Aug +0.3 | Sep -1.0 | Oct  0.0 | Nov -1.2 | Dec -2.6
      → Annual: -9.3%

2026: Jan +2.5 | Feb +2.5 | Mar -3.3
      → YTD: +1.6%
```

---

## 6. Key Observations

### 강점
1. **MDD -15.83%**: BR-R02 한도(-15%) 근처에서 Circuit Breaker가 작동하여 치명적 손실 방지
2. **2024년 강세장 포착**: WR 51%, +82.8% PnL — 강세장에서는 효과적
3. **ES_SMC ATR TP**: 30건 평균 +7.03% — SMC TP가 가장 효율적
4. **ES5 보유기간 초과**: 26건 평균 +5.73% — 장기 보유 시 수익 실현

### 약점
1. **ES1 손절이 전체 PnL의 -407.6% 기여**: 79건(26%)이 -5% 손절 — 진입 정확도 부족
2. **약세/횡보장 WR 32-35%**: 2022, 2023, 2025 모두 손실 — 방어 전략 미흡
3. **2021년 12개월 미진입**: 데이터 축적 기간이 너무 긴 것은 아닌지 검토 필요
4. **Max Consecutive Losses 11**: 심리적 부담 + 자본 감소 누적
5. **전략 구분 없음** (all `unknown`): 트레이드별 전략 태깅이 API 응답에 누락

### 2-Year vs 5-Year 비교

| Metric | 2-Year (2024-2026) | 5-Year (2021-2026) |
|--------|-------------------|-------------------|
| Return | +28.4% | -11.73% |
| Sharpe | 1.18 | -0.15 |
| MDD | -9.7% | -15.83% |
| Trades | 185 | 304 |
| WR | ~55% | 38.2% |
| PF | 1.46 | 0.85 |

---

## 7. Upgrade Priorities for Engine v2

### P0 — Critical (약세장 방어)
1. **BEAR 레짐 진입 차단 강화**: 현재 BEAR 3.1% 시간만 인식 → 실제 약세 구간(2022 상반기)을 NEUTRAL로 분류하여 진입 허용
2. **ES1 손절 빈도 줄이기**: 79건(26%) → 진입 필터 강화 또는 초기 Stop 완화
3. **연속 손절 정지 규칙 활성화 확인**: BR-P05 (3회 연속 → 정지)가 실제로 작동하는지 검증

### P1 — Important (수익성 개선)
4. **Defensive 전략 강화**: 약세장에서 현금 비율 상향 또는 역추세 전략
5. **CHoCH Exit 최적화**: 28건 평균 -1.93% → PnL gate 조건 재조정
6. **데드크로스(ES4) 개선**: 22건 평균 -3.30% → 조기 청산이 손해를 키우는 케이스

### P2 — Enhancement
7. **트레이드별 전략 태깅**: `strategy` 필드가 `unknown` → 전략별 성과 분석 불가
8. **2021년 미진입 원인 분석**: 워밍업 기간 단축 또는 조건 완화 검토
9. **Regime 인식 개선**: MA200 Breadth 기반 레짐이 실제 약세를 늦게 감지

---

## 8. Comparison Baseline

이 리포트를 향후 엔진 업그레이드의 **기준선(baseline)**으로 사용:

```
5-Year Baseline (2021-03-16 ~ 2026-03-16):
  Return: -11.73%  |  Sharpe: -0.15  |  MDD: -15.83%
  Trades: 304      |  WR: 38.2%     |  PF: 0.85
  Final: $88,269
```

모든 엔진 변경 후 동일 기간/조건으로 백테스트하여 regression 체크.
