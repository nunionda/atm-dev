"""
백테스트 결과 데이터클래스 및 리포트 출력
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class TradeRecord:
    """개별 매매 기록."""
    stock_code: str
    stock_name: str
    entry_date: str
    entry_price: float
    exit_date: str
    exit_price: float
    quantity: int
    pnl: float
    pnl_pct: float
    exit_reason: str
    holding_days: int = 0


@dataclass
class DailyEquity:
    """일별 자산 기록."""
    date: str
    total_value: float
    cash: float
    positions_value: float = 0.0
    daily_return: float = 0.0
    drawdown: float = 0.0


@dataclass
class BacktestResult:
    """백테스트 전체 결과."""
    start_date: str
    end_date: str
    initial_capital: float
    final_value: float = 0.0

    total_return: float = 0.0
    cagr: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_date: str = ""

    total_trades: int = 0
    win_count: int = 0
    lose_count: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    avg_pnl_pct: float = 0.0
    avg_holding_days: float = 0.0

    trades: List[TradeRecord] = field(default_factory=list)
    equity_curve: List[DailyEquity] = field(default_factory=list)

    def calculate_metrics(self):
        """trades와 equity_curve로부터 성과 지표를 계산한다."""
        # --- 수익률 ---
        if self.initial_capital > 0:
            self.final_value = (
                self.equity_curve[-1].total_value if self.equity_curve else self.initial_capital
            )
            self.total_return = (self.final_value - self.initial_capital) / self.initial_capital

        # --- CAGR ---
        if self.equity_curve and len(self.equity_curve) >= 2:
            trading_days = len(self.equity_curve)
            years = trading_days / 252
            if years > 0 and self.final_value > 0 and self.initial_capital > 0:
                self.cagr = (self.final_value / self.initial_capital) ** (1 / years) - 1

        # --- MDD ---
        peak = 0.0
        for eq in self.equity_curve:
            if eq.total_value > peak:
                peak = eq.total_value
            if peak > 0:
                dd = (eq.total_value - peak) / peak
                eq.drawdown = dd
                if dd < self.max_drawdown:
                    self.max_drawdown = dd
                    self.max_drawdown_date = eq.date

        # --- 일별 수익률 + Sharpe ---
        daily_returns = [eq.daily_return for eq in self.equity_curve if eq.daily_return != 0.0]
        if not daily_returns and len(self.equity_curve) >= 2:
            daily_returns = []
            for i in range(1, len(self.equity_curve)):
                prev = self.equity_curve[i - 1].total_value
                if prev > 0:
                    ret = (self.equity_curve[i].total_value - prev) / prev
                    self.equity_curve[i].daily_return = ret
                    daily_returns.append(ret)

        if daily_returns and len(daily_returns) >= 2:
            avg_ret = sum(daily_returns) / len(daily_returns)
            std_ret = math.sqrt(
                sum((r - avg_ret) ** 2 for r in daily_returns) / (len(daily_returns) - 1)
            )
            if std_ret > 0:
                self.sharpe_ratio = (avg_ret / std_ret) * math.sqrt(252)

        # --- 매매 통계 ---
        self.total_trades = len(self.trades)
        self.win_count = sum(1 for t in self.trades if t.pnl > 0)
        self.lose_count = sum(1 for t in self.trades if t.pnl <= 0)
        self.win_rate = self.win_count / self.total_trades if self.total_trades > 0 else 0.0

        total_profit = sum(t.pnl for t in self.trades if t.pnl > 0)
        total_loss = abs(sum(t.pnl for t in self.trades if t.pnl < 0))
        self.profit_factor = total_profit / total_loss if total_loss > 0 else float("inf")

        if self.total_trades > 0:
            self.avg_pnl_pct = sum(t.pnl_pct for t in self.trades) / self.total_trades
            self.avg_holding_days = sum(t.holding_days for t in self.trades) / self.total_trades

    def print_summary(self):
        """콘솔에 결과 요약을 출력한다."""
        print("=" * 60)
        print("  BACKTEST RESULT SUMMARY")
        print("=" * 60)
        print(f"  Period       : {self.start_date} ~ {self.end_date}")
        print(f"  Initial Cap  : {self.initial_capital:>15,.0f} KRW")
        print(f"  Final Value  : {self.final_value:>15,.0f} KRW")
        print("-" * 60)
        print(f"  Total Return : {self.total_return:>+10.2%}")
        print(f"  CAGR         : {self.cagr:>+10.2%}")
        print(f"  Sharpe Ratio : {self.sharpe_ratio:>10.2f}")
        print(f"  Max Drawdown : {self.max_drawdown:>+10.2%}  ({self.max_drawdown_date})")
        print("-" * 60)
        print(f"  Total Trades : {self.total_trades:>10d}")
        print(f"  Win / Lose   : {self.win_count} / {self.lose_count}")
        print(f"  Win Rate     : {self.win_rate:>10.1%}")
        print(f"  Profit Factor: {self.profit_factor:>10.2f}")
        print(f"  Avg PnL %    : {self.avg_pnl_pct:>+10.2%}")
        print(f"  Avg Hold Days: {self.avg_holding_days:>10.1f}")
        print("=" * 60)

        if self.trades:
            print("\n  Recent Trades (last 10):")
            print(f"  {'Code':<8} {'Entry':>10} {'Exit':>10} {'PnL%':>8} {'Reason':<12}")
            for t in self.trades[-10:]:
                print(
                    f"  {t.stock_code:<8} {t.entry_price:>10,.0f} "
                    f"{t.exit_price:>10,.0f} {t.pnl_pct:>+7.2%} {t.exit_reason:<12}"
                )
            print()

    def export_trades_csv(self, path: str):
        """매매 내역을 CSV로 저장한다."""
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "stock_code", "stock_name", "entry_date", "entry_price",
                "exit_date", "exit_price", "quantity", "pnl", "pnl_pct",
                "exit_reason", "holding_days",
            ])
            for t in self.trades:
                writer.writerow([
                    t.stock_code, t.stock_name, t.entry_date, t.entry_price,
                    t.exit_date, t.exit_price, t.quantity, t.pnl, f"{t.pnl_pct:.4f}",
                    t.exit_reason, t.holding_days,
                ])
        print(f"Trades exported: {path} ({len(self.trades)} rows)")

    def export_equity_csv(self, path: str):
        """자산곡선을 CSV로 저장한다."""
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "date", "total_value", "cash", "positions_value",
                "daily_return", "drawdown",
            ])
            for eq in self.equity_curve:
                writer.writerow([
                    eq.date, f"{eq.total_value:.0f}", f"{eq.cash:.0f}",
                    f"{eq.positions_value:.0f}",
                    f"{eq.daily_return:.6f}", f"{eq.drawdown:.6f}",
                ])
        print(f"Equity curve exported: {path} ({len(self.equity_curve)} rows)")
