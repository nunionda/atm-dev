"""
선물 전략 파라미터 최적화 — Grid Search with Min/Max Interpolation.

3가지 축의 파라미터를 보간하여 최적 조합을 탐색:
  1. ATR Breakout Multiplier: [min, max] → 일일봉 적합도
  2. Fakeout Filter: wick_ratio [min, max], vol_ratio [min, max]
  3. Z-Score Trend Continuation: cont_max_pct [min, max]

결과: CSV + JSON 저장, 최적 파라미터 리포트.
"""

from __future__ import annotations

import copy
import csv
import itertools
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from typing import List, Tuple

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from data.config_manager import ConfigManager
from backtest.futures_backtester import FuturesBacktester


@dataclass
class ParamSet:
    """하나의 파라미터 조합."""
    atr_breakout_mult: float
    fakeout_max_wick_ratio: float
    fakeout_min_vol_ratio: float
    zscore_trend_cont_max_pct: float
    zscore_trend_cont_min_pct: float


def interpolate(min_val: float, max_val: float, steps: int) -> List[float]:
    """min~max 사이를 steps 개로 선형 보간."""
    if steps == 1:
        return [min_val]
    return [round(min_val + (max_val - min_val) * i / (steps - 1), 3) for i in range(steps)]


def generate_param_grid() -> List[ParamSet]:
    """파라미터 그리드 생성 (min/max 보간)."""
    # ── 파라미터 범위 정의 ──
    # ATR Breakout Mult: 기존 0.75 → 일일봉 적합 0.15~0.5
    atr_vals = interpolate(0.15, 0.50, 4)  # [0.15, 0.267, 0.383, 0.5]

    # Fakeout Wick Ratio: 기존 1.5 → 일일봉 완화 1.5~3.5
    wick_vals = interpolate(1.5, 3.5, 3)  # [1.5, 2.5, 3.5]

    # Fakeout Min Volume Ratio: 기존 0.8 → 완화 0.4~0.8
    vol_vals = interpolate(0.4, 0.8, 3)  # [0.4, 0.6, 0.8]

    # Z-Score Trend Continuation Max %: 0.3~0.7
    zcont_vals = interpolate(0.3, 0.7, 3)  # [0.3, 0.5, 0.7]

    # Z-Score Trend Continuation Min % (고정 비율: max의 1/3)
    grid = []
    for atr, wick, vol, zcont in itertools.product(atr_vals, wick_vals, vol_vals, zcont_vals):
        grid.append(ParamSet(
            atr_breakout_mult=atr,
            fakeout_max_wick_ratio=wick,
            fakeout_min_vol_ratio=vol,
            zscore_trend_cont_max_pct=zcont,
            zscore_trend_cont_min_pct=round(zcont / 3, 3),
        ))
    return grid


def run_single_backtest(
    base_config,
    params: ParamSet,
    ticker: str,
    start_date: str,
    end_date: str,
    initial_equity: float,
) -> dict:
    """단일 파라미터 조합으로 백테스트 실행."""
    config = copy.deepcopy(base_config)

    # 파라미터 적용
    config.sp500_futures.atr_breakout_mult = params.atr_breakout_mult
    config.sp500_futures.fakeout_max_wick_ratio = params.fakeout_max_wick_ratio
    config.sp500_futures.fakeout_min_vol_ratio = params.fakeout_min_vol_ratio
    config.sp500_futures.zscore_trend_cont_max_pct = params.zscore_trend_cont_max_pct
    config.sp500_futures.zscore_trend_cont_min_pct = params.zscore_trend_cont_min_pct

    bt = FuturesBacktester(
        config=config,
        ticker=ticker,
        start_date=start_date,
        end_date=end_date,
        initial_equity=initial_equity,
    )
    return bt.run()


def main():
    ticker = "ES=F"
    start_date = "20250315"
    end_date = "20260315"
    initial_equity = 100000.0

    print("=" * 70)
    print("  ES=F Futures Strategy — Parameter Sweep Optimization")
    print(f"  Period: {start_date} ~ {end_date} | Equity: ${initial_equity:,.0f}")
    print("=" * 70)

    base_config = ConfigManager().load()
    grid = generate_param_grid()
    total = len(grid)
    print(f"\nGrid size: {total} combinations")
    print(f"Parameters: ATR_mult × Wick_ratio × Vol_ratio × ZCont_max")
    print()

    results = []
    start_time = time.time()

    for i, params in enumerate(grid):
        t0 = time.time()
        result = run_single_backtest(base_config, params, ticker, start_date, end_date, initial_equity)
        elapsed = time.time() - t0

        m = result["metrics"]
        row = {
            "idx": i + 1,
            "atr_mult": params.atr_breakout_mult,
            "wick_ratio": params.fakeout_max_wick_ratio,
            "vol_ratio": params.fakeout_min_vol_ratio,
            "zcont_max": params.zscore_trend_cont_max_pct,
            "zcont_min": params.zscore_trend_cont_min_pct,
            "total_return_pct": m["total_return_pct"],
            "sharpe": m["sharpe_ratio"],
            "sortino": m["sortino_ratio"],
            "calmar": m["calmar_ratio"],
            "cagr": m["cagr"],
            "max_dd_pct": m["max_drawdown_pct"],
            "mdd_duration": m["mdd_duration_days"],
            "total_trades": m["total_trades"],
            "win_rate": m["win_rate"],
            "profit_factor": m["profit_factor"],
            "avg_rr": m["avg_rr"],
            "total_pnl": m["total_pnl"],
            "total_costs": m["total_costs"],
            "long_trades": m["long_trades"],
            "short_trades": m["short_trades"],
            "long_wr": m["long_win_rate"],
            "short_wr": m["short_win_rate"],
            "avg_holding": m["avg_holding_days"],
            "best_trade": m["best_trade_pct"],
            "worst_trade": m["worst_trade_pct"],
            "mc_var95": m["monte_carlo"].get("var_95", 0),
            "mc_median": m["monte_carlo"].get("median_return", 0),
            "elapsed_sec": round(elapsed, 1),
        }
        results.append(row)

        # 진행 상황 (10개마다 또는 마지막)
        if (i + 1) % 10 == 0 or i == total - 1:
            eta = (time.time() - start_time) / (i + 1) * (total - i - 1)
            print(
                f"[{i+1:3d}/{total}] ATR={params.atr_breakout_mult:.2f} "
                f"Wick={params.fakeout_max_wick_ratio:.1f} "
                f"Vol={params.fakeout_min_vol_ratio:.1f} "
                f"ZC={params.zscore_trend_cont_max_pct:.1f} → "
                f"Return={m['total_return_pct']:+.1f}% "
                f"Sharpe={m['sharpe_ratio']:.2f} "
                f"Trades={m['total_trades']} "
                f"WR={m['win_rate']:.0f}% "
                f"({elapsed:.1f}s, ETA {eta:.0f}s)"
            )

    total_time = time.time() - start_time
    print(f"\nTotal time: {total_time:.0f}s ({total_time/60:.1f}min)")

    # ── 결과 저장 ──
    out_dir = os.path.join(os.path.dirname(__file__), "..", "..", "data_store", "backtest_reports")
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # CSV
    csv_path = os.path.join(out_dir, f"param_sweep_{ts}.csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=results[0].keys())
        writer.writeheader()
        writer.writerows(results)
    print(f"\nCSV saved: {csv_path}")

    # JSON (전체)
    json_path = os.path.join(out_dir, f"param_sweep_{ts}.json")
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"JSON saved: {json_path}")

    # ── 분석 ──
    print("\n" + "=" * 70)
    print("  OPTIMIZATION RESULTS")
    print("=" * 70)

    # 트레이드가 있는 결과만 필터
    active = [r for r in results if r["total_trades"] >= 3]
    if not active:
        active = [r for r in results if r["total_trades"] >= 1]
        print("\n⚠ No combinations with 3+ trades. Showing best of 1+ trades.")

    if not active:
        print("\n❌ No combinations produced any trades!")
        return

    # Sharpe 기준 정렬
    by_sharpe = sorted(active, key=lambda x: x["sharpe"], reverse=True)

    # 복합 스코어: Sharpe × 0.4 + Return × 0.3 + (1 - |MDD|/100) × 0.3
    for r in active:
        r["composite_score"] = (
            r["sharpe"] * 0.4
            + r["total_return_pct"] / 100 * 0.3
            + (1 + r["max_dd_pct"] / 100) * 0.3  # MDD는 음수
        )
    by_composite = sorted(active, key=lambda x: x["composite_score"], reverse=True)

    print(f"\n{'='*70}")
    print(f"  TOP 10 BY COMPOSITE SCORE (Sharpe×0.4 + Return×0.3 + Safety×0.3)")
    print(f"{'='*70}")
    print(f"{'#':>3} {'ATR':>5} {'Wick':>5} {'Vol':>5} {'ZC':>5} | {'Return':>8} {'Sharpe':>7} {'MDD':>7} {'Trades':>6} {'WR':>5} {'PF':>6} | {'Score':>6}")
    print("-" * 85)
    for i, r in enumerate(by_composite[:10]):
        print(
            f"{i+1:>3} {r['atr_mult']:>5.2f} {r['wick_ratio']:>5.1f} "
            f"{r['vol_ratio']:>5.1f} {r['zcont_max']:>5.1f} | "
            f"{r['total_return_pct']:>+7.1f}% {r['sharpe']:>7.2f} "
            f"{r['max_dd_pct']:>6.1f}% {r['total_trades']:>6} "
            f"{r['win_rate']:>4.0f}% {r['profit_factor']:>5.2f} | "
            f"{r['composite_score']:>6.3f}"
        )

    print(f"\n{'='*70}")
    print(f"  TOP 10 BY SHARPE RATIO")
    print(f"{'='*70}")
    print(f"{'#':>3} {'ATR':>5} {'Wick':>5} {'Vol':>5} {'ZC':>5} | {'Return':>8} {'Sharpe':>7} {'MDD':>7} {'Trades':>6} {'WR':>5} {'PF':>6}")
    print("-" * 78)
    for i, r in enumerate(by_sharpe[:10]):
        print(
            f"{i+1:>3} {r['atr_mult']:>5.2f} {r['wick_ratio']:>5.1f} "
            f"{r['vol_ratio']:>5.1f} {r['zcont_max']:>5.1f} | "
            f"{r['total_return_pct']:>+7.1f}% {r['sharpe']:>7.2f} "
            f"{r['max_dd_pct']:>6.1f}% {r['total_trades']:>6} "
            f"{r['win_rate']:>4.0f}% {r['profit_factor']:>5.02f}"
        )

    # 최적 조합 상세
    best = by_composite[0]
    print(f"\n{'='*70}")
    print(f"  BEST PARAMETER SET (Composite Score: {best['composite_score']:.3f})")
    print(f"{'='*70}")
    print(f"  atr_breakout_mult:          {best['atr_mult']}")
    print(f"  fakeout_max_wick_ratio:     {best['wick_ratio']}")
    print(f"  fakeout_min_vol_ratio:      {best['vol_ratio']}")
    print(f"  zscore_trend_cont_max_pct:  {best['zcont_max']}")
    print(f"  zscore_trend_cont_min_pct:  {best['zcont_min']}")
    print()
    print(f"  Total Return:  {best['total_return_pct']:+.2f}%")
    print(f"  Sharpe Ratio:  {best['sharpe']:.2f}")
    print(f"  Sortino Ratio: {best['sortino']:.2f}")
    print(f"  Max Drawdown:  {best['max_dd_pct']:.2f}%")
    print(f"  Total Trades:  {best['total_trades']}")
    print(f"  Win Rate:      {best['win_rate']:.1f}%")
    print(f"  Profit Factor: {best['profit_factor']:.2f}")
    print(f"  Avg R:R:       {best['avg_rr']:.2f}")
    print(f"  Long/Short:    {best['long_trades']}/{best['short_trades']}")
    print(f"  Avg Holding:   {best['avg_holding']} days")
    print(f"  MC VaR95:      {best['mc_var95']:.1f}%")

    # 파라미터 민감도 분석
    print(f"\n{'='*70}")
    print(f"  PARAMETER SENSITIVITY (Average Sharpe by parameter value)")
    print(f"{'='*70}")

    for param_name, param_key in [
        ("ATR Breakout Mult", "atr_mult"),
        ("Fakeout Wick Ratio", "wick_ratio"),
        ("Fakeout Vol Ratio", "vol_ratio"),
        ("Z-Score Cont Max", "zcont_max"),
    ]:
        vals = sorted(set(r[param_key] for r in results))
        print(f"\n  {param_name}:")
        for v in vals:
            subset = [r for r in results if r[param_key] == v]
            avg_sharpe = np.mean([r["sharpe"] for r in subset])
            avg_return = np.mean([r["total_return_pct"] for r in subset])
            avg_trades = np.mean([r["total_trades"] for r in subset])
            print(f"    {v:>6.2f} → Sharpe={avg_sharpe:+.2f}  Return={avg_return:+.1f}%  Trades={avg_trades:.0f}")


if __name__ == "__main__":
    main()
