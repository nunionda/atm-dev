"""
SMC (Smart Money Concepts) 4-Layer 스코어링 전략 구현체.
문서 참조: stock_theory/smcTheory.md

4-Layer 스코어링:
  Layer 1 (40점): SMC Bias — BOS/CHoCH, Order Block, FVG
  Layer 2 (20점): Volatility Setup — BB Squeeze, ATR 상태
  Layer 3a (20점): OBV — 거래량 추세 확인
  Layer 3b (20점): Momentum — ADX, MACD

진입: Total Score ≥ entry_threshold (default 60)
청산: ES1(-3% 불변) > ATR SL > ATR TP > CHoCH Exit > ES3 트레일링 > ES5 보유기간
"""

from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from common.enums import ExitReason
from common.types import ExitSignal, PriceData, Signal
from data.config_manager import ATSConfig, SMCStrategyConfig
from infra.logger import get_logger
from strategy.base import BaseStrategy

logger = get_logger("smc_strategy")


class SMCStrategy(BaseStrategy):
    """
    SMC 4-Layer 스코어링 전략.

    smcTheory.md의 알고리즘 아키텍처를 구현한다:
    - Layer 1: Context & Bias (BOS/CHoCH → 시장 방향 + OB/FVG 근접도)
    - Layer 2: Setup & Volatility (BB Squeeze + ATR 적정 범위)
    - Layer 3: Signal & Momentum (OBV 추세 + ADX/MACD 모멘텀)
    """

    def __init__(self, config: ATSConfig):
        self.config = config
        self.sc = config.strategy       # 기존 StrategyConfig (MA, MACD 등 공유)
        self.ec = config.exit            # ExitConfig
        self.smc = config.smc_strategy   # SMCStrategyConfig

    # ══════════════════════════════════════════
    # 기술적 지표 계산
    # ══════════════════════════════════════════

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        기존 기술지표 + SMC + OBV를 통합 계산한다.
        필요 컬럼: open, high, low, close, volume
        """
        if df.empty or len(df) < max(self.sc.ma_long, 26) + 5:
            return df

        c = df["close"].astype(float)
        v = df["volume"].astype(float)
        h = df["high"].astype(float)
        lo = df["low"].astype(float)

        # ── 이동평균선 ──
        df["ma_short"] = c.rolling(window=self.sc.ma_short).mean()
        df["ma_long"] = c.rolling(window=self.sc.ma_long).mean()

        # ── MACD ──
        ema_fast = c.ewm(span=self.sc.macd_fast, adjust=False).mean()
        ema_slow = c.ewm(span=self.sc.macd_slow, adjust=False).mean()
        df["macd_line"] = ema_fast - ema_slow
        df["macd_signal"] = df["macd_line"].ewm(span=self.sc.macd_signal, adjust=False).mean()
        df["macd_hist"] = df["macd_line"] - df["macd_signal"]

        # ── RSI ──
        delta = c.diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)
        avg_gain = gain.rolling(window=self.sc.rsi_period).mean()
        avg_loss = loss.rolling(window=self.sc.rsi_period).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        df["rsi"] = 100 - (100 / (1 + rs))

        # ── 볼린저밴드 ──
        bb_ma = c.rolling(window=self.sc.bb_period).mean()
        bb_std = c.rolling(window=self.sc.bb_period).std()
        df["bb_upper"] = bb_ma + (bb_std * self.sc.bb_std)
        df["bb_lower"] = bb_ma - (bb_std * self.sc.bb_std)
        df["bb_middle"] = bb_ma
        df["bb_width"] = ((df["bb_upper"] - df["bb_lower"]) / bb_ma.replace(0, np.nan))

        # ── 거래량 이동평균 ──
        df["volume_ma"] = v.rolling(window=self.sc.volume_ma_period).mean()

        # ── ATR (14일) ──
        tr1 = h - lo
        tr2 = (h - c.shift()).abs()
        tr3 = (lo - c.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        df["atr"] = tr.rolling(window=14).mean()
        df["atr_pct"] = df["atr"] / c

        # ── ADX / DMI ──
        df = self._compute_adx(df, period=14)

        # ── SMC: Swing Points, BOS/CHoCH, Order Blocks, FVG ──
        df = self._calculate_smc(df)

        # ── OBV (On Balance Volume) ──
        df["obv"] = (np.sign(c.diff()).fillna(0) * v).cumsum()
        df["obv_ema5"] = df["obv"].ewm(span=5, adjust=False).mean()
        df["obv_ema20"] = df["obv"].ewm(span=20, adjust=False).mean()

        return df

    # ══════════════════════════════════════════
    # SMC 지표 계산 (analytics/indicators.py 로직 인라인)
    # ══════════════════════════════════════════

    def _calculate_smc(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        SMC Market Structure 계산.
        analytics/indicators.py의 calculate_smc()를 인라인으로 가져옴
        (import 의존성을 줄이기 위해).
        """
        swing_length = self.smc.swing_length
        highs = df["high"].values
        lows = df["low"].values
        closes = df["close"].values
        opens = df["open"].values
        length = len(df)

        # 1. Swing Points (Pivot)
        df["is_swing_high"] = False
        df["is_swing_low"] = False

        swing_highs = []  # (index, price)
        swing_lows = []

        for i in range(swing_length, length - swing_length):
            is_sh = True
            is_sl = True
            for j in range(1, swing_length + 1):
                if highs[i] <= highs[i - j] or highs[i] <= highs[i + j]:
                    is_sh = False
                if lows[i] >= lows[i - j] or lows[i] >= lows[i + j]:
                    is_sl = False

            if is_sh:
                df.iat[i, df.columns.get_loc("is_swing_high")] = True
                swing_highs.append((i, highs[i]))
            if is_sl:
                df.iat[i, df.columns.get_loc("is_swing_low")] = True
                swing_lows.append((i, lows[i]))

        # 2. BOS, CHoCH, Order Blocks
        df["marker"] = None
        df["ob_top"] = np.nan
        df["ob_bottom"] = np.nan

        trend = 1  # 1: Bullish, -1: Bearish
        last_sh_idx, last_sh_price = -1, float("inf")
        last_sl_idx, last_sl_price = -1, float("-inf")

        for i in range(length):
            close = closes[i]

            # Lookahead bias 방지: swing_length만큼 지연 확인
            curr_confirmed_idx = i - swing_length
            if curr_confirmed_idx >= 0:
                if df["is_swing_high"].iloc[curr_confirmed_idx]:
                    last_sh_idx = curr_confirmed_idx
                    last_sh_price = highs[curr_confirmed_idx]
                if df["is_swing_low"].iloc[curr_confirmed_idx]:
                    last_sl_idx = curr_confirmed_idx
                    last_sl_price = lows[curr_confirmed_idx]

            if last_sh_idx != -1 and last_sl_idx != -1:
                if trend == 1:
                    if close > last_sh_price:  # BOS Bull
                        df.iat[i, df.columns.get_loc("marker")] = "BOS_BULL"
                        # OB: 마지막 음봉 (Order Block)
                        for j in range(i - 1, max(0, last_sl_idx - 5), -1):
                            if closes[j] < opens[j]:
                                df.iat[i, df.columns.get_loc("ob_top")] = highs[j]
                                df.iat[i, df.columns.get_loc("ob_bottom")] = lows[j]
                                break
                        last_sh_price = float("inf")
                    elif close < last_sl_price:  # CHoCH Bear
                        df.iat[i, df.columns.get_loc("marker")] = "CHOCH_BEAR"
                        trend = -1
                        last_sl_price = float("-inf")
                elif trend == -1:
                    if close < last_sl_price:  # BOS Bear
                        df.iat[i, df.columns.get_loc("marker")] = "BOS_BEAR"
                        for j in range(i - 1, max(0, last_sh_idx - 5), -1):
                            if closes[j] > opens[j]:
                                df.iat[i, df.columns.get_loc("ob_top")] = highs[j]
                                df.iat[i, df.columns.get_loc("ob_bottom")] = lows[j]
                                break
                        last_sl_price = float("-inf")
                    elif close > last_sh_price:  # CHoCH Bull
                        df.iat[i, df.columns.get_loc("marker")] = "CHOCH_BULL"
                        trend = 1
                        last_sh_price = float("inf")

        # 3. Fair Value Gap (FVG)
        df["fvg_top"] = np.nan
        df["fvg_bottom"] = np.nan
        df["fvg_type"] = None

        for i in range(2, length):
            c1_high = highs[i - 2]
            c1_low = lows[i - 2]
            c3_high = highs[i]
            c3_low = lows[i]

            if c3_low > c1_high:  # Bull FVG
                df.iat[i - 1, df.columns.get_loc("fvg_type")] = "bull"
                df.iat[i - 1, df.columns.get_loc("fvg_top")] = c3_low
                df.iat[i - 1, df.columns.get_loc("fvg_bottom")] = c1_high
            elif c3_high < c1_low:  # Bear FVG
                df.iat[i - 1, df.columns.get_loc("fvg_type")] = "bear"
                df.iat[i - 1, df.columns.get_loc("fvg_top")] = c1_low
                df.iat[i - 1, df.columns.get_loc("fvg_bottom")] = c3_high

        return df

    @staticmethod
    def _compute_adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """ADX / +DI / -DI 계산 (순수 pandas)."""
        h = df["high"].astype(float)
        lo = df["low"].astype(float)
        c = df["close"].astype(float)

        plus_dm = h.diff().clip(lower=0)
        minus_dm = (-lo.diff()).clip(lower=0)

        mask_plus = plus_dm <= minus_dm
        mask_minus = minus_dm <= plus_dm
        plus_dm = plus_dm.copy()
        minus_dm = minus_dm.copy()
        plus_dm[mask_plus] = 0
        minus_dm[mask_minus] = 0

        tr1 = h - lo
        tr2 = (h - c.shift()).abs()
        tr3 = (lo - c.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        atr = tr.rolling(window=period).mean()
        plus_di = 100 * (plus_dm.rolling(window=period).mean() / atr.replace(0, np.nan))
        minus_di = 100 * (minus_dm.rolling(window=period).mean() / atr.replace(0, np.nan))

        dx = (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan) * 100
        adx = dx.rolling(window=period).mean()

        df["adx"] = adx
        df["plus_di"] = plus_di
        df["minus_di"] = minus_di
        return df

    # ══════════════════════════════════════════
    # Layer 1: SMC Bias 스코어 (0~40)
    # ══════════════════════════════════════════

    def _score_smc_bias(self, df: pd.DataFrame) -> int:
        """
        최근 SMC 마커 + OB/FVG 근접도로 Bias 점수를 산출한다.
        - BOS_BULL → +25 (강한 상승 지속)
        - CHOCH_BULL → +20 (하락→상승 반전)
        - OB 근접 → +10
        - Bull FVG 미티게이션 → +5
        - BOS_BEAR, CHOCH_BEAR → 0
        """
        if len(df) < 10:
            return 0

        score = 0
        curr = df.iloc[-1]
        price = float(curr["close"])

        # 최근 N봉 내 가장 가까운 마커 찾기
        lookback = min(20, len(df))
        recent = df.iloc[-lookback:]
        markers = recent[recent["marker"].notna()]

        if not markers.empty:
            last_marker = markers.iloc[-1]["marker"]
            if last_marker == "BOS_BULL":
                score += 25
            elif last_marker == "CHOCH_BULL":
                score += 20
            elif last_marker == "BOS_BEAR":
                score += 0
            elif last_marker == "CHOCH_BEAR":
                score += 0

        # OB 근접도 (최근 OB 영역에 가격이 위치하는지)
        ob_rows = recent[recent["ob_top"].notna()]
        if not ob_rows.empty:
            last_ob = ob_rows.iloc[-1]
            ob_top = float(last_ob["ob_top"])
            ob_bottom = float(last_ob["ob_bottom"])
            # 가격이 OB 영역 내 또는 근접 (5% 이내)
            ob_range = ob_top - ob_bottom if ob_top > ob_bottom else 1.0
            if ob_bottom <= price <= ob_top:
                score += 10  # OB 영역 내 — 스마트 머니 수요 구간
            elif price < ob_top and price > ob_bottom - ob_range * 0.5:
                score += 5   # OB 근접

        # FVG 미티게이션 (Bull FVG 영역에 가격 진입)
        if self.smc.fvg_mitigation:
            fvg_rows = recent[(recent["fvg_type"] == "bull") & recent["fvg_top"].notna()]
            if not fvg_rows.empty:
                last_fvg = fvg_rows.iloc[-1]
                fvg_top = float(last_fvg["fvg_top"])
                fvg_bottom = float(last_fvg["fvg_bottom"])
                if fvg_bottom <= price <= fvg_top:
                    score += 5  # FVG 미티게이션 중

        return min(score, self.smc.weight_smc)

    # ══════════════════════════════════════════
    # Layer 2: Volatility Setup 스코어 (0~20)
    # ══════════════════════════════════════════

    def _score_volatility_setup(self, df: pd.DataFrame) -> int:
        """
        BB Squeeze + ATR 적정 범위 확인.
        - BB Squeeze (밴드 수축) → +15
        - ATR 적정 범위 → +5
        """
        if len(df) < 50:
            return 0

        score = 0
        curr = df.iloc[-1]

        # BB Squeeze: bb_width / 50일 평균 bb_width
        bb_width = float(curr.get("bb_width", 0)) if pd.notna(curr.get("bb_width")) else 0
        bb_avg_series = df["bb_width"].rolling(window=50).mean()
        bb_width_avg = float(bb_avg_series.iloc[-1]) if pd.notna(bb_avg_series.iloc[-1]) else bb_width
        if bb_width_avg > 0:
            squeeze_ratio = bb_width / bb_width_avg
        else:
            squeeze_ratio = 1.0

        if squeeze_ratio < 0.8:
            score += 15  # 에너지 응축 — 폭발 직전
        elif squeeze_ratio < 1.0:
            score += 8   # 약간의 수축

        # ATR 적정 범위 (너무 낮거나 높지 않은)
        atr_pct = float(curr.get("atr_pct", 0)) if pd.notna(curr.get("atr_pct")) else 0
        atr_avg = df["atr_pct"].rolling(window=50).mean()
        atr_avg_val = float(atr_avg.iloc[-1]) if pd.notna(atr_avg.iloc[-1]) else atr_pct
        if atr_avg_val > 0:
            atr_ratio = atr_pct / atr_avg_val
            if 0.5 <= atr_ratio <= 1.5:
                score += 5  # 적정 변동성

        return min(score, self.smc.weight_bb)

    # ══════════════════════════════════════════
    # Layer 3a: OBV 스코어 (0~20)
    # ══════════════════════════════════════════

    def _score_obv(self, df: pd.DataFrame) -> int:
        """
        OBV 추세 확인: EMA5 > EMA20 → 거래량 추세 상승.
        - OBV 상승 추세 → +10~20
        """
        if len(df) < 25:
            return 0

        score = 0
        curr = df.iloc[-1]

        obv_ema5 = float(curr.get("obv_ema5", 0)) if pd.notna(curr.get("obv_ema5")) else 0
        obv_ema20 = float(curr.get("obv_ema20", 0)) if pd.notna(curr.get("obv_ema20")) else 0

        if obv_ema5 > obv_ema20:
            score += 10  # OBV 상승 추세

            # 추가: OBV EMA 기울기가 양수 (5일 전 대비)
            if len(df) >= 6:
                obv_5ago = float(df.iloc[-6].get("obv_ema5", 0)) if pd.notna(df.iloc[-6].get("obv_ema5")) else 0
                if obv_ema5 > obv_5ago:
                    score += 5   # 기울기 양수 — 가속 중

            # 가격 돌파 + 거래량 동반 확인
            curr_vol = float(curr.get("volume", 0)) if pd.notna(curr.get("volume")) else 0
            vol_ma = float(curr.get("volume_ma", 1)) if pd.notna(curr.get("volume_ma")) else 1
            if vol_ma > 0 and curr_vol >= vol_ma * 1.3:
                score += 5   # 평균 이상 거래량

        return min(score, self.smc.weight_obv)

    # ══════════════════════════════════════════
    # Layer 3b: ADX/MACD 모멘텀 스코어 (0~20)
    # ══════════════════════════════════════════

    def _score_momentum(self, df: pd.DataFrame) -> int:
        """
        ADX + MACD 모멘텀 확인.
        - ADX > 25 → +10
        - MACD 히스토그램 양수 전환 → +10
        """
        if len(df) < 30:
            return 0

        score = 0
        curr = df.iloc[-1]
        prev = df.iloc[-2]

        # ADX > 25: 추세 존재
        adx = float(curr.get("adx", 0)) if pd.notna(curr.get("adx")) else 0
        plus_di = float(curr.get("plus_di", 0)) if pd.notna(curr.get("plus_di")) else 0
        minus_di = float(curr.get("minus_di", 0)) if pd.notna(curr.get("minus_di")) else 0

        if adx > 25 and plus_di > minus_di:
            score += 10  # 강한 상승 추세
        elif adx > 20 and plus_di > minus_di:
            score += 5   # 발전 중인 추세

        # MACD 골든크로스 또는 양수 히스토그램
        macd_hist = float(curr.get("macd_hist", 0)) if pd.notna(curr.get("macd_hist")) else 0
        prev_macd = float(prev.get("macd_hist", 0)) if pd.notna(prev.get("macd_hist")) else 0

        if prev_macd <= 0 and macd_hist > 0:
            score += 10  # MACD 골든크로스
        elif macd_hist > 0 and macd_hist > prev_macd:
            score += 5   # MACD 히스토그램 증가 추세

        return min(score, self.smc.weight_momentum)

    # ══════════════════════════════════════════
    # 진입 시그널 스캔 (4-Layer 통합)
    # ══════════════════════════════════════════

    def scan_entry_signals(
        self,
        universe_codes: List[str],
        ohlcv_data: Dict[str, pd.DataFrame],
        current_prices: Dict[str, PriceData],
    ) -> List[Signal]:
        """
        4-Layer 스코어 합산 → Score ≥ entry_threshold 시 Signal 반환.
        """
        signals = []

        for code in universe_codes:
            df = ohlcv_data.get(code)
            if df is None or df.empty or len(df) < 50:
                continue

            df = self.calculate_indicators(df.copy())
            if df.empty or len(df) < 2:
                continue

            curr = df.iloc[-1]
            price_data = current_prices.get(code)
            current_price = price_data.current_price if price_data else float(curr["close"])
            stock_name = price_data.stock_name if price_data else code

            # 4-Layer 스코어링
            score_smc = self._score_smc_bias(df)
            score_vol = self._score_volatility_setup(df)
            score_obv = self._score_obv(df)
            score_mom = self._score_momentum(df)
            total_score = score_smc + score_vol + score_obv + score_mom

            if total_score >= self.smc.entry_threshold:
                bb_upper = float(curr["bb_upper"]) if pd.notna(curr.get("bb_upper")) else float("inf")

                signal = Signal(
                    stock_code=code,
                    stock_name=stock_name,
                    signal_type="BUY",
                    primary_signals=[f"SMC_{total_score}"],
                    confirmation_filters=[
                        f"L1:{score_smc}",
                        f"L2:{score_vol}",
                        f"L3a:{score_obv}",
                        f"L3b:{score_mom}",
                    ],
                    current_price=current_price,
                    bb_upper=bb_upper,
                )
                # Override strength to use SMC total score
                signal.strength = total_score

                signals.append(signal)
                logger.info(
                    "SMC Entry | %s (%s) | score=%d [L1:%d L2:%d L3a:%d L3b:%d] | price=%.2f",
                    stock_name, code, total_score,
                    score_smc, score_vol, score_obv, score_mom, current_price,
                )

        # 점수 내림차순 정렬
        signals.sort(key=lambda s: s.strength, reverse=True)
        return signals

    # ══════════════════════════════════════════
    # 청산 시그널 스캔 (SMC 전용)
    # ══════════════════════════════════════════

    def scan_exit_signals(
        self,
        positions: list,
        ohlcv_data: Dict[str, pd.DataFrame],
        current_prices: Dict[str, PriceData],
    ) -> List[ExitSignal]:
        """
        SMC 전용 청산 로직.
        우선순위: ES1(-3%) > ATR SL > ATR TP > CHoCH > ES3 트레일링 > ES5 보유기간
        BR-S01: 손절 -3% 절대 불변 Floor 유지.
        """
        exit_signals = []

        for pos in positions:
            price_data = current_prices.get(pos.stock_code)
            if not price_data:
                continue

            current_price = price_data.current_price
            entry_price = pos.entry_price
            if not entry_price or entry_price <= 0:
                continue

            pnl_pct = (current_price - entry_price) / entry_price

            # ── ES1: 손절 -5% (CLAUDE.md Phase 5) ──
            if current_price <= entry_price * (1 + self.ec.stop_loss_pct):
                exit_signals.append(ExitSignal(
                    stock_code=pos.stock_code,
                    stock_name=pos.stock_name,
                    position_id=pos.position_id,
                    exit_type=ExitReason.STOP_LOSS.value,
                    exit_reason="STOP_LOSS",
                    order_type="MARKET",
                    current_price=current_price,
                    pnl_pct=pnl_pct,
                ))
                logger.info("EXIT ES1 STOP_LOSS | %s | pnl=%.2f%%", pos.stock_name, pnl_pct * 100)
                continue

            # ── ATR 기반 SL/TP ──
            df = ohlcv_data.get(pos.stock_code)
            atr_val = None
            if df is not None and len(df) > 14:
                df_calc = self.calculate_indicators(df.copy())
                last_atr = df_calc.iloc[-1].get("atr")
                if pd.notna(last_atr):
                    atr_val = float(last_atr)

            if atr_val is not None and atr_val > 0:
                # ATR SL: entry - ATR * mult (단, -3% Floor)
                atr_sl_price = entry_price - atr_val * self.smc.atr_sl_mult
                floor_sl_price = entry_price * (1 + self.ec.stop_loss_pct)
                effective_sl = max(atr_sl_price, floor_sl_price)  # -5% Floor 보장

                if current_price <= effective_sl and effective_sl > floor_sl_price:
                    exit_signals.append(ExitSignal(
                        stock_code=pos.stock_code,
                        stock_name=pos.stock_name,
                        position_id=pos.position_id,
                        exit_type="ES_SMC_SL",
                        exit_reason="ATR_STOP_LOSS",
                        order_type="MARKET",
                        current_price=current_price,
                        pnl_pct=pnl_pct,
                    ))
                    logger.info("EXIT ES_SMC_SL | %s | ATR SL=%.2f | pnl=%.2f%%",
                                pos.stock_name, effective_sl, pnl_pct * 100)
                    continue

                # ATR TP: entry + ATR * mult
                atr_tp_price = entry_price + atr_val * self.smc.atr_tp_mult
                if current_price >= atr_tp_price:
                    exit_signals.append(ExitSignal(
                        stock_code=pos.stock_code,
                        stock_name=pos.stock_name,
                        position_id=pos.position_id,
                        exit_type="ES_SMC_TP",
                        exit_reason="ATR_TAKE_PROFIT",
                        order_type="MARKET",
                        current_price=current_price,
                        pnl_pct=pnl_pct,
                    ))
                    logger.info("EXIT ES_SMC_TP | %s | ATR TP=%.2f | pnl=+%.2f%%",
                                pos.stock_name, atr_tp_price, pnl_pct * 100)
                    continue

            # ── CHoCH Exit: 추세 반전 감지 ──
            if self.smc.choch_exit and df is not None and len(df) > 10:
                df_calc = self.calculate_indicators(df.copy())
                recent_markers = df_calc.iloc[-5:]
                for _, row in recent_markers.iterrows():
                    if row.get("marker") == "CHOCH_BEAR":
                        exit_signals.append(ExitSignal(
                            stock_code=pos.stock_code,
                            stock_name=pos.stock_name,
                            position_id=pos.position_id,
                            exit_type="ES_CHOCH",
                            exit_reason="CHOCH_BEAR_EXIT",
                            order_type="MARKET",
                            current_price=current_price,
                            pnl_pct=pnl_pct,
                        ))
                        logger.info("EXIT ES_CHOCH | %s | CHoCH Bear 감지 | pnl=%.2f%%",
                                    pos.stock_name, pnl_pct * 100)
                        break
                else:
                    # CHoCH 없으면 다음 청산 조건으로
                    pass

                # CHoCH로 청산했으면 continue
                if exit_signals and exit_signals[-1].stock_code == pos.stock_code:
                    continue

            # ── ES3: 트레일링 스탑 ──
            trailing_high = pos.trailing_high or entry_price
            if current_price > trailing_high:
                trailing_high = current_price
            trailing_stop_price = trailing_high * (1 + self.ec.trailing_stop_pct)
            if current_price <= trailing_stop_price and trailing_high > entry_price:
                exit_signals.append(ExitSignal(
                    stock_code=pos.stock_code,
                    stock_name=pos.stock_name,
                    position_id=pos.position_id,
                    exit_type=ExitReason.TRAILING_STOP.value,
                    exit_reason="TRAILING_STOP",
                    order_type="MARKET",
                    current_price=current_price,
                    pnl_pct=pnl_pct,
                ))
                continue

            # ── ES5: 보유기간 초과 ──
            if pos.holding_days and pos.holding_days > self.ec.max_holding_days:
                exit_signals.append(ExitSignal(
                    stock_code=pos.stock_code,
                    stock_name=pos.stock_name,
                    position_id=pos.position_id,
                    exit_type=ExitReason.MAX_HOLDING.value,
                    exit_reason="MAX_HOLDING",
                    order_type="LIMIT",
                    current_price=current_price,
                    pnl_pct=pnl_pct,
                ))
                continue

        return exit_signals
