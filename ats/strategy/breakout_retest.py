"""
Breakout-Retest 전략 구현체.
문서 참조: CLAUDE.md, stock_theory/smcTheory.md

2-Phase 전략:
  Phase A: 돌파 감지 — 4-Layer 스코어링 + 6조건 + 3 페이크아웃 필터
  Phase B: 리테스트 진입 — 돌파 영역(FVG/OB/레벨) 복귀 시 진입

State Machine (티커별):
  IDLE -> WAITING_RETEST -> Entry (or EXPIRED -> IDLE)

Exit 우선순위:
  ES1(-5%) > ES_BRT_SL(ATR×1.5) > ES_BRT_TP(ATR×3.0) > ES_CHOCH >
  ES3(트레일링) > ES_ZONE_BREAK(존 무효화) > ES5(보유기간)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from common.enums import ExitReason
from common.types import ExitSignal, PriceData, Signal
from data.config_manager import ATSConfig, BreakoutRetestConfig
from infra.logger import get_logger
from strategy.base import BaseStrategy

logger = get_logger("breakout_retest")


# ──────────────────────────────────────────────
# Per-Ticker Breakout State
# ──────────────────────────────────────────────

@dataclass
class BreakoutState:
    """티커별 돌파-리테스트 라이프사이클 상태."""
    phase: str = "IDLE"              # IDLE | WAITING_RETEST | EXPIRED
    breakout_bar_idx: int = -1       # 돌파 감지 봉 인덱스
    breakout_price: float = 0.0      # 돌파 시 종가
    breakout_score: int = 0          # 돌파 품질 점수 (0-100)
    breakout_direction: str = "BULL"  # BULL | BEAR (현재 BULL만 사용)
    bars_since_breakout: int = 0     # 돌파 이후 경과 봉 수

    # Retest Zone (돌파 시점에 캡처)
    zone_top: float = 0.0           # 복합 존 상단
    zone_bottom: float = 0.0        # 복합 존 하단
    zone_type: str = ""             # COMPOSITE | FVG | OB | LEVEL

    # 개별 존 정보
    fvg_top: float = 0.0
    fvg_bottom: float = 0.0
    ob_top: float = 0.0
    ob_bottom: float = 0.0
    breakout_level: float = 0.0     # 돌파된 저항선 (swing high)

    # 돌파 시점 ATR
    breakout_atr: float = 0.0

    # 돌파 시 충족된 조건
    conditions_met: List[str] = field(default_factory=list)


class BreakoutRetestStrategy(BaseStrategy):
    """
    Breakout-Retest 전략.

    Phase A: 돌파 감지 (4-Layer 스코어링 + 6조건 + 3필터)
    Phase B: 리테스트 진입 (돌파 영역 복귀 시 진입)
    """

    def __init__(self, config: ATSConfig):
        self.config = config
        self.sc = config.strategy           # 공유 StrategyConfig (MA, MACD 등)
        self.ec = config.exit               # ExitConfig
        self.brc = config.breakout_retest   # BreakoutRetestConfig
        self.smc_cfg = config.smc_strategy  # SMCStrategyConfig (공유 SMC 파라미터)

        # 티커별 돌파 상태 추적
        self._breakout_states: Dict[str, BreakoutState] = {}

    # ══════════════════════════════════════════
    # 기술적 지표 계산
    # ══════════════════════════════════════════

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        SMC 지표 + 기본 기술지표 + OBV 통합 계산.
        SMCStrategy.calculate_indicators()와 동일한 지표 세트를 생성.
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
        bb_std_val = c.rolling(window=self.sc.bb_period).std()
        df["bb_upper"] = bb_ma + (bb_std_val * self.sc.bb_std)
        df["bb_lower"] = bb_ma - (bb_std_val * self.sc.bb_std)
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

        # ── OBV ──
        df["obv"] = (np.sign(c.diff()).fillna(0) * v).cumsum()
        df["obv_ema5"] = df["obv"].ewm(span=5, adjust=False).mean()
        df["obv_ema20"] = df["obv"].ewm(span=20, adjust=False).mean()

        return df

    # ══════════════════════════════════════════
    # SMC 지표 계산 (SMCStrategy에서 가져옴)
    # ══════════════════════════════════════════

    def _calculate_smc(self, df: pd.DataFrame) -> pd.DataFrame:
        """SMC Market Structure 계산 (Swing Points, BOS/CHoCH, OB, FVG)."""
        swing_length = self.brc.swing_length
        highs = df["high"].values
        lows = df["low"].values
        closes = df["close"].values
        opens = df["open"].values
        length = len(df)

        # 1. Swing Points (Pivot)
        df["is_swing_high"] = False
        df["is_swing_low"] = False

        swing_highs = []
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

        trend = 1
        last_sh_idx, last_sh_price = -1, float("inf")
        last_sl_idx, last_sl_price = -1, float("-inf")

        for i in range(length):
            close = closes[i]

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
                    if close > last_sh_price:
                        df.iat[i, df.columns.get_loc("marker")] = "BOS_BULL"
                        for j in range(i - 1, max(0, last_sl_idx - 5), -1):
                            if closes[j] < opens[j]:
                                df.iat[i, df.columns.get_loc("ob_top")] = highs[j]
                                df.iat[i, df.columns.get_loc("ob_bottom")] = lows[j]
                                break
                        last_sh_price = float("inf")
                    elif close < last_sl_price:
                        df.iat[i, df.columns.get_loc("marker")] = "CHOCH_BEAR"
                        trend = -1
                        last_sl_price = float("-inf")
                elif trend == -1:
                    if close < last_sl_price:
                        df.iat[i, df.columns.get_loc("marker")] = "BOS_BEAR"
                        for j in range(i - 1, max(0, last_sh_idx - 5), -1):
                            if closes[j] > opens[j]:
                                df.iat[i, df.columns.get_loc("ob_top")] = highs[j]
                                df.iat[i, df.columns.get_loc("ob_bottom")] = lows[j]
                                break
                        last_sl_price = float("-inf")
                    elif close > last_sh_price:
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

            if c3_low > c1_high:
                df.iat[i - 1, df.columns.get_loc("fvg_type")] = "bull"
                df.iat[i - 1, df.columns.get_loc("fvg_top")] = c3_low
                df.iat[i - 1, df.columns.get_loc("fvg_bottom")] = c1_high
            elif c3_high < c1_low:
                df.iat[i - 1, df.columns.get_loc("fvg_type")] = "bear"
                df.iat[i - 1, df.columns.get_loc("fvg_top")] = c1_low
                df.iat[i - 1, df.columns.get_loc("fvg_bottom")] = c3_high

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
    # Phase A: 돌파 감지
    # ══════════════════════════════════════════

    def _score_structure(self, df: pd.DataFrame) -> int:
        """Layer 1: SMC 구조 스코어 (0-30). BOS + 유동성 스윕."""
        if len(df) < 10:
            return 0

        score = 0
        lookback = min(20, len(df))
        recent = df.iloc[-lookback:]

        # BOS/CHoCH 마커
        markers = recent[recent["marker"].notna()]
        if not markers.empty:
            last_marker = markers.iloc[-1]["marker"]
            if last_marker == "BOS_BULL":
                score += 20
            elif last_marker == "CHOCH_BULL":
                score += 15

        # 유동성 스윕: 돌파 전 반대쪽 극값 터치
        swing_lows = recent[recent["is_swing_low"] == True]
        if not swing_lows.empty and len(df) >= 7:
            last_sl = float(swing_lows.iloc[-1]["low"])
            recent_7 = df.iloc[-7:]
            swept = (recent_7["low"] < last_sl).any()
            if swept:
                score += 10

        return min(score, self.brc.weight_structure)

    def _score_volatility_squeeze(self, df: pd.DataFrame) -> int:
        """Layer 2: BB/ATR 변동성 스코어 (0-20). BB squeeze 감지."""
        if len(df) < max(self.brc.bb_squeeze_lookback, 50):
            return 0

        score = 0
        bb_width = df["bb_width"].dropna()
        if len(bb_width) < self.brc.bb_squeeze_lookback:
            return 0

        current_width = float(bb_width.iloc[-1])
        min_width = float(bb_width.iloc[-self.brc.bb_squeeze_lookback:].min())
        bb_ema = float(bb_width.ewm(span=self.brc.bb_squeeze_ema).mean().iloc[-1])

        # BB Width가 100봉 최저 근처
        if min_width > 0 and current_width <= min_width * 1.1:
            score += 15
        elif bb_ema > 0 and current_width < bb_ema:
            score += 8

        # ATR 압축 확인
        atr_pct = df["atr_pct"].dropna()
        if len(atr_pct) >= 50:
            atr_avg = float(atr_pct.rolling(50).mean().iloc[-1])
            curr_atr = float(atr_pct.iloc[-1])
            if atr_avg > 0 and curr_atr < atr_avg * 0.8:
                score += 5

        return min(score, self.brc.weight_volatility)

    def _score_obv_break(self, df: pd.DataFrame) -> int:
        """Layer 3: OBV 돌파 스코어 (0-25). OBV가 이전 N봉 최고 돌파."""
        obv = df["obv"].dropna()
        if len(obv) < self.brc.obv_break_lookback + 1:
            return 0

        score = 0
        curr_obv = float(obv.iloc[-1])
        prev_obv_high = float(obv.iloc[-self.brc.obv_break_lookback - 1:-1].max())

        if curr_obv > prev_obv_high:
            score += 15

            obv_ema5 = float(df["obv_ema5"].iloc[-1]) if "obv_ema5" in df.columns and pd.notna(df["obv_ema5"].iloc[-1]) else 0
            obv_ema20 = float(df["obv_ema20"].iloc[-1]) if "obv_ema20" in df.columns and pd.notna(df["obv_ema20"].iloc[-1]) else 0
            if obv_ema5 > obv_ema20:
                score += 10

        return min(score, self.brc.weight_volume)

    def _score_momentum_breakout(self, df: pd.DataFrame) -> int:
        """Layer 4: ADX/MACD 모멘텀 스코어 (0-25)."""
        if len(df) < self.brc.adx_rising_bars + 2:
            return 0

        score = 0
        curr = df.iloc[-1]
        prev = df.iloc[-2]

        # ADX > threshold + rising
        adx_series = df["adx"].dropna()
        if len(adx_series) >= self.brc.adx_rising_bars + 1:
            curr_adx = float(adx_series.iloc[-1])
            plus_di = float(curr.get("plus_di", 0)) if pd.notna(curr.get("plus_di")) else 0
            minus_di = float(curr.get("minus_di", 0)) if pd.notna(curr.get("minus_di")) else 0

            if curr_adx > self.brc.adx_threshold and plus_di > minus_di:
                score += 8
                # ADX 연속 상승 확인
                rising = True
                for i in range(1, self.brc.adx_rising_bars + 1):
                    if float(adx_series.iloc[-i]) <= float(adx_series.iloc[-i - 1]):
                        rising = False
                        break
                if rising:
                    score += 7

        # MACD 골든크로스
        macd_hist = float(curr.get("macd_hist", 0)) if pd.notna(curr.get("macd_hist")) else 0
        prev_macd = float(prev.get("macd_hist", 0)) if pd.notna(prev.get("macd_hist")) else 0

        if prev_macd <= 0 and macd_hist > 0:
            score += 10
        elif macd_hist > 0 and macd_hist > prev_macd:
            score += 5

        return min(score, self.brc.weight_momentum)

    def _check_six_conditions(self, df: pd.DataFrame) -> tuple:
        """6조건 검증. (충족 여부, 충족된 조건 목록) 반환. 최소 4개 필요."""
        met = []
        curr = df.iloc[-1]

        # C1: Volatility Squeeze
        bb_width = df["bb_width"].dropna()
        if len(bb_width) >= self.brc.bb_squeeze_lookback:
            curr_w = float(bb_width.iloc[-1])
            min_w = float(bb_width.iloc[-self.brc.bb_squeeze_lookback:].min())
            if min_w > 0 and curr_w <= min_w * 1.2:
                met.append("C1_SQUEEZE")

        # C2: Liquidity Sweep
        swing_lows = df[df["is_swing_low"] == True]
        if not swing_lows.empty and len(df) >= 7:
            last_sl = float(swing_lows.iloc[-1]["low"])
            recent = df.iloc[-7:]
            if (recent["low"] < last_sl).any():
                met.append("C2_LIQ_SWEEP")

        # C3: Displacement (body > 1.5 * ATR)
        body = abs(float(curr["close"]) - float(curr["open"]))
        atr = float(curr.get("atr", 0)) if pd.notna(curr.get("atr")) else 0
        if atr > 0 and body > atr * self.brc.displacement_atr_mult:
            met.append("C3_DISPLACEMENT")

        # C4: OBV Break
        obv = df["obv"].dropna()
        if len(obv) > self.brc.obv_break_lookback:
            curr_obv = float(obv.iloc[-1])
            prev_high = float(obv.iloc[-self.brc.obv_break_lookback - 1:-1].max())
            if curr_obv > prev_high:
                met.append("C4_OBV_BREAK")

        # C5: ADX > threshold & rising
        adx_s = df["adx"].dropna()
        if len(adx_s) >= self.brc.adx_rising_bars + 1:
            if float(adx_s.iloc[-1]) > self.brc.adx_threshold:
                rising = all(
                    float(adx_s.iloc[-i]) > float(adx_s.iloc[-i - 1])
                    for i in range(1, self.brc.adx_rising_bars + 1)
                )
                if rising:
                    met.append("C5_ADX_RISING")

        # C6: FVG Formation (최근 3봉 내)
        fvg_recent = df.iloc[-3:]
        fvg_found = fvg_recent[fvg_recent["fvg_type"] == "bull"]
        if not fvg_found.empty:
            met.append("C6_FVG")

        return len(met) >= 4, met

    def _apply_fakeout_filters(self, df: pd.DataFrame) -> tuple:
        """3개 페이크아웃 필터. (통과 여부, 차단 사유) 반환."""
        curr = df.iloc[-1]

        # Error 01: 저거래량 돌파
        volume = float(curr.get("volume", 0))
        vol_ma = float(curr.get("volume_ma", 1)) if pd.notna(curr.get("volume_ma")) else 1
        if vol_ma > 0 and volume < vol_ma * self.brc.min_volume_ratio:
            return False, "ERR01_LOW_VOLUME"

        # Error 02: 긴 윗꼬리 (유동성 헌트)
        close = float(curr["close"])
        open_p = float(curr["open"])
        high = float(curr["high"])
        body = abs(close - open_p)
        upper_wick = high - max(close, open_p)
        if body > 0 and upper_wick / body > self.brc.max_wick_body_ratio:
            return False, "ERR02_WICK_TRAP"

        # Error 03: MACD/RSI 다이버전스
        if self.brc.divergence_check and len(df) >= 10:
            price_curr = float(df["close"].iloc[-1])
            price_prev_max = float(df["close"].iloc[-10:-1].max())
            macd_curr = float(curr.get("macd_hist", 0)) if pd.notna(curr.get("macd_hist")) else 0
            macd_prev_max = float(df["macd_hist"].iloc[-10:-1].max()) if "macd_hist" in df.columns else 0
            rsi_curr = float(curr.get("rsi", 50)) if pd.notna(curr.get("rsi")) else 50
            rsi_prev_max = float(df["rsi"].iloc[-10:-1].max()) if "rsi" in df.columns else 50

            # 가격 신고가 but MACD/RSI 저고가 → 다이버전스
            if price_curr > price_prev_max and (macd_curr < macd_prev_max * 0.8 or rsi_curr < rsi_prev_max * 0.9):
                return False, "ERR03_DIVERGENCE"

        return True, None

    def _capture_retest_zones(self, df: pd.DataFrame, breakout_price: float, breakout_atr: float) -> BreakoutState:
        """돌파 시점에 FVG/OB/레벨 존을 캡처."""
        state = BreakoutState()
        state.phase = "WAITING_RETEST"
        state.breakout_price = breakout_price
        state.breakout_bar_idx = len(df) - 1
        state.breakout_atr = breakout_atr

        recent = df.iloc[-20:]

        # FVG 존 캡처
        if self.brc.use_fvg_zone:
            fvg_rows = recent[(recent["fvg_type"] == "bull") & recent["fvg_top"].notna()]
            if not fvg_rows.empty:
                last_fvg = fvg_rows.iloc[-1]
                state.fvg_top = float(last_fvg["fvg_top"])
                state.fvg_bottom = float(last_fvg["fvg_bottom"])

        # OB 존 캡처
        if self.brc.use_ob_zone:
            ob_rows = recent[recent["ob_top"].notna()]
            if not ob_rows.empty:
                last_ob = ob_rows.iloc[-1]
                state.ob_top = float(last_ob["ob_top"])
                state.ob_bottom = float(last_ob["ob_bottom"])

        # 돌파 레벨 (마지막 swing high)
        if self.brc.use_breakout_level:
            swing_highs = recent[recent["is_swing_high"] == True]
            if not swing_highs.empty:
                state.breakout_level = float(swing_highs.iloc[-1]["high"])

        # 복합 존 계산
        zone_candidates = []
        if state.fvg_bottom > 0:
            zone_candidates.append((state.fvg_bottom, state.fvg_top))
        if state.ob_bottom > 0:
            zone_candidates.append((state.ob_bottom, state.ob_top))
        if state.breakout_level > 0:
            buffer = breakout_atr * self.brc.retest_zone_atr_buffer
            zone_candidates.append((state.breakout_level - buffer, state.breakout_level))

        if zone_candidates:
            state.zone_bottom = min(z[0] for z in zone_candidates)
            state.zone_top = max(z[1] for z in zone_candidates)
            state.zone_type = "COMPOSITE"
        else:
            # Fallback: 돌파 가격 기준 ATR 버퍼
            buffer = breakout_atr * self.brc.retest_zone_atr_buffer
            state.zone_bottom = breakout_price - breakout_atr - buffer
            state.zone_top = breakout_price
            state.zone_type = "LEVEL"

        return state

    def _detect_breakout(self, code: str, df: pd.DataFrame) -> Optional[BreakoutState]:
        """Phase A: 풀 돌파 감지 파이프라인. 돌파 확인 시 BreakoutState 반환."""
        if len(df) < max(self.brc.bb_squeeze_lookback, 50):
            return None

        # Step 1: 4-Layer 스코어링
        score_struct = self._score_structure(df)
        score_vol = self._score_volatility_squeeze(df)
        score_obv = self._score_obv_break(df)
        score_mom = self._score_momentum_breakout(df)
        total_score = score_struct + score_vol + score_obv + score_mom

        if total_score < self.brc.breakout_threshold:
            return None

        # Step 2: 6조건 중 4개 이상 충족
        conditions_met, met_list = self._check_six_conditions(df)
        if not conditions_met:
            return None

        # Step 3: 3개 페이크아웃 필터 통과
        filter_passed, block_reason = self._apply_fakeout_filters(df)
        if not filter_passed:
            logger.debug("Breakout BLOCKED | %s | %s", code, block_reason)
            return None

        # Step 4: 리테스트 존 캡처
        curr = df.iloc[-1]
        breakout_price = float(curr["close"])
        breakout_atr = float(curr.get("atr", breakout_price * 0.03)) if pd.notna(curr.get("atr")) else breakout_price * 0.03

        state = self._capture_retest_zones(df, breakout_price, breakout_atr)
        state.breakout_score = total_score
        state.conditions_met = met_list

        logger.info(
            "BREAKOUT DETECTED | %s | score=%d [S:%d V:%d O:%d M:%d] | conditions=%s | zone=[%.2f-%.2f]",
            code, total_score, score_struct, score_vol, score_obv, score_mom,
            ",".join(met_list), state.zone_bottom, state.zone_top,
        )

        return state

    # ══════════════════════════════════════════
    # Phase B: 리테스트 진입
    # ══════════════════════════════════════════

    def _score_retest_zone(self, df: pd.DataFrame, state: BreakoutState) -> int:
        """리테스트 존 근접도 스코어링 (0-100)."""
        price = float(df.iloc[-1]["close"])
        score = 0

        # FVG 근접도
        if state.fvg_bottom > 0 and self.brc.use_fvg_zone:
            if state.fvg_bottom <= price <= state.fvg_top:
                score += self.brc.fvg_zone_weight
            elif price < state.fvg_top and price > state.fvg_bottom - state.breakout_atr * 0.3:
                score += self.brc.fvg_zone_weight // 2

        # OB 근접도
        if state.ob_bottom > 0 and self.brc.use_ob_zone:
            if state.ob_bottom <= price <= state.ob_top:
                score += self.brc.ob_zone_weight
            elif price < state.ob_top and price > state.ob_bottom - state.breakout_atr * 0.3:
                score += self.brc.ob_zone_weight // 2

        # 돌파 레벨 근접도
        if state.breakout_level > 0 and self.brc.use_breakout_level:
            buffer = state.breakout_atr * self.brc.retest_zone_atr_buffer
            if state.breakout_level - buffer <= price <= state.breakout_level + buffer:
                score += self.brc.level_zone_weight

        return min(score, 100)

    def _check_retest(self, code: str, df: pd.DataFrame, state: BreakoutState) -> Optional[Signal]:
        """Phase B: 리테스트 확인. 유효 시 Signal 반환."""
        curr = df.iloc[-1]
        price = float(curr["close"])
        low = float(curr["low"])

        state.bars_since_breakout += 1

        # 만료 체크
        if state.bars_since_breakout > self.brc.retest_max_bars:
            state.phase = "IDLE"
            logger.debug("Retest EXPIRED | %s | bars=%d", code, state.bars_since_breakout)
            return None

        # 존 하단 이탈 체크 (close가 존 아래면 실패 — 존 무효화)
        if price < state.zone_bottom:
            state.phase = "IDLE"
            logger.debug("Retest FAILED (below zone) | %s | price=%.2f < zone_bottom=%.2f",
                         code, price, state.zone_bottom)
            return None

        # 가격이 존에 도달했는지 확인 (low가 존 상단 이하 + close가 존 하단 이상)
        in_zone = low <= state.zone_top and price >= state.zone_bottom
        if not in_zone:
            return None

        # ── 확인 조건 (3개 중 2개 이상) ──
        confirmations = 0
        confirm_list = []

        # 1. 거래량 감소 (건강한 조정)
        volume = float(curr.get("volume", 0))
        vol_ma = float(curr.get("volume_ma", 1)) if pd.notna(curr.get("volume_ma")) else 1
        if vol_ma > 0 and volume < vol_ma * self.brc.retest_volume_decay:
            confirmations += 1
            confirm_list.append("VOL_DECAY")

        # 2. 반등 캔들 (하단꼬리 or 양봉)
        open_p = float(curr["open"])
        body = abs(price - open_p)
        lower_wick = min(price, open_p) - low
        bullish_rejection = body > 0 and lower_wick > body * self.brc.retest_rejection_wick_ratio
        bullish_close = price > open_p
        if bullish_rejection or bullish_close:
            confirmations += 1
            confirm_list.append("REJECTION" if bullish_rejection else "BULL_CLOSE")

        # 3. RSI 지지
        rsi = float(curr.get("rsi", 50)) if pd.notna(curr.get("rsi")) else 50
        if rsi >= self.brc.retest_rsi_floor:
            confirmations += 1
            confirm_list.append(f"RSI_{int(rsi)}")

        # 존 스코어 + 확인 조건 판정
        zone_score = self._score_retest_zone(df, state)

        if zone_score >= self.brc.retest_zone_threshold and confirmations >= 2:
            strength = min(state.breakout_score + zone_score // 2, 100)

            price_data_name = code  # 실제 사용 시 stock_name으로 대체
            signal = Signal(
                stock_code=code,
                stock_name=price_data_name,
                signal_type="BUY",
                primary_signals=[
                    f"BKO_{state.breakout_score}",
                    f"RETEST_{zone_score}",
                    f"ZONE_{state.zone_type}",
                ],
                confirmation_filters=[c for c in confirm_list if c],
                current_price=price,
                bb_upper=float(curr.get("bb_upper", float("inf"))) if pd.notna(curr.get("bb_upper")) else float("inf"),
            )
            signal.strength = strength

            # 상태 초기화
            state.phase = "IDLE"

            logger.info(
                "RETEST ENTRY | %s | strength=%d | zone_score=%d | confirms=%s | price=%.2f",
                code, strength, zone_score, ",".join(confirm_list), price,
            )
            return signal

        return None

    # ══════════════════════════════════════════
    # BaseStrategy 인터페이스 구현
    # ══════════════════════════════════════════

    def scan_entry_signals(
        self,
        universe_codes: List[str],
        ohlcv_data: Dict[str, pd.DataFrame],
        current_prices: Dict[str, PriceData],
    ) -> List[Signal]:
        """
        2-pass 스캔:
        Pass 1: IDLE 티커에 대해 Phase A 돌파 감지
        Pass 2: WAITING_RETEST 티커에 대해 Phase B 리테스트 확인
        """
        signals = []

        for code in universe_codes:
            df = ohlcv_data.get(code)
            if df is None or df.empty or len(df) < 50:
                continue

            df = self.calculate_indicators(df.copy())
            if df.empty or len(df) < 2:
                continue

            # 상태 가져오기 또는 생성
            if code not in self._breakout_states:
                self._breakout_states[code] = BreakoutState()
            state = self._breakout_states[code]

            if state.phase == "IDLE":
                # Pass 1: 돌파 감지
                new_state = self._detect_breakout(code, df)
                if new_state:
                    self._breakout_states[code] = new_state

            elif state.phase == "WAITING_RETEST":
                # Pass 2: 리테스트 확인
                signal = self._check_retest(code, df, state)
                if signal:
                    # stock_name 업데이트
                    price_data = current_prices.get(code)
                    if price_data:
                        signal.stock_name = price_data.stock_name
                        signal.current_price = price_data.current_price
                    signals.append(signal)

        # 만료된 상태 정리
        self._expire_stale_breakouts()

        # 강도 내림차순 정렬
        signals.sort(key=lambda s: s.strength, reverse=True)
        return signals

    def _expire_stale_breakouts(self):
        """만료된 돌파 상태 정리."""
        for code, state in self._breakout_states.items():
            if state.phase == "WAITING_RETEST" and state.bars_since_breakout > self.brc.retest_max_bars:
                state.phase = "IDLE"

    # ══════════════════════════════════════════
    # 청산 시그널 스캔
    # ══════════════════════════════════════════

    def scan_exit_signals(
        self,
        positions: list,
        ohlcv_data: Dict[str, pd.DataFrame],
        current_prices: Dict[str, PriceData],
    ) -> List[ExitSignal]:
        """
        Breakout-Retest 전용 청산 로직.
        우선순위: ES1 > ES_BRT_SL > ES_BRT_TP > ES_CHOCH > ES3 > ES_ZONE_BREAK > ES5
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

            # ── ES1: 하드 손절 -5% (BR-S01 불변) ──
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

            # ATR 기반 SL/TP
            df = ohlcv_data.get(pos.stock_code)
            atr_val = None
            if df is not None and len(df) > 14:
                df_calc = self.calculate_indicators(df.copy())
                last_atr = df_calc.iloc[-1].get("atr")
                if pd.notna(last_atr):
                    atr_val = float(last_atr)

            if atr_val is not None and atr_val > 0:
                # ── ES_BRT_SL: ATR × 1.5 손절 (타이트) ──
                atr_sl_price = entry_price - atr_val * self.brc.atr_sl_mult
                floor_sl_price = entry_price * (1 + self.ec.stop_loss_pct)
                effective_sl = max(atr_sl_price, floor_sl_price)

                if current_price <= effective_sl and effective_sl > floor_sl_price:
                    exit_signals.append(ExitSignal(
                        stock_code=pos.stock_code,
                        stock_name=pos.stock_name,
                        position_id=pos.position_id,
                        exit_type="ES_BRT_SL",
                        exit_reason="ATR_STOP_LOSS",
                        order_type="MARKET",
                        current_price=current_price,
                        pnl_pct=pnl_pct,
                    ))
                    logger.info("EXIT ES_BRT_SL | %s | SL=%.2f | pnl=%.2f%%",
                                pos.stock_name, effective_sl, pnl_pct * 100)
                    continue

                # ── ES_BRT_TP: ATR × 3.0 익절 ──
                atr_tp_price = entry_price + atr_val * self.brc.atr_tp_mult
                if current_price >= atr_tp_price:
                    exit_signals.append(ExitSignal(
                        stock_code=pos.stock_code,
                        stock_name=pos.stock_name,
                        position_id=pos.position_id,
                        exit_type="ES_BRT_TP",
                        exit_reason="ATR_TAKE_PROFIT",
                        order_type="MARKET",
                        current_price=current_price,
                        pnl_pct=pnl_pct,
                    ))
                    logger.info("EXIT ES_BRT_TP | %s | TP=%.2f | pnl=+%.2f%%",
                                pos.stock_name, atr_tp_price, pnl_pct * 100)
                    continue

            # ── ES_CHOCH: CHoCH Bear 청산 ──
            if self.brc.choch_exit and df is not None and len(df) > 10:
                df_calc = self.calculate_indicators(df.copy())
                recent_markers = df_calc.iloc[-5:]
                choch_found = False
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
                        logger.info("EXIT ES_CHOCH | %s | pnl=%.2f%%", pos.stock_name, pnl_pct * 100)
                        choch_found = True
                        break
                if choch_found:
                    continue

            # ── ES3: 트레일링 스탑 ──
            trailing_high = pos.trailing_high or entry_price
            if current_price > trailing_high:
                trailing_high = current_price

            # 활성화 조건: pnl >= trailing_activation_pct
            if pnl_pct >= self.brc.trailing_activation_pct:
                if atr_val and atr_val > 0:
                    trailing_stop_price = trailing_high - atr_val * self.brc.trailing_atr_mult
                else:
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
                    logger.info("EXIT ES3 TRAILING | %s | pnl=%.2f%%", pos.stock_name, pnl_pct * 100)
                    continue

            # ── ES5: 최대 보유기간 ──
            if pos.holding_days and pos.holding_days > self.brc.max_holding_days:
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
                logger.info("EXIT ES5 MAX_HOLD | %s | days=%d | pnl=%.2f%%",
                            pos.stock_name, pos.holding_days, pnl_pct * 100)
                continue

        return exit_signals
