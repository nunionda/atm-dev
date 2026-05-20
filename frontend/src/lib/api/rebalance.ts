/**
 * Rebalance / Universe Backtest API
 * Phase 3.A-2: api.ts → api/rebalance.ts
 *
 * 외부 의존:
 *   - API_BASE_URL, fetchOrMock  (./_client)
 *   - MarketId  (./market)
 */

import { API_BASE_URL, fetchOrMock } from './_client';
import type { MarketId } from './market';

// --- Rebalance Types ---

export interface RebalanceRecommendation {
    rank: number;
    code: string;
    name: string;
    sector: string;
    score: number;
    price: number;
    return_6m?: string;
    signal?: string;
    pnl_pct?: number;
    days_held?: number;
    reason?: string;
    action: 'BUY' | 'HOLD' | 'SELL';
}

export interface RebalanceResult {
    market: string;
    scan_date: string | null;
    total_scanned: number;
    passed_prefilter: number;
    buy: RebalanceRecommendation[];
    hold: RebalanceRecommendation[];
    sell: RebalanceRecommendation[];
}

export interface RebalanceStatus {
    market: string;
    last_scan_date: string | null;
    next_scan_date: string | null;
    current_watchlist_count: number;
    is_scanning: boolean;
}

// --- Rebalance API Functions ---

export async function triggerRebalanceScan(market: MarketId): Promise<RebalanceResult> {
    const response = await fetch(`${API_BASE_URL}/rebalance/scan?market=${market}`, { method: 'POST' });
    if (!response.ok) throw new Error(`Scan failed: ${response.status}`);
    return response.json();
}

export async function fetchRebalanceRecommendations(market: MarketId): Promise<RebalanceResult> {
    return fetchOrMock(`/rebalance/recommendations?market=${market}`, () => ({
        market,
        scan_date: null,
        total_scanned: 0,
        passed_prefilter: 0,
        buy: [],
        hold: [],
        sell: [],
    }));
}

export async function fetchRebalanceStatus(market: MarketId): Promise<RebalanceStatus> {
    return fetchOrMock(`/rebalance/status?market=${market}`, () => ({
        market,
        last_scan_date: null,
        next_scan_date: null,
        current_watchlist_count: 0,
        is_scanning: false,
    }));
}

// --- Universe Backtest Types ---

export interface BacktestMetrics {
    total_return: number;
    cagr: number;
    sharpe_ratio: number;
    sortino_ratio: number;
    calmar_ratio: number;
    max_drawdown: number;
    max_drawdown_date: string;
    total_trades: number;
    win_rate: number;
    profit_factor: number;
    avg_pnl_pct: number;
    avg_holding_days: number;
    final_value: number;
    avg_win_pct: number;
    avg_loss_pct: number;
    best_trade_pct: number;
    worst_trade_pct: number;
    max_consecutive_wins: number;
    max_consecutive_losses: number;
    total_rebalances: number;
    avg_turnover_pct: number;
    time_in_bull_pct: number;
    time_in_bear_pct: number;
    time_in_neutral_pct: number;
}

export interface UniverseBacktestResult {
    market: string;
    strategy: string;  // "momentum" | "smc" | "breakout_retest"
    start_date: string;
    end_date: string;
    metrics: BacktestMetrics;
    equity_curve: EquityPoint[];
    trades: TradeRecord[];
    phase_stats: Record<string, number>;
    monthly_returns: Record<string, number>;
}

export interface BacktestStatus {
    market: string;
    is_running: boolean;
    has_result: boolean;
    start_date: string | null;
    end_date: string | null;
}

// --- Universe Backtest API Functions ---

export async function triggerUniverseBacktest(
    market: MarketId,
    startDate: string,
    endDate: string,
    strategy: string = "momentum",
): Promise<UniverseBacktestResult> {
    const response = await fetch(
        `${API_BASE_URL}/rebalance/backtest?market=${market}&start_date=${startDate}&end_date=${endDate}&strategy=${strategy}`,
        { method: 'POST' },
    );
    if (!response.ok) {
        const detail = await response.text();
        throw new Error(`Backtest failed (${response.status}): ${detail}`);
    }
    return response.json();
}

export async function fetchBacktestResult(market: MarketId): Promise<UniverseBacktestResult | null> {
    try {
        const response = await fetch(`${API_BASE_URL}/rebalance/backtest/result?market=${market}`);
        if (response.status === 404) return null;
        if (!response.ok) return null;
        return response.json();
    } catch {
        return null;
    }
}

export async function fetchBacktestStatus(market: MarketId): Promise<BacktestStatus> {
    return fetchOrMock(`/rebalance/backtest/status?market=${market}`, () => ({
        market,
        is_running: false,
        has_result: false,
        start_date: null,
        end_date: null,
    }));
}

