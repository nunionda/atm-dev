"""
risk/risk_manager.py 단위 테스트
TC-RSK-001 ~ TC-RSK-010: 리스크 게이트 및 한도 검증 (BRD §3.3~3.4)
"""

import pytest
from common.types import Portfolio, Signal
from risk.risk_manager import RiskManager


class TestRiskGates:
    """RG1~RG4 게이트 검증."""

    @pytest.fixture
    def risk_mgr(self, config):
        return RiskManager(config)

    @pytest.fixture
    def base_signal(self):
        return Signal(
            stock_code="005930",
            stock_name="삼성전자",
            primary_signals=["PS1"],
            confirmation_filters=["CF1"],
            current_price=72000.0,
            bb_upper=76000.0,
        )

    @pytest.fixture
    def base_portfolio(self):
        return Portfolio(
            total_capital=10_000_000.0,
            cash_balance=8_000_000.0,
            active_count=2,
            daily_buy_amount=1_500_000.0,
        )

    def test_all_gates_pass(self, risk_mgr, base_signal, base_portfolio):
        """TC-RSK-001: 모든 게이트 통과."""
        result = risk_mgr.check_risk_gates(base_signal, base_portfolio)
        assert result.passed is True
        assert result.failed_gate is None

    def test_rg1_max_positions_fail(self, risk_mgr, base_signal, base_portfolio):
        """TC-RSK-002: RG1 — 보유종목 한도 초과 (10종목)."""
        base_portfolio.active_count = 10  # max_positions=10
        result = risk_mgr.check_risk_gates(base_signal, base_portfolio)
        assert result.passed is False
        assert result.failed_gate == "RG1"

    def test_rg1_at_limit_fail(self, risk_mgr, base_signal, base_portfolio):
        """RG1 — 정확히 한도에 도달."""
        base_portfolio.active_count = 10
        result = risk_mgr.check_risk_gates(base_signal, base_portfolio)
        assert result.passed is False

    def test_rg1_one_below_limit_pass(self, risk_mgr, base_signal, base_portfolio):
        """RG1 — 한도 미만이면 통과."""
        base_portfolio.active_count = 9
        result = risk_mgr.check_risk_gates(base_signal, base_portfolio)
        assert result.passed is True

    def test_rg4_bb_upper_fail(self, risk_mgr, base_signal, base_portfolio):
        """TC-RSK-003: RG4 — 볼린저밴드 상단 도달."""
        base_signal.current_price = 77000.0  # > bb_upper 76000
        result = risk_mgr.check_risk_gates(base_signal, base_portfolio)
        assert result.passed is False
        assert result.failed_gate == "RG4"

    def test_rg4_at_bb_upper_fail(self, risk_mgr, base_signal, base_portfolio):
        """RG4 — 정확히 BB 상단에 도달."""
        base_signal.current_price = 76000.0  # == bb_upper
        result = risk_mgr.check_risk_gates(base_signal, base_portfolio)
        assert result.passed is False
        assert result.failed_gate == "RG4"

    def test_rg4_just_below_pass(self, risk_mgr, base_signal, base_portfolio):
        """RG4 — BB 상단 바로 아래면 통과."""
        base_signal.current_price = 75999.0
        result = risk_mgr.check_risk_gates(base_signal, base_portfolio)
        assert result.passed is True


class TestDailyLossLimit:
    """BR-R01 일일 손실 한도 검증."""

    @pytest.fixture
    def risk_mgr(self, config):
        return RiskManager(config)

    def test_no_loss_returns_false(self, risk_mgr):
        """TC-RSK-004: 손실 없으면 False."""
        portfolio = Portfolio(total_capital=10_000_000, daily_pnl=50000)
        assert risk_mgr.check_daily_loss_limit(portfolio) is False

    def test_at_limit_returns_true(self, risk_mgr):
        """TC-RSK-005: 정확히 -3%에 도달하면 True."""
        portfolio = Portfolio(total_capital=10_000_000, daily_pnl=-300_000)
        assert risk_mgr.check_daily_loss_limit(portfolio) is True

    def test_exceeds_limit_returns_true(self, risk_mgr):
        """TC-RSK-006: -3% 초과하면 True."""
        portfolio = Portfolio(total_capital=10_000_000, daily_pnl=-500_000)
        assert risk_mgr.check_daily_loss_limit(portfolio) is True

    def test_small_loss_returns_false(self, risk_mgr):
        """-1%는 한도 미달."""
        portfolio = Portfolio(total_capital=10_000_000, daily_pnl=-100_000)
        assert risk_mgr.check_daily_loss_limit(portfolio) is False


class TestMDDLimit:
    """BR-R02 MDD 한도 검증."""

    @pytest.fixture
    def risk_mgr(self, config):
        return RiskManager(config)

    def test_mdd_within_limit(self, risk_mgr):
        """TC-RSK-007: MDD -5%는 한도 내."""
        portfolio = Portfolio(mdd=-0.05)
        assert risk_mgr.check_mdd_limit(portfolio) is False

    def test_mdd_at_limit(self, risk_mgr):
        """TC-RSK-008: MDD -10%에 도달하면 True."""
        portfolio = Portfolio(mdd=-0.10)
        assert risk_mgr.check_mdd_limit(portfolio) is True

    def test_mdd_exceeds_limit(self, risk_mgr):
        """MDD -15% 초과하면 True."""
        portfolio = Portfolio(mdd=-0.15)
        assert risk_mgr.check_mdd_limit(portfolio) is True


class TestCalculateBuyQuantity:
    """BRD §2.7 매수 수량 계산 검증."""

    @pytest.fixture
    def risk_mgr(self, config):
        return RiskManager(config)

    def test_normal_calculation(self, risk_mgr):
        """TC-RSK-009: 정상 매수 수량 계산.
        총투자금 10M × 15% = 1.5M
        1,500,000 ÷ 72,000 = 20.83 → 20주
        """
        portfolio = Portfolio(
            total_capital=10_000_000,
            cash_balance=8_000_000,
        )
        qty = risk_mgr.calculate_buy_quantity(72000.0, portfolio)
        assert qty == 20

    def test_insufficient_cash(self, risk_mgr):
        """TC-RSK-010: 현금 부족 시 0주."""
        portfolio = Portfolio(
            total_capital=10_000_000,
            cash_balance=1_500_000,  # 20% 최소현금 = 2M → 여유 없음
        )
        qty = risk_mgr.calculate_buy_quantity(72000.0, portfolio)
        assert qty == 0

    def test_zero_price(self, risk_mgr):
        """현재가 0이면 0주."""
        portfolio = Portfolio(total_capital=10_000_000, cash_balance=8_000_000)
        qty = risk_mgr.calculate_buy_quantity(0, portfolio)
        assert qty == 0

    def test_max_order_amount_capped(self, risk_mgr):
        """1회 최대 주문금액(3M) 적용."""
        portfolio = Portfolio(
            total_capital=100_000_000,  # 1억
            cash_balance=80_000_000,
        )
        # 15% = 15M이지만 max_order_amount=3M으로 제한
        qty = risk_mgr.calculate_buy_quantity(72000.0, portfolio)
        expected = int(3_000_000 / 72000)  # 41주
        assert qty == expected
