"""
SP500 4-Layer vs Turtle Donchian — 4종목 직접 비교 (6개월 backtest).
"""
from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request

import argparse

BASE = "http://localhost:8000/api/v1"
TICKERS = ["ES=F", "NQ=F", "CL=F", "GC=F"]
MICRO_MAP = {"ES=F": "MES=F", "NQ=F": "MNQ=F", "CL=F": "MCL=F", "GC=F": "MGC=F"}


def run(ticker: str, strategy: str, is_micro: bool = False) -> dict:
    params = {
        "ticker": ticker, "start_date": "20251101", "end_date": "20260520",
        "equity": 100000, "is_micro": str(is_micro).lower(), "strategy_type": strategy,
    }
    url = f"{BASE}/futures/backtest?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            d = json.loads(r.read().decode())
    except Exception as e:
        return {"err": str(e)}
    m = d.get("metrics", {})
    return {
        "trades": m.get("total_trades", 0),
        "long": m.get("long_trades", 0),
        "short": m.get("short_trades", 0),
        "return_pct": m.get("total_return_pct", 0),
        "mdd_pct": m.get("max_drawdown_pct", 0),
        "sharpe": m.get("sharpe_ratio", 0),
        "win_rate": m.get("win_rate", 0),
        "pf": m.get("profit_factor", 0),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--micro", action="store_true", help="Use Micro contracts (5x smaller)")
    args = ap.parse_args()
    print("=" * 100)
    print(f"SP500 4-Layer vs Turtle Donchian — 4종목 × 6개월 backtest 비교 ({'Micro' if args.micro else 'Full'} contracts)")
    print("=" * 100)
    print(f"{'Ticker':<8} {'Strategy':<10} {'Trd':<5} {'L/S':<8} {'Return%':<9} {'MDD%':<8} {'Sharpe':<7} {'WR%':<7} {'PF':<5}")
    print("-" * 80)

    for ticker in TICKERS:
        for strat in ("sp500", "turtle"):
            print(f"  Running {ticker} × {strat} ...", end="\r", file=sys.stderr)
            r = run(ticker, strat, is_micro=args.micro)
            if "err" in r:
                print(f"{ticker:<8} {strat:<10} ERROR: {r['err'][:50]}")
            else:
                ls = f"{r['long']}/{r['short']}"
                print(f"{ticker:<8} {strat:<10} {r['trades']:<5} {ls:<8} "
                      f"{r['return_pct']:<9.2f} {r['mdd_pct']:<8.2f} "
                      f"{r['sharpe']:<7.2f} {r['win_rate']:<7.1f} {r['pf']:<5.2f}")
        print("-" * 80)


if __name__ == "__main__":
    main()
