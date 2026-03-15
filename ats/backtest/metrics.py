"""
백테스트 메트릭 수집기.

SimulationEngine의 일별 상태를 수집하고
확장 메트릭(Sortino, Calmar, Phase Funnel, Regime Timeline 등)을 계산한다.

기존 result.py의 BacktestResult/TradeRecord/DailyEquity를 재사용한다.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from backtest.result import BacktestResult, DailyEquity, TradeRecord

if TYPE_CHECKING:
    from simulation.engine import SimulationEngine
    from backtest.scenarios import BacktestScenario


@dataclass
class PhaseStats:
    """Phase별 파이프라인 통계."""

    total_scans: int = 0
    phase0_bear_blocks: int = 0
    phase1_trend_rejects: int = 0
    phase2_late_rejects: int = 0
    phase3_no_primary: int = 0
    phase3_no_confirm: int = 0
    phase3_ps3_pullback: int = 0   # PS3 MA풀백 시그널 발생 횟수
    phase4_risk_blocks: int = 0
    divergence_blocks: int = 0
    entries_executed: int = 0

    # 레짐 품질 게이트
    regime_quality_blocks: int = 0

    # 지수 추세 기반 전략 선택
    index_trend_updates: int = 0

    # 청산 이유별
    es0_emergency_stop: int = 0   # 비상 손절 -10%
    es1_stop_loss: int = 0
    es2_take_profit: int = 0
    es3_trailing_stop: int = 0
    es4_dead_cross: int = 0
    es5_max_holding: int = 0
    es6_time_decay: int = 0
    es7_rebalance_exit: int = 0
    total_commission_paid: float = 0.0

    # SMC 전용
    es_smc_sl: int = 0        # ATR 기반 스탑 로스
    es_smc_tp: int = 0        # ATR 기반 테이크 프로핏
    es_choch_exit: int = 0    # CHoCH 반전 청산
    smc_total_score: int = 0  # 누적 진입 스코어 합계
    smc_entries: int = 0      # SMC 진입 횟수

    # Breakout-Retest 전용
    brt_breakouts_detected: int = 0   # 돌파 감지 횟수
    brt_fakeout_blocked: int = 0      # 페이크아웃 차단 횟수
    brt_retests_entered: int = 0      # 리테스트 진입 횟수
    brt_retests_expired: int = 0      # 리테스트 만료 횟수
    es_brt_sl: int = 0                # ATR×1.5 손절
    es_brt_tp: int = 0                # ATR×3.0 익절
    es_zone_break: int = 0            # 존 무효화 청산

    # Mean Reversion 전용
    mr_entries: int = 0               # MR 진입 횟수
    mr_total_score: int = 0           # 누적 MR 스코어 합계
    es_mr_sl: int = 0                 # MR ATR 손절
    es_mr_tp: int = 0                 # MR TP (MA20/RSI)
    es_mr_bb: int = 0                 # MR BB Mid 청산
    es_mr_ob: int = 0                 # MR Overbought 청산

    # Arbitrage 전용
    arb_pairs_scanned: int = 0        # 스캔한 페어 수
    arb_spreads_detected: int = 0     # Z-Score 이탈 감지 횟수
    arb_correlation_rejects: int = 0  # 상관관계 필터 탈락 횟수
    arb_entries: int = 0              # Long 진입 횟수
    arb_short_entries: int = 0        # Short 진입 횟수
    arb_total_score: int = 0          # 누적 ARB 스코어 합계
    es_arb_sl: int = 0                # ARB ATR 손절
    es_arb_tp: int = 0                # ARB Z-Score 정상화 익절
    es_arb_corr: int = 0             # ARB 상관관계 붕괴 청산
    # v5: Basis Gate + Fixed Pair stats
    arb_basis_gate_blocks: int = 0   # Basis 게이트 차단 횟수
    arb_basis_window_opens: int = 0  # Basis 윈도우 OPEN 횟수
    arb_fixed_pairs_loaded: int = 0  # 고정 페어 로드 횟수

    # Multi-Strategy 전용
    multi_dedup_skips: int = 0        # 종목 중복으로 스킵한 시그널 수

    # Defensive 전략 전용
    defensive_entries: int = 0         # 인버스 ETF 진입 횟수
    defensive_regime_exits: int = 0    # 레짐 전환 청산 횟수

    # 레짐별 전략 모듈화 카운터
    phase3_ps4_donchian: int = 0       # STRONG_BULL Donchian 돌파 진입
    es_neutral_time_decay: int = 0     # NEUTRAL 시간감쇄 강제 청산
    es_range_box_breakout: int = 0     # RANGE_BOUND 박스 이탈 청산
    es_disp_partial_sell: int = 0      # BULL 이격도 부분 청산
    regime_pyramid_entries: int = 0    # STRONG_BULL 피라미딩 횟수
    regime_sizing_reductions: int = 0  # 레짐별 사이징 감축 횟수

    # MDD Guard (P0)
    es_mdd_guard: int = 0             # DD>15% 비방어 포지션 강제 청산 횟수

    # 종목별 레짐 분류
    stock_regime_distribution: Dict[str, int] = field(default_factory=dict)
    stock_regime_strategy_map: Dict[str, int] = field(default_factory=dict)

    # B7: 종목별 레짐 성과 추적
    stock_regime_win_rate: Dict[str, float] = field(default_factory=dict)
    stock_regime_avg_pnl: Dict[str, float] = field(default_factory=dict)
    stock_regime_entry_count: Dict[str, int] = field(default_factory=dict)

    @property
    def smc_avg_score(self) -> float:
        """SMC 평균 진입 스코어."""
        return self.smc_total_score / self.smc_entries if self.smc_entries > 0 else 0.0

    @property
    def total_exits(self) -> int:
        return (
            self.es1_stop_loss + self.es2_take_profit + self.es3_trailing_stop
            + self.es4_dead_cross + self.es5_max_holding + self.es6_time_decay
            + self.es7_rebalance_exit + self.es_smc_sl + self.es_smc_tp
            + self.es_choch_exit + self.es_brt_sl + self.es_brt_tp
            + self.es_zone_break + self.es_mr_sl + self.es_mr_tp
            + self.es_mr_bb + self.es_mr_ob
            + self.es_arb_sl + self.es_arb_tp + self.es_arb_corr
        )


@dataclass
class RegimeTransition:
    """시장 체제 전환 기록."""

    date: str
    from_regime: str
    to_regime: str


@dataclass
class CrisisAnalysis:
    """위기 시기 행동 분석."""

    crash_onset_date: str = ""        # BEAR 최초 전환일
    peak_fear_date: str = ""          # MDD 최저점 날짜
    recovery_date: str = ""           # BEAR→BULL 복귀일
    max_drawdown_pct: float = 0.0
    total_trades: int = 0
    positions_at_crash: int = 0       # 폭락 시작 시 보유 포지션 수
    days_without_entry: int = 0       # BEAR 기간 중 미매수 일수


@dataclass
class ExtendedMetrics:
    """확장 백테스트 메트릭 (기본 BacktestResult + 추가 분석)."""

    # 기본 (BacktestResult에서 복사)
    total_return: float = 0.0
    cagr: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_date: str = ""
    total_trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    avg_pnl_pct: float = 0.0
    avg_holding_days: float = 0.0
    final_value: float = 0.0

    # 확장
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    max_drawdown_duration_days: int = 0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    avg_win_pct: float = 0.0
    avg_loss_pct: float = 0.0
    best_trade_pct: float = 0.0
    worst_trade_pct: float = 0.0

    # 월별 수익률
    monthly_returns: Dict[str, float] = field(default_factory=dict)

    # Alpha Decay
    rolling_sharpe_6m: Dict[str, float] = field(default_factory=dict)
    alpha_decay_rate: float = 0.0  # 롤링 Sharpe 기울기; 음수 = 알파 감소

    # Survivorship Bias
    survivorship_score: float = 1.0  # 0~1, 1.0 = bias 없음
    survivorship_warning: str = ""
    survivorship_details: Dict[str, Any] = field(default_factory=dict)

    # Rebalancing
    total_rebalances: int = 0
    avg_turnover_pct: float = 0.0

    # Phase 통계
    phase_stats: PhaseStats = field(default_factory=PhaseStats)

    # Regime
    regime_transitions: List[RegimeTransition] = field(default_factory=list)
    time_in_bull_pct: float = 0.0
    time_in_bear_pct: float = 0.0
    time_in_neutral_pct: float = 0.0

    # 위기 분석
    crisis_analysis: Optional[CrisisAnalysis] = None

    # Phase 7: Monte Carlo Stress Test
    mc_var_95: float = 0.0          # 95% Value at Risk (annual)
    mc_cvar_99: float = 0.0         # 99% Conditional VaR (annual)
    mc_worst_mdd: float = 0.0       # Worst MDD across simulations
    mc_median_return: float = 0.0   # Median return across simulations
    mc_bankruptcy_prob: float = 0.0 # P(equity < 50% of peak)

    # Benchmark comparison (P1)
    benchmark_return: float = 0.0       # SPY/index total return over same period
    benchmark_cagr: float = 0.0
    alpha: float = 0.0                  # Jensen's alpha (annualized)
    beta: float = 0.0                   # Portfolio beta vs benchmark
    information_ratio: float = 0.0     # Excess return / tracking error
    tracking_error: float = 0.0        # Annualized std of excess returns
    excess_return: float = 0.0         # Portfolio return - Benchmark return
    up_capture_ratio: float = 0.0      # Performance in up-benchmark markets
    down_capture_ratio: float = 0.0    # Performance in down-benchmark markets

    # 원본 데이터 (차트용)
    equity_curve: List[DailyEquity] = field(default_factory=list)
    trades: List[TradeRecord] = field(default_factory=list)


class MetricsCollector:
    """
    백테스트 진행 중 일별 데이터를 수집하고 최종 메트릭을 계산한다.

    사용법:
        collector = MetricsCollector(initial_capital, scenario)
        for date in trading_dates:
            engine.run_backtest_day(...)
            collector.record_daily(date, engine)
        result = collector.calculate_all(engine)
    """

    def __init__(self, initial_capital: float, scenario: BacktestScenario, benchmark_daily_returns: Optional[Dict[str, float]] = None):
        self.initial_capital = initial_capital
        self.scenario = scenario
        self._benchmark_returns: Dict[str, float] = benchmark_daily_returns or {}

        # 일별 데이터
        self._equity_data: List[DailyEquity] = []
        self._prev_equity: float = initial_capital

        # Regime 추적
        self._regime_transitions: List[RegimeTransition] = []
        self._regime_days: Dict[str, int] = {"BULL": 0, "BEAR": 0, "NEUTRAL": 0}
        self._prev_regime: str = "NEUTRAL"

        # MDD Duration 추적
        self._peak_equity: float = initial_capital
        self._underwater_start: Optional[str] = None
        self._max_underwater_days: int = 0
        self._current_underwater_days: int = 0

        # 위기 분석
        self._crisis = CrisisAnalysis()
        self._first_bear_date: Optional[str] = None
        self._bear_entry_count: int = 0

    def record_daily(self, date: str, engine: SimulationEngine):
        """매 거래일 종료 후 호출. 에쿼티, 체제, 포지션 기록."""
        equity = engine._get_total_equity()
        cash = engine.cash
        invested = equity - cash
        daily_return = (equity - self._prev_equity) / self._prev_equity if self._prev_equity > 0 else 0.0

        self._equity_data.append(DailyEquity(
            date=date,
            total_value=equity,
            cash=cash,
            positions_value=invested,
            daily_return=daily_return,
            drawdown=0.0,  # calculate_all에서 계산
        ))
        self._prev_equity = equity

        # MDD Duration 추적
        if equity >= self._peak_equity:
            self._peak_equity = equity
            if self._current_underwater_days > self._max_underwater_days:
                self._max_underwater_days = self._current_underwater_days
            self._current_underwater_days = 0
            self._underwater_start = None
        else:
            self._current_underwater_days += 1
            if self._underwater_start is None:
                self._underwater_start = date

        # Regime 추적
        regime = engine._market_regime
        self._regime_days[regime] = self._regime_days.get(regime, 0) + 1

        if regime != self._prev_regime:
            self._regime_transitions.append(RegimeTransition(
                date=date,
                from_regime=self._prev_regime,
                to_regime=regime,
            ))
            # 위기 분석: 최초 BEAR 전환
            if regime == "BEAR" and self._first_bear_date is None:
                self._first_bear_date = date
                self._crisis.crash_onset_date = date
                self._crisis.positions_at_crash = len([
                    p for p in engine.positions.values() if p.status == "ACTIVE"
                ])
            # 위기 분석: BEAR → BULL 복귀
            if self._prev_regime == "BEAR" and regime == "BULL":
                self._crisis.recovery_date = date

            self._prev_regime = regime

    def record_regime_transition(self, date: str, from_regime: str, to_regime: str):
        """별도 체제 전환 기록 (record_daily에서도 처리하므로 중복 방지)."""
        pass  # record_daily에서 자동 처리

    def calculate_all(self, engine: SimulationEngine) -> ExtendedMetrics:
        """전체 메트릭 계산. 백테스트 완료 후 호출."""
        # 마지막 underwater 체크
        if self._current_underwater_days > self._max_underwater_days:
            self._max_underwater_days = self._current_underwater_days

        # 1. BacktestResult 기본 메트릭 계산 (재사용)
        trades = self._convert_trades(engine)
        base = BacktestResult(
            start_date=self.scenario.start_date,
            end_date=self.scenario.end_date,
            initial_capital=self.initial_capital,
            trades=trades,
            equity_curve=self._equity_data,
        )
        base.calculate_metrics()

        # 2. 확장 메트릭
        result = ExtendedMetrics(
            # 기본
            total_return=base.total_return,
            cagr=base.cagr,
            sharpe_ratio=base.sharpe_ratio,
            max_drawdown=base.max_drawdown,
            max_drawdown_date=base.max_drawdown_date,
            total_trades=base.total_trades,
            win_rate=base.win_rate,
            profit_factor=base.profit_factor,
            avg_pnl_pct=base.avg_pnl_pct,
            avg_holding_days=base.avg_holding_days,
            final_value=base.final_value,
            equity_curve=self._equity_data,
            trades=trades,
        )

        # 3. Sortino Ratio
        daily_returns = [eq.daily_return for eq in self._equity_data if eq.daily_return != 0.0]
        if daily_returns:
            avg_ret = sum(daily_returns) / len(daily_returns)
            downside = [r for r in daily_returns if r < 0]
            if len(downside) >= 2:
                downside_std = math.sqrt(sum(r ** 2 for r in downside) / len(downside))
                if downside_std > 0:
                    result.sortino_ratio = (avg_ret / downside_std) * math.sqrt(252)

        # 4. Calmar Ratio
        if base.max_drawdown < 0 and base.cagr != 0:
            result.calmar_ratio = base.cagr / abs(base.max_drawdown)

        # 5. MDD Duration
        result.max_drawdown_duration_days = self._max_underwater_days

        # 6. 연승/연패
        wins, losses = 0, 0
        max_wins, max_losses = 0, 0
        for t in trades:
            if t.pnl > 0:
                wins += 1
                losses = 0
                max_wins = max(max_wins, wins)
            else:
                losses += 1
                wins = 0
                max_losses = max(max_losses, losses)
        result.max_consecutive_wins = max_wins
        result.max_consecutive_losses = max_losses

        # 7. 승/패 평균
        win_trades = [t for t in trades if t.pnl > 0]
        loss_trades = [t for t in trades if t.pnl <= 0]
        if win_trades:
            result.avg_win_pct = sum(t.pnl_pct for t in win_trades) / len(win_trades)
        if loss_trades:
            result.avg_loss_pct = sum(t.pnl_pct for t in loss_trades) / len(loss_trades)
        if trades:
            result.best_trade_pct = max(t.pnl_pct for t in trades)
            result.worst_trade_pct = min(t.pnl_pct for t in trades)

        # 8. 월별 수익률
        result.monthly_returns = self._calc_monthly_returns()

        # 9. Phase 통계
        # B7: _stock_regime_pnls는 PhaseStats 필드가 아니므로 분리해서 처리
        _phase_stats_copy = {k: v for k, v in engine._phase_stats.items() if k != "_stock_regime_pnls"}
        result.phase_stats = PhaseStats(**_phase_stats_copy)
        result.phase_stats.total_commission_paid = engine._total_commission_paid

        # B7: 종목별 레짐 성과 집계
        sr_pnls = engine._phase_stats.get("_stock_regime_pnls", {})
        for regime, data in sr_pnls.items():
            count = data.get("count", 0)
            result.phase_stats.stock_regime_entry_count[regime] = count
            if count > 0:
                result.phase_stats.stock_regime_win_rate[regime] = round(data["wins"] / count * 100, 1)
                result.phase_stats.stock_regime_avg_pnl[regime] = round(data["total_pnl"] / count, 2)

        # 10. Regime
        result.regime_transitions = self._regime_transitions
        total_days = sum(self._regime_days.values()) or 1
        result.time_in_bull_pct = self._regime_days.get("BULL", 0) / total_days * 100
        result.time_in_bear_pct = self._regime_days.get("BEAR", 0) / total_days * 100
        result.time_in_neutral_pct = self._regime_days.get("NEUTRAL", 0) / total_days * 100

        # 11. 위기 분석
        self._crisis.max_drawdown_pct = base.max_drawdown * 100
        self._crisis.peak_fear_date = base.max_drawdown_date
        self._crisis.total_trades = base.total_trades
        result.crisis_analysis = self._crisis

        # 12. Alpha Decay (Rolling 6M Sharpe)
        result.rolling_sharpe_6m = self._calc_rolling_sharpe(window_months=6)
        result.alpha_decay_rate = self._calc_alpha_decay_rate(result.rolling_sharpe_6m)

        # 13. Phase 7: Monte Carlo Stress Test
        mc = self._run_monte_carlo(daily_returns, n_simulations=1000, n_days=252)
        if mc:
            result.mc_var_95 = mc["var_95"]
            result.mc_cvar_99 = mc["cvar_99"]
            result.mc_worst_mdd = mc["worst_mdd"]
            result.mc_median_return = mc["median_return"]
            result.mc_bankruptcy_prob = mc["bankruptcy_prob"]

        # 14. Benchmark comparison (P1)
        if self._benchmark_returns:
            self._calc_benchmark_metrics(result, daily_returns)

        return result

    def _run_monte_carlo(
        self,
        daily_returns: List[float],
        n_simulations: int = 1000,
        n_days: int = 252,
    ) -> Optional[Dict[str, float]]:
        """Monte Carlo 부트스트랩 시뮬레이션.

        실제 일일 수익률에서 무작위 복원 추출하여 N개 경로 생성.
        VaR, CVaR, worst MDD, 파산 확률 계산.
        """
        if len(daily_returns) < 20:
            return None

        random.seed(42)
        final_returns: List[float] = []
        max_drawdowns: List[float] = []
        bankruptcy_count = 0

        for _ in range(n_simulations):
            # 복원추출로 n_days일 경로 생성
            path_returns = random.choices(daily_returns, k=n_days)
            equity = 1.0
            peak = 1.0
            worst_dd = 0.0

            for r in path_returns:
                equity *= (1 + r)
                if equity > peak:
                    peak = equity
                dd = (equity - peak) / peak if peak > 0 else 0
                if dd < worst_dd:
                    worst_dd = dd

            final_returns.append(equity - 1.0)  # total return
            max_drawdowns.append(worst_dd)
            if equity < 0.5:  # 자본 50% 이하 = 파산
                bankruptcy_count += 1

        # 정렬
        final_returns.sort()
        max_drawdowns.sort()

        n = len(final_returns)
        idx_5 = int(n * 0.05)   # 5th percentile
        idx_1 = int(n * 0.01)   # 1st percentile

        # 95% VaR: 하위 5% 경계
        var_95 = final_returns[idx_5] if idx_5 < n else final_returns[0]
        # 99% CVaR: 하위 1% 평균
        cvar_slice = final_returns[:max(idx_1, 1)]
        cvar_99 = sum(cvar_slice) / len(cvar_slice)
        # Worst MDD
        worst_mdd = min(max_drawdowns)
        # Median return
        median_return = final_returns[n // 2]
        # 파산 확률
        bankruptcy_prob = bankruptcy_count / n_simulations

        return {
            "var_95": round(var_95 * 100, 2),
            "cvar_99": round(cvar_99 * 100, 2),
            "worst_mdd": round(worst_mdd * 100, 2),
            "median_return": round(median_return * 100, 2),
            "bankruptcy_prob": round(bankruptcy_prob * 100, 2),
        }

    def _calc_benchmark_metrics(self, result: ExtendedMetrics, portfolio_daily_returns: List[float]):
        """벤치마크 대비 알파/베타/정보비율 등 계산 (P1).

        포트폴리오 일별 수익률과 벤치마크 일별 수익률을 날짜 기준으로 매칭하여 계산한다.
        """
        if not self._benchmark_returns or not self._equity_data:
            return

        # 날짜별 포트폴리오 수익률 매핑
        port_by_date: Dict[str, float] = {}
        for eq in self._equity_data:
            port_by_date[eq.date] = eq.daily_return

        # 양쪽 모두 존재하는 날짜만 매칭
        common_dates = sorted(set(port_by_date.keys()) & set(self._benchmark_returns.keys()))
        if len(common_dates) < 20:
            return  # 최소 20일 데이터 필요

        port_rets = [port_by_date[d] for d in common_dates]
        bench_rets = [self._benchmark_returns[d] for d in common_dates]
        n = len(common_dates)

        # --- Benchmark total return ---
        bench_cumulative = 1.0
        for r in bench_rets:
            bench_cumulative *= (1 + r)
        result.benchmark_return = bench_cumulative - 1.0

        # --- Benchmark CAGR ---
        years = n / 252.0
        if years > 0 and bench_cumulative > 0:
            result.benchmark_cagr = bench_cumulative ** (1.0 / years) - 1.0

        # --- Excess Return ---
        result.excess_return = result.total_return - result.benchmark_return

        # --- Beta = Cov(port, bench) / Var(bench) ---
        port_mean = sum(port_rets) / n
        bench_mean = sum(bench_rets) / n

        cov_pb = sum((p - port_mean) * (b - bench_mean) for p, b in zip(port_rets, bench_rets)) / n
        var_bench = sum((b - bench_mean) ** 2 for b in bench_rets) / n

        if var_bench > 1e-12:
            result.beta = cov_pb / var_bench
        else:
            result.beta = 0.0

        # --- Alpha (Jensen's) = port_annual - (rf + beta * (bench_annual - rf)) ---
        rf = 0.04  # risk-free rate
        port_annual = result.cagr if result.cagr != 0 else result.total_return
        bench_annual = result.benchmark_cagr if result.benchmark_cagr != 0 else result.benchmark_return
        result.alpha = port_annual - (rf + result.beta * (bench_annual - rf))

        # --- Tracking Error = annualized std of excess returns ---
        excess_daily = [p - b for p, b in zip(port_rets, bench_rets)]
        excess_mean = sum(excess_daily) / n
        excess_var = sum((e - excess_mean) ** 2 for e in excess_daily) / n
        result.tracking_error = math.sqrt(excess_var) * math.sqrt(252) if excess_var > 0 else 0.0

        # --- Information Ratio = (port_annual - bench_annual) / tracking_error ---
        if result.tracking_error > 1e-8:
            result.information_ratio = (port_annual - bench_annual) / result.tracking_error
        else:
            result.information_ratio = 0.0

        # --- Up/Down Capture ---
        up_port = [p for p, b in zip(port_rets, bench_rets) if b > 0]
        up_bench = [b for b in bench_rets if b > 0]
        down_port = [p for p, b in zip(port_rets, bench_rets) if b < 0]
        down_bench = [b for b in bench_rets if b < 0]

        if up_bench:
            avg_up_port = sum(up_port) / len(up_port)
            avg_up_bench = sum(up_bench) / len(up_bench)
            if abs(avg_up_bench) > 1e-12:
                result.up_capture_ratio = (avg_up_port / avg_up_bench) * 100
        if down_bench:
            avg_down_port = sum(down_port) / len(down_port)
            avg_down_bench = sum(down_bench) / len(down_bench)
            if abs(avg_down_bench) > 1e-12:
                result.down_capture_ratio = (avg_down_port / avg_down_bench) * 100

    def _convert_trades(self, engine: SimulationEngine) -> List[TradeRecord]:
        """SimTradeRecord → TradeRecord 변환."""
        trades = []
        for t in engine.closed_trades:
            trades.append(TradeRecord(
                stock_code=t.stock_code,
                stock_name=t.stock_name,
                entry_date=t.entry_date,
                entry_price=t.entry_price,
                exit_date=t.exit_date,
                exit_price=t.exit_price,
                quantity=t.quantity,
                pnl=t.pnl,
                pnl_pct=t.pnl_pct / 100.0,  # SimTradeRecord: percentage → TradeRecord: fraction
                exit_reason=t.exit_reason,
                holding_days=t.holding_days,
                strategy_tag=getattr(t, 'strategy_tag', ''),
                entry_signal_strength=getattr(t, 'entry_signal_strength', 0),
                entry_regime=getattr(t, 'entry_regime', ''),
                entry_trend_strength=getattr(t, 'entry_trend_strength', ''),
            ))
        return trades

    def _calc_monthly_returns(self) -> Dict[str, float]:
        """일별 에쿼티에서 월별 수익률을 계산한다."""
        if not self._equity_data:
            return {}

        monthly: Dict[str, float] = {}
        month_start_value: Optional[float] = None
        current_month = ""

        for eq in self._equity_data:
            # YYYYMMDD → YYYY-MM
            month_key = f"{eq.date[:4]}-{eq.date[4:6]}"
            if month_key != current_month:
                # 이전 달 수익률 마감
                if current_month and month_start_value and month_start_value > 0:
                    prev_eq = self._equity_data[self._equity_data.index(eq) - 1] if self._equity_data.index(eq) > 0 else eq
                    monthly[current_month] = (prev_eq.total_value - month_start_value) / month_start_value
                current_month = month_key
                month_start_value = eq.total_value

        # 마지막 달
        if current_month and month_start_value and month_start_value > 0:
            monthly[current_month] = (self._equity_data[-1].total_value - month_start_value) / month_start_value

        return monthly

    def _calc_rolling_sharpe(self, window_months: int = 6) -> Dict[str, float]:
        """롤링 N개월 Sharpe Ratio를 계산한다.

        Returns:
            Dict[YYYY-MM, sharpe] — 각 월말 기준 직전 N개월 Sharpe.
        """
        if not self._equity_data or window_months < 1:
            return {}

        # 월별로 일일 수익률 그룹핑
        month_daily_returns: Dict[str, List[float]] = {}
        for eq in self._equity_data:
            month_key = f"{eq.date[:4]}-{eq.date[4:6]}"
            if month_key not in month_daily_returns:
                month_daily_returns[month_key] = []
            if eq.daily_return != 0.0:
                month_daily_returns[month_key].append(eq.daily_return)

        sorted_months = sorted(month_daily_returns.keys())
        if len(sorted_months) < window_months:
            return {}

        rolling_sharpe: Dict[str, float] = {}
        for i in range(window_months - 1, len(sorted_months)):
            window_keys = sorted_months[i - window_months + 1: i + 1]
            # window_months 개월치 일일 수익률 합치기
            window_returns: List[float] = []
            for mk in window_keys:
                window_returns.extend(month_daily_returns[mk])

            if len(window_returns) < 20:  # 최소 20일 데이터
                continue

            avg = sum(window_returns) / len(window_returns)
            variance = sum((r - avg) ** 2 for r in window_returns) / len(window_returns)
            std = math.sqrt(variance) if variance > 0 else 0.0
            if std > 0:
                rolling_sharpe[sorted_months[i]] = (avg / std) * math.sqrt(252)
            else:
                rolling_sharpe[sorted_months[i]] = 0.0

        return rolling_sharpe

    def _calc_alpha_decay_rate(self, rolling_sharpe: Dict[str, float]) -> float:
        """롤링 Sharpe의 선형회귀 기울기를 계산한다.

        음수 = 알파 감소 (전략 성능 하락 추세).
        양수 = 알파 증가.
        0.0 = 데이터 부족 또는 안정.

        Returns:
            기울기 (월당 Sharpe 변화량).
        """
        if len(rolling_sharpe) < 3:
            return 0.0

        sorted_months = sorted(rolling_sharpe.keys())
        n = len(sorted_months)
        x_vals = list(range(n))  # 0, 1, 2, ...
        y_vals = [rolling_sharpe[m] for m in sorted_months]

        # 단순 선형회귀: slope = (n*Σxy - Σx*Σy) / (n*Σx² - (Σx)²)
        sum_x = sum(x_vals)
        sum_y = sum(y_vals)
        sum_xy = sum(x * y for x, y in zip(x_vals, y_vals))
        sum_x2 = sum(x * x for x in x_vals)

        denominator = n * sum_x2 - sum_x * sum_x
        if denominator == 0:
            return 0.0

        slope = (n * sum_xy - sum_x * sum_y) / denominator
        return slope
