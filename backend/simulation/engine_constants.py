"""
Simulation Engine Constants — 워치리스트, 레짐 파라미터, Kelly 분포 등.

Phase 4.C 분할: ats/simulation/engine.py → ats/simulation/engine_constants.py
"""

from typing import Any, Callable, Coroutine, Dict, List

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
    # H5: 추세 우선 정책 — BULL 계열 TP 사실상 비활성 + trail 조기 활성 + max_holding 연장.
    # ES2 절대값 익절 도달은 거의 없음 (백테스트 1건/77건) → trailing 위주 운영.
    "STRONG_BULL": {"max_holding": 60, "take_profit": 0.50, "trail_activation": 0.03},
    "BULL":        {"max_holding": 60, "take_profit": 0.40, "trail_activation": 0.03},
    # NEUTRAL/약세 레짐은 빠른 회수가 맞으므로 기존 유지
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
    # H7: Kelly + min_cash_override를 추세에 따라 동적 매핑
    # 기본 Half-Kelly(0.5) ↔ cash floor 50%
    # 추세상승: Kelly ↑ 0.75 ↔ cash floor 25% (75% 투자)
    # 추세하락: Kelly ↓ 0.25 ↔ cash floor 75% (25% 투자)
    "STRONG_BULL": {
        # H7: Three-Quarter Kelly = 75% 투자
        "kelly_fraction": 0.75,
        "min_cash_override": 0.10,     # H8: 현금 10% (90% 투자 — 패시브 ETF + 액티브 혼합)
        # H8: 패시브 ETF 모드 (시장 추종) — 강세장에서 액티브 매매보다 우월
        "passive_etf_mode": True,
        "passive_etf_weight": 0.70,    # ETF에 70% 배분 (액티브 20% + 현금 10%)
        # Entry: Donchian 돌파 추가, 피라미딩 허용
        "donchian_entry": True,
        "donchian_period": 20,
        "pyramiding_enabled": True,
        "pyramiding_max": 1,
        "pyramiding_pnl_min": 0.05,
        # Exit: 공격적 트레일링
        "trail_atr_mult": 2.0,
        "trail_floor_pct": -0.04,
    },
    "BULL": {
        # H7: 65% Kelly (= 35% cash floor) — Half-Kelly와 STRONG_BULL 사이 보간
        "kelly_fraction": 0.65,
        "min_cash_override": 0.20,     # H8: 현금 20% (80% 투자 — 패시브 50% + 액티브 30%)
        # H8: 패시브 ETF 모드 (시장 추종)
        "passive_etf_mode": True,
        "passive_etf_weight": 0.50,    # ETF 50% + 액티브 30% + 현금 20%
        "donchian_entry": False,
        "pyramiding_enabled": False,
        "disparity_partial_sell": True,
        "disparity_threshold": 1.15,
        "partial_sell_ratio": 0.5,
    },
    "NEUTRAL": {
        # C4.1: Half-Kelly + 자본 활용 ↑ (이전 0.50 → 0.60, cash 40%)
        # NEUTRAL이 백테스트 시간의 37% 차지하므로 자본 활용도 ↑
        "kelly_fraction": 0.60,
        "min_cash_override": 0.40,     # 현금 40% (60% 투자 — 이전 50/50 → 60/40)
        "mr_adx_limit": 22,
        "time_decay_enabled": True,
        "time_decay_days": 10,
        "time_decay_pnl_min": 0.02,
    },
    "RANGE_BOUND": {
        # H7: 40% Kelly = 60% cash
        "kelly_fraction": 0.40,
        "min_cash_override": 0.60,     # 현금 60%
        "sr_zone_entry": True,
        "sr_atr_buffer": 1.5,
        "box_breakout_exit": True,
        "box_lookback": 40,
    },
    "BEAR": {
        # H7: 30% Kelly = 70% cash (이전 50% → 70% 강화)
        "kelly_fraction": 0.30,
        "min_cash_override": 0.70,     # 현금 70%
        "defensive_vix_threshold": 20,
        "bear_exit_tighten": True,
    },
    "CRISIS": {
        # H7: Quarter Kelly = 75% cash (사용자 의도 "추세하락 0.25" 정확히 매칭)
        "kelly_fraction": 0.25,
        "min_cash_override": 0.75,     # 현금 75% (위기 시 25%만 위험자산)
        "safe_haven_enabled": True,
        "crisis_vix_threshold": 30,
        "crisis_exit_immediate": True,
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

# H8: 패시브 모드 ETF (STRONG_BULL/BULL 레짐에서 시장 추종)
# 강세장에서는 액티브 매매보다 인덱스 ETF Buy & Hold가 우월하므로,
# REGIME=STRONG_BULL/BULL 시 워치리스트 종목 매수 대신 ETF 직매수.
PASSIVE_INDEX_ETFS: Dict[str, Dict[str, str]] = {
    "sp500":  {"code": "SPY",        "ticker": "SPY",        "name": "S&P 500 ETF"},
    "nasdaq": {"code": "QQQ",        "ticker": "QQQ",        "name": "Nasdaq 100 ETF"},
    "ndx":    {"code": "QQQ",        "ticker": "QQQ",        "name": "Nasdaq 100 ETF"},
    "kospi":  {"code": "069500",     "ticker": "069500.KS",  "name": "KODEX 200"},
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


