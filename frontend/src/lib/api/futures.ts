/**
 * Futures API (KOSPI200 / E-mini)
 *
 * Phase 3.A 분할: lib/api.ts → lib/api/futures.ts
 * 265 lines extracted (analysis, signal, quote, backtest, tickers, contract specs, roll schedule).
 *
 * 외부 의존:
 *   - API_BASE_URL  (./client)
 *   - getCached / setCache  (../cache)
 */

import { API_BASE_URL } from './_client';
import { getCached, setCache } from '../cache';

export interface FuturesLayerScore {
    score: number;
    max_score: number;
    signals: string[];
}

export interface FuturesAnalysis {
    ticker: string;
    direction: 'LONG' | 'SHORT' | 'NEUTRAL';
    total_score: number;
    entry_threshold: number;
    signal_active: boolean;
    layers: {
        zscore: FuturesLayerScore;
        trend: FuturesLayerScore;
        momentum: FuturesLayerScore;
        volume: FuturesLayerScore;
    };
    indicators: {
        zscore: number;
        rsi: number;
        adx: number;
        macd_hist: number;
        atr: number;
        bb_squeeze_ratio: number;
        volume_ratio: number;
    };
    entry_price: number;
    stop_loss: number;
    take_profit: number;
    risk_reward_ratio: number;
    position_size_contracts: number;
    last_updated: string;
}

export interface FuturesSignalData {
    ticker: string;
    direction: string;
    signal_strength: number;
    entry_price: number;
    stop_loss: number;
    take_profit: number;
    atr: number;
    z_score: number;
    risk_reward_ratio: number;
    position_size_contracts: number;
    primary_signals: string[];
    confirmation_filters: string[];
    metadata: Record<string, number>;
    timestamp: string;
}

export interface FuturesTickerInfo {
    ticker: string;
    name: string;
    multiplier: number;
    micro: string | null;
}

export interface FuturesMonteCarloResult {
    var_95: number;
    cvar_99: number;
    worst_mdd: number;
    median_return: number;
    bankruptcy_prob: number;
    return_distribution: { bin: number; count: number }[];
    mdd_distribution: { bin: number; count: number }[];
    return_percentiles: { p5: number; p25: number; p50: number; p75: number; p95: number };
}

export interface FuturesBacktestMetrics {
    total_return_pct: number;
    sharpe_ratio: number;
    sortino_ratio: number;
    calmar_ratio: number;
    cagr: number;
    max_drawdown_pct: number;
    mdd_duration_days: number;
    total_trades: number;
    win_rate: number;
    profit_factor: number;
    avg_win: number;
    avg_loss: number;
    avg_rr: number;
    total_pnl: number;
    total_costs: number;
    long_trades: number;
    short_trades: number;
    long_win_rate: number;
    short_win_rate: number;
    avg_holding_days: number;
    max_consecutive_wins: number;
    max_consecutive_losses: number;
    best_trade_pct: number;
    worst_trade_pct: number;
    exit_reasons: Record<string, number>;
    monte_carlo: FuturesMonteCarloResult;
    // 증거금/CB/롤오버
    margin_call_count: number;
    max_effective_leverage: number;
    avg_margin_utilization: number;
    cb_event_count: number;
    cb_events_detail: { date: string; level: string; pct_change: number }[];
    roll_count: number;
    total_roll_costs: number;
}

export interface FuturesTrade {
    entry_date: string;
    exit_date: string;
    direction: string;
    entry_price: number;
    exit_price: number;
    contracts: number;
    pnl_dollar: number;
    pnl_pct: number;
    holding_days: number;
    exit_reason: string;
}

export interface FuturesBacktestResult {
    ticker: string;
    start_date: string;
    end_date: string;
    initial_equity: number;
    final_equity: number;
    metrics: FuturesBacktestMetrics;
    equity_curve: { date: string; total_value: number; equity: number; drawdown_pct: number; margin_used: number; effective_leverage: number }[];
    trades: FuturesTrade[];
}

export async function fetchFuturesTickers(): Promise<FuturesTickerInfo[]> {
    const res = await fetch(`${API_BASE_URL}/futures/tickers`);
    if (!res.ok) return [];
    const data = await res.json();
    return data.tickers || [];
}

export async function fetchFuturesAnalysis(ticker: string = 'ES=F', period: string = '1y'): Promise<FuturesAnalysis | null> {
    const cacheKey = `futures:${ticker}:${period}`;
    const isDefaultIndicators = (d: FuturesAnalysis) =>
        d.indicators.adx === 0 && d.indicators.atr === 0 && d.indicators.rsi === 50;

    try {
        const res = await fetch(`${API_BASE_URL}/futures/analyze/${encodeURIComponent(ticker)}?period=${period}`);
        if (!res.ok) return getCached<FuturesAnalysis>(cacheKey);
        const data: FuturesAnalysis = await res.json();

        // yfinance 동시 호출 시 첫 응답이 기본값을 반환할 수 있음 → 1회 재시도
        if (isDefaultIndicators(data)) {
            await new Promise(r => setTimeout(r, 2000));
            const retry = await fetch(`${API_BASE_URL}/futures/analyze/${encodeURIComponent(ticker)}?period=${period}`);
            if (retry.ok) {
                const retryData: FuturesAnalysis = await retry.json();
                if (!isDefaultIndicators(retryData)) {
                    setCache(cacheKey, retryData);
                    return retryData;
                }
            }
        }

        setCache(cacheKey, data);
        return data;
    } catch {
        return getCached<FuturesAnalysis>(cacheKey);
    }
}

export async function fetchFuturesSignal(ticker: string = 'ES=F', equity: number = 100000): Promise<{ signal: FuturesSignalData | null; message?: string }> {
    try {
        const res = await fetch(`${API_BASE_URL}/futures/signal/${encodeURIComponent(ticker)}?equity=${equity}`);
        if (!res.ok) return { signal: null };
        return res.json();
    } catch {
        return { signal: null };
    }
}

export async function fetchFuturesQuote(ticker: string = 'ES=F') {
    const res = await fetch(`${API_BASE_URL}/futures/quote/${encodeURIComponent(ticker)}`);
    if (!res.ok) return null;
    return res.json();
}

export async function triggerFuturesBacktest(
    ticker: string,
    startDate: string,
    endDate: string,
    equity: number = 100000,
    isMicro: boolean = false,
    overrides?: { entry_threshold?: number; sl_hard_pct?: number; max_holding_days?: number },
): Promise<FuturesBacktestResult | null> {
    try {
        const params = new URLSearchParams({
            ticker, start_date: startDate, end_date: endDate,
            equity: String(equity), is_micro: String(isMicro),
        });
        if (overrides?.entry_threshold != null) params.set('entry_threshold', String(overrides.entry_threshold));
        if (overrides?.sl_hard_pct != null) params.set('sl_hard_pct', String(overrides.sl_hard_pct));
        if (overrides?.max_holding_days != null) params.set('max_holding_days', String(overrides.max_holding_days));
        const res = await fetch(`${API_BASE_URL}/futures/backtest?${params}`, { method: 'POST' });
        if (!res.ok) return null;
        return res.json();
    } catch {
        return null;
    }
}

export async function fetchFuturesBacktestStatus(): Promise<{ in_progress: boolean; has_result: boolean; progress: number }> {
    try {
        const res = await fetch(`${API_BASE_URL}/futures/backtest/status`);
        if (!res.ok) return { in_progress: false, has_result: false, progress: 0 };
        return res.json();
    } catch {
        return { in_progress: false, has_result: false, progress: 0 };
    }
}

export async function fetchFuturesBacktestResult(): Promise<FuturesBacktestResult | null> {
    try {
        const res = await fetch(`${API_BASE_URL}/futures/backtest/result`);
        if (res.status === 404) return null;
        if (!res.ok) return null;
        return res.json();
    } catch {
        return null;
    }
}

// 롤오버 스케줄
export interface RollScheduleEntry {
    contract: string;
    roll_date: string;
    expiry: string;
    next_contract: string;
}

export async function fetchRollSchedule(year: number = new Date().getFullYear()): Promise<{ schedule: RollScheduleEntry[]; next_roll: { contract: string; roll_date: string; days_remaining: number } | null }> {
    try {
        const res = await fetch(`${API_BASE_URL}/futures/roll-schedule?year=${year}`);
        if (!res.ok) return { schedule: [], next_roll: null };
        return res.json();
    } catch {
        return { schedule: [], next_roll: null };
    }
}

// 상품 규격
export interface ContractSpecs {
    es: { multiplier: number; tick_size: number; tick_value: number; notional: number; initial_margin: number; maintenance_margin: number };
    mes: { multiplier: number; tick_size: number; tick_value: number; notional: number; initial_margin: number; maintenance_margin: number };
    current_session: { name: string; status: string; is_dst: boolean };
    cost_breakdown: { es_round_trip: number; mes_round_trip: number; cost_pct_of_notional: number };
}

export async function fetchContractSpecs(): Promise<ContractSpecs | null> {
    try {
        const res = await fetch(`${API_BASE_URL}/futures/contract-specs`);
        if (!res.ok) return null;
        return res.json();
    } catch {
        return null;
    }
}

