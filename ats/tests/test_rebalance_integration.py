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


class TestSetRebalanceExitsUnion:
    """set_rebalance_exits()가 기존 코드를 덮어쓰지 않고 병합하는지 테스트."""

    def test_union_with_existing_codes(self):
        """기존 퇴출 코드에 새 코드가 병합된다."""
        from simulation.engine import SimulationEngine

        async def noop(t, d): pass
        engine = SimulationEngine(on_event=noop, market_id="sp500")

        # 레짐 다운그레이드로 퇴출 코드 추가된 상태
        engine._rebalance_exit_codes = {"INTC", "BA"}

        # 리밸런싱으로 추가 퇴출
        engine.set_rebalance_exits({"DIS", "BA"})

        # BA는 중복, DIS는 신규 — 모두 포함되어야 함
        assert engine._rebalance_exit_codes == {"INTC", "BA", "DIS"}

    def test_union_with_empty_existing(self):
        """기존 코드가 비어있으면 새 코드만 설정된다."""
        from simulation.engine import SimulationEngine

        async def noop(t, d): pass
        engine = SimulationEngine(on_event=noop, market_id="sp500")

        engine.set_rebalance_exits({"AAPL"})
        assert engine._rebalance_exit_codes == {"AAPL"}


class TestEngineRebalanceIntegration:
    """SimulationEngine._check_rebalance_sync() 통합 테스트."""

    @pytest.fixture
    def engine_with_rebalance(self):
        """리밸런싱이 내장된 엔진."""
        from simulation.engine import SimulationEngine

        async def noop(t, d): pass

        engine = SimulationEngine(on_event=noop, market_id="sp500")

        scanner = MagicMock()
        scanner.scan.return_value = [
            {"code": "AAPL", "ticker": "AAPL", "name": "Apple", "sector": "Tech"},
            {"code": "MSFT", "ticker": "MSFT", "name": "Microsoft", "sector": "Tech"},
        ]

        engine.init_rebalance_manager(scanner=scanner, rebalance_interval=3)
        return engine

    def test_no_rebalance_when_not_initialized(self):
        """리밸런스 매니저가 없으면 아무것도 안 한다."""
        from simulation.engine import SimulationEngine

        async def noop(t, d): pass
        engine = SimulationEngine(on_event=noop, market_id="sp500")

        # 에러 없이 통과해야 함
        engine._check_rebalance_sync()

    def test_first_day_triggers_rebalance(self, engine_with_rebalance):
        """첫 거래일에 리밸런싱이 발동한다 (초기 워치리스트 시딩)."""
        engine = engine_with_rebalance
        engine._backtest_date = "2024-01-02"

        # 전체 유니버스 데이터 주입 (mock)
        engine._full_universe_ohlcv = {"AAPL": MagicMock(), "MSFT": MagicMock(), "INTC": MagicMock()}

        engine._check_rebalance_sync()

        # 워치리스트가 스캔 결과로 교체됨
        assert len(engine._watchlist) == 2
        codes = {w["code"] for w in engine._watchlist}
        assert codes == {"AAPL", "MSFT"}
        assert len(engine._rebalance_history) == 1

    def test_rebalance_not_triggered_before_interval(self, engine_with_rebalance):
        """주기 도달 전에는 리밸런싱 안 함."""
        engine = engine_with_rebalance
        engine._backtest_date = "2024-01-02"
        engine._full_universe_ohlcv = {"AAPL": MagicMock(), "MSFT": MagicMock()}

        # 첫 리밸런싱
        engine._check_rebalance_sync()
        assert len(engine._rebalance_history) == 1

        # 1일 후 — 아직 안 됨
        engine._check_rebalance_sync()
        assert len(engine._rebalance_history) == 1

    def test_apply_rebalance_merges_exit_codes(self, engine_with_rebalance):
        """_apply_rebalance()는 기존 퇴출 코드와 병합한다."""
        engine = engine_with_rebalance

        # 기존 레짐 다운그레이드 퇴출 코드
        engine._rebalance_exit_codes = {"BA"}

        from backtest.rebalancer import RebalanceEvent
        event = RebalanceEvent(
            date="2024-01-15",
            cycle_number=1,
            positions_force_exited=["INTC"],
            new_watchlist=[
                {"code": "AAPL", "ticker": "AAPL", "name": "Apple", "sector": "Tech"},
            ],
        )

        engine._apply_rebalance(event)

        # 병합 확인
        assert engine._rebalance_exit_codes == {"BA", "INTC"}
        assert len(engine._rebalance_history) == 1
