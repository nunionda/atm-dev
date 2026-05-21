/**
 * Simulation / Replay API
 * Phase 3.A-2: api.ts → api/sim.ts
 *
 * Domain: force-liquidate, simulation controller (start/stop/reset),
 *         replay control (pause/resume/speed), replay results CRUD.
 *
 * 외부 의존:
 *   - API_BASE_URL  (./_client)
 *   - MarketId  (./market)
 */

import { API_BASE_URL } from './_client';
import type { MarketId } from './market';

// --- Force Liquidate ---

export interface ForceLiquidateResult {
    status: string;
    market: string;
    positions_closed: number;
    details: {
        stock_code: string;
        stock_name: string;
        quantity: number;
        sell_price: number;
        entry_price: number;
    }[];
}

export async function forceLiquidateAll(market: MarketId): Promise<ForceLiquidateResult> {
    const res = await fetch(`${API_BASE_URL}/sim/force-liquidate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ market }),
    });
    if (!res.ok) throw new Error(`Force liquidate failed: ${res.status}`);
    return res.json();
}

// --- Simulation Control Types ---

export type StrategyMode = 'momentum' | 'smc' | 'breakout_retest' | 'mean_reversion' | 'arbitrage' | 'multi';

export interface ReplayStatus {
    active: boolean;
    current_date: string;
    progress_pct: number;
    total_days: number;
    speed: number;
    paused: boolean;
    completed: boolean;
    start_date?: string;
    end_date?: string;
}

export interface ReplayProgress {
    current_date: string;
    progress_pct: number;
    day_index: number;
    total_days: number;
    speed: number;
    paused: boolean;
    completed?: boolean;
    status?: string;
    error?: string;
}

export interface SimControllerStatus {
    mode: string;
    markets: Record<string, {
        is_running: boolean;
        strategy_mode: StrategyMode;
        total_equity: number;
        cash: number;
        position_count: number;
        replay?: ReplayStatus;
    }>;
    available_markets: string[];
    available_strategies: StrategyMode[];
}

export interface SimControlResult {
    status: string;
    market?: string;
    strategy?: string;
    initial_capital?: number;
    detail?: string;
    total_days?: number;
    start_date?: string;
    end_date?: string;
}

export async function fetchSimControllerStatus(): Promise<SimControllerStatus> {
    const res = await fetch(`${API_BASE_URL}/sim/status`);
    if (!res.ok) throw new Error(`Failed: ${res.status}`);
    return res.json();
}

export async function simStart(
    market: MarketId,
    strategy?: StrategyMode,
    replayOptions?: {
        startDate?: string;   // YYYYMMDD
        endDate?: string;     // YYYYMMDD
        replaySpeed?: number; // 1.0=1초/일
    },
): Promise<SimControlResult> {
    const body: Record<string, unknown> = { market, strategy_mode: strategy };
    if (replayOptions?.startDate) body.start_date = replayOptions.startDate;
    if (replayOptions?.endDate) body.end_date = replayOptions.endDate;
    if (replayOptions?.replaySpeed != null) body.replay_speed = replayOptions.replaySpeed;
    const res = await fetch(`${API_BASE_URL}/sim/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });
    return res.json();
}

export async function simStop(market: MarketId): Promise<SimControlResult> {
    const res = await fetch(`${API_BASE_URL}/sim/stop`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ market }),
    });
    return res.json();
}

export async function simReset(market: MarketId, strategy?: StrategyMode): Promise<SimControlResult> {
    const res = await fetch(`${API_BASE_URL}/sim/reset`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ market, strategy_mode: strategy }),
    });
    return res.json();
}

// --- Replay Control ---

export async function replayPause(market: MarketId): Promise<SimControlResult> {
    const res = await fetch(`${API_BASE_URL}/sim/replay/pause`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ market }),
    });
    return res.json();
}

export async function replayResume(market: MarketId): Promise<SimControlResult> {
    const res = await fetch(`${API_BASE_URL}/sim/replay/resume`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ market }),
    });
    return res.json();
}

export async function replaySetSpeed(market: MarketId, speed: number): Promise<SimControlResult> {
    const res = await fetch(`${API_BASE_URL}/sim/replay/speed`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ market, speed }),
    });
    return res.json();
}

// --- Replay Results ---

export interface ReplayResultSummary {
    result_id: string;
    market: string;
    strategy: string;
    start_date: string;
    end_date: string;
    initial_capital: number;
    final_equity: number;
    total_return_pct: number;
    sharpe_ratio: number;
    max_drawdown_pct: number;
    total_trades: number;
    win_rate: number;
    profit_factor: number;
    created_at: string;
}

export interface ReplayResultFull extends ReplayResultSummary {
    equity_curve: { date: string; equity: number; drawdown_pct: number }[];
    trades: {
        id: string; stock_code: string; stock_name: string;
        entry_date: string; exit_date: string; entry_price: number;
        exit_price: number; quantity: number; pnl: number;
        pnl_pct: number; exit_reason: string; holding_days: number;
    }[];
    metrics: Record<string, number>;
}

export async function saveReplayResult(market: MarketId): Promise<{ status: string; result_id: string }> {
    const res = await fetch(`${API_BASE_URL}/replay/results/save`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ market }),
    });
    if (!res.ok) throw new Error(`Failed: ${res.status}`);
    return res.json();
}

export async function listReplayResults(
    market?: MarketId,
    limit: number = 20,
): Promise<{ results: ReplayResultSummary[]; count: number }> {
    const params = new URLSearchParams();
    if (market) params.set('market', market);
    params.set('limit', String(limit));
    const res = await fetch(`${API_BASE_URL}/replay/results?${params}`);
    if (!res.ok) throw new Error(`Failed: ${res.status}`);
    return res.json();
}

export async function getReplayResult(resultId: string): Promise<ReplayResultFull> {
    const res = await fetch(`${API_BASE_URL}/replay/results/${resultId}`);
    if (!res.ok) throw new Error(`Failed: ${res.status}`);
    return res.json();
}

export async function deleteReplayResult(resultId: string): Promise<void> {
    const res = await fetch(`${API_BASE_URL}/replay/results/${resultId}`, {
        method: 'DELETE',
    });
    if (!res.ok) throw new Error(`Failed: ${res.status}`);
}
