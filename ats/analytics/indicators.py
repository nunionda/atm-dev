import pandas as pd
import ta
import numpy as np

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

    # NaN 값을 None 또는 특정 값으로 처리하기 (JSON 직렬화를 위해)
    df = df.replace({np.nan: None})
    return df

def calculate_smc(df: pd.DataFrame, swing_length=3) -> pd.DataFrame:
    """
    Market Structure (SMC) 관련 지표를 계산합니다.
    - swing_high, swing_low: 로컬 고점/저점
    - bos, choch: 추세 지속 및 반전 마커
    - ob_bull, ob_bear: 오더 블록 (가격대 튜플을 문자열화 또는 별도 필드로 반환 시 복잡하므로 여기선 단일 캔들 마커로 간소화 혹은 FVG처럼 리스트로 별도로 빼내는 것이 좋으나, 데이터프레임 구조상 각 캔들의 속성으로 추가합니다)
    """
    # 1. Swings (Pivot)
    # 고점은 양옆 swing_length 만큼의 캔들보다 높아야 함
    df['is_swing_high'] = False
    df['is_swing_low'] = False
    
    highs = df['high'].values
    lows = df['low'].values
    length = len(df)
    
    swing_highs = [] # (index, price)
    swing_lows = []
    
    for i in range(swing_length, length - swing_length):
        is_sh = True
        is_sl = True
        
        # Check surrounding bars
        for j in range(1, swing_length + 1):
            if highs[i] <= highs[i-j] or highs[i] <= highs[i+j]:
                is_sh = False
            if lows[i] >= lows[i-j] or lows[i] >= lows[i+j]:
                is_sl = False
                
        if is_sh:
            df.at[df.index[i], 'is_swing_high'] = True
            swing_highs.append((i, highs[i]))
        if is_sl:
            df.at[df.index[i], 'is_swing_low'] = True
            swing_lows.append((i, lows[i]))
            
    # 2. BOS & CHoCH & OB
    # 굉장히 복잡한 알고리즘이 될 수 있으므로, 간소화된 룰 적용
    # 가장 최근 확정된 SH(Swing High)와 SL(Swing Low)을 추적
    df['marker'] = None # 'BOS_BULL', 'BOS_BEAR', 'CHOCH_BULL', 'CHOCH_BEAR'
    df['ob_top'] = None
    df['ob_bottom'] = None
    
    trend = 1 # 1: Bullish, -1: Bearish
    last_sh_idx, last_sh_price = -1, float('inf')
    last_sl_idx, last_sl_price = -1, float('-inf')
    
    for i in range(length):
        close = df['close'].iloc[i]
        
        # update current recent swings (that are already confirmed, so up to i - swing_length)
        # To avoid lookahead bias, we only know a swing is formed after swing_length bars
        curr_confirmed_idx = i - swing_length
        if curr_confirmed_idx >= 0:
            if df['is_swing_high'].iloc[curr_confirmed_idx]:
                last_sh_idx = curr_confirmed_idx
                last_sh_price = df['high'].iloc[curr_confirmed_idx]
            if df['is_swing_low'].iloc[curr_confirmed_idx]:
                last_sl_idx = curr_confirmed_idx
                last_sl_price = df['low'].iloc[curr_confirmed_idx]

        if last_sh_idx != -1 and last_sl_idx != -1:
            if trend == 1:
                if close > last_sh_price: # BOS Bull
                    df.at[df.index[i], 'marker'] = 'BOS_BULL'
                    # OB Bull: The last down candle before this impulsive move
                    # Search back from last_sl_idx to find the lowest close/open diff or just the last red candle
                    for j in range(i-1, max(0, last_sl_idx-5), -1):
                        if df['close'].iloc[j] < df['open'].iloc[j]:
                            df.at[df.index[i], 'ob_top'] = df['high'].iloc[j]
                            df.at[df.index[i], 'ob_bottom'] = df['low'].iloc[j]
                            break
                    # We broke the high, so we need a new high to break next time. Reset last_sh_price to prevent multiple triggers.
                    last_sh_price = float('inf') 
                elif close < last_sl_price: # CHoCH Bear
                    df.at[df.index[i], 'marker'] = 'CHOCH_BEAR'
                    trend = -1
                    last_sl_price = float('-inf')
            elif trend == -1:
                if close < last_sl_price: # BOS Bear
                    df.at[df.index[i], 'marker'] = 'BOS_BEAR'
                    # OB Bear: The last up candle
                    for j in range(i-1, max(0, last_sh_idx-5), -1):
                        if df['close'].iloc[j] > df['open'].iloc[j]:
                            df.at[df.index[i], 'ob_top'] = df['high'].iloc[j]
                            df.at[df.index[i], 'ob_bottom'] = df['low'].iloc[j]
                            break
                    last_sl_price = float('-inf')
                elif close > last_sh_price: # CHoCH Bull
                    df.at[df.index[i], 'marker'] = 'CHOCH_BULL'
                    trend = 1
                    last_sh_price = float('inf')

    # 3. Fair Value Gap (FVG)
    # Bull FVG: Low of candle 3 > High of candle 1
    # Bear FVG: High of candle 3 < Low of candle 1
    df['fvg_top'] = None
    df['fvg_bottom'] = None
    df['fvg_type'] = None # 'bull' or 'bear'
    
    for i in range(2, length):
        # Candle 1 = i-2, Candle 2 = i-1, Candle 3 = i
        c1_high = highs[i-2]
        c1_low = lows[i-2]
        c3_high = highs[i]
        c3_low = lows[i]
        
        if c3_low > c1_high: # Bull FVG
            df.at[df.index[i-1], 'fvg_type'] = 'bull' # Tag the middle candle
            df.at[df.index[i-1], 'fvg_top'] = c3_low
            df.at[df.index[i-1], 'fvg_bottom'] = c1_high
        elif c3_high < c1_low: # Bear FVG
            df.at[df.index[i-1], 'fvg_type'] = 'bear'
            df.at[df.index[i-1], 'fvg_top'] = c1_low
            df.at[df.index[i-1], 'fvg_bottom'] = c3_high

    return df
