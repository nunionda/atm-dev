# Engine.py Decomposition (C2) Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decompose `ats/simulation/engine.py` (6689 lines) into focused modules, reducing it to ~1800 lines of orchestration while preserving all behavior and backtest compatibility.

**Architecture:** Extract constants, Pydantic models, StrategyAllocator, regime logic, risk gates, sizing, and per-strategy scan/exit methods into separate modules under `ats/simulation/`. The engine retains orchestration (`run_backtest_day`, `run_cycle`), execution (`_execute_buy/sell`), state management, and SSE broadcast. No behavioral changes — pure structural refactor.

**Tech Stack:** Python 3.9+, Pydantic, NumPy, Pandas, asyncio

**Validation:** After each phase, run `cd /Users/daniel/dev/atm-dev && python3 run_tests.py` (58 tests) + verify backtest produces identical results.

---

## File Structure

After decomposition, `ats/simulation/` will contain:

| File | Responsibility | Source Lines | Est. Lines |
|------|---------------|-------------|------------|
| `constants.py` | All dict constants, watchlist, type alias | 152-494 | ~345 |
| `models.py` | 8 Pydantic models (SimPosition, SimSignal, etc.) | 23-151 | ~130 |
| `allocator.py` | StrategyAllocator class + `_compute_adx` helper | 497-823 | ~330 |
| `regime.py` | Market regime, stock regime, index trend, VIX | 1517-1860 + 2047-2142 | ~500 |
| `risk_gates.py` | RG1-RG5, bearish divergence, S/R detection | 2144-2215, 2244-2340 | ~170 |
| `sizing.py` | Position sizing pure functions (ATR, multipliers) | Extracted from `_execute_buy` | ~120 |
| `indicators.py` | `_calculate_indicators*`, `_confirm_trend`, `_estimate_trend_stage` | 1426-1515, 1938-2046 | ~200 |
| `strategies/momentum.py` | `_scan_entries_momentum` + `_check_exits_momentum` | 2789-3064, 5866-6055 | ~460 |
| `strategies/smc.py` | SMC scan + exit + 4 scoring methods + indicators | 3065-3430 | ~370 |
| `strategies/mean_reversion.py` | MR scan + exit + 3 scoring + indicators | 3432-3892 | ~460 |
| `strategies/breakout_retest.py` | BRT scan + exit + scoring + conditions + zones | 3892-4549 | ~660 |
| `strategies/arbitrage.py` | Arb scan + exit + pairs + basis + sizing | 4550-5563 | ~1015 |
| `strategies/defensive.py` | Defensive scan + exit | 2514-2654 | ~140 |
| `strategies/volatility.py` | Volatility premium scan + exit | 2654-2789 | ~135 |
| `engine.py` | Orchestration, execution, state, SSE broadcast | Remainder | ~1800 |

**Existing files unchanged:** `controller.py`, `event_bus.py`, `universe.py`, `watchlists.py`, `portfolio_allocator.py`

---

## Chunk 1: Phase A — Zero-Risk Extractions

### Task 1: Extract constants.py

**Files:**
- Create: `ats/simulation/constants.py`
- Modify: `ats/simulation/engine.py:152-494`

- [ ] **Step 1: Create constants.py with all dict constants**

Extract these from engine.py lines 152-494:
```python
# ats/simulation/constants.py
"""
Simulation engine constants: regime parameters, strategy weights, ETF universes.
"""
from __future__ import annotations
from typing import Any, Callable, Coroutine, Dict, List

# ── 워치리스트 ──
WATCHLIST = [
    {"code": "005930", "ticker": "005930.KS", "name": "삼성전자"},
    # ... (전체 복사)
]

OnEventType = Callable[[str, Any], Coroutine[Any, Any, None]]

REGIME_PARAMS = { ... }
STOCK_REGIME_THRESHOLDS = [ ... ]
REGIME_EXIT_PARAMS = { ... }
BASE_KELLY: float = 0.50
REGIME_OVERRIDES: Dict[str, Dict[str, Any]] = { ... }
VIX_SIZING_SCALE = { ... }
REGIME_STRATEGY_WEIGHTS: Dict[str, Dict[str, float]] = { ... }
INDEX_TREND_STRATEGY_WEIGHTS: Dict[str, Dict[str, float]] = { ... }
REGIME_DISPLAY_NAMES: Dict[str, Dict[str, str]] = { ... }
STRATEGY_DISPLAY_NAMES: Dict[str, Dict[str, str]] = { ... }
REGIME_STRATEGY_COMPOSITION: Dict[str, Dict] = { ... }
INVERSE_ETFS = { ... }
SAFE_HAVEN_ETFS: Dict[str, List[Dict[str, str]]] = { ... }
MULTI_STRATEGIES = [...]
REGIME_STRATEGY_MODES: Dict[str, str] = { ... }
```

- [ ] **Step 2: Replace engine.py constants with imports**

In engine.py, remove lines 152-494 and add at top:
```python
from simulation.constants import (
    WATCHLIST, OnEventType,
    REGIME_PARAMS, STOCK_REGIME_THRESHOLDS, REGIME_EXIT_PARAMS,
    BASE_KELLY, REGIME_OVERRIDES, VIX_SIZING_SCALE,
    REGIME_STRATEGY_WEIGHTS, INDEX_TREND_STRATEGY_WEIGHTS,
    REGIME_DISPLAY_NAMES, STRATEGY_DISPLAY_NAMES,
    REGIME_STRATEGY_COMPOSITION,
    INVERSE_ETFS, SAFE_HAVEN_ETFS,
    MULTI_STRATEGIES, REGIME_STRATEGY_MODES,
)
```

- [ ] **Step 3: Fix external imports of constants**

Check `ats/scripts/analyze_market_today.py` — it imports `INDEX_TREND_STRATEGY_WEIGHTS, REGIME_STRATEGY_WEIGHTS` from `simulation.engine`. Update to import from `simulation.constants`.

Also check `ats/simulation/controller.py` — it defines its own `OnEventType` at line 29. Update it to import from `simulation.constants` instead.

- [ ] **Step 4: Run tests**

Run: `cd /Users/daniel/dev/atm-dev && python3 run_tests.py`
Expected: 58/58 PASS (no behavioral change)

- [ ] **Step 5: Commit**

```bash
git add ats/simulation/constants.py ats/simulation/engine.py ats/scripts/analyze_market_today.py
git commit -m "refactor: extract simulation constants to dedicated module"
```

---

### Task 2: Extract models.py

**Files:**
- Create: `ats/simulation/models.py`
- Modify: `ats/simulation/engine.py:23-151`

- [ ] **Step 1: Create models.py with all 8 Pydantic models**

Extract lines 23-151 from engine.py:
```python
# ats/simulation/models.py
"""
Pydantic models for simulation state serialization (frontend SSE + backtest).
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class SimSystemState(BaseModel): ...
class SimPosition(BaseModel): ...
class SimOrder(BaseModel): ...
class SimSignal(BaseModel): ...
class SimRiskMetrics(BaseModel): ...
class SimTradeRecord(BaseModel): ...
class SimEquityPoint(BaseModel): ...
class SimPerformanceSummary(BaseModel): ...
```

Copy all field definitions exactly as-is from engine.py lines 23-151.

- [ ] **Step 2: Replace engine.py model definitions with imports**

Remove lines 23-151 from engine.py, add:
```python
from simulation.models import (
    SimSystemState, SimPosition, SimOrder, SimSignal,
    SimRiskMetrics, SimTradeRecord, SimEquityPoint,
    SimPerformanceSummary,
)
```

- [ ] **Step 3: Check external model imports**

Search for any files importing these models from `simulation.engine` and update:
```bash
grep -rn "from simulation.engine import Sim" ats/
```
Update each to import from `simulation.models`.

- [ ] **Step 4: Run tests**

Run: `cd /Users/daniel/dev/atm-dev && python3 run_tests.py`
Expected: 58/58 PASS

- [ ] **Step 5: Commit**

```bash
git add ats/simulation/models.py ats/simulation/engine.py
git commit -m "refactor: extract Pydantic simulation models to dedicated module"
```

---

### Task 3: Extract allocator.py

**Files:**
- Create: `ats/simulation/allocator.py`
- Modify: `ats/simulation/engine.py:497-823`

- [ ] **Step 1: Create allocator.py**

Extract `StrategyAllocator` class (lines 497-795) and `_compute_adx()` function (lines 797-823):

```python
# ats/simulation/allocator.py
"""
Multi-strategy capital allocator with regime-based weights, Kelly scaling, and correlation tracking.
"""
from __future__ import annotations
from typing import Dict, List, Optional
import numpy as np

from simulation.constants import REGIME_STRATEGY_WEIGHTS


class StrategyAllocator:
    """멀티 전략 모드용 전략별 자본 배분 관리자."""
    # ... (전체 클래스 복사)


def _compute_adx(high, low, close, period: int = 14):
    """Standalone ADX calculation (used by regime classification)."""
    # ... (함수 복사)
```

- [ ] **Step 2: Update engine.py imports**

Remove lines 497-823, add:
```python
from simulation.allocator import StrategyAllocator, _compute_adx
```

- [ ] **Step 3: Run tests**

Run: `cd /Users/daniel/dev/atm-dev && python3 run_tests.py`
Expected: 58/58 PASS

- [ ] **Step 4: Commit**

```bash
git add ats/simulation/allocator.py ats/simulation/engine.py
git commit -m "refactor: extract StrategyAllocator to dedicated module"
```

---

## Chunk 2: Phase B — Regime, Risk, Indicators, Sizing

### Task 4: Extract regime.py

**Files:**
- Create: `ats/simulation/regime.py`
- Modify: `ats/simulation/engine.py`

- [ ] **Step 1: Create regime.py with regime-related methods as standalone functions**

Extract these methods, converting from `self.` to explicit parameters:

```python
# ats/simulation/regime.py
"""
Market regime classification: breadth-based regime judgment, smoothing,
index trend analysis, per-stock regime scoring.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd

from simulation.constants import (
    REGIME_PARAMS, STOCK_REGIME_THRESHOLDS, REGIME_OVERRIDES,
    INDEX_TREND_STRATEGY_WEIGHTS, REGIME_STRATEGY_WEIGHTS,
)
from simulation.allocator import _compute_adx


def judge_market_regime(
    ohlcv_cache: Dict[str, pd.DataFrame],
    watchlist: list,
    vix_level: float = 18.0,
) -> str:
    """Breadth-based regime classification. Returns regime string."""
    # Adapt from engine.py _judge_market_regime() (lines 1517-1623)
    # Replace self._ohlcv_cache → ohlcv_cache, self._watchlist → watchlist, etc.
    ...


def smooth_regime(
    raw_regime: str,
    candidate: str,
    candidate_days: int,
    confirmation_days: int = 5,
) -> tuple:
    """5-day regime confirmation. Returns (smoothed_regime, new_candidate, new_days)."""
    # Adapt from engine.py _smooth_regime() (lines 1624-1640)
    ...


def analyze_index_trend(
    index_ohlcv: List[Dict],
    market_regime: str,
) -> Dict:
    """SPX/KOSPI index trend analysis. Returns trend dict."""
    # Adapt from engine.py _analyze_index_trend() (lines 1684-1806)
    ...


def get_index_strategy_weights(
    trend_result: Dict,
) -> Optional[Dict[str, float]]:
    """Map index trend to strategy weight overrides."""
    # Adapt from engine.py _update_strategy_weights_from_index() (lines 1807-1860)
    # Return the weights dict instead of mutating engine state
    ...


def classify_stock_regime(
    df: pd.DataFrame,
) -> str:
    """Per-stock composite regime scoring (0-100 → 6 tiers)."""
    # Adapt from engine.py _classify_stock_regime() (lines 2047-2114)
    ...
```

- [ ] **Step 2: Add thin delegation methods on SimulationEngine**

In engine.py, replace the extracted methods with thin wrappers:
```python
def _judge_market_regime(self) -> str:
    return regime.judge_market_regime(
        self._ohlcv_cache, self._watchlist, self._vix_level,
    )

def _smooth_regime(self, raw_regime: str) -> str:
    result, self._regime_candidate, self._regime_candidate_days = regime.smooth_regime(
        raw_regime, self._regime_candidate,
        self._regime_candidate_days, self._regime_confirmation_days,
    )
    return result

def _analyze_index_trend(self) -> Dict:
    return regime.analyze_index_trend(self._index_ohlcv, self._market_regime)

def _classify_stock_regime(self, df: pd.DataFrame) -> str:
    return regime.classify_stock_regime(df)
```

This preserves the existing call pattern while delegating logic.

**Methods that remain on engine (NOT extracted):**
- `_update_market_regime()` (1641-1652) — orchestrates regime detection, mutates `self._market_regime`
- `update_vix()` (1654-1666) — VIX history management, backtest API
- `update_index_data()` (1672-1682) — index OHLCV buffer, backtest API
- `_update_stock_regimes()` (2115-2138) — 7-day caching orchestration, calls `classify_stock_regime()`
- `get_market_intelligence()` (1861-1886) — UI-facing aggregation
- `_reduce_positions_for_regime()` (1917-1932) — regime downgrade position cleanup
- `_get_vix_sizing_mult()` (1888-1916) — moved to sizing.py (see Task 7)

- [ ] **Step 3: Run tests**

Run: `cd /Users/daniel/dev/atm-dev && python3 run_tests.py`
Expected: 58/58 PASS

- [ ] **Step 4: Commit**

```bash
git add ats/simulation/regime.py ats/simulation/engine.py
git commit -m "refactor: extract market regime logic to simulation/regime.py"
```

---

### Task 5: Extract risk_gates.py

**Files:**
- Create: `ats/simulation/risk_gates.py`
- Modify: `ats/simulation/engine.py`

- [ ] **Step 1: Create risk_gates.py**

Extract lines 2144-2215 (`_risk_gate_check`) and 2244-2340 (divergence/S/R detection).

**Methods that remain on engine (NOT extracted):**
- `_force_liquidate_all()` (2216-2221) — mutates `self.positions`, calls `self._execute_sell()`
- `force_liquidate_all_immediate()` (2223-2242) — public API, same mutations

```python
# ats/simulation/risk_gates.py
"""
Risk gates RG1-RG5: daily loss, MDD, position limits, cash ratio, VIX extreme.
"""
from __future__ import annotations
from typing import Dict
import pandas as pd

from simulation.constants import REGIME_PARAMS


def check_risk_gates(
    daily_start_equity: float,
    current_equity: float,
    peak_equity: float,
    initial_capital: float,
    active_position_count: int,
    cash: float,
    market_regime: str,
    vix_level: float = 18.0,
    vix_ema20: float = 18.0,
) -> tuple:
    """
    Run RG1-RG5 risk gates.
    Returns: (can_trade: bool, reason: str)
    """
    # Adapt from engine.py _risk_gate_check() (lines 2144-2215)
    ...


def detect_bearish_divergence(df: pd.DataFrame, lookback: int = 10) -> bool:
    """Detect RSI/MACD bearish divergence."""
    # Adapt from engine.py _detect_bearish_divergence() (lines 2244-2271)
    ...


def detect_support_resistance(df: pd.DataFrame, lookback: int = 40) -> dict:
    """Detect support/resistance levels via clustering."""
    # Adapt from engine.py _detect_support_resistance() (lines 2272-2301)
    ...


def cluster_levels(levels: list, tolerance: float = 0.015) -> list:
    """Cluster price levels by tolerance."""
    # Adapt from engine.py _cluster_levels() (lines 2302-2336)
    ...
```

- [ ] **Step 2: Update engine.py with delegation**

Replace the extracted methods with thin wrappers calling `risk_gates.*` functions. Keep `_force_liquidate_all()` and `force_liquidate_all_immediate()` on engine as-is.

- [ ] **Step 3: Run tests**

Run: `cd /Users/daniel/dev/atm-dev && python3 run_tests.py`
Expected: 58/58 PASS

- [ ] **Step 4: Commit**

```bash
git add ats/simulation/risk_gates.py ats/simulation/engine.py
git commit -m "refactor: extract risk gates to simulation/risk_gates.py"
```

---

### Task 6: Extract indicators.py

**Files:**
- Create: `ats/simulation/indicators.py`
- Modify: `ats/simulation/engine.py`

- [ ] **Step 1: Create indicators.py**

Extract base indicator calculation and trend helpers:

```python
# ats/simulation/indicators.py
"""
Technical indicator calculation for simulation engine.
MA, RSI, MACD, BB, ATR, ADX/DMI, Volume MA, OBV.
Trend confirmation and stage estimation.
"""
from __future__ import annotations
import numpy as np
import pandas as pd


def calculate_indicators(
    df: pd.DataFrame,
    ma_short: int = 5,
    ma_long: int = 20,
    rsi_period: int = 14,
) -> pd.DataFrame:
    """Calculate base technical indicators on OHLCV DataFrame."""
    # Adapt from engine.py _calculate_indicators() (lines 1426-1515)
    ...


def confirm_trend(df: pd.DataFrame) -> dict:
    """Check MA alignment + ADX strength. Returns trend dict."""
    # Adapt from engine.py _confirm_trend() (lines 1938-1993)
    ...


def estimate_trend_stage(df: pd.DataFrame) -> str:
    """Classify trend as EARLY/MID/LATE."""
    # Adapt from engine.py _estimate_trend_stage() (lines 1994-2046)
    ...
```

- [ ] **Step 2: Update engine.py — delegate to indicators module**

- [ ] **Step 3: Run tests**

Run: `cd /Users/daniel/dev/atm-dev && python3 run_tests.py`
Expected: 58/58 PASS

- [ ] **Step 4: Commit**

```bash
git add ats/simulation/indicators.py ats/simulation/engine.py
git commit -m "refactor: extract technical indicators to simulation/indicators.py"
```

---

### Task 7: Extract sizing.py

**Files:**
- Create: `ats/simulation/sizing.py`
- Modify: `ats/simulation/engine.py`

- [ ] **Step 1: Create sizing.py with pure sizing functions**

Extract the position sizing logic from `_execute_buy()` (lines 5563-5811):

```python
# ats/simulation/sizing.py
"""
Position sizing: ATR-based risk sizing with regime/signal/VIX multipliers.
"""
from __future__ import annotations
from typing import Dict, Optional

from simulation.constants import (
    REGIME_PARAMS, REGIME_OVERRIDES, VIX_SIZING_SCALE, BASE_KELLY,
)


def get_vix_sizing_mult(
    vix_ema20: float,
    strategy: str = "momentum",
) -> float:
    """VIX-based sizing multiplier (1.0 normal → 0.3 panic)."""
    # Adapt from engine.py _get_vix_sizing_mult() (lines 1888-1916)
    ...


def calculate_position_size(
    price: float,
    atr: float,
    equity: float,
    cash: float,
    signal_strength: int,
    market_regime: str,
    trend_strength: str = "MODERATE",
    trend_stage: str = "MID",
    vix_ema20: float = 18.0,
    strategy: str = "momentum",
    kelly_scalar: float = 1.0,
    vol_scalar: float = 1.0,
    fixed_amount: float = 0,
    min_cash_ratio: float = 0.30,
    slippage_pct: float = 0.001,
    commission_pct: float = 0.00015,
) -> dict:
    """
    Calculate position quantity + buy_amount.
    Returns: {"quantity": int, "buy_price": float, "buy_amount": float, "raw_qty": int}
    """
    # Extract sizing logic from _execute_buy(), return computed values
    # Engine keeps execution logic (position creation, order recording)
    ...
```

- [ ] **Step 2: Refactor _execute_buy() to use sizing.calculate_position_size()**

Engine's `_execute_buy()` (lines 5563-5811) has two halves:
- **Lines 5563-~5680**: Pure sizing computation (ATR lookup, multipliers, quantity calc, caps) → extract to `sizing.py`
- **Lines ~5680-5811**: Position creation, order recording, state mutation → stays on engine

The boundary: everything before `pos = SimPosition(...)` is sizing; everything from `SimPosition(...)` onward is execution.

Engine's `_execute_buy()` calls `sizing.calculate_position_size()` then handles position creation. Also move `_get_vix_sizing_mult()` (lines 1888-1916) to `sizing.py` as `get_vix_sizing_mult()` since it's a pure function of VIX/strategy params.

- [ ] **Step 3: Run tests**

Run: `cd /Users/daniel/dev/atm-dev && python3 run_tests.py`
Expected: 58/58 PASS

- [ ] **Step 4: Commit**

```bash
git add ats/simulation/sizing.py ats/simulation/engine.py
git commit -m "refactor: extract position sizing to simulation/sizing.py"
```

---

## Chunk 3: Phase C — Strategy Extraction

### Task 8: Create strategies package + momentum

**Files:**
- Create: `ats/simulation/strategies/__init__.py`
- Create: `ats/simulation/strategies/momentum.py`
- Modify: `ats/simulation/engine.py`

- [ ] **Step 1: Create strategies package**

```python
# ats/simulation/strategies/__init__.py
"""Per-strategy scan/exit modules for the simulation engine."""
```

- [ ] **Step 2: Create momentum.py**

Extract `_scan_entries_momentum()` (lines 2789-3064) and `_check_exits_momentum()` (lines 5866-6054):

```python
# ats/simulation/strategies/momentum.py
"""
Momentum Swing strategy: 6-Phase pipeline scan + 7-tier exit cascade.
"""
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from simulation.engine import SimulationEngine


def scan_entries(engine: 'SimulationEngine'):
    """
    Phase 1-4 momentum entry scanning.
    Mutates engine.signals list directly (same pattern as original).
    """
    # Full copy of _scan_entries_momentum() logic
    # Replace all `self.` with `engine.`
    ...


def check_exits(engine: 'SimulationEngine'):
    """
    Momentum exit cascade: ES1→ES2→ES3→ES4→ES5→ES6→ES7.
    Calls engine._execute_sell() / engine._execute_partial_sell() directly.
    """
    # Full copy of _check_exits_momentum() logic
    # Replace all `self.` with `engine.`
    ...
```

**Key pattern:** Each strategy module receives the engine instance as parameter, accessing its state directly. This avoids creating a complex context object while keeping the exact same behavior.

- [ ] **Step 3: Update engine.py dispatcher**

Replace the inline methods with imports:
```python
from simulation.strategies import momentum as strat_momentum

def _scan_entries_momentum(self):
    strat_momentum.scan_entries(self)

def _check_exits_momentum(self):
    strat_momentum.check_exits(self)
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/daniel/dev/atm-dev && python3 run_tests.py`
Expected: 58/58 PASS

- [ ] **Step 5: Commit**

```bash
git add ats/simulation/strategies/ ats/simulation/engine.py
git commit -m "refactor: extract momentum strategy to simulation/strategies/"
```

---

### Task 9: Extract SMC strategy

**Files:**
- Create: `ats/simulation/strategies/smc.py`
- Modify: `ats/simulation/engine.py`

- [ ] **Step 1: Create smc.py**

Extract these methods (lines 3065-3430):
- `_scan_entries_smc()` → `scan_entries(engine)`
- `_calculate_indicators_smc()` → `calculate_indicators_smc(engine, df)`
- `_score_smc_bias()` → `score_smc_bias(df)`
- `_score_volatility()` → `score_volatility(df)`
- `_score_obv_signal()` → `score_obv_signal(df)`
- `_score_momentum_signal()` → `score_momentum_signal(df)`
- `_check_exits_smc()` → `check_exits(engine)`

- [ ] **Step 2: Update engine.py with delegation stubs**

- [ ] **Step 3: Run tests and commit**

```bash
git commit -m "refactor: extract SMC strategy to simulation/strategies/smc.py"
```

---

### Task 10: Extract Mean Reversion strategy

**Files:**
- Create: `ats/simulation/strategies/mean_reversion.py`
- Modify: `ats/simulation/engine.py`

- [ ] **Step 1: Create mean_reversion.py**

Extract lines 3432-3892 (ALL methods — scan AND exit):
- `_calculate_indicators_mean_reversion()` (3432-3469) → `calculate_indicators(engine, df)`
- `_score_mr_signal()` (3470-3502) → `score_mr_signal(df)`
- `_score_mr_volatility()` (3503-3543) → `score_mr_volatility(df)`
- `_score_mr_confirmation()` (3544-3583) → `score_mr_confirmation(df)`
- `_scan_entries_mean_reversion()` (3584-3712) → `scan_entries(engine)`
- `_check_exits_mean_reversion()` (3714-3892) → `check_exits(engine)`

- [ ] **Step 2: Update engine.py with delegation stubs**

- [ ] **Step 3: Run tests and commit**

```bash
git commit -m "refactor: extract mean reversion strategy to simulation/strategies/"
```

---

### Task 11: Extract Breakout-Retest strategy

**Files:**
- Create: `ats/simulation/strategies/breakout_retest.py`
- Modify: `ats/simulation/engine.py`

- [ ] **Step 1: Create breakout_retest.py**

Extract lines 3892-4549 — the largest strategy module (ALL methods — scan AND exit):
- `_calculate_indicators_breakout_retest()` (3892-3910) → `calculate_indicators(engine, df)`
- `_score_brt_structure()` (3911-3937) → `score_structure(df)`
- `_score_brt_volatility()` (3938-3967) → `score_volatility(df)`
- `_score_brt_obv()` (3968-3987) → `score_obv(df)`
- `_score_brt_momentum()` (3988-4023) → `score_momentum(df)`
- `_check_brt_six_conditions()` (4024-4075) → `check_six_conditions(df)`
- `_apply_brt_fakeout_filters()` (4076-4109) → `apply_fakeout_filters(df)`
- `_capture_brt_retest_zones()` (4110-4172) → `capture_retest_zones(df, price, atr)`
- `_scan_entries_breakout_retest()` (4173-4373) → `scan_entries(engine)`
- `_score_brt_retest_zone()` (4374-4406) → `score_retest_zone(df, state)`
- `_check_exits_breakout_retest()` (4407-4549) → `check_exits(engine)`

- [ ] **Step 2: Update engine.py with delegation stubs**

- [ ] **Step 3: Run tests and commit**

```bash
git commit -m "refactor: extract breakout-retest strategy to simulation/strategies/"
```

---

### Task 12: Extract Arbitrage strategy

**Files:**
- Create: `ats/simulation/strategies/arbitrage.py`
- Modify: `ats/simulation/engine.py`

- [ ] **Step 1: Create arbitrage.py**

Extract lines 4550-5563 — the most complex strategy (ALL methods — scan AND exit):
- `_discover_pairs()` (4550-4683) → `discover_pairs(engine)`
- `_load_fixed_pairs()` (4684-4775) → `load_fixed_pairs(engine)`
- `_check_basis_gate()` (4776-4902) → `check_basis_gate(engine)`
- `_score_arb_correlation()` (4903-4939) → `score_correlation(pair)`
- `_score_arb_spread()` (4940-4981) → `score_spread(pair)`
- `_score_arb_volume()` (4982-5020) → `score_volume(pair)`
- `_calculate_arb_ev()` (5021-5080) → `calculate_ev(pair)`
- `_size_arb_pair()` (5081-5110) → `size_pair(price_a, price_b, score)` — stays in arb module (not sizing.py) because it's pair-specific dollar-neutral logic
- `_scan_entries_arbitrage()` (5111-5356) → `scan_entries(engine)`
- `_check_exits_arbitrage()` (5357-5563) → `check_exits(engine)`

**Note:** This module calls `engine._execute_buy_arb()` and `engine._execute_sell_short()` which remain on the engine.

- [ ] **Step 2: Update engine.py with delegation stubs**

- [ ] **Step 3: Run tests and commit**

```bash
git commit -m "refactor: extract arbitrage strategy to simulation/strategies/"
```

---

### Task 13: Extract Defensive + Volatility strategies

**Files:**
- Create: `ats/simulation/strategies/defensive.py`
- Create: `ats/simulation/strategies/volatility.py`
- Modify: `ats/simulation/engine.py`

- [ ] **Step 1: Create defensive.py**

Extract lines 2514-2654:
- `_scan_entries_defensive()` → `scan_entries(engine)`
- `_check_exits_defensive()` → `check_exits(engine)`

- [ ] **Step 2: Create volatility.py**

Extract lines 2654-2789:
- `_scan_entries_volatility()` → `scan_entries(engine)`
- `_check_exits_volatility()` → `check_exits(engine)`

- [ ] **Step 3: Update engine.py dispatchers**

- [ ] **Step 4: Run tests and commit**

```bash
git commit -m "refactor: extract defensive + volatility strategies to simulation/strategies/"
```

---

## Chunk 4: Phase D — Cleanup and Verification

### Task 14: Clean up engine.py dispatcher methods

**Files:**
- Modify: `ats/simulation/engine.py`

- [ ] **Step 1: Replace all inline strategy delegation stubs with a strategy registry**

```python
# At top of engine.py
from simulation.strategies import (
    momentum as strat_momentum,
    smc as strat_smc,
    mean_reversion as strat_mr,
    breakout_retest as strat_brt,
    arbitrage as strat_arb,
    defensive as strat_def,
    volatility as strat_vol,
)

# Strategy dispatch registry
_STRATEGY_MODULES = {
    "momentum": strat_momentum,
    "smc": strat_smc,
    "mean_reversion": strat_mr,
    "breakout_retest": strat_brt,
    "arbitrage": strat_arb,
    "defensive": strat_def,
    "volatility": strat_vol,
}
```

- [ ] **Step 2: Simplify _scan_entries() and _check_exits() dispatchers**

```python
def _scan_entries(self):
    if self.strategy_mode == "multi" or self.strategy_mode in REGIME_STRATEGY_MODES:
        self._scan_entries_multi()
    else:
        module = _STRATEGY_MODULES.get(self.strategy_mode)
        if module:
            module.scan_entries(self)

def _check_exits(self):
    if self.strategy_mode == "multi" or self.strategy_mode in REGIME_STRATEGY_MODES:
        self._check_exits_multi()
    else:
        module = _STRATEGY_MODULES.get(self.strategy_mode)
        if module:
            module.check_exits(self)
```

- [ ] **Step 3: Update _scan_entries_multi() to use registry**

Replace hardcoded strategy method calls with registry dispatch:
```python
def _scan_entries_multi(self):
    for strategy_name in active_strategies:
        module = _STRATEGY_MODULES.get(strategy_name)
        if module:
            self._exit_tag_filter = strategy_name
            module.scan_entries(self)
```

- [ ] **Step 4: Fix strategy_mode mutation hack in BOTH multi methods**

Replace the `self.strategy_mode` swapping in `_scan_entries_multi()` AND `_check_exits_multi()` with direct module dispatch:

```python
def _scan_entries_multi(self):
    # ... (existing collect_mode / signal aggregation logic stays)
    for strategy_name in active_strategies:
        module = _STRATEGY_MODULES.get(strategy_name)
        if module and self._strategy_allocator.is_active(strategy_name):
            self._exit_tag_filter = strategy_name
            module.scan_entries(self)
    self._exit_tag_filter = None
    # ... (existing signal sorting / dedup logic stays)

def _check_exits_multi(self):
    strategy_tags = set(pos.strategy_tag for pos in self.positions.values() if pos.status == "ACTIVE")
    for tag in strategy_tags:
        module = _STRATEGY_MODULES.get(tag)
        if module:
            self._exit_tag_filter = tag
            module.check_exits(self)
    self._exit_tag_filter = None
```

- [ ] **Step 5: Run tests**

Run: `cd /Users/daniel/dev/atm-dev && python3 run_tests.py`
Expected: 58/58 PASS

- [ ] **Step 6: Commit**

```bash
git add ats/simulation/engine.py
git commit -m "refactor: simplify engine dispatchers with strategy registry"
```

---

### Task 15: Verify engine.py line count and backtest parity

**Files:**
- No file changes — verification only

- [ ] **Step 1: Count engine.py lines**

Run: `wc -l ats/simulation/engine.py`
Expected: ~1800-2200 lines (down from 6689)

- [ ] **Step 2: Verify all simulation/ modules exist**

```bash
ls -la ats/simulation/
# Expected: __init__.py, allocator.py, constants.py, controller.py, engine.py,
#           event_bus.py, indicators.py, models.py, portfolio_allocator.py,
#           regime.py, risk_gates.py, sizing.py, strategies/, universe.py, watchlists.py
ls -la ats/simulation/strategies/
# Expected: __init__.py, arbitrage.py, breakout_retest.py, defensive.py,
#           mean_reversion.py, momentum.py, smc.py, volatility.py
```

- [ ] **Step 3: Run full test suite**

Run: `cd /Users/daniel/dev/atm-dev && python3 run_tests.py`
Expected: 58/58 PASS

- [ ] **Step 4: Run a quick backtest to verify identical results**

```bash
cd /Users/daniel/dev/atm-dev && python3 -c "
from ats.backtest.historical_engine import HistoricalBacktester
bt = HistoricalBacktester(market='sp500', strategy_mode='multi')
# Just verify it initializes without error
print('Backtest engine initialized OK')
print(f'Engine type: {type(bt.engine).__name__}')
print(f'Engine line count verification: strategy modules loaded')
"
```

- [ ] **Step 5: Final commit**

```bash
git add -A ats/simulation/
git commit -m "refactor: complete engine.py decomposition — 6689→~1800 lines

Extracted modules:
- constants.py: regime params, strategy weights, ETF universes
- models.py: 8 Pydantic serialization models
- allocator.py: StrategyAllocator (capital allocation)
- regime.py: market/stock regime classification
- risk_gates.py: RG1-RG5 risk checks
- indicators.py: technical indicator calculation
- sizing.py: ATR-based position sizing
- strategies/: 7 strategy modules (momentum, smc, mr, brt, arb, def, vol)

No behavioral changes. All 58 tests pass."
```

---

## Important Notes for Implementation

### Backtest Compatibility
`HistoricalBacktester` accesses these engine attributes directly:
- `engine._ohlcv_cache`, `engine._current_prices`, `engine._market_regime`
- `engine._replay_mode`, `engine.positions`, `engine.closed_trades`
- `engine.update_vix()`, `engine.update_index_data()`, `engine.run_backtest_day()`

All must remain accessible on `SimulationEngine`. Delegation methods are fine; removing them is not.

### Strategy Module Pattern
Each `strategies/*.py` module receives the engine instance as its first parameter. This avoids creating abstraction layers while enabling extraction. The engine's public attributes are the module's API contract:
- `engine._ohlcv_cache`, `engine._current_prices`, `engine._stock_names`
- `engine.positions`, `engine.signals`, `engine.orders`
- `engine._market_regime`, `engine._strategy_allocator`
- `engine._execute_buy()`, `engine._execute_sell()`, `engine._execute_partial_sell()`
- `engine._phase_stats`, `engine._add_risk_event()`

### Constants Import Chain
```
simulation/constants.py  (no dependencies within simulation/)
    ↑
simulation/allocator.py  (imports constants)
simulation/regime.py     (imports constants, allocator._compute_adx)
simulation/risk_gates.py (imports constants)
simulation/sizing.py     (imports constants)
simulation/indicators.py (no simulation dependencies — pure functions)
simulation/strategies/*  (import from TYPE_CHECKING only, receive engine at runtime)
    ↑
simulation/engine.py     (imports all above)
```
No circular dependencies.
