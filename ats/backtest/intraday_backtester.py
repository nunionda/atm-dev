"""
ES-F 인트라데이 백테스터 — 세션 기반 15m 바 시뮬레이션.

FuturesBacktester(일봉 양방향)와 동일 구조를 따르되,
인트라데이 특화 로직을 적용:
  - 15m 봉 기반 RTH 세션 분할
  - 세션 내 bar-by-bar 진입/청산
  - EOD 강제 청산 (15:45 ET)
  - 세션별 P&L / 연속 손절 관리
  - Monte Carlo (세션 리샘플링)

참조:
  - backtest/futures_backtester.py (구조 패턴)
  - data/config_manager.py (ESFIntradayConfig)
  - common/enums.py (ExitReason: EOD_CLOSE, SESSION_HALT, VP_ZONE_BREAK)
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional

import numpy as np
import pandas as pd
import pytz
import yfinance as yf

from common.enums import ExitReason
from common.types import FuturesSignal
from data.config_manager import ATSConfig, ESFIntradayConfig
from infra.logger import get_logger

logger = get_logger("intraday_backtester")

ET = pytz.timezone("America/New_York")


# ──────────────────────────────────────────────
# 데이터 클래스
# ──────────────────────────────────────────────

@dataclass
class IntradayPosition:
    """인트라데이 포지션."""
    ticker: str
    entry_price: float
    direction: str  # "LONG" | "SHORT"
    contracts: int
    entry_bar_idx: int
    entry_time: str
    stop_loss: float
    take_profit: float
    trailing_high: float = 0.0
    trailing_low: float = 999999.0
    trailing_active: bool = False
    grade: str = "C"

    def __post_init__(self):
        if self.trailing_high <= 0:
            self.trailing_high = self.entry_price
        if self.trailing_low >= 999999:
            self.trailing_low = self.entry_price


@dataclass
class SessionResult:
    """세션(일) 단위 결과."""
    date: str
    trades: int
    wins: int
    losses: int
    total_pnl: float
    max_drawdown: float
    entry_signals: List[str] = field(default_factory=list)


@dataclass
class IntradayMetrics:
    """인트라데이 백테스트 성과 지표."""
    total_return_pct: float = 0.0
    total_pnl: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    sessions_traded: int = 0
    avg_trades_per_session: float = 0.0
    best_session_pnl: float = 0.0
    worst_session_pnl: float = 0.0
    session_win_rate: float = 0.0
    avg_holding_bars: float = 0.0
    avg_holding_minutes: float = 0.0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    exit_reason_distribution: Dict[str, int] = field(default_factory=dict)
    long_trades: int = 0
    short_trades: int = 0
    long_win_rate: float = 0.0
    short_win_rate: float = 0.0


# ──────────────────────────────────────────────
# 인트라데이 백테스터
# ──────────────────────────────────────────────

class IntradayBacktester:
    """ES-F 인트라데이 백테스터 — 세션 기반 15m 바 시뮬레이션."""

    def __init__(
        self,
        config: ATSConfig,
        ticker: str = "ES=F",
        period: str = "60d",
        initial_equity: float = 10000.0,
        is_micro: bool = True,
        progress_callback: Optional[Callable[[float], None]] = None,
    ):
        self.config = config
        self.ic = config.esf_intraday
        self.ticker = ticker
        self.period = period
        self.initial_equity = initial_equity
        self.is_micro = is_micro
        self.progress_callback = progress_callback

        # 계약 승수
        if is_micro:
            self.multiplier = 5.0   # MES = $5/pt
        else:
            self.multiplier = self.ic.contract_multiplier  # ES = $50/pt

        # 거래비용 (편도)
        self.tick_size = 0.25
        self.slippage_per_contract = self.ic.slippage_ticks * self.tick_size * self.multiplier
        self.commission_per_contract = self.ic.commission_per_contract

        # 증거금
        self.initial_margin = self.ic.initial_margin
        self.maintenance_margin = self.ic.maintenance_margin

        # 전략 (lazy import — 파일이 아직 없을 수 있음)
        self._strategy = None

    def _get_strategy(self):
        """ESFIntradayStrategy lazy 로드."""
        if self._strategy is None:
            try:
                from strategy.esf_intraday import ESFIntradayStrategy
                self._strategy = ESFIntradayStrategy(self.config)
            except ImportError:
                logger.warning("ESFIntradayStrategy not found — using indicator-only mode")
                self._strategy = None
        return self._strategy

    # ══════════════════════════════════════════
    # 데이터 다운로드 & 세션 분할
    # ══════════════════════════════════════════

    def _download_data(self) -> pd.DataFrame:
        """yfinance에서 15m 데이터 다운로드."""
        logger.info("Downloading %s, period=%s, interval=15m", self.ticker, self.period)
        raw = yf.download(
            self.ticker,
            period=self.period,
            interval="15m",
            auto_adjust=False,
            progress=False,
        )

        if raw.empty:
            logger.error("No data for %s", self.ticker)
            return pd.DataFrame()

        # MultiIndex 컬럼 처리
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.droplevel(1)

        # 중복 컬럼 제거
        raw = raw.loc[:, ~raw.columns.duplicated()]

        df = raw.rename(columns={
            "Open": "open", "High": "high", "Low": "low",
            "Close": "close", "Volume": "volume",
        })

        # Adj Close 제거 (auto_adjust=False)
        cols = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
        df = df[cols].dropna()

        if df.empty:
            return df

        # UTC → ET 변환
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        df.index = df.index.tz_convert(ET)

        return df

    def _filter_rth(self, df: pd.DataFrame) -> pd.DataFrame:
        """RTH(Regular Trading Hours) 봉만 필터링 (09:30-16:00 ET)."""
        rth_start_h, rth_start_m = map(int, self.ic.rth_start.split(":"))
        rth_end_h, rth_end_m = map(int, self.ic.rth_end.split(":"))

        start_minutes = rth_start_h * 60 + rth_start_m
        end_minutes = rth_end_h * 60 + rth_end_m

        mask = []
        for ts in df.index:
            bar_minutes = ts.hour * 60 + ts.minute
            # 15m 봉: 09:30 봉은 09:30-09:45 구간, 15:45 봉은 15:45-16:00 구간
            mask.append(start_minutes <= bar_minutes < end_minutes)

        return df[mask].copy()

    def _group_by_session(self, df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
        """RTH 데이터를 날짜별 세션으로 그룹핑."""
        sessions = {}
        for ts in df.index:
            date_str = ts.strftime("%Y-%m-%d")
            if date_str not in sessions:
                sessions[date_str] = []
            sessions[date_str].append(ts)

        result = {}
        for date_str, timestamps in sorted(sessions.items()):
            session_df = df.loc[timestamps]
            if len(session_df) >= 2:  # 최소 2봉 이상
                result[date_str] = session_df

        return result

    # ══════════════════════════════════════════
    # 지표 계산
    # ══════════════════════════════════════════

    def _calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """인트라데이 지표 계산 (전체 데이터에 대해 한 번만)."""
        if len(df) < max(self.ic.ema_slow, self.ic.atr_period, self.ic.bb_period) + 5:
            return df

        # EMA
        df["ema_fast"] = df["close"].ewm(span=self.ic.ema_fast, adjust=False).mean()
        df["ema_mid"] = df["close"].ewm(span=self.ic.ema_mid, adjust=False).mean()
        df["ema_slow"] = df["close"].ewm(span=self.ic.ema_slow, adjust=False).mean()

        # ATR
        high_low = df["high"] - df["low"]
        high_pc = (df["high"] - df["close"].shift(1)).abs()
        low_pc = (df["low"] - df["close"].shift(1)).abs()
        true_range = pd.concat([high_low, high_pc, low_pc], axis=1).max(axis=1)
        df["atr"] = true_range.rolling(window=self.ic.atr_period).mean()

        # RSI
        delta = df["close"].diff()
        gain = delta.where(delta > 0, 0.0)
        loss = (-delta).where(delta < 0, 0.0)
        avg_gain = gain.ewm(com=self.ic.rsi_period - 1, min_periods=self.ic.rsi_period).mean()
        avg_loss = loss.ewm(com=self.ic.rsi_period - 1, min_periods=self.ic.rsi_period).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        df["rsi"] = 100 - (100 / (1 + rs))

        # MACD
        ema_fast_macd = df["close"].ewm(span=self.ic.macd_fast, adjust=False).mean()
        ema_slow_macd = df["close"].ewm(span=self.ic.macd_slow, adjust=False).mean()
        df["macd"] = ema_fast_macd - ema_slow_macd
        df["macd_signal"] = df["macd"].ewm(span=self.ic.macd_signal, adjust=False).mean()
        df["macd_hist"] = df["macd"] - df["macd_signal"]

        # Bollinger Bands
        sma = df["close"].rolling(self.ic.bb_period).mean()
        std = df["close"].rolling(self.ic.bb_period).std()
        df["bb_upper"] = sma + self.ic.bb_std * std
        df["bb_lower"] = sma - self.ic.bb_std * std
        df["bb_mid"] = sma

        # Z-Score
        rolling_mean = df["close"].rolling(self.ic.zscore_window).mean()
        rolling_std = df["close"].rolling(self.ic.zscore_window).std()
        df["zscore"] = (df["close"] - rolling_mean) / rolling_std.replace(0, np.nan)

        # Volume MA
        df["volume_ma"] = df["volume"].rolling(self.ic.volume_ma_period).mean()

        # ADX (simplified)
        plus_dm = df["high"].diff()
        minus_dm = -df["low"].diff()
        plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
        minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)
        atr_smooth = true_range.ewm(span=self.ic.adx_period, adjust=False).mean()
        plus_di = 100 * (plus_dm.ewm(span=self.ic.adx_period, adjust=False).mean() / atr_smooth.replace(0, np.nan))
        minus_di = 100 * (minus_dm.ewm(span=self.ic.adx_period, adjust=False).mean() / atr_smooth.replace(0, np.nan))
        dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan))
        df["adx"] = dx.ewm(span=self.ic.adx_period, adjust=False).mean()
        df["plus_di"] = plus_di
        df["minus_di"] = minus_di

        return df

    # ══════════════════════════════════════════
    # 시그널 생성 (전략 없을 때 내장 로직)
    # ══════════════════════════════════════════

    def _generate_signal(
        self,
        df_slice: pd.DataFrame,
        current_bar: pd.Series,
        equity: float,
    ) -> Optional[FuturesSignal]:
        """전략이 있으면 위임, 없으면 내장 4-Layer 스코어링."""
        strategy = self._get_strategy()
        if strategy is not None:
            return strategy.generate_intraday_signal(
                df=df_slice,
                equity=equity,
            )

        # ── Fallback: 내장 간이 시그널 로직 ──
        row = current_bar
        close = float(row["close"])
        atr = float(row.get("atr", 0))
        rsi = float(row.get("rsi", 50))
        zscore = float(row.get("zscore", 0))
        macd_hist = float(row.get("macd_hist", 0))
        adx = float(row.get("adx", 0))
        volume = float(row.get("volume", 0))
        vol_ma = float(row.get("volume_ma", 1))
        ema_fast = float(row.get("ema_fast", close))
        ema_mid = float(row.get("ema_mid", close))
        ema_slow = float(row.get("ema_slow", close))

        if atr <= 0 or np.isnan(atr):
            return None

        # 4-Layer 스코어링
        score = 0.0
        direction = "NEUTRAL"
        signals: List[str] = []

        # L1: AMT + Location (30점)
        l1 = 0.0
        if zscore < -1.5:
            l1 += 20.0
            signals.append("ZSCORE_OVERSOLD")
        elif zscore > 1.5:
            l1 += 20.0
            signals.append("ZSCORE_OVERBOUGHT")
        if close < float(row.get("bb_lower", close)):
            l1 += 10.0
            signals.append("BB_LOWER_BREAK")
        elif close > float(row.get("bb_upper", close)):
            l1 += 10.0
            signals.append("BB_UPPER_BREAK")
        l1 = min(l1, self.ic.weight_amt_location)

        # L2: Z-Score 통계 (20점)
        l2 = 0.0
        abs_z = abs(zscore)
        if abs_z >= 2.0:
            l2 = 20.0
        elif abs_z >= 1.5:
            l2 = 15.0
        elif abs_z >= 1.0:
            l2 = 8.0
        l2 = min(l2, self.ic.weight_zscore)

        # L3: Momentum (25점)
        l3 = 0.0
        if adx > self.ic.adx_threshold:
            l3 += 10.0
            signals.append("ADX_STRONG")
        if macd_hist > 0:
            l3 += 8.0
        elif macd_hist < 0:
            l3 += 8.0  # 양방향 모두 유효
        if self.ic.rsi_long_range_min <= rsi <= self.ic.rsi_long_range_max:
            l3 += 7.0
        elif self.ic.rsi_short_range_min <= rsi <= self.ic.rsi_short_range_max:
            l3 += 7.0
        l3 = min(l3, self.ic.weight_momentum)

        # L4: Volume + Aggression (25점)
        l4 = 0.0
        if vol_ma > 0 and volume > vol_ma * self.ic.amt_aggression_vol_mult:
            l4 += 15.0
            signals.append("VOL_SURGE")
        if vol_ma > 0 and volume > vol_ma:
            l4 += 10.0
        l4 = min(l4, self.ic.weight_volume_aggression)

        score = l1 + l2 + l3 + l4

        # 방향 결정
        if zscore < -1.0 and ema_fast > ema_mid and rsi < 70:
            direction = "LONG"
        elif zscore > 1.0 and ema_fast < ema_mid and rsi > 30:
            direction = "SHORT"
        elif macd_hist > 0 and ema_fast > ema_mid > ema_slow and rsi < 70:
            direction = "LONG"
        elif macd_hist < 0 and ema_fast < ema_mid < ema_slow and rsi > 30:
            direction = "SHORT"

        if direction == "NEUTRAL":
            return None

        # Grade 판정
        if score >= self.ic.grade_a_threshold:
            grade = "A"
        elif score >= self.ic.grade_b_threshold:
            grade = "B"
        elif score >= self.ic.grade_c_threshold:
            grade = "C"
        else:
            return None  # 최소 임계값 미달

        # SL / TP 계산
        if direction == "LONG":
            sl = close - atr * self.ic.sl_atr_mult
            tp = close + atr * self.ic.tp_atr_mult
        else:
            sl = close + atr * self.ic.sl_atr_mult
            tp = close - atr * self.ic.tp_atr_mult

        # 포지션 사이즈
        grade_mult = {"A": 1.0, "B": 0.5, "C": 0.25}[grade]
        risk_dollars = equity * self.ic.risk_per_trade_pct
        risk_per_contract = atr * self.ic.sl_atr_mult * self.multiplier
        if risk_per_contract <= 0:
            return None
        raw_contracts = int(risk_dollars / risk_per_contract)
        contracts = max(1, min(int(raw_contracts * grade_mult), self.ic.max_contracts))

        # 증거금 검증
        max_affordable = int(equity // self.initial_margin) if self.initial_margin > 0 else contracts
        contracts = min(contracts, max_affordable)
        if contracts <= 0:
            return None

        return FuturesSignal(
            ticker=self.ticker,
            direction=direction,
            signal_strength=score,
            entry_price=close,
            stop_loss=sl,
            take_profit=tp,
            atr=atr,
            z_score=zscore,
            primary_signals=signals,
            risk_reward_ratio=round(self.ic.tp_atr_mult / self.ic.sl_atr_mult, 2),
            position_size_contracts=contracts,
            metadata={"grade": grade},
        )

    # ══════════════════════════════════════════
    # 청산 로직
    # ══════════════════════════════════════════

    def _check_exit(
        self,
        position: IntradayPosition,
        bar: pd.Series,
        bar_idx: int,
        is_eod: bool,
        session_halted: bool,
    ) -> Optional[str]:
        """청산 조건 체크. 반환값: exit_reason 문자열 또는 None."""
        close = float(bar["close"])
        high = float(bar["high"])
        low = float(bar["low"])
        atr = float(bar.get("atr", 0)) if not np.isnan(bar.get("atr", 0)) else 0

        if position.direction == "LONG":
            pnl_pct = (close - position.entry_price) / position.entry_price
        else:
            pnl_pct = (position.entry_price - close) / position.entry_price

        # ES_HARD: 하드 손절
        if abs(pnl_pct) > 0 and pnl_pct < -self.ic.sl_hard_pct:
            return ExitReason.HARD_STOP.value

        # ES_ATR_SL: ATR 기반 손절
        if position.direction == "LONG" and low <= position.stop_loss:
            return ExitReason.ATR_STOP_LOSS.value
        if position.direction == "SHORT" and high >= position.stop_loss:
            return ExitReason.ATR_STOP_LOSS.value

        # ES_ATR_TP: ATR 기반 익절
        if position.direction == "LONG" and high >= position.take_profit:
            return ExitReason.ATR_TAKE_PROFIT.value
        if position.direction == "SHORT" and low <= position.take_profit:
            return ExitReason.ATR_TAKE_PROFIT.value

        # 트레일링 업데이트
        if position.direction == "LONG":
            position.trailing_high = max(position.trailing_high, high)
            if pnl_pct >= self.ic.trailing_activation_pct:
                position.trailing_active = True
        else:
            position.trailing_low = min(position.trailing_low, low)
            if pnl_pct >= self.ic.trailing_activation_pct:
                position.trailing_active = True

        # ES_TRAIL: 트레일링 스탑
        if position.trailing_active and atr > 0:
            if position.direction == "LONG":
                trail_stop = position.trailing_high - atr * self.ic.trailing_atr_mult
                if low <= trail_stop:
                    return ExitReason.TRAILING_STOP.value
            else:
                trail_stop = position.trailing_low + atr * self.ic.trailing_atr_mult
                if high >= trail_stop:
                    return ExitReason.TRAILING_STOP.value

        # ES_EOD: 장 마감 전 강제 청산
        if is_eod:
            return ExitReason.EOD_CLOSE.value

        # ES_SESSION: 세션 중단
        if session_halted:
            return ExitReason.SESSION_HALT.value

        return None

    # ══════════════════════════════════════════
    # 메인 실행
    # ══════════════════════════════════════════

    def run(self) -> dict:
        """백테스트 실행. metrics + equity_curve + trades + sessions + monte_carlo 반환."""
        # 1. 데이터 다운로드
        df_raw = self._download_data()
        if df_raw.empty:
            return self._empty_result()

        # 2. RTH 필터 & 지표 계산
        df_rth = self._filter_rth(df_raw)
        if len(df_rth) < 20:
            logger.warning("Insufficient RTH bars: %d", len(df_rth))
            return self._empty_result()

        df_rth = self._calculate_indicators(df_rth)

        # 3. 세션 분할
        sessions = self._group_by_session(df_rth)
        if not sessions:
            return self._empty_result()

        logger.info(
            "Intraday backtest: %d sessions, %d RTH bars",
            len(sessions), len(df_rth),
        )

        # 4. 세션별 시뮬레이션
        equity = self.initial_equity
        peak_equity = equity
        trades: List[dict] = []
        equity_curve: List[dict] = []
        session_results: List[dict] = []
        session_pnls: List[float] = []
        total_costs = 0.0

        rth_end_h, rth_end_m = map(int, self.ic.rth_end.split(":"))
        eod_minutes = rth_end_h * 60 + rth_end_m - self.ic.eod_close_minutes_before

        total_sessions = len(sessions)
        session_dates = sorted(sessions.keys())

        for s_idx, date_str in enumerate(session_dates):
            session_df = sessions[date_str]

            # 진행률 보고
            if self.progress_callback:
                self.progress_callback(s_idx / total_sessions)

            # 세션 상태 초기화
            session_trades = 0
            session_wins = 0
            session_losses = 0
            session_pnl = 0.0
            session_peak = equity
            session_max_dd = 0.0
            consecutive_losses = 0
            session_halted = False
            position: Optional[IntradayPosition] = None
            session_signals: List[str] = []

            bars = list(session_df.iterrows())

            for b_idx, (ts, bar) in enumerate(bars):
                close = float(bar["close"])
                bar_minutes = ts.hour * 60 + ts.minute
                is_eod = bar_minutes >= eod_minutes
                is_last_bar = (b_idx == len(bars) - 1)

                # ── 세션 중단 체크 ──
                if not session_halted:
                    if consecutive_losses >= self.ic.max_consecutive_losses:
                        session_halted = True
                    if session_pnl < -self.ic.max_daily_loss_dollars:
                        session_halted = True

                # ── 포지션 보유 중: 청산 체크 ──
                if position is not None:
                    exit_reason = self._check_exit(
                        position, bar, b_idx,
                        is_eod=is_eod or is_last_bar,
                        session_halted=session_halted,
                    )

                    if exit_reason is not None:
                        # 청산 가격 결정
                        if exit_reason == ExitReason.ATR_STOP_LOSS.value:
                            exit_price = position.stop_loss
                        elif exit_reason == ExitReason.ATR_TAKE_PROFIT.value:
                            exit_price = position.take_profit
                        else:
                            exit_price = close

                        if position.direction == "LONG":
                            pnl_points = exit_price - position.entry_price
                        else:
                            pnl_points = position.entry_price - exit_price

                        pnl_dollar = pnl_points * position.contracts * self.multiplier
                        exit_cost = position.contracts * (
                            self.slippage_per_contract + self.commission_per_contract
                        )
                        pnl_dollar -= exit_cost
                        total_costs += exit_cost

                        pnl_pct = pnl_points / position.entry_price if position.entry_price > 0 else 0
                        equity += pnl_dollar
                        session_pnl += pnl_dollar

                        holding_bars = b_idx - position.entry_bar_idx
                        holding_minutes = holding_bars * 15

                        trade_record = {
                            "entry_time": position.entry_time,
                            "exit_time": ts.strftime("%Y-%m-%d %H:%M"),
                            "date": date_str,
                            "direction": position.direction,
                            "entry_price": round(position.entry_price, 2),
                            "exit_price": round(exit_price, 2),
                            "contracts": position.contracts,
                            "pnl_dollar": round(pnl_dollar, 2),
                            "pnl_pct": round(pnl_pct * 100, 2),
                            "holding_bars": holding_bars,
                            "holding_minutes": holding_minutes,
                            "exit_reason": exit_reason,
                            "grade": position.grade,
                        }
                        trades.append(trade_record)
                        session_trades += 1

                        if pnl_dollar > 0:
                            session_wins += 1
                            consecutive_losses = 0
                        else:
                            session_losses += 1
                            consecutive_losses += 1

                        position = None

                # ── 포지션 없음: 진입 체크 ──
                if position is None and not session_halted and not is_eod and not is_last_bar:
                    if session_trades >= self.ic.max_daily_trades:
                        pass  # 일일 거래 한도 초과
                    else:
                        # 지표 계산에 필요한 충분한 과거 데이터 확보
                        bar_loc = df_rth.index.get_loc(ts)
                        if isinstance(bar_loc, slice):
                            bar_loc = bar_loc.start
                        elif isinstance(bar_loc, np.ndarray):
                            bar_loc = int(bar_loc[0])

                        lookback = max(self.ic.ema_slow, self.ic.zscore_window) + 10
                        start_loc = max(0, bar_loc - lookback)
                        df_slice = df_rth.iloc[start_loc:bar_loc + 1]

                        signal = self._generate_signal(df_slice, bar, equity)
                        if signal is not None:
                            entry_cost = signal.position_size_contracts * (
                                self.slippage_per_contract + self.commission_per_contract
                            )
                            equity -= entry_cost
                            total_costs += entry_cost

                            grade = signal.metadata.get("grade", "C") if signal.metadata else "C"

                            position = IntradayPosition(
                                ticker=self.ticker,
                                entry_price=signal.entry_price,
                                direction=signal.direction,
                                contracts=signal.position_size_contracts,
                                entry_bar_idx=b_idx,
                                entry_time=ts.strftime("%Y-%m-%d %H:%M"),
                                stop_loss=signal.stop_loss,
                                take_profit=signal.take_profit,
                                grade=grade,
                            )
                            session_signals.append(
                                f"{signal.direction}@{signal.entry_price:.2f}"
                            )

                # Equity curve (매 바)
                unrealized = 0.0
                if position is not None:
                    if position.direction == "LONG":
                        unrealized = (close - position.entry_price) * position.contracts * self.multiplier
                    else:
                        unrealized = (position.entry_price - close) * position.contracts * self.multiplier

                total_value = equity + unrealized
                peak_equity = max(peak_equity, total_value)
                drawdown = (total_value - peak_equity) / peak_equity if peak_equity > 0 else 0

                session_max_dd = min(session_max_dd, drawdown)

                equity_curve.append({
                    "timestamp": ts.strftime("%Y-%m-%d %H:%M"),
                    "equity": round(total_value, 2),
                    "drawdown_pct": round(drawdown * 100, 2),
                })

            # ── 세션 종료: 미청산 포지션은 이미 EOD/last_bar에서 처리됨 ──
            session_results.append({
                "date": date_str,
                "trades": session_trades,
                "wins": session_wins,
                "losses": session_losses,
                "total_pnl": round(session_pnl, 2),
                "max_drawdown": round(session_max_dd * 100, 2),
                "signals": session_signals,
            })
            session_pnls.append(session_pnl)

        # 최종 진행률
        if self.progress_callback:
            self.progress_callback(1.0)

        # 5. 메트릭 계산
        metrics = self._calculate_metrics(trades, equity_curve, session_results, total_costs)

        # 6. Monte Carlo (세션 P&L 리샘플링)
        monte_carlo = self._run_monte_carlo(session_pnls)

        return {
            "ticker": self.ticker,
            "period": self.period,
            "initial_equity": self.initial_equity,
            "final_equity": round(equity, 2),
            "is_micro": self.is_micro,
            "metrics": self._metrics_to_dict(metrics),
            "equity_curve": equity_curve,
            "trades": trades,
            "sessions": session_results,
            "monte_carlo": monte_carlo,
        }

    # ══════════════════════════════════════════
    # 메트릭 계산
    # ══════════════════════════════════════════

    def _calculate_metrics(
        self,
        trades: List[dict],
        equity_curve: List[dict],
        session_results: List[dict],
        total_costs: float,
    ) -> IntradayMetrics:
        """성과 지표 계산."""
        if not trades:
            return IntradayMetrics()

        pnls = [t["pnl_dollar"] for t in trades]
        pnl_pcts = [t["pnl_pct"] for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]

        total_pnl = sum(pnls)
        total_return_pct = (total_pnl / self.initial_equity) * 100

        win_rate = len(wins) / len(trades) * 100 if trades else 0
        avg_win = float(np.mean(wins)) if wins else 0
        avg_loss = abs(float(np.mean(losses))) if losses else 0
        profit_factor = sum(wins) / abs(sum(losses)) if losses and sum(losses) != 0 else 999.0

        # MDD
        max_dd = 0.0
        if equity_curve:
            dd_values = [e["drawdown_pct"] for e in equity_curve]
            max_dd = min(dd_values) if dd_values else 0.0

        # Sharpe / Sortino (세션 수익률 기반)
        sharpe = 0.0
        sortino = 0.0
        if len(equity_curve) > 1:
            values = [e["equity"] for e in equity_curve]
            returns = pd.Series(values).pct_change().dropna()
            if len(returns) > 0 and returns.std() > 0:
                # 인트라데이: 연환산에 바 기준 사용
                # 26 bars/session * 252 sessions/year ≈ 6552 bars/year
                annualize = np.sqrt(6552)
                sharpe = float((returns.mean() / returns.std()) * annualize)

            downside = returns[returns < 0]
            if len(downside) > 0:
                downside_std = float(np.sqrt(np.mean(downside ** 2)))
                if downside_std > 0:
                    sortino = float((returns.mean() / downside_std) * annualize)

        # Consecutive wins/losses
        max_consec_wins = 0
        max_consec_losses = 0
        curr_wins = 0
        curr_losses = 0
        for t in trades:
            if t["pnl_dollar"] > 0:
                curr_wins += 1
                curr_losses = 0
                max_consec_wins = max(max_consec_wins, curr_wins)
            else:
                curr_losses += 1
                curr_wins = 0
                max_consec_losses = max(max_consec_losses, curr_losses)

        # 방향별 통계
        long_trades = [t for t in trades if t["direction"] == "LONG"]
        short_trades = [t for t in trades if t["direction"] == "SHORT"]
        long_wins = len([t for t in long_trades if t["pnl_dollar"] > 0])
        short_wins = len([t for t in short_trades if t["pnl_dollar"] > 0])

        # Exit reason 분포
        exit_reasons: Dict[str, int] = {}
        for t in trades:
            reason = t.get("exit_reason", "UNKNOWN")
            exit_reasons[reason] = exit_reasons.get(reason, 0) + 1

        # 세션 통계
        sessions_traded = len([s for s in session_results if s["trades"] > 0])
        session_pnls = [s["total_pnl"] for s in session_results if s["trades"] > 0]
        best_session = max(session_pnls) if session_pnls else 0
        worst_session = min(session_pnls) if session_pnls else 0
        session_wins_count = len([p for p in session_pnls if p > 0])
        session_win_rate = session_wins_count / sessions_traded * 100 if sessions_traded > 0 else 0

        # 보유 시간
        holding_bars = [t["holding_bars"] for t in trades]
        holding_minutes = [t["holding_minutes"] for t in trades]

        return IntradayMetrics(
            total_return_pct=round(total_return_pct, 2),
            total_pnl=round(total_pnl, 2),
            sharpe_ratio=round(sharpe, 2),
            sortino_ratio=round(sortino, 2),
            max_drawdown_pct=round(max_dd, 2),
            win_rate=round(win_rate, 1),
            profit_factor=round(profit_factor, 2),
            total_trades=len(trades),
            winning_trades=len(wins),
            losing_trades=len(losses),
            avg_win=round(avg_win, 2),
            avg_loss=round(avg_loss, 2),
            sessions_traded=sessions_traded,
            avg_trades_per_session=round(len(trades) / sessions_traded, 1) if sessions_traded > 0 else 0,
            best_session_pnl=round(best_session, 2),
            worst_session_pnl=round(worst_session, 2),
            session_win_rate=round(session_win_rate, 1),
            avg_holding_bars=round(float(np.mean(holding_bars)), 1) if holding_bars else 0,
            avg_holding_minutes=round(float(np.mean(holding_minutes)), 1) if holding_minutes else 0,
            max_consecutive_wins=max_consec_wins,
            max_consecutive_losses=max_consec_losses,
            exit_reason_distribution=exit_reasons,
            long_trades=len(long_trades),
            short_trades=len(short_trades),
            long_win_rate=round(long_wins / len(long_trades) * 100, 1) if long_trades else 0,
            short_win_rate=round(short_wins / len(short_trades) * 100, 1) if short_trades else 0,
        )

    def _metrics_to_dict(self, m: IntradayMetrics) -> dict:
        """IntradayMetrics → dict 변환."""
        return {
            "total_return_pct": m.total_return_pct,
            "total_pnl": m.total_pnl,
            "sharpe_ratio": m.sharpe_ratio,
            "sortino_ratio": m.sortino_ratio,
            "max_drawdown_pct": m.max_drawdown_pct,
            "win_rate": m.win_rate,
            "profit_factor": m.profit_factor,
            "total_trades": m.total_trades,
            "winning_trades": m.winning_trades,
            "losing_trades": m.losing_trades,
            "avg_win": m.avg_win,
            "avg_loss": m.avg_loss,
            "sessions_traded": m.sessions_traded,
            "avg_trades_per_session": m.avg_trades_per_session,
            "best_session_pnl": m.best_session_pnl,
            "worst_session_pnl": m.worst_session_pnl,
            "session_win_rate": m.session_win_rate,
            "avg_holding_bars": m.avg_holding_bars,
            "avg_holding_minutes": m.avg_holding_minutes,
            "max_consecutive_wins": m.max_consecutive_wins,
            "max_consecutive_losses": m.max_consecutive_losses,
            "exit_reason_distribution": m.exit_reason_distribution,
            "long_trades": m.long_trades,
            "short_trades": m.short_trades,
            "long_win_rate": m.long_win_rate,
            "short_win_rate": m.short_win_rate,
        }

    # ══════════════════════════════════════════
    # Monte Carlo (세션 리샘플링)
    # ══════════════════════════════════════════

    def _run_monte_carlo(
        self,
        session_pnls: List[float],
        n_simulations: int = 1000,
        n_sessions: int = 252,
    ) -> dict:
        """Monte Carlo 부트스트랩 — 세션 P&L 리샘플링."""
        empty_mc = {
            "var_95": 0, "cvar_99": 0, "worst_mdd": 0,
            "median_return": 0, "bankruptcy_prob": 0,
            "return_distribution": [], "mdd_distribution": [],
            "return_percentiles": {"p5": 0, "p25": 0, "p50": 0, "p75": 0, "p95": 0},
        }

        # 거래가 있는 세션만
        active_pnls = [p for p in session_pnls if p != 0]
        if len(active_pnls) < 5:
            return empty_mc

        random.seed(42)
        final_returns = []
        max_drawdowns = []
        bankrupt_count = 0

        for _ in range(n_simulations):
            sampled = random.choices(active_pnls, k=n_sessions)
            equity = self.initial_equity
            peak = equity
            worst_dd = 0.0

            for pnl in sampled:
                equity += pnl
                peak = max(peak, equity)
                if peak > 0:
                    dd = (equity - peak) / peak
                    worst_dd = min(worst_dd, dd)

            ret = (equity - self.initial_equity) / self.initial_equity
            final_returns.append(ret)
            max_drawdowns.append(worst_dd)
            if equity < self.initial_equity * 0.5:
                bankrupt_count += 1

        final_returns.sort()
        max_drawdowns.sort()

        var_95_idx = max(0, int(n_simulations * 0.05) - 1)
        cvar_99_count = max(1, int(n_simulations * 0.01))
        cvar_99 = float(np.mean(final_returns[:cvar_99_count]))

        # 분포 히스토그램 (20 bins)
        final_arr = np.array(final_returns) * 100
        mdd_arr = np.array(max_drawdowns) * 100

        ret_counts, ret_edges = np.histogram(final_arr, bins=20)
        mdd_counts, mdd_edges = np.histogram(mdd_arr, bins=20)

        return {
            "var_95": round(abs(final_returns[var_95_idx]) * 100, 2),
            "cvar_99": round(abs(cvar_99) * 100, 2),
            "worst_mdd": round(abs(min(max_drawdowns)) * 100, 2),
            "median_return": round(float(np.median(final_returns)) * 100, 2),
            "bankruptcy_prob": round(bankrupt_count / n_simulations * 100, 2),
            "return_distribution": [
                {"bin": round(float(ret_edges[i]), 1), "count": int(ret_counts[i])}
                for i in range(len(ret_counts))
            ],
            "mdd_distribution": [
                {"bin": round(float(mdd_edges[i]), 1), "count": int(mdd_counts[i])}
                for i in range(len(mdd_counts))
            ],
            "return_percentiles": {
                "p5": round(float(np.percentile(final_arr, 5)), 2),
                "p25": round(float(np.percentile(final_arr, 25)), 2),
                "p50": round(float(np.percentile(final_arr, 50)), 2),
                "p75": round(float(np.percentile(final_arr, 75)), 2),
                "p95": round(float(np.percentile(final_arr, 95)), 2),
            },
        }

    # ══════════════════════════════════════════
    # 빈 결과
    # ══════════════════════════════════════════

    def _empty_result(self) -> dict:
        return {
            "ticker": self.ticker,
            "period": self.period,
            "initial_equity": self.initial_equity,
            "final_equity": self.initial_equity,
            "is_micro": self.is_micro,
            "metrics": self._metrics_to_dict(IntradayMetrics()),
            "equity_curve": [],
            "trades": [],
            "sessions": [],
            "monte_carlo": {
                "var_95": 0, "cvar_99": 0, "worst_mdd": 0,
                "median_return": 0, "bankruptcy_prob": 0,
                "return_distribution": [], "mdd_distribution": [],
                "return_percentiles": {"p5": 0, "p25": 0, "p50": 0, "p75": 0, "p95": 0},
            },
        }
