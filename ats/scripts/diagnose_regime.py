#!/usr/bin/env python3
"""multi 레짐 분류 진단 — 기간별 레짐 분포 확인."""
import sys, os
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, "ats"))

from backtest.historical_engine import HistoricalBacktester

bt = HistoricalBacktester(
    market='sp500', scenario='custom',
    start_date='20250316', end_date='20260316',
    strategy_mode='multi', top_n=20,
)

# Monkey-patch to capture regime history
original_run_day = bt.__class__.__mro__[0]  # skip

result = bt.run()
engine = bt.engine

print("\n" + "="*70)
print("  REGIME 진단 (multi, 2025-03 ~ 2026-03)")
print("="*70)

# 1. Market Regime History
print("\n▶ Market Regime (Phase 0, breadth 기반):")
from collections import Counter
regime_hist = engine._phase_stats.get("regime_history", [])
if regime_hist:
    for entry in regime_hist[-20:]:
        print(f"   {entry}")
else:
    print(f"   현재 레짐: {engine._market_regime}")
    print(f"   실제 감지 레짐: {engine._actual_market_regime}")

# 2. Index Trend History
print("\n▶ Index Trend History (지수 추세 기반):")
trend_hist = engine._index_trend_history
if trend_hist:
    for entry in trend_hist:
        ts = entry.get("timestamp", "?")
        fr = entry.get("from_trend", "?")
        to = entry.get("to_trend", "?")
        print(f"   {ts}: {fr} → {to}")
else:
    print("   (변경 없음)")

# 3. Current Index Trend
print("\n▶ 현재 Index Trend 분석:")
idx_trend = engine._index_trend
if idx_trend:
    for k, v in idx_trend.items():
        if k == "signals":
            print(f"   signals:")
            for s in v:
                print(f"     - {s}")
        else:
            print(f"   {k}: {v}")

# 4. Strategy Allocator
print("\n▶ 현재 전략 가중치:")
if engine._strategy_allocator:
    for s, w in sorted(engine._strategy_allocator.weights.items(), key=lambda x: -x[1]):
        print(f"   {s:20s}: {w:.1%}")

# 5. Phase Stats
print("\n▶ 주요 Phase Stats:")
ps = engine._phase_stats
for key in ['index_trend_updates', 'p5_threshold_adjustments', 'p5_conflict_reductions',
            'rg6_spy_blocks', 'es_mdd_guard', 'regime_changes']:
    if key in ps:
        print(f"   {key}: {ps[key]}")

# 6. Regime distribution from trade log
print("\n▶ 트레이드별 진입 레짐 분포:")
regime_counter = Counter()
for pos in engine._closed_positions:
    regime_counter[pos.entry_regime] += 1
for regime, count in regime_counter.most_common():
    print(f"   {regime:15s}: {count}건")
