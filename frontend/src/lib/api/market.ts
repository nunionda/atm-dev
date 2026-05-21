/**
 * Market Overview / MarketId / Intelligence / Performance Comparison API
 * Phase 3.A-2: api.ts → api/market.ts
 *
 * 외부 의존:
 *   - API_BASE_URL  (./_client)
 *   - getCached / setCache  (../cache)
 *   - fetchOrMock  (./_client)
 */

import { API_BASE_URL, fetchOrMock } from './_client';
import { getCached, setCache } from '../cache';

// --- Market Overview ---

export interface MarketIndex {
    symbol: string;
    name: string;
    name_kr: string;
    group: string;
    price: number | null;
    change: number | null;
    change_pct: number | null;
}

export interface MarketRegime {
    regime: 'RISK_ON' | 'NEUTRAL' | 'RISK_OFF';
    label: string;
    label_kr: string;
    score: number;
    signals: string[];
}

export interface MarketOverview {
    indices: MarketIndex[];
    regime: MarketRegime;
    updated_at: string;
}

export async function fetchMarketOverview(signal?: AbortSignal): Promise<MarketOverview | null> {
    const cacheKey = 'market-overview';
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 30000);
    if (signal) signal.addEventListener('abort', () => controller.abort());

    try {
        const response = await fetch(`${API_BASE_URL}/market-overview`, { signal: controller.signal });
        clearTimeout(timeout);
        if (!response.ok) {
            console.error(`[API] market-overview HTTP ${response.status}`);
            return getCached<MarketOverview>(cacheKey);
        }
        const data = await response.json();
        setCache(cacheKey, data);
        console.log(`[API] market-overview loaded: ${data.indices?.length} indices`);
        return data;
    } catch (error: any) {
        clearTimeout(timeout);
        if (error?.name === 'AbortError') return null;
        console.error('[API] market-overview fetch failed:', error);
        return getCached<MarketOverview>(cacheKey);
    }
}

// --- Multi-Market ---

export type MarketId = 'kospi' | 'sp500' | 'ndx';

export interface MarketConfig {
    id: MarketId;
    label: string;
    currency: string;
    currencySymbol: string;
    flag: string;
}

export const MARKETS: MarketConfig[] = [
    { id: 'sp500', label: 'S&P 500', currency: 'USD', currencySymbol: '$', flag: '🇺🇸' },
    { id: 'ndx', label: 'NASDAQ 100', currency: 'USD', currencySymbol: '$', flag: '🇺🇸' },
    { id: 'kospi', label: 'KOSPI 200', currency: 'KRW', currencySymbol: '₩', flag: '🇰🇷' },
];

export function getMarketConfig(id: MarketId): MarketConfig {
    return MARKETS.find(m => m.id === id) ?? MARKETS[0];
}

// --- Market Intelligence Types ---

// K5: 6레짐 (legacy) + 3레짐 (new) 모두 지원 — 백엔드 호환
export type IndexTrend =
    // 6-key (backward compat)
    | 'STRONG_BULL' | 'BULL' | 'NEUTRAL' | 'RANGE_BOUND' | 'BEAR' | 'CRISIS'
    // 3-key (new, default under _use_3regime=True)
    | 'BULL_AGG' | 'BEAR_AGG';
export type IndexTrend3 = 'BULL_AGG' | 'NEUTRAL' | 'BEAR_AGG';
export type MAAlignment = 'ALIGNED_BULL' | 'MIXED' | 'ALIGNED_BEAR';
export type VolatilityState = 'LOW' | 'NORMAL' | 'HIGH' | 'EXTREME';

export interface IndexTrendData {
    trend: IndexTrend;
    ma_alignment: MAAlignment;
    momentum_score: number;
    volatility_state: VolatilityState;
    signals: string[];
    rsi?: number;
    adx?: number;
    macd_value?: number;
    macd_signal?: number;
    // J2/K3: futures + basis + VIX percentile
    index_source?: 'futures' | 'spot';
    basis_pct?: number;
    basis_signal?: number;
    vix_percentile_20d?: number;
    vix_percentile_50d?: number;
}

// K5: 6→3 collapse helper (UI 일관성)
export function collapseIndexTrend(trend: IndexTrend): IndexTrend3 {
    switch (trend) {
        case 'STRONG_BULL':
        case 'BULL':
        case 'BULL_AGG':
            return 'BULL_AGG';
        case 'NEUTRAL':
            return 'NEUTRAL';
        case 'RANGE_BOUND':
        case 'BEAR':
        case 'CRISIS':
        case 'BEAR_AGG':
            return 'BEAR_AGG';
        default:
            return 'NEUTRAL';
    }
}

export interface TrendChangeEntry {
    timestamp: string;
    from_trend: IndexTrend | null;
    to_trend: IndexTrend;
    from_weights: Record<string, number>;
    to_weights: Record<string, number>;
    trigger_signals: string[];
}

export interface MarketIntelligenceData {
    index_trend: IndexTrendData;
    strategy_weights: Record<string, number>;
    vix_ema20: number;
    market_regime: string;
    trend_history: TrendChangeEntry[];
}

export type MarketIntelligenceResponse = Record<MarketId, MarketIntelligenceData | null>;

// --- Performance Comparison (Live vs Backtest) ---

export interface ComparisonMetrics {
    total_return_pct: number;
    sharpe_ratio: number;
    max_drawdown_pct: number;
    win_rate: number;
    profit_factor: number;
}

export interface PerformanceComparison {
    market: string;
    live: ComparisonMetrics;
    backtest: ComparisonMetrics | null;
    deltas: ComparisonMetrics | null;
    has_backtest: boolean;
}

export async function fetchPerformanceComparison(market: MarketId): Promise<PerformanceComparison> {
    return fetchOrMock(`/performance/vs-backtest?market=${market}`, () => ({
        market,
        live: { total_return_pct: 0, sharpe_ratio: 0, max_drawdown_pct: 0, win_rate: 0, profit_factor: 0 },
        backtest: null,
        deltas: null,
        has_backtest: false,
    }));
}

export async function fetchMarketIntelligence(): Promise<MarketIntelligenceResponse> {
    return fetchOrMock('/market-intelligence', () => ({
        sp500: null, ndx: null, kospi: null,
    }));
}
