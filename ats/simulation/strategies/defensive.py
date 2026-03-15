"""
Defensive strategy — scan_entries / check_exits.

Extracted from SimulationEngine to keep engine.py smaller.
All logic is identical; `self` is replaced with `engine`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List

import pandas as pd

from simulation.constants import (
    REGIME_OVERRIDES, INVERSE_ETFS, SAFE_HAVEN_ETFS,
)
from simulation.models import SimSignal

if TYPE_CHECKING:
    from simulation.engine import SimulationEngine


def scan_entries(engine: "SimulationEngine"):
    """
    Defensive 전략: BEAR/RANGE_BOUND 레짐 시 인버스 ETF + 안전자산 매수.

    조건:
    - 레짐이 BEAR/CRISIS 또는 (RANGE_BOUND/NEUTRAL AND VIX > threshold)
    - 인버스 ETF / 안전자산 OHLCV 데이터 존재
    - 이미 보유 중이 아닌 것
    """
    # 레짐별 VIX 진입 임계값 (BEAR: 20, 기본: 25)
    _def_ro = REGIME_OVERRIDES.get(engine._market_regime, {})
    vix_threshold = _def_ro.get("defensive_vix_threshold", 25)

    # STRONG_BULL/BULL에서는 진입하지 않음
    if engine._market_regime in ("STRONG_BULL", "BULL"):
        return
    if engine._market_regime == "NEUTRAL" and engine._vix_ema20 < vix_threshold:
        return

    # 마켓에 맞는 인버스 ETF 목록
    market_key = "sp500"  # 기본값
    if "kospi" in engine.market_id.lower():
        market_key = "kospi"
    elif "nasdaq" in engine.market_id.lower():
        market_key = "nasdaq"

    # 인버스 ETF + CRISIS 안전자산 합산
    defensive_tickers = list(INVERSE_ETFS.get(market_key, []))
    if _def_ro.get("safe_haven_enabled"):
        for item in SAFE_HAVEN_ETFS.get(market_key, []):
            ticker = item["ticker"]
            if ticker not in defensive_tickers:
                defensive_tickers.append(ticker)

    if not defensive_tickers:
        return

    for ticker in defensive_tickers:
        # 이미 보유 중이면 스킵
        if ticker in engine.positions and engine.positions[ticker].status == "ACTIVE":
            continue

        df = engine._ohlcv_cache.get(ticker)
        if df is None or len(df) < 20:
            continue

        price = float(df.iloc[-1]["close"])
        if price <= 0:
            continue

        # 시그널 생성 (고정 strength — defensive는 레짐 기반)
        strength = 70 if engine._market_regime in ("BEAR", "CRISIS") else 50
        if engine._vix_ema20 > 30:
            strength += 10
        # CRISIS 안전자산은 추가 강도
        is_safe_haven = any(
            item["ticker"] == ticker
            for item in SAFE_HAVEN_ETFS.get(market_key, [])
        )
        if is_safe_haven and engine._market_regime == "CRISIS":
            strength += 15

        ticker_name = f"SafeHaven_{ticker}" if is_safe_haven else f"Inv_{ticker}"

        engine._signal_counter += 1
        signal = SimSignal(
            id=f"sim-sig-{engine._signal_counter:04d}",
            stock_code=ticker,
            stock_name=ticker_name,
            type="BUY",
            price=price,
            strength=strength,
            reason=f"Defensive: {engine._market_regime} regime, VIX={engine._vix_ema20:.1f}",
            detected_at=engine._get_current_iso(),
        )
        engine._execute_buy(
            signal,
            trend_strength="MODERATE",
            trend_stage="MID",
            alignment_score=3,
        )


def check_exits(engine: "SimulationEngine"):
    """
    Defensive 전략 청산: 레짐이 BULL로 전환되면 청산.
    또는 일반 ES1 손절(-5%) 적용.
    """
    to_close: List[str] = []

    for code, pos in engine.positions.items():
        if pos.status != "ACTIVE":
            continue
        if engine._exit_tag_filter and pos.strategy_tag != engine._exit_tag_filter:
            continue

        current_price = engine._current_prices.get(code, pos.current_price)
        entry_price = pos.entry_price
        pnl_pct = (current_price - entry_price) / entry_price

        exit_reason = None
        exit_type = None

        # ES1: 하드 손절 -5%
        if pnl_pct <= -0.05:
            exit_reason = "ES1: 손절 -5%"
            exit_type = "STOP_LOSS"

        # 레짐이 BULL로 전환 → 인버스 청산
        elif engine._market_regime == "BULL":
            exit_reason = "DEF_REGIME: BULL 전환 청산"
            exit_type = "REGIME_EXIT"

        # 익절: +10% (인버스는 보수적 TP)
        elif pnl_pct >= 0.10:
            exit_reason = "DEF_TP: 익절 +10%"
            exit_type = "TAKE_PROFIT"

        # 트레일링: +5% 이상이면 2×ATR 트레일링
        elif pnl_pct >= 0.05:
            df = engine._ohlcv_cache.get(code)
            if df is not None and "atr" in df.columns and len(df) > 0:
                atr_val = float(df.iloc[-1].get("atr", 0))
                if atr_val > 0:
                    trail_stop = pos.highest_price - 2.0 * atr_val
                    if current_price <= trail_stop:
                        exit_reason = f"DEF_TRAIL: 트레일링 (ATR×2.0)"
                        exit_type = "TRAILING_STOP"

        if exit_reason:
            to_close.append(code)
            engine._close_position(code, current_price, exit_reason, exit_type)

    for code in to_close:
        if code in engine.positions:
            del engine.positions[code]
