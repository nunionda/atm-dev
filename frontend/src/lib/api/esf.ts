/**
 * ESF (E-mini Scalping Framework) API
 *
 * Phase 3.A 분할: lib/api.ts → lib/api/esf.ts
 * 608 lines extracted (intraday types, journal evolution system, A/B experiments).
 *
 * 외부 의존: `API_BASE_URL` (./client)
 */

import { API_BASE_URL } from './_client';

// ══════════════════════════════════════════
// ESF Intraday Types
// ══════════════════════════════════════════

export interface ESFAMTState {
    market_state: 'BALANCE' | 'IMBALANCE_BULL' | 'IMBALANCE_BEAR';
    market_state_score: number;
    location: {
        zone: 'AT_POC' | 'ABOVE_VAH' | 'BELOW_VAL' | 'IN_VALUE' | 'AT_LVN';
        score: number;
        poc: number;
        vah: number;
        val: number;
    };
    aggression: {
        detected: boolean;
        direction: 'BULLISH' | 'BEARISH' | 'NEUTRAL';
        score: number;
    };
}

export interface ESFLayerScore {
    score: number;
    max_score: number;
    signals: string[];
}

export interface ESFRegimeInfo {
    regime: 'BULL' | 'NEUTRAL' | 'BEAR' | 'CRISIS';
    trend_score: number;
    recommended_strategy: string;
    confidence: number;
    components: Record<string, number>;
}

export interface ESFAnalysis {
    ticker: string;
    session_status: string;
    amt: ESFAMTState;
    layers: {
        amt_location: ESFLayerScore;
        zscore: ESFLayerScore;
        momentum: ESFLayerScore;
        volume_aggression: ESFLayerScore;
    };
    total_score: number;
    grade: 'A' | 'B' | 'C' | 'NO_TRADE';
    direction: 'LONG' | 'SHORT' | 'NEUTRAL';
    entry_price: number;
    stop_loss: number;
    take_profit: number;
    risk_reward_ratio: number;
    contracts: number;
    z_score: number;
    atr: number;
    indicators: Record<string, number>;
    regime?: ESFRegimeInfo;
    magnetic_ma?: {
        rankings: Array<{
            period: number; type: string;
            reversion_rate: number; avg_reversion_bars: number;
            avg_distance_atr: number; magnetic_score: number;
            current_value: number; current_distance_atr: number;
            total_samples: number;
        }>;
        best: {
            period: number; type: string;
            reversion_rate: number; avg_reversion_bars: number;
            avg_distance_atr: number; magnetic_score: number;
            current_value: number; current_distance_atr: number;
            total_samples: number;
        } | null;
    };
    vwatr_zones?: VWATRZone[];
}

export interface VWATRZone {
    ma_type: string;
    ma_period: number;
    ma_value: number;
    support_lower: number;
    support_upper: number;
    resistance_lower: number;
    resistance_upper: number;
    strength: number;
    zone_type: 'SUPPORT' | 'RESISTANCE';
    distance_atr: number;
}

export interface VolumeProfileNode {
    price: number;
    volume: number;
}

export interface VolumeProfileData {
    poc: number;
    vah: number;
    val: number;
    nodes: VolumeProfileNode[];
    lvn_levels: number[];
}

export interface ESFSessionStatus {
    is_rth: boolean;
    current_time_et: string;
    session: string;
    rth_start: string;
    rth_end: string;
}

export interface ESFCandle {
    datetime: string;
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
    rsi_14: number | null;
    adx: number | null;
    plus_di: number | null;
    minus_di: number | null;
    macd: number | null;
    macd_signal: number | null;
    macd_diff: number | null;
    zscore: number | null;
    atr_14: number | null;
    bb_hband: number | null;
    bb_lband: number | null;
    bb_mavg: number | null;
    ema_fast: number | null;
    ema_mid: number | null;
    ema_slow: number | null;
    magnetic_ma: number | null;
    vwatr: number | null;
}

export interface IntradayTrade {
    entry_time: string;
    exit_time: string;
    direction: string;
    entry_price: number;
    exit_price: number;
    contracts: number;
    pnl: number;
    pnl_pct: number;
    holding_bars: number;
    exit_reason: string;
    grade: string;
}

export interface SessionSummary {
    date: string;
    trades: number;
    wins: number;
    losses: number;
    total_pnl: number;
    max_drawdown: number;
}

export interface IntradayMetrics {
    total_return_pct: number;
    total_pnl: number;
    sharpe_ratio: number;
    sortino_ratio: number;
    max_drawdown_pct: number;
    win_rate: number;
    profit_factor: number;
    total_trades: number;
    sessions_traded: number;
    avg_trades_per_session: number;
    best_session_pnl: number;
    worst_session_pnl: number;
    session_win_rate: number;
    avg_holding_bars: number;
    avg_holding_minutes: number;
    max_consecutive_wins: number;
    max_consecutive_losses: number;
    exit_reason_distribution: Record<string, number>;
    long_trades: number;
    short_trades: number;
    long_win_rate: number;
    short_win_rate: number;
}

export interface ESFBacktestResult {
    metrics: IntradayMetrics;
    equity_curve: { timestamp: string; equity: number }[];
    trades: IntradayTrade[];
    sessions: SessionSummary[];
    monte_carlo: {
        var_95: number;
        cvar_99: number;
        worst_mdd: number;
        bankruptcy_prob: number;
        median_return: number;
        paths_count: number;
    };
}

export interface ESFBacktestParams {
    ticker: string;
    period: string;
    initial_equity: number;
    is_micro: boolean;
    mode?: 'intraday' | 'daily';
    start_date?: string;  // YYYYMMDD, daily mode only
    end_date?: string;    // YYYYMMDD, daily mode only
    trend_adaptive?: boolean;  // trend-adaptive regime detection (daily only)
}

// ══════════════════════════════════════════
// ESF Intraday API
// ══════════════════════════════════════════

export async function fetchESFTickers(): Promise<any[]> {
    const res = await fetch(`${API_BASE_URL}/esf/tickers`);
    if (!res.ok) throw new Error('Failed to fetch ESF tickers');
    return res.json();
}

export async function fetchESFAnalysis(
    ticker: string = 'ES=F',
    interval: string = '15m',
    period: string = '60d',
): Promise<ESFAnalysis> {
    const params = new URLSearchParams({ interval, period });
    const res = await fetch(`${API_BASE_URL}/esf/analyze/${encodeURIComponent(ticker)}?${params}`);
    if (!res.ok) throw new Error('Failed to fetch ESF analysis');
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const raw: any = await res.json();

    // API returns amt_state (different shape) — normalize to frontend ESFAnalysis type
    const amtRaw = raw.amt_state || {};
    const msRaw = amtRaw.market_state;
    const amt: ESFAMTState = {
        market_state: Array.isArray(msRaw) ? msRaw[0] : (msRaw || 'BALANCE'),
        market_state_score: Array.isArray(msRaw) ? (msRaw[1] || 0) : 0,
        location: {
            zone: amtRaw.location?.zone || 'IN_VALUE',
            score: amtRaw.location?.score || 0,
            poc: raw.volume_profile?.poc || 0,
            vah: raw.volume_profile?.vah || 0,
            val: raw.volume_profile?.val || 0,
        },
        aggression: {
            detected: amtRaw.aggression?.detected || false,
            direction: amtRaw.aggression?.direction || 'NEUTRAL',
            score: amtRaw.aggression?.score || 0,
        },
    };

    return {
        ticker: raw.ticker,
        session_status: raw.session_status || '',
        amt,
        layers: raw.layers,
        total_score: raw.total_score,
        grade: raw.grade === 'D' ? 'NO_TRADE' : raw.grade,
        direction: raw.direction,
        entry_price: raw.indicators?.price || 0,
        stop_loss: raw.stop_loss || 0,
        take_profit: raw.take_profit || 0,
        risk_reward_ratio: raw.rr_ratio || 0,
        contracts: raw.contracts || 0,
        z_score: raw.indicators?.zscore || 0,
        atr: raw.indicators?.atr || 0,
        indicators: raw.indicators || {},
        signal_active: raw.signal_active || false,
        regime: raw.regime || undefined,
        magnetic_ma: raw.magnetic_ma || undefined,
        vwatr_zones: raw.vwatr_zones || undefined,
    } as ESFAnalysis;
}

export async function fetchESFSignal(
    ticker: string = 'ES=F',
    equity: number = 10000,
    is_micro: boolean = true,
): Promise<ESFAnalysis> {
    const params = new URLSearchParams({ equity: equity.toString(), is_micro: is_micro.toString() });
    const res = await fetch(`${API_BASE_URL}/esf/signal/${encodeURIComponent(ticker)}?${params}`);
    if (!res.ok) throw new Error('Failed to fetch ESF signal');
    return res.json();
}

export async function fetchESFSessionStatus(): Promise<ESFSessionStatus> {
    const res = await fetch(`${API_BASE_URL}/esf/session-status`);
    if (!res.ok) throw new Error('Failed to fetch session status');
    return res.json();
}

export async function fetchESFVolumeProfile(
    ticker: string = 'ES=F',
    period: string = '5d',
    interval: string = '15m',
): Promise<VolumeProfileData> {
    const params = new URLSearchParams({ period, interval });
    const res = await fetch(`${API_BASE_URL}/esf/volume-profile/${encodeURIComponent(ticker)}?${params}`);
    if (!res.ok) throw new Error('Failed to fetch volume profile');
    return res.json();
}

export async function fetchESFCandles(
    ticker: string = 'ES=F',
    interval: string = '15m',
    period: string = '5d',
): Promise<{ ticker: string; interval: string; period: string; count: number; candles: ESFCandle[] }> {
    const params = new URLSearchParams({ interval, period });
    const res = await fetch(`${API_BASE_URL}/esf/candles/${encodeURIComponent(ticker)}?${params}`);
    if (!res.ok) throw new Error('Failed to fetch ESF candles');
    return res.json();
}

export async function triggerESFBacktest(params: ESFBacktestParams): Promise<{ status: string }> {
    const res = await fetch(`${API_BASE_URL}/esf/backtest`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(params),
    });
    if (!res.ok) throw new Error('Failed to start ESF backtest');
    return res.json();
}

export async function fetchESFBacktestStatus(): Promise<{ status: string; progress: number }> {
    const res = await fetch(`${API_BASE_URL}/esf/backtest/status`);
    if (!res.ok) throw new Error('Failed to fetch backtest status');
    return res.json();
}

export async function fetchESFBacktestResult(): Promise<ESFBacktestResult> {
    const res = await fetch(`${API_BASE_URL}/esf/backtest/result`);
    if (!res.ok) throw new Error('Failed to fetch backtest result');
    const raw: any = await res.json();

    // Normalize trade fields: backend uses pnl_dollar, frontend expects pnl
    if (raw.trades) {
        raw.trades = raw.trades.map((t: any) => ({
            ...t,
            pnl: t.pnl_dollar ?? t.pnl ?? 0,
        }));
    }

    // Daily mode returns FuturesBacktester shape — normalize to ESFBacktestResult
    if (raw.metrics && !raw.sessions) {
        // Map equity_curve: {date, total_value} → {timestamp, equity}
        if (raw.equity_curve) {
            raw.equity_curve = raw.equity_curve.map((e: any) => ({
                timestamp: e.date ?? e.timestamp,
                equity: e.total_value ?? e.equity ?? 0,
                drawdown_pct: e.drawdown_pct ?? 0,
            }));
        }
        // Ensure monte_carlo exists
        if (!raw.monte_carlo && raw.metrics?.monte_carlo) {
            raw.monte_carlo = raw.metrics.monte_carlo;
        }
    }

    return raw as ESFBacktestResult;
}

// ══════════════════════════════════════════
// ESF Strategy Evolution System
// ══════════════════════════════════════════

export interface ESFHypothesis {
  hypothesis_id: number;
  trade_date: string;
  ticker: string;
  variant_id: number | null;
  experiment_id: number | null;
  direction: 'LONG' | 'SHORT' | 'NEUTRAL';
  entry_price: number;
  stop_loss: number;
  take_profit: number;
  total_score: number;
  grade: string;
  confidence: number;
  regime: string;
  entry_hour_et: number | null;
  reasoning_json: Record<string, any>;
  params_json: Record<string, any> | null;
  status: 'PENDING' | 'ACTIVE' | 'CLOSED' | 'SKIPPED';
  created_at: string;
  updated_at: string;
  // Extra fields from generation
  risk_reward_ratio?: number;
  contracts?: number;
  primary_signals?: string[];
}

export interface ESFResult {
  result_id: number;
  hypothesis_id: number;
  actual_entry_price: number;
  actual_exit_price: number;
  actual_direction: string;
  contracts: number;
  pnl_dollars: number;
  pnl_pct: number;
  is_win: number;
  exit_reason: string;
  holding_minutes: number;
  direction_correct: number;
  sl_hit: number;
  tp_hit: number;
  created_at: string;
}

export interface ESFVariant {
  variant_id: number;
  name: string;
  description: string;
  is_baseline: number;
  is_active: number;
  param_overrides_json: Record<string, any>;
  created_at: string;
  updated_at: string;
}

export interface ESFExperiment {
  experiment_id: number;
  name: string;
  description: string;
  status: 'RUNNING' | 'PAUSED' | 'CONCLUDED';
  variant_a_id: number;
  variant_b_id: number;
  min_trades_per_variant: number;
  max_days: number;
  winner_variant_id: number | null;
  conclusion_reason: string | null;
  start_date: string;
  end_date: string | null;
  created_at: string;
}

export interface ESFCumulativeStat {
  stat_id: number;
  dimension: string;
  dimension_value: string;
  variant_id: number | null;
  total_trades: number;
  wins: number;
  losses: number;
  win_rate: number;
  total_pnl: number;
  avg_pnl: number;
  sharpe_approx: number;
  profit_factor: number;
  avg_holding_minutes: number;
  direction_accuracy: number;
}

export interface ESFExperimentStatus {
  experiment_id: number;
  experiment_name: string;
  status: string;
  ready: boolean;
  variant_a: { name: string; variant_id: number; trades: number; wins: number; win_rate: number; avg_pnl: number; total_pnl: number; sharpe: number };
  variant_b: { name: string; variant_id: number; trades: number; wins: number; win_rate: number; avg_pnl: number; total_pnl: number; sharpe: number };
  min_trades_per_variant: number;
  p_value: number | null;
  days_elapsed: number;
  max_days: number;
}

// ── ESF Journal API ──

export async function createHypothesis(ticker = 'ES=F', variantId?: number): Promise<ESFHypothesis> {
  const res = await fetch(`${API_BASE_URL}/esf/journal/hypothesis`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ticker, variant_id: variantId ?? null }),
  });
  // 400 means no signal / no data — return the error body so hook can show it
  if (res.status === 400) return res.json();
  if (!res.ok) throw new Error(`createHypothesis failed: ${res.status}`);
  return res.json();
}

export async function createABHypotheses(ticker: string, experimentId: number): Promise<ESFHypothesis[]> {
  const res = await fetch(`${API_BASE_URL}/esf/journal/hypothesis/ab`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ticker, experiment_id: experimentId }),
  });
  if (!res.ok) throw new Error(`createABHypotheses failed: ${res.status}`);
  return res.json();
}

export async function fetchTodayHypotheses(): Promise<ESFHypothesis[]> {
  const res = await fetch(`${API_BASE_URL}/esf/journal/hypothesis/today`);
  if (!res.ok) throw new Error(`fetchTodayHypotheses failed: ${res.status}`);
  const data = await res.json();
  return Array.isArray(data) ? data : (data.items ?? []);
}

export async function fetchHypotheses(params: {
  offset?: number; limit?: number; direction?: string; regime?: string; grade?: string;
  date_from?: string; date_to?: string;
} = {}): Promise<{ items: ESFHypothesis[]; total: number }> {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => { if (v != null) qs.set(k, String(v)); });
  const res = await fetch(`${API_BASE_URL}/esf/journal/hypotheses?${qs}`);
  if (!res.ok) throw new Error(`fetchHypotheses failed: ${res.status}`);
  return res.json();
}

export async function recordResult(data: {
  hypothesis_id: number; actual_entry_price: number; actual_exit_price: number;
  actual_direction?: string; contracts?: number; exit_reason?: string;
  holding_minutes?: number; actual_high?: number; actual_low?: number; actual_close?: number;
}): Promise<ESFResult> {
  const res = await fetch(`${API_BASE_URL}/esf/journal/result`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`recordResult failed: ${res.status}`);
  return res.json();
}

export async function skipHypothesis(hypothesisId: number, reason = ''): Promise<void> {
  await fetch(`${API_BASE_URL}/esf/journal/hypothesis/${hypothesisId}/skip`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason }),
  });
}

export async function fetchCumulativeStats(dimension?: string, variantId?: number): Promise<ESFCumulativeStat[]> {
  const qs = new URLSearchParams();
  if (dimension) qs.set('dimension', dimension);
  if (variantId != null) qs.set('variant_id', String(variantId));
  const res = await fetch(`${API_BASE_URL}/esf/journal/stats?${qs}`);
  if (!res.ok) throw new Error(`fetchCumulativeStats failed: ${res.status}`);
  const data = await res.json();
  return Array.isArray(data) ? data : (data.items ?? []);
}

export async function fetchStatsComparison(variantAId: number, variantBId: number): Promise<{ variant_a: ESFCumulativeStat[]; variant_b: ESFCumulativeStat[] }> {
  const res = await fetch(`${API_BASE_URL}/esf/journal/stats/comparison?variant_a_id=${variantAId}&variant_b_id=${variantBId}`);
  if (!res.ok) throw new Error(`fetchStatsComparison failed: ${res.status}`);
  return res.json();
}

export async function fetchStatsTrends(days = 30): Promise<any[]> {
  const res = await fetch(`${API_BASE_URL}/esf/journal/stats/trends?days=${days}`);
  if (!res.ok) throw new Error(`fetchStatsTrends failed: ${res.status}`);
  const data = await res.json();
  return Array.isArray(data) ? data : (data.items ?? []);
}

export async function createVariant(data: { name: string; description?: string; param_overrides?: Record<string, any> }): Promise<ESFVariant> {
  const res = await fetch(`${API_BASE_URL}/esf/journal/variants`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`createVariant failed: ${res.status}`);
  return res.json();
}

export async function fetchVariants(): Promise<ESFVariant[]> {
  const res = await fetch(`${API_BASE_URL}/esf/journal/variants`);
  if (!res.ok) throw new Error(`fetchVariants failed: ${res.status}`);
  const data = await res.json();
  return Array.isArray(data) ? data : (data.items ?? []);
}

export async function createExperiment(data: {
  name: string; variant_a_id: number; variant_b_id: number;
  min_trades?: number; max_days?: number; description?: string;
}): Promise<ESFExperiment> {
  const res = await fetch(`${API_BASE_URL}/esf/journal/experiments`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`createExperiment failed: ${res.status}`);
  return res.json();
}

export async function fetchExperiments(): Promise<ESFExperiment[]> {
  const res = await fetch(`${API_BASE_URL}/esf/journal/experiments`);
  if (!res.ok) throw new Error(`fetchExperiments failed: ${res.status}`);
  const data = await res.json();
  return Array.isArray(data) ? data : (data.items ?? []);
}

export async function fetchExperimentStatus(experimentId: number): Promise<ESFExperimentStatus> {
  const res = await fetch(`${API_BASE_URL}/esf/journal/experiments/${experimentId}`);
  if (!res.ok) throw new Error(`fetchExperimentStatus failed: ${res.status}`);
  return res.json();
}

export async function concludeExperiment(experimentId: number): Promise<any> {
  const res = await fetch(`${API_BASE_URL}/esf/journal/experiments/${experimentId}/conclude`, { method: 'POST' });
  if (!res.ok) throw new Error(`concludeExperiment failed: ${res.status}`);
  return res.json();
}

export async function graduateWinner(experimentId: number): Promise<any> {
  const res = await fetch(`${API_BASE_URL}/esf/journal/experiments/${experimentId}/graduate`, { method: 'POST' });
  if (!res.ok) throw new Error(`graduateWinner failed: ${res.status}`);
  return res.json();
}

// ══════════════════════════════════════════
// Paper Trading (Decision Engine → SimPosition)
// ══════════════════════════════════════════

export interface FuturesPaperPosition {
  position_id: string;
  ticker: string;
  direction: 'LONG' | 'SHORT';
  contracts: number;
  contract_multiplier: number;
  tick_value: number;
  entry_price: number;
  stop_loss: number;
  take_profit: number;
  status: 'OPEN' | 'SL_HIT' | 'TP_HIT' | 'MANUAL_CLOSE' | 'CLOSED';
  exit_price: number | null;
  exit_reason: string | null;
  opened_at: string;
  closed_at: string | null;
  last_price: number | null;
  last_price_at: string | null;
  hypothesis_id: number | null;
  trailing_high: number | null;
  trailing_stop: number | null;
  created_at: string;
  updated_at: string;
}

export interface PaperRiskStatus {
  realized_pnl_today: number;
  daily_loss_limit: number;
  limit_reached: boolean;
  starting_equity: number;
  max_concurrent: number;
  open_count: number;
}

export async function openPaperPosition(req: {
  ticker: string;
  frontend_direction: 'LONG' | 'SHORT';
  contracts?: number;
  interval?: string;
  period?: string;
}): Promise<{ position: FuturesPaperPosition; hypothesis_id: number }> {
  const res = await fetch(`${API_BASE_URL}/esf/paper/open`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      ticker: req.ticker,
      frontend_direction: req.frontend_direction,
      contracts: req.contracts ?? 1,
      interval: req.interval ?? '15m',
      period: req.period ?? '60d',
    }),
  });
  if (!res.ok) {
    let detail = '';
    try { const j = await res.json(); detail = j.detail || JSON.stringify(j); } catch {}
    throw new Error(`openPaperPosition failed (${res.status}): ${detail}`);
  }
  return res.json();
}

export async function getOpenPaperPositions(): Promise<FuturesPaperPosition[]> {
  const res = await fetch(`${API_BASE_URL}/esf/paper/positions?status=OPEN`);
  if (!res.ok) throw new Error(`getOpenPaperPositions failed: ${res.status}`);
  const data = await res.json();
  return data.items ?? [];
}

export async function getPaperPosition(positionId: string): Promise<FuturesPaperPosition> {
  const res = await fetch(`${API_BASE_URL}/esf/paper/positions/${positionId}`);
  if (!res.ok) throw new Error(`getPaperPosition failed: ${res.status}`);
  return res.json();
}

export async function closePaperPosition(positionId: string, price?: number): Promise<FuturesPaperPosition> {
  const res = await fetch(`${API_BASE_URL}/esf/paper/positions/${positionId}/close`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ price: price ?? null }),
  });
  if (!res.ok) {
    let detail = '';
    try { const j = await res.json(); detail = j.detail || JSON.stringify(j); } catch {}
    throw new Error(`closePaperPosition failed (${res.status}): ${detail}`);
  }
  return res.json();
}

export async function getPaperRiskStatus(): Promise<PaperRiskStatus> {
  const res = await fetch(`${API_BASE_URL}/esf/paper/risk-status`);
  if (!res.ok) throw new Error(`getPaperRiskStatus failed: ${res.status}`);
  return res.json();
}

// ══════════════════════════════════════════
// Walk-Forward Backtest
// ══════════════════════════════════════════

export interface WalkForwardWindow {
  index: number;
  label: string;
  start_date: string;       // YYYYMMDD
  end_date: string;
  contract_code: string;
  duration_days: number;
  total_return_pct: number;
  total_pnl: number;
  sharpe_ratio: number;
  max_drawdown_pct: number;
  win_rate: number;
  profit_factor: number;
  total_trades: number;
  long_trades: number;
  short_trades: number;
  avg_holding_days: number;
  error: string | null;
}

export interface WalkForwardDistribution {
  metric: string;
  count: number;
  median: number;
  mean: number;
  p25: number;
  p75: number;
  worst: number;
  best: number;
}

export interface WalkForwardResult {
  ticker: string;
  asset_class: 'equity_index' | 'energy' | 'metal';
  window_size_months: number;
  n_windows: number;
  windows: WalkForwardWindow[];
  distributions: WalkForwardDistribution[];
  completed_at: string;
  errors: string[];
}

export async function triggerWalkForward(req: {
  ticker: string;
  initial_equity?: number;
  is_micro?: boolean;
}): Promise<{ status: string; result: WalkForwardResult }> {
  const res = await fetch(`${API_BASE_URL}/esf/backtest/walk-forward`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      ticker: req.ticker,
      initial_equity: req.initial_equity ?? 100_000,
      is_micro: req.is_micro ?? false,
    }),
  });
  if (!res.ok) {
    let detail = '';
    try { const j = await res.json(); detail = j.detail || JSON.stringify(j); } catch {}
    throw new Error(`triggerWalkForward failed (${res.status}): ${detail}`);
  }
  return res.json();
}

export async function fetchWalkForwardStatus(): Promise<{ status: string; progress: number }> {
  const res = await fetch(`${API_BASE_URL}/esf/backtest/walk-forward/status`);
  if (!res.ok) throw new Error(`fetchWalkForwardStatus failed: ${res.status}`);
  return res.json();
}

export async function fetchWalkForwardResult(): Promise<WalkForwardResult> {
  const res = await fetch(`${API_BASE_URL}/esf/backtest/walk-forward/result`);
  if (!res.ok) throw new Error(`fetchWalkForwardResult failed: ${res.status}`);
  return res.json();
}

