"""
Volatility Premium strategy — scan_entries / check_exits.

Extracted from SimulationEngine to keep engine.py smaller.
All logic is identical; `self` is replaced with `engine`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List

import pandas as pd

from simulation.models import SimSignal

if TYPE_CHECKING:
    from simulation.engine import SimulationEngine


def scan_entries(engine: "SimulationEngine"):
    """
    VIX Mean Reversion: VIX 급등 후 하락 반전 시 SPY/QQQ 매수.
    변동성 프리미엄 수확 — VIX가 평균 회귀할 때 주가 반등 포착.

    진입 조건:
    - VIX EMA20 > 22 (변동성 상승 확인)
    - VIX 3일 연속 하락 (하락 반전)
    - RSI(VIX 대리: 시장 RSI < 45) — 시장이 아직 과매도 영역

    청산:
    - VIX EMA20 < 18 (정상화 완료) OR 20일 보유 OR -5% SL
    """
    # VIX 데이터 필요
    if engine._vix_ema20 is None or engine._vix_ema20 <= 0:
        return

    # 진입 조건: VIX 높고 하락 중
    if engine._vix_ema20 < 22:
        return

    # VIX 3일 연속 하락 체크 (VIX 히스토리 필요)
    vix_history = getattr(engine, '_vix_history', [])
    if len(vix_history) < 4:
        return

    vix_declining = all(
        vix_history[-i] < vix_history[-i-1]
        for i in range(1, 4)
    )
    if not vix_declining:
        return

    # 리스크 게이트
    can_trade, _ = engine._risk_gate_check()
    if not can_trade:
        return

    # 타겟: 대형 ETF 또는 시장 대표 종목 (워치리스트에서 유동성 높은 종목)
    vol_targets = ["SPY", "QQQ", "AAPL", "MSFT", "AMZN", "GOOGL", "META", "NVDA"]
    for code in vol_targets:
        if code in engine.positions and engine.positions[code].status == "ACTIVE":
            continue

        df = engine._ohlcv_cache.get(code)
        if df is None or len(df) < 20:
            continue

        df = engine._calculate_indicators(df.copy())
        if df.empty:
            continue
        engine._ohlcv_cache[code] = df

        curr = df.iloc[-1]
        price = engine._current_prices.get(code, float(curr["close"]))

        # 시장 RSI < 50 (아직 반등 여지 있음)
        rsi = float(curr.get("rsi", 50)) if pd.notna(curr.get("rsi")) else 50
        if rsi > 50:
            continue

        # 시그널 강도: VIX 높을수록 + RSI 낮을수록 강함
        strength = min(int(30 + (engine._vix_ema20 - 22) * 5 + (50 - rsi)), 100)

        engine._signal_counter += 1
        signal = SimSignal(
            id=f"sim-sig-{engine._signal_counter:04d}",
            stock_code=code,
            stock_name=engine._stock_names.get(code, code),
            type="BUY",
            price=price,
            reason=f"VOL_PREMIUM VIX={engine._vix_ema20:.1f} RSI={rsi:.0f}",
            strength=strength,
            detected_at=engine._get_current_iso(),
        )

        if engine._collect_mode:
            engine._collected_signals.append((engine.strategy_mode, signal, "MODERATE", "MID", 3))
        else:
            engine._execute_buy(signal, "MODERATE", "MID", 3)


def check_exits(engine: "SimulationEngine"):
    """Volatility Premium 청산: VIX 정상화 OR 20일 보유 OR -5% SL."""
    to_close: List[str] = []

    for code, pos in engine.positions.items():
        if pos.status != "ACTIVE" or pos.strategy_tag != "volatility":
            continue

        current_price = engine._current_prices.get(code, pos.current_price)
        entry_price = pos.entry_price
        pnl_pct = (current_price - entry_price) / entry_price

        exit_reason = None
        exit_type = None

        # ES1: -5% 손절
        if pnl_pct <= -0.05:
            exit_reason = "ES_VOL SL -5%"
            exit_type = "STOP_LOSS"

        # VIX 정상화 청산 (VIX < 18)
        elif engine._vix_ema20 is not None and engine._vix_ema20 < 18:
            exit_reason = f"ES_VOL VIX 정상화 ({engine._vix_ema20:.1f})"
            exit_type = "VOLATILITY_TP"

        # 익절: +8%
        elif pnl_pct >= 0.08:
            exit_reason = "ES_VOL TP +8%"
            exit_type = "TAKE_PROFIT"

        # 20일 보유 초과
        elif pos.days_held > 20:
            exit_reason = "ES_VOL 보유기간 20일 초과"
            exit_type = "MAX_HOLDING"

        # 트레일링: +4%에서 활성
        elif pnl_pct >= 0.04:
            df = engine._ohlcv_cache.get(code)
            if df is not None and "atr" in df.columns:
                atr_val = float(df.iloc[-1].get("atr", 0)) if pd.notna(df.iloc[-1].get("atr")) else 0
                if atr_val > 0:
                    trail_stop = pos.highest_price - 2.0 * atr_val
                    if current_price <= trail_stop:
                        exit_reason = "ES_VOL 트레일링"
                        exit_type = "TRAILING_STOP"

        if exit_reason:
            to_close.append(code)
            engine._execute_sell(pos, current_price, exit_reason, exit_type or "")

    for code in to_close:
        if code in engine.positions:
            del engine.positions[code]
