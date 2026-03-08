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
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 30000);
        const response = await fetch(`${API_BASE_URL}/market-overview`, { signal: controller.signal });
        clearTimeout(timeout);
        if (!response.ok) {
            console.error(`[API] market-overview HTTP ${response.status}`);
            return null;
        }
        const data = await response.json();
        console.log(`[API] market-overview loaded: ${data.indices?.length} indices`);
        return data;
    } catch (error) {
        console.error('[API] market-overview fetch failed:', error);
        return null;
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

// --- System State ---

export type SystemStatus = 'INIT' | 'READY' | 'RUNNING' | 'STOPPING' | 'STOPPED' | 'ERROR';

export type MarketRegime = 'BULL' | 'BEAR' | 'NEUTRAL';

export interface SystemState {
    status: SystemStatus;
    mode: 'PAPER' | 'LIVE';
    started_at: string | null;
    market_phase: 'PRE_MARKET' | 'OPEN' | 'CLOSED';
    market_regime?: MarketRegime;
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

// --- Operations API ---

const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true';

async function fetchOrMock<T>(url: string, mockFn: () => T): Promise<T> {
    if (USE_MOCK) return mockFn();
    const response = await fetch(`${API_BASE_URL}${url}`);
    if (!response.ok) throw new Error(`API error: ${response.status}`);
    return response.json();
}

export async function fetchSystemState(market: MarketId = 'kospi'): Promise<SystemState> {
    if (USE_MOCK) { const { mockSystemState } = await import('./mock'); return mockSystemState(); }
    return fetchOrMock(`/system/state?market=${market}`, () => null as never);
}

export async function fetchPositions(market: MarketId = 'kospi'): Promise<Position[]> {
    if (USE_MOCK) { const { mockPositions } = await import('./mock'); return mockPositions(); }
    return fetchOrMock(`/positions?market=${market}`, () => null as never);
}

export async function fetchOrders(market: MarketId = 'kospi'): Promise<Order[]> {
    if (USE_MOCK) { const { mockOrders } = await import('./mock'); return mockOrders(); }
    return fetchOrMock(`/orders?market=${market}`, () => null as never);
}

export async function fetchSignals(market: MarketId = 'kospi'): Promise<Signal[]> {
    if (USE_MOCK) { const { mockSignals } = await import('./mock'); return mockSignals(); }
    return fetchOrMock(`/signals/today?market=${market}`, () => null as never);
}

export async function fetchRiskMetrics(market: MarketId = 'kospi'): Promise<RiskMetrics> {
    if (USE_MOCK) { const { mockRiskMetrics } = await import('./mock'); return mockRiskMetrics(); }
    return fetchOrMock(`/risk/metrics?market=${market}`, () => null as never);
}

export async function fetchRiskEvents(market: MarketId = 'kospi'): Promise<RiskEvent[]> {
    if (USE_MOCK) { const { mockRiskEvents } = await import('./mock'); return mockRiskEvents(); }
    return fetchOrMock(`/risk/events?market=${market}`, () => null as never);
}

export async function fetchPerformanceSummary(market: MarketId = 'kospi'): Promise<PerformanceSummary> {
    if (USE_MOCK) { const { mockPerformanceSummary } = await import('./mock'); return mockPerformanceSummary(); }
    return fetchOrMock(`/performance/summary?market=${market}`, () => null as never);
}

export async function fetchEquityCurve(market: MarketId = 'kospi'): Promise<EquityPoint[]> {
    if (USE_MOCK) { const { mockEquityCurve } = await import('./mock'); return mockEquityCurve(); }
    return fetchOrMock(`/performance/equity?market=${market}`, () => null as never);
}

export async function fetchTradeHistory(market: MarketId = 'kospi'): Promise<TradeRecord[]> {
    if (USE_MOCK) { const { mockTradeHistory } = await import('./mock'); return mockTradeHistory(); }
    return fetchOrMock(`/trades?market=${market}`, () => null as never);
}

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
    strategy: string;  // "momentum" | "smc"
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

