"""
Simulation engine Pydantic models.
Frontend TypeScript 인터페이스와 1:1 매칭.
Extracted from engine.py for modularity (C2 decomposition).
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class SimSystemState(BaseModel):
    status: str = "STOPPED"
    mode: str = "PAPER"
    started_at: Optional[str] = None
    market_phase: str = "CLOSED"
    market_regime: str = "NEUTRAL"  # BULL / BEAR / NEUTRAL (Phase 0)
    next_scan_at: Optional[str] = None
    total_equity: float = 0
    cash: float = 0
    invested: float = 0
    daily_pnl: float = 0
    daily_pnl_pct: float = 0
    position_count: int = 0
    max_positions: int = 10


class SimPosition(BaseModel):
    id: str
    stock_code: str
    stock_name: str
    status: str  # PENDING | ACTIVE | CLOSING | CLOSED
    quantity: int
    entry_price: float
    current_price: float
    pnl: float
    pnl_pct: float
    stop_loss: float
    take_profit: float
    trailing_stop: float
    highest_price: float
    entry_date: str
    days_held: int
    max_holding_days: int = 30
    weight_pct: float
    trailing_activated: bool = False
    side: str = "LONG"                    # "LONG" | "SHORT" (Arbitrage 양방향)
    lowest_price: float = 0.0             # Short 트레일링용 최저가 추적
    pair_id: Optional[str] = None         # Arbitrage 페어 연결 ID
    strategy_tag: str = "momentum"        # 진입 시 활성 전략 태그 (exit 라우팅용)
    scale_count: int = 0                   # 피라미딩 횟수 (max 1)
    avg_entry_price: float = 0.0           # 가중평균 매입가 (스케일업 시 사용)
    entry_signal_strength: int = 0         # 진입 시그널 강도 (0-100)
    entry_regime: str = ""                 # 진입 시 시장 레짐 (BULL/NEUTRAL/BEAR/RANGE_BOUND)
    entry_trend_strength: str = ""         # 추세 강도 (STRONG/MODERATE/WEAK)
    disparity_sold: bool = False           # BULL 이격도 부분 청산 완료 여부
    stock_regime: str = ""                 # 진입 시 종목 개별 레짐 (STRONG_BULL~CRISIS)


class SimOrder(BaseModel):
    id: str
    stock_code: str
    stock_name: str
    side: str  # BUY | SELL
    order_type: str  # LIMIT | MARKET
    status: str  # PENDING | FILLED | CANCELLED
    price: float
    filled_price: Optional[float] = None
    quantity: int
    filled_quantity: int = 0
    created_at: str
    filled_at: Optional[str] = None
    reason: str


class SimSignal(BaseModel):
    id: str
    stock_code: str
    stock_name: str
    type: str  # BUY | SELL
    price: float
    reason: str
    strength: int
    detected_at: str


class SimRiskMetrics(BaseModel):
    daily_pnl_pct: float = 0
    daily_loss_limit: float = -5.0
    mdd: float = 0
    mdd_limit: float = -15.0
    cash_ratio: float = 100.0
    min_cash_ratio: float = 30.0
    consecutive_stops: int = 0
    max_consecutive_stops: int = 3
    daily_trade_amount: float = 0
    max_daily_trade_amount: float = 30_000_000
    is_trading_halted: bool = False
    halt_reason: Optional[str] = None


class SimTradeRecord(BaseModel):
    id: str
    stock_code: str
    stock_name: str
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    quantity: int
    pnl: float
    pnl_pct: float
    exit_reason: str
    holding_days: int
    strategy_tag: str = "momentum"
    entry_signal_strength: int = 0         # 진입 시그널 강도 (0-100)
    entry_regime: str = ""                 # 진입 시 시장 레짐
    entry_trend_strength: str = ""         # 추세 강도
    stock_regime: str = ""                 # 진입 시 종목 개별 레짐


class SimEquityPoint(BaseModel):
    date: str
    equity: float
    drawdown_pct: float


class SimPerformanceSummary(BaseModel):
    total_return_pct: float = 0
    total_trades: int = 0
    win_rate: float = 0
    avg_win_pct: float = 0
    avg_loss_pct: float = 0
    profit_factor: float = 0
    sharpe_ratio: float = 0
    max_drawdown_pct: float = 0
    avg_holding_days: float = 0
    best_trade_pct: float = 0
    worst_trade_pct: float = 0
