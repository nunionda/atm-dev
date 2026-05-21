"""
common/ 모듈 단위 테스트
TC-COM-001 ~ TC-COM-006
"""

import pytest
from common.enums import (
    ExitReason,
    OrderSide,
    OrderStatus,
    OrderType,
    PositionStatus,
    SystemState,
)
from common.types import Portfolio, RiskCheckResult, Signal


class TestEnums:
    """TC-COM-001: Enum 정의 검증."""

    def test_system_state_values(self):
        assert SystemState.INIT.value == "INIT"
        assert SystemState.RUNNING.value == "RUNNING"
        assert len(SystemState) == 6

    def test_position_status_values(self):
        assert PositionStatus.PENDING.value == "PENDING"
        assert PositionStatus.CLOSED.value == "CLOSED"
        assert len(PositionStatus) == 5

    def test_exit_reason_values(self):
        """BRD §2.4 청산 사유 ES1~ES5 매핑."""
        assert ExitReason.STOP_LOSS.value == "ES1"
        assert ExitReason.TAKE_PROFIT.value == "ES2"
        assert ExitReason.TRAILING_STOP.value == "ES3"
        assert ExitReason.DEAD_CROSS.value == "ES4"
        assert ExitReason.MAX_HOLDING.value == "ES5"


class TestSignal:
    """TC-COM-002: Signal 데이터 클래스."""

    def test_signal_strength_auto_calc(self):
        """시그널 강도가 자동 계산되는지 확인."""
        s = Signal(
            stock_code="005930",
            stock_name="삼성전자",
            primary_signals=["PS1", "PS2"],
            confirmation_filters=["CF1"],
            current_price=72000.0,
        )
        assert s.strength == 3  # 2 primary + 1 confirm

    def test_signal_empty(self):
        s = Signal(stock_code="005930", stock_name="테스트")
        assert s.strength == 0
        assert s.timestamp  # 자동 생성

    def test_signal_timestamp_auto(self):
        s = Signal(stock_code="005930", stock_name="테스트")
        assert len(s.timestamp) > 0


class TestPortfolio:
    """TC-COM-003: Portfolio 데이터 클래스."""

    def test_portfolio_defaults(self):
        p = Portfolio()
        assert p.total_capital == 0.0
        assert p.active_count == 0
        assert p.today_sold_codes == []

    def test_portfolio_with_values(self, sample_portfolio):
        assert sample_portfolio.total_capital == 10_000_000.0
        assert sample_portfolio.cash_balance == 8_000_000.0
        assert sample_portfolio.active_count == 2


class TestRiskCheckResult:
    """TC-COM-004: RiskCheckResult."""

    def test_passed(self):
        r = RiskCheckResult(passed=True)
        assert r.passed is True
        assert r.failed_gate is None

    def test_failed(self):
        r = RiskCheckResult(passed=False, failed_gate="RG1", reason="한도 초과")
        assert r.passed is False
        assert r.failed_gate == "RG1"
