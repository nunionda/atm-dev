#!/usr/bin/env python3
"""
Top60 → 10종목 고정사이징 + ES2 제거 전략 검증 스크립트.

3개 마켓(KOSPI/SP500/NDX)에서 기존 전략 vs 신규 전략 A/B 비교 백테스트.

Usage:
    cd ats && python scripts/verify_top60_strategy.py
    cd ats && python scripts/verify_top60_strategy.py --market sp500
    cd ats && python scripts/verify_top60_strategy.py --start 20240101 --end 20251231
"""

import argparse
import os
import sys
import time

# 프로젝트 루트를 sys.path에 추가
script_dir = os.path.dirname(os.path.abspath(__file__))
ats_dir = os.path.dirname(script_dir)
if ats_dir not in sys.path:
    sys.path.insert(0, ats_dir)

from backtest.historical_engine import HistoricalBacktester


# ── 마켓별 설정 ──
MARKET_CONFIGS = {
    "sp500": {
        "baseline_universe": "sp500_full",
        "baseline_top_n": 15,
        "baseline_capital": 100_000,
        "new_universe": "sp500_top60",
        "new_top_n": 10,
        "new_capital": 30_000,
        "fixed_amount": 3_000,
        "currency_symbol": "$",
    },
    "ndx": {
        "baseline_universe": "ndx_full",
        "baseline_top_n": 15,
        "baseline_capital": 100_000,
        "new_universe": "ndx_top60",
        "new_top_n": 10,
        "new_capital": 30_000,
        "fixed_amount": 3_000,
        "currency_symbol": "$",
    },
    "kospi": {
        "baseline_universe": "kospi_full",
        "baseline_top_n": 10,
        "baseline_capital": 100_000_000,
        "new_universe": "kospi_top60",
        "new_top_n": 10,
        "new_capital": 30_000_000,
        "fixed_amount": 3_000_000,
        "currency_symbol": "₩",
    },
}


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
    print(f"  [{label}] {market.upper()} 백테스트")
    print(f"  Universe: {universe}, Top-N: {top_n}, Capital: {initial_capital:,.0f}")
    if fixed_amount > 0:
        print(f"  Fixed sizing: {fixed_amount:,.0f}/종목, ES2: 비활성")
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


def print_comparison(market: str, baseline, new, cfg: dict):
    """두 결과를 비교 표로 출력."""
    sym = cfg["currency_symbol"]

    print(f"\n{'='*70}")
    print(f"  📊 {market.upper()} — Baseline vs New Strategy 비교")
    print(f"{'='*70}")
    print(f"  {'지표':<25} {'Baseline':>18} {'New (Top60)':>18} {'변화':>10}")
    print(f"  {'-'*71}")

    rows = [
        ("총 수익률", f"{baseline.total_return:.2%}", f"{new.total_return:.2%}",
         f"{(new.total_return - baseline.total_return):+.2%}"),
        ("CAGR", f"{baseline.cagr:.2%}", f"{new.cagr:.2%}",
         f"{(new.cagr - baseline.cagr):+.2%}"),
        ("Sharpe Ratio", f"{baseline.sharpe_ratio:.2f}", f"{new.sharpe_ratio:.2f}",
         f"{(new.sharpe_ratio - baseline.sharpe_ratio):+.2f}"),
        ("Sortino Ratio", f"{baseline.sortino_ratio:.2f}", f"{new.sortino_ratio:.2f}",
         f"{(new.sortino_ratio - baseline.sortino_ratio):+.2f}"),
        ("MDD", f"{baseline.max_drawdown:.2%}", f"{new.max_drawdown:.2%}",
         f"{(new.max_drawdown - baseline.max_drawdown):+.2%}"),
        ("총 거래 수", f"{baseline.total_trades}", f"{new.total_trades}",
         f"{new.total_trades - baseline.total_trades:+d}"),
        ("승률", f"{baseline.win_rate:.1%}", f"{new.win_rate:.1%}",
         f"{(new.win_rate - baseline.win_rate):+.1%}"),
        ("Profit Factor", f"{baseline.profit_factor:.2f}", f"{new.profit_factor:.2f}",
         f"{(new.profit_factor - baseline.profit_factor):+.2f}"),
        ("평균 수익률/건", f"{baseline.avg_pnl_pct:.2%}", f"{new.avg_pnl_pct:.2%}",
         f"{(new.avg_pnl_pct - baseline.avg_pnl_pct):+.2%}"),
        ("평균 보유일", f"{baseline.avg_holding_days:.1f}일", f"{new.avg_holding_days:.1f}일",
         f"{(new.avg_holding_days - baseline.avg_holding_days):+.1f}"),
        ("최고 수익 거래", f"{baseline.best_trade_pct:.2%}", f"{new.best_trade_pct:.2%}",
         f"{(new.best_trade_pct - baseline.best_trade_pct):+.2%}"),
        ("최대 연속 손실", f"{baseline.max_consecutive_losses}회", f"{new.max_consecutive_losses}회",
         f"{new.max_consecutive_losses - baseline.max_consecutive_losses:+d}"),
        ("최종 자산", f"{sym}{baseline.final_value:,.0f}", f"{sym}{new.final_value:,.0f}", ""),
    ]

    for label, val_a, val_b, change in rows:
        print(f"  {label:<25} {val_a:>18} {val_b:>18} {change:>10}")

    # Phase 통계 (ES별)
    ps_b = baseline.phase_stats
    ps_n = new.phase_stats
    print(f"\n  {'청산 유형별 통계':<25} {'Baseline':>18} {'New (Top60)':>18}")
    print(f"  {'-'*63}")
    print(f"  {'ES1 손절':.<25} {ps_b.es1_stop_loss:>18} {ps_n.es1_stop_loss:>18}")
    print(f"  {'ES2 익절':.<25} {ps_b.es2_take_profit:>18} {ps_n.es2_take_profit:>18}")
    print(f"  {'ES3 트레일링':.<25} {ps_b.es3_trailing_stop:>18} {ps_n.es3_trailing_stop:>18}")
    print(f"  {'ES4 데드크로스':.<25} {ps_b.es4_dead_cross:>18} {ps_n.es4_dead_cross:>18}")
    print(f"  {'ES5 보유기간':.<25} {ps_b.es5_max_holding:>18} {ps_n.es5_max_holding:>18}")
    print(f"  {'ES7 리밸런스':.<25} {ps_b.es7_rebalance_exit:>18} {ps_n.es7_rebalance_exit:>18}")
    print()


def main():
    parser = argparse.ArgumentParser(description="Top60 전략 A/B 검증")
    parser.add_argument("--market", choices=["sp500", "ndx", "kospi", "all"], default="all",
                        help="대상 마켓 (기본: all)")
    parser.add_argument("--start", default="20240101", help="시작일 (YYYYMMDD, 기본: 20240101)")
    parser.add_argument("--end", default="20251231", help="종료일 (YYYYMMDD, 기본: 20251231)")
    args = parser.parse_args()

    markets = list(MARKET_CONFIGS.keys()) if args.market == "all" else [args.market]

    print("\n" + "=" * 70)
    print("  🔬 Top60 → 10종목 고정사이징 + ES2 제거 전략 검증")
    print("  " + "=" * 66)
    print(f"  대상 마켓: {', '.join(m.upper() for m in markets)}")
    print(f"  검증 기간: {args.start} ~ {args.end}")
    print(f"  비교: Baseline (ATR사이징+ES2) vs New (고정사이징+강화트레일링)")
    print("=" * 70)

    all_results = {}

    for market in markets:
        cfg = MARKET_CONFIGS[market]

        # A) Baseline
        baseline = run_backtest(
            market=market,
            universe=cfg["baseline_universe"],
            top_n=cfg["baseline_top_n"],
            initial_capital=cfg["baseline_capital"],
            start_date=args.start,
            end_date=args.end,
            fixed_amount=0,
            disable_es2=False,
            label="A: Baseline",
        )

        # B) New Strategy
        new = run_backtest(
            market=market,
            universe=cfg["new_universe"],
            top_n=cfg["new_top_n"],
            initial_capital=cfg["new_capital"],
            start_date=args.start,
            end_date=args.end,
            fixed_amount=cfg["fixed_amount"],
            disable_es2=True,
            label="B: New (Top60+FixedSize+NoES2)",
        )

        print_comparison(market, baseline, new, cfg)
        all_results[market] = {"baseline": baseline, "new": new}

    # 전체 요약
    if len(markets) > 1:
        print("\n" + "=" * 70)
        print("  📋 전체 마켓 요약")
        print("=" * 70)
        print(f"  {'마켓':<10} {'Baseline Return':>18} {'New Return':>18} {'Baseline Sharpe':>16} {'New Sharpe':>12}")
        print(f"  {'-'*76}")
        for market, res in all_results.items():
            b, n = res["baseline"], res["new"]
            print(f"  {market.upper():<10} {b.total_return:>17.2%} {n.total_return:>17.2%} "
                  f"{b.sharpe_ratio:>15.2f} {n.sharpe_ratio:>11.2f}")
        print()

    print("\n✅ 검증 완료!\n")


if __name__ == "__main__":
    main()
