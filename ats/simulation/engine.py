"""
모의투자 시뮬레이션 엔진.
yfinance에서 실시간 가격을 가져오고, 모멘텀 스윙 전략 로직으로
가상 포지션/주문/시그널을 자동 생성한다.
전략 로직은 strategy/momentum_swing.py에서 간소화하여 복제.
"""

from __future__ import annotations

import asyncio
import math
import uuid
from datetime import datetime
from typing import Any, Callable, Coroutine, Dict, List, Optional

import numpy as np
import pandas as pd
from pydantic import BaseModel

# ── Pydantic Models (프론트엔드 TypeScript 인터페이스와 1:1 매칭) ──


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


# ── 워치리스트 ──

WATCHLIST = [
    {"code": "005930", "ticker": "005930.KS", "name": "삼성전자"},
    {"code": "000660", "ticker": "000660.KS", "name": "SK하이닉스"},
    {"code": "005380", "ticker": "005380.KS", "name": "현대자동차"},
    {"code": "035420", "ticker": "035420.KS", "name": "NAVER"},
    {"code": "051910", "ticker": "051910.KS", "name": "LG화학"},
    {"code": "006400", "ticker": "006400.KS", "name": "삼성SDI"},
    {"code": "003670", "ticker": "003670.KS", "name": "포스코퓨처엠"},
    {"code": "105560", "ticker": "105560.KS", "name": "KB금융"},
    {"code": "055550", "ticker": "055550.KS", "name": "신한지주"},
    {"code": "066570", "ticker": "066570.KS", "name": "LG전자"},
]

OnEventType = Callable[[str, Any], Coroutine[Any, Any, None]]

# ── Phase별 시장 체제 파라미터 (6단계: STRONG_BULL ~ CRISIS) ──
REGIME_PARAMS = {
    "STRONG_BULL": {"max_positions": 10, "max_weight": 0.15},
    "BULL":        {"max_positions": 10, "max_weight": 0.15},
    "NEUTRAL":     {"max_positions": 6,  "max_weight": 0.12},
    "RANGE_BOUND": {"max_positions": 4,  "max_weight": 0.08},
    "BEAR":        {"max_positions": 2,  "max_weight": 0.05},
    "CRISIS":      {"max_positions": 1,  "max_weight": 0.05},
}

# ── 종목별 레짐 분류 임계값 (0-100 복합 스코어 → 5단계) ──
STOCK_REGIME_THRESHOLDS: list = [
    # (min_score, regime) — 내림차순 매칭 (5단계)
    (72, "STRONG_BULL"),   # Was 80 — capture more uptrending stocks
    (55, "BULL"),          # Was 60 — wider bull band
    (40, "NEUTRAL"),       # Was 45 — narrower neutral (was 83% clustering here)
    (25, "BEAR"),          # Merges old RANGE_BOUND + BEAR
    (0,  "STRONG_BEAR"),   # Merges old BEAR + CRISIS
]

# ── 종목 레짐 레벨 (스무딩용: 2+ 레벨 하락 → 즉시 적용) ──
_STOCK_REGIME_LEVEL = {
    "STRONG_BULL": 4, "BULL": 3, "NEUTRAL": 2, "BEAR": 1, "STRONG_BEAR": 0
}

# ── 종목별 레짐 → 전략 스캔 친화도 (0.0=스킵, 1.0=풀스캔) ──
STOCK_REGIME_STRATEGY_AFFINITY: Dict[str, Dict[str, float]] = {
    "STRONG_BULL": {"momentum": 1.0, "breakout_retest": 0.8, "smc": 0.5, "mean_reversion": 0.0, "defensive": 0.0},
    "BULL":        {"momentum": 0.8, "breakout_retest": 0.5, "smc": 0.6, "mean_reversion": 0.3, "defensive": 0.0},
    "NEUTRAL":     {"mean_reversion": 1.0, "smc": 0.5, "momentum": 0.0, "breakout_retest": 0.0, "defensive": 0.3},
    "BEAR":        {"defensive": 0.8, "mean_reversion": 0.5, "smc": 0.3, "momentum": 0.0, "breakout_retest": 0.0},
    "STRONG_BEAR": {"defensive": 1.0, "mean_reversion": 0.2, "momentum": 0.0, "breakout_retest": 0.0, "smc": 0.0},
}

# ── 체제별 청산 파라미터 ──
REGIME_EXIT_PARAMS = {
    "STRONG_BULL": {"max_holding": 40, "take_profit": 0.20, "trail_activation": 0.05},
    "BULL":        {"max_holding": 40, "take_profit": 0.20, "trail_activation": 0.05},
    "NEUTRAL":     {"max_holding": 25, "take_profit": 0.12, "trail_activation": 0.04},
    "RANGE_BOUND": {"max_holding": 15, "take_profit": 0.08, "trail_activation": 0.03},
    "BEAR":        {"max_holding": 15, "take_profit": 0.08, "trail_activation": 0.03},
    "CRISIS":      {"max_holding": 10, "take_profit": 0.05, "trail_activation": 0.02},
}

# ── 레짐별 전략 오버라이드 (Entry/Exit/Risk 모듈화) ──
# 기존 전략 메서드 내에서 self._market_regime을 확인하여 분기
# ── 레짐별 Kelly Fraction (포지션 사이징 근거) ──
# 기본 Half-Kelly(0.5) 대비 레짐별 공격도 조절
# STRONG_BULL=0.75 → CRISIS=0.25, 선형 보간 (step=0.10)
# effective_sizing = kelly_fraction / BASE_KELLY(0.5)
BASE_KELLY: float = 0.50  # 현물 기본 Half-Kelly

REGIME_OVERRIDES: Dict[str, Dict[str, Any]] = {
    "STRONG_BULL": {
        # Kelly: 3/4 Kelly → effective ×1.50
        "kelly_fraction": 0.75,
        # Entry: Donchian 돌파 추가, 피라미딩 허용
        "donchian_entry": True,        # 모멘텀에 Donchian 20d 돌파 시그널 추가
        "donchian_period": 20,
        "pyramiding_enabled": True,    # 추가 매수 허용 (모멘텀 전략)
        "pyramiding_max": 1,           # 최대 1회 추가 매수
        "pyramiding_pnl_min": 0.05,    # 수익 5% 이상일 때 피라미딩
        # Exit: 공격적 트레일링
        "trail_atr_mult": 2.0,         # 기본 3.0 → 2.0 (타이트)
        "trail_floor_pct": -0.04,      # 최소 바닥 -4%
        # Risk
        "min_cash_override": None,     # 기본 사용
    },
    "BULL": {
        # Kelly: 0.65 → effective ×1.30
        "kelly_fraction": 0.65,
        # Entry: 표준 (기존 유지)
        "donchian_entry": False,
        "pyramiding_enabled": False,
        # Exit: 이격도 부분 청산
        "disparity_partial_sell": True, # MA20 이격도 과대 시 50% 분할 청산
        "disparity_threshold": 1.15,    # 가격/MA20 > 115%
        "partial_sell_ratio": 0.5,      # 50% 청산
        # Risk
        "min_cash_override": None,
    },
    "NEUTRAL": {
        # Kelly: 0.55 → effective ×1.10
        "kelly_fraction": 0.55,
        # Entry: MR 강화 (ADX 필터 엄격)
        "mr_adx_limit": 22,            # 기본 25 → 22 (추세 약한 것만)
        # Exit: 공격적 시간감쇄
        "time_decay_enabled": True,
        "time_decay_days": 10,         # 10일 보유 + 수익 < 2% → 강제 청산
        "time_decay_pnl_min": 0.02,
        # Risk
        "min_cash_override": None,
    },
    "RANGE_BOUND": {
        # Kelly: 0.45 → effective ×0.90
        "kelly_fraction": 0.45,
        # Entry: 지지/저항 영역 활용
        "sr_zone_entry": True,         # S/R 영역 가격일 때만 MR 진입
        "sr_atr_buffer": 1.5,          # 지지선 ± 1.5×ATR 내
        # Exit: 박스 이탈 즉시 손절
        "box_breakout_exit": True,     # 박스 상단/하단 이탈 시 즉시 청산
        "box_lookback": 40,            # 40일 고가/저가 = 박스 범위
        # Risk
        "min_cash_override": None,
    },
    "BEAR": {
        # Kelly: 0.35 → effective ×0.70
        "kelly_fraction": 0.35,
        # Entry: 방어 강화
        "defensive_vix_threshold": 20, # 기본 25 → 20 (더 일찍 방어)
        # Exit: 빠른 청산
        "bear_exit_tighten": True,     # TP 축소, 보유기간 단축
        # Risk
        "min_cash_override": 0.50,     # 현금 50% 유지
    },
    "CRISIS": {
        # Kelly: 1/4 Kelly → effective ×0.50
        "kelly_fraction": 0.25,
        # Entry: 안전자산 스위칭
        "safe_haven_enabled": True,    # GLD, TLT 등 안전자산 편입
        "crisis_vix_threshold": 30,    # VIX > 30 → 최대 방어
        # Exit: 초빠른 청산
        "crisis_exit_immediate": True, # 비방어 포지션 즉시 청산
        # Risk
        "min_cash_override": 0.70,     # 현금 70% 유지
    },
}

# ── VIX 기반 포지션 사이징 스케일러 ──
VIX_SIZING_SCALE = {
    # (lower, upper): multiplier
    (0, 16): 1.0,       # 안정
    (16, 20): 0.9,      # 보통
    (20, 25): 0.8,      # 경계
    (25, 30): 0.6,      # 고변동
    (30, 100): 0.3,     # 공포 — 극소 사이징
}

# ── 레짐별 전략 비중 매핑 (멀티 전략 모드용) ──
# 레짐 표시명 ↔ primary 전략 1:1 매칭:
#   BULL → 추세추종 = momentum primary
#   NEUTRAL/RANGE → 평균회귀 = mean_reversion primary
#   BEAR → 하락방어 = defensive primary
# 주의: 이전 MR+Def 2전략 집중(Sharpe 2.51)에서 다전략 활성화로 변경
# 성능 변동 예상 → 반드시 2-year backtest 검증 후 production 적용
REGIME_STRATEGY_WEIGHTS: Dict[str, Dict[str, float]] = {
    # Fallback: 지수 데이터 부족 시 Phase 0 breadth 기반 레짐 사용
    "BULL":        {"momentum": 0.30, "smc": 0.15, "mean_reversion": 0.35, "defensive": 0.15, "breakout_retest": 0.05},
    "NEUTRAL":     {"mean_reversion": 0.60, "defensive": 0.25, "arbitrage": 0.10, "smc": 0.05},
    "RANGE_BOUND": {"mean_reversion": 0.55, "arbitrage": 0.20, "defensive": 0.20, "smc": 0.05},
    "BEAR":        {"defensive": 0.55, "volatility": 0.15, "mean_reversion": 0.25, "smc": 0.05},
}

# 지수 추세별 동적 전략 비중 — 표시명과 primary 전략 1:1 매칭
# _analyze_index_trend() 결과에 따라 REGIME_STRATEGY_WEIGHTS를 오버라이드
INDEX_TREND_STRATEGY_WEIGHTS: Dict[str, Dict[str, float]] = {
    # STRONG_BULL "공격적 추세추종": momentum primary (40%)
    # 강한 상승추세 → 모멘텀 breakout 매수 + BRT 돌파 리테스트
    "STRONG_BULL": {
        "momentum": 0.40,          # PRIMARY: 추세추종 (표시명 매칭)
        "breakout_retest": 0.20,   # 돌파 리테스트 (강한 추세에서 유효)
        "smc": 0.10,               # 스마트머니 구조 확인
        "mean_reversion": 0.20,    # 눌림목 매수
        "defensive": 0.10,         # 최소 헤지
    },
    # BULL "추세추종": momentum primary (30%)
    # 상승추세 → 추세 추종 + SMC 구조확인 + MR 눌림목
    "BULL": {
        "momentum": 0.30,          # PRIMARY: 추세추종 (표시명 매칭)
        "smc": 0.15,               # SMC 구조 확인
        "mean_reversion": 0.35,    # 눌림목 매수 (여전히 강한 알파)
        "defensive": 0.15,         # 적정 헤지
        "breakout_retest": 0.05,   # 소량 돌파 매매
    },
    # NEUTRAL "평균회귀": mean_reversion primary (60%)
    # 횡보 → 과매도 반등 매수 + 페어 차익거래
    "NEUTRAL": {
        "mean_reversion": 0.60,    # PRIMARY: 평균회귀 (표시명 매칭)
        "defensive": 0.25,         # 적정 헤지
        "arbitrage": 0.10,         # 페어 차익거래
        "smc": 0.05,               # 구조 필터
    },
    # BEAR "하락방어": defensive primary (55%)
    # 하락추세 → 인버스 ETF + VIX 프리미엄
    "BEAR": {
        "defensive": 0.55,         # PRIMARY: 인버스 헤지 (표시명 매칭)
        "volatility": 0.15,        # VIX 스파이크 역매매
        "mean_reversion": 0.25,    # 극단 과매도만
        "smc": 0.05,               # 구조 필터 (반전 감지)
    },
    # RANGE_BOUND "박스권 회귀": mean_reversion primary (55%)
    # 박스권 → 평균회귀 + 차익거래 강화
    "RANGE_BOUND": {
        "mean_reversion": 0.55,    # PRIMARY: 박스권 회귀 (표시명 매칭)
        "arbitrage": 0.20,         # 페어 차익거래 (박스권 유리)
        "defensive": 0.20,         # 적정 헤지
        "smc": 0.05,               # 구조 필터
    },
    # CRISIS "위기방어": defensive primary (85%)
    # 위기 → 자본 보존 최우선
    "CRISIS": {
        "defensive": 0.85,         # PRIMARY: 인버스 헤지 (표시명 매칭)
        "mean_reversion": 0.15,    # 최소 MR
    },
}

# 레짐별 전략 표시 이름 (프론트엔드 UI용)
# Multi 모드에서 현재 레짐에 맞는 전략명을 동적으로 표시
REGIME_DISPLAY_NAMES: Dict[str, Dict[str, str]] = {
    "STRONG_BULL": {"ko": "공격적 추세추종", "en": "Aggressive Trend Trail"},
    "BULL":        {"ko": "추세추종",       "en": "Trend Trail"},
    "NEUTRAL":     {"ko": "평균회귀",       "en": "Mean Reversion"},
    "RANGE_BOUND": {"ko": "박스권 회귀",    "en": "Range Reversion"},
    "BEAR":        {"ko": "하락방어",       "en": "Bear Shield"},
    "CRISIS":      {"ko": "위기방어",       "en": "Crisis Shield"},
}

# 개별 전략 표시 이름 (프론트엔드 UI용)
STRATEGY_DISPLAY_NAMES: Dict[str, Dict[str, str]] = {
    "multi":            {"ko": "적응형 알파",     "en": "Adaptive Alpha",       "desc": "레짐 적응형 동적 전략"},
    "momentum":         {"ko": "모멘텀 스윙",     "en": "Momentum Swing",       "desc": "6-Phase 추세추종 전략"},
    "smc":              {"ko": "스마트머니",       "en": "Smart Money",          "desc": "SMC 4-Layer 구조분석"},
    "mean_reversion":   {"ko": "평균회귀",        "en": "Mean Reversion",       "desc": "과매도 반등 매수 전략"},
    "arbitrage":        {"ko": "페어 차익거래",    "en": "Pairs Arbitrage",      "desc": "Z-Score 통계적 차익"},
    "breakout_retest":  {"ko": "돌파 리테스트",    "en": "Breakout Retest",      "desc": "돌파 후 되돌림 진입"},
    "defensive":        {"ko": "인버스 헤지",      "en": "Inverse Hedge",        "desc": "인버스 ETF 하락 방어"},
    "volatility":       {"ko": "변동성 프리미엄",   "en": "Vol Premium",         "desc": "VIX 스파이크 역매매"},
    # 레짐 전략 모드 표시 이름
    "regime_strong_bull": {"ko": "공격적 추세추종", "en": "Aggressive Trend Trail", "desc": "강세장 전용 · 모멘텀 주도 복합전략"},
    "regime_bull":        {"ko": "추세추종",       "en": "Trend Trail",            "desc": "상승추세 추종 · 모멘텀+MR 복합전략"},
    "regime_neutral":     {"ko": "평균회귀",       "en": "Mean Reversion",         "desc": "횡보장 전용 · 과매도 반등 복합전략"},
    "regime_range_bound": {"ko": "박스권 회귀",    "en": "Range Reversion",        "desc": "박스권 전용 · 차익거래 보조 복합전략"},
    "regime_bear":        {"ko": "하락방어",       "en": "Bear Shield",            "desc": "하락장 전용 · 인버스 헤지 복합전략"},
    "regime_crisis":      {"ko": "위기방어",       "en": "Crisis Shield",          "desc": "위기 전용 · 자본 보존 복합전략"},
}

# 레짐별 전략 구성 메타데이터 (프론트엔드 UI + 내부 문서화)
# 각 레짐의 표시 이름이 primary 전략과 1:1 매칭되도록 구성
REGIME_STRATEGY_COMPOSITION: Dict[str, Dict] = {
    "STRONG_BULL": {
        "primary": "momentum",
        "secondary": ["breakout_retest", "mean_reversion"],
        "filter": ["smc"],
        "hedge": ["defensive"],
        "rationale": {
            "ko": "강한 상승추세 → 모멘텀 추세추종 주력, 돌파매매 보조, MR 눌림목 매수",
            "en": "Strong uptrend → momentum primary, breakout secondary, MR dip-buying",
        },
    },
    "BULL": {
        "primary": "momentum",
        "secondary": ["smc", "mean_reversion"],
        "filter": [],
        "hedge": ["defensive"],
        "rationale": {
            "ko": "상승추세 → 모멘텀 주력, SMC 구조확인 보조, MR 눌림목 매수",
            "en": "Uptrend → momentum primary, SMC structure confirmation, MR dip-buying",
        },
    },
    "NEUTRAL": {
        "primary": "mean_reversion",
        "secondary": ["arbitrage"],
        "filter": ["smc"],
        "hedge": ["defensive"],
        "rationale": {
            "ko": "횡보 → 평균회귀 주력, 페어 차익거래 보조",
            "en": "Sideways → mean reversion primary, pairs arbitrage secondary",
        },
    },
    "RANGE_BOUND": {
        "primary": "mean_reversion",
        "secondary": ["arbitrage"],
        "filter": ["smc"],
        "hedge": ["defensive"],
        "rationale": {
            "ko": "박스권 → 평균회귀 주력, 페어 차익거래 보조",
            "en": "Range-bound → mean reversion primary, pairs arbitrage secondary",
        },
    },
    "BEAR": {
        "primary": "defensive",
        "secondary": ["volatility"],
        "filter": ["smc"],
        "hedge": [],
        "rationale": {
            "ko": "하락추세 → 인버스 헤지 주력, VIX 프리미엄 보조, 최소 MR",
            "en": "Downtrend → inverse hedge primary, VIX premium secondary, minimal MR",
        },
    },
    "CRISIS": {
        "primary": "defensive",
        "secondary": [],
        "filter": [],
        "hedge": [],
        "rationale": {
            "ko": "위기 → 인버스 헤지 최대, 자본 보존 최우선",
            "en": "Crisis → maximum inverse hedge, capital preservation priority",
        },
    },
}

# 인버스 ETF 유니버스 (Phase 3.3: Defensive 전략)
INVERSE_ETFS = {
    "sp500":  ["SH", "SDS"],         # ProShares Short S&P500, UltraShort S&P500
    "nasdaq": ["PSQ", "QID"],        # ProShares Short QQQ, UltraShort QQQ
    "kospi":  ["114800.KS", "252670.KS"],  # KODEX 인버스, KODEX 200선물인버스2X
}

# 안전자산 ETF 유니버스 (CRISIS 레짐 방어 전략)
SAFE_HAVEN_ETFS: Dict[str, List[Dict[str, str]]] = {
    "sp500": [
        {"ticker": "GLD", "name": "Gold ETF"},
        {"ticker": "TLT", "name": "US Treasury 20Y+"},
        {"ticker": "UUP", "name": "US Dollar Index"},
    ],
    "nasdaq": [
        {"ticker": "GLD", "name": "Gold ETF"},
        {"ticker": "TLT", "name": "US Treasury 20Y+"},
    ],
    "kospi": [
        {"ticker": "411060.KS", "name": "KODEX 미국달러선물"},
        {"ticker": "132030.KS", "name": "KODEX 골드선물"},
    ],
}

# 멀티 전략 모드 기본 전략 목록
MULTI_STRATEGIES = ["momentum", "smc", "breakout_retest", "mean_reversion", "defensive", "volatility", "arbitrage"]

# 레짐 전략 모드: 레짐 가중치 고정 + multi 파이프라인 재사용
# 각 모드는 특정 레짐의 전략 비중을 고정하여 실행 (적응형 알파의 개별 테스트용)
REGIME_STRATEGY_MODES: Dict[str, str] = {
    "regime_strong_bull": "STRONG_BULL",
    "regime_bull":        "BULL",
    "regime_neutral":     "NEUTRAL",
    "regime_range_bound": "RANGE_BOUND",
    "regime_bear":        "BEAR",
    "regime_crisis":      "CRISIS",
}


class StrategyAllocator:
    """
    멀티 전략 모드용 전략별 자본 배분 관리자.

    각 전략에 레짐 기반 비중을 할당하고, 전략별 포지션 수/자본 한도를 관리.
    물리적 현금 풀은 단일이지만, 가상 예산(virtual budget)으로 전략 간 자본을 분리.

    Phase 3 추가:
    - Correlation Control: 전략간 rolling corr 모니터링, corr>0.4 시 비중 조정
    - Dynamic Kelly: regime + VIX + 최근 승률 반영 Kelly × 0.25
    """

    def __init__(self, strategies: List[str], regime: str = "NEUTRAL"):
        self.strategies = strategies
        self.regime = regime
        self.weights: Dict[str, float] = {}
        # Volatility Targeting 상태
        self._daily_returns: List[float] = []
        self._target_vol: float = 0.15  # 연 15% 포트폴리오 변동성
        self._vol_scalar: float = 1.0   # target_vol / realized_vol
        self._prev_equity: float = 0.0
        # Phase 7: Risk Parity 상태
        self._rp_weights: Dict[str, float] = {}  # 전략별 RP 비중
        self._rp_warmup_done: bool = False  # 데이터 충분 여부
        # Correlation Control 상태 (Phase 3.1)
        self._strategy_daily_pnl: Dict[str, List[float]] = {s: [] for s in strategies}
        self._corr_matrix: Dict[tuple, float] = {}  # (s1, s2) → rolling corr
        self._corr_adjustment: Dict[str, float] = {}  # strategy → 비중 조정 승수
        # Dynamic Kelly 상태 (Phase 3.4)
        self._strategy_wins: Dict[str, int] = {s: 0 for s in strategies}
        self._strategy_losses: Dict[str, int] = {s: 0 for s in strategies}
        self._strategy_win_pnl: Dict[str, float] = {s: 0.0 for s in strategies}
        self._strategy_loss_pnl: Dict[str, float] = {s: 0.0 for s in strategies}
        self._kelly_scalar: float = 1.0
        self._vix_ema: float = 0.0
        self._apply_regime_weights(regime)

    def _apply_regime_weights(self, regime: str):
        """레짐에 맞는 전략 비중 적용 (correlation + Risk Parity 조정 반영)."""
        weights = REGIME_STRATEGY_WEIGHTS.get(regime, REGIME_STRATEGY_WEIGHTS["NEUTRAL"])
        raw = {s: weights.get(s, 0.0) for s in self.strategies}
        # Correlation 조정 적용
        if self._corr_adjustment:
            for s in raw:
                raw[s] *= self._corr_adjustment.get(s, 1.0)
            total = sum(raw.values())
            if total > 0:
                raw = {s: w / total for s, w in raw.items()}
        # Phase 7: Risk Parity 블렌딩 (비활성화 — 모든 비율에서 성능 저하 확인)
        # RP는 momentum(핵심 전략) 비중을 과도하게 축소하여 net alpha 감소
        # if self._rp_warmup_done and self._rp_weights:
        #     blended = {}
        #     for s in self.strategies:
        #         regime_w = raw.get(s, 0.0)
        #         rp_w = self._rp_weights.get(s, regime_w)
        #         blended[s] = 0.90 * regime_w + 0.10 * rp_w
        #     total = sum(blended.values())
        #     if total > 0:
        #         raw = {s: w / total for s, w in blended.items()}
        self.weights = raw

    def update_regime(self, regime: str):
        """레짐 변경 시 비중 갱신."""
        if regime != self.regime:
            self.regime = regime
            self._apply_regime_weights(regime)

    def override_weights(self, weights: Dict[str, float]):
        """지수 추세 기반 전략 비중 오버라이드.

        INDEX_TREND_STRATEGY_WEIGHTS에서 받은 비중으로 교체.
        활성 전략에 없는 전략은 무시하고 나머지를 정규화.
        Correlation 조정도 적용.
        """
        active_weights = {}
        for strat, w in weights.items():
            if strat in self.strategies:
                active_weights[strat] = w

        if not active_weights:
            return  # 유효한 전략 없으면 무시

        # Correlation 조정 적용
        if self._corr_adjustment:
            for s in active_weights:
                active_weights[s] *= self._corr_adjustment.get(s, 1.0)

        # 정규화 (합 = 1.0)
        total = sum(active_weights.values())
        if total > 0:
            self.weights = {s: w / total for s, w in active_weights.items()}

    def is_active(self, strategy: str) -> bool:
        """해당 전략이 현재 레짐에서 활성인지."""
        return self.weights.get(strategy, 0.0) > 0.01

    def get_budget(self, strategy: str, total_equity: float, used_by_strategy: float) -> float:
        """전략의 남은 가용 자본 (가상 예산)."""
        weight = self.weights.get(strategy, 0.0)
        budget = total_equity * weight
        return max(0.0, budget - used_by_strategy)

    def get_max_positions(self, strategy: str, regime_max: int) -> int:
        """전략별 최대 포지션 수 (Largest Remainder Method)."""
        dist = self.distribute_positions(regime_max)
        return dist.get(strategy, 1)

    def distribute_positions(self, regime_max: int) -> Dict[str, int]:
        """Largest Remainder Method로 포지션 수 공정 분배.

        Phase 4.2: round() 대신 LRM 사용 — 저비중 전략 굶주림 해결.
        합계가 regime_max를 초과하지 않도록 보장.
        """
        active = {s: w for s, w in self.weights.items() if w > 0.01}
        if not active:
            return {}
        raw = {s: regime_max * w for s, w in active.items()}
        floors = {s: int(v) for s, v in raw.items()}
        remainders = {s: raw[s] - floors[s] for s in active}
        leftover = regime_max - sum(floors.values())
        for s in sorted(remainders, key=lambda k: remainders[k], reverse=True):
            if leftover <= 0:
                break
            floors[s] += 1
            leftover -= 1
        return {s: max(1, v) for s, v in floors.items()}

    def get_max_weight_for_strategy(self, strategy: str, regime_max_weight: float) -> float:
        """전략별 종목당 최대 비중. 전략 비중이 작을수록 더 집중."""
        weight = self.weights.get(strategy, 0.0)
        if weight < 0.15:
            return regime_max_weight
        return regime_max_weight

    # ── Volatility Targeting ──

    def update_daily_return(self, total_equity: float):
        """일일 수익률 기록 및 변동성 스칼라 갱신."""
        if self._prev_equity > 0:
            daily_ret = (total_equity - self._prev_equity) / self._prev_equity
            self._daily_returns.append(daily_ret)
            if len(self._daily_returns) > 60:
                self._daily_returns = self._daily_returns[-60:]
            if len(self._daily_returns) >= 20:
                recent = self._daily_returns[-20:]
                realized_vol = float(np.std(recent)) * (252 ** 0.5)
                if realized_vol > 0.001:
                    self._vol_scalar = min(1.5, max(0.3, self._target_vol / realized_vol))
                else:
                    self._vol_scalar = 1.0
        self._prev_equity = total_equity

    def get_vol_scalar(self) -> float:
        """현재 변동성 타겟팅 스칼라 (0.3 ~ 1.5)."""
        return self._vol_scalar

    # ── Phase 7: Risk Parity ──

    def update_risk_parity(self):
        """전략별 실현 변동성의 역수에 비례하는 Risk Parity 비중 계산.

        전략별 일일 PnL의 비영 일(포지션 있는 날)만 사용.
        최소 10일 데이터 필요, 2개 이상 전략에 데이터 있어야 활성화.
        """
        active_vols: Dict[str, float] = {}
        for s in self.strategies:
            pnl_series = self._strategy_daily_pnl.get(s, [])
            # 비영 일만 (포지션 있는 날의 PnL)
            nonzero = [p for p in pnl_series[-60:] if abs(p) > 0.01]
            if len(nonzero) >= 10:
                vol = float(np.std(nonzero))
                active_vols[s] = max(vol, 0.001)

        if len(active_vols) < 2:
            self._rp_warmup_done = False
            return

        # 역변동성 비중
        inv_vols = {s: 1.0 / v for s, v in active_vols.items()}
        total_iv = sum(inv_vols.values())
        self._rp_weights = {s: iv / total_iv for s, iv in inv_vols.items()}
        self._rp_warmup_done = True

        # 비중 재적용
        self._apply_regime_weights(self.regime)

    # ── Correlation Control (Phase 3.1) ──

    def record_strategy_daily_pnl(self, strategy: str, daily_pnl: float):
        """전략별 일일 PnL 기록."""
        if strategy in self._strategy_daily_pnl:
            self._strategy_daily_pnl[strategy].append(daily_pnl)
            if len(self._strategy_daily_pnl[strategy]) > 60:
                self._strategy_daily_pnl[strategy] = self._strategy_daily_pnl[strategy][-60:]

    def update_correlation(self):
        """전략간 rolling correlation 계산 및 비중 조정.

        corr > 0.4 인 페어의 고상관 전략 비중 축소, 저상관 전략 비중 확대.
        20거래일 이상 데이터 필요.
        """
        active = [s for s in self.strategies if len(self._strategy_daily_pnl.get(s, [])) >= 20]
        if len(active) < 2:
            return

        # 페어별 correlation 계산
        high_corr_strategies = set()
        for i, s1 in enumerate(active):
            for s2 in active[i + 1:]:
                pnl1 = self._strategy_daily_pnl[s1][-20:]
                pnl2 = self._strategy_daily_pnl[s2][-20:]
                if np.std(pnl1) < 1e-10 or np.std(pnl2) < 1e-10:
                    corr = 0.0
                else:
                    corr = float(np.corrcoef(pnl1, pnl2)[0, 1])
                self._corr_matrix[(s1, s2)] = corr
                if corr > 0.4:
                    high_corr_strategies.add(s1)
                    high_corr_strategies.add(s2)

        # 비중 조정: 고상관 전략 0.8x, 저상관 전략 1.2x
        self._corr_adjustment = {}
        for s in self.strategies:
            if s in high_corr_strategies:
                self._corr_adjustment[s] = 0.8
            elif len(active) > 0 and s in active:
                self._corr_adjustment[s] = 1.2
            else:
                self._corr_adjustment[s] = 1.0

        # 비중 재적용
        self._apply_regime_weights(self.regime)

    def get_corr_matrix(self) -> Dict[tuple, float]:
        """현재 전략간 상관관계 매트릭스."""
        return self._corr_matrix.copy()

    # ── Dynamic Kelly (Phase 3.4) ──

    def record_trade_result(self, strategy: str, pnl_pct: float):
        """전략별 거래 결과 기록 (Kelly 동적 조정용)."""
        if strategy not in self._strategy_wins:
            return
        if pnl_pct > 0:
            self._strategy_wins[strategy] += 1
            self._strategy_win_pnl[strategy] += pnl_pct
        else:
            self._strategy_losses[strategy] += 1
            self._strategy_loss_pnl[strategy] += abs(pnl_pct)

    def update_kelly(self, vix_ema: float):
        """Dynamic Kelly 스칼라 갱신.

        Quarter-Kelly(0.25) 기반, regime + VIX + 최근 승률 반영.
        kelly_scalar = base(0.25) × regime_mult × vix_mult × performance_mult
        """
        self._vix_ema = vix_ema
        base_kelly = 0.25  # Quarter-Kelly

        # Regime 승수
        regime_mult = {"BULL": 1.2, "NEUTRAL": 1.0, "RANGE_BOUND": 0.8, "BEAR": 0.5}.get(self.regime, 1.0)

        # VIX 승수 (VIX 높을수록 보수적)
        if vix_ema <= 16:
            vix_mult = 1.1
        elif vix_ema <= 20:
            vix_mult = 1.0
        elif vix_ema <= 25:
            vix_mult = 0.8
        elif vix_ema <= 30:
            vix_mult = 0.6
        else:
            vix_mult = 0.4

        # 최근 성과 승수 (전체 전략 합산 승률)
        total_w = sum(self._strategy_wins.values())
        total_l = sum(self._strategy_losses.values())
        total_trades = total_w + total_l
        if total_trades >= 10:
            win_rate = total_w / total_trades
            if win_rate >= 0.45:
                perf_mult = 1.1
            elif win_rate >= 0.35:
                perf_mult = 1.0
            elif win_rate >= 0.25:
                perf_mult = 0.8
            else:
                perf_mult = 0.6
        else:
            perf_mult = 1.0  # 데이터 부족 시 기본값

        self._kelly_scalar = base_kelly * regime_mult * vix_mult * perf_mult
        # 범위 제한: 0.05 ~ 0.40
        self._kelly_scalar = min(0.40, max(0.05, self._kelly_scalar))

    def get_kelly_scalar(self) -> float:
        """현재 Dynamic Kelly 스칼라 (0.05 ~ 0.40)."""
        return self._kelly_scalar


def _compute_adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14):
    """순수 pandas로 ADX, +DI, -DI 계산 (ta 라이브러리 의존 없음)."""
    plus_dm = high.diff().clip(lower=0)
    minus_dm = (-low.diff()).clip(lower=0)

    # +DM과 -DM 중 큰 쪽만 유효
    mask_plus = plus_dm <= minus_dm
    mask_minus = minus_dm <= plus_dm
    plus_dm = plus_dm.copy()
    minus_dm = minus_dm.copy()
    plus_dm[mask_plus] = 0
    minus_dm[mask_minus] = 0

    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = tr.rolling(window=period).mean()
    plus_di = 100 * (plus_dm.rolling(window=period).mean() / atr.replace(0, np.nan))
    minus_di = 100 * (minus_dm.rolling(window=period).mean() / atr.replace(0, np.nan))

    dx = (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan) * 100
    adx = dx.rolling(window=period).mean()

    return adx, plus_di, minus_di


class SimulationEngine:

    # 레짐별 최소 시그널 강도 (Fix 2: BULL 과진입 방지)
    # MR 시그널은 57-81 분포이므로 BULL 50이면 저품질만 차단
    _REGIME_MIN_STRENGTH = {"BULL": 50, "NEUTRAL": 40, "RANGE_BOUND": 45, "BEAR": 55}

    def __init__(
        self,
        on_event: OnEventType,
        market_id: str = "kospi",
        watchlist: list | None = None,
        initial_capital: float = 100_000_000.0,
        currency: str = "KRW",
        currency_symbol: str = "₩",
        market_label: str = "KOSPI 200",
        slippage_pct: float = 0.001,
        commission_pct: float = 0.00015,
        strategy_mode: str = "momentum",
        fixed_amount_per_stock: float = 0,
        disable_es2: bool = False,
    ):
        self._on_event = on_event
        self.market_id = market_id
        self._watchlist = watchlist or WATCHLIST  # 하위호환
        self.currency = currency
        self.currency_symbol = currency_symbol
        self.market_label = market_label
        self.strategy_mode = strategy_mode  # "momentum" | "smc" | "multi" | "regime_*"
        self._regime_locked = strategy_mode in REGIME_STRATEGY_MODES
        self._locked_regime = REGIME_STRATEGY_MODES.get(strategy_mode)
        self._actual_market_regime = "NEUTRAL"  # 실제 감지 레짐 (표시용, 고정 시에도 갱신)
        self.fixed_amount_per_stock = fixed_amount_per_stock  # 0이면 기존 ATR 사이징
        self.disable_es2 = disable_es2  # True면 ES2 고정 익절 비활성화

        # 트랜잭션 비용
        self.slippage_pct = slippage_pct       # 0.1% 슬리피지 (편도)
        self.commission_pct = commission_pct   # 0.015% 수수료 (편도)
        self._total_commission_paid = 0.0      # 누적 수수료

        # 전략 파라미터 (config.yaml 미러링)
        self.ma_short = 5
        self.ma_long = 20
        self.rsi_period = 14
        self.rsi_lower = 52   # CF1 RSI 하한 (CLAUDE.md Phase 3: 52-78)
        self.rsi_upper = 78   # CF1 RSI 상한
        self.volume_multiplier = 1.5
        self.stop_loss_pct = -0.05    # ES1 손절 -5% (CLAUDE.md Phase 5)
        self.take_profit_pct = 0.20   # ES2 익절 BULL 기준 (체제별 동적)
        self.trailing_stop_pct = -0.04  # ES3 기본 floor -4% (Progressive ATR)
        self.trailing_activation_pct = 0.05
        self.max_holding_days = 40    # ES5 BULL 기준 (체제별: 40/25/15)
        self.max_positions = 10
        self.max_weight = 0.15
        self.min_cash_ratio = 0.30    # BR-P03: 최소 현금 비율 30%

        # 가상 포트폴리오
        self.initial_capital = initial_capital
        self.cash = self.initial_capital
        self.positions: Dict[str, SimPosition] = {}
        self.orders: List[SimOrder] = []
        self.signals: List[SimSignal] = []
        self.risk_events: List[Dict[str, Any]] = []

        # 시장 데이터 캐시
        self._ohlcv_cache: Dict[str, pd.DataFrame] = {}
        self._current_prices: Dict[str, float] = {}
        self._candle_score_cache: Dict[str, int] = {}  # P2: per-day candle score cache
        self._stock_names: Dict[str, str] = {w["code"]: w["name"] for w in self._watchlist}

        # 성과 추적
        self.closed_trades: List[SimTradeRecord] = []
        self.equity_curve: List[SimEquityPoint] = []
        self._trade_counter = 0

        # 리플레이 모드 (truncation 비활성화)
        self._replay_mode: bool = False
        self._exit_tag_filter: Optional[str] = None  # multi-mode exit tag routing
        # Phase 3.2: 단계적 DD 대응
        self._dd_level: int = 0       # 0=정상, 1=DD>10%, 2=DD>15%, 3=DD>20%
        self._dd_sizing_mult: float = 1.0  # DD>10% 시 0.5
        # Phase 4.6: 시그널 수집 모드
        self._collect_mode: bool = False
        self._collected_signals: List[tuple] = []

        # 트래킹
        self._started_at: Optional[str] = None
        self._peak_equity = self.initial_capital
        self._daily_start_equity = self.initial_capital
        self._consecutive_stops = 0
        self._daily_trade_amount = 0.0
        self._is_running = False
        self._market_regime: str = "NEUTRAL"  # Phase 0 결과 (BULL/NEUTRAL/RANGE_BOUND/BEAR)
        self._stock_regimes: Dict[str, str] = {}   # 종목별 개별 레짐 {stock_code: regime}
        self._stock_regimes_updated: bool = False  # 사이클 내 중복 업데이트 방지
        self._prev_regime: str = "NEUTRAL"  # 레짐 전환 감지용 이전 레짐
        self._regime_candidate: str = "NEUTRAL"  # 체제 전환 후보
        self._regime_candidate_days: int = 0  # 후보 연속 일수
        self._regime_confirmation_days: int = 5  # 체제 전환 확인 필요 일수

        # VIX 상태 (복합 Regime Classifier 및 포지션 사이징)
        self._vix_level: float = 18.0  # 기본값: 보통 수준
        self._vix_ema20: float = 18.0  # 20일 EMA (스파이크 스무딩)
        self._vix_history: List[float] = []  # VIX 이력 (EMA 계산용)

        # 지수 데이터 캐시 (Index-Driven Strategy Selection)
        self._index_ohlcv: List[Dict] = []   # [{open, high, low, close, volume}, ...]
        self._index_trend: Dict = {}          # _analyze_index_trend() 결과 캐시
        self._index_trend_history: List[Dict] = []  # 추세 변경 이력 (max 20)

        self._backtest_date: Optional[str] = None  # 백테스트 시 시뮬레이션 날짜
        self._cycle_count = 0
        self._order_counter = 0
        self._signal_counter = 0
        self._event_counter = 0

        # 진단 대상 종목 (Phase Funnel 디버그 로깅)
        self._debug_tickers: set = set()  # 예: {"005930", "000660"}

        # Phase 통계 (백테스트 수집용)
        self._phase_stats = {
            "total_scans": 0,
            "phase0_bear_blocks": 0,
            "phase1_trend_rejects": 0,
            "phase2_late_rejects": 0,
            "phase3_no_primary": 0,
            "phase3_no_confirm": 0,
            "phase3_ps3_pullback": 0,
            "phase4_risk_blocks": 0,
            "entries_executed": 0,
            "es1_stop_loss": 0,
            "es2_take_profit": 0,
            "es3_trailing_stop": 0,
            "es4_dead_cross": 0,
            "es5_max_holding": 0,
            "es6_time_decay": 0,
            "es7_rebalance_exit": 0,
            "es0_emergency_stop": 0,
            "divergence_blocks": 0,
            "regime_quality_blocks": 0,
            "index_trend_updates": 0,
            # 레짐별 전략 모듈화 카운터
            "phase3_ps4_donchian": 0,
            "es_neutral_time_decay": 0,
            "es_range_box_breakout": 0,
            "es_disp_partial_sell": 0,
            "regime_pyramid_entries": 0,
            "regime_sizing_reductions": 0,
            # 종목별 레짐 통계
            "stock_regime_distribution": {},     # {regime: count} 마지막 사이클 분포
            "stock_regime_strategy_map": {},     # {"regime→strategy": count} 라우팅 이력
            "es_mdd_guard": 0,                    # MDD 가드 강제 청산 횟수
        }

        # 에쿼티 히스토리 (프로그레시브 트레일링 기준용)
        self._equity_history: List[float] = []

        # 리밸런스 청산 대상 (ES7)
        self._rebalance_exit_codes: set = set()

        # --- 리밸런싱 내장 (Step 1) ---
        self._rebalance_mgr = None
        self._pending_rebalance = None
        self._full_universe_ohlcv = None

        # ── Tactical 전용 포트폴리오 배분 (Kelly Criterion) ──
        self._allocator: Optional['PortfolioAllocator'] = None

        if self.market_id == "kospi":
            try:
                from simulation.portfolio_allocator import PortfolioAllocator
                from data.config_manager import PortfolioAllocationConfig
                alloc_cfg = PortfolioAllocationConfig(
                    enabled=True,
                    kelly_fraction=0.30,
                )
                self._allocator = PortfolioAllocator(alloc_cfg)
                self.min_cash_ratio = 1.0 - alloc_cfg.kelly_fraction  # 0.70
                self.max_positions = alloc_cfg.tactical.top_n  # tactical 60종목
            except ImportError as e:
                print(f"[SimEngine:{self.market_id}] PortfolioAllocator 모듈 임포트 실패: {e}")
                self._allocator = None
            except Exception as e:
                print(f"[SimEngine:{self.market_id}] PortfolioAllocator 초기화 실패: {e} — 기본값 사용")
                self._allocator = None

        # ── 멀티 전략 / 레짐 전략 모드 초기화 ──
        self._strategy_allocator: Optional[StrategyAllocator] = None
        if self.strategy_mode == "multi" or self.strategy_mode in REGIME_STRATEGY_MODES:
            init_regime = self._locked_regime if self._regime_locked else self._market_regime
            self._strategy_allocator = StrategyAllocator(
                strategies=MULTI_STRATEGIES,
                regime=init_regime,
            )
            # 멀티/레짐 모드에서는 모든 전략의 설정을 로드
            self._init_strategy_configs(MULTI_STRATEGIES)
        else:
            # 단일 전략 모드: 해당 전략만 초기화
            self._init_strategy_configs([self.strategy_mode])

    def _init_strategy_configs(self, strategies: List[str]):
        """전략별 설정 및 상태를 초기화한다. 멀티 모드에서는 여러 전략을 동시 로드."""
        for s in strategies:
            if s == "smc" and not hasattr(self, '_smc_cfg'):
                from data.config_manager import SMCStrategyConfig
                self._smc_cfg = SMCStrategyConfig()
                self._smc_entry_threshold = self._smc_cfg.entry_threshold
                self._phase_stats.setdefault("es_smc_sl", 0)
                self._phase_stats.setdefault("es_smc_tp", 0)
                self._phase_stats.setdefault("es_choch_exit", 0)
                self._phase_stats.setdefault("smc_total_score", 0)
                self._phase_stats.setdefault("smc_entries", 0)

            elif s == "mean_reversion" and not hasattr(self, '_mr_cfg'):
                from data.config_manager import MeanReversionConfig
                self._mr_cfg = MeanReversionConfig()
                self._phase_stats.setdefault("mr_entries", 0)
                self._phase_stats.setdefault("mr_total_score", 0)
                self._phase_stats.setdefault("es_mr_sl", 0)
                self._phase_stats.setdefault("es_mr_tp", 0)
                self._phase_stats.setdefault("es_mr_bb", 0)
                self._phase_stats.setdefault("es_mr_ob", 0)

            elif s == "breakout_retest" and not hasattr(self, '_brt_cfg'):
                from data.config_manager import SMCStrategyConfig, BreakoutRetestConfig
                if not hasattr(self, '_smc_cfg'):
                    self._smc_cfg = SMCStrategyConfig()
                self._brt_cfg = BreakoutRetestConfig()
                if not hasattr(self, '_breakout_states'):
                    self._breakout_states: Dict[str, Any] = {}
                self._phase_stats.setdefault("brt_breakouts_detected", 0)
                self._phase_stats.setdefault("brt_fakeout_blocked", 0)
                self._phase_stats.setdefault("brt_retests_entered", 0)
                self._phase_stats.setdefault("brt_retests_expired", 0)
                self._phase_stats.setdefault("es_brt_sl", 0)
                self._phase_stats.setdefault("es_brt_tp", 0)
                self._phase_stats.setdefault("es_zone_break", 0)
                self._phase_stats.setdefault("es_choch_exit", 0)

            elif s == "arbitrage" and not hasattr(self, '_arb_cfg'):
                from data.config_manager import ArbitrageConfig, ConfigManager
                try:
                    _cfg_mgr = ConfigManager()
                    _full_cfg = _cfg_mgr.load()
                    self._arb_cfg = _full_cfg.arbitrage
                except Exception:
                    self._arb_cfg = ArbitrageConfig()
                cfg = self._arb_cfg
                self._arb_pairs: List[Dict] = []
                self._arb_pair_states: Dict[str, Any] = {}
                self._arb_last_discovery: str = ""
                self._arb_trade_history: List[Dict] = []
                self._arb_pair_cooldown: Dict[str, int] = {}
                self._arb_corr_decay_count: Dict[str, int] = {}
                self._arb_day_count: int = 0
                self._arb_mdd_halted: bool = False
                self._arb_mdd_halt_days: int = 0
                self._arb_fixed_pair_defs: List[Dict] = [
                    p for p in cfg.fixed_pairs if p.get("market") == self.market_id
                ]
                self._arb_basis_signals: List[Dict] = [
                    s_item for s_item in cfg.basis_signals if s_item.get("market") == self.market_id
                ]
                self._arb_basis_window_open: bool = False
                self._arb_basis_data: Dict[str, Any] = {}
                for key in ["arb_pairs_scanned", "arb_spreads_detected", "arb_correlation_rejects",
                            "arb_entries", "arb_short_entries", "arb_total_score",
                            "es_arb_sl", "es_arb_tp", "es_arb_corr",
                            "arb_basis_gate_blocks", "arb_basis_window_opens", "arb_fixed_pairs_loaded"]:
                    self._phase_stats.setdefault(key, 0)

            elif s == "defensive":
                # Defensive 전략: 별도 설정 불필요, 인버스 ETF 데이터는 런타임에 확인
                self._phase_stats.setdefault("defensive_entries", 0)
                self._phase_stats.setdefault("defensive_regime_exits", 0)

            # momentum은 별도 설정 불필요 (기본 파라미터 사용)

        # 멀티/레짐 모드 phase stats
        if self.strategy_mode == "multi" or self.strategy_mode in REGIME_STRATEGY_MODES:
            self._phase_stats.setdefault("multi_dedup_skips", 0)

    # ══════════════════════════════════════════
    # 메인 루프
    # ══════════════════════════════════════════

    async def start(self):
        self._is_running = True
        self._started_at = datetime.now().isoformat()
        self._add_risk_event("INFO", "시뮬레이션 엔진 시작 (모의투자)")

        await self._fetch_historical_data()
        self._add_risk_event("INFO", f"OHLCV 데이터 로드 완료 ({len(self._ohlcv_cache)}종목)")

        # 초기 에쿼티 포인트 기록
        self._record_equity_point()

        await self._broadcast_all()

        while self._is_running:
            try:
                await self._run_cycle()
            except Exception as e:
                print(f"[SimEngine] Cycle error: {e}")
            await asyncio.sleep(30)

    async def stop(self):
        self._is_running = False

    async def _run_cycle(self):
        self._cycle_count += 1
        await self._fetch_current_prices()
        self._update_position_prices()
        self._check_exits()

        # Phase 0: 시장 체제 매 사이클 갱신 (UI 표시용)
        self._update_market_regime()
        self._update_stock_regimes()

        if self._cycle_count % 2 == 0:
            self._scan_entries()

        # 에쿼티 커브 스냅샷 (매 10사이클 ≈ 5분)
        if self._cycle_count % 10 == 0:
            self._record_equity_point()

        await self._broadcast_all()

    # ══════════════════════════════════════════
    # 백테스트 인터페이스 (동기식)
    # ══════════════════════════════════════════

    def run_backtest_day(
        self,
        date: str,
        ohlcv_cache: Dict[str, pd.DataFrame],
        current_prices: Dict[str, float],
    ):
        """
        히스토리컬 백테스트용 동기 1일 실행.
        외부에서 OHLCV + 현재가를 주입하면 6-Phase 파이프라인이 그대로 실행된다.
        async 불필요 — asyncio.sleep, SSE broadcast 없음.
        """
        # YYYYMMDD → YYYY-MM-DD 변환하여 백테스트 날짜 설정
        if len(date) == 8:
            self._backtest_date = f"{date[:4]}-{date[4:6]}-{date[6:]}"
        else:
            self._backtest_date = date

        self._ohlcv_cache = ohlcv_cache
        self._current_prices = current_prices

        # 당일 OHLC 추출 — 갭다운 보호용
        self._daily_lows: Dict[str, float] = {}
        self._daily_highs: Dict[str, float] = {}
        self._daily_opens: Dict[str, float] = {}
        for code, df in ohlcv_cache.items():
            if df is not None and not df.empty:
                last = df.iloc[-1]
                if "low" in df.columns and pd.notna(last.get("low")):
                    self._daily_lows[code] = float(last["low"])
                if "high" in df.columns and pd.notna(last.get("high")):
                    self._daily_highs[code] = float(last["high"])
                if "open" in df.columns and pd.notna(last.get("open")):
                    self._daily_opens[code] = float(last["open"])

        # 포지션 현재가 갱신
        self._update_position_prices()

        # Peak equity 갱신 (매일, entry scan과 무관하게)
        equity = self._get_total_equity()
        self._peak_equity = max(self._peak_equity, equity)

        # Phase 5: 청산 체크 (매수보다 선행)
        self._check_exits()

        # Phase 0: 시장 체제
        self._prev_regime = self._market_regime
        self._update_market_regime()

        # Phase 0.1: 종목별 개별 레짐 갱신 (7일 주기, analytics용)
        self._stock_regimes_updated = False
        self._update_stock_regimes()

        # Phase 0.5: 지수 추세 기반 전략 비중 동적 조정 (multi/레짐 모드)
        if (self.strategy_mode == "multi" or self.strategy_mode in REGIME_STRATEGY_MODES) and self._index_ohlcv:
            self._update_strategy_weights_from_index()

        # 레짐 다운그레이드 감지 → 초과 포지션 ES7 청산 대상 지정
        regime_order = {"BULL": 3, "NEUTRAL": 2, "RANGE_BOUND": 1, "BEAR": 0}
        if regime_order.get(self._market_regime, 2) < regime_order.get(self._prev_regime, 2):
            self._reduce_positions_for_regime()

        # 리밸런싱 체크 (regime 업데이트 후, entry 스캔 전)
        self._check_rebalance_sync()

        # Phase 1~4 + 매수 실행
        self._scan_entries()

        # 보유일수 증가
        for pos in self.positions.values():
            if pos.status == "ACTIVE":
                pos.days_held += 1

        # 에쿼티 기록
        self._record_equity_point()

    def reset_daily_state(self):
        """일일 PnL 리셋 (백테스트에서 매 거래일 시작 시 호출)."""
        self._daily_start_equity = self._get_total_equity()
        self._daily_trade_amount = 0.0
        self._candle_score_cache.clear()  # P2: reset candle score cache per day

    def update_watchlist(self, new_watchlist: list):
        """동적 워치리스트 교체 (리밸런싱 시 호출)."""
        self._watchlist = new_watchlist
        self._stock_names = {w["code"]: w["name"] for w in new_watchlist}

    def set_rebalance_exits(self, codes: set):
        """리밸런스 탈락 종목을 ES7 청산 대상으로 지정 (기존 코드와 병합)."""
        self._rebalance_exit_codes |= set(codes)

    def set_full_universe_ohlcv(self, ohlcv: dict):
        """전체 유니버스 OHLCV 주입 (BACKTEST 리밸런싱 스캔용).

        _ohlcv_cache(워치리스트용)와 별도로 관리한다.
        리밸런싱 스캔 시 전체 유니버스에서 종목을 선별하기 위해 사용.
        """
        self._full_universe_ohlcv = ohlcv

    @property
    def rebalance_history(self) -> list:
        """리밸런스 이력. _rebalance_mgr._history를 단일 소스로 사용."""
        if self._rebalance_mgr:
            return self._rebalance_mgr._history
        return []

    def init_rebalance_manager(self, scanner, rebalance_interval: int = 14):
        """리밸런스 매니저를 엔진에 내장한다.

        Args:
            scanner: UniverseScanner 인스턴스
            rebalance_interval: 리밸런싱 주기 (거래일 단위, 기본 14)
        """
        from backtest.rebalancer import RebalanceManager
        self._rebalance_mgr = RebalanceManager(
            scanner=scanner,
            rebalance_interval=rebalance_interval,
        )

    def needs_full_universe_ohlcv(self) -> bool:
        """리밸런싱 스캔을 위해 전체 유니버스 OHLCV가 필요한지 판단.

        HistoricalBacktester가 이 메서드를 통해 데이터 주입 여부를 결정한다.
        엔진 내부 상태를 직접 접근하지 않도록 캡슐화.
        """
        return bool(self._rebalance_mgr and self._rebalance_mgr.should_rebalance())

    def _check_rebalance_sync(self):
        """BACKTEST 모드 전용 리밸런싱 체크 (동기 실행).

        should_rebalance() → execute_rebalance() → tick() 순서를 유지한다.
        현재 HistoricalBacktester의 실행 순서와 동일하게 유지하여 회귀를 방지.
        """
        if not self._rebalance_mgr:
            return

        if not self._rebalance_mgr.should_rebalance():
            self._rebalance_mgr.tick()
            return

        # 전체 유니버스 데이터로 스캔 (없으면 워치리스트 데이터 폴백)
        ohlcv_for_scan = self._full_universe_ohlcv or self._ohlcv_cache
        active_positions = {
            pos.stock_code: pos for pos in self.positions.values()
            if pos.status == "ACTIVE"
        }

        event = self._rebalance_mgr.execute_rebalance(
            ohlcv_map=ohlcv_for_scan,
            current_date=self._backtest_date,
            active_positions=active_positions,
        )

        self._apply_rebalance(event)
        self._rebalance_mgr.tick()

    def _apply_rebalance(self, event):
        """리밸런싱 이벤트를 엔진에 적용한다.

        update_watchlist()를 사용하여 _stock_names도 함께 갱신.
        기존 regime 다운그레이드 퇴출 코드와 병합 (덮어쓰기 방지).
        """
        # 워치리스트 교체 + _stock_names 갱신
        self.update_watchlist(event.new_watchlist)

        # 기존 퇴출 코드와 병합
        self._rebalance_exit_codes |= set(event.positions_force_exited)

    def _get_current_date_str(self) -> str:
        """현재 날짜 문자열. 백테스트 시 시뮬레이션 날짜, 실시간 시 오늘 날짜."""
        if self._backtest_date:
            return self._backtest_date
        return datetime.now().strftime("%Y-%m-%d")

    # 시장별 거래 시간 (현지 시각 기준)
    _MARKET_HOURS = {
        "kospi":  {"open_min": 9 * 60,       "duration": 390},  # 09:00~15:30 KST (390분)
        "sp500":  {"open_min": 9 * 60 + 30,  "duration": 390},  # 09:30~16:00 ET  (390분)
        "ndx":    {"open_min": 9 * 60 + 30,  "duration": 390},  # 09:30~16:00 ET  (390분)
    }

    def _get_current_iso(self) -> str:
        """현재 ISO 타임스탬프. 백테스트 시 시뮬레이션 날짜 기반.
        주문 카운터를 활용해 시장별 거래 시간 범위에서 시간 분산."""
        if self._backtest_date:
            hours = self._MARKET_HOURS.get(self.market_id, self._MARKET_HOURS["kospi"])
            total_minutes = hours["open_min"] + (self._order_counter * 17) % hours["duration"]
            hour = total_minutes // 60
            minute = total_minutes % 60
            return f"{self._backtest_date}T{hour:02d}:{minute:02d}:00"
        return datetime.now().isoformat()

    # ══════════════════════════════════════════
    # 데이터 수집
    # ══════════════════════════════════════════

    # yfinance 세션 충돌 방지: 스레드 레벨 락 (멀티 엔진 동시 다운로드 차단)
    import threading
    _yf_thread_lock = threading.Lock()

    async def _fetch_historical_data(self):
        import yfinance as yf

        # 인버스 ETF + 안전자산 ETF 함께 다운로드 (Defensive 전략용)
        extra_items = []
        market_key = self.market_id
        if market_key == "ndx":
            market_key = "nasdaq"
        for inv_ticker in INVERSE_ETFS.get(market_key, []):
            inv_code = inv_ticker.replace(".KS", "")
            if not any(w["code"] == inv_code for w in self._watchlist):
                extra_items.append({"code": inv_code, "ticker": inv_ticker, "name": f"INV_{inv_ticker}"})
        # CRISIS 방어용 안전자산 ETF도 추가
        for item in SAFE_HAVEN_ETFS.get(market_key, []):
            sh_ticker = item["ticker"]
            sh_code = sh_ticker.replace(".KS", "")
            if not any(w["code"] == sh_code for w in self._watchlist):
                if not any(e["code"] == sh_code for e in extra_items):
                    extra_items.append({"code": sh_code, "ticker": sh_ticker, "name": item["name"]})

        all_items = list(self._watchlist) + extra_items

        BATCH_SIZE = 20
        loop = asyncio.get_event_loop()
        failed_tickers = []

        for i in range(0, len(all_items), BATCH_SIZE):
            batch = all_items[i:i + BATCH_SIZE]
            tickers_str = " ".join(w["ticker"] for w in batch)

            try:
                def _download_batch(t=tickers_str):
                    with SimulationEngine._yf_thread_lock:
                        # yfinance 내부 캐시 클리어 (마켓 간 데이터 오염 방지)
                        yf.shared._DFS.clear()
                        yf.shared._ERRORS.clear()
                        return yf.download(t, period="1y", interval="1d", progress=False)

                data = await loop.run_in_executor(None, _download_batch)
            except Exception as e:
                print(f"[SimEngine:{self.market_id}] Batch {i // BATCH_SIZE + 1} fetch failed: {e}")
                failed_tickers.extend(w["ticker"] for w in batch)
                continue

            if data.empty:
                failed_tickers.extend(w["ticker"] for w in batch)
                continue

            # 타임존 안전 처리 (Fix 6)
            if hasattr(data.index, 'tz') and data.index.tz is not None:
                if self.market_id == "kospi":
                    data.index = data.index.tz_convert("Asia/Seoul")
                data.index = data.index.tz_localize(None)

            # yfinance 캐시 오염 감지: 반환된 티커가 요청 티커와 일치하는지 확인
            batch_tickers = {w["ticker"] for w in batch}
            if isinstance(data.columns, pd.MultiIndex):
                returned_tickers = set(data.columns.get_level_values(1).unique().tolist())
                if not batch_tickers.intersection(returned_tickers):
                    print(f"[SimEngine:{self.market_id}] ⚠ 배치 데이터 오염 감지 — 개별 다운로드로 전환")
                    failed_tickers.extend(w["ticker"] for w in batch)
                    continue

            for w in batch:
                try:
                    if isinstance(data.columns, pd.MultiIndex):
                        stock_df = pd.DataFrame(
                            {
                                "open": data[("Open", w["ticker"])],
                                "high": data[("High", w["ticker"])],
                                "low": data[("Low", w["ticker"])],
                                "close": data[("Close", w["ticker"])],
                                "volume": data[("Volume", w["ticker"])],
                            }
                        ).dropna()
                    else:
                        stock_df = data.rename(columns=str.lower)

                    if stock_df.empty:
                        print(f"[SimEngine:{self.market_id}] ✗ {w['ticker']}: 0 rows after dropna (delisted?)")
                        continue
                    self._ohlcv_cache[w["code"]] = stock_df
                    self._current_prices[w["code"]] = float(stock_df["close"].iloc[-1])
                except Exception as e:
                    print(f"[SimEngine:{self.market_id}] ✗ {w['ticker']}: {type(e).__name__}: {e}")
                    failed_tickers.append(w["ticker"])

        # 실패 종목 개별 재시도 (yf.Ticker.history 사용 — _DFS 오염 회피)
        retry_items = [w for w in all_items if w["ticker"] in failed_tickers and w["code"] not in self._ohlcv_cache]
        if retry_items:
            print(f"[SimEngine:{self.market_id}] 개별 재시도: {len(retry_items)}종목")
        for idx, w in enumerate(retry_items):
            try:
                # Yahoo 레이트 리밋 회피: 10종목마다 1초 대기
                if idx > 0 and idx % 10 == 0:
                    await asyncio.sleep(1)

                def _retry_ticker(t=w["ticker"]):
                    ticker_obj = yf.Ticker(t)
                    return ticker_obj.history(period="1y", interval="1d")

                data = await loop.run_in_executor(None, _retry_ticker)
                if data is not None and not data.empty:
                    if hasattr(data.index, 'tz') and data.index.tz is not None:
                        if self.market_id == "kospi":
                            data.index = data.index.tz_convert("Asia/Seoul")
                        data.index = data.index.tz_localize(None)

                    stock_df = data.rename(columns=str.lower)
                    # history()는 'dividends', 'stock splits' 등도 포함 → OHLCV만 추출
                    ohlcv_cols = ["open", "high", "low", "close", "volume"]
                    available = [c for c in ohlcv_cols if c in stock_df.columns]
                    if len(available) >= 4:
                        stock_df = stock_df[available].dropna()
                        if not stock_df.empty:
                            self._ohlcv_cache[w["code"]] = stock_df
                            self._current_prices[w["code"]] = float(stock_df["close"].iloc[-1])
                        else:
                            print(f"[SimEngine:{self.market_id}] ✗ {w['ticker']}: 재시도 후에도 0 rows")
                    else:
                        print(f"[SimEngine:{self.market_id}] ✗ {w['ticker']}: OHLCV 컬럼 부족")
                else:
                    print(f"[SimEngine:{self.market_id}] ✗ {w['ticker']}: 재시도 후에도 데이터 없음")
            except Exception as e:
                print(f"[SimEngine:{self.market_id}] ✗ {w['ticker']}: 재시도 실패 {type(e).__name__}: {e}")

        total = len(all_items)
        loaded = len(self._ohlcv_cache)
        if loaded < total:
            print(f"[SimEngine:{self.market_id}] ⚠ 데이터 로드: {loaded}/{total}종목 ({total - loaded}종목 실패)")
        else:
            print(f"[SimEngine:{self.market_id}] 데이터 로드 완료: {loaded}/{total}종목")

    async def _fetch_current_prices(self):
        import yfinance as yf

        tickers = " ".join(w["ticker"] for w in self._watchlist)
        loop = asyncio.get_event_loop()
        try:
            data = await loop.run_in_executor(
                None,
                lambda: yf.download(tickers, period="1d", interval="1m", progress=False),
            )
            if data.empty:
                return

            for w in self._watchlist:
                try:
                    if isinstance(data.columns, pd.MultiIndex):
                        close_series = data[("Close", w["ticker"])].dropna()
                    else:
                        close_series = data["Close"].dropna()
                    if not close_series.empty:
                        self._current_prices[w["code"]] = float(close_series.iloc[-1])
                except Exception:
                    pass
        except Exception:
            pass  # 다음 사이클에 재시도

    # ══════════════════════════════════════════
    # 지표 계산 (momentum_swing.py 복제)
    # ══════════════════════════════════════════

    def _calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty or len(df) < self.ma_long:
            return df

        # 거래량 0인 행 제거 (휴장일/비정상 데이터 — 지표 왜곡 방지)
        if "volume" in df.columns:
            df = df[df["volume"] > 0]
        if len(df) < self.ma_long:
            return df

        c = df["close"].astype(float)
        v = df["volume"].astype(float)
        h = df["high"].astype(float)
        lo = df["low"].astype(float)
        df = df.copy()

        # ── 기존 이평선 ──
        df["ma_short"] = c.rolling(window=self.ma_short).mean()
        df["ma_long"] = c.rolling(window=self.ma_long).mean()

        # ── Phase 1: 정배열용 이평선 ──
        df["ma60"] = c.rolling(window=60).mean()
        df["ma120"] = c.rolling(window=120).mean()
        df["ma200"] = c.rolling(window=200).mean()


        # ── Phase 1: ADX / DMI (14일) ──
        adx_vals, plus_di_vals, minus_di_vals = _compute_adx(h, lo, c, period=14)
        df["adx"] = adx_vals
        df["plus_di"] = plus_di_vals
        df["minus_di"] = minus_di_vals

        # ── Phase 2: 볼린저 밴드 (20, 2σ) ──
        bb_ma = c.rolling(window=20).mean()
        bb_std = c.rolling(window=20).std()
        df["bb_upper"] = bb_ma + bb_std * 2
        df["bb_lower"] = bb_ma - bb_std * 2
        df["bb_width"] = ((df["bb_upper"] - df["bb_lower"]) / bb_ma.replace(0, np.nan))
        df["bb_middle"] = bb_ma

        # ── Phase 3: MACD (12/26/9) ──
        ema_fast = c.ewm(span=12, adjust=False).mean()
        ema_slow = c.ewm(span=26, adjust=False).mean()
        df["macd_line"] = ema_fast - ema_slow
        df["macd_signal"] = df["macd_line"].ewm(span=9, adjust=False).mean()
        df["macd_hist"] = df["macd_line"] - df["macd_signal"]

        # ── RSI ──
        delta = c.diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)
        avg_gain = gain.rolling(window=self.rsi_period).mean()
        avg_loss = loss.rolling(window=self.rsi_period).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        df["rsi"] = 100 - (100 / (1 + rs))

        # ── 슬로우 RSI (28일) — 멀티 타임프레임 확인용 ──
        delta_slow = c.diff()
        gain_slow = delta_slow.clip(lower=0)
        loss_slow = (-delta_slow).clip(lower=0)
        avg_gain_slow = gain_slow.rolling(window=28).mean()
        avg_loss_slow = loss_slow.rolling(window=28).mean()
        rs_slow = avg_gain_slow / avg_loss_slow.replace(0, np.nan)
        df["rsi_slow"] = 100 - (100 / (1 + rs_slow))

        # ── 거래량 이동평균 ──
        df["volume_ma"] = v.rolling(window=20).mean()

        # ── ATR (14-period) — 동적 트레일링 + 포지션 사이징용 ──
        tr1 = h - lo
        tr2 = (h - c.shift()).abs()
        tr3 = (lo - c.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        df["atr"] = tr.rolling(window=14).mean()
        df["atr_pct"] = df["atr"] / c  # 가격 대비 ATR 비율

        # ── Donchian Channel (20d) — STRONG_BULL Donchian 돌파용 ──
        df["donchian_high"] = h.rolling(20, min_periods=20).max()
        df["donchian_low"] = lo.rolling(20, min_periods=20).min()

        # ── 이격도 (Disparity) — BULL 부분 청산용 ──
        ma20 = c.rolling(window=20).mean()
        df["ma20"] = ma20
        df["disparity_20"] = c / ma20.replace(0, np.nan)

        return df

    # ══════════════════════════════════════════
    # Phase 0: 시장 체제 판단 (TradingLogicFlow.md)
    # ══════════════════════════════════════════

    def _judge_market_regime(self) -> str:
        """
        Phase 0: 복합 지표 기반 시장 체제 판단 (4단계).

        복합 점수 = breadth(40%) + ADX 평균(25%) + VIX(20%) + BB bandwidth(15%)
        BULL ≥ 65 | NEUTRAL 40-65 | RANGE_BOUND 25-40 (ADX<20) | BEAR < 25

        기존 breadth 단독 판단 대비 횡보장(RANGE_BOUND) 구분 추가.
        """
        above_count = 0
        total_valid = 0
        adx_values = []
        bb_bandwidths = []

        for w in self._watchlist:
            code = w["code"]
            df = self._ohlcv_cache.get(code)
            if df is None or len(df) < 220:
                continue

            close = df["close"].astype(float)
            ma200 = close.rolling(window=200).mean()

            if pd.isna(ma200.iloc[-1]):
                continue

            total_valid += 1
            if float(close.iloc[-1]) > float(ma200.iloc[-1]):
                above_count += 1

            # ADX 수집 (종목별 추세 강도)
            if len(df) >= 30:
                high = df["high"].astype(float) if "high" in df.columns else None
                low = df["low"].astype(float) if "low" in df.columns else None
                if high is not None and low is not None:
                    try:
                        adx, _, _ = _compute_adx(high, low, close, period=14)
                        last_adx = adx.iloc[-1]
                        if pd.notna(last_adx):
                            adx_values.append(float(last_adx))
                    except Exception:
                        pass

            # BB Bandwidth 수집 (변동성 폭)
            if len(df) >= 30:
                ma20 = close.rolling(window=20).mean()
                std20 = close.rolling(window=20).std()
                last_ma20 = ma20.iloc[-1]
                last_std = std20.iloc[-1]
                if pd.notna(last_ma20) and pd.notna(last_std) and last_ma20 > 0:
                    bandwidth = float(last_std * 2 / last_ma20) * 100  # % 단위
                    bb_bandwidths.append(bandwidth)

        if total_valid < 3:
            return self._market_regime  # 데이터 부족 → 현재 유지

        # ── 복합 점수 계산 (0-100) ──

        # 1. Breadth 점수 (40%): 0-100 → 0-40
        breadth_pct = above_count / total_valid * 100
        breadth_score = breadth_pct * 0.40  # 0~40

        # 2. ADX 평균 점수 (25%): ADX 높을수록 추세 강 → 높은 점수
        #    ADX < 15 = 0점, ADX 15-25 = 선형, ADX > 40 = 만점
        if adx_values:
            avg_adx = sum(adx_values) / len(adx_values)
            adx_score = min(max((avg_adx - 15) / 25 * 25, 0), 25)  # 0~25
        else:
            avg_adx = 25.0  # 데이터 없으면 중립
            adx_score = 10.0

        # 3. VIX 점수 (20%): VIX 낮을수록 강세 → 높은 점수
        #    VIX < 14 = 20점, VIX 14-30 = 선형 역, VIX > 30 = 0점
        vix = self._vix_ema20
        vix_score = min(max((30 - vix) / 16 * 20, 0), 20)  # 0~20

        # 4. BB Bandwidth 점수 (15%): bandwidth 넓으면 추세/변동 → 점수 높음
        #    좁으면(횡보) 점수 낮음
        if bb_bandwidths:
            avg_bw = sum(bb_bandwidths) / len(bb_bandwidths)
            # 일반적 bandwidth: 2-10%. 좁은 < 3%, 넓은 > 6%
            bw_score = min(max((avg_bw - 2) / 6 * 15, 0), 15)  # 0~15
        else:
            avg_bw = 4.0
            bw_score = 7.5

        composite_score = breadth_score + adx_score + vix_score + bw_score

        # ── 레짐 결정 ──
        if composite_score >= 65:
            raw_regime = "BULL"
        elif composite_score >= 40:
            # NEUTRAL vs RANGE_BOUND 구분: ADX<20 AND BB bandwidth 하위20%
            is_range_bound = (
                adx_values
                and avg_adx < 20
                and bb_bandwidths
                and avg_bw < 3.5  # 좁은 bandwidth
            )
            raw_regime = "RANGE_BOUND" if is_range_bound else "NEUTRAL"
        elif composite_score >= 25:
            raw_regime = "NEUTRAL" if breadth_pct > 45 else "BEAR"
        else:
            raw_regime = "BEAR"

        return self._smooth_regime(raw_regime)

    def _smooth_regime(self, raw_regime: str) -> str:
        """체제 전환 스무딩: N일 연속 동일 신호 시에만 전환."""
        if raw_regime == self._market_regime:
            self._regime_candidate = raw_regime
            self._regime_candidate_days = 0
            return self._market_regime

        if raw_regime == self._regime_candidate:
            self._regime_candidate_days += 1
            if self._regime_candidate_days >= self._regime_confirmation_days:
                return raw_regime  # 확인 완료 → 체제 전환
        else:
            self._regime_candidate = raw_regime
            self._regime_candidate_days = 1

        return self._market_regime  # 아직 미확인 → 현재 유지

    def _update_market_regime(self):
        """레짐 감지 + 레짐 고정 모드 오버라이드.

        실제 감지 레짐은 _actual_market_regime에 보존 (UI 표시용).
        레짐 고정 모드(_regime_locked)일 때 _market_regime을 locked 값으로 덮어씀.
        """
        detected = self._judge_market_regime()
        self._actual_market_regime = detected  # 실제 감지 보존
        if self._regime_locked:
            self._market_regime = self._locked_regime  # 고정 레짐 적용
        else:
            self._market_regime = detected

    def update_vix(self, vix_value: float):
        """VIX 값 업데이트 (외부에서 주입: 백테스트 or 실시간)."""
        if vix_value <= 0:
            return
        self._vix_level = vix_value
        self._vix_history.append(vix_value)
        # 20일 EMA 계산
        if len(self._vix_history) >= 20:
            alpha = 2.0 / (20 + 1)
            self._vix_ema20 = self._vix_ema20 * (1 - alpha) + vix_value * alpha
        else:
            # 워밍업 중 — 단순 평균
            self._vix_ema20 = sum(self._vix_history) / len(self._vix_history)

    # ══════════════════════════════════════════
    # 지수 데이터 기반 자동 전략 선택
    # ══════════════════════════════════════════

    def update_index_data(self, date: str, ohlcv: Dict):
        """지수 OHLCV 데이터 주입 (백테스트/실시간 공용).

        Args:
            date: YYYYMMDD
            ohlcv: {"open": float, "high": float, "low": float, "close": float, "volume": float}
        """
        self._index_ohlcv.append(ohlcv)
        # 최대 260일 보관 (MA200 + buffer)
        if len(self._index_ohlcv) > 260:
            self._index_ohlcv = self._index_ohlcv[-260:]

    def _get_index_return(self, days: int) -> float:
        """최근 N일 지수 수익률 계산. 데이터 부족 시 0.0 반환."""
        if not self._index_ohlcv or len(self._index_ohlcv) < days + 1:
            return 0.0
        try:
            current = float(self._index_ohlcv[-1]["close"])
            past = float(self._index_ohlcv[-days - 1]["close"])
            if past > 0:
                return (current - past) / past
        except (KeyError, IndexError, ValueError):
            pass
        return 0.0

    def _analyze_index_trend(self) -> Dict:
        """지수 OHLCV에서 추세 시그널 분석.

        복합 지표: MA 정렬 + RSI + ADX + MACD + VIX
        Returns:
            {
                "trend": "STRONG_BULL" | "BULL" | "NEUTRAL" | "RANGE_BOUND" | "BEAR" | "CRISIS",
                "ma_alignment": "ALIGNED_BULL" | "ALIGNED_BEAR" | "MIXED",
                "momentum_score": float (0-100),
                "volatility_state": "LOW" | "NORMAL" | "HIGH" | "EXTREME",
                "signals": List[str],
            }
        """
        n = len(self._index_ohlcv)
        if n < 50:
            return {"trend": "NEUTRAL", "ma_alignment": "MIXED",
                    "momentum_score": 50.0, "volatility_state": "NORMAL",
                    "signals": ["지수 데이터 부족 (< 50일)"]}

        closes = pd.Series([d["close"] for d in self._index_ohlcv])
        highs = pd.Series([d["high"] for d in self._index_ohlcv])
        lows = pd.Series([d["low"] for d in self._index_ohlcv])
        signals = []

        # ── MA Alignment ──
        ma20 = closes.rolling(20).mean().iloc[-1] if n >= 20 else closes.mean()
        ma50 = closes.rolling(50).mean().iloc[-1] if n >= 50 else closes.mean()
        ma200 = closes.rolling(200).mean().iloc[-1] if n >= 200 else None
        current_close = closes.iloc[-1]

        if ma200 is not None and not pd.isna(ma200):
            if current_close > ma50 > ma200:
                ma_state = "ALIGNED_BULL"
                signals.append(f"지수 MA 정렬: Close > MA50 > MA200")
            elif current_close < ma50 < ma200:
                ma_state = "ALIGNED_BEAR"
                signals.append(f"지수 MA 정렬: Close < MA50 < MA200")
            else:
                ma_state = "MIXED"
                signals.append(f"지수 MA 혼합")
        elif current_close > ma50:
            ma_state = "ALIGNED_BULL"
            signals.append(f"지수 Close > MA50 (MA200 미계산)")
        else:
            ma_state = "MIXED"
            signals.append(f"지수 MA 혼합 (MA200 미계산)")

        # ── RSI(14) ──
        delta = closes.diff()
        gain = delta.where(delta > 0, 0.0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
        rs = gain.iloc[-1] / loss.iloc[-1] if loss.iloc[-1] > 0 else 100
        rsi = 100.0 - (100.0 / (1.0 + rs))
        signals.append(f"지수 RSI: {rsi:.1f}")

        # ── ADX(14) ──
        try:
            adx_series, _, _ = _compute_adx(highs, lows, closes, period=14)
            adx = float(adx_series.iloc[-1]) if pd.notna(adx_series.iloc[-1]) else 20.0
        except Exception:
            adx = 20.0
        signals.append(f"지수 ADX: {adx:.1f}")

        # ── MACD(12, 26, 9) ──
        ema12 = closes.ewm(span=12, adjust=False).mean()
        ema26 = closes.ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        macd_hist = macd_line.iloc[-1] - signal_line.iloc[-1]
        macd_positive = macd_hist > 0
        signals.append(f"지수 MACD 히스토그램: {macd_hist:.2f} ({'양' if macd_positive else '음'})")

        # ── Momentum Score (0-100) ──
        # RSI 정규화: 30-70 → 0-100 (중립 = 50)
        rsi_norm = min(max((rsi - 30) / 40 * 40, 0), 40)  # 0~40
        # ADX 정규화: 0-50 → 0-35
        adx_norm = min(max(adx / 50 * 35, 0), 35)  # 0~35
        # MACD 보너스: 양전환 +25, 음전환 0
        macd_bonus = 25 if macd_positive else 0
        momentum_score = rsi_norm + adx_norm + macd_bonus
        momentum_score = min(max(momentum_score, 0), 100)

        # ── Volatility State (VIX 기반) ──
        vix = self._vix_ema20
        if vix < 16:
            volatility_state = "LOW"
        elif vix < 22:
            volatility_state = "NORMAL"
        elif vix < 30:
            volatility_state = "HIGH"
        else:
            volatility_state = "EXTREME"
        signals.append(f"VIX EMA20: {vix:.1f} → {volatility_state}")

        # ── Final Trend Classification ──
        if ma_state == "ALIGNED_BULL" and adx > 30 and rsi > 55:
            trend = "STRONG_BULL"
        elif ma_state == "ALIGNED_BULL" or (
            (ma200 is None or current_close > ma200) and momentum_score > 55
        ):
            trend = "BULL"
        elif ma_state == "ALIGNED_BEAR" and volatility_state in ("HIGH", "EXTREME"):
            trend = "CRISIS"
        elif ma_state == "ALIGNED_BEAR":
            trend = "BEAR"
        # ── Secondary bear detection (B6): momentum + VIX + short-term return ──
        elif momentum_score < 35 and self._vix_ema20 > 22 and self._get_index_return(20) < -0.05:
            trend = "BEAR"
            signals.append("보조 약세 감지: momentum<35, VIX>22, 20일수익률<-5%")
        # ── Secondary crisis detection (B6): 60-day deep drawdown ──
        elif self._get_index_return(60) < -0.15:
            trend = "CRISIS"
            signals.append("보조 위기 감지: 60일수익률<-15%")
        elif adx < 20 and volatility_state in ("LOW", "NORMAL"):
            trend = "RANGE_BOUND"  # 저추세 + 저변동성 = 박스권
        else:
            trend = "NEUTRAL"
        signals.append(f"최종 지수 추세: {trend}")

        return {
            "trend": trend,
            "ma_alignment": ma_state,
            "momentum_score": round(momentum_score, 1),
            "volatility_state": volatility_state,
            "signals": signals,
            "rsi": round(rsi, 1),
            "adx": round(adx, 1),
            "macd_value": round(float(macd_line.iloc[-1]), 2),
            "macd_signal": round(float(signal_line.iloc[-1]), 2),
        }

    def _update_strategy_weights_from_index(self):
        """지수 추세 분석 → 전략 비중 동적 오버라이드.

        레짐 고정 모드: 고정 레짐의 가중치 강제 적용 (자동 감지 건너뜀).
        multi 모드: 지수 데이터 있으면 INDEX_TREND_STRATEGY_WEIGHTS 적용.
        지수 데이터 부족하면 기존 REGIME_STRATEGY_WEIGHTS 유지 (fallback).
        """
        # 레짐 전략 모드: 고정 레짐 가중치 강제 적용
        if self._regime_locked:
            weights = INDEX_TREND_STRATEGY_WEIGHTS.get(
                self._locked_regime,
                INDEX_TREND_STRATEGY_WEIGHTS.get("NEUTRAL", {})
            )
            if self._strategy_allocator:
                self._strategy_allocator.override_weights(weights)
            # 지수 추세 분석은 여전히 실행 (표시용)
            if len(self._index_ohlcv) >= 50:
                self._index_trend = self._analyze_index_trend()
            return

        if len(self._index_ohlcv) < 50:
            return  # 데이터 부족 → 기존 로직 유지

        old_trend = self._index_trend.get("trend") if self._index_trend else None
        old_weights = (
            dict(self._strategy_allocator.weights)
            if self._strategy_allocator else {}
        )

        self._index_trend = self._analyze_index_trend()
        trend = self._index_trend.get("trend", "NEUTRAL")

        weights = INDEX_TREND_STRATEGY_WEIGHTS.get(
            trend, INDEX_TREND_STRATEGY_WEIGHTS["NEUTRAL"]
        )

        if self._strategy_allocator:
            self._strategy_allocator.override_weights(weights)
            self._phase_stats["index_trend_updates"] += 1

        # 추세 변경 이력 기록
        if old_trend != trend:
            ts = self._backtest_date or datetime.now().strftime("%Y-%m-%d %H:%M")
            self._index_trend_history.append({
                "timestamp": ts,
                "from_trend": old_trend,
                "to_trend": trend,
                "from_weights": old_weights,
                "to_weights": dict(weights),
                "trigger_signals": self._index_trend.get("signals", [])[-3:],
            })
            if len(self._index_trend_history) > 20:
                self._index_trend_history = self._index_trend_history[-20:]

    def get_market_intelligence(self) -> Dict:
        """프론트엔드용 마켓 인텔리전스 데이터 반환."""
        trend_key = (self._index_trend or {}).get("trend", self._market_regime)
        return {
            "index_trend": self._index_trend or {
                "trend": "NEUTRAL", "ma_alignment": "MIXED",
                "momentum_score": 50.0, "volatility_state": "NORMAL",
                "signals": ["데이터 대기 중"],
            },
            "strategy_weights": (
                dict(self._strategy_allocator.weights)
                if self._strategy_allocator else {}
            ),
            "strategy_composition": REGIME_STRATEGY_COMPOSITION.get(
                trend_key, REGIME_STRATEGY_COMPOSITION.get("NEUTRAL", {})
            ),
            "vix_ema20": round(self._vix_ema20, 1),
            "market_regime": self._market_regime,
            "actual_market_regime": self._actual_market_regime,
            "regime_locked": self._regime_locked,
            "locked_regime": self._locked_regime,
            "trend_history": self._index_trend_history[-10:],
            "active_strategy_label": REGIME_DISPLAY_NAMES.get(
                trend_key, REGIME_DISPLAY_NAMES.get("NEUTRAL")
            ),
        }

    def _get_vix_sizing_mult(self, strategy: str = "momentum") -> float:
        """Phase 4.5: 전략별 VIX 사이징 배율.

        MR은 변동성 높을 때 기회 → VIX 높으면 사이즈 증가.
        Defensive는 VIX 높을 때 활성화 → 할인 없음.
        나머지(momentum/smc/brt)는 기존 로직 유지.
        """
        vix = self._vix_ema20
        if strategy == "mean_reversion":
            if vix > 25:
                return 1.2
            elif vix > 20:
                return 1.0
            return 0.8
        if strategy == "defensive":
            return 1.0  # defensive는 VIX 할인 없음
        if strategy == "volatility":
            # volatility premium: VIX 높을수록 기회 크므로 사이즈 증가
            if vix > 30:
                return 1.3
            elif vix > 25:
                return 1.1
            return 0.9
        # 기존 로직 (momentum/smc/brt)
        for (lo, hi), mult in VIX_SIZING_SCALE.items():
            if lo <= vix < hi:
                return mult
        return 0.3  # VIX 100+ fallback

    def _reduce_positions_for_regime(self):
        """레짐 다운그레이드 시 초과 포지션을 PnL 하위부터 ES7 청산."""
        regime_params = REGIME_PARAMS.get(self._market_regime, REGIME_PARAMS["NEUTRAL"])
        max_pos = regime_params["max_positions"]
        active = [
            (code, pos) for code, pos in self.positions.items()
            if pos.status == "ACTIVE"
        ]
        if len(active) <= max_pos:
            return

        # PnL 하위부터 초과분 선택
        active_sorted = sorted(active, key=lambda x: x[1].pnl_pct)
        excess_count = len(active) - max_pos
        for code, pos in active_sorted[:excess_count]:
            self._rebalance_exit_codes.add(code)

    # ══════════════════════════════════════════
    # Phase 1: 추세 확인 (TradingLogicFlow.md)
    # ══════════════════════════════════════════

    def _confirm_trend(self, df: pd.DataFrame) -> dict:
        """
        Phase 1: 종목 수준 추세 방향 + 강도 판정.
        Returns: {"direction": "UP"/"DOWN"/"FLAT",
                  "strength": "STRONG"/"MODERATE"/"WEAK",
                  "aligned": bool, "adx": float}
        """
        default = {"direction": "FLAT", "strength": "WEAK", "aligned": False, "adx": 0}
        if len(df) < 200:
            return default

        curr = df.iloc[-1]
        price = float(curr["close"])

        # 정배열: 3/5 이상이면 정배열 인정 (기존 5/5 → 완화)
        mas = [curr.get("ma_short"), curr.get("ma_long"), curr.get("ma60"),
               curr.get("ma120"), curr.get("ma200")]
        alignment_score = 0
        if all(pd.notna(m) for m in mas):
            ma_vals = [float(m) for m in mas]
            if price > ma_vals[0]:
                alignment_score += 1
            for i in range(len(ma_vals) - 1):
                if ma_vals[i] > ma_vals[i + 1]:
                    alignment_score += 1
            aligned = alignment_score >= 3
        else:
            aligned = False

        # ADX/DMI
        adx = float(curr.get("adx", 0)) if pd.notna(curr.get("adx")) else 0
        plus_di = float(curr.get("plus_di", 0)) if pd.notna(curr.get("plus_di")) else 0
        minus_di = float(curr.get("minus_di", 0)) if pd.notna(curr.get("minus_di")) else 0
        trend_exists = adx > 20  # 완화: 발전 중인 추세도 포착 (기존 25)
        bullish_di = plus_di > minus_di

        # 종합: MA정렬 또는 ADX+DI 중 하나면 UP (1/2)
        bull_count = sum([aligned, trend_exists and bullish_di])
        if bull_count >= 2:
            direction = "UP"
        elif aligned or (trend_exists and bullish_di):
            direction = "UP"
        elif not aligned and minus_di > plus_di:
            direction = "DOWN"
        else:
            direction = "FLAT"

        strength = "STRONG" if adx > 40 else "MODERATE" if adx > 25 else "WEAK"

        return {"direction": direction, "strength": strength, "aligned": aligned,
                "adx": adx, "alignment_score": alignment_score}

    # ══════════════════════════════════════════
    # Phase 2: 추세 위치 파악 (TradingLogicFlow.md)
    # ══════════════════════════════════════════

    def _estimate_trend_stage(self, df: pd.DataFrame) -> str:
        """
        Phase 2: EARLY / MID / LATE 판정.
        볼린저 밴드 스퀴즈 비율 + RSI + 52주 고점 근접도 종합.
        """
        if len(df) < 50:
            return "MID"

        curr = df.iloc[-1]
        bb_width = float(curr.get("bb_width", 0)) if pd.notna(curr.get("bb_width")) else 0

        # BB 폭 평균 (50일)
        if "bb_width" in df.columns:
            bb_avg_series = df["bb_width"].rolling(window=50).mean()
            bb_width_avg = float(bb_avg_series.iloc[-1]) if pd.notna(bb_avg_series.iloc[-1]) else bb_width
        else:
            bb_width_avg = bb_width
        if bb_width_avg == 0:
            bb_width_avg = bb_width or 1.0

        rsi = float(curr.get("rsi", 50)) if pd.notna(curr.get("rsi")) else 50
        squeeze_ratio = bb_width / bb_width_avg if bb_width_avg > 0 else 1.0

        # 52주 고점 대비
        close_series = df["close"].astype(float)
        window_52w = min(252, len(close_series))
        high_52w = float(close_series.rolling(window=window_52w).max().iloc[-1])
        price = float(curr["close"])
        pct_of_high = (price / high_52w * 100) if high_52w > 0 else 50

        # 판정
        if squeeze_ratio < 0.8 or (squeeze_ratio < 1.2 and rsi < 65):
            return "EARLY"
        # LATE 판정: 점수 기반 (기존 OR 조건 → 복합 스코어링)
        # 52주 고점 근접만으로 LATE 차단하면 상승 추세 대형주 진입 불가
        late_score = 0
        if squeeze_ratio > 2.0:
            late_score += 2   # BB 과확장 (강한 과열 신호)
        if rsi > 80:
            late_score += 2   # 극단적 과매수 (강한 과열 신호)
        if pct_of_high > 95:
            late_score += 1   # 52주 고점 근접 (단독으로는 약한 신호)
        if pct_of_high > 98:
            late_score += 1   # 52주 최고점 근접 (추가 가중)

        if late_score >= 3:
            return "LATE"
        return "MID"

    # ══════════════════════════════════════════
    # Phase 2.5: 종목별 레짐 분류 (Per-Stock Regime)
    # ══════════════════════════════════════════

    def _classify_stock_regime(self, df: pd.DataFrame) -> str:
        """
        종목 개별 레짐 분류 (0-100 복합 스코어, v2).

        기존 _confirm_trend(), _estimate_trend_stage() 결과를 종합하여
        글로벌 레짐과 독립적으로 각 종목의 추세 상태를 6단계로 판정.

        구성요소:
          (1) MA 정렬 점수 (0-25): alignment_score 0~5 → 0~25
          (2) ADX 방향+기울기 점수 (0-20): UP 추세 + ADX 강도
          (3) RSI 위치 점수 (0-15): 강세/약세 위치 (reduced from 20)
          (4) Price vs MA200 (0-15): 장기 추세 위치
          (5) Trend Stage 보너스 (0-10): EARLY/MID/LATE (reduced from 15)
          (6) Volume Trend — OBV 20일 기울기 (0-15): NEW
        """
        if len(df) < 200:
            return "NEUTRAL"

        trend = self._confirm_trend(df)
        stage = self._estimate_trend_stage(df)
        curr = df.iloc[-1]
        score = 0.0

        # (1) MA 정렬 점수 (0-25): alignment_score 0~5 → 0~25
        alignment = trend.get("alignment_score", 0)
        score += alignment * 5  # 0, 5, 10, 15, 20, 25

        # (2) ADX 방향+기울기 점수 (0-20)
        adx = trend.get("adx", 0)
        direction = trend.get("direction", "FLAT")
        if direction == "UP":
            score += min(adx / 50 * 20, 20)    # ADX 높을수록 가산
        elif direction == "DOWN":
            score += max(0, 5 - adx / 50 * 5)  # 하락+ADX 강 → 낮은 점수
        else:
            score += 10  # FLAT → 중립

        # (3) RSI 위치 점수 (0-15) — reduced from 20
        rsi = float(curr.get("rsi", 50)) if pd.notna(curr.get("rsi")) else 50
        if rsi >= 55:
            score += min((rsi - 40) / 40 * 15, 15)   # RSI 55~80 → 5.6~15
        elif rsi <= 35:
            score += max(0, rsi / 35 * 4)             # RSI 0~35 → 0~4
        else:
            score += 7.5  # 35~55 → 중립

        # (4) Price vs MA200 (0-15) — unchanged
        ma200 = float(curr.get("ma200", 0)) if pd.notna(curr.get("ma200")) else 0
        price = float(curr["close"])
        if ma200 > 0:
            ratio = price / ma200
            if ratio > 1.0:
                score += min((ratio - 1.0) * 100, 15)  # 1%=1pt, max 15
            else:
                score += max(0, 15 - (1.0 - ratio) * 100)
        else:
            score += 7  # 데이터 없으면 중립

        # (5) Trend Stage 보너스 (0-10) — reduced from 15
        stage_bonus = {"EARLY": 10, "MID": 5, "LATE": 1}
        score += stage_bonus.get(stage, 5)

        # (6) Volume Trend — OBV 20일 기울기 (0-15) NEW
        obv_score = 7.5  # 기본값: 중립
        try:
            if len(df) >= 20 and "close" in df.columns and "volume" in df.columns:
                # OBV가 이미 계산되어 있으면 사용, 아니면 인라인 계산
                if "obv" in df.columns:
                    obv_vals = df["obv"].iloc[-20:].dropna()
                else:
                    c = df["close"].iloc[-20:]
                    v = df["volume"].iloc[-20:]
                    obv_vals = (np.sign(c.diff()).fillna(0) * v).cumsum()
                    obv_vals = obv_vals.dropna()

                if len(obv_vals) >= 10:
                    x = np.arange(len(obv_vals))
                    slope, _ = np.polyfit(x, obv_vals.values.astype(float), 1)
                    obv_mean = abs(float(obv_vals.mean()))
                    if obv_mean > 0:
                        norm_slope = slope / obv_mean * 100  # % change per day
                        obv_score = max(0, min(15, 7.5 + norm_slope * 50))
        except Exception:
            obv_score = 7.5
        score += obv_score

        # 스코어 → 레짐 매핑
        score = max(0, min(100, score))
        for threshold, regime in STOCK_REGIME_THRESHOLDS:
            if score >= threshold:
                return regime
        return "STRONG_BEAR"

    def _update_stock_regimes(self, force: bool = False):
        """워치리스트 종목의 개별 레짐 갱신. 성능을 위해 7일 주기로 실행. 2-cycle smoothing."""
        if self._stock_regimes_updated:
            return  # 이미 이번 사이클에서 갱신됨 → 스킵
        self._stock_regimes_updated = True

        # 7일 주기로만 전체 재분류 (성능 최적화)
        self._stock_regime_counter = getattr(self, "_stock_regime_counter", 0) + 1
        if not force and self._stock_regimes and self._stock_regime_counter % 7 != 1:
            return  # 캐시된 결과 사용

        # Initialize pending dict if not exists
        if not hasattr(self, "_stock_regime_pending"):
            self._stock_regime_pending: Dict[str, Tuple[str, int]] = {}

        for w in self._watchlist:
            code = w["code"]
            df = self._ohlcv_cache.get(code)
            if df is None or len(df) < 200:
                self._stock_regimes[code] = "NEUTRAL"  # 데이터 부족 → 중립
                continue

            new_regime = self._classify_stock_regime(df)
            current_regime = self._stock_regimes.get(code, "NEUTRAL")

            if new_regime == current_regime:
                # Same regime → clear any pending transition
                self._stock_regime_pending.pop(code, None)
                continue

            # Check for rapid downgrade (2+ levels) → immediate change (crash protection)
            curr_level = _STOCK_REGIME_LEVEL.get(current_regime, 2)
            new_level = _STOCK_REGIME_LEVEL.get(new_regime, 2)
            if curr_level - new_level >= 2:
                self._stock_regimes[code] = new_regime
                self._stock_regime_pending.pop(code, None)
                continue

            # Normal transition: require 2 consecutive cycles
            pending = self._stock_regime_pending.get(code)
            if pending and pending[0] == new_regime:
                # Same pending regime for 2nd cycle → confirm transition
                self._stock_regimes[code] = new_regime
                self._stock_regime_pending.pop(code, None)
            else:
                # First cycle with new regime → mark as pending
                self._stock_regime_pending[code] = (new_regime, 1)

        # 분포 집계 (PhaseStats)
        dist: Dict[str, int] = {}
        for regime in self._stock_regimes.values():
            dist[regime] = dist.get(regime, 0) + 1
        self._phase_stats["stock_regime_distribution"] = dist

    def _get_stock_affinity(self, code: str, strategy: str) -> float:
        """종목별 레짐에 따른 전략 친화도 반환 (0.0=스킵, 1.0=풀스캔)."""
        stock_regime = self._stock_regimes.get(code, "NEUTRAL")
        affinity_map = STOCK_REGIME_STRATEGY_AFFINITY.get(stock_regime, {})
        return affinity_map.get(strategy, 0.5)  # 미정의 전략은 0.5 (기본)

    # ══════════════════════════════════════════
    # Phase 4: 리스크 게이트 (TradingLogicFlow.md)
    # ══════════════════════════════════════════

    def _risk_gate_check(self) -> tuple:
        """
        Phase 4: 리스크 게이트. 하나라도 실패 시 (False, reason) 반환.

        Phase 3.2 단계적 DD 대응:
          DD > 10% → 포지션 사이즈 50% 감축 (dd_sizing_mult=0.5)
          DD > 15% → 신규 진입 차단
          DD > 20% → 전 포지션 청산, 시스템 정지
        """
        total_equity = self._get_total_equity()
        daily_pnl_pct = (
            (total_equity - self._daily_start_equity) / self._daily_start_equity * 100
            if self._daily_start_equity > 0 else 0
        )

        # RG1: 일일 손실 -10% → 매매 중단
        if daily_pnl_pct <= -10.0:
            return False, "RG1: 일일 손실 -10% 도달"

        # DD 단계적 대응 (Phase 3.2)
        self._peak_equity = max(self._peak_equity, total_equity)
        mdd = (
            (total_equity - self._peak_equity) / self._peak_equity * 100
            if self._peak_equity > 0 else 0
        )

        # RG2c: DD > 20% → 전 포지션 청산 + 시스템 정지
        if mdd <= -20.0:
            self._dd_level = 3
            self._force_liquidate_all("DD>20% 시스템 정지")
            return False, "RG2c: DD -20% — 전 포지션 청산, 시스템 정지"

        # RG2b: DD > 15% → 신규 진입 차단 (기존 포지션은 유지)
        if mdd <= -15.0:
            self._dd_level = 2
            return False, "RG2b: DD -15% — 신규 진입 차단"

        # RG2a: DD > 10% → 사이징 50% 감축 (진입은 허용)
        if mdd <= -10.0:
            self._dd_level = 1
            self._dd_sizing_mult = 0.5
        else:
            self._dd_level = 0
            self._dd_sizing_mult = 1.0

        # RG3: 최대 포지션 수 (regime별)
        active_count = len([p for p in self.positions.values() if p.status == "ACTIVE"])
        regime_params = REGIME_PARAMS.get(self._market_regime, REGIME_PARAMS["NEUTRAL"])
        if active_count >= regime_params["max_positions"]:
            return False, f"RG3: 최대 보유 {regime_params['max_positions']}종목 도달"

        # RG4: 현금 비율 (활성 포지션 수에 따라 동적 적용)
        cash_ratio = self.cash / total_equity if total_equity > 0 else 1.0
        effective_rg4 = self.min_cash_ratio
        if self._allocator:
            ac = sum(1 for p in self.positions.values() if p.status == "ACTIVE")
            if ac <= 2:
                effective_rg4 = max(0.50, self.min_cash_ratio - 0.20)
        # RG4b: 레짐별 현금 비율 오버라이드 (BEAR: 50%, CRISIS: 70%)
        regime_cash = REGIME_OVERRIDES.get(self._market_regime, {}).get("min_cash_override")
        if regime_cash is not None:
            effective_rg4 = max(effective_rg4, regime_cash)

        if cash_ratio < effective_rg4:
            return False, f"RG4: 현금 비율 {effective_rg4*100:.0f}% 미만"

        # RG5: VIX > 30 공포 구간 → 신규 진입 차단
        if self._vix_ema20 > 30:
            return False, f"RG5: VIX 공포구간 ({self._vix_ema20:.1f} > 30)"

        return True, None

    def _force_liquidate_all(self, reason: str):
        """DD>20% 시 모든 ACTIVE 포지션 강제 청산."""
        for code in list(self.positions.keys()):
            pos = self.positions[code]
            if pos.status == "ACTIVE":
                self._rebalance_exit_codes.add(code)

    def force_liquidate_all_immediate(self) -> dict:
        """사용자 긴급 청산: 모든 ACTIVE 포지션을 현재가로 즉시 청산."""
        closed = []
        codes_to_remove = []
        for code in list(self.positions.keys()):
            pos = self.positions[code]
            if pos.status == "ACTIVE":
                sell_price = pos.current_price if pos.current_price > 0 else pos.entry_price
                self._execute_sell(pos, sell_price, "FORCE_LIQUIDATE 사용자 긴급 청산", "FORCE_LIQUIDATE")
                closed.append({
                    "stock_code": pos.stock_code,
                    "stock_name": pos.stock_name,
                    "quantity": pos.quantity,
                    "sell_price": sell_price,
                    "entry_price": pos.entry_price,
                })
                codes_to_remove.append(code)
        for code in codes_to_remove:
            del self.positions[code]
        return {"positions_closed": len(closed), "details": closed}

    def _detect_bearish_divergence(self, df: pd.DataFrame, lookback: int = 10) -> bool:
        """
        베어리시 다이버전스 감지: 가격은 고점 갱신인데 RSI는 고점 하락.
        True → 진입 차단 (모멘텀 약화 신호).
        """
        if len(df) < lookback + 2 or "rsi" not in df.columns:
            return False

        recent = df.iloc[-lookback:]
        price = recent["close"].astype(float)
        rsi = recent["rsi"]

        if rsi.isna().any():
            return False

        price_peaks = []
        rsi_at_peaks = []
        for i in range(1, len(recent) - 1):
            if float(price.iloc[i]) > float(price.iloc[i - 1]) and float(price.iloc[i]) > float(price.iloc[i + 1]):
                price_peaks.append(float(price.iloc[i]))
                rsi_at_peaks.append(float(rsi.iloc[i]))

        if len(price_peaks) >= 2:
            if price_peaks[-1] > price_peaks[-2] and rsi_at_peaks[-1] < rsi_at_peaks[-2]:
                return True

        return False

    def _detect_support_resistance(self, df: pd.DataFrame, lookback: int = 40) -> dict:
        """최근 N봉의 스윙 포인트를 클러스터링하여 S/R 레벨 반환.
        RANGE_BOUND 레짐에서 MR 진입 시 가격이 지지선 근처인지 확인.
        """
        if len(df) < lookback:
            return {"support": [], "resistance": []}

        recent = df.tail(lookback)
        levels: List[tuple] = []

        # 3-candle 프랙탈 기반 스윙 포인트
        highs = recent["high"].astype(float).values
        lows = recent["low"].astype(float).values
        for i in range(1, len(recent) - 1):
            if highs[i] > highs[i - 1] and highs[i] > highs[i + 1]:
                levels.append(("R", float(highs[i])))
            if lows[i] < lows[i - 1] and lows[i] < lows[i + 1]:
                levels.append(("S", float(lows[i])))

        if not levels:
            return {"support": [], "resistance": []}

        # 1.5% 이내 레벨 클러스터링
        clustered = self._cluster_levels(levels, tolerance=0.015)
        return {
            "support": [l for t, l in clustered if t == "S"],
            "resistance": [l for t, l in clustered if t == "R"],
        }

    @staticmethod
    def _cluster_levels(levels: list, tolerance: float = 0.015) -> list:
        """가격 레벨을 tolerance % 이내로 클러스터링.
        각 클러스터에서 가장 빈번한 타입과 평균 가격을 반환.
        """
        if not levels:
            return []

        # 가격순 정렬
        sorted_levels = sorted(levels, key=lambda x: x[1])
        clusters: List[list] = [[sorted_levels[0]]]

        for item in sorted_levels[1:]:
            last_cluster = clusters[-1]
            avg_price = sum(l[1] for l in last_cluster) / len(last_cluster)
            if abs(item[1] - avg_price) / avg_price <= tolerance:
                last_cluster.append(item)
            else:
                clusters.append([item])

        # 각 클러스터에서 대표값 추출
        result = []
        for cluster in clusters:
            avg_price = sum(l[1] for l in cluster) / len(cluster)
            # 다수 타입 결정
            s_count = sum(1 for t, _ in cluster if t == "S")
            r_count = len(cluster) - s_count
            dominant_type = "S" if s_count >= r_count else "R"
            result.append((dominant_type, round(avg_price, 2)))

        return result

    # ══════════════════════════════════════════
    # 진입 시그널 스캔 (6-Phase 통합 파이프라인)
    # ══════════════════════════════════════════

    def _scan_entries(self):
        """
        전략 모드에 따라 진입 스캔 분기.
        multi: 멀티 전략 동시 실행 (레짐별 비중 기반, 자동 전환)
        regime_*: 레짐 고정 + multi 파이프라인 (개별 레짐 전략 테스트)
        momentum/smc/breakout_retest/mean_reversion/arbitrage/defensive: 단일 전략
        """
        if self.strategy_mode == "multi" or self.strategy_mode in REGIME_STRATEGY_MODES:
            return self._scan_entries_multi()
        elif self.strategy_mode == "smc":
            return self._scan_entries_smc()
        elif self.strategy_mode == "breakout_retest":
            return self._scan_entries_breakout_retest()
        elif self.strategy_mode == "mean_reversion":
            return self._scan_entries_mean_reversion()
        elif self.strategy_mode == "arbitrage":
            return self._scan_entries_arbitrage()
        elif self.strategy_mode == "defensive":
            return self._scan_entries_defensive()
        return self._scan_entries_momentum()

    def _scan_entries_multi(self):
        """
        Phase 4 리팩토링: 시그널 수집 → 종목 중복 제거 → 실행.

        1. 모든 활성 전략에서 시그널만 수집 (_collect_mode=True)
        2. 같은 종목 → 최고 strength 시그널만 선택
        3. 선택된 시그널을 전략별 예산 한도 내에서 실행
        """
        allocator = self._strategy_allocator
        if allocator is None:
            return

        # 레짐 갱신 → 전략 비중 재조정
        allocator.update_regime(self._market_regime)

        # Volatility Targeting: 일일 수익률 기록
        total_equity = self._get_total_equity()
        allocator.update_daily_return(total_equity)

        # Phase 3.1: 전략간 상관관계 갱신 (5일마다)
        if len(allocator._daily_returns) % 5 == 0:
            allocator.update_correlation()
            # Phase 7: Risk Parity 비중 갱신 (correlation과 동일 주기)
            allocator.update_risk_parity()

        # Phase 3.4: Dynamic Kelly 갱신
        allocator.update_kelly(self._vix_ema20)

        # Phase 3.1: 전략별 일일 PnL 기록
        for strategy in allocator.strategies:
            strat_pnl = sum(
                (pos.current_price - pos.entry_price) / pos.entry_price * pos.quantity * pos.entry_price
                for pos in self.positions.values()
                if pos.status == "ACTIVE" and pos.strategy_tag == strategy
            )
            allocator.record_strategy_daily_pnl(strategy, strat_pnl)

        # ── Phase 4.3: Day-start 예산 사전 계산 ──
        used_per_strategy: Dict[str, float] = {}
        pos_count_per_strategy: Dict[str, int] = {}
        for pos in self.positions.values():
            if pos.status == "ACTIVE":
                tag = pos.strategy_tag
                used_per_strategy[tag] = used_per_strategy.get(tag, 0) + pos.quantity * pos.current_price
                pos_count_per_strategy[tag] = pos_count_per_strategy.get(tag, 0) + 1

        regime_params = REGIME_PARAMS.get(self._market_regime, REGIME_PARAMS["NEUTRAL"])
        pos_dist = allocator.distribute_positions(regime_params["max_positions"])

        # 전략별 사전 예산 (고정, 실행 중 다른 전략 예산 침범 불가)
        day_budgets: Dict[str, float] = {}
        for strategy in allocator.strategies:
            weight = allocator.weights.get(strategy, 0.0)
            day_budgets[strategy] = max(0.0, total_equity * weight - used_per_strategy.get(strategy, 0.0))

        # ── 1단계: 모든 전략에서 시그널 수집 (실행 없음) ──
        self._collected_signals: List[tuple] = []  # (strategy, signal, trend_str, trend_stage, align)
        self._collect_mode = True

        sorted_strategies = sorted(
            allocator.strategies,
            key=lambda s: allocator.weights.get(s, 0),
            reverse=True,
        )

        for strategy in sorted_strategies:
            if not allocator.is_active(strategy):
                continue
            if day_budgets.get(strategy, 0) <= 0:
                continue
            max_pos = pos_dist.get(strategy, 1)
            if pos_count_per_strategy.get(strategy, 0) >= max_pos:
                continue

            original_mode = self.strategy_mode
            self.strategy_mode = strategy

            if strategy == "momentum":
                self._scan_entries_momentum()
            elif strategy == "smc":
                self._scan_entries_smc()
            elif strategy == "breakout_retest":
                self._scan_entries_breakout_retest()
            elif strategy == "mean_reversion":
                self._scan_entries_mean_reversion()
            elif strategy == "defensive":
                self._scan_entries_defensive()
            elif strategy == "volatility":
                self._scan_entries_volatility()
            elif strategy == "arbitrage":
                self._scan_entries_arbitrage()

            self.strategy_mode = original_mode

        self._collect_mode = False

        # ── 2단계: 종목별 최적 시그널 선택 ──
        # 종목별 레짐 친화도를 강도 배율로 적용하여 라우팅
        best_per_stock: Dict[str, tuple] = {}
        for sig_tuple in self._collected_signals:
            strategy, signal = sig_tuple[0], sig_tuple[1]
            code = signal.stock_code

            # Apply per-stock regime affinity as strength multiplier
            affinity = self._get_stock_affinity(code, strategy)
            if affinity <= 0.0:
                continue  # Skip zero-affinity signals
            # Scale effective strength by affinity
            effective_strength = signal.strength * affinity

            if code not in best_per_stock:
                best_per_stock[code] = (sig_tuple, effective_strength)
            else:
                _, existing_eff = best_per_stock[code]
                if effective_strength > existing_eff:
                    best_per_stock[code] = (sig_tuple, effective_strength)

        dedup_skips = len(self._collected_signals) - len(best_per_stock)
        if dedup_skips > 0:
            self._phase_stats["multi_dedup_skips"] += dedup_skips

        # ── 2.5단계: 유휴 예산은 재분배하지 않음 ──
        # 미사용 예산을 재분배하면 momentum 과잉 배분 → 저품질 진입 증가
        # 비활성 전략 예산은 현금으로 유보 (자연스러운 포지션 사이징 제약)

        # ── 3단계: 선택된 시그널을 전략별 예산 한도 내에서 실행 ──
        sorted_signals = sorted(best_per_stock.values(), key=lambda x: x[1], reverse=True)

        exec_count_per_strategy: Dict[str, int] = {}
        for item in sorted_signals:
            sig_tuple = item[0]
            strategy, signal, trend_str, trend_stage, align = sig_tuple
            if day_budgets.get(strategy, 0) <= 0:
                continue
            max_pos = pos_dist.get(strategy, 1)
            current_count = pos_count_per_strategy.get(strategy, 0) + exec_count_per_strategy.get(strategy, 0)
            if current_count >= max_pos:
                continue

            original_mode = self.strategy_mode
            self.strategy_mode = strategy
            self._execute_buy(signal, trend_strength=trend_str,
                             trend_stage=trend_stage, alignment_score=align)
            self.strategy_mode = original_mode

            exec_count_per_strategy[strategy] = exec_count_per_strategy.get(strategy, 0) + 1

            # 종목 레짐→전략 라우팅 이력 기록
            _sig_stock_regime = self._stock_regimes.get(signal.stock_code, self._market_regime)
            rsm = self._phase_stats["stock_regime_strategy_map"]
            rsm_key = f"{_sig_stock_regime}→{strategy}"
            rsm[rsm_key] = rsm.get(rsm_key, 0) + 1

        self._collected_signals = []

    # ── Phase 3.3: Defensive 전략 (인버스 ETF) ──

    def _scan_entries_defensive(self):
        """
        Defensive 전략: BEAR/RANGE_BOUND 레짐 시 인버스 ETF + 안전자산 매수.

        조건:
        - 레짐이 BEAR/CRISIS 또는 (RANGE_BOUND/NEUTRAL AND VIX > threshold)
        - 인버스 ETF / 안전자산 OHLCV 데이터 존재
        - 이미 보유 중이 아닌 것
        """
        # 레짐별 VIX 진입 임계값 (BEAR: 20, 기본: 25)
        _def_ro = REGIME_OVERRIDES.get(self._market_regime, {})
        vix_threshold = _def_ro.get("defensive_vix_threshold", 25)

        # STRONG_BULL/BULL에서는 진입하지 않음
        if self._market_regime in ("STRONG_BULL", "BULL"):
            return
        if self._market_regime == "NEUTRAL" and self._vix_ema20 < vix_threshold:
            return

        # 마켓에 맞는 인버스 ETF 목록
        market_key = "sp500"  # 기본값
        if "kospi" in self.market_id.lower():
            market_key = "kospi"
        elif "nasdaq" in self.market_id.lower():
            market_key = "nasdaq"

        # 인버스 ETF + CRISIS 안전자산 합산
        defensive_tickers = list(INVERSE_ETFS.get(market_key, []))
        if _def_ro.get("safe_haven_enabled"):
            for item in SAFE_HAVEN_ETFS.get(market_key, []):
                ticker = item["ticker"]
                if ticker not in defensive_tickers:
                    defensive_tickers.append(ticker)

        if not defensive_tickers:
            return

        for ticker in defensive_tickers:
            # 이미 보유 중이면 스킵
            if ticker in self.positions and self.positions[ticker].status == "ACTIVE":
                continue

            df = self._ohlcv_cache.get(ticker)
            if df is None or len(df) < 20:
                continue

            price = float(df.iloc[-1]["close"])
            if price <= 0:
                continue

            # 시그널 생성 (고정 strength — defensive는 레짐 기반)
            strength = 70 if self._market_regime in ("BEAR", "CRISIS") else 50
            if self._vix_ema20 > 30:
                strength += 10
            # CRISIS 안전자산은 추가 강도
            is_safe_haven = any(
                item["ticker"] == ticker
                for item in SAFE_HAVEN_ETFS.get(market_key, [])
            )
            if is_safe_haven and self._market_regime == "CRISIS":
                strength += 15

            ticker_name = f"SafeHaven_{ticker}" if is_safe_haven else f"Inv_{ticker}"

            self._signal_counter += 1
            signal = SimSignal(
                id=f"sim-sig-{self._signal_counter:04d}",
                stock_code=ticker,
                stock_name=ticker_name,
                type="BUY",
                price=price,
                strength=strength,
                reason=f"Defensive: {self._market_regime} regime, VIX={self._vix_ema20:.1f}",
                detected_at=self._get_current_iso(),
            )
            self._execute_buy(
                signal,
                trend_strength="MODERATE",
                trend_stage="MID",
                alignment_score=3,
            )

    def _check_exits_defensive(self):
        """
        Defensive 전략 청산: 레짐이 BULL로 전환되면 청산.
        또는 일반 ES1 손절(-5%) 적용.
        """
        to_close: List[str] = []

        for code, pos in self.positions.items():
            if pos.status != "ACTIVE":
                continue
            if self._exit_tag_filter and pos.strategy_tag != self._exit_tag_filter:
                continue

            current_price = self._current_prices.get(code, pos.current_price)
            entry_price = pos.entry_price
            pnl_pct = (current_price - entry_price) / entry_price

            exit_reason = None
            exit_type = None

            # ES1: 하드 손절 -5%
            if pnl_pct <= -0.05:
                exit_reason = "ES1: 손절 -5%"
                exit_type = "STOP_LOSS"

            # 레짐이 BULL로 전환 → 인버스 청산
            elif self._market_regime == "BULL":
                exit_reason = "DEF_REGIME: BULL 전환 청산"
                exit_type = "REGIME_EXIT"

            # 익절: +10% (인버스는 보수적 TP)
            elif pnl_pct >= 0.10:
                exit_reason = "DEF_TP: 익절 +10%"
                exit_type = "TAKE_PROFIT"

            # 트레일링: +5% 이상이면 2×ATR 트레일링
            elif pnl_pct >= 0.05:
                df = self._ohlcv_cache.get(code)
                if df is not None and "atr" in df.columns and len(df) > 0:
                    atr_val = float(df.iloc[-1].get("atr", 0))
                    if atr_val > 0:
                        trail_stop = pos.highest_price - 2.0 * atr_val
                        if current_price <= trail_stop:
                            exit_reason = f"DEF_TRAIL: 트레일링 (ATR×2.0)"
                            exit_type = "TRAILING_STOP"

            if exit_reason:
                to_close.append(code)
                self._close_position(code, current_price, exit_reason, exit_type)

        for code in to_close:
            if code in self.positions:
                del self.positions[code]

    # ─────────────────────────────────────────────────────
    # Phase 6: Volatility Premium Strategy
    # ─────────────────────────────────────────────────────

    def _scan_entries_volatility(self):
        """
        VIX Mean Reversion: VIX 급등 후 하락 반전 시 SPY/QQQ 매수.
        변동성 프리미엄 수확 — VIX가 평균 회귀할 때 주가 반등 포착.

        진입 조건:
        - VIX EMA20 > 22 (변동성 상승 확인)
        - VIX 3일 연속 하락 (하락 반전)
        - RSI(VIX 대리: 시장 RSI < 45) — 시장이 아직 과매도 영역

        청산:
        - VIX EMA20 < 18 (정상화 완료) OR 20일 보유 OR -5% SL
        """
        # VIX 데이터 필요
        if self._vix_ema20 is None or self._vix_ema20 <= 0:
            return

        # 진입 조건: VIX 높고 하락 중
        if self._vix_ema20 < 22:
            return

        # VIX 3일 연속 하락 체크 (VIX 히스토리 필요)
        vix_history = getattr(self, '_vix_history', [])
        if len(vix_history) < 4:
            return

        vix_declining = all(
            vix_history[-i] < vix_history[-i-1]
            for i in range(1, 4)
        )
        if not vix_declining:
            return

        # 리스크 게이트
        can_trade, _ = self._risk_gate_check()
        if not can_trade:
            return

        # 타겟: 대형 ETF 또는 시장 대표 종목 (워치리스트에서 유동성 높은 종목)
        vol_targets = ["SPY", "QQQ", "AAPL", "MSFT", "AMZN", "GOOGL", "META", "NVDA"]
        for code in vol_targets:
            if code in self.positions and self.positions[code].status == "ACTIVE":
                continue

            df = self._ohlcv_cache.get(code)
            if df is None or len(df) < 20:
                continue

            df = self._calculate_indicators(df.copy())
            if df.empty:
                continue
            self._ohlcv_cache[code] = df

            curr = df.iloc[-1]
            price = self._current_prices.get(code, float(curr["close"]))

            # 시장 RSI < 50 (아직 반등 여지 있음)
            rsi = float(curr.get("rsi", 50)) if pd.notna(curr.get("rsi")) else 50
            if rsi > 50:
                continue

            # 시그널 강도: VIX 높을수록 + RSI 낮을수록 강함
            strength = min(int(30 + (self._vix_ema20 - 22) * 5 + (50 - rsi)), 100)

            self._signal_counter += 1
            signal = SimSignal(
                id=f"sim-sig-{self._signal_counter:04d}",
                stock_code=code,
                stock_name=self._stock_names.get(code, code),
                type="BUY",
                price=price,
                reason=f"VOL_PREMIUM VIX={self._vix_ema20:.1f} RSI={rsi:.0f}",
                strength=strength,
                detected_at=self._get_current_iso(),
            )

            if self._collect_mode:
                self._collected_signals.append((self.strategy_mode, signal, "MODERATE", "MID", 3))
            else:
                self._execute_buy(signal, "MODERATE", "MID", 3)

    def _check_exits_volatility(self):
        """Volatility Premium 청산: VIX 정상화 OR 20일 보유 OR -5% SL."""
        to_close: List[str] = []

        for code, pos in self.positions.items():
            if pos.status != "ACTIVE" or pos.strategy_tag != "volatility":
                continue

            current_price = self._current_prices.get(code, pos.current_price)
            entry_price = pos.entry_price
            pnl_pct = (current_price - entry_price) / entry_price

            exit_reason = None
            exit_type = None

            # ES1: -5% 손절
            if pnl_pct <= -0.05:
                exit_reason = "ES_VOL SL -5%"
                exit_type = "STOP_LOSS"

            # VIX 정상화 청산 (VIX < 18)
            elif self._vix_ema20 is not None and self._vix_ema20 < 18:
                exit_reason = f"ES_VOL VIX 정상화 ({self._vix_ema20:.1f})"
                exit_type = "VOLATILITY_TP"

            # 익절: +8%
            elif pnl_pct >= 0.08:
                exit_reason = "ES_VOL TP +8%"
                exit_type = "TAKE_PROFIT"

            # 20일 보유 초과
            elif pos.days_held > 20:
                exit_reason = "ES_VOL 보유기간 20일 초과"
                exit_type = "MAX_HOLDING"

            # 트레일링: +4%에서 활성
            elif pnl_pct >= 0.04:
                df = self._ohlcv_cache.get(code)
                if df is not None and "atr" in df.columns:
                    atr_val = float(df.iloc[-1].get("atr", 0)) if pd.notna(df.iloc[-1].get("atr")) else 0
                    if atr_val > 0:
                        trail_stop = pos.highest_price - 2.0 * atr_val
                        if current_price <= trail_stop:
                            exit_reason = "ES_VOL 트레일링"
                            exit_type = "TRAILING_STOP"

            if exit_reason:
                to_close.append(code)
                self._execute_sell(pos, current_price, exit_reason, exit_type or "")

        for code in to_close:
            if code in self.positions:
                del self.positions[code]

    def _get_candle_score(self, code: str) -> int:
        """P2: Quick candlestick pattern score from raw OHLCV, cached per day."""
        cache_key = f"{code}_{self._backtest_date}"
        if cache_key in self._candle_score_cache:
            return self._candle_score_cache[cache_key]

        df = self._ohlcv_cache.get(code)
        if df is None or len(df) < 3:
            return 0

        score = 0
        c = df['close'].values.astype(float)
        o = df['open'].values.astype(float)
        h = df['high'].values.astype(float)
        lo = df['low'].values.astype(float)

        # Last bar
        body = c[-1] - o[-1]
        prev_body = c[-2] - o[-2]
        body_abs = abs(body)
        prev_body_abs = abs(prev_body)

        # Bullish Engulfing (+30)
        if prev_body < 0 and body > 0 and o[-1] <= c[-2] and c[-1] >= o[-2]:
            score += 30
        # Bearish Engulfing (-30)
        elif prev_body > 0 and body < 0 and o[-1] >= c[-2] and c[-1] <= o[-2]:
            score -= 30

        # Hammer (+25) — small body top, long lower shadow
        lower_shadow = min(c[-1], o[-1]) - lo[-1]
        upper_shadow = h[-1] - max(c[-1], o[-1])
        if body_abs > 0 and lower_shadow >= 2 * body_abs and upper_shadow < body_abs:
            # Check 3+ down bars context
            down_count = 0
            for i in range(2, min(6, len(c))):
                if c[-i] < o[-i]:
                    down_count += 1
                else:
                    break
            if down_count >= 3:
                score += 25

        # Shooting Star (-25)
        if body_abs > 0 and upper_shadow >= 2 * body_abs and lower_shadow < body_abs:
            up_count = 0
            for i in range(2, min(6, len(c))):
                if c[-i] > o[-i]:
                    up_count += 1
                else:
                    break
            if up_count >= 3:
                score -= 25

        # Morning Star (+30) — 3-candle
        if len(df) >= 3:
            body_2 = c[-3] - o[-3]
            body_1_abs = abs(c[-2] - o[-2])
            hl_range_1 = h[-2] - lo[-2]
            midpoint = o[-3] + body_2 / 2
            if (body_2 < 0 and body > 0
                    and hl_range_1 > 0 and body_1_abs < 0.1 * hl_range_1
                    and c[-1] > midpoint):
                score += 30

        # Evening Star (-30)
        if len(df) >= 3:
            body_2 = c[-3] - o[-3]
            body_1_abs = abs(c[-2] - o[-2])
            hl_range_1 = h[-2] - lo[-2]
            midpoint = o[-3] + body_2 / 2
            if (body_2 > 0 and body < 0
                    and hl_range_1 > 0 and body_1_abs < 0.1 * hl_range_1
                    and c[-1] < midpoint):
                score -= 30

        # Doji (±15 based on shadow direction)
        hl_range = h[-1] - lo[-1]
        if hl_range > 0 and body_abs < 0.1 * hl_range:
            if lower_shadow > 2 * upper_shadow:
                score += 15  # Dragonfly Doji (bullish)
            elif upper_shadow > 2 * lower_shadow:
                score -= 15  # Gravestone Doji (bearish)

        # Clamp
        score = max(-100, min(100, score))
        self._candle_score_cache[cache_key] = score
        return score

    def _get_fib_alignment(self, code: str) -> float:
        """P3: Fibonacci level proximity score (0.0 to 1.0)."""
        df = self._ohlcv_cache.get(code)
        if df is None or len(df) < 30:
            return 0.0

        close = df['close'].values
        high = df['high'].values
        low = df['low'].values
        price = close[-1]

        # Find recent swing high and swing low (last 50 bars)
        lookback = min(50, len(df))
        recent_high = np.max(high[-lookback:])
        recent_low = np.min(low[-lookback:])
        swing_range = recent_high - recent_low
        if swing_range <= 0:
            return 0.0

        # Key Fib levels (retracement from high)
        fib_levels = [
            recent_high - swing_range * 0.382,
            recent_high - swing_range * 0.500,
            recent_high - swing_range * 0.618,
        ]

        # Score = how close price is to nearest Fib level (within 2% = max score)
        min_dist = min(abs(price - level) / price for level in fib_levels)
        if min_dist < 0.02:
            return 1.0 - (min_dist / 0.02)  # Linear decay from 1.0 at level to 0.0 at 2% away
        return 0.0

    def _get_chart_pattern_score(self, code: str) -> int:
        """P3: Simple chart pattern detection from raw OHLCV."""
        cache_key = f"cp_{code}_{self._backtest_date}"
        if cache_key in self._candle_score_cache:  # reuse same cache dict
            return self._candle_score_cache[cache_key]

        df = self._ohlcv_cache.get(code)
        if df is None or len(df) < 30:
            return 0

        score = 0
        close = df['close'].values
        high = df['high'].values
        low = df['low'].values
        volume = df['volume'].values if 'volume' in df.columns else None
        price = close[-1]

        # Double Bottom detection (simplified)
        lookback = min(60, len(df))
        lows_arr = low[-lookback:]
        # Find two local minimums
        min1_idx = np.argmin(lows_arr[:lookback // 2])
        min2_idx = lookback // 2 + np.argmin(lows_arr[lookback // 2:])
        min1 = lows_arr[min1_idx]
        min2 = lows_arr[min2_idx]

        if min1 > 0 and abs(min1 - min2) / min1 < 0.03:  # Within 3%
            neckline = np.max(high[-lookback:][min1_idx:min2_idx]) if min2_idx > min1_idx else 0
            if neckline > 0 and price > neckline:
                score += 70  # Double bottom confirmed

        # Bull Flag detection (simplified)
        if len(df) >= 20:
            atr = np.mean(high[-20:] - low[-20:])
            # Check for impulse: 5-bar move > 2*ATR
            impulse_move = close[-15] - close[-20] if len(df) >= 20 else 0
            if atr > 0 and impulse_move > 2 * atr:
                # Check consolidation: last 10 bars range < 50% of impulse
                consol_range = np.max(high[-10:]) - np.min(low[-10:])
                if consol_range < 0.5 * abs(impulse_move):
                    # Check declining volume
                    if volume is not None:
                        vol_start = np.mean(volume[-15:-10])
                        vol_end = np.mean(volume[-5:])
                        if vol_end < vol_start:
                            score += 60

        score = max(-100, min(100, score))
        self._candle_score_cache[cache_key] = score
        return score

    def _scan_entries_momentum(self):
        """
        6-Phase 통합 파이프라인 (기존 Momentum Swing):
        Phase 0 (시장 체제) → Phase 4 (리스크 게이트) → 종목별 Phase 1→2→3
        """
        # ── Phase 0: 시장 체제 판단 ──
        self._update_market_regime()
        # BEAR 체제: 제한적 거래 허용 (max_positions=2, max_weight=5%)
        # 하드블록 대신 REGIME_PARAMS가 RG3에서 포지션 수 제한

        # ── Phase 4: 리스크 게이트 (사전 체크) ──
        can_trade, block_reason = self._risk_gate_check()
        if not can_trade:
            self._phase_stats["phase4_risk_blocks"] += 1
            self._add_risk_event("WARNING", f"진입 차단: {block_reason}")
            return

        total_equity = self._get_total_equity()
        regime_params = REGIME_PARAMS.get(self._market_regime, REGIME_PARAMS["NEUTRAL"])

        active_count = len([p for p in self.positions.values() if p.status == "ACTIVE"])

        if active_count >= regime_params["max_positions"]:
            return

        new_signals: List[tuple] = []  # (signal, trend_strength, trend_stage)

        for w in self._watchlist:
            code = w["code"]

            # B5: 종목별 레짐 기반 전략 필터링
            if self._get_stock_affinity(code, "momentum") <= 0.0:
                continue

            # STRONG_BULL 피라미딩: 기존 보유 종목도 조건부 추가 매수 허용
            is_pyramid = False
            _pyr_ro = REGIME_OVERRIDES.get(self._market_regime, {})
            if code in self.positions and self.positions[code].status in ("ACTIVE", "PENDING"):
                pos_existing = self.positions[code]
                if (_pyr_ro.get("pyramiding_enabled")
                        and pos_existing.strategy_tag == "momentum"
                        and pos_existing.scale_count < _pyr_ro.get("pyramiding_max", 1)
                        and pos_existing.days_held >= 5):
                    cur_px = self._current_prices.get(code, pos_existing.current_price)
                    eff_entry = pos_existing.avg_entry_price if pos_existing.avg_entry_price > 0 else pos_existing.entry_price
                    pnl_ratio = (cur_px - eff_entry) / eff_entry if eff_entry > 0 else 0
                    if pnl_ratio >= _pyr_ro.get("pyramiding_pnl_min", 0.05):
                        is_pyramid = True  # 피라미딩 조건 충족, fall through
                    else:
                        continue
                else:
                    continue

            df = self._ohlcv_cache.get(code)
            if df is None or len(df) < self.ma_long + 5:
                continue

            df = self._calculate_indicators(df.copy())
            if df.empty or len(df) < 2:
                continue

            self._phase_stats["total_scans"] += 1

            # ── Phase 1: 추세 확인 ──
            trend = self._confirm_trend(df)
            if trend["direction"] != "UP":
                self._phase_stats["phase1_trend_rejects"] += 1
                if code in self._debug_tickers:
                    print(
                        f"[DIAG] {code} Phase1 REJECT: direction={trend['direction']} "
                        f"adx={trend['adx']:.1f} aligned={trend['aligned']}"
                    )
                continue  # FLAT/DOWN 종목 스킵

            # ── Phase 2: 추세 위치 파악 ──
            stage = self._estimate_trend_stage(df)
            if stage == "LATE":
                self._phase_stats["phase2_late_rejects"] += 1
                if code in self._debug_tickers:
                    _curr = df.iloc[-1]
                    _rsi = float(_curr.get("rsi", 0)) if pd.notna(_curr.get("rsi")) else 0
                    _close = float(_curr["close"])
                    _52w_h = float(df["close"].astype(float).rolling(min(252, len(df))).max().iloc[-1])
                    _pct_h = (_close / _52w_h * 100) if _52w_h > 0 else 0
                    print(
                        f"[DIAG] {code} Phase2 LATE REJECT: rsi={_rsi:.1f} "
                        f"pct_of_52w_high={_pct_h:.1f}%"
                    )
                continue  # 말기 종목 진입 스킵

            # ── Phase 3: 진입 시그널 ──
            curr = df.iloc[-1]
            prev = df.iloc[-2]

            primary = []
            confirmations = []

            # PS1: 골든크로스
            if (
                pd.notna(curr["ma_short"])
                and pd.notna(curr["ma_long"])
                and pd.notna(prev["ma_short"])
                and pd.notna(prev["ma_long"])
            ):
                if prev["ma_short"] <= prev["ma_long"] and curr["ma_short"] > curr["ma_long"]:
                    primary.append("PS1")

            # PS2: MACD 골든크로스 + 기울기 필터
            if pd.notna(curr.get("macd_hist")) and pd.notna(prev.get("macd_hist")):
                if prev["macd_hist"] <= 0 and curr["macd_hist"] > 0:
                    # 3봉 기울기 양수 확인 (감속 크로스 필터링)
                    if len(df) >= 4:
                        hist_3ago = float(df.iloc[-3].get("macd_hist", 0)) if pd.notna(df.iloc[-3].get("macd_hist")) else 0
                        slope = float(curr["macd_hist"]) - hist_3ago
                        if slope > 0:
                            primary.append("PS2")
                    else:
                        primary.append("PS2")

            # PS3: MA 풀백 진입 (추세 지속 시그널)
            # 확립된 상승 추세에서 MA20 지지 확인 후 반등 → 대형 주도주 포착
            if not primary:
                if (
                    pd.notna(curr["ma_short"])
                    and pd.notna(curr["ma_long"])
                    and pd.notna(curr.get("ma60"))
                    and len(df) >= 5
                ):
                    ma_short_val = float(curr["ma_short"])
                    ma_long_val = float(curr["ma_long"])
                    ma60_val = float(curr["ma60"])
                    price = float(curr["close"])
                    prev_price = float(prev["close"])

                    # 조건1: 확립된 상승 정배열 (MA5 > MA20 > MA60)
                    uptrend = (ma_short_val > ma_long_val > ma60_val)

                    if uptrend:
                        # 조건2: 최근 3봉 내 MA20 근처까지 풀백 (2% 이내 접근)
                        recent_lows = df["low"].astype(float).iloc[-4:-1]
                        pullback_zone = ma_long_val * 1.02
                        ma20_proximity = any(
                            low <= pullback_zone for low in recent_lows
                        )

                        # 조건3: 현재 종가 > MA20 (지지 확인 후 반등)
                        above_ma20 = price > ma_long_val

                        # 조건4: 상승 봉 (현재 종가 > 전일 종가)
                        bounce_confirm = price > prev_price

                        if ma20_proximity and above_ma20 and bounce_confirm:
                            primary.append("PS3")
                            self._phase_stats["phase3_ps3_pullback"] += 1

            # PS4: Donchian Channel 돌파 (STRONG_BULL 전용 — 독립 시그널)
            _mom_ro = REGIME_OVERRIDES.get(self._market_regime, {})
            ps4_donchian = False
            if _mom_ro.get("donchian_entry") and "donchian_high" in df.columns:
                prev_donchian = prev.get("donchian_high") if pd.notna(prev.get("donchian_high")) else None
                if prev_donchian is not None and float(curr["close"]) > float(prev_donchian):
                    ps4_donchian = True
                    primary.append("PS4")
                    self._phase_stats.setdefault("phase3_ps4_donchian", 0)
                    self._phase_stats["phase3_ps4_donchian"] += 1

            if not primary:
                self._phase_stats["phase3_no_primary"] += 1
                if code in self._debug_tickers:
                    _rsi = float(curr.get("rsi", 0)) if pd.notna(curr.get("rsi")) else 0
                    _ma_s = float(curr.get("ma_short", 0)) if pd.notna(curr.get("ma_short")) else 0
                    _ma_l = float(curr.get("ma_long", 0)) if pd.notna(curr.get("ma_long")) else 0
                    _ma60 = float(curr.get("ma60", 0)) if pd.notna(curr.get("ma60")) else 0
                    _macd_h = float(curr.get("macd_hist", 0)) if pd.notna(curr.get("macd_hist")) else 0
                    print(
                        f"[DIAG] {code} Phase3 NO PRIMARY: ma5={_ma_s:.0f} ma20={_ma_l:.0f} "
                        f"ma60={_ma60:.0f} ma5>ma20={_ma_s > _ma_l} rsi={_rsi:.1f} "
                        f"macd_hist={_macd_h:.4f}"
                    )
                continue

            # CF1: RSI 적정 범위 (52-78)
            if pd.notna(curr["rsi"]) and self.rsi_lower <= curr["rsi"] <= self.rsi_upper:
                confirmations.append("CF1")

            # CF2: 거래량 돌파
            if pd.notna(curr["volume_ma"]) and curr["volume_ma"] > 0:
                if float(curr["volume"]) >= curr["volume_ma"] * self.volume_multiplier:
                    confirmations.append("CF2")

            # CF3: 슬로우 RSI 멀티 타임프레임 확인 (28일)
            if pd.notna(curr.get("rsi_slow")) and 45 <= float(curr["rsi_slow"]) <= 70:
                confirmations.append("CF3")

            # PS3 전용: 추세 지속 진입은 완화된 확인 임계값 사용
            # 입증된 상승 추세이므로 RSI/거래량 기준을 낮춰도 안전
            if "PS3" in primary and not confirmations:
                # CF1_R: RSI 42-82 (기존 52-78 → 완화)
                if pd.notna(curr["rsi"]) and 42 <= float(curr["rsi"]) <= 82:
                    confirmations.append("CF1_R")

                # CF2_R: 거래량 >= MA20 × 1.0 (기존 1.5 → 완화, 대형주 안정 거래량 반영)
                if pd.notna(curr["volume_ma"]) and curr["volume_ma"] > 0:
                    if float(curr["volume"]) >= curr["volume_ma"] * 1.0:
                        confirmations.append("CF2_R")

            if not confirmations:
                self._phase_stats["phase3_no_confirm"] += 1
                if code in self._debug_tickers:
                    _rsi = float(curr.get("rsi", 0)) if pd.notna(curr.get("rsi")) else 0
                    _vol = float(curr["volume"])
                    _vol_ma = float(curr["volume_ma"]) if pd.notna(curr["volume_ma"]) else 1
                    print(
                        f"[DIAG] {code} Phase3 NO CONFIRM: primary={primary} "
                        f"rsi={_rsi:.1f} vol_ratio={_vol / _vol_ma:.2f}"
                    )
                continue

            # 베어리시 다이버전스 필터 (가격↑ RSI↓ → 모멘텀 약화)
            if self._detect_bearish_divergence(df):
                self._phase_stats["divergence_blocks"] += 1
                continue



            # 시그널 강도 계산 (연속 스코어링)
            adx = trend.get("adx", 0)
            rsi = float(curr.get("rsi", 50)) if pd.notna(curr.get("rsi")) else 50
            vol_ratio = float(curr["volume"]) / float(curr["volume_ma"]) if pd.notna(curr["volume_ma"]) and float(curr["volume_ma"]) > 0 else 1.0

            # PS3는 추세 지속 시그널이므로 개시 시그널(PS1/PS2) 대비 낮은 강도
            ps3_penalty = -10 if "PS3" in primary else 0
            ps4_bonus = 20 if ps4_donchian else 0  # Donchian 돌파 시 +20
            base_strength = len(primary) * 25 + len(confirmations) * 15 + ps3_penalty + ps4_bonus
            trend_bonus = min(int(adx * 0.5), 25)  # ADX 연속값 → 최대 25점
            stage_bonus = 15 if stage == "EARLY" else 8 if stage == "MID" else 0
            rsi_quality = max(0, int(10 - abs(rsi - 55) * 0.5))  # RSI 55 이상대
            volume_bonus = min(int((vol_ratio - 1.5) * 10), 10) if vol_ratio > 1.5 else 0
            strength = min(max(base_strength + trend_bonus + stage_bonus + rsi_quality + volume_bonus, 10), 100)

            # P2: Candlestick pattern bonus
            candle_score = self._get_candle_score(code)
            if candle_score > 20:
                strength += 10
            elif candle_score < -20:
                strength -= 5  # Bearish candle near entry = reduce confidence

            # P3: Fibonacci alignment & chart pattern bonus
            fib_score = self._get_fib_alignment(code)
            if fib_score > 0.5:
                strength += 8
            chart_pattern_score = self._get_chart_pattern_score(code)
            if chart_pattern_score > 50:
                strength += 12

            strength = min(max(strength, 10), 100)

            # B8: Minimum strength filter to reduce ES1 fires
            if strength < 45:
                self._phase_stats.setdefault("b8_strength_blocks", 0)
                self._phase_stats["b8_strength_blocks"] += 1
                continue  # Skip weak signals that are likely to stop out

            current_price = self._current_prices.get(code, float(curr["close"]))

            self._signal_counter += 1
            signal = SimSignal(
                id=f"sim-sig-{self._signal_counter:04d}",
                stock_code=code,
                stock_name=w["name"],
                type="BUY",
                price=current_price,
                reason=f"{'PYR_' if is_pyramid else ''}{'+'.join(primary)} {'+'.join(confirmations)} [trend={trend['strength']}, stage={stage}]",
                strength=min(strength, 100),
                detected_at=self._get_current_iso(),
            )
            new_signals.append((signal, trend["strength"], stage, trend.get("alignment_score", 3)))

            if code in self._debug_tickers:
                print(
                    f"[DIAG] {code} ✅ SIGNAL: primary={primary} confirm={confirmations} "
                    f"strength={strength} stage={stage} price={current_price:.0f}"
                )

        # 시그널 강도순 정렬 후 매수 실행
        new_signals.sort(key=lambda x: x[0].strength, reverse=True)

        for sig, trend_strength, trend_stage, align_score in new_signals:
            if active_count >= regime_params["max_positions"]:
                break
            self.signals.append(sig)
            if len(self.signals) > 100:
                self.signals = self.signals[-100:]

            self._execute_buy(sig, trend_strength=trend_strength,
                             trend_stage=trend_stage, alignment_score=align_score)
            self._phase_stats["entries_executed"] += 1
            active_count += 1

    # ══════════════════════════════════════════
    # SMC 4-Layer 진입 스캔
    # ══════════════════════════════════════════

    def _scan_entries_smc(self):
        """
        SMC 4-Layer 스코어링 기반 진입 스캔.
        Phase 0 (시장 체제) + Phase 4 (리스크 게이트) → SMC 스코어링 → 매수 실행.
        """
        # ── Phase 0: 시장 체제 판단 ──
        self._update_market_regime()

        # ── Phase 4: 리스크 게이트 (사전 체크) ──
        can_trade, block_reason = self._risk_gate_check()
        if not can_trade:
            self._phase_stats["phase4_risk_blocks"] += 1
            self._add_risk_event("WARNING", f"SMC 진입 차단: {block_reason}")
            return

        total_equity = self._get_total_equity()
        regime_params = REGIME_PARAMS.get(self._market_regime, REGIME_PARAMS["NEUTRAL"])

        active_count = len([p for p in self.positions.values() if p.status == "ACTIVE"])

        if active_count >= regime_params["max_positions"]:
            return

        new_signals: List[tuple] = []

        for w in self._watchlist:
            code = w["code"]

            # B5: 종목별 레짐 기반 전략 필터링
            if self._get_stock_affinity(code, "smc") <= 0.0:
                continue

            if code in self.positions and self.positions[code].status in ("ACTIVE", "PENDING"):
                continue

            df = self._ohlcv_cache.get(code)
            if df is None or len(df) < 50:
                continue

            df = self._calculate_indicators_smc(df.copy())
            if df.empty or len(df) < 2:
                continue

            self._phase_stats["total_scans"] += 1

            curr = df.iloc[-1]

            # ── SMC 4-Layer 스코어링 ──
            score_smc = self._score_smc_bias(df)
            score_vol = self._score_volatility(df)
            score_obv = self._score_obv_signal(df)
            score_mom = self._score_momentum_signal(df)

            # P2: Candlestick at OB/FVG zone confirmation
            candle_score = self._get_candle_score(code)
            candle_bonus = 15 if candle_score > 15 else 0  # Strong candlestick confirmation at SMC zone

            total_score = score_smc + score_vol + score_obv + score_mom + candle_bonus

            if total_score < self._smc_entry_threshold:
                self._phase_stats["phase3_no_primary"] += 1
                continue

            current_price = self._current_prices.get(code, float(curr["close"]))

            self._signal_counter += 1
            signal = SimSignal(
                id=f"sim-sig-{self._signal_counter:04d}",
                stock_code=code,
                stock_name=w["name"],
                type="BUY",
                price=current_price,
                reason=f"SMC_{total_score} [L1:{score_smc} L2:{score_vol} L3a:{score_obv} L3b:{score_mom}]",
                strength=min(total_score, 100),
                detected_at=self._get_current_iso(),
            )
            new_signals.append((signal, "MODERATE", "MID", 3))

            # SMC 통계
            self._phase_stats["smc_total_score"] += total_score
            self._phase_stats["smc_entries"] += 1

        # 시그널 강도순 정렬 후 매수 실행
        new_signals.sort(key=lambda x: x[0].strength, reverse=True)

        for sig, trend_strength, trend_stage, align_score in new_signals:
            if active_count >= regime_params["max_positions"]:
                break
            self.signals.append(sig)
            if len(self.signals) > 100:
                self.signals = self.signals[-100:]

            self._execute_buy(sig, trend_strength=trend_strength,
                             trend_stage=trend_stage, alignment_score=align_score)
            self._phase_stats["entries_executed"] += 1
            active_count += 1

    def _calculate_indicators_smc(self, df: pd.DataFrame) -> pd.DataFrame:
        """기존 지표 + SMC + OBV 통합 계산."""
        df = self._calculate_indicators(df)
        if df.empty:
            return df

        # SMC: Swing Points, BOS/CHoCH, Order Blocks, FVG
        from analytics.indicators import calculate_smc
        df = calculate_smc(df, swing_length=self._smc_cfg.swing_length)

        # OBV (On Balance Volume)
        c = df["close"].astype(float)
        v = df["volume"].astype(float)
        df["obv"] = (np.sign(c.diff()).fillna(0) * v).cumsum()
        df["obv_ema5"] = df["obv"].ewm(span=5, adjust=False).mean()
        df["obv_ema20"] = df["obv"].ewm(span=20, adjust=False).mean()

        return df

    def _score_smc_bias(self, df: pd.DataFrame) -> int:
        """Layer 1: SMC Bias 스코어 (0~40)."""
        if len(df) < 10:
            return 0

        score = 0
        curr = df.iloc[-1]
        price = float(curr["close"])

        lookback = min(20, len(df))
        recent = df.iloc[-lookback:]
        markers = recent[recent["marker"].notna()]

        if not markers.empty:
            last_marker = markers.iloc[-1]["marker"]
            if last_marker == "BOS_BULL":
                score += 25
            elif last_marker == "CHOCH_BULL":
                score += 20

        # OB 근접도
        ob_rows = recent[recent["ob_top"].notna()]
        if not ob_rows.empty:
            last_ob = ob_rows.iloc[-1]
            ob_top = float(last_ob["ob_top"])
            ob_bottom = float(last_ob["ob_bottom"])
            ob_range = ob_top - ob_bottom if ob_top > ob_bottom else 1.0
            if ob_bottom <= price <= ob_top:
                score += 10
            elif price < ob_top and price > ob_bottom - ob_range * 0.5:
                score += 5

        # FVG 미티게이션
        if self._smc_cfg.fvg_mitigation:
            fvg_rows = recent[(recent["fvg_type"] == "bull") & recent["fvg_top"].notna()]
            if not fvg_rows.empty:
                last_fvg = fvg_rows.iloc[-1]
                fvg_top = float(last_fvg["fvg_top"])
                fvg_bottom = float(last_fvg["fvg_bottom"])
                if fvg_bottom <= price <= fvg_top:
                    score += 5

        return min(score, self._smc_cfg.weight_smc)

    def _score_volatility(self, df: pd.DataFrame) -> int:
        """Layer 2: Volatility Setup 스코어 (0~20)."""
        if len(df) < 50:
            return 0

        score = 0
        curr = df.iloc[-1]

        bb_width = float(curr.get("bb_width", 0)) if pd.notna(curr.get("bb_width")) else 0
        bb_avg_series = df["bb_width"].rolling(window=50).mean()
        bb_width_avg = float(bb_avg_series.iloc[-1]) if pd.notna(bb_avg_series.iloc[-1]) else bb_width
        if bb_width_avg > 0:
            squeeze_ratio = bb_width / bb_width_avg
        else:
            squeeze_ratio = 1.0

        if squeeze_ratio < 0.8:
            score += 15
        elif squeeze_ratio < 1.0:
            score += 8

        atr_pct = float(curr.get("atr_pct", 0)) if pd.notna(curr.get("atr_pct")) else 0
        atr_avg = df["atr_pct"].rolling(window=50).mean()
        atr_avg_val = float(atr_avg.iloc[-1]) if pd.notna(atr_avg.iloc[-1]) else atr_pct
        if atr_avg_val > 0 and 0.5 <= atr_pct / atr_avg_val <= 1.5:
            score += 5

        return min(score, self._smc_cfg.weight_bb)

    def _score_obv_signal(self, df: pd.DataFrame) -> int:
        """Layer 3a: OBV 스코어 (0~20)."""
        if len(df) < 25:
            return 0

        score = 0
        curr = df.iloc[-1]

        obv_ema5 = float(curr.get("obv_ema5", 0)) if pd.notna(curr.get("obv_ema5")) else 0
        obv_ema20 = float(curr.get("obv_ema20", 0)) if pd.notna(curr.get("obv_ema20")) else 0

        if obv_ema5 > obv_ema20:
            score += 10
            if len(df) >= 6:
                obv_5ago = float(df.iloc[-6].get("obv_ema5", 0)) if pd.notna(df.iloc[-6].get("obv_ema5")) else 0
                if obv_ema5 > obv_5ago:
                    score += 5

            curr_vol = float(curr.get("volume", 0)) if pd.notna(curr.get("volume")) else 0
            vol_ma = float(curr.get("volume_ma", 1)) if pd.notna(curr.get("volume_ma")) else 1
            if vol_ma > 0 and curr_vol >= vol_ma * 1.3:
                score += 5

        return min(score, self._smc_cfg.weight_obv)

    def _score_momentum_signal(self, df: pd.DataFrame) -> int:
        """Layer 3b: ADX/MACD 모멘텀 스코어 (0~20)."""
        if len(df) < 30:
            return 0

        score = 0
        curr = df.iloc[-1]
        prev = df.iloc[-2]

        adx = float(curr.get("adx", 0)) if pd.notna(curr.get("adx")) else 0
        plus_di = float(curr.get("plus_di", 0)) if pd.notna(curr.get("plus_di")) else 0
        minus_di = float(curr.get("minus_di", 0)) if pd.notna(curr.get("minus_di")) else 0

        if adx > 25 and plus_di > minus_di:
            score += 10
        elif adx > 20 and plus_di > minus_di:
            score += 5

        macd_hist = float(curr.get("macd_hist", 0)) if pd.notna(curr.get("macd_hist")) else 0
        prev_macd = float(prev.get("macd_hist", 0)) if pd.notna(prev.get("macd_hist")) else 0

        if prev_macd <= 0 and macd_hist > 0:
            score += 10
        elif macd_hist > 0 and macd_hist > prev_macd:
            score += 5

        return min(score, self._smc_cfg.weight_momentum)

    # ══════════════════════════════════════════
    # SMC 청산 로직
    # ══════════════════════════════════════════

    def _check_exits_smc(self):
        """
        SMC 전용 청산 체크.
        ES1(-5%) > ATR SL > ATR TP > CHoCH > ES3 트레일링 > ES5 보유기간 > ES7 리밸런스
        """
        to_close: List[str] = []

        for code, pos in self.positions.items():
            if pos.status != "ACTIVE":
                continue
            if self._exit_tag_filter and pos.strategy_tag != self._exit_tag_filter:
                continue
            # 글로벌 레짐 기반 청산 파라미터 (종목별 레짐은 analytics용)
            regime_exit = REGIME_EXIT_PARAMS.get(self._market_regime, REGIME_EXIT_PARAMS["NEUTRAL"])

            current_price = self._current_prices.get(code, pos.current_price)
            entry_price = pos.entry_price
            pnl_pct = (current_price - entry_price) / entry_price

            exit_reason = None
            exit_type = None

            # ATR 조회
            atr_val = None
            df = self._ohlcv_cache.get(code)
            if df is not None and len(df) > 14:
                if "atr" not in df.columns:
                    df = self._calculate_indicators(df.copy())
                    self._ohlcv_cache[code] = df
                last_atr = df.iloc[-1].get("atr")
                if pd.notna(last_atr):
                    atr_val = float(last_atr)

            # ES1: 손절 -5% (GAP DOWN 보호: _execute_sell에서 fill price 조정)
            if current_price <= entry_price * (1 + self.stop_loss_pct):
                exit_reason = "ES1 손절 -5%"
                exit_type = "STOP_LOSS"

            # ATR SL: entry - ATR * mult (2일 쿨다운)
            elif atr_val and atr_val > 0:
                atr_sl_price = entry_price - atr_val * self._smc_cfg.atr_sl_mult
                floor_sl_price = entry_price * (1 + self.stop_loss_pct)
                effective_sl = max(atr_sl_price, floor_sl_price)

                if current_price <= effective_sl and effective_sl > floor_sl_price:
                    exit_reason = "ES_SMC ATR SL"
                    exit_type = "ATR_STOP_LOSS"

                # ATR TP
                if not exit_reason:
                    atr_tp_price = entry_price + atr_val * self._smc_cfg.atr_tp_mult
                    if current_price >= atr_tp_price:
                        exit_reason = "ES_SMC ATR TP"
                        exit_type = "ATR_TAKE_PROFIT"

            # CHoCH Exit: 추세 반전 감지 (Phase 5: PnL 게이트 추가)
            # 데이터: CHoCH exits 9/23 trades, -$2,352 → 조기 청산이 수익 기회 파괴
            # 수정: PnL < -2% (손실 확대 방지) 또는 PnL > +5% (수익 보호)만 CHoCH 청산
            # -2%~+5% "발전 구간"에서는 CHoCH 무시 → 트레이드 성숙 대기
            if not exit_reason and self._smc_cfg.choch_exit and df is not None and len(df) > 10:
                choch_pnl_gate = pnl_pct < -0.02 or pnl_pct > 0.05
                if choch_pnl_gate:
                    df_smc = self._calculate_indicators_smc(df.copy())
                    recent_markers = df_smc.iloc[-5:]
                    for _, row in recent_markers.iterrows():
                        if row.get("marker") == "CHOCH_BEAR":
                            exit_reason = "ES_CHOCH 추세반전"
                            exit_type = "CHOCH_EXIT"
                            break

            # ES3: 트레일링 스탑
            if not exit_reason:
                trail_pct = self.trailing_stop_pct
                if pnl_pct >= regime_exit["trail_activation"]:
                    if not pos.trailing_activated:
                        pos.trailing_activated = True
                    trailing_stop_price = pos.highest_price * (1 + trail_pct)
                    if current_price <= trailing_stop_price:
                        exit_reason = "ES3 트레일링스탑"
                        exit_type = "TRAILING_STOP"

            # ES5: 보유기간 초과
            if not exit_reason and pos.days_held > regime_exit["max_holding"]:
                exit_reason = "ES5 보유기간 초과"
                exit_type = "MAX_HOLDING"

            # ES7: 리밸런스 청산 (PnL 게이트: 수익 중이면 유예)
            if not exit_reason and code in self._rebalance_exit_codes:
                if pos.days_held < 3 or pnl_pct <= -0.02:
                    exit_reason = "ES7 리밸런스 청산"
                    exit_type = "REBALANCE_EXIT"
                    self._rebalance_exit_codes.discard(code)
                elif pnl_pct > 0.02:
                    # 수익 +2%+ → 다음 리밸런스까지 유예
                    self._rebalance_exit_codes.discard(code)
                else:
                    exit_reason = "ES7 리밸런스 청산"
                    exit_type = "REBALANCE_EXIT"
                    self._rebalance_exit_codes.discard(code)

            if exit_reason:
                to_close.append(code)
                # Phase 통계
                exit_stat_map = {
                    "EMERGENCY_STOP": "es0_emergency_stop",
                    "STOP_LOSS": "es1_stop_loss",
                    "ATR_STOP_LOSS": "es_smc_sl",
                    "ATR_TAKE_PROFIT": "es_smc_tp",
                    "CHOCH_EXIT": "es_choch_exit",
                    "TRAILING_STOP": "es3_trailing_stop",
                    "MAX_HOLDING": "es5_max_holding",
                    "REBALANCE_EXIT": "es7_rebalance_exit",
                }
                stat_key = exit_stat_map.get(exit_type or "")
                if stat_key and stat_key in self._phase_stats:
                    self._phase_stats[stat_key] += 1
                self._execute_sell(pos, current_price, exit_reason, exit_type or "")
            else:
                # 트레일링 최고가 갱신
                if current_price > pos.highest_price:
                    pos.highest_price = current_price

        for code in to_close:
            del self.positions[code]

    # ══════════════════════════════════════════
    # Mean Reversion 지표/진입/청산 로직
    # ══════════════════════════════════════════

    def _calculate_indicators_mean_reversion(self, df: pd.DataFrame) -> pd.DataFrame:
        """기존 지표 + MA200 + Stochastic + 연속하락일 계산."""
        df = self._calculate_indicators(df)
        if df.empty:
            return df

        c = df["close"].astype(float)
        h = df["high"].astype(float)
        lo = df["low"].astype(float)

        # Stochastic %K/%D
        k_period = self._mr_cfg.stochastic_k_period
        d_period = self._mr_cfg.stochastic_d_period
        lowest_low = lo.rolling(window=k_period).min()
        highest_high = h.rolling(window=k_period).max()
        denom = (highest_high - lowest_low).replace(0, np.nan)
        df["stoch_k"] = 100 * (c - lowest_low) / denom
        df["stoch_d"] = df["stoch_k"].rolling(window=d_period).mean()

        # 연속 하락일 카운터
        daily_return = c.pct_change()
        is_down = (daily_return < 0).astype(int)
        consec = []
        count = 0
        for val in is_down:
            if val == 1:
                count += 1
            else:
                count = 0
            consec.append(count)
        df["consecutive_down_days"] = consec

        # Phase 5: MA50 for MR TP target
        if len(df) >= 50:
            df["ma50"] = c.rolling(window=50).mean()

        return df

    def _score_mr_signal(self, df: pd.DataFrame) -> int:
        """Layer 1: MR Signal (0~weight_signal). Graduated RSI + BB proximity + MA200."""
        if len(df) < 200:
            return 0

        score = 0
        curr = df.iloc[-1]
        price = float(curr["close"])

        # Graduated RSI scoring (바이너리 → 단계적)
        rsi = float(curr.get("rsi", 50)) if pd.notna(curr.get("rsi")) else 50
        if rsi < 25:
            score += 20      # 강한 과매도
        elif rsi < 35:
            score += 15      # 중간 과매도
        elif rsi < 42:
            score += 10      # 경미한 과매도

        # Graduated BB Lower proximity (breach + 근접)
        bb_lower = float(curr.get("bb_lower", 0)) if pd.notna(curr.get("bb_lower")) else 0
        if bb_lower > 0:
            if price < bb_lower:
                score += 15  # BB 하단 돌파 (강한 시그널)
            elif price < bb_lower * 1.01:
                score += 8   # BB 하단 1% 이내 근접

        # MA200 위 = 장기 상승 추세 안에서의 pullback (건강한 MR)
        ma200 = float(curr.get("ma200", 0)) if pd.notna(curr.get("ma200")) else 0
        if ma200 > 0 and price > ma200:
            score += 5

        return min(score, self._mr_cfg.weight_signal)

    def _score_mr_volatility(self, df: pd.DataFrame) -> int:
        """Layer 2: Volatility & Volume (0~weight_volatility). Graduated scoring."""
        if len(df) < 30:
            return 0

        score = 0
        curr = df.iloc[-1]

        # BB Width 확장 (변동성 증가 = 평균 회귀 기회)
        bb_width = float(curr.get("bb_width", 0)) if pd.notna(curr.get("bb_width")) else 0
        bb_width_avg = df["bb_width"].rolling(window=20).mean()
        bb_avg_val = float(bb_width_avg.iloc[-1]) if pd.notna(bb_width_avg.iloc[-1]) else bb_width
        if bb_avg_val > 0:
            if bb_width > bb_avg_val * 1.5:
                score += 12  # 강한 변동성 확장
            elif bb_width > bb_avg_val * 1.2:
                score += 8   # 보통 확장
            elif bb_width > bb_avg_val * 1.0:
                score += 4   # 약간 확장

        # Graduated volume scoring (2.0x → 1.5x/1.2x 단계)
        curr_vol = float(curr.get("volume", 0)) if pd.notna(curr.get("volume")) else 0
        vol_ma = float(curr.get("volume_ma", 1)) if pd.notna(curr.get("volume_ma")) else 1
        if vol_ma > 0:
            vol_ratio = curr_vol / vol_ma
            if vol_ratio > 2.0:
                score += 10  # 강한 볼륨 스파이크 (capitulation)
            elif vol_ratio > self._mr_cfg.volume_spike_mult:
                score += 7   # 보통 스파이크
            elif vol_ratio > 1.2:
                score += 4   # 약한 볼륨 증가

        # ATR 확장 (패닉 셀오프 감지)
        atr = float(curr.get("atr", 0)) if pd.notna(curr.get("atr")) else 0
        atr_ma = df["atr"].rolling(window=20).mean()
        atr_avg_val = float(atr_ma.iloc[-1]) if pd.notna(atr_ma.iloc[-1]) else atr
        if atr_avg_val > 0 and atr > atr_avg_val * 1.3:
            score += 8

        return min(score, self._mr_cfg.weight_volatility)

    def _score_mr_confirmation(self, df: pd.DataFrame) -> int:
        """Layer 3: Confirmation (0~weight_confirmation). MACD slope + Stochastic + 연속하락."""
        if len(df) < 30:
            return 0

        score = 0
        curr = df.iloc[-1]
        prev = df.iloc[-2]

        # MACD: zero cross (+10) OR slope positive (+5)
        macd_hist = float(curr.get("macd_hist", 0)) if pd.notna(curr.get("macd_hist")) else 0
        prev_macd = float(prev.get("macd_hist", 0)) if pd.notna(prev.get("macd_hist")) else 0
        if prev_macd <= 0 and macd_hist > 0:
            score += 10      # zero cross (강한 반전 시그널)
        elif macd_hist > prev_macd and macd_hist < 0:
            score += 5       # slope positive (하락세 둔화)

        # Stochastic: graduated (K<20 → +10, K<30 → +5, K<20 GC bonus +5)
        stoch_k = float(curr.get("stoch_k", 50)) if pd.notna(curr.get("stoch_k")) else 50
        stoch_d = float(curr.get("stoch_d", 50)) if pd.notna(curr.get("stoch_d")) else 50
        prev_stoch_k = float(prev.get("stoch_k", 50)) if pd.notna(prev.get("stoch_k")) else 50
        prev_stoch_d = float(prev.get("stoch_d", 50)) if pd.notna(prev.get("stoch_d")) else 50
        if stoch_k < 20:
            score += 8       # 강한 과매도
            if prev_stoch_k <= prev_stoch_d and stoch_k > stoch_d:
                score += 4   # golden cross 보너스
        elif stoch_k < 30:
            score += 5       # 보통 과매도

        # 연속 하락일: graduated (>=2 → +5, >=3 → +8, >=5 → +10)
        consec_down = int(curr.get("consecutive_down_days", 0))
        if consec_down >= 5:
            score += 10      # 장기 하락 (강한 MR 후보)
        elif consec_down >= self._mr_cfg.consecutive_down_days + 1:
            score += 8       # 3일 연속 하락
        elif consec_down >= self._mr_cfg.consecutive_down_days:
            score += 5       # 2일 연속 하락

        return min(score, self._mr_cfg.weight_confirmation)

    def _scan_entries_mean_reversion(self):
        """
        Mean Reversion 3-Layer 스코어링 기반 진입 스캔.
        Phase 0 (시장 체제) + Phase 4 (리스크 게이트) → 레짐 필터 → MR 스코어링 → 매수 실행.
        """
        # ── Phase 0: 시장 체제 판단 ──
        self._update_market_regime()

        # ── Phase 4: 리스크 게이트 ──
        can_trade, block_reason = self._risk_gate_check()
        if not can_trade:
            self._phase_stats["phase4_risk_blocks"] += 1
            self._add_risk_event("WARNING", f"MR 진입 차단: {block_reason}")
            return

        total_equity = self._get_total_equity()
        regime_params = REGIME_PARAMS.get(self._market_regime, REGIME_PARAMS["NEUTRAL"])

        active_count = len([p for p in self.positions.values() if p.status == "ACTIVE"])

        if active_count >= regime_params["max_positions"]:
            return

        new_signals: List[tuple] = []

        for w in self._watchlist:
            code = w["code"]

            # B5: 종목별 레짐 기반 전략 필터링
            if self._get_stock_affinity(code, "mean_reversion") <= 0.0:
                continue

            # 기존 보유 종목 체크 — MR 수익 +3%, 3일+ 보유, 미스케일 → 추가 진입 허용
            is_scale = False
            if code in self.positions and self.positions[code].status in ("ACTIVE", "PENDING"):
                pos = self.positions[code]
                if (pos.strategy_tag == "mean_reversion"
                        and pos.scale_count < 1
                        and pos.days_held >= 3):
                    cur_px = self._current_prices.get(code, pos.current_price)
                    eff_entry = pos.avg_entry_price if pos.avg_entry_price > 0 else pos.entry_price
                    if (cur_px - eff_entry) / eff_entry >= 0.03:
                        is_scale = True  # Fall through to scoring
                    else:
                        continue
                else:
                    continue

            df = self._ohlcv_cache.get(code)
            if df is None or len(df) < 200:
                continue

            df = self._calculate_indicators_mean_reversion(df.copy())
            if df.empty or len(df) < 2:
                continue

            self._phase_stats["total_scans"] += 1
            curr = df.iloc[-1]

            # 레짐 필터: ADX < 25 (비추세) OR 극도 과매도
            # NEUTRAL 레짐: 더 엄격한 ADX 제한 (25→22)
            _mr_ro = REGIME_OVERRIDES.get(self._market_regime, {})
            effective_adx_limit = _mr_ro.get("mr_adx_limit", self._mr_cfg.adx_trending_limit)
            adx = float(curr.get("adx", 0)) if pd.notna(curr.get("adx")) else 0
            rsi = float(curr.get("rsi", 50)) if pd.notna(curr.get("rsi")) else 50
            if adx >= effective_adx_limit and rsi >= self._mr_cfg.extreme_oversold_rsi:
                self._phase_stats["phase1_trend_rejects"] += 1
                continue

            # RANGE_BOUND 레짐: 지지선 근처에서만 MR 진입
            if _mr_ro.get("sr_zone_entry") and not is_scale:
                sr = self._detect_support_resistance(df, lookback=_mr_ro.get("box_lookback", 40))
                _current_px = self._current_prices.get(code, float(curr["close"]))
                atr_buf = float(curr.get("atr", 0)) if pd.notna(curr.get("atr")) else 0
                buffer = atr_buf * _mr_ro.get("sr_atr_buffer", 1.5)
                near_support = any(abs(_current_px - s) < buffer for s in sr["support"]) if sr["support"] else False
                if not near_support and sr["support"]:
                    continue  # 지지선 근처가 아니면 진입 차단

            # Phase 5: 반전 확인 캔들 — 전일 양봉 필수 (스케일업은 면제)
            if not is_scale and len(df) >= 2:
                prev = df.iloc[-2]
                prev_close = float(prev["close"]) if pd.notna(prev.get("close")) else 0
                prev_open = float(prev["open"]) if pd.notna(prev.get("open")) else 0
                if prev_close <= prev_open:  # 전일 음봉 → 반전 미확인
                    continue

            # 3-Layer 스코어링
            score_signal = self._score_mr_signal(df)
            score_vol = self._score_mr_volatility(df)
            score_confirm = self._score_mr_confirmation(df)

            # P2: Reversal candle at oversold
            candle_score = self._get_candle_score(code)
            candle_bonus = 0
            if candle_score > 15 and rsi < 40:  # Bullish candle at oversold
                candle_bonus = 10

            # P3: Fib alignment bonus (price at key retracement = good MR entry)
            fib_bonus = 0
            fib_score = self._get_fib_alignment(code)
            if fib_score > 0.5:
                fib_bonus = 8

            total_score = score_signal + score_vol + score_confirm + candle_bonus + fib_bonus

            if total_score < self._mr_cfg.entry_threshold:
                self._phase_stats["phase3_no_primary"] += 1
                continue

            current_price = self._current_prices.get(code, float(curr["close"]))

            # 스케일업: 시그널 강도 50% 감소, 라벨 변경
            scale_label = "MR_SCALE" if is_scale else "MR"
            effective_strength = min(int(total_score * 0.5), 50) if is_scale else min(total_score, 100)

            self._signal_counter += 1
            signal = SimSignal(
                id=f"sim-sig-{self._signal_counter:04d}",
                stock_code=code,
                stock_name=w["name"],
                type="BUY",
                price=current_price,
                reason=f"{scale_label}_{total_score} [L1:{score_signal} L2:{score_vol} L3:{score_confirm}]",
                strength=effective_strength,
                detected_at=self._get_current_iso(),
            )
            new_signals.append((signal, "MODERATE", "MID", 3))

            self._phase_stats["mr_total_score"] += total_score
            self._phase_stats["mr_entries"] += 1

        # 시그널 강도순 정렬 후 매수 실행
        new_signals.sort(key=lambda x: x[0].strength, reverse=True)

        for sig, trend_strength, trend_stage, align_score in new_signals:
            if active_count >= regime_params["max_positions"]:
                break
            self.signals.append(sig)
            if len(self.signals) > 100:
                self.signals = self.signals[-100:]

            self._execute_buy(sig, trend_strength=trend_strength,
                             trend_stage=trend_stage, alignment_score=align_score)
            self._phase_stats["entries_executed"] += 1
            active_count += 1

    def _check_exits_mean_reversion(self):
        """
        Mean Reversion 전용 7-Priority 청산 체크.
        ES1(-5%) > ATR SL > MR TP(MA20/RSI>60) > BB Mid > Trailing > Overbought > Max Holding > ES7
        """
        to_close: List[str] = []

        for code, pos in self.positions.items():
            if pos.status != "ACTIVE":
                continue
            if self._exit_tag_filter and pos.strategy_tag != self._exit_tag_filter:
                continue
            # 글로벌 레짐 기반 청산 파라미터 (종목별 레짐은 analytics용)
            regime_exit = REGIME_EXIT_PARAMS.get(self._market_regime, REGIME_EXIT_PARAMS["NEUTRAL"])


            current_price = self._current_prices.get(code, pos.current_price)
            entry_price = pos.entry_price
            # 스케일업된 포지션은 가중평균 매입가 기준 PnL 계산
            effective_entry = pos.avg_entry_price if pos.avg_entry_price > 0 else entry_price
            pnl_pct = (current_price - effective_entry) / effective_entry

            exit_reason = None
            exit_type = None

            # ATR / RSI / BB 조회
            atr_val = None
            rsi_val = None
            bb_mid = None
            ma20 = None
            df = self._ohlcv_cache.get(code)
            if df is not None and len(df) > 14:
                if "atr" not in df.columns or "stoch_k" not in df.columns:
                    df = self._calculate_indicators_mean_reversion(df.copy())
                    self._ohlcv_cache[code] = df
                last = df.iloc[-1]
                if pd.notna(last.get("atr")):
                    atr_val = float(last["atr"])
                if pd.notna(last.get("rsi")):
                    rsi_val = float(last["rsi"])
                if pd.notna(last.get("bb_middle")):
                    bb_mid = float(last["bb_middle"])
                if pd.notna(last.get("ma_long")):
                    ma20 = float(last["ma_long"])

            # ES1: 손절 -5% (GAP DOWN 보호: _execute_sell에서 fill price 조정)
            if current_price <= entry_price * (1 + self.stop_loss_pct):
                exit_reason = "ES1 손절 -5%"
                exit_type = "STOP_LOSS"

            # ATR SL (2일 쿨다운)
            elif atr_val and atr_val > 0:
                atr_sl_price = entry_price - atr_val * self._mr_cfg.atr_sl_mult
                floor_sl = entry_price * (1 + self.stop_loss_pct)
                effective_sl = max(atr_sl_price, floor_sl)
                if current_price <= effective_sl and effective_sl > floor_sl:
                    exit_reason = "ES_MR ATR SL"
                    exit_type = "ATR_STOP_LOSS"

            # Phase 5.4: MR TP 상향 — MA50+RSI>55 (더 큰 반등 포착)
            # 기존 MA20+RSI>50 → 너무 일찍 청산 (2-3% 수익), SL -5%와 R:R 불균형
            ma50 = None
            if df is not None and len(df) > 50:
                last = df.iloc[-1]
                if pd.notna(last.get("ma50")):
                    ma50 = float(last["ma50"])
                elif pd.notna(last.get("ma60")):
                    ma50 = float(last["ma60"])  # MA50 없으면 MA60 대체

            if not exit_reason and ma50 and rsi_val is not None:
                if current_price > ma50 and rsi_val > 55:
                    exit_reason = "ES_MR TP (MA50+RSI>55)"
                    exit_type = "MEAN_REVERSION_TP"

            # RSI > 65 제거 — 너무 이른 청산. 대신 RSI > 70만 유지 (아래 overbought)

            # 수익 보호: pnl >= 5% 이면 MA20 단독으로도 청산 (최소 수익 확보)
            if not exit_reason and ma20 and pnl_pct >= 0.05 and current_price > ma20:
                exit_reason = "ES_MR TP (MA20 profit lock 5%)"
                exit_type = "MEAN_REVERSION_TP"

            # ES3: 트레일링 스탑 (MR → 5%에서 활성화, 기존 4%)
            if not exit_reason:
                trail_pct = self.trailing_stop_pct
                if pnl_pct >= 0.05:
                    if not pos.trailing_activated:
                        pos.trailing_activated = True
                    trailing_stop_price = pos.highest_price * (1 + trail_pct)
                    if current_price <= trailing_stop_price:
                        exit_reason = "ES3 트레일링스탑"
                        exit_type = "TRAILING_STOP"

            # Overbought: RSI > 70
            if not exit_reason and rsi_val is not None and rsi_val > self._mr_cfg.rsi_overbought:
                exit_reason = "ES_MR 과매수(RSI>70)"
                exit_type = "OVERBOUGHT_EXIT"

            # ES_TIME_DECAY: 글로벌 레짐 기반 시간감쇄 강제 청산
            _ro_mr = REGIME_OVERRIDES.get(self._market_regime, {})
            if not exit_reason and _ro_mr.get("time_decay_enabled"):
                decay_days = _ro_mr.get("time_decay_days", 10)
                decay_pnl = _ro_mr.get("time_decay_pnl_min", 0.02)
                if pos.days_held >= decay_days and pnl_pct < decay_pnl:
                    exit_reason = f"ES_TIME_DECAY: {pos.days_held}일 보유, PnL {pnl_pct:.1%} < {decay_pnl:.0%}"
                    exit_type = "TIME_DECAY"
                    self._phase_stats.setdefault("es_neutral_time_decay", 0)
                    self._phase_stats["es_neutral_time_decay"] += 1

            # ES_BOX_BREAK: RANGE_BOUND 레짐 박스 이탈 즉시 청산
            if not exit_reason and _ro_mr.get("box_breakout_exit") and df is not None:
                _box_lb = _ro_mr.get("box_lookback", 40)
                if len(df) >= _box_lb:
                    recent_box = df.tail(_box_lb)
                    box_high = float(recent_box["high"].max())
                    box_low = float(recent_box["low"].min())
                    if current_price > box_high * 1.01 or current_price < box_low * 0.99:
                        exit_reason = f"ES_BOX_BREAK: 박스({box_low:.0f}-{box_high:.0f}) 이탈"
                        exit_type = "BOX_BREAKOUT_EXIT"
                        self._phase_stats.setdefault("es_range_box_breakout", 0)
                        self._phase_stats["es_range_box_breakout"] += 1

            # ES5: 수익률 연동 보유기간 (MR 전용)
            if not exit_reason:
                base_max = self._mr_cfg.max_holding_days  # 20
                if pnl_pct >= 0.10:
                    effective_max = 60   # 큰 수익: 트레일링 스탑이 관리
                elif pnl_pct >= 0.05:
                    effective_max = 35   # 좋은 수익: 적정 확장
                elif pnl_pct >= 0.02:
                    effective_max = 25   # 소폭 수익: 완만 확장
                else:
                    effective_max = base_max  # 손실/평: 20일 유지
                if pos.days_held > effective_max:
                    exit_reason = f"ES5 보유기간 초과 ({effective_max}일)"
                    exit_type = "MAX_HOLDING"

            # ES7: 리밸런스 청산 (PnL 게이트: 수익 중이면 유예)
            if not exit_reason and code in self._rebalance_exit_codes:
                if pos.days_held < 3 or pnl_pct <= -0.02:
                    exit_reason = "ES7 리밸런스 청산"
                    exit_type = "REBALANCE_EXIT"
                    self._rebalance_exit_codes.discard(code)
                elif pnl_pct > 0.02:
                    # 수익 +2%+ → 다음 리밸런스까지 유예
                    self._rebalance_exit_codes.discard(code)
                else:
                    exit_reason = "ES7 리밸런스 청산"
                    exit_type = "REBALANCE_EXIT"
                    self._rebalance_exit_codes.discard(code)

            if exit_reason:
                to_close.append(code)
                exit_stat_map = {
                    "EMERGENCY_STOP": "es0_emergency_stop",
                    "STOP_LOSS": "es1_stop_loss",
                    "ATR_STOP_LOSS": "es_mr_sl",
                    "MEAN_REVERSION_TP": "es_mr_tp",
                    "BB_MID_REVERT": "es_mr_bb",
                    "TRAILING_STOP": "es3_trailing_stop",
                    "OVERBOUGHT_EXIT": "es_mr_ob",
                    "MAX_HOLDING": "es5_max_holding",
                    "REBALANCE_EXIT": "es7_rebalance_exit",
                }
                stat_key = exit_stat_map.get(exit_type or "")
                if stat_key and stat_key in self._phase_stats:
                    self._phase_stats[stat_key] += 1
                self._execute_sell(pos, current_price, exit_reason, exit_type or "")
            else:
                if current_price > pos.highest_price:
                    pos.highest_price = current_price

        for code in to_close:
            del self.positions[code]

    # ══════════════════════════════════════════
    # Breakout-Retest 지표/진입/청산 로직
    # ══════════════════════════════════════════

    def _calculate_indicators_breakout_retest(self, df: pd.DataFrame) -> pd.DataFrame:
        """기존 지표 + SMC + OBV + ADX 통합 계산 (breakout_retest 전용)."""
        df = self._calculate_indicators(df)
        if df.empty:
            return df

        # SMC: Swing Points, BOS/CHoCH, Order Blocks, FVG
        from analytics.indicators import calculate_smc
        df = calculate_smc(df, swing_length=self._brt_cfg.swing_length)

        # OBV (On Balance Volume)
        c = df["close"].astype(float)
        v = df["volume"].astype(float)
        df["obv"] = (np.sign(c.diff()).fillna(0) * v).cumsum()
        df["obv_ema5"] = df["obv"].ewm(span=5, adjust=False).mean()
        df["obv_ema20"] = df["obv"].ewm(span=20, adjust=False).mean()

        return df

    def _score_brt_structure(self, df: pd.DataFrame) -> int:
        """Layer 1: SMC 구조 스코어 (0~weight_structure). BOS + 유동성 스윕."""
        if len(df) < 10:
            return 0

        score = 0
        lookback = min(20, len(df))
        recent = df.iloc[-lookback:]

        markers = recent[recent["marker"].notna()]
        if not markers.empty:
            last_marker = markers.iloc[-1]["marker"]
            if last_marker == "BOS_BULL":
                score += 20
            elif last_marker == "CHOCH_BULL":
                score += 15

        # 유동성 스윕
        swing_lows = recent[recent["is_swing_low"] == True]
        if not swing_lows.empty and len(df) >= 7:
            last_sl = float(swing_lows.iloc[-1]["low"])
            recent_7 = df.iloc[-7:]
            if (recent_7["low"] < last_sl).any():
                score += 10

        return min(score, self._brt_cfg.weight_structure)

    def _score_brt_volatility(self, df: pd.DataFrame) -> int:
        """Layer 2: BB/ATR 변동성 스코어 (0~weight_volatility)."""
        lookback = self._brt_cfg.bb_squeeze_lookback
        if len(df) < max(lookback, 50):
            return 0

        score = 0
        bb_width = df["bb_width"].dropna()
        if len(bb_width) < lookback:
            return 0

        current_width = float(bb_width.iloc[-1])
        min_width = float(bb_width.iloc[-lookback:].min())
        bb_ema = float(bb_width.ewm(span=self._brt_cfg.bb_squeeze_ema).mean().iloc[-1])

        if min_width > 0 and current_width <= min_width * 1.1:
            score += 15
        elif bb_ema > 0 and current_width < bb_ema:
            score += 8

        # ATR 압축
        atr_pct = df["atr_pct"].dropna()
        if len(atr_pct) >= 50:
            atr_avg = float(atr_pct.rolling(50).mean().iloc[-1])
            curr_atr = float(atr_pct.iloc[-1])
            if atr_avg > 0 and curr_atr < atr_avg * 0.8:
                score += 5

        return min(score, self._brt_cfg.weight_volatility)

    def _score_brt_obv(self, df: pd.DataFrame) -> int:
        """Layer 3: OBV 돌파 스코어 (0~weight_volume)."""
        obv = df["obv"].dropna()
        lb = self._brt_cfg.obv_break_lookback
        if len(obv) < lb + 1:
            return 0

        score = 0
        curr_obv = float(obv.iloc[-1])
        prev_obv_high = float(obv.iloc[-lb - 1:-1].max())

        if curr_obv > prev_obv_high:
            score += 15
            obv_ema5 = float(df["obv_ema5"].iloc[-1]) if pd.notna(df["obv_ema5"].iloc[-1]) else 0
            obv_ema20 = float(df["obv_ema20"].iloc[-1]) if pd.notna(df["obv_ema20"].iloc[-1]) else 0
            if obv_ema5 > obv_ema20:
                score += 10

        return min(score, self._brt_cfg.weight_volume)

    def _score_brt_momentum(self, df: pd.DataFrame) -> int:
        """Layer 4: ADX/MACD 모멘텀 스코어 (0~weight_momentum)."""
        rising_bars = self._brt_cfg.adx_rising_bars
        if len(df) < rising_bars + 2:
            return 0

        score = 0
        curr = df.iloc[-1]
        prev = df.iloc[-2]

        adx_series = df["adx"].dropna()
        if len(adx_series) >= rising_bars + 1:
            curr_adx = float(adx_series.iloc[-1])
            plus_di = float(curr.get("plus_di", 0)) if pd.notna(curr.get("plus_di")) else 0
            minus_di = float(curr.get("minus_di", 0)) if pd.notna(curr.get("minus_di")) else 0

            if curr_adx > self._brt_cfg.adx_threshold and plus_di > minus_di:
                score += 8
                rising = True
                for i in range(1, rising_bars + 1):
                    if float(adx_series.iloc[-i]) <= float(adx_series.iloc[-i - 1]):
                        rising = False
                        break
                if rising:
                    score += 7

        macd_hist = float(curr.get("macd_hist", 0)) if pd.notna(curr.get("macd_hist")) else 0
        prev_macd = float(prev.get("macd_hist", 0)) if pd.notna(prev.get("macd_hist")) else 0

        if prev_macd <= 0 and macd_hist > 0:
            score += 10
        elif macd_hist > 0 and macd_hist > prev_macd:
            score += 5

        return min(score, self._brt_cfg.weight_momentum)

    def _check_brt_six_conditions(self, df: pd.DataFrame) -> tuple:
        """6조건 검증 (sim). 최소 4개 필요."""
        met = []
        curr = df.iloc[-1]
        cfg = self._brt_cfg

        # C1: Volatility Squeeze
        bb_width = df["bb_width"].dropna()
        if len(bb_width) >= cfg.bb_squeeze_lookback:
            curr_w = float(bb_width.iloc[-1])
            min_w = float(bb_width.iloc[-cfg.bb_squeeze_lookback:].min())
            if min_w > 0 and curr_w <= min_w * 1.2:
                met.append("C1_SQUEEZE")

        # C2: Liquidity Sweep
        swing_lows = df[df.get("is_swing_low", pd.Series(dtype=bool)) == True]
        if not swing_lows.empty and len(df) >= 7:
            last_sl = float(swing_lows.iloc[-1]["low"])
            recent = df.iloc[-7:]
            if (recent["low"] < last_sl).any():
                met.append("C2_LIQ_SWEEP")

        # C3: Displacement
        body = abs(float(curr["close"]) - float(curr["open"]))
        atr = float(curr.get("atr", 0)) if pd.notna(curr.get("atr")) else 0
        if atr > 0 and body > atr * cfg.displacement_atr_mult:
            met.append("C3_DISPLACEMENT")

        # C4: OBV Break
        obv = df["obv"].dropna()
        if len(obv) > cfg.obv_break_lookback:
            if float(obv.iloc[-1]) > float(obv.iloc[-cfg.obv_break_lookback - 1:-1].max()):
                met.append("C4_OBV_BREAK")

        # C5: ADX > threshold & rising
        adx_s = df["adx"].dropna()
        if len(adx_s) >= cfg.adx_rising_bars + 1:
            if float(adx_s.iloc[-1]) > cfg.adx_threshold:
                rising = all(
                    float(adx_s.iloc[-i]) > float(adx_s.iloc[-i - 1])
                    for i in range(1, cfg.adx_rising_bars + 1)
                )
                if rising:
                    met.append("C5_ADX_RISING")

        # C6: FVG Formation
        fvg_recent = df.iloc[-3:]
        if not fvg_recent[fvg_recent.get("fvg_type", pd.Series(dtype=str)) == "bull"].empty:
            met.append("C6_FVG")

        return len(met) >= 3, met  # Phase 5: 4/6→3/6 진입 기준 완화

    def _apply_brt_fakeout_filters(self, df: pd.DataFrame) -> tuple:
        """3개 페이크아웃 필터 (sim). (통과 여부, 차단 사유)."""
        curr = df.iloc[-1]
        cfg = self._brt_cfg

        # ERR01: 저거래량
        volume = float(curr.get("volume", 0))
        vol_ma = float(curr.get("volume_ma", 1)) if pd.notna(curr.get("volume_ma")) else 1
        if vol_ma > 0 and volume < vol_ma * cfg.min_volume_ratio:
            return False, "ERR01_LOW_VOLUME"

        # ERR02: 긴 윗꼬리
        close = float(curr["close"])
        open_p = float(curr["open"])
        high = float(curr["high"])
        body = abs(close - open_p)
        upper_wick = high - max(close, open_p)
        if body > 0 and upper_wick / body > cfg.max_wick_body_ratio:
            return False, "ERR02_WICK_TRAP"

        # ERR03: MACD/RSI 다이버전스
        if cfg.divergence_check and len(df) >= 10:
            price_curr = float(df["close"].iloc[-1])
            price_prev_max = float(df["close"].iloc[-10:-1].max())
            macd_curr = float(curr.get("macd_hist", 0)) if pd.notna(curr.get("macd_hist")) else 0
            macd_prev_max = float(df["macd_hist"].iloc[-10:-1].max()) if "macd_hist" in df.columns else 0
            rsi_curr = float(curr.get("rsi", 50)) if pd.notna(curr.get("rsi")) else 50
            rsi_prev_max = float(df["rsi"].iloc[-10:-1].max()) if "rsi" in df.columns else 50

            if price_curr > price_prev_max and (macd_curr < macd_prev_max * 0.8 or rsi_curr < rsi_prev_max * 0.9):
                return False, "ERR03_DIVERGENCE"

        return True, None

    def _capture_brt_retest_zones(self, df: pd.DataFrame, breakout_price: float, breakout_atr: float) -> Dict[str, Any]:
        """돌파 시점 FVG/OB/레벨 존을 캡처해서 상태 dict로 반환."""
        cfg = self._brt_cfg
        state: Dict[str, Any] = {
            "phase": "WAITING_RETEST",
            "breakout_price": breakout_price,
            "breakout_atr": breakout_atr,
            "bars_since_breakout": 0,
            "breakout_score": 0,
            "fvg_top": 0.0, "fvg_bottom": 0.0,
            "ob_top": 0.0, "ob_bottom": 0.0,
            "breakout_level": 0.0,
            "zone_top": 0.0, "zone_bottom": 0.0,
            "zone_type": "LEVEL",
            "conditions_met": [],
        }

        recent = df.iloc[-20:]

        # FVG 존 캡처
        if cfg.use_fvg_zone:
            fvg_rows = recent[(recent.get("fvg_type", pd.Series(dtype=str)) == "bull") & recent["fvg_top"].notna()]
            if not fvg_rows.empty:
                last_fvg = fvg_rows.iloc[-1]
                state["fvg_top"] = float(last_fvg["fvg_top"])
                state["fvg_bottom"] = float(last_fvg["fvg_bottom"])

        # OB 존 캡처
        if cfg.use_ob_zone:
            ob_rows = recent[recent["ob_top"].notna()]
            if not ob_rows.empty:
                last_ob = ob_rows.iloc[-1]
                state["ob_top"] = float(last_ob["ob_top"])
                state["ob_bottom"] = float(last_ob["ob_bottom"])

        # 돌파 레벨 (마지막 swing high)
        if cfg.use_breakout_level:
            swing_highs = recent[recent.get("is_swing_high", pd.Series(dtype=bool)) == True]
            if not swing_highs.empty:
                state["breakout_level"] = float(swing_highs.iloc[-1]["high"])

        # 복합 존 계산
        zone_candidates = []
        if state["fvg_bottom"] > 0:
            zone_candidates.append((state["fvg_bottom"], state["fvg_top"]))
        if state["ob_bottom"] > 0:
            zone_candidates.append((state["ob_bottom"], state["ob_top"]))
        if state["breakout_level"] > 0:
            buffer = breakout_atr * cfg.retest_zone_atr_buffer
            zone_candidates.append((state["breakout_level"] - buffer, state["breakout_level"]))

        if zone_candidates:
            state["zone_bottom"] = min(z[0] for z in zone_candidates)
            state["zone_top"] = max(z[1] for z in zone_candidates)
            state["zone_type"] = "COMPOSITE"
        else:
            buffer = breakout_atr * cfg.retest_zone_atr_buffer
            state["zone_bottom"] = breakout_price - breakout_atr - buffer
            state["zone_top"] = breakout_price
            state["zone_type"] = "LEVEL"

        return state

    def _scan_entries_breakout_retest(self):
        """
        Breakout-Retest 2-Phase 진입 스캔.
        Pass 1: IDLE 티커 → Phase A 돌파 감지
        Pass 2: WAITING_RETEST 티커 → Phase B 리테스트 확인
        """
        # ── Phase 0: 시장 체제 판단 ──
        self._update_market_regime()

        # ── Phase 4: 리스크 게이트 ──
        can_trade, block_reason = self._risk_gate_check()
        if not can_trade:
            self._phase_stats["phase4_risk_blocks"] += 1
            self._add_risk_event("WARNING", f"BRT 진입 차단: {block_reason}")
            return

        total_equity = self._get_total_equity()
        regime_params = REGIME_PARAMS.get(self._market_regime, REGIME_PARAMS["NEUTRAL"])

        active_count = len([p for p in self.positions.values() if p.status == "ACTIVE"])

        # ── Pass 1: IDLE 티커에서 돌파 감지 ──
        for w in self._watchlist:
            code = w["code"]

            # B5: 종목별 레짐 기반 전략 필터링
            if self._get_stock_affinity(code, "breakout_retest") <= 0.0:
                continue

            if code in self.positions and self.positions[code].status in ("ACTIVE", "PENDING"):
                continue

            # 이미 WAITING_RETEST 상태면 Pass 1 스킵
            if code in self._breakout_states and self._breakout_states[code].get("phase") == "WAITING_RETEST":
                continue

            df = self._ohlcv_cache.get(code)
            if df is None or len(df) < max(self._brt_cfg.bb_squeeze_lookback, 50):
                continue

            df = self._calculate_indicators_breakout_retest(df.copy())
            if df.empty or len(df) < 2:
                continue
            self._ohlcv_cache[code] = df

            self._phase_stats["total_scans"] += 1

            # 4-Layer 스코어링
            score_s = self._score_brt_structure(df)
            score_v = self._score_brt_volatility(df)
            score_o = self._score_brt_obv(df)
            score_m = self._score_brt_momentum(df)
            total_score = score_s + score_v + score_o + score_m

            if total_score < self._brt_cfg.breakout_threshold:
                self._phase_stats["phase3_no_primary"] += 1
                continue

            # 6조건 검증
            conditions_ok, met_list = self._check_brt_six_conditions(df)
            if not conditions_ok:
                self._phase_stats["phase3_no_confirm"] += 1
                continue

            # 3개 페이크아웃 필터
            filter_ok, block_reason = self._apply_brt_fakeout_filters(df)
            if not filter_ok:
                self._phase_stats["brt_fakeout_blocked"] += 1
                continue

            # 돌파 확인 → WAITING_RETEST 전이
            curr = df.iloc[-1]
            breakout_price = float(curr["close"])
            breakout_atr = float(curr.get("atr", breakout_price * 0.03)) if pd.notna(curr.get("atr")) else breakout_price * 0.03

            state = self._capture_brt_retest_zones(df, breakout_price, breakout_atr)
            state["breakout_score"] = total_score
            state["conditions_met"] = met_list
            self._breakout_states[code] = state
            self._phase_stats["brt_breakouts_detected"] += 1

            self._add_risk_event(
                "INFO",
                f"돌파 감지: {w['name']} score={total_score} [S:{score_s} V:{score_v} O:{score_o} M:{score_m}]"
            )

        # ── Pass 2: WAITING_RETEST 티커에서 리테스트 진입 확인 ──
        new_signals: List[tuple] = []
        expired_codes = []

        for code, state in list(self._breakout_states.items()):
            if state.get("phase") != "WAITING_RETEST":
                continue
            if code in self.positions and self.positions[code].status in ("ACTIVE", "PENDING"):
                continue

            df = self._ohlcv_cache.get(code)
            if df is None or len(df) < 2:
                continue

            # 지표가 이미 계산되어 있지 않으면 재계산
            if "obv" not in df.columns:
                df = self._calculate_indicators_breakout_retest(df.copy())
                self._ohlcv_cache[code] = df

            curr = df.iloc[-1]
            price = float(curr["close"])
            low = float(curr["low"])

            state["bars_since_breakout"] = state.get("bars_since_breakout", 0) + 1

            # 만료 체크
            if state["bars_since_breakout"] > self._brt_cfg.retest_max_bars:
                state["phase"] = "IDLE"
                expired_codes.append(code)
                self._phase_stats["brt_retests_expired"] += 1
                continue

            # 존 하단 이탈 → 실패
            if price < state["zone_bottom"]:
                state["phase"] = "IDLE"
                expired_codes.append(code)
                continue

            # 존 도달 확인
            in_zone = low <= state["zone_top"] and price >= state["zone_bottom"]
            if not in_zone:
                continue

            # ── 확인 조건 (3개 중 2개 이상) ──
            confirmations = 0
            confirm_parts = []

            # 1. 거래량 감소
            volume = float(curr.get("volume", 0))
            vol_ma = float(curr.get("volume_ma", 1)) if pd.notna(curr.get("volume_ma")) else 1
            if vol_ma > 0 and volume < vol_ma * self._brt_cfg.retest_volume_decay:
                confirmations += 1
                confirm_parts.append("VOL_DECAY")

            # 2. 반등 캔들
            open_p = float(curr["open"])
            body = abs(price - open_p)
            lower_wick = min(price, open_p) - low
            bullish_rejection = body > 0 and lower_wick > body * self._brt_cfg.retest_rejection_wick_ratio
            bullish_close = price > open_p
            if bullish_rejection or bullish_close:
                confirmations += 1
                confirm_parts.append("REJECTION" if bullish_rejection else "BULL_CLOSE")

            # 3. RSI 지지
            rsi = float(curr.get("rsi", 50)) if pd.notna(curr.get("rsi")) else 50
            if rsi >= self._brt_cfg.retest_rsi_floor:
                confirmations += 1
                confirm_parts.append(f"RSI_{int(rsi)}")

            if confirmations < 2:
                continue

            # 존 스코어링
            zone_score = self._score_brt_retest_zone(df, state)

            # P3: Chart pattern bonus for retest quality
            chart_pattern_score = self._get_chart_pattern_score(code)
            if chart_pattern_score > 40:
                zone_score += 10

            if zone_score < self._brt_cfg.retest_zone_threshold:
                continue

            # ── 리테스트 진입 확인 ──
            # P2: Candlestick confirmation at retest zone
            candle_score = self._get_candle_score(code)
            candle_bonus = 10 if candle_score > 15 else 0
            strength = min(state.get("breakout_score", 60) + zone_score // 2 + candle_bonus, 100)
            stock_name = self._stock_names.get(code, code)

            self._signal_counter += 1
            signal = SimSignal(
                id=f"sim-sig-{self._signal_counter:04d}",
                stock_code=code,
                stock_name=stock_name,
                type="BUY",
                price=self._current_prices.get(code, price),
                reason=f"BRT_RETEST_{strength} [BKO:{state.get('breakout_score', 0)} ZONE:{zone_score} {'+'.join(confirm_parts)}]",
                strength=strength,
                detected_at=self._get_current_iso(),
            )
            new_signals.append((signal, "MODERATE", "MID", 3))

            state["phase"] = "IDLE"  # 사용된 상태 리셋
            self._phase_stats["brt_retests_entered"] += 1

        # 만료된 상태 정리
        for code in expired_codes:
            if code in self._breakout_states and self._breakout_states[code].get("phase") == "IDLE":
                del self._breakout_states[code]

        # 시그널 강도순 정렬 후 매수 실행
        new_signals.sort(key=lambda x: x[0].strength, reverse=True)

        for sig, trend_strength, trend_stage, align_score in new_signals:
            if active_count >= regime_params["max_positions"]:
                break
            self.signals.append(sig)
            if len(self.signals) > 100:
                self.signals = self.signals[-100:]

            self._execute_buy(sig, trend_strength=trend_strength,
                             trend_stage=trend_stage, alignment_score=align_score)
            self._phase_stats["entries_executed"] += 1
            active_count += 1

    def _score_brt_retest_zone(self, df: pd.DataFrame, state: Dict[str, Any]) -> int:
        """리테스트 존 근접도 스코어링 (0-100)."""
        price = float(df.iloc[-1]["close"])
        score = 0
        cfg = self._brt_cfg

        # FVG 근접도
        fvg_b = state.get("fvg_bottom", 0)
        fvg_t = state.get("fvg_top", 0)
        if fvg_b > 0 and cfg.use_fvg_zone:
            if fvg_b <= price <= fvg_t:
                score += cfg.fvg_zone_weight
            elif price < fvg_t and price > fvg_b - state.get("breakout_atr", 0) * 0.3:
                score += cfg.fvg_zone_weight // 2

        # OB 근접도
        ob_b = state.get("ob_bottom", 0)
        ob_t = state.get("ob_top", 0)
        if ob_b > 0 and cfg.use_ob_zone:
            if ob_b <= price <= ob_t:
                score += cfg.ob_zone_weight
            elif price < ob_t and price > ob_b - state.get("breakout_atr", 0) * 0.3:
                score += cfg.ob_zone_weight // 2

        # 돌파 레벨 근접도
        bl = state.get("breakout_level", 0)
        if bl > 0 and cfg.use_breakout_level:
            buffer = state.get("breakout_atr", 0) * cfg.retest_zone_atr_buffer
            if bl - buffer <= price <= bl + buffer:
                score += cfg.level_zone_weight

        return min(score, 100)

    def _check_exits_breakout_retest(self):
        """
        Breakout-Retest 전용 청산 체크.
        ES1(-5%) > ATR SL(1.5x) > ATR TP(3.0x) > CHoCH > ES3 트레일링 > Zone Break > ES5 보유기간 > ES7 리밸런스
        """
        to_close: List[str] = []

        for code, pos in self.positions.items():
            if pos.status != "ACTIVE":
                continue
            if self._exit_tag_filter and pos.strategy_tag != self._exit_tag_filter:
                continue
            # 글로벌 레짐 기반 청산 파라미터 (종목별 레짐은 analytics용)
            regime_exit = REGIME_EXIT_PARAMS.get(self._market_regime, REGIME_EXIT_PARAMS["NEUTRAL"])


            current_price = self._current_prices.get(code, pos.current_price)
            entry_price = pos.entry_price
            pnl_pct = (current_price - entry_price) / entry_price

            exit_reason = None
            exit_type = None

            # ATR 조회
            atr_val = None
            df = self._ohlcv_cache.get(code)
            if df is not None and len(df) > 14:
                if "atr" not in df.columns:
                    df = self._calculate_indicators(df.copy())
                    self._ohlcv_cache[code] = df
                last_atr = df.iloc[-1].get("atr")
                if pd.notna(last_atr):
                    atr_val = float(last_atr)

            # ES1: 손절 -5% (GAP DOWN 보호: _execute_sell에서 fill price 조정)
            if current_price <= entry_price * (1 + self.stop_loss_pct):
                exit_reason = "ES1 손절 -5%"
                exit_type = "STOP_LOSS"

            # ES_BRT_SL: ATR × 1.5 (2일 쿨다운)
            elif atr_val and atr_val > 0:
                atr_sl_price = entry_price - atr_val * self._brt_cfg.atr_sl_mult
                floor_sl_price = entry_price * (1 + self.stop_loss_pct)
                effective_sl = max(atr_sl_price, floor_sl_price)

                if current_price <= effective_sl and effective_sl > floor_sl_price:
                    exit_reason = "ES_BRT ATR SL (1.5x)"
                    exit_type = "ATR_STOP_LOSS"

                # ES_BRT_TP: ATR × 3.0
                if not exit_reason:
                    atr_tp_price = entry_price + atr_val * self._brt_cfg.atr_tp_mult
                    if current_price >= atr_tp_price:
                        exit_reason = "ES_BRT ATR TP (3.0x)"
                        exit_type = "ATR_TAKE_PROFIT"

            # ES_CHOCH: 추세 반전 감지 (Phase 5: PnL 게이트)
            if not exit_reason and self._brt_cfg.choch_exit and df is not None and len(df) > 10:
                choch_pnl_gate = pnl_pct < -0.02 or pnl_pct > 0.05
                if choch_pnl_gate:
                    df_calc = self._calculate_indicators_breakout_retest(df.copy())
                    recent_markers = df_calc.iloc[-5:]
                    for _, row in recent_markers.iterrows():
                        if row.get("marker") == "CHOCH_BEAR":
                            exit_reason = "ES_CHOCH 추세반전"
                            exit_type = "CHOCH_EXIT"
                            break

            # ES3: 트레일링 스탑 (+5% 활성화, ATR × 2.0)
            if not exit_reason:
                if pnl_pct >= self._brt_cfg.trailing_activation_pct:
                    if not pos.trailing_activated:
                        pos.trailing_activated = True
                    # ATR 기반 트레일링
                    trail_pct = self.trailing_stop_pct  # 기본 -4%
                    if atr_val and atr_val > 0:
                        atr_trail = -(atr_val * self._brt_cfg.trailing_atr_mult) / entry_price
                        trail_pct = max(atr_trail, self.trailing_stop_pct)
                    trailing_stop_price = pos.highest_price * (1 + trail_pct)
                    if current_price <= trailing_stop_price:
                        exit_reason = "ES3 트레일링스탑"
                        exit_type = "TRAILING_STOP"

            # ES_ZONE_BREAK: 리테스트 존 무효화 (존 하단 이탈 시 청산)
            if not exit_reason and code in self._breakout_states:
                brt_state = self._breakout_states[code]
                zone_bottom = brt_state.get("zone_bottom", 0)
                if zone_bottom > 0 and current_price < zone_bottom:
                    exit_reason = "ES_ZONE_BREAK 존 무효화"
                    exit_type = "ZONE_BREAK"

            # ES5: 보유기간 초과
            max_hold = min(self._brt_cfg.max_holding_days, regime_exit["max_holding"])
            if not exit_reason and pos.days_held > max_hold:
                exit_reason = "ES5 보유기간 초과"
                exit_type = "MAX_HOLDING"

            # ES7: 리밸런스 청산 (PnL 게이트: 수익 중이면 유예)
            if not exit_reason and code in self._rebalance_exit_codes:
                if pos.days_held < 3 or pnl_pct <= -0.02:
                    exit_reason = "ES7 리밸런스 청산"
                    exit_type = "REBALANCE_EXIT"
                    self._rebalance_exit_codes.discard(code)
                elif pnl_pct > 0.02:
                    # 수익 +2%+ → 다음 리밸런스까지 유예
                    self._rebalance_exit_codes.discard(code)
                else:
                    exit_reason = "ES7 리밸런스 청산"
                    exit_type = "REBALANCE_EXIT"
                    self._rebalance_exit_codes.discard(code)

            if exit_reason:
                to_close.append(code)
                # Phase 통계
                exit_stat_map = {
                    "EMERGENCY_STOP": "es0_emergency_stop",
                    "STOP_LOSS": "es1_stop_loss",
                    "ATR_STOP_LOSS": "es_brt_sl",
                    "ATR_TAKE_PROFIT": "es_brt_tp",
                    "CHOCH_EXIT": "es_choch_exit",
                    "TRAILING_STOP": "es3_trailing_stop",
                    "ZONE_BREAK": "es_zone_break",
                    "MAX_HOLDING": "es5_max_holding",
                    "REBALANCE_EXIT": "es7_rebalance_exit",
                }
                stat_key = exit_stat_map.get(exit_type or "")
                if stat_key and stat_key in self._phase_stats:
                    self._phase_stats[stat_key] += 1
                self._execute_sell(pos, current_price, exit_reason, exit_type or "")
            else:
                # 트레일링 최고가 갱신
                if current_price > pos.highest_price:
                    pos.highest_price = current_price

        for code in to_close:
            del self.positions[code]

    # ══════════════════════════════════════════
    # Arbitrage: Statistical Pairs (Long+Short 양방향)
    # 이론 참조: futuresStrategy.md (Z-Score), BlackScholesEquation.md (IV/RV),
    #           future_trading_stratedy.md (Dynamic ATR), Kelly Criterion.md
    # ══════════════════════════════════════════

    def _discover_pairs(self) -> List[Dict]:
        """
        워치리스트 내 페어 자동 발견 — v2.
        동일 섹터 우선 + 크로스섹터 허용 (BUG-7).
        Phase Stats 누적 (BUG-1), 쿨다운 중 페어 스킵 (BUG-3).
        """
        import itertools

        cfg = self._arb_cfg
        watchlist = self._watchlist
        pairs: List[Dict] = []

        # v2: 쿨다운 중 페어 키 집합 (BUG-3)
        cooldown_keys = set(self._arb_pair_cooldown.keys())

        # ── 후보 조합 생성 ──
        combos: List[tuple] = []

        # 1) 동일 섹터 내 조합 (우선)
        sector_map: Dict[str, List[Dict]] = {}
        for w in watchlist:
            sector = w.get("sector", "")
            if sector:
                sector_map.setdefault(sector, []).append(w)

        for sector, stocks in sector_map.items():
            if len(stocks) < 2:
                continue
            for w_a, w_b in itertools.combinations(stocks, 2):
                combos.append((w_a, w_b, sector))

        # 2) 크로스섹터 조합 (v2 BUG-7)
        if cfg.cross_sector_pairs:
            all_stocks = [w for w in watchlist if w.get("sector", "")]
            for w_a, w_b in itertools.combinations(all_stocks, 2):
                if w_a.get("sector", "") != w_b.get("sector", ""):
                    combos.append((w_a, w_b, "cross"))

        # v2: 누적 통계 (BUG-1) — 리셋하지 않고 += 누적
        self._phase_stats["arb_pairs_scanned"] = (
            self._phase_stats.get("arb_pairs_scanned", 0) + len(combos)
        )

        for w_a, w_b, sector_label in combos:
            code_a, code_b = w_a["code"], w_b["code"]

            # v2: 쿨다운 중 페어 스킵 (BUG-3)
            pair_key = f"{min(code_a,code_b)}-{max(code_a,code_b)}"
            if pair_key in cooldown_keys:
                continue

            df_a = self._ohlcv_cache.get(code_a)
            df_b = self._ohlcv_cache.get(code_b)

            if df_a is None or df_b is None or len(df_a) < cfg.correlation_lookback or len(df_b) < cfg.correlation_lookback:
                continue

            # 날짜 정렬 후 최근 N일 종가 추출
            close_a = df_a["close"].astype(float).tail(cfg.correlation_lookback)
            close_b = df_b["close"].astype(float).tail(cfg.correlation_lookback)

            if len(close_a) != len(close_b):
                min_len = min(len(close_a), len(close_b))
                close_a = close_a.tail(min_len).reset_index(drop=True)
                close_b = close_b.tail(min_len).reset_index(drop=True)

            if len(close_a) < 30:
                continue

            # 상관계수 체크 (v2: 0.60 threshold)
            corr = close_a.corr(close_b)
            if pd.isna(corr) or corr < cfg.correlation_min:
                self._phase_stats["arb_correlation_rejects"] = (
                    self._phase_stats.get("arb_correlation_rejects", 0) + 1
                )
                continue

            # 스프레드 계산: log(price_A / price_B)
            spread = np.log(close_a.values / close_b.values)
            spread = spread[~np.isnan(spread)]
            if len(spread) < cfg.zscore_lookback:
                continue

            # 반감기(half-life) 계산: OLS Δspread ~ spread_lag
            spread_lag = spread[:-1]
            spread_diff = np.diff(spread)
            if len(spread_lag) < 10 or np.std(spread_lag) < 1e-10:
                continue

            try:
                beta = np.cov(spread_diff, spread_lag)[0, 1] / np.var(spread_lag)
                if beta >= 0:  # 비수렴
                    continue
                halflife = -np.log(2) / beta
                if halflife > cfg.halflife_max or halflife < 1:
                    continue
            except (ValueError, ZeroDivisionError):
                continue

            # 스프레드 통계
            spread_mean = float(np.mean(spread))
            spread_std = float(np.std(spread))
            if spread_std < 1e-10:
                continue

            current_zscore = (spread[-1] - spread_mean) / spread_std

            # 중복 페어 방지 (동일 섹터에서 이미 발견된 경우)
            existing_keys = {f"{min(p['code_a'],p['code_b'])}-{max(p['code_a'],p['code_b'])}" for p in pairs}
            if pair_key in existing_keys:
                continue

            pairs.append({
                "code_a": code_a,
                "code_b": code_b,
                "name_a": w_a["name"],
                "name_b": w_b["name"],
                "sector": sector_label,
                "correlation": round(float(corr), 4),
                "halflife": round(float(halflife), 1),
                "spread_mean": spread_mean,
                "spread_std": spread_std,
                "current_zscore": round(float(current_zscore), 3),
                "spread_series": spread,
                "close_a": close_a,
                "close_b": close_b,
            })

        # v2: 누적 (BUG-1)
        self._phase_stats["arb_spreads_detected"] = (
            self._phase_stats.get("arb_spreads_detected", 0) + len(pairs)
        )
        return pairs

    def _load_fixed_pairs(self) -> List[Dict]:
        """
        v5: 설정 기반 고정 ETF 페어 로드.
        _discover_pairs() 대체. correlation_min 필터링 없음 (사전 검증된 페어).
        """
        cfg = self._arb_cfg
        pairs: List[Dict] = []
        cooldown_keys = set(self._arb_pair_cooldown.keys())

        for pair_def in self._arb_fixed_pair_defs:
            code_a = pair_def.get("code_a", "")
            code_b = pair_def.get("code_b", "")
            if not code_a or not code_b:
                continue

            # 쿨다운 체크
            pair_key = f"{min(code_a,code_b)}-{max(code_a,code_b)}"
            if pair_key in cooldown_keys:
                continue

            df_a = self._ohlcv_cache.get(code_a)
            df_b = self._ohlcv_cache.get(code_b)

            if df_a is None or df_b is None:
                continue
            if len(df_a) < cfg.zscore_lookback or len(df_b) < cfg.zscore_lookback:
                continue

            close_a = df_a["close"].astype(float).tail(cfg.correlation_lookback)
            close_b = df_b["close"].astype(float).tail(cfg.correlation_lookback)

            min_len = min(len(close_a), len(close_b))
            if min_len < cfg.zscore_lookback:
                continue
            close_a = close_a.tail(min_len).reset_index(drop=True)
            close_b = close_b.tail(min_len).reset_index(drop=True)

            # 상관계수 (참고용, 필터링 없음)
            corr = close_a.corr(close_b)
            if pd.isna(corr):
                corr = 0.0

            # 스프레드: log(price_A / price_B)
            spread = np.log(close_a.values / close_b.values)
            spread = spread[~np.isnan(spread)]
            if len(spread) < cfg.zscore_lookback:
                continue

            # 반감기
            spread_lag = spread[:-1]
            spread_diff = np.diff(spread)
            halflife = 10.0  # default
            if len(spread_lag) >= 10 and np.std(spread_lag) > 1e-10:
                try:
                    beta = np.cov(spread_diff, spread_lag)[0, 1] / np.var(spread_lag)
                    if beta < 0:
                        halflife = min(-np.log(2) / beta, cfg.halflife_max)
                except (ValueError, ZeroDivisionError):
                    pass

            # 스프레드 통계
            spread_mean = float(np.mean(spread))
            spread_std = float(np.std(spread))
            if spread_std < 1e-10:
                continue

            current_zscore = (spread[-1] - spread_mean) / spread_std

            pairs.append({
                "code_a": code_a,
                "code_b": code_b,
                "name_a": pair_def.get("name_a", code_a),
                "name_b": pair_def.get("name_b", code_b),
                "sector": pair_def.get("sector", "ETF"),
                "correlation": round(float(corr), 4),
                "halflife": round(float(halflife), 1),
                "spread_mean": spread_mean,
                "spread_std": spread_std,
                "current_zscore": round(float(current_zscore), 3),
                "spread_series": spread,
                "close_a": close_a,
                "close_b": close_b,
            })

        self._phase_stats["arb_fixed_pairs_loaded"] = (
            self._phase_stats.get("arb_fixed_pairs_loaded", 0) + len(pairs)
        )
        self._phase_stats["arb_spreads_detected"] = (
            self._phase_stats.get("arb_spreads_detected", 0) + len(pairs)
        )
        return pairs

    def _check_basis_gate(self) -> bool:
        """
        v5: 콘탱고/백워데이션 Basis Gate.
        True = 차익거래 윈도우 OPEN, False = CLOSED.

        US: Basis = (ES=F − SPY) / SPY × 100 → Z-Score
        KOSPI: ^KS200 실현변동성 Z-Score 프록시
        """
        cfg = self._arb_cfg
        if not cfg.basis_gate_enabled:
            self._arb_basis_window_open = True
            return True

        if not self._arb_basis_signals:
            # Basis signal 설정이 없으면 게이트 비활성 (항상 열림)
            self._arb_basis_window_open = True
            return True

        for sig in self._arb_basis_signals:
            spot_code = sig.get("spot_code", "")
            futures_code = sig.get("futures_code", "")
            ma_period = sig.get("basis_ma_period", 20)
            z_threshold = sig.get("basis_zscore_threshold", 1.5)
            use_premium = sig.get("use_premium_estimate", False)

            if use_premium or not futures_code:
                # KOSPI: 변동성 프록시
                spot_ticker = sig.get("spot_ticker", "")
                # ^KS200 데이터는 spot_code 또는 spot_ticker로 조회
                df_spot = self._ohlcv_cache.get(spot_code)
                if df_spot is None:
                    df_spot = self._ohlcv_cache.get(spot_ticker)
                if df_spot is None or len(df_spot) < ma_period * 3:
                    # 데이터 부족 시 게이트 열기 (거래 허용)
                    self._arb_basis_window_open = True
                    return True

                close = df_spot["close"].astype(float)
                returns = close.pct_change().dropna()
                if len(returns) < ma_period:
                    self._arb_basis_window_open = True
                    return True

                # 실현 변동성 (연환산)
                realized_vol = returns.rolling(ma_period).std() * np.sqrt(252)
                realized_vol = realized_vol.dropna()
                if len(realized_vol) < ma_period * 3:
                    self._arb_basis_window_open = True
                    return True

                vol_ma = realized_vol.rolling(ma_period * 3).mean()
                vol_std = realized_vol.rolling(ma_period * 3).std()
                vol_ma_last = vol_ma.iloc[-1]
                vol_std_last = vol_std.iloc[-1]

                if pd.isna(vol_ma_last) or pd.isna(vol_std_last) or vol_std_last < 1e-10:
                    self._arb_basis_window_open = True
                    return True

                vol_zscore = (realized_vol.iloc[-1] - vol_ma_last) / vol_std_last
                is_open = abs(float(vol_zscore)) > z_threshold

                self._arb_basis_data = {
                    "type": "volatility_proxy",
                    "realized_vol": round(float(realized_vol.iloc[-1]), 4),
                    "vol_zscore": round(float(vol_zscore), 3),
                    "threshold": z_threshold,
                    "window_open": is_open,
                }
            else:
                # US: Basis = (Futures - Spot) / Spot × 100
                df_spot = self._ohlcv_cache.get(spot_code)
                df_futures = self._ohlcv_cache.get(futures_code)
                if df_spot is None or df_futures is None:
                    self._arb_basis_window_open = True
                    return True
                if len(df_spot) < ma_period * 2 or len(df_futures) < ma_period * 2:
                    self._arb_basis_window_open = True
                    return True

                spot_close = df_spot["close"].astype(float)
                fut_close = df_futures["close"].astype(float)

                # 날짜 정렬 보장: 길이 맞추기
                min_len = min(len(spot_close), len(fut_close))
                spot_close = spot_close.tail(min_len).reset_index(drop=True)
                fut_close = fut_close.tail(min_len).reset_index(drop=True)

                # Basis 계산: (Futures - Spot) / Spot × 100
                # ES=F는 SPY의 약 10배이므로 스케일 조정
                basis = (fut_close - spot_close * 10) / (spot_close * 10) * 100

                if len(basis) < ma_period:
                    self._arb_basis_window_open = True
                    return True

                basis_ma = basis.rolling(ma_period).mean()
                basis_std = basis.rolling(ma_period).std()

                basis_ma_last = basis_ma.iloc[-1]
                basis_std_last = basis_std.iloc[-1]

                if pd.isna(basis_ma_last) or pd.isna(basis_std_last) or basis_std_last < 1e-10:
                    self._arb_basis_window_open = True
                    return True

                basis_zscore = (basis.iloc[-1] - basis_ma_last) / basis_std_last
                is_open = abs(float(basis_zscore)) > z_threshold

                self._arb_basis_data = {
                    "type": "futures_basis",
                    "basis_pct": round(float(basis.iloc[-1]), 4),
                    "basis_zscore": round(float(basis_zscore), 3),
                    "threshold": z_threshold,
                    "window_open": is_open,
                }

            self._arb_basis_window_open = is_open
            if is_open:
                self._phase_stats["arb_basis_window_opens"] = (
                    self._phase_stats.get("arb_basis_window_opens", 0) + 1
                )
            return is_open

        self._arb_basis_window_open = True
        return True

    def _score_arb_correlation(self, pair: Dict) -> int:
        """
        Layer 1: 상관관계 품질 (0 ~ weight_correlation).
        graduated scoring + 안정성 + 추세.
        """
        cfg = self._arb_cfg
        score = 0
        corr = pair["correlation"]

        # Graduated 상관계수 점수
        if corr > 0.85:
            score += 20
        elif corr > 0.75:
            score += 15
        elif corr > 0.70:
            score += 10

        # 상관관계 안정성: rolling 20일 std
        close_a = pair["close_a"]
        close_b = pair["close_b"]
        if len(close_a) >= 30:
            rolling_corr = close_a.rolling(20).corr(close_b).dropna()
            if len(rolling_corr) > 5:
                corr_std = float(rolling_corr.std())
                if corr_std < 0.1:
                    score += 10
                elif corr_std < 0.15:
                    score += 5

                # 최근 5일 corr 상승 추세
                recent_corr = rolling_corr.tail(5)
                if len(recent_corr) >= 5:
                    if float(recent_corr.iloc[-1]) > float(recent_corr.iloc[0]):
                        score += 5

        return min(score, cfg.weight_correlation)

    def _score_arb_spread(self, pair: Dict) -> int:
        """
        Layer 2: 스프레드 이탈도 (0 ~ weight_spread).
        Z-Score graduated + half-life + IV/RV 비교 (BlackScholes 참조).
        """
        cfg = self._arb_cfg
        score = 0
        zscore = abs(pair["current_zscore"])

        # Graduated Z-Score 점수
        if zscore > 2.5:
            score += 20
        elif zscore > 2.0:
            score += 15
        elif zscore > 1.5:
            score += 10

        # 반감기 보너스 (빠른 회귀 = 높은 점수)
        halflife = pair["halflife"]
        if halflife < 10:
            score += 10
        elif halflife < 20:
            score += 5

        # IV vs RV 비교 (Black-Scholes 영감): 스프레드 실현변동성 분석
        spread_series = pair["spread_series"]
        if len(spread_series) >= 60:
            # 실현변동성 (RV): 최근 20일 vs 장기 60일
            recent_rv = float(np.std(spread_series[-20:]))
            long_rv = float(np.std(spread_series[-60:]))
            if long_rv > 0 and recent_rv > long_rv:
                score += 5  # 변동성 확장 = 회귀 기회↑

        # 스프레드 극단 횟수 (반복 패턴 = 높은 신뢰)
        if len(spread_series) >= 60 and pair["spread_std"] > 0:
            historical_z = (spread_series[-60:] - pair["spread_mean"]) / pair["spread_std"]
            extreme_count = np.sum(np.abs(historical_z) > 1.5)
            if extreme_count >= 3:
                score += 5

        return min(score, cfg.weight_spread)

    def _score_arb_volume(self, pair: Dict) -> int:
        """
        Layer 3: 거래량 + EV 확인 (0 ~ weight_volume).
        EV Engine (futuresStrategy.md): EV = P(W) × Avg.W - P(L) × Avg.L > 0
        """
        cfg = self._arb_cfg
        score = 0

        # 양쪽 종목 거래량 확인
        df_a = self._ohlcv_cache.get(pair["code_a"])
        df_b = self._ohlcv_cache.get(pair["code_b"])

        if df_a is not None and df_b is not None and len(df_a) >= 20 and len(df_b) >= 20:
            vol_a = float(df_a["volume"].iloc[-1])
            vol_b = float(df_b["volume"].iloc[-1])
            vol_ma_a = float(df_a["volume"].tail(20).mean())
            vol_ma_b = float(df_b["volume"].tail(20).mean())

            # 양쪽 vol > MA20
            if vol_ma_a > 0 and vol_ma_b > 0:
                if vol_a > vol_ma_a and vol_b > vol_ma_b:
                    score += 10
                elif vol_a > vol_ma_a or vol_b > vol_ma_b:
                    score += 5

            # 이탈 방향 종목 거래량 급증 (1.5x)
            zscore = pair["current_zscore"]
            if zscore > 0 and vol_ma_a > 0 and vol_a > vol_ma_a * 1.5:
                score += 5  # A가 고평가 → A에 거래량 급증 = 의미있는 이탈
            elif zscore < 0 and vol_ma_b > 0 and vol_b > vol_ma_b * 1.5:
                score += 5  # B가 고평가 → B에 거래량 급증

        # EV > 0 검증 (과거 유사 스프레드 회귀의 승률/손익비)
        ev_positive = self._calculate_arb_ev(pair)
        if ev_positive:
            score += 10

        return min(score, cfg.weight_volume)

    def _calculate_arb_ev(self, pair: Dict) -> bool:
        """
        Expected Value 검증 (futuresStrategy.md).
        EV = P(W) × Avg.W - P(L) × Avg.L
        과거 스프레드 데이터에서 유사 Z-Score 진입의 가상 결과를 시뮬레이션.
        """
        spread_series = pair["spread_series"]
        if len(spread_series) < 60:
            return True  # 데이터 부족 시 통과 (보수적)

        mean = pair["spread_mean"]
        std = pair["spread_std"]
        if std < 1e-10:
            return True

        zscore_series = (spread_series - mean) / std
        entry_threshold = self._arb_cfg.zscore_entry
        exit_threshold = self._arb_cfg.zscore_exit

        wins = []
        losses = []

        i = 0
        while i < len(zscore_series) - 5:
            z = zscore_series[i]
            if abs(z) >= entry_threshold:
                # 진입 시뮬레이션: 이후 5~20일 내 |z| < exit_threshold 도달 여부
                direction = -1 if z > 0 else 1  # z>0이면 축소 베팅
                for j in range(1, min(21, len(zscore_series) - i)):
                    future_z = zscore_series[i + j]
                    pnl_z = direction * (z - future_z)  # Z-Score 변화량
                    if abs(future_z) < exit_threshold:
                        wins.append(float(pnl_z))
                        break
                else:
                    # 20일 내 미회귀 = 손실
                    pnl_z = direction * (z - zscore_series[min(i + 20, len(zscore_series) - 1)])
                    if pnl_z > 0:
                        wins.append(float(pnl_z))
                    else:
                        losses.append(float(abs(pnl_z)))
                i += 10  # 겹치지 않게 점프
            else:
                i += 1

        if not wins and not losses:
            return True  # 데이터 부족

        total = len(wins) + len(losses)
        if total < 3:
            return True  # 충분하지 않으면 통과

        p_win = len(wins) / total
        avg_win = sum(wins) / len(wins) if wins else 0
        avg_loss = sum(losses) / len(losses) if losses else 0
        p_loss = 1 - p_win

        ev = p_win * avg_win - p_loss * avg_loss
        return ev > 0

    def _size_arb_pair(self, price_a: float, price_b: float, score: int) -> tuple:
        """
        v2: 페어 전용 dollar-neutral 사이징 (BUG-6).
        양쪽 동일 금액 기준. 스코어 기반 승수.
        Returns: (qty_a, qty_b)
        """
        equity = self._get_total_equity()
        max_alloc = equity * self._arb_cfg.max_weight_per_pair  # 10%
        half_alloc = max_alloc / 2  # 각 leg 5%

        # 스코어 기반 사이징 (0.7~1.2)
        score_mult = 0.7 + (score - 60) / 100.0 * 0.5  # 60점=0.7, 100점=0.9
        score_mult = max(0.7, min(score_mult, 1.2))

        alloc = half_alloc * score_mult

        # 현금 제약: 최소 현금 비율 유지
        min_cash = equity * self.min_cash_ratio
        available = self.cash - min_cash
        if available <= 0:
            return (0, 0)
        # Long 매수 + Short 마진(50%) 필요 금액
        total_needed = alloc + alloc * 0.5  # Long full + Short margin
        if total_needed > available:
            alloc = available / 1.5  # 역산

        qty_a = max(1, int(alloc / price_a)) if price_a > 0 else 0
        qty_b = max(1, int(alloc / price_b)) if price_b > 0 else 0
        return (qty_a, qty_b)

    def _scan_entries_arbitrage(self):
        """
        Statistical Pairs Arbitrage 양방향 진입 스캔 — v5.
        Z-Score 기반 통계적 진입 (futuresStrategy.md 참조).
        Long + Short 동시 진입.
        v2: 쿨다운 차감, dollar-neutral 사이징, 진입 시 entry_z 저장.
        v3: 워밍업 버퍼, ARB MDD 서킷브레이커 (-10%), 최소 보유일.
        v4: MDD 복구, 진입 완화, 페어 재발견 3일, 쿨다운 5일.
        v5: Fixed ETF Pair Mode + Basis Gate (콘탱고/백워데이션).
        """
        cfg = self._arb_cfg

        # ── v2: 쿨다운 차감 (BUG-3) ──
        expired_keys = []
        for key in list(self._arb_pair_cooldown.keys()):
            self._arb_pair_cooldown[key] -= 1
            if self._arb_pair_cooldown[key] <= 0:
                expired_keys.append(key)
        for key in expired_keys:
            del self._arb_pair_cooldown[key]

        # ── v3: 워밍업 버퍼 (첫 N거래일 진입 금지) ──
        self._arb_day_count += 1
        if self._arb_day_count <= cfg.warmup_buffer_days:
            return

        # ── v4: ARB MDD 서킷브레이커 + 복구 메커니즘 ──
        equity = self._get_total_equity()
        if hasattr(self, '_peak_equity') and self._peak_equity > 0:
            mdd_pct = (equity - self._peak_equity) / self._peak_equity
            if mdd_pct <= -cfg.arb_mdd_limit:
                # MDD 한도 초과 → 신규 진입 차단
                if not self._arb_mdd_halted:
                    self._arb_mdd_halted = True
                    self._arb_mdd_halt_days = 0
                self._arb_mdd_halt_days += 1
                # v4: 시간 기반 자동 복구 (halt_max_days 초과 시 재개)
                halt_max = getattr(cfg, 'arb_mdd_halt_max_days', 20)
                if self._arb_mdd_halt_days >= halt_max:
                    # 현재 equity를 새 baseline으로 설정 (peak 리셋)
                    self._peak_equity = equity
                    self._arb_mdd_halted = False
                    self._arb_mdd_halt_days = 0
                else:
                    return
            elif self._arb_mdd_halted:
                self._arb_mdd_halt_days += 1
                # v4: DD가 recovery 수준(-5%)으로 회복 OR 시간 초과
                recovery_threshold = getattr(cfg, 'arb_mdd_recovery', 0.05)
                halt_max = getattr(cfg, 'arb_mdd_halt_max_days', 20)
                if mdd_pct > -recovery_threshold or self._arb_mdd_halt_days >= halt_max:
                    if self._arb_mdd_halt_days >= halt_max:
                        self._peak_equity = equity
                    self._arb_mdd_halted = False
                    self._arb_mdd_halt_days = 0
                else:
                    return  # 아직 recovery 미달 & 시간 미초과 → 계속 차단

        # ── v5: Basis Gate (콘탱고/백워데이션 체크) ──
        if not self._check_basis_gate():
            self._phase_stats["arb_basis_gate_blocks"] = (
                self._phase_stats.get("arb_basis_gate_blocks", 0) + 1
            )
            return

        # ── Phase 0: 시장 체제 판단 ──
        self._update_market_regime()

        # ── Phase 4: 리스크 게이트 ──
        gate_pass, gate_reason = self._risk_gate_check()
        if not gate_pass:
            return

        # 현재 활성 페어 수 체크
        active_pair_ids = set()
        for pos in self.positions.values():
            if pos.status == "ACTIVE" and pos.pair_id:
                active_pair_ids.add(pos.pair_id)
        if len(active_pair_ids) >= cfg.max_pairs:
            return

        # 이미 보유 중인 종목 코드
        held_codes = set(self.positions.keys())

        # v5: 페어 발견 — use_fixed_pairs 분기
        rediscovery_days = getattr(cfg, 'pair_rediscovery_days', 3)
        current_date = self._get_current_date_str()
        days_since_discovery = 999
        if self._arb_last_discovery and current_date:
            try:
                from datetime import datetime as _dt
                d1 = _dt.strptime(self._arb_last_discovery.replace("-", "")[:8], "%Y%m%d")
                d2 = _dt.strptime(current_date.replace("-", "")[:8], "%Y%m%d")
                days_since_discovery = (d2 - d1).days
            except ValueError:
                days_since_discovery = 999

        if not self._arb_pairs or days_since_discovery >= rediscovery_days:
            if cfg.use_fixed_pairs and self._arb_fixed_pair_defs:
                self._arb_pairs = self._load_fixed_pairs()
            else:
                self._arb_pairs = self._discover_pairs()
            self._arb_last_discovery = current_date

        if not self._arb_pairs:
            return

        # 스캔 누적 (BUG-1)
        self._phase_stats["total_scans"] = self._phase_stats.get("total_scans", 0) + 1

        # 각 페어 스코어링 및 진입
        for pair in self._arb_pairs:
            if len(active_pair_ids) >= cfg.max_pairs:
                break

            code_a = pair["code_a"]
            code_b = pair["code_b"]

            # 이미 보유 중인 종목은 스킵
            if code_a in held_codes or code_b in held_codes:
                continue

            # v4: 실시간 Z-Score 재계산 (페어 발견 시점 값이 아닌 현재 가격 기준)
            df_a = self._ohlcv_cache.get(code_a)
            df_b = self._ohlcv_cache.get(code_b)
            if df_a is not None and df_b is not None and len(df_a) >= cfg.zscore_lookback and len(df_b) >= cfg.zscore_lookback:
                close_a = df_a["close"].astype(float).tail(cfg.correlation_lookback)
                close_b = df_b["close"].astype(float).tail(cfg.correlation_lookback)
                min_len = min(len(close_a), len(close_b))
                if min_len >= cfg.zscore_lookback:
                    close_a = close_a.tail(min_len).reset_index(drop=True)
                    close_b = close_b.tail(min_len).reset_index(drop=True)
                    spread = np.log(close_a.values / close_b.values)
                    spread_recent = spread[-cfg.zscore_lookback:]
                    s_mean = float(np.mean(spread_recent))
                    s_std = float(np.std(spread_recent))
                    if s_std > 1e-10:
                        zscore = (spread[-1] - s_mean) / s_std
                    else:
                        zscore = 0.0
                else:
                    zscore = pair.get("current_zscore", 0)
            else:
                zscore = pair.get("current_zscore", 0)

            # Z-Score 임계값 미달 → 스킵
            if abs(zscore) < cfg.zscore_entry:
                continue

            # 3-Layer 스코어링
            score_l1 = self._score_arb_correlation(pair)
            score_l2 = self._score_arb_spread(pair)
            score_l3 = self._score_arb_volume(pair)
            total_score = score_l1 + score_l2 + score_l3

            self._phase_stats["arb_total_score"] = (
                self._phase_stats.get("arb_total_score", 0) + total_score
            )

            # v5: 고정 페어 모드 → etf_entry_threshold 사용
            threshold = cfg.etf_entry_threshold if cfg.use_fixed_pairs else cfg.entry_threshold
            if total_score < threshold:
                continue

            # ── 양방향 진입 결정 ──
            pair_id = f"arb-{code_a}-{code_b}-{current_date}"

            if zscore > 0:
                # Z > 0: A 고평가 → Short A, B 저평가 → Long B
                long_code, long_name = code_b, pair["name_b"]
                short_code, short_name = code_a, pair["name_a"]
            else:
                # Z < 0: A 저평가 → Long A, B 고평가 → Short B
                long_code, long_name = code_a, pair["name_a"]
                short_code, short_name = code_b, pair["name_b"]

            # Long leg 가격
            long_price = self._current_prices.get(long_code)
            short_price = self._current_prices.get(short_code)
            if not long_price or not short_price:
                continue

            # v2: dollar-neutral 사이징 (BUG-6)
            qty_long, qty_short = self._size_arb_pair(long_price, short_price, total_score)
            if qty_long <= 0 or qty_short <= 0:
                continue

            now = self._get_current_iso()

            # Long leg 시그널 생성 + 매수
            self._signal_counter += 1
            long_signal = SimSignal(
                id=f"sim-sig-{self._signal_counter:04d}",
                stock_code=long_code,
                stock_name=long_name,
                type="BUY",
                price=long_price,
                reason=f"ARB L1:{score_l1} L2:{score_l2} L3:{score_l3} Z:{zscore:+.2f}",
                strength=total_score,
                detected_at=now,
            )
            self.signals.append(long_signal)
            if len(self.signals) > 100:
                self.signals = self.signals[-100:]

            # v2: 통일 사이징으로 매수 (BUG-6)
            self._execute_buy_arb(long_signal, qty_long, pair_id)

            # Short leg 시그널 생성 + 공매도 진입
            self._signal_counter += 1
            short_signal = SimSignal(
                id=f"sim-sig-{self._signal_counter:04d}",
                stock_code=short_code,
                stock_name=short_name,
                type="SELL_SHORT",
                price=short_price,
                reason=f"ARB L1:{score_l1} L2:{score_l2} L3:{score_l3} Z:{zscore:+.2f}",
                strength=total_score,
                detected_at=now,
            )
            self.signals.append(short_signal)
            if len(self.signals) > 100:
                self.signals = self.signals[-100:]

            # v2: 통일 사이징으로 공매도 (BUG-6)
            self._execute_sell_short(short_signal, pair_id, qty_short)

            # v2: 진입 시 entry_z 저장 (방향성 청산용, BUG-5)
            self._arb_pair_states[pair_id] = {
                "entry_z": zscore,
                "code_a": code_a,
                "code_b": code_b,
                "entry_date": current_date,
                "initial_corr": pair["correlation"],
            }

            self._phase_stats["arb_entries"] = self._phase_stats.get("arb_entries", 0) + 1
            active_pair_ids.add(pair_id)
            held_codes.add(long_code)
            held_codes.add(short_code)

            self._add_risk_event(
                "INFO",
                f"ARB 페어 진입: {long_name}(L) + {short_name}(S) | Z={zscore:+.2f} Score={total_score}",
            )

    def _check_exits_arbitrage(self):
        """
        Arbitrage 양방향 청산 로직 — v4.
        우선순위 재정렬 (BUG-2), 방향성 Z-Score (BUG-5),
        상관관계 2일 연속 확인 (BUG-4), 청산 시 쿨다운 등록 (BUG-3).
        v3: Z-Score TP 최소 보유일 3일 (조기 청산 방지).

        Exit Priority:
        1. ES1: -5% 하드 손절 (Long/Short 각각 명시) — BUG-2
        2. ES_ARB_SL: Dynamic ATR SL
        3. ES_ARB_TP: 방향성 Z-Score 청산 (z 부호 전환, v3: 최소 3일 보유) — BUG-5
        4. ES_ARB_CORR: 상관관계 35% 하락 + 2일 연속 — BUG-4
        5. ES3: 트레일링 (5% 활성화)
        6. ES5: 최대 보유 20일
        """
        cfg = self._arb_cfg
        to_close: List[str] = []
        pair_close_reasons: Dict[str, str] = {}  # pair_id → 청산 사유

        for code, pos in self.positions.items():
            if pos.status != "ACTIVE":
                continue

            current_price = pos.current_price
            entry_price = pos.entry_price

            # PnL 계산 (side 별)
            if pos.side == "SHORT":
                pnl_pct = (entry_price - current_price) / entry_price
            else:
                pnl_pct = (current_price - entry_price) / entry_price

            exit_reason = None

            # ══ 순위 1: ES1 -5% 하드 손절 (BUG-2: 최우선, Long/Short 각각 명시) ══
            if pos.side == "SHORT":
                # Short: 가격이 진입가 대비 5% 상승하면 손절
                if current_price >= entry_price * 1.05:
                    actual_loss = (entry_price - current_price) / entry_price
                    exit_reason = f"ES1 Short 하드 손절 ({actual_loss*100:+.1f}%)"
                    self._phase_stats["es_arb_sl"] = self._phase_stats.get("es_arb_sl", 0) + 1
            else:
                # Long: 가격이 진입가 대비 5% 하락하면 손절
                if current_price <= entry_price * 0.95:
                    actual_loss = (current_price - entry_price) / entry_price
                    exit_reason = f"ES1 Long 하드 손절 ({actual_loss*100:+.1f}%)"
                    self._phase_stats["es_arb_sl"] = self._phase_stats.get("es_arb_sl", 0) + 1

            # ══ 순위 2: ES_ARB_SL Dynamic ATR Stop ══
            if not exit_reason:
                df = self._ohlcv_cache.get(code)
                if df is not None and len(df) > 14:
                    if "atr" not in df.columns:
                        df = self._calculate_indicators(df.copy())
                        self._ohlcv_cache[code] = df
                    last_atr = df.iloc[-1].get("atr")
                    last_adx = df.iloc[-1].get("adx")
                    if pd.notna(last_atr) and float(last_atr) > 0:
                        atr_val = float(last_atr)
                        adx_val = float(last_adx) if pd.notna(last_adx) else 0
                        sl_mult = cfg.atr_sl_mult_strong if adx_val >= cfg.adx_dynamic_threshold else cfg.atr_sl_mult

                        if pos.side == "SHORT":
                            atr_stop = entry_price + atr_val * sl_mult
                            # ATR 스탑이 하드 손절보다 넓으면 하드 손절 우선 (이미 체크됨)
                            if current_price >= atr_stop and current_price < entry_price * 1.05:
                                exit_reason = f"ES_ARB_SL Short ATR×{sl_mult} ({pnl_pct*100:+.1f}%)"
                                self._phase_stats["es_arb_sl"] = self._phase_stats.get("es_arb_sl", 0) + 1
                        else:
                            atr_stop = entry_price - atr_val * sl_mult
                            if current_price <= atr_stop and current_price > entry_price * 0.95:
                                exit_reason = f"ES_ARB_SL Long ATR×{sl_mult} ({pnl_pct*100:+.1f}%)"
                                self._phase_stats["es_arb_sl"] = self._phase_stats.get("es_arb_sl", 0) + 1

            # ══ 순위 3: ES_ARB_TP 방향성 Z-Score 청산 (BUG-5, v3: 최소 보유일) ══
            if not exit_reason and pos.pair_id:
                # v3: 최소 보유일 미달 시 Z-Score TP 스킵
                days_held = getattr(pos, 'days_held', 0) or 0
                skip_zscore_tp = days_held < cfg.min_hold_days_for_tp

                for pair in self._arb_pairs:
                    pair_codes = {pair["code_a"], pair["code_b"]}
                    if code in pair_codes:
                        # 실시간 Z-Score 재계산
                        df_a = self._ohlcv_cache.get(pair["code_a"])
                        df_b = self._ohlcv_cache.get(pair["code_b"])
                        if df_a is not None and df_b is not None:
                            close_a = df_a["close"].astype(float).tail(cfg.correlation_lookback)
                            close_b = df_b["close"].astype(float).tail(cfg.correlation_lookback)
                            min_len = min(len(close_a), len(close_b))
                            if min_len >= cfg.zscore_lookback:
                                close_a = close_a.tail(min_len).reset_index(drop=True)
                                close_b = close_b.tail(min_len).reset_index(drop=True)
                                spread = np.log(close_a.values / close_b.values)
                                spread_recent = spread[-cfg.zscore_lookback:]
                                if len(spread_recent) > 0:
                                    s_mean = float(np.mean(spread_recent))
                                    s_std = float(np.std(spread_recent))
                                    if s_std > 1e-10:
                                        current_z = (spread[-1] - s_mean) / s_std

                                        # pair_state는 TP/CORR 양쪽에서 사용
                                        pair_state = self._arb_pair_states.get(pos.pair_id, {})

                                        # v2: 방향성 Z-Score 청산 (BUG-5)
                                        # v3: 최소 보유일(min_hold_days_for_tp) 미달 시 스킵
                                        if not skip_zscore_tp:
                                            entry_z = pair_state.get("entry_z", 0)

                                            if entry_z > 0 and current_z <= cfg.zscore_exit:
                                                # 진입 Z>+2 → 스프레드 축소 기대 → z<0.2 이면 청산
                                                exit_reason = f"ES_ARB_TP Z 방향성 청산 (entry_z={entry_z:+.1f} → z={current_z:.2f})"
                                                self._phase_stats["es_arb_tp"] = self._phase_stats.get("es_arb_tp", 0) + 1
                                                if pos.pair_id:
                                                    pair_close_reasons[pos.pair_id] = exit_reason
                                            elif entry_z < 0 and current_z >= -cfg.zscore_exit:
                                                # 진입 Z<-2 → 스프레드 확대 기대 → z>-0.2 이면 청산
                                                exit_reason = f"ES_ARB_TP Z 방향성 청산 (entry_z={entry_z:+.1f} → z={current_z:.2f})"
                                                self._phase_stats["es_arb_tp"] = self._phase_stats.get("es_arb_tp", 0) + 1
                                                if pos.pair_id:
                                                    pair_close_reasons[pos.pair_id] = exit_reason

                                        # ══ 순위 4: ES_ARB_CORR 상관관계 35% 하락 + 2일 연속 (BUG-4) ══
                                        if not exit_reason:
                                            current_corr = close_a.corr(close_b)
                                            initial_corr = pair_state.get("initial_corr", pair["correlation"])
                                            if pd.notna(current_corr) and initial_corr > 0:
                                                corr_decay = (initial_corr - current_corr) / initial_corr
                                                if corr_decay >= cfg.correlation_decay_exit:
                                                    # v2: 2일 연속 확인 (BUG-4)
                                                    decay_key = pos.pair_id or code
                                                    self._arb_corr_decay_count[decay_key] = (
                                                        self._arb_corr_decay_count.get(decay_key, 0) + 1
                                                    )
                                                    if self._arb_corr_decay_count[decay_key] >= cfg.corr_decay_confirm_days:
                                                        exit_reason = f"ES_ARB_CORR 상관관계 붕괴 {cfg.corr_decay_confirm_days}일 연속 ({corr_decay*100:.0f}%↓)"
                                                        self._phase_stats["es_arb_corr"] = self._phase_stats.get("es_arb_corr", 0) + 1
                                                        if pos.pair_id:
                                                            pair_close_reasons[pos.pair_id] = exit_reason
                                                else:
                                                    # 붕괴 조건 미달 → 카운트 리셋
                                                    decay_key = pos.pair_id or code
                                                    self._arb_corr_decay_count[decay_key] = 0
                        break

            # ══ 순위 5: ES3 트레일링 ══
            if not exit_reason:
                if pos.side == "SHORT":
                    if pnl_pct >= cfg.trailing_activation_pct:
                        pos.trailing_activated = True
                    if pos.trailing_activated and pos.lowest_price > 0:
                        trail_pct = 0.04
                        trail_stop = pos.lowest_price * (1 + trail_pct)
                        if current_price >= trail_stop:
                            exit_reason = f"ES3 Short 트레일링 ({pnl_pct*100:+.1f}%)"
                else:
                    if pnl_pct >= cfg.trailing_activation_pct:
                        pos.trailing_activated = True
                    if pos.trailing_activated:
                        trail_pct = 0.04
                        trail_stop = pos.highest_price * (1 - trail_pct)
                        if current_price <= trail_stop:
                            exit_reason = f"ES3 Long 트레일링 ({pnl_pct*100:+.1f}%)"

            # ══ 순위 6: ES5 최대 보유 ══
            if not exit_reason and pos.days_held >= cfg.max_holding_days:
                exit_reason = f"ES5 최대 보유 {cfg.max_holding_days}일 ({pnl_pct*100:+.1f}%)"

            if exit_reason:
                exit_type = "STOP_LOSS" if pnl_pct < 0 else "TAKE_PROFIT"
                self._execute_sell(pos, current_price, exit_reason, exit_type)
                to_close.append(code)
                if pos.pair_id:
                    pair_close_reasons.setdefault(pos.pair_id, exit_reason)
                    # v2: 청산 시 쿨다운 등록 (BUG-3)
                    pair_state = self._arb_pair_states.get(pos.pair_id, {})
                    cd_a = pair_state.get("code_a", "")
                    cd_b = pair_state.get("code_b", "")
                    if cd_a and cd_b:
                        cooldown_key = f"{min(cd_a,cd_b)}-{max(cd_a,cd_b)}"
                        self._arb_pair_cooldown[cooldown_key] = cfg.pair_cooldown_days
            else:
                # highest/lowest 갱신
                if pos.side == "SHORT":
                    if pos.lowest_price <= 0 or current_price < pos.lowest_price:
                        pos.lowest_price = current_price
                else:
                    if current_price > pos.highest_price:
                        pos.highest_price = current_price

        # 페어 동시 청산: 한쪽이 청산되면 반대쪽도 청산
        for pair_id, reason in pair_close_reasons.items():
            for code, pos in self.positions.items():
                if code in to_close:
                    continue
                if pos.pair_id == pair_id and pos.status == "ACTIVE":
                    paired_reason = f"페어 동시 청산 ({reason})"
                    pnl_pct = (pos.entry_price - pos.current_price) / pos.entry_price if pos.side == "SHORT" else (pos.current_price - pos.entry_price) / pos.entry_price
                    exit_type = "STOP_LOSS" if pnl_pct < 0 else "TAKE_PROFIT"
                    self._execute_sell(pos, pos.current_price, paired_reason, exit_type)
                    to_close.append(code)

        for code in to_close:
            if code in self.positions:
                del self.positions[code]

    def _execute_buy(
        self,
        signal: SimSignal,
        trend_strength: str = "MODERATE",
        trend_stage: str = "MID",
        alignment_score: int = 3,
    ):
        # Phase 4.6: 수집 모드 — 실행하지 않고 시그널만 저장
        if getattr(self, '_collect_mode', False):
            self._collected_signals.append(
                (self.strategy_mode, signal, trend_strength, trend_stage, alignment_score)
            )
            return

        total_equity = self._get_total_equity()
        regime_params = REGIME_PARAMS.get(self._market_regime, REGIME_PARAMS["NEUTRAL"])
        price = signal.price

        # ── 멀티 전략 모드: 슬리브 체크 ──
        if self._strategy_allocator is not None:
            strategy = self.strategy_mode  # 임시 전환된 상태
            pos_count = sum(
                1 for p in self.positions.values()
                if p.status == "ACTIVE" and p.strategy_tag == strategy
            )
            max_pos = self._strategy_allocator.get_max_positions(
                strategy, regime_params["max_positions"]
            )
            if pos_count >= max_pos:
                return
            # 코어(momentum): 전체 equity 사용, 위성 전략: 슬리브 예산 제한
            if strategy != "momentum":
                used = sum(
                    p.quantity * p.current_price
                    for p in self.positions.values()
                    if p.status == "ACTIVE" and p.strategy_tag == strategy
                )
                budget = self._strategy_allocator.get_budget(strategy, total_equity, used)
                if budget <= 0:
                    return

        # Fix 2: 레짐별 시그널 품질 게이트 (BULL 과진입 방지)
        min_strength = self._REGIME_MIN_STRENGTH.get(self._market_regime, 45)
        if signal.strength < min_strength:
            self._phase_stats["regime_quality_blocks"] += 1
            return

        if self.fixed_amount_per_stock > 0:
            # ── 고정 사이징 모드: 종목당 고정 금액 ──
            quantity = int(self.fixed_amount_per_stock / price)
        else:
            # ── ATR 기반 리스크 패리티 포지션 사이징 (BR-P04: 1.5%) ──
            risk_per_trade = total_equity * 0.015

            # ATR 조회
            df = self._ohlcv_cache.get(signal.stock_code)
            atr_val = None
            if df is not None and len(df) > 14:
                if "atr" not in df.columns:
                    df = self._calculate_indicators(df.copy())
                    self._ohlcv_cache[signal.stock_code] = df
                last_atr = df.iloc[-1].get("atr")
                if pd.notna(last_atr):
                    atr_val = float(last_atr)

            if atr_val and atr_val > 0:
                stop_distance = max(atr_val, price * 0.05)  # 최소 ES1 5%
            else:
                stop_distance = price * 0.05

            raw_quantity = risk_per_trade / stop_distance

            # Phase 4.4: 사이징 승수 4개로 단순화 (기존 8개 → 4개)
            # quality: 시그널 품질 (0.6~1.3)
            quality_mult = max(0.6, min(signal.strength / 70.0, 1.3))

            # vix: 변동성 기반 스케일러 (전략별 차별화)
            current_strategy = self.strategy_mode if self.strategy_mode != "multi" else "momentum"
            vix_mult = self._get_vix_sizing_mult(current_strategy)

            # vol: 포트폴리오 변동성 타겟팅 (0.3~1.5)
            vol_mult = 1.0
            if self._strategy_allocator is not None:
                vol_mult = self._strategy_allocator.get_vol_scalar()

            # risk: DD 단계적 감축 (0.5~1.0)
            risk_mult = self._dd_sizing_mult

            # 글로벌 레짐 Kelly Fraction 기반 사이징 (종목별 레짐은 analytics용)
            # kelly_fraction / BASE_KELLY → STRONG_BULL ×1.50, BULL ×1.30, ... CRISIS ×0.50
            _regime_ov = REGIME_OVERRIDES.get(self._market_regime, {})
            kelly_f = _regime_ov.get("kelly_fraction", BASE_KELLY)
            regime_sizing = kelly_f / BASE_KELLY  # 0.75/0.5=1.5, 0.25/0.5=0.5
            if kelly_f != BASE_KELLY:
                self._phase_stats.setdefault("regime_sizing_reductions", 0)
                self._phase_stats["regime_sizing_reductions"] += 1

            quantity = int(raw_quantity * quality_mult * vix_mult * vol_mult * risk_mult * regime_sizing)

            # 최대 가중치 제한 (활성 포지션 수 기반 동적 비중)
            if self._allocator:
                active_count = sum(1 for p in self.positions.values() if p.status == "ACTIVE")
                if active_count <= 3:
                    # 소수 보유: Kelly / (보유+1) → 0: 30%, 1: 15%, 2: 10%, 3: 7.5%
                    dynamic_weight = self._allocator.config.kelly_fraction / max(active_count + 1, 2)
                    tactical_weight = min(dynamic_weight, regime_params["max_weight"])
                else:
                    tactical_weight = self._allocator.get_tactical_max_weight(total_equity)
                max_amount = total_equity * min(tactical_weight, regime_params["max_weight"])
            else:
                max_amount = total_equity * regime_params["max_weight"]

            # 멀티 모드: 위성 전략은 슬리브 예산으로 추가 제한 (코어는 제한 없음)
            if self._strategy_allocator is not None and self.strategy_mode != "momentum":
                strategy = self.strategy_mode
                used = sum(
                    p.quantity * p.current_price
                    for p in self.positions.values()
                    if p.status == "ACTIVE" and p.strategy_tag == strategy
                )
                sleeve_budget = self._strategy_allocator.get_budget(strategy, total_equity, used)
                max_amount = min(max_amount, sleeve_budget)

            if quantity * price > max_amount:
                quantity = int(max_amount / price)

        # 현금 제약 (1-2종목이면 현금 비율 완화)
        effective_cash_ratio = self.min_cash_ratio
        if self._allocator:
            active_count_cash = sum(1 for p in self.positions.values() if p.status == "ACTIVE")
            if active_count_cash <= 2:
                effective_cash_ratio = max(0.50, self.min_cash_ratio - 0.20)
        min_cash = total_equity * effective_cash_ratio
        available = self.cash - min_cash
        if available <= 0 or quantity <= 0:
            return
        if quantity * price > available:
            quantity = int(available / price)
        if quantity <= 0:
            return

        # 슬리피지 + 수수료 적용
        effective_price = price * (1 + self.slippage_pct)
        commission = quantity * effective_price * self.commission_pct
        actual_amount = quantity * effective_price + commission
        self.cash -= actual_amount
        self._daily_trade_amount += actual_amount
        self._total_commission_paid += commission

        now = self._get_current_iso()

        # ── 스케일업 처리: 기존 MR 포지션에 추가 매수 ──
        if signal.stock_code in self.positions:
            existing = self.positions[signal.stock_code]
            if existing.status == "ACTIVE" and existing.scale_count < 1:
                old_qty = existing.quantity
                eff_old_entry = existing.avg_entry_price if existing.avg_entry_price > 0 else existing.entry_price
                old_cost = old_qty * eff_old_entry
                new_cost = quantity * effective_price
                total_qty = old_qty + quantity
                avg_price = (old_cost + new_cost) / total_qty
                existing.quantity = total_qty
                existing.entry_price = round(avg_price, 2)
                existing.avg_entry_price = round(avg_price, 2)
                existing.scale_count += 1
                existing.stop_loss = round(avg_price * (1 + self.stop_loss_pct))
                existing.weight_pct = round((total_qty * existing.current_price) / total_equity * 100, 1)
                self._add_risk_event("INFO",
                    f"스케일업: {signal.stock_name} +{quantity}주 @ {self.currency_symbol}{effective_price:,.0f}")
                # 스케일업 주문 기록
                self._order_counter += 1
                self.orders.append(
                    SimOrder(
                        id=f"sim-ord-{self._order_counter:04d}",
                        stock_code=signal.stock_code,
                        stock_name=signal.stock_name,
                        side="BUY",
                        order_type="MARKET",
                        status="FILLED",
                        price=price,
                        filled_price=effective_price,
                        quantity=quantity,
                        filled_quantity=quantity,
                        created_at=now,
                        filled_at=now,
                        reason=f"MR_SCALE +{quantity}주",
                    )
                )
                if len(self.orders) > 200:
                    self.orders = self.orders[-200:]
                return

        # ── 신규 포지션 생성 ──
        pos_id = f"sim-pos-{signal.stock_code}"
        # B8: Adaptive initial stop — tighter for low-vol stocks, capped at -5%
        _df_for_stop = self._ohlcv_cache.get(signal.stock_code)
        _atr_val = 0.0
        if _df_for_stop is not None and "atr" in _df_for_stop.columns and len(_df_for_stop) > 0:
            _last_atr = _df_for_stop.iloc[-1].get("atr")
            if pd.notna(_last_atr):
                _atr_val = float(_last_atr)
        if _atr_val > 0:
            atr_stop = effective_price - 2.0 * _atr_val
            # Use tighter of ATR-based or -5%
            stop_loss = max(atr_stop, effective_price * 0.95)  # Never wider than -5%
        else:
            stop_loss = effective_price * (1 + self.stop_loss_pct)
        take_profit = effective_price * (1 + self.take_profit_pct)

        self.positions[signal.stock_code] = SimPosition(
            id=pos_id,
            stock_code=signal.stock_code,
            stock_name=signal.stock_name,
            status="ACTIVE",
            quantity=quantity,
            entry_price=effective_price,
            current_price=effective_price,
            pnl=0,
            pnl_pct=0,
            stop_loss=round(stop_loss),
            take_profit=round(take_profit),
            trailing_stop=round(stop_loss),
            highest_price=effective_price,
            entry_date=self._get_current_date_str(),
            days_held=0,
            weight_pct=round(actual_amount / total_equity * 100, 1),
            strategy_tag=self.strategy_mode,
            avg_entry_price=effective_price,
            entry_signal_strength=signal.strength,
            entry_regime=self._market_regime,
            entry_trend_strength=trend_strength,
            stock_regime=self._stock_regimes.get(signal.stock_code, self._market_regime),
        )

        self._order_counter += 1
        self.orders.append(
            SimOrder(
                id=f"sim-ord-{self._order_counter:04d}",
                stock_code=signal.stock_code,
                stock_name=signal.stock_name,
                side="BUY",
                order_type="LIMIT",
                status="FILLED",
                price=price,
                filled_price=effective_price,
                quantity=quantity,
                filled_quantity=quantity,
                created_at=now,
                filled_at=now,
                reason=signal.reason,
            )
        )
        if len(self.orders) > 200:
            self.orders = self.orders[-200:]

        self._add_risk_event("INFO", f"매수 체결: {signal.stock_name} {quantity}주 @ {self.currency_symbol}{price:,.0f}")

    # ══════════════════════════════════════════
    # 청산 시그널 스캔 (momentum_swing.py 복제)
    # ══════════════════════════════════════════

    def _check_exits(self):
        """전략 모드에 따라 청산 체크 분기. multi/regime_* 모드에서는 strategy_tag 기반 라우팅."""
        if self.strategy_mode == "multi" or self.strategy_mode in REGIME_STRATEGY_MODES:
            return self._check_exits_multi()
        elif self.strategy_mode == "smc":
            return self._check_exits_smc()
        elif self.strategy_mode == "breakout_retest":
            return self._check_exits_breakout_retest()
        elif self.strategy_mode == "mean_reversion":
            return self._check_exits_mean_reversion()
        elif self.strategy_mode == "arbitrage":
            return self._check_exits_arbitrage()
        elif self.strategy_mode == "defensive":
            return self._check_exits_defensive()
        return self._check_exits_momentum()

    def _portfolio_mdd_guard(self):
        """DD 12-15% 구간: 스탑 타이트닝, DD >= 15%: 비방어 포지션 강제 청산."""
        equity = self._get_total_equity()
        dd_pct = (equity - self._peak_equity) / self._peak_equity if self._peak_equity > 0 else 0

        if dd_pct <= -0.15:
            # Force liquidate all non-defensive positions
            for code, pos in list(self.positions.items()):
                if pos.status == "ACTIVE" and pos.strategy_tag != "defensive":
                    self._rebalance_exit_codes.add(code)
            self._phase_stats["es_mdd_guard"] += 1
        elif dd_pct <= -0.12:
            # Tighten all active stops to -2% from current price
            for code, pos in self.positions.items():
                if pos.status == "ACTIVE":
                    tight_stop = pos.current_price * 0.98
                    if tight_stop > pos.stop_loss:
                        pos.stop_loss = tight_stop

    def _check_exits_multi(self):
        """멀티 전략 모드: 각 포지션의 strategy_tag에 따라 올바른 청산 로직 라우팅."""
        # P0: Portfolio MDD Guard — DD 기반 강제 청산/스탑 타이트닝
        self._portfolio_mdd_guard()

        # CRISIS 레짐: 비방어 포지션 즉시 청산 대상 지정
        overrides = REGIME_OVERRIDES.get(self._market_regime, {})
        if overrides.get("crisis_exit_immediate"):
            for code, pos in list(self.positions.items()):
                if pos.status == "ACTIVE" and pos.strategy_tag not in ("defensive", "volatility"):
                    self._rebalance_exit_codes.add(code)

        tags_in_use = set()
        for pos in self.positions.values():
            if pos.status == "ACTIVE":
                tags_in_use.add(pos.strategy_tag)

        for tag in tags_in_use:
            original_mode = self.strategy_mode
            self.strategy_mode = tag
            # 태그 필터 설정 — 각 exit 메서드가 해당 전략 포지션만 처리
            self._exit_tag_filter = tag

            if tag == "smc":
                self._check_exits_smc()
            elif tag == "breakout_retest":
                self._check_exits_breakout_retest()
            elif tag == "mean_reversion":
                self._check_exits_mean_reversion()
            elif tag == "arbitrage":
                self._check_exits_arbitrage()
            elif tag == "defensive":
                self._check_exits_defensive()
            elif tag == "volatility":
                self._check_exits_volatility()
            else:  # momentum (default)
                self._check_exits_momentum()

            self._exit_tag_filter = None
            self.strategy_mode = original_mode

    def _check_exits_momentum(self):
        """기존 Momentum Swing 청산 로직."""
        to_close: List[str] = []

        for code, pos in self.positions.items():
            if pos.status != "ACTIVE":
                continue
            if self._exit_tag_filter and pos.strategy_tag != self._exit_tag_filter:
                continue
            # 글로벌 레짐 기반 청산 파라미터 (종목별 레짐은 analytics용)
            regime_exit = REGIME_EXIT_PARAMS.get(self._market_regime, REGIME_EXIT_PARAMS["NEUTRAL"])

            current_price = self._current_prices.get(code, pos.current_price)
            entry_price = pos.entry_price
            pnl_pct = (current_price - entry_price) / entry_price

            exit_reason = None
            exit_type = None

            # ATR 기반 프로그레시브 트레일링 폭 사전 계산
            atr_pct_val = 0.03  # 기본값
            df = self._ohlcv_cache.get(code)
            if df is not None and len(df) > 14:
                if "atr_pct" not in df.columns:
                    df = self._calculate_indicators(df.copy())
                    self._ohlcv_cache[code] = df
                last_atr = df.iloc[-1].get("atr_pct")
                if pd.notna(last_atr):
                    atr_pct_val = float(last_atr)
            # 프로그레시브 트레일링: 수익 클수록 타이트한 보호
            if self.disable_es2:
                # ── 강화 트레일링 (ES2 비활성화 모드: 7단계) ──
                if pnl_pct >= 0.30:
                    trail_mult = 2.0   # +30%+: 2×ATR, 플로어 -4% (슈퍼 위너 타이트 보호)
                    trail_floor = -0.04
                elif pnl_pct >= 0.25:
                    trail_mult = 2.5   # +25-30%: 2.5×ATR, 플로어 -5%
                    trail_floor = -0.05
                elif pnl_pct >= 0.20:
                    trail_mult = 3.0   # +20-25%: 3×ATR, 플로어 -6% (기존 ES2 대체)
                    trail_floor = -0.06
                elif pnl_pct >= 0.15:
                    trail_mult = 3.5   # +15-20%: 3.5×ATR, 플로어 -6%
                    trail_floor = -0.06
                elif pnl_pct >= 0.10:
                    trail_mult = 4.0   # +10-15%: 4×ATR, 플로어 -5%
                    trail_floor = -0.05
                elif pnl_pct >= 0.07:
                    trail_mult = 3.5   # +7-10%: 3.5×ATR, 플로어 -5%
                    trail_floor = -0.05
                else:
                    trail_mult = 3.0   # 기본: 3×ATR, 플로어 -4%
                    trail_floor = self.trailing_stop_pct
            else:
                # ── 기존 트레일링 (4단계) ──
                if pnl_pct >= 0.15:
                    trail_mult = 5.0   # +15%+: 5×ATR, 플로어 -8%
                    trail_floor = -0.08
                elif pnl_pct >= 0.10:
                    trail_mult = 4.0   # +10-15%: 4×ATR, 플로어 -6%
                    trail_floor = -0.06
                elif pnl_pct >= 0.07:
                    trail_mult = 3.5   # +7-10%: 3.5×ATR, 플로어 -5%
                    trail_floor = -0.05
                else:
                    trail_mult = 3.0   # 기본: 3×ATR, 플로어 -4%
                    trail_floor = self.trailing_stop_pct
            # 글로벌 레짐별 트레일링 오버라이드 (STRONG_BULL: 2.0×ATR 타이트)
            _ro = REGIME_OVERRIDES.get(self._market_regime, {})
            if "trail_atr_mult" in _ro:
                regime_trail_mult = _ro["trail_atr_mult"]
                regime_trail_floor = _ro.get("trail_floor_pct", trail_floor)
                # 레짐 기반 배수가 현재보다 더 타이트하면 적용
                if regime_trail_mult < trail_mult:
                    trail_mult = regime_trail_mult
                    trail_floor = regime_trail_floor

            trail_pct = max(-trail_mult * atr_pct_val, trail_floor)

            # BULL 이격도 부분 청산 (ES1/ES2 전에 실행 — 비파괴적)
            if _ro.get("disparity_partial_sell") and not pos.disparity_sold:
                _disp = None
                if df is not None and "disparity_20" in df.columns:
                    _disp = df.iloc[-1].get("disparity_20")
                elif df is not None and "ma20" in df.columns:
                    _ma20 = df.iloc[-1].get("ma20")
                    if pd.notna(_ma20) and _ma20 > 0:
                        _disp = current_price / float(_ma20)
                if _disp is not None and pd.notna(_disp) and _disp > _ro.get("disparity_threshold", 1.15):
                    sell_qty = max(1, int(pos.quantity * _ro.get("partial_sell_ratio", 0.5)))
                    if sell_qty < pos.quantity:
                        self._execute_partial_sell(pos, sell_qty, "ES_DISP_PARTIAL")
                        pos.disparity_sold = True

            # ES1: 손절 -5% (GAP DOWN 보호: _execute_sell에서 fill price 조정)
            if current_price <= entry_price * (1 + self.stop_loss_pct):
                exit_reason = "ES1 손절 -5%"
                exit_type = "STOP_LOSS"

            # ES2: 익절 (체제별 동적) — disable_es2 모드에서 비활성화
            elif not self.disable_es2 and current_price >= entry_price * (1 + regime_exit["take_profit"]):
                tp_label = f"+{regime_exit['take_profit']*100:.0f}%"
                exit_reason = f"ES2 익절 {tp_label}"
                exit_type = "TAKE_PROFIT"

            # ES3: 트레일링 스탑 (활성화 임계 도달 후에만, ATR 기반)
            elif pnl_pct >= (0.03 if self.disable_es2 else regime_exit["trail_activation"]):
                if not pos.trailing_activated:
                    pos.trailing_activated = True
                trailing_stop_price = pos.highest_price * (1 + trail_pct)
                if current_price <= trailing_stop_price:
                    exit_reason = "ES3 트레일링스탑"
                    exit_type = "TRAILING_STOP"

            # ES4: 데드크로스 (MA5/20 — 수익 포지션: 타이트 트레일링 전환)
            if not exit_reason:
                if df is not None and len(df) >= self.ma_long + 2:
                    df_calc = df if "ma_short" in df.columns else self._calculate_indicators(df.copy())
                    if len(df_calc) >= 2:
                        curr_row = df_calc.iloc[-1]
                        prev_row = df_calc.iloc[-2]
                        if (
                            pd.notna(curr_row.get("ma_short"))
                            and pd.notna(curr_row.get("ma_long"))
                            and pd.notna(prev_row.get("ma_short"))
                            and pd.notna(prev_row.get("ma_long"))
                            and prev_row["ma_short"] >= prev_row["ma_long"]
                            and curr_row["ma_short"] < curr_row["ma_long"]
                        ):
                            if pnl_pct >= 0.02:
                                # 수익 포지션: 즉시 청산 대신 타이트 트레일링 활성화
                                # 1.5×ATR (표준 3×ATR보다 타이트) 또는 최소 -2%
                                tight_trail = max(-1.5 * atr_pct_val, -0.02)
                                pos.trailing_activated = True
                                pos.trailing_stop = round(current_price * (1 + tight_trail))
                            elif pnl_pct < -0.02:
                                # 손실 -2% 초과만 청산 (경미한 손실은 회복 기회)
                                exit_reason = "ES4 데드크로스"
                                exit_type = "DEAD_CROSS"
                            # -2% ~ +2%: 무시 (ES1/ES3/ES5가 처리)

            # ES5: 보유기간 초과 (체제별 동적)
            if not exit_reason and pos.days_held > regime_exit["max_holding"]:
                exit_reason = "ES5 보유기간 초과"
                exit_type = "MAX_HOLDING"

            # ES7: 리밸런스 청산 (워치리스트 탈락) — PnL 게이트 적용
            if not exit_reason and code in self._rebalance_exit_codes:
                if pos.days_held < 3 or pnl_pct <= -0.02:
                    exit_reason = "ES7 리밸런스 청산"
                    exit_type = "REBALANCE_EXIT"
                    self._rebalance_exit_codes.discard(code)
                elif pnl_pct > 0.02:
                    # 수익 포지션은 유예 (다음 리밸런스까지 보유)
                    self._rebalance_exit_codes.discard(code)
                else:
                    exit_reason = "ES7 리밸런스 청산"
                    exit_type = "REBALANCE_EXIT"
                    self._rebalance_exit_codes.discard(code)

            if exit_reason:
                to_close.append(code)
                # Phase 통계: 청산 이유별 카운터
                exit_stat_map = {
                    "EMERGENCY_STOP": "es0_emergency_stop",
                    "STOP_LOSS": "es1_stop_loss",
                    "TAKE_PROFIT": "es2_take_profit",
                    "TRAILING_STOP": "es3_trailing_stop",
                    "DEAD_CROSS": "es4_dead_cross",
                    "MAX_HOLDING": "es5_max_holding",
                    "TIME_DECAY": "es6_time_decay",
                    "REBALANCE_EXIT": "es7_rebalance_exit",
                }
                stat_key = exit_stat_map.get(exit_type or "")
                if stat_key:
                    self._phase_stats[stat_key] += 1
                self._execute_sell(pos, current_price, exit_reason, exit_type or "")
            else:
                # 트레일링 최고가 갱신 (ATR 기반)
                if current_price > pos.highest_price:
                    pos.highest_price = current_price
                    if pos.trailing_activated:
                        pos.trailing_stop = round(current_price * (1 + trail_pct))
                    else:
                        pos.trailing_stop = round(current_price * (1 + self.trailing_stop_pct))

        for code in to_close:
            del self.positions[code]

    def _execute_partial_sell(self, pos: 'SimPosition', sell_qty: int, exit_code: str):
        """포지션의 일부만 청산 (BULL 이격도 분할 청산용).
        수량만 줄이고, 잔여 포지션은 계속 유지. avg_entry_price 유지.
        """
        if sell_qty <= 0 or sell_qty >= pos.quantity:
            return
        price = pos.current_price
        if price <= 0:
            price = pos.entry_price
        effective_price = price * (1 - self.slippage_pct)
        commission = sell_qty * effective_price * self.commission_pct
        proceeds = sell_qty * effective_price - commission
        self.cash += proceeds
        self._total_commission_paid += commission

        # 포지션 수량 감소 (avg_entry_price 유지)
        old_qty = pos.quantity
        pos.quantity -= sell_qty

        self._phase_stats.setdefault("es_disp_partial_sell", 0)
        self._phase_stats["es_disp_partial_sell"] += 1

        # 주문 기록
        self._order_counter += 1
        now = self._get_current_iso()
        self.orders.append(
            SimOrder(
                id=f"sim-ord-{self._order_counter:04d}",
                stock_code=pos.stock_code,
                stock_name=pos.stock_name,
                side="SELL",
                order_type="MARKET",
                status="FILLED",
                price=price,
                filled_price=effective_price,
                quantity=sell_qty,
                filled_quantity=sell_qty,
                created_at=now,
                filled_at=now,
                reason=f"{exit_code}: 부분청산 {sell_qty}/{old_qty}주",
            )
        )

        self._add_risk_event("INFO",
            f"부분청산: {pos.stock_name} {sell_qty}/{old_qty}주 @ {self.currency_symbol}{effective_price:,.0f} ({exit_code})")

    def _execute_sell(self, pos: SimPosition, price: float, reason: str, exit_type: str):
        now = self._get_current_iso()

        # ── GAP DOWN 보호: 스탑 청산 시 fill price를 stop level로 제한 ──
        # 갭다운으로 종가가 스탑보다 훨씬 아래인 경우, 스탑가 부근에서 체결된 것으로 시뮬레이션
        if exit_type in ("STOP_LOSS", "ATR_STOP_LOSS", "EMERGENCY_STOP") and pos.side != "SHORT":
            daily_low = getattr(self, '_daily_lows', {}).get(pos.stock_code)
            daily_high = getattr(self, '_daily_highs', {}).get(pos.stock_code)
            daily_open = getattr(self, '_daily_opens', {}).get(pos.stock_code)
            eff_entry = pos.avg_entry_price if pos.avg_entry_price > 0 else pos.entry_price
            # ATR SL은 포지션의 실제 stop_loss 사용, ES0은 -10%, ES1은 -5% 하드 스탑
            if exit_type == "ATR_STOP_LOSS" and pos.stop_loss > 0:
                stop_price = pos.stop_loss
            elif exit_type == "EMERGENCY_STOP":
                stop_price = eff_entry * 0.90  # -10% 비상 스탑
            else:
                stop_price = eff_entry * (1 + self.stop_loss_pct)  # -5% 스탑
            if daily_low is not None and daily_low < stop_price:
                if daily_high is not None and daily_high >= stop_price:
                    # 장중 스탑 레벨 통과 → 스탑가에서 체결 (정상 케이스)
                    price = stop_price
                elif daily_open is not None and daily_open < stop_price:
                    # 갭다운: 시가부터 스탑 이하 → 시가에서 체결 (시장가 주문)
                    price = daily_open
                else:
                    # 시가 데이터 없을 때 → 스탑가에서 체결 (보수적)
                    price = stop_price
            elif price < stop_price:
                # 종가가 스탑 이하지만 저가는 스탑 이상 → 스탑가에서 체결
                price = stop_price

        if pos.side == "SHORT":
            # ── Short 청산 (Buy to Cover) ──
            effective_price = price * (1 + self.slippage_pct)  # 매수이므로 불리한 방향
            commission = pos.quantity * effective_price * self.commission_pct
            cost = pos.quantity * effective_price + commission
            self.cash -= cost  # 환매 비용 차감
            self._daily_trade_amount += cost
            self._total_commission_paid += commission
            pnl = (pos.entry_price - effective_price) * pos.quantity - commission
            pnl_pct_val = (pos.entry_price - effective_price) / pos.entry_price * 100
            order_side = "BUY_TO_COVER"
            action_label = "숏 청산"
        else:
            # ── Long 청산 (기존 로직) ──
            effective_price = price * (1 - self.slippage_pct)
            commission = pos.quantity * effective_price * self.commission_pct
            proceeds = pos.quantity * effective_price - commission
            self.cash += proceeds
            self._daily_trade_amount += proceeds
            self._total_commission_paid += commission
            eff_entry = pos.avg_entry_price if pos.avg_entry_price > 0 else pos.entry_price
            pnl = proceeds - (pos.quantity * eff_entry)
            pnl_pct_val = (effective_price - eff_entry) / eff_entry * 100
            order_side = "SELL"
            action_label = "매도 체결"

        self._order_counter += 1
        self.orders.append(
            SimOrder(
                id=f"sim-ord-{self._order_counter:04d}",
                stock_code=pos.stock_code,
                stock_name=pos.stock_name,
                side=order_side,
                order_type="MARKET",
                status="FILLED",
                price=price,
                filled_price=effective_price,
                quantity=pos.quantity,
                filled_quantity=pos.quantity,
                created_at=now,
                filled_at=now,
                reason=reason,
            )
        )
        if len(self.orders) > 200:
            self.orders = self.orders[-200:]

        # 청산 시그널 기록
        self._signal_counter += 1
        self.signals.append(
            SimSignal(
                id=f"sim-sig-{self._signal_counter:04d}",
                stock_code=pos.stock_code,
                stock_name=pos.stock_name,
                type=order_side,
                price=price,
                reason=reason,
                strength=80,
                detected_at=now,
            )
        )
        if len(self.signals) > 100:
            self.signals = self.signals[-100:]

        # 청산 트레이드 기록
        self._trade_counter += 1
        self.closed_trades.append(
            SimTradeRecord(
                id=f"sim-trade-{self._trade_counter:04d}",
                stock_code=pos.stock_code,
                stock_name=pos.stock_name,
                entry_date=pos.entry_date,
                exit_date=now[:10],
                entry_price=pos.entry_price,
                exit_price=effective_price,
                quantity=pos.quantity,
                pnl=round(pnl),
                pnl_pct=round(pnl_pct_val, 2),
                exit_reason=reason,
                holding_days=pos.days_held,
                strategy_tag=pos.strategy_tag,
                entry_signal_strength=pos.entry_signal_strength,
                entry_regime=pos.entry_regime,
                entry_trend_strength=pos.entry_trend_strength,
                stock_regime=pos.stock_regime,
            )
        )
        if not self._replay_mode and len(self.closed_trades) > 200:
            self.closed_trades = self.closed_trades[-200:]

        # B7: Per-stock regime performance tracking
        _entry_stock_regime = getattr(pos, "stock_regime", "NEUTRAL")
        _sr_counts = self._phase_stats.setdefault("_stock_regime_pnls", {})
        if _entry_stock_regime not in _sr_counts:
            _sr_counts[_entry_stock_regime] = {"wins": 0, "losses": 0, "total_pnl": 0.0, "count": 0}
        _sr_counts[_entry_stock_regime]["count"] += 1
        _sr_counts[_entry_stock_regime]["total_pnl"] += pnl_pct_val
        if pnl_pct_val > 0:
            _sr_counts[_entry_stock_regime]["wins"] += 1
        else:
            _sr_counts[_entry_stock_regime]["losses"] += 1

        # Phase 3.4: Dynamic Kelly — 전략별 거래 결과 기록
        if self._strategy_allocator is not None:
            self._strategy_allocator.record_trade_result(pos.strategy_tag, pnl_pct_val / 100.0)

        event_type = "WARNING" if pnl < 0 else "INFO"
        self._add_risk_event(event_type, f"{action_label}: {pos.stock_name} {reason} (P&L {pnl_pct_val:+.1f}%)")

        if exit_type == "STOP_LOSS":
            self._consecutive_stops += 1
            if self._consecutive_stops >= 3:
                self._add_risk_event("HALT", f"연속 손절 {self._consecutive_stops}회 — 매매 정지")
        else:
            self._consecutive_stops = 0

    def _execute_buy_arb(self, signal: SimSignal, quantity: int, pair_id: str):
        """
        v2: Arbitrage Long leg 매수 — dollar-neutral 사이징 (BUG-6).
        _execute_buy()와 유사하지만 수량이 _size_arb_pair()에서 미리 계산됨.
        """
        total_equity = self._get_total_equity()
        price = signal.price

        if quantity <= 0 or price <= 0:
            return

        # 현금 제약
        cost = quantity * price
        min_cash = total_equity * self.min_cash_ratio
        available = self.cash - min_cash
        if available <= 0:
            return
        if cost > available:
            quantity = int(available / price)
        if quantity <= 0:
            return

        cost = quantity * price

        # 슬리피지 + 수수료
        effective_price = price * (1 + self.slippage_pct)
        commission = quantity * effective_price * self.commission_pct
        total_cost = quantity * effective_price + commission

        if total_cost > self.cash:
            quantity = int((self.cash - commission) / effective_price)
        if quantity <= 0:
            return

        total_cost = quantity * effective_price + commission
        self.cash -= total_cost
        self._daily_trade_amount += total_cost
        self._total_commission_paid += commission

        now = self._get_current_iso()
        pos_id = f"sim-long-{signal.stock_code}"

        # 스탑로스: 고정 -5% (BUG-2: Long/Short 동일)
        stop_loss = effective_price * (1 + self.stop_loss_pct)  # -5%

        self.positions[signal.stock_code] = SimPosition(
            id=pos_id,
            stock_code=signal.stock_code,
            stock_name=signal.stock_name,
            status="ACTIVE",
            quantity=quantity,
            entry_price=effective_price,
            current_price=effective_price,
            pnl=0,
            pnl_pct=0,
            stop_loss=round(stop_loss, 2),
            take_profit=0,  # Z-Score 기반 청산
            trailing_stop=round(stop_loss, 2),
            highest_price=effective_price,
            entry_date=self._get_current_date_str(),
            days_held=0,
            max_holding_days=self._arb_cfg.max_holding_days,
            weight_pct=round(total_cost / self.initial_capital * 100, 1),
            side="LONG",
            lowest_price=effective_price,
            pair_id=pair_id,
            strategy_tag=self.strategy_mode,
            entry_signal_strength=signal.strength,
            entry_regime=self._market_regime,
            entry_trend_strength="MODERATE",
            stock_regime=self._stock_regimes.get(signal.stock_code, self._market_regime),
        )

        self._order_counter += 1
        self.orders.append(
            SimOrder(
                id=f"sim-ord-{self._order_counter:04d}",
                stock_code=signal.stock_code,
                stock_name=signal.stock_name,
                side="BUY",
                order_type="MARKET",
                status="FILLED",
                price=price,
                filled_price=effective_price,
                quantity=quantity,
                filled_quantity=quantity,
                created_at=now,
                filled_at=now,
                reason=f"ARB Long: {signal.reason}",
            )
        )
        if len(self.orders) > 200:
            self.orders = self.orders[-200:]

        self._add_risk_event("INFO", f"롱 진입: {signal.stock_name} @{effective_price:,.0f} ×{quantity} (pair: {pair_id})")

    def _execute_sell_short(self, signal: SimSignal, pair_id: str, arb_quantity: int = 0):
        """Short 포지션 오픈 (공매도 진입). Arbitrage 전용. v2: dollar-neutral 사이징 (BUG-6)."""
        total_equity = self._get_total_equity()
        price = signal.price

        # v2: arb_quantity가 제공되면 사용, 아니면 기존 로직 (하위호환)
        if arb_quantity > 0:
            quantity = arb_quantity
        else:
            # 기존 fallback 사이징
            risk_per_trade = total_equity * 0.015
            df_tmp = self._ohlcv_cache.get(signal.stock_code)
            atr_tmp = None
            if df_tmp is not None and len(df_tmp) > 14:
                if "atr" not in df_tmp.columns:
                    df_tmp = self._calculate_indicators(df_tmp.copy())
                    self._ohlcv_cache[signal.stock_code] = df_tmp
                last_atr_tmp = df_tmp.iloc[-1].get("atr")
                if pd.notna(last_atr_tmp):
                    atr_tmp = float(last_atr_tmp)
            stop_dist = max(atr_tmp * self._arb_cfg.atr_sl_mult, price * 0.05) if (atr_tmp and atr_tmp > 0) else price * 0.05
            quantity = int(risk_per_trade / stop_dist)

        # 페어당 최대 비중 제한
        max_amount = total_equity * self._arb_cfg.max_weight_per_pair * 0.5
        if quantity * price > max_amount:
            quantity = int(max_amount / price)

        # 현금 제약 (Short 마진 = 매도 대금의 50% 예비)
        min_cash = total_equity * self.min_cash_ratio
        margin_required = quantity * price * 0.5
        available = self.cash - min_cash
        if available <= 0 or quantity <= 0:
            return
        if margin_required > available:
            quantity = int(available * 2 / price)
        if quantity <= 0:
            return

        # 슬리피지 + 수수료 (매도 진입)
        effective_price = price * (1 - self.slippage_pct)
        commission = quantity * effective_price * self.commission_pct
        proceeds = quantity * effective_price - commission
        self.cash += proceeds  # 매도 대금 수취
        self._daily_trade_amount += proceeds
        self._total_commission_paid += commission

        now = self._get_current_iso()
        pos_id = f"sim-short-{signal.stock_code}"

        # v2: 스탑로스 고정 -5% (BUG-2: Long과 동일, 하드 손절 최우선)
        stop_loss = effective_price * 1.05  # Short: 가격 5% 상승 시 손절

        take_profit = 0  # Z-Score 기반 청산이므로 고정 TP 없음

        self.positions[signal.stock_code] = SimPosition(
            id=pos_id,
            stock_code=signal.stock_code,
            stock_name=signal.stock_name,
            status="ACTIVE",
            quantity=quantity,
            entry_price=effective_price,
            current_price=effective_price,
            pnl=0,
            pnl_pct=0,
            stop_loss=round(stop_loss, 2),
            take_profit=round(take_profit, 2),
            trailing_stop=round(stop_loss, 2),
            highest_price=effective_price,
            entry_date=self._get_current_date_str(),
            days_held=0,
            max_holding_days=self._arb_cfg.max_holding_days,
            weight_pct=round(proceeds / self.initial_capital * 100, 1),
            side="SHORT",
            lowest_price=effective_price,
            pair_id=pair_id,
            strategy_tag=self.strategy_mode,
            entry_signal_strength=signal.strength,
            entry_regime=self._market_regime,
            entry_trend_strength="MODERATE",
            stock_regime=self._stock_regimes.get(signal.stock_code, self._market_regime),
        )

        # 매도 진입 주문 기록
        self._order_counter += 1
        self.orders.append(
            SimOrder(
                id=f"sim-ord-{self._order_counter:04d}",
                stock_code=signal.stock_code,
                stock_name=signal.stock_name,
                side="SELL_SHORT",
                order_type="MARKET",
                status="FILLED",
                price=price,
                filled_price=effective_price,
                quantity=quantity,
                filled_quantity=quantity,
                created_at=now,
                filled_at=now,
                reason=f"ARB Short: {signal.reason}",
            )
        )
        if len(self.orders) > 200:
            self.orders = self.orders[-200:]

        self._add_risk_event("INFO", f"숏 진입: {signal.stock_name} @{effective_price:,.0f} ×{quantity} (pair: {pair_id})")
        self._phase_stats["arb_short_entries"] = self._phase_stats.get("arb_short_entries", 0) + 1


    # ══════════════════════════════════════════
    # 가격 업데이트
    # ══════════════════════════════════════════

    def _update_position_prices(self):
        total_equity = self._get_total_equity()
        for code, pos in self.positions.items():
            if pos.status != "ACTIVE":
                continue
            price = self._current_prices.get(code, pos.current_price)
            pos.current_price = price

            if pos.side == "SHORT":
                # Short: 가격 하락 = 이익
                pos.pnl = (pos.entry_price - price) * pos.quantity
                pos.pnl_pct = round((pos.entry_price - price) / pos.entry_price * 100, 2)
                # Short 트레일링용 최저가 추적
                if pos.lowest_price <= 0:
                    pos.lowest_price = price
                else:
                    pos.lowest_price = min(pos.lowest_price, price)
            else:
                # Long: 가격 상승 = 이익 (기존 로직)
                pos.pnl = (price - pos.entry_price) * pos.quantity
                pos.pnl_pct = round((price - pos.entry_price) / pos.entry_price * 100, 2)

            pos.weight_pct = round(price * pos.quantity / total_equity * 100, 1) if total_equity > 0 else 0

    # ══════════════════════════════════════════
    # 상태 조회
    # ══════════════════════════════════════════

    def _get_total_equity(self) -> float:
        invested = 0
        for p in self.positions.values():
            if p.status != "ACTIVE":
                continue
            if p.side == "SHORT":
                # Short 가치: 매도 대금(entry×qty) + 미실현 손익(entry-current)×qty
                # = 2×entry×qty - current×qty (margin + unrealized PnL)
                invested += p.entry_price * p.quantity + (p.entry_price - p.current_price) * p.quantity
            else:
                invested += p.current_price * p.quantity
        return self.cash + invested

    def get_system_state(self) -> SimSystemState:
        total_equity = self._get_total_equity()
        invested = total_equity - self.cash
        daily_pnl = total_equity - self._daily_start_equity
        daily_pnl_pct = (daily_pnl / self._daily_start_equity * 100) if self._daily_start_equity > 0 else 0

        regime_params = REGIME_PARAMS.get(self._market_regime, REGIME_PARAMS["NEUTRAL"])
        mode = "REPLAY" if self._backtest_date else "PAPER"
        return SimSystemState(
            status="RUNNING" if self._is_running else "STOPPED",
            mode=mode,
            started_at=self._started_at,
            market_phase="OPEN" if self._is_running else "CLOSED",
            market_regime=self._market_regime,
            next_scan_at=None,
            total_equity=round(total_equity),
            cash=round(self.cash),
            invested=round(invested),
            daily_pnl=round(daily_pnl),
            daily_pnl_pct=round(daily_pnl_pct, 2),
            position_count=len([p for p in self.positions.values() if p.status == "ACTIVE"]),
            max_positions=regime_params["max_positions"],
        )

    def get_risk_metrics(self) -> SimRiskMetrics:
        total_equity = self._get_total_equity()
        daily_pnl_pct = (
            (total_equity - self._daily_start_equity) / self._daily_start_equity * 100
            if self._daily_start_equity > 0
            else 0
        )
        self._peak_equity = max(self._peak_equity, total_equity)
        mdd = (
            (total_equity - self._peak_equity) / self._peak_equity * 100
            if self._peak_equity > 0
            else 0
        )
        cash_ratio = (self.cash / total_equity * 100) if total_equity > 0 else 100

        is_halted = daily_pnl_pct <= -3.0 or self._consecutive_stops >= 3
        halt_reason = None
        if daily_pnl_pct <= -3.0:
            halt_reason = "일일 손실 한도 도달"
        elif self._consecutive_stops >= 3:
            halt_reason = f"연속 손절 {self._consecutive_stops}회"

        return SimRiskMetrics(
            daily_pnl_pct=round(daily_pnl_pct, 2),
            mdd=round(mdd, 2),
            cash_ratio=round(cash_ratio, 1),
            consecutive_stops=self._consecutive_stops,
            daily_trade_amount=round(self._daily_trade_amount),
            is_trading_halted=is_halted,
            halt_reason=halt_reason,
        )

    def _add_risk_event(self, event_type: str, message: str, value: float = None, limit: float = None):
        self._event_counter += 1
        self.risk_events.append(
            {
                "id": f"sim-evt-{self._event_counter:04d}",
                "type": event_type,
                "message": message,
                "value": value,
                "limit": limit,
                "timestamp": self._get_current_iso(),
            }
        )
        if len(self.risk_events) > 100:
            self.risk_events = self.risk_events[-100:]

    # ══════════════════════════════════════════
    # 성과 추적
    # ══════════════════════════════════════════

    def _record_equity_point(self):
        total_equity = self._get_total_equity()
        self._peak_equity = max(self._peak_equity, total_equity)
        # 에쿼티 모멘텀 히스토리 갱신 (최근 30일)
        self._equity_history.append(total_equity)
        if len(self._equity_history) > 30:
            self._equity_history = self._equity_history[-30:]
        dd = (
            (total_equity - self._peak_equity) / self._peak_equity * 100
            if self._peak_equity > 0
            else 0
        )
        today = self._get_current_date_str()
        # 같은 날 마지막 포인트만 유지 (덮어쓰기)
        if self.equity_curve and self.equity_curve[-1].date == today:
            self.equity_curve[-1] = SimEquityPoint(
                date=today, equity=round(total_equity), drawdown_pct=round(dd, 2)
            )
        else:
            self.equity_curve.append(
                SimEquityPoint(
                    date=today, equity=round(total_equity), drawdown_pct=round(dd, 2)
                )
            )
        if not self._replay_mode and len(self.equity_curve) > 365:
            self.equity_curve = self.equity_curve[-365:]

    def get_performance_summary(self) -> SimPerformanceSummary:
        trades = self.closed_trades
        if not trades:
            total_equity = self._get_total_equity()
            total_return = (total_equity - self.initial_capital) / self.initial_capital * 100
            return SimPerformanceSummary(
                total_return_pct=round(total_return, 2),
                max_drawdown_pct=round(
                    min((p.drawdown_pct for p in self.equity_curve), default=0), 2
                ),
            )

        wins = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl <= 0]
        total_equity = self._get_total_equity()
        total_return = (total_equity - self.initial_capital) / self.initial_capital * 100

        win_rate = len(wins) / len(trades) * 100 if trades else 0
        avg_win = sum(t.pnl_pct for t in wins) / len(wins) if wins else 0
        avg_loss = sum(t.pnl_pct for t in losses) / len(losses) if losses else 0
        total_win_amount = sum(t.pnl for t in wins)
        total_loss_amount = abs(sum(t.pnl for t in losses))
        profit_factor = (
            total_win_amount / total_loss_amount if total_loss_amount > 0 else 0
        )
        avg_holding = sum(t.holding_days for t in trades) / len(trades) if trades else 0
        best_trade = max(t.pnl_pct for t in trades) if trades else 0
        worst_trade = min(t.pnl_pct for t in trades) if trades else 0

        # 간이 Sharpe (일간 수익률 기반)
        if len(self.equity_curve) >= 2:
            returns = []
            for i in range(1, len(self.equity_curve)):
                prev = self.equity_curve[i - 1].equity
                curr = self.equity_curve[i].equity
                if prev > 0:
                    returns.append((curr - prev) / prev)
            if returns and len(returns) > 1:
                mean_r = sum(returns) / len(returns)
                std_r = (sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)) ** 0.5
                sharpe = (mean_r / std_r * math.sqrt(252)) if std_r > 0 else 0
            else:
                sharpe = 0
        else:
            sharpe = 0

        max_dd = min((p.drawdown_pct for p in self.equity_curve), default=0)

        return SimPerformanceSummary(
            total_return_pct=round(total_return, 2),
            total_trades=len(trades),
            win_rate=round(win_rate, 2),
            avg_win_pct=round(avg_win, 2),
            avg_loss_pct=round(avg_loss, 2),
            profit_factor=round(profit_factor, 2),
            sharpe_ratio=round(sharpe, 2),
            max_drawdown_pct=round(max_dd, 2),
            avg_holding_days=round(avg_holding, 1),
            best_trade_pct=round(best_trade, 2),
            worst_trade_pct=round(worst_trade, 2),
        )

    # ══════════════════════════════════════════
    # SSE 브로드캐스트
    # ══════════════════════════════════════════

    async def _broadcast_all(self):
        state = self.get_system_state()
        risk = self.get_risk_metrics()
        positions = [p.model_dump() for p in self.positions.values() if p.status == "ACTIVE"]

        prefix = self.market_id

        # system_state에 마켓 메타데이터 포함
        state_data = state.model_dump()
        state_data["market_id"] = self.market_id
        state_data["currency"] = self.currency
        state_data["currency_symbol"] = self.currency_symbol
        state_data["market_label"] = self.market_label

        # 레짐별 동적 전략 이름 (Multi 모드에서 사용)
        trend_key = (self._index_trend or {}).get("trend", self._market_regime)
        regime_label = REGIME_DISPLAY_NAMES.get(
            trend_key, REGIME_DISPLAY_NAMES.get("NEUTRAL")
        )
        state_data["active_strategy_label"] = regime_label
        state_data["strategy_display_names"] = STRATEGY_DISPLAY_NAMES
        state_data["strategy_composition"] = REGIME_STRATEGY_COMPOSITION.get(
            trend_key, REGIME_STRATEGY_COMPOSITION.get("NEUTRAL", {})
        )
        state_data["actual_market_regime"] = self._actual_market_regime
        state_data["regime_locked"] = self._regime_locked
        state_data["locked_regime"] = self._locked_regime

        await self._on_event(f"{prefix}:system_state", state_data)
        await self._on_event(f"{prefix}:positions", positions)
        await self._on_event(f"{prefix}:signals", [s.model_dump() for s in self.signals[-20:]])
        await self._on_event(f"{prefix}:orders", [o.model_dump() for o in self.orders[-50:]])
        await self._on_event(f"{prefix}:risk_metrics", risk.model_dump())
        await self._on_event(f"{prefix}:risk_events", self.risk_events[-30:])
        await self._on_event(f"{prefix}:equity_curve", [p.model_dump() for p in self.equity_curve[-200:]])
        await self._on_event(f"{prefix}:performance", self.get_performance_summary().model_dump())
