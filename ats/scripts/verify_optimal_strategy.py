#!/usr/bin/env python3
"""
마켓별 최적 전략 검증 스크립트.

백테스트 검증으로 확정된 마켓별 최적 설정을 사용하여 성과를 확인한다:
- KOSPI: Top60 + ₩3M 고정사이징 + ES2 제거 + 강화 트레일링
- SP500: Top60 + $3K 고정사이징 + ES2 제거 + 강화 트레일링
- NDX: 기존 전략 유지 (ATR사이징 + ES2 활성)

Usage:
    cd ats && python scripts/verify_optimal_strategy.py
    cd ats && python scripts/verify_optimal_strategy.py --market kospi
    cd ats && python scripts/verify_optimal_strategy.py --start 20230101 --end 20251231
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
from simulation.universe import OPTIMAL_STRATEGY_CONFIG


CURRENCY_SYMBOLS = {"kospi": "₩", "sp500": "$", "ndx": "$"}


def run_optimal_backtest(market: str, start_date: str, end_date: str):
    """마켓별 최적 전략으로 백테스트 실행."""
    cfg = OPTIMAL_STRATEGY_CONFIG[market]
    sym = CURRENCY_SYMBOLS[market]

    print(f"\n{'='*60}")
    print(f"  [{market.upper()}] 최적 전략 백테스트")
    print(f"  전략: {cfg['label']}")
    print(f"  Universe: {cfg['universe']}, Top-N: {cfg['top_n']}")
    if cfg["fixed_amount_per_stock"] > 0:
        print(f"  사이징: 고정 {sym}{cfg['fixed_amount_per_stock']:,.0f}/종목")
    else:
        print(f"  사이징: ATR 리스크 패리티")
    print(f"  ES2: {'비활성' if cfg['disable_es2'] else '활성'}")
    print(f"  자본: {sym}{cfg['initial_capital']:,.0f}")
    print(f"  기간: {start_date} ~ {end_date}")
    print(f"{'='*60}")

    bt = HistoricalBacktester.from_optimal(
        market=market,
        start_date=start_date,
        end_date=end_date,
    )

    start_time = time.time()
    result = bt.run()
    elapsed = time.time() - start_time
    print(f"\n  ⏱ 소요 시간: {elapsed:.1f}초")

    return result


def print_result(market: str, result):
    """단일 마켓 결과 출력."""
    sym = CURRENCY_SYMBOLS[market]
    cfg = OPTIMAL_STRATEGY_CONFIG[market]
    ps = result.phase_stats

    print(f"\n{'='*60}")
    print(f"  📊 {market.upper()} — {cfg['label']}")
    print(f"{'='*60}")
    print(f"  {'지표':<25} {'결과':>20}")
    print(f"  {'-'*47}")
    print(f"  {'총 수익률':<25} {result.total_return:>19.2%}")
    print(f"  {'CAGR':<25} {result.cagr:>19.2%}")
    print(f"  {'Sharpe Ratio':<25} {result.sharpe_ratio:>19.2f}")
    print(f"  {'Sortino Ratio':<25} {result.sortino_ratio:>19.2f}")
    print(f"  {'MDD':<25} {result.max_drawdown:>19.2%}")
    print(f"  {'총 거래 수':<25} {result.total_trades:>19}")
    print(f"  {'승률':<25} {result.win_rate:>18.1%}")
    print(f"  {'Profit Factor':<25} {result.profit_factor:>19.2f}")
    print(f"  {'평균 수익률/건':<25} {result.avg_pnl_pct:>19.2%}")
    print(f"  {'평균 보유일':<25} {result.avg_holding_days:>17.1f}일")
    print(f"  {'최고 수익 거래':<25} {result.best_trade_pct:>19.2%}")
    print(f"  {'최대 연속 손실':<25} {result.max_consecutive_losses:>18}회")
    print(f"  {'최종 자산':<25} {sym}{result.final_value:>17,.0f}")
    print()
    print(f"  {'청산 유형별 통계':<25}")
    print(f"  {'-'*40}")
    print(f"  {'ES1 손절':.<25} {ps.es1_stop_loss:>15}")
    print(f"  {'ES2 익절':.<25} {ps.es2_take_profit:>15}")
    print(f"  {'ES3 트레일링':.<25} {ps.es3_trailing_stop:>15}")
    print(f"  {'ES4 데드크로스':.<25} {ps.es4_dead_cross:>15}")
    print(f"  {'ES5 보유기간':.<25} {ps.es5_max_holding:>15}")
    print(f"  {'ES7 리밸런스':.<25} {ps.es7_rebalance_exit:>15}")
    print()


def main():
    parser = argparse.ArgumentParser(description="마켓별 최적 전략 검증")
    parser.add_argument("--market", choices=["sp500", "ndx", "kospi", "all"], default="all")
    parser.add_argument("--start", default="20240101", help="시작일 (YYYYMMDD)")
    parser.add_argument("--end", default="20251231", help="종료일 (YYYYMMDD)")
    args = parser.parse_args()

    markets = list(OPTIMAL_STRATEGY_CONFIG.keys()) if args.market == "all" else [args.market]

    print("\n" + "=" * 60)
    print("  🏆 마켓별 최적 전략 검증")
    print("  " + "=" * 56)
    for m in markets:
        cfg = OPTIMAL_STRATEGY_CONFIG[m]
        print(f"  {m.upper():>6}: {cfg['label']}")
    print(f"  기간: {args.start} ~ {args.end}")
    print("=" * 60)

    all_results = {}

    for market in markets:
        result = run_optimal_backtest(market, args.start, args.end)
        print_result(market, result)
        all_results[market] = result

    # 전체 요약
    if len(markets) > 1:
        print("\n" + "=" * 70)
        print("  📋 전체 마켓 최적 전략 요약")
        print("=" * 70)
        print(f"  {'마켓':<10} {'전략':<30} {'Return':>10} {'Sharpe':>8} {'MDD':>10} {'PF':>6}")
        print(f"  {'-'*76}")
        for market, result in all_results.items():
            cfg = OPTIMAL_STRATEGY_CONFIG[market]
            strategy = "Top60+Fixed+NoES2" if cfg["disable_es2"] else "Full+ATR+ES2"
            print(
                f"  {market.upper():<10} {strategy:<30} "
                f"{result.total_return:>9.2%} {result.sharpe_ratio:>7.2f} "
                f"{result.max_drawdown:>9.2%} {result.profit_factor:>5.2f}"
            )
        print()

    print("\n✅ 최적 전략 검증 완료!\n")


if __name__ == "__main__":
    main()
