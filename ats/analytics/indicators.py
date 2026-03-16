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


def calculate_fibonacci_levels(df: pd.DataFrame, swing_length: int = 3) -> pd.DataFrame:
    """
    P3: Fibonacci retracement/extension levels based on recent swing high/low.
    Reuses is_swing_high/is_swing_low from calculate_smc() if available.

    Output columns: fib_236, fib_382, fib_500, fib_618, fib_786,
                    fib_ext_1272, fib_ext_1618, fib_trend ("UP"/"DOWN")
    """
    df = df.copy()

    # Compute swing points if not already present
    if 'is_swing_high' not in df.columns or 'is_swing_low' not in df.columns:
        highs = df['high'].values
        lows = df['low'].values
        length = len(df)
        df['is_swing_high'] = False
        df['is_swing_low'] = False
        for i in range(swing_length, length - swing_length):
            is_sh = True
            is_sl = True
            for j in range(1, swing_length + 1):
                if highs[i] <= highs[i - j] or highs[i] <= highs[i + j]:
                    is_sh = False
                if lows[i] >= lows[i - j] or lows[i] >= lows[i + j]:
                    is_sl = False
            if is_sh:
                df.at[df.index[i], 'is_swing_high'] = True
            if is_sl:
                df.at[df.index[i], 'is_swing_low'] = True

    # Initialize output columns
    fib_cols = ['fib_236', 'fib_382', 'fib_500', 'fib_618', 'fib_786',
                'fib_ext_1272', 'fib_ext_1618']
    for col in fib_cols:
        df[col] = None
    df['fib_trend'] = None

    # Find most recent confirmed swing high and swing low
    sh_mask = df['is_swing_high'] == True  # noqa: E712
    sl_mask = df['is_swing_low'] == True   # noqa: E712

    sh_indices = df.index[sh_mask]
    sl_indices = df.index[sl_mask]

    if len(sh_indices) == 0 or len(sl_indices) == 0:
        return df

    last_sh_idx = sh_indices[-1]
    last_sl_idx = sl_indices[-1]
    last_sh_pos = df.index.get_loc(last_sh_idx)
    last_sl_pos = df.index.get_loc(last_sl_idx)

    swing_high = float(df.loc[last_sh_idx, 'high'])
    swing_low = float(df.loc[last_sl_idx, 'low'])
    swing_range = swing_high - swing_low

    if swing_range <= 0:
        return df

    # Determine trend: if swing low is more recent → uptrend (retracing from high)
    # if swing high is more recent → downtrend (bouncing from low)
    ratios_ret = [0.236, 0.382, 0.5, 0.618, 0.786]
    ratios_ext = [1.272, 1.618]

    if last_sl_pos > last_sh_pos:
        # Downtrend: swing high then swing low, price bouncing from low
        trend = "DOWN"
        fib_ret = [swing_low + swing_range * r for r in ratios_ret]
        fib_ext = [swing_low - swing_range * (r - 1.0) for r in ratios_ext]
    else:
        # Uptrend: swing low then swing high, price retracing from high
        trend = "UP"
        fib_ret = [swing_high - swing_range * r for r in ratios_ret]
        fib_ext = [swing_high + swing_range * (r - 1.0) for r in ratios_ext]

    # Set fib levels as constant across all rows (current levels)
    df['fib_236'] = fib_ret[0]
    df['fib_382'] = fib_ret[1]
    df['fib_500'] = fib_ret[2]
    df['fib_618'] = fib_ret[3]
    df['fib_786'] = fib_ret[4]
    df['fib_ext_1272'] = fib_ext[0]
    df['fib_ext_1618'] = fib_ext[1]
    df['fib_trend'] = trend

    return df


def _detect_triangle(high: np.ndarray, low: np.ndarray, close: np.ndarray,
                     atr: float, i: int, lookback: int = 30) -> tuple:
    """
    B8: Triangle pattern detector (Symmetric/Ascending/Descending).
    Uses linear regression slopes on recent highs/lows.
    Returns (pattern_name, score, None) or (None, 0, None).
    """
    if i < lookback:
        return None, 0, None

    w_high = high[i - lookback: i].astype(float)
    w_low  = low[i - lookback: i].astype(float)
    x = np.arange(lookback, dtype=float)

    if atr <= 0:
        return None, 0, None

    # Linear regression slopes (ATR-normalized)
    upper_slope = float(np.polyfit(x, w_high, 1)[0]) / atr
    lower_slope = float(np.polyfit(x, w_low,  1)[0]) / atr

    threshold = 0.015  # ATR-normalized slope threshold

    if upper_slope < -threshold and lower_slope > threshold:
        return "SYMMETRIC_TRIANGLE", 55, None   # converging — neutral breakout pending
    elif abs(upper_slope) <= threshold and lower_slope > threshold:
        return "ASCENDING_TRIANGLE", 60, None   # bullish (flat top, rising support)
    elif upper_slope < -threshold and abs(lower_slope) <= threshold:
        return "DESCENDING_TRIANGLE", -50, None # bearish (declining top, flat support)

    return None, 0, None


def _detect_cup_and_handle(close: np.ndarray, high: np.ndarray, low: np.ndarray,
                            volume, i: int, lookback: int = 60) -> tuple:
    """
    B7: Cup & Handle pattern detector for a single bar index i.
    Cup depth: 15-35% below left rim. Handle retracement < 50% of cup.
    Returns (pattern_name, score, price_target) or (None, 0, None).
    """
    if i < lookback:
        return None, 0, None

    window_high = high[i - lookback: i]
    window_low  = low[i - lookback: i]

    left_rim_rel = int(np.argmax(window_high))
    left_rim = float(window_high[left_rim_rel])

    cup_bottom_rel = int(np.argmin(window_low[left_rim_rel:]))
    cup_bottom = float(window_low[left_rim_rel + cup_bottom_rel])

    if left_rim <= 0:
        return None, 0, None

    cup_depth_pct = (left_rim - cup_bottom) / left_rim
    if not (0.15 <= cup_depth_pct <= 0.40):
        return None, 0, None

    # Handle: last 5-25 bars should show smaller range than cup
    handle_len = min(25, i)
    handle_high = np.max(high[i - handle_len: i])
    handle_low  = np.min(low[i - handle_len: i])
    cup_range = left_rim - cup_bottom
    handle_range = handle_high - handle_low
    if cup_range <= 0 or handle_range > 0.5 * cup_range:
        return None, 0, None

    # Breakout: current close near or above left rim (within 3%)
    if close[i] < left_rim * 0.97:
        return None, 0, None

    # Volume: handle should have lower volume than cup (optional check)
    vol_ok = True
    if volume is not None:
        cup_vol_mean = np.mean(volume[i - lookback: i - handle_len]) if (i - lookback) < (i - handle_len) else 1.0
        handle_vol_mean = np.mean(volume[i - handle_len: i]) if handle_len > 0 else 1.0
        vol_ok = handle_vol_mean < cup_vol_mean

    score = 70 if vol_ok else 55
    target = close[i] + cup_range  # price target = cup depth above breakout
    return "CUP_AND_HANDLE", score, target


def detect_chart_patterns(df: pd.DataFrame, swing_length: int = 3) -> pd.DataFrame:
    """
    P3: Classic chart pattern detection using swing points.
    Detects: Double Bottom (+70), Double Top (-70), Bull Flag (+60), Bear Flag (-60).

    Output columns: chart_pattern (str|None), chart_pattern_score (int -100..+100),
                    chart_pattern_target (float|None)
    """
    df = df.copy()
    n = len(df)

    df['chart_pattern'] = None
    df['chart_pattern_score'] = 0
    df['chart_pattern_target'] = None

    if n < 15:
        return df

    close = df['close'].values.astype(float)
    high = df['high'].values.astype(float)
    low = df['low'].values.astype(float)
    open_p = df['open'].values.astype(float)
    volume = df['volume'].values.astype(float) if 'volume' in df.columns else None

    # Compute swing points if missing
    if 'is_swing_high' not in df.columns or 'is_swing_low' not in df.columns:
        df['is_swing_high'] = False
        df['is_swing_low'] = False
        for i in range(swing_length, n - swing_length):
            is_sh = True
            is_sl = True
            for j in range(1, swing_length + 1):
                if high[i] <= high[i - j] or high[i] <= high[i + j]:
                    is_sh = False
                if low[i] >= low[i - j] or low[i] >= low[i + j]:
                    is_sl = False
            if is_sh:
                df.iat[i, df.columns.get_loc('is_swing_high')] = True
            if is_sl:
                df.iat[i, df.columns.get_loc('is_swing_low')] = True

    # Collect swing indices
    sh_positions = [i for i in range(n) if df['is_swing_high'].iloc[i]]
    sl_positions = [i for i in range(n) if df['is_swing_low'].iloc[i]]

    # ATR for flag detection
    atr_arr = np.zeros(n)
    if n >= 14:
        tr = np.maximum(high[1:] - low[1:],
                        np.maximum(np.abs(high[1:] - close[:-1]),
                                   np.abs(low[1:] - close[:-1])))
        tr = np.concatenate([[high[0] - low[0]], tr])
        atr_series = pd.Series(tr).rolling(window=14, min_periods=1).mean().values
        atr_arr = atr_series

    # Scan each bar for patterns (check most recent occurrences)
    for i in range(20, n):
        best_pattern = None
        best_score = 0
        best_target = None

        # ── Double Bottom ──
        # Find two swing lows before bar i, separated by 10-50 bars, within 3%
        recent_sl = [pos for pos in sl_positions if pos < i and pos >= i - 60]
        if len(recent_sl) >= 2:
            for k in range(len(recent_sl) - 1, 0, -1):
                sl2 = recent_sl[k]
                for m in range(k - 1, -1, -1):
                    sl1 = recent_sl[m]
                    sep = sl2 - sl1
                    if 10 <= sep <= 50:
                        low1 = low[sl1]
                        low2 = low[sl2]
                        if low1 > 0 and abs(low1 - low2) / low1 < 0.03:
                            neckline = np.max(high[sl1:sl2 + 1])
                            bottom = min(low1, low2)
                            if close[i] > neckline:
                                target = neckline + (neckline - bottom)
                                if abs(70) > abs(best_score):
                                    best_pattern = "DOUBLE_BOTTOM"
                                    best_score = 70
                                    best_target = target
                    if best_pattern:
                        break
                if best_pattern:
                    break

        # ── Double Top ──
        recent_sh = [pos for pos in sh_positions if pos < i and pos >= i - 60]
        if len(recent_sh) >= 2 and best_pattern is None:
            for k in range(len(recent_sh) - 1, 0, -1):
                sh2 = recent_sh[k]
                for m in range(k - 1, -1, -1):
                    sh1 = recent_sh[m]
                    sep = sh2 - sh1
                    if 10 <= sep <= 50:
                        high1 = high[sh1]
                        high2 = high[sh2]
                        if high1 > 0 and abs(high1 - high2) / high1 < 0.03:
                            neckline = np.min(low[sh1:sh2 + 1])
                            top = max(high1, high2)
                            if close[i] < neckline:
                                target = neckline - (top - neckline)
                                if abs(-70) > abs(best_score):
                                    best_pattern = "DOUBLE_TOP"
                                    best_score = -70
                                    best_target = target
                    if best_pattern:
                        break
                if best_pattern:
                    break

        # ── Bull Flag ──
        if i >= 20 and best_pattern is None:
            atr = atr_arr[i] if atr_arr[i] > 0 else 1.0
            # Impulse: check bars i-20 to i-15 for strong up move
            impulse_start = max(0, i - 20)
            impulse_end = max(0, i - 15)
            if impulse_end < n and impulse_start < n:
                impulse_move = close[impulse_end] - close[impulse_start]
                if impulse_move > 2 * atr:
                    # Consolidation: last 10 bars (i-10 to i)
                    consol_start = max(0, i - 10)
                    consol_range = np.max(high[consol_start:i + 1]) - np.min(low[consol_start:i + 1])
                    if consol_range < 0.5 * abs(impulse_move):
                        vol_ok = True
                        if volume is not None:
                            vol_start_mean = np.mean(volume[max(0, i - 15):max(1, i - 10)])
                            vol_end_mean = np.mean(volume[max(0, i - 5):i + 1])
                            vol_ok = vol_end_mean < vol_start_mean
                        if vol_ok:
                            target = close[i] + impulse_move
                            best_pattern = "BULL_FLAG"
                            best_score = 60
                            best_target = target

        # ── Bear Flag ──
        if i >= 20 and best_pattern is None:
            atr = atr_arr[i] if atr_arr[i] > 0 else 1.0
            impulse_start = max(0, i - 20)
            impulse_end = max(0, i - 15)
            if impulse_end < n and impulse_start < n:
                impulse_move = close[impulse_start] - close[impulse_end]  # down move
                if impulse_move > 2 * atr:
                    consol_start = max(0, i - 10)
                    consol_range = np.max(high[consol_start:i + 1]) - np.min(low[consol_start:i + 1])
                    if consol_range < 0.5 * abs(impulse_move):
                        vol_ok = True
                        if volume is not None:
                            vol_start_mean = np.mean(volume[max(0, i - 15):max(1, i - 10)])
                            vol_end_mean = np.mean(volume[max(0, i - 5):i + 1])
                            vol_ok = vol_end_mean < vol_start_mean
                        if vol_ok:
                            target = close[i] - impulse_move
                            best_pattern = "BEAR_FLAG"
                            best_score = -60
                            best_target = target

        # B7: Cup & Handle
        ch_name, ch_score, ch_target = _detect_cup_and_handle(close, high, low, volume, i)
        if abs(ch_score) > abs(best_score):
            best_pattern = ch_name
            best_score = ch_score
            best_target = ch_target

        # B8: Triangle
        atr = atr_arr[i] if i < len(atr_arr) else 0.0
        tri_name, tri_score, tri_target = _detect_triangle(high, low, close, atr, i)
        if tri_name and abs(tri_score) > abs(best_score):
            best_pattern = tri_name
            best_score = tri_score
            best_target = tri_target

        if best_pattern:
            df.iat[i, df.columns.get_loc('chart_pattern')] = best_pattern
            df.iat[i, df.columns.get_loc('chart_pattern_score')] = best_score
            df.iat[i, df.columns.get_loc('chart_pattern_target')] = best_target

    return df


# ============================================================
# B1-B5: Additional Technical Indicators
# ============================================================

def calculate_connors_rsi(df: pd.DataFrame, rsi_period: int = 3, streak_period: int = 2, rank_period: int = 100) -> pd.DataFrame:
    """
    B1: Connors RSI — composite momentum/reversion indicator.
    Components:
      1. RSI(3) — fast price RSI
      2. Streak RSI(2) — RSI of consecutive up/down day count
      3. PercentRank(100) — percentile rank of today's 1-day return in last 100 bars
    Output columns: crsi (float 0-100), crsi_oversold (bool: crsi < 15), crsi_overbought (bool: crsi > 80)
    """
    df = df.copy()
    close = df['close'].astype(float)

    # Component 1: Fast RSI(3)
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(com=rsi_period - 1, min_periods=rsi_period).mean()
    avg_loss = loss.ewm(com=rsi_period - 1, min_periods=rsi_period).mean()
    rs1 = avg_gain / avg_loss.replace(0, np.finfo(float).eps)
    rsi3 = 100 - (100 / (1 + rs1))

    # Component 2: Streak RSI
    # Count consecutive up (+) or down (-) days
    direction = np.sign(close.diff()).fillna(0)
    streak = pd.Series(0.0, index=df.index)
    current_streak = 0.0
    for idx in range(len(direction)):
        d = direction.iloc[idx]
        if d > 0:
            current_streak = max(0, current_streak) + 1
        elif d < 0:
            current_streak = min(0, current_streak) - 1
        else:
            current_streak = 0.0
        streak.iloc[idx] = current_streak

    # Apply RSI(2) to streak values
    s_delta = streak.diff()
    s_gain = s_delta.clip(lower=0)
    s_loss = (-s_delta).clip(lower=0)
    s_avg_gain = s_gain.ewm(com=streak_period - 1, min_periods=streak_period).mean()
    s_avg_loss = s_loss.ewm(com=streak_period - 1, min_periods=streak_period).mean()
    rs2 = s_avg_gain / s_avg_loss.replace(0, np.finfo(float).eps)
    streak_rsi = 100 - (100 / (1 + rs2))

    # Component 3: PercentRank(100) — where today's return ranks vs last 100
    daily_ret = close.pct_change()
    percent_rank = daily_ret.rolling(rank_period).apply(
        lambda x: float((x[:-1] < x[-1]).sum()) / max(len(x) - 1, 1) * 100,
        raw=True
    )

    # Composite: average of 3 components
    crsi = (rsi3 + streak_rsi + percent_rank) / 3.0
    crsi = crsi.clip(0, 100)

    df['crsi'] = crsi
    df['crsi_oversold'] = crsi < 15
    df['crsi_overbought'] = crsi > 80
    return df


def calculate_williams_r(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """
    B2: Williams %R — momentum/mean-reversion oscillator.
    Range: -100 to 0. Oversold < -80, Overbought > -20.
    Output columns: williams_r (float), williams_r_oversold (bool: wr < -80)
    """
    df = df.copy()
    highest_high = df['high'].rolling(period).max()
    lowest_low = df['low'].rolling(period).min()
    denom = (highest_high - lowest_low).replace(0, np.finfo(float).eps)
    df['williams_r'] = (highest_high - df['close']) / denom * -100
    df['williams_r_oversold'] = df['williams_r'] < -80
    return df


def calculate_mfi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """
    B3: Money Flow Index (MFI) — volume-weighted RSI.
    Oversold < 20, Overbought > 80.
    Also detects bearish divergence: price at 20-bar high but MFI declining.
    Output columns: mfi (float 0-100), mfi_bear_div (int 0/1)
    """
    df = df.copy()
    tp = (df['high'] + df['low'] + df['close']) / 3.0
    raw_mf = tp * df['volume']

    # Positive / Negative money flow
    pos_mf = raw_mf.where(tp > tp.shift(1), 0.0)
    neg_mf = raw_mf.where(tp < tp.shift(1), 0.0)

    pos_sum = pos_mf.rolling(period).sum()
    neg_sum = neg_mf.rolling(period).sum().replace(0, np.finfo(float).eps)

    mfr = pos_sum / neg_sum
    df['mfi'] = 100 - (100 / (1 + mfr))
    df['mfi'] = df['mfi'].clip(0, 100)

    # Bearish divergence: price at new 20-bar high but MFI trending down
    price_new_high = df['close'] > df['close'].rolling(20).max().shift(1)
    mfi_declining = df['mfi'] < df['mfi'].shift(5)
    df['mfi_bear_div'] = (price_new_high & mfi_declining).astype(int)

    return df


def calculate_zscore(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    """
    B4: Rolling Z-score normalization of price.
    Z < -2.0 = statistically oversold (MR entry signal)
    Z > +2.0 = statistically overbought (MR exit / short signal)
    Output columns: zscore (float)
    """
    df = df.copy()
    roll_mean = df['close'].rolling(period).mean()
    roll_std = df['close'].rolling(period).std().replace(0, np.finfo(float).eps)
    df['zscore'] = (df['close'] - roll_mean) / roll_std
    return df


def calculate_cmf(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    """
    B5: Chaikin Money Flow — institutional accumulation/distribution.
    CMF > 0.05 = bullish (buying pressure), < -0.05 = bearish.
    Output columns: cmf (float -1 to +1)
    """
    df = df.copy()
    hl_range = (df['high'] - df['low']).replace(0, np.finfo(float).eps)
    mfm = ((df['close'] - df['low']) - (df['high'] - df['close'])) / hl_range
    mfm = mfm.fillna(0.0)
    vol_sum = df['volume'].rolling(period).sum().replace(0, np.finfo(float).eps)
    df['cmf'] = (mfm * df['volume']).rolling(period).sum() / vol_sum
    df['cmf'] = df['cmf'].clip(-1, 1)
    return df
