#!/usr/bin/env python3
"""
Phase J4-J5: optimizer 결과의 best_params 를 config.yaml에 안전 승격.

Usage:
    python3 backend/scripts/promote_best_params.py --result data_store/optimizer_results/20250521_120000_sp500_quick.json
    python3 backend/scripts/promote_best_params.py --result <path> --dry-run

게이트:
  1. result.best_objective > 0 (그 자체로 robustness_floor 통과한 것)
  2. baseline alpha 와 비교 시 개선 ≥ ALPHA_IMPROVEMENT_MIN (0.005 = 0.5%p)
  3. result.best_trial.robustness ≥ ROBUSTNESS_MIN (0.7)

수동 정책:
- 백업: config.yaml.backup.{timestamp}
- 변경 로그: data_store/promotion_log.jsonl (append-only)
- Kill switch: data_store/auto_iterate.disabled 파일 존재 시 즉시 종료
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from typing import Any, Dict, Optional

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(THIS_DIR)
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)

CONFIG_PATH = os.path.join(PROJECT_ROOT, "config.yaml")
LOG_PATH = os.path.join(PROJECT_ROOT, "data_store", "promotion_log.jsonl")
KILL_SWITCH = os.path.join(PROJECT_ROOT, "data_store", "auto_iterate.disabled")

ALPHA_IMPROVEMENT_MIN = 0.005   # 0.5%p
ROBUSTNESS_MIN = 0.7


def _kill_switch_active() -> bool:
    return os.path.exists(KILL_SWITCH)


def _backup_config() -> str:
    """config.yaml 백업 후 백업 경로 반환."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{CONFIG_PATH}.backup.{timestamp}"
    if os.path.exists(CONFIG_PATH):
        shutil.copy2(CONFIG_PATH, backup_path)
    return backup_path


def _append_log(entry: Dict[str, Any]):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _evaluate_gate(result: Dict[str, Any], baseline_alpha: Optional[float] = None) -> tuple:
    """승격 게이트 평가. (passed, reason)"""
    best = result.get("best_trial") or {}
    if not best:
        return (False, "no_best_trial")
    if best.get("objective", 0.0) <= 0:
        return (False, "objective_zero_or_negative")
    rob = best.get("robustness", 0.0)
    if rob < ROBUSTNESS_MIN:
        return (False, f"robustness_below_min ({rob:.2f} < {ROBUSTNESS_MIN})")
    alpha = best.get("alpha", 0.0)
    if baseline_alpha is not None and (alpha - baseline_alpha) < ALPHA_IMPROVEMENT_MIN:
        return (False, f"alpha_improvement_too_small "
                       f"(Δ{(alpha - baseline_alpha):+.4f} < {ALPHA_IMPROVEMENT_MIN})")
    return (True, "ok")


def _apply_params_to_config(params: Dict[str, Any], dry_run: bool) -> Dict[str, Any]:
    """
    config.yaml에 params를 적용.

    현재 구현: 시범 — 파라미터를 yaml에 새 키 `auto_iterate_overrides` 아래 기록.
    엔진은 향후 환경변수 `ATS_OPT_*`를 우선 사용.

    Returns:
        {"applied": [...], "skipped": [...]}
    """
    if dry_run:
        return {"applied": list(params.keys()), "skipped": [], "dry_run": True}

    import yaml  # noqa: WPS433
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    else:
        cfg = {}

    cfg["auto_iterate_overrides"] = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "params": params,
    }

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, sort_keys=False, allow_unicode=True)

    return {"applied": list(params.keys()), "skipped": []}


def main():
    parser = argparse.ArgumentParser(description="Promote optimizer best_params to config.yaml")
    parser.add_argument("--result", required=True, help="optimizer_results/*.json 경로")
    parser.add_argument("--baseline-alpha", type=float, default=None,
                        help="이전 baseline alpha (annualized). 지정 시 개선폭 게이트 적용.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true",
                        help="게이트 무시 (위험!)")
    args = parser.parse_args()

    if _kill_switch_active():
        print(f"⚠ Kill switch active: {KILL_SWITCH}")
        sys.exit(2)

    if not os.path.exists(args.result):
        print(f"✗ Result file not found: {args.result}")
        sys.exit(1)

    with open(args.result, "r", encoding="utf-8") as f:
        result = json.load(f)

    passed, reason = _evaluate_gate(result, baseline_alpha=args.baseline_alpha)
    print(f"Gate: {'PASS' if passed else 'FAIL'} | reason={reason}")

    if not passed and not args.force:
        _append_log({
            "timestamp": datetime.now().isoformat(),
            "result_file": args.result,
            "market": result.get("market"),
            "decision": "skipped",
            "reason": reason,
            "best_objective": result.get("best_objective"),
        })
        print("→ Skipped (use --force to override)")
        sys.exit(0)

    best_params = result.get("best_params") or {}
    if not best_params:
        print("✗ No best_params in result.")
        sys.exit(1)

    backup_path = "" if args.dry_run else _backup_config()
    applied = _apply_params_to_config(best_params, dry_run=args.dry_run)

    _append_log({
        "timestamp": datetime.now().isoformat(),
        "result_file": args.result,
        "market": result.get("market"),
        "decision": "promoted" if not args.dry_run else "dry_run",
        "reason": reason,
        "best_objective": result.get("best_objective"),
        "best_params": best_params,
        "applied": applied,
        "config_backup": backup_path,
    })

    print(f"✓ {'DRY-RUN' if args.dry_run else 'PROMOTED'} — params applied: {applied}")
    if backup_path:
        print(f"  Backup: {backup_path}")


if __name__ == "__main__":
    main()
