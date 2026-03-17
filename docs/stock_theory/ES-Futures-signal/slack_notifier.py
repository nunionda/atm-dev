"""
ES Futures Signal Bot — slack_notifier.py
Sends entry & exit alerts to Slack via Incoming Webhook.
Uses Block Kit for rich formatting.
"""
import json
import urllib.request
from datetime import datetime
from typing import Optional
import config as C
from signal_engine import SignalResult
from exit_engine   import ExitSignal
from position_sizer import PositionSize


# ─── Emoji helpers ───────────────────────────────────────────────────────────
_DIR_EMOJI = {"LONG": "🟢", "SHORT": "🔴", "FLAT": "⚪"}
_EXIT_EMOJI = {
    "ES1":           "🚨",
    "ES_ATR_SL":     "⛔",
    "ES_ATR_TP":     "✅",
    "ES_CHANDELIER": "🕯️",
    "ES3":           "🔒",
    "ES_CHOCH":      "🔄",
    "ES5":           "⏰",
}


def _score_bar(score: float, total: float = 100.0, width: int = 10) -> str:
    filled = int(score / total * width)
    return "█" * filled + "░" * (width - filled)


def _post(payload: dict) -> bool:
    body = json.dumps(payload).encode()
    req  = urllib.request.Request(
        C.SLACK_WEBHOOK_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status == 200
    except Exception as e:
        print(f"[Slack] POST failed: {e}")
        return False


# ─── Entry alert ─────────────────────────────────────────────────────────────
def send_entry_alert(sig: SignalResult, pos: PositionSize) -> bool:
    dir_e  = _DIR_EMOJI.get(sig.direction, "⚪")
    sc     = sig.score
    ts_str = sig.timestamp.strftime("%Y-%m-%d %H:%M")

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{dir_e}  ES 진입 신호  |  {sig.direction}",
                "emoji": True
            }
        },
        {"type": "divider"},
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Ticker*\n`{sig.ticker}`"},
                {"type": "mrkdwn", "text": f"*시각*\n{ts_str}"},
                {"type": "mrkdwn", "text": f"*진입가*\n`{sig.entry_price:,.2f}`"},
                {"type": "mrkdwn", "text": f"*방향*\n{sig.direction}"},
                {"type": "mrkdwn", "text": f"*손절가*\n`{sig.stop_loss:,.2f}`"},
                {"type": "mrkdwn", "text": f"*익절가*\n`{sig.take_profit:,.2f}`"},
                {"type": "mrkdwn", "text": f"*R:R*\n{sig.rr_ratio:.2f}:1"},
                {"type": "mrkdwn", "text": f"*ATR*\n{sig.atr:.2f}  |  ADX {sig.adx:.1f}"},
            ]
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*4-Layer 스코어  →  {sc.total:.0f} / 100*\n"
                    f"```"
                    f"L1 Z-Score   {_score_bar(sc.l1_zscore, 25)}  {sc.l1_zscore:.0f}/25\n"
                    f"L2 Trend     {_score_bar(sc.l2_trend,  25)}  {sc.l2_trend:.0f}/25\n"
                    f"L3 Momentum  {_score_bar(sc.l3_momentum,25)} {sc.l3_momentum:.0f}/25\n"
                    f"L4 Volume    {_score_bar(sc.l4_volume, 25)}  {sc.l4_volume:.0f}/25\n"
                    f"{'─'*38}\n"
                    f"TOTAL        {_score_bar(sc.total)}  {sc.total:.0f}/100"
                    f"```"
                )
            }
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn",
                 "text": f"*포지션 사이징 (Kelly)*\n`{pos.contracts}` contracts ({pos.contract_type})"},
                {"type": "mrkdwn",
                 "text": f"*리스크*\n${pos.risk_dollars:,.0f}  ({pos.risk_pct:.2f}%)"},
                {"type": "mrkdwn",
                 "text": f"*명목가치*\n${pos.notional:,.0f}"},
                {"type": "mrkdwn",
                 "text": f"*노트*\n{sig.note}"},
            ]
        },
        {
            "type": "context",
            "elements": [
                {"type": "mrkdwn",
                 "text": f"ES Signal Bot  •  임계값 {C.ENTRY_THRESHOLD}pt  •  {ts_str}"}
            ]
        }
    ]

    return _post({"blocks": blocks})


# ─── Exit alert ──────────────────────────────────────────────────────────────
def send_exit_alert(exit_sig: ExitSignal,
                    entry_price: float,
                    direction: str,
                    pos: PositionSize) -> bool:
    emoji    = _EXIT_EMOJI.get(exit_sig.exit_id, "⚠️")
    pnl_sign = "+" if exit_sig.pnl_pct >= 0 else ""
    ts_str   = datetime.now().strftime("%Y-%m-%d %H:%M")

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{emoji}  ES 청산 신호  |  {exit_sig.exit_id}",
                "emoji": True
            }
        },
        {"type": "divider"},
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*청산 ID*\n`{exit_sig.exit_id}`  (P{exit_sig.priority})"},
                {"type": "mrkdwn", "text": f"*방향*\n{direction}"},
                {"type": "mrkdwn", "text": f"*진입가*\n`{entry_price:,.2f}`"},
                {"type": "mrkdwn", "text": f"*청산가*\n`{exit_sig.exit_price:,.2f}`"},
                {"type": "mrkdwn", "text": f"*손익*\n`{pnl_sign}{exit_sig.pnl_pct:.2f}%`"},
                {"type": "mrkdwn", "text": f"*계약수*\n{pos.contracts} ({pos.contract_type})"},
            ]
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn",
                     "text": f"*사유*\n{exit_sig.reason}"}
        },
        {
            "type": "context",
            "elements": [
                {"type": "mrkdwn",
                 "text": f"ES Signal Bot  •  청산 우선순위 {exit_sig.priority}/7  •  {ts_str}"}
            ]
        }
    ]

    return _post({"blocks": blocks})


# ─── Heartbeat / health check ─────────────────────────────────────────────────
def send_heartbeat(msg: str = "ES Signal Bot 정상 동작 중 ✅") -> bool:
    return _post({"text": msg})


# ─── Error alert ──────────────────────────────────────────────────────────────
def send_error(error: str) -> bool:
    return _post({"text": f"⚠️  *ES Signal Bot 오류*\n```{error}```"})
