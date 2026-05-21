/**
 * SignalAnalysis 내부 헬퍼 — 인디케이터 포맷, RSI 색상 클래스.
 *
 * Phase D3 분할: dashboard/SignalAnalysis.tsx → dashboard/signal-analysis/_helpers.ts
 */

export function fmtIndicator(v: number | null | undefined, decimals = 2): string {
    if (v === null || v === undefined) return 'N/A';
    return v.toLocaleString(undefined, { maximumFractionDigits: decimals });
}

// --- ATR Entry Panel ---


export function getRsiClass(rsi: number | null): string {
    if (rsi == null) return '';
    if (rsi >= 70) return 'rsi-overbought';
    if (rsi <= 30) return 'rsi-oversold';
    return '';
}

// --- Confidence Bar ---

