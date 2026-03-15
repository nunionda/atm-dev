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

    def test_apply_scan_result_returns_event(self, mgr):
        """apply_scan_result()는 RebalanceEvent를 반환한다."""
        # 초기 워치리스트 설정
        mgr._current_watchlist = [
            {"code": "AAPL", "ticker": "AAPL", "name": "Apple", "sector": "Tech"},
            {"code": "INTC", "ticker": "INTC", "name": "Intel", "sector": "Tech"},
        ]
        mgr._current_watchlist_codes = {"AAPL", "INTC"}
        mgr._is_initialized = True

        # 새 스캔 결과: INTC 퇴출, MSFT 추가
        scan_result = [
            {"code": "AAPL", "ticker": "AAPL", "name": "Apple", "sector": "Tech"},
            {"code": "MSFT", "ticker": "MSFT", "name": "Microsoft", "sector": "Tech"},
        ]
        active_positions = {"INTC": MagicMock()}  # INTC에 포지션 보유 중

        event = mgr.apply_scan_result(scan_result, active_positions)

        assert isinstance(event, RebalanceEvent)
        assert "MSFT" in event.stocks_added
        assert "INTC" in event.stocks_removed
        assert "INTC" in event.positions_force_exited
        assert event.new_watchlist == scan_result

    def test_apply_scan_result_updates_state(self, mgr):
        """apply_scan_result()는 내부 상태를 업데이트한다."""
        mgr._current_watchlist_codes = {"AAPL"}
        mgr._is_initialized = True
        mgr._trading_day_count = 14
        old_cycle = mgr._cycle_count

        scan_result = [
            {"code": "MSFT", "ticker": "MSFT", "name": "Microsoft", "sector": "Tech"},
        ]

        mgr.apply_scan_result(scan_result, {})

        assert mgr._current_watchlist == scan_result
        assert mgr._current_watchlist_codes == {"MSFT"}
        assert mgr._cycle_count == old_cycle + 1
        assert mgr._trading_day_count == 0
