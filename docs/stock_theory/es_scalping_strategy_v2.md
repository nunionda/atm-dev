# ES Futures Scalping Strategy v2

## Overview

Unified ES/MES scalping strategy combining AMT (Auction Market Theory) 3-Stage filter
with statistical decision engine for intraday futures trading.

**Target Instrument**: E-mini S&P 500 (ES=F) / Micro E-mini (MES=F)
**Timeframe**: 15m primary, 5m execution
**Session**: RTH 09:30-16:00 ET (primary), Globex (reduced sizing)

---

## Architecture

```
Market Overview (Session + AMT State)
    ↓
4-Layer Scoring (100 pts total)
    ↓
Grade Gate (A/B/C/NO_TRADE)
    ↓
Decision Engine (Z-Score + EV + Kelly + R:R)
    ↓
Position Sizing + Entry/Exit
```

---

## 4-Layer Scoring (100 pts)

| Layer | Points | Components |
|-------|--------|-----------|
| L1: AMT + Location | 30 | Market State (15) + VP Zone (15) |
| L2: Z-Score | 20 | Statistical deviation from SMA20 |
| L3: Momentum | 25 | MACD (10) + ADX/DMI (8) + RSI (5) + Bars (2) |
| L4: Volume + Aggression | 25 | Volume surge (12) + OBV (8) + Aggression (5) |

### L1: AMT + Location (30 pts)

**Market State (15 pts)**:
- IMBALANCE aligned with direction: +15
- TRANSITION: +8
- BALANCE: +3

**VP Zone (15 pts)**:
- Long at VAL / Short at VAH: +15
- Long below POC / Short above POC: +10
- At POC: +5
- Against location: +0

### L2: Z-Score (20 pts)

```
Z = (Price - SMA20) / σ20
```

| Z-Score | Signal | Points |
|---------|--------|--------|
| Z < -2.0 | STRONG LONG | 20 |
| Z > +2.0 | STRONG SHORT | 20 |
| -2.0 ≤ Z < -1.5 | LEAN LONG | 15 |
| +1.5 < Z ≤ +2.0 | LEAN SHORT | 15 |
| -1.5 ≤ Z < -1.0 | MILD LONG | 8 |
| +1.0 < Z ≤ +1.5 | MILD SHORT | 8 |
| |Z| < 1.0 | NEUTRAL | 0 |

### L3: Momentum (25 pts)

- **MACD** (10 pts): Histogram positive + crossover aligned with direction
- **ADX/DMI** (8 pts): ADX > 25 AND +DI/-DI aligned
- **RSI** (5 pts): 40-60 range (mean-reversion) or aligned with trend
- **Bar pattern** (2 pts): 3-bar momentum confirmation

### L4: Volume + Aggression (25 pts)

- **Volume surge** (12 pts): Current volume > 1.5× MA20 volume
- **OBV trend** (8 pts): OBV slope aligned with direction
- **Aggression** (5 pts): Delta spike / CVD pressure (when footprint available)

---

## Grade System

| Grade | Score | Position Multiplier | Action |
|-------|-------|-------------------|--------|
| A | ≥ 55 | 100% | Full entry |
| B | ≥ 45 | 50% | Half position |
| C | ≥ 35 | 25% | Quarter position |
| D | < 35 | 0% | NO TRADE |

---

## Decision Gate (Post-Grade)

After passing grade filter, all 4 checks must pass for "GO":

1. **Z-Score Directionality**: |Z| ≥ 1.5
2. **Net EV > 0**: `EV = P(W) × AvgW - P(L) × AvgL - friction > 0`
3. **Kelly > 0**: `f* = (b×p - q) / b > 0` where b = AvgW/AvgL
4. **R:R ≥ 1.5**: Risk-reward ratio (TP/SL distance)

| Checks Passed | Verdict |
|---------------|---------|
| 4/4 | GO |
| 3/4 | CAUTION (reduced size) |
| < 3 | NO ENTRY |

---

## Expected Value Engine

```
Gross EV = p × avgWin - q × avgLoss        (in ticks)
Friction = slippage + commission/tickValue   (in ticks)
Net EV = Gross EV - Friction                (in ticks)
Net EV ($) = Net EV × tickValue
```

### Default Friction (MES)
- Slippage: 0.5 ticks ($0.625)
- Commission: $2.25 round-turn
- Tick value: $1.25

### Default Friction (ES)
- Slippage: 0.5 ticks ($6.25)
- Commission: $4.50 round-turn
- Tick value: $12.50

---

## Kelly Criterion & Position Sizing

```
f* = (b × p - q) / b
Half Kelly = f* / 2              (recommended for live trading)
```

**Conviction Scale**:
| Half-Kelly | Conviction |
|-----------|-----------|
| ≤ 0 | NO EDGE |
| < 2% | VERY LOW |
| < 5% | LOW |
| < 10% | MODERATE |
| < 20% | HIGH |
| ≥ 20% | VERY HIGH |

**Position Size**:
```
Risk Budget = Account × Risk% (default 2%)
Max Contracts = floor(Risk Budget / (ATR_Stop × Point_Value))
Recommended = min(Max Contracts, 2)      (scalping cap)
Final = Recommended × Grade_Multiplier
```

---

## ATR Stop & Take Profit

```
ATR Stop = ATR(14) × Multiplier (default 1.0)
```

**Direction**:
- Long: SL = Price - ATR_Stop, TP = Price + ATR_Stop × R_mult
- Short: SL = Price + ATR_Stop, TP = Price - ATR_Stop × R_mult

**Take Profit Levels**:
| Level | R-Multiple | Usage |
|-------|-----------|-------|
| TP1 | 1.5× ATR | Primary target (50% position) |
| TP2 | 2.0× ATR | Secondary target (30% position) |
| TP3 | 3.0× ATR | Runner (20% position, trailing) |

---

## Exit Cascade (Priority Order)

| Priority | ID | Condition |
|----------|-----|-----------|
| 1 | ES_HARD_SL | -1.5% account equity |
| 2 | ES_ATR_SL | ATR × multiplier stop |
| 3 | ES_ATR_TP | ATR × 2.5 take profit |
| 4 | ES_TRAIL | Trailing stop: activate at +0.8%, trail ATR × 1.0 |
| 5 | ES_EOD | 15 min before RTH close (15:45 ET) |
| 6 | ES_HALT | 3 consecutive losses → session halt |
| 7 | ES_VP_BREAK | VP zone (VAL/VAH) break against position |

---

## Basis Spread Monitor

```
Basis = Futures Price - Spot Price (SPY × 10)
Basis% = (Basis / Spot) × 100
```

| State | Condition | Implication |
|-------|-----------|-------------|
| CONTANGO | Basis > +2 pts | Normal (futures premium) |
| BACKWARDATION | Basis < -2 pts | Unusual (stress signal) |
| FAIR VALUE | -2 ≤ Basis ≤ +2 | Arbitrage-free |

---

## Session Rules

| Session | Polling | Sizing | Notes |
|---------|---------|--------|-------|
| RTH (09:30-16:00 ET) | 15s | 100% | Primary trading window |
| Globex/ETH | 60s | 50% | Reduced liquidity |
| Closed/Weekend | None | 0% | No trading |

**Intraday Risk Limits**:
- Max 1 open position at a time
- 3 consecutive losses → halt for session
- Daily loss hard limit: -1.5% of account
- 0.25-0.5% risk per trade (scalping)

---

## Backtest Modes

### Intraday Backtest
- **Data**: 15-minute bars
- **Max Period**: 60 days (yfinance limit)
- **Scoring**: ESF 4-Layer (AMT + Z-Score + Momentum + Volume)
- **Sessions**: Trades within RTH only, EOD forced close

### Daily Backtest
- **Data**: Daily bars
- **Max Period**: 10+ years
- **Scoring**: SP500 Futures 4-Layer (Z-Score + Trend + Momentum + Volume)
- **Exit**: Strategy-driven (ATR SL/TP, trailing, max holding, CHoCH)
- **Features**: Margin simulation, rollover costs, circuit breakers, Monte Carlo

---

## Performance Targets

| Metric | Intraday | Daily |
|--------|----------|-------|
| Sharpe | ≥ 1.0 | ≥ 1.0 |
| Win Rate | ≥ 50% | ≥ 50% |
| Profit Factor | ≥ 1.5 | ≥ 1.5 |
| MDD | ≤ -10% | ≤ -15% |
| CAGR | N/A | ≥ 8% |

---

## References

- `stock_theory/futuresStrategy.md` — Z-Score, EV Engine
- `stock_theory/future_trading_stratedy.md` — ATR-based entry/exit
- `stock_theory/scalpingPlaybook.md` — AMT 3-Stage, Triple-A Model
- `stock_theory/Kelly Criterion.md` — Kelly formula & asset allocation
- `stock_theory/ExitStrategyIndex.md` — Exit strategy taxonomy
- `ats/strategy/sp500_futures.py` — SP500FuturesStrategy implementation
- `ats/strategy/esf_intraday.py` — ESFIntradayStrategy implementation
