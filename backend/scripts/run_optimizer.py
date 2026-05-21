#!/usr/bin/env python3
"""
Phase J4: 파라미터 옵티마이저 CLI 진입점.

Usage:
    python3 backend/scripts/run_optimizer.py --market sp500 --quick
    python3 backend/scripts/run_optimizer.py --market all --quick --max-trials 5
    python3 backend/scripts/run_optimizer.py --market kospi --start 20220101 --end 20231231

Options:
    --market       sp500 | kospi | ndx | all (병렬 실행)
    --start/--end  YYYYMMDD (default: 최근 2년)
    --quick        3-파라미터 그리드 (default)
    --full         전체 그리드
    --max-trials   디버그용 상한 (default: 무제한)
    --dry-run      실제 BT 실행하지 않고 grid만 출력
    --is-ratio     walk-forward IS 비율 (default 0.7)
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta

# backend/ 패키지 경로
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(THIS_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from backtest.optimizer import ParameterOptimizer, QUICK_GRIDS, FULL_GRIDS


def _default_dates() -> tuple:
    """기본 백테스트 기간: 최근 2년."""
    today = datetime.now()
    end = today.strftime("%Y%m%d")
    start = (today - timedelta(days=730)).strftime("%Y%m%d")
    return start, end


def main():
    parser = argparse.ArgumentParser(description="ATS Parameter Optimizer")
    parser.add_argument("--market", default="sp500",
                        choices=["sp500", "kospi", "ndx", "nasdaq", "all"])
    parser.add_argument("--start", default=None, help="YYYYMMDD")
    parser.add_argument("--end", default=None, help="YYYYMMDD")
    parser.add_argument("--mode", default="quick", choices=["quick", "full"])
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--max-trials", type=int, default=None)
    parser.add_argument("--is-ratio", type=float, default=0.7)
    parser.add_argument("--robustness-floor", type=float, default=0.5)
    parser.add_argument("--index-source", default="futures", choices=["futures", "spot"])
    parser.add_argument("--strategy-mode", default="multi")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    # mode 결정
    mode = "full" if args.full else "quick"

    # dates
    default_start, default_end = _default_dates()
    start = args.start or default_start
    end = args.end or default_end

    if args.dry_run:
        grids = QUICK_GRIDS if mode == "quick" else FULL_GRIDS
        from itertools import product
        names = [g.name for g in grids]
        values = [g.values for g in grids]
        n = 1
        for v in values:
            n *= len(v)
        print(f"[DRY-RUN] mode={mode} grid={names} → {n} 조합")
        for combo in product(*values):
            print("  -", {k: v for k, v in zip(names, combo)})
        return

    markets = ["sp500", "kospi", "ndx"] if args.market == "all" else [args.market]
    for mkt in markets:
        opt = ParameterOptimizer(
            market=mkt,
            start_date=start,
            end_date=end,
            strategy_mode=args.strategy_mode,
            index_source=args.index_source,
            is_ratio=args.is_ratio,
            robustness_floor=args.robustness_floor,
        )
        opt.run(mode=mode, max_trials=args.max_trials)


if __name__ == "__main__":
    main()
