#!/usr/bin/env python3
"""
백테스트 결과 시각화

Usage:
    python scripts/visualize_backtest.py
    python scripts/visualize_backtest.py --trades results/trades.csv --equity results/equity_curve.csv
    python scripts/visualize_backtest.py --output results/backtest_report.png
"""

import argparse
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker
import pandas as pd
import numpy as np


def load_data(trades_path: str, equity_path: str):
    trades = pd.read_csv(trades_path)
    equity = pd.read_csv(equity_path)
    equity["date"] = pd.to_datetime(equity["date"], format="%Y%m%d")
    trades["entry_date"] = pd.to_datetime(trades["entry_date"])
    trades["exit_date"] = pd.to_datetime(trades["exit_date"])
    return trades, equity


def plot_report(trades: pd.DataFrame, equity: pd.DataFrame, output_path: str):
    fig = plt.figure(figsize=(18, 22), facecolor="white")
    fig.suptitle("ATS Backtest Report", fontsize=20, fontweight="bold", y=0.98)

    gs = fig.add_gridspec(4, 2, hspace=0.35, wspace=0.3,
                          left=0.08, right=0.95, top=0.95, bottom=0.04)

    colors = {
        "equity": "#2563eb",
        "cash": "#94a3b8",
        "drawdown": "#ef4444",
        "win": "#22c55e",
        "lose": "#ef4444",
        "neutral": "#94a3b8",
    }

    # ── 1. Equity Curve (top, full width) ──
    ax1 = fig.add_subplot(gs[0, :])
    ax1.fill_between(equity["date"], equity["total_value"], equity["total_value"].iloc[0],
                     alpha=0.15, color=colors["equity"])
    ax1.plot(equity["date"], equity["total_value"], color=colors["equity"],
             linewidth=2, label="Total Value")
    ax1.plot(equity["date"], equity["cash"], color=colors["cash"],
             linewidth=1, linestyle="--", alpha=0.7, label="Cash")

    # Mark trades on equity curve
    for _, t in trades.iterrows():
        c = colors["win"] if t["pnl"] > 0 else colors["lose"] if t["pnl"] < 0 else colors["neutral"]
        ax1.axvline(t["entry_date"], color=c, alpha=0.08, linewidth=1)

    ax1.set_title("Equity Curve", fontsize=14, fontweight="bold")
    ax1.set_ylabel("Value (KRW)")
    ax1.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x/1e6:.1f}M"))
    ax1.legend(loc="upper left")
    ax1.grid(True, alpha=0.3)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))

    # ── 2. Drawdown (second row, full width) ──
    ax2 = fig.add_subplot(gs[1, :], sharex=ax1)
    dd_pct = equity["drawdown"] * 100
    ax2.fill_between(equity["date"], dd_pct, 0, color=colors["drawdown"], alpha=0.3)
    ax2.plot(equity["date"], dd_pct, color=colors["drawdown"], linewidth=1.5)
    ax2.set_title("Drawdown", fontsize=14, fontweight="bold")
    ax2.set_ylabel("Drawdown (%)")
    ax2.set_ylim(dd_pct.min() * 1.3 if dd_pct.min() < 0 else -1, 0.1)
    ax2.grid(True, alpha=0.3)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))

    # ── 3. Trade PnL Distribution ──
    ax3 = fig.add_subplot(gs[2, 0])
    pnl_pct = trades["pnl_pct"] * 100
    bar_colors = [colors["win"] if x > 0 else colors["lose"] if x < 0 else colors["neutral"]
                  for x in pnl_pct]
    ax3.bar(range(len(pnl_pct)), pnl_pct, color=bar_colors, alpha=0.8, width=0.8)
    ax3.axhline(0, color="black", linewidth=0.5)
    ax3.axhline(pnl_pct.mean(), color=colors["equity"], linewidth=1.5,
                linestyle="--", label=f"Avg: {pnl_pct.mean():.2f}%")
    ax3.set_title("Trade PnL (%)", fontsize=14, fontweight="bold")
    ax3.set_xlabel("Trade #")
    ax3.set_ylabel("PnL (%)")
    ax3.legend()
    ax3.grid(True, alpha=0.3, axis="y")

    # ── 4. PnL Histogram ──
    ax4 = fig.add_subplot(gs[2, 1])
    bins = np.linspace(pnl_pct.min() - 1, pnl_pct.max() + 1, 20)
    n, bin_edges, patches = ax4.hist(pnl_pct, bins=bins, edgecolor="white", alpha=0.8)
    for patch, left_edge in zip(patches, bin_edges):
        center = left_edge + (bin_edges[1] - bin_edges[0]) / 2
        patch.set_facecolor(colors["win"] if center > 0 else colors["lose"])
    ax4.axvline(0, color="black", linewidth=0.8, linestyle="-")
    ax4.axvline(pnl_pct.mean(), color=colors["equity"], linewidth=1.5,
                linestyle="--", label=f"Mean: {pnl_pct.mean():.2f}%")
    ax4.set_title("PnL Distribution", fontsize=14, fontweight="bold")
    ax4.set_xlabel("PnL (%)")
    ax4.set_ylabel("Frequency")
    ax4.legend()
    ax4.grid(True, alpha=0.3, axis="y")

    # ── 5. Exit Reason Breakdown ──
    ax5 = fig.add_subplot(gs[3, 0])
    reason_stats = trades.groupby("exit_reason").agg(
        count=("pnl", "size"),
        avg_pnl=("pnl_pct", "mean"),
        total_pnl=("pnl", "sum"),
    ).sort_values("count", ascending=True)

    reason_colors = [colors["win"] if v > 0 else colors["lose"]
                     for v in reason_stats["avg_pnl"]]
    bars = ax5.barh(reason_stats.index, reason_stats["count"], color=reason_colors, alpha=0.8)

    for bar, avg in zip(bars, reason_stats["avg_pnl"]):
        width = bar.get_width()
        ax5.text(width + 0.3, bar.get_y() + bar.get_height() / 2,
                 f"avg {avg*100:+.1f}%", va="center", fontsize=9, color="#374151")

    ax5.set_title("Exit Reasons", fontsize=14, fontweight="bold")
    ax5.set_xlabel("Count")
    ax5.grid(True, alpha=0.3, axis="x")

    # ── 6. Cumulative PnL over time ──
    ax6 = fig.add_subplot(gs[3, 1])
    trades_sorted = trades.sort_values("exit_date")
    cum_pnl = trades_sorted["pnl"].cumsum()
    cum_colors = [colors["win"] if v > 0 else colors["lose"] for v in cum_pnl]

    ax6.fill_between(range(len(cum_pnl)), cum_pnl, 0,
                     where=(cum_pnl >= 0), color=colors["win"], alpha=0.15)
    ax6.fill_between(range(len(cum_pnl)), cum_pnl, 0,
                     where=(cum_pnl < 0), color=colors["lose"], alpha=0.15)
    ax6.plot(range(len(cum_pnl)), cum_pnl, color=colors["equity"], linewidth=2)
    ax6.axhline(0, color="black", linewidth=0.5)
    ax6.set_title("Cumulative PnL", fontsize=14, fontweight="bold")
    ax6.set_xlabel("Trade #")
    ax6.set_ylabel("Cumulative PnL (KRW)")
    ax6.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x/1e3:.0f}K"))
    ax6.grid(True, alpha=0.3)

    plt.savefig(output_path, dpi=150, bbox_inches="tight", facecolor="white")
    print(f"Report saved: {output_path}")
    plt.close()


def main():
    parser = argparse.ArgumentParser(description="백테스트 결과 시각화")
    parser.add_argument("--trades", default="results/trades.csv")
    parser.add_argument("--equity", default="results/equity_curve.csv")
    parser.add_argument("--output", default="results/backtest_report.png")
    args = parser.parse_args()

    trades, equity = load_data(args.trades, args.equity)
    plot_report(trades, equity, args.output)


if __name__ == "__main__":
    main()
