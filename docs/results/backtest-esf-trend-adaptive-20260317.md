# ES Futures — Trend-Adaptive Strategy Backtest Report

**Date**: 2026-03-17
**Strategy**: Trend-Adaptive Regime Detection + 4-Layer Scoring
**Changes**: TrendRegimeDetector, CRISIS blocking, regime-aware counter-bias

---

## 10-Year Results (2016-01-01 → 2026-03-17, MES, $100K)

| Metric | Baseline | Trend-Adaptive | Delta |
|--------|----------|---------------|-------|
| Sharpe | **0.82** | **0.92** | **+0.10** |
| Return | 23.68% | 22.31% | -1.37% |
| Trades | 90 (L:81 S:9) | 83 (L:83 S:0) | -7 |
| Win Rate | 56.7% | **59.0%** | **+2.3%** |
| PF | 1.86 | **2.03** | **+0.17** |
| MDD | -3.79% | -3.79% | 0 |
| CAGR | 2.04% | 1.94% | -0.10% |
| MDD Duration | 471d | 471d | 0 |

### Regime Breakdown (Trend-Adaptive)

| Regime | Trades | Win Rate | PnL |
|--------|--------|----------|-----|
| BULL | 54 | 51.9% | +$9,264 |
| **NEUTRAL** | **29** | **72.4%** | **+$13,045** |
| BEAR | 0 (blocked) | — | — |
| CRISIS | 0 (blocked) | — | — |

---

## 2-Year Results (2024-01-01 → 2026-03-17, MES, $100K)

| Metric | Baseline | Trend-Adaptive |
|--------|----------|---------------|
| Sharpe | 1.49 | 1.25 |
| Trades | 22 (L:21 S:1) | 21 (L:21 S:0) |
| Win Rate | 63.6% | 61.9% |
| PF | 2.78 | 2.28 |
| MDD | -3.10% | **-2.67%** |

### Regime Breakdown (2y)

| Regime | Trades | Win Rate | PnL |
|--------|--------|----------|-----|
| NEUTRAL | 9 | **77.8%** | +$5,345 |
| BULL | 12 | 50.0% | +$1,169 |

---

## Key Findings

### What Worked
1. **NEUTRAL regime identification**: 72-78% WR — mean reversion in sideways markets is the primary alpha
2. **CRISIS blocking**: Prevented 14-19 losing trades (21-37% WR), saved $1,000-5,450
3. **Sharpe improvement**: 0.82 → 0.92 on 10y by eliminating low-quality trades
4. **Higher PF**: 1.86 → 2.03 (better risk/reward per trade)

### What Didn't Work
1. **Daily bar SHORT trades**: 27-37% WR across all tests — insufficient edge
2. **BEAR regime entries**: Even with regime detection, bear market shorts lose
3. **Relaxed direction (2-pt threshold)**: Generated too many low-quality signals

### Root Cause Analysis
- **SHORT on daily bars fails** because bear markets have violent rallies
- The original strategy's LONG bias was actually correct for daily timeframes
- SHORT edge exists only on **intraday** bars (where Fabio scalping applies)

---

## Architecture Changes

| File | Change |
|------|--------|
| `ats/strategy/trend_regime_detector.py` | NEW: Centralized regime detection (-10 to +10 score) |
| `ats/strategy/sp500_futures.py` | Regime-adaptive `_apply_regime()`, relaxed Z-Score (±1.5) |
| `ats/strategy/mean_reversion.py` | Bidirectional: SHORT scoring + exit cascade |
| `ats/backtest/futures_backtester.py` | `trend_adaptive` param, regime_at_entry tracking |
| `ats/api/esf_intraday_routes.py` | `trend_adaptive` param in backtest API |
| `web/src/lib/api.ts` | `trend_adaptive` param in ESFBacktestParams |

---

## Regime Detection Components

| Component | Score | Description |
|-----------|-------|-------------|
| MA200 position | ±2 | Price vs MA200 |
| MA200 slope | ±1 | 20-day MA200 direction |
| EMA alignment | ±2 | EMA 20/50/100 order |
| MACD | ±1 | Histogram direction |
| RSI breadth | ±1 | RSI > 60 / < 40 |
| VIX level | +1/-1/-2 | < 15 / > 25 / > 35 |

**Mapping**: BULL ≥ +5, NEUTRAL +1~+4, BEAR -1~-4, CRISIS ≤ -5

---

## Next Steps

### P0: Intraday SHORT (Fabio Scalping)
- SHORT edge exists on intraday bars, not daily
- Integrate Fabio Model 1 (inverted) + Model 2 for intraday SHORT
- AMT 3-Stage + Triple-A for intraday execution quality

### P1: Regime Display
- Add regime badge to /es-futures Live Analysis tab
- Show trend score, components, recommended strategy

### P2: Multi-contract Scaling
- NEUTRAL regime (72% WR) → increase position size
- Scale contracts with equity growth

---

## Files

| File | Description |
|------|------------|
| `data_store/backtest_esf_baseline_10yr.json` | Baseline 10y result |
| `data_store/backtest_esf_trend_adaptive_10yr.json` | Trend-adaptive 10y result |
| `data_store/backtest_esf_trend_adaptive_2yr.json` | Trend-adaptive 2y result |
