"""
백테스트 리포트 생성기.

콘솔 요약, CSV 내보내기, Matplotlib 차트 생성을 담당한다.
"""

from __future__ import annotations

import csv
import os
from typing import Dict, Optional

from backtest.metrics import ExtendedMetrics, PhaseStats
from backtest.scenarios import BacktestScenario
from infra.logger import get_logger

logger = get_logger("backtest.reporter")


class ReportGenerator:
    """백테스트 결과 리포트 생성."""

    def __init__(
        self,
        result: ExtendedMetrics,
        scenario: BacktestScenario,
        market: str,
        currency_symbol: str = "$",
        output_dir: str = "output/backtest",
    ):
        self.result = result
        self.scenario = scenario
        self.market = market
        self.currency_symbol = currency_symbol
        self.output_dir = output_dir

    # ══════════════════════════════════════════
    # 콘솔 요약
    # ══════════════════════════════════════════

    def print_summary(self):
        """콘솔에 종합 결과를 출력한다."""
        r = self.result
        sym = self.currency_symbol

        print(f"\n{'═'*60}")
        print(f"  ATS HISTORICAL BACKTEST RESULT")
        print(f"{'═'*60}")
        print(f"  시나리오  : {self.scenario.name}")
        print(f"  마켓      : {self.market.upper()}")
        print(f"  기간      : {_fmt(self.scenario.start_date)} ~ {_fmt(self.scenario.end_date)}")
        print(f"  초기자본  : {sym}{r.final_value / (1 + r.total_return):,.0f}" if r.total_return != -1 else "")
        print(f"  최종자산  : {sym}{r.final_value:,.0f}")
        print(f"{'═'*60}")

        # 수익성
        print(f"\n  {'수익성':<20}{'리스크':<20}")
        print(f"  {'─'*18}  {'─'*18}")
        print(f"  총수익률  : {r.total_return:>+8.2%}    MDD      : {r.max_drawdown:>+8.2%}")
        print(f"  CAGR     : {r.cagr:>+8.2%}    MDD 기간  : {r.max_drawdown_duration_days:>6}일")
        print(f"  Sharpe   : {r.sharpe_ratio:>8.2f}    Calmar   : {r.calmar_ratio:>8.2f}")
        print(f"  Sortino  : {r.sortino_ratio:>8.2f}")

        # 매매
        print(f"\n  {'매매':<20}{'체제 (Regime)':<20}")
        print(f"  {'─'*18}  {'─'*18}")
        print(f"  거래 수   : {r.total_trades:>8d}    BULL  : {r.time_in_bull_pct:>6.1f}%")
        print(f"  승률     : {r.win_rate:>7.1%}    BEAR  : {r.time_in_bear_pct:>6.1f}%")
        print(f"  PF       : {r.profit_factor:>8.2f}    중립  : {r.time_in_neutral_pct:>6.1f}%")
        print(f"  평균보유  : {r.avg_holding_days:>6.1f}일    전환  : {len(r.regime_transitions):>4}회")
        print(f"  평균승  % : {r.avg_win_pct:>+7.2%}")
        print(f"  평균패  % : {r.avg_loss_pct:>+7.2%}")
        print(f"  최고거래  : {r.best_trade_pct:>+7.2%}")
        print(f"  최악거래  : {r.worst_trade_pct:>+7.2%}")
        print(f"  최대연승  : {r.max_consecutive_wins:>8d}")
        print(f"  최대연패  : {r.max_consecutive_losses:>8d}")

        # Phase Funnel
        ps = r.phase_stats
        print(f"\n  Phase Funnel")
        print(f"  {'─'*40}")
        total = ps.total_scans or 1
        print(f"  총 스캔        : {ps.total_scans:>8,d}")
        print(f"  Phase 0 BEAR   : {ps.phase0_bear_blocks:>8,d} ({ps.phase0_bear_blocks/max(total+ps.phase0_bear_blocks,1)*100:>5.1f}%)")
        print(f"  Phase 1 추세   : {ps.phase1_trend_rejects:>8,d} ({ps.phase1_trend_rejects/total*100:>5.1f}%)")
        print(f"  Phase 2 위치   : {ps.phase2_late_rejects:>8,d} ({ps.phase2_late_rejects/total*100:>5.1f}%)")
        print(f"  Phase 3 시그널  : {ps.phase3_no_primary + ps.phase3_no_confirm:>8,d} ({(ps.phase3_no_primary+ps.phase3_no_confirm)/total*100:>5.1f}%)")
        print(f"  Phase 4 리스크  : {ps.phase4_risk_blocks:>8,d}")
        print(f"  진입 실행      : {ps.entries_executed:>8,d}")

        # 거래비용
        if ps.total_commission_paid > 0:
            print(f"\n  거래비용")
            print(f"  {'─'*40}")
            print(f"  총 수수료    : {sym}{ps.total_commission_paid:>12,.0f}")
            cost_pct = ps.total_commission_paid / (r.final_value / (1 + r.total_return)) * 100 if r.total_return != -1 else 0
            print(f"  비용 비율    : {cost_pct:>11.3f}%")

        # 청산 분류
        if ps.total_exits > 0:
            print(f"\n  청산 분류 (총 {ps.total_exits}건)")
            print(f"  {'─'*40}")
            print(f"  ES1 손절     : {ps.es1_stop_loss:>5d}")
            print(f"  ES2 익절     : {ps.es2_take_profit:>5d}")
            print(f"  ES3 트레일링  : {ps.es3_trailing_stop:>5d}")
            print(f"  ES4 데드크로스 : {ps.es4_dead_cross:>5d}")
            print(f"  ES5 보유기간  : {ps.es5_max_holding:>5d}")
            print(f"  ES6 횡보청산  : {ps.es6_time_decay:>5d}")
            if ps.es7_rebalance_exit > 0:
                print(f"  ES7 리밸런스  : {ps.es7_rebalance_exit:>5d}")

        # Regime 전환 이력
        if r.regime_transitions:
            print(f"\n  체제 전환 이력")
            print(f"  {'─'*40}")
            for rt in r.regime_transitions[:20]:  # 최대 20건
                print(f"  {_fmt(rt.date)}  {rt.from_regime:>7} → {rt.to_regime}")

        # 위기 분석
        if r.crisis_analysis and r.crisis_analysis.crash_onset_date:
            ca = r.crisis_analysis
            print(f"\n  위기 행동 분석")
            print(f"  {'─'*40}")
            print(f"  하락 진입    : {_fmt(ca.crash_onset_date)}")
            print(f"  포지션 보유  : {ca.positions_at_crash}개")
            print(f"  피크 공포    : {_fmt(ca.peak_fear_date)}")
            print(f"  MDD         : {ca.max_drawdown_pct:>+.2f}%")
            if ca.recovery_date:
                print(f"  회복 시점    : {_fmt(ca.recovery_date)}")

        # Alpha Decay
        if r.rolling_sharpe_6m:
            print(f"\n  Alpha Decay 분석")
            print(f"  {'─'*40}")
            decay_trend = "감소 ↓" if r.alpha_decay_rate < -0.05 else "안정 →" if abs(r.alpha_decay_rate) <= 0.05 else "증가 ↑"
            print(f"  기울기 (월당) : {r.alpha_decay_rate:>+8.4f} ({decay_trend})")
            sorted_months = sorted(r.rolling_sharpe_6m.keys())
            if len(sorted_months) >= 2:
                print(f"  최초 Sharpe6M : {r.rolling_sharpe_6m[sorted_months[0]]:>8.2f} ({sorted_months[0]})")
                print(f"  최종 Sharpe6M : {r.rolling_sharpe_6m[sorted_months[-1]]:>8.2f} ({sorted_months[-1]})")

        # Benchmark Comparison (P1)
        if r.benchmark_return != 0.0 or r.alpha != 0.0:
            print(f"\n  벤치마크 비교 (vs Index)")
            print(f"  {'─'*40}")
            print(f"  벤치 수익률 : {r.benchmark_return:>+8.2%}    Alpha   : {r.alpha:>+8.2%}")
            print(f"  벤치 CAGR  : {r.benchmark_cagr:>+8.2%}    Beta    : {r.beta:>8.2f}")
            print(f"  초과 수익률 : {r.excess_return:>+8.2%}    IR      : {r.information_ratio:>8.2f}")
            print(f"  TE         : {r.tracking_error:>8.2%}    Up Cap  : {r.up_capture_ratio:>7.1f}%")
            print(f"  {'':>30}    Dn Cap  : {r.down_capture_ratio:>7.1f}%")

        # Survivorship Bias
        if r.survivorship_score < 1.0 or r.survivorship_warning:
            print(f"\n  Survivorship Bias")
            print(f"  {'─'*40}")
            score_icon = "✓" if r.survivorship_score >= 0.8 else "⚠" if r.survivorship_score >= 0.5 else "✗"
            print(f"  점수         : {score_icon} {r.survivorship_score:.2f} / 1.00")
            if r.survivorship_warning:
                print(f"  경고         : {r.survivorship_warning}")

        # Rebalancing 통계
        if r.total_rebalances > 0:
            print(f"\n  리밸런싱 통계")
            print(f"  {'─'*40}")
            print(f"  총 리밸런스  : {r.total_rebalances:>8d}회")
            print(f"  평균 턴오버  : {r.avg_turnover_pct:>7.1f}%")

        # 최근 매매
        if r.trades:
            n = min(10, len(r.trades))
            print(f"\n  최근 매매 (마지막 {n}건)")
            print(f"  {'─'*60}")
            print(f"  {'종목':<10} {'진입일':>10} {'청산일':>10} {'P&L%':>8} {'사유':<16}")
            for t in r.trades[-n:]:
                print(
                    f"  {t.stock_code:<10} {t.entry_date:>10} {t.exit_date:>10} "
                    f"{t.pnl_pct:>+7.2%} {t.exit_reason:<16}"
                )

        print(f"\n{'═'*60}\n")

    # ══════════════════════════════════════════
    # CSV 내보내기
    # ══════════════════════════════════════════

    def export_csv(self):
        """매매, 에쿼티, 월별 수익률 CSV를 내보낸다."""
        os.makedirs(self.output_dir, exist_ok=True)
        prefix = f"{self.market}_{self.scenario.id}"

        # trades.csv
        trades_path = os.path.join(self.output_dir, f"{prefix}_trades.csv")
        with open(trades_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "stock_code", "stock_name", "entry_date", "entry_price",
                "exit_date", "exit_price", "quantity", "pnl", "pnl_pct",
                "exit_reason", "holding_days",
            ])
            for t in self.result.trades:
                writer.writerow([
                    t.stock_code, t.stock_name, t.entry_date, t.entry_price,
                    t.exit_date, t.exit_price, t.quantity, t.pnl, f"{t.pnl_pct:.4f}",
                    t.exit_reason, t.holding_days,
                ])
        print(f"  Trades CSV: {trades_path} ({len(self.result.trades)} rows)")

        # equity.csv
        equity_path = os.path.join(self.output_dir, f"{prefix}_equity.csv")
        with open(equity_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["date", "total_value", "cash", "positions_value", "daily_return", "drawdown"])
            for eq in self.result.equity_curve:
                writer.writerow([
                    eq.date, f"{eq.total_value:.0f}", f"{eq.cash:.0f}",
                    f"{eq.positions_value:.0f}",
                    f"{eq.daily_return:.6f}", f"{eq.drawdown:.6f}",
                ])
        print(f"  Equity CSV: {equity_path} ({len(self.result.equity_curve)} rows)")

        # monthly.csv
        if self.result.monthly_returns:
            monthly_path = os.path.join(self.output_dir, f"{prefix}_monthly.csv")
            with open(monthly_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["month", "return"])
                for month, ret in sorted(self.result.monthly_returns.items()):
                    writer.writerow([month, f"{ret:.6f}"])
            print(f"  Monthly CSV: {monthly_path} ({len(self.result.monthly_returns)} rows)")

    # ══════════════════════════════════════════
    # Matplotlib 차트
    # ══════════════════════════════════════════

    def plot_charts(self):
        """Matplotlib 차트 5종을 생성한다."""
        try:
            import matplotlib
            matplotlib.use("Agg")  # 비대화형 백엔드
            import matplotlib.pyplot as plt
            import matplotlib.dates as mdates
            from datetime import datetime
        except ImportError:
            print("  ⚠ matplotlib 미설치. 차트 생성 스킵.")
            return

        os.makedirs(self.output_dir, exist_ok=True)
        prefix = f"{self.market}_{self.scenario.id}"

        # 1. 자산곡선 + 드로다운
        self._plot_equity_curve(plt, mdates, datetime, prefix)

        # 2. 월별 수익률 히트맵
        self._plot_monthly_heatmap(plt, prefix)

        # 3. Phase Funnel
        self._plot_phase_funnel(plt, prefix)

        # 4. 거래 PnL 분포
        self._plot_trade_distribution(plt, prefix)

        # 5. Rolling Sharpe (Alpha Decay)
        self._plot_rolling_sharpe(plt, prefix)

        print(f"  차트 저장 완료: {self.output_dir}/")

    def _plot_equity_curve(self, plt, mdates, datetime, prefix: str):
        """자산곡선 + 드로다운 차트."""
        if not self.result.equity_curve:
            return

        dates = []
        values = []
        drawdowns = []
        peak = 0

        for eq in self.result.equity_curve:
            try:
                d = datetime.strptime(eq.date, "%Y%m%d")
            except ValueError:
                d = datetime.strptime(eq.date, "%Y-%m-%d")
            dates.append(d)
            values.append(eq.total_value)
            if eq.total_value > peak:
                peak = eq.total_value
            dd = (eq.total_value - peak) / peak * 100 if peak > 0 else 0
            drawdowns.append(dd)

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), height_ratios=[3, 1], sharex=True)
        fig.suptitle(f"Equity Curve — {self.scenario.name} ({self.market.upper()})", fontsize=14)

        # 상단: 에쿼티
        ax1.plot(dates, values, color="#2563eb", linewidth=1.2)
        ax1.axhline(y=values[0], color="gray", linestyle="--", alpha=0.5, label="Initial Capital")
        ax1.set_ylabel(f"Equity ({self.currency_symbol})")
        ax1.legend()
        ax1.grid(True, alpha=0.3)

        # Regime 색상 밴드
        for rt in self.result.regime_transitions:
            try:
                rt_date = datetime.strptime(rt.date, "%Y%m%d")
            except ValueError:
                rt_date = datetime.strptime(rt.date, "%Y-%m-%d")
            color = {"BEAR": "#fee2e2", "BULL": "#dcfce7", "NEUTRAL": "#fef9c3"}.get(rt.to_regime, "white")
            ax1.axvline(x=rt_date, color="gray", linestyle=":", alpha=0.5)

        # 하단: 드로다운
        ax2.fill_between(dates, drawdowns, 0, color="#ef4444", alpha=0.3)
        ax2.plot(dates, drawdowns, color="#ef4444", linewidth=0.8)
        ax2.set_ylabel("Drawdown (%)")
        ax2.set_xlabel("Date")
        ax2.grid(True, alpha=0.3)

        ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        ax2.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
        plt.xticks(rotation=45)

        plt.tight_layout()
        path = os.path.join(self.output_dir, f"{prefix}_equity.png")
        plt.savefig(path, dpi=150)
        plt.close()

    def _plot_monthly_heatmap(self, plt, prefix: str):
        """월별 수익률 히트맵."""
        if not self.result.monthly_returns:
            return

        # 데이터 정리
        months_data = {}
        for key, val in self.result.monthly_returns.items():
            year, month = key.split("-")
            if year not in months_data:
                months_data[year] = {}
            months_data[year][int(month)] = val * 100  # %

        years = sorted(months_data.keys())
        if not years:
            return

        import numpy as np
        grid = np.full((12, len(years)), np.nan)
        for j, year in enumerate(years):
            for month, val in months_data[year].items():
                grid[month - 1, j] = val

        fig, ax = plt.subplots(figsize=(max(8, len(years) * 1.5), 6))
        im = ax.imshow(grid, cmap="RdYlGn", aspect="auto", vmin=-10, vmax=10)
        ax.set_xticks(range(len(years)))
        ax.set_xticklabels(years)
        ax.set_yticks(range(12))
        ax.set_yticklabels(["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                            "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])
        ax.set_title(f"Monthly Returns (%) — {self.scenario.name}")
        plt.colorbar(im, label="Return %")

        # 셀 텍스트
        for i in range(12):
            for j in range(len(years)):
                val = grid[i, j]
                if not np.isnan(val):
                    color = "white" if abs(val) > 5 else "black"
                    ax.text(j, i, f"{val:.1f}", ha="center", va="center", color=color, fontsize=8)

        plt.tight_layout()
        path = os.path.join(self.output_dir, f"{prefix}_monthly.png")
        plt.savefig(path, dpi=150)
        plt.close()

    def _plot_phase_funnel(self, plt, prefix: str):
        """Phase Funnel 수평 바 차트."""
        ps = self.result.phase_stats
        labels = ["Phase 0\nBEAR", "Phase 1\n추세", "Phase 2\n위치",
                  "Phase 3\n시그널", "Phase 4\n리스크", "진입\n실행"]
        values = [
            ps.phase0_bear_blocks,
            ps.phase1_trend_rejects,
            ps.phase2_late_rejects,
            ps.phase3_no_primary + ps.phase3_no_confirm,
            ps.phase4_risk_blocks,
            ps.entries_executed,
        ]
        colors = ["#ef4444", "#f97316", "#eab308", "#3b82f6", "#8b5cf6", "#22c55e"]

        fig, ax = plt.subplots(figsize=(10, 5))
        bars = ax.barh(labels, values, color=colors)
        ax.set_xlabel("Count")
        ax.set_title(f"Phase Funnel — {self.scenario.name}")

        for bar, val in zip(bars, values):
            if val > 0:
                ax.text(bar.get_width() + max(values) * 0.02, bar.get_y() + bar.get_height() / 2,
                        f"{val:,}", va="center", fontsize=9)

        ax.invert_yaxis()
        plt.tight_layout()
        path = os.path.join(self.output_dir, f"{prefix}_funnel.png")
        plt.savefig(path, dpi=150)
        plt.close()

    def _plot_trade_distribution(self, plt, prefix: str):
        """거래 PnL 분포 히스토그램."""
        if not self.result.trades:
            return

        pnls = [t.pnl_pct * 100 for t in self.result.trades]

        fig, ax = plt.subplots(figsize=(10, 5))
        ax.hist(pnls, bins=30, color="#3b82f6", alpha=0.7, edgecolor="white")
        ax.axvline(x=0, color="black", linestyle="--", alpha=0.5)
        ax.axvline(x=-3, color="red", linestyle="--", alpha=0.5, label="Stop Loss -3%")
        ax.axvline(x=7, color="green", linestyle="--", alpha=0.5, label="Take Profit +7%")
        ax.set_xlabel("P&L (%)")
        ax.set_ylabel("Count")
        ax.set_title(f"Trade P&L Distribution — {self.scenario.name}")
        ax.legend()

        plt.tight_layout()
        path = os.path.join(self.output_dir, f"{prefix}_distribution.png")
        plt.savefig(path, dpi=150)
        plt.close()

    def _plot_rolling_sharpe(self, plt, prefix: str):
        """Rolling 6M Sharpe 차트 (Alpha Decay 시각화)."""
        if not self.result.rolling_sharpe_6m:
            return

        sorted_months = sorted(self.result.rolling_sharpe_6m.keys())
        values = [self.result.rolling_sharpe_6m[m] for m in sorted_months]

        fig, ax = plt.subplots(figsize=(12, 5))
        ax.plot(range(len(sorted_months)), values, color="#2563eb", linewidth=1.5, marker="o", markersize=3)
        ax.axhline(y=0, color="gray", linestyle="--", alpha=0.5)

        # 추세선
        if len(sorted_months) >= 3:
            n = len(sorted_months)
            x_vals = list(range(n))
            slope = self.result.alpha_decay_rate
            intercept = sum(values) / n - slope * sum(x_vals) / n
            trend_y = [slope * x + intercept for x in x_vals]
            trend_color = "#ef4444" if slope < -0.05 else "#22c55e" if slope > 0.05 else "#6b7280"
            ax.plot(x_vals, trend_y, color=trend_color, linestyle="--", linewidth=1.5,
                    label=f"Trend (slope={slope:+.4f}/mo)")

        # X축 라벨
        tick_interval = max(1, len(sorted_months) // 12)
        ax.set_xticks(range(0, len(sorted_months), tick_interval))
        ax.set_xticklabels([sorted_months[i] for i in range(0, len(sorted_months), tick_interval)], rotation=45)

        ax.set_ylabel("Rolling 6M Sharpe Ratio")
        ax.set_title(f"Alpha Decay — Rolling 6M Sharpe — {self.scenario.name}")
        ax.legend()
        ax.grid(True, alpha=0.3)

        plt.tight_layout()
        path = os.path.join(self.output_dir, f"{prefix}_rolling_sharpe.png")
        plt.savefig(path, dpi=150)
        plt.close()

    # ══════════════════════════════════════════
    # 시나리오 비교
    # ══════════════════════════════════════════

    @staticmethod
    def compare_scenarios(results: Dict[str, ExtendedMetrics], market: str):
        """여러 시나리오 결과를 비교 테이블로 출력한다."""
        if not results:
            print("  No results to compare.")
            return

        print(f"\n{'═'*90}")
        print(f"  SCENARIO COMPARISON — {market.upper()}")
        print(f"{'═'*90}")

        header = f"  {'Scenario':<25} {'Return':>8} {'CAGR':>8} {'MDD':>8} {'Sharpe':>7} {'Win%':>6} {'Trades':>7} {'BEAR%':>6}"
        print(header)
        print(f"  {'─'*86}")

        for scenario_id, r in results.items():
            name = scenario_id[:24]
            print(
                f"  {name:<25} {r.total_return:>+7.1%} {r.cagr:>+7.1%} "
                f"{r.max_drawdown:>+7.1%} {r.sharpe_ratio:>7.2f} "
                f"{r.win_rate:>5.0%} {r.total_trades:>7d} "
                f"{r.time_in_bear_pct:>5.1f}%"
            )

        print(f"{'═'*90}\n")


def _fmt(date_str: str) -> str:
    """YYYYMMDD → YYYY-MM-DD."""
    if len(date_str) == 8:
        return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
    return date_str
