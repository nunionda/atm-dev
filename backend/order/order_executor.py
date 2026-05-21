"""
주문 실행 모듈
문서: ATS-SAD-001 §5.4, ATS-BRD-001 UC-03, UC-04

매수: 지정가 → 30분 미체결 시 취소 (BR-B06)
매도: 손절/익절 시장가, 데드크로스/보유초과 지정가
      15분 미체결 시 시장가 재주문 (BR-S05)
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime
from typing import Optional

from common.enums import OrderSide, OrderStatus, OrderType, TradeEventType
from common.exceptions import OrderError, OrderRejectedError
from common.types import (
    ExitSignal,
    OrderRequest,
    OrderResult,
    Portfolio,
    Signal,
)
from data.config_manager import ATSConfig
from infra.broker.base import BaseBroker
from infra.db.models import Order
from infra.db.repository import Repository
from infra.logger import get_logger
from infra.notifier.base import BaseNotifier
from position.position_manager import PositionManager
from risk.risk_manager import RiskManager

logger = get_logger("order_executor")


class OrderExecutor:
    """
    주문 생성, 전송, 체결 확인, 재시도를 담당한다.
    """

    def __init__(
        self,
        broker: BaseBroker,
        repository: Repository,
        position_manager: PositionManager,
        risk_manager: RiskManager,
        notifier: BaseNotifier,
        config: ATSConfig,
    ):
        self.broker = broker
        self.repo = repository
        self.pos_mgr = position_manager
        self.risk_mgr = risk_manager
        self.notifier = notifier
        self.config = config
        self.oc = config.order  # OrderConfig

    # ══════════════════════════════════════════
    # 매수 주문 (UC-03)
    # ══════════════════════════════════════════

    def execute_buy(self, signal: Signal, portfolio: Portfolio) -> Optional[OrderResult]:
        """
        매수 주문을 실행한다 (UC-03 기본 흐름).
        
        1. 매수 수량 계산
        2. 더블체크 (BR-B02, BR-S04)
        3. 주문 전송 (재시도 3회)
        4. 포지션/주문 DB 기록
        5. 알림 발송
        """
        today = datetime.now().strftime("%Y-%m-%d")

        # ── Step 1: 매수 수량 계산 (BRD §2.7) ──
        quantity = self.risk_mgr.calculate_buy_quantity(signal.current_price, portfolio)
        if quantity <= 0:
            logger.info("Buy skipped: quantity=0 | stock=%s", signal.stock_code)
            return None

        buy_amount = signal.current_price * quantity

        # ── Step 2: 더블체크 ──
        # BR-B02: 물타기 금지
        if self.pos_mgr.is_stock_held(signal.stock_code):
            logger.info("Buy blocked: already held | stock=%s", signal.stock_code)
            self.repo.log_trade_event(
                TradeEventType.RISK_CHECK_FAILED.value,
                stock_code=signal.stock_code,
                detail={"reason": "BR-B02 already held"},
            )
            return None

        # BR-S04: 당일 재매수 금지
        if self.pos_mgr.was_sold_today(signal.stock_code, today):
            logger.info("Buy blocked: sold today | stock=%s", signal.stock_code)
            self.repo.log_trade_event(
                TradeEventType.RISK_CHECK_FAILED.value,
                stock_code=signal.stock_code,
                detail={"reason": "BR-S04 sold today"},
            )
            return None

        # BR-R04: 1회 최대 주문금액
        if self.risk_mgr.check_max_order_amount(buy_amount):
            logger.info("Buy blocked: exceeds max order amount | amount=%.0f", buy_amount)
            return None

        # ── Step 3: 포지션 생성 (PENDING) ──
        position = self.pos_mgr.create_pending_position(
            signal=signal,
            quantity=quantity,
            order_price=signal.current_price,
        )

        # ── Step 4: 주문 전송 (재시도 3회) ──
        order_id = str(uuid.uuid4())[:12]
        order_type = self.oc.default_buy_type  # "LIMIT"

        order_req = OrderRequest(
            order_id=order_id,
            position_id=position.position_id,
            stock_code=signal.stock_code,
            stock_name=signal.stock_name,
            side=OrderSide.BUY.value,
            order_type=order_type,
            price=signal.current_price,
            quantity=quantity,
        )

        result = self._send_order_with_retry(order_req)

        # ── Step 5: 주문 DB 기록 ──
        now = datetime.now().isoformat()
        order_record = Order(
            order_id=order_id,
            position_id=position.position_id,
            stock_code=signal.stock_code,
            side=OrderSide.BUY.value,
            order_type=order_type,
            status=OrderStatus.SUBMITTED.value if result.success else OrderStatus.REJECTED.value,
            price=signal.current_price,
            quantity=quantity,
            broker_order_id=result.broker_order_id,
            reject_reason=result.error_message,
            created_at=now,
            submitted_at=now if result.success else None,
        )
        self.repo.create_order(order_record)

        # ── Step 6: 알림 발송 ──
        if result.success:
            signal_desc = "+".join(signal.primary_signals + signal.confirmation_filters)
            self.notifier.send_message(
                f"📈 매수 주문 | {signal.stock_name} | "
                f"{quantity}주 × {signal.current_price:,.0f}원 | "
                f"시그널: {signal_desc}"
            )
            self.repo.log_trade_event(
                TradeEventType.ORDER_SUBMITTED.value,
                position_id=position.position_id,
                stock_code=signal.stock_code,
                detail={"order_id": order_id, "broker_id": result.broker_order_id},
            )
        else:
            self.pos_mgr.cancel_position(position.position_id)
            logger.error("Buy order failed | stock=%s | error=%s",
                         signal.stock_code, result.error_message)

        return result

    # ══════════════════════════════════════════
    # 매도 주문 (UC-04)
    # ══════════════════════════════════════════

    def execute_sell(self, exit_signal: ExitSignal, position) -> Optional[OrderResult]:
        """
        매도 주문을 실행한다 (UC-04 기본 흐름).
        
        손절/익절/트레일링: 시장가 즉시
        데드크로스/보유초과: 지정가
        """
        order_id = str(uuid.uuid4())[:12]

        order_req = OrderRequest(
            order_id=order_id,
            position_id=exit_signal.position_id,
            stock_code=exit_signal.stock_code,
            stock_name=exit_signal.stock_name,
            side=OrderSide.SELL.value,
            order_type=exit_signal.order_type,
            price=exit_signal.current_price if exit_signal.order_type == "LIMIT" else None,
            quantity=position.quantity,
        )

        result = self._send_order_with_retry(order_req)

        # 주문 DB 기록
        now = datetime.now().isoformat()
        order_record = Order(
            order_id=order_id,
            position_id=exit_signal.position_id,
            stock_code=exit_signal.stock_code,
            side=OrderSide.SELL.value,
            order_type=exit_signal.order_type,
            status=OrderStatus.SUBMITTED.value if result.success else OrderStatus.REJECTED.value,
            price=exit_signal.current_price,
            quantity=position.quantity,
            broker_order_id=result.broker_order_id,
            created_at=now,
            submitted_at=now if result.success else None,
        )
        self.repo.create_order(order_record)

        if result.success:
            self.pos_mgr.start_closing(exit_signal.position_id, exit_signal)

            reason_emoji = {
                "ES1": "🔴 손절", "ES2": "🟢 익절", "ES3": "🟡 트레일링",
                "ES4": "🔵 데드크로스", "ES5": "⚪ 보유초과",
            }
            emoji = reason_emoji.get(exit_signal.exit_type, "매도")

            self.notifier.send_message(
                f"📉 {emoji} | {exit_signal.stock_name} | "
                f"{position.quantity}주 | "
                f"손익: {exit_signal.pnl_pct:+.2%}",
                level="WARNING" if exit_signal.exit_type == "ES1" else "INFO",
            )
        else:
            logger.error("Sell order failed | stock=%s | error=%s",
                         exit_signal.stock_code, result.error_message)
            # 손절 실패 시 즉시 시장가 재시도 (NFR-A03)
            if exit_signal.exit_type == "ES1":
                logger.critical("STOP LOSS order failed - retrying with MARKET")
                order_req.order_type = OrderType.MARKET.value
                order_req.price = None
                result = self._send_order_with_retry(order_req, max_retry=10)

        return result

    # ══════════════════════════════════════════
    # 미체결 주문 처리
    # ══════════════════════════════════════════

    def check_pending_orders(self):
        """
        미체결 주문을 확인하고 처리한다.
        - 매수: 30분 초과 시 취소 (BR-B06)
        - 매도: 15분 초과 시 시장가 재주문 (BR-S05)
        """
        pending_orders = self.repo.get_pending_orders()
        now = datetime.now()

        for order in pending_orders:
            if not order.broker_order_id:
                continue

            # 체결 상태 확인
            try:
                status_resp = self.broker.get_order_status(order.broker_order_id)
            except Exception as e:
                logger.warning("Order status check failed | order=%s | error=%s", order.order_id, e)
                continue

            if status_resp.status == "FILLED":
                self._handle_filled_order(order, status_resp)
                continue

            # 미체결 타임아웃 체크
            submitted = datetime.fromisoformat(order.submitted_at) if order.submitted_at else now
            elapsed_min = (now - submitted).total_seconds() / 60

            if order.side == OrderSide.BUY.value:
                if elapsed_min >= self.oc.buy_timeout_min:
                    logger.info("Buy order timeout | order=%s | elapsed=%.1fmin", order.order_id, elapsed_min)
                    self.broker.cancel_order(order.broker_order_id)
                    self.repo.update_order(
                        order.order_id,
                        status=OrderStatus.CANCELLED.value,
                        cancelled_at=now.isoformat(),
                    )
                    self.pos_mgr.cancel_position(order.position_id)
            else:  # SELL
                if elapsed_min >= self.oc.sell_timeout_min:
                    logger.info("Sell order timeout → MARKET re-order | order=%s", order.order_id)
                    self.broker.cancel_order(order.broker_order_id)
                    self.repo.update_order(
                        order.order_id,
                        status=OrderStatus.CANCELLED.value,
                        cancelled_at=now.isoformat(),
                    )
                    # 시장가 재주문 (BR-S05)
                    new_order = OrderRequest(
                        order_id=str(uuid.uuid4())[:12],
                        position_id=order.position_id,
                        stock_code=order.stock_code,
                        stock_name="",
                        side=OrderSide.SELL.value,
                        order_type=OrderType.MARKET.value,
                        quantity=order.quantity - order.filled_quantity,
                    )
                    self._send_order_with_retry(new_order)

    def _handle_filled_order(self, order, status_resp):
        """체결된 주문을 처리한다."""
        self.repo.update_order(
            order.order_id,
            status=OrderStatus.FILLED.value,
            filled_quantity=status_resp.filled_quantity,
            filled_price=status_resp.filled_price,
            filled_amount=status_resp.filled_amount,
            filled_at=datetime.now().isoformat(),
        )

        if order.side == OrderSide.BUY.value:
            self.pos_mgr.activate_position(
                order.position_id,
                filled_price=status_resp.filled_price,
                filled_quantity=status_resp.filled_quantity,
            )
            self.notifier.send_message(
                f"✅ 매수 체결 | {order.stock_code} | "
                f"{status_resp.filled_quantity}주 × {status_resp.filled_price:,.0f}원"
            )
        else:
            pos = self.repo.get_position(order.position_id)
            exit_reason = pos.exit_reason if pos else "UNKNOWN"
            self.pos_mgr.close_position(
                order.position_id,
                exit_price=status_resp.filled_price,
                exit_reason=exit_reason,
            )

    # ══════════════════════════════════════════
    # 내부 유틸
    # ══════════════════════════════════════════

    def _send_order_with_retry(
        self, order_req: OrderRequest, max_retry: int = None
    ) -> OrderResult:
        """주문을 재시도 로직과 함께 전송한다 (BR-O05)."""
        retries = max_retry or self.oc.max_retry

        for attempt in range(1, retries + 1):
            try:
                result = self.broker.place_order(order_req)
                if result.success:
                    return result
            except OrderRejectedError as e:
                logger.error("Order rejected (no retry) | %s", e)
                return OrderResult(
                    success=False,
                    order_id=order_req.order_id,
                    error_message=str(e),
                )
            except OrderError as e:
                logger.warning(
                    "Order attempt %d/%d failed | %s", attempt, retries, e
                )
                if attempt < retries:
                    time.sleep(self.oc.retry_interval_sec)

        return OrderResult(
            success=False,
            order_id=order_req.order_id,
            error_message=f"Max retries ({retries}) exceeded",
        )
