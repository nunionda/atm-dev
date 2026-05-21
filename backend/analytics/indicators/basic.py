"""
Basic technical indicators — SMA, EMA, RSI, MACD, BB, ATR, ADX/DMI.

Phase 4.A 분할: ats/analytics/indicators.py → ats/analytics/indicators/basic.py
"""
import pandas as pd
import numpy as np
import ta

# Phase 4.A: calculate_basic_indicators는 다른 도메인 인디케이터를 chain으로 호출.
# 분할 후 cross-module import 필요.
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


def calculate_basic_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    OHLCV 데이터프레임에 기본적인 기술적 지표를 추가합니다.
    df: 'open', 'high', 'low', 'close', 'volume' 컬럼이 포함되어야 합니다.
    """
    df = df.copy()

    # 필수 컬럼 확인
    required_cols = ['open', 'high', 'low', 'close', 'volume']
    if not all(col in df.columns for col in required_cols):
        raise ValueError(f"DataFrame must contain columns: {required_cols}")

    # 거래량 0인 행 제거 (휴장일 데이터 왜곡 방지)
    # 단, 인덱스 같은 'volume이 항상 0'인 ticker는 필터를 건너뜀 (DXY, ^VIX 등)
    if df['volume'].max() > 0:
        df = df[df['volume'] > 0]

    # ===== 1. 이동평균선 (Moving Averages) =====
    df['sma_5'] = ta.trend.sma_indicator(df['close'], window=5)
    df['sma_20'] = ta.trend.sma_indicator(df['close'], window=20)
    df['sma_50'] = ta.trend.sma_indicator(df['close'], window=50)
    df['sma_60'] = ta.trend.sma_indicator(df['close'], window=60)
    df['sma_120'] = ta.trend.sma_indicator(df['close'], window=120)
    df['sma_200'] = ta.trend.sma_indicator(df['close'], window=200)
    df['ema_20'] = ta.trend.ema_indicator(df['close'], window=20)
    
    # ===== 2. 볼린저 밴드 (Bollinger Bands) =====
    indicator_bb = ta.volatility.BollingerBands(close=df['close'], window=20, window_dev=2)
    df['bb_hband'] = indicator_bb.bollinger_hband()
    df['bb_lband'] = indicator_bb.bollinger_lband()
    df['bb_mavg'] = indicator_bb.bollinger_mavg()
    df['bb_width'] = indicator_bb.bollinger_wband()
    
    # ===== 3. 모멘텀 지표 (Momentum) =====
    df['rsi_14'] = ta.momentum.rsi(df['close'], window=14)
    df['macd'] = ta.trend.macd(df['close'])
    df['macd_signal'] = ta.trend.macd_signal(df['close'])
    df['macd_diff'] = ta.trend.macd_diff(df['close'])
    
    # ===== 4. 변동성 지표 (Volatility) =====
    if len(df) >= 14:
        df['atr_14'] = ta.volatility.average_true_range(
            high=df['high'], low=df['low'], close=df['close'], window=14
        )
    else:
        df['atr_14'] = np.nan

    # ===== 5. 추세 강도 지표 (ADX) =====
    # ADX는 내부적으로 2×window 이상의 데이터가 필요 (ta 라이브러리 제약)
    if len(df) >= 28:
        try:
            adx_indicator = ta.trend.ADXIndicator(
                high=df['high'], low=df['low'], close=df['close'], window=14, fillna=True
            )
            df['adx'] = adx_indicator.adx()
            df['plus_di'] = adx_indicator.adx_pos()
            df['minus_di'] = adx_indicator.adx_neg()
        except (IndexError, Exception):
            df['adx'] = np.nan
            df['plus_di'] = np.nan
            df['minus_di'] = np.nan
    else:
        df['adx'] = np.nan
        df['plus_di'] = np.nan
        df['minus_di'] = np.nan
    
    # ===== 6. Market Structure (SMC) =====
    # 이 부분은 별도의 함수로 분리하여 복잡도를 낮출 수도 있으나,
    # 프론트엔드로 일괄 전달하기 위해 df 변환 함수 내에 통합합니다.
    df = calculate_smc(df)
    df = calculate_candlestick_patterns(df)  # P2: Candlestick patterns
    df = calculate_fibonacci_levels(df)       # P3: Fibonacci levels
    df = detect_chart_patterns(df)            # P3: Chart patterns

    # B1-B5: Additional technical indicators (Connors RSI, Williams %R, MFI, Z-score, CMF)
    df = calculate_connors_rsi(df)
    df = calculate_williams_r(df)
    if 'volume' in df.columns:
        df = calculate_mfi(df)
        df = calculate_cmf(df)
    df = calculate_zscore(df)

    # NaN 값을 None 또는 특정 값으로 처리하기 (JSON 직렬화를 위해)
    df = df.replace({np.nan: None})
    return df

