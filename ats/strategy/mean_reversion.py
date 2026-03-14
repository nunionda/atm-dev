"""
Mean Reversion 전략 구현체.
과매도 구간의 평균 회귀를 포착하는 3-Layer 스코어링 전략.

3-Layer 스코어링:
  Layer 1 (40점): MR Signal — RSI 과매도, BB 하단, 장기 추세 유지
  Layer 2 (30점): Volatility & Volume — BB Width 확대, 거래량 스파이크, ATR 고조
  Layer 3 (30점): Confirmation — MACD 양전환, Stochastic 과매도 크로스, 연속 하락일

진입: Total Score ≥ entry_threshold (default 65)
레짐 필터: ADX < 25 (비추세 선호) OR RSI < 25 (극도 과매도 시 ADX 무시)

청산 우선순위:
  ES1(-5% 불변) > ATR SL > MR TP(MA20/RSI>60) > BB Mid > Trailing > Overbought > Max Holding
"""

from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

from common.enums import ExitReason
from common.types import ExitSignal, PriceData, Signal
from data.config_manager import ATSConfig, MeanReversionConfig
from infra.logger import get_logger
from strategy.base import BaseStrategy

logger = get_logger("mean_reversion")


class MeanReversionStrategy(BaseStrategy):
    """
    Mean Reversion 3-Layer 스코어링 전략.

    횡보/비추세 시장에서 과매도 종목의 평균 회귀를 포착한다.
    - Layer 1: MR Signal (RSI < 30, BB Lower 이탈, MA200 위)
    - Layer 2: Volatility & Volume (BB Width 확대, 거래량 스파이크, ATR 고조)
    - Layer 3: Confirmation (MACD 양전환, Stochastic 크로스, 연속 하락일)
    """

    def __init__(self, config: ATSConfig):
        self.config = config
        self.sc = config.strategy         # StrategyConfig (MA, MACD 등 공유)
        self.ec = config.exit             # ExitConfig
        self.mr = config.mean_reversion   # MeanReversionConfig

    # ══════════════════════════════════════════
    # 기술적 지표 계산
    # ══════════════════════════════════════════

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        기존 기술지표 + Mean Reversion 전용 지표를 통합 계산한다.
        추가 지표: MA200, Stochastic %K/%D, 연속 하락일 카운터
        """
        if df.empty or len(df) < max(200, self.sc.ma_long) + 5:
            return df

        c = df["close"].astype(float)
        v = df["volume"].astype(float)
        h = df["high"].astype(float)
        lo = df["low"].astype(float)

        # ── 이동평균선 ──
        df["ma_short"] = c.rolling(window=self.sc.ma_short).mean()
        df["ma_long"] = c.rolling(window=self.sc.ma_long).mean()
        df["ma200"] = c.rolling(window=200).mean()

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

        # ── Stochastic %K/%D ──
        k_period = self.mr.stochastic_k_period
        d_period = self.mr.stochastic_d_period
        lowest_low = lo.rolling(window=k_period).min()
        highest_high = h.rolling(window=k_period).max()
        denom = (highest_high - lowest_low).replace(0, np.nan)
        df["stoch_k"] = 100 * (c - lowest_low) / denom
        df["stoch_d"] = df["stoch_k"].rolling(window=d_period).mean()

        # ── 연속 하락일 카운터 ──
        daily_return = c.pct_change()
        is_down = (daily_return < 0).astype(int)
        # 연속 하락일 계산: 현재 봉까지 연속 하락 횟수
        consec = []
        count = 0
        for val in is_down:
            if val == 1:
                count += 1
            else:
                count = 0
            consec.append(count)
        df["consecutive_down_days"] = consec

        return df

    @staticmethod
    def _compute_adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """ADX / +DI / -DI 계산."""
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
    # Layer 1: MR Signal 스코어 (0~40)
    # ══════════════════════════════════════════

    def _score_mr_signal(self, df: pd.DataFrame) -> int:
        """
        Layer 1: Mean Reversion 시그널.
        - RSI(14) < 30 → +20 (과매도)
        - Price < BB Lower → +15 (평균 이탈)
        - Price > MA200 → +5 (장기 상승 추세 유지)
        """
        if len(df) < 200:
            return 0

        score = 0
        curr = df.iloc[-1]
        price = float(curr["close"])

        # RSI 과매도
        rsi = float(curr.get("rsi", 50)) if pd.notna(curr.get("rsi")) else 50
        if rsi < self.mr.rsi_oversold:
            score += 20

        # Price < BB Lower
        bb_lower = float(curr.get("bb_lower", 0)) if pd.notna(curr.get("bb_lower")) else 0
        if bb_lower > 0 and price < bb_lower:
            score += 15

        # Price > MA200 (장기 추세 유지)
        ma200 = float(curr.get("ma200", 0)) if pd.notna(curr.get("ma200")) else 0
        if ma200 > 0 and price > ma200:
            score += 5

        return min(score, self.mr.weight_signal)

    # ══════════════════════════════════════════
    # Layer 2: Volatility & Volume 스코어 (0~30)
    # ══════════════════════════════════════════

    def _score_mr_volatility(self, df: pd.DataFrame) -> int:
        """
        Layer 2: 변동성 & 거래량.
        - BB Width > 20일 평균 × 1.2 → +10 (변동성 확대)
        - Volume > MA20 × volume_spike_mult → +10 (투매/클라이맥스)
        - ATR > 20일 ATR MA × 1.5 → +10 (변동성 고조)
        """
        if len(df) < 30:
            return 0

        score = 0
        curr = df.iloc[-1]

        # BB Width 확대
        bb_width = float(curr.get("bb_width", 0)) if pd.notna(curr.get("bb_width")) else 0
        bb_width_avg = df["bb_width"].rolling(window=20).mean()
        bb_avg_val = float(bb_width_avg.iloc[-1]) if pd.notna(bb_width_avg.iloc[-1]) else bb_width
        if bb_avg_val > 0 and bb_width > bb_avg_val * 1.2:
            score += 10

        # 거래량 스파이크
        curr_vol = float(curr.get("volume", 0)) if pd.notna(curr.get("volume")) else 0
        vol_ma = float(curr.get("volume_ma", 1)) if pd.notna(curr.get("volume_ma")) else 1
        if vol_ma > 0 and curr_vol > vol_ma * self.mr.volume_spike_mult:
            score += 10

        # ATR 고조
        atr = float(curr.get("atr", 0)) if pd.notna(curr.get("atr")) else 0
        atr_ma = df["atr"].rolling(window=20).mean()
        atr_avg_val = float(atr_ma.iloc[-1]) if pd.notna(atr_ma.iloc[-1]) else atr
        if atr_avg_val > 0 and atr > atr_avg_val * 1.5:
            score += 10

        return min(score, self.mr.weight_volatility)

    # ══════════════════════════════════════════
    # Layer 3: Confirmation 스코어 (0~30)
    # ══════════════════════════════════════════

    def _score_mr_confirmation(self, df: pd.DataFrame) -> int:
        """
        Layer 3: 확인 시그널.
        - MACD 히스토그램 양전환 → +10 (모멘텀 전환)
        - Stochastic %K < 20 AND %K > %D 크로스 → +10 (과매도 확인)
        - 연속 하락일 ≥ consecutive_down_days → +10 (과매도 스트레칭)
        """
        if len(df) < 30:
            return 0

        score = 0
        curr = df.iloc[-1]
        prev = df.iloc[-2]

        # MACD 히스토그램 양전환
        macd_hist = float(curr.get("macd_hist", 0)) if pd.notna(curr.get("macd_hist")) else 0
        prev_macd = float(prev.get("macd_hist", 0)) if pd.notna(prev.get("macd_hist")) else 0
        if prev_macd <= 0 and macd_hist > 0:
            score += 10

        # Stochastic 과매도 크로스
        stoch_k = float(curr.get("stoch_k", 50)) if pd.notna(curr.get("stoch_k")) else 50
        stoch_d = float(curr.get("stoch_d", 50)) if pd.notna(curr.get("stoch_d")) else 50
        prev_stoch_k = float(prev.get("stoch_k", 50)) if pd.notna(prev.get("stoch_k")) else 50
        prev_stoch_d = float(prev.get("stoch_d", 50)) if pd.notna(prev.get("stoch_d")) else 50
        if stoch_k < 20 and prev_stoch_k <= prev_stoch_d and stoch_k > stoch_d:
            score += 10

        # 연속 하락일
        consec_down = int(curr.get("consecutive_down_days", 0))
        if consec_down >= self.mr.consecutive_down_days:
            score += 10

        return min(score, self.mr.weight_confirmation)

    # ══════════════════════════════════════════
    # 진입 시그널 스캔 (3-Layer 통합)
    # ══════════════════════════════════════════

    def scan_entry_signals(
        self,
        universe_codes: List[str],
        ohlcv_data: Dict[str, pd.DataFrame],
        current_prices: Dict[str, PriceData],
    ) -> List[Signal]:
        """
        3-Layer 스코어 합산 → Score ≥ entry_threshold 시 Signal 반환.
        레짐 필터: ADX < adx_trending_limit (비추세) OR RSI < extreme_oversold_rsi
        """
        signals = []

        for code in universe_codes:
            df = ohlcv_data.get(code)
            if df is None or df.empty or len(df) < 200:
                continue

            df = self.calculate_indicators(df.copy())
            if df.empty or len(df) < 2:
                continue

            curr = df.iloc[-1]

            # 레짐 필터: ADX < 25 (비추세 선호) OR 극도 과매도 시 무시
            adx = float(curr.get("adx", 0)) if pd.notna(curr.get("adx")) else 0
            rsi = float(curr.get("rsi", 50)) if pd.notna(curr.get("rsi")) else 50
            if adx >= self.mr.adx_trending_limit and rsi >= self.mr.extreme_oversold_rsi:
                continue  # 추세장이면서 극도 과매도 아님 → 스킵

            price_data = current_prices.get(code)
            current_price = price_data.current_price if price_data else float(curr["close"])
            stock_name = price_data.stock_name if price_data else code

            # 3-Layer 스코어링
            score_signal = self._score_mr_signal(df)
            score_vol = self._score_mr_volatility(df)
            score_confirm = self._score_mr_confirmation(df)
            total_score = score_signal + score_vol + score_confirm

            if total_score >= self.mr.entry_threshold:
                signal = Signal(
                    stock_code=code,
                    stock_name=stock_name,
                    signal_type="BUY",
                    primary_signals=[f"MR_{total_score}"],
                    confirmation_filters=[
                        f"L1:{score_signal}",
                        f"L2:{score_vol}",
                        f"L3:{score_confirm}",
                    ],
                    current_price=current_price,
                    bb_upper=float(curr.get("bb_upper", float("inf"))) if pd.notna(curr.get("bb_upper")) else float("inf"),
                )
                signal.strength = total_score
                signals.append(signal)

                logger.info(
                    "MR Entry | %s (%s) | score=%d [L1:%d L2:%d L3:%d] | RSI=%.0f | price=%.2f",
                    stock_name, code, total_score,
                    score_signal, score_vol, score_confirm, rsi, current_price,
                )

        signals.sort(key=lambda s: s.strength, reverse=True)
        return signals

    # ══════════════════════════════════════════
    # 청산 시그널 스캔 (7-Priority Cascade)
    # ══════════════════════════════════════════

    def scan_exit_signals(
        self,
        positions: list,
        ohlcv_data: Dict[str, pd.DataFrame],
        current_prices: Dict[str, PriceData],
    ) -> List[ExitSignal]:
        """
        Mean Reversion 전용 7-Priority 청산 cascade:
        1. ES1: -5% 하드 스톱 (BR-S01 불변)
        2. ES_MR_SL: Entry - ATR × 1.5
        3. ES_MR_TP: Price > MA20 OR RSI > 60 (평균 회귀 도달)
        4. ES_MR_BB: Price > BB 중간밴드 (평균 복귀)
        5. ES3: Progressive trailing
        6. ES_MR_OB: RSI > 70 (과매수 전환)
        7. ES5: 최대 보유 15일
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

            # ── Priority 1: ES1 손절 -5% ──
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

            # ATR 조회
            df = ohlcv_data.get(pos.stock_code)
            atr_val = None
            rsi_val = None
            bb_mid = None
            ma20 = None
            if df is not None and len(df) > 200:
                df_calc = self.calculate_indicators(df.copy())
                last = df_calc.iloc[-1]
                if pd.notna(last.get("atr")):
                    atr_val = float(last["atr"])
                if pd.notna(last.get("rsi")):
                    rsi_val = float(last["rsi"])
                if pd.notna(last.get("bb_middle")):
                    bb_mid = float(last["bb_middle"])
                if pd.notna(last.get("ma_long")):
                    ma20 = float(last["ma_long"])

            # ── Priority 2: ATR SL ──
            if atr_val and atr_val > 0:
                atr_sl_price = entry_price - atr_val * self.mr.atr_sl_mult
                floor_sl = entry_price * (1 + self.ec.stop_loss_pct)
                effective_sl = max(atr_sl_price, floor_sl)
                if current_price <= effective_sl and effective_sl > floor_sl:
                    exit_signals.append(ExitSignal(
                        stock_code=pos.stock_code,
                        stock_name=pos.stock_name,
                        position_id=pos.position_id,
                        exit_type="ES_MR_SL",
                        exit_reason="ATR_STOP_LOSS",
                        order_type="MARKET",
                        current_price=current_price,
                        pnl_pct=pnl_pct,
                    ))
                    logger.info("EXIT ES_MR_SL | %s | pnl=%.2f%%", pos.stock_name, pnl_pct * 100)
                    continue

            # ── Priority 3: MR TP (평균 회귀 도달) ──
            if ma20 and current_price > ma20:
                exit_signals.append(ExitSignal(
                    stock_code=pos.stock_code,
                    stock_name=pos.stock_name,
                    position_id=pos.position_id,
                    exit_type="ES_MR_TP",
                    exit_reason="MEAN_REVERSION_TP",
                    order_type="LIMIT",
                    current_price=current_price,
                    pnl_pct=pnl_pct,
                ))
                logger.info("EXIT ES_MR_TP | %s | Price > MA20 | pnl=%.2f%%", pos.stock_name, pnl_pct * 100)
                continue

            if rsi_val is not None and rsi_val > 60:
                exit_signals.append(ExitSignal(
                    stock_code=pos.stock_code,
                    stock_name=pos.stock_name,
                    position_id=pos.position_id,
                    exit_type="ES_MR_TP",
                    exit_reason="MEAN_REVERSION_TP",
                    order_type="LIMIT",
                    current_price=current_price,
                    pnl_pct=pnl_pct,
                ))
                logger.info("EXIT ES_MR_TP | %s | RSI > 60 | pnl=%.2f%%", pos.stock_name, pnl_pct * 100)
                continue

            # ── Priority 4: BB Mid (평균 복귀) ──
            if bb_mid and current_price > bb_mid:
                exit_signals.append(ExitSignal(
                    stock_code=pos.stock_code,
                    stock_name=pos.stock_name,
                    position_id=pos.position_id,
                    exit_type="ES_MR_BB",
                    exit_reason="BB_MID_REVERT",
                    order_type="LIMIT",
                    current_price=current_price,
                    pnl_pct=pnl_pct,
                ))
                logger.info("EXIT ES_MR_BB | %s | Price > BB Mid | pnl=%.2f%%", pos.stock_name, pnl_pct * 100)
                continue

            # ── Priority 5: Trailing Stop ──
            trailing_high = pos.trailing_high or entry_price
            if current_price > trailing_high:
                trailing_high = current_price
            if pnl_pct >= 0.07:
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

            # ── Priority 6: Overbought (RSI > 70) ──
            if rsi_val is not None and rsi_val > self.mr.rsi_overbought:
                exit_signals.append(ExitSignal(
                    stock_code=pos.stock_code,
                    stock_name=pos.stock_name,
                    position_id=pos.position_id,
                    exit_type="ES_MR_OB",
                    exit_reason="OVERBOUGHT_EXIT",
                    order_type="LIMIT",
                    current_price=current_price,
                    pnl_pct=pnl_pct,
                ))
                logger.info("EXIT ES_MR_OB | %s | RSI > 70 | pnl=%.2f%%", pos.stock_name, pnl_pct * 100)
                continue

            # ── Priority 7: Max Holding ──
            if pos.holding_days and pos.holding_days > self.mr.max_holding_days:
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
