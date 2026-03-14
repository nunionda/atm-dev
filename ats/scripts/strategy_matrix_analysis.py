#!/usr/bin/env python3
"""
3-Index × 5-Strategy = 15 시뮬레이션 종합 분석 시스템

SP500, NDX, KOSPI 3개 시장에서 momentum, mean_reversion, smc, breakout_retest, multi
5개 전략을 각각 실행하여:

1. 성과 매트릭스 (Sharpe, 수익률, PF, Win Rate, MDD)
2. 모멘텀 판단 정확도 (시그널 강도, 레짐, 추세 강도 vs 결과)
3. 손절/익절 패턴 분석 (Exit Reason 분포, GAP DOWN, 보유기간별)
4. 교차 전략 비교 (시장별 최적 전략, 레짐별 최적 전략)
5. 종합 개선 제안

Usage:
    python3 ats/scripts/strategy_matrix_analysis.py
    python3 ats/scripts/strategy_matrix_analysis.py --markets sp500 ndx --strategies momentum multi
"""

import os
import sys
import json
import argparse
import math
from collections import defaultdict, Counter
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple

# 프로젝트 루트 설정
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(project_root, "ats"))

from backtest.historical_engine import HistoricalBacktester

# ─────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────
ALL_MARKETS = ["sp500", "ndx", "kospi"]
ALL_STRATEGIES = ["momentum", "mean_reversion", "smc", "breakout_retest", "multi"]
START_DATE = "20240101"
END_DATE = "20260228"

SIGNAL_STRENGTH_BINS = [
    (0, 40, "Low(0-40)"),
    (41, 60, "Mid(41-60)"),
    (61, 80, "High(61-80)"),
    (81, 100, "Elite(81-100)"),
]

HOLDING_DAY_BINS = [
    (1, 3, "1-3d"),
    (4, 7, "4-7d"),
    (8, 14, "8-14d"),
    (15, 999, "15d+"),
]


# ─────────────────────────────────────────────
# Data Structures
# ─────────────────────────────────────────────
@dataclass
class CellResult:
    """단일 (시장, 전략) 셀 결과."""
    market: str
    strategy: str
    total_return: float = 0.0
    cagr: float = 0.0
    sharpe: float = 0.0
    sortino: float = 0.0
    max_drawdown: float = 0.0
    profit_factor: float = 0.0
    win_rate: float = 0.0
    total_trades: int = 0
    avg_pnl_pct: float = 0.0
    avg_holding_days: float = 0.0
    best_trade_pct: float = 0.0
    worst_trade_pct: float = 0.0
    avg_win_pct: float = 0.0
    avg_loss_pct: float = 0.0
    final_value: float = 0.0

    # Phase stats
    total_scans: int = 0
    phase1_rejects: int = 0
    phase2_rejects: int = 0
    phase3_no_primary: int = 0
    phase3_no_confirm: int = 0
    phase4_risk_blocks: int = 0
    entries_executed: int = 0

    # Exit counts
    exit_counts: Dict[str, int] = field(default_factory=dict)

    # Trades with metadata
    trades: List[Dict[str, Any]] = field(default_factory=list)

    # Equity curve (dates + values)
    equity_dates: List[str] = field(default_factory=list)
    equity_values: List[float] = field(default_factory=list)

    # Regime data
    time_in_bull: float = 0.0
    time_in_neutral: float = 0.0
    time_in_bear: float = 0.0

    error: str = ""


# ─────────────────────────────────────────────
# Section 1: Grid Runner
# ─────────────────────────────────────────────
def run_single_backtest(market: str, strategy: str) -> CellResult:
    """단일 (시장, 전략) 조합 백테스트 실행."""
    cell = CellResult(market=market, strategy=strategy)
    try:
        bt = HistoricalBacktester.from_optimal(
            market=market,
            start_date=START_DATE,
            end_date=END_DATE,
            strategy_mode=strategy,
        )
        result = bt.run()
        engine = bt.engine

        # 기본 메트릭
        cell.total_return = result.total_return
        cell.cagr = result.cagr
        cell.sharpe = result.sharpe_ratio
        cell.sortino = result.sortino_ratio
        cell.max_drawdown = result.max_drawdown
        cell.profit_factor = result.profit_factor
        cell.win_rate = result.win_rate
        cell.total_trades = result.total_trades
        cell.avg_pnl_pct = result.avg_pnl_pct
        cell.avg_holding_days = result.avg_holding_days
        cell.best_trade_pct = result.best_trade_pct
        cell.worst_trade_pct = result.worst_trade_pct
        cell.avg_win_pct = result.avg_win_pct
        cell.avg_loss_pct = result.avg_loss_pct
        cell.final_value = result.final_value

        # Phase stats
        ps = result.phase_stats
        cell.total_scans = ps.total_scans
        cell.phase1_rejects = ps.phase1_trend_rejects
        cell.phase2_rejects = ps.phase2_late_rejects
        cell.phase3_no_primary = ps.phase3_no_primary
        cell.phase3_no_confirm = ps.phase3_no_confirm
        cell.phase4_risk_blocks = ps.phase4_risk_blocks
        cell.entries_executed = ps.entries_executed

        # Exit counts
        cell.exit_counts = {
            "ES1": ps.es1_stop_loss,
            "ES2": ps.es2_take_profit,
            "ES3": ps.es3_trailing_stop,
            "ES4": ps.es4_dead_cross,
            "ES5": ps.es5_max_holding,
            "ES6": ps.es6_time_decay,
            "ES7": ps.es7_rebalance_exit,
            "SMC_SL": ps.es_smc_sl,
            "SMC_TP": ps.es_smc_tp,
            "CHoCH": ps.es_choch_exit,
        }

        # Trades with metadata
        for t in engine.closed_trades:
            cell.trades.append({
                "stock_code": t.stock_code,
                "stock_name": t.stock_name,
                "entry_date": t.entry_date,
                "exit_date": t.exit_date,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "quantity": t.quantity,
                "pnl": t.pnl,
                "pnl_pct": t.pnl_pct,
                "exit_reason": t.exit_reason,
                "holding_days": t.holding_days,
                "strategy_tag": getattr(t, "strategy_tag", ""),
                "entry_signal_strength": getattr(t, "entry_signal_strength", 0),
                "entry_regime": getattr(t, "entry_regime", ""),
                "entry_trend_strength": getattr(t, "entry_trend_strength", ""),
            })

        # Equity curve (sampled to reduce size)
        for eq in result.equity_curve:
            cell.equity_dates.append(eq.date)
            cell.equity_values.append(eq.total_value)

        # Regime
        cell.time_in_bull = result.time_in_bull_pct
        cell.time_in_neutral = result.time_in_neutral_pct
        cell.time_in_bear = result.time_in_bear_pct

    except Exception as e:
        cell.error = str(e)
        print(f"  ❌ ERROR {market}/{strategy}: {e}")

    return cell


def run_grid(markets: List[str], strategies: List[str]) -> Dict[str, CellResult]:
    """전체 그리드 실행."""
    results = {}
    total = len(markets) * len(strategies)
    count = 0
    for market in markets:
        for strategy in strategies:
            count += 1
            key = f"{market}/{strategy}"
            print(f"\n[{count}/{total}] Running {key} ...")
            cell = run_single_backtest(market, strategy)
            results[key] = cell
            if not cell.error:
                print(f"  ✅ Return: {cell.total_return*100:+.1f}%, "
                      f"Sharpe: {cell.sharpe:.2f}, "
                      f"Trades: {cell.total_trades}, "
                      f"WR: {cell.win_rate*100:.0f}%")
    return results


# ─────────────────────────────────────────────
# Section 2: Performance Matrix
# ─────────────────────────────────────────────
def print_performance_matrix(results: Dict[str, CellResult], markets: List[str], strategies: List[str]):
    """5개 지표별 3×5 테이블 출력."""
    metrics_info = [
        ("Sharpe Ratio", lambda c: f"{c.sharpe:>7.2f}"),
        ("Total Return", lambda c: f"{c.total_return*100:>+7.1f}%"),
        ("Profit Factor", lambda c: f"{c.profit_factor:>7.2f}"),
        ("Win Rate", lambda c: f"{c.win_rate*100:>6.1f}%"),
        ("Max Drawdown", lambda c: f"{c.max_drawdown*100:>+7.2f}%"),
    ]

    print("\n" + "=" * 80)
    print("  SECTION 1: PERFORMANCE MATRIX")
    print("=" * 80)

    for metric_name, formatter in metrics_info:
        print(f"\n  ── {metric_name} ──")
        # Header
        header = f"  {'Market':<8}"
        for s in strategies:
            label = s[:10]
            header += f" | {label:>12}"
        print(header)
        print("  " + "-" * (8 + len(strategies) * 15))
        # Rows
        for m in markets:
            row = f"  {m.upper():<8}"
            for s in strategies:
                key = f"{m}/{s}"
                cell = results.get(key)
                if cell and not cell.error:
                    row += f" | {formatter(cell):>12}"
                else:
                    row += f" | {'ERR':>12}"
            print(row)


# ─────────────────────────────────────────────
# Section 3: Momentum Judgment Accuracy
# ─────────────────────────────────────────────
def analyze_momentum_accuracy(results: Dict[str, CellResult], markets: List[str], strategies: List[str]):
    """모멘텀 판단 정확도 분석."""
    print("\n" + "=" * 80)
    print("  SECTION 2: MOMENTUM JUDGMENT ACCURACY")
    print("=" * 80)

    # ── 2A: Phase Funnel ──
    print("\n  ── 2A. Phase Funnel (Entry Conversion Rate) ──")
    print(f"  {'Market/Strat':<20} {'Scans':>8} {'P1Rej':>8} {'P2Rej':>8} {'P3NoPri':>8} "
          f"{'P4Risk':>8} {'Entries':>8} {'Conv%':>8}")
    print("  " + "-" * 100)

    for m in markets:
        for s in strategies:
            key = f"{m}/{s}"
            cell = results.get(key)
            if not cell or cell.error or cell.total_scans == 0:
                continue
            conv = cell.entries_executed / cell.total_scans * 100 if cell.total_scans > 0 else 0
            print(f"  {key:<20} {cell.total_scans:>8} {cell.phase1_rejects:>8} "
                  f"{cell.phase2_rejects:>8} {cell.phase3_no_primary:>8} "
                  f"{cell.phase4_risk_blocks:>8} {cell.entries_executed:>8} {conv:>7.1f}%")

    # ── 2B: Signal Strength vs Outcome ──
    print("\n  ── 2B. Signal Strength vs Outcome ──")
    all_trades = []
    for key, cell in results.items():
        if cell.error:
            continue
        for t in cell.trades:
            t["_cell_key"] = key
            all_trades.append(t)

    if all_trades:
        print(f"  {'Strength Bin':<16} {'Count':>8} {'WinRate':>8} {'AvgPnL%':>10} {'AvgWin%':>10} {'AvgLoss%':>10}")
        print("  " + "-" * 72)

        for lo, hi, label in SIGNAL_STRENGTH_BINS:
            bin_trades = [t for t in all_trades if lo <= t["entry_signal_strength"] <= hi]
            if not bin_trades:
                print(f"  {label:<16} {0:>8} {'N/A':>8} {'N/A':>10} {'N/A':>10} {'N/A':>10}")
                continue
            wins = [t for t in bin_trades if t["pnl"] > 0]
            losses = [t for t in bin_trades if t["pnl"] <= 0]
            wr = len(wins) / len(bin_trades) * 100 if bin_trades else 0
            avg_pnl = sum(t["pnl_pct"] for t in bin_trades) / len(bin_trades)
            avg_win = sum(t["pnl_pct"] for t in wins) / len(wins) if wins else 0
            avg_loss = sum(t["pnl_pct"] for t in losses) / len(losses) if losses else 0
            print(f"  {label:<16} {len(bin_trades):>8} {wr:>7.1f}% {avg_pnl:>+9.2f}% "
                  f"{avg_win:>+9.2f}% {avg_loss:>+9.2f}%")

    # ── 2C: Regime Accuracy ──
    print("\n  ── 2C. Entry Regime vs Outcome ──")
    if all_trades:
        print(f"  {'Regime':<14} {'Count':>8} {'WinRate':>8} {'AvgPnL%':>10} {'AvgWin%':>10} {'AvgLoss%':>10}")
        print("  " + "-" * 68)

        regime_groups = defaultdict(list)
        for t in all_trades:
            regime = t.get("entry_regime", "UNKNOWN") or "UNKNOWN"
            regime_groups[regime].append(t)

        for regime in ["BULL", "NEUTRAL", "RANGE_BOUND", "BEAR", "UNKNOWN"]:
            trades = regime_groups.get(regime, [])
            if not trades:
                continue
            wins = [t for t in trades if t["pnl"] > 0]
            losses = [t for t in trades if t["pnl"] <= 0]
            wr = len(wins) / len(trades) * 100
            avg_pnl = sum(t["pnl_pct"] for t in trades) / len(trades)
            avg_win = sum(t["pnl_pct"] for t in wins) / len(wins) if wins else 0
            avg_loss = sum(t["pnl_pct"] for t in losses) / len(losses) if losses else 0
            print(f"  {regime:<14} {len(trades):>8} {wr:>7.1f}% {avg_pnl:>+9.2f}% "
                  f"{avg_win:>+9.2f}% {avg_loss:>+9.2f}%")

    # ── 2D: Trend Strength Verification ──
    print("\n  ── 2D. Trend Strength vs Outcome ──")
    if all_trades:
        print(f"  {'TrendStr':<14} {'Count':>8} {'WinRate':>8} {'AvgPnL%':>10} {'AvgWin%':>10} {'AvgLoss%':>10}")
        print("  " + "-" * 68)

        trend_groups = defaultdict(list)
        for t in all_trades:
            ts = t.get("entry_trend_strength", "UNKNOWN") or "UNKNOWN"
            trend_groups[ts].append(t)

        for ts_label in ["STRONG", "MODERATE", "WEAK", "UNKNOWN"]:
            trades = trend_groups.get(ts_label, [])
            if not trades:
                continue
            wins = [t for t in trades if t["pnl"] > 0]
            losses = [t for t in trades if t["pnl"] <= 0]
            wr = len(wins) / len(trades) * 100
            avg_pnl = sum(t["pnl_pct"] for t in trades) / len(trades)
            avg_win = sum(t["pnl_pct"] for t in wins) / len(wins) if wins else 0
            avg_loss = sum(t["pnl_pct"] for t in losses) / len(losses) if losses else 0
            print(f"  {ts_label:<14} {len(trades):>8} {wr:>7.1f}% {avg_pnl:>+9.2f}% "
                  f"{avg_win:>+9.2f}% {avg_loss:>+9.2f}%")


# ─────────────────────────────────────────────
# Section 4: Stop-Loss / Take-Profit Analysis
# ─────────────────────────────────────────────
def analyze_exits(results: Dict[str, CellResult], markets: List[str], strategies: List[str]):
    """손절/익절 패턴 분석."""
    print("\n" + "=" * 80)
    print("  SECTION 3: STOP-LOSS / TAKE-PROFIT PATTERN ANALYSIS")
    print("=" * 80)

    # ── 3A: Exit Reason Distribution ──
    print("\n  ── 3A. Exit Reason Distribution ──")
    exit_labels = ["ES1", "ES2", "ES3", "ES4", "ES5", "ES6", "ES7", "SMC_SL", "SMC_TP", "CHoCH"]
    # Header
    header = f"  {'Market/Strat':<20}"
    for el in exit_labels:
        header += f" {el:>6}"
    header += f" {'Total':>6}"
    print(header)
    print("  " + "-" * (20 + len(exit_labels) * 7 + 8))

    for m in markets:
        for s in strategies:
            key = f"{m}/{s}"
            cell = results.get(key)
            if not cell or cell.error:
                continue
            row = f"  {key:<20}"
            total = 0
            for el in exit_labels:
                cnt = cell.exit_counts.get(el, 0)
                total += cnt
                row += f" {cnt:>6}"
            row += f" {total:>6}"
            print(row)

    # ── 3B: Exit Type Efficiency ──
    print("\n  ── 3B. Exit Type Efficiency ──")
    all_trades = []
    for key, cell in results.items():
        if cell.error:
            continue
        all_trades.extend(cell.trades)

    if all_trades:
        exit_groups = defaultdict(list)
        for t in all_trades:
            reason = t["exit_reason"]
            # Normalize exit reason to category
            if "ES1" in reason or "손절" in reason:
                cat = "STOP_LOSS"
            elif "ES2" in reason or "익절" in reason:
                cat = "TAKE_PROFIT"
            elif "ES3" in reason or "트레일링" in reason or "trailing" in reason.lower():
                cat = "TRAILING"
            elif "ES4" in reason or "데드크로스" in reason:
                cat = "DEAD_CROSS"
            elif "ES5" in reason or "보유기간" in reason or "최대 보유" in reason:
                cat = "MAX_HOLD"
            elif "ES7" in reason or "리밸런스" in reason:
                cat = "REBALANCE"
            elif "SMC" in reason or "ATR" in reason:
                if "TP" in reason or "익절" in reason:
                    cat = "SMC_TP"
                else:
                    cat = "SMC_SL"
            elif "CHoCH" in reason:
                cat = "CHoCH"
            elif "MR" in reason or "MA" in reason or "mean" in reason.lower():
                cat = "MR_TP"
            else:
                cat = "OTHER"
            exit_groups[cat].append(t)

        print(f"  {'ExitType':<14} {'Count':>6} {'WinRate':>8} {'AvgPnL%':>10} {'Expect%':>10}")
        print("  " + "-" * 56)

        for cat in sorted(exit_groups.keys()):
            trades = exit_groups[cat]
            wins = [t for t in trades if t["pnl"] > 0]
            losses = [t for t in trades if t["pnl"] <= 0]
            wr = len(wins) / len(trades) * 100 if trades else 0
            avg_pnl = sum(t["pnl_pct"] for t in trades) / len(trades)
            # Expectancy
            avg_win = sum(t["pnl_pct"] for t in wins) / len(wins) if wins else 0
            avg_loss = sum(t["pnl_pct"] for t in losses) / len(losses) if losses else 0
            expectancy = (wr / 100) * avg_win + (1 - wr / 100) * avg_loss
            print(f"  {cat:<14} {len(trades):>6} {wr:>7.1f}% {avg_pnl:>+9.2f}% {expectancy:>+9.2f}%")

    # ── 3C: GAP DOWN Analysis ──
    print("\n  ── 3C. GAP DOWN Analysis (PnL < -5%) ──")
    gap_trades = [t for t in all_trades if t["pnl_pct"] < -5.0]
    if gap_trades:
        print(f"  Total GAP DOWN trades: {len(gap_trades)} / {len(all_trades)} "
              f"({len(gap_trades)/len(all_trades)*100:.1f}%)")
        print(f"  {'Code':<10} {'Entry':>10} {'Exit':>10} {'PnL%':>8} {'Hold':>5} {'Exit Reason':<20} {'Regime':<12}")
        print("  " + "-" * 85)
        for t in sorted(gap_trades, key=lambda x: x["pnl_pct"])[:20]:
            print(f"  {t['stock_code']:<10} {t['entry_price']:>10,.0f} {t['exit_price']:>10,.0f} "
                  f"{t['pnl_pct']:>+7.2f}% {t['holding_days']:>5d} "
                  f"{t['exit_reason'][:20]:<20} {t.get('entry_regime',''):<12}")
    else:
        print("  No trades with PnL < -5%")

    # ── 3D: TP Capture Rate ──
    print("\n  ── 3D. Take-Profit Capture Rate ──")
    if all_trades:
        wins = [t for t in all_trades if t["pnl"] > 0]
        if wins:
            pnls = [t["pnl_pct"] for t in wins]
            pnls_sorted = sorted(pnls)
            median = pnls_sorted[len(pnls_sorted) // 2]
            p90 = pnls_sorted[int(len(pnls_sorted) * 0.9)]
            big_wins = [p for p in pnls if p >= 10.0]
            print(f"  Winning trades: {len(wins)}")
            print(f"  Average win:    {sum(pnls)/len(pnls):+.2f}%")
            print(f"  Median win:     {median:+.2f}%")
            print(f"  P90 win:        {p90:+.2f}%")
            print(f"  Big wins (>10%): {len(big_wins)} ({len(big_wins)/len(wins)*100:.1f}%)")

    # ── 3E: Holding Period vs Loss Pattern ──
    print("\n  ── 3E. Holding Period vs Loss Pattern ──")
    if all_trades:
        print(f"  {'Period':<10} {'Count':>8} {'WinRate':>8} {'AvgPnL%':>10} {'LossRate':>10} {'AvgLoss%':>10}")
        print("  " + "-" * 64)

        for lo, hi, label in HOLDING_DAY_BINS:
            bin_trades = [t for t in all_trades if lo <= t["holding_days"] <= hi]
            if not bin_trades:
                continue
            wins = [t for t in bin_trades if t["pnl"] > 0]
            losses = [t for t in bin_trades if t["pnl"] <= 0]
            wr = len(wins) / len(bin_trades) * 100
            avg_pnl = sum(t["pnl_pct"] for t in bin_trades) / len(bin_trades)
            loss_rate = len(losses) / len(bin_trades) * 100
            avg_loss = sum(t["pnl_pct"] for t in losses) / len(losses) if losses else 0
            print(f"  {label:<10} {len(bin_trades):>8} {wr:>7.1f}% {avg_pnl:>+9.2f}% "
                  f"{loss_rate:>9.1f}% {avg_loss:>+9.2f}%")


# ─────────────────────────────────────────────
# Section 5: Cross-Strategy Comparison
# ─────────────────────────────────────────────
def analyze_cross_strategy(results: Dict[str, CellResult], markets: List[str], strategies: List[str]):
    """교차 전략 비교."""
    print("\n" + "=" * 80)
    print("  SECTION 4: CROSS-STRATEGY COMPARISON")
    print("=" * 80)

    # ── 4A: Best Strategy per Market ──
    print("\n  ── 4A. Best Strategy per Market (by Sharpe) ──")
    for m in markets:
        ranked = []
        for s in strategies:
            key = f"{m}/{s}"
            cell = results.get(key)
            if cell and not cell.error:
                ranked.append((s, cell.sharpe, cell.total_return, cell.profit_factor))
        ranked.sort(key=lambda x: x[1], reverse=True)
        print(f"\n  {m.upper()}:")
        for i, (s, sharpe, ret, pf) in enumerate(ranked):
            marker = " ★" if i == 0 else ""
            print(f"    {i+1}. {s:<18} Sharpe {sharpe:>6.2f}  "
                  f"Return {ret*100:>+7.1f}%  PF {pf:>5.2f}{marker}")

    # ── 4B: Regime-Based Best Strategy ──
    print("\n  ── 4B. Regime-Based Strategy Performance ──")

    # Collect all trades by regime and strategy
    regime_strat_perf = defaultdict(lambda: defaultdict(list))
    for key, cell in results.items():
        if cell.error:
            continue
        for t in cell.trades:
            regime = t.get("entry_regime", "UNKNOWN") or "UNKNOWN"
            stag = t.get("strategy_tag", cell.strategy) or cell.strategy
            regime_strat_perf[regime][stag].append(t["pnl_pct"])

    for regime in ["BULL", "NEUTRAL", "RANGE_BOUND", "BEAR"]:
        strat_data = regime_strat_perf.get(regime, {})
        if not strat_data:
            continue
        print(f"\n  {regime}:")
        ranked = []
        for stag, pnls in strat_data.items():
            if not pnls:
                continue
            avg = sum(pnls) / len(pnls)
            wr = sum(1 for p in pnls if p > 0) / len(pnls) * 100
            ranked.append((stag, avg, wr, len(pnls)))
        ranked.sort(key=lambda x: x[1], reverse=True)
        print(f"    {'Strategy':<18} {'AvgPnL%':>10} {'WinRate':>8} {'Count':>6}")
        print("    " + "-" * 48)
        for stag, avg, wr, cnt in ranked:
            print(f"    {stag:<18} {avg:>+9.2f}% {wr:>7.1f}% {cnt:>6}")

    # ── 4C: Return Correlation ──
    print("\n  ── 4C. Strategy Equity Correlation (per market) ──")
    for m in markets:
        strat_returns = {}
        for s in strategies:
            key = f"{m}/{s}"
            cell = results.get(key)
            if not cell or cell.error or len(cell.equity_values) < 10:
                continue
            # daily returns
            rets = []
            for i in range(1, len(cell.equity_values)):
                prev = cell.equity_values[i - 1]
                if prev > 0:
                    rets.append((cell.equity_values[i] - prev) / prev)
                else:
                    rets.append(0)
            strat_returns[s] = rets

        if len(strat_returns) < 2:
            continue

        print(f"\n  {m.upper()} daily return correlation:")
        strat_names = list(strat_returns.keys())
        # Header
        header = "    " + " " * 14
        for sn in strat_names:
            header += f" {sn[:10]:>12}"
        print(header)

        for i, sn1 in enumerate(strat_names):
            row = f"    {sn1[:14]:<14}"
            for j, sn2 in enumerate(strat_names):
                if j < i:
                    row += " " * 13
                elif j == i:
                    row += f" {'1.00':>12}"
                else:
                    corr = _pearson_correlation(strat_returns[sn1], strat_returns[sn2])
                    row += f" {corr:>12.3f}"
            print(row)


def _pearson_correlation(x: List[float], y: List[float]) -> float:
    """두 시계열의 피어슨 상관계수."""
    n = min(len(x), len(y))
    if n < 10:
        return 0.0
    x, y = x[:n], y[:n]
    mx = sum(x) / n
    my = sum(y) / n
    cov = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y)) / n
    sx = math.sqrt(sum((xi - mx) ** 2 for xi in x) / n) if n > 0 else 0
    sy = math.sqrt(sum((yi - my) ** 2 for yi in y) / n) if n > 0 else 0
    if sx == 0 or sy == 0:
        return 0.0
    return cov / (sx * sy)


# ─────────────────────────────────────────────
# Section 6: Improvement Recommendations
# ─────────────────────────────────────────────
def generate_recommendations(results: Dict[str, CellResult], markets: List[str], strategies: List[str]):
    """데이터 기반 규칙형 개선 제안."""
    print("\n" + "=" * 80)
    print("  SECTION 5: DATA-DRIVEN IMPROVEMENT RECOMMENDATIONS")
    print("=" * 80)

    recommendations = []
    all_trades = []
    for key, cell in results.items():
        if cell.error:
            continue
        all_trades.extend(cell.trades)

    for key, cell in results.items():
        if cell.error:
            continue
        market, strategy = key.split("/")

        # Rule 1: ES1 ratio > 30%
        total_exits = sum(cell.exit_counts.values())
        if total_exits > 0:
            es1_ratio = cell.exit_counts.get("ES1", 0) / total_exits
            if es1_ratio > 0.30:
                recommendations.append(
                    f"[{key}] ES1 손절 비율 {es1_ratio*100:.0f}% > 30% → 진입 타이밍/필터 개선 필요"
                )

        # Rule 2: Phase1 reject rate > 90% (over-filtering)
        if cell.total_scans > 0:
            p1_ratio = cell.phase1_rejects / cell.total_scans
            if p1_ratio > 0.90:
                recommendations.append(
                    f"[{key}] Phase1 거부율 {p1_ratio*100:.0f}% > 90% → 필터 과잉, 완화 검토"
                )

        # Rule 3: Phase1 reject rate < 50% (under-filtering)
        if cell.total_scans > 100:
            p1_ratio = cell.phase1_rejects / cell.total_scans
            if p1_ratio < 0.50:
                recommendations.append(
                    f"[{key}] Phase1 거부율 {p1_ratio*100:.0f}% < 50% → 필터 부족, 강화 검토"
                )

        # Rule 4: Short-term losses (3 days or less) > 50%
        short_trades = [t for t in cell.trades if t["holding_days"] <= 3]
        if len(short_trades) >= 5:
            short_loss_rate = sum(1 for t in short_trades if t["pnl"] <= 0) / len(short_trades)
            if short_loss_rate > 0.50:
                recommendations.append(
                    f"[{key}] 단기(≤3일) 손실률 {short_loss_rate*100:.0f}% > 50% → 휩소(whipsaw) 문제"
                )

    # Rule 5: Sharpe variance across markets > 1.0
    for s in strategies:
        sharpes = []
        for m in markets:
            key = f"{m}/{s}"
            cell = results.get(key)
            if cell and not cell.error:
                sharpes.append(cell.sharpe)
        if len(sharpes) >= 2:
            variance = max(sharpes) - min(sharpes)
            if variance > 1.0:
                detail_parts = []
                for m in markets:
                    mk = f"{m}/{s}"
                    c = results.get(mk)
                    if c and not c.error:
                        detail_parts.append(f"{m}:{c.sharpe:.2f}")
                detail_str = ", ".join(detail_parts)
                recommendations.append(
                    f"[{s}] Sharpe 시장 간 편차 {variance:.2f} > 1.0 "
                    f"({detail_str}) → 시장 특화 튜닝 필요"
                )

    # Rule 6: BULL regime win rate < 50%
    regime_trades = defaultdict(list)
    for t in all_trades:
        regime = t.get("entry_regime", "")
        if regime:
            regime_trades[regime].append(t)

    for regime in ["BULL", "NEUTRAL"]:
        trades = regime_trades.get(regime, [])
        if len(trades) >= 10:
            wr = sum(1 for t in trades if t["pnl"] > 0) / len(trades)
            if wr < 0.50:
                recommendations.append(
                    f"[{regime}] 레짐 승률 {wr*100:.0f}% < 50% → 레짐 판단 부정확 또는 진입 시그널 약함"
                )

    # Rule 7: Signal strength Elite group should outperform Low group
    low_trades = [t for t in all_trades if 0 <= t.get("entry_signal_strength", 0) <= 40]
    elite_trades = [t for t in all_trades if t.get("entry_signal_strength", 0) >= 81]
    if len(low_trades) >= 5 and len(elite_trades) >= 5:
        low_wr = sum(1 for t in low_trades if t["pnl"] > 0) / len(low_trades) * 100
        elite_wr = sum(1 for t in elite_trades if t["pnl"] > 0) / len(elite_trades) * 100
        if elite_wr <= low_wr:
            recommendations.append(
                f"시그널 강도 Elite({elite_wr:.0f}%) ≤ Low({low_wr:.0f}%) → 시그널 스코어링 재검토 필요"
            )

    # Print recommendations
    if recommendations:
        for i, rec in enumerate(recommendations, 1):
            print(f"\n  {i}. {rec}")
    else:
        print("\n  모든 지표가 정상 범위 내에 있습니다.")

    return recommendations


# ─────────────────────────────────────────────
# Export
# ─────────────────────────────────────────────
def export_json(results: Dict[str, CellResult], recommendations: List[str], filepath: str):
    """전체 결과를 JSON으로 저장."""
    data = {
        "generated_at": datetime.now().isoformat(),
        "period": f"{START_DATE}-{END_DATE}",
        "cells": {},
        "recommendations": recommendations,
    }
    for key, cell in results.items():
        cell_data = {
            "market": cell.market,
            "strategy": cell.strategy,
            "metrics": {
                "total_return": round(cell.total_return, 6),
                "cagr": round(cell.cagr, 6),
                "sharpe": round(cell.sharpe, 4),
                "sortino": round(cell.sortino, 4),
                "max_drawdown": round(cell.max_drawdown, 6),
                "profit_factor": round(cell.profit_factor, 4),
                "win_rate": round(cell.win_rate, 4),
                "total_trades": cell.total_trades,
                "avg_pnl_pct": round(cell.avg_pnl_pct, 6),
                "avg_holding_days": round(cell.avg_holding_days, 2),
                "best_trade_pct": round(cell.best_trade_pct, 6),
                "worst_trade_pct": round(cell.worst_trade_pct, 6),
                "final_value": round(cell.final_value, 2),
            },
            "phase_stats": {
                "total_scans": cell.total_scans,
                "phase1_rejects": cell.phase1_rejects,
                "phase2_rejects": cell.phase2_rejects,
                "phase3_no_primary": cell.phase3_no_primary,
                "phase3_no_confirm": cell.phase3_no_confirm,
                "phase4_risk_blocks": cell.phase4_risk_blocks,
                "entries_executed": cell.entries_executed,
            },
            "exit_counts": cell.exit_counts,
            "trades": cell.trades,
            "regime": {
                "bull_pct": round(cell.time_in_bull, 2),
                "neutral_pct": round(cell.time_in_neutral, 2),
                "bear_pct": round(cell.time_in_bear, 2),
            },
            "error": cell.error,
        }
        data["cells"][key] = cell_data

    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n  JSON exported: {filepath}")


def export_markdown(results: Dict[str, CellResult], recommendations: List[str],
                    markets: List[str], strategies: List[str], filepath: str):
    """Markdown 요약 리포트 생성."""
    lines = []
    lines.append(f"# Strategy Matrix Analysis Report")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"Period: {START_DATE} ~ {END_DATE}")
    lines.append("")

    # Performance Matrix
    lines.append("## 1. Performance Matrix")
    lines.append("")

    # Sharpe table
    lines.append("### Sharpe Ratio")
    header = "| Market |"
    sep = "|--------|"
    for s in strategies:
        header += f" {s} |"
        sep += "--------|"
    lines.append(header)
    lines.append(sep)
    for m in markets:
        row = f"| {m.upper()} |"
        for s in strategies:
            key = f"{m}/{s}"
            cell = results.get(key)
            if cell and not cell.error:
                row += f" {cell.sharpe:.2f} |"
            else:
                row += " ERR |"
        lines.append(row)
    lines.append("")

    # Return table
    lines.append("### Total Return")
    lines.append(header.replace("Sharpe Ratio", "Total Return"))
    lines.append(sep)
    for m in markets:
        row = f"| {m.upper()} |"
        for s in strategies:
            key = f"{m}/{s}"
            cell = results.get(key)
            if cell and not cell.error:
                row += f" {cell.total_return*100:+.1f}% |"
            else:
                row += " ERR |"
        lines.append(row)
    lines.append("")

    # PF table
    lines.append("### Profit Factor")
    lines.append(header)
    lines.append(sep)
    for m in markets:
        row = f"| {m.upper()} |"
        for s in strategies:
            key = f"{m}/{s}"
            cell = results.get(key)
            if cell and not cell.error:
                row += f" {cell.profit_factor:.2f} |"
            else:
                row += " ERR |"
        lines.append(row)
    lines.append("")

    # MDD table
    lines.append("### Max Drawdown")
    lines.append(header)
    lines.append(sep)
    for m in markets:
        row = f"| {m.upper()} |"
        for s in strategies:
            key = f"{m}/{s}"
            cell = results.get(key)
            if cell and not cell.error:
                row += f" {cell.max_drawdown*100:.2f}% |"
            else:
                row += " ERR |"
        lines.append(row)
    lines.append("")

    # Best per market
    lines.append("## 2. Best Strategy per Market")
    lines.append("")
    for m in markets:
        best_key = None
        best_sharpe = -999
        for s in strategies:
            key = f"{m}/{s}"
            cell = results.get(key)
            if cell and not cell.error and cell.sharpe > best_sharpe:
                best_sharpe = cell.sharpe
                best_key = key
        if best_key:
            cell = results[best_key]
            lines.append(f"- **{m.upper()}**: {cell.strategy} (Sharpe {cell.sharpe:.2f}, "
                        f"Return {cell.total_return*100:+.1f}%, PF {cell.profit_factor:.2f})")
    lines.append("")

    # Recommendations
    lines.append("## 3. Improvement Recommendations")
    lines.append("")
    if recommendations:
        for i, rec in enumerate(recommendations, 1):
            lines.append(f"{i}. {rec}")
    else:
        lines.append("All metrics within normal range.")
    lines.append("")

    # Trade summary
    lines.append("## 4. Trade Summary")
    lines.append("")
    lines.append("| Market/Strategy | Trades | Win Rate | Avg PnL% | Best | Worst |")
    lines.append("|-----------------|--------|----------|----------|------|-------|")
    for m in markets:
        for s in strategies:
            key = f"{m}/{s}"
            cell = results.get(key)
            if cell and not cell.error:
                lines.append(f"| {key} | {cell.total_trades} | {cell.win_rate*100:.0f}% | "
                           f"{cell.avg_pnl_pct*100:+.2f}% | {cell.best_trade_pct*100:+.1f}% | "
                           f"{cell.worst_trade_pct*100:+.1f}% |")
    lines.append("")

    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"  Markdown exported: {filepath}")


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="3-Index × 5-Strategy Matrix Analysis")
    parser.add_argument("--markets", nargs="+", default=ALL_MARKETS,
                        help=f"Markets to test (default: {ALL_MARKETS})")
    parser.add_argument("--strategies", nargs="+", default=ALL_STRATEGIES,
                        help=f"Strategies to test (default: {ALL_STRATEGIES})")
    parser.add_argument("--no-export", action="store_true",
                        help="Skip JSON/Markdown export")
    args = parser.parse_args()

    markets = args.markets
    strategies = args.strategies

    print("=" * 80)
    print("  3-INDEX × 5-STRATEGY MATRIX ANALYSIS")
    print(f"  Markets:    {markets}")
    print(f"  Strategies: {strategies}")
    print(f"  Period:     {START_DATE} ~ {END_DATE}")
    print("=" * 80)

    # 1. Grid Runner
    results = run_grid(markets, strategies)

    # 2. Performance Matrix
    print_performance_matrix(results, markets, strategies)

    # 3. Momentum Accuracy
    analyze_momentum_accuracy(results, markets, strategies)

    # 4. Exit Analysis
    analyze_exits(results, markets, strategies)

    # 5. Cross-Strategy Comparison
    analyze_cross_strategy(results, markets, strategies)

    # 6. Recommendations
    recommendations = generate_recommendations(results, markets, strategies)

    # 7. Export
    if not args.no_export:
        timestamp = datetime.now().strftime("%Y%m%d")
        reports_dir = os.path.join(project_root, "ats", "reports")
        json_path = os.path.join(reports_dir, f"strategy_matrix_{timestamp}.json")
        md_path = os.path.join(reports_dir, f"strategy_matrix_{timestamp}.md")
        export_json(results, recommendations, json_path)
        export_markdown(results, recommendations, markets, strategies, md_path)

    print("\n" + "=" * 80)
    print("  ANALYSIS COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
