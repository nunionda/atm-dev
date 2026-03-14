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

import { getCached, setCache } from './cache';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';

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

// --- Operations API ---

const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true';

async function fetchOrMock<T>(url: string, mockFn: () => T): Promise<T> {
    if (USE_MOCK) return mockFn();
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 8000);
    try {
        const response = await fetch(`${API_BASE_URL}${url}`, { signal: controller.signal });
        if (!response.ok) throw new Error(`API error: ${response.status}`);
        return response.json();
    } finally {
        clearTimeout(timeout);
    }
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

// --- Market Intelligence Types ---

export type IndexTrend = 'STRONG_BULL' | 'BULL' | 'NEUTRAL' | 'BEAR' | 'CRISIS';
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


// ══════════════════════════════════════════
// Futures Trading API
// ══════════════════════════════════════════

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
    equity_curve: { date: string; total_value: number; equity: number; drawdown_pct: number }[];
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
    try {
        const res = await fetch(`${API_BASE_URL}/futures/analyze/${encodeURIComponent(ticker)}?period=${period}`);
        if (!res.ok) return getCached<FuturesAnalysis>(cacheKey);
        const data = await res.json();
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
): Promise<FuturesBacktestResult | null> {
    try {
        const params = new URLSearchParams({
            ticker, start_date: startDate, end_date: endDate,
            equity: String(equity), is_micro: String(isMicro),
        });
        const res = await fetch(`${API_BASE_URL}/futures/backtest?${params}`, { method: 'POST' });
        if (!res.ok) return null;
        return res.json();
    } catch {
        return null;
    }
}

export async function fetchFuturesBacktestStatus(): Promise<{ in_progress: boolean; has_result: boolean }> {
    try {
        const res = await fetch(`${API_BASE_URL}/futures/backtest/status`);
        if (!res.ok) return { in_progress: false, has_result: false };
        return res.json();
    } catch {
        return { in_progress: false, has_result: false };
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

