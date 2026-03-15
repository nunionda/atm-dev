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
    df = calculate_candlestick_patterns(df)  # P2: Candlestick patterns

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


def calculate_candlestick_patterns(df: pd.DataFrame) -> pd.DataFrame:
    """
    P2: Vectorized candlestick pattern detector.
    Detects 12 patterns (Tier 1 base ±30, Tier 2 base ±15).
    Output columns: candle_pattern (str|None), candle_score (int, -100 to +100).
    """
    if len(df) < 3:
        df['candle_pattern'] = None
        df['candle_score'] = 0
        return df

    df = df.copy()
    close = df['close'].values.astype(float)
    open_p = df['open'].values.astype(float)
    high = df['high'].values.astype(float)
    low = df['low'].values.astype(float)
    volume = df['volume'].values.astype(float) if 'volume' in df.columns else None
    n = len(df)

    body = close - open_p
    body_abs = np.abs(body)
    upper_shadow = high - np.maximum(close, open_p)
    lower_shadow = np.minimum(close, open_p) - low
    hl_range = high - low
    # Avoid division by zero
    hl_range_safe = np.where(hl_range > 0, hl_range, 1.0)
    body_abs_safe = np.where(body_abs > 0, body_abs, 1e-10)

    # Bullish/Bearish candle flags
    is_bullish = body > 0
    is_bearish = body < 0

    # Previous bar values (shifted by 1)
    prev_close = np.roll(close, 1)
    prev_open = np.roll(open_p, 1)
    prev_high = np.roll(high, 1)
    prev_low = np.roll(low, 1)
    prev_body = np.roll(body, 1)
    prev_body_abs = np.roll(body_abs, 1)
    prev_bullish = np.roll(is_bullish, 1)
    prev_bearish = np.roll(is_bearish, 1)

    # 2-bars-ago values (shifted by 2)
    prev2_close = np.roll(close, 2)
    prev2_open = np.roll(open_p, 2)
    prev2_body = np.roll(body, 2)
    prev2_hl_range = np.roll(hl_range, 2)

    # Initialize score and pattern arrays
    scores = np.zeros(n, dtype=float)
    patterns = np.full(n, None, dtype=object)
    pattern_scores = np.zeros(n, dtype=float)  # track strongest pattern score per bar

    # ═══ Tier 1 Patterns (base ±30) ═══

    # 1. Bullish Engulfing: prev bearish, curr bullish, curr body covers prev body
    bull_engulf = (
        prev_bearish & is_bullish &
        (open_p <= prev_close) & (close >= prev_open)
    )
    bull_engulf[:1] = False
    scores += np.where(bull_engulf, 30, 0)
    _update_pattern(patterns, pattern_scores, bull_engulf, "BULLISH_ENGULFING", 30)

    # 2. Bearish Engulfing: prev bullish, curr bearish, curr body covers prev body
    bear_engulf = (
        prev_bullish & is_bearish &
        (open_p >= prev_close) & (close <= prev_open)
    )
    bear_engulf[:1] = False
    scores += np.where(bear_engulf, -30, 0)
    _update_pattern(patterns, pattern_scores, bear_engulf, "BEARISH_ENGULFING", 30)

    # 3. Hammer: small body at top, lower shadow >= 2x body, upper shadow < body, after 3+ down bars
    hammer_shape = (
        (body_abs > 0) &
        (lower_shadow >= 2 * body_abs) &
        (upper_shadow < body_abs)
    )
    # Context: 3+ consecutive down bars before
    down_count = np.zeros(n)
    for i in range(1, n):
        if close[i - 1] < open_p[i - 1]:
            down_count[i] = down_count[i - 1] + 1
        else:
            down_count[i] = 0
    hammer = hammer_shape & (down_count >= 3)
    scores += np.where(hammer, 30, 0)
    _update_pattern(patterns, pattern_scores, hammer, "HAMMER", 30)

    # 4a. Shooting Star: small body at bottom, upper shadow >= 2x body, after 3+ up bars
    shooting_shape = (
        (body_abs > 0) &
        (upper_shadow >= 2 * body_abs) &
        (lower_shadow < body_abs)
    )
    up_count = np.zeros(n)
    for i in range(1, n):
        if close[i - 1] > open_p[i - 1]:
            up_count[i] = up_count[i - 1] + 1
        else:
            up_count[i] = 0
    shooting_star = shooting_shape & (up_count >= 3)
    scores += np.where(shooting_star, -30, 0)
    _update_pattern(patterns, pattern_scores, shooting_star, "SHOOTING_STAR", 30)

    # 4b. Inverted Hammer: upper shadow >= 2x body, after 3+ down bars (bullish reversal)
    inv_hammer = shooting_shape & (down_count >= 3)
    scores += np.where(inv_hammer, 25, 0)
    _update_pattern(patterns, pattern_scores, inv_hammer, "INVERTED_HAMMER", 25)

    # 5. Morning Star: bearish -> small body -> bullish, 3rd close > midpoint of 1st body
    prev2_bearish_ms = prev2_body < 0
    prev1_doji = np.roll(body_abs, 1) < 0.1 * np.roll(hl_range_safe, 1)
    prev2_midpoint = prev2_open + prev2_body / 2
    morning_star = (
        prev2_bearish_ms & prev1_doji & is_bullish &
        (close > prev2_midpoint)
    )
    morning_star[:2] = False
    scores += np.where(morning_star, 30, 0)
    _update_pattern(patterns, pattern_scores, morning_star, "MORNING_STAR", 30)

    # 6. Evening Star: bullish -> small body -> bearish, 3rd close < midpoint of 1st body
    prev2_bullish_es = prev2_body > 0
    evening_star = (
        prev2_bullish_es & prev1_doji & is_bearish &
        (close < prev2_midpoint)
    )
    evening_star[:2] = False
    scores += np.where(evening_star, -30, 0)
    _update_pattern(patterns, pattern_scores, evening_star, "EVENING_STAR", 30)

    # 7. Three White Soldiers: 3 consecutive bullish, higher closes, each opens within prev body
    prev2_bullish_flag = np.roll(is_bullish, 2)
    prev1_bullish_flag = np.roll(is_bullish, 1)
    higher_closes = (close > prev_close) & (prev_close > prev2_close)
    opens_in_prev_body = (
        (open_p >= np.minimum(prev_close, prev_open)) & (open_p <= np.maximum(prev_close, prev_open)) &
        (prev_open >= np.minimum(prev2_close, prev2_open)) & (prev_open <= np.maximum(prev2_close, prev2_open))
    )
    three_white = prev2_bullish_flag & prev1_bullish_flag & is_bullish & higher_closes & opens_in_prev_body
    three_white[:2] = False
    scores += np.where(three_white, 30, 0)
    _update_pattern(patterns, pattern_scores, three_white, "THREE_WHITE_SOLDIERS", 30)

    # 8. Three Black Crows: 3 consecutive bearish, lower closes, each opens within prev body
    prev2_bearish_flag = np.roll(is_bearish, 2)
    prev1_bearish_flag = np.roll(is_bearish, 1)
    lower_closes = (close < prev_close) & (prev_close < prev2_close)
    opens_in_prev_body_bear = (
        (open_p >= np.minimum(prev_close, prev_open)) & (open_p <= np.maximum(prev_close, prev_open)) &
        (prev_open >= np.minimum(prev2_close, prev2_open)) & (prev_open <= np.maximum(prev2_close, prev2_open))
    )
    three_black = prev2_bearish_flag & prev1_bearish_flag & is_bearish & lower_closes & opens_in_prev_body_bear
    three_black[:2] = False
    scores += np.where(three_black, -30, 0)
    _update_pattern(patterns, pattern_scores, three_black, "THREE_BLACK_CROWS", 30)

    # ═══ Tier 2 Patterns (base ±15) ═══

    # 9. Doji: body < 10% of hl_range
    doji = body_abs < 0.1 * hl_range_safe
    dragonfly = doji & (lower_shadow > 2 * upper_shadow) & (lower_shadow > 0)
    gravestone = doji & (upper_shadow > 2 * lower_shadow) & (upper_shadow > 0)
    scores += np.where(dragonfly, 15, 0)
    scores += np.where(gravestone, -15, 0)
    _update_pattern(patterns, pattern_scores, dragonfly, "DRAGONFLY_DOJI", 15)
    _update_pattern(patterns, pattern_scores, gravestone, "GRAVESTONE_DOJI", 15)

    # 10. Piercing Line: prev bearish, open < prev low, close > prev body midpoint
    prev_mid_bear = prev_open + prev_body / 2  # midpoint of prev body (bearish: open > close)
    piercing = (
        prev_bearish & is_bullish &
        (open_p < prev_low) &
        (close > prev_mid_bear)
    )
    piercing[:1] = False
    scores += np.where(piercing, 15, 0)
    _update_pattern(patterns, pattern_scores, piercing, "PIERCING_LINE", 15)

    # 11. Dark Cloud Cover: prev bullish, open > prev high, close < prev body midpoint
    prev_mid_bull = prev_open + prev_body / 2
    dark_cloud = (
        prev_bullish & is_bearish &
        (open_p > prev_high) &
        (close < prev_mid_bull)
    )
    dark_cloud[:1] = False
    scores += np.where(dark_cloud, -15, 0)
    _update_pattern(patterns, pattern_scores, dark_cloud, "DARK_CLOUD_COVER", 15)

    # 12. Harami: current body entirely within prev body
    bull_harami = (
        prev_bearish & is_bullish &
        (open_p >= prev_close) & (close <= prev_open)
    )
    bear_harami = (
        prev_bullish & is_bearish &
        (open_p <= prev_close) & (close >= prev_open)
    )
    bull_harami[:1] = False
    bear_harami[:1] = False
    scores += np.where(bull_harami, 15, 0)
    scores += np.where(bear_harami, -15, 0)
    _update_pattern(patterns, pattern_scores, bull_harami, "BULLISH_HARAMI", 15)
    _update_pattern(patterns, pattern_scores, bear_harami, "BEARISH_HARAMI", 15)

    # ═══ Context Multipliers ═══

    # Volume confirmation: volume > MA20 * 1.5 → multiply by 1.2
    if volume is not None and len(volume) >= 20:
        vol_ma20 = pd.Series(volume).rolling(window=20, min_periods=1).mean().values
        vol_confirm = volume > vol_ma20 * 1.5
        scores = np.where(vol_confirm & (scores != 0), scores * 1.2, scores)

    # Reversal context: 3+ consecutive opposite trend bars → multiply by 1.3
    # For positive scores (bullish), check 3+ down bars before; for negative, 3+ up bars
    reversal_bull = (scores > 0) & (down_count >= 3)
    reversal_bear = (scores < 0) & (up_count >= 3)
    scores = np.where(reversal_bull, scores * 1.3, scores)
    scores = np.where(reversal_bear, scores * 1.3, scores)

    # Clamp to [-100, +100]
    scores = np.clip(scores, -100, 100).astype(int)

    df['candle_pattern'] = patterns
    df['candle_score'] = scores

    return df


def _update_pattern(patterns: np.ndarray, pattern_scores: np.ndarray,
                    mask: np.ndarray, label: str, abs_score: float):
    """Helper: update pattern label where this pattern is stronger than existing."""
    update_mask = mask & (abs_score > pattern_scores)
    patterns[update_mask] = label
    pattern_scores[update_mask] = abs_score
