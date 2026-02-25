"""
Repository 패턴: 데이터 접근 추상화
문서: ATS-SAD-001 Part B
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from common.enums import OrderStatus, PositionStatus
from common.types import DailyReportData
from infra.db.connection import Database
from infra.db.models import (
    ConfigHistory,
    DailyReport,
    Order,
    Position,
    TradeLog,
    Universe,
)
from infra.logger import get_logger

logger = get_logger("repository")


class Repository:
    """DB CRUD 레포지토리."""

    def __init__(self, database: Database):
        self.db = database

    def _session(self) -> Session:
        return self.db.get_session()

    # ──────────────────────────────────────
    # Universe
    # ──────────────────────────────────────

    def get_active_universe(self) -> List[Universe]:
        """활성 유니버스 종목 목록을 반환한다."""
        with self._session() as s:
            return s.query(Universe).filter(Universe.is_active == 1).all()

    def upsert_universe(self, stock_code: str, stock_name: str,
                        market: str = "KOSPI", sector: str = None):
        """유니버스 종목을 추가하거나 업데이트한다."""
        with self._session() as s:
            existing = s.query(Universe).get(stock_code)
            now = datetime.now().isoformat()
            if existing:
                existing.stock_name = stock_name
                existing.market = market
                existing.sector = sector or existing.sector
                existing.is_active = 1
                existing.updated_at = now
            else:
                s.add(Universe(
                    stock_code=stock_code,
                    stock_name=stock_name,
                    market=market,
                    sector=sector,
                    is_active=1,
                    updated_at=now,
                ))
            s.commit()

    # ──────────────────────────────────────
    # Position
    # ──────────────────────────────────────

    def create_position(self, pos: Position):
        """포지션을 생성한다."""
        with self._session() as s:
            s.add(pos)
            s.commit()
            logger.info("Position created | id=%s | stock=%s | status=%s",
                        pos.position_id, pos.stock_code, pos.status)

    def get_position(self, position_id: str) -> Optional[Position]:
        """포지션을 ID로 조회한다."""
        with self._session() as s:
            return s.query(Position).get(position_id)

    def get_positions_by_status(self, status: str) -> List[Position]:
        """상태별 포지션 목록을 조회한다."""
        with self._session() as s:
            return s.query(Position).filter(Position.status == status).all()

    def get_active_positions(self) -> List[Position]:
        """ACTIVE 상태 포지션을 조회한다."""
        return self.get_positions_by_status(PositionStatus.ACTIVE.value)

    def get_pending_positions(self) -> List[Position]:
        """PENDING 상태 포지션을 조회한다."""
        return self.get_positions_by_status(PositionStatus.PENDING.value)

    def is_stock_held(self, stock_code: str) -> bool:
        """해당 종목을 현재 보유 중인지 확인한다 (BR-B02 물타기 금지)."""
        with self._session() as s:
            count = (
                s.query(Position)
                .filter(
                    Position.stock_code == stock_code,
                    Position.status.in_([
                        PositionStatus.PENDING.value,
                        PositionStatus.ACTIVE.value,
                        PositionStatus.CLOSING.value,
                    ]),
                )
                .count()
            )
            return count > 0

    def update_position(self, position_id: str, **kwargs):
        """포지션 필드를 업데이트한다."""
        with self._session() as s:
            pos = s.query(Position).get(position_id)
            if not pos:
                logger.warning("Position not found | id=%s", position_id)
                return
            for key, val in kwargs.items():
                setattr(pos, key, val)
            pos.updated_at = datetime.now().isoformat()
            s.commit()
            logger.debug("Position updated | id=%s | fields=%s", position_id, list(kwargs.keys()))

    def get_today_closed_positions(self, trade_date: str) -> List[Position]:
        """당일 청산된 포지션 목록을 조회한다."""
        with self._session() as s:
            return (
                s.query(Position)
                .filter(
                    Position.status == PositionStatus.CLOSED.value,
                    Position.exit_date.like(f"{trade_date}%"),
                )
                .all()
            )

    def get_today_sold_codes(self, trade_date: str) -> List[str]:
        """당일 매도한 종목 코드 목록 (BR-S04 당일 재매수 방지)."""
        with self._session() as s:
            positions = (
                s.query(Position.stock_code)
                .filter(
                    Position.status == PositionStatus.CLOSED.value,
                    Position.exit_date.like(f"{trade_date}%"),
                )
                .all()
            )
            return [p.stock_code for p in positions]

    # ──────────────────────────────────────
    # Order
    # ──────────────────────────────────────

    def create_order(self, order: Order):
        """주문을 기록한다."""
        with self._session() as s:
            s.add(order)
            s.commit()

    def get_order(self, order_id: str) -> Optional[Order]:
        """주문을 ID로 조회한다."""
        with self._session() as s:
            return s.query(Order).get(order_id)

    def get_pending_orders(self, side: str = None) -> List[Order]:
        """미체결 주문을 조회한다."""
        with self._session() as s:
            query = s.query(Order).filter(
                Order.status == OrderStatus.SUBMITTED.value
            )
            if side:
                query = query.filter(Order.side == side)
            return query.all()

    def update_order(self, order_id: str, **kwargs):
        """주문 필드를 업데이트한다."""
        with self._session() as s:
            order = s.query(Order).get(order_id)
            if not order:
                return
            for key, val in kwargs.items():
                setattr(order, key, val)
            s.commit()

    # ──────────────────────────────────────
    # TradeLog
    # ──────────────────────────────────────

    def log_trade_event(
        self,
        event_type: str,
        position_id: str = None,
        stock_code: str = None,
        detail: dict = None,
    ):
        """매매 이벤트를 기록한다."""
        with self._session() as s:
            s.add(TradeLog(
                position_id=position_id,
                stock_code=stock_code,
                event_type=event_type,
                detail=json.dumps(detail or {}, ensure_ascii=False),
                created_at=datetime.now().isoformat(),
            ))
            s.commit()

    # ──────────────────────────────────────
    # DailyReport
    # ──────────────────────────────────────

    def save_daily_report(self, report_data: DailyReportData):
        """일일 리포트를 저장한다."""
        with self._session() as s:
            # 동일 날짜 기존 리포트가 있으면 업데이트
            existing = (
                s.query(DailyReport)
                .filter(DailyReport.trade_date == report_data.trade_date)
                .first()
            )
            if existing:
                for field_name in [
                    "buy_count", "sell_count", "buy_amount", "sell_amount",
                    "realized_pnl", "unrealized_pnl", "total_pnl",
                    "daily_return", "cumulative_return", "active_positions",
                    "cash_balance", "total_value", "mdd", "win_count", "lose_count",
                ]:
                    setattr(existing, field_name, getattr(report_data, field_name))
                existing.created_at = datetime.now().isoformat()
            else:
                s.add(DailyReport(
                    trade_date=report_data.trade_date,
                    buy_count=report_data.buy_count,
                    sell_count=report_data.sell_count,
                    buy_amount=report_data.buy_amount,
                    sell_amount=report_data.sell_amount,
                    realized_pnl=report_data.realized_pnl,
                    unrealized_pnl=report_data.unrealized_pnl,
                    total_pnl=report_data.total_pnl,
                    daily_return=report_data.daily_return,
                    cumulative_return=report_data.cumulative_return,
                    active_positions=report_data.active_positions,
                    cash_balance=report_data.cash_balance,
                    total_value=report_data.total_value,
                    mdd=report_data.mdd,
                    win_count=report_data.win_count,
                    lose_count=report_data.lose_count,
                    created_at=datetime.now().isoformat(),
                ))
            s.commit()
            logger.info("Daily report saved | date=%s", report_data.trade_date)

    def get_latest_report(self) -> Optional[DailyReport]:
        """최신 일일 리포트를 조회한다."""
        with self._session() as s:
            return (
                s.query(DailyReport)
                .order_by(DailyReport.trade_date.desc())
                .first()
            )

    # ──────────────────────────────────────
    # ConfigHistory
    # ──────────────────────────────────────

    def log_config_change(self, param_key: str, old_value: str, new_value: str):
        """설정 변경을 기록한다."""
        with self._session() as s:
            s.add(ConfigHistory(
                param_key=param_key,
                old_value=old_value,
                new_value=new_value,
                changed_at=datetime.now().isoformat(),
            ))
            s.commit()
