"""
Mean Reversion strategy — indicators, scoring, scan_entries, check_exits.

Extracted from SimulationEngine to keep engine.py smaller.
All logic is identical; `self` is replaced with `engine`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List

import numpy as np
import pandas as pd

from simulation.constants import (
    REGIME_PARAMS, REGIME_EXIT_PARAMS, REGIME_OVERRIDES,
)
from simulation.models import SimSignal

if TYPE_CHECKING:
    from simulation.engine import SimulationEngine


# ──────────────────────────────────────────────────────────
# Indicator calculation
# ──────────────────────────────────────────────────────────

def calculate_indicators_mean_reversion(engine: "SimulationEngine", df: pd.DataFrame) -> pd.DataFrame:
    """기존 지표 + MA200 + Stochastic + 연속하락일 계산."""
    df = engine._calculate_indicators(df)
    if df.empty:
        return df

    c = df["close"].astype(float)
    h = df["high"].astype(float)
    lo = df["low"].astype(float)

    # Stochastic %K/%D
    k_period = engine._mr_cfg.stochastic_k_period
    d_period = engine._mr_cfg.stochastic_d_period
    lowest_low = lo.rolling(window=k_period).min()
    highest_high = h.rolling(window=k_period).max()
    denom = (highest_high - lowest_low).replace(0, np.nan)
    df["stoch_k"] = 100 * (c - lowest_low) / denom
    df["stoch_d"] = df["stoch_k"].rolling(window=d_period).mean()

    # 연속 하락일 카운터
    daily_return = c.pct_change()
    is_down = (daily_return < 0).astype(int)
    consec = []
    count = 0
    for val in is_down:
        if val == 1:
            count += 1
        else:
            count = 0
        consec.append(count)
    df["consecutive_down_days"] = consec

    # Phase 5: MA50 for MR TP target
    if len(df) >= 50:
        df["ma50"] = c.rolling(window=50).mean()

    return df


# ──────────────────────────────────────────────────────────
# 3-Layer scoring (pure functions using df + engine._mr_cfg)
# ──────────────────────────────────────────────────────────

def score_mr_signal(engine: "SimulationEngine", df: pd.DataFrame) -> int:
    """Layer 1: MR Signal (0~weight_signal). Graduated RSI + BB proximity + MA200."""
    if len(df) < 200:
        return 0

    score = 0
    curr = df.iloc[-1]
    price = float(curr["close"])

    # Graduated RSI scoring (바이너리 → 단계적)
    rsi = float(curr.get("rsi", 50)) if pd.notna(curr.get("rsi")) else 50
    if rsi < 25:
        score += 20      # 강한 과매도
    elif rsi < 35:
        score += 15      # 중간 과매도
    elif rsi < 42:
        score += 10      # 경미한 과매도

    # Graduated BB Lower proximity (breach + 근접)
    bb_lower = float(curr.get("bb_lower", 0)) if pd.notna(curr.get("bb_lower")) else 0
    if bb_lower > 0:
        if price < bb_lower:
            score += 15  # BB 하단 돌파 (강한 시그널)
        elif price < bb_lower * 1.01:
            score += 8   # BB 하단 1% 이내 근접

    # MA200 위 = 장기 상승 추세 안에서의 pullback (건강한 MR)
    ma200 = float(curr.get("ma200", 0)) if pd.notna(curr.get("ma200")) else 0
    if ma200 > 0 and price > ma200:
        score += 5

    return min(score, engine._mr_cfg.weight_signal)


def score_mr_volatility(engine: "SimulationEngine", df: pd.DataFrame) -> int:
    """Layer 2: Volatility & Volume (0~weight_volatility). Graduated scoring."""
    if len(df) < 30:
        return 0

    score = 0
    curr = df.iloc[-1]

    # BB Width 확장 (변동성 증가 = 평균 회귀 기회)
    bb_width = float(curr.get("bb_width", 0)) if pd.notna(curr.get("bb_width")) else 0
    bb_width_avg = df["bb_width"].rolling(window=20).mean()
    bb_avg_val = float(bb_width_avg.iloc[-1]) if pd.notna(bb_width_avg.iloc[-1]) else bb_width
    if bb_avg_val > 0:
        if bb_width > bb_avg_val * 1.5:
            score += 12  # 강한 변동성 확장
        elif bb_width > bb_avg_val * 1.2:
            score += 8   # 보통 확장
        elif bb_width > bb_avg_val * 1.0:
            score += 4   # 약간 확장

    # Graduated volume scoring (2.0x → 1.5x/1.2x 단계)
    curr_vol = float(curr.get("volume", 0)) if pd.notna(curr.get("volume")) else 0
    vol_ma = float(curr.get("volume_ma", 1)) if pd.notna(curr.get("volume_ma")) else 1
    if vol_ma > 0:
        vol_ratio = curr_vol / vol_ma
        if vol_ratio > 2.0:
            score += 10  # 강한 볼륨 스파이크 (capitulation)
        elif vol_ratio > engine._mr_cfg.volume_spike_mult:
            score += 7   # 보통 스파이크
        elif vol_ratio > 1.2:
            score += 4   # 약한 볼륨 증가

    # ATR 확장 (패닉 셀오프 감지)
    atr = float(curr.get("atr", 0)) if pd.notna(curr.get("atr")) else 0
    atr_ma = df["atr"].rolling(window=20).mean()
    atr_avg_val = float(atr_ma.iloc[-1]) if pd.notna(atr_ma.iloc[-1]) else atr
    if atr_avg_val > 0 and atr > atr_avg_val * 1.3:
        score += 8

    return min(score, engine._mr_cfg.weight_volatility)


def score_mr_confirmation(engine: "SimulationEngine", df: pd.DataFrame) -> int:
    """Layer 3: Confirmation (0~weight_confirmation). MACD slope + Stochastic + 연속하락."""
    if len(df) < 30:
        return 0

    score = 0
    curr = df.iloc[-1]
    prev = df.iloc[-2]

    # MACD: zero cross (+10) OR slope positive (+5)
    macd_hist = float(curr.get("macd_hist", 0)) if pd.notna(curr.get("macd_hist")) else 0
    prev_macd = float(prev.get("macd_hist", 0)) if pd.notna(prev.get("macd_hist")) else 0
    if prev_macd <= 0 and macd_hist > 0:
        score += 10      # zero cross (강한 반전 시그널)
    elif macd_hist > prev_macd and macd_hist < 0:
        score += 5       # slope positive (하락세 둔화)

    # Stochastic: graduated (K<20 → +10, K<30 → +5, K<20 GC bonus +5)
    stoch_k = float(curr.get("stoch_k", 50)) if pd.notna(curr.get("stoch_k")) else 50
    stoch_d = float(curr.get("stoch_d", 50)) if pd.notna(curr.get("stoch_d")) else 50
    prev_stoch_k = float(prev.get("stoch_k", 50)) if pd.notna(prev.get("stoch_k")) else 50
    prev_stoch_d = float(prev.get("stoch_d", 50)) if pd.notna(prev.get("stoch_d")) else 50
    if stoch_k < 20:
        score += 8       # 강한 과매도
        if prev_stoch_k <= prev_stoch_d and stoch_k > stoch_d:
            score += 4   # golden cross 보너스
    elif stoch_k < 30:
        score += 5       # 보통 과매도

    # 연속 하락일: graduated (>=2 → +5, >=3 → +8, >=5 → +10)
    consec_down = int(curr.get("consecutive_down_days", 0))
    if consec_down >= 5:
        score += 10      # 장기 하락 (강한 MR 후보)
    elif consec_down >= engine._mr_cfg.consecutive_down_days + 1:
        score += 8       # 3일 연속 하락
    elif consec_down >= engine._mr_cfg.consecutive_down_days:
        score += 5       # 2일 연속 하락

    return min(score, engine._mr_cfg.weight_confirmation)


# ──────────────────────────────────────────────────────────
# Entry scan
# ──────────────────────────────────────────────────────────

def scan_entries(engine: "SimulationEngine"):
    """
    Mean Reversion 3-Layer 스코어링 기반 진입 스캔.
    Phase 0 (시장 체제) + Phase 4 (리스크 게이트) → 레짐 필터 → MR 스코어링 → 매수 실행.
    """
    # ── Phase 0: 시장 체제 판단 ──
    engine._update_market_regime()

    # ── Phase 4: 리스크 게이트 ──
    can_trade, block_reason = engine._risk_gate_check()
    if not can_trade:
        engine._phase_stats["phase4_risk_blocks"] += 1
        engine._add_risk_event("WARNING", f"MR 진입 차단: {block_reason}")
        return

    total_equity = engine._get_total_equity()
    regime_params = REGIME_PARAMS.get(engine._market_regime, REGIME_PARAMS["NEUTRAL"])

    active_count = len([p for p in engine.positions.values() if p.status == "ACTIVE"])

    if active_count >= regime_params["max_positions"]:
        return

    new_signals: List[tuple] = []

    for w in engine._watchlist:
        code = w["code"]

        # 기존 보유 종목 체크 — MR 수익 +3%, 3일+ 보유, 미스케일 → 추가 진입 허용
        is_scale = False
        if code in engine.positions and engine.positions[code].status in ("ACTIVE", "PENDING"):
            pos = engine.positions[code]
            if (pos.strategy_tag == "mean_reversion"
                    and pos.scale_count < 1
                    and pos.days_held >= 3):
                cur_px = engine._current_prices.get(code, pos.current_price)
                eff_entry = pos.avg_entry_price if pos.avg_entry_price > 0 else pos.entry_price
                if (cur_px - eff_entry) / eff_entry >= 0.03:
                    is_scale = True  # Fall through to scoring
                else:
                    continue
            else:
                continue

        df = engine._ohlcv_cache.get(code)
        if df is None or len(df) < 200:
            continue

        df = calculate_indicators_mean_reversion(engine, df.copy())
        if df.empty or len(df) < 2:
            continue

        engine._phase_stats["total_scans"] += 1
        curr = df.iloc[-1]

        # 레짐 필터: ADX < 25 (비추세) OR 극도 과매도
        # NEUTRAL 레짐: 더 엄격한 ADX 제한 (25→22)
        _mr_ro = REGIME_OVERRIDES.get(engine._market_regime, {})
        effective_adx_limit = _mr_ro.get("mr_adx_limit", engine._mr_cfg.adx_trending_limit)
        adx = float(curr.get("adx", 0)) if pd.notna(curr.get("adx")) else 0
        rsi = float(curr.get("rsi", 50)) if pd.notna(curr.get("rsi")) else 50
        if adx >= effective_adx_limit and rsi >= engine._mr_cfg.extreme_oversold_rsi:
            engine._phase_stats["phase1_trend_rejects"] += 1
            continue

        # RANGE_BOUND 레짐: 지지선 근처에서만 MR 진입
        if _mr_ro.get("sr_zone_entry") and not is_scale:
            sr = engine._detect_support_resistance(df, lookback=_mr_ro.get("box_lookback", 40))
            _current_px = engine._current_prices.get(code, float(curr["close"]))
            atr_buf = float(curr.get("atr", 0)) if pd.notna(curr.get("atr")) else 0
            buffer = atr_buf * _mr_ro.get("sr_atr_buffer", 1.5)
            near_support = any(abs(_current_px - s) < buffer for s in sr["support"]) if sr["support"] else False
            if not near_support and sr["support"]:
                continue  # 지지선 근처가 아니면 진입 차단

        # Phase 5: 반전 확인 캔들 — 전일 양봉 필수 (스케일업은 면제)
        if not is_scale and len(df) >= 2:
            prev = df.iloc[-2]
            prev_close = float(prev["close"]) if pd.notna(prev.get("close")) else 0
            prev_open = float(prev["open"]) if pd.notna(prev.get("open")) else 0
            if prev_close <= prev_open:  # 전일 음봉 → 반전 미확인
                continue

        # 3-Layer 스코어링
        score_signal = score_mr_signal(engine, df)
        score_vol = score_mr_volatility(engine, df)
        score_confirm = score_mr_confirmation(engine, df)
        total_score = score_signal + score_vol + score_confirm

        if total_score < engine._mr_cfg.entry_threshold:
            engine._phase_stats["phase3_no_primary"] += 1
            continue

        current_price = engine._current_prices.get(code, float(curr["close"]))

        # 스케일업: 시그널 강도 50% 감소, 라벨 변경
        scale_label = "MR_SCALE" if is_scale else "MR"
        effective_strength = min(int(total_score * 0.5), 50) if is_scale else min(total_score, 100)

        engine._signal_counter += 1
        signal = SimSignal(
            id=f"sim-sig-{engine._signal_counter:04d}",
            stock_code=code,
            stock_name=w["name"],
            type="BUY",
            price=current_price,
            reason=f"{scale_label}_{total_score} [L1:{score_signal} L2:{score_vol} L3:{score_confirm}]",
            strength=effective_strength,
            detected_at=engine._get_current_iso(),
        )
        new_signals.append((signal, "MODERATE", "MID", 3))

        engine._phase_stats["mr_total_score"] += total_score
        engine._phase_stats["mr_entries"] += 1

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


# ──────────────────────────────────────────────────────────
# Exit check
# ──────────────────────────────────────────────────────────

def check_exits(engine: "SimulationEngine"):
    """
    Mean Reversion 전용 7-Priority 청산 체크.
    ES1(-5%) > ATR SL > MR TP(MA20/RSI>60) > BB Mid > Trailing > Overbought > Max Holding > ES7
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
        # 스케일업된 포지션은 가중평균 매입가 기준 PnL 계산
        effective_entry = pos.avg_entry_price if pos.avg_entry_price > 0 else entry_price
        pnl_pct = (current_price - effective_entry) / effective_entry

        exit_reason = None
        exit_type = None

        # ATR / RSI / BB 조회
        atr_val = None
        rsi_val = None
        bb_mid = None
        ma20 = None
        df = engine._ohlcv_cache.get(code)
        if df is not None and len(df) > 14:
            if "atr" not in df.columns or "stoch_k" not in df.columns:
                df = calculate_indicators_mean_reversion(engine, df.copy())
                engine._ohlcv_cache[code] = df
            last = df.iloc[-1]
            if pd.notna(last.get("atr")):
                atr_val = float(last["atr"])
            if pd.notna(last.get("rsi")):
                rsi_val = float(last["rsi"])
            if pd.notna(last.get("bb_middle")):
                bb_mid = float(last["bb_middle"])
            if pd.notna(last.get("ma_long")):
                ma20 = float(last["ma_long"])

        # ES1: 손절 -5% (GAP DOWN 보호: _execute_sell에서 fill price 조정)
        if current_price <= entry_price * (1 + engine.stop_loss_pct):
            exit_reason = "ES1 손절 -5%"
            exit_type = "STOP_LOSS"

        # ATR SL (2일 쿨다운)
        elif atr_val and atr_val > 0:
            atr_sl_price = entry_price - atr_val * engine._mr_cfg.atr_sl_mult
            floor_sl = entry_price * (1 + engine.stop_loss_pct)
            effective_sl = max(atr_sl_price, floor_sl)
            if current_price <= effective_sl and effective_sl > floor_sl:
                exit_reason = "ES_MR ATR SL"
                exit_type = "ATR_STOP_LOSS"

        # Phase 5.4: MR TP 상향 — MA50+RSI>55 (더 큰 반등 포착)
        # 기존 MA20+RSI>50 → 너무 일찍 청산 (2-3% 수익), SL -5%와 R:R 불균형
        ma50 = None
        if df is not None and len(df) > 50:
            last = df.iloc[-1]
            if pd.notna(last.get("ma50")):
                ma50 = float(last["ma50"])
            elif pd.notna(last.get("ma60")):
                ma50 = float(last["ma60"])  # MA50 없으면 MA60 대체

        if not exit_reason and ma50 and rsi_val is not None:
            if current_price > ma50 and rsi_val > 55:
                exit_reason = "ES_MR TP (MA50+RSI>55)"
                exit_type = "MEAN_REVERSION_TP"

        # RSI > 65 제거 — 너무 이른 청산. 대신 RSI > 70만 유지 (아래 overbought)

        # 수익 보호: pnl >= 5% 이면 MA20 단독으로도 청산 (최소 수익 확보)
        if not exit_reason and ma20 and pnl_pct >= 0.05 and current_price > ma20:
            exit_reason = "ES_MR TP (MA20 profit lock 5%)"
            exit_type = "MEAN_REVERSION_TP"

        # ES3: 트레일링 스탑 (MR → 5%에서 활성화, 기존 4%)
        if not exit_reason:
            trail_pct = engine.trailing_stop_pct
            if pnl_pct >= 0.05:
                if not pos.trailing_activated:
                    pos.trailing_activated = True
                trailing_stop_price = pos.highest_price * (1 + trail_pct)
                if current_price <= trailing_stop_price:
                    exit_reason = "ES3 트레일링스탑"
                    exit_type = "TRAILING_STOP"

        # Overbought: RSI > 70
        if not exit_reason and rsi_val is not None and rsi_val > engine._mr_cfg.rsi_overbought:
            exit_reason = "ES_MR 과매수(RSI>70)"
            exit_type = "OVERBOUGHT_EXIT"

        # ES_TIME_DECAY: 글로벌 레짐 기반 시간감쇄 강제 청산
        _ro_mr = REGIME_OVERRIDES.get(engine._market_regime, {})
        if not exit_reason and _ro_mr.get("time_decay_enabled"):
            decay_days = _ro_mr.get("time_decay_days", 10)
            decay_pnl = _ro_mr.get("time_decay_pnl_min", 0.02)
            if pos.days_held >= decay_days and pnl_pct < decay_pnl:
                exit_reason = f"ES_TIME_DECAY: {pos.days_held}일 보유, PnL {pnl_pct:.1%} < {decay_pnl:.0%}"
                exit_type = "TIME_DECAY"
                engine._phase_stats.setdefault("es_neutral_time_decay", 0)
                engine._phase_stats["es_neutral_time_decay"] += 1

        # ES_BOX_BREAK: RANGE_BOUND 레짐 박스 이탈 즉시 청산
        if not exit_reason and _ro_mr.get("box_breakout_exit") and df is not None:
            _box_lb = _ro_mr.get("box_lookback", 40)
            if len(df) >= _box_lb:
                recent_box = df.tail(_box_lb)
                box_high = float(recent_box["high"].max())
                box_low = float(recent_box["low"].min())
                if current_price > box_high * 1.01 or current_price < box_low * 0.99:
                    exit_reason = f"ES_BOX_BREAK: 박스({box_low:.0f}-{box_high:.0f}) 이탈"
                    exit_type = "BOX_BREAKOUT_EXIT"
                    engine._phase_stats.setdefault("es_range_box_breakout", 0)
                    engine._phase_stats["es_range_box_breakout"] += 1

        # ES5: 수익률 연동 보유기간 (MR 전용)
        if not exit_reason:
            base_max = engine._mr_cfg.max_holding_days  # 20
            if pnl_pct >= 0.10:
                effective_max = 60   # 큰 수익: 트레일링 스탑이 관리
            elif pnl_pct >= 0.05:
                effective_max = 35   # 좋은 수익: 적정 확장
            elif pnl_pct >= 0.02:
                effective_max = 25   # 소폭 수익: 완만 확장
            else:
                effective_max = base_max  # 손실/평: 20일 유지
            if pos.days_held > effective_max:
                exit_reason = f"ES5 보유기간 초과 ({effective_max}일)"
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
            exit_stat_map = {
                "EMERGENCY_STOP": "es0_emergency_stop",
                "STOP_LOSS": "es1_stop_loss",
                "ATR_STOP_LOSS": "es_mr_sl",
                "MEAN_REVERSION_TP": "es_mr_tp",
                "BB_MID_REVERT": "es_mr_bb",
                "TRAILING_STOP": "es3_trailing_stop",
                "OVERBOUGHT_EXIT": "es_mr_ob",
                "MAX_HOLDING": "es5_max_holding",
                "REBALANCE_EXIT": "es7_rebalance_exit",
            }
            stat_key = exit_stat_map.get(exit_type or "")
            if stat_key and stat_key in engine._phase_stats:
                engine._phase_stats[stat_key] += 1
            engine._execute_sell(pos, current_price, exit_reason, exit_type or "")
        else:
            if current_price > pos.highest_price:
                pos.highest_price = current_price

    for code in to_close:
        del engine.positions[code]
