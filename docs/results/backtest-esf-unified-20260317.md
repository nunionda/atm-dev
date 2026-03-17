# ES Futures Scalping — Unified Backtest Report

**Date**: 2026-03-17
**Page**: `/es-futures` (Unified ES Futures Scalping)
**Strategy**: SP500 Futures 4-Layer Scoring + ESF Intraday AMT

---

## Backtest Results Summary

### 1. Intraday Backtest (60d, MES, $10K)

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Return | +5.05% | — | — |
| Sharpe | **2.11** | ≥ 1.0 | PASS |
| MDD | -2.67% | ≤ -10% | PASS |
| Trades | 20 | — | — |
| Win Rate | 50.0% | ≥ 50% | PASS |
| PF | 1.69 | ≥ 1.5 | PASS |
| R:R | 1.69 | — | — |
| Avg Win | $123.75 | — | — |
| Avg Loss | $73.26 | — | — |

**Exit Reasons**: ATR_SL 7, ATR_TP 7, EOD 6
**Sessions**: 49 trading days
**Monte Carlo**: VaR95=49.2%, Bankruptcy=0.0%

**File**: `data_store/backtest_esf_intraday_60d_20260317.json`

---

### 2. Daily Backtest (2y, MES, $100K)

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Return | +9.08% | — | — |
| Sharpe | **1.49** | ≥ 1.0 | PASS |
| Sortino | 1.24 | — | — |
| Calmar | 1.28 | — | — |
| CAGR | 3.98% | ≥ 8% | FAIL |
| MDD | -3.10% | ≤ -15% | PASS |
| Trades | 22 (L:21 S:1) | — | — |
| Win Rate | 63.6% | ≥ 50% | PASS |
| PF | 2.78 | ≥ 1.5 | PASS |
| R:R | 1.59 | — | — |

**Exit Reasons**: ATR_TP 12, ATR_SL 7, MAX_HOLDING 2, CHANDELIER 1
**Rolls**: 7 ($87.50)
**Monte Carlo**: VaR95=0.3%, CVaR99=3.2%, Worst MDD=6.5%, Bankruptcy=0.0%

**File**: `data_store/backtest_esf_daily_2yr_20240101_20260317.json`

---

### 3. Daily Backtest (10y, MES, $100K)

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Return | +23.68% | — | — |
| Sharpe | 0.82 | ≥ 1.0 | FAIL |
| Sortino | 0.54 | — | — |
| Calmar | 0.54 | — | — |
| CAGR | 2.04% | ≥ 8% | FAIL |
| MDD | -3.79% | ≤ -15% | PASS |
| MDD Duration | 471 days | — | — |
| Trades | 90 (L:81 S:9) | — | — |
| Win Rate | 56.7% (L:58.0% S:44.4%) | ≥ 50% | PASS |
| PF | 1.86 | ≥ 1.5 | PASS |
| R:R | 1.42 | — | — |
| Total PnL | $23,682.62 | — | — |
| Costs | $1,067.96 | — | — |

**Exit Reasons**: ATR_TP 40, ATR_SL 27, MAX_HOLDING 13, MACD_REVERSAL 5, HARD_SL 3, CHANDELIER 2
**CB Events**: 4 (market circuit breakers)
**Rolls**: 24 ($575.00)
**Monte Carlo**: VaR95=1.8%, CVaR99=4.4%, Worst MDD=7.1%, Bankruptcy=0.0%
**Percentiles**: p5=-1.8% p25=0.3% p50=1.9% p75=3.6% p95=6.6%

**File**: `data_store/backtest_esf_10yr_20160101_20260317.json`

---

## Analysis

### Strengths
- **Risk-adjusted returns excellent for intraday**: Sharpe 2.11 (60d)
- **Very low MDD**: -2.67% to -3.79% across all timeframes
- **Zero margin calls, zero bankruptcy risk**
- **Robust win rate**: 50-63.6% across all periods
- **Profit Factor consistently > 1.5**: 1.69 to 2.78

### Weaknesses
- **10y Sharpe 0.82**: Below 1.0 target. Root cause: long MDD duration (471 days)
- **CAGR 2-4%**: Below 8% target. Root cause: MES micro contracts on $100K = low capital efficiency
- **Trade frequency**: ~9 trades/year on daily bars = many flat periods
- **Short side weak**: Only 9 shorts in 10 years, 44.4% WR
- **ATR_SL exits dominant**: 30% of exits are stop-outs

### Parameter Sensitivity (10y)
| Config | Sharpe | Trades | CAGR |
|--------|--------|--------|------|
| **entry_threshold=50 (baseline)** | **0.82** | **90** | **2.04%** |
| entry_threshold=45 | 0.54 | 93 | 1.24% |
| entry_threshold=55 | -0.04 | 5 | -0.03% |
| max_holding_days=30 | 0.64 | 89 | 1.58% |
| atr_breakout_mult=0.10 | 0.70 | 94 | 1.69% |
| ES full (not micro) | 0.44 | 71 | 5.69% (MDD -15%) |

**Conclusion**: Current parameters are at local optimum. Entry threshold 50 is the sweet spot.

---

## Upgrade Recommendations

### P0: Increase CAGR (structural)
1. **Multi-contract scaling**: Scale MES contracts with equity growth (currently capped)
2. **Add NQ=F/MNQ=F**: Diversify across indices for more signals
3. **Intraday+Daily hybrid**: Use intraday signals (Sharpe 2.11) as primary, daily as swing overlay

### P1: Improve 10y Sharpe
1. **Adaptive ATR SL**: Use wider stops in low-volatility (VIX < 15) and tighter in high-vol
2. **Short-side improvements**: Reduce counter-bias penalty in BEAR regime from 5.0 → 3.0
3. **MDD duration reduction**: Add time-based exit tightening after 30+ days underwater

### P2: Strategy extensions
1. **Session-aware sizing**: Full size in RTH, half in Globex
2. **Volume Profile integration into daily**: Port VP levels from intraday to daily scoring
3. **Correlated instrument confirmation**: Use VIX, DXY, bond yields as filters

---

## Config (Current Optimum)

```yaml
sp500_futures:
  entry_threshold: 50.0
  sl_atr_mult: 2.0
  sl_atr_mult_strong: 1.5
  tp_atr_mult: 3.0
  max_holding_days: 20
  regime_bull_entry_threshold: 50.0
  regime_counter_bias_penalty: 5.0
```

---

## Files

| File | Description |
|------|------------|
| `data_store/backtest_esf_intraday_60d_20260317.json` | Intraday 60d result |
| `data_store/backtest_esf_daily_2yr_20240101_20260317.json` | Daily 2y result |
| `data_store/backtest_esf_10yr_20160101_20260317.json` | Daily 10y result |
| `docs/stock_theory/es_scalping_strategy_v2.md` | Strategy documentation |
| `web/src/pages/ESFuturesScalping.tsx` | Unified page |
| `web/src/hooks/useESFuturesScalp.ts` | Merged hook |
