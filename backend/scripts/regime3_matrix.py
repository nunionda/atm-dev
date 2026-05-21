#!/usr/bin/env python3
"""
Phase K6: 3-regime 통합 + VIX percentile 강화 검증 매트릭스.

4 config × 3 market = 12 backtest:

| Config | 설명                              |
|--------|-----------------------------------|
| A      | baseline (6레짐, VIX 절대값만)     |
| B      | 3레짐 통합 (VIX 절대값만)          |
| C      | 6레짐 + VIX percentile             |
| D      | 3레짐 + VIX percentile (FULL)      |

Markets: SP500, NASDAQ, KOSPI
Period: 2023-01-01 ~ 2024-12-31 (2년)

Acceptance criteria:
- D config의 Sharpe가 A 대비 -10% 이내 (회귀 없음)
- 각 marker에서 멀티 전략 entries 모두 ≥ 1 (전략 분배 작동)
- 3마켓 모두 BEAR 시간 > 0% (약세 감지 가능)

Usage:
    python3 backend/scripts/regime3_matrix.py --start 20230101 --end 20241231
    python3 backend/scripts/regime3_matrix.py --markets sp500 --quick   # quick: 6개월 (smoke)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from datetime import datetime
from typing import Any, Dict, List

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(THIS_DIR)
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

OUTPUT_DIR = os.path.join(PROJECT_ROOT, "data_store", "regime3_matrix")


def _run_one(market: str, start: str, end: str, use_3regime: bool, vix_percentile: bool) -> Dict[str, Any]:
    """단일 백테스트 — feature flag로 4 config 중 하나 실행."""
    from backtest.historical_engine import HistoricalBacktester

    bt = HistoricalBacktester(
        market=market,
        scenario="custom",
        start_date=start,
        end_date=end,
        initial_capital=100000 if market != "kospi" else 100_000_000,
        strategy_mode="multi",
        index_source="futures",
    )

    # Engine은 run() 내부에서 생성되므로, 우리는 _use_3regime을 사전에 패치할 수 없음.
    # 대신 BT 인스턴스 attr로 전달 → BT.run()이 engine 생성 직후 적용하도록 monkey-patch.
    # 가장 안전한 방식: BT.run() 호출 후 reset 없이 engine 속성을 직접 패치.
    # 하지만 run()이 동기 함수이므로, engine 생성 → run loop 진입 사이에 끼어들 곳이 없다.
    # 해결: 환경변수로 flag 전달, engine init에서 환경변수 체크.

    os.environ["ATS_FORCE_3REGIME"] = "1" if use_3regime else "0"
    os.environ["ATS_FORCE_VIX_PCT"] = "1" if vix_percentile else "0"

    try:
        result = bt.run()
    finally:
        os.environ.pop("ATS_FORCE_3REGIME", None)
        os.environ.pop("ATS_FORCE_VIX_PCT", None)

    # 전략별 entries 카운터 추출
    ps = result.phase_stats
    return {
        "total_return":      round(float(result.total_return) * 100, 2),
        "cagr":              round(float(result.cagr) * 100, 2),
        "sharpe_ratio":      round(float(result.sharpe_ratio), 2),
        "max_drawdown":      round(float(result.max_drawdown) * 100, 2),
        "total_trades":      int(result.total_trades),
        "win_rate":          round(float(result.win_rate) * 100, 1),
        "alpha":             round(float(result.alpha) * 100, 2),
        "beta":              round(float(result.beta), 3),
        "information_ratio": round(float(result.information_ratio), 3),
        "time_in_bull":      round(float(result.time_in_bull_pct), 1),
        "time_in_neutral":   round(float(result.time_in_neutral_pct), 1),
        "time_in_bear":      round(float(result.time_in_bear_pct), 1),
        "smc_entries":       int(ps.smc_entries),
        "mr_entries":        int(ps.mr_entries),
        "brt_entries":       int(ps.brt_retests_entered),
        "arb_entries":       int(ps.arb_entries),
        "defensive_entries": int(getattr(ps, "defensive_entries", 0)),
        "passive_etf_entries": int(getattr(ps, "passive_etf_entries", 0)),
        "defensive_etf_entries": int(getattr(ps, "defensive_etf_entries", 0)),
    }


def run_matrix(markets: List[str], start: str, end: str) -> Dict[str, Any]:
    """전체 매트릭스 실행 — 4 config × len(markets) backtests."""
    configs = [
        ("A_baseline",    False, False),
        ("B_3regime",     True,  False),
        ("C_vix_pct",     False, True),
        ("D_full",        True,  True),
    ]

    print(f"\n{'='*70}")
    print(f"  REGIME3 MATRIX — {len(configs)} configs × {len(markets)} markets = {len(configs)*len(markets)} backtests")
    print(f"  Period: {start} ~ {end}")
    print(f"{'='*70}\n")

    matrix: Dict[str, Dict[str, Any]] = {}
    for cfg_name, use_3regime, vix_pct in configs:
        matrix[cfg_name] = {}
        for mkt in markets:
            print(f"\n--- {cfg_name} / {mkt} ---")
            try:
                metrics = _run_one(mkt, start, end, use_3regime, vix_pct)
                matrix[cfg_name][mkt] = metrics
                print(
                    f"   ✓ ret={metrics['total_return']:+.2f}% "
                    f"sharpe={metrics['sharpe_ratio']:.2f} "
                    f"mdd={metrics['max_drawdown']:+.2f}% "
                    f"trades={metrics['total_trades']}"
                )
            except Exception as e:
                matrix[cfg_name][mkt] = {"error": str(e)[:200]}
                print(f"   ✗ ERROR: {e}")

    return {
        "start": start,
        "end": end,
        "timestamp": datetime.now().isoformat(),
        "matrix": matrix,
    }


def _format_markdown(result: Dict[str, Any]) -> str:
    """매트릭스 결과를 markdown 표로 변환."""
    lines: List[str] = []
    lines.append("# Regime3 Matrix Results\n")
    lines.append(f"Period: {result['start']} ~ {result['end']}\n")
    lines.append(f"Timestamp: {result['timestamp']}\n")

    matrix = result["matrix"]
    metrics_to_show = [
        ("sharpe_ratio",   "Sharpe"),
        ("total_return",   "Return %"),
        ("max_drawdown",   "MDD %"),
        ("alpha",          "Alpha %"),
        ("information_ratio", "IR"),
        ("total_trades",   "Trades"),
        ("win_rate",       "Win %"),
        ("time_in_bear",   "Time BEAR %"),
    ]

    for metric_key, label in metrics_to_show:
        lines.append(f"\n## {label}\n")
        lines.append("| Config | " + " | ".join(matrix[next(iter(matrix))].keys()) + " |")
        lines.append("|--------|" + "|".join(["--------"] * len(matrix[next(iter(matrix))])) + "|")
        for cfg_name in matrix:
            row = [cfg_name]
            for mkt in matrix[cfg_name]:
                v = matrix[cfg_name][mkt].get(metric_key, "—") if isinstance(matrix[cfg_name][mkt], dict) else "—"
                row.append(str(v))
            lines.append("| " + " | ".join(row) + " |")

    # Strategy entry distribution
    lines.append("\n## Strategy Entry Distribution\n")
    entry_keys = [
        ("smc_entries", "SMC"),
        ("mr_entries", "MR"),
        ("brt_entries", "BRT"),
        ("arb_entries", "ARB"),
        ("defensive_entries", "Def"),
        ("passive_etf_entries", "Passive"),
        ("defensive_etf_entries", "DefETF"),
    ]
    for cfg_name in matrix:
        lines.append(f"\n### {cfg_name}\n")
        lines.append("| Market | " + " | ".join(label for _, label in entry_keys) + " |")
        lines.append("|--------|" + "|".join(["----"] * len(entry_keys)) + "|")
        for mkt, m in matrix[cfg_name].items():
            if not isinstance(m, dict) or "error" in m:
                continue
            row = [mkt] + [str(m.get(k, "—")) for k, _ in entry_keys]
            lines.append("| " + " | ".join(row) + " |")

    # Acceptance Gate
    lines.append("\n## Acceptance Gate\n")
    try:
        # D Sharpe vs A Sharpe
        if "A_baseline" in matrix and "D_full" in matrix:
            for mkt in matrix["A_baseline"]:
                a_sharpe = matrix["A_baseline"][mkt].get("sharpe_ratio")
                d_sharpe = matrix["D_full"].get(mkt, {}).get("sharpe_ratio")
                if a_sharpe is not None and d_sharpe is not None and a_sharpe != 0:
                    delta_pct = (d_sharpe - a_sharpe) / abs(a_sharpe) * 100
                    status = "✓" if delta_pct >= -10 else "✗"
                    lines.append(f"- **{mkt}**: A Sharpe {a_sharpe:.2f} → D Sharpe {d_sharpe:.2f} (Δ {delta_pct:+.1f}%) {status}")
    except Exception as e:
        lines.append(f"⚠ gate eval failed: {e}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Regime3 Matrix Backtest")
    parser.add_argument("--start", default="20230101")
    parser.add_argument("--end", default="20241231")
    parser.add_argument("--markets", nargs="+", default=["sp500", "ndx", "kospi"])
    parser.add_argument("--quick", action="store_true", help="6개월 smoke test")
    args = parser.parse_args()

    start = args.start
    end = args.end
    if args.quick:
        start = "20240101"
        end = "20240630"
        print(f"[QUICK MODE] 6개월 smoke test: {start} ~ {end}")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    result = run_matrix(args.markets, start, end)

    # JSON 저장
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = os.path.join(OUTPUT_DIR, f"{timestamp}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # Markdown 리포트
    md_path = os.path.join(OUTPUT_DIR, f"{timestamp}.md")
    md = _format_markdown(result)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)

    print(f"\n{'='*70}")
    print(f"  ✓ Matrix complete.")
    print(f"  JSON: {json_path}")
    print(f"  MD:   {md_path}")
    print(f"{'='*70}\n")
    print(md)


if __name__ == "__main__":
    main()
