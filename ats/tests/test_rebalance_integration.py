# ats/tests/test_rebalance_integration.py
"""리밸런싱 내장 통합 테스트."""
import pytest
from unittest.mock import MagicMock
from backtest.rebalancer import RebalanceManager, RebalanceEvent


class TestRebalanceManagerExtensions:
    """RebalanceManager 신규 메서드 테스트."""

    @pytest.fixture
    def scanner_mock(self):
        scanner = MagicMock()
        scanner.scan.return_value = [
            {"code": "AAPL", "ticker": "AAPL", "name": "Apple", "sector": "Tech"},
            {"code": "MSFT", "ticker": "MSFT", "name": "Microsoft", "sector": "Tech"},
        ]
        return scanner

    @pytest.fixture
    def mgr(self, scanner_mock):
        return RebalanceManager(scanner=scanner_mock, rebalance_interval=14)

    def test_reset_counter_sets_zero(self, mgr):
        """reset_counter()는 _trading_day_count를 0으로 리셋한다."""
        for _ in range(10):
            mgr.tick()
        assert mgr._trading_day_count == 10

        mgr.reset_counter()
        assert mgr._trading_day_count == 0

    def test_reset_counter_prevents_immediate_rebalance(self, mgr):
        """reset 후 should_rebalance()는 False (초기화 이후)."""
        mgr._is_initialized = True
        mgr._trading_day_count = 14
        assert mgr.should_rebalance() is True

        mgr.reset_counter()
        assert mgr.should_rebalance() is False
