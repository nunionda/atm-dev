"""
analytics.indicators — Barrel

Phase 4.A 완료: 940-line indicators.py를 도메인별 6개 모듈로 분할.
외부 import 호환성을 위해 단일 진입점 유지.

분할 구조:
    basic.py        — SMA/EMA/RSI/MACD/BB/ATR/ADX (uses `ta` library)
    smc.py          — Smart Money Concepts (BOS/CHoCH/OB/FVG)
    candlestick.py  — Hammer/Engulfing/Doji/Soldiers etc.
    fibonacci.py    — Fibonacci retracement levels
    patterns.py     — Triangle/Cup&Handle/H&S chart patterns
    oscillators.py  — Connors RSI/Williams %R/MFI/Z-Score/CMF

Usage:
    from analytics.indicators import calculate_basic_indicators, calculate_smc
    # or directly:
    from analytics.indicators.smc import calculate_smc
"""

from .basic import calculate_basic_indicators
from .smc import calculate_smc
from .candlestick import calculate_candlestick_patterns
from .fibonacci import calculate_fibonacci_levels
from .patterns import detect_chart_patterns
from .oscillators import (
    calculate_connors_rsi,
    calculate_williams_r,
    calculate_mfi,
    calculate_zscore,
    calculate_cmf,
)

__all__ = [
    "calculate_basic_indicators",
    "calculate_smc",
    "calculate_candlestick_patterns",
    "calculate_fibonacci_levels",
    "detect_chart_patterns",
    "calculate_connors_rsi",
    "calculate_williams_r",
    "calculate_mfi",
    "calculate_zscore",
    "calculate_cmf",
]
