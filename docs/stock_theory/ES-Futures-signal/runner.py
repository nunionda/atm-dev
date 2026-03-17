"""
ES Futures Signal Bot — runner.py
Orchestrates the full pipeline on a 5-minute schedule.

Usage:
    python runner.py                   # live mode
    python runner.py --backtest 7      # back-test last 7 days
    python runner.py --once            # run once and exit
"""
import argparse
import sys
import traceback
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd

try:
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.interval   import IntervalTrigger
except ImportError:
    print("Install APScheduler:  pip install apscheduler")
    sys.exit(1)

import config         as C
import signal_engine  as SE
import exit_engine    as EE
import position_sizer as PS
import slack_notifier as SN


# ─── Minimal in-memory state (replace with DB for production) ───────────────
class PositionState:
    open:          bool = False
    direction:     str  = "FLAT"
    entry_price:   float = 0.0
    entry_time:    pd.Timestamp = None
    stop_loss:     float = 0.0
    take_profit:   float = 0.0
    high_water:    float = 0.0   # highest (long) / lowest (short) since entry
    contracts:     int   = 0
    contract_type: str   = C.CONTRACT_TYPE

_state = PositionState()


# ─── Core pipeline ──────────────────────────────────────────────────────────
def run_once(verbose: bool = True) -> dict:
    result = {"timestamp": datetime.now().isoformat(), "action": "none"}
    try:
        df = SE.fetch_bars()

        # ── EXIT check (if in a position) ──────────────────────────────
        if _state.open:
            pos = PS.PositionSize(
                contracts=_state.contracts,
                risk_dollars=0, risk_pct=0,
                contract_type=_state.contract_type, notional=0
            )
            # Update high-water mark
            close = float(df["close"].iloc[-1])
            if _state.direction == "LONG":
                _state.high_water = max(_state.high_water, close)
            else:
                _state.high_water = min(_state.high_water, close)

            exit_sig = EE.evaluate_exit(
                df            = df,
                entry_price   = _state.entry_price,
                direction     = _state.direction,
                entry_time    = _state.entry_time,
                highest_price = _state.high_water,
            )
            if exit_sig:
                ok = SN.send_exit_alert(exit_sig, _state.entry_price,
                                        _state.direction, pos)
                _log(f"EXIT [{exit_sig.exit_id}] pnl={exit_sig.pnl_pct:+.2f}%"
                     f"  slack={'ok' if ok else 'fail'}")
                _state.open = False
                result["action"] = f"exit:{exit_sig.exit_id}"
                return result

        # ── ENTRY check ────────────────────────────────────────────────
        if not _state.open:
            sig = SE.evaluate_entry(df)
            _log(f"score={sig.score.total:.0f}/100 dir={sig.direction}"
                 f" fired={sig.fired}"
                 + (f" blocked:{sig.score.filter_reason}" if sig.score.filtered else ""))

            if sig.fired:
                pos = PS.calculate_size(sig.entry_price, sig.stop_loss)
                ok  = SN.send_entry_alert(sig, pos)

                # Update state
                _state.open          = True
                _state.direction     = sig.direction
                _state.entry_price   = sig.entry_price
                _state.entry_time    = sig.timestamp
                _state.stop_loss     = sig.stop_loss
                _state.take_profit   = sig.take_profit
                _state.high_water    = sig.entry_price
                _state.contracts     = pos.contracts
                _state.contract_type = pos.contract_type

                _log(f"ENTRY {sig.direction} @ {sig.entry_price:.2f}"
                     f"  SL={sig.stop_loss:.2f} TP={sig.take_profit:.2f}"
                     f"  {pos.contracts}ct  slack={'ok' if ok else 'fail'}")
                result["action"] = f"entry:{sig.direction}"

    except Exception as e:
        err = traceback.format_exc()
        _log(f"ERROR: {e}", level="ERROR")
        SN.send_error(err)
        result["action"] = f"error:{e}"

    return result


# ─── Backtest (simple signal-only scan) ─────────────────────────────────────
def run_backtest(days: int = 7):
    print(f"\n{'─'*60}")
    print(f"  Backtest mode  |  last {days} days  |  {C.ES_TICKER}")
    print(f"{'─'*60}")

    df_full = SE.fetch_bars(days=max(days + 30, 60))   # extra buffer for indicators
    cutoff  = df_full.index[-1] - pd.Timedelta(days=days)
    signals = 0

    for i in range(200, len(df_full)):
        slice_df = df_full.iloc[:i]
        if slice_df.index[-1] < cutoff:
            continue
        sig = SE.evaluate_entry(slice_df)
        if sig.fired:
            signals += 1
            print(f"  [{sig.timestamp}]  {sig.direction:5s}  "
                  f"score={sig.score.total:.0f}  entry={sig.entry_price:.2f}  "
                  f"SL={sig.stop_loss:.2f}  TP={sig.take_profit:.2f}  "
                  f"R:R={sig.rr_ratio:.2f}")

    print(f"\n  총 신호: {signals}건  (마지막 {days}일)")


# ─── Helpers ────────────────────────────────────────────────────────────────
def _log(msg: str, level: str = "INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [{level}] {msg}")


# ─── Entry point ────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="ES Futures Signal Bot")
    parser.add_argument("--once",      action="store_true", help="Run once and exit")
    parser.add_argument("--backtest",  type=int, metavar="DAYS",
                        help="Signal-only backtest for N days")
    args = parser.parse_args()

    if args.backtest:
        run_backtest(args.backtest)
        return

    if args.once:
        run_once()
        return

    # ── Live scheduler ──────────────────────────────────────────────────
    scheduler = BlockingScheduler(timezone="America/New_York")
    scheduler.add_job(
        func    = run_once,
        trigger = IntervalTrigger(minutes=C.SCHEDULE_MIN),
        id      = "es_signal",
        name    = "ES Signal Scanner",
        misfire_grace_time = 60,
        coalesce           = True,
    )

    _log(f"ES Signal Bot 시작  —  {C.SCHEDULE_MIN}분 간격  [{C.ES_TICKER}]")
    SN.send_heartbeat("🚀  ES Signal Bot 시작됨  |  스케줄: 5분 간격")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        _log("봇 종료")
        SN.send_heartbeat("🛑  ES Signal Bot 종료됨")


if __name__ == "__main__":
    main()
