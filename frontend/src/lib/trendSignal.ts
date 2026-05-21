/**
 * Trend Signal — 가장 최근 캔들의 OHLC + 이동평균선 정렬을 기반으로
 * Bullish / Bearish / Squeeze / Neutral 단계 라벨을 산출하는 순수 함수.
 *
 * Phase D1.2 추출: pages/Dashboard.tsx → lib/trendSignal.ts
 * 의존성 없음 (순수 함수). useMemo와 함께 사용 권장.
 */

import type { AnalyticsData } from '@/types';

export interface TrendSignal {
    label: string;
    /** Dashboard CSS의 text-color utility class. */
    color: 'text-muted' | 'text-success' | 'text-warning' | 'text-error';
    /** Dashboard CSS background (rgba). */
    bg: string;
}

const NEUTRAL: TrendSignal = {
    label: 'Neutral Phase',
    color: 'text-muted',
    bg: 'rgba(148, 163, 184, 0.1)',
};

const BULL_STRONG: TrendSignal = {
    label: 'Strong Bull Trend 🚀',
    color: 'text-success',
    bg: 'rgba(34, 197, 94, 0.1)',
};

const BULL: TrendSignal = {
    label: 'Bullish Phase 🟢',
    color: 'text-success',
    bg: 'rgba(34, 197, 94, 0.1)',
};

const BEAR_STRONG: TrendSignal = {
    label: 'Strong Bear Trend 🩸',
    color: 'text-error',
    bg: 'rgba(239, 68, 68, 0.1)',
};

const BEAR: TrendSignal = {
    label: 'Bearish Phase 🔴',
    color: 'text-error',
    bg: 'rgba(239, 68, 68, 0.1)',
};

const SQUEEZE: TrendSignal = {
    label: 'Volatility Squeeze ⚠️',
    color: 'text-warning',
    bg: 'rgba(234, 179, 8, 0.1)',
};

/**
 * 최신 캔들에서 trend signal 단계를 산출.
 *
 * 우선순위:
 *   1. Bollinger 폭이 종가 5% 미만 → Volatility Squeeze
 *   2. 5/20/60/120/200 SMA 완전 정렬(상승) → Strong Bull
 *   3. close > SMA200 && SMA20 > SMA60 → Bullish
 *   4. 5/20/60/120/200 SMA 완전 정렬(하락) → Strong Bear
 *   5. close < SMA200 && SMA20 < SMA60 → Bearish
 *   6. 그 외 → Neutral
 */
export function computeTrendSignal(d: AnalyticsData | null | undefined): TrendSignal {
    if (!d) return NEUTRAL;

    const { close, sma_5, sma_20, sma_60, sma_120, sma_200, bb_width } = d;

    if (bb_width && close && bb_width / close < 0.05) {
        return SQUEEZE;
    }

    if (sma_5 && sma_20 && sma_60 && sma_120 && sma_200) {
        if (close > sma_5 && sma_5 > sma_20 && sma_20 > sma_60 && sma_60 > sma_120 && sma_120 > sma_200) {
            return BULL_STRONG;
        }
        if (close > sma_200 && sma_20 > sma_60) {
            return BULL;
        }
        if (close < sma_5 && sma_5 < sma_20 && sma_20 < sma_60 && sma_60 < sma_120 && sma_120 < sma_200) {
            return BEAR_STRONG;
        }
        if (close < sma_200 && sma_20 < sma_60) {
            return BEAR;
        }
    }

    return NEUTRAL;
}
