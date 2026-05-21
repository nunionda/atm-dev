"""
position/position_manager.py 단위 테스트
TC-POS-001 ~ TC-POS-008: 포지션 상태 전이 검증 (SAD §9)
"""

import pytest
from common.enums import PositionStatus
from common.types import Signal
from position.position_manager import PositionManager


class TestPositionCreation:

    def test_create_pending_position(self, repository, config):
        """TC-POS-001: PENDING 포지션 생성."""
        pm = PositionManager(repository, config)
        signal = Signal(
            stock_code="005930",
            stock_name="삼성전자",
            primary_signals=["PS1"],
            confirmation_filters=["CF1"],
            current_price=72000.0,
        )

        pos = pm.create_pending_position(signal, quantity=20, order_price=72000)

        assert pos.position_id is not None
        assert pos.stock_code == "005930"
        assert pos.status == PositionStatus.PENDING.value
        assert pos.quantity == 20

    def test_created_position_is_in_db(self, repository, config):
        """TC-POS-002: 생성된 포지션이 DB에 저장."""
        pm = PositionManager(repository, config)
        signal = Signal(
            stock_code="005930", stock_name="삼성전자",
            primary_signals=["PS1"], confirmation_filters=["CF1"],
            current_price=72000.0,
        )

        pos = pm.create_pending_position(signal, 20, 72000)
        found = repository.get_position(pos.position_id)
        assert found is not None
        assert found.stock_code == "005930"


class TestPositionStateTransition:

    @pytest.fixture
    def pm(self, repository, config):
        return PositionManager(repository, config)

    @pytest.fixture
    def pending_pos(self, pm):
        signal = Signal(
            stock_code="005930", stock_name="삼성전자",
            primary_signals=["PS1"], confirmation_filters=["CF1"],
            current_price=72000.0,
        )
        return pm.create_pending_position(signal, 20, 72000)

    def test_activate_position(self, pm, pending_pos, repository):
        """TC-POS-003: PENDING → ACTIVE 전이.
        체결 시 손절가/익절가가 자동 설정되는지.
        """
        pm.activate_position(pending_pos.position_id, 72000.0, 20)

        pos = repository.get_position(pending_pos.position_id)
        assert pos.status == PositionStatus.ACTIVE.value
        assert pos.entry_price == 72000.0
        assert pos.stop_loss_price == pytest.approx(72000 * 0.97, rel=0.001)  # 69840
        assert pos.take_profit_price == pytest.approx(72000 * 1.07, rel=0.001)  # 77040

    def test_close_position(self, pm, pending_pos, repository):
        """TC-POS-004: ACTIVE → CLOSING → CLOSED 전이.

        Option A: cost (commission+slippage) 차감 반영.
        gross_pnl = (75000-70000)*20 = 100,000
        cost = (70000+75000)*20 * (0.00015+0.0) = 2,900,000 * 0.00015 ≈ 435
        pnl ≈ 100,000 - 435 = 99,565
        """
        pm.activate_position(pending_pos.position_id, 70000.0, 20)
        pm.close_position(pending_pos.position_id, 75000.0, "ES2")

        pos = repository.get_position(pending_pos.position_id)
        assert pos.status == PositionStatus.CLOSED.value
        assert pos.exit_price == 75000.0
        assert pos.exit_reason == "ES2"
        # Option A: cost 차감으로 gross PnL보다 작음 (단, 비율은 < 0.5%)
        gross_pnl = (75000 - 70000) * 20
        assert pos.pnl < gross_pnl, "Option A: cost 차감으로 net pnl < gross"
        assert pos.pnl == pytest.approx(gross_pnl - 435, abs=5)  # ±5원 오차 허용
        assert pos.pnl_pct < (5000 / 70000)  # 비율도 cost 차감 반영

    def test_cancel_position(self, pm, pending_pos, repository):
        """TC-POS-005: PENDING → CANCELLED 전이."""
        pm.cancel_position(pending_pos.position_id)

        pos = repository.get_position(pending_pos.position_id)
        assert pos.status == PositionStatus.CANCELLED.value

    def test_pnl_calculation_loss(self, pm, pending_pos, repository):
        """TC-POS-006: 손실 PnL 계산 (cost 차감 반영).

        gross_pnl = (67000-70000)*20 = -60,000
        cost = (70000+67000)*20 * 0.00015 = 2,740,000 * 0.00015 ≈ 411
        pnl ≈ -60,000 - 411 = -60,411 (손실 더 큼)
        """
        pm.activate_position(pending_pos.position_id, 70000.0, 20)
        pm.close_position(pending_pos.position_id, 67000.0, "ES1")

        pos = repository.get_position(pending_pos.position_id)
        gross_pnl = (67000 - 70000) * 20
        assert pos.pnl < gross_pnl  # Option A: 손실이 cost만큼 더 큼
        assert pos.pnl == pytest.approx(gross_pnl - 411, abs=5)
        assert pos.pnl_pct < 0


    # ──────────────────────────────────────
    # Option A: 슬리피지·수수료 명시 차감 회귀 보호
    # ──────────────────────────────────────

    def test_option_a_commission_subtracted_from_pnl(self, pm, pending_pos, repository):
        """Option A: commission_pct(0.015%/side)가 양방향 차감되어 gross보다 작은 net pnl."""
        pm.activate_position(pending_pos.position_id, 100000.0, 10)
        pm.close_position(pending_pos.position_id, 110000.0, "ES2")

        pos = repository.get_position(pending_pos.position_id)
        gross = (110000 - 100000) * 10  # 100,000
        # commission_pct = 0.00015, slippage = 0 (실전 default)
        # cost = (100000 + 110000) * 10 * 0.00015 = 2,100,000 * 0.00015 = 315
        expected_cost = (100000 * 10 + 110000 * 10) * 0.00015
        assert pos.pnl == pytest.approx(gross - expected_cost, abs=1)


    def test_option_a_paper_mode_includes_slippage(self, pending_pos, repository, config):
        """모의/mock 모드 (slippage_pct=0.001)에선 슬리피지도 함께 차감."""
        from position.position_manager import PositionManager
        # config의 order에 slippage_pct 강제 설정 (paper mode 시뮬)
        config.order.slippage_pct = 0.001  # 0.1%/side
        config.order.commission_pct = 0.00015

        pm = PositionManager(repository, config)
        pm.activate_position(pending_pos.position_id, 100000.0, 10)
        pm.close_position(pending_pos.position_id, 110000.0, "ES2")

        pos = repository.get_position(pending_pos.position_id)
        gross = (110000 - 100000) * 10  # 100,000
        # cost = (1,000,000 + 1,100,000) * (0.001 + 0.00015) = 2,100,000 * 0.00115 = 2,415
        expected_cost = (100000 * 10 + 110000 * 10) * (0.001 + 0.00015)
        assert pos.pnl == pytest.approx(gross - expected_cost, abs=2)


    def test_option_a_config_defaults(self):
        """OrderConfig 디폴트: commission_pct=0.00015, slippage_pct=0.0 (실전 broker fill 자연 반영)."""
        from data.config_manager import OrderConfig
        oc = OrderConfig()
        assert oc.commission_pct == 0.00015
        assert oc.slippage_pct == 0.0


class TestPositionQueries:

    @pytest.fixture
    def pm(self, repository, config):
        return PositionManager(repository, config)

    def test_is_stock_held(self, pm):
        """TC-POS-007: 보유 종목 확인 (BR-B02)."""
        signal = Signal(
            stock_code="005930", stock_name="삼성전자",
            primary_signals=["PS1"], confirmation_filters=["CF1"],
            current_price=72000.0,
        )
        pm.create_pending_position(signal, 20, 72000)

        assert pm.is_stock_held("005930") is True
        assert pm.is_stock_held("000660") is False

    def test_active_count(self, pm):
        """TC-POS-008: 보유 종목 수 카운트."""
        assert pm.active_count() == 0

        for code in ["005930", "000660"]:
            signal = Signal(
                stock_code=code, stock_name=f"종목_{code}",
                primary_signals=["PS1"], confirmation_filters=["CF1"],
                current_price=72000.0,
            )
            pos = pm.create_pending_position(signal, 10, 72000)
            pm.activate_position(pos.position_id, 72000.0, 10)

        assert pm.active_count() == 2


class TestTrailingStop:

    def test_trailing_high_update(self, repository, config):
        """트레일링 최고가 갱신."""
        pm = PositionManager(repository, config)
        signal = Signal(
            stock_code="005930", stock_name="삼성전자",
            primary_signals=["PS1"], confirmation_filters=["CF1"],
            current_price=72000.0,
        )
        pos = pm.create_pending_position(signal, 20, 72000)
        pm.activate_position(pos.position_id, 72000.0, 20)

        # 현재가 74000으로 갱신
        pm.update_trailing_high(pos.position_id, 74000.0)

        updated = repository.get_position(pos.position_id)
        assert updated.trailing_high == 74000.0
        assert updated.trailing_stop_price == pytest.approx(74000 * 0.97, rel=0.001)

    def test_trailing_high_not_decreased(self, repository, config):
        """최고가보다 낮은 가격에는 갱신하지 않음."""
        pm = PositionManager(repository, config)
        signal = Signal(
            stock_code="005930", stock_name="삼성전자",
            primary_signals=["PS1"], confirmation_filters=["CF1"],
            current_price=72000.0,
        )
        pos = pm.create_pending_position(signal, 20, 72000)
        pm.activate_position(pos.position_id, 72000.0, 20)
        pm.update_trailing_high(pos.position_id, 75000.0)  # 75000으로 갱신

        pm.update_trailing_high(pos.position_id, 73000.0)  # 73000은 하향 → 무시

        updated = repository.get_position(pos.position_id)
        assert updated.trailing_high == 75000.0  # 75000 유지
