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
    ReplayResult,
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
            existing = s.get(Universe, stock_code)
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
            return s.get(Position, position_id)

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
            pos = s.get(Position, position_id)
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

    def create_position_with_order(
        self, pos: Position, order: Order, event_detail: dict = None
    ):
        """포지션 + 주문 + 이벤트 로그를 단일 트랜잭션으로 생성한다."""
        with self._session() as s:
            s.add(pos)
            s.add(order)
            s.add(TradeLog(
                position_id=pos.position_id,
                stock_code=pos.stock_code,
                event_type="ENTRY",
                detail=json.dumps(event_detail or {}, ensure_ascii=False),
                created_at=datetime.now().isoformat(),
            ))
            s.commit()
            logger.info("Position+Order created (atomic) | id=%s | stock=%s",
                        pos.position_id, pos.stock_code)

    def close_position_with_order(
        self, position_id: str, order: Order,
        exit_price: float, exit_date: str, exit_reason: str,
        pnl: float, pnl_pct: float, holding_days: int,
        event_detail: dict = None,
    ):
        """포지션 청산 + 주문 + 이벤트 로그를 단일 트랜잭션으로 처리한다."""
        with self._session() as s:
            pos = s.get(Position, position_id)
            if not pos:
                logger.warning("close_position_with_order: Position not found | id=%s", position_id)
                return
            pos.status = PositionStatus.CLOSED.value
            pos.exit_price = exit_price
            pos.exit_date = exit_date
            pos.exit_reason = exit_reason
            pos.pnl = pnl
            pos.pnl_pct = pnl_pct
            pos.holding_days = holding_days
            pos.updated_at = datetime.now().isoformat()
            s.add(order)
            s.add(TradeLog(
                position_id=position_id,
                stock_code=pos.stock_code,
                event_type="EXIT",
                detail=json.dumps(event_detail or {}, ensure_ascii=False),
                created_at=datetime.now().isoformat(),
            ))
            s.commit()
            logger.info("Position closed (atomic) | id=%s | reason=%s | pnl=%.2f%%",
                        position_id, exit_reason, pnl_pct * 100)

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
            return s.get(Order, order_id)

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
            order = s.get(Order, order_id)
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

    # ──────────────────────────────────────
    # ReplayResult
    # ──────────────────────────────────────

    def save_replay_result(self, data: dict) -> str:
        """리플레이 결과를 저장한다. result_id를 반환."""
        import uuid
        result_id = data.get("result_id") or str(uuid.uuid4())[:12]
        with self._session() as s:
            s.add(ReplayResult(
                result_id=result_id,
                market=data["market"],
                strategy=data["strategy"],
                start_date=data["start_date"],
                end_date=data["end_date"],
                initial_capital=data.get("initial_capital", 0),
                final_equity=data.get("final_equity", 0),
                total_return_pct=data.get("total_return_pct", 0),
                sharpe_ratio=data.get("sharpe_ratio", 0),
                max_drawdown_pct=data.get("max_drawdown_pct", 0),
                total_trades=data.get("total_trades", 0),
                win_rate=data.get("win_rate", 0),
                profit_factor=data.get("profit_factor", 0),
                equity_curve_json=json.dumps(data.get("equity_curve", []), ensure_ascii=False, default=str),
                trades_json=json.dumps(data.get("trades", []), ensure_ascii=False, default=str),
                metrics_json=json.dumps(data.get("metrics", {}), ensure_ascii=False, default=str),
                created_at=datetime.now().isoformat(),
            ))
            s.commit()
        logger.info("Replay result saved | id=%s | market=%s", result_id, data["market"])
        return result_id

    def list_replay_results(
        self, market: Optional[str] = None, limit: int = 20, offset: int = 0
    ) -> List[dict]:
        """저장된 리플레이 결과 목록을 반환한다 (요약만, JSON blob 제외)."""
        with self._session() as s:
            query = s.query(ReplayResult)
            if market:
                query = query.filter(ReplayResult.market == market)
            results = (
                query.order_by(ReplayResult.created_at.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )
            return [
                {
                    "result_id": r.result_id,
                    "market": r.market,
                    "strategy": r.strategy,
                    "start_date": r.start_date,
                    "end_date": r.end_date,
                    "initial_capital": r.initial_capital,
                    "final_equity": r.final_equity,
                    "total_return_pct": r.total_return_pct,
                    "sharpe_ratio": r.sharpe_ratio,
                    "max_drawdown_pct": r.max_drawdown_pct,
                    "total_trades": r.total_trades,
                    "win_rate": r.win_rate,
                    "profit_factor": r.profit_factor,
                    "created_at": r.created_at,
                }
                for r in results
            ]

    def get_replay_result(self, result_id: str) -> Optional[dict]:
        """리플레이 결과 상세 조회 (JSON blob 포함)."""
        with self._session() as s:
            r = s.get(ReplayResult, result_id)
            if not r:
                return None
            return {
                "result_id": r.result_id,
                "market": r.market,
                "strategy": r.strategy,
                "start_date": r.start_date,
                "end_date": r.end_date,
                "initial_capital": r.initial_capital,
                "final_equity": r.final_equity,
                "total_return_pct": r.total_return_pct,
                "sharpe_ratio": r.sharpe_ratio,
                "max_drawdown_pct": r.max_drawdown_pct,
                "total_trades": r.total_trades,
                "win_rate": r.win_rate,
                "profit_factor": r.profit_factor,
                "equity_curve": json.loads(r.equity_curve_json) if r.equity_curve_json else [],
                "trades": json.loads(r.trades_json) if r.trades_json else [],
                "metrics": json.loads(r.metrics_json) if r.metrics_json else {},
                "created_at": r.created_at,
            }

    def delete_replay_result(self, result_id: str) -> bool:
        """리플레이 결과를 삭제한다."""
        with self._session() as s:
            r = s.get(ReplayResult, result_id)
            if not r:
                return False
            s.delete(r)
            s.commit()
        logger.info("Replay result deleted | id=%s", result_id)
        return True
