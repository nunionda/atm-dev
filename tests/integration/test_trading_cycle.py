"""
통합 테스트: 매매 사이클 E2E 검증
TC-INT-001 ~ TC-INT-005

브로커/텔레그램을 Mock으로 대체하고,
실제 DB + 전략 + 리스크 + 주문 + 포지션이 함께 동작하는지 검증.
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock

from common.enums import PositionStatus, SystemState
from common.types import (
    Balance,
    BalancePosition,
    ExitSignal,
    OrderResult,
    OrderStatusResponse,
    PriceData,
    Signal,
)
from core.state_manager import SystemStateManager
from data.config_manager import ATSConfig
from infra.db.models import Position
from order.order_executor import OrderExecutor
from position.position_manager import PositionManager
from risk.risk_manager import RiskManager
from strategy.momentum_swing import MomentumSwingStrategy


class TestBuyCycle:
    """TC-INT-001: 시그널 → 리스크체크 → 매수 주문 → 포지션 생성 통합 흐름."""

    def test_full_buy_flow(self, repository, config, mock_broker, mock_notifier):
        """전략 시그널 → 리스크 게이트 → 매수 → PENDING 포지션 생성."""
        pm = PositionManager(repository, config)
        rm = RiskManager(config)
        oe = OrderExecutor(
            broker=mock_broker, repository=repository,
            position_manager=pm, risk_manager=rm,
            notifier=mock_notifier, config=config,
        )

        # 1) 시그널 생성 (전략에서 생성되었다고 가정)
        signal = Signal(
            stock_code="005930", stock_name="삼성전자",
            primary_signals=["PS1"], confirmation_filters=["CF1"],
            current_price=72000.0, bb_upper=76000.0,
        )

        # 2) 포트폴리오 구성
        portfolio = pm.build_portfolio(
            cash_balance=8_000_000, total_capital=10_000_000,
        )

        # 3) 리스크 게이트 체크
        risk_result = rm.check_risk_gates(signal, portfolio)
        assert risk_result.passed is True

        # 4) 매수 실행
        result = oe.execute_buy(signal, portfolio)
        assert result is not None
        assert result.success is True

        # 5) PENDING 포지션 확인
        pending = pm.get_pending_positions()
        assert len(pending) == 1
        assert pending[0].stock_code == "005930"
        assert pending[0].status == PositionStatus.PENDING.value

        # 6) 알림 발송 확인
        mock_notifier.send_message.assert_called()


class TestSellCycle:
    """TC-INT-002: 포지션 보유 → 청산 시그널 → 매도 → CLOSED 통합 흐름."""

    def test_full_sell_flow(self, repository, config, mock_broker, mock_notifier):
        pm = PositionManager(repository, config)
        rm = RiskManager(config)
        strategy = MomentumSwingStrategy(config)
        oe = OrderExecutor(
            broker=mock_broker, repository=repository,
            position_manager=pm, risk_manager=rm,
            notifier=mock_notifier, config=config,
        )

        # 1) ACTIVE 포지션 생성
        signal = Signal(
            stock_code="005930", stock_name="삼성전자",
            primary_signals=["PS1"], confirmation_filters=["CF1"],
            current_price=70000.0,
        )
        pos = pm.create_pending_position(signal, 20, 70000)
        pm.activate_position(pos.position_id, 70000.0, 20)

        # 2) 손절가 이하로 하락 → 청산 시그널 생성
        active_positions = pm.get_active_positions()
        prices = {
            "005930": PriceData(
                stock_code="005930", stock_name="삼성전자",
                current_price=67000.0, open_price=68000, high_price=68500,
                low_price=66500, prev_close=69000, volume=20000000,
                change_pct=-2.9, timestamp=datetime.now().isoformat(),
            ),
        }

        # 빈 ohlcv (ES1 체크에는 불필요)
        import pandas as pd
        ohlcv = {"005930": pd.DataFrame()}

        exit_signals = strategy.scan_exit_signals(active_positions, ohlcv, prices)
        assert len(exit_signals) == 1
        assert exit_signals[0].exit_type == "ES1"

        # 3) 매도 실행
        result = oe.execute_sell(exit_signals[0], active_positions[0])
        assert result.success is True

        # 4) 포지션 CLOSING 확인
        updated_pos = repository.get_position(pos.position_id)
        assert updated_pos.status == PositionStatus.CLOSING.value


class TestRiskLimitIntegration:
    """TC-INT-003: 리스크 한도 → 매매 차단 통합 검증."""

    def test_max_positions_blocks_buy(self, repository, config, mock_broker, mock_notifier):
        """10종목 보유 시 추가 매수 차단."""
        pm = PositionManager(repository, config)
        rm = RiskManager(config)
        oe = OrderExecutor(
            broker=mock_broker, repository=repository,
            position_manager=pm, risk_manager=rm,
            notifier=mock_notifier, config=config,
        )

        # 10종목 ACTIVE 생성
        for i in range(10):
            code = f"00{i:04d}"
            sig = Signal(
                stock_code=code, stock_name=f"종목{i}",
                primary_signals=["PS1"], confirmation_filters=["CF1"],
                current_price=50000.0,
            )
            pos = pm.create_pending_position(sig, 10, 50000)
            pm.activate_position(pos.position_id, 50000.0, 10)

        assert pm.active_count() == 10

        # 11번째 매수 시도
        new_signal = Signal(
            stock_code="099999", stock_name="신규종목",
            primary_signals=["PS1"], confirmation_filters=["CF1"],
            current_price=60000.0, bb_upper=65000.0,
        )
        portfolio = pm.build_portfolio(
            cash_balance=50_000_000, total_capital=100_000_000,
        )

        risk_result = rm.check_risk_gates(new_signal, portfolio)
        assert risk_result.passed is False
        assert risk_result.failed_gate == "RG1"


class TestStateTransitionIntegration:
    """TC-INT-004: 시스템 상태 전이 통합 검증."""

    def test_full_lifecycle(self):
        """INIT → READY → RUNNING → STOPPING → STOPPED 전체 수명주기."""
        sm = SystemStateManager()

        assert sm.state == SystemState.INIT

        sm.transition_to(SystemState.READY)
        assert sm.is_ready

        sm.transition_to(SystemState.RUNNING)
        assert sm.is_running

        sm.transition_to(SystemState.STOPPING)

        sm.transition_to(SystemState.STOPPED)
        assert sm.is_stopped

    def test_error_and_recovery(self):
        """에러 발생 후 복구."""
        sm = SystemStateManager()
        sm.transition_to(SystemState.READY)
        sm.transition_to(SystemState.RUNNING)

        sm.force_error("API failure")
        assert sm.state == SystemState.ERROR

        sm.transition_to(SystemState.READY)
        assert sm.is_ready


class TestMultiPositionScenario:
    """TC-INT-005: 복수 포지션 동시 관리 시나리오."""

    def test_multiple_positions_exit_independently(
        self, repository, config, mock_broker, mock_notifier
    ):
        """포지션 3개: 1개 손절, 1개 익절, 1개 HOLD."""
        pm = PositionManager(repository, config)
        strategy = MomentumSwingStrategy(config)

        positions = []
        for i, (code, name, entry) in enumerate([
            ("005930", "삼성전자", 70000),
            ("000660", "SK하이닉스", 130000),
            ("035420", "NAVER", 350000),
        ]):
            sig = Signal(
                stock_code=code, stock_name=name,
                primary_signals=["PS1"], confirmation_filters=["CF1"],
                current_price=entry,
            )
            pos = pm.create_pending_position(sig, 10, entry)
            pm.activate_position(pos.position_id, float(entry), 10)
            positions.append(pos)

        active = pm.get_active_positions()
        assert len(active) == 3

        import pandas as pd
        prices = {
            "005930": PriceData(  # 손절: 70000 → 67000 (-4.3%)
                stock_code="005930", stock_name="삼성전자",
                current_price=67000.0, open_price=68000, high_price=68500,
                low_price=66500, prev_close=69000, volume=20000000,
                change_pct=-2.9, timestamp=datetime.now().isoformat(),
            ),
            "000660": PriceData(  # 익절: 130000 → 140000 (+7.7%)
                stock_code="000660", stock_name="SK하이닉스",
                current_price=140000.0, open_price=138000, high_price=141000,
                low_price=137000, prev_close=139000, volume=5000000,
                change_pct=0.72, timestamp=datetime.now().isoformat(),
            ),
            "035420": PriceData(  # HOLD: 350000 → 355000 (+1.4%)
                stock_code="035420", stock_name="NAVER",
                current_price=355000.0, open_price=352000, high_price=356000,
                low_price=351000, prev_close=353000, volume=1000000,
                change_pct=0.57, timestamp=datetime.now().isoformat(),
            ),
        }

        ohlcv = {code: pd.DataFrame() for code in ["005930", "000660", "035420"]}

        exit_signals = strategy.scan_exit_signals(active, ohlcv, prices)

        # 삼성전자: ES1 손절, SK하이닉스: ES2 익절, NAVER: 없음
        assert len(exit_signals) == 2

        exit_types = {es.stock_code: es.exit_type for es in exit_signals}
        assert exit_types["005930"] == "ES1"  # 손절
        assert exit_types["000660"] == "ES2"  # 익절
        assert "035420" not in exit_types     # HOLD
