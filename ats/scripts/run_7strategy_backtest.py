#!/usr/bin/env python3
"""7전략 1년 SP500 배치 백테스트 — Phase C

Usage:
    python3 ats/scripts/run_7strategy_backtest.py
"""
import sys
import json
import os
from datetime import datetime

# 프로젝트 루트 설정
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, "ats"))

from backtest.historical_engine import HistoricalBacktester

STRATEGIES = [
    'multi',
    'regime_strong_bull',
    'regime_bull',
    'regime_neutral',
    'regime_range_bound',
    'regime_bear',
    'regime_crisis',
]

START_DATE = '20250316'
END_DATE = '20260316'
INITIAL_CAPITAL = 100_000.0


def run_one(strategy_mode: str) -> dict:
    bt = HistoricalBacktester(
        market='sp500',
        scenario='custom',
        start_date=START_DATE,
        end_date=END_DATE,
        strategy_mode=strategy_mode,
        initial_capital=INITIAL_CAPITAL,
        top_n=20,
    )
    result = bt.run()
    ps = bt.engine._phase_stats if bt.engine else {}

    return {
        'strategy': strategy_mode,
        'return_pct':    round(result.total_return * 100, 2),
        'cagr_pct':      round(result.cagr * 100, 2),
        'sharpe':        round(result.sharpe_ratio, 3),
        'mdd_pct':       round(result.max_drawdown * 100, 2),
        'win_rate_pct':  round(result.win_rate * 100, 1),
        'profit_factor': round(result.profit_factor, 3),
        'trades':        result.total_trades,
        'mdd_guard':     ps.get('es_mdd_guard', 0) if isinstance(ps, dict) else getattr(ps, 'es_mdd_guard', 0),
        'rg6_blocks':    ps.get('rg6_spy_blocks', 0) if isinstance(ps, dict) else getattr(ps, 'rg6_spy_blocks', 0),
        'p5_conflicts':  ps.get('p5_conflict_reductions', 0) if isinstance(ps, dict) else getattr(ps, 'p5_conflict_reductions', 0),
    }


if __name__ == '__main__':
    today = datetime.now().strftime('%Y%m%d_%H%M')
    results = []

    print(f"\n{'='*60}")
    print(f"  7전략 1년 SP500 백테스트")
    print(f"  기간: {START_DATE} ~ {END_DATE}")
    print(f"  초기 자본: ${INITIAL_CAPITAL:,.0f}")
    print(f"{'='*60}\n")

    for strat in STRATEGIES:
        print(f'▶ Running [{strat}]...')
        try:
            r = run_one(strat)
            results.append(r)
            print(f'  Return {r["return_pct"]:+.1f}%  Sharpe {r["sharpe"]:.3f}  '
                  f'MDD {r["mdd_pct"]:.1f}%  WR {r["win_rate_pct"]:.1f}%  '
                  f'PF {r["profit_factor"]:.3f}  Trades {r["trades"]}')
        except Exception as e:
            import traceback
            print(f'  ERROR: {e}')
            traceback.print_exc()
            results.append({'strategy': strat, 'error': str(e)})

    # 결과 저장
    os.makedirs('data_store', exist_ok=True)
    out_path = f'data_store/backtest_7strat_1yr_{today}.json'
    payload = {
        'run_date': today,
        'start_date': START_DATE,
        'end_date': END_DATE,
        'initial_capital': INITIAL_CAPITAL,
        'results': results,
    }
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    # 요약 출력
    print(f'\n{"="*60}')
    print(f'  결과 요약 (Sharpe 기준 정렬)')
    print(f'{"="*60}')
    valid = [r for r in results if 'error' not in r]
    valid.sort(key=lambda x: x['sharpe'], reverse=True)

    print(f"\n{'전략':<22} {'수익률':>8} {'Sharpe':>8} {'MDD':>8} {'WR':>6} {'PF':>6} {'거래수':>6}")
    print('-' * 70)
    for r in valid:
        print(f"{r['strategy']:<22} {r['return_pct']:>+7.1f}% {r['sharpe']:>8.3f} "
              f"{r['mdd_pct']:>7.1f}% {r['win_rate_pct']:>5.1f}% {r['profit_factor']:>6.3f} {r['trades']:>6}")

    if valid:
        best = valid[0]
        print(f'\n🏆 최고 Sharpe: [{best["strategy"]}] → Sharpe {best["sharpe"]:.3f}, '
              f'Return {best["return_pct"]:+.1f}%, MDD {best["mdd_pct"]:.1f}%')

    print(f'\n✅ 결과 저장: {out_path}')
