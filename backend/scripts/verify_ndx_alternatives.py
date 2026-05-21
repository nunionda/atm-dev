#!/usr/bin/env python3
"""
NDX 대안 전략 비교 검증 스크립트.

NDX는 고가 종목 특성으로 $3K 고정사이징이 비효율적이었으므로 3가지 대안을 비교:
  A) 기존 Baseline (ATR사이징 + ES2 활성)
  B) $5K 고정사이징 + ES2 제거 + 강화 트레일링
  C) $10K 고정사이징 + ES2 제거 + 강화 트레일링
  D) 하이브리드: ATR사이징 유지 + ES2만 제거 + 강화 트레일링

Usage:
    cd ats && python scripts/verify_ndx_alternatives.py
    cd ats && python scripts/verify_ndx_alternatives.py --start 20240101 --end 20251231
"""

import argparse
import os
import sys
import time

script_dir = os.path.dirname(os.path.abspath(__file__))
ats_dir = os.path.dirname(script_dir)
if ats_dir not in sys.path:
    sys.path.insert(0, ats_dir)

from backtest.historical_engine import HistoricalBacktester


def run_backtest(
    market: str,
    universe: str,
    top_n: int,
    initial_capital: float,
    start_date: str,
    end_date: str,
    fixed_amount: float = 0,
    disable_es2: bool = False,
    label: str = "",
):
    """단일 백테스트 실행 후 결과 반환."""
    print(f"\n{'='*60}")
    print(f"  [{label}] NDX 백테스트")
    print(f"  Universe: {universe}, Top-N: {top_n}, Capital: ${initial_capital:,.0f}")
    if fixed_amount > 0:
        print(f"  Fixed sizing: ${fixed_amount:,.0f}/종목")
    else:
        print(f"  Sizing: ATR 리스크 패리티")
    print(f"  ES2: {'비활성' if disable_es2 else '활성'}")
    print(f"  Period: {start_date} ~ {end_date}")
    print(f"{'='*60}")

    bt = HistoricalBacktester(
        market=market,
        scenario="custom",
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
        universe=universe,
        rebalance_days=14,
        top_n=top_n,
        strategy_mode="momentum",
        fixed_amount_per_stock=fixed_amount,
        disable_es2=disable_es2,
    )

    start_time = time.time()
    result = bt.run()
    elapsed = time.time() - start_time
    print(f"\n  ⏱ 소요 시간: {elapsed:.1f}초")

    return result


def print_multi_comparison(results: dict):
    """다수 전략 결과를 비교 표로 출력."""
    labels = list(results.keys())
    data = list(results.values())

    print(f"\n{'='*100}")
    print(f"  📊 NDX — 대안 전략 비교 (4가지)")
    print(f"{'='*100}")

    # 헤더
    header = f"  {'지표':<20}"
    for label in labels:
        header += f" {label:>18}"
    print(header)
    print(f"  {'-'*len(header)}")

    rows = [
        ("총 수익률", [f"{r.total_return:.2%}" for r in data]),
        ("CAGR", [f"{r.cagr:.2%}" for r in data]),
        ("Sharpe Ratio", [f"{r.sharpe_ratio:.2f}" for r in data]),
        ("Sortino Ratio", [f"{r.sortino_ratio:.2f}" for r in data]),
        ("MDD", [f"{r.max_drawdown:.2%}" for r in data]),
        ("총 거래 수", [f"{r.total_trades}" for r in data]),
        ("승률", [f"{r.win_rate:.1%}" for r in data]),
        ("Profit Factor", [f"{r.profit_factor:.2f}" for r in data]),
        ("평균 수익률/건", [f"{r.avg_pnl_pct:.2%}" for r in data]),
        ("평균 보유일", [f"{r.avg_holding_days:.1f}일" for r in data]),
        ("최고 수익 거래", [f"{r.best_trade_pct:.2%}" for r in data]),
        ("최대 연속 손실", [f"{r.max_consecutive_losses}회" for r in data]),
        ("최종 자산", [f"${r.final_value:,.0f}" for r in data]),
    ]

    for metric, values in rows:
        row = f"  {metric:<20}"
        for v in values:
            row += f" {v:>18}"
        print(row)

    # ES별 통계
    print(f"\n  {'청산 유형':<20}", end="")
    for label in labels:
        print(f" {label:>18}", end="")
    print()
    print(f"  {'-'*90}")

    es_rows = [
        ("ES1 손절", [f"{r.phase_stats.es1_stop_loss}" for r in data]),
        ("ES2 익절", [f"{r.phase_stats.es2_take_profit}" for r in data]),
        ("ES3 트레일링", [f"{r.phase_stats.es3_trailing_stop}" for r in data]),
        ("ES4 데드크로스", [f"{r.phase_stats.es4_dead_cross}" for r in data]),
        ("ES5 보유기간", [f"{r.phase_stats.es5_max_holding}" for r in data]),
        ("ES7 리밸런스", [f"{r.phase_stats.es7_rebalance_exit}" for r in data]),
    ]

    for metric, values in es_rows:
        row = f"  {metric:<20}"
        for v in values:
            row += f" {v:>18}"
        print(row)

    # 최적 전략 판정
    print(f"\n{'='*100}")
    print(f"  🏆 최적 전략 판정")
    print(f"{'='*100}")

    best_sharpe_idx = max(range(len(data)), key=lambda i: data[i].sharpe_ratio)
    best_return_idx = max(range(len(data)), key=lambda i: data[i].total_return)
    best_mdd_idx = max(range(len(data)), key=lambda i: data[i].max_drawdown)  # MDD is negative, higher = better
    best_pf_idx = max(range(len(data)), key=lambda i: data[i].profit_factor)

    print(f"  최고 Sharpe Ratio : {labels[best_sharpe_idx]} ({data[best_sharpe_idx].sharpe_ratio:.2f})")
    print(f"  최고 수익률       : {labels[best_return_idx]} ({data[best_return_idx].total_return:.2%})")
    print(f"  최소 MDD          : {labels[best_mdd_idx]} ({data[best_mdd_idx].max_drawdown:.2%})")
    print(f"  최고 Profit Factor: {labels[best_pf_idx]} ({data[best_pf_idx].profit_factor:.2f})")

    # 종합 점수 (Sharpe 40% + Return 30% + MDD 20% + PF 10%)
    scores = []
    sharpe_vals = [d.sharpe_ratio for d in data]
    return_vals = [d.total_return for d in data]
    mdd_vals = [d.max_drawdown for d in data]
    pf_vals = [d.profit_factor for d in data]

    s_range = max(sharpe_vals) - min(sharpe_vals) if max(sharpe_vals) != min(sharpe_vals) else 1
    r_range = max(return_vals) - min(return_vals) if max(return_vals) != min(return_vals) else 1
    m_range = max(mdd_vals) - min(mdd_vals) if max(mdd_vals) != min(mdd_vals) else 1
    p_range = max(pf_vals) - min(pf_vals) if max(pf_vals) != min(pf_vals) else 1

    for i, d in enumerate(data):
        s = (d.sharpe_ratio - min(sharpe_vals)) / s_range * 40
        r = (d.total_return - min(return_vals)) / r_range * 30
        m = (d.max_drawdown - min(mdd_vals)) / m_range * 20  # higher MDD = better (less negative)
        p = (d.profit_factor - min(pf_vals)) / p_range * 10
        total = s + r + m + p
        scores.append(total)

    print(f"\n  종합 점수 (Sharpe 40% + Return 30% + MDD 20% + PF 10%):")
    for i, label in enumerate(labels):
        marker = " ⭐" if scores[i] == max(scores) else ""
        print(f"    {label}: {scores[i]:.1f}/100{marker}")

    winner_idx = scores.index(max(scores))
    print(f"\n  🏆 NDX 최적 전략: {labels[winner_idx]}")
    print()


def main():
    parser = argparse.ArgumentParser(description="NDX 대안 전략 비교 검증")
    parser.add_argument("--start", default="20240101", help="시작일 (YYYYMMDD)")
    parser.add_argument("--end", default="20251231", help="종료일 (YYYYMMDD)")
    args = parser.parse_args()

    print("\n" + "=" * 100)
    print("  🔬 NDX 대안 전략 비교 검증")
    print("  " + "=" * 96)
    print(f"  검증 기간: {args.start} ~ {args.end}")
    print(f"  A) Baseline: ATR사이징 + ES2 활성 (기존)")
    print(f"  B) $5K 고정사이징 + ES2 제거 + 강화 트레일링")
    print(f"  C) $10K 고정사이징 + ES2 제거 + 강화 트레일링")
    print(f"  D) 하이브리드: ATR사이징 유지 + ES2만 제거 + 강화 트레일링")
    print("=" * 100)

    results = {}

    # A) Baseline
    results["A:Baseline"] = run_backtest(
        market="ndx",
        universe="ndx_full",
        top_n=15,
        initial_capital=100_000,
        start_date=args.start,
        end_date=args.end,
        fixed_amount=0,
        disable_es2=False,
        label="A: Baseline (ATR+ES2)",
    )

    # B) $5K 고정사이징
    results["B:Fixed$5K"] = run_backtest(
        market="ndx",
        universe="ndx_top60",
        top_n=10,
        initial_capital=50_000,  # 10종목 × $5K
        start_date=args.start,
        end_date=args.end,
        fixed_amount=5_000,
        disable_es2=True,
        label="B: Top60 + $5K Fixed + NoES2",
    )

    # C) $10K 고정사이징
    results["C:Fixed$10K"] = run_backtest(
        market="ndx",
        universe="ndx_top60",
        top_n=10,
        initial_capital=100_000,  # 10종목 × $10K
        start_date=args.start,
        end_date=args.end,
        fixed_amount=10_000,
        disable_es2=True,
        label="C: Top60 + $10K Fixed + NoES2",
    )

    # D) 하이브리드: ATR사이징 유지 + ES2만 제거
    results["D:Hybrid"] = run_backtest(
        market="ndx",
        universe="ndx_top60",
        top_n=10,
        initial_capital=100_000,
        start_date=args.start,
        end_date=args.end,
        fixed_amount=0,  # ATR 사이징 유지
        disable_es2=True,  # ES2만 제거
        label="D: Top60 + ATR사이징 + NoES2 (Hybrid)",
    )

    print_multi_comparison(results)
    print("\n✅ NDX 대안 검증 완료!\n")


if __name__ == "__main__":
    main()
