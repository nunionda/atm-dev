"""
Mean-Reversion SHORT Strategy — 별도 SHORT 전용 strategy (P).

SP500FuturesStrategy(trend-following LONG 위주)의 LONG-편향을 보완하는
독립 SHORT 신호 생성기. 강세장에서도 통계적 과매수 → 평균회귀 SHORT
진입을 가능하게 한다.

설계 원칙:
  - 4-Layer scoring 사용 안 함 — 단순 mean-reversion 조건만
  - 자체 entry threshold (느슨) + 자체 SL/TP (tighter R:R)
  - SHORT direction 고정
  - SP500FuturesStrategy와 병행 호출 (FuturesBacktester에서)

진입 조건 (모두 만족):
  1. zscore >= 1.5         (과매수)
  2. RSI >= 65             (과매수 모멘텀)
  3. close > ema_fast      (단기 EMA 위 — 추세 정점 가능성)
  4. (선택) BB upper 근접  — 추가 confirm

청산:
  - SL: entry + ATR × 1.0  (tighter than SP500 default)
  - TP: entry - ATR × 2.5  (R:R 2.5:1)
  - 또는 zscore <= 0 (평균 복귀) → 익절
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from common.types import FuturesSignal
from data.config_manager import ATSConfig
from infra.logger import get_logger

logger = get_logger("mean_reversion_short")


class MeanReversionShortStrategy:
    """평균회귀 SHORT 전용 전략.

    SP500FuturesStrategy가 LONG-편향이라 강세장 SHORT 진입 불가능한 문제를
    별도 trigger path로 우회. 통계적 과매수 시점 SHORT 진입.
    """

    def __init__(self, config: ATSConfig):
        self.config = config
        self.fc = config.sp500_futures  # multiplier, slippage 등 공유

        # MR-SHORT 전용 임계값.
        # P-2 (첫 시도 후 조정): Q3'25 강세장에서 MR-SHORT 1건이 LONG 4건을
        # 차단해 return +24% → +1.6%로 악화. 조건 strict하게 조정.
        self.zscore_threshold = 2.0      # 과매수 entry (1.5 → 2.0, strict)
        self.rsi_threshold = 75.0        # 과매수 RSI (65 → 75, strict)
        self.atr_sl_mult = 1.0           # SL tight
        self.atr_tp_mult = 2.5           # R:R 2.5:1
        self.signal_threshold = 50.0     # 자체 entry score 임계 (35 → 50)
        self.risk_per_trade_pct = 0.5    # 0.5% per trade (보수적)
        # BB upper 필수 — 더 보수적 over-extension 요구
        self.require_bb_top = True

    def generate_short_signal(
        self,
        ticker: str,
        df: pd.DataFrame,
        current_price: float,
        equity: float = 100_000.0,
    ) -> Optional[FuturesSignal]:
        """평균회귀 SHORT 신호 생성. 조건 미충족 시 None.

        Args:
            ticker: 대상 ticker (ES=F, NQ=F 등)
            df: indicator pre-calculated DataFrame
            current_price: 현재 종가
            equity: 현재 자본금

        Returns:
            FuturesSignal(direction='SHORT') 또는 None.
        """
        if df.empty or len(df) < 5:
            return None

        curr = df.iloc[-1]
        for col in ["zscore", "rsi", "atr", "ema_fast", "bb_upper"]:
            val = curr.get(col)
            if val is None or pd.isna(val):
                return None

        zscore = float(curr["zscore"])
        rsi = float(curr["rsi"])
        atr = float(curr["atr"])
        ema_fast = float(curr["ema_fast"])
        bb_upper = float(curr["bb_upper"])

        # ── 진입 조건 ──
        if zscore < self.zscore_threshold:
            return None
        if rsi < self.rsi_threshold:
            return None
        if current_price <= ema_fast:
            return None
        if atr <= 0:
            return None
        # BB upper 터치 필수 (over-extension confirm)
        if self.require_bb_top and current_price < bb_upper * 0.998:
            return None

        # ── 신호 강도 점수 (0-100, 진단/필터용) ──
        # zscore 절댓값 비례 (1.5→30, 2.5→50, 3.5→70+)
        z_score_pts = min(50.0, abs(zscore) * 20)
        # RSI 과매수 강도 (65→0, 80→30+)
        rsi_pts = max(0.0, (rsi - 65.0) * 2.0)
        # BB upper 근접 (close가 bb_upper 이상이면 만점)
        bb_pts = 20.0 if current_price >= bb_upper else 10.0 if current_price >= bb_upper * 0.995 else 0.0
        signal_strength = z_score_pts + rsi_pts + bb_pts

        if signal_strength < self.signal_threshold:
            return None

        # ── SL/TP ──
        sl = current_price + atr * self.atr_sl_mult
        tp = current_price - atr * self.atr_tp_mult
        rr_ratio = abs(tp - current_price) / abs(current_price - sl) if abs(current_price - sl) > 0 else 0

        # ── 포지션 사이징 (단순) ──
        is_micro = self.fc.is_micro
        multiplier = 5.0 if is_micro else self.fc.contract_multiplier
        risk_amount = equity * (self.risk_per_trade_pct / 100.0)
        dollar_risk = abs(current_price - sl) * multiplier
        contracts = max(1, int(risk_amount / dollar_risk)) if dollar_risk > 0 else 1
        contracts = min(contracts, self.fc.max_contracts)

        logger.info(
            "MR-SHORT signal | %s @ %.2f | Z=%.2f RSI=%.1f BB_top=%.2f | "
            "score=%.1f | SL=%.2f TP=%.2f | contracts=%d",
            ticker, current_price, zscore, rsi, bb_upper,
            signal_strength, sl, tp, contracts,
        )

        return FuturesSignal(
            ticker=ticker,
            direction="SHORT",
            signal_strength=signal_strength,
            entry_price=current_price,
            stop_loss=round(sl, 2),
            take_profit=round(tp, 2),
            atr=atr,
            z_score=zscore,
            primary_signals=[
                f"MR_Z_{zscore:.1f}",
                f"MR_RSI_{rsi:.0f}",
                "MR_BB_TOP" if current_price >= bb_upper else "MR_BB_NEAR",
            ],
            confirmation_filters=[],
            risk_reward_ratio=round(rr_ratio, 2),
            position_size_contracts=contracts,
            metadata={
                "strategy": "mean_reversion_short",
                "zscore": zscore,
                "rsi": rsi,
                "bb_upper": bb_upper,
                "signal_strength": signal_strength,
            },
        )
