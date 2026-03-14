"""
백테스트 엔진

기존 프로덕션 컴포넌트(Strategy, RiskManager, PositionManager, OrderExecutor)를
SimulatedBroker + In-memory DB와 조합하여 과거 데이터로 시뮬레이션한다.

datetime.now() 패치로 시뮬레이션 날짜를 프로덕션 코드에 주입하고,
time.sleep 패치로 재시도 대기를 건너뛴다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional
from unittest.mock import patch

import pandas as pd

from backtest.data_loader import get_trading_dates, load_universe
from backtest.null_notifier import NullNotifier
from backtest.result import BacktestResult, DailyEquity, TradeRecord
from backtest.simulated_broker import SimulatedBroker
from common.enums import PositionStatus
from common.types import PriceData
from data.config_manager import ATSConfig, ConfigManager
from infra.db.connection import Database
from infra.db.repository import Repository
from infra.logger import get_logger
from order.order_executor import OrderExecutor
from position.position_manager import PositionManager
from risk.risk_manager import RiskManager
from strategy.momentum_swing import MomentumSwingStrategy

logger = get_logger("backtest.engine")


class BacktestEngine:
    """
    백테스트 메인 오케스트레이터.

    Usage:
        engine = BacktestEngine(config, initial_capital=100_000_000)
        result = engine.run("20240101", "20241231", universe_codes=["005930", "000660"])
    """

    def __init__(
        self,
        config: ATSConfig,
        initial_capital: float = 100_000_000,
        data_dir: str = "data_store/backtest_data",
    ):
        self.config = config
        self.initial_capital = initial_capital
        self.data_dir = data_dir

        # 컴포넌트 (run() 시 초기화)
        self.broker: Optional[SimulatedBroker] = None
        self.database: Optional[Database] = None
        self.repo: Optional[Repository] = None
        self.pos_mgr: Optional[PositionManager] = None
        self.risk_mgr: Optional[RiskManager] = None
        self.order_executor: Optional[OrderExecutor] = None
        self.strategy: Optional[MomentumSwingStrategy] = None
        self.notifier: Optional[NullNotifier] = None

    def run(
        self,
        start_date: str,
        end_date: str,
        universe_codes: Optional[List[str]] = None,
    ) -> BacktestResult:
        """
        백테스트를 실행한다.

        Args:
            start_date: 시작일 (YYYYMMDD 또는 YYYY-MM-DD)
            end_date: 종료일 (YYYYMMDD 또는 YYYY-MM-DD)
            universe_codes: 종목 코드 리스트 (None이면 data_dir의 모든 CSV)
        """
        start_date = start_date.replace("-", "")
        end_date = end_date.replace("-", "")

        # 데이터 로드
        if universe_codes is None:
            universe_codes = self._discover_codes()
        if not universe_codes:
            logger.error("No universe codes specified and no CSV files found")
            raise ValueError("No universe codes to backtest")

        logger.info("Loading OHLCV data for %d codes...", len(universe_codes))
        ohlcv_map = load_universe(universe_codes, self.data_dir)
        if not ohlcv_map:
            raise ValueError(f"No OHLCV data loaded from {self.data_dir}")

        trading_dates = get_trading_dates(ohlcv_map, start_date, end_date)
        if not trading_dates:
            raise ValueError(f"No trading dates in range {start_date}~{end_date}")

        # 컴포넌트 조립
        self._build_components()
        self.broker.set_market_data(ohlcv_map)

        # 결과 수집
        equity_curve: List[DailyEquity] = []
        peak_value = self.initial_capital
        daily_loss_triggered = False

        logger.info(
            "Backtest start | %s ~ %s | %d days | %d codes | capital=%.0f",
            start_date, end_date, len(trading_dates), len(ohlcv_map), self.initial_capital,
        )

        # datetime 패치 대상 모듈
        dt_patches = [
            "order.order_executor.datetime",
            "position.position_manager.datetime",
            "infra.db.repository.datetime",
        ]
        sleep_patch_target = "order.order_executor.time.sleep"

        for day_idx, date in enumerate(trading_dates):
            # 시뮬레이션 날짜 (해당일 12:00)
            sim_dt = datetime.strptime(date, "%Y%m%d").replace(hour=12, minute=0, second=0)

            # datetime.now() 패치 클래스
            class FakeDatetime(datetime):
                @classmethod
                def now(cls, tz=None):
                    return sim_dt

                @classmethod
                def fromisoformat(cls, s):
                    return datetime.fromisoformat(s)

            # 패치 적용하여 하루 시뮬레이션
            patches = [patch(target, FakeDatetime) for target in dt_patches]
            patches.append(patch(sleep_patch_target, lambda *a, **kw: None))

            for p in patches:
                p.start()
            try:
                self._run_day(date, ohlcv_map, universe_codes, daily_loss_triggered)
            finally:
                for p in patches:
                    p.stop()

            # End-of-day: equity 기록
            balance = self.broker.get_balance()
            total_value = balance.cash + balance.total_eval
            positions_value = balance.total_eval

            prev_value = equity_curve[-1].total_value if equity_curve else self.initial_capital
            daily_return = (total_value - prev_value) / prev_value if prev_value > 0 else 0.0

            if total_value > peak_value:
                peak_value = total_value
            drawdown = (total_value - peak_value) / peak_value if peak_value > 0 else 0.0

            equity_curve.append(DailyEquity(
                date=date,
                total_value=total_value,
                cash=balance.cash,
                positions_value=positions_value,
                daily_return=daily_return,
                drawdown=drawdown,
            ))

            # 일일 손실 리셋 (다음 날은 새로 체크)
            daily_loss_triggered = False

            # MDD 체크 — 한도 도달 시 조기 종료
            if drawdown <= self.config.risk.mdd_limit:
                logger.critical("MDD limit hit (%.2f%%) — stopping backtest at %s", drawdown * 100, date)
                break

        # 결과 생성
        trades = self._collect_trades()
        result = BacktestResult(
            start_date=start_date,
            end_date=end_date,
            initial_capital=self.initial_capital,
            trades=trades,
            equity_curve=equity_curve,
        )
        result.calculate_metrics()

        # 정리
        if self.database:
            self.database.close()

        logger.info(
            "Backtest complete | return=%.2f%% | trades=%d | MDD=%.2f%%",
            result.total_return * 100, result.total_trades, result.max_drawdown * 100,
        )
        return result

    # ══════════════════════════════════════════
    # 내부 메서드
    # ══════════════════════════════════════════

    def _build_components(self):
        """백테스트용 컴포넌트를 조립한다."""
        self.broker = SimulatedBroker(self.initial_capital)
        self.notifier = NullNotifier()

        # In-memory SQLite
        self.database = Database(db_path=":memory:")
        self.database.init_tables()
        self.repo = Repository(self.database)

        self.strategy = MomentumSwingStrategy(config=self.config)
        self.risk_mgr = RiskManager(config=self.config)
        self.pos_mgr = PositionManager(repository=self.repo, config=self.config)
        self.order_executor = OrderExecutor(
            broker=self.broker,
            repository=self.repo,
            position_manager=self.pos_mgr,
            risk_manager=self.risk_mgr,
            notifier=self.notifier,
            config=self.config,
        )

    def _run_day(
        self,
        date: str,
        ohlcv_map: Dict[str, pd.DataFrame],
        universe_codes: List[str],
        daily_loss_triggered: bool,
    ):
        """하루치 시뮬레이션을 실행한다 (4-Phase)."""
        self.broker.set_current_date(date)
        self.broker.update_current_prices()

        # 현재가 딕셔너리 (Strategy에 전달)
        current_prices: Dict[str, PriceData] = {}
        for code in universe_codes:
            if code in self.broker.current_bar:
                current_prices[code] = self.broker.get_price(code)

        if not current_prices:
            return  # 거래 데이터 없는 날

        # current_date까지의 OHLCV (미래 차단)
        ohlcv_up_to_today: Dict[str, pd.DataFrame] = {}
        for code in universe_codes:
            df = self.broker.get_ohlcv(code, period=100)
            if not df.empty:
                ohlcv_up_to_today[code] = df

        # ── Phase 1: 보유 포지션 청산 시그널 스캔 + 매도 ──
        active_positions = self.pos_mgr.get_active_positions()
        if active_positions:
            exit_signals = self.strategy.scan_exit_signals(
                active_positions, ohlcv_up_to_today, current_prices,
            )
            for es in exit_signals:
                pos = self.repo.get_position(es.position_id)
                if pos and pos.status == PositionStatus.ACTIVE.value:
                    self.order_executor.execute_sell(es, pos)

            # 트레일링 최고가 갱신 (매도하지 않은 포지션)
            for pos in self.pos_mgr.get_active_positions():
                price_data = current_prices.get(pos.stock_code)
                if price_data:
                    self.pos_mgr.update_trailing_high(pos.position_id, price_data.current_price)

        # ── Phase 2: 일일 손실 / MDD 체크 ──
        portfolio = self._build_portfolio()
        if self.risk_mgr.check_daily_loss_limit(portfolio):
            daily_loss_triggered = True

        # ── Phase 3: 진입 시그널 스캔 + 매수 (손실 한도 미도달 시만) ──
        if not daily_loss_triggered:
            signals = self.strategy.scan_entry_signals(
                universe_codes, ohlcv_up_to_today, current_prices,
            )
            for signal in signals:
                portfolio = self._build_portfolio()
                risk_result = self.risk_mgr.check_risk_gates(signal, portfolio)
                if risk_result.passed:
                    self.order_executor.execute_buy(signal, portfolio)

        # ── Phase 4: 미체결 주문 처리 (즉시 체결 → PENDING→ACTIVE 전환) ──
        self.order_executor.check_pending_orders()

        # ── End-of-day: holding_days 증가 ──
        self.pos_mgr.increment_holding_days()

    def _build_portfolio(self):
        """현재 포트폴리오를 구성한다."""
        balance = self.broker.get_balance()
        total_value = balance.cash + balance.total_eval
        return self.pos_mgr.build_portfolio(
            cash_balance=balance.cash,
            total_capital=total_value,
        )

    def _collect_trades(self) -> List[TradeRecord]:
        """DB에서 CLOSED 포지션을 수집하여 TradeRecord로 변환한다."""
        closed = self.repo.get_positions_by_status(PositionStatus.CLOSED.value)
        trades = []
        for pos in closed:
            trades.append(TradeRecord(
                stock_code=pos.stock_code,
                stock_name=pos.stock_name,
                entry_date=pos.entry_date or "",
                entry_price=pos.entry_price or 0.0,
                exit_date=pos.exit_date or "",
                exit_price=pos.exit_price or 0.0,
                quantity=pos.quantity or 0,
                pnl=pos.pnl or 0.0,
                pnl_pct=pos.pnl_pct or 0.0,
                exit_reason=pos.exit_reason or "UNKNOWN",
                holding_days=pos.holding_days or 0,
            ))
        trades.sort(key=lambda t: t.entry_date)
        return trades

    def _discover_codes(self) -> List[str]:
        """data_dir에서 CSV 파일명으로 종목 코드를 추출한다."""
        import os
        codes = []
        if os.path.isdir(self.data_dir):
            for f in sorted(os.listdir(self.data_dir)):
                if f.endswith(".csv"):
                    codes.append(f.replace(".csv", ""))
        return codes
