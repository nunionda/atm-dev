"""
ATS 공용 데이터 클래스
문서: ATS-SAD-001 §12.1
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional, List


# ──────────────────────────────────────────────
# 시세 데이터
# ──────────────────────────────────────────────

@dataclass
class PriceData:
    """현재가 정보"""
    stock_code: str
    stock_name: str
    current_price: float
    open_price: float
    high_price: float
    low_price: float
    prev_close: float
    volume: int
    change_pct: float
    timestamp: str


@dataclass
class OHLCV:
    """일봉 데이터 1행"""
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int


# ──────────────────────────────────────────────
# 시그널
# ──────────────────────────────────────────────

@dataclass
class Signal:
    """매수 시그널 결과 (SAD §5.2)"""
    stock_code: str
    stock_name: str
    signal_type: str = "BUY"
    primary_signals: List[str] = field(default_factory=list)
    confirmation_filters: List[str] = field(default_factory=list)
    strength: int = 0
    current_price: float = 0.0
    bb_upper: float = 0.0          # RG4 체크용
    timestamp: str = ""

    def __post_init__(self):
        self.strength = len(self.primary_signals) + len(self.confirmation_filters)
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


@dataclass
class ExitSignal:
    """청산 시그널 결과 (SAD §5.2)"""
    stock_code: str
    stock_name: str
    position_id: str
    exit_type: str               # "ES1" ~ "ES5"
    exit_reason: str             # "STOP_LOSS", "TAKE_PROFIT", ...
    order_type: str              # "MARKET" | "LIMIT"
    current_price: float = 0.0
    pnl_pct: float = 0.0
    metadata: dict = field(default_factory=dict)
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


@dataclass
class FuturesSignal:
    """선물 매매 시그널"""
    ticker: str = ""
    direction: str = "NEUTRAL"
    signal_strength: float = 0.0
    entry_price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    atr: float = 0.0
    z_score: float = 0.0
    primary_signals: List[str] = field(default_factory=list)
    confirmation_filters: List[str] = field(default_factory=list)
    risk_reward_ratio: float = 0.0
    position_size_contracts: int = 0
    metadata: dict = field(default_factory=dict)
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


# ──────────────────────────────────────────────
# 주문
# ──────────────────────────────────────────────

@dataclass
class OrderRequest:
    """주문 요청"""
    order_id: str
    position_id: str
    stock_code: str
    stock_name: str
    side: str                    # "BUY" | "SELL"
    order_type: str              # "MARKET" | "LIMIT"
    price: Optional[float] = None
    quantity: int = 0


@dataclass
class OrderResult:
    """주문 결과"""
    success: bool
    order_id: str
    broker_order_id: Optional[str] = None
    filled_price: Optional[float] = None
    filled_quantity: int = 0
    error_message: Optional[str] = None


@dataclass
class OrderStatusResponse:
    """체결 상태 응답"""
    broker_order_id: str
    status: str                  # "FILLED", "PARTIALLY_FILLED", "SUBMITTED", ...
    filled_quantity: int = 0
    filled_price: float = 0.0
    filled_amount: float = 0.0


# ──────────────────────────────────────────────
# 포트폴리오
# ──────────────────────────────────────────────

@dataclass
class Portfolio:
    """포트폴리오 현황 (SAD §12.1)"""
    total_capital: float = 0.0
    cash_balance: float = 0.0
    active_count: int = 0
    daily_buy_amount: float = 0.0
    daily_pnl: float = 0.0
    total_value: float = 0.0
    unrealized_pnl: float = 0.0
    mdd: float = 0.0
    peak_value: float = 0.0
    today_sold_codes: List[str] = field(default_factory=list)
    position_weights: Dict[str, float] = field(default_factory=dict)  # stock_code → 현재 비중


# ──────────────────────────────────────────────
# 리스크
# ──────────────────────────────────────────────

@dataclass
class RiskCheckResult:
    """리스크 게이트 체크 결과 (SAD §5.3)"""
    passed: bool
    failed_gate: Optional[str] = None
    reason: Optional[str] = None


# ──────────────────────────────────────────────
# 잔고
# ──────────────────────────────────────────────

@dataclass
class Balance:
    """계좌 잔고"""
    cash: float                  # 예수금
    total_eval: float            # 평가금 총액
    total_pnl: float             # 평가손익 총액
    total_pnl_pct: float         # 평가손익률
    positions: List[BalancePosition] = field(default_factory=list)


@dataclass
class BalancePosition:
    """잔고 내 보유 종목"""
    stock_code: str
    stock_name: str
    quantity: int
    avg_price: float
    current_price: float
    eval_amount: float
    pnl: float
    pnl_pct: float


# ──────────────────────────────────────────────
# 리포트
# ──────────────────────────────────────────────

@dataclass
class DailyReportData:
    """일일 리포트 데이터 (SAD §10.5)"""
    trade_date: str
    buy_count: int = 0
    sell_count: int = 0
    buy_amount: float = 0.0
    sell_amount: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    total_pnl: float = 0.0
    daily_return: float = 0.0
    cumulative_return: float = 0.0
    active_positions: int = 0
    cash_balance: float = 0.0
    total_value: float = 0.0
    mdd: float = 0.0
    win_count: int = 0
    lose_count: int = 0
