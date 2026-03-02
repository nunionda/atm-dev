/**
 * 모멘텀 스윙 전략 시그널 분석 엔진.
 * momentum_swing.py의 진입/청산 로직을 프론트엔드에서 복제한다.
 * 순수 함수 — React 의존성 없음.
 */

import type { AnalyticsData } from './api';

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

// --- Helpers ---

function fmt(v: number | null, decimals = 0): string {
    if (v === null || v === undefined) return 'N/A';
    return v.toLocaleString(undefined, { maximumFractionDigits: decimals });
}

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

export function analyzeEntrySignals(
    current: AnalyticsData,
    previous: AnalyticsData,
    volumeMA: number,
): EntryAnalysis {
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

    // PS2: MACD Bullish Crossover (histogram crosses from <=0 to >0)
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
    const strength = passedPrimary + passedConfirm;

    let verdict: Verdict;
    let verdictLabel: string;

    if (passedPrimary >= 1 && passedConfirm >= 1) {
        verdict = 'BUY_SUITABLE';
        verdictLabel = '매수 적합';
    } else if (passedPrimary >= 1 || passedConfirm >= 1) {
        verdict = 'WATCH';
        verdictLabel = '관망';
    } else {
        verdict = 'NOT_SUITABLE';
        verdictLabel = '매수 부적합';
    }

    return { primarySignals, confirmations, riskGates, strength, verdict, verdictLabel };
}

export function calculateExitLevels(
    currentPrice: number,
    current: AnalyticsData,
    _previous: AnalyticsData,
): ExitLevels {
    const hasMAs = current.sma_5 != null && current.sma_20 != null;
    const deadCrossActive = hasMAs && current.sma_5! < current.sma_20!;

    return {
        stopLoss: currentPrice * 0.97,
        takeProfit: currentPrice * 1.07,
        deadCrossActive,
        deadCrossDetail: hasMAs
            ? deadCrossActive
                ? `5MA(${fmt(current.sma_5)}) < 20MA(${fmt(current.sma_20)}) — 발생 중`
                : `5MA(${fmt(current.sma_5)}) ≥ 20MA(${fmt(current.sma_20)}) — 미발생`
            : '데이터 부족',
        maxHoldingDays: 10,
    };
}
