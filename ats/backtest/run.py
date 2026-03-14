"""
ATS 히스토리컬 백테스트 CLI.

Usage:
    cd ats
    python -m backtest.run --market sp500 --scenario financial_crisis_us
    python -m backtest.run --market kospi --scenario covid_crash
    python -m backtest.run --market sp500 --all-scenarios
    python -m backtest.run --market ndx --start 20200101 --end 20231231
    python -m backtest.run --compare --market sp500
"""

from __future__ import annotations

import argparse
import sys
from typing import Dict

from backtest.historical_engine import HistoricalBacktester
from backtest.metrics import ExtendedMetrics
from backtest.reporter import ReportGenerator
from backtest.scenarios import SCENARIOS, get_scenarios_for_market
from simulation.watchlists import MARKET_CONFIG


def main():
    parser = argparse.ArgumentParser(
        description="ATS Historical Backtester — 6-Phase Pipeline Crisis Testing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m backtest.run --market sp500 --scenario financial_crisis_us
  python -m backtest.run --market kospi --scenario covid_crash --capital 50000000
  python -m backtest.run --market sp500 --all-scenarios
  python -m backtest.run --compare --market sp500
  python -m backtest.run --market ndx --start 20200101 --end 20231231
        """,
    )
    parser.add_argument(
        "--market",
        choices=list(MARKET_CONFIG.keys()),
        required=True,
        help="Target market (sp500, ndx, kospi). Required.",
    )
    parser.add_argument(
        "--scenario",
        choices=list(SCENARIOS.keys()) + ["custom"],
        default="custom",
        help="Pre-defined scenario ID (default: custom)",
    )
    parser.add_argument(
        "--start",
        help="Start date YYYYMMDD (for custom scenario)",
    )
    parser.add_argument(
        "--end",
        help="End date YYYYMMDD (for custom scenario)",
    )
    parser.add_argument(
        "--capital",
        type=float,
        help="Override initial capital",
    )
    parser.add_argument(
        "--all-scenarios",
        action="store_true",
        help="Run all applicable scenarios for the market",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Run all scenarios and generate comparison report",
    )
    parser.add_argument(
        "--output",
        default="output/backtest",
        help="Output directory (default: output/backtest)",
    )
    parser.add_argument(
        "--no-charts",
        action="store_true",
        help="Skip chart generation (faster)",
    )
    parser.add_argument(
        "--force-download",
        action="store_true",
        help="Re-download data even if cached",
    )
    parser.add_argument(
        "--list-scenarios",
        action="store_true",
        help="List all available scenarios and exit",
    )
    parser.add_argument(
        "--slippage",
        type=float,
        default=0.001,
        help="Slippage per side (default: 0.001 = 0.1%%)",
    )
    parser.add_argument(
        "--commission",
        type=float,
        default=0.00015,
        help="Commission per side (default: 0.00015 = 0.015%%)",
    )
    parser.add_argument(
        "--walk-forward",
        action="store_true",
        help="Run walk-forward validation (IS/OOS split)",
    )
    parser.add_argument(
        "--is-ratio",
        type=float,
        default=0.7,
        help="In-sample ratio for walk-forward (default: 0.7 = 70%%)",
    )
    parser.add_argument(
        "--universe",
        choices=["sp500_full", "ndx_full", "kospi_full"],
        help="Universe for dynamic rebalancing (e.g., sp500_full)",
    )
    parser.add_argument(
        "--rebalance-days",
        type=int,
        default=14,
        help="Rebalancing interval in trading days (default: 14)",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=15,
        help="Number of top stocks to select per rebalance (default: 15)",
    )

    args = parser.parse_args()

    # 시나리오 목록 출력
    if args.list_scenarios:
        _list_scenarios(args.market)
        return

    market_cfg = MARKET_CONFIG[args.market]
    currency_symbol = market_cfg["currency_symbol"]

    # 전체 시나리오 실행
    if args.all_scenarios or args.compare:
        applicable = get_scenarios_for_market(args.market)
        if not applicable:
            print(f"No scenarios available for market '{args.market}'")
            sys.exit(1)

        print(f"\n🎯 Running {len(applicable)} scenarios for {args.market.upper()}...\n")
        results: Dict[str, ExtendedMetrics] = {}

        for scenario_id, scenario in applicable.items():
            try:
                bt = HistoricalBacktester(
                    market=args.market,
                    scenario=scenario_id,
                    initial_capital=args.capital,
                    slippage_pct=args.slippage,
                    commission_pct=args.commission,
                )
                result = bt.run()
                results[scenario_id] = result

                reporter = ReportGenerator(
                    result=result,
                    scenario=scenario,
                    market=args.market,
                    currency_symbol=currency_symbol,
                    output_dir=args.output,
                )
                reporter.print_summary()
                reporter.export_csv()
                if not args.no_charts:
                    reporter.plot_charts()

            except Exception as e:
                print(f"\n❌ Scenario '{scenario_id}' failed: {e}\n")
                continue

        # 비교표
        if args.compare and len(results) >= 2:
            ReportGenerator.compare_scenarios(results, args.market)

    else:
        # Walk-Forward Validation
        if args.walk_forward:
            from backtest.walk_forward import WalkForwardValidator, print_walk_forward_summary

            if not args.start or not args.end:
                print("❌ Walk-forward requires --start and --end dates (YYYYMMDD)")
                sys.exit(1)

            wfv = WalkForwardValidator(
                market=args.market,
                start_date=args.start,
                end_date=args.end,
                is_ratio=args.is_ratio,
                initial_capital=args.capital,
                slippage_pct=args.slippage,
                commission_pct=args.commission,
            )
            wf_result = wfv.run()
            print_walk_forward_summary(wf_result, currency_symbol)
            return

        # 단일 시나리오 실행
        try:
            bt = HistoricalBacktester(
                market=args.market,
                scenario=args.scenario,
                start_date=args.start or "",
                end_date=args.end or "",
                initial_capital=args.capital,
                slippage_pct=args.slippage,
                commission_pct=args.commission,
                universe=args.universe,
                rebalance_days=args.rebalance_days,
                top_n=args.top_n,
            )
            result = bt.run()

            reporter = ReportGenerator(
                result=result,
                scenario=bt.scenario,
                market=args.market,
                currency_symbol=currency_symbol,
                output_dir=args.output,
            )
            reporter.print_summary()
            reporter.export_csv()
            if not args.no_charts:
                reporter.plot_charts()

        except Exception as e:
            print(f"\n❌ Backtest failed: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)


def _list_scenarios(market: str):
    """사용 가능한 시나리오 목록 출력."""
    print(f"\n📋 Available Scenarios for {market.upper()}:\n")
    print(f"  {'ID':<25} {'Name':<30} {'Period':<25} {'Character'}")
    print(f"  {'─'*90}")

    applicable = get_scenarios_for_market(market)
    if not applicable:
        all_scenarios = SCENARIOS
        print(f"  (No market-specific scenarios. Showing all:)")
        applicable = all_scenarios

    for sid, s in applicable.items():
        period = f"{s.start_date[:4]}-{s.start_date[4:6]} ~ {s.end_date[:4]}-{s.end_date[4:6]}"
        markets = ", ".join(s.markets)
        marker = "✓" if market in s.markets else " "
        print(f"  {marker} {sid:<23} {s.name:<28} {period:<23} {s.character}")

    print(f"\n  Usage: python -m backtest.run --market {market} --scenario <ID>\n")


if __name__ == "__main__":
    main()
