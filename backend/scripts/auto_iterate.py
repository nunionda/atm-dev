#!/usr/bin/env python3
"""
Phase J5: CI/cron 자가 반복 루프.

전체 사이클:
  1. data refresh (선물 + spot OHLCV 캐시 갱신)
  2. baseline backtest (현재 config 그대로)
  3. optimizer 실행 (quick grid)
  4. walk-forward IS/OOS 검증 (optimizer 내부 통합)
  5. promotion 게이트 평가
  6. config.yaml 승격 (게이트 통과 시)
  7. 결과 journal + telegram 알림

Usage:
    python3 backend/scripts/auto_iterate.py --market all --mode quick
    python3 backend/scripts/auto_iterate.py --market sp500 --dry-run

Cron 권장:
    0 2 * * 0 cd /path/to/atm-dev && python3 backend/scripts/auto_iterate.py --market all
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(THIS_DIR)
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

JOURNAL_PATH = os.path.join(PROJECT_ROOT, "data_store", "auto_iterate_log.jsonl")
KILL_SWITCH = os.path.join(PROJECT_ROOT, "data_store", "auto_iterate.disabled")
PROMOTE_SCRIPT = os.path.join(BACKEND_DIR, "scripts", "promote_best_params.py")


def _kill_switch_active() -> bool:
    return os.path.exists(KILL_SWITCH)


def _journal(entry: Dict[str, Any]):
    os.makedirs(os.path.dirname(JOURNAL_PATH), exist_ok=True)
    with open(JOURNAL_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _notify_telegram(message: str) -> None:
    """Telegram 알림 시도 — 설정 없으면 skip."""
    try:
        from data.config_manager import ConfigManager
        from infra.notifier.telegram_notifier import TelegramNotifier
        cfg = ConfigManager().load()
        notifier_cfg = cfg.notifier if hasattr(cfg, "notifier") else None
        if not notifier_cfg:
            return
        n = TelegramNotifier(notifier_cfg)
        n.send_message(message, level="INFO")
    except Exception as e:
        print(f"  ⚠ Telegram 알림 실패 (무시): {e}")


def _run_baseline_backtest(market: str, start: str, end: str) -> Optional[Dict[str, Any]]:
    """현재 config 기준 baseline 백테스트. alpha/IR 결과 반환."""
    from backtest.historical_engine import HistoricalBacktester
    try:
        bt = HistoricalBacktester(
            market=market,
            scenario="custom",
            start_date=start,
            end_date=end,
            strategy_mode="multi",
            index_source="futures",
        )
        result = bt.run()
        return {
            "sharpe_ratio": float(result.sharpe_ratio),
            "cagr":         float(result.cagr),
            "alpha":        float(result.alpha),
            "information_ratio": float(result.information_ratio),
            "max_drawdown": float(result.max_drawdown),
        }
    except Exception as e:
        print(f"  ✗ baseline backtest 실패: {e}")
        return None


def _run_optimizer_subprocess(
    market: str,
    start: str,
    end: str,
    mode: str,
    max_trials: Optional[int],
) -> Optional[str]:
    """옵티마이저 subprocess 실행 → 결과 파일 경로 반환."""
    cmd = [
        sys.executable,
        os.path.join(BACKEND_DIR, "scripts", "run_optimizer.py"),
        "--market", market,
        "--start", start,
        "--end", end,
        "--mode", mode,
    ]
    if max_trials:
        cmd += ["--max-trials", str(max_trials)]

    print(f"  → optimizer subprocess: {' '.join(cmd)}")
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3 * 3600)
    if proc.returncode != 0:
        print(f"  ✗ optimizer 실패 (rc={proc.returncode}): {proc.stderr[:500]}")
        return None

    # 가장 최근 결과 파일 찾기
    results_dir = os.path.join(PROJECT_ROOT, "data_store", "optimizer_results")
    if not os.path.exists(results_dir):
        return None
    candidates = sorted(
        [f for f in os.listdir(results_dir) if f.endswith(f"_{market}_{mode}.json")],
        reverse=True,
    )
    if not candidates:
        return None
    return os.path.join(results_dir, candidates[0])


def _promote(result_file: str, baseline_alpha: Optional[float], dry_run: bool) -> Dict[str, Any]:
    """promote_best_params.py 호출 → decision dict 반환."""
    cmd = [sys.executable, PROMOTE_SCRIPT, "--result", result_file]
    if baseline_alpha is not None:
        cmd += ["--baseline-alpha", str(baseline_alpha)]
    if dry_run:
        cmd.append("--dry-run")

    proc = subprocess.run(cmd, capture_output=True, text=True)
    stdout = proc.stdout.strip()
    print(f"  promote.py stdout:\n{stdout}")
    return {
        "returncode": proc.returncode,
        "stdout": stdout,
        "stderr": proc.stderr.strip(),
    }


def run_cycle(
    market: str,
    start: str,
    end: str,
    mode: str = "quick",
    max_trials: Optional[int] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """단일 마켓 사이클."""
    cycle_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{market}"
    print(f"\n{'='*60}")
    print(f"  AUTO-ITERATE CYCLE: {cycle_id}")
    print(f"  Market: {market} | Period: {start} ~ {end} | Mode: {mode}")
    print(f"{'='*60}\n")

    entry: Dict[str, Any] = {
        "cycle_id": cycle_id,
        "timestamp": datetime.now().isoformat(),
        "market": market,
        "start": start,
        "end": end,
        "mode": mode,
        "dry_run": dry_run,
    }

    # ── 1. Baseline ──
    print("[1/3] Baseline backtest...")
    baseline = _run_baseline_backtest(market, start, end)
    entry["baseline"] = baseline
    baseline_alpha = baseline.get("alpha") if baseline else None

    # ── 2. Optimizer ──
    print("[2/3] Optimizer...")
    result_file = _run_optimizer_subprocess(market, start, end, mode, max_trials)
    entry["optimizer_result_file"] = result_file
    if not result_file:
        entry["decision"] = "optimizer_failed"
        _journal(entry)
        _notify_telegram(f"[{market}] auto-iterate FAILED (optimizer)")
        return entry

    # ── 3. Promotion ──
    print("[3/3] Promotion gate...")
    promote_dec = _promote(result_file, baseline_alpha, dry_run)
    entry["promotion"] = promote_dec

    decision = "promoted" if (promote_dec["returncode"] == 0 and "PROMOTED" in promote_dec["stdout"]) else (
        "dry_run" if (promote_dec["returncode"] == 0 and "DRY-RUN" in promote_dec["stdout"]) else "skipped"
    )
    entry["decision"] = decision

    _journal(entry)

    # Telegram 알림
    summary = (
        f"[{market}] auto-iterate: {decision.upper()}\n"
        f"baseline_alpha={baseline_alpha}\n"
        f"result={os.path.basename(result_file or '')}"
    )
    _notify_telegram(summary)

    print(f"\n{'='*60}")
    print(f"  ✓ Cycle done: {decision}")
    print(f"{'='*60}\n")
    return entry


def _default_dates() -> tuple:
    today = datetime.now()
    end = today.strftime("%Y%m%d")
    start = (today - timedelta(days=730)).strftime("%Y%m%d")
    return start, end


def main():
    parser = argparse.ArgumentParser(description="ATS Auto-Iterate Cycle")
    parser.add_argument("--market", default="sp500",
                        choices=["sp500", "kospi", "ndx", "nasdaq", "all"])
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    parser.add_argument("--mode", default="quick", choices=["quick", "full"])
    parser.add_argument("--max-trials", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true",
                        help="Promotion 시 config.yaml에 적용하지 않음 (저널만)")
    args = parser.parse_args()

    if _kill_switch_active():
        print(f"⚠ Kill switch active: {KILL_SWITCH} — aborting.")
        sys.exit(2)

    default_start, default_end = _default_dates()
    start = args.start or default_start
    end = args.end or default_end

    markets = ["sp500", "kospi", "ndx"] if args.market == "all" else [args.market]
    results = []
    for mkt in markets:
        results.append(run_cycle(
            market=mkt,
            start=start,
            end=end,
            mode=args.mode,
            max_trials=args.max_trials,
            dry_run=args.dry_run,
        ))

    print("\n=== SUMMARY ===")
    for r in results:
        print(f"  {r['market']}: {r['decision']}")


if __name__ == "__main__":
    main()
