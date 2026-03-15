"""
Momentum Swing strategy — scan_entries / check_exits.

Extracted from SimulationEngine to keep engine.py smaller.
All logic is identical; `self` is replaced with `engine`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List

import pandas as pd

from simulation.constants import (
    REGIME_PARAMS, REGIME_EXIT_PARAMS, REGIME_OVERRIDES,
)
from simulation.models import SimSignal

if TYPE_CHECKING:
    from simulation.engine import SimulationEngine


def scan_entries(engine: "SimulationEngine"):
    """
    6-Phase 통합 파이프라인 (기존 Momentum Swing):
    Phase 0 (시장 체제) → Phase 4 (리스크 게이트) → 종목별 Phase 1→2→3
    """
    # ── Phase 0: 시장 체제 판단 ──
    engine._update_market_regime()
    # BEAR 체제: 제한적 거래 허용 (max_positions=2, max_weight=5%)
    # 하드블록 대신 REGIME_PARAMS가 RG3에서 포지션 수 제한

    # ── Phase 4: 리스크 게이트 (사전 체크) ──
    can_trade, block_reason = engine._risk_gate_check()
    if not can_trade:
        engine._phase_stats["phase4_risk_blocks"] += 1
        engine._add_risk_event("WARNING", f"진입 차단: {block_reason}")
        return

    total_equity = engine._get_total_equity()
    regime_params = REGIME_PARAMS.get(engine._market_regime, REGIME_PARAMS["NEUTRAL"])

    active_count = len([p for p in engine.positions.values() if p.status == "ACTIVE"])

    if active_count >= regime_params["max_positions"]:
        return

    new_signals: List[tuple] = []  # (signal, trend_strength, trend_stage)

    for w in engine._watchlist:
        code = w["code"]

        # STRONG_BULL 피라미딩: 기존 보유 종목도 조건부 추가 매수 허용
        is_pyramid = False
        _pyr_ro = REGIME_OVERRIDES.get(engine._market_regime, {})
        if code in engine.positions and engine.positions[code].status in ("ACTIVE", "PENDING"):
            pos_existing = engine.positions[code]
            if (_pyr_ro.get("pyramiding_enabled")
                    and pos_existing.strategy_tag == "momentum"
                    and pos_existing.scale_count < _pyr_ro.get("pyramiding_max", 1)
                    and pos_existing.days_held >= 5):
                cur_px = engine._current_prices.get(code, pos_existing.current_price)
                eff_entry = pos_existing.avg_entry_price if pos_existing.avg_entry_price > 0 else pos_existing.entry_price
                pnl_ratio = (cur_px - eff_entry) / eff_entry if eff_entry > 0 else 0
                if pnl_ratio >= _pyr_ro.get("pyramiding_pnl_min", 0.05):
                    is_pyramid = True  # 피라미딩 조건 충족, fall through
                else:
                    continue
            else:
                continue

        df = engine._ohlcv_cache.get(code)
        if df is None or len(df) < engine.ma_long + 5:
            continue

        df = engine._calculate_indicators(df.copy())
        if df.empty or len(df) < 2:
            continue

        engine._phase_stats["total_scans"] += 1

        # ── Phase 1: 추세 확인 ──
        trend = engine._confirm_trend(df)
        if trend["direction"] != "UP":
            engine._phase_stats["phase1_trend_rejects"] += 1
            if code in engine._debug_tickers:
                print(
                    f"[DIAG] {code} Phase1 REJECT: direction={trend['direction']} "
                    f"adx={trend['adx']:.1f} aligned={trend['aligned']}"
                )
            continue  # FLAT/DOWN 종목 스킵

        # ── Phase 2: 추세 위치 파악 ──
        stage = engine._estimate_trend_stage(df)
        if stage == "LATE":
            engine._phase_stats["phase2_late_rejects"] += 1
            if code in engine._debug_tickers:
                _curr = df.iloc[-1]
                _rsi = float(_curr.get("rsi", 0)) if pd.notna(_curr.get("rsi")) else 0
                _close = float(_curr["close"])
                _52w_h = float(df["close"].astype(float).rolling(min(252, len(df))).max().iloc[-1])
                _pct_h = (_close / _52w_h * 100) if _52w_h > 0 else 0
                print(
                    f"[DIAG] {code} Phase2 LATE REJECT: rsi={_rsi:.1f} "
                    f"pct_of_52w_high={_pct_h:.1f}%"
                )
            continue  # 말기 종목 진입 스킵

        # ── Phase 3: 진입 시그널 ──
        curr = df.iloc[-1]
        prev = df.iloc[-2]

        primary = []
        confirmations = []

        # PS1: 골든크로스
        if (
            pd.notna(curr["ma_short"])
            and pd.notna(curr["ma_long"])
            and pd.notna(prev["ma_short"])
            and pd.notna(prev["ma_long"])
        ):
            if prev["ma_short"] <= prev["ma_long"] and curr["ma_short"] > curr["ma_long"]:
                primary.append("PS1")

        # PS2: MACD 골든크로스 + 기울기 필터
        if pd.notna(curr.get("macd_hist")) and pd.notna(prev.get("macd_hist")):
            if prev["macd_hist"] <= 0 and curr["macd_hist"] > 0:
                # 3봉 기울기 양수 확인 (감속 크로스 필터링)
                if len(df) >= 4:
                    hist_3ago = float(df.iloc[-3].get("macd_hist", 0)) if pd.notna(df.iloc[-3].get("macd_hist")) else 0
                    slope = float(curr["macd_hist"]) - hist_3ago
                    if slope > 0:
                        primary.append("PS2")
                else:
                    primary.append("PS2")

        # PS3: MA 풀백 진입 (추세 지속 시그널)
        # 확립된 상승 추세에서 MA20 지지 확인 후 반등 → 대형 주도주 포착
        if not primary:
            if (
                pd.notna(curr["ma_short"])
                and pd.notna(curr["ma_long"])
                and pd.notna(curr.get("ma60"))
                and len(df) >= 5
            ):
                ma_short_val = float(curr["ma_short"])
                ma_long_val = float(curr["ma_long"])
                ma60_val = float(curr["ma60"])
                price = float(curr["close"])
                prev_price = float(prev["close"])

                # 조건1: 확립된 상승 정배열 (MA5 > MA20 > MA60)
                uptrend = (ma_short_val > ma_long_val > ma60_val)

                if uptrend:
                    # 조건2: 최근 3봉 내 MA20 근처까지 풀백 (2% 이내 접근)
                    recent_lows = df["low"].astype(float).iloc[-4:-1]
                    pullback_zone = ma_long_val * 1.02
                    ma20_proximity = any(
                        low <= pullback_zone for low in recent_lows
                    )

                    # 조건3: 현재 종가 > MA20 (지지 확인 후 반등)
                    above_ma20 = price > ma_long_val

                    # 조건4: 상승 봉 (현재 종가 > 전일 종가)
                    bounce_confirm = price > prev_price

                    if ma20_proximity and above_ma20 and bounce_confirm:
                        primary.append("PS3")
                        engine._phase_stats["phase3_ps3_pullback"] += 1

        # PS4: Donchian Channel 돌파 (STRONG_BULL 전용 — 독립 시그널)
        _mom_ro = REGIME_OVERRIDES.get(engine._market_regime, {})
        ps4_donchian = False
        if _mom_ro.get("donchian_entry") and "donchian_high" in df.columns:
            prev_donchian = prev.get("donchian_high") if pd.notna(prev.get("donchian_high")) else None
            if prev_donchian is not None and float(curr["close"]) > float(prev_donchian):
                ps4_donchian = True
                primary.append("PS4")
                engine._phase_stats.setdefault("phase3_ps4_donchian", 0)
                engine._phase_stats["phase3_ps4_donchian"] += 1

        if not primary:
            engine._phase_stats["phase3_no_primary"] += 1
            if code in engine._debug_tickers:
                _rsi = float(curr.get("rsi", 0)) if pd.notna(curr.get("rsi")) else 0
                _ma_s = float(curr.get("ma_short", 0)) if pd.notna(curr.get("ma_short")) else 0
                _ma_l = float(curr.get("ma_long", 0)) if pd.notna(curr.get("ma_long")) else 0
                _ma60 = float(curr.get("ma60", 0)) if pd.notna(curr.get("ma60")) else 0
                _macd_h = float(curr.get("macd_hist", 0)) if pd.notna(curr.get("macd_hist")) else 0
                print(
                    f"[DIAG] {code} Phase3 NO PRIMARY: ma5={_ma_s:.0f} ma20={_ma_l:.0f} "
                    f"ma60={_ma60:.0f} ma5>ma20={_ma_s > _ma_l} rsi={_rsi:.1f} "
                    f"macd_hist={_macd_h:.4f}"
                )
            continue

        # CF1: RSI 적정 범위 (52-78)
        if pd.notna(curr["rsi"]) and engine.rsi_lower <= curr["rsi"] <= engine.rsi_upper:
            confirmations.append("CF1")

        # CF2: 거래량 돌파
        if pd.notna(curr["volume_ma"]) and curr["volume_ma"] > 0:
            if float(curr["volume"]) >= curr["volume_ma"] * engine.volume_multiplier:
                confirmations.append("CF2")

        # CF3: 슬로우 RSI 멀티 타임프레임 확인 (28일)
        if pd.notna(curr.get("rsi_slow")) and 45 <= float(curr["rsi_slow"]) <= 70:
            confirmations.append("CF3")

        # PS3 전용: 추세 지속 진입은 완화된 확인 임계값 사용
        # 입증된 상승 추세이므로 RSI/거래량 기준을 낮춰도 안전
        if "PS3" in primary and not confirmations:
            # CF1_R: RSI 42-82 (기존 52-78 → 완화)
            if pd.notna(curr["rsi"]) and 42 <= float(curr["rsi"]) <= 82:
                confirmations.append("CF1_R")

            # CF2_R: 거래량 >= MA20 × 1.0 (기존 1.5 → 완화, 대형주 안정 거래량 반영)
            if pd.notna(curr["volume_ma"]) and curr["volume_ma"] > 0:
                if float(curr["volume"]) >= curr["volume_ma"] * 1.0:
                    confirmations.append("CF2_R")

        if not confirmations:
            engine._phase_stats["phase3_no_confirm"] += 1
            if code in engine._debug_tickers:
                _rsi = float(curr.get("rsi", 0)) if pd.notna(curr.get("rsi")) else 0
                _vol = float(curr["volume"])
                _vol_ma = float(curr["volume_ma"]) if pd.notna(curr["volume_ma"]) else 1
                print(
                    f"[DIAG] {code} Phase3 NO CONFIRM: primary={primary} "
                    f"rsi={_rsi:.1f} vol_ratio={_vol / _vol_ma:.2f}"
                )
            continue

        # 베어리시 다이버전스 필터 (가격↑ RSI↓ → 모멘텀 약화)
        if engine._detect_bearish_divergence(df):
            engine._phase_stats["divergence_blocks"] += 1
            continue



        # 시그널 강도 계산 (연속 스코어링)
        adx = trend.get("adx", 0)
        rsi = float(curr.get("rsi", 50)) if pd.notna(curr.get("rsi")) else 50
        vol_ratio = float(curr["volume"]) / float(curr["volume_ma"]) if pd.notna(curr["volume_ma"]) and float(curr["volume_ma"]) > 0 else 1.0

        # PS3는 추세 지속 시그널이므로 개시 시그널(PS1/PS2) 대비 낮은 강도
        ps3_penalty = -10 if "PS3" in primary else 0
        ps4_bonus = 20 if ps4_donchian else 0  # Donchian 돌파 시 +20
        base_strength = len(primary) * 25 + len(confirmations) * 15 + ps3_penalty + ps4_bonus
        trend_bonus = min(int(adx * 0.5), 25)  # ADX 연속값 → 최대 25점
        stage_bonus = 15 if stage == "EARLY" else 8 if stage == "MID" else 0
        rsi_quality = max(0, int(10 - abs(rsi - 55) * 0.5))  # RSI 55 이상대
        volume_bonus = min(int((vol_ratio - 1.5) * 10), 10) if vol_ratio > 1.5 else 0
        strength = min(max(base_strength + trend_bonus + stage_bonus + rsi_quality + volume_bonus, 10), 100)

        current_price = engine._current_prices.get(code, float(curr["close"]))

        engine._signal_counter += 1
        signal = SimSignal(
            id=f"sim-sig-{engine._signal_counter:04d}",
            stock_code=code,
            stock_name=w["name"],
            type="BUY",
            price=current_price,
            reason=f"{'PYR_' if is_pyramid else ''}{'+'.join(primary)} {'+'.join(confirmations)} [trend={trend['strength']}, stage={stage}]",
            strength=min(strength, 100),
            detected_at=engine._get_current_iso(),
        )
        new_signals.append((signal, trend["strength"], stage, trend.get("alignment_score", 3)))

        if code in engine._debug_tickers:
            print(
                f"[DIAG] {code} ✅ SIGNAL: primary={primary} confirm={confirmations} "
                f"strength={strength} stage={stage} price={current_price:.0f}"
            )

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


def check_exits(engine: "SimulationEngine"):
    """기존 Momentum Swing 청산 로직."""
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

        # ATR 기반 프로그레시브 트레일링 폭 사전 계산
        atr_pct_val = 0.03  # 기본값
        df = engine._ohlcv_cache.get(code)
        if df is not None and len(df) > 14:
            if "atr_pct" not in df.columns:
                df = engine._calculate_indicators(df.copy())
                engine._ohlcv_cache[code] = df
            last_atr = df.iloc[-1].get("atr_pct")
            if pd.notna(last_atr):
                atr_pct_val = float(last_atr)
        # 프로그레시브 트레일링: 수익 클수록 타이트한 보호
        if engine.disable_es2:
            # ── 강화 트레일링 (ES2 비활성화 모드: 7단계) ──
            if pnl_pct >= 0.30:
                trail_mult = 2.0   # +30%+: 2×ATR, 플로어 -4% (슈퍼 위너 타이트 보호)
                trail_floor = -0.04
            elif pnl_pct >= 0.25:
                trail_mult = 2.5   # +25-30%: 2.5×ATR, 플로어 -5%
                trail_floor = -0.05
            elif pnl_pct >= 0.20:
                trail_mult = 3.0   # +20-25%: 3×ATR, 플로어 -6% (기존 ES2 대체)
                trail_floor = -0.06
            elif pnl_pct >= 0.15:
                trail_mult = 3.5   # +15-20%: 3.5×ATR, 플로어 -6%
                trail_floor = -0.06
            elif pnl_pct >= 0.10:
                trail_mult = 4.0   # +10-15%: 4×ATR, 플로어 -5%
                trail_floor = -0.05
            elif pnl_pct >= 0.07:
                trail_mult = 3.5   # +7-10%: 3.5×ATR, 플로어 -5%
                trail_floor = -0.05
            else:
                trail_mult = 3.0   # 기본: 3×ATR, 플로어 -4%
                trail_floor = engine.trailing_stop_pct
        else:
            # ── 기존 트레일링 (4단계) ──
            if pnl_pct >= 0.15:
                trail_mult = 5.0   # +15%+: 5×ATR, 플로어 -8%
                trail_floor = -0.08
            elif pnl_pct >= 0.10:
                trail_mult = 4.0   # +10-15%: 4×ATR, 플로어 -6%
                trail_floor = -0.06
            elif pnl_pct >= 0.07:
                trail_mult = 3.5   # +7-10%: 3.5×ATR, 플로어 -5%
                trail_floor = -0.05
            else:
                trail_mult = 3.0   # 기본: 3×ATR, 플로어 -4%
                trail_floor = engine.trailing_stop_pct
        # 글로벌 레짐별 트레일링 오버라이드 (STRONG_BULL: 2.0×ATR 타이트)
        _ro = REGIME_OVERRIDES.get(engine._market_regime, {})
        if "trail_atr_mult" in _ro:
            regime_trail_mult = _ro["trail_atr_mult"]
            regime_trail_floor = _ro.get("trail_floor_pct", trail_floor)
            # 레짐 기반 배수가 현재보다 더 타이트하면 적용
            if regime_trail_mult < trail_mult:
                trail_mult = regime_trail_mult
                trail_floor = regime_trail_floor

        trail_pct = max(-trail_mult * atr_pct_val, trail_floor)

        # BULL 이격도 부분 청산 (ES1/ES2 전에 실행 — 비파괴적)
        if _ro.get("disparity_partial_sell") and not pos.disparity_sold:
            _disp = None
            if df is not None and "disparity_20" in df.columns:
                _disp = df.iloc[-1].get("disparity_20")
            elif df is not None and "ma20" in df.columns:
                _ma20 = df.iloc[-1].get("ma20")
                if pd.notna(_ma20) and _ma20 > 0:
                    _disp = current_price / float(_ma20)
            if _disp is not None and pd.notna(_disp) and _disp > _ro.get("disparity_threshold", 1.15):
                sell_qty = max(1, int(pos.quantity * _ro.get("partial_sell_ratio", 0.5)))
                if sell_qty < pos.quantity:
                    engine._execute_partial_sell(pos, sell_qty, "ES_DISP_PARTIAL")
                    pos.disparity_sold = True

        # ES1: 손절 -5% (GAP DOWN 보호: _execute_sell에서 fill price 조정)
        if current_price <= entry_price * (1 + engine.stop_loss_pct):
            exit_reason = "ES1 손절 -5%"
            exit_type = "STOP_LOSS"

        # ES2: 익절 (체제별 동적) — disable_es2 모드에서 비활성화
        elif not engine.disable_es2 and current_price >= entry_price * (1 + regime_exit["take_profit"]):
            tp_label = f"+{regime_exit['take_profit']*100:.0f}%"
            exit_reason = f"ES2 익절 {tp_label}"
            exit_type = "TAKE_PROFIT"

        # ES3: 트레일링 스탑 (활성화 임계 도달 후에만, ATR 기반)
        elif pnl_pct >= (0.03 if engine.disable_es2 else regime_exit["trail_activation"]):
            if not pos.trailing_activated:
                pos.trailing_activated = True
            trailing_stop_price = pos.highest_price * (1 + trail_pct)
            if current_price <= trailing_stop_price:
                exit_reason = "ES3 트레일링스탑"
                exit_type = "TRAILING_STOP"

        # ES4: 데드크로스 (MA5/20 — 수익 포지션: 타이트 트레일링 전환)
        if not exit_reason:
            if df is not None and len(df) >= engine.ma_long + 2:
                df_calc = df if "ma_short" in df.columns else engine._calculate_indicators(df.copy())
                if len(df_calc) >= 2:
                    curr_row = df_calc.iloc[-1]
                    prev_row = df_calc.iloc[-2]
                    if (
                        pd.notna(curr_row.get("ma_short"))
                        and pd.notna(curr_row.get("ma_long"))
                        and pd.notna(prev_row.get("ma_short"))
                        and pd.notna(prev_row.get("ma_long"))
                        and prev_row["ma_short"] >= prev_row["ma_long"]
                        and curr_row["ma_short"] < curr_row["ma_long"]
                    ):
                        if pnl_pct >= 0.02:
                            # 수익 포지션: 즉시 청산 대신 타이트 트레일링 활성화
                            # 1.5×ATR (표준 3×ATR보다 타이트) 또는 최소 -2%
                            tight_trail = max(-1.5 * atr_pct_val, -0.02)
                            pos.trailing_activated = True
                            pos.trailing_stop = round(current_price * (1 + tight_trail))
                        elif pnl_pct < -0.02:
                            # 손실 -2% 초과만 청산 (경미한 손실은 회복 기회)
                            exit_reason = "ES4 데드크로스"
                            exit_type = "DEAD_CROSS"
                        # -2% ~ +2%: 무시 (ES1/ES3/ES5가 처리)

        # ES5: 보유기간 초과 (체제별 동적)
        if not exit_reason and pos.days_held > regime_exit["max_holding"]:
            exit_reason = "ES5 보유기간 초과"
            exit_type = "MAX_HOLDING"

        # ES7: 리밸런스 청산 (워치리스트 탈락) — PnL 게이트 적용
        if not exit_reason and code in engine._rebalance_exit_codes:
            if pos.days_held < 3 or pnl_pct <= -0.02:
                exit_reason = "ES7 리밸런스 청산"
                exit_type = "REBALANCE_EXIT"
                engine._rebalance_exit_codes.discard(code)
            elif pnl_pct > 0.02:
                # 수익 포지션은 유예 (다음 리밸런스까지 보유)
                engine._rebalance_exit_codes.discard(code)
            else:
                exit_reason = "ES7 리밸런스 청산"
                exit_type = "REBALANCE_EXIT"
                engine._rebalance_exit_codes.discard(code)

        if exit_reason:
            to_close.append(code)
            # Phase 통계: 청산 이유별 카운터
            exit_stat_map = {
                "EMERGENCY_STOP": "es0_emergency_stop",
                "STOP_LOSS": "es1_stop_loss",
                "TAKE_PROFIT": "es2_take_profit",
                "TRAILING_STOP": "es3_trailing_stop",
                "DEAD_CROSS": "es4_dead_cross",
                "MAX_HOLDING": "es5_max_holding",
                "TIME_DECAY": "es6_time_decay",
                "REBALANCE_EXIT": "es7_rebalance_exit",
            }
            stat_key = exit_stat_map.get(exit_type or "")
            if stat_key:
                engine._phase_stats[stat_key] += 1
            engine._execute_sell(pos, current_price, exit_reason, exit_type or "")
        else:
            # 트레일링 최고가 갱신 (ATR 기반)
            if current_price > pos.highest_price:
                pos.highest_price = current_price
                if pos.trailing_activated:
                    pos.trailing_stop = round(current_price * (1 + trail_pct))
                else:
                    pos.trailing_stop = round(current_price * (1 + engine.trailing_stop_pct))

    for code in to_close:
        del engine.positions[code]
