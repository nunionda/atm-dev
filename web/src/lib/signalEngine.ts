/**
 * 모멘텀 스윙 전략 시그널 분석 엔진.
 * momentum_swing.py의 진입/청산 로직을 프론트엔드에서 복제한다.
 * 순수 함수 — React 의존성 없음.
 */

import type { AnalyticsData } from './api';
import { fmt } from './indicators';
export type { TrendBias } from './indicators';
import type { TrendBias } from './indicators';

// --- Types ---

export interface SignalCheck {
    id: string;
    label: string;
    passed: boolean;
    detail: string;
}

export type Verdict = 'BUY_SUITABLE' | 'WATCH' | 'NOT_SUITABLE';

export interface EntryAnalysis {
    primarySignals: SignalCheck[];
    confirmations: SignalCheck[];
    riskGates: SignalCheck[];
    strength: number;
    verdict: Verdict;
    verdictLabel: string;
}

export interface ExitLevels {
    stopLoss: number;
    takeProfit: number;
    deadCrossActive: boolean;
    deadCrossDetail: string;
    maxHoldingDays: number;
}
export type SMCBias = 'BULLISH' | 'BEARISH' | 'NEUTRAL';

export interface TrendFilter {
    maAlignment: string;
    adxStrength: string;
    adxValue: number | null;
    diSignal: string;
    pctFrom200: number | null;
    pctFrom50: number | null;
    bias: TrendBias;
    biasLabel: string;
}

export interface SMCMarkerInfo {
    type: string;
    barsAgo: number;
    date: string;
}

export interface OrderBlockInfo {
    top: number;
    bottom: number;
    relation: string;
    barsAgo: number;
}

export interface FVGInfo {
    type: string;
    top: number;
    bottom: number;
    relation: string;
    barsAgo: number;
}

export interface SMCAnalysis {
    markers: SMCMarkerInfo[];
    orderBlocks: OrderBlockInfo[];
    fvgs: FVGInfo[];
    smcBias: SMCBias;
    smcLabel: string;
}

export interface DynamicExitLevels extends ExitLevels {
    atrStopLoss: number | null;
    effectiveStopLoss: number;
    atrTakeProfit: number | null;
    effectiveTakeProfit: number;
    trailingStop: number | null;
    chandelierExit: number | null;
    dynamicMultiplier: number | null;
    atrValue: number | null;
}

export interface EnhancedEntryAnalysis extends EntryAnalysis {
    trendFilter: TrendFilter | null;
    smcAnalysis: SMCAnalysis | null;
    confidenceScore: number;
    confidenceLabel: string;
}

// --- Helpers ---

function fmtVol(v: number): string {
    if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
    if (v >= 1_000) return `${(v / 1_000).toFixed(0)}K`;
    return v.toLocaleString();
}

// --- Core Analysis ---

export function computeVolumeMA(data: AnalyticsData[], period = 20): number {
    if (data.length < period) return 0;
    const recent = data.slice(-period);
    const sum = recent.reduce((acc, d) => acc + (d.volume || 0), 0);
    return sum / period;
}

// --- Trend Filter ---

export function analyzeTrendFilter(current: AnalyticsData): TrendFilter {
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

        if (current.sma_20 != null && current.sma_60 != null && current.sma_20 > current.sma_60) maBullCount++;
        if (current.sma_60 != null && current.sma_200 != null && current.sma_60 > current.sma_200) maBullCount++;
        if (current.close != null && current.sma_200 != null && current.close > current.sma_200) maBullCount++;

        if (ascending) maAlignment = '완벽 정배열 (Perfect Bull)';
        else if (descending) maAlignment = '완벽 역배열 (Perfect Bear)';
        else if (maBullCount >= 2) maAlignment = '상승 우세 (Bullish Lean)';
        else if (maBullCount === 0) maAlignment = '하락 우세 (Bearish Lean)';
        else maAlignment = '혼조세 (Mixed)';
    }

    const adx = current.adx;
    let adxStrength = '데이터 부족';
    if (adx != null) {
        if (adx >= 40) adxStrength = '매우 강한 추세 (Very Strong)';
        else if (adx >= 25) adxStrength = '강한 추세 (Strong)';
        else if (adx >= 20) adxStrength = '약한 추세 (Weak)';
        else adxStrength = '추세 없음 (No Trend)';
    }

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

    let pctFrom200: number | null = null;
    let pctFrom50: number | null = null;
    if (current.close != null && current.sma_200 != null) {
        pctFrom200 = ((current.close - current.sma_200) / current.sma_200) * 100;
    }
    if (current.close != null && current.sma_50 != null) {
        pctFrom50 = ((current.close - current.sma_50) / current.sma_50) * 100;
    }

    let bias: TrendBias = 'NEUTRAL';
    let biasLabel = '중립 (Neutral)';
    const adxTrending = adx != null && adx >= 20;
    const bullDi = plusDi != null && minusDi != null && plusDi > minusDi;

    if (maBullCount >= 3 && adxTrending && bullDi) {
        bias = 'STRONG_BULL'; biasLabel = '강한 상승 추세';
    } else if (maBullCount >= 2 && bullDi) {
        bias = 'BULL'; biasLabel = '상승 추세';
    } else if (maBullCount === 0 && adxTrending && !bullDi) {
        bias = 'STRONG_BEAR'; biasLabel = '강한 하락 추세';
    } else if (maBullCount <= 1 && !bullDi) {
        bias = 'BEAR'; biasLabel = '하락 추세';
    }

    return { maAlignment, adxStrength, adxValue: adx, diSignal, pctFrom200, pctFrom50, bias, biasLabel };
}

// --- SMC Analysis ---

export function analyzeSMC(data: AnalyticsData[], currentPrice: number): SMCAnalysis {
    const markers: SMCMarkerInfo[] = [];
    const orderBlocks: OrderBlockInfo[] = [];
    const fvgs: FVGInfo[] = [];
    const len = data.length;

    // Last 5 bars for BOS/CHOCH markers
    const markerRange = Math.min(5, len);
    for (let i = 0; i < markerRange; i++) {
        const bar = data[len - 1 - i];
        if (bar.marker) {
            markers.push({ type: bar.marker, barsAgo: i, date: bar.datetime });
        }
    }

    // Last 20 bars for Order Blocks
    const obRange = Math.min(20, len);
    for (let i = 0; i < obRange; i++) {
        const bar = data[len - 1 - i];
        if (bar.ob_top != null && bar.ob_bottom != null) {
            let relation: string;
            if (currentPrice > bar.ob_top) relation = 'ABOVE';
            else if (currentPrice < bar.ob_bottom) relation = 'BELOW';
            else relation = 'INSIDE';
            orderBlocks.push({ top: bar.ob_top, bottom: bar.ob_bottom, relation, barsAgo: i });
        }
    }

    // Last 20 bars for FVGs
    const fvgRange = Math.min(20, len);
    for (let i = 0; i < fvgRange; i++) {
        const bar = data[len - 1 - i];
        if (bar.fvg_type && bar.fvg_top != null && bar.fvg_bottom != null) {
            let relation: string;
            if (currentPrice > bar.fvg_top) relation = 'ABOVE';
            else if (currentPrice < bar.fvg_bottom) relation = 'BELOW';
            else relation = 'INSIDE';
            fvgs.push({ type: bar.fvg_type, top: bar.fvg_top, bottom: bar.fvg_bottom, relation, barsAgo: i });
        }
    }

    // SMC bias scoring
    let bullScore = 0;
    let bearScore = 0;
    for (const m of markers) {
        if (m.type === 'BOS_BULL' || m.type === 'CHOCH_BULL') bullScore++;
        if (m.type === 'BOS_BEAR' || m.type === 'CHOCH_BEAR') bearScore++;
    }
    for (const ob of orderBlocks.slice(0, 3)) {
        if (ob.relation === 'ABOVE') bullScore++;
        else if (ob.relation === 'BELOW') bearScore++;
    }

    let smcBias: SMCBias = 'NEUTRAL';
    let smcLabel = '중립 (Neutral)';
    if (bullScore > bearScore && bullScore >= 2) { smcBias = 'BULLISH'; smcLabel = '강세 (Bullish)'; }
    else if (bearScore > bullScore && bearScore >= 2) { smcBias = 'BEARISH'; smcLabel = '약세 (Bearish)'; }
    else if (bullScore > bearScore) { smcBias = 'BULLISH'; smcLabel = '약한 강세'; }
    else if (bearScore > bullScore) { smcBias = 'BEARISH'; smcLabel = '약한 약세'; }

    return { markers, orderBlocks, fvgs, smcBias, smcLabel };
}

// --- Weighted Confidence Score ---

export function computeWeightedScore(analysis: EnhancedEntryAnalysis): number {
    const weights: Record<string, number> = {
        PS1: 2.0, PS2: 2.0, PS3: 1.5, PS4: 1.5,
        CF1: 1.0, CF2: 1.0, CF3: 1.0, CF4: 1.5,
    };

    const maxWeight = Object.values(weights).reduce((a, b) => a + b, 0);
    let score = 0;

    for (const s of [...analysis.primarySignals, ...analysis.confirmations]) {
        if (s.passed && weights[s.id]) {
            score += weights[s.id];
        }
    }

    let pct = (score / maxWeight) * 100;

    for (const rg of analysis.riskGates) {
        if (!rg.passed) pct -= 15;
    }

    return Math.max(0, Math.min(100, Math.round(pct)));
}

// --- Core Analysis (Enhanced) ---

export function analyzeEntrySignals(
    current: AnalyticsData,
    previous: AnalyticsData,
    volumeMA: number,
    data?: AnalyticsData[],
): EnhancedEntryAnalysis {
    const primarySignals: SignalCheck[] = [];
    const confirmations: SignalCheck[] = [];
    const riskGates: SignalCheck[] = [];

    // PS1: Golden Cross (5MA crosses above 20MA)
    const hasMAs = current.sma_5 != null && current.sma_20 != null
        && previous.sma_5 != null && previous.sma_20 != null;
    const ps1Crossed = hasMAs && previous.sma_5! <= previous.sma_20! && current.sma_5! > current.sma_20!;
    const maAbove = hasMAs && current.sma_5! > current.sma_20!;

    primarySignals.push({
        id: 'PS1',
        label: '골든크로스 (5MA > 20MA)',
        passed: ps1Crossed,
        detail: hasMAs
            ? ps1Crossed
                ? `5MA(${fmt(current.sma_5)}) > 20MA(${fmt(current.sma_20)}), 전일 5MA ≤ 20MA → 크로스 발생`
                : maAbove
                    ? `5MA(${fmt(current.sma_5)}) > 20MA(${fmt(current.sma_20)}) 유지 중 (신규 크로스 아님)`
                    : `5MA(${fmt(current.sma_5)}) ≤ 20MA(${fmt(current.sma_20)}) — 크로스 미발생`
            : '데이터 부족',
    });

    // PS2: MACD Bullish Crossover
    const hasMacd = current.macd_diff != null && previous.macd_diff != null;
    const ps2Crossed = hasMacd && previous.macd_diff! <= 0 && current.macd_diff! > 0;

    primarySignals.push({
        id: 'PS2',
        label: 'MACD 매수 시그널',
        passed: ps2Crossed,
        detail: hasMacd
            ? ps2Crossed
                ? `Hist: ${current.macd_diff!.toFixed(2)} (전일: ${previous.macd_diff!.toFixed(2)}) → 시그널선 상향돌파`
                : `Hist: ${current.macd_diff!.toFixed(2)} (전일: ${previous.macd_diff!.toFixed(2)})`
            : '데이터 부족',
    });

    // PS3: ADX/DI Trend Confirmation (ADX>=25 AND +DI>-DI with diff>5)
    const hasAdxDi = current.adx != null && current.plus_di != null && current.minus_di != null;
    const ps3Passed = hasAdxDi && current.adx! >= 25
        && current.plus_di! > current.minus_di!
        && (current.plus_di! - current.minus_di!) > 5;

    primarySignals.push({
        id: 'PS3',
        label: 'ADX/DI 추세확인',
        passed: ps3Passed,
        detail: hasAdxDi
            ? ps3Passed
                ? `ADX(${current.adx!.toFixed(1)})≥25, +DI(${current.plus_di!.toFixed(1)}) > -DI(${current.minus_di!.toFixed(1)}) → 매수추세 확인`
                : current.adx! < 25
                    ? `ADX(${current.adx!.toFixed(1)}) < 25 — 추세 약함`
                    : `+DI(${current.plus_di!.toFixed(1)}) ≤ -DI(${current.minus_di!.toFixed(1)}) — 매도 우위`
            : '데이터 부족',
    });

    // PS4: SMC Bullish Signal (BOS_BULL or CHOCH_BULL in last 5 bars)
    let ps4Passed = false;
    let ps4Detail = '데이터 부족';
    if (data && data.length >= 2) {
        const lookback = Math.min(5, data.length);
        const recentMarkers: string[] = [];
        for (let i = 0; i < lookback; i++) {
            const bar = data[data.length - 1 - i];
            if (bar.marker && (bar.marker === 'BOS_BULL' || bar.marker === 'CHOCH_BULL')) {
                recentMarkers.push(`${bar.marker} (${i}봉 전)`);
            }
        }
        ps4Passed = recentMarkers.length > 0;
        ps4Detail = ps4Passed
            ? `Smart Money Concept 강세: ${recentMarkers.join(', ')}`
            : '최근 5봉 내 BOS_BULL/CHOCH_BULL 없음';
    }

    primarySignals.push({
        id: 'PS4',
        label: 'Smart Money Concept 강세 시그널',
        passed: ps4Passed,
        detail: ps4Detail,
    });

    // CF1: RSI in range [30, 70]
    const hasRsi = current.rsi_14 != null;
    const cf1Passed = hasRsi && current.rsi_14! >= 30 && current.rsi_14! <= 70;

    confirmations.push({
        id: 'CF1',
        label: 'RSI 적정 범위 (30~70)',
        passed: cf1Passed,
        detail: hasRsi
            ? `RSI(14): ${current.rsi_14!.toFixed(1)} ${cf1Passed ? '(적정 구간)' : current.rsi_14! > 70 ? '(과매수 구간)' : '(과매도 구간)'}`
            : '데이터 부족',
    });

    // CF2: Volume > 20MA * 1.5
    const vol = current.volume || 0;
    const volThreshold = volumeMA * 1.5;
    const cf2Passed = volumeMA > 0 && vol >= volThreshold;

    confirmations.push({
        id: 'CF2',
        label: '거래량 증가 (20MA × 1.5)',
        passed: cf2Passed,
        detail: volumeMA > 0
            ? `Vol: ${fmtVol(vol)} ${cf2Passed ? '≥' : '<'} MA×1.5: ${fmtVol(volThreshold)}`
            : '거래량 MA 계산 불가',
    });

    // CF3: ADX Trend Exists (ADX>=20)
    const cf3HasAdx = current.adx != null;
    const cf3Passed = cf3HasAdx && current.adx! >= 20;

    confirmations.push({
        id: 'CF3',
        label: 'ADX 추세 존재 (≥20)',
        passed: cf3Passed,
        detail: cf3HasAdx
            ? `ADX(14): ${current.adx!.toFixed(1)} ${cf3Passed ? '≥ 20 (추세 확인)' : '< 20 (추세 약함)'}`
            : '데이터 부족',
    });

    // CF4: 200MA Long-term Filter (close > 200MA)
    const has200MA = current.sma_200 != null && current.close != null;
    const cf4Passed = has200MA && current.close! > current.sma_200!;

    confirmations.push({
        id: 'CF4',
        label: '200MA 장기 필터',
        passed: cf4Passed,
        detail: has200MA
            ? `종가(${fmt(current.close)}) ${cf4Passed ? '>' : '≤'} 200MA(${fmt(current.sma_200)}) ${cf4Passed ? '— 장기 상승추세' : '— 장기 추세 미확인'}`
            : '데이터 부족 (200MA 미산출)',
    });

    // RG1: Mid-term Trend Alignment (20MA > 60MA)
    const hasRg1 = current.sma_20 != null && current.sma_60 != null;
    const rg1Passed = hasRg1 && current.sma_20! > current.sma_60!;

    riskGates.push({
        id: 'RG1',
        label: '중기추세 정렬 (20MA > 60MA)',
        passed: rg1Passed,
        detail: hasRg1
            ? `20MA(${fmt(current.sma_20)}) ${rg1Passed ? '>' : '≤'} 60MA(${fmt(current.sma_60)}) ${rg1Passed ? '— 순추세' : '— 역추세 위험'}`
            : '데이터 부족',
    });

    // RG2: BB Extreme Filter (%B 0.1~0.9)
    let rg2Passed = true;
    let rg2Detail = '데이터 부족';
    if (current.bb_hband != null && current.bb_lband != null && current.close != null) {
        const bbRange = current.bb_hband - current.bb_lband;
        if (bbRange > 0) {
            const pctB = (current.close - current.bb_lband) / bbRange;
            rg2Passed = pctB >= 0.1 && pctB <= 0.9;
            rg2Detail = `BB %B: ${(pctB * 100).toFixed(1)}% ${rg2Passed ? '(안전 범위)' : pctB > 0.9 ? '(과매수 극단)' : '(과매도 극단)'}`;
        }
    }

    riskGates.push({
        id: 'RG2',
        label: 'BB 극단 필터 (%B 0.1~0.9)',
        passed: rg2Passed,
        detail: rg2Detail,
    });

    // RG3: RSI Overbought Guard (RSI < 75)
    const rg3HasRsi = current.rsi_14 != null;
    const rg3Passed = !rg3HasRsi || current.rsi_14! < 75;

    riskGates.push({
        id: 'RG3',
        label: 'RSI 과매수 경계 (< 75)',
        passed: rg3Passed,
        detail: rg3HasRsi
            ? `RSI: ${current.rsi_14!.toFixed(1)} ${rg3Passed ? '< 75 (정상)' : '≥ 75 (과매수 경계)'}`
            : '데이터 부족',
    });

    // RG4: Price < BB Upper
    const hasBB = current.bb_hband != null && current.close != null;
    const rg4Passed = hasBB && current.close! < current.bb_hband!;

    riskGates.push({
        id: 'RG4',
        label: 'BB 상단 미도달',
        passed: rg4Passed,
        detail: hasBB
            ? `${fmt(current.close)} ${rg4Passed ? '<' : '≥'} BB상단 ${fmt(current.bb_hband)}`
            : '데이터 부족',
    });

    // Calculate strength & verdict
    const passedPrimary = primarySignals.filter(s => s.passed).length;
    const passedConfirm = confirmations.filter(c => c.passed).length;
    const allRiskGatesPassed = riskGates.every(r => r.passed);
    const strength = passedPrimary + passedConfirm;

    let verdict: Verdict;
    let verdictLabel: string;

    if (passedPrimary >= 1 && passedConfirm >= 2 && allRiskGatesPassed) {
        verdict = 'BUY_SUITABLE';
        verdictLabel = '매수 적합';
    } else if (passedPrimary >= 1 || passedConfirm >= 2) {
        verdict = 'WATCH';
        verdictLabel = '관망';
    } else {
        verdict = 'NOT_SUITABLE';
        verdictLabel = '매수 부적합';
    }

    // Trend Filter & SMC
    const trendFilter = analyzeTrendFilter(current);
    let smcAnalysis: SMCAnalysis | null = null;
    if (data && data.length >= 2 && current.close != null) {
        smcAnalysis = analyzeSMC(data, current.close);
    }

    const result: EnhancedEntryAnalysis = {
        primarySignals, confirmations, riskGates,
        strength, verdict, verdictLabel,
        trendFilter, smcAnalysis,
        confidenceScore: 0, confidenceLabel: '',
    };

    const score = computeWeightedScore(result);
    result.confidenceScore = score;
    if (score >= 75) result.confidenceLabel = '매우 강함';
    else if (score >= 55) result.confidenceLabel = '강함';
    else if (score >= 35) result.confidenceLabel = '보통';
    else result.confidenceLabel = '약함';

    return result;
}

export function calculateExitLevels(
    currentPrice: number,
    current: AnalyticsData,
    _previous: AnalyticsData,
    data?: AnalyticsData[],
): DynamicExitLevels {
    const hasMAs = current.sma_5 != null && current.sma_20 != null;
    const deadCrossActive = hasMAs && current.sma_5! < current.sma_20!;

    const fixedStopLoss = currentPrice * 0.97;
    const fixedTakeProfit = currentPrice * 1.07;

    const atr = current.atr_14;
    let atrStopLoss: number | null = null;
    let atrTakeProfit: number | null = null;
    let trailingStop: number | null = null;
    let chandelierExit: number | null = null;
    let dynamicMultiplier: number | null = null;

    if (atr != null && atr > 0) {
        const adx = current.adx;
        dynamicMultiplier = (adx != null && adx < 20) ? 2.0 : 1.5;

        atrStopLoss = currentPrice - dynamicMultiplier * atr;
        atrTakeProfit = currentPrice + 2 * atr;
        trailingStop = currentPrice - 1.5 * atr;

        if (data && data.length >= 2) {
            const lb = Math.min(22, data.length);
            let highest = -Infinity;
            for (let i = 0; i < lb; i++) {
                const bar = data[data.length - 1 - i];
                if (bar.high != null && bar.high > highest) highest = bar.high;
            }
            if (highest > 0) chandelierExit = highest - 3 * atr;
        }
    }

    // Effective stop: tighter (higher) of ATR and fixed -3%
    const effectiveStopLoss = atrStopLoss != null ? Math.max(atrStopLoss, fixedStopLoss) : fixedStopLoss;
    const effectiveTakeProfit = atrTakeProfit != null ? Math.max(atrTakeProfit, fixedTakeProfit) : fixedTakeProfit;

    return {
        stopLoss: fixedStopLoss,
        takeProfit: fixedTakeProfit,
        deadCrossActive,
        deadCrossDetail: hasMAs
            ? deadCrossActive
                ? `5MA(${fmt(current.sma_5)}) < 20MA(${fmt(current.sma_20)}) — 발생 중`
                : `5MA(${fmt(current.sma_5)}) ≥ 20MA(${fmt(current.sma_20)}) — 미발생`
            : '데이터 부족',
        maxHoldingDays: 10,
        atrStopLoss,
        effectiveStopLoss,
        atrTakeProfit,
        effectiveTakeProfit,
        trailingStop,
        chandelierExit,
        dynamicMultiplier,
        atrValue: atr,
    };
}
