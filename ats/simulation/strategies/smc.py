"""
SMC (Smart Money Concepts) 4-Layer strategy — scan_entries / check_exits.

Extracted from SimulationEngine to keep engine.py smaller.
All logic is identical; `self` is replaced with `engine`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List

import numpy as np
import pandas as pd

from simulation.constants import (
    REGIME_PARAMS, REGIME_EXIT_PARAMS,
)
from simulation.models import SimSignal

if TYPE_CHECKING:
    from simulation.engine import SimulationEngine


# ══════════════════════════════════════════
# SMC 지표 계산
# ══════════════════════════════════════════

def calculate_indicators_smc(engine: "SimulationEngine", df: pd.DataFrame) -> pd.DataFrame:
    """기존 지표 + SMC + OBV 통합 계산."""
    df = engine._calculate_indicators(df)
    if df.empty:
        return df

    # SMC: Swing Points, BOS/CHoCH, Order Blocks, FVG
    from analytics.indicators import calculate_smc
    df = calculate_smc(df, swing_length=engine._smc_cfg.swing_length)

    # OBV (On Balance Volume)
    c = df["close"].astype(float)
    v = df["volume"].astype(float)
    df["obv"] = (np.sign(c.diff()).fillna(0) * v).cumsum()
    df["obv_ema5"] = df["obv"].ewm(span=5, adjust=False).mean()
    df["obv_ema20"] = df["obv"].ewm(span=20, adjust=False).mean()

    return df


# ══════════════════════════════════════════
# SMC 4-Layer 스코어링
# ══════════════════════════════════════════

def score_smc_bias(engine: "SimulationEngine", df: pd.DataFrame) -> int:
    """Layer 1: SMC Bias 스코어 (0~40)."""
    if len(df) < 10:
        return 0

    score = 0
    curr = df.iloc[-1]
    price = float(curr["close"])

    lookback = min(20, len(df))
    recent = df.iloc[-lookback:]
    markers = recent[recent["marker"].notna()]

    if not markers.empty:
        last_marker = markers.iloc[-1]["marker"]
        if last_marker == "BOS_BULL":
            score += 25
        elif last_marker == "CHOCH_BULL":
            score += 20

    # OB 근접도
    ob_rows = recent[recent["ob_top"].notna()]
    if not ob_rows.empty:
        last_ob = ob_rows.iloc[-1]
        ob_top = float(last_ob["ob_top"])
        ob_bottom = float(last_ob["ob_bottom"])
        ob_range = ob_top - ob_bottom if ob_top > ob_bottom else 1.0
        if ob_bottom <= price <= ob_top:
            score += 10
        elif price < ob_top and price > ob_bottom - ob_range * 0.5:
            score += 5

    # FVG 미티게이션
    if engine._smc_cfg.fvg_mitigation:
        fvg_rows = recent[(recent["fvg_type"] == "bull") & recent["fvg_top"].notna()]
        if not fvg_rows.empty:
            last_fvg = fvg_rows.iloc[-1]
            fvg_top = float(last_fvg["fvg_top"])
            fvg_bottom = float(last_fvg["fvg_bottom"])
            if fvg_bottom <= price <= fvg_top:
                score += 5

    return min(score, engine._smc_cfg.weight_smc)


def score_volatility(engine: "SimulationEngine", df: pd.DataFrame) -> int:
    """Layer 2: Volatility Setup 스코어 (0~20)."""
    if len(df) < 50:
        return 0

    score = 0
    curr = df.iloc[-1]

    bb_width = float(curr.get("bb_width", 0)) if pd.notna(curr.get("bb_width")) else 0
    bb_avg_series = df["bb_width"].rolling(window=50).mean()
    bb_width_avg = float(bb_avg_series.iloc[-1]) if pd.notna(bb_avg_series.iloc[-1]) else bb_width
    if bb_width_avg > 0:
        squeeze_ratio = bb_width / bb_width_avg
    else:
        squeeze_ratio = 1.0

    if squeeze_ratio < 0.8:
        score += 15
    elif squeeze_ratio < 1.0:
        score += 8

    atr_pct = float(curr.get("atr_pct", 0)) if pd.notna(curr.get("atr_pct")) else 0
    atr_avg = df["atr_pct"].rolling(window=50).mean()
    atr_avg_val = float(atr_avg.iloc[-1]) if pd.notna(atr_avg.iloc[-1]) else atr_pct
    if atr_avg_val > 0 and 0.5 <= atr_pct / atr_avg_val <= 1.5:
        score += 5

    return min(score, engine._smc_cfg.weight_bb)


def score_obv_signal(engine: "SimulationEngine", df: pd.DataFrame) -> int:
    """Layer 3a: OBV 스코어 (0~20)."""
    if len(df) < 25:
        return 0

    score = 0
    curr = df.iloc[-1]

    obv_ema5 = float(curr.get("obv_ema5", 0)) if pd.notna(curr.get("obv_ema5")) else 0
    obv_ema20 = float(curr.get("obv_ema20", 0)) if pd.notna(curr.get("obv_ema20")) else 0

    if obv_ema5 > obv_ema20:
        score += 10
        if len(df) >= 6:
            obv_5ago = float(df.iloc[-6].get("obv_ema5", 0)) if pd.notna(df.iloc[-6].get("obv_ema5")) else 0
            if obv_ema5 > obv_5ago:
                score += 5

        curr_vol = float(curr.get("volume", 0)) if pd.notna(curr.get("volume")) else 0
        vol_ma = float(curr.get("volume_ma", 1)) if pd.notna(curr.get("volume_ma")) else 1
        if vol_ma > 0 and curr_vol >= vol_ma * 1.3:
            score += 5

    return min(score, engine._smc_cfg.weight_obv)


def score_momentum_signal(engine: "SimulationEngine", df: pd.DataFrame) -> int:
    """Layer 3b: ADX/MACD 모멘텀 스코어 (0~20)."""
    if len(df) < 30:
        return 0

    score = 0
    curr = df.iloc[-1]
    prev = df.iloc[-2]

    adx = float(curr.get("adx", 0)) if pd.notna(curr.get("adx")) else 0
    plus_di = float(curr.get("plus_di", 0)) if pd.notna(curr.get("plus_di")) else 0
    minus_di = float(curr.get("minus_di", 0)) if pd.notna(curr.get("minus_di")) else 0

    if adx > 25 and plus_di > minus_di:
        score += 10
    elif adx > 20 and plus_di > minus_di:
        score += 5

    macd_hist = float(curr.get("macd_hist", 0)) if pd.notna(curr.get("macd_hist")) else 0
    prev_macd = float(prev.get("macd_hist", 0)) if pd.notna(prev.get("macd_hist")) else 0

    if prev_macd <= 0 and macd_hist > 0:
        score += 10
    elif macd_hist > 0 and macd_hist > prev_macd:
        score += 5

    return min(score, engine._smc_cfg.weight_momentum)


# ══════════════════════════════════════════
# SMC 진입 스캔
# ══════════════════════════════════════════

def scan_entries(engine: "SimulationEngine"):
    """
    SMC 4-Layer 스코어링 기반 진입 스캔.
    Phase 0 (시장 체제) + Phase 4 (리스크 게이트) → SMC 스코어링 → 매수 실행.
    """
    # ── Phase 0: 시장 체제 판단 ──
    engine._update_market_regime()

    # ── Phase 4: 리스크 게이트 (사전 체크) ──
    can_trade, block_reason = engine._risk_gate_check()
    if not can_trade:
        engine._phase_stats["phase4_risk_blocks"] += 1
        engine._add_risk_event("WARNING", f"SMC 진입 차단: {block_reason}")
        return

    total_equity = engine._get_total_equity()
    regime_params = REGIME_PARAMS.get(engine._market_regime, REGIME_PARAMS["NEUTRAL"])

    active_count = len([p for p in engine.positions.values() if p.status == "ACTIVE"])

    if active_count >= regime_params["max_positions"]:
        return

    new_signals: List[tuple] = []

    for w in engine._watchlist:
        code = w["code"]


        if code in engine.positions and engine.positions[code].status in ("ACTIVE", "PENDING"):
            continue

        df = engine._ohlcv_cache.get(code)
        if df is None or len(df) < 50:
            continue

        df = calculate_indicators_smc(engine, df.copy())
        if df.empty or len(df) < 2:
            continue

        engine._phase_stats["total_scans"] += 1

        curr = df.iloc[-1]

        # ── SMC 4-Layer 스코어링 ──
        s_smc = score_smc_bias(engine, df)
        s_vol = score_volatility(engine, df)
        s_obv = score_obv_signal(engine, df)
        s_mom = score_momentum_signal(engine, df)
        total_score = s_smc + s_vol + s_obv + s_mom

        if total_score < engine._smc_entry_threshold:
            engine._phase_stats["phase3_no_primary"] += 1
            continue

        current_price = engine._current_prices.get(code, float(curr["close"]))

        engine._signal_counter += 1
        signal = SimSignal(
            id=f"sim-sig-{engine._signal_counter:04d}",
            stock_code=code,
            stock_name=w["name"],
            type="BUY",
            price=current_price,
            reason=f"SMC_{total_score} [L1:{s_smc} L2:{s_vol} L3a:{s_obv} L3b:{s_mom}]",
            strength=min(total_score, 100),
            detected_at=engine._get_current_iso(),
        )
        new_signals.append((signal, "MODERATE", "MID", 3))

        # SMC 통계
        engine._phase_stats["smc_total_score"] += total_score
        engine._phase_stats["smc_entries"] += 1

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
# SMC 청산 로직
# ══════════════════════════════════════════

def check_exits(engine: "SimulationEngine"):
    """
    SMC 전용 청산 체크.
    ES1(-5%) > ATR SL > ATR TP > CHoCH > ES3 트레일링 > ES5 보유기간 > ES7 리밸런스
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

        # ATR SL: entry - ATR * mult (2일 쿨다운)
        elif atr_val and atr_val > 0:
            atr_sl_price = entry_price - atr_val * engine._smc_cfg.atr_sl_mult
            floor_sl_price = entry_price * (1 + engine.stop_loss_pct)
            effective_sl = max(atr_sl_price, floor_sl_price)

            if current_price <= effective_sl and effective_sl > floor_sl_price:
                exit_reason = "ES_SMC ATR SL"
                exit_type = "ATR_STOP_LOSS"

            # ATR TP
            if not exit_reason:
                atr_tp_price = entry_price + atr_val * engine._smc_cfg.atr_tp_mult
                if current_price >= atr_tp_price:
                    exit_reason = "ES_SMC ATR TP"
                    exit_type = "ATR_TAKE_PROFIT"

        # CHoCH Exit: 추세 반전 감지 (Phase 5: PnL 게이트 추가)
        # 데이터: CHoCH exits 9/23 trades, -$2,352 → 조기 청산이 수익 기회 파괴
        # 수정: PnL < -2% (손실 확대 방지) 또는 PnL > +5% (수익 보호)만 CHoCH 청산
        # -2%~+5% "발전 구간"에서는 CHoCH 무시 → 트레이드 성숙 대기
        if not exit_reason and engine._smc_cfg.choch_exit and df is not None and len(df) > 10:
            choch_pnl_gate = pnl_pct < -0.02 or pnl_pct > 0.05
            if choch_pnl_gate:
                df_smc = calculate_indicators_smc(engine, df.copy())
                recent_markers = df_smc.iloc[-5:]
                for _, row in recent_markers.iterrows():
                    if row.get("marker") == "CHOCH_BEAR":
                        exit_reason = "ES_CHOCH 추세반전"
                        exit_type = "CHOCH_EXIT"
                        break

        # ES3: 트레일링 스탑
        if not exit_reason:
            trail_pct = engine.trailing_stop_pct
            if pnl_pct >= regime_exit["trail_activation"]:
                if not pos.trailing_activated:
                    pos.trailing_activated = True
                trailing_stop_price = pos.highest_price * (1 + trail_pct)
                if current_price <= trailing_stop_price:
                    exit_reason = "ES3 트레일링스탑"
                    exit_type = "TRAILING_STOP"

        # ES5: 보유기간 초과
        if not exit_reason and pos.days_held > regime_exit["max_holding"]:
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
                "ATR_STOP_LOSS": "es_smc_sl",
                "ATR_TAKE_PROFIT": "es_smc_tp",
                "CHOCH_EXIT": "es_choch_exit",
                "TRAILING_STOP": "es3_trailing_stop",
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
