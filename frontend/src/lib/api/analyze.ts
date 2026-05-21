/**
 * Analytics / Quote / Search / MTF API
 * Phase 3.A-2: api.ts → api/analyze.ts (~164 lines)
 *
 * 외부 의존:
 *   - API_BASE_URL  (./_client)
 *   - getCached / setCache  (../cache)
 */

import { API_BASE_URL } from './_client';
import { getCached, setCache } from '../cache';

export interface AnalyticsData {
    datetime: string;
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
    sma_5: number | null;
    sma_20: number | null;
    sma_50: number | null;
    sma_60: number | null;
    sma_120: number | null;
    sma_200: number | null;
    ema_20: number | null;
    bb_hband: number | null;
    bb_lband: number | null;
    bb_mavg: number | null;
    bb_width: number | null;
    rsi_14: number | null;
    macd: number | null;
    macd_signal: number | null;
    macd_diff: number | null;
    atr_14: number | null;
    adx: number | null;
    plus_di: number | null;
    minus_di: number | null;
    marker: string | null;
    ob_top: number | null;
    ob_bottom: number | null;
    fvg_type: string | null;
    fvg_top: number | null;
    fvg_bottom: number | null;
}

export interface AnalyticsResponse {
    ticker: string;
    period: string;
    interval: string;
    data: AnalyticsData[];
}

export async function fetchAnalyticsData(
    ticker: string,
    period: string = 'ytd',
    interval: string = '1d',
    signal?: AbortSignal,
): Promise<AnalyticsResponse> {
    const cacheKey = `analytics:${ticker}:${period}:${interval}`;
    const cached = getCached<AnalyticsResponse>(cacheKey);

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    if (signal) signal.addEventListener('abort', () => controller.abort());

    try {
        const response = await fetch(
            `${API_BASE_URL}/analyze/${encodeURIComponent(ticker)}?period=${period}&interval=${interval}`,
            { signal: controller.signal },
        );
        clearTimeout(timeout);
        if (!response.ok) {
            if (cached) return cached; // 실패 시 캐시 폴백
            throw new Error(`Failed to fetch analytics for ${ticker}. Status: ${response.status}`);
        }
        const data = await response.json();
        setCache(cacheKey, data);
        return data;
    } catch (error) {
        clearTimeout(timeout);
        if (cached) return cached; // 네트워크 에러 시 캐시 폴백
        throw error;
    }
}
// --- Quote (lightweight polling endpoint) ---

export interface QuoteCandle {
    datetime: string;
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
}

export interface QuoteLatest {
    price: number;
    change: number;
    change_pct: number;
    high: number;
    low: number;
    volume: number;
}

export interface QuoteResponse {
    ticker: string;
    updated_at: string;
    cached: boolean;
    candles: QuoteCandle[];
    latest: QuoteLatest;
}

export async function fetchQuote(ticker: string, count: number = 5): Promise<QuoteResponse> {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);
    try {
        const response = await fetch(
            `${API_BASE_URL}/quote/${ticker}?count=${count}`,
            { signal: controller.signal },
        );
        clearTimeout(timeout);
        if (!response.ok) {
            throw new Error(`Quote fetch failed for ${ticker}. Status: ${response.status}`);
        }
        return response.json();
    } catch (error) {
        clearTimeout(timeout);
        throw error;
    }
}

// --- Multi-Timeframe Data ---

/**
 * 멀티타임프레임 데이터 조회
 * HTF: 1H (period='1mo'), LTF: 5min (period='5d')
 * yfinance 제한: 5m → 최대 60일, 1h → 최대 730일
 */
export async function fetchMTFData(ticker: string): Promise<{
    htf: AnalyticsResponse;
    ltf: AnalyticsResponse;
}> {
    const [htf, ltf] = await Promise.all([
        fetchAnalyticsData(ticker, '1mo', '1h'),
        fetchAnalyticsData(ticker, '5d', '5m'),
    ]);
    return { htf, ltf };
}

// --- Ticker Search ---

export interface SearchResult {
    code: string;
    name_kr: string;
    name_en: string;
    market: string; // "KS" | "KQ" | "US" | "CRYPTO"
    ticker: string; // yfinance format
}

export async function searchTickers(query: string): Promise<SearchResult[]> {
    if (!query.trim()) return [];
    try {
        const response = await fetch(`${API_BASE_URL}/search?q=${encodeURIComponent(query)}`);
        if (!response.ok) return [];
        const data = await response.json();
        return data.results || [];
    } catch {
        return [];
    }
}
