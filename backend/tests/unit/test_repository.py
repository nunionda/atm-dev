"""
infra/db/repository.py 단위 테스트
TC-REP-001 ~ TC-REP-008: DB CRUD 검증
"""

import pytest
from datetime import datetime
from common.enums import PositionStatus
from common.types import DailyReportData
from infra.db.models import Position, Universe
from infra.db.repository import Repository


class TestUniverseRepository:

    def test_upsert_and_get_universe(self, repository):
        """TC-REP-001: 유니버스 종목 추가/조회."""
        repository.upsert_universe("005930", "삼성전자", "KOSPI", "전기전자")
        repository.upsert_universe("000660", "SK하이닉스", "KOSPI", "전기전자")

        active = repository.get_active_universe()
        assert len(active) == 2
        codes = [u.stock_code for u in active]
        assert "005930" in codes
        assert "000660" in codes

    def test_upsert_updates_existing(self, repository):
        """TC-REP-002: 기존 종목 업데이트."""
        repository.upsert_universe("005930", "삼성전자", "KOSPI")
        repository.upsert_universe("005930", "삼성전자(수정)", "KOSPI")

        active = repository.get_active_universe()
        assert len(active) == 1
        assert active[0].stock_name == "삼성전자(수정)"


class TestPositionRepository:

    def test_create_and_get_position(self, repository):
        """TC-REP-003: 포지션 생성/조회."""
        now = datetime.now().isoformat()
        pos = Position(
            position_id="test_001",
            stock_code="005930",
            stock_name="삼성전자",
            status="PENDING",
            quantity=20,
            created_at=now,
            updated_at=now,
        )
        repository.create_position(pos)

        found = repository.get_position("test_001")
        assert found is not None
        assert found.stock_code == "005930"

    def test_get_active_positions(self, repository):
        """TC-REP-004: ACTIVE 상태 포지션 조회."""
        now = datetime.now().isoformat()
        for i, status in enumerate(["ACTIVE", "ACTIVE", "PENDING", "CLOSED"]):
            repository.create_position(Position(
                position_id=f"pos_{i}",
                stock_code=f"00{i}",
                stock_name=f"종목{i}",
                status=status,
                quantity=10,
                created_at=now,
                updated_at=now,
            ))

        active = repository.get_active_positions()
        assert len(active) == 2

    def test_is_stock_held(self, repository):
        """TC-REP-005: 보유 종목 체크."""
        now = datetime.now().isoformat()
        repository.create_position(Position(
            position_id="held_001",
            stock_code="005930",
            stock_name="삼성전자",
            status="ACTIVE",
            quantity=20,
            created_at=now,
            updated_at=now,
        ))

        assert repository.is_stock_held("005930") is True
        assert repository.is_stock_held("000660") is False

    def test_update_position(self, repository):
        """TC-REP-006: 포지션 필드 업데이트."""
        now = datetime.now().isoformat()
        repository.create_position(Position(
            position_id="upd_001",
            stock_code="005930",
            stock_name="삼성전자",
            status="PENDING",
            quantity=20,
            created_at=now,
            updated_at=now,
        ))

        repository.update_position("upd_001", status="ACTIVE", entry_price=72000.0)

        pos = repository.get_position("upd_001")
        assert pos.status == "ACTIVE"
        assert pos.entry_price == 72000.0


class TestTradeLogRepository:

    def test_log_trade_event(self, repository):
        """TC-REP-007: 매매 이벤트 로깅."""
        repository.log_trade_event(
            event_type="SIGNAL_DETECTED",
            position_id="pos_001",
            stock_code="005930",
            detail={"signal": "PS1+CF1"},
        )
        # 에러 없이 실행되면 성공


class TestDailyReportRepository:

    def test_save_and_get_report(self, repository):
        """TC-REP-008: 일일 리포트 저장/조회."""
        report = DailyReportData(
            trade_date="2026-02-25",
            buy_count=3,
            sell_count=2,
            realized_pnl=150000,
            daily_return=1.5,
            active_positions=5,
            cash_balance=7_000_000,
            total_value=10_150_000,
        )
        repository.save_daily_report(report)

        latest = repository.get_latest_report()
        assert latest is not None
        assert latest.trade_date == "2026-02-25"
        assert latest.buy_count == 3
        assert latest.realized_pnl == 150000
