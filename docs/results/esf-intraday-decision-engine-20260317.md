# ESF Intraday Decision Engine — Analysis Report

**Date**: 2026-03-17
**Ticker**: MES=F (Micro E-mini S&P 500)
**Period**: 60d intraday (15m bars)
**Initial Equity**: $10,000

---

## Phase Summary

### Phase A: Page Rename + Tab Restructure
- Route: `/es-futures` → `/futures` (with redirect)
- Chart tab removed, embedded into Decision Engine tab
- Title: "Futures" / "Regime + MA + ATR Decision Engine"

### Phase B: Strategy Dashboard (Frontend)
- `StrategyDashboard` component: 3-panel layout (Regime, MA Trend, ATR Volatility)
- `analyzeMA()`: EMA 8/21/55 alignment + slope detection
- `analyzeATR()`: Current vs rolling avg, EXPANDING/NORMAL/CONTRACTING state
- `computeUnifiedStrategy()`: Combines regime + MA + ATR + Z-Score → direction, strategy type, entry timing, confidence

### Phase C: Backend Regime-Aware Scoring
- MA alignment bonus/penalty (configurable, default disabled after testing)
- Regime direction bias (CRISIS blocks LONG, configurable per-regime)
- ATR-adaptive SL/TP (configurable expand/contract multipliers)
- Regime-adjusted grade thresholds (configurable per regime)
- All new fields tracked in signal metadata

### Phase D: Baseline Backtest + Trade Analysis

**Baseline Results (60d, cached snapshot):**

| Metric | Value |
|--------|-------|
| Return | +3.26% ($326) |
| Sharpe | 1.06 |
| MDD | -5.49% |
| WR | 37.5% (9W/15L/24T) |
| PF | 1.34 |
| Avg Win | $143.09 |
| Avg Loss | $64.10 |

**Trade Analysis Findings:**

| Category | Key Finding |
|----------|------------|
| **Best Hour** | 11h ET: 4T, 75% WR, avg +$178/trade |
| **Worst Hour** | 10h ET: 11T, 27.3% WR, avg -$28/trade |
| **Direction** | SHORT outperforms LONG (44.4% vs 33.3% WR) |
| **Grade** | Grade B (45.5% WR) > Grade A (22.2% WR) |
| **Regime** | All 24 trades in NEUTRAL (current market) |
| **Exit** | ES_EOD (46%), ES_ATR_SL (29%), ES_ATR_TP (25%) |

**Hourly Entry Distribution:**
```
 9h: 5T  WR 40.0%  avg -$7
10h: 11T WR 27.3%  avg -$28  ← WORST (most trades, lowest WR)
11h: 4T  WR 75.0%  avg +$178 ← BEST
12h: 1T  WR  0.0%  avg -$6   (lunch lull)
14h: 1T  WR  0.0%  avg -$16
15h: 2T  WR 50.0%  avg -$9
```

### Phase E: Strategy Refinement

**Tested modifications (all degraded performance):**

| Modification | Impact |
|-------------|--------|
| MA alignment bonus (+15/+8/+5 pts) | Boosted wrong trades, degraded Sharpe |
| MA counter-penalty (-10/-5/-3 pts) | Filtered good trades |
| Regime direction bias (±5/10 pts) | No effect in NEUTRAL, too aggressive in BULL/BEAR |
| ATR-adaptive SL/TP (1.3x/0.7x) | Widened stops, reduced TP hits: 6→2 ES_ATR_TP |
| LONG penalty in NEUTRAL (-2/-3/-5) | Removed good LONG trades |
| Time filter (avoid 10h/12h) | Removed trades but didn't improve quality |

**Conclusion**: The original 4-layer scoring is well-calibrated. Additive bonuses/penalties on a 100-point scale introduce non-linear distortions. All scoring modifications were disabled (set to 0).

**Retained improvements:**
- Regime detection metadata in signals and trade records
- MA alignment tracking for analytics
- ATR ratio tracking for monitoring
- Trade pattern analysis (`analyze_trades()` method)
- CRISIS regime blocks LONG entries (safety gate)
- Time filter infrastructure (disabled by default, configurable)
- Frontend StrategyDashboard showing real-time regime/MA/ATR state

### Phase F: Verification
- Python tests: 58/58 pass
- TypeScript: Clean compile (`npx tsc --noEmit`)
- Frontend: `/futures` renders correctly with embedded chart + StrategyDashboard

---

## Key Learnings

1. **Small score adjustments (±5-15 pts) have outsized impact** on a 100pt scale with tight grade thresholds (55/45/35)
2. **11h ET is the optimal entry window** — opening range breakouts at 10h are traps
3. **SHORT outperforms LONG** in current NEUTRAL regime — structural short-selling edge
4. **Grade A WR (22%) < Grade B WR (46%)** — highest confidence signals may be momentum traps
5. **ES_EOD dominates exits (46%)** — trades held to end of day, suggesting TP/SL are set too wide
6. **60d intraday data is inherently noisy** — results shift significantly with 1-day window changes

## Files Modified

| File | Changes |
|------|---------|
| `web/src/App.tsx` | Route `/futures`, redirects |
| `web/src/components/layout/Navbar.tsx` | "Futures" nav link |
| `web/src/pages/ESFuturesScalping.tsx` | Tab restructure, StrategyDashboard, RegimePanel |
| `web/src/pages/ESFuturesScalping.css` | Decision layout CSS, Strategy Dashboard CSS |
| `web/src/hooks/useESFuturesScalp.ts` | TabKey update, default decision tab |
| `web/src/lib/futuresScalpEngine.ts` | analyzeMA, analyzeATR, computeUnifiedStrategy |
| `ats/strategy/esf_intraday.py` | MA bonus, regime bias, ATR-adaptive, time filter |
| `ats/data/config_manager.py` | Phase C/E config params |
| `ats/backtest/intraday_backtester.py` | analyze_trades(), regime/ma_alignment in trades |
