"""
ATS 공통 데이터 타입 정의
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class PriceData:
    stock_code: str
    stock_name: str
    current_price: float
    open_price: float = 0.0
    high_price: float = 0.0
    low_price: float = 0.0
    prev_close: float = 0.0
    volume: int = 0
    change_pct: float = 0.0
    timestamp: str = ""


@dataclass
class Signal:
    stock_code: str
    stock_name: str
    signal_type: str = "BUY"
    primary_signals: List[str] = field(default_factory=list)
    confirmation_filters: List[str] = field(default_factory=list)
    current_price: float = 0.0
    bb_upper: float = float("inf")
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def strength(self) -> int:
        return len(self.primary_signals) + len(self.confirmation_filters)


@dataclass
class FuturesSignal:
    """선물 매매 신호 데이터."""
    ticker: str
    direction: str  # "LONG" or "SHORT"
    signal_strength: float  # 0-100
    entry_price: float
    stop_loss: float
    take_profit: float
    atr: float
    z_score: float = 0.0
    primary_signals: List[str] = field(default_factory=list)
    confirmation_filters: List[str] = field(default_factory=list)
    risk_reward_ratio: float = 0.0
    position_size_contracts: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: dict = field(default_factory=dict)


@dataclass
class ExitSignal:
    stock_code: str
    stock_name: str
    position_id: str = ""
    exit_type: str = ""
    exit_reason: str = ""
    order_type: str = "MARKET"
    current_price: float = 0.0
    pnl_pct: float = 0.0
    metadata: dict = field(default_factory=dict)


@dataclass
class Portfolio:
    total_capital: float = 0.0
    cash_balance: float = 0.0
    active_count: int = 0
    daily_pnl: float = 0.0
    daily_buy_amount: float = 0.0
    mdd: float = 0.0
    today_sold_codes: List[str] = field(default_factory=list)


@dataclass
class RiskCheckResult:
    passed: bool = True
    failed_gate: Optional[str] = None
    reason: Optional[str] = None
