"""
선물 전용 백테스터 — 단일 티커 양방향(LONG/SHORT) 시뮬레이션.

기존 HistoricalBacktester는 유니버스 기반(멀티 종목)이므로,
단일 선물 티커의 양방향 매매를 위한 경량 백테스터.

고도화:
  - 거래비용 모델링 (슬리피지 + 커미션)
  - 확장 메트릭 (Sortino, Calmar, CAGR, 연승/연패, MDD Duration)
  - 서킷브레이커 (RG1 일일 손실, RG2 MDD, 거래소 CB)
  - 증거금 시뮬레이션 (개시/유지 증거금, Margin Call)
  - 롤오버 비용 (분기별 캘린더 스프레드)
  - Monte Carlo 스트레스 테스트
"""

from __future__ import annotations

import calendar
import random
from dataclasses import dataclass, field
from datetime import datetime, date as date_type, timedelta
from typing import Callable, Dict, List, Optional

import numpy as np
import pandas as pd
import yfinance as yf

from common.types import ExitSignal, PriceData
from data.config_manager import ATSConfig, ConfigManager
from infra.logger import get_logger
from strategy.sp500_futures import SP500FuturesStrategy, FuturesPositionState

logger = get_logger("futures_backtester")


@dataclass
class FuturesPosition:
    """백테스트용 선물 포지션."""
    stock_code: str
    entry_price: float
    direction: str  # "LONG" | "SHORT"
    contracts: int = 1
    entry_date: str = ""
    holding_days: int = 0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    position_id: str = ""
    stock_name: str = ""

    def __post_init__(self):
        if not self.position_id:
            self.position_id = f"FUT-{self.stock_code}-{self.entry_date}"
        if not self.stock_name:
            self.stock_name = self.stock_code


class FuturesBacktester:
    """단일 선물 티커 백테스터."""

    def __init__(
        self,
        config: ATSConfig,
        ticker: str = "ES=F",
        start_date: str = "20240101",
        end_date: str = "20260101",
        initial_equity: float = 100000.0,
        is_micro: bool = False,
        progress_callback: Optional[Callable[[float], None]] = None,
        trend_adaptive: bool = False,
    ):
        # is_micro 설정 반영
        if is_micro:
            config.sp500_futures.is_micro = True
            config.sp500_futures.contract_multiplier = 5.0

        self.trend_adaptive = trend_adaptive
        self.strategy = SP500FuturesStrategy(config, trend_adaptive=trend_adaptive)
        self.fc = config.sp500_futures
        self.ticker = ticker
        self.start_date = start_date
        self.end_date = end_date
        self.initial_equity = initial_equity
        self.is_micro = is_micro
        self.multiplier = 5.0 if is_micro else config.sp500_futures.contract_multiplier
        self.progress_callback = progress_callback

        # 거래비용
        if is_micro:
            self.slippage_per_contract = 1.25   # Micro 1 tick
            self.commission_per_contract = 0.62  # Micro round-turn
        else:
            self.slippage_per_contract = self.fc.futures_slippage_per_contract
            self.commission_per_contract = self.fc.futures_commission_per_contract

        # 증거금
        if is_micro:
            self.initial_margin = self.fc.mes_initial_margin
            self.maintenance_margin = self.fc.mes_maintenance_margin
        else:
            self.initial_margin = self.fc.es_initial_margin
            self.maintenance_margin = self.fc.es_maintenance_margin
        self.margin_calls: List[dict] = []

        # 거래소 서킷브레이커
        self.cb_events: List[dict] = []

        # 롤오버
        self.roll_events: List[dict] = []
        self.total_roll_costs = 0.0
        self._roll_dates = self._compute_roll_dates()

    # ── 롤오버 유틸리티 ──

    def _compute_roll_dates(self) -> set:
        """백테스트 기간 내 롤 데이트(셋째 금요일 직전 월요일) 집합 반환."""
        start_dt = datetime.strptime(self.start_date, "%Y%m%d")
        end_dt = datetime.strptime(self.end_date, "%Y%m%d")
        roll_dates = set()
        for year in range(start_dt.year - 1, end_dt.year + 1):
            for month in [3, 6, 9, 12]:
                expiry = self._third_friday(year, month)
                roll_date = expiry - timedelta(days=(expiry.weekday() - 0) % 7)
                if roll_date >= expiry:
                    roll_date -= timedelta(days=7)
                roll_dates.add(roll_date.isoformat())
        return roll_dates

    @staticmethod
    def _third_friday(year: int, month: int) -> date_type:
        """주어진 년/월의 셋째 금요일 계산."""
        c = calendar.Calendar(firstweekday=calendar.MONDAY)
        fridays = [
            d for d in c.itermonthdays2(year, month)
            if d[0] != 0 and d[1] == calendar.FRIDAY
        ]
        return date_type(year, month, fridays[2][0])

    # ── 거래소 서킷브레이커 ──

    def _check_exchange_cb(self, close: float, prev_close: float) -> Optional[str]:
        """거래소 CB 체크. 발동 시 레벨 문자열 반환."""
        if not self.fc.exchange_cb_enabled or prev_close <= 0:
            return None
        pct_change = (close - prev_close) / prev_close
        if pct_change <= -self.fc.cb_level3_pct:
            return "LEVEL3"
        if pct_change <= -self.fc.cb_level2_pct:
            return "LEVEL2"
        if pct_change <= -self.fc.cb_level1_pct:
            return "LEVEL1"
        return None

    def run(self) -> dict:
        """백테스트 실행. metrics + equity_curve + trades 반환."""
        # 1. 데이터 다운로드 (워밍업 포함)
        start_dt = datetime.strptime(self.start_date, "%Y%m%d")
        end_dt = datetime.strptime(self.end_date, "%Y%m%d")

        warmup_start = start_dt - pd.Timedelta(days=365)

        raw = yf.download(
            self.ticker,
            start=warmup_start.strftime("%Y-%m-%d"),
            end=end_dt.strftime("%Y-%m-%d"),
            auto_adjust=True,
            progress=False,
        )

        if raw.empty:
            logger.error("No data for %s", self.ticker)
            return self._empty_result()

        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.droplevel(1)

        # 중복 컬럼 제거 (yfinance 버그 방지)
        raw = raw.loc[:, ~raw.columns.duplicated()]

        df = raw.rename(columns={
            "Open": "open", "High": "high", "Low": "low",
            "Close": "close", "Volume": "volume",
        })
        df = df[["open", "high", "low", "close", "volume"]].dropna()

        df = self.strategy.calculate_indicators(df)
        if df.empty:
            return self._empty_result()

        df_bt = df[df.index >= start_dt].copy()
        if len(df_bt) < 10:
            return self._empty_result()

        # 2. 바별 시뮬레이션
        equity = self.initial_equity
        peak_equity = equity
        position: Optional[FuturesPosition] = None
        trades: List[dict] = []
        equity_curve: List[dict] = []
        total_costs = 0.0
        day_start_equity = equity  # RG1 일일 손실 추적
        prev_date_str = ""
        rg2_halt_days = 0  # RG2 서킷브레이커 쿨다운 카운터
        consec_halt_days = 0  # 연속손절 쿨다운 카운터
        RG2_COOLDOWN = 60  # 60 거래일 후 리셋
        CONSEC_COOLDOWN = 20  # 연속손절 후 20 거래일 쿨다운

        total_bars = len(df_bt)
        for i, (date, row) in enumerate(df_bt.iterrows()):
            current_price = float(row["close"])
            date_str = date.strftime("%Y-%m-%d") if hasattr(date, "strftime") else str(date)

            # 진행률 보고 (50봉마다)
            if self.progress_callback and i % 50 == 0:
                self.progress_callback(i / total_bars * 100)

            # 새로운 거래일 → 일일 시작 에쿼티 갱신
            if date_str != prev_date_str:
                day_start_equity = equity + (
                    self._unrealized_pnl(position, current_price) if position else 0.0
                )
                prev_date_str = date_str

            prev_close = float(df_bt.iloc[max(0, i - 1)]["close"])

            # ── 거래소 서킷브레이커 체크 ──
            cb_level = self._check_exchange_cb(current_price, prev_close)
            cb_block_entry = False
            if cb_level:
                self.cb_events.append({
                    "date": date_str,
                    "level": cb_level,
                    "pct_change": round((current_price - prev_close) / prev_close * 100, 2),
                })
                cb_block_entry = True  # 모든 레벨에서 신규 진입 차단

            # ── 롤오버 비용 처리 ──
            if date_str in self._roll_dates and position is not None:
                roll_cost = position.contracts * self.fc.roll_cost_per_contract
                equity -= roll_cost
                self.total_roll_costs += roll_cost
                total_costs += roll_cost
                self.roll_events.append({
                    "date": date_str,
                    "contracts": position.contracts,
                    "cost": round(roll_cost, 2),
                })

            # 포지션 보유 중 → 청산 체크
            if position is not None:
                position.holding_days += 1

                # ── Margin Call 체크 ──
                unrealized = self._unrealized_pnl(position, current_price)
                if self.fc.margin_call_enabled:
                    required_margin = self.maintenance_margin * position.contracts
                    if (equity + unrealized) < required_margin:
                        # Margin Call → 강제 청산
                        if position.direction == "LONG":
                            pnl_points = current_price - position.entry_price
                        else:
                            pnl_points = position.entry_price - current_price

                        pnl_dollar = pnl_points * position.contracts * self.multiplier
                        exit_cost = position.contracts * (
                            self.slippage_per_contract + self.commission_per_contract / 2
                        )
                        pnl_dollar -= exit_cost
                        total_costs += exit_cost
                        pnl_pct = pnl_points / position.entry_price if position.entry_price > 0 else 0
                        equity += pnl_dollar

                        trades.append(self._make_trade_record(
                            position, date_str, current_price, pnl_dollar, pnl_pct, "MARGIN_CALL",
                        ))
                        self.margin_calls.append({
                            "date": date_str,
                            "equity": round(equity + unrealized, 2),
                            "required": round(required_margin, 2),
                        })
                        self.strategy.record_trade_result(pnl_pct)
                        self.strategy._position_states.pop(self.ticker, None)
                        position = None

                # ── 거래소 CB Level 2/3 → 강제 청산 ──
                if position is not None and cb_level in ("LEVEL2", "LEVEL3"):
                    if position.direction == "LONG":
                        pnl_points = current_price - position.entry_price
                    else:
                        pnl_points = position.entry_price - current_price

                    pnl_dollar = pnl_points * position.contracts * self.multiplier
                    exit_cost = position.contracts * (
                        self.slippage_per_contract + self.commission_per_contract / 2
                    )
                    pnl_dollar -= exit_cost
                    total_costs += exit_cost
                    pnl_pct = pnl_points / position.entry_price if position.entry_price > 0 else 0
                    equity += pnl_dollar

                    trades.append(self._make_trade_record(
                        position, date_str, current_price, pnl_dollar, pnl_pct, f"CB_{cb_level}",
                    ))
                    self.strategy.record_trade_result(pnl_pct)
                    self.strategy._position_states.pop(self.ticker, None)
                    position = None

                # ── 전략 퇴출 시그널 ──
                if position is not None:
                    price_data = PriceData(
                        stock_code=self.ticker,
                        stock_name=self.ticker,
                        current_price=current_price,
                        open_price=float(row["open"]),
                        high_price=float(row["high"]),
                        low_price=float(row["low"]),
                        prev_close=prev_close,
                        volume=int(row.get("volume", 0)),
                        change_pct=0.0,
                        timestamp=date_str,
                    )

                    df_slice = df.loc[:date]

                    exit_signals = self.strategy.scan_exit_signals(
                        positions=[position],
                        ohlcv_data={self.ticker: df_slice},
                        current_prices={self.ticker: price_data},
                    )

                    if exit_signals:
                        exit_sig = exit_signals[0]
                        if position.direction == "LONG":
                            pnl_points = current_price - position.entry_price
                        else:
                            pnl_points = position.entry_price - current_price

                        pnl_dollar = pnl_points * position.contracts * self.multiplier

                        exit_cost = position.contracts * (
                            self.slippage_per_contract + self.commission_per_contract / 2
                        )
                        pnl_dollar -= exit_cost
                        total_costs += exit_cost

                        pnl_pct = pnl_points / position.entry_price if position.entry_price > 0 else 0
                        equity += pnl_dollar

                        trades.append(self._make_trade_record(
                            position, date_str, current_price, pnl_dollar, pnl_pct, exit_sig.exit_reason,
                        ))

                        self.strategy.record_trade_result(pnl_pct)
                        self.strategy._position_states.pop(self.ticker, None)
                        position = None

            # 포지션 없음 → 진입 체크 (서킷브레이커 검증)
            if position is None:
                # RG1: 일일 손실 한도
                total_value = equity
                daily_pnl_pct = (total_value - day_start_equity) / day_start_equity if day_start_equity > 0 else 0

                # RG2: MDD 한도 (쿨다운 리셋 포함)
                mdd_breached = peak_equity > 0 and (total_value - peak_equity) / peak_equity <= self.fc.rg2_mdd_limit
                if mdd_breached:
                    rg2_halt_days += 1
                    if rg2_halt_days >= RG2_COOLDOWN:
                        peak_equity = total_value
                        rg2_halt_days = 0
                        mdd_breached = False
                        self.strategy._trade_history = []
                else:
                    rg2_halt_days = 0

                # 연속손절 쿨다운
                if self.strategy._consecutive_losses >= self.strategy.fc.max_consecutive_losses:
                    consec_halt_days += 1
                    if consec_halt_days >= CONSEC_COOLDOWN:
                        self.strategy._consecutive_losses = 0
                        consec_halt_days = 0
                        self.strategy._trade_history = []
                else:
                    consec_halt_days = 0

                if cb_block_entry:
                    pass  # 거래소 CB 차단
                elif daily_pnl_pct <= self.fc.rg1_daily_loss_limit:
                    pass  # RG1 차단
                elif mdd_breached:
                    pass  # RG2 차단
                else:
                    df_slice = df.loc[:date]
                    signal = self.strategy.generate_futures_signal(
                        code=self.ticker,
                        df=df_slice,
                        current_price=current_price,
                        equity=equity,
                    )

                    if signal:
                        contracts = signal.position_size_contracts

                        # ── 증거금 검증 ──
                        if self.fc.margin_call_enabled:
                            max_affordable = int(equity // self.initial_margin) if self.initial_margin > 0 else contracts
                            contracts = min(contracts, max_affordable)
                            if contracts <= 0:
                                contracts = 0  # 증거금 부족 → 진입 불가

                        if contracts > 0:
                            entry_cost = contracts * (
                                self.slippage_per_contract + self.commission_per_contract / 2
                            )
                            equity -= entry_cost
                            total_costs += entry_cost

                            position = FuturesPosition(
                                stock_code=self.ticker,
                                entry_price=current_price,
                                direction=signal.direction,
                                contracts=contracts,
                                entry_date=date_str,
                                stop_loss=signal.stop_loss,
                                take_profit=signal.take_profit,
                            )
                            # 레짐 정보 저장 (trend_adaptive 모드)
                            if self.trend_adaptive and self.strategy._last_regime_result:
                                position._regime_at_entry = self.strategy._last_regime_result.regime
                                position._trend_score = self.strategy._last_regime_result.trend_score
                            else:
                                position._regime_at_entry = "UNKNOWN"
                                position._trend_score = 0

                            state = self.strategy._get_position_state(self.ticker)
                            state.reset_for_entry(signal.direction, current_price)

            # Equity curve 기록
            unrealized = self._unrealized_pnl(position, current_price) if position else 0.0
            total_value = equity + unrealized
            peak_equity = max(peak_equity, total_value)
            drawdown = (total_value - peak_equity) / peak_equity if peak_equity > 0 else 0

            margin_used = position.contracts * self.initial_margin if position else 0.0
            notional = current_price * position.contracts * self.multiplier if position else 0.0
            eff_leverage = notional / max(total_value, 1) if position else 0.0

            equity_curve.append({
                "date": date_str,
                "total_value": round(total_value, 2),
                "equity": round(equity, 2),
                "drawdown_pct": round(drawdown * 100, 2),
                "margin_used": round(margin_used, 2),
                "effective_leverage": round(eff_leverage, 2),
            })

        # 미청산 포지션 강제 청산
        if position is not None and len(df_bt) > 0:
            last_row = df_bt.iloc[-1]
            last_price = float(last_row["close"])
            last_date = df_bt.index[-1].strftime("%Y-%m-%d")

            if position.direction == "LONG":
                pnl_points = last_price - position.entry_price
            else:
                pnl_points = position.entry_price - last_price

            pnl_dollar = pnl_points * position.contracts * self.multiplier
            exit_cost = position.contracts * (
                self.slippage_per_contract + self.commission_per_contract / 2
            )
            pnl_dollar -= exit_cost
            total_costs += exit_cost

            pnl_pct = pnl_points / position.entry_price if position.entry_price > 0 else 0
            equity += pnl_dollar

            trades.append(self._make_trade_record(
                position, last_date, last_price, pnl_dollar, pnl_pct, "FORCED_CLOSE",
            ))
            self.strategy.record_trade_result(pnl_pct)

        # 3. Metrics 계산
        metrics = self._calculate_metrics(trades, equity_curve, total_costs)

        # 증거금/CB/롤오버 메트릭 추가
        metrics["margin_call_count"] = len(self.margin_calls)
        metrics["cb_event_count"] = len(self.cb_events)
        metrics["cb_events_detail"] = self.cb_events[:20]  # 최대 20개
        metrics["roll_count"] = len(self.roll_events)
        metrics["total_roll_costs"] = round(self.total_roll_costs, 2)

        # 레버리지 통계
        leverages = [e["effective_leverage"] for e in equity_curve if e["effective_leverage"] > 0]
        metrics["max_effective_leverage"] = round(max(leverages), 2) if leverages else 0.0
        margins = [e["margin_used"] for e in equity_curve if e["margin_used"] > 0]
        equities = [e["total_value"] for i, e in enumerate(equity_curve) if e["margin_used"] > 0]
        metrics["avg_margin_utilization"] = (
            round(sum(margins) / sum(equities) * 100, 1) if equities and sum(equities) > 0 else 0.0
        )

        return {
            "ticker": self.ticker,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "initial_equity": self.initial_equity,
            "final_equity": round(equity, 2),
            "trend_adaptive": self.trend_adaptive,
            "metrics": metrics,
            "equity_curve": equity_curve,
            "trades": trades,
        }

    def _make_trade_record(
        self, position: FuturesPosition, exit_date: str, exit_price: float,
        pnl_dollar: float, pnl_pct: float, exit_reason: str,
    ) -> dict:
        """트레이드 기록 생성 (regime 정보 포함)."""
        record = {
            "entry_date": position.entry_date,
            "exit_date": exit_date,
            "direction": position.direction,
            "entry_price": round(position.entry_price, 2),
            "exit_price": round(exit_price, 2),
            "contracts": position.contracts,
            "pnl_dollar": round(pnl_dollar, 2),
            "pnl_pct": round(pnl_pct * 100, 2),
            "holding_days": position.holding_days,
            "exit_reason": exit_reason,
        }
        if self.trend_adaptive:
            record["regime_at_entry"] = getattr(position, "_regime_at_entry", "UNKNOWN")
            record["trend_score"] = getattr(position, "_trend_score", 0)
        return record

    def _unrealized_pnl(self, position: Optional[FuturesPosition], current_price: float) -> float:
        if position is None:
            return 0.0
        if position.direction == "LONG":
            return (current_price - position.entry_price) * position.contracts * self.multiplier
        return (position.entry_price - current_price) * position.contracts * self.multiplier

    def _calculate_metrics(self, trades: List[dict], equity_curve: List[dict], total_costs: float) -> dict:
        """확장 성과 지표 계산."""
        if not trades:
            return self._empty_metrics()

        pnls = [t["pnl_dollar"] for t in trades]
        pnl_pcts = [t["pnl_pct"] for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]

        total_return_pct = ((self.initial_equity + sum(pnls)) / self.initial_equity - 1) * 100
        win_rate = len(wins) / len(trades) * 100 if trades else 0
        avg_win = np.mean(wins) if wins else 0
        avg_loss = abs(np.mean(losses)) if losses else 1
        profit_factor = sum(wins) / abs(sum(losses)) if losses and sum(losses) != 0 else float("inf")

        # MDD + MDD Duration
        max_dd = 0.0
        mdd_duration_days = 0
        if equity_curve:
            dd_values = [e["drawdown_pct"] for e in equity_curve]
            max_dd = min(dd_values) if dd_values else 0.0

            # MDD Duration: 고점 회복까지 최대 일수
            underwater_days = 0
            for e in equity_curve:
                if e["drawdown_pct"] < -0.01:  # underwater
                    underwater_days += 1
                    mdd_duration_days = max(mdd_duration_days, underwater_days)
                else:
                    underwater_days = 0

        # Daily returns for Sharpe/Sortino
        daily_returns = pd.Series(dtype=float)
        sharpe = 0.0
        sortino = 0.0
        if len(equity_curve) > 1:
            values = [e["total_value"] for e in equity_curve]
            daily_returns = pd.Series(values).pct_change().dropna()
            if len(daily_returns) > 0 and daily_returns.std() > 0:
                sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252)

            # Sortino (downside deviation)
            downside = daily_returns[daily_returns < 0]
            if len(downside) > 0:
                downside_std = np.sqrt(np.mean(downside ** 2))
                if downside_std > 0:
                    sortino = (daily_returns.mean() / downside_std) * np.sqrt(252)

        # CAGR + Calmar
        cagr = 0.0
        calmar = 0.0
        if len(equity_curve) > 1:
            years = len(equity_curve) / 252
            final_val = equity_curve[-1]["total_value"]
            if years > 0 and final_val > 0:
                cagr = (final_val / self.initial_equity) ** (1 / years) - 1
                if max_dd < 0:
                    calmar = cagr / abs(max_dd / 100)

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

        # Best/worst trade
        best_trade = max(pnl_pcts) if pnl_pcts else 0
        worst_trade = min(pnl_pcts) if pnl_pcts else 0

        # 방향별 통계
        long_trades = [t for t in trades if t["direction"] == "LONG"]
        short_trades = [t for t in trades if t["direction"] == "SHORT"]
        long_wins = len([t for t in long_trades if t["pnl_dollar"] > 0])
        short_wins = len([t for t in short_trades if t["pnl_dollar"] > 0])

        # Monte Carlo
        monte_carlo = self._run_monte_carlo(daily_returns)

        result = {
            "total_return_pct": round(total_return_pct, 2),
            "sharpe_ratio": round(sharpe, 2),
            "sortino_ratio": round(sortino, 2),
            "calmar_ratio": round(calmar, 2),
            "cagr": round(cagr * 100, 2),
            "max_drawdown_pct": round(max_dd, 2),
            "mdd_duration_days": mdd_duration_days,
            "total_trades": len(trades),
            "win_rate": round(win_rate, 1),
            "profit_factor": round(profit_factor, 2) if profit_factor != float("inf") else 999.0,
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "avg_rr": round(avg_win / avg_loss, 2) if avg_loss > 0 else 0,
            "total_pnl": round(sum(pnls), 2),
            "total_costs": round(total_costs, 2),
            "long_trades": len(long_trades),
            "short_trades": len(short_trades),
            "long_win_rate": round(long_wins / len(long_trades) * 100, 1) if long_trades else 0,
            "short_win_rate": round(short_wins / len(short_trades) * 100, 1) if short_trades else 0,
            "avg_holding_days": round(np.mean([t["holding_days"] for t in trades]), 1) if trades else 0,
            "max_consecutive_wins": max_consec_wins,
            "max_consecutive_losses": max_consec_losses,
            "best_trade_pct": round(best_trade, 2),
            "worst_trade_pct": round(worst_trade, 2),
            "exit_reasons": self._count_exit_reasons(trades),
            "monte_carlo": monte_carlo,
        }

        # Trend-adaptive 모드: 레짐별 통계 추가
        if self.trend_adaptive:
            regime_stats = {}
            for t in trades:
                regime = t.get("regime_at_entry", "UNKNOWN")
                if regime not in regime_stats:
                    regime_stats[regime] = {"trades": 0, "wins": 0, "total_pnl": 0.0}
                regime_stats[regime]["trades"] += 1
                if t["pnl_dollar"] > 0:
                    regime_stats[regime]["wins"] += 1
                regime_stats[regime]["total_pnl"] += t["pnl_dollar"]

            for regime, stats in regime_stats.items():
                stats["win_rate"] = round(stats["wins"] / stats["trades"] * 100, 1) if stats["trades"] > 0 else 0
                stats["total_pnl"] = round(stats["total_pnl"], 2)

            result["regime_stats"] = regime_stats
            result["trend_adaptive"] = True

        return result

    def _run_monte_carlo(self, daily_returns: pd.Series, n_simulations: int = 1000, n_days: int = 252) -> dict:
        """Monte Carlo 부트스트랩 스트레스 테스트."""
        empty_mc = {
            "var_95": 0, "cvar_99": 0, "worst_mdd": 0, "median_return": 0, "bankruptcy_prob": 0,
            "return_distribution": [], "mdd_distribution": [],
            "return_percentiles": {"p5": 0, "p25": 0, "p50": 0, "p75": 0, "p95": 0},
        }
        if len(daily_returns) < 20:
            return empty_mc

        returns_list = daily_returns.tolist()
        final_returns = []
        max_drawdowns = []
        bankrupt_count = 0

        random.seed(42)
        for _ in range(n_simulations):
            sampled = random.choices(returns_list, k=n_days)
            equity = 1.0
            peak = 1.0
            worst_dd = 0.0

            for r in sampled:
                equity *= (1 + r)
                peak = max(peak, equity)
                dd = (equity - peak) / peak
                worst_dd = min(worst_dd, dd)

            final_returns.append(equity - 1)
            max_drawdowns.append(worst_dd)
            if equity < 0.5:
                bankrupt_count += 1

        final_returns.sort()
        max_drawdowns.sort()

        var_95_idx = max(0, int(n_simulations * 0.05) - 1)
        cvar_99_count = max(1, int(n_simulations * 0.01))
        cvar_99 = np.mean(final_returns[:cvar_99_count])

        # 분포 히스토그램 데이터 (20 bins)
        final_arr = np.array(final_returns) * 100
        mdd_arr = np.array(max_drawdowns) * 100

        ret_counts, ret_edges = np.histogram(final_arr, bins=20)
        mdd_counts, mdd_edges = np.histogram(mdd_arr, bins=20)

        return {
            "var_95": round(abs(final_returns[var_95_idx]) * 100, 2),
            "cvar_99": round(abs(cvar_99) * 100, 2),
            "worst_mdd": round(abs(min(max_drawdowns)) * 100, 2),
            "median_return": round(np.median(final_returns) * 100, 2),
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

    def _count_exit_reasons(self, trades: List[dict]) -> dict:
        """청산 사유별 카운트."""
        reasons: Dict[str, int] = {}
        for t in trades:
            reason = t.get("exit_reason", "UNKNOWN")
            reasons[reason] = reasons.get(reason, 0) + 1
        return reasons

    def _empty_metrics(self) -> dict:
        return {
            "total_return_pct": 0, "sharpe_ratio": 0, "sortino_ratio": 0,
            "calmar_ratio": 0, "cagr": 0,
            "max_drawdown_pct": 0, "mdd_duration_days": 0,
            "total_trades": 0, "win_rate": 0, "profit_factor": 0,
            "avg_win": 0, "avg_loss": 0, "avg_rr": 0, "total_pnl": 0,
            "total_costs": 0,
            "long_trades": 0, "short_trades": 0,
            "long_win_rate": 0, "short_win_rate": 0,
            "avg_holding_days": 0,
            "max_consecutive_wins": 0, "max_consecutive_losses": 0,
            "best_trade_pct": 0, "worst_trade_pct": 0,
            "exit_reasons": {},
            "monte_carlo": {
                "var_95": 0, "cvar_99": 0, "worst_mdd": 0, "median_return": 0, "bankruptcy_prob": 0,
                "return_distribution": [], "mdd_distribution": [],
                "return_percentiles": {"p5": 0, "p25": 0, "p50": 0, "p75": 0, "p95": 0},
            },
            # 증거금/CB/롤오버
            "margin_call_count": 0, "max_effective_leverage": 0, "avg_margin_utilization": 0,
            "cb_event_count": 0, "cb_events_detail": [],
            "roll_count": 0, "total_roll_costs": 0,
        }

    def _empty_result(self) -> dict:
        return {
            "ticker": self.ticker,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "initial_equity": self.initial_equity,
            "final_equity": self.initial_equity,
            "metrics": self._empty_metrics(),
            "equity_curve": [],
            "trades": [],
        }
