"""
S&P 500 선물지수 매매 신호 전략 (E-mini ES / Micro MES)

4-Layer 스코어링 기반 양방향(롱/숏) 진입 + 다단계 청산 엔진

진입 시그널:
  Layer 1 — Z-Score 통계적 위치 (25점)
  Layer 2 — 추세/구조 (EMA 정렬, MA200 방향) (25점)
  Layer 3 — 모멘텀 (MACD, ADX/DMI, RSI) (25점)
  Layer 4 — 거래량/OBV 확인 (25점)
  → 총점 ≥ 60/100 시 진입

청산 시그널 (우선순위):
  ES1: 하드 손절 (-3%)
  ES_ATR_SL: ATR 기반 동적 손절 (ADX 기반 배수 조정)
  ES_ATR_TP: ATR 기반 익절 (R:R ≥ 2:1)
  ES_CHANDELIER: 샹들리에 청산 (최고/최저가 - 3×ATR)
  ES3: 프로그레시브 트레일링 스탑
  ES_CHOCH: 구조 반전 (MACD 데드/골든 크로스)
  ES5: 최대 보유기간 초과

참조:
  - stock_theory/futuresStrategy.md (Z-Score, EV Engine)
  - stock_theory/future_trading_stratedy.md (ATR 기반 진입/청산)
  - CLAUDE.md §Strategy 2: SMC 4-Layer Scoring
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from common.enums import ExitReason, FuturesDirection
from common.types import ExitSignal, FuturesSignal, PriceData, Signal
from data.config_manager import ATSConfig, SP500FuturesConfig
from infra.logger import get_logger
from strategy.base import BaseStrategy

logger = get_logger("sp500_futures")


# ══════════════════════════════════════════
# 내부 상태 관리
# ══════════════════════════════════════════

@dataclass
class FuturesPositionState:
    """선물 포지션 상태 추적."""
    direction: str = "NEUTRAL"          # LONG / SHORT / NEUTRAL
    entry_price: float = 0.0
    highest_since_entry: float = 0.0    # 진입 이후 최고가 (롱)
    lowest_since_entry: float = float("inf")  # 진입 이후 최저가 (숏)
    trailing_active: bool = False
    bars_held: int = 0


class SP500FuturesStrategy(BaseStrategy):
    """
    S&P 500 선물 매매 신호 전략.

    핵심 원리: "Trade the Edge, Not the Noise"
    - Z-Score로 통계적 과매수/과매도 감지
    - ATR로 변동성 기반 동적 손절/익절
    - 다중 타임프레임 추세 필터
    - 거래량 확인으로 가짜 돌파 배제
    """

    def __init__(self, config: ATSConfig):
        self.config = config
        self.fc: SP500FuturesConfig = config.sp500_futures
        self._position_states: Dict[str, FuturesPositionState] = {}

    # ══════════════════════════════════════════
    # 1. 기술적 지표 계산
    # ══════════════════════════════════════════

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        OHLCV DataFrame에 선물 매매용 기술적 지표를 추가한다.

        추가 컬럼:
          이동평균: ema_fast, ema_mid, ema_slow, ma_trend
          MACD: macd_line, macd_signal, macd_hist
          RSI: rsi
          볼린저밴드: bb_upper, bb_lower, bb_middle, bb_width, bb_squeeze_ratio
          ATR: atr, atr_pct
          ADX/DMI: adx, plus_di, minus_di
          Z-Score: zscore
          거래량: volume_ma, volume_ratio
          OBV: obv, obv_ema_fast, obv_ema_slow
        """
        if df.empty or len(df) < max(self.fc.ma_trend, self.fc.macd_slow + self.fc.macd_signal):
            return df

        c = df["close"].astype(float)
        h = df["high"].astype(float)
        lo = df["low"].astype(float)
        v = df["volume"].astype(float)

        # ── EMA (추세 필터) ──
        df["ema_fast"] = c.ewm(span=self.fc.ma_fast, adjust=False).mean()
        df["ema_mid"] = c.ewm(span=self.fc.ma_mid, adjust=False).mean()
        df["ema_slow"] = c.ewm(span=self.fc.ma_slow, adjust=False).mean()
        df["ma_trend"] = c.rolling(window=self.fc.ma_trend).mean()

        # ── MACD ──
        ema_fast_macd = c.ewm(span=self.fc.macd_fast, adjust=False).mean()
        ema_slow_macd = c.ewm(span=self.fc.macd_slow, adjust=False).mean()
        df["macd_line"] = ema_fast_macd - ema_slow_macd
        df["macd_signal"] = df["macd_line"].ewm(span=self.fc.macd_signal, adjust=False).mean()
        df["macd_hist"] = df["macd_line"] - df["macd_signal"]

        # ── RSI ──
        delta = c.diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)
        avg_gain = gain.ewm(span=self.fc.rsi_period, adjust=False).mean()
        avg_loss = loss.ewm(span=self.fc.rsi_period, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        df["rsi"] = 100 - (100 / (1 + rs))

        # ── 볼린저밴드 ──
        bb_ma = c.rolling(window=self.fc.bb_period).mean()
        bb_std_val = c.rolling(window=self.fc.bb_period).std()
        df["bb_upper"] = bb_ma + (bb_std_val * self.fc.bb_std)
        df["bb_lower"] = bb_ma - (bb_std_val * self.fc.bb_std)
        df["bb_middle"] = bb_ma
        bb_width = df["bb_upper"] - df["bb_lower"]
        df["bb_width"] = bb_width
        bb_width_ma = bb_width.rolling(window=self.fc.bb_period).mean()
        df["bb_squeeze_ratio"] = (bb_width / bb_width_ma.replace(0, np.nan)).fillna(1.0)

        # ── ATR ──
        tr1 = h - lo
        tr2 = (h - c.shift(1)).abs()
        tr3 = (lo - c.shift(1)).abs()
        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        df["atr"] = true_range.rolling(window=self.fc.atr_period).mean()
        df["atr_pct"] = (df["atr"] / c * 100).fillna(0)

        # ── ADX / DMI ──
        df["adx"], df["plus_di"], df["minus_di"] = self._calc_adx_dmi(h, lo, c, self.fc.adx_period)

        # ── Z-Score ──
        ma_z = c.rolling(window=self.fc.zscore_ma_period).mean()
        std_z = c.rolling(window=self.fc.zscore_std_period).std()
        df["zscore"] = ((c - ma_z) / std_z.replace(0, np.nan)).fillna(0)

        # ── 거래량 ──
        df["volume_ma"] = v.rolling(window=self.fc.volume_ma_period).mean()
        df["volume_ratio"] = (v / df["volume_ma"].replace(0, np.nan)).fillna(1.0)

        # ── OBV ──
        obv = np.where(c > c.shift(1), v, np.where(c < c.shift(1), -v, 0))
        df["obv"] = pd.Series(obv, index=df.index).cumsum()
        df["obv_ema_fast"] = df["obv"].ewm(span=self.fc.obv_ema_fast, adjust=False).mean()
        df["obv_ema_slow"] = df["obv"].ewm(span=self.fc.obv_ema_slow, adjust=False).mean()

        return df

    @staticmethod
    def _calc_adx_dmi(
        high: pd.Series, low: pd.Series, close: pd.Series, period: int
    ) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """ADX / +DI / -DI 계산."""
        plus_dm = high.diff()
        minus_dm = -low.diff()

        plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
        minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)

        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        atr_smooth = tr.ewm(span=period, adjust=False).mean()
        plus_di = 100 * (plus_dm.ewm(span=period, adjust=False).mean() / atr_smooth.replace(0, np.nan))
        minus_di = 100 * (minus_dm.ewm(span=period, adjust=False).mean() / atr_smooth.replace(0, np.nan))

        dx = (100 * ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan))).fillna(0)
        adx = dx.ewm(span=period, adjust=False).mean()

        return adx.fillna(0), plus_di.fillna(0), minus_di.fillna(0)

    # ══════════════════════════════════════════
    # 2. 진입 시그널 스캔
    # ══════════════════════════════════════════

    def scan_entry_signals(
        self,
        universe_codes: List[str],
        ohlcv_data: Dict[str, pd.DataFrame],
        current_prices: Dict[str, PriceData],
    ) -> List[Signal]:
        """
        S&P 500 선물 진입 시그널을 스캔한다.

        4-Layer 스코어링:
          L1 Z-Score: 통계적 과매수/과매도 위치
          L2 추세: EMA 정렬 + MA200 방향
          L3 모멘텀: MACD 크로스 + ADX 강도 + RSI 확인
          L4 거래량: 거래량 폭증 + OBV 추세
        """
        signals = []

        for code in universe_codes:
            df = ohlcv_data.get(code)
            if df is None or df.empty:
                continue

            min_len = max(self.fc.ma_trend, self.fc.macd_slow + self.fc.macd_signal) + 5
            if len(df) < min_len:
                continue

            df = self.calculate_indicators(df.copy())
            if df.empty:
                continue

            result = self._evaluate_entry(code, df, current_prices)
            if result is not None:
                signals.append(result)

        signals.sort(key=lambda s: s.strength, reverse=True)
        return signals

    def _evaluate_entry(
        self,
        code: str,
        df: pd.DataFrame,
        current_prices: Dict[str, PriceData],
    ) -> Optional[Signal]:
        """단일 종목 진입 평가. 4-Layer 스코어링 + 방향 결정."""
        curr = df.iloc[-1]
        prev = df.iloc[-2]

        price_data = current_prices.get(code)
        current_price = price_data.current_price if price_data else float(curr["close"])
        stock_name = price_data.stock_name if price_data else code

        # ── 방향 결정 (롱 vs 숏) ──
        direction = self._determine_direction(df)
        if direction == FuturesDirection.NEUTRAL:
            return None

        is_long = direction == FuturesDirection.LONG

        # ── 4-Layer 스코어링 ──
        l1_score, l1_signals = self._score_zscore(df, is_long)
        l2_score, l2_signals = self._score_trend(df, is_long)
        l3_score, l3_signals = self._score_momentum(df, is_long)
        l4_score, l4_signals = self._score_volume(df, is_long)

        total_score = l1_score + l2_score + l3_score + l4_score
        all_primaries = l1_signals + l2_signals
        all_confirms = l3_signals + l4_signals

        # ── 진입 임계값 체크 ──
        if total_score < self.fc.entry_threshold:
            return None

        # ── ATR 돌파 필터 ──
        if not self._check_atr_breakout(df, is_long):
            return None

        # ── 페이크아웃 필터 ──
        if not self._check_fakeout_filter(df, is_long):
            return None

        # ── 시그널 생성 ──
        atr = float(curr["atr"]) if pd.notna(curr["atr"]) else 0
        sl, tp = self._calculate_sl_tp(current_price, atr, is_long, float(curr.get("adx", 0)))

        signal = Signal(
            stock_code=code,
            stock_name=stock_name,
            signal_type="BUY" if is_long else "SELL",
            primary_signals=all_primaries,
            confirmation_filters=all_confirms,
            current_price=current_price,
        )

        # FuturesSignal 메타데이터를 Signal에 저장
        signal.bb_upper = float(curr.get("bb_upper", float("inf")))

        logger.info(
            "FUTURES %s | %s | score=%d (Z:%.0f T:%.0f M:%.0f V:%.0f) | "
            "price=%.2f | SL=%.2f | TP=%.2f | ATR=%.2f | Z=%.2f",
            "LONG" if is_long else "SHORT",
            code, total_score, l1_score, l2_score, l3_score, l4_score,
            current_price, sl, tp, atr, float(curr.get("zscore", 0)),
        )

        return signal

    def generate_futures_signal(
        self,
        code: str,
        df: pd.DataFrame,
        current_price: float,
        equity: float = 100000.0,
    ) -> Optional[FuturesSignal]:
        """
        상세 선물 시그널을 생성한다 (FuturesSignal 반환).
        API 엔드포인트나 시뮬레이션에서 직접 호출용.
        """
        if df.empty:
            return None

        min_len = max(self.fc.ma_trend, self.fc.macd_slow + self.fc.macd_signal) + 5
        if len(df) < min_len:
            return None

        df = self.calculate_indicators(df.copy())
        if df.empty:
            return None

        curr = df.iloc[-1]

        direction = self._determine_direction(df)
        if direction == FuturesDirection.NEUTRAL:
            return None

        is_long = direction == FuturesDirection.LONG

        l1_score, l1_signals = self._score_zscore(df, is_long)
        l2_score, l2_signals = self._score_trend(df, is_long)
        l3_score, l3_signals = self._score_momentum(df, is_long)
        l4_score, l4_signals = self._score_volume(df, is_long)

        total_score = l1_score + l2_score + l3_score + l4_score
        if total_score < self.fc.entry_threshold:
            return None

        if not self._check_atr_breakout(df, is_long):
            return None

        if not self._check_fakeout_filter(df, is_long):
            return None

        atr = float(curr["atr"]) if pd.notna(curr["atr"]) else 0
        adx = float(curr.get("adx", 0))
        zscore = float(curr.get("zscore", 0))
        sl, tp = self._calculate_sl_tp(current_price, atr, is_long, adx)

        rr_ratio = abs(tp - current_price) / abs(current_price - sl) if abs(current_price - sl) > 0 else 0
        contracts = self._calculate_position_size(equity, current_price, sl)

        return FuturesSignal(
            ticker=code,
            direction="LONG" if is_long else "SHORT",
            signal_strength=total_score,
            entry_price=current_price,
            stop_loss=sl,
            take_profit=tp,
            atr=atr,
            z_score=zscore,
            primary_signals=l1_signals + l2_signals,
            confirmation_filters=l3_signals + l4_signals,
            risk_reward_ratio=round(rr_ratio, 2),
            position_size_contracts=contracts,
            metadata={
                "l1_zscore": l1_score,
                "l2_trend": l2_score,
                "l3_momentum": l3_score,
                "l4_volume": l4_score,
                "adx": adx,
                "rsi": float(curr.get("rsi", 50)),
                "macd_hist": float(curr.get("macd_hist", 0)),
                "bb_squeeze": float(curr.get("bb_squeeze_ratio", 1)),
            },
        )

    # ══════════════════════════════════════════
    # 3. 방향 결정 로직
    # ══════════════════════════════════════════

    def _determine_direction(self, df: pd.DataFrame) -> FuturesDirection:
        """
        롱/숏/중립 방향을 결정한다.

        판단 기준:
          1. MA200 대비 가격 위치 (장기 추세)
          2. EMA 정렬 방향 (단기-중기-장기)
          3. MACD 히스토그램 방향
          4. Z-Score 극단값
        """
        curr = df.iloc[-1]

        if not all(pd.notna(curr.get(col)) for col in ["ema_fast", "ema_mid", "ema_slow", "ma_trend", "macd_hist", "zscore"]):
            return FuturesDirection.NEUTRAL

        close = float(curr["close"])
        ema_fast = float(curr["ema_fast"])
        ema_mid = float(curr["ema_mid"])
        ema_slow = float(curr["ema_slow"])
        ma_trend = float(curr["ma_trend"])
        macd_hist = float(curr["macd_hist"])
        zscore = float(curr["zscore"])

        long_score = 0
        short_score = 0

        # MA200 위/아래
        if close > ma_trend:
            long_score += 2
        elif close < ma_trend:
            short_score += 2

        # EMA 정렬
        if ema_fast > ema_mid > ema_slow:
            long_score += 2
        elif ema_fast < ema_mid < ema_slow:
            short_score += 2

        # MACD 방향
        if macd_hist > 0:
            long_score += 1
        elif macd_hist < 0:
            short_score += 1

        # Z-Score 극단
        if zscore <= self.fc.zscore_long_threshold:
            long_score += 2  # 과매도 → 롱
        elif zscore >= self.fc.zscore_short_threshold:
            short_score += 2  # 과매수 → 숏

        # 최소 3점 이상 차이로 방향 결정
        if long_score >= 3 and long_score > short_score:
            return FuturesDirection.LONG
        elif short_score >= 3 and short_score > long_score:
            return FuturesDirection.SHORT

        return FuturesDirection.NEUTRAL

    # ══════════════════════════════════════════
    # 4. Layer별 스코어링
    # ══════════════════════════════════════════

    def _score_zscore(self, df: pd.DataFrame, is_long: bool) -> Tuple[float, List[str]]:
        """
        Layer 1: Z-Score 통계적 위치 (max weight_zscore점).
        Z < -2.0: 통계적 과매도 (롱 유리)
        Z > +2.0: 통계적 과매수 (숏 유리)
        """
        max_score = self.fc.weight_zscore
        curr = df.iloc[-1]
        zscore = float(curr.get("zscore", 0))
        signals = []
        score = 0.0

        if is_long:
            # 과매도일수록 롱 점수 증가
            if zscore <= -3.0:
                score = max_score
                signals.append("Z_EXTREME_OVERSOLD")
            elif zscore <= -2.0:
                score = max_score * 0.8
                signals.append("Z_OVERSOLD")
            elif zscore <= -1.5:
                score = max_score * 0.5
                signals.append("Z_MILD_OVERSOLD")
            elif zscore <= -1.0:
                score = max_score * 0.3
                signals.append("Z_BELOW_MEAN")
            # 과매수 영역에서 롱은 감점
            elif zscore >= 2.0:
                score = 0
        else:
            # 과매수일수록 숏 점수 증가
            if zscore >= 3.0:
                score = max_score
                signals.append("Z_EXTREME_OVERBOUGHT")
            elif zscore >= 2.0:
                score = max_score * 0.8
                signals.append("Z_OVERBOUGHT")
            elif zscore >= 1.5:
                score = max_score * 0.5
                signals.append("Z_MILD_OVERBOUGHT")
            elif zscore >= 1.0:
                score = max_score * 0.3
                signals.append("Z_ABOVE_MEAN")
            elif zscore <= -2.0:
                score = 0

        return round(score, 1), signals

    def _score_trend(self, df: pd.DataFrame, is_long: bool) -> Tuple[float, List[str]]:
        """
        Layer 2: 추세/구조 (max weight_trend점).
        EMA 정렬 + MA200 방향 + 가격 위치.
        """
        max_score = self.fc.weight_trend
        curr = df.iloc[-1]
        signals = []
        score = 0.0

        ema_fast = float(curr.get("ema_fast", 0))
        ema_mid = float(curr.get("ema_mid", 0))
        ema_slow = float(curr.get("ema_slow", 0))
        ma_trend = float(curr.get("ma_trend", 0))
        close = float(curr["close"])

        if not all([ema_fast, ema_mid, ema_slow, ma_trend]):
            return 0, []

        if is_long:
            # EMA 정배열: fast > mid > slow
            if ema_fast > ema_mid > ema_slow:
                score += max_score * 0.4
                signals.append("EMA_BULL_ALIGNED")
            elif ema_fast > ema_mid:
                score += max_score * 0.2
                signals.append("EMA_PARTIAL_BULL")

            # MA200 위
            if close > ma_trend:
                score += max_score * 0.3
                signals.append("ABOVE_MA200")

            # MA200 기울기 상승
            if len(df) >= 5:
                ma_trend_prev = df["ma_trend"].iloc[-5]
                if pd.notna(ma_trend_prev) and ma_trend > ma_trend_prev:
                    score += max_score * 0.3
                    signals.append("MA200_RISING")
        else:
            # EMA 역배열: fast < mid < slow
            if ema_fast < ema_mid < ema_slow:
                score += max_score * 0.4
                signals.append("EMA_BEAR_ALIGNED")
            elif ema_fast < ema_mid:
                score += max_score * 0.2
                signals.append("EMA_PARTIAL_BEAR")

            # MA200 아래
            if close < ma_trend:
                score += max_score * 0.3
                signals.append("BELOW_MA200")

            # MA200 기울기 하락
            if len(df) >= 5:
                ma_trend_prev = df["ma_trend"].iloc[-5]
                if pd.notna(ma_trend_prev) and ma_trend < ma_trend_prev:
                    score += max_score * 0.3
                    signals.append("MA200_FALLING")

        return round(min(score, max_score), 1), signals

    def _score_momentum(self, df: pd.DataFrame, is_long: bool) -> Tuple[float, List[str]]:
        """
        Layer 3: 모멘텀 (max weight_momentum점).
        MACD 크로스/히스토그램 + ADX 강도 + RSI 확인.
        """
        max_score = self.fc.weight_momentum
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        signals = []
        score = 0.0

        macd_hist = float(curr.get("macd_hist", 0))
        macd_hist_prev = float(prev.get("macd_hist", 0))
        adx = float(curr.get("adx", 0))
        plus_di = float(curr.get("plus_di", 0))
        minus_di = float(curr.get("minus_di", 0))
        rsi = float(curr.get("rsi", 50))

        if is_long:
            # MACD 히스토그램 양전환
            if macd_hist_prev <= 0 < macd_hist:
                score += max_score * 0.3
                signals.append("MACD_BULL_CROSS")
            elif macd_hist > 0 and macd_hist > macd_hist_prev:
                score += max_score * 0.2
                signals.append("MACD_HIST_RISING")

            # ADX + DI 확인
            if adx > self.fc.adx_threshold and plus_di > minus_di:
                score += max_score * 0.3
                signals.append("ADX_BULL_TREND")
                if adx > self.fc.adx_strong:
                    score += max_score * 0.1
                    signals.append("ADX_STRONG")

            # RSI 적정 범위 (과매도 반등 OR 추세 중 적정)
            if self.fc.rsi_long_range[0] <= rsi <= self.fc.rsi_long_range[1]:
                score += max_score * 0.2
                signals.append("RSI_LONG_OK")
            elif rsi < self.fc.rsi_oversold:
                score += max_score * 0.15
                signals.append("RSI_OVERSOLD_BOUNCE")
        else:
            # MACD 히스토그램 음전환
            if macd_hist_prev >= 0 > macd_hist:
                score += max_score * 0.3
                signals.append("MACD_BEAR_CROSS")
            elif macd_hist < 0 and macd_hist < macd_hist_prev:
                score += max_score * 0.2
                signals.append("MACD_HIST_FALLING")

            # ADX + DI 확인
            if adx > self.fc.adx_threshold and minus_di > plus_di:
                score += max_score * 0.3
                signals.append("ADX_BEAR_TREND")
                if adx > self.fc.adx_strong:
                    score += max_score * 0.1
                    signals.append("ADX_STRONG")

            # RSI 과매수 또는 적정 범위
            if self.fc.rsi_short_range[0] <= rsi <= self.fc.rsi_short_range[1]:
                score += max_score * 0.2
                signals.append("RSI_SHORT_OK")
            elif rsi > self.fc.rsi_overbought:
                score += max_score * 0.15
                signals.append("RSI_OVERBOUGHT_DROP")

        return round(min(score, max_score), 1), signals

    def _score_volume(self, df: pd.DataFrame, is_long: bool) -> Tuple[float, List[str]]:
        """
        Layer 4: 거래량/OBV (max weight_volume점).
        거래량 확인 + OBV 추세 일치.
        """
        max_score = self.fc.weight_volume
        curr = df.iloc[-1]
        signals = []
        score = 0.0

        vol_ratio = float(curr.get("volume_ratio", 1.0))
        obv_fast = float(curr.get("obv_ema_fast", 0))
        obv_slow = float(curr.get("obv_ema_slow", 0))
        bb_squeeze = float(curr.get("bb_squeeze_ratio", 1.0))

        # 거래량 확인 (돌파 시 거래량 증가)
        if vol_ratio >= self.fc.volume_confirm_mult:
            score += max_score * 0.35
            signals.append("VOL_SURGE")
        elif vol_ratio >= 1.2:
            score += max_score * 0.15
            signals.append("VOL_ABOVE_AVG")

        # OBV 추세 확인
        if is_long:
            if obv_fast > obv_slow:
                score += max_score * 0.35
                signals.append("OBV_BULL")
        else:
            if obv_fast < obv_slow:
                score += max_score * 0.35
                signals.append("OBV_BEAR")

        # BB 스퀴즈 (변동성 수축 → 폭발 잠재)
        if bb_squeeze < self.fc.bb_squeeze_ratio:
            score += max_score * 0.3
            signals.append("BB_SQUEEZE")

        return round(min(score, max_score), 1), signals

    # ══════════════════════════════════════════
    # 5. 필터
    # ══════════════════════════════════════════

    def _check_atr_breakout(self, df: pd.DataFrame, is_long: bool) -> bool:
        """
        ATR 돌파 필터.
        유의미한 변동성 움직임이 발생했는지 확인.
        (High - PrevClose) > atr_breakout_mult * ATR (롱)
        (PrevClose - Low) > atr_breakout_mult * ATR (숏)
        """
        curr = df.iloc[-1]
        atr = float(curr.get("atr", 0))
        if atr <= 0:
            return False

        prev_close = float(df.iloc[-2]["close"])

        if is_long:
            move = float(curr["high"]) - prev_close
        else:
            move = prev_close - float(curr["low"])

        return move > self.fc.atr_breakout_mult * atr

    def _check_fakeout_filter(self, df: pd.DataFrame, is_long: bool) -> bool:
        """
        페이크아웃 필터.
        1. 저거래량 돌파 차단
        2. 긴 꼬리(위크) 차단
        """
        curr = df.iloc[-1]

        # 저거래량 체크
        vol_ratio = float(curr.get("volume_ratio", 1.0))
        if vol_ratio < 0.8:
            return False

        # 위크 트랩 체크
        o = float(curr["open"])
        c = float(curr["close"])
        h = float(curr["high"])
        lo = float(curr["low"])
        body = abs(c - o)

        if body < 0.001:  # 도지 캔들은 통과 (별도 판단)
            return True

        if is_long:
            upper_wick = h - max(o, c)
            if upper_wick / body > 1.5:
                return False
        else:
            lower_wick = min(o, c) - lo
            if lower_wick / body > 1.5:
                return False

        return True

    # ══════════════════════════════════════════
    # 6. 손절/익절 계산
    # ══════════════════════════════════════════

    def _calculate_sl_tp(
        self, entry_price: float, atr: float, is_long: bool, adx: float
    ) -> Tuple[float, float]:
        """
        ATR 기반 동적 손절/익절 계산.

        Dynamic ATR 배수: ADX < 20 → 2.0x, ADX ≥ 20 → 1.5x (추세 강할수록 타이트)
        하드 손절: ±3% (절대 한도)
        """
        # 동적 ATR 배수 (추세 강도에 따라 조정)
        if adx >= self.fc.adx_threshold:
            sl_mult = self.fc.sl_atr_mult_strong  # 1.5
        else:
            sl_mult = self.fc.sl_atr_mult  # 2.0

        tp_mult = self.fc.tp_atr_mult  # 3.0

        if atr <= 0:
            atr = entry_price * 0.01  # fallback: 1%

        if is_long:
            sl_atr = entry_price - atr * sl_mult
            sl_hard = entry_price * (1 - self.fc.sl_hard_pct)
            sl = max(sl_atr, sl_hard)  # 더 가까운 것 선택 (보수적)
            tp = entry_price + atr * tp_mult
        else:
            sl_atr = entry_price + atr * sl_mult
            sl_hard = entry_price * (1 + self.fc.sl_hard_pct)
            sl = min(sl_atr, sl_hard)
            tp = entry_price - atr * tp_mult

        return round(sl, 2), round(tp, 2)

    def _calculate_position_size(
        self, equity: float, entry_price: float, stop_loss: float
    ) -> int:
        """
        Kelly Criterion 기반 포지션 사이징.
        contracts = (Equity × Risk%) / (|Entry - SL| × Multiplier)
        """
        risk_amount = equity * self.fc.risk_per_trade_pct
        point_risk = abs(entry_price - stop_loss)

        if point_risk <= 0:
            return 0

        multiplier = 5.0 if self.fc.is_micro else self.fc.contract_multiplier
        dollar_risk_per_contract = point_risk * multiplier

        contracts = int(risk_amount / dollar_risk_per_contract)
        contracts = max(1, min(contracts, self.fc.max_contracts))

        return contracts

    # ══════════════════════════════════════════
    # 7. 청산 시그널 스캔
    # ══════════════════════════════════════════

    def scan_exit_signals(
        self,
        positions: list,
        ohlcv_data: Dict[str, pd.DataFrame],
        current_prices: Dict[str, PriceData],
    ) -> List[ExitSignal]:
        """
        보유 선물 포지션의 청산 시그널을 스캔한다.

        우선순위:
          1. ES1: 하드 손절 (-3%)
          2. ES_ATR_SL: ATR 동적 손절
          3. ES_ATR_TP: ATR 익절
          4. ES_CHANDELIER: 샹들리에 청산
          5. ES3: 프로그레시브 트레일링 스탑
          6. ES_CHOCH: 구조 반전 (MACD 데드/골든크로스)
          7. ES5: 최대 보유기간
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

            # 방향 판단 (포지션 속성 또는 entry 기반)
            is_long = getattr(pos, "direction", "LONG") == "LONG"

            if is_long:
                pnl_pct = (current_price - entry_price) / entry_price
            else:
                pnl_pct = (entry_price - current_price) / entry_price

            # 포지션 상태 업데이트
            state = self._get_position_state(pos.stock_code)
            state.bars_held = getattr(pos, "holding_days", state.bars_held + 1)
            if is_long:
                state.highest_since_entry = max(state.highest_since_entry, current_price)
            else:
                state.lowest_since_entry = min(state.lowest_since_entry, current_price)

            # OHLCV 및 ATR
            df = ohlcv_data.get(pos.stock_code)
            atr = 0.0
            adx = 0.0
            if df is not None and not df.empty:
                # 이미 지표가 계산된 df인 경우 재계산 생략
                if "atr" not in df.columns:
                    df = self.calculate_indicators(df.copy())
                if not df.empty:
                    atr = float(df.iloc[-1].get("atr", 0))
                    adx = float(df.iloc[-1].get("adx", 0))

            # ── ES1: 하드 손절 (-3%) ──
            exit_sig = self._check_hard_stop(pos, current_price, pnl_pct, is_long)
            if exit_sig:
                exit_signals.append(exit_sig)
                continue

            # ── ES_ATR_SL: ATR 동적 손절 ──
            exit_sig = self._check_atr_stop_loss(pos, current_price, entry_price, atr, adx, pnl_pct, is_long)
            if exit_sig:
                exit_signals.append(exit_sig)
                continue

            # ── ES_ATR_TP: ATR 익절 ──
            exit_sig = self._check_atr_take_profit(pos, current_price, entry_price, atr, pnl_pct, is_long)
            if exit_sig:
                exit_signals.append(exit_sig)
                continue

            # ── ES_CHANDELIER: 샹들리에 청산 ──
            exit_sig = self._check_chandelier_exit(pos, current_price, atr, pnl_pct, is_long, state)
            if exit_sig:
                exit_signals.append(exit_sig)
                continue

            # ── ES3: 트레일링 스탑 ──
            exit_sig = self._check_trailing_stop(pos, current_price, entry_price, atr, pnl_pct, is_long, state)
            if exit_sig:
                exit_signals.append(exit_sig)
                continue

            # ── ES_CHOCH: 구조 반전 (MACD 크로스) ──
            if df is not None and not df.empty:
                exit_sig = self._check_structure_reversal(pos, df, pnl_pct, is_long)
                if exit_sig:
                    exit_signals.append(exit_sig)
                    continue

            # ── ES5: 최대 보유기간 ──
            exit_sig = self._check_max_holding(pos, current_price, pnl_pct)
            if exit_sig:
                exit_signals.append(exit_sig)
                continue

        return exit_signals

    # ── 개별 청산 체크 메서드 ──

    def _check_hard_stop(self, pos, current_price: float, pnl_pct: float, is_long: bool) -> Optional[ExitSignal]:
        """ES1: 하드 손절 (절대 한도 -3%)."""
        if pnl_pct <= -self.fc.sl_hard_pct:
            logger.info(
                "EXIT ES1 HARD_STOP | %s | %s | pnl=%.2f%%",
                pos.stock_name, "LONG" if is_long else "SHORT", pnl_pct * 100,
            )
            return ExitSignal(
                stock_code=pos.stock_code,
                stock_name=pos.stock_name,
                position_id=getattr(pos, "position_id", ""),
                exit_type=ExitReason.STOP_LOSS.value,
                exit_reason="HARD_STOP_LOSS",
                order_type="MARKET",
                current_price=current_price,
                pnl_pct=pnl_pct,
            )
        return None

    def _check_atr_stop_loss(
        self, pos, current_price: float, entry_price: float,
        atr: float, adx: float, pnl_pct: float, is_long: bool,
    ) -> Optional[ExitSignal]:
        """ES_ATR_SL: ATR 기반 동적 손절."""
        if atr <= 0:
            return None

        sl, _ = self._calculate_sl_tp(entry_price, atr, is_long, adx)

        triggered = (is_long and current_price <= sl) or (not is_long and current_price >= sl)
        if triggered:
            logger.info(
                "EXIT ES_ATR_SL | %s | %s | price=%.2f | SL=%.2f | pnl=%.2f%%",
                pos.stock_name, "LONG" if is_long else "SHORT",
                current_price, sl, pnl_pct * 100,
            )
            return ExitSignal(
                stock_code=pos.stock_code,
                stock_name=pos.stock_name,
                position_id=getattr(pos, "position_id", ""),
                exit_type=ExitReason.ATR_STOP_LOSS.value,
                exit_reason="ATR_STOP_LOSS",
                order_type="MARKET",
                current_price=current_price,
                pnl_pct=pnl_pct,
                metadata={"atr": atr, "stop_price": sl},
            )
        return None

    def _check_atr_take_profit(
        self, pos, current_price: float, entry_price: float,
        atr: float, pnl_pct: float, is_long: bool,
    ) -> Optional[ExitSignal]:
        """ES_ATR_TP: ATR 기반 익절 (3×ATR)."""
        if atr <= 0:
            return None

        _, tp = self._calculate_sl_tp(entry_price, atr, is_long, 0)

        triggered = (is_long and current_price >= tp) or (not is_long and current_price <= tp)
        if triggered:
            logger.info(
                "EXIT ES_ATR_TP | %s | %s | price=%.2f | TP=%.2f | pnl=+%.2f%%",
                pos.stock_name, "LONG" if is_long else "SHORT",
                current_price, tp, pnl_pct * 100,
            )
            return ExitSignal(
                stock_code=pos.stock_code,
                stock_name=pos.stock_name,
                position_id=getattr(pos, "position_id", ""),
                exit_type=ExitReason.ATR_TAKE_PROFIT.value,
                exit_reason="ATR_TAKE_PROFIT",
                order_type="MARKET",
                current_price=current_price,
                pnl_pct=pnl_pct,
                metadata={"atr": atr, "tp_price": tp},
            )
        return None

    def _check_chandelier_exit(
        self, pos, current_price: float, atr: float,
        pnl_pct: float, is_long: bool, state: FuturesPositionState,
    ) -> Optional[ExitSignal]:
        """
        ES_CHANDELIER: 샹들리에 청산.
        롱: 진입 이후 최고가 - 3×ATR 이탈 시 청산
        숏: 진입 이후 최저가 + 3×ATR 이탈 시 청산
        """
        if atr <= 0:
            return None

        chandelier_mult = self.fc.chandelier_atr_mult

        if is_long:
            chandelier_stop = state.highest_since_entry - chandelier_mult * atr
            triggered = current_price <= chandelier_stop and state.highest_since_entry > pos.entry_price
        else:
            chandelier_stop = state.lowest_since_entry + chandelier_mult * atr
            triggered = current_price >= chandelier_stop and state.lowest_since_entry < pos.entry_price

        if triggered:
            logger.info(
                "EXIT ES_CHANDELIER | %s | %s | price=%.2f | chandelier=%.2f",
                pos.stock_name, "LONG" if is_long else "SHORT",
                current_price, chandelier_stop,
            )
            return ExitSignal(
                stock_code=pos.stock_code,
                stock_name=pos.stock_name,
                position_id=getattr(pos, "position_id", ""),
                exit_type=ExitReason.CHANDELIER_EXIT.value,
                exit_reason="CHANDELIER_EXIT",
                order_type="MARKET",
                current_price=current_price,
                pnl_pct=pnl_pct,
                metadata={"chandelier_stop": chandelier_stop},
            )
        return None

    def _check_trailing_stop(
        self, pos, current_price: float, entry_price: float,
        atr: float, pnl_pct: float, is_long: bool,
        state: FuturesPositionState,
    ) -> Optional[ExitSignal]:
        """
        ES3: 프로그레시브 트레일링 스탑.
        활성화: pnl_pct ≥ trailing_activation_pct (+2%)
        스탑: 최고가/최저가 - trailing_atr_mult × ATR
        """
        if atr <= 0:
            return None

        if pnl_pct < self.fc.trailing_activation_pct:
            return None

        state.trailing_active = True
        trail_mult = self.fc.trailing_atr_mult

        # PnL 구간별 타이트닝
        if pnl_pct >= 0.06:  # +6% 이상
            trail_mult = max(1.0, trail_mult - 0.5)
        elif pnl_pct >= 0.04:  # +4% 이상
            trail_mult = max(1.2, trail_mult - 0.3)

        if is_long:
            trail_stop = state.highest_since_entry - trail_mult * atr
            triggered = current_price <= trail_stop
        else:
            trail_stop = state.lowest_since_entry + trail_mult * atr
            triggered = current_price >= trail_stop

        if triggered:
            logger.info(
                "EXIT ES3 TRAILING | %s | %s | price=%.2f | trail_stop=%.2f | pnl=%.2f%%",
                pos.stock_name, "LONG" if is_long else "SHORT",
                current_price, trail_stop, pnl_pct * 100,
            )
            return ExitSignal(
                stock_code=pos.stock_code,
                stock_name=pos.stock_name,
                position_id=getattr(pos, "position_id", ""),
                exit_type=ExitReason.TRAILING_STOP.value,
                exit_reason="TRAILING_STOP",
                order_type="MARKET",
                current_price=current_price,
                pnl_pct=pnl_pct,
                metadata={"trail_stop": trail_stop, "trail_mult": trail_mult},
            )
        return None

    def _check_structure_reversal(
        self, pos, df: pd.DataFrame, pnl_pct: float, is_long: bool,
    ) -> Optional[ExitSignal]:
        """
        ES_CHOCH: 구조 반전 (MACD 데드/골든 크로스).
        롱 보유 중 MACD 데드크로스 → 청산
        숏 보유 중 MACD 골든크로스 → 청산
        """
        if len(df) < 3:
            return None

        curr = df.iloc[-1]
        prev = df.iloc[-2]

        macd_hist = float(curr.get("macd_hist", 0))
        macd_hist_prev = float(prev.get("macd_hist", 0))

        triggered = False
        if is_long and macd_hist_prev >= 0 and macd_hist < 0:
            triggered = True  # 데드크로스
        elif not is_long and macd_hist_prev <= 0 and macd_hist > 0:
            triggered = True  # 골든크로스

        if triggered:
            current_price = float(curr["close"])
            logger.info(
                "EXIT ES_CHOCH | %s | %s | MACD reversal | pnl=%.2f%%",
                pos.stock_name, "LONG" if is_long else "SHORT", pnl_pct * 100,
            )
            return ExitSignal(
                stock_code=pos.stock_code,
                stock_name=pos.stock_name,
                position_id=getattr(pos, "position_id", ""),
                exit_type=ExitReason.CHOCH_REVERSAL.value,
                exit_reason="MACD_REVERSAL",
                order_type="LIMIT",
                current_price=current_price,
                pnl_pct=pnl_pct,
            )
        return None

    def _check_max_holding(self, pos, current_price: float, pnl_pct: float) -> Optional[ExitSignal]:
        """ES5: 최대 보유기간 초과."""
        holding = getattr(pos, "holding_days", 0) or 0
        if holding > self.fc.max_holding_days:
            logger.info(
                "EXIT ES5 MAX_HOLDING | %s | days=%d | pnl=%.2f%%",
                pos.stock_name, holding, pnl_pct * 100,
            )
            return ExitSignal(
                stock_code=pos.stock_code,
                stock_name=pos.stock_name,
                position_id=getattr(pos, "position_id", ""),
                exit_type=ExitReason.MAX_HOLDING.value,
                exit_reason="MAX_HOLDING",
                order_type="LIMIT",
                current_price=current_price,
                pnl_pct=pnl_pct,
            )
        return None

    # ══════════════════════════════════════════
    # 유틸리티
    # ══════════════════════════════════════════

    def _get_position_state(self, code: str) -> FuturesPositionState:
        if code not in self._position_states:
            self._position_states[code] = FuturesPositionState()
        return self._position_states[code]

    def clear_position_state(self, code: str):
        self._position_states.pop(code, None)
