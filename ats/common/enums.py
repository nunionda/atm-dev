"""
ATS 공통 열거형 정의
"""

from enum import Enum


class SystemState(Enum):
    INIT = "INIT"
    READY = "READY"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    ERROR = "ERROR"


class PositionStatus(Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"


class OrderSide(Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class ExitReason(Enum):
    STOP_LOSS = "ES1"
    TAKE_PROFIT = "ES2"
    TRAILING_STOP = "ES3"
    DEAD_CROSS = "ES4"
    MAX_HOLDING = "ES5"
    ATR_STOP_LOSS = "ES_ATR_SL"
    ATR_TAKE_PROFIT = "ES_ATR_TP"
    CHANDELIER_EXIT = "ES_CHANDELIER"
    CHOCH_REVERSAL = "ES_CHOCH"


class TradeEventType(Enum):
    ENTRY = "ENTRY"
    EXIT = "EXIT"
    SIGNAL = "SIGNAL"
    RISK_GATE = "RISK_GATE"


class FuturesDirection(Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NEUTRAL = "NEUTRAL"
