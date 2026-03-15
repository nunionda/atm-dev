/**
 * Shared indicator computation utilities.
 *
 * Extracted from signalEngine.ts, strategyEngine.ts, and futuresEngine.ts
 * to eliminate duplication. All functions are pure (no side-effects).
 */

import type { OHLC } from './scalpEngine';

// ── Shared Types ─────────────────────────────────────────────────────

export type TrendBias = 'STRONG_BULL' | 'BULL' | 'NEUTRAL' | 'BEAR' | 'STRONG_BEAR';

// ── Formatting Helpers ───────────────────────────────────────────────

/** Format a nullable number for display. */
export function fmt(v: number | null | undefined, decimals = 2): string {
    if (v === null || v === undefined) return 'N/A';
    return v.toLocaleString(undefined, { maximumFractionDigits: decimals });
}

// ── OHLC-based Indicator Computations ────────────────────────────────

/** Simple Moving Average over `period` bars ending at index `end`. */
export function computeMA(candles: OHLC[], end: number, period: number): number {
    const start = Math.max(0, end - period + 1);
    let sum = 0, cnt = 0;
    for (let i = start; i <= end; i++) { sum += candles[i].c; cnt++; }
    return cnt > 0 ? sum / cnt : candles[end].c;
}

/** Standard deviation of close prices over `period` bars ending at `end`. */
export function computeStdDev(candles: OHLC[], end: number, period: number): number {
    const ma = computeMA(candles, end, period);
    const start = Math.max(0, end - period + 1);
    let sumSq = 0, cnt = 0;
    for (let i = start; i <= end; i++) { sumSq += (candles[i].c - ma) ** 2; cnt++; }
    return cnt > 1 ? Math.sqrt(sumSq / cnt) : 0;
}

/** Average True Range over `period` bars ending at `end`. */
export function computeATR(candles: OHLC[], end: number, period: number): number {
    let sum = 0, cnt = 0;
    for (let i = Math.max(1, end - period + 1); i <= end; i++) {
        const tr = Math.max(
            candles[i].h - candles[i].l,
            Math.abs(candles[i].h - candles[i - 1].c),
            Math.abs(candles[i].l - candles[i - 1].c)
        );
        sum += tr; cnt++;
    }
    return cnt > 0 ? sum / cnt : 0;
}

/** RSI proxy computed from close prices. */
export function computeRSI(candles: OHLC[], end: number, period: number = 14): number | null {
    if (end < period) return null;
    let gains = 0, losses = 0;
    for (let i = end - period + 1; i <= end; i++) {
        const delta = candles[i].c - candles[i - 1].c;
        if (delta > 0) gains += delta;
        else losses -= delta;
    }
    const avgGain = gains / period;
    const avgLoss = losses / period;
    if (avgLoss === 0) return 100;
    const rs = avgGain / avgLoss;
    return 100 - (100 / (1 + rs));
}

/** ADX proxy -- simplified DI-based estimation. */
export function computeADXProxy(candles: OHLC[], end: number, period: number = 14): {
    adx: number; plusDI: number; minusDI: number;
} | null {
    if (end < period + 1) return null;

    let plusDMSum = 0, minusDMSum = 0, trSum = 0;
    for (let i = end - period + 1; i <= end; i++) {
        const upMove = candles[i].h - candles[i - 1].h;
        const downMove = candles[i - 1].l - candles[i].l;
        const plusDM = upMove > downMove && upMove > 0 ? upMove : 0;
        const minusDM = downMove > upMove && downMove > 0 ? downMove : 0;
        const tr = Math.max(
            candles[i].h - candles[i].l,
            Math.abs(candles[i].h - candles[i - 1].c),
            Math.abs(candles[i].l - candles[i - 1].c)
        );
        plusDMSum += plusDM;
        minusDMSum += minusDM;
        trSum += tr;
    }

    if (trSum === 0) return null;
    const plusDI = (plusDMSum / trSum) * 100;
    const minusDI = (minusDMSum / trSum) * 100;
    const diSum = plusDI + minusDI;
    const dx = diSum > 0 ? (Math.abs(plusDI - minusDI) / diSum) * 100 : 0;
    // Simplified: use DX as ADX proxy (real ADX would use smoothed DX average)
    return { adx: dx, plusDI, minusDI };
}

/** Bollinger Band width as % of price. */
export function computeBBWidth(candles: OHLC[], end: number, period: number = 20): number {
    const ma = computeMA(candles, end, period);
    const sd = computeStdDev(candles, end, period);
    if (ma === 0) return 0;
    return ((sd * 4) / ma) * 100;  // 2σ upper - 2σ lower = 4σ
}
