"""
백테스트용 시뮬레이션 브로커

BaseBroker 인터페이스를 구현하여 종가 기반 즉시 체결을 시뮬레이션한다.
- 주문은 당일 종가에 즉시 체결
- 현금 차감/가산을 추적
- 미래 데이터 접근을 차단 (current_date 기준)
"""

from __future__ import annotations

import uuid
from typing import Dict, List, Optional

import pandas as pd

from common.enums import OrderSide
from common.types import (
    Balance,
    BalancePosition,
    OrderRequest,
    OrderResult,
    OrderStatusResponse,
    PriceData,
)
from infra.broker.base import BaseBroker
from infra.logger import get_logger

logger = get_logger("backtest.sim_broker")


class SimulatedBroker(BaseBroker):
    """
    백테스트 전용 브로커.
    엔진이 매일 set_current_date() + set_market_data()를 호출하면
    그 날의 종가 기반으로 주문을 즉시 체결한다.
    """

    def __init__(self, initial_capital: float):
        self.initial_capital = initial_capital
        self.cash = initial_capital

        # 보유 종목: {stock_code: {"quantity": int, "avg_price": float, "stock_name": str}}
        self.holdings: Dict[str, dict] = {}

        # 엔진이 매일 갱신
        self.current_date: str = ""
        # {stock_code: {"open": ..., "high": ..., "low": ..., "close": ..., "volume": ...}}
        self.current_bar: Dict[str, dict] = {}
        # 전체 OHLCV DataFrame: {stock_code: DataFrame}
        self.ohlcv_data: Dict[str, pd.DataFrame] = {}

        # 체결 기록 (order_id → OrderResult)
        self._filled_orders: Dict[str, OrderResult] = {}

    # ─── 엔진이 호출하는 설정 메서드 ───

    def set_current_date(self, date: str):
        """시뮬레이션 현재 날짜를 설정한다 (YYYYMMDD)."""
        self.current_date = date

    def set_market_data(self, ohlcv_map: Dict[str, pd.DataFrame]):
        """전체 OHLCV 데이터를 설정한다."""
        self.ohlcv_data = ohlcv_map

    def update_current_prices(self):
        """current_date의 바 데이터를 current_bar에 캐싱한다."""
        self.current_bar = {}
        for code, df in self.ohlcv_data.items():
            row = df[df["date"] == self.current_date]
            if not row.empty:
                r = row.iloc[0]
                self.current_bar[code] = {
                    "open": float(r["open"]),
                    "high": float(r["high"]),
                    "low": float(r["low"]),
                    "close": float(r["close"]),
                    "volume": int(r["volume"]),
                }

    # ─── BaseBroker 인터페이스 구현 ───

    def authenticate(self) -> str:
        return "simulated_token"

    def is_token_valid(self) -> bool:
        return True

    def get_price(self, stock_code: str) -> PriceData:
        """현재 날짜의 종가를 반환한다."""
        bar = self.current_bar.get(stock_code)
        if not bar:
            return PriceData(
                stock_code=stock_code, stock_name=stock_code,
                current_price=0.0, open_price=0.0, high_price=0.0,
                low_price=0.0, prev_close=0.0, volume=0,
                change_pct=0.0, timestamp=self.current_date,
            )

        prev_close = self._get_prev_close(stock_code)
        change_pct = (bar["close"] - prev_close) / prev_close if prev_close > 0 else 0.0

        return PriceData(
            stock_code=stock_code,
            stock_name=stock_code,
            current_price=bar["close"],
            open_price=bar["open"],
            high_price=bar["high"],
            low_price=bar["low"],
            prev_close=prev_close,
            volume=bar["volume"],
            change_pct=change_pct,
            timestamp=self.current_date,
        )

    def get_ohlcv(self, stock_code: str, period: int = 60) -> pd.DataFrame:
        """current_date까지의 OHLCV를 반환한다 (미래 데이터 차단)."""
        df = self.ohlcv_data.get(stock_code)
        if df is None or df.empty:
            return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])

        # 미래 데이터 차단
        mask = df["date"] <= self.current_date
        filtered = df[mask].copy()

        # period만큼만 반환
        if len(filtered) > period:
            filtered = filtered.tail(period)

        return filtered.reset_index(drop=True)

    def place_order(self, order: OrderRequest) -> OrderResult:
        """종가에 즉시 체결한다."""
        bar = self.current_bar.get(order.stock_code)
        if not bar:
            return OrderResult(
                success=False,
                order_id=order.order_id,
                error_message=f"No market data for {order.stock_code} on {self.current_date}",
            )

        fill_price = bar["close"]
        fill_amount = fill_price * order.quantity

        if order.side == OrderSide.BUY.value:
            if fill_amount > self.cash:
                return OrderResult(
                    success=False,
                    order_id=order.order_id,
                    error_message=f"Insufficient cash: need {fill_amount:.0f}, have {self.cash:.0f}",
                )
            self.cash -= fill_amount
            # 보유 종목 갱신
            if order.stock_code in self.holdings:
                h = self.holdings[order.stock_code]
                total_qty = h["quantity"] + order.quantity
                total_cost = h["avg_price"] * h["quantity"] + fill_amount
                h["avg_price"] = total_cost / total_qty
                h["quantity"] = total_qty
            else:
                self.holdings[order.stock_code] = {
                    "quantity": order.quantity,
                    "avg_price": fill_price,
                    "stock_name": order.stock_name or order.stock_code,
                }
        else:  # SELL
            h = self.holdings.get(order.stock_code)
            if not h or h["quantity"] < order.quantity:
                return OrderResult(
                    success=False,
                    order_id=order.order_id,
                    error_message=f"Insufficient holdings for {order.stock_code}",
                )
            self.cash += fill_amount
            h["quantity"] -= order.quantity
            if h["quantity"] == 0:
                del self.holdings[order.stock_code]

        broker_order_id = f"SIM-{uuid.uuid4().hex[:8]}"
        result = OrderResult(
            success=True,
            order_id=order.order_id,
            broker_order_id=broker_order_id,
            filled_price=fill_price,
            filled_quantity=order.quantity,
        )
        self._filled_orders[broker_order_id] = result
        return result

    def cancel_order(self, broker_order_id: str) -> bool:
        return True

    def get_order_status(self, broker_order_id: str) -> OrderStatusResponse:
        """즉시 체결이므로 항상 FILLED."""
        result = self._filled_orders.get(broker_order_id)
        if result:
            return OrderStatusResponse(
                broker_order_id=broker_order_id,
                status="FILLED",
                filled_quantity=result.filled_quantity,
                filled_price=result.filled_price or 0.0,
                filled_amount=(result.filled_price or 0.0) * result.filled_quantity,
            )
        return OrderStatusResponse(
            broker_order_id=broker_order_id,
            status="FILLED",
        )

    def get_balance(self) -> Balance:
        """현금 + 보유종목 평가를 반환한다."""
        positions: List[BalancePosition] = []
        total_eval = 0.0
        total_pnl = 0.0

        for code, h in self.holdings.items():
            bar = self.current_bar.get(code)
            current_price = bar["close"] if bar else h["avg_price"]
            eval_amount = current_price * h["quantity"]
            pnl = (current_price - h["avg_price"]) * h["quantity"]
            pnl_pct = (current_price - h["avg_price"]) / h["avg_price"] if h["avg_price"] > 0 else 0.0

            total_eval += eval_amount
            total_pnl += pnl

            positions.append(BalancePosition(
                stock_code=code,
                stock_name=h.get("stock_name", code),
                quantity=h["quantity"],
                avg_price=h["avg_price"],
                current_price=current_price,
                eval_amount=eval_amount,
                pnl=pnl,
                pnl_pct=pnl_pct,
            ))

        total_value = self.cash + total_eval
        total_pnl_pct = total_pnl / (total_value - total_pnl) if (total_value - total_pnl) > 0 else 0.0

        return Balance(
            cash=self.cash,
            total_eval=total_eval,
            total_pnl=total_pnl,
            total_pnl_pct=total_pnl_pct,
            positions=positions,
        )

    # ─── 내부 유틸 ───

    def _get_prev_close(self, stock_code: str) -> float:
        """전일 종가를 반환한다."""
        df = self.ohlcv_data.get(stock_code)
        if df is None or df.empty:
            return 0.0
        past = df[df["date"] < self.current_date]
        if past.empty:
            return 0.0
        return float(past.iloc[-1]["close"])
