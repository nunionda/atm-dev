"""
선물 전용 백테스터 — 단일 티커 양방향(LONG/SHORT) 시뮬레이션.

기존 HistoricalBacktester는 유니버스 기반(멀티 종목)이므로,
단일 선물 티커의 양방향 매매를 위한 경량 백테스터.

고도화:
  - 거래비용 모델링 (슬리피지 + 커미션)
  - 확장 메트릭 (Sortino, Calmar, CAGR, 연승/연패, MDD Duration)
  - 서킷브레이커 (RG1 일일 손실, RG2 MDD)
  - Monte Carlo 스트레스 테스트
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

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
    ):
        # is_micro 설정 반영
        if is_micro:
            config.sp500_futures.is_micro = True
            config.sp500_futures.contract_multiplier = 5.0

        self.strategy = SP500FuturesStrategy(config)
        self.fc = config.sp500_futures
        self.ticker = ticker
        self.start_date = start_date
        self.end_date = end_date
        self.initial_equity = initial_equity
        self.is_micro = is_micro
        self.multiplier = 5.0 if is_micro else config.sp500_futures.contract_multiplier

        # 거래비용
        if is_micro:
            self.slippage_per_contract = 1.25   # Micro 1 tick
            self.commission_per_contract = 0.62  # Micro round-turn
        else:
            self.slippage_per_contract = self.fc.futures_slippage_per_contract
            self.commission_per_contract = self.fc.futures_commission_per_contract

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

        for i, (date, row) in enumerate(df_bt.iterrows()):
            current_price = float(row["close"])
            date_str = date.strftime("%Y-%m-%d") if hasattr(date, "strftime") else str(date)

            # 새로운 거래일 → 일일 시작 에쿼티 갱신
            if date_str != prev_date_str:
                day_start_equity = equity + (
                    self._unrealized_pnl(position, current_price) if position else 0.0
                )
                prev_date_str = date_str

            # 포지션 보유 중 → 청산 체크
            if position is not None:
                position.holding_days += 1

                price_data = PriceData(
                    stock_code=self.ticker,
                    stock_name=self.ticker,
                    current_price=current_price,
                    open_price=float(row["open"]),
                    high_price=float(row["high"]),
                    low_price=float(row["low"]),
                    prev_close=float(df_bt.iloc[max(0, i - 1)]["close"]),
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

                    # 퇴출 거래비용
                    exit_cost = position.contracts * (
                        self.slippage_per_contract + self.commission_per_contract / 2
                    )
                    pnl_dollar -= exit_cost
                    total_costs += exit_cost

                    pnl_pct = pnl_points / position.entry_price if position.entry_price > 0 else 0
                    equity += pnl_dollar

                    trades.append({
                        "entry_date": position.entry_date,
                        "exit_date": date_str,
                        "direction": position.direction,
                        "entry_price": round(position.entry_price, 2),
                        "exit_price": round(current_price, 2),
                        "contracts": position.contracts,
                        "pnl_dollar": round(pnl_dollar, 2),
                        "pnl_pct": round(pnl_pct * 100, 2),
                        "holding_days": position.holding_days,
                        "exit_reason": exit_sig.exit_reason,
                    })

                    # EV/Kelly/연속손절 추적
                    self.strategy.record_trade_result(pnl_pct)

                    self.strategy._position_states.pop(self.ticker, None)
                    position = None

            # 포지션 없음 → 진입 체크 (서킷브레이커 검증)
            if position is None:
                # RG1: 일일 손실 한도
                total_value = equity
                daily_pnl_pct = (total_value - day_start_equity) / day_start_equity if day_start_equity > 0 else 0
                if daily_pnl_pct <= self.fc.rg1_daily_loss_limit:
                    pass  # 진입 차단
                # RG2: MDD 한도
                elif peak_equity > 0 and (total_value - peak_equity) / peak_equity <= self.fc.rg2_mdd_limit:
                    pass  # 진입 차단
                else:
                    df_slice = df.loc[:date]
                    signal = self.strategy.generate_futures_signal(
                        code=self.ticker,
                        df=df_slice,
                        current_price=current_price,
                        equity=equity,
                    )

                    if signal:
                        # 진입 거래비용
                        entry_cost = signal.position_size_contracts * (
                            self.slippage_per_contract + self.commission_per_contract / 2
                        )
                        equity -= entry_cost
                        total_costs += entry_cost

                        position = FuturesPosition(
                            stock_code=self.ticker,
                            entry_price=current_price,
                            direction=signal.direction,
                            contracts=signal.position_size_contracts,
                            entry_date=date_str,
                            stop_loss=signal.stop_loss,
                            take_profit=signal.take_profit,
                        )
                        state = self.strategy._get_position_state(self.ticker)
                        state.reset_for_entry(signal.direction, current_price)

            # Equity curve 기록
            unrealized = self._unrealized_pnl(position, current_price) if position else 0.0
            total_value = equity + unrealized
            peak_equity = max(peak_equity, total_value)
            drawdown = (total_value - peak_equity) / peak_equity if peak_equity > 0 else 0

            equity_curve.append({
                "date": date_str,
                "total_value": round(total_value, 2),
                "equity": round(equity, 2),
                "drawdown_pct": round(drawdown * 100, 2),
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

            trades.append({
                "entry_date": position.entry_date,
                "exit_date": last_date,
                "direction": position.direction,
                "entry_price": round(position.entry_price, 2),
                "exit_price": round(last_price, 2),
                "contracts": position.contracts,
                "pnl_dollar": round(pnl_dollar, 2),
                "pnl_pct": round(pnl_pct * 100, 2),
                "holding_days": position.holding_days,
                "exit_reason": "FORCED_CLOSE",
            })
            self.strategy.record_trade_result(pnl_pct)

        # 3. Metrics 계산
        metrics = self._calculate_metrics(trades, equity_curve, total_costs)

        return {
            "ticker": self.ticker,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "initial_equity": self.initial_equity,
            "final_equity": round(equity, 2),
            "metrics": metrics,
            "equity_curve": equity_curve,
            "trades": trades,
        }

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
        return result

    def _run_monte_carlo(self, daily_returns: pd.Series, n_simulations: int = 1000, n_days: int = 252) -> dict:
        """Monte Carlo 부트스트랩 스트레스 테스트."""
        if len(daily_returns) < 20:
            return {"var_95": 0, "cvar_99": 0, "worst_mdd": 0, "median_return": 0, "bankruptcy_prob": 0}

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

        return {
            "var_95": round(abs(final_returns[var_95_idx]) * 100, 2),
            "cvar_99": round(abs(cvar_99) * 100, 2),
            "worst_mdd": round(abs(min(max_drawdowns)) * 100, 2),
            "median_return": round(np.median(final_returns) * 100, 2),
            "bankruptcy_prob": round(bankrupt_count / n_simulations * 100, 2),
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
            "monte_carlo": {"var_95": 0, "cvar_99": 0, "worst_mdd": 0, "median_return": 0, "bankruptcy_prob": 0},
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
