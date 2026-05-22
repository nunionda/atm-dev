"""
Turtle Trading Swing Strategy — classic Donchian breakout system.

Richard Dennis & William Eckhardt's "Turtle" system (1983):
- Entry  : Donchian Channel breakout (20-day OR 55-day high/low)
- Stop   : Entry ± 2N (N = 20-day ATR) — volatility-based exit
- Sizing : 1% equity / 2N (volatility position sizing)
- Trail  : 10-day reverse breakout exit (System 1) — let winners run
- Time   : days to weeks holding

이 구현은 SP500FuturesStrategy와 동일한 generate_futures_signal/scan_exit_signals
인터페이스를 따른다 — FuturesBacktester가 strategy 교체만으로 사용 가능.

참고: docs/stock_theory/futuresOverlays.md Section A — Turtle 사양 정리.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from common.enums import ExitReason, FuturesDirection
from common.types import ExitSignal, FuturesSignal, PriceData, Signal
from data.config_manager import ATSConfig
from infra.logger import get_logger
from strategy.base import BaseStrategy

logger = get_logger("turtle_swing")


# ══════════════════════════════════════════
# 내부 상태 추적 (SP500과 동일 패턴)
# ══════════════════════════════════════════

@dataclass
class TurtlePositionState:
    """Turtle 포지션 추적 — SP500 FuturesPositionState와 인터페이스 호환."""
    direction: str = "NEUTRAL"
    entry_price: float = 0.0
    entry_atr: float = 0.0       # N at entry (stop 계산용 — 진입 시점 고정)
    bars_held: int = 0
    # SP500 인터페이스 호환 — backtester가 trailing/chandelier에서 사용
    highest_since_entry: float = 0.0
    lowest_since_entry: float = float("inf")
    trailing_active: bool = False
    choch_confirm_count: int = 0

    def reset_for_entry(self, direction: str, entry_price: float):
        """신규 진입 시 상태 초기화 (SP500 인터페이스 호환)."""
        self.direction = direction
        self.entry_price = entry_price
        self.bars_held = 0
        self.trailing_active = False
        self.choch_confirm_count = 0
        if direction == "LONG":
            self.highest_since_entry = entry_price
            self.lowest_since_entry = float("inf")
        else:
            self.lowest_since_entry = entry_price
            self.highest_since_entry = 0.0


# ══════════════════════════════════════════
# Turtle 파라미터 (config 별도 안 거치고 클래스 상수)
# ══════════════════════════════════════════

@dataclass
class TurtleConfig:
    """Turtle 전략 파라미터."""
    # Donchian Channel periods
    entry_period: int = 20        # System 1: 20일 돌파 진입
    exit_period: int = 10         # System 1: 10일 반대 돌파 청산
    # ATR (N) period
    atr_period: int = 20
    # Stop multiplier
    stop_atr_mult: float = 2.0    # Entry ± 2N
    # Position sizing
    risk_per_trade: float = 0.01  # 1% per trade
    max_units: int = 4            # 최대 4 unit 누적
    # Risk cap — 1 contract 만 진입해도 이 값 초과면 entry skip (Micro 권장)
    max_risk_per_contract: float = 0.015  # 1.5% of equity per contract
    # Trend filter (선택) — long-term EMA가 같은 방향일 때만 진입
    use_trend_filter: bool = True
    trend_ma_period: int = 200    # MA200 기준
    # B: Hard stop — Turtle 정통 룰 회복. Default False (2N stop만 사용).
    # 변동성 큰 자산(CL/GC)에서 hard stop이 본 룰 덮어쓰면서 whipsaw 다발 → 비활성화.
    # Catastrophic 안전망은 BR-R02 -15% MDD circuit (futures_backtester)에 위임.
    enable_hard_stop: bool = False
    hard_stop_pct: float = 0.05   # enable_hard_stop=True일 때만 사용
    # C: 변동성 부적합 자산 진입 차단 — Turtle volatility-norm stop 가정 위반.
    # CL ATR% 5.27%, GC ATR% 2.37% — 모두 2N stop이 일상 변동에 잡혀 whipsaw 53/44%.
    # 이 자산은 mean-reversion 또는 commodity-tuned 전략으로 분리.
    disabled_tickers: set = field(default_factory=lambda: {
        "CL=F", "MCL=F", "GC=F", "MGC=F",
    })
    # Per-ticker overrides (T 패턴 답습)
    # 키별 enable_short / enable_long 토글
    per_ticker_overrides: Dict[str, Dict[str, bool]] = field(default_factory=lambda: {
        "GC=F":  {"enable_short": False},
        "MGC=F": {"enable_short": False},
        "CL=F":  {"enable_short": False},
        "MCL=F": {"enable_short": False},
    })


# ══════════════════════════════════════════
# TurtleSwingStrategy
# ══════════════════════════════════════════

class TurtleSwingStrategy(BaseStrategy):
    """Donchian breakout + ATR(N) stop + 1% volatility sizing."""

    def __init__(self, config: ATSConfig, trend_adaptive: bool = False):
        self.config = config
        self.tc = TurtleConfig()
        # SP500FuturesConfig에서 contract_multiplier 등 공유
        self.fc = config.sp500_futures
        self.trend_adaptive = trend_adaptive
        self._position_states: Dict[str, TurtlePositionState] = {}
        # 진단용 카운터 (SP500과 동일 키)
        self._last_long_score = 0
        self._last_short_score = 0
        self._last_regime_result = None
        # consecutive_losses (SP500 인터페이스 호환)
        self._consecutive_losses = 0
        self._trade_history: List[float] = []

    # ══════════════════════════════════════════
    # 1. 지표 계산 — Donchian + ATR
    # ══════════════════════════════════════════

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Donchian Channels + ATR(N) + trend MA."""
        if df.empty or len(df) < max(self.tc.entry_period, self.tc.atr_period, self.tc.trend_ma_period) + 5:
            return df

        h = df["high"].astype(float)
        lo = df["low"].astype(float)
        c = df["close"].astype(float)

        # Donchian Channels — shift(1)로 lookahead bias 차단 (현 봉은 자기 자신 비교 안 함)
        df["donchian_entry_high"] = h.rolling(window=self.tc.entry_period).max().shift(1)
        df["donchian_entry_low"]  = lo.rolling(window=self.tc.entry_period).min().shift(1)
        df["donchian_exit_high"]  = h.rolling(window=self.tc.exit_period).max().shift(1)
        df["donchian_exit_low"]   = lo.rolling(window=self.tc.exit_period).min().shift(1)

        # ATR(N) — Wilder's smoothed ATR (Turtle 원조 방식)
        # α = 1/period (Wilder smoothing) — SMA보다 약 10-15% 큼 (실제 변동성 반영)
        tr1 = h - lo
        tr2 = (h - c.shift(1)).abs()
        tr3 = (lo - c.shift(1)).abs()
        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        df["atr"] = true_range.ewm(alpha=1.0 / self.tc.atr_period, adjust=False).mean()
        df["atr_pct"] = (df["atr"] / c * 100).fillna(0)

        # Trend MA (long-term filter)
        df["trend_ma"] = c.rolling(window=self.tc.trend_ma_period).mean()

        return df

    # ══════════════════════════════════════════
    # 2. 신호 생성 (SP500과 동일 시그너처)
    # ══════════════════════════════════════════

    def generate_futures_signal(
        self,
        code: str,
        df: pd.DataFrame,
        current_price: float,
        equity: float = 100000.0,
    ) -> Optional[FuturesSignal]:
        """Donchian breakout 감지 → FuturesSignal 반환 (없으면 None)."""
        # C: 변동성 부적합 자산 진입 차단 (CL/GC 시리즈)
        if code in self.tc.disabled_tickers:
            return None

        if df.empty or len(df) < max(self.tc.entry_period, self.tc.trend_ma_period) + 2:
            return None

        df = self.calculate_indicators(df.copy())
        if df.empty:
            return None

        curr = df.iloc[-1]

        # NaN 방어
        for col in ("donchian_entry_high", "donchian_entry_low", "atr", "trend_ma"):
            if pd.isna(curr.get(col)):
                return None

        donch_high = float(curr["donchian_entry_high"])
        donch_low = float(curr["donchian_entry_low"])
        atr = float(curr["atr"])
        trend_ma = float(curr["trend_ma"])

        if atr <= 0:
            return None

        # ── 돌파 감지 ──
        long_breakout = current_price > donch_high
        short_breakout = current_price < donch_low

        # Trend filter — MA200 같은 방향만 허용
        if self.tc.use_trend_filter:
            if long_breakout and current_price < trend_ma:
                long_breakout = False  # 장기 추세 반대 → 차단
            if short_breakout and current_price > trend_ma:
                short_breakout = False

        # per-ticker enable_short / enable_long 게이트 (T 패턴)
        allow_short = self._get_ticker_override(code, "enable_short", True)
        allow_long = self._get_ticker_override(code, "enable_long", True)
        if long_breakout and not allow_long:
            long_breakout = False
        if short_breakout and not allow_short:
            short_breakout = False

        # 진단 카운터
        self._last_long_score = 1 if long_breakout else 0
        self._last_short_score = 1 if short_breakout else 0

        if not (long_breakout or short_breakout):
            return None
        if long_breakout and short_breakout:
            # 동시 발생 — 데이터 anomaly, skip
            return None

        is_long = long_breakout
        direction = FuturesDirection.LONG if is_long else FuturesDirection.SHORT

        # ── Stop & Take Profit ──
        # B: Turtle 정통 룰 — 2N stop만 사용 (hard stop default 비활성화).
        # enable_hard_stop=True인 경우만 -5% hard stop 추가 적용.
        stop_distance = self.tc.stop_atr_mult * atr
        if is_long:
            sl = current_price - stop_distance
            if self.tc.enable_hard_stop:
                sl_hard = current_price * (1 - self.tc.hard_stop_pct)
                sl = max(sl, sl_hard)  # 더 가까운 stop 선택
            tp = current_price + stop_distance * 2  # R:R 2:1
        else:
            sl = current_price + stop_distance
            if self.tc.enable_hard_stop:
                sl_hard = current_price * (1 + self.tc.hard_stop_pct)
                sl = min(sl, sl_hard)
            tp = current_price - stop_distance * 2

        # ── Position Sizing — Turtle "Unit" formula ──
        # contracts = (Equity × risk%) / (2N × multiplier)
        multiplier = 5.0 if self.fc.is_micro else self.fc.contract_multiplier
        # B: Turtle 정통 — 2N stop만 사용. enable_hard_stop 시 hard와 더 가까운 것 채택.
        if self.tc.enable_hard_stop:
            if is_long:
                actual_sl_distance = current_price - max(current_price - stop_distance,
                                                          current_price * (1 - self.tc.hard_stop_pct))
            else:
                actual_sl_distance = min(current_price + stop_distance,
                                          current_price * (1 + self.tc.hard_stop_pct)) - current_price
        else:
            actual_sl_distance = stop_distance  # 2N stop만 사용
        dollar_risk_per_contract = actual_sl_distance * multiplier
        if dollar_risk_per_contract <= 0:
            return None
        # Risk cap — 1 contract만 진입해도 max_risk_per_contract 초과 시 entry skip
        one_ct_risk_pct = dollar_risk_per_contract / equity
        if one_ct_risk_pct > self.tc.max_risk_per_contract:
            logger.warning(
                "TURTLE SKIP %s: 1 ct risk = %.2f%% > cap %.2f%% (use Micro contract)",
                code, one_ct_risk_pct * 100, self.tc.max_risk_per_contract * 100,
            )
            return None
        risk_amount = equity * self.tc.risk_per_trade
        contracts = max(1, int(risk_amount / dollar_risk_per_contract))
        contracts = min(contracts, self.tc.max_units, self.fc.max_contracts)

        # signal_strength: 돌파 강도 — (price - donchian) / atr 정규화
        breakout_strength = abs(current_price - (donch_high if is_long else donch_low)) / atr
        signal_strength = min(100.0, 50.0 + breakout_strength * 25.0)  # 50-100 범위

        rr_ratio = 2.0  # 고정 (2N stop + 4N target)

        logger.info(
            "TURTLE %s | %s | breakout=%.2f vs donch=%.2f | ATR=%.2f | SL=%.2f TP=%.2f | %d ct",
            "LONG" if is_long else "SHORT", code,
            current_price, donch_high if is_long else donch_low,
            atr, sl, tp, contracts,
        )

        return FuturesSignal(
            ticker=code,
            direction="LONG" if is_long else "SHORT",
            signal_strength=signal_strength,
            entry_price=current_price,
            stop_loss=round(sl, 2),
            take_profit=round(tp, 2),
            atr=atr,
            z_score=0.0,  # Turtle은 Z-Score 미사용
            primary_signals=[f"DONCHIAN_{self.tc.entry_period}D_{'HIGH' if is_long else 'LOW'}_BREAKOUT"],
            confirmation_filters=[
                f"ATR={atr:.2f}",
                f"TREND_MA200_{'ABOVE' if current_price > trend_ma else 'BELOW'}",
            ],
            risk_reward_ratio=rr_ratio,
            position_size_contracts=contracts,
            metadata={
                "donchian_high": donch_high,
                "donchian_low": donch_low,
                "trend_ma": trend_ma,
                "n_value": atr,  # N = ATR (Turtle 용어)
                "stop_distance_atr": self.tc.stop_atr_mult,
                "strategy": "turtle_swing",
            },
        )

    # ══════════════════════════════════════════
    # 3. 청산 시그널 — 10일 반대 돌파 + ATR stop
    # ══════════════════════════════════════════

    def scan_exit_signals(
        self,
        positions: list,
        ohlcv_data: Dict[str, pd.DataFrame],
        current_prices: Dict[str, PriceData],
    ) -> List[ExitSignal]:
        """10일 반대 Donchian 돌파 OR 2N stop OR 하드 손절."""
        exit_signals: List[ExitSignal] = []

        for pos in positions:
            price_data = current_prices.get(pos.stock_code)
            if not price_data:
                continue
            current_price = price_data.current_price
            entry_price = pos.entry_price
            if not entry_price or entry_price <= 0:
                continue

            is_long = getattr(pos, "direction", "LONG") == "LONG"
            pnl_pct = ((current_price - entry_price) / entry_price) if is_long else ((entry_price - current_price) / entry_price)

            df = ohlcv_data.get(pos.stock_code)
            if df is None or df.empty:
                continue
            if "donchian_exit_high" not in df.columns:
                df = self.calculate_indicators(df.copy())

            if df.empty or len(df) < 2:
                continue
            curr = df.iloc[-1]
            atr = float(curr.get("atr", 0)) or 0.0

            # ── ES1: 하드 손절 (B: 옵션) — enable_hard_stop=True 시에만 ──
            # Default False (Turtle 정통: 2N stop만, catastrophic은 BR-R02 -15% MDD에 위임).
            if self.tc.enable_hard_stop and pnl_pct <= -self.tc.hard_stop_pct:
                exit_signals.append(self._mk_exit(pos, current_price, pnl_pct,
                    ExitReason.STOP_LOSS.value, "HARD_STOP_LOSS"))
                continue

            # ── ES_ATR_SL: 2N ATR stop (Turtle 본 룰) ──
            if atr > 0:
                stop_distance = self.tc.stop_atr_mult * atr
                if is_long and current_price <= entry_price - stop_distance:
                    exit_signals.append(self._mk_exit(pos, current_price, pnl_pct,
                        ExitReason.ATR_STOP_LOSS.value, "TURTLE_2N_STOP"))
                    continue
                if not is_long and current_price >= entry_price + stop_distance:
                    exit_signals.append(self._mk_exit(pos, current_price, pnl_pct,
                        ExitReason.ATR_STOP_LOSS.value, "TURTLE_2N_STOP"))
                    continue

            # ── ES_DONCHIAN_EXIT: 10일 반대 돌파 (Turtle let winners run) ──
            exit_high = curr.get("donchian_exit_high")
            exit_low = curr.get("donchian_exit_low")
            if pd.notna(exit_high) and pd.notna(exit_low):
                if is_long and current_price < float(exit_low):
                    exit_signals.append(self._mk_exit(pos, current_price, pnl_pct,
                        ExitReason.CHOCH_REVERSAL.value, "TURTLE_10D_REVERSE_BREAKOUT"))
                    continue
                if not is_long and current_price > float(exit_high):
                    exit_signals.append(self._mk_exit(pos, current_price, pnl_pct,
                        ExitReason.CHOCH_REVERSAL.value, "TURTLE_10D_REVERSE_BREAKOUT"))
                    continue

        return exit_signals

    def _mk_exit(self, pos, current_price: float, pnl_pct: float,
                 exit_type: str, exit_reason: str) -> ExitSignal:
        logger.info(
            "TURTLE EXIT %s | %s | %s | pnl=%.2f%%",
            pos.stock_name if hasattr(pos, "stock_name") else pos.stock_code,
            "LONG" if getattr(pos, "direction", "LONG") == "LONG" else "SHORT",
            exit_reason, pnl_pct * 100,
        )
        return ExitSignal(
            stock_code=pos.stock_code,
            stock_name=getattr(pos, "stock_name", pos.stock_code),
            position_id=getattr(pos, "position_id", ""),
            exit_type=exit_type,
            exit_reason=exit_reason,
            order_type="MARKET",
            current_price=current_price,
            pnl_pct=pnl_pct,
        )

    # ══════════════════════════════════════════
    # 4. 호환 메서드 (SP500FuturesStrategy 인터페이스 ductyping)
    # ══════════════════════════════════════════

    def scan_entry_signals(
        self,
        universe_codes: List[str],
        ohlcv_data: Dict[str, pd.DataFrame],
        current_prices: Dict[str, PriceData],
    ) -> List[Signal]:
        """BaseStrategy 인터페이스 — 빈 리스트 반환 (FuturesBacktester는 generate_futures_signal 사용)."""
        return []

    def record_trade_result(self, pnl_pct: float) -> None:
        """SP500과 인터페이스 호환 — backtester 호출."""
        self._trade_history.append(pnl_pct)
        if pnl_pct < 0:
            self._consecutive_losses += 1
        else:
            self._consecutive_losses = 0

    def _get_ticker_override(self, ticker: Optional[str], key: str, default: bool) -> bool:
        if not ticker:
            return default
        return bool(self.tc.per_ticker_overrides.get(ticker, {}).get(key, default))

    def _get_regime_mode(self, regime: Optional[str], key: str, default):
        """SP500 호환 더미 — Turtle은 regime-based mr_short path 미사용.

        Backtester가 MR-SHORT 별도 path 진입 여부 결정 시 이 메서드 호출.
        Turtle은 항상 'mr_short' False 반환 → MR-SHORT path 비활성.
        """
        if key == "mr_short":
            return False
        return default

    def _get_position_state(self, code: str) -> TurtlePositionState:
        if code not in self._position_states:
            self._position_states[code] = TurtlePositionState()
        return self._position_states[code]

    def clear_position_state(self, code: str) -> None:
        self._position_states.pop(code, None)
