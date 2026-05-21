/**
 * Chart utility functions — pure helpers with no React dependency.
 * Provides 4H aggregation, Heikin-Ashi, volume profile, and MA configuration.
 */

import type { AnalyticsData } from './api';

// --- Types ---

export type ChartType = 'candlestick' | 'line' | 'area' | 'heikin-ashi';

export interface OverlayState {
    sma5: boolean;
    sma20: boolean;
    sma50: boolean;
    sma60: boolean;
    sma120: boolean;
    sma200: boolean;
    ema20: boolean;
}

export interface VolumeBucket {
    priceLevel: number;
    totalVolume: number;
    buyVolume: number;
    sellVolume: number;
    pct: number; // 0-100, relative to max bucket
}

// --- MA Configuration ---

export const MA_CONFIG: Record<string, { field: keyof AnalyticsData; color: string; label: string }> = {
    sma5:   { field: 'sma_5',   color: '#f59e0b', label: 'SMA5' },
    sma20:  { field: 'sma_20',  color: '#2962ff', label: 'SMA20' },
    sma50:  { field: 'sma_50',  color: '#e91e63', label: 'SMA50' },
    sma60:  { field: 'sma_60',  color: '#ff5722', label: 'SMA60' },
    sma120: { field: 'sma_120', color: '#00bcd4', label: 'SMA120' },
    sma200: { field: 'sma_200', color: '#4caf50', label: 'SMA200' },
    ema20:  { field: 'ema_20',  color: '#ff9800', label: 'EMA20' },
};

// --- 4H Candle Aggregation ---

export function aggregate4HCandles(data: AnalyticsData[]): AnalyticsData[] {
    if (data.length === 0) return [];

    const sorted = [...data].sort(
        (a, b) => new Date(a.datetime).getTime() - new Date(b.datetime).getTime(),
    );

    const buckets = new Map<string, AnalyticsData[]>();

    for (const item of sorted) {
        const dt = new Date(item.datetime);
        const flooredHour = Math.floor(dt.getHours() / 4) * 4;
        const key = `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, '0')}-${String(dt.getDate()).padStart(2, '0')} ${String(flooredHour).padStart(2, '0')}:00:00`;

        if (!buckets.has(key)) buckets.set(key, []);
        buckets.get(key)!.push(item);
    }

    return Array.from(buckets.entries()).map(([key, items]) => {
        const first = items[0];
        const last = items[items.length - 1];
        return {
            ...last, // carry forward indicator values from last 1h candle
            datetime: key,
            open: first.open,
            high: Math.max(...items.map(i => i.high)),
            low: Math.min(...items.map(i => i.low)),
            close: last.close,
            volume: items.reduce((sum, i) => sum + (i.volume || 0), 0),
        };
    });
}

// --- Heikin-Ashi Computation ---

export function computeHeikinAshi(data: AnalyticsData[]): AnalyticsData[] {
    if (data.length === 0) return [];

    const sorted = [...data].sort(
        (a, b) => new Date(a.datetime).getTime() - new Date(b.datetime).getTime(),
    );

    const result: AnalyticsData[] = [];

    for (let i = 0; i < sorted.length; i++) {
        const item = sorted[i];
        const haClose = (item.open + item.high + item.low + item.close) / 4;
        const prev = i > 0 ? result[i - 1] : null;
        const haOpen = prev
            ? (prev.open + prev.close) / 2
            : (item.open + item.close) / 2;
        const haHigh = Math.max(item.high, haOpen, haClose);
        const haLow = Math.min(item.low, haOpen, haClose);

        result.push({
            ...item, // keep all indicator values from original
            open: haOpen,
            high: haHigh,
            low: haLow,
            close: haClose,
        });
    }

    return result;
}

// --- Volume Profile ---

export function computeVolumeProfile(
    data: AnalyticsData[],
    bucketCount = 24,
): VolumeBucket[] {
    if (data.length === 0) return [];

    const prices = data.flatMap(d => [d.high, d.low]);
    const minPrice = Math.min(...prices);
    const maxPrice = Math.max(...prices);
    const range = maxPrice - minPrice;
    if (range === 0) return [];

    const bucketSize = range / bucketCount;
    const buckets: VolumeBucket[] = Array.from({ length: bucketCount }, (_, i) => ({
        priceLevel: minPrice + (i + 0.5) * bucketSize,
        totalVolume: 0,
        buyVolume: 0,
        sellVolume: 0,
        pct: 0,
    }));

    for (const item of data) {
        const candleLow = Math.min(item.low, item.high);
        const candleHigh = Math.max(item.low, item.high);
        const candleRange = candleHigh - candleLow || 1;
        const isBuy = item.close >= item.open;

        for (const bucket of buckets) {
            const bucketLow = bucket.priceLevel - bucketSize / 2;
            const bucketHigh = bucket.priceLevel + bucketSize / 2;

            if (candleHigh >= bucketLow && candleLow <= bucketHigh) {
                const overlapLow = Math.max(candleLow, bucketLow);
                const overlapHigh = Math.min(candleHigh, bucketHigh);
                const overlapRatio = (overlapHigh - overlapLow) / candleRange;
                const vol = (item.volume || 0) * overlapRatio;

                bucket.totalVolume += vol;
                if (isBuy) bucket.buyVolume += vol;
                else bucket.sellVolume += vol;
            }
        }
    }

    const maxVol = Math.max(...buckets.map(b => b.totalVolume));
    for (const b of buckets) {
        b.pct = maxVol > 0 ? (b.totalVolume / maxVol) * 100 : 0;
    }

    return buckets;
}

// --- Support/Resistance Detection ---

export interface SRLevel {
    price: number;
    type: 'support' | 'resistance';
    touches: number;
    strength: number; // 1-3 based on touches
}

export function computeSupportResistance(
    data: AnalyticsData[],
    currentPrice: number,
    swingPeriod = 5,
    clusterPct = 0.015,
    maxLevels = 3,
): SRLevel[] {
    if (data.length < swingPeriod * 2 + 1) return [];

    // 1. Detect swing highs and lows
    const swingPoints: { price: number; kind: 'high' | 'low' }[] = [];

    for (let i = swingPeriod; i < data.length - swingPeriod; i++) {
        const h = data[i].high;
        const l = data[i].low;

        let isSwingHigh = true;
        let isSwingLow = true;

        for (let j = 1; j <= swingPeriod; j++) {
            if (data[i - j].high >= h || data[i + j].high >= h) isSwingHigh = false;
            if (data[i - j].low <= l || data[i + j].low <= l) isSwingLow = false;
        }

        if (isSwingHigh) swingPoints.push({ price: h, kind: 'high' });
        if (isSwingLow) swingPoints.push({ price: l, kind: 'low' });
    }

    if (swingPoints.length === 0) return [];

    // 2. Cluster nearby levels
    const sorted = [...swingPoints].sort((a, b) => a.price - b.price);
    const clusters: { prices: number[]; avg: number }[] = [];

    for (const sp of sorted) {
        const matched = clusters.find(
            c => Math.abs(sp.price - c.avg) / c.avg < clusterPct,
        );
        if (matched) {
            matched.prices.push(sp.price);
            matched.avg = matched.prices.reduce((s, p) => s + p, 0) / matched.prices.length;
        } else {
            clusters.push({ prices: [sp.price], avg: sp.price });
        }
    }

    // 3. Classify as support/resistance and build levels
    const levels: SRLevel[] = clusters.map(c => {
        const touches = c.prices.length;
        return {
            price: c.avg,
            type: c.avg >= currentPrice ? 'resistance' as const : 'support' as const,
            touches,
            strength: touches >= 4 ? 3 : touches >= 2 ? 2 : 1,
        };
    });

    // 4. Sort by touches descending, take top N for each type
    const resistances = levels
        .filter(l => l.type === 'resistance')
        .sort((a, b) => b.touches - a.touches)
        .slice(0, maxLevels);

    const supports = levels
        .filter(l => l.type === 'support')
        .sort((a, b) => b.touches - a.touches)
        .slice(0, maxLevels);

    return [...resistances, ...supports];
}
