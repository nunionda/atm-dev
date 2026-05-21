/**
 * 지수 선물 매매 전략 분석 엔진.
 * S&P 500, NASDAQ 등 지수 선물 트레이딩에 활용되는 지표를 분석한다.
 * 기존 AnalyticsData 필드(RSI, MACD, ADX, BB, SMA, ATR)를 활용.
 */

import type { AnalyticsData } from './api';
import { fmt } from './indicators';
export type { TrendBias } from './indicators';

// --- Types ---
export type VolatilityRegime = 'SQUEEZE' | 'LOW' | 'NORMAL' | 'HIGH' | 'EXTREME';
export type SetupBias = 'LONG' | 'SHORT' | 'NEUTRAL';

export interface TrendAnalysis {
    bias: TrendBias;
    label: string;
    maAlignment: string;
    adxStrength: string;
    adxValue: number | null;
    diSignal: string;
    details: string[];
}

export interface MomentumAnalysis {
    rsiZone: string;
    rsiValue: number | null;
    macdStatus: string;
    macdHistogram: string;
    macdValue: number | null;
    macdSignalValue: number | null;
    macdDiffValue: number | null;
}

export interface VolatilityAnalysis {
    regime: VolatilityRegime;
    label: string;
    bbWidth: number | null;
    bbPercentB: number | null;
    atrValue: number | null;
    atrPct: number | null;
    squeezeDetected: boolean;
}

export interface PivotLevels {
    pp: number;
    r1: number;
    r2: number;
    r3: number;
    s1: number;
    s2: number;
    s3: number;
}

export interface KeyLevels {
    pivot: PivotLevels | null;
    atrLevels: {
        plus1: number;
        plus2: number;
        minus1: number;
        minus2: number;
    } | null;
    bbLevels: {
        upper: number;
        lower: number;
        mid: number;
    } | null;
    nearestSupport: number | null;
    nearestResistance: number | null;
}

export interface FuturesSetup {
    bias: SetupBias;
    biasLabel: string;
    confidence: number; // 0-5
    signals: string[];
}

export interface FuturesAnalysis {
    trend: TrendAnalysis;
    momentum: MomentumAnalysis;
    volatility: VolatilityAnalysis;
    levels: KeyLevels;
    setup: FuturesSetup;
}

// --- Trend Analysis ---

function analyzeTrend(current: AnalyticsData, _data: AnalyticsData[]): TrendAnalysis {
    const details: string[] = [];

    // MA Alignment
    const mas = [
        { key: 'sma_5', val: current.sma_5 },
        { key: 'sma_20', val: current.sma_20 },
        { key: 'sma_60', val: current.sma_60 },
        { key: 'sma_120', val: current.sma_120 },
        { key: 'sma_200', val: current.sma_200 },
    ].filter(m => m.val != null);

    let maAlignment = '데이터 부족';
    let maBullCount = 0;

    if (mas.length >= 3) {
        let ascending = true;
        let descending = true;
        for (let i = 0; i < mas.length - 1; i++) {
            if (mas[i].val! <= mas[i + 1].val!) ascending = false;
            if (mas[i].val! >= mas[i + 1].val!) descending = false;
        }

        // Count how many short MAs are above long MAs
        if (current.sma_20 != null && current.sma_60 != null && current.sma_20 > current.sma_60) maBullCount++;
        if (current.sma_60 != null && current.sma_200 != null && current.sma_60 > current.sma_200) maBullCount++;
        if (current.close != null && current.sma_200 != null && current.close > current.sma_200) maBullCount++;

        if (ascending) {
            maAlignment = '완벽 정배열 (Perfect Bull)';
        } else if (descending) {
            maAlignment = '완벽 역배열 (Perfect Bear)';
        } else if (maBullCount >= 2) {
            maAlignment = '상승 우세 (Bullish Lean)';
        } else if (maBullCount === 0) {
            maAlignment = '하락 우세 (Bearish Lean)';
        } else {
            maAlignment = '혼조세 (Mixed)';
        }
    }

    // ADX Strength
    const adx = current.adx;
    let adxStrength = '데이터 부족';
    if (adx != null) {
        if (adx >= 40) adxStrength = '매우 강한 추세 (Very Strong)';
        else if (adx >= 25) adxStrength = '강한 추세 (Strong)';
        else if (adx >= 20) adxStrength = '약한 추세 (Weak)';
        else adxStrength = '추세 없음 (No Trend)';
    }

    // DI Signal
    const plusDi = current.plus_di;
    const minusDi = current.minus_di;
    let diSignal = '데이터 부족';
    if (plusDi != null && minusDi != null) {
        const diDiff = Math.abs(plusDi - minusDi);
        if (plusDi > minusDi && diDiff > 5) {
            diSignal = `매수 우위 (+DI ${fmt(plusDi, 1)} > -DI ${fmt(minusDi, 1)})`;
        } else if (minusDi > plusDi && diDiff > 5) {
            diSignal = `매도 우위 (-DI ${fmt(minusDi, 1)} > +DI ${fmt(plusDi, 1)})`;
        } else {
            diSignal = `균형 (+DI ${fmt(plusDi, 1)} ≈ -DI ${fmt(minusDi, 1)})`;
        }
    }

    // Price vs key MAs
    if (current.close != null && current.sma_200 != null) {
        const pctFrom200 = ((current.close - current.sma_200) / current.sma_200) * 100;
        details.push(`200MA 대비: ${pctFrom200 >= 0 ? '+' : ''}${pctFrom200.toFixed(1)}%`);
    }
    if (current.close != null && current.sma_50 != null) {
        const pctFrom50 = ((current.close - current.sma_50) / current.sma_50) * 100;
        details.push(`50MA 대비: ${pctFrom50 >= 0 ? '+' : ''}${pctFrom50.toFixed(1)}%`);
    }

    // Determine overall trend bias
    let bias: TrendBias = 'NEUTRAL';
    let label = '중립 (Neutral)';

    const bullPoints = maBullCount;
    const adxTrending = adx != null && adx >= 20;
    const bullDi = plusDi != null && minusDi != null && plusDi > minusDi;

    if (bullPoints >= 3 && adxTrending && bullDi) {
        bias = 'STRONG_BULL';
        label = '강한 상승 추세';
    } else if (bullPoints >= 2 && bullDi) {
        bias = 'BULL';
        label = '상승 추세';
    } else if (bullPoints === 0 && adxTrending && !bullDi) {
        bias = 'STRONG_BEAR';
        label = '강한 하락 추세';
    } else if (bullPoints <= 1 && !bullDi) {
        bias = 'BEAR';
        label = '하락 추세';
    }

    return { bias, label, maAlignment, adxStrength, adxValue: adx, diSignal, details };
}

// --- Momentum Analysis ---

function analyzeMomentum(current: AnalyticsData, previous: AnalyticsData | null): MomentumAnalysis {
    // RSI
    const rsi = current.rsi_14;
    let rsiZone = '데이터 부족';
    if (rsi != null) {
        if (rsi >= 70) rsiZone = '과매수 (Overbought)';
        else if (rsi >= 60) rsiZone = '강세 구간 (Bullish)';
        else if (rsi >= 40) rsiZone = '중립 구간 (Neutral)';
        else if (rsi >= 30) rsiZone = '약세 구간 (Bearish)';
        else rsiZone = '과매도 (Oversold)';
    }

    // MACD
    const macd = current.macd;
    const macdSig = current.macd_signal;
    const macdDiff = current.macd_diff;
    let macdStatus = '데이터 부족';
    let macdHistogram = '데이터 부족';

    if (macd != null && macdSig != null && macdDiff != null) {
        // Crossover detection
        const prevDiff = previous?.macd_diff;
        if (prevDiff != null && prevDiff <= 0 && macdDiff > 0) {
            macdStatus = '매수 크로스오버 (Bullish Cross)';
        } else if (prevDiff != null && prevDiff >= 0 && macdDiff < 0) {
            macdStatus = '매도 크로스오버 (Bearish Cross)';
        } else if (macd > macdSig) {
            macdStatus = '시그널선 상회 (Above Signal)';
        } else {
            macdStatus = '시그널선 하회 (Below Signal)';
        }

        // Histogram momentum
        if (macdDiff > 0 && prevDiff != null && macdDiff > prevDiff) {
            macdHistogram = '상승 가속 (Accelerating Up)';
        } else if (macdDiff > 0 && prevDiff != null && macdDiff < prevDiff) {
            macdHistogram = '상승 감속 (Decelerating Up)';
        } else if (macdDiff < 0 && prevDiff != null && macdDiff < prevDiff) {
            macdHistogram = '하락 가속 (Accelerating Down)';
        } else if (macdDiff < 0 && prevDiff != null && macdDiff > prevDiff) {
            macdHistogram = '하락 감속 (Decelerating Down)';
        } else {
            macdHistogram = macdDiff >= 0 ? '양수 (Positive)' : '음수 (Negative)';
        }
    }

    return {
        rsiZone,
        rsiValue: rsi,
        macdStatus,
        macdHistogram,
        macdValue: macd,
        macdSignalValue: macdSig,
        macdDiffValue: macdDiff,
    };
}

// --- Volatility Analysis ---

function analyzeVolatility(current: AnalyticsData): VolatilityAnalysis {
    const bbWidth = current.bb_width;
    const close = current.close;
    const atr = current.atr_14;

    // BB %B (0=lower band, 1=upper band)
    let bbPercentB: number | null = null;
    if (current.bb_hband != null && current.bb_lband != null && close != null) {
        const range = current.bb_hband - current.bb_lband;
        if (range > 0) {
            bbPercentB = (close - current.bb_lband) / range;
        }
    }

    // BB width as % of price
    let bbWidthPct: number | null = null;
    if (bbWidth != null && close != null && close > 0) {
        bbWidthPct = (bbWidth / close) * 100;
    }

    // ATR as % of price
    let atrPct: number | null = null;
    if (atr != null && close != null && close > 0) {
        atrPct = (atr / close) * 100;
    }

    // Squeeze detection
    const squeezeDetected = bbWidthPct != null && bbWidthPct < 4;

    // Volatility regime
    let regime: VolatilityRegime = 'NORMAL';
    let label = '보통 (Normal)';

    if (squeezeDetected) {
        regime = 'SQUEEZE';
        label = '스퀴즈 (Squeeze)';
    } else if (bbWidthPct != null) {
        if (bbWidthPct < 5) { regime = 'LOW'; label = '저변동 (Low)'; }
        else if (bbWidthPct < 10) { regime = 'NORMAL'; label = '보통 (Normal)'; }
        else if (bbWidthPct < 15) { regime = 'HIGH'; label = '고변동 (High)'; }
        else { regime = 'EXTREME'; label = '극단적 (Extreme)'; }
    }

    return {
        regime,
        label,
        bbWidth: bbWidthPct,
        bbPercentB,
        atrValue: atr,
        atrPct,
        squeezeDetected,
    };
}

// --- Key Levels ---

function computeKeyLevels(current: AnalyticsData, previous: AnalyticsData | null): KeyLevels {
    // Classic Pivot Points from previous day's H/L/C
    let pivot: PivotLevels | null = null;
    if (previous && previous.high != null && previous.low != null && previous.close != null) {
        const h = previous.high;
        const l = previous.low;
        const c = previous.close;
        const pp = (h + l + c) / 3;

        pivot = {
            pp,
            r1: 2 * pp - l,
            r2: pp + (h - l),
            r3: h + 2 * (pp - l),
            s1: 2 * pp - h,
            s2: pp - (h - l),
            s3: l - 2 * (h - pp),
        };
    }

    // ATR-based levels
    let atrLevels: KeyLevels['atrLevels'] = null;
    if (current.close != null && current.atr_14 != null) {
        const c = current.close;
        const atr = current.atr_14;
        atrLevels = {
            plus1: c + atr,
            plus2: c + 2 * atr,
            minus1: c - atr,
            minus2: c - 2 * atr,
        };
    }

    // BB levels
    let bbLevels: KeyLevels['bbLevels'] = null;
    if (current.bb_hband != null && current.bb_lband != null && current.bb_mavg != null) {
        bbLevels = {
            upper: current.bb_hband,
            lower: current.bb_lband,
            mid: current.bb_mavg,
        };
    }

    // Nearest support/resistance from pivot + BB
    let nearestSupport: number | null = null;
    let nearestResistance: number | null = null;

    if (current.close != null) {
        const price = current.close;
        const supports: number[] = [];
        const resistances: number[] = [];

        if (pivot) {
            [pivot.s1, pivot.s2, pivot.s3].forEach(s => { if (s < price) supports.push(s); });
            [pivot.r1, pivot.r2, pivot.r3].forEach(r => { if (r > price) resistances.push(r); });
            if (pivot.pp < price) supports.push(pivot.pp);
            else if (pivot.pp > price) resistances.push(pivot.pp);
        }
        if (bbLevels) {
            if (bbLevels.lower < price) supports.push(bbLevels.lower);
            if (bbLevels.upper > price) resistances.push(bbLevels.upper);
        }

        if (supports.length > 0) nearestSupport = Math.max(...supports);
        if (resistances.length > 0) nearestResistance = Math.min(...resistances);
    }

    return { pivot, atrLevels, bbLevels, nearestSupport, nearestResistance };
}

// --- Trade Setup ---

function evaluateSetup(
    trend: TrendAnalysis,
    momentum: MomentumAnalysis,
    volatility: VolatilityAnalysis,
): FuturesSetup {
    let longPoints = 0;
    let shortPoints = 0;
    const signals: string[] = [];

    // Trend contribution
    if (trend.bias === 'STRONG_BULL') { longPoints += 2; signals.push('강한 상승 추세'); }
    else if (trend.bias === 'BULL') { longPoints += 1; signals.push('상승 추세'); }
    else if (trend.bias === 'STRONG_BEAR') { shortPoints += 2; signals.push('강한 하락 추세'); }
    else if (trend.bias === 'BEAR') { shortPoints += 1; signals.push('하락 추세'); }

    // RSI contribution
    if (momentum.rsiValue != null) {
        if (momentum.rsiValue <= 30) { longPoints += 1; signals.push('RSI 과매도 반등 가능'); }
        else if (momentum.rsiValue >= 70) { shortPoints += 1; signals.push('RSI 과매수 조정 가능'); }
        else if (momentum.rsiValue >= 50 && momentum.rsiValue < 60) { longPoints += 0.5; }
        else if (momentum.rsiValue > 40 && momentum.rsiValue < 50) { shortPoints += 0.5; }
    }

    // MACD contribution
    if (momentum.macdDiffValue != null) {
        if (momentum.macdStatus.includes('매수 크로스오버')) { longPoints += 1; signals.push('MACD 매수 전환'); }
        else if (momentum.macdStatus.includes('매도 크로스오버')) { shortPoints += 1; signals.push('MACD 매도 전환'); }
        else if (momentum.macdHistogram.includes('상승 가속')) { longPoints += 0.5; }
        else if (momentum.macdHistogram.includes('하락 가속')) { shortPoints += 0.5; }
    }

    // Volatility contribution
    if (volatility.squeezeDetected) {
        signals.push('BB 스퀴즈 → 돌파 임박');
    }
    if (volatility.bbPercentB != null) {
        if (volatility.bbPercentB <= 0.05) { longPoints += 0.5; signals.push('BB 하단 접촉 → 반등 가능'); }
        else if (volatility.bbPercentB >= 0.95) { shortPoints += 0.5; signals.push('BB 상단 접촉 → 조정 가능'); }
    }

    // Determine bias
    const netPoints = longPoints - shortPoints;
    const totalPoints = longPoints + shortPoints;
    let bias: SetupBias;
    let biasLabel: string;

    if (netPoints >= 1.5) { bias = 'LONG'; biasLabel = '롱 (매수) 유리'; }
    else if (netPoints <= -1.5) { bias = 'SHORT'; biasLabel = '숏 (매도) 유리'; }
    else { bias = 'NEUTRAL'; biasLabel = '중립 (관망)'; }

    // Confidence: 0~5 based on how many signals agree
    const confidence = Math.min(5, Math.round(Math.abs(netPoints) + (totalPoints > 3 ? 1 : 0)));

    if (signals.length === 0) signals.push('뚜렷한 시그널 없음');

    return { bias, biasLabel, confidence, signals };
}

// --- ATR Entry Calculator (based on ATR strategy document) ---

export interface ATREntryCalc {
    // 현재 시장 상태
    currentPrice: number;
    prevClose: number;
    atr: number;
    atrPct: number;

    // 1) ATR 브레이크아웃 필터: (현재 고가 - 전일 종가) > 0.5 * ATR
    breakoutValid: boolean;
    breakoutDelta: number;
    breakoutThreshold: number;

    // 2) 추세 추종 진입가
    trendLongEntry: number;    // prevClose + 1.5 * ATR
    trendLongStrong: number;   // prevClose + 2.0 * ATR
    trendShortEntry: number;   // prevClose - 1.5 * ATR
    trendShortStrong: number;  // prevClose - 2.0 * ATR

    // 3) ATR 밴드 (볼린저 유사 채널)
    upperBand: number;         // close + 2 * ATR
    lowerBand: number;         // close - 2 * ATR

    // 4) 트레일링 스톱
    longStop: number;          // currentPrice - 1.5 * ATR
    longStopWide: number;      // currentPrice - 2.0 * ATR
    shortStop: number;         // currentPrice + 1.5 * ATR
    shortStopWide: number;     // currentPrice + 2.0 * ATR

    // 5) 샹들리에 청산
    chandelierLongExit: number;   // highest - 3 * ATR
    chandelierShortExit: number;  // lowest + 3 * ATR
    chandelierHighest: number;
    chandelierLowest: number;

    // 6) 동적 ATR 배수 (ADX 기반)
    dynamicMultiplier: number;       // adx < 20 ? 2.0 : 1.5
    adxValue: number | null;
    dynamicLongStop: number;         // close - dynamicMultiplier * ATR
    dynamicShortStop: number;        // close + dynamicMultiplier * ATR

    // 7) 거래량 가중 ATR (Integrated ATR)
    volumeRoc: number | null;
    integratedATR: number | null;
    integratedBreakoutValid: boolean | null;

    // 8) 피라미딩 간격
    pyramidLong: number[];           // 4단계 long 진입 레벨
    pyramidShort: number[];          // 4단계 short 진입 레벨

    // 종합 판단
    direction: 'LONG' | 'SHORT' | 'WAIT';
    reasons: string[];
}

export function computeATREntry(data: AnalyticsData[], lookback: number = 22): ATREntryCalc | null {
    if (data.length < 3) return null;

    const current = data[data.length - 1];
    const prev = data[data.length - 2];

    const close = current.close;
    const high = current.high;
    const atr = current.atr_14;
    const prevClose = prev.close;

    if (close == null || high == null || atr == null || atr === 0 || prevClose == null) return null;

    const atrPct = (atr / close) * 100;

    // 1) ATR 브레이크아웃 필터
    const breakoutDelta = high - prevClose;
    const breakoutThreshold = 0.5 * atr;
    const breakoutValid = breakoutDelta > breakoutThreshold;

    // 2) 추세 추종 진입가
    const trendLongEntry = prevClose + 1.5 * atr;
    const trendLongStrong = prevClose + 2.0 * atr;
    const trendShortEntry = prevClose - 1.5 * atr;
    const trendShortStrong = prevClose - 2.0 * atr;

    // 3) ATR 밴드
    const upperBand = close + 2 * atr;
    const lowerBand = close - 2 * atr;

    // 4) 트레일링 스톱 (현재가 기준)
    const longStop = close - 1.5 * atr;
    const longStopWide = close - 2.0 * atr;
    const shortStop = close + 1.5 * atr;
    const shortStopWide = close + 2.0 * atr;

    // 5) 샹들리에 청산: lookback 기간 최고/최저
    const lb = Math.min(lookback, data.length);
    const recentSlice = data.slice(-lb);
    let chandelierHighest = -Infinity;
    let chandelierLowest = Infinity;
    for (const d of recentSlice) {
        if (d.high != null && d.high > chandelierHighest) chandelierHighest = d.high;
        if (d.low != null && d.low < chandelierLowest) chandelierLowest = d.low;
    }
    const chandelierLongExit = chandelierHighest - 3 * atr;
    const chandelierShortExit = chandelierLowest + 3 * atr;

    // 6) 동적 ATR 배수 (ADX 기반)
    const adxValue = current.adx;
    const dynamicMultiplier = (adxValue != null && adxValue < 20) ? 2.0 : 1.5;
    const dynamicLongStop = close - dynamicMultiplier * atr;
    const dynamicShortStop = close + dynamicMultiplier * atr;

    // 7) 거래량 가중 ATR (Integrated ATR)
    let volumeRoc: number | null = null;
    let integratedATR: number | null = null;
    let integratedBreakoutValid: boolean | null = null;

    if (data.length >= 10) {
        const recent5 = data.slice(-5);
        const prev5 = data.slice(-10, -5);
        const avgRecent = recent5.reduce((s, d) => s + (d.volume || 0), 0) / 5;
        const avgPrev = prev5.reduce((s, d) => s + (d.volume || 0), 0) / 5;
        if (avgPrev > 0) {
            volumeRoc = (avgRecent - avgPrev) / avgPrev;
            integratedATR = atr * 0.7 + (volumeRoc * atr) * 0.3;
            integratedBreakoutValid = breakoutDelta > 0.5 * integratedATR;
        }
    }

    // 8) 피라미딩 간격 (0.5 * ATR 단위 4단계)
    const pyramidLong = [0, 1, 2, 3].map(i => trendLongEntry + i * 0.5 * atr);
    const pyramidShort = [0, 1, 2, 3].map(i => trendShortEntry - i * 0.5 * atr);

    // 종합 방향 판단
    const reasons: string[] = [];
    let longScore = 0;
    let shortScore = 0;

    // MA 정렬 확인
    const aboveMa = current.sma_20 != null && current.sma_60 != null && close > current.sma_20 && current.sma_20 > current.sma_60;
    const belowMa = current.sma_20 != null && current.sma_60 != null && close < current.sma_20 && current.sma_20 < current.sma_60;

    if (aboveMa) { longScore++; reasons.push('MA 정배열 (가격 > 20MA > 60MA)'); }
    if (belowMa) { shortScore++; reasons.push('MA 역배열 (가격 < 20MA < 60MA)'); }

    // 브레이크아웃 유효 + 방향
    if (breakoutValid && close > prevClose) { longScore++; reasons.push('ATR 상방 브레이크아웃 유효'); }
    if (breakoutValid && close < prevClose) { shortScore++; reasons.push('ATR 하방 브레이크아웃 유효'); }

    // 추세 추종 조건 충족
    if (close >= trendLongEntry) { longScore++; reasons.push(`종가가 추세추종 Long 진입가 상회 (${fmt(trendLongEntry)})`); }
    if (close <= trendShortEntry) { shortScore++; reasons.push(`종가가 추세추종 Short 진입가 하회 (${fmt(trendShortEntry)})`); }

    // ADX 추세 강도
    if (current.adx != null && current.adx >= 25) {
        reasons.push(`ADX ${fmt(current.adx, 1)} — 추세 유효`);
    }

    // 동적 배수 정보
    if (adxValue != null) {
        reasons.push(`동적 배수 ${dynamicMultiplier}x (ADX ${adxValue < 20 ? '<20 횡보' : '≥20 추세'})`);
    }

    // 통합 ATR 돌파 확인
    if (integratedATR != null && integratedATR > atr * 1.2 && close > prevClose) {
        longScore++;
        reasons.push('거래량 가중 ATR 상승 → 돌파 신뢰도 높음');
    } else if (integratedATR != null && integratedATR > atr * 1.2 && close < prevClose) {
        shortScore++;
        reasons.push('거래량 가중 ATR 상승 → 하방 돌파 신뢰도 높음');
    }

    let direction: 'LONG' | 'SHORT' | 'WAIT';
    if (longScore >= 2) { direction = 'LONG'; }
    else if (shortScore >= 2) { direction = 'SHORT'; }
    else { direction = 'WAIT'; reasons.push('조건 미충족 — 관망'); }

    return {
        currentPrice: close,
        prevClose,
        atr,
        atrPct,
        breakoutValid,
        breakoutDelta,
        breakoutThreshold,
        trendLongEntry,
        trendLongStrong,
        trendShortEntry,
        trendShortStrong,
        upperBand,
        lowerBand,
        longStop,
        longStopWide,
        shortStop,
        shortStopWide,
        chandelierLongExit,
        chandelierShortExit,
        chandelierHighest,
        chandelierLowest,
        dynamicMultiplier,
        adxValue,
        dynamicLongStop,
        dynamicShortStop,
        volumeRoc,
        integratedATR,
        integratedBreakoutValid,
        pyramidLong,
        pyramidShort,
        direction,
        reasons,
    };
}

// --- Main Export ---

export function analyzeFutures(data: AnalyticsData[]): FuturesAnalysis | null {
    if (data.length < 2) return null;

    const current = data[data.length - 1];
    const previous = data[data.length - 2];

    const trend = analyzeTrend(current, data);
    const momentum = analyzeMomentum(current, previous);
    const volatility = analyzeVolatility(current);
    const levels = computeKeyLevels(current, previous);
    const setup = evaluateSetup(trend, momentum, volatility);

    return { trend, momentum, volatility, levels, setup };
}
