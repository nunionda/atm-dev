"""
ES-F 인트라데이 데이트레이딩 전략 (E-mini / Micro E-mini S&P500 선물)

AMT 3-Stage Filter + Z-Score 통계 기반 하이브리드 전략.
15분봉 실행, 1시간봉 바이어스, Volume Profile 기반 위치 분석.

진입 시그널 — 4-Layer 스코어링 (100점):
  Layer 1 — AMT Location (30점): 마켓 상태 정렬 + VP 기반 위치 품질
  Layer 2 — Z-Score 통계 (20점): 평균 회귀 / 추세 추종 구간
  Layer 3 — 모멘텀 (25점): MACD 크로스, ADX/DMI, RSI, 연속 방향 봉
  Layer 4 — 거래량 + 공격성 (25점): 볼륨 서지, OBV, Aggression 감지

Grade 시스템:
  A (≥55): 100% 계약 — 풀 리스크
  B (≥45): 50% 계약 — 하프 리스크
  C (≥35): 25% 계약 — 쿼터 리스크

청산 우선순위:
  ES_HARD: 하드 손절 (-1.5%)
  ES_ATR_SL: ATR × 1.5 손절
  ES_ATR_TP: ATR × 2.5 익절
  ES3: 트레일링 (+0.8% 활성화, ATR × 1.0)
  ES_EOD: EOD 강제 청산 (RTH 종료 15분 전)
  ES_SESSION: 세션 정지 (3연속 손절 or 일일 손실 한도)
  ES_VP_BREAK: VP 존 이탈

참조:
  - stock_theory/scalpingPlaybook.md (AMT 3-Stage, Triple-A Model)
  - stock_theory/futuresStrategy.md (Z-Score, EV Engine)
  - CLAUDE.md §Scalping Playbook, §Futures Trading Strategy
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from common.enums import ExitReason, FuturesDirection
from common.types import ExitSignal, FuturesSignal
from data.config_manager import ATSConfig, ESFIntradayConfig
from infra.logger import get_logger

logger = get_logger("esf_intraday")


# ══════════════════════════════════════════
# 내부 상태 관리
# ══════════════════════════════════════════

@dataclass
class IntradayPositionState:
    """인트라데이 포지션 상태 추적."""
    direction: str = "NEUTRAL"          # LONG / SHORT / NEUTRAL
    entry_price: float = 0.0
    highest_since_entry: float = 0.0    # 진입 이후 최고가 (롱)
    lowest_since_entry: float = float("inf")  # 진입 이후 최저가 (숏)
    trailing_active: bool = False
    bars_held: int = 0

    def reset_for_entry(self, direction: str, entry_price: float):
        """신규 진입 시 상태 초기화."""
        self.direction = direction
        self.entry_price = entry_price
        self.bars_held = 0
        self.trailing_active = False
        if direction == "LONG":
            self.highest_since_entry = entry_price
            self.lowest_since_entry = float("inf")
        else:
            self.lowest_since_entry = entry_price
            self.highest_since_entry = 0.0


@dataclass
class SessionState:
    """세션(장중) 상태 관리."""
    trade_count: int = 0
    total_pnl_dollars: float = 0.0
    consecutive_losses: int = 0
    should_stop: bool = False
    stop_reason: str = ""

    def record_trade(self, pnl_dollars: float, max_daily_trades: int,
                     max_daily_loss: float, max_consec: int):
        """트레이드 결과 기록 및 세션 정지 판단."""
        self.trade_count += 1
        self.total_pnl_dollars += pnl_dollars

        if pnl_dollars < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0

        # 세션 정지 조건 체크
        if self.consecutive_losses >= max_consec:
            self.should_stop = True
            self.stop_reason = f"CONSEC_LOSS_{self.consecutive_losses}"
        if self.total_pnl_dollars <= -max_daily_loss:
            self.should_stop = True
            self.stop_reason = f"DAILY_LOSS_{self.total_pnl_dollars:.0f}"
        if self.trade_count >= max_daily_trades:
            self.should_stop = True
            self.stop_reason = f"MAX_TRADES_{self.trade_count}"

    def reset(self):
        """새 세션 시작 시 초기화."""
        self.trade_count = 0
        self.total_pnl_dollars = 0.0
        self.consecutive_losses = 0
        self.should_stop = False
        self.stop_reason = ""


# ══════════════════════════════════════════
# Volume Profile 데이터
# ══════════════════════════════════════════

@dataclass
class VolumeProfileData:
    """Volume Profile 결과."""
    poc: float = 0.0                    # Point of Control (최대 거래량 가격)
    vah: float = 0.0                    # Value Area High
    val: float = 0.0                    # Value Area Low
    nodes: List[Dict] = field(default_factory=list)  # [{price, volume}, ...]
    lvn_levels: List[float] = field(default_factory=list)  # Low Volume Nodes


class ESFIntradayStrategy:
    """
    ES-F 인트라데이 데이트레이딩 전략.

    핵심 원리: AMT 3-Stage Filter + Z-Score 통계적 우위 탐색
    - Volume Profile 기반 마켓 상태/위치 분석 (AMT)
    - Z-Score로 통계적 과매수/과매도 구간 포착
    - 공격성(Aggression) 감지로 진입 타이밍 확인
    - Grade 시스템으로 리스크 계층화 (A/B/C)
    """

    def __init__(self, config: ATSConfig):
        self.config = config
        self.fc: ESFIntradayConfig = config.esf_intraday
        self._position_states: Dict[str, IntradayPositionState] = {}
        self._session = SessionState()
        # EV Engine: 최근 N건 PnL% 기록
        self._trade_history: List[float] = []

    # ══════════════════════════════════════════
    # 1. 기술적 지표 계산
    # ══════════════════════════════════════════

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        OHLCV DataFrame에 인트라데이 매매용 기술적 지표를 추가한다.

        추가 컬럼:
          이동평균: ema_fast(8), ema_mid(21), ema_slow(55)
          MACD: macd_line, macd_signal, macd_hist
          RSI: rsi
          볼린저밴드: bb_upper, bb_lower, bb_middle, bb_width, bb_squeeze_ratio
          ATR: atr, atr_pct
          ADX/DMI: adx, plus_di, minus_di
          Z-Score: zscore (40-window)
          거래량: volume_ma, volume_ratio
          OBV: obv, obv_ema_fast, obv_ema_slow
        """
        min_len = max(self.fc.ema_slow, self.fc.macd_slow + self.fc.macd_signal, self.fc.zscore_window)
        if df.empty or len(df) < min_len:
            return df

        c = df["close"].astype(float)
        h = df["high"].astype(float)
        lo = df["low"].astype(float)
        v = df["volume"].astype(float)

        # ── EMA (8, 21, 55) ──
        df["ema_fast"] = c.ewm(span=self.fc.ema_fast, adjust=False).mean()
        df["ema_mid"] = c.ewm(span=self.fc.ema_mid, adjust=False).mean()
        df["ema_slow"] = c.ewm(span=self.fc.ema_slow, adjust=False).mean()

        # ── MACD (12, 26, 9) ──
        ema_fast_macd = c.ewm(span=self.fc.macd_fast, adjust=False).mean()
        ema_slow_macd = c.ewm(span=self.fc.macd_slow, adjust=False).mean()
        df["macd_line"] = ema_fast_macd - ema_slow_macd
        df["macd_signal"] = df["macd_line"].ewm(span=self.fc.macd_signal, adjust=False).mean()
        df["macd_hist"] = df["macd_line"] - df["macd_signal"]

        # ── RSI (14) ──
        delta = c.diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)
        avg_gain = gain.ewm(span=self.fc.rsi_period, adjust=False).mean()
        avg_loss = loss.ewm(span=self.fc.rsi_period, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        df["rsi"] = 100 - (100 / (1 + rs))

        # ── 볼린저밴드 (20, 2σ) ──
        bb_ma = c.rolling(window=self.fc.bb_period).mean()
        bb_std_val = c.rolling(window=self.fc.bb_period).std()
        df["bb_upper"] = bb_ma + (bb_std_val * self.fc.bb_std)
        df["bb_lower"] = bb_ma - (bb_std_val * self.fc.bb_std)
        df["bb_middle"] = bb_ma
        bb_width = df["bb_upper"] - df["bb_lower"]
        df["bb_width"] = bb_width
        bb_width_ma = bb_width.rolling(window=self.fc.bb_period).mean()
        df["bb_squeeze_ratio"] = (bb_width / bb_width_ma.replace(0, np.nan)).fillna(1.0)

        # ── ATR (20) ──
        tr1 = h - lo
        tr2 = (h - c.shift(1)).abs()
        tr3 = (lo - c.shift(1)).abs()
        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        df["atr"] = true_range.rolling(window=self.fc.atr_period).mean()
        df["atr_pct"] = (df["atr"] / c * 100).fillna(0)

        # ── ADX / DMI (14) ──
        df["adx"], df["plus_di"], df["minus_di"] = self._calc_adx_dmi(
            h, lo, c, self.fc.adx_period
        )

        # ── Z-Score (40-window) ──
        ma_z = c.rolling(window=self.fc.zscore_window).mean()
        std_z = c.rolling(window=self.fc.zscore_window).std()
        df["zscore"] = ((c - ma_z) / std_z.replace(0, np.nan)).fillna(0)

        # ── 거래량 ──
        df["volume_ma"] = v.rolling(window=self.fc.volume_ma_period).mean()
        df["volume_ratio"] = (v / df["volume_ma"].replace(0, np.nan)).fillna(1.0)

        # ── OBV ──
        obv = np.where(c > c.shift(1), v, np.where(c < c.shift(1), -v, 0))
        df["obv"] = pd.Series(obv, index=df.index).cumsum()
        df["obv_ema_fast"] = df["obv"].ewm(span=5, adjust=False).mean()
        df["obv_ema_slow"] = df["obv"].ewm(span=20, adjust=False).mean()

        return df

    @staticmethod
    def _calc_adx_dmi(
        high: pd.Series, low: pd.Series, close: pd.Series, period: int,
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
    # 2. Volume Profile
    # ══════════════════════════════════════════

    def build_volume_profile(self, df: pd.DataFrame) -> VolumeProfileData:
        """
        최근 세션 바에서 Volume Profile을 산출한다.

        로직:
          1. 최근 N바(vp_session_bars × vp_lookback_sessions) 추출
          2. 가격 범위를 50개 빈으로 분할
          3. 각 빈에 거래량 배분 (Close 50%, Open 30%, Mid 20%)
          4. POC = 최대 거래량 빈
          5. VAH/VAL = 총 거래량 70% 구간
          6. LVN = POC 대비 30% 이하인 로컬 최소값

        Returns:
            VolumeProfileData: POC, VAH, VAL, 노드 목록, LVN 레벨
        """
        n_bars = self.fc.vp_session_bars * self.fc.vp_lookback_sessions
        session_df = df.tail(min(n_bars, len(df)))

        if session_df.empty:
            return VolumeProfileData()

        price_min = float(session_df["low"].min())
        price_max = float(session_df["high"].max())
        if price_max <= price_min:
            return VolumeProfileData(poc=price_min, vah=price_max, val=price_min)

        # 50개 빈으로 분할
        n_bins = 50
        bin_size = (price_max - price_min) / n_bins
        if bin_size <= 0:
            return VolumeProfileData(poc=price_min, vah=price_max, val=price_min)

        buckets: Dict[float, float] = {}
        total_volume = 0.0

        for _, row in session_df.iterrows():
            vol = float(row.get("volume", 100))
            close_price = float(row["close"])
            open_price = float(row["open"])
            mid_price = (float(row["high"]) + float(row["low"])) / 2.0

            # 가격을 빈에 매핑
            for price, weight in [(close_price, 0.5), (open_price, 0.3), (mid_price, 0.2)]:
                bin_price = round(price_min + round((price - price_min) / bin_size) * bin_size, 4)
                bin_price = max(price_min, min(price_max, bin_price))
                buckets[bin_price] = buckets.get(bin_price, 0.0) + vol * weight

            total_volume += vol

        if not buckets or total_volume <= 0:
            return VolumeProfileData()

        # 노드 정렬 (가격 순)
        nodes = sorted(
            [{"price": p, "volume": v} for p, v in buckets.items()],
            key=lambda x: x["price"],
        )

        # POC: 최대 거래량 빈
        poc_node = max(nodes, key=lambda x: x["volume"])
        poc = poc_node["price"]

        # Value Area (70% of total volume)
        target_va = total_volume * self.fc.vp_value_area_pct
        poc_idx = next(i for i, n in enumerate(nodes) if n["price"] == poc)
        current_va = poc_node["volume"]
        upper_idx = poc_idx
        lower_idx = poc_idx

        while current_va < target_va and (upper_idx < len(nodes) - 1 or lower_idx > 0):
            next_upper = nodes[upper_idx + 1]["volume"] if upper_idx < len(nodes) - 1 else -1
            next_lower = nodes[lower_idx - 1]["volume"] if lower_idx > 0 else -1

            if next_upper == -1 and next_lower == -1:
                break

            # 양쪽 2-step 비교 (dual distribution 대응)
            upper2 = (nodes[upper_idx + 1]["volume"] + nodes[min(upper_idx + 2, len(nodes) - 1)]["volume"]
                      if upper_idx < len(nodes) - 2 else next_upper)
            lower2 = (nodes[lower_idx - 1]["volume"] + nodes[max(lower_idx - 2, 0)]["volume"]
                      if lower_idx > 1 else next_lower)

            if upper2 > lower2:
                upper_idx += 1
                current_va += nodes[upper_idx]["volume"]
            else:
                lower_idx -= 1
                current_va += nodes[lower_idx]["volume"]

        vah = nodes[upper_idx]["price"]
        val = nodes[lower_idx]["price"]

        # LVN 감지: 로컬 최소 + POC 대비 30% 이하
        max_vol = poc_node["volume"]
        lvn_levels = []
        if len(nodes) > 5:
            for i in range(2, len(nodes) - 2):
                v_cur = nodes[i]["volume"]
                if (v_cur < nodes[i - 1]["volume"] and v_cur < nodes[i + 1]["volume"]
                        and v_cur < nodes[i - 2]["volume"] and v_cur < nodes[i + 2]["volume"]
                        and v_cur < max_vol * 0.3):
                    lvn_levels.append(nodes[i]["price"])

        return VolumeProfileData(
            poc=poc, vah=vah, val=val, nodes=nodes, lvn_levels=lvn_levels,
        )

    # ══════════════════════════════════════════
    # 3. AMT 3-Stage Filter
    # ══════════════════════════════════════════

    def _detect_market_state(
        self, df: pd.DataFrame, vp: VolumeProfileData,
    ) -> Tuple[str, float, str]:
        """
        AMT Step 1: 마켓 상태 감지 — BALANCE / IMBALANCE_BULL / IMBALANCE_BEAR.

        판단 기준:
          - 최근 N바 중 VAH-VAL 내 체류 비율 (≥70% → BALANCE)
          - Z-Score 방향성
          - 연속 방향 봉 & 레인지 확장

        Returns:
            (state, score, reason)
        """
        if len(df) < 10:
            return "BALANCE", 0.0, "데이터 부족"

        recent = df.tail(10)
        vah, val = vp.vah, vp.val

        if vah <= val:
            return "BALANCE", 50.0, "VA 범위 0"

        # VA 내 체류 비율
        in_va = sum(1 for _, r in recent.iterrows()
                    if val <= float(r["close"]) <= vah)
        in_va_pct = in_va / len(recent)

        # Z-Score
        zscore = float(df.iloc[-1].get("zscore", 0)) if "zscore" in df.columns else 0.0

        # 연속 방향 봉
        closes = [float(r["close"]) for _, r in recent.iterrows()]
        bull_momentum = 0
        bear_momentum = 0
        for i in range(len(closes) - 1, 0, -1):
            if closes[i] > closes[i - 1]:
                bull_momentum += 1
            elif closes[i] < closes[i - 1]:
                bear_momentum += 1
            else:
                break

        # 레인지 확장
        ranges = [float(r["high"]) - float(r["low"]) for _, r in recent.iterrows()]
        avg_range = np.mean(ranges) if ranges else 1.0
        last_range = ranges[-1] if ranges else 0.0
        range_expansion = last_range / avg_range if avg_range > 0 else 1.0

        # ── BALANCE: VA 내 봉 ≥ 70%, Z-Score 약, 레인지 확장 없음 ──
        balance_ratio = self.fc.amt_balance_ratio
        if in_va_pct >= balance_ratio and abs(zscore) < 1.5 and range_expansion < 1.5:
            score = min(100.0, in_va_pct * 100 + (1.5 - abs(zscore)) * 20)
            return "BALANCE", score, (
                f"VA 내 체류 {in_va_pct * 100:.0f}%, Z={zscore:.1f}, 방향성 약함"
            )

        # ── IMBALANCE: VA 밖 or Z-Score 강 ──
        if abs(zscore) >= 1.0 or in_va_pct < 0.5:
            last_close = closes[-1]
            is_bull = zscore < -1.0 or (bull_momentum >= 3 and last_close > vah)
            is_bear = zscore > 1.0 or (bear_momentum >= 3 and last_close < val)

            if is_bull and not is_bear:
                score = min(100.0, abs(zscore) * 25 + bull_momentum * 15 + range_expansion * 10)
                return "IMBALANCE_BULL", score, (
                    f"상방 이탈 Z={zscore:.1f}, 연속상승 {bull_momentum}봉, "
                    f"레인지확장 {range_expansion:.1f}x"
                )
            if is_bear and not is_bull:
                score = min(100.0, abs(zscore) * 25 + bear_momentum * 15 + range_expansion * 10)
                return "IMBALANCE_BEAR", score, (
                    f"하방 이탈 Z={zscore:.1f}, 연속하락 {bear_momentum}봉, "
                    f"레인지확장 {range_expansion:.1f}x"
                )

            # 방향성 모호 — Z-Score 방향으로 판단
            direction = "IMBALANCE_BULL" if zscore <= 0 else "IMBALANCE_BEAR"
            score = abs(zscore) * 20 + 20
            return direction, score, (
                f"VA 밖 {(1 - in_va_pct) * 100:.0f}%, Z={zscore:.1f}, 방향성 미약"
            )

        # ── 전환 구간 ──
        score = in_va_pct * 80
        return "BALANCE", score, (
            f"전환 구간 — VA 내 {in_va_pct * 100:.0f}%, Z={zscore:.1f}"
        )

    def _analyze_location(
        self, price: float, vp: VolumeProfileData, atr: float,
    ) -> Dict:
        """
        AMT Step 2: 가격 위치 분석.

        Zones:
          AT_POC: POC ± ATR × 0.1
          ABOVE_VAH: price > VAH
          BELOW_VAL: price < VAL
          IN_VALUE: VAL ~ VAH 사이
          AT_LVN: LVN 근처 (± ATR × 0.15)

        Returns:
            {"zone": str, "score": float, "distance_from_poc": float}
        """
        atr_buffer = atr * 0.1 if atr > 0 else 0.5

        # LVN 체크 (우선)
        lvn_buffer = atr * 0.15 if atr > 0 else 0.75
        for lvn in vp.lvn_levels:
            if abs(price - lvn) <= lvn_buffer:
                return {
                    "zone": "AT_LVN",
                    "score": 15.0,
                    "distance_from_poc": price - vp.poc,
                }

        # POC 근처
        if abs(price - vp.poc) <= atr_buffer:
            return {
                "zone": "AT_POC",
                "score": 10.0,
                "distance_from_poc": price - vp.poc,
            }

        # VAH 위
        if price > vp.vah:
            return {
                "zone": "ABOVE_VAH",
                "score": 3.0,
                "distance_from_poc": price - vp.poc,
            }

        # VAL 아래
        if price < vp.val:
            return {
                "zone": "BELOW_VAL",
                "score": 3.0,
                "distance_from_poc": price - vp.poc,
            }

        # IN_VALUE
        return {
            "zone": "IN_VALUE",
            "score": 5.0,
            "distance_from_poc": price - vp.poc,
        }

    def _detect_aggression(self, df: pd.DataFrame) -> Dict:
        """
        AMT Step 3: 공격성(Aggression) 감지.

        조건:
          1. body/range 비율 > config.amt_aggression_body_ratio (0.65)
          2. 연속 방향 봉 ≥ config.amt_consecutive_bars (3)
          3. 거래량 서지 (volume > MA × config.amt_aggression_vol_mult)
          4. 레인지 확장 (current range > avg range × 1.2)

        Returns:
            {"detected": bool, "direction": str, "score": float, "reason": str}
        """
        if len(df) < 5:
            return {"detected": False, "direction": "NEUTRAL", "score": 0.0, "reason": "데이터 부족"}

        recent = df.tail(5)
        last = recent.iloc[-1]
        lookback = df.tail(20)

        # Body/Range 비율
        body_ratios = []
        for _, r in recent.iterrows():
            rng = float(r["high"]) - float(r["low"])
            body = abs(float(r["close"]) - float(r["open"]))
            body_ratios.append(body / rng if rng > 0 else 0)
        last_body_ratio = body_ratios[-1]

        # 레인지 확장
        all_ranges = [float(r["high"]) - float(r["low"]) for _, r in lookback.iterrows()]
        avg_range = np.mean(all_ranges) if all_ranges else 1.0
        last_range = float(last["high"]) - float(last["low"])
        range_expansion = last_range / avg_range if avg_range > 0 else 1.0

        # 거래량 서지
        vol_ratio = float(last.get("volume_ratio", 1.0)) if "volume_ratio" in df.columns else 1.0
        vol_surge = vol_ratio >= self.fc.amt_aggression_vol_mult

        # 연속 방향 봉
        consecutive_dir = 0
        direction = "NEUTRAL"
        for i in range(len(df) - 1, max(0, len(df) - 6), -1):
            row = df.iloc[i]
            is_bull = float(row["close"]) > float(row["open"])
            if consecutive_dir == 0:
                direction = "BULL" if is_bull else "BEAR"
                consecutive_dir = 1
            elif (is_bull and direction == "BULL") or (not is_bull and direction == "BEAR"):
                consecutive_dir += 1
            else:
                break

        # 공격성 판정
        is_aggressive = (
            last_body_ratio > self.fc.amt_aggression_body_ratio
            and range_expansion > 1.2
            and (vol_surge or consecutive_dir >= self.fc.amt_consecutive_bars)
        )

        if is_aggressive:
            score = min(100.0, last_body_ratio * 40 + range_expansion * 20 + vol_ratio * 20 + consecutive_dir * 10)
            reason = (
                f"방향성 폭발 ({direction}) — 바디 {last_body_ratio * 100:.0f}%, "
                f"레인지 {range_expansion:.1f}x, 볼륨 {vol_ratio:.1f}x, "
                f"연속 {consecutive_dir}봉"
            )
        else:
            score = 0.0
            reason = (
                f"공격성 미달 — 바디 {last_body_ratio * 100:.0f}%, "
                f"레인지 {range_expansion:.1f}x"
            )

        return {
            "detected": is_aggressive,
            "direction": direction,
            "score": score,
            "reason": reason,
            "body_ratio": last_body_ratio,
            "range_expansion": range_expansion,
            "consecutive_dir": consecutive_dir,
        }

    # ══════════════════════════════════════════
    # 4. 방향 결정
    # ══════════════════════════════════════════

    def _determine_direction(
        self, df: pd.DataFrame, market_state: str, aggression: Dict,
    ) -> FuturesDirection:
        """
        AMT + 모멘텀 합의(consensus)로 방향 결정.

        점수 체계:
          마켓 상태: IMBALANCE_BULL +2, IMBALANCE_BEAR -2
          공격성: direction BULL +2, BEAR -2
          EMA 정렬: fast > mid > slow +1, 역배열 -1
          MACD 히스토그램: > 0 → +1, < 0 → -1
          Z-Score: < -1.5 → +1 (과매도 롱), > +1.5 → -1 (과매수 숏)

        합계 ≥ 3 → LONG, ≤ -3 → SHORT, 그 외 NEUTRAL.
        """
        if len(df) < 2:
            return FuturesDirection.NEUTRAL

        curr = df.iloc[-1]
        for col in ["ema_fast", "ema_mid", "ema_slow", "macd_hist", "zscore"]:
            val = curr.get(col)
            if val is None or pd.isna(val):
                return FuturesDirection.NEUTRAL

        score = 0

        # 마켓 상태
        if market_state == "IMBALANCE_BULL":
            score += 2
        elif market_state == "IMBALANCE_BEAR":
            score -= 2

        # 공격성
        if aggression["detected"]:
            if aggression["direction"] == "BULL":
                score += 2
            elif aggression["direction"] == "BEAR":
                score -= 2

        # EMA 정렬
        ema_f = float(curr["ema_fast"])
        ema_m = float(curr["ema_mid"])
        ema_s = float(curr["ema_slow"])
        if ema_f > ema_m > ema_s:
            score += 1
        elif ema_f < ema_m < ema_s:
            score -= 1

        # MACD
        macd_hist = float(curr["macd_hist"])
        if macd_hist > 0:
            score += 1
        elif macd_hist < 0:
            score -= 1

        # Z-Score
        zscore = float(curr["zscore"])
        if zscore < -1.5:
            score += 1  # 과매도 → 롱 기회
        elif zscore > 1.5:
            score -= 1  # 과매수 → 숏 기회

        if score >= 3:
            return FuturesDirection.LONG
        elif score <= -3:
            return FuturesDirection.SHORT

        return FuturesDirection.NEUTRAL

    # ══════════════════════════════════════════
    # 5. 4-Layer 스코어링
    # ══════════════════════════════════════════

    def _score_amt_location(
        self, market_state: str, location: Dict, direction: FuturesDirection,
    ) -> Tuple[float, List[str]]:
        """
        Layer 1: AMT + Location (max 30점).

        구성:
          AMT 정렬 (max 15): 마켓 상태와 방향 일치
          위치 품질 (max 15): AT_LVN 추세 방향 +15, AT_POC +10, IN_VALUE +5, 엣지 +3

        Returns:
            (score, signals)
        """
        max_score = self.fc.weight_amt_location
        signals: List[str] = []
        score = 0.0
        is_long = direction == FuturesDirection.LONG

        # ── AMT 정렬: 마켓 상태와 매매 방향 일치 (max 15) ──
        if is_long and market_state == "IMBALANCE_BULL":
            score += 15.0
            signals.append("AMT_BULL_ALIGNED")
        elif not is_long and market_state == "IMBALANCE_BEAR":
            score += 15.0
            signals.append("AMT_BEAR_ALIGNED")
        elif market_state == "BALANCE":
            score += 5.0
            signals.append("AMT_BALANCE")

        # ── 위치 품질 (max 15) ──
        zone = location["zone"]
        if zone == "AT_LVN":
            # LVN에서 추세 방향이면 최고 점수
            if (is_long and market_state != "IMBALANCE_BEAR") or (
                not is_long and market_state != "IMBALANCE_BULL"
            ):
                score += 15.0
                signals.append("LOC_LVN_TREND")
            else:
                score += 8.0
                signals.append("LOC_LVN_COUNTER")
        elif zone == "AT_POC":
            score += 10.0
            signals.append("LOC_AT_POC")
        elif zone == "IN_VALUE":
            score += 5.0
            signals.append("LOC_IN_VALUE")
        elif zone in ("ABOVE_VAH", "BELOW_VAL"):
            # 엣지: 추세 방향과 일치하면 추가 점수
            if (is_long and zone == "ABOVE_VAH") or (not is_long and zone == "BELOW_VAL"):
                score += 5.0
                signals.append("LOC_EDGE_TREND")
            else:
                score += 3.0
                signals.append("LOC_EDGE_COUNTER")

        return round(min(score, max_score), 1), signals

    def _score_zscore(
        self, df: pd.DataFrame, direction: FuturesDirection,
    ) -> Tuple[float, List[str]]:
        """
        Layer 2: Z-Score 통계적 위치 (max 20점).

        Mean-Reversion:
          LONG: z < -2.0 → 20, z < -1.5 → 15, z < -1.0 → 10
          SHORT: z > 2.0 → 20, z > 1.5 → 15, z > 1.0 → 10
        Trend-Continuation (추세 방향 약간의 Z):
          5-8점 보간

        Returns:
            (score, signals)
        """
        if len(df) < 1:
            return 0.0, []

        max_score = self.fc.weight_zscore
        zscore = float(df.iloc[-1].get("zscore", 0))
        signals: List[str] = []
        score = 0.0
        is_long = direction == FuturesDirection.LONG

        if is_long:
            if zscore <= -2.0:
                score = max_score  # 20점
                signals.append("Z_EXTREME_OVERSOLD")
            elif zscore <= -1.5:
                score = max_score * 0.75  # 15점
                signals.append("Z_OVERSOLD")
            elif zscore <= -1.0:
                score = max_score * 0.50  # 10점
                signals.append("Z_MILD_OVERSOLD")
            elif -1.0 < zscore <= 0.5:
                # 추세 추종: 평균 근처에서 롱 (5-8점)
                t = (zscore - (-1.0)) / 1.5  # 0..1
                score = max_score * (0.40 * (1 - t) + 0.25 * t)
                signals.append("Z_TREND_PULLBACK")
            elif zscore >= 2.0:
                # 과매수 → 롱 차단
                score = 0
                signals.append("Z_OVERBOUGHT_BLOCK")
        else:
            if zscore >= 2.0:
                score = max_score
                signals.append("Z_EXTREME_OVERBOUGHT")
            elif zscore >= 1.5:
                score = max_score * 0.75
                signals.append("Z_OVERBOUGHT")
            elif zscore >= 1.0:
                score = max_score * 0.50
                signals.append("Z_MILD_OVERBOUGHT")
            elif -0.5 <= zscore < 1.0:
                t = (1.0 - zscore) / 1.5
                score = max_score * (0.40 * (1 - t) + 0.25 * t)
                signals.append("Z_TREND_PULLBACK")
            elif zscore <= -2.0:
                score = 0
                signals.append("Z_OVERSOLD_BLOCK")

        return round(score, 1), signals

    def _score_momentum(
        self, df: pd.DataFrame, direction: FuturesDirection,
    ) -> Tuple[float, List[str]]:
        """
        Layer 3: 모멘텀 (max 25점).

        구성:
          MACD 크로스 방향 일치: +8
          ADX > 25 & DI 정렬: +7
          RSI 적정 범위: +5
          연속 방향 봉: +5

        Returns:
            (score, signals)
        """
        if len(df) < 2:
            return 0.0, []

        max_score = self.fc.weight_momentum
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        signals: List[str] = []
        score = 0.0
        is_long = direction == FuturesDirection.LONG

        macd_hist = float(curr.get("macd_hist", 0))
        macd_hist_prev = float(prev.get("macd_hist", 0))
        adx = float(curr.get("adx", 0))
        plus_di = float(curr.get("plus_di", 0))
        minus_di = float(curr.get("minus_di", 0))
        rsi = float(curr.get("rsi", 50))

        # ── MACD 크로스 (max 8) ──
        if is_long:
            if macd_hist_prev <= 0 < macd_hist:
                score += 8.0
                signals.append("MACD_BULL_CROSS")
            elif macd_hist > 0 and macd_hist > macd_hist_prev:
                score += 4.0
                signals.append("MACD_HIST_RISING")
        else:
            if macd_hist_prev >= 0 > macd_hist:
                score += 8.0
                signals.append("MACD_BEAR_CROSS")
            elif macd_hist < 0 and macd_hist < macd_hist_prev:
                score += 4.0
                signals.append("MACD_HIST_FALLING")

        # ── ADX + DI (max 7) ──
        if is_long:
            if adx > self.fc.adx_threshold and plus_di > minus_di:
                score += 7.0
                signals.append("ADX_BULL_TREND")
        else:
            if adx > self.fc.adx_threshold and minus_di > plus_di:
                score += 7.0
                signals.append("ADX_BEAR_TREND")

        # ── RSI 적정 범위 (max 5) ──
        if is_long:
            if self.fc.rsi_long_range_min <= rsi <= self.fc.rsi_long_range_max:
                score += 5.0
                signals.append("RSI_LONG_OK")
        else:
            if self.fc.rsi_short_range_min <= rsi <= self.fc.rsi_short_range_max:
                score += 5.0
                signals.append("RSI_SHORT_OK")

        # ── 연속 방향 봉 (max 5) ──
        consecutive = 0
        for i in range(len(df) - 1, max(0, len(df) - 6), -1):
            row = df.iloc[i]
            if is_long and float(row["close"]) > float(row["open"]):
                consecutive += 1
            elif not is_long and float(row["close"]) < float(row["open"]):
                consecutive += 1
            else:
                break
        if consecutive >= 3:
            score += 5.0
            signals.append(f"CONSEC_{consecutive}_BARS")

        return round(min(score, max_score), 1), signals

    def _score_volume_aggression(
        self, df: pd.DataFrame, aggression: Dict, direction: FuturesDirection,
    ) -> Tuple[float, List[str]]:
        """
        Layer 4: 거래량 + 공격성 (max 25점).

        구성:
          거래량 서지 (vol > MA × 1.5): +8
          OBV 추세 방향 일치: +7
          Aggression 감지 & 방향 일치: +10

        Returns:
            (score, signals)
        """
        if len(df) < 1:
            return 0.0, []

        max_score = self.fc.weight_volume_aggression
        curr = df.iloc[-1]
        signals: List[str] = []
        score = 0.0
        is_long = direction == FuturesDirection.LONG

        # ── 거래량 서지 (max 8) ──
        vol_ratio = float(curr.get("volume_ratio", 1.0))
        if vol_ratio >= self.fc.amt_aggression_vol_mult:
            score += 8.0
            signals.append("VOL_SURGE")
        elif vol_ratio >= 1.2:
            score += 4.0
            signals.append("VOL_ABOVE_AVG")

        # ── OBV 추세 (max 7) ──
        obv_fast = float(curr.get("obv_ema_fast", 0))
        obv_slow = float(curr.get("obv_ema_slow", 0))
        if is_long and obv_fast > obv_slow:
            score += 7.0
            signals.append("OBV_BULL")
        elif not is_long and obv_fast < obv_slow:
            score += 7.0
            signals.append("OBV_BEAR")

        # ── Aggression (max 10) ──
        if aggression["detected"]:
            dir_match = (
                (is_long and aggression["direction"] == "BULL")
                or (not is_long and aggression["direction"] == "BEAR")
            )
            if dir_match:
                score += 10.0
                signals.append("AGGRESSION_ALIGNED")
            else:
                # 반대 방향 aggression → 페널티
                score -= 5.0
                signals.append("AGGRESSION_COUNTER")

        return round(max(0, min(score, max_score)), 1), signals

    # ══════════════════════════════════════════
    # 6. 메인 시그널 생성
    # ══════════════════════════════════════════

    def generate_intraday_signal(
        self, df: pd.DataFrame, equity: float = 50000.0,
    ) -> Optional[FuturesSignal]:
        """
        인트라데이 시그널을 생성한다.

        파이프라인:
          1. 지표 계산
          2. Volume Profile 산출
          3. AMT 3-Stage Filter (상태 → 위치 → 공격성)
          4. 방향 결정 (AMT + 모멘텀 합의)
          5. 4-Layer 스코어링
          6. Grade 판정 (A/B/C)
          7. SL/TP + 포지션 사이징
          8. FuturesSignal 반환

        Args:
            df: OHLCV DataFrame (15m bars)
            equity: 현재 자본금

        Returns:
            FuturesSignal 또는 None (시그널 없음)
        """
        # ── 세션 정지 체크 ──
        if self._session.should_stop:
            logger.warning("SESSION HALTED | reason=%s", self._session.stop_reason)
            return None

        # ── 지표 계산 ──
        min_len = max(self.fc.ema_slow, self.fc.macd_slow + self.fc.macd_signal, self.fc.zscore_window)
        if df.empty or len(df) < min_len:
            return None

        df = self.calculate_indicators(df.copy())
        if df.empty:
            return None

        curr = df.iloc[-1]

        # NaN 방어
        for col in ["atr", "zscore", "rsi", "adx", "macd_hist"]:
            val = curr.get(col)
            if val is not None and (pd.isna(val) or np.isinf(val)):
                logger.warning("NaN/Inf in %s, skipping", col)
                return None

        current_price = float(curr["close"])
        atr = float(curr["atr"]) if pd.notna(curr.get("atr")) else 0.0

        # ── Volume Profile ──
        vp = self.build_volume_profile(df)

        # ── AMT 3-Stage ──
        market_state, state_score, state_reason = self._detect_market_state(df, vp)
        location = self._analyze_location(current_price, vp, atr)
        aggression = self._detect_aggression(df)

        logger.debug(
            "AMT | state=%s (%.0f) | zone=%s | aggression=%s (%s)",
            market_state, state_score, location["zone"],
            aggression["detected"], aggression["direction"],
        )

        # ── 방향 결정 ──
        direction = self._determine_direction(df, market_state, aggression)
        if direction == FuturesDirection.NEUTRAL:
            return None

        is_long = direction == FuturesDirection.LONG

        # ── 4-Layer 스코어링 ──
        l1_score, l1_signals = self._score_amt_location(market_state, location, direction)
        l2_score, l2_signals = self._score_zscore(df, direction)
        l3_score, l3_signals = self._score_momentum(df, direction)
        l4_score, l4_signals = self._score_volume_aggression(df, aggression, direction)

        total_score = l1_score + l2_score + l3_score + l4_score

        # ── Grade 판정 ──
        if total_score >= self.fc.grade_a_threshold:
            grade = "A"
            contract_mult = 1.0
        elif total_score >= self.fc.grade_b_threshold:
            grade = "B"
            contract_mult = 0.5
        elif total_score >= self.fc.grade_c_threshold:
            grade = "C"
            contract_mult = 0.25
        else:
            # 진입 임계값 미달
            return None

        # ── SL / TP 계산 ──
        if atr <= 0:
            atr = current_price * 0.005  # 폴백: 가격의 0.5%

        sl_distance = atr * self.fc.sl_atr_mult
        tp_distance = atr * self.fc.tp_atr_mult

        if is_long:
            sl = current_price - sl_distance
            tp = current_price + tp_distance
            # 하드 손절 제한
            sl_hard = current_price * (1 - self.fc.sl_hard_pct)
            sl = max(sl, sl_hard)
        else:
            sl = current_price + sl_distance
            tp = current_price - tp_distance
            sl_hard = current_price * (1 + self.fc.sl_hard_pct)
            sl = min(sl, sl_hard)

        rr_ratio = abs(tp - current_price) / abs(current_price - sl) if abs(current_price - sl) > 0 else 0

        # ── 포지션 사이징 ──
        multiplier = 5.0 if self.fc.is_micro else self.fc.contract_multiplier
        risk_amount = equity * self.fc.risk_per_trade_pct
        dollar_risk = abs(current_price - sl) * multiplier
        base_contracts = risk_amount / dollar_risk if dollar_risk > 0 else 0
        contracts = max(1, min(int(base_contracts * contract_mult), self.fc.max_contracts))

        logger.info(
            "INTRADAY %s | grade=%s | score=%.0f (L1:%.0f L2:%.0f L3:%.0f L4:%.0f) | "
            "price=%.2f | SL=%.2f | TP=%.2f | ATR=%.2f | Z=%.2f | contracts=%d",
            "LONG" if is_long else "SHORT", grade, total_score,
            l1_score, l2_score, l3_score, l4_score,
            current_price, sl, tp, atr,
            float(curr.get("zscore", 0)), contracts,
        )

        return FuturesSignal(
            ticker=self.fc.ticker,
            direction="LONG" if is_long else "SHORT",
            signal_strength=total_score,
            entry_price=current_price,
            stop_loss=round(sl, 2),
            take_profit=round(tp, 2),
            atr=atr,
            z_score=float(curr.get("zscore", 0)),
            primary_signals=l1_signals + l2_signals,
            confirmation_filters=l3_signals + l4_signals,
            risk_reward_ratio=round(rr_ratio, 2),
            position_size_contracts=contracts,
            metadata={
                "l1_amt_location": l1_score,
                "l2_zscore": l2_score,
                "l3_momentum": l3_score,
                "l4_volume_aggression": l4_score,
                "grade": grade,
                "contract_mult": contract_mult,
                "market_state": market_state,
                "market_state_score": state_score,
                "market_state_reason": state_reason,
                "location_zone": location["zone"],
                "aggression_detected": aggression["detected"],
                "aggression_direction": aggression["direction"],
                "adx": float(curr.get("adx", 0)),
                "rsi": float(curr.get("rsi", 50)),
                "macd_hist": float(curr.get("macd_hist", 0)),
                "bb_squeeze": float(curr.get("bb_squeeze_ratio", 1)),
                "vp_poc": vp.poc,
                "vp_vah": vp.vah,
                "vp_val": vp.val,
            },
        )

    # ══════════════════════════════════════════
    # 7. 청산 시그널 스캔
    # ══════════════════════════════════════════

    def scan_exit_signals(
        self, position, current_bar: pd.Series, atr: float,
        vp: Optional[VolumeProfileData] = None,
    ) -> List[ExitSignal]:
        """
        보유 포지션의 청산 시그널을 스캔한다.

        우선순위:
          1. ES_HARD: 하드 손절 (|PnL| > 1.5%)
          2. ES_ATR_SL: ATR × 1.5 손절
          3. ES_ATR_TP: ATR × 2.5 익절
          4. ES3: 트레일링 스탑 (+0.8% 활성화, ATR × 1.0)
          5. ES_EOD: EOD 강제 청산 (RTH 종료 15분 전)
          6. ES_SESSION: 세션 정지 (3연속 손절 / 일일 손실)
          7. ES_VP_BREAK: VP 존 이탈 (반대 방향)

        Args:
            position: 보유 포지션 (stock_code, entry_price, direction, position_id 등)
            current_bar: 현재 바 데이터 (close, high, low, timestamp 등)
            atr: 현재 ATR 값
            vp: Volume Profile (VP 존 이탈 체크용, 선택)

        Returns:
            List[ExitSignal]: 발생한 청산 시그널 목록
        """
        exit_signals: List[ExitSignal] = []
        current_price = float(current_bar["close"])
        entry_price = getattr(position, "entry_price", 0.0)
        if entry_price <= 0:
            return exit_signals

        is_long = getattr(position, "direction", "LONG") == "LONG"
        stock_code = getattr(position, "stock_code", self.fc.ticker)
        stock_name = getattr(position, "stock_name", stock_code)
        position_id = getattr(position, "position_id", "")

        if is_long:
            pnl_pct = (current_price - entry_price) / entry_price
        else:
            pnl_pct = (entry_price - current_price) / entry_price

        # 포지션 상태 업데이트
        state = self._get_position_state(stock_code)
        state.bars_held += 1
        if is_long:
            state.highest_since_entry = max(state.highest_since_entry, current_price)
        else:
            state.lowest_since_entry = min(state.lowest_since_entry, current_price)

        def _make_exit(exit_reason: ExitReason, order_type: str = "MARKET",
                       meta: Optional[dict] = None) -> ExitSignal:
            return ExitSignal(
                stock_code=stock_code,
                stock_name=stock_name,
                position_id=position_id,
                exit_type=exit_reason.value,
                exit_reason=exit_reason.name,
                order_type=order_type,
                current_price=current_price,
                pnl_pct=pnl_pct,
                metadata=meta or {},
            )

        # ── 1. ES_HARD: 하드 손절 (-1.5%) ──
        if pnl_pct <= -self.fc.sl_hard_pct:
            logger.info(
                "EXIT ES_HARD | %s | %s | pnl=%.2f%%",
                stock_name, "LONG" if is_long else "SHORT", pnl_pct * 100,
            )
            exit_signals.append(_make_exit(ExitReason.HARD_STOP))
            return exit_signals

        # ── 2. ES_ATR_SL: ATR 기반 손절 ──
        if atr > 0:
            sl_dist = atr * self.fc.sl_atr_mult
            if is_long:
                sl_level = entry_price - sl_dist
                triggered = current_price <= sl_level
            else:
                sl_level = entry_price + sl_dist
                triggered = current_price >= sl_level

            if triggered:
                logger.info(
                    "EXIT ES_ATR_SL | %s | %s | price=%.2f | SL=%.2f | pnl=%.2f%%",
                    stock_name, "LONG" if is_long else "SHORT",
                    current_price, sl_level, pnl_pct * 100,
                )
                exit_signals.append(_make_exit(
                    ExitReason.ATR_STOP_LOSS,
                    meta={"sl_level": round(sl_level, 2)},
                ))
                return exit_signals

        # ── 3. ES_ATR_TP: ATR 기반 익절 ──
        if atr > 0:
            tp_dist = atr * self.fc.tp_atr_mult
            if is_long:
                tp_level = entry_price + tp_dist
                triggered = current_price >= tp_level
            else:
                tp_level = entry_price - tp_dist
                triggered = current_price <= tp_level

            if triggered:
                logger.info(
                    "EXIT ES_ATR_TP | %s | %s | price=%.2f | TP=%.2f | pnl=%.2f%%",
                    stock_name, "LONG" if is_long else "SHORT",
                    current_price, tp_level, pnl_pct * 100,
                )
                exit_signals.append(_make_exit(
                    ExitReason.ATR_TAKE_PROFIT,
                    meta={"tp_level": round(tp_level, 2)},
                ))
                return exit_signals

        # ── 4. ES3: 트레일링 스탑 ──
        if pnl_pct >= self.fc.trailing_activation_pct:
            state.trailing_active = True

        if state.trailing_active and atr > 0:
            trail_dist = atr * self.fc.trailing_atr_mult
            if is_long:
                trail_stop = state.highest_since_entry - trail_dist
                triggered = current_price <= trail_stop
            else:
                trail_stop = state.lowest_since_entry + trail_dist
                triggered = current_price >= trail_stop

            if triggered:
                logger.info(
                    "EXIT ES3 TRAILING | %s | %s | price=%.2f | trail=%.2f | pnl=%.2f%%",
                    stock_name, "LONG" if is_long else "SHORT",
                    current_price, trail_stop, pnl_pct * 100,
                )
                exit_signals.append(_make_exit(
                    ExitReason.TRAILING_STOP,
                    meta={"trail_stop": round(trail_stop, 2)},
                ))
                return exit_signals

        # ── 5. ES_EOD: EOD 강제 청산 ──
        timestamp = current_bar.get("timestamp") or current_bar.name
        if self._is_near_eod(timestamp):
            logger.info(
                "EXIT ES_EOD | %s | forced close | pnl=%.2f%%",
                stock_name, pnl_pct * 100,
            )
            exit_signals.append(_make_exit(ExitReason.EOD_CLOSE))
            return exit_signals

        # ── 6. ES_SESSION: 세션 정지 ──
        if self._session.should_stop:
            logger.info(
                "EXIT ES_SESSION | %s | %s | pnl=%.2f%%",
                stock_name, self._session.stop_reason, pnl_pct * 100,
            )
            exit_signals.append(_make_exit(
                ExitReason.SESSION_HALT,
                meta={"stop_reason": self._session.stop_reason},
            ))
            return exit_signals

        # ── 7. ES_VP_BREAK: VP 존 이탈 ──
        if vp is not None:
            vp_triggered = False
            if is_long and current_price < vp.val:
                vp_triggered = True
            elif not is_long and current_price > vp.vah:
                vp_triggered = True

            if vp_triggered:
                logger.info(
                    "EXIT ES_VP_BREAK | %s | %s | price=%.2f | VAH=%.2f VAL=%.2f | pnl=%.2f%%",
                    stock_name, "LONG" if is_long else "SHORT",
                    current_price, vp.vah, vp.val, pnl_pct * 100,
                )
                exit_signals.append(_make_exit(
                    ExitReason.VP_ZONE_BREAK,
                    meta={"vp_vah": vp.vah, "vp_val": vp.val},
                ))
                return exit_signals

        return exit_signals

    # ══════════════════════════════════════════
    # 유틸리티
    # ══════════════════════════════════════════

    def _get_position_state(self, code: str) -> IntradayPositionState:
        """포지션 상태 반환 (없으면 생성)."""
        if code not in self._position_states:
            self._position_states[code] = IntradayPositionState()
        return self._position_states[code]

    def _is_near_eod(self, timestamp) -> bool:
        """RTH 종료 N분 전 여부 판단."""
        try:
            if isinstance(timestamp, str):
                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            elif isinstance(timestamp, pd.Timestamp):
                dt = timestamp.to_pydatetime()
            elif isinstance(timestamp, datetime):
                dt = timestamp
            else:
                return False

            # RTH 종료 시간 파싱
            end_parts = self.fc.rth_end.split(":")
            rth_end_minutes = int(end_parts[0]) * 60 + int(end_parts[1])
            current_minutes = dt.hour * 60 + dt.minute

            minutes_to_close = rth_end_minutes - current_minutes
            return 0 < minutes_to_close <= self.fc.eod_close_minutes_before
        except (ValueError, AttributeError):
            return False

    def record_trade_result(self, pnl_pct: float, pnl_dollars: float = 0.0) -> None:
        """트레이드 결과 기록 (세션 + EV 히스토리)."""
        self._trade_history.append(pnl_pct)
        if len(self._trade_history) > 50:
            self._trade_history = self._trade_history[-50:]

        self._session.record_trade(
            pnl_dollars,
            self.fc.max_daily_trades,
            self.fc.max_daily_loss_dollars,
            self.fc.max_consecutive_losses,
        )

    def reset_session(self) -> None:
        """새 거래일 시작 시 세션 상태 초기화."""
        self._session.reset()
        self._position_states.clear()
        logger.info("SESSION RESET | new trading day")

    def get_session_state(self) -> Dict:
        """현재 세션 상태 반환 (API 노출용)."""
        return {
            "trade_count": self._session.trade_count,
            "total_pnl_dollars": self._session.total_pnl_dollars,
            "consecutive_losses": self._session.consecutive_losses,
            "should_stop": self._session.should_stop,
            "stop_reason": self._session.stop_reason,
        }

    # ── Public API 래퍼 메서드 ──────────────────────

    def determine_amt_state(self, df: pd.DataFrame) -> Dict:
        """AMT 3-Stage 상태 판별 (API 노출용)."""
        vp = self.build_volume_profile(df)
        curr = df.iloc[-1]
        current_price = float(curr["close"])
        atr = float(curr.get("atr", 0)) if not pd.isna(curr.get("atr", 0)) else 0.0

        market_state = self._detect_market_state(df, vp)
        location = self._analyze_location(current_price, vp, atr)
        aggression = self._detect_aggression(df)

        return {
            "market_state": market_state,
            "location": location,
            "aggression": aggression,
        }

    def determine_direction(self, df: pd.DataFrame) -> str:
        """매매 방향 판별 (API 노출용)."""
        vp = self.build_volume_profile(df)
        market_state = self._detect_market_state(df, vp)
        aggression = self._detect_aggression(df)
        result = self._determine_direction(df, market_state, aggression)
        return result.value  # FuturesDirection → str

    def score_amt_location(self, df: pd.DataFrame, is_long: bool):
        """L1 AMT+Location 스코어 (API 노출용)."""
        vp = self.build_volume_profile(df)
        curr = df.iloc[-1]
        current_price = float(curr["close"])
        atr = float(curr.get("atr", 0)) if not pd.isna(curr.get("atr", 0)) else 0.0
        market_state = self._detect_market_state(df, vp)
        location = self._analyze_location(current_price, vp, atr)
        direction = FuturesDirection.LONG if is_long else FuturesDirection.SHORT
        return self._score_amt_location(market_state, location, direction)

    def score_zscore(self, df: pd.DataFrame, is_long: bool):
        """L2 Z-Score 스코어 (API 노출용)."""
        direction = FuturesDirection.LONG if is_long else FuturesDirection.SHORT
        return self._score_zscore(df, direction)

    def score_momentum(self, df: pd.DataFrame, is_long: bool):
        """L3 Momentum 스코어 (API 노출용)."""
        direction = FuturesDirection.LONG if is_long else FuturesDirection.SHORT
        return self._score_momentum(df, direction)

    def score_volume_aggression(self, df: pd.DataFrame, is_long: bool):
        """L4 Volume+Aggression 스코어 (API 노출용)."""
        direction = FuturesDirection.LONG if is_long else FuturesDirection.SHORT
        aggression = self._detect_aggression(df)
        return self._score_volume_aggression(df, aggression, direction)

    def get_volume_profile_summary(self, df: pd.DataFrame) -> Dict:
        """VP 요약 데이터 (API 노출용)."""
        vp = self.build_volume_profile(df)
        return {
            "poc": vp.poc,
            "vah": vp.vah,
            "val": vp.val,
            "lvn_levels": vp.lvn_levels,
            "node_count": len(vp.nodes),
        }
