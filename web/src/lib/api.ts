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

const API_BASE_URL = 'http://localhost:8000/api/v1';

export async function fetchAnalyticsData(ticker: string, period: string = 'ytd', interval: string = '1d'): Promise<AnalyticsResponse> {
    console.log(`[API] Fetching data for ${ticker}, period: ${period}, interval: ${interval}`);
    try {
        const response = await fetch(`${API_BASE_URL}/analyze/${ticker}?period=${period}&interval=${interval}`);
        if (!response.ok) {
            console.error(`[API] HTTP error! status: ${response.status}`);
            throw new Error(`Failed to fetch analytics for ${ticker}. Status: ${response.status}`);
        }
        const data = await response.json();
        console.log(`[API] Successfully parsed JSON for ${ticker}`);
        return data;
    } catch (error) {
        console.error(`[API] Fetch failed for ${ticker}:`, error);
        throw error;
    }
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

export async function fetchMarketOverview(): Promise<MarketOverview | null> {
    try {
        const response = await fetch(`${API_BASE_URL}/market-overview`);
        if (!response.ok) return null;
        return await response.json();
    } catch {
        return null;
    }
}

// --- System State ---

export type SystemStatus = 'INIT' | 'READY' | 'RUNNING' | 'STOPPING' | 'STOPPED' | 'ERROR';

export interface SystemState {
    status: SystemStatus;
    mode: 'PAPER' | 'LIVE';
    started_at: string | null;
    market_phase: 'PRE_MARKET' | 'OPEN' | 'CLOSED';
    next_scan_at: string | null;
    total_equity: number;
    cash: number;
    invested: number;
    daily_pnl: number;
    daily_pnl_pct: number;
    position_count: number;
    max_positions: number;
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

// --- Operations API ---

const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true';

async function fetchOrMock<T>(url: string, mockFn: () => T): Promise<T> {
    if (USE_MOCK) return mockFn();
    const response = await fetch(`${API_BASE_URL}${url}`);
    if (!response.ok) throw new Error(`API error: ${response.status}`);
    return response.json();
}

export async function fetchSystemState(): Promise<SystemState> {
    if (USE_MOCK) { const { mockSystemState } = await import('./mock'); return mockSystemState(); }
    return fetchOrMock('/system/state', () => null as never);
}

export async function fetchPositions(): Promise<Position[]> {
    if (USE_MOCK) { const { mockPositions } = await import('./mock'); return mockPositions(); }
    return fetchOrMock('/positions', () => null as never);
}

export async function fetchOrders(): Promise<Order[]> {
    if (USE_MOCK) { const { mockOrders } = await import('./mock'); return mockOrders(); }
    return fetchOrMock('/orders', () => null as never);
}

export async function fetchSignals(): Promise<Signal[]> {
    if (USE_MOCK) { const { mockSignals } = await import('./mock'); return mockSignals(); }
    return fetchOrMock('/signals/today', () => null as never);
}

export async function fetchRiskMetrics(): Promise<RiskMetrics> {
    if (USE_MOCK) { const { mockRiskMetrics } = await import('./mock'); return mockRiskMetrics(); }
    return fetchOrMock('/risk/metrics', () => null as never);
}

export async function fetchRiskEvents(): Promise<RiskEvent[]> {
    if (USE_MOCK) { const { mockRiskEvents } = await import('./mock'); return mockRiskEvents(); }
    return fetchOrMock('/risk/events', () => null as never);
}

export async function fetchPerformanceSummary(): Promise<PerformanceSummary> {
    if (USE_MOCK) { const { mockPerformanceSummary } = await import('./mock'); return mockPerformanceSummary(); }
    return fetchOrMock('/performance/summary', () => null as never);
}

export async function fetchEquityCurve(): Promise<EquityPoint[]> {
    if (USE_MOCK) { const { mockEquityCurve } = await import('./mock'); return mockEquityCurve(); }
    return fetchOrMock('/performance/equity', () => null as never);
}

export async function fetchTradeHistory(): Promise<TradeRecord[]> {
    if (USE_MOCK) { const { mockTradeHistory } = await import('./mock'); return mockTradeHistory(); }
    return fetchOrMock('/trades', () => null as never);
}

