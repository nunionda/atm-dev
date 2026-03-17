"""
ES Futures Signal Bot — config.py
All tunable parameters in one place.
"""
from dataclasses import dataclass, field
from typing import Optional

# ─── Slack ─────────────────────────────────────────────────────────────────
SLACK_WEBHOOK_URL = "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
SLACK_CHANNEL     = "#es-signals"          # optional (webhook already knows)

# ─── Data ───────────────────────────────────────────────────────────────────
ES_TICKER       = "ES=F"                   # yfinance ticker
INTERVAL        = "5m"                     # candle interval
LOOKBACK_DAYS   = 30                       # bars to pull on each run
SCHEDULE_MIN    = 5                        # APScheduler cadence (minutes)

# ─── Signal thresholds ──────────────────────────────────────────────────────
ENTRY_THRESHOLD = 60                       # minimum score to fire a signal
ZSCORE_LONG     = -2.0                     # z ≤ this → long candidate
ZSCORE_SHORT    =  2.0                     # z ≥ this → short candidate

# ─── Exit parameters ────────────────────────────────────────────────────────
HARD_SL_PCT     = 0.03                     # ES1  hard stop -3 %
ATR_SL_MULT_TRENDING = 1.5                 # ES_ATR_SL when ADX ≥ 25
ATR_SL_MULT_RANGING  = 2.0                 # ES_ATR_SL when ADX < 25
ATR_TP_MULT     = 3.0                      # ES_ATR_TP take-profit
RR_MIN          = 2.0                      # minimum R:R to place trade
CHANDELIER_MULT = 3.0                      # ES_CHANDELIER multiplier
TRAIL_ACTIVATE  = 0.02                     # progressive trail activation +2 %
MAX_HOLD_DAYS   = 20                       # ES5 max holding period

# ─── Position sizing ────────────────────────────────────────────────────────
EQUITY          = 100_000                  # account equity USD
RISK_PCT        = 0.015                    # Kelly fraction (1.5 %)
EMINI_MULT      = 50                       # E-mini $/point
MICRO_MULT      = 5                        # Micro ES $/point
CONTRACT_TYPE   = "emini"                  # "emini" | "micro"

# ─── Indicator periods ──────────────────────────────────────────────────────
ZSCORE_PERIOD   = 20
EMA_SHORT       = 10
EMA_MED         = 20
EMA_LONG        = 50
MA200           = 200
MACD_FAST       = 12
MACD_SLOW       = 26
MACD_SIGNAL     = 9
ADX_PERIOD      = 14
RSI_PERIOD      = 14
ATR_PERIOD      = 14
BB_PERIOD       = 20
BB_STD          = 2.0
VOL_SPIKE_MULT  = 1.5                      # volume spike threshold
