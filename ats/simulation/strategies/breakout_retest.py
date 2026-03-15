"""
Breakout-Retest 2-Phase strategy — scan_entries / check_exits.

Extracted from SimulationEngine to keep engine.py smaller.
All logic is identical; `self` is replaced with `engine`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List

import numpy as np
import pandas as pd

from simulation.constants import (
    REGIME_PARAMS, REGIME_EXIT_PARAMS,
)
from simulation.models import SimSignal

if TYPE_CHECKING:
    from simulation.engine import SimulationEngine


# ══════════════════════════════════════════
# BRT 지표 계산
# ══════════════════════════════════════════

def calculate_indicators_breakout_retest(engine: "SimulationEngine", df: pd.DataFrame) -> pd.DataFrame:
    """기존 지표 + SMC + OBV + ADX 통합 계산 (breakout_retest 전용)."""
    df = engine._calculate_indicators(df)
    if df.empty:
        return df

    # SMC: Swing Points, BOS/CHoCH, Order Blocks, FVG
    from analytics.indicators import calculate_smc
    df = calculate_smc(df, swing_length=engine._brt_cfg.swing_length)

    # OBV (On Balance Volume)
    c = df["close"].astype(float)
    v = df["volume"].astype(float)
    df["obv"] = (np.sign(c.diff()).fillna(0) * v).cumsum()
    df["obv_ema5"] = df["obv"].ewm(span=5, adjust=False).mean()
    df["obv_ema20"] = df["obv"].ewm(span=20, adjust=False).mean()

    return df


# ══════════════════════════════════════════
# BRT 4-Layer 스코어링
# ══════════════════════════════════════════

def score_brt_structure(engine: "SimulationEngine", df: pd.DataFrame) -> int:
    """Layer 1: SMC 구조 스코어 (0~weight_structure). BOS + 유동성 스윕."""
    if len(df) < 10:
        return 0

    score = 0
    lookback = min(20, len(df))
    recent = df.iloc[-lookback:]

    markers = recent[recent["marker"].notna()]
    if not markers.empty:
        last_marker = markers.iloc[-1]["marker"]
        if last_marker == "BOS_BULL":
            score += 20
        elif last_marker == "CHOCH_BULL":
            score += 15

    # 유동성 스윕
    swing_lows = recent[recent["is_swing_low"] == True]
    if not swing_lows.empty and len(df) >= 7:
        last_sl = float(swing_lows.iloc[-1]["low"])
        recent_7 = df.iloc[-7:]
        if (recent_7["low"] < last_sl).any():
            score += 10

    return min(score, engine._brt_cfg.weight_structure)


def score_brt_volatility(engine: "SimulationEngine", df: pd.DataFrame) -> int:
    """Layer 2: BB/ATR 변동성 스코어 (0~weight_volatility)."""
    lookback = engine._brt_cfg.bb_squeeze_lookback
    if len(df) < max(lookback, 50):
        return 0

    score = 0
    bb_width = df["bb_width"].dropna()
    if len(bb_width) < lookback:
        return 0

    current_width = float(bb_width.iloc[-1])
    min_width = float(bb_width.iloc[-lookback:].min())
    bb_ema = float(bb_width.ewm(span=engine._brt_cfg.bb_squeeze_ema).mean().iloc[-1])

    if min_width > 0 and current_width <= min_width * 1.1:
        score += 15
    elif bb_ema > 0 and current_width < bb_ema:
        score += 8

    # ATR 압축
    atr_pct = df["atr_pct"].dropna()
    if len(atr_pct) >= 50:
        atr_avg = float(atr_pct.rolling(50).mean().iloc[-1])
        curr_atr = float(atr_pct.iloc[-1])
        if atr_avg > 0 and curr_atr < atr_avg * 0.8:
            score += 5

    return min(score, engine._brt_cfg.weight_volatility)


def score_brt_obv(engine: "SimulationEngine", df: pd.DataFrame) -> int:
    """Layer 3: OBV 돌파 스코어 (0~weight_volume)."""
    obv = df["obv"].dropna()
    lb = engine._brt_cfg.obv_break_lookback
    if len(obv) < lb + 1:
        return 0

    score = 0
    curr_obv = float(obv.iloc[-1])
    prev_obv_high = float(obv.iloc[-lb - 1:-1].max())

    if curr_obv > prev_obv_high:
        score += 15
        obv_ema5 = float(df["obv_ema5"].iloc[-1]) if pd.notna(df["obv_ema5"].iloc[-1]) else 0
        obv_ema20 = float(df["obv_ema20"].iloc[-1]) if pd.notna(df["obv_ema20"].iloc[-1]) else 0
        if obv_ema5 > obv_ema20:
            score += 10

    return min(score, engine._brt_cfg.weight_volume)


def score_brt_momentum(engine: "SimulationEngine", df: pd.DataFrame) -> int:
    """Layer 4: ADX/MACD 모멘텀 스코어 (0~weight_momentum)."""
    rising_bars = engine._brt_cfg.adx_rising_bars
    if len(df) < rising_bars + 2:
        return 0

    score = 0
    curr = df.iloc[-1]
    prev = df.iloc[-2]

    adx_series = df["adx"].dropna()
    if len(adx_series) >= rising_bars + 1:
        curr_adx = float(adx_series.iloc[-1])
        plus_di = float(curr.get("plus_di", 0)) if pd.notna(curr.get("plus_di")) else 0
        minus_di = float(curr.get("minus_di", 0)) if pd.notna(curr.get("minus_di")) else 0

        if curr_adx > engine._brt_cfg.adx_threshold and plus_di > minus_di:
            score += 8
            rising = True
            for i in range(1, rising_bars + 1):
                if float(adx_series.iloc[-i]) <= float(adx_series.iloc[-i - 1]):
                    rising = False
                    break
            if rising:
                score += 7

    macd_hist = float(curr.get("macd_hist", 0)) if pd.notna(curr.get("macd_hist")) else 0
    prev_macd = float(prev.get("macd_hist", 0)) if pd.notna(prev.get("macd_hist")) else 0

    if prev_macd <= 0 and macd_hist > 0:
        score += 10
    elif macd_hist > 0 and macd_hist > prev_macd:
        score += 5

    return min(score, engine._brt_cfg.weight_momentum)


# ══════════════════════════════════════════
# BRT 6조건 / 페이크아웃 필터 / 리테스트 존
# ══════════════════════════════════════════

def check_brt_six_conditions(engine: "SimulationEngine", df: pd.DataFrame) -> tuple:
    """6조건 검증 (sim). 최소 4개 필요."""
    met = []
    curr = df.iloc[-1]
    cfg = engine._brt_cfg

    # C1: Volatility Squeeze
    bb_width = df["bb_width"].dropna()
    if len(bb_width) >= cfg.bb_squeeze_lookback:
        curr_w = float(bb_width.iloc[-1])
        min_w = float(bb_width.iloc[-cfg.bb_squeeze_lookback:].min())
        if min_w > 0 and curr_w <= min_w * 1.2:
            met.append("C1_SQUEEZE")

    # C2: Liquidity Sweep
    swing_lows = df[df.get("is_swing_low", pd.Series(dtype=bool)) == True]
    if not swing_lows.empty and len(df) >= 7:
        last_sl = float(swing_lows.iloc[-1]["low"])
        recent = df.iloc[-7:]
        if (recent["low"] < last_sl).any():
            met.append("C2_LIQ_SWEEP")

    # C3: Displacement
    body = abs(float(curr["close"]) - float(curr["open"]))
    atr = float(curr.get("atr", 0)) if pd.notna(curr.get("atr")) else 0
    if atr > 0 and body > atr * cfg.displacement_atr_mult:
        met.append("C3_DISPLACEMENT")

    # C4: OBV Break
    obv = df["obv"].dropna()
    if len(obv) > cfg.obv_break_lookback:
        if float(obv.iloc[-1]) > float(obv.iloc[-cfg.obv_break_lookback - 1:-1].max()):
            met.append("C4_OBV_BREAK")

    # C5: ADX > threshold & rising
    adx_s = df["adx"].dropna()
    if len(adx_s) >= cfg.adx_rising_bars + 1:
        if float(adx_s.iloc[-1]) > cfg.adx_threshold:
            rising = all(
                float(adx_s.iloc[-i]) > float(adx_s.iloc[-i - 1])
                for i in range(1, cfg.adx_rising_bars + 1)
            )
            if rising:
                met.append("C5_ADX_RISING")

    # C6: FVG Formation
    fvg_recent = df.iloc[-3:]
    if not fvg_recent[fvg_recent.get("fvg_type", pd.Series(dtype=str)) == "bull"].empty:
        met.append("C6_FVG")

    return len(met) >= 3, met  # Phase 5: 4/6→3/6 진입 기준 완화


def apply_brt_fakeout_filters(engine: "SimulationEngine", df: pd.DataFrame) -> tuple:
    """3개 페이크아웃 필터 (sim). (통과 여부, 차단 사유)."""
    curr = df.iloc[-1]
    cfg = engine._brt_cfg

    # ERR01: 저거래량
    volume = float(curr.get("volume", 0))
    vol_ma = float(curr.get("volume_ma", 1)) if pd.notna(curr.get("volume_ma")) else 1
    if vol_ma > 0 and volume < vol_ma * cfg.min_volume_ratio:
        return False, "ERR01_LOW_VOLUME"

    # ERR02: 긴 윗꼬리
    close = float(curr["close"])
    open_p = float(curr["open"])
    high = float(curr["high"])
    body = abs(close - open_p)
    upper_wick = high - max(close, open_p)
    if body > 0 and upper_wick / body > cfg.max_wick_body_ratio:
        return False, "ERR02_WICK_TRAP"

    # ERR03: MACD/RSI 다이버전스
    if cfg.divergence_check and len(df) >= 10:
        price_curr = float(df["close"].iloc[-1])
        price_prev_max = float(df["close"].iloc[-10:-1].max())
        macd_curr = float(curr.get("macd_hist", 0)) if pd.notna(curr.get("macd_hist")) else 0
        macd_prev_max = float(df["macd_hist"].iloc[-10:-1].max()) if "macd_hist" in df.columns else 0
        rsi_curr = float(curr.get("rsi", 50)) if pd.notna(curr.get("rsi")) else 50
        rsi_prev_max = float(df["rsi"].iloc[-10:-1].max()) if "rsi" in df.columns else 50

        if price_curr > price_prev_max and (macd_curr < macd_prev_max * 0.8 or rsi_curr < rsi_prev_max * 0.9):
            return False, "ERR03_DIVERGENCE"

    return True, None


def capture_brt_retest_zones(engine: "SimulationEngine", df: pd.DataFrame, breakout_price: float, breakout_atr: float) -> Dict[str, Any]:
    """돌파 시점 FVG/OB/레벨 존을 캡처해서 상태 dict로 반환."""
    cfg = engine._brt_cfg
    state: Dict[str, Any] = {
        "phase": "WAITING_RETEST",
        "breakout_price": breakout_price,
        "breakout_atr": breakout_atr,
        "bars_since_breakout": 0,
        "breakout_score": 0,
        "fvg_top": 0.0, "fvg_bottom": 0.0,
        "ob_top": 0.0, "ob_bottom": 0.0,
        "breakout_level": 0.0,
        "zone_top": 0.0, "zone_bottom": 0.0,
        "zone_type": "LEVEL",
        "conditions_met": [],
    }

    recent = df.iloc[-20:]

    # FVG 존 캡처
    if cfg.use_fvg_zone:
        fvg_rows = recent[(recent.get("fvg_type", pd.Series(dtype=str)) == "bull") & recent["fvg_top"].notna()]
        if not fvg_rows.empty:
            last_fvg = fvg_rows.iloc[-1]
            state["fvg_top"] = float(last_fvg["fvg_top"])
            state["fvg_bottom"] = float(last_fvg["fvg_bottom"])

    # OB 존 캡처
    if cfg.use_ob_zone:
        ob_rows = recent[recent["ob_top"].notna()]
        if not ob_rows.empty:
            last_ob = ob_rows.iloc[-1]
            state["ob_top"] = float(last_ob["ob_top"])
            state["ob_bottom"] = float(last_ob["ob_bottom"])

    # 돌파 레벨 (마지막 swing high)
    if cfg.use_breakout_level:
        swing_highs = recent[recent.get("is_swing_high", pd.Series(dtype=bool)) == True]
        if not swing_highs.empty:
            state["breakout_level"] = float(swing_highs.iloc[-1]["high"])

    # 복합 존 계산
    zone_candidates = []
    if state["fvg_bottom"] > 0:
        zone_candidates.append((state["fvg_bottom"], state["fvg_top"]))
    if state["ob_bottom"] > 0:
        zone_candidates.append((state["ob_bottom"], state["ob_top"]))
    if state["breakout_level"] > 0:
        buffer = breakout_atr * cfg.retest_zone_atr_buffer
        zone_candidates.append((state["breakout_level"] - buffer, state["breakout_level"]))

    if zone_candidates:
        state["zone_bottom"] = min(z[0] for z in zone_candidates)
        state["zone_top"] = max(z[1] for z in zone_candidates)
        state["zone_type"] = "COMPOSITE"
    else:
        buffer = breakout_atr * cfg.retest_zone_atr_buffer
        state["zone_bottom"] = breakout_price - breakout_atr - buffer
        state["zone_top"] = breakout_price
        state["zone_type"] = "LEVEL"

    return state


def score_brt_retest_zone(engine: "SimulationEngine", df: pd.DataFrame, state: Dict[str, Any]) -> int:
    """리테스트 존 근접도 스코어링 (0-100)."""
    price = float(df.iloc[-1]["close"])
    score = 0
    cfg = engine._brt_cfg

    # FVG 근접도
    fvg_b = state.get("fvg_bottom", 0)
    fvg_t = state.get("fvg_top", 0)
    if fvg_b > 0 and cfg.use_fvg_zone:
        if fvg_b <= price <= fvg_t:
            score += cfg.fvg_zone_weight
        elif price < fvg_t and price > fvg_b - state.get("breakout_atr", 0) * 0.3:
            score += cfg.fvg_zone_weight // 2

    # OB 근접도
    ob_b = state.get("ob_bottom", 0)
    ob_t = state.get("ob_top", 0)
    if ob_b > 0 and cfg.use_ob_zone:
        if ob_b <= price <= ob_t:
            score += cfg.ob_zone_weight
        elif price < ob_t and price > ob_b - state.get("breakout_atr", 0) * 0.3:
            score += cfg.ob_zone_weight // 2

    # 돌파 레벨 근접도
    bl = state.get("breakout_level", 0)
    if bl > 0 and cfg.use_breakout_level:
        buffer = state.get("breakout_atr", 0) * cfg.retest_zone_atr_buffer
        if bl - buffer <= price <= bl + buffer:
            score += cfg.level_zone_weight

    return min(score, 100)


# ══════════════════════════════════════════
# BRT 진입 스캔
# ══════════════════════════════════════════

def scan_entries(engine: "SimulationEngine"):
    """
    Breakout-Retest 2-Phase 진입 스캔.
    Pass 1: IDLE 티커 → Phase A 돌파 감지
    Pass 2: WAITING_RETEST 티커 → Phase B 리테스트 확인
    """
    # ── Phase 0: 시장 체제 판단 ──
    engine._update_market_regime()

    # ── Phase 4: 리스크 게이트 ──
    can_trade, block_reason = engine._risk_gate_check()
    if not can_trade:
        engine._phase_stats["phase4_risk_blocks"] += 1
        engine._add_risk_event("WARNING", f"BRT 진입 차단: {block_reason}")
        return

    total_equity = engine._get_total_equity()
    regime_params = REGIME_PARAMS.get(engine._market_regime, REGIME_PARAMS["NEUTRAL"])

    active_count = len([p for p in engine.positions.values() if p.status == "ACTIVE"])

    # ── Pass 1: IDLE 티커에서 돌파 감지 ──
    for w in engine._watchlist:
        code = w["code"]


        if code in engine.positions and engine.positions[code].status in ("ACTIVE", "PENDING"):
            continue

        # 이미 WAITING_RETEST 상태면 Pass 1 스킵
        if code in engine._breakout_states and engine._breakout_states[code].get("phase") == "WAITING_RETEST":
            continue

        df = engine._ohlcv_cache.get(code)
        if df is None or len(df) < max(engine._brt_cfg.bb_squeeze_lookback, 50):
            continue

        df = calculate_indicators_breakout_retest(engine, df.copy())
        if df.empty or len(df) < 2:
            continue
        engine._ohlcv_cache[code] = df

        engine._phase_stats["total_scans"] += 1

        # 4-Layer 스코어링
        score_s = score_brt_structure(engine, df)
        score_v = score_brt_volatility(engine, df)
        score_o = score_brt_obv(engine, df)
        score_m = score_brt_momentum(engine, df)
        total_score = score_s + score_v + score_o + score_m

        if total_score < engine._brt_cfg.breakout_threshold:
            engine._phase_stats["phase3_no_primary"] += 1
            continue

        # 6조건 검증
        conditions_ok, met_list = check_brt_six_conditions(engine, df)
        if not conditions_ok:
            engine._phase_stats["phase3_no_confirm"] += 1
            continue

        # 3개 페이크아웃 필터
        filter_ok, block_reason = apply_brt_fakeout_filters(engine, df)
        if not filter_ok:
            engine._phase_stats["brt_fakeout_blocked"] += 1
            continue

        # 돌파 확인 → WAITING_RETEST 전이
        curr = df.iloc[-1]
        breakout_price = float(curr["close"])
        breakout_atr = float(curr.get("atr", breakout_price * 0.03)) if pd.notna(curr.get("atr")) else breakout_price * 0.03

        state = capture_brt_retest_zones(engine, df, breakout_price, breakout_atr)
        state["breakout_score"] = total_score
        state["conditions_met"] = met_list
        engine._breakout_states[code] = state
        engine._phase_stats["brt_breakouts_detected"] += 1

        engine._add_risk_event(
            "INFO",
            f"돌파 감지: {w['name']} score={total_score} [S:{score_s} V:{score_v} O:{score_o} M:{score_m}]"
        )

    # ── Pass 2: WAITING_RETEST 티커에서 리테스트 진입 확인 ──
    new_signals: List[tuple] = []
    expired_codes = []

    for code, state in list(engine._breakout_states.items()):
        if state.get("phase") != "WAITING_RETEST":
            continue
        if code in engine.positions and engine.positions[code].status in ("ACTIVE", "PENDING"):
            continue

        df = engine._ohlcv_cache.get(code)
        if df is None or len(df) < 2:
            continue

        # 지표가 이미 계산되어 있지 않으면 재계산
        if "obv" not in df.columns:
            df = calculate_indicators_breakout_retest(engine, df.copy())
            engine._ohlcv_cache[code] = df

        curr = df.iloc[-1]
        price = float(curr["close"])
        low = float(curr["low"])

        state["bars_since_breakout"] = state.get("bars_since_breakout", 0) + 1

        # 만료 체크
        if state["bars_since_breakout"] > engine._brt_cfg.retest_max_bars:
            state["phase"] = "IDLE"
            expired_codes.append(code)
            engine._phase_stats["brt_retests_expired"] += 1
            continue

        # 존 하단 이탈 → 실패
        if price < state["zone_bottom"]:
            state["phase"] = "IDLE"
            expired_codes.append(code)
            continue

        # 존 도달 확인
        in_zone = low <= state["zone_top"] and price >= state["zone_bottom"]
        if not in_zone:
            continue

        # ── 확인 조건 (3개 중 2개 이상) ──
        confirmations = 0
        confirm_parts = []

        # 1. 거래량 감소
        volume = float(curr.get("volume", 0))
        vol_ma = float(curr.get("volume_ma", 1)) if pd.notna(curr.get("volume_ma")) else 1
        if vol_ma > 0 and volume < vol_ma * engine._brt_cfg.retest_volume_decay:
            confirmations += 1
            confirm_parts.append("VOL_DECAY")

        # 2. 반등 캔들
        open_p = float(curr["open"])
        body = abs(price - open_p)
        lower_wick = min(price, open_p) - low
        bullish_rejection = body > 0 and lower_wick > body * engine._brt_cfg.retest_rejection_wick_ratio
        bullish_close = price > open_p
        if bullish_rejection or bullish_close:
            confirmations += 1
            confirm_parts.append("REJECTION" if bullish_rejection else "BULL_CLOSE")

        # 3. RSI 지지
        rsi = float(curr.get("rsi", 50)) if pd.notna(curr.get("rsi")) else 50
        if rsi >= engine._brt_cfg.retest_rsi_floor:
            confirmations += 1
            confirm_parts.append(f"RSI_{int(rsi)}")

        if confirmations < 2:
            continue

        # 존 스코어링
        zone_score = score_brt_retest_zone(engine, df, state)
        if zone_score < engine._brt_cfg.retest_zone_threshold:
            continue

        # ── 리테스트 진입 확인 ──
        strength = min(state.get("breakout_score", 60) + zone_score // 2, 100)
        stock_name = engine._stock_names.get(code, code)

        engine._signal_counter += 1
        signal = SimSignal(
            id=f"sim-sig-{engine._signal_counter:04d}",
            stock_code=code,
            stock_name=stock_name,
            type="BUY",
            price=engine._current_prices.get(code, price),
            reason=f"BRT_RETEST_{strength} [BKO:{state.get('breakout_score', 0)} ZONE:{zone_score} {'+'.join(confirm_parts)}]",
            strength=strength,
            detected_at=engine._get_current_iso(),
        )
        new_signals.append((signal, "MODERATE", "MID", 3))

        state["phase"] = "IDLE"  # 사용된 상태 리셋
        engine._phase_stats["brt_retests_entered"] += 1

    # 만료된 상태 정리
    for code in expired_codes:
        if code in engine._breakout_states and engine._breakout_states[code].get("phase") == "IDLE":
            del engine._breakout_states[code]

    # 시그널 강도순 정렬 후 매수 실행
    new_signals.sort(key=lambda x: x[0].strength, reverse=True)

    for sig, trend_strength, trend_stage, align_score in new_signals:
        if active_count >= regime_params["max_positions"]:
            break
        engine.signals.append(sig)
        if len(engine.signals) > 100:
            engine.signals = engine.signals[-100:]

        engine._execute_buy(sig, trend_strength=trend_strength,
                         trend_stage=trend_stage, alignment_score=align_score)
        engine._phase_stats["entries_executed"] += 1
        active_count += 1


# ══════════════════════════════════════════
# BRT 청산 로직
# ══════════════════════════════════════════

def check_exits(engine: "SimulationEngine"):
    """
    Breakout-Retest 전용 청산 체크.
    ES1(-5%) > ATR SL(1.5x) > ATR TP(3.0x) > CHoCH > ES3 트레일링 > Zone Break > ES5 보유기간 > ES7 리밸런스
    """
    to_close: List[str] = []

    for code, pos in engine.positions.items():
        if pos.status != "ACTIVE":
            continue
        if engine._exit_tag_filter and pos.strategy_tag != engine._exit_tag_filter:
            continue
        # 글로벌 레짐 기반 청산 파라미터 (종목별 레짐은 analytics용)
        regime_exit = REGIME_EXIT_PARAMS.get(engine._market_regime, REGIME_EXIT_PARAMS["NEUTRAL"])


        current_price = engine._current_prices.get(code, pos.current_price)
        entry_price = pos.entry_price
        pnl_pct = (current_price - entry_price) / entry_price

        exit_reason = None
        exit_type = None

        # ATR 조회
        atr_val = None
        df = engine._ohlcv_cache.get(code)
        if df is not None and len(df) > 14:
            if "atr" not in df.columns:
                df = engine._calculate_indicators(df.copy())
                engine._ohlcv_cache[code] = df
            last_atr = df.iloc[-1].get("atr")
            if pd.notna(last_atr):
                atr_val = float(last_atr)

        # ES1: 손절 -5% (GAP DOWN 보호: _execute_sell에서 fill price 조정)
        if current_price <= entry_price * (1 + engine.stop_loss_pct):
            exit_reason = "ES1 손절 -5%"
            exit_type = "STOP_LOSS"

        # ES_BRT_SL: ATR × 1.5 (2일 쿨다운)
        elif atr_val and atr_val > 0:
            atr_sl_price = entry_price - atr_val * engine._brt_cfg.atr_sl_mult
            floor_sl_price = entry_price * (1 + engine.stop_loss_pct)
            effective_sl = max(atr_sl_price, floor_sl_price)

            if current_price <= effective_sl and effective_sl > floor_sl_price:
                exit_reason = "ES_BRT ATR SL (1.5x)"
                exit_type = "ATR_STOP_LOSS"

            # ES_BRT_TP: ATR × 3.0
            if not exit_reason:
                atr_tp_price = entry_price + atr_val * engine._brt_cfg.atr_tp_mult
                if current_price >= atr_tp_price:
                    exit_reason = "ES_BRT ATR TP (3.0x)"
                    exit_type = "ATR_TAKE_PROFIT"

        # ES_CHOCH: 추세 반전 감지 (Phase 5: PnL 게이트)
        if not exit_reason and engine._brt_cfg.choch_exit and df is not None and len(df) > 10:
            choch_pnl_gate = pnl_pct < -0.02 or pnl_pct > 0.05
            if choch_pnl_gate:
                df_calc = calculate_indicators_breakout_retest(engine, df.copy())
                recent_markers = df_calc.iloc[-5:]
                for _, row in recent_markers.iterrows():
                    if row.get("marker") == "CHOCH_BEAR":
                        exit_reason = "ES_CHOCH 추세반전"
                        exit_type = "CHOCH_EXIT"
                        break

        # ES3: 트레일링 스탑 (+5% 활성화, ATR × 2.0)
        if not exit_reason:
            if pnl_pct >= engine._brt_cfg.trailing_activation_pct:
                if not pos.trailing_activated:
                    pos.trailing_activated = True
                # ATR 기반 트레일링
                trail_pct = engine.trailing_stop_pct  # 기본 -4%
                if atr_val and atr_val > 0:
                    atr_trail = -(atr_val * engine._brt_cfg.trailing_atr_mult) / entry_price
                    trail_pct = max(atr_trail, engine.trailing_stop_pct)
                trailing_stop_price = pos.highest_price * (1 + trail_pct)
                if current_price <= trailing_stop_price:
                    exit_reason = "ES3 트레일링스탑"
                    exit_type = "TRAILING_STOP"

        # ES_ZONE_BREAK: 리테스트 존 무효화 (존 하단 이탈 시 청산)
        if not exit_reason and code in engine._breakout_states:
            brt_state = engine._breakout_states[code]
            zone_bottom = brt_state.get("zone_bottom", 0)
            if zone_bottom > 0 and current_price < zone_bottom:
                exit_reason = "ES_ZONE_BREAK 존 무효화"
                exit_type = "ZONE_BREAK"

        # ES5: 보유기간 초과
        max_hold = min(engine._brt_cfg.max_holding_days, regime_exit["max_holding"])
        if not exit_reason and pos.days_held > max_hold:
            exit_reason = "ES5 보유기간 초과"
            exit_type = "MAX_HOLDING"

        # ES7: 리밸런스 청산 (PnL 게이트: 수익 중이면 유예)
        if not exit_reason and code in engine._rebalance_exit_codes:
            if pos.days_held < 3 or pnl_pct <= -0.02:
                exit_reason = "ES7 리밸런스 청산"
                exit_type = "REBALANCE_EXIT"
                engine._rebalance_exit_codes.discard(code)
            elif pnl_pct > 0.02:
                # 수익 +2%+ → 다음 리밸런스까지 유예
                engine._rebalance_exit_codes.discard(code)
            else:
                exit_reason = "ES7 리밸런스 청산"
                exit_type = "REBALANCE_EXIT"
                engine._rebalance_exit_codes.discard(code)

        if exit_reason:
            to_close.append(code)
            # Phase 통계
            exit_stat_map = {
                "EMERGENCY_STOP": "es0_emergency_stop",
                "STOP_LOSS": "es1_stop_loss",
                "ATR_STOP_LOSS": "es_brt_sl",
                "ATR_TAKE_PROFIT": "es_brt_tp",
                "CHOCH_EXIT": "es_choch_exit",
                "TRAILING_STOP": "es3_trailing_stop",
                "ZONE_BREAK": "es_zone_break",
                "MAX_HOLDING": "es5_max_holding",
                "REBALANCE_EXIT": "es7_rebalance_exit",
            }
            stat_key = exit_stat_map.get(exit_type or "")
            if stat_key and stat_key in engine._phase_stats:
                engine._phase_stats[stat_key] += 1
            engine._execute_sell(pos, current_price, exit_reason, exit_type or "")
        else:
            # 트레일링 최고가 갱신
            if current_price > pos.highest_price:
                pos.highest_price = current_price

    for code in to_close:
        del engine.positions[code]
