"""
order/order_executor.py 단위 테스트
TC-ORD-001 ~ TC-ORD-007: 주문 실행 로직 검증
"""

import pytest
from unittest.mock import MagicMock, patch
from common.enums import PositionStatus
from common.types import OrderResult, Portfolio, Signal
from order.order_executor import OrderExecutor
from position.position_manager import PositionManager
from risk.risk_manager import RiskManager


class TestExecuteBuy:

    @pytest.fixture
    def setup(self, repository, config, mock_broker, mock_notifier):
        pm = PositionManager(repository, config)
        rm = RiskManager(config)
        oe = OrderExecutor(
            broker=mock_broker,
            repository=repository,
            position_manager=pm,
            risk_manager=rm,
            notifier=mock_notifier,
            config=config,
        )
        portfolio = Portfolio(
            total_capital=10_000_000,
            cash_balance=8_000_000,
            active_count=2,
            daily_buy_amount=1_000_000,
        )
        return oe, pm, portfolio

    def test_successful_buy(self, setup, repository):
        """TC-ORD-001: 정상 매수 주문 실행."""
        oe, pm, portfolio = setup
        signal = Signal(
            stock_code="005930", stock_name="삼성전자",
            primary_signals=["PS1"], confirmation_filters=["CF1"],
            current_price=72000.0, bb_upper=76000.0,
        )

        result = oe.execute_buy(signal, portfolio)

        assert result is not None
        assert result.success is True
        # PENDING 포지션이 생성되었는지
        pending = pm.get_pending_positions()
        assert len(pending) >= 1

    def test_buy_blocked_already_held(self, setup, repository, config):
        """TC-ORD-002: BR-B02 물타기 금지 — 이미 보유 중이면 매수 거부."""
        oe, pm, portfolio = setup

        # 먼저 같은 종목 포지션 생성
        signal = Signal(
            stock_code="005930", stock_name="삼성전자",
            primary_signals=["PS1"], confirmation_filters=["CF1"],
            current_price=72000.0, bb_upper=76000.0,
        )
        pos = pm.create_pending_position(signal, 20, 72000)
        pm.activate_position(pos.position_id, 72000.0, 20)

        # 동일 종목 재매수 시도
        result = oe.execute_buy(signal, portfolio)
        assert result is None  # 매수 거부됨

    def test_buy_quantity_zero_skipped(self, setup):
        """TC-ORD-003: 매수 수량 0이면 스킵."""
        oe, pm, portfolio = setup
        portfolio.cash_balance = 1_000_000  # 현금 부족 → 수량 0

        signal = Signal(
            stock_code="005930", stock_name="삼성전자",
            primary_signals=["PS1"], confirmation_filters=["CF1"],
            current_price=72000.0, bb_upper=76000.0,
        )

        result = oe.execute_buy(signal, portfolio)
        assert result is None

    def test_buy_broker_failure(self, setup, mock_broker):
        """TC-ORD-004: 브로커 주문 실패 시 포지션 CANCELLED."""
        oe, pm, portfolio = setup
        mock_broker.place_order.return_value = OrderResult(
            success=False, order_id="fail", error_message="Network error"
        )

        signal = Signal(
            stock_code="000660", stock_name="SK하이닉스",
            primary_signals=["PS1"], confirmation_filters=["CF1"],
            current_price=135000.0, bb_upper=145000.0,
        )

        result = oe.execute_buy(signal, portfolio)
        assert result is not None
        assert result.success is False

    def test_buy_sends_notification(self, setup, mock_notifier):
        """TC-ORD-005: 매수 주문 시 Telegram 알림 발송."""
        oe, pm, portfolio = setup
        signal = Signal(
            stock_code="000660", stock_name="SK하이닉스",
            primary_signals=["PS1", "PS2"], confirmation_filters=["CF1"],
            current_price=135000.0, bb_upper=145000.0,
        )

        oe.execute_buy(signal, portfolio)
        mock_notifier.send_message.assert_called()


class TestExecuteSell:

    @pytest.fixture
    def setup(self, repository, config, mock_broker, mock_notifier):
        pm = PositionManager(repository, config)
        rm = RiskManager(config)
        oe = OrderExecutor(
            broker=mock_broker,
            repository=repository,
            position_manager=pm,
            risk_manager=rm,
            notifier=mock_notifier,
            config=config,
        )
        # ACTIVE 포지션 생성
        signal = Signal(
            stock_code="005930", stock_name="삼성전자",
            primary_signals=["PS1"], confirmation_filters=["CF1"],
            current_price=70000.0,
        )
        pos = pm.create_pending_position(signal, 20, 70000)
        pm.activate_position(pos.position_id, 70000.0, 20)
        return oe, pm, pos

    def test_sell_stop_loss(self, setup, mock_notifier):
        """TC-ORD-006: 손절 매도 주문 실행."""
        from common.types import ExitSignal
        oe, pm, pos = setup

        exit_signal = ExitSignal(
            stock_code="005930", stock_name="삼성전자",
            position_id=pos.position_id,
            exit_type="ES1", exit_reason="STOP_LOSS",
            order_type="MARKET",
            current_price=67000.0, pnl_pct=-0.043,
        )

        result = oe.execute_sell(exit_signal, pos)
        assert result.success is True
        mock_notifier.send_message.assert_called()

    def test_sell_sends_warning_for_stop_loss(self, setup, mock_notifier):
        """TC-ORD-007: 손절 시 WARNING 레벨 알림."""
        from common.types import ExitSignal
        oe, pm, pos = setup

        exit_signal = ExitSignal(
            stock_code="005930", stock_name="삼성전자",
            position_id=pos.position_id,
            exit_type="ES1", exit_reason="STOP_LOSS",
            order_type="MARKET",
            current_price=67000.0, pnl_pct=-0.043,
        )

        oe.execute_sell(exit_signal, pos)

        # WARNING 레벨로 발송되었는지 확인
        calls = mock_notifier.send_message.call_args_list
        assert any(
            call.kwargs.get("level") == "WARNING" or
            (len(call.args) > 1 and call.args[1] == "WARNING")
            for call in calls
        )
