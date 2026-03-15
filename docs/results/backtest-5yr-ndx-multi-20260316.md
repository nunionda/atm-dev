# 5-Year NASDAQ 100 Multi-Strategy Backtest Report

**Date:** 2026-03-16
**Period:** 2021-03-16 ~ 2026-03-16 (1,255 trading days)
**Strategy:** multi (all strategies)
**Universe:** ndx_full (NASDAQ 100 stocks, 14-day rebalancing)
**Initial Capital:** $100,000
**Raw Data:** `data_store/backtest_5yr_ndx_multi_20210316_20260316.json`

---

## 1. Summary Metrics

| Metric | Value |
|--------|-------|
| Total Return | **+10.22%** |
| CAGR | +1.97% |
| Sharpe Ratio | **0.27** |
| Sortino Ratio | 0.28 |
| Calmar Ratio | 0.17 |
| MDD | **-11.50%** (2023-10-03) |
| Profit Factor | 1.02 |
| Win Rate | 38.6% |
| Total Trades | 334 |
| Avg Holding Days | 11.1 |
| Max Consecutive Wins | 9 |
| Max Consecutive Losses | 14 |
| Final Value | $110,215 |
| Total Rebalances | 90 |
| Avg Turnover | 3.4% |
| Avg Win | +9.07% |
| Avg Loss | -4.84% |
| Best Trade | +33.65% |
| Worst Trade | -24.63% |

### Regime Distribution

| Regime | Time % |
|--------|--------|
| BULL | 57.3% |
| NEUTRAL | 37.1% |
| BEAR | 5.6% |

---

## 2. Yearly Performance

| Year | Trades | WR | Total PnL | Notable |
|------|--------|----|-----------|---------|
| 2021 | 0 | - | - | 데이터 축적 기간 |
| 2022 | 55 | 38% | +12.2% | 약세장에서도 소폭 수익 |
| **2023** | **80** | **40%** | **+82.4%** | 최고 수익 연도 |
| **2024** | **93** | **43%** | **+122.4%** | 최다 거래, 최고 WR |
| 2025 | 88 | 39% | +19.2% | 횡보장 |
| 2026 (Q1) | 18 | 11% | -58.5% | 급격한 손실 |

---

## 3. Exit Reason Analysis

| Exit Reason | Count | Avg PnL | Total PnL | Comment |
|-------------|-------|---------|-----------|---------|
| **ES1 손절 -5%** | **118** | **-5.78%** | **-682.2%** | 최대 손실 원인 (35%) |
| ES_SMC ATR TP | 38 | +11.08% | +421.1% | 최대 수익 원인 |
| ES_MR TP (MA20) | 33 | +8.69% | +286.7% | MR 전략 TP |
| ES3 트레일링스탑 | 22 | +6.86% | +150.9% | 트레일링 수익 확보 |
| ES4 데드크로스 | 34 | -3.61% | -122.7% | 추세 약화 |
| ES2 익절 +20% | 5 | +22.81% | +114.1% | 슈퍼 위너 |
| ES5 보유기간 초과 | 19 | +4.05% | +76.9% | 장기 보유 수익 |
| ES_MR ATR SL | 18 | -4.26% | -76.7% | MR 손절 |
| ES2 익절 +12% | 3 | +21.96% | +65.9% | NEUTRAL TP |
| ES_CHOCH 추세반전 | 20 | -2.36% | -47.3% | 약세장 반전 신호 |
| ES_SMC ATR SL | 9 | -3.34% | -30.1% | SMC 손절 |

---

## 4. Monthly Returns Heatmap

```
2021: (no trades — data accumulation period)

2022: Jan -0.6 | Feb -3.4 | Mar +2.9 | Apr -0.5 | May +0.1 | Jun +0.5
      Jul +0.8 | Aug -0.6 | Sep -0.3 | Oct -0.3 | Nov +1.0 | Dec +0.1
      → Annual: -0.3%

2023: Jan +2.8 | Feb -4.7 | Mar -3.0 | Apr -0.1 | May +0.5 | Jun +1.3
      Jul -0.0 | Aug -3.0 | Sep -2.8 | Oct +1.2 | Nov +6.6 | Dec +4.3
      → Annual: +3.1%

2024: Jan -0.1 | Feb +0.0 | Mar +1.7 | Apr -8.1 | May +3.6 | Jun +1.7
      Jul -1.2 | Aug +3.4 | Sep +2.6 | Oct +4.5 | Nov +5.3 | Dec -3.1
      → Annual: +10.3%

2025: Jan +4.4 | Feb -0.8 | Mar -3.4 | Apr +1.2 | May +0.4 | Jun +1.7
      Jul -2.2 | Aug +0.2 | Sep +5.0 | Oct -1.2 | Nov -0.1 | Dec -0.1
      → Annual: +5.1%

2026: Jan -4.6 | Feb +1.1 | Mar -2.1
      → YTD: -5.6%
```

---

## 5. Phase Funnel Stats

| Phase | Count | Rate |
|-------|-------|------|
| Total Scans | 23,401 | 100% |
| Phase 1 Trend Rejects | 7,413 | 31.7% |
| Phase 2 Late Rejects | 46 | 0.2% |
| Phase 3 No Primary | 12,405 | 53.0% |
| Phase 3 No Confirm | 275 | 1.2% |
| Phase 4 Risk Blocks | 173 | 0.7% |
| **Entries Executed** | **629** | **2.7%** |

### Strategy Entries

| Strategy | Entries |
|----------|--------|
| SMC | 390 |
| Mean Reversion | 110 |
| Momentum | ~114 (from trades) |
| Breakout-Retest | 0 (0 retests entered) |

### Per-Stock Regime Distribution

| Stock Regime | Stocks |
|-------------|--------|
| RANGE_BOUND | 42 (84%) |
| BULL | 4 (8%) |
| BEAR | 2 (4%) |
| NEUTRAL | 1 (2%) |
| STRONG_BULL | 1 (2%) |

---

## 6. Key Observations

### 강점
1. **양수 수익률 (+10.22%)**: SP500 대비 크게 우수 (-11.73% vs +10.22%)
2. **낮은 MDD (-11.50%)**: BR-R02 한도(-15%) 이내
3. **2023-2024 연속 수익**: NDX 기술주 강세장 포착 성공
4. **SMC ATR TP 우수**: 38건 평균 +11.08% — SP500보다 높은 수익

### 약점
1. **ES1 손절 -682.2%**: 118건(35%)로 SP500(79건)보다 더 심각 — NDX 변동성 반영
2. **2026 Q1 급락**: 18건 중 WR 11%, -58.5% PnL — 시장 전환 대응 실패
3. **Max Consecutive Losses 14**: SP500(11)보다 높음 — 심리적 부담 가중
4. **RANGE_BOUND 84%**: 종목별 레짐이 대부분 RANGE_BOUND에 집중 (SP500과 동일 문제)
5. **BRT 미작동**: Breakout-Retest 0건 진입 — NDX 유니버스에서 비효율

### SP500 vs NDX 비교

| Metric | SP500 5Y | NDX 5Y |
|--------|----------|--------|
| Return | -11.73% | **+10.22%** |
| Sharpe | -0.15 | **0.27** |
| MDD | -15.83% | **-11.50%** |
| Trades | 304 | 334 |
| WR | 38.2% | 38.6% |
| PF | 0.85 | **1.02** |
| ES1 fires | 79 (26%) | **118 (35%)** |
| ES1 PnL | -407.6% | **-682.2%** |

---

## 7. NDX-Specific Upgrade Insights

### NDX가 SP500보다 나은 이유
1. 기술주 중심 → 모멘텀/트렌드 전략에 유리
2. BULL 시간 57.3% (SP500 50.4%) → 더 긴 강세 기간
3. SMC TP가 더 높은 수익 (+11.08% vs +7.03%)

### NDX 특유의 문제
1. ES1 빈도가 더 높음 (35% vs 26%) → 높은 변동성으로 인한 거짓 진입
2. 2026 Q1 급락 대응 실패 → 빠른 하락전환 감지 필요
3. BRT 전략 완전 미작동 → NDX에서 BRT 파라미터 재조정 필요

---

## 8. Comparison Baseline

```
NDX 5-Year Baseline (2021-03-16 ~ 2026-03-16):
  Return: +10.22%  |  Sharpe: 0.27   |  MDD: -11.50%
  Trades: 334      |  WR: 38.6%     |  PF: 1.02
  Final: $110,215
```
