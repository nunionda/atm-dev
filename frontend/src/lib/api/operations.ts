/**
 * Operations API
 * Phase 3.A-2: api.ts → api/operations.ts
 *
 * Domain: system state, positions, orders, signals, risk metrics/events,
 *         performance summary/equity/trades.
 *
 * 외부 의존:
 *   - API_BASE_URL, USE_MOCK, fetchOrMock  (./_client)
 *   - MarketId  (./market)
 */

import { fetchOrMock, USE_MOCK } from './_client';
import type { MarketId } from './market';

// --- System State ---

export type SystemStatus = 'INIT' | 'READY' | 'RUNNING' | 'STOPPING' | 'STOPPED' | 'ERROR';

export type SystemMarketRegime = 'BULL' | 'BEAR' | 'NEUTRAL';

export interface SystemState {
    status: SystemStatus;
    mode: 'PAPER' | 'LIVE';
    started_at: string | null;
    market_phase: 'PRE_MARKET' | 'OPEN' | 'CLOSED';
    market_regime?: SystemMarketRegime;
    next_scan_at: string | null;
    total_equity: number;
    cash: number;
    invested: number;
    daily_pnl: number;
    daily_pnl_pct: number;
    position_count: number;
    max_positions: number;
    market_id?: string;
    currency?: string;
    currency_symbol?: string;
    market_label?: string;
}

// --- Positions ---

export type PositionStatus = 'PENDING' | 'ACTIVE' | 'CLOSING' | 'CLOSED';

export interface Position {
    id: string;
    stock_code: string;
    stock_name: string;
    status: PositionStatus;
    quantity: number;
    entry_price: number;
    current_price: number;
    pnl: number;
    pnl_pct: number;
    stop_loss: number;
    take_profit: number;
    trailing_stop: number;
    highest_price: number;
    entry_date: string;
    days_held: number;
    max_holding_days: number;
    weight_pct: number;
}

// --- Orders ---

export type OrderSide = 'BUY' | 'SELL';
export type OrderType = 'LIMIT' | 'MARKET';
export type OrderStatus = 'PENDING' | 'FILLED' | 'PARTIAL' | 'CANCELLED' | 'REJECTED';

export interface Order {
    id: string;
    stock_code: string;
    stock_name: string;
    side: OrderSide;
    order_type: OrderType;
    status: OrderStatus;
    price: number;
    filled_price: number | null;
    quantity: number;
    filled_quantity: number;
    created_at: string;
    filled_at: string | null;
    reason: string;
}

// --- Signals ---

export type SignalType = 'BUY' | 'SELL';

export interface Signal {
    id: string;
    stock_code: string;
    stock_name: string;
    type: SignalType;
    price: number;
    reason: string;
    strength: number;
    detected_at: string;
}

// --- Risk Metrics ---

export interface RiskMetrics {
    daily_pnl_pct: number;
    daily_loss_limit: number;
    mdd: number;
    mdd_limit: number;
    cash_ratio: number;
    min_cash_ratio: number;
    consecutive_stops: number;
    max_consecutive_stops: number;
    daily_trade_amount: number;
    max_daily_trade_amount: number;
    is_trading_halted: boolean;
    halt_reason: string | null;
}

export interface RiskEvent {
    id: string;
    type: 'WARNING' | 'BREACH' | 'HALT' | 'INFO';
    message: string;
    value: number | null;
    limit: number | null;
    timestamp: string;
}

// --- Performance ---

export interface PerformanceSummary {
    total_return_pct: number;
    total_trades: number;
    win_rate: number;
    avg_win_pct: number;
    avg_loss_pct: number;
    profit_factor: number;
    sharpe_ratio: number;
    max_drawdown_pct: number;
    avg_holding_days: number;
    best_trade_pct: number;
    worst_trade_pct: number;
}

export interface EquityPoint {
    date: string;
    equity: number;
    drawdown_pct: number;
}

export interface TradeRecord {
    id: string;
    stock_code: string;
    stock_name: string;
    entry_date: string;
    exit_date: string;
    entry_price: number;
    exit_price: number;
    quantity: number;
    pnl: number;
    pnl_pct: number;
    exit_reason: string;
    holding_days: number;
}


export async function fetchSystemState(market: MarketId = 'kospi'): Promise<SystemState> {
    if (USE_MOCK) { const { mockSystemState } = await import('../mock'); return mockSystemState(); }
    return fetchOrMock(`/system/state?market=${market}`, () => null as never);
}

export async function fetchPositions(market: MarketId = 'kospi'): Promise<Position[]> {
    if (USE_MOCK) { const { mockPositions } = await import('../mock'); return mockPositions(); }
    return fetchOrMock(`/positions?market=${market}`, () => null as never);
}

export async function fetchOrders(market: MarketId = 'kospi'): Promise<Order[]> {
    if (USE_MOCK) { const { mockOrders } = await import('../mock'); return mockOrders(); }
    return fetchOrMock(`/orders?market=${market}`, () => null as never);
}

export async function fetchSignals(market: MarketId = 'kospi'): Promise<Signal[]> {
    if (USE_MOCK) { const { mockSignals } = await import('../mock'); return mockSignals(); }
    return fetchOrMock(`/signals/today?market=${market}`, () => null as never);
}

export async function fetchRiskMetrics(market: MarketId = 'kospi'): Promise<RiskMetrics> {
    if (USE_MOCK) { const { mockRiskMetrics } = await import('../mock'); return mockRiskMetrics(); }
    return fetchOrMock(`/risk/metrics?market=${market}`, () => null as never);
}

export async function fetchRiskEvents(market: MarketId = 'kospi'): Promise<RiskEvent[]> {
    if (USE_MOCK) { const { mockRiskEvents } = await import('../mock'); return mockRiskEvents(); }
    return fetchOrMock(`/risk/events?market=${market}`, () => null as never);
}

export async function fetchPerformanceSummary(market: MarketId = 'kospi'): Promise<PerformanceSummary> {
    if (USE_MOCK) { const { mockPerformanceSummary } = await import('../mock'); return mockPerformanceSummary(); }
    return fetchOrMock(`/performance/summary?market=${market}`, () => null as never);
}

export async function fetchEquityCurve(market: MarketId = 'kospi'): Promise<EquityPoint[]> {
    if (USE_MOCK) { const { mockEquityCurve } = await import('../mock'); return mockEquityCurve(); }
    return fetchOrMock(`/performance/equity?market=${market}`, () => null as never);
}

export async function fetchTradeHistory(market: MarketId = 'kospi'): Promise<TradeRecord[]> {
    if (USE_MOCK) { const { mockTradeHistory } = await import('../mock'); return mockTradeHistory(); }
    return fetchOrMock(`/trades?market=${market}`, () => null as never);
}
