"""
포지션 관리 모듈
문서: ATS-SAD-001 §9 (상태 전이), ATS-BRD-001 UC-03, UC-04

상태 전이: PENDING → ACTIVE → CLOSING → CLOSED
                └→ CANCELLED
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import List, Optional

from common.enums import PositionStatus, TradeEventType
from common.types import ExitSignal, Portfolio, Signal
from data.config_manager import ATSConfig
from infra.db.models import Position
from infra.db.repository import Repository
from infra.logger import get_logger

logger = get_logger("position_manager")


class PositionManager:
    """포지션 CRUD, 상태 전이, PnL 계산."""

    def __init__(self, repository: Repository, config: ATSConfig):
        self.repo = repository
        self.config = config

    # ──────────────────────────────────────
    # 조회
    # ──────────────────────────────────────

    def get_active_positions(self) -> List[Position]:
        return self.repo.get_active_positions()

    def get_pending_positions(self) -> List[Position]:
        return self.repo.get_pending_positions()

    def get_active_codes(self) -> List[str]:
        return [p.stock_code for p in self.get_active_positions()]

    def has_active_positions(self) -> bool:
        return len(self.get_active_positions()) > 0

    def active_count(self) -> int:
        return len(self.get_active_positions())

    def is_stock_held(self, stock_code: str) -> bool:
        """BR-B02: 동일 종목 보유 중인지 확인."""
        return self.repo.is_stock_held(stock_code)

    def was_sold_today(self, stock_code: str, trade_date: str) -> bool:
        """BR-S04: 당일 매도 후 재매수 방지."""
        today_sold = self.repo.get_today_sold_codes(trade_date)
        return stock_code in today_sold

    # ──────────────────────────────────────
    # 포지션 생성 (PENDING)
    # ──────────────────────────────────────

    def create_pending_position(
        self,
        signal: Signal,
        quantity: int,
        order_price: float,
    ) -> Position:
        """매수 주문 시 PENDING 포지션을 생성한다 (UC-03 Step 4)."""
        now = datetime.now().isoformat()
        position_id = str(uuid.uuid4())[:12]

        pos = Position(
            position_id=position_id,
            stock_code=signal.stock_code,
            stock_name=signal.stock_name,
            status=PositionStatus.PENDING.value,
            quantity=quantity,
            entry_signal=json.dumps({
                "primary": signal.primary_signals,
                "confirmation": signal.confirmation_filters,
                "strength": signal.strength,
            }, ensure_ascii=False),
            created_at=now,
            updated_at=now,
        )

        self.repo.create_position(pos)
        self.repo.log_trade_event(
            event_type=TradeEventType.SIGNAL_DETECTED.value,
            position_id=position_id,
            stock_code=signal.stock_code,
            detail={"signal": signal.__dict__},
        )

        logger.info(
            "Position PENDING created | id=%s | %s | qty=%d",
            position_id, signal.stock_name, quantity,
        )
        return pos

    # ──────────────────────────────────────
    # 상태 전이
    # ──────────────────────────────────────

    def activate_position(
        self,
        position_id: str,
        filled_price: float,
        filled_quantity: int,
    ):
        """매수 체결 → PENDING → ACTIVE 전이."""
        stop_loss = filled_price * (1 + self.config.exit.stop_loss_pct)
        take_profit = filled_price * (1 + self.config.exit.take_profit_pct)
        entry_amount = filled_price * filled_quantity

        self.repo.update_position(
            position_id,
            status=PositionStatus.ACTIVE.value,
            entry_price=filled_price,
            quantity=filled_quantity,
            entry_amount=entry_amount,
            entry_date=datetime.now().isoformat(),
            stop_loss_price=stop_loss,
            take_profit_price=take_profit,
            trailing_high=filled_price,
            trailing_stop_price=filled_price * (1 + self.config.exit.trailing_stop_pct),
            holding_days=0,
        )

        self.repo.log_trade_event(
            event_type=TradeEventType.ORDER_FILLED.value,
            position_id=position_id,
            detail={
                "filled_price": filled_price,
                "quantity": filled_quantity,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
            },
        )

        logger.info(
            "Position ACTIVATED | id=%s | price=%.0f | qty=%d | SL=%.0f | TP=%.0f",
            position_id, filled_price, filled_quantity, stop_loss, take_profit,
        )

    def start_closing(self, position_id: str, exit_signal: ExitSignal):
        """매도 주문 → ACTIVE → CLOSING 전이."""
        self.repo.update_position(
            position_id,
            status=PositionStatus.CLOSING.value,
        )

        event_map = {
            "ES1": TradeEventType.STOP_LOSS_TRIGGERED,
            "ES2": TradeEventType.TAKE_PROFIT_TRIGGERED,
            "ES3": TradeEventType.TRAILING_STOP_TRIGGERED,
        }
        event_type = event_map.get(
            exit_signal.exit_type, TradeEventType.ORDER_SUBMITTED
        ).value

        self.repo.log_trade_event(
            event_type=event_type,
            position_id=position_id,
            stock_code=exit_signal.stock_code,
            detail={"exit_type": exit_signal.exit_type, "pnl_pct": exit_signal.pnl_pct},
        )

    def close_position(
        self,
        position_id: str,
        exit_price: float,
        exit_reason: str,
    ):
        """매도 체결 → CLOSING → CLOSED 전이."""
        pos = self.repo.get_position(position_id)
        if not pos:
            return

        entry_price = pos.entry_price or 0
        quantity = pos.quantity or 0
        pnl = (exit_price - entry_price) * quantity
        pnl_pct = (exit_price - entry_price) / entry_price if entry_price > 0 else 0

        self.repo.update_position(
            position_id,
            status=PositionStatus.CLOSED.value,
            exit_price=exit_price,
            exit_date=datetime.now().isoformat(),
            exit_reason=exit_reason,
            pnl=pnl,
            pnl_pct=pnl_pct,
        )

        logger.info(
            "Position CLOSED | id=%s | %s | pnl=%.0f원 (%.2f%%) | reason=%s",
            position_id, pos.stock_name, pnl, pnl_pct * 100, exit_reason,
        )

    def cancel_position(self, position_id: str):
        """미체결 타임아웃 → PENDING → CANCELLED 전이."""
        self.repo.update_position(
            position_id,
            status=PositionStatus.CANCELLED.value,
        )
        self.repo.log_trade_event(
            event_type=TradeEventType.ORDER_CANCELLED.value,
            position_id=position_id,
        )
        logger.info("Position CANCELLED | id=%s", position_id)

    # ──────────────────────────────────────
    # 트레일링 스탑 갱신
    # ──────────────────────────────────────

    def update_trailing_high(self, position_id: str, current_price: float):
        """보유 중 최고가를 갱신하고 트레일링 스탑가를 재계산한다."""
        pos = self.repo.get_position(position_id)
        if not pos:
            return

        trailing_high = pos.trailing_high or pos.entry_price or 0
        if current_price > trailing_high:
            new_trailing_stop = current_price * (1 + self.config.exit.trailing_stop_pct)
            self.repo.update_position(
                position_id,
                trailing_high=current_price,
                trailing_stop_price=new_trailing_stop,
            )

    def increment_holding_days(self):
        """장 마감 시 ACTIVE 포지션의 보유일수를 +1 한다."""
        for pos in self.get_active_positions():
            new_days = (pos.holding_days or 0) + 1
            self.repo.update_position(pos.position_id, holding_days=new_days)

    # ──────────────────────────────────────
    # 포트폴리오 현황
    # ──────────────────────────────────────

    def build_portfolio(self, cash_balance: float, total_capital: float) -> Portfolio:
        """현재 포트폴리오 현황을 구성한다."""
        active = self.get_active_positions()
        today = datetime.now().strftime("%Y-%m-%d")
        today_sold = self.repo.get_today_sold_codes(today)

        # 당일 매수 금액 합산
        daily_buy = sum(
            (p.entry_amount or 0)
            for p in active
            if p.entry_date and p.entry_date.startswith(today)
        )

        return Portfolio(
            total_capital=total_capital,
            cash_balance=cash_balance,
            active_count=len(active),
            daily_buy_amount=daily_buy,
            today_sold_codes=today_sold,
        )
