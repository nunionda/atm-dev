"""
Smart Money Concepts (SMC) — BOS/CHoCH, Order Block, FVG, Swing Points.

Phase 4.A 분할: ats/analytics/indicators.py → ats/analytics/indicators/smc.py
"""
import pandas as pd
import numpy as np

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


