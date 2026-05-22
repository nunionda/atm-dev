"""
Per-ticker intraday backtester spec map.

자산 클래스별로 contract multiplier, tick size, RTH(Regular Trading Hours),
slippage, commission, margin이 다르다. IntradayBacktester가 ES 외 다른 종목에도
의미있게 동작하려면 ticker별로 이 값들을 조회해야 한다.

참고:
- ES/MES: CME E-mini S&P 500, RTH 09:30-16:00 ET, tick 0.25, mult 50/5
- NQ/MNQ: CME E-mini NASDAQ 100, RTH 09:30-16:00 ET, tick 0.25, mult 20/2
- CL/MCL: NYMEX WTI Crude Oil, floor session 09:00-14:30 ET, tick 0.01, mult 1000/100
- GC/MGC: COMEX Gold, floor session 08:20-13:30 ET, tick 0.10, mult 100/10

Margin (IM/MM) 은 CME 공시 기준 추정치 — broker별로 차이 있음.
"""
from __future__ import annotations

from typing import NotRequired, Optional, TypedDict


class IntradaySpec(TypedDict):
    multiplier: float
    tick_size: float
    rth_start: str
    rth_end: str
    slippage_ticks: int
    commission_per_contract: float
    initial_margin: float
    maintenance_margin: float
    # F3: optional EMA period override per ticker (없으면 ic.ema_* fallback)
    # 자산별 세션 길이가 다른 점 보정 — pit 5h대 commodity는 Fibonacci 단축.
    ema_fast: NotRequired[int]
    ema_mid: NotRequired[int]
    ema_slow: NotRequired[int]


# ── Per-ticker spec table ──
INTRADAY_SPECS: dict[str, IntradaySpec] = {
    # ── Equity Index — CME (Regular Trading Hours 09:30-16:00 ET) ──
    "ES=F": {
        "multiplier": 50.0, "tick_size": 0.25,
        "rth_start": "09:30", "rth_end": "16:00",
        "slippage_ticks": 1, "commission_per_contract": 0.62,
        "initial_margin": 15500.0, "maintenance_margin": 13700.0,
    },
    "MES=F": {
        "multiplier": 5.0, "tick_size": 0.25,
        "rth_start": "09:30", "rth_end": "16:00",
        "slippage_ticks": 1, "commission_per_contract": 0.62,
        "initial_margin": 1550.0, "maintenance_margin": 1370.0,
    },
    "NQ=F": {
        "multiplier": 20.0, "tick_size": 0.25,
        "rth_start": "09:30", "rth_end": "16:00",
        "slippage_ticks": 1, "commission_per_contract": 0.62,
        "initial_margin": 21450.0, "maintenance_margin": 19500.0,
    },
    "MNQ=F": {
        "multiplier": 2.0, "tick_size": 0.25,
        "rth_start": "09:30", "rth_end": "16:00",
        "slippage_ticks": 1, "commission_per_contract": 0.62,
        "initial_margin": 2145.0, "maintenance_margin": 1950.0,
    },

    # ── Energy — NYMEX WTI Crude Oil (pit session 09:00-14:30 ET, 5.5h) ──
    # F3: 짧은 세션 보정 — Fibonacci 단축 EMA (5/13/34 ≈ 8/21/55 × 0.625).
    "CL=F": {
        "multiplier": 1000.0, "tick_size": 0.01,
        "rth_start": "09:00", "rth_end": "14:30",
        "slippage_ticks": 1, "commission_per_contract": 0.62,
        "initial_margin": 6336.0, "maintenance_margin": 5760.0,
        "ema_fast": 5, "ema_mid": 13, "ema_slow": 34,
    },
    "MCL=F": {
        "multiplier": 100.0, "tick_size": 0.01,
        "rth_start": "09:00", "rth_end": "14:30",
        "slippage_ticks": 1, "commission_per_contract": 0.62,
        "initial_margin": 633.0, "maintenance_margin": 576.0,
        "ema_fast": 5, "ema_mid": 13, "ema_slow": 34,
    },

    # ── Metal — COMEX Gold (floor session 08:20-13:30 ET, 5.2h) ──
    # F3: 짧은 세션 보정 — Fibonacci 단축 EMA.
    "GC=F": {
        "multiplier": 100.0, "tick_size": 0.10,
        "rth_start": "08:20", "rth_end": "13:30",
        "slippage_ticks": 1, "commission_per_contract": 0.62,
        "initial_margin": 11000.0, "maintenance_margin": 10000.0,
        "ema_fast": 5, "ema_mid": 13, "ema_slow": 34,
    },
    "MGC=F": {
        "multiplier": 10.0, "tick_size": 0.10,
        "rth_start": "08:20", "rth_end": "13:30",
        "slippage_ticks": 1, "commission_per_contract": 0.62,
        "initial_margin": 1100.0, "maintenance_margin": 1000.0,
        "ema_fast": 5, "ema_mid": 13, "ema_slow": 34,
    },
}


def get_intraday_spec(ticker: str) -> Optional[IntradaySpec]:
    """ticker → IntradaySpec dict, 없으면 None (caller가 ic.* fallback 사용)."""
    return INTRADAY_SPECS.get(ticker)


def is_supported_intraday(ticker: str) -> bool:
    """Intraday backtest 지원 ticker인지."""
    return ticker in INTRADAY_SPECS


def list_supported_tickers() -> list[str]:
    """순서 있는 ticker 목록."""
    return list(INTRADAY_SPECS.keys())
