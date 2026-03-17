/**
 * Futures Scalp Decision Engine — Pure TypeScript (Zero React Dependencies)
 *
 * Probability-based decision engine for ES/MES scalping.
 * Ported from FuturesScalpAnalyzer v1.2 (Layer 1 + Layer 2).
 *
 * Architecture:
 *   - Pure math & statistics functions
 *   - Data parsers (Close / OHLC)
 *   - Core calculation engine (Z-Score, EV, Kelly, ATR Stop, Position Sizing, Basis)
 *   - Completely independent from stock trading engine
 */

// ══════════════════════════════════════════════════════════════
// Types
// ══════════════════════════════════════════════════════════════

export interface AssetSpec {
  label: string;
  tick: number;
  tickVal: number;
  ptVal: number;
}

export interface AutoStats {
  ma: number;
  stdDev: number;
  atr: number;
  currentPrice: number;
  count: number;
  maPeriod: number;
  atrMethod: 'TRUE-RANGE' | 'CLOSE-PROXY';
}

export interface OHLCCandle {
  o: number;
  h: number;
  l: number;
  c: number;
}

export interface ScalpInputs {
  asset: 'ES' | 'MES';
  currentPrice: number;
  ma: number;
  stdDev: number;
  atr: number;
  atrMult: number;
  winRate: number;
  avgWin: number;
  avgLoss: number;
  slippage: number;
  commission: number;
  accountBalance: number;
  riskPct: number;
  spotPrice: number;
  futuresPrice: number;
}

export interface DecisionCheck {
  label: string;
  pass: boolean;
  val: string;
}

export interface ScalpAnalysis {
  cfg: AssetSpec;
  // Z-Score
  z: number;
  pVal: number;
  zSignal: string;
  zColor: string;
  // EV
  p: number;
  q: number;
  b: number;
  grossEV: number;
  friction: number;
  netEV: number;
  netEVusd: number;
  // Kelly
  kelly: number;
  halfKelly: number;
  conviction: string;
  // ATR Stop
  atrStop: number;
  isLong: boolean;
  sl: number;
  riskPerContract: number;
  // Position
  riskBudget: number;
  maxContracts: number;
  recContracts: number;
  // TP levels
  tp15: number;
  tp2: number;
  tp3: number;
  // Basis
  basis: number;
  basisPct: number;
  basisState: 'CONTANGO' | 'BACKWARDATION' | 'FAIR VALUE';
  // P&L
  pnlTP1: number;
  pnlSL: number;
  // Decision
  checks: DecisionCheck[];
  passN: number;
  verdict: 'GO' | 'CAUTION' | 'NO ENTRY';
}

// ══════════════════════════════════════════════════════════════
// Constants
// ══════════════════════════════════════════════════════════════

export const ASSETS: Record<string, AssetSpec> = {
  ES: { label: 'E-mini S&P 500', tick: 0.25, tickVal: 12.50, ptVal: 50 },
  MES: { label: 'Micro E-mini S&P', tick: 0.25, tickVal: 1.25, ptVal: 5 },
};

export const SAMPLE_CLOSE = '5872.50, 5878.25, 5865.00, 5880.75, 5889.50, 5895.25, 5887.00, 5892.75, 5901.50, 5898.00, 5905.25, 5910.75, 5903.50, 5908.00, 5915.25, 5911.50, 5918.75, 5922.00, 5916.50, 5920.00';

export const SAMPLE_OHLC = `5870.00, 5878.50, 5868.25, 5872.50
5873.00, 5882.75, 5871.50, 5878.25
5879.00, 5880.00, 5862.50, 5865.00
5866.00, 5884.25, 5864.75, 5880.75
5881.00, 5893.00, 5879.25, 5889.50
5890.00, 5899.75, 5888.00, 5895.25
5895.50, 5896.00, 5884.50, 5887.00
5887.25, 5896.50, 5886.00, 5892.75
5893.00, 5905.25, 5891.75, 5901.50
5901.75, 5903.50, 5895.00, 5898.00
5898.25, 5909.00, 5897.50, 5905.25
5905.50, 5914.50, 5904.25, 5910.75
5911.00, 5912.00, 5901.00, 5903.50
5903.75, 5911.25, 5902.50, 5908.00
5908.25, 5918.75, 5907.00, 5915.25
5915.50, 5917.00, 5909.25, 5911.50
5912.00, 5922.50, 5911.25, 5918.75
5919.00, 5925.75, 5918.00, 5922.00
5922.25, 5923.00, 5914.50, 5916.50
5917.00, 5923.50, 5916.25, 5920.00`;

// ══════════════════════════════════════════════════════════════
// Pure Math Functions
// ══════════════════════════════════════════════════════════════

export function clamp(v: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, v));
}

export function fmt(v: number, d = 2): string {
  return isNaN(v) || !isFinite(v) ? '—' : v.toFixed(d);
}

export function fmtUSD(v: number): string {
  return isNaN(v) || !isFinite(v)
    ? '—'
    : '$' + Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function fmtPct(v: number): string {
  return isNaN(v) || !isFinite(v) ? '—' : (v * 100).toFixed(1) + '%';
}

/** Normal CDF — Abramowitz & Stegun approximation (error < 1.5e-7) */
export function normCDF(z: number): number {
  if (z < -6) return 0;
  if (z > 6) return 1;
  const a1 = 0.254829592, a2 = -0.284496736, a3 = 1.421413741,
    a4 = -1.453152027, a5 = 1.061405429, p = 0.3275911;
  const s = z < 0 ? -1 : 1;
  const x = Math.abs(z) / Math.SQRT2;
  const t = 1 / (1 + p * x);
  return 0.5 * (1 + s * (1 - ((((a5 * t + a4) * t + a3) * t + a2) * t + a1) * t * Math.exp(-x * x)));
}

/** True Range = max(H-L, |H-prevC|, |L-prevC|) */
export function trueRange(high: number, low: number, prevClose: number | null): number {
  if (prevClose === null || prevClose === undefined) return high - low;
  return Math.max(high - low, Math.abs(high - prevClose), Math.abs(low - prevClose));
}

// ══════════════════════════════════════════════════════════════
// Data Parsers
// ══════════════════════════════════════════════════════════════

/** Parse close-only prices from text (comma/space/newline/tab/semicolon) */
export function parseCloses(text: string): number[] {
  if (!text.trim()) return [];
  return text.split(/[,\s;|\t\n]+/).map(s => s.trim()).filter(Boolean).map(Number).filter(n => !isNaN(n) && n > 0);
}

/** Parse OHLC data from text. One candle per line: O,H,L,C */
export function parseOHLC(text: string): OHLCCandle[] {
  if (!text.trim()) return [];
  const lines = text.split(/\n/).map(l => l.trim()).filter(Boolean);
  const candles: OHLCCandle[] = [];
  for (const line of lines) {
    const tokens = line.split(/[,\s\t;|]+/).map(Number);
    if (tokens.length >= 4 && tokens.every(n => !isNaN(n) && n > 0)) {
      candles.push({ o: tokens[0], h: tokens[1], l: tokens[2], c: tokens[3] });
    }
  }
  return candles;
}

// ══════════════════════════════════════════════════════════════
// Statistics Engine
// ══════════════════════════════════════════════════════════════

/** Compute MA, sigma, ATR from close-only data. ATR approximation: avg(|C[i]-C[i-1]|) */
export function statsFromCloses(closes: number[], maPeriod = 20): AutoStats | null {
  if (!closes || closes.length < 3) return null;
  const n = closes.length;
  const maSlice = closes.slice(-maPeriod);
  const ma = maSlice.reduce((a, b) => a + b, 0) / maSlice.length;
  const variance = maSlice.reduce((acc, p) => acc + (p - ma) ** 2, 0) / maSlice.length;
  const stdDev = Math.sqrt(variance);
  const trs: number[] = [];
  for (let i = 1; i < n; i++) trs.push(Math.abs(closes[i] - closes[i - 1]));
  const atrSlice = trs.slice(-Math.min(14, trs.length));
  const atr = atrSlice.length > 0 ? atrSlice.reduce((a, b) => a + b, 0) / atrSlice.length : 0;
  return {
    ma: +ma.toFixed(2), stdDev: +stdDev.toFixed(2), atr: +atr.toFixed(2),
    currentPrice: closes[n - 1], count: n, maPeriod: maSlice.length, atrMethod: 'CLOSE-PROXY',
  };
}

/** Compute MA, sigma, ATR from OHLC data using True Range */
export function statsFromOHLC(candles: OHLCCandle[], maPeriod = 20): AutoStats | null {
  if (!candles || candles.length < 3) return null;
  const n = candles.length;
  const closes = candles.map(c => c.c);
  const maSlice = closes.slice(-maPeriod);
  const ma = maSlice.reduce((a, b) => a + b, 0) / maSlice.length;
  const variance = maSlice.reduce((acc, p) => acc + (p - ma) ** 2, 0) / maSlice.length;
  const stdDev = Math.sqrt(variance);
  const trs: number[] = [];
  for (let i = 0; i < n; i++) {
    const prevC = i > 0 ? candles[i - 1].c : null;
    trs.push(trueRange(candles[i].h, candles[i].l, prevC));
  }
  const atrSlice = trs.slice(-Math.min(14, trs.length));
  const atr = atrSlice.length > 0 ? atrSlice.reduce((a, b) => a + b, 0) / atrSlice.length : 0;
  return {
    ma: +ma.toFixed(2), stdDev: +stdDev.toFixed(2), atr: +atr.toFixed(2),
    currentPrice: closes[n - 1], count: n, maPeriod: maSlice.length, atrMethod: 'TRUE-RANGE',
  };
}

// ══════════════════════════════════════════════════════════════
// Core Calculation Engine
// ══════════════════════════════════════════════════════════════

// Color tokens for Z-Score visualization
const C_GRN = '#00e676';
const C_RED = '#ff1744';
const C_GRN_LIGHT = '#69f0ae';
const C_RED_LIGHT = '#ff8a80';
const C_NEUTRAL = '#78909c';

export function computeScalpAnalysis(inputs: ScalpInputs): ScalpAnalysis {
  const { asset, currentPrice, ma, stdDev, atr, atrMult, winRate, avgWin, avgLoss, slippage, commission, accountBalance, riskPct, spotPrice, futuresPrice } = inputs;
  const cfg = ASSETS[asset];

  // Z-Score
  const z = stdDev > 0 ? (currentPrice - ma) / stdDev : 0;
  const pVal = normCDF(-Math.abs(z)) * 2;
  const zSignal = z < -2 ? 'STRONG LONG' : z > 2 ? 'STRONG SHORT' : z < -1.5 ? 'LEAN LONG' : z > 1.5 ? 'LEAN SHORT' : 'NEUTRAL';
  const zColor = z < -2 ? C_GRN : z > 2 ? C_RED : z < -1 ? C_GRN_LIGHT : z > 1 ? C_RED_LIGHT : C_NEUTRAL;

  // EV (net of friction)
  const p = winRate / 100;
  const q = 1 - p;
  const grossEV = p * avgWin - q * avgLoss;
  const friction = slippage + (commission / cfg.tickVal);
  const netEV = grossEV - friction;
  const netEVusd = netEV * cfg.tickVal;

  // Kelly
  const b = avgLoss > 0 ? avgWin / avgLoss : 0;
  const kelly = b > 0 ? (b * p - q) / b : 0;
  const halfKelly = kelly / 2;
  const conviction = kelly <= 0 ? 'NO EDGE' : halfKelly < 0.02 ? 'VERY LOW' : halfKelly < 0.05 ? 'LOW' : halfKelly < 0.1 ? 'MODERATE' : halfKelly < 0.2 ? 'HIGH' : 'VERY HIGH';

  // ATR Stop
  const atrStop = atr * atrMult;
  const isLong = z <= 0;
  const sl = isLong ? currentPrice - atrStop : currentPrice + atrStop;
  const riskPerContract = atrStop * cfg.ptVal;

  // Position
  const riskBudget = accountBalance * (riskPct / 100);
  const maxContracts = riskPerContract > 0 ? Math.floor(riskBudget / riskPerContract) : 0;
  const recContracts = Math.min(maxContracts, 2);

  // TP levels
  const tp15 = isLong ? currentPrice + atrStop * 1.5 : currentPrice - atrStop * 1.5;
  const tp2 = isLong ? currentPrice + atrStop * 2 : currentPrice - atrStop * 2;
  const tp3 = isLong ? currentPrice + atrStop * 3 : currentPrice - atrStop * 3;

  // Basis
  const basis = futuresPrice - spotPrice;
  const basisPct = spotPrice > 0 ? (basis / spotPrice) * 100 : 0;
  const basisState: ScalpAnalysis['basisState'] = basis > 2 ? 'CONTANGO' : basis < -2 ? 'BACKWARDATION' : 'FAIR VALUE';

  // P&L
  const lots = Math.max(recContracts, 1);
  const pnlTP1 = Math.abs(tp15 - currentPrice) * cfg.ptVal * lots;
  const pnlSL = atrStop * cfg.ptVal * lots;

  // Decision Matrix
  const checks: DecisionCheck[] = [
    { label: 'Z-Score 방향성', pass: Math.abs(z) >= 1.5, val: `Z = ${fmt(z)}` },
    { label: '순 기대값 > 0', pass: netEV > 0, val: `${fmt(netEV)}t (${fmtUSD(Math.abs(netEVusd))})` },
    { label: 'Kelly 양수', pass: kelly > 0, val: fmtPct(kelly) },
    { label: '손익비 >= 1.5', pass: b >= 1.5, val: `${fmt(b, 1)}:1` },
  ];
  const passN = checks.filter(c => c.pass).length;
  const verdict: ScalpAnalysis['verdict'] = passN === 4 ? 'GO' : passN >= 3 ? 'CAUTION' : 'NO ENTRY';

  return {
    cfg, z, pVal, zSignal, zColor,
    p, q, b, grossEV, friction, netEV, netEVusd,
    kelly, halfKelly, conviction,
    atrStop, isLong, sl, riskPerContract,
    riskBudget, maxContracts, recContracts,
    tp15, tp2, tp3,
    basis, basisPct, basisState,
    pnlTP1, pnlSL,
    checks, passN, verdict,
  };
}

// ══════════════════════════════════════════════════════════════
// Strategy Dashboard — MA / ATR / Unified Strategy Analysis
// ══════════════════════════════════════════════════════════════

export interface MAAnalysis {
  alignment: 'BULLISH' | 'BEARISH' | 'MIXED';
  slope: 'RISING' | 'FLAT' | 'FALLING';
  strength: number; // 0-100
  emaFast: number;
  emaMid: number;
  emaSlow: number;
}

export interface ATRState {
  current: number;
  average: number;
  ratio: number;
  state: 'EXPANDING' | 'NORMAL' | 'CONTRACTING';
  positionSizeAdj: number; // 0.5-1.5
}

export type StrategyType = 'TREND_CONTINUATION' | 'MEAN_REVERSION' | 'STAND_ASIDE';
export type EntryTiming = 'IMMEDIATE' | 'WAIT_PULLBACK' | 'NO_ENTRY';

export interface UnifiedStrategy {
  direction: 'LONG' | 'SHORT' | 'NEUTRAL';
  strategyType: StrategyType;
  entryTiming: EntryTiming;
  positionSizePct: number;
  confidence: number; // 0-100
  reasons: string[];
}

interface CandleLike {
  close: number;
  atr_14: number | null;
  ema_fast: number | null;
  ema_mid: number | null;
  ema_slow: number | null;
  rsi_14: number | null;
  macd_diff: number | null;
  adx: number | null;
  zscore: number | null;
}

export function analyzeMA(candles: CandleLike[]): MAAnalysis {
  const defaults: MAAnalysis = { alignment: 'MIXED', slope: 'FLAT', strength: 0, emaFast: 0, emaMid: 0, emaSlow: 0 };
  if (candles.length < 5) return defaults;

  const last = candles[candles.length - 1];
  const prev = candles[candles.length - 4];
  const ef = last.ema_fast, em = last.ema_mid, es = last.ema_slow;
  if (ef == null || em == null || es == null) return defaults;

  // Alignment
  let alignment: MAAnalysis['alignment'] = 'MIXED';
  if (ef > em && em > es) alignment = 'BULLISH';
  else if (ef < em && em < es) alignment = 'BEARISH';

  // Slope (EMA mid over last 3 bars)
  const prevMid = prev.ema_mid;
  let slope: MAAnalysis['slope'] = 'FLAT';
  if (prevMid != null) {
    const change = (em - prevMid) / prevMid * 100;
    if (change > 0.05) slope = 'RISING';
    else if (change < -0.05) slope = 'FALLING';
  }

  // Strength: how spread apart the EMAs are (normalized)
  const spread = Math.abs(ef - es);
  const avgPrice = (ef + em + es) / 3;
  const spreadPct = avgPrice > 0 ? (spread / avgPrice) * 100 : 0;
  // 0.5% spread = ~50 strength, 1%+ = ~100
  const strength = clamp(spreadPct * 100, 0, 100);

  return { alignment, slope, strength, emaFast: ef, emaMid: em, emaSlow: es };
}

export function analyzeATR(candles: CandleLike[], lookback = 20): ATRState {
  const defaults: ATRState = { current: 0, average: 0, ratio: 1, state: 'NORMAL', positionSizeAdj: 1 };
  if (candles.length < lookback + 1) return defaults;

  const last = candles[candles.length - 1];
  if (last.atr_14 == null) return defaults;
  const current = last.atr_14;

  // Rolling average ATR over lookback period
  const atrValues: number[] = [];
  for (let i = candles.length - lookback; i < candles.length; i++) {
    if (candles[i].atr_14 != null) atrValues.push(candles[i].atr_14!);
  }
  if (atrValues.length < 5) return { ...defaults, current };

  const average = atrValues.reduce((a, b) => a + b, 0) / atrValues.length;
  const ratio = average > 0 ? current / average : 1;

  let state: ATRState['state'] = 'NORMAL';
  let positionSizeAdj = 1.0;
  if (ratio > 1.2) { state = 'EXPANDING'; positionSizeAdj = 0.7; }
  else if (ratio < 0.8) { state = 'CONTRACTING'; positionSizeAdj = 1.3; }

  return { current, average, ratio, state, positionSizeAdj };
}

export function computeUnifiedStrategy(
  regime: string | undefined,
  ma: MAAnalysis,
  atr: ATRState,
  zScore: number | null,
): UnifiedStrategy {
  const reasons: string[] = [];
  let direction: UnifiedStrategy['direction'] = 'NEUTRAL';
  let strategyType: StrategyType = 'STAND_ASIDE';
  let entryTiming: EntryTiming = 'NO_ENTRY';
  let confidence = 0;
  let positionSizePct = 0;

  const r = regime || 'NEUTRAL';
  const z = zScore ?? 0;

  // CRISIS → stand aside
  if (r === 'CRISIS') {
    reasons.push('CRISIS regime — stand aside');
    return { direction, strategyType, entryTiming, positionSizePct: 0, confidence: 10, reasons };
  }

  // Determine direction from regime + MA alignment
  let bullSignals = 0, bearSignals = 0;

  if (r === 'BULL') { bullSignals += 2; reasons.push('BULL regime (+2)'); }
  else if (r === 'BEAR') { bearSignals += 2; reasons.push('BEAR regime (+2 bear)'); }

  if (ma.alignment === 'BULLISH') { bullSignals += 2; reasons.push('EMA alignment bullish (+2)'); }
  else if (ma.alignment === 'BEARISH') { bearSignals += 2; reasons.push('EMA alignment bearish (+2)'); }

  if (ma.slope === 'RISING') { bullSignals += 1; reasons.push('EMA slope rising (+1)'); }
  else if (ma.slope === 'FALLING') { bearSignals += 1; reasons.push('EMA slope falling (+1)'); }

  if (z < -1.5) { bullSignals += 1; reasons.push(`Z-Score ${z.toFixed(2)} mean reversion long (+1)`); }
  else if (z > 1.5) { bearSignals += 1; reasons.push(`Z-Score ${z.toFixed(2)} mean reversion short (+1)`); }

  const netSignal = bullSignals - bearSignals;

  if (netSignal >= 2) direction = 'LONG';
  else if (netSignal <= -2) direction = 'SHORT';

  // Strategy type
  if (direction === 'NEUTRAL') {
    strategyType = 'STAND_ASIDE';
    entryTiming = 'NO_ENTRY';
    confidence = 20;
    reasons.push('Conflicting signals — no clear direction');
  } else {
    // Trend continuation if regime + MA align
    const regimeBull = r === 'BULL' || r === 'STRONG_BULL';
    const regimeBear = r === 'BEAR';
    const maAligned = (direction === 'LONG' && ma.alignment === 'BULLISH') ||
                       (direction === 'SHORT' && ma.alignment === 'BEARISH');

    if (maAligned && ((direction === 'LONG' && regimeBull) || (direction === 'SHORT' && regimeBear))) {
      strategyType = 'TREND_CONTINUATION';
      confidence = 70 + Math.min(ma.strength, 20);
      reasons.push('Regime + MA aligned → trend continuation');
    } else if (Math.abs(z) > 1.5) {
      strategyType = 'MEAN_REVERSION';
      confidence = 50 + Math.min(Math.abs(z) * 10, 25);
      reasons.push(`Z-Score extreme (${z.toFixed(2)}) → mean reversion`);
    } else {
      strategyType = 'TREND_CONTINUATION';
      confidence = 40 + Math.abs(netSignal) * 8;
      reasons.push('Partial alignment → cautious trend follow');
    }

    // Entry timing
    if (atr.state === 'EXPANDING') {
      entryTiming = 'WAIT_PULLBACK';
      reasons.push('ATR expanding — wait for pullback');
      confidence = Math.max(confidence - 10, 10);
    } else {
      entryTiming = confidence >= 60 ? 'IMMEDIATE' : 'WAIT_PULLBACK';
    }

    // Position size
    const base = confidence >= 70 ? 100 : confidence >= 50 ? 50 : 25;
    positionSizePct = base * atr.positionSizeAdj;
  }

  return { direction, strategyType, entryTiming, positionSizePct: clamp(positionSizePct, 0, 150), confidence: clamp(confidence, 0, 100), reasons };
}
