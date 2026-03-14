"""
모멘텀 스윙 트레이딩 전략 구현체
문서: ATS-BRD-001 §2, ATS-SAD-001 §5.2

시그널 체계:
  주 시그널 (PS1, PS2) → 보조 필터 (CF1, CF2) → 리스크 게이트 (별도 RiskManager)
청산 우선순위:
  ES1(손절-5%) > ES2(익절 체제별) > ES3(Progressive ATR) > ES4(데드크로스) > ES5(보유기간 체제별)
"""

from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

from common.enums import ExitReason
from common.types import ExitSignal, PriceData, Signal
from data.config_manager import ATSConfig
from infra.logger import get_logger
from strategy.base import BaseStrategy

logger = get_logger("momentum_swing")


class MomentumSwingStrategy(BaseStrategy):
    """
    모멘텀 스윙 전략 (BRD §2 전략 정의).
    
    진입: 골든크로스 or MACD 매수 → RSI 필터 or 거래량 필터
    청산: 손절(-5%) > 익절(+20%) > 트레일링(ATR) > 데드크로스 > 보유기간(40일)
    """

    def __init__(self, config: ATSConfig):
        self.config = config
        self.sc = config.strategy  # StrategyConfig
        self.ec = config.exit      # ExitConfig

    # ══════════════════════════════════════════
    # 기술적 지표 계산
    # ══════════════════════════════════════════

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        OHLCV DataFrame에 기술적 지표 컬럼을 추가한다.
        필요 컬럼: close, volume
        """
        if df.empty or len(df) < self.sc.ma_long:
            return df

        c = df["close"].astype(float)
        v = df["volume"].astype(float)

        # ── 이동평균선 (BRD §2.3.1 PS1) ──
        df["ma_short"] = c.rolling(window=self.sc.ma_short).mean()
        df["ma_long"] = c.rolling(window=self.sc.ma_long).mean()
        df["ma60"] = c.rolling(window=60).mean()  # PS3 풀백 진입용

        # ── MACD (BRD §2.3.1 PS2) ──
        ema_fast = c.ewm(span=self.sc.macd_fast, adjust=False).mean()
        ema_slow = c.ewm(span=self.sc.macd_slow, adjust=False).mean()
        df["macd_line"] = ema_fast - ema_slow
        df["macd_signal"] = df["macd_line"].ewm(span=self.sc.macd_signal, adjust=False).mean()
        df["macd_hist"] = df["macd_line"] - df["macd_signal"]

        # ── RSI (BRD §2.3.2 CF1) ──
        delta = c.diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)
        avg_gain = gain.rolling(window=self.sc.rsi_period).mean()
        avg_loss = loss.rolling(window=self.sc.rsi_period).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        df["rsi"] = 100 - (100 / (1 + rs))

        # ── 볼린저밴드 (BRD §2.3.3 RG4) ──
        bb_ma = c.rolling(window=self.sc.bb_period).mean()
        bb_std = c.rolling(window=self.sc.bb_period).std()
        df["bb_upper"] = bb_ma + (bb_std * self.sc.bb_std)
        df["bb_lower"] = bb_ma - (bb_std * self.sc.bb_std)
        df["bb_middle"] = bb_ma

        # ── 거래량 이동평균 (BRD §2.3.2 CF2) ──
        df["volume_ma"] = v.rolling(window=self.sc.volume_ma_period).mean()

        return df

    # ══════════════════════════════════════════
    # 진입 시그널 스캔 (UC-02)
    # ══════════════════════════════════════════

    def scan_entry_signals(
        self,
        universe_codes: List[str],
        ohlcv_data: Dict[str, pd.DataFrame],
        current_prices: Dict[str, PriceData],
    ) -> List[Signal]:
        """
        매수 시그널을 스캔한다.
        
        흐름:
        1. 각 종목별 지표 계산
        2. 주 시그널 (PS1, PS2) 체크
        3. 보조 필터 (CF1, CF2) 체크
        4. 시그널 강도 정렬
        """
        signals = []

        for code in universe_codes:
            df = ohlcv_data.get(code)
            if df is None or df.empty or len(df) < self.sc.ma_long + 5:
                continue

            # 지표 계산
            df = self.calculate_indicators(df.copy())
            if df.empty:
                continue

            curr = df.iloc[-1]
            prev = df.iloc[-2]

            price_data = current_prices.get(code)
            current_price = price_data.current_price if price_data else float(curr["close"])
            stock_name = price_data.stock_name if price_data else code

            # ── Step 1: 주 시그널 체크 ──
            primary = []

            # PS1: 골든크로스 (단기MA가 장기MA를 아래에서 위로 돌파)
            if (
                pd.notna(curr["ma_short"]) and pd.notna(curr["ma_long"])
                and pd.notna(prev["ma_short"]) and pd.notna(prev["ma_long"])
            ):
                if prev["ma_short"] <= prev["ma_long"] and curr["ma_short"] > curr["ma_long"]:
                    primary.append("PS1")

            # PS2: MACD 매수 시그널 (MACD가 시그널을 아래에서 위로 돌파)
            if (
                pd.notna(curr["macd_hist"]) and pd.notna(prev["macd_hist"])
            ):
                if prev["macd_hist"] <= 0 and curr["macd_hist"] > 0:
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

            if not primary:
                continue  # 주 시그널 없으면 스킵

            # ── Step 2: 보조 필터 체크 ──
            confirmations = []

            # CF1: RSI 적정 범위 (52~78, CLAUDE.md Phase 3)
            if pd.notna(curr["rsi"]):
                if self.sc.rsi_lower <= curr["rsi"] <= self.sc.rsi_upper:
                    confirmations.append("CF1")

            # CF2: 거래량 증가 (20일 평균 × 1.5배 이상)
            if pd.notna(curr["volume_ma"]) and curr["volume_ma"] > 0:
                if float(curr["volume"]) >= curr["volume_ma"] * self.sc.volume_multiplier:
                    confirmations.append("CF2")

            # PS3 전용: 추세 지속 진입은 완화된 확인 임계값 사용
            if "PS3" in primary and not confirmations:
                # CF1_R: RSI 42-82 (기존 52-78 → 완화)
                if pd.notna(curr["rsi"]) and 42 <= float(curr["rsi"]) <= 82:
                    confirmations.append("CF1_R")

                # CF2_R: 거래량 >= MA20 × 1.0 (기존 1.5 → 완화, 대형주 안정 거래량 반영)
                if pd.notna(curr["volume_ma"]) and curr["volume_ma"] > 0:
                    if float(curr["volume"]) >= curr["volume_ma"] * 1.0:
                        confirmations.append("CF2_R")

            if not confirmations:
                continue  # 보조 필터 0개면 스킵

            # ── Step 3: 매수 후보 확정 ──
            bb_upper = float(curr["bb_upper"]) if pd.notna(curr["bb_upper"]) else float("inf")

            signal = Signal(
                stock_code=code,
                stock_name=stock_name,
                signal_type="BUY",
                primary_signals=primary,
                confirmation_filters=confirmations,
                current_price=current_price,
                bb_upper=bb_upper,
            )

            signals.append(signal)
            logger.info(
                "Entry signal | %s (%s) | primary=%s | confirm=%s | strength=%d | price=%.0f",
                stock_name, code, primary, confirmations, signal.strength, current_price,
            )

        # 시그널 강도 내림차순 정렬
        signals.sort(key=lambda s: s.strength, reverse=True)
        return signals

    # ══════════════════════════════════════════
    # 청산 시그널 스캔 (UC-04)
    # ══════════════════════════════════════════

    def scan_exit_signals(
        self,
        positions: list,
        ohlcv_data: Dict[str, pd.DataFrame],
        current_prices: Dict[str, PriceData],
    ) -> List[ExitSignal]:
        """
        보유 포지션의 청산 시그널을 스캔한다.
        우선순위: ES1(손절-5%) > ES2(익절) > ES3(트레일링) > ES4(데드크로스) > ES5(보유기간)
        각 포지션당 최우선 시그널 1개만 반환.
        """
        exit_signals = []

        for pos in positions:
            price_data = current_prices.get(pos.stock_code)
            if not price_data:
                logger.warning("No price data for position | stock=%s", pos.stock_code)
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
                logger.info(
                    "EXIT ES1 STOP_LOSS | %s | pnl=%.2f%% | price=%.0f → %.0f",
                    pos.stock_name, pnl_pct * 100, entry_price, current_price,
                )
                continue

            # ── ES2: 익절 ──
            if current_price >= entry_price * (1 + self.ec.take_profit_pct):
                exit_signals.append(ExitSignal(
                    stock_code=pos.stock_code,
                    stock_name=pos.stock_name,
                    position_id=pos.position_id,
                    exit_type=ExitReason.TAKE_PROFIT.value,
                    exit_reason="TAKE_PROFIT",
                    order_type="MARKET",
                    current_price=current_price,
                    pnl_pct=pnl_pct,
                ))
                logger.info(
                    "EXIT ES2 TAKE_PROFIT | %s | pnl=+%.2f%%",
                    pos.stock_name, pnl_pct * 100,
                )
                continue

            # ── ES3: 트레일링 스탑 ──
            trailing_high = pos.trailing_high or entry_price
            if current_price > trailing_high:
                trailing_high = current_price  # 최고가 갱신

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
                logger.info(
                    "EXIT ES3 TRAILING_STOP | %s | high=%.0f → price=%.0f",
                    pos.stock_name, trailing_high, current_price,
                )
                continue

            # ── ES4: 데드크로스 ──
            df = ohlcv_data.get(pos.stock_code)
            if df is not None and len(df) >= self.sc.ma_long + 2:
                df_calc = self.calculate_indicators(df.copy())
                if not df_calc.empty:
                    curr_row = df_calc.iloc[-1]
                    prev_row = df_calc.iloc[-2]
                    if (
                        pd.notna(curr_row["ma_short"]) and pd.notna(curr_row["ma_long"])
                        and pd.notna(prev_row["ma_short"]) and pd.notna(prev_row["ma_long"])
                    ):
                        if (
                            prev_row["ma_short"] >= prev_row["ma_long"]
                            and curr_row["ma_short"] < curr_row["ma_long"]
                        ):
                            exit_signals.append(ExitSignal(
                                stock_code=pos.stock_code,
                                stock_name=pos.stock_name,
                                position_id=pos.position_id,
                                exit_type=ExitReason.DEAD_CROSS.value,
                                exit_reason="DEAD_CROSS",
                                order_type="LIMIT",
                                current_price=current_price,
                                pnl_pct=pnl_pct,
                            ))
                            logger.info("EXIT ES4 DEAD_CROSS | %s", pos.stock_name)
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
                logger.info(
                    "EXIT ES5 MAX_HOLDING | %s | days=%d",
                    pos.stock_name, pos.holding_days,
                )
                continue

            # ── HOLD: 해당 없음 → 트레일링 최고가만 갱신 ──
            # (PositionManager에서 trailing_high 갱신 처리)

        return exit_signals
