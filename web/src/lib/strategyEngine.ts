/**
 * Multi-Strategy Engine — Regime Detection + 3 Strategy Signal Generators
 *
 * Strategies:
 *   1. Mean Reversion Swing (RANGE regime)
 *   2. Trend Following (TRENDING regime)
 *   3. Scalp/Momentum (VOLATILE/MIXED regime, uses Fabio engine)
 *
 * Backtest: runs all 3 strategies in parallel + regime-based auto-select mode.
 */

import type { AnalyticsData } from './api';
import type { OHLC } from './scalpEngine';
import type { FabioAnalysis } from './fabioEngine';
import { computeMA, computeStdDev, computeATR, computeRSI, computeADXProxy, computeBBWidth } from './indicators';

// ── Types ─────────────────────────────────────────────────────────────

export type MarketRegime = 'SQUEEZE' | 'RANGE' | 'TRENDING' | 'VOLATILE' | 'MIXED';
export type StrategyName = 'MEAN_REVERSION' | 'TREND_FOLLOWING' | 'SCALP_MOMENTUM';
export type SignalAction = 'LONG' | 'SHORT' | 'EXIT' | 'HOLD' | 'WAIT';

export interface RegimeAnalysis {
  regime: MarketRegime;
  confidence: number;         // 0~100
  indicators: {
    adx: number | null;
    bbWidth: number | null;   // as % of price
    diSpread: number | null;  // |+DI - -DI|
    atrPct: number | null;    // ATR as % of price
  };
  reason: string;
  recommended: StrategyName | null;  // null for SQUEEZE (wait)
}

export interface StrategySignal {
  strategy: StrategyName;
  action: SignalAction;
  confidence: number;         // 0~100
  direction: 'BULL' | 'BEAR' | 'NEUTRAL';
  stopLoss: number | null;
  takeProfit: number | null;
  reason: string;
}

export interface MeanReversionSignal extends StrategySignal {
  zScore: number;
  rsiProxy: number | null;    // RSI or proxy
  targetZ: number;            // exit target Z-score
  holdDays: string;           // "2~10"
}

export interface TrendFollowingSignal extends StrategySignal {
  adxValue: number | null;
  diSpread: number | null;
  chandelierStop: number | null;
  trailingStop: number | null;
  holdDays: string;
}

export interface ScalpMomentumSignal extends StrategySignal {
  tripleAPhase: string;
  grade: string;
  holdBars: string;
}

export interface MultiStrategyAnalysis {
  regime: RegimeAnalysis;
  recommended: StrategyName | null;
  signals: {
    meanRev: MeanReversionSignal;
    trendFollow: TrendFollowingSignal;
    scalp: ScalpMomentumSignal;
  };
}

// ── Backtest Types ────────────────────────────────────────────────────

export interface MultiStrategyBacktestConfig {
  lookback: number;
  atrMult: number;
  tpMultiplier: number;
  maxHoldBars: number;         // max hold for mean rev / trend
  mrMaxHoldBars: number;       // mean reversion max
  tfMaxHoldBars: number;       // trend following max
  scalpMaxHoldBars: number;    // scalp max
}

export interface MSBacktestTrade {
  strategy: StrategyName;
  regime: MarketRegime;
  direction: 'LONG' | 'SHORT';
  entryBar: number;
  entryPrice: number;
  exitBar: number;
  exitPrice: number;
  pnlPoints: number;
  bars: number;
  exitReason: string;
}

export interface StrategyStats {
  trades: number;
  wins: number;
  losses: number;
  winRate: number;
  totalPnL: number;
  profitFactor: number;
  avgWin: number;
  avgLoss: number;
  maxDD: number;
  sharpe: number;
}

export interface RegimeStats {
  regime: MarketRegime;
  bars: number;
  barsPct: number;
  trades: number;
  winRate: number;
  totalPnL: number;
}

export interface MSBacktestResult {
  trades: MSBacktestTrade[];
  strategyStats: Record<StrategyName, StrategyStats>;
  regimeStats: RegimeStats[];
  autoSelectStats: StrategyStats;
  regimeHistory: MarketRegime[];   // per-bar regime
  totalBars: number;
}

// ── Default Config ────────────────────────────────────────────────────

export const DEFAULT_MS_CONFIG: MultiStrategyBacktestConfig = {
  lookback: 20,
  atrMult: 1.5,
  tpMultiplier: 2.0,
  maxHoldBars: 10,
  mrMaxHoldBars: 10,
  tfMaxHoldBars: 20,
  scalpMaxHoldBars: 3,
};

// ── Regime Colors ─────────────────────────────────────────────────────

export const REGIME_COLORS: Record<MarketRegime, string> = {
  SQUEEZE: '#fdd835',
  RANGE: '#4fc3f7',
  TRENDING: '#00e676',
  VOLATILE: '#ff1744',
  MIXED: '#b0bec5',
};

export const REGIME_LABELS: Record<MarketRegime, string> = {
  SQUEEZE: 'Squeeze (스퀴즈)',
  RANGE: 'Range (횡보)',
  TRENDING: 'Trending (추세)',
  VOLATILE: 'Volatile (고변동)',
  MIXED: 'Mixed (혼조)',
};

export const STRATEGY_LABELS: Record<StrategyName, string> = {
  MEAN_REVERSION: 'Mean Reversion',
  TREND_FOLLOWING: 'Trend Following',
  SCALP_MOMENTUM: 'Scalp / Momentum',
};

// ── Regime Detection ──────────────────────────────────────────────────

/**
 * Detect market regime from live AnalyticsData (uses pre-computed indicators).
 */
export function detectRegime(data: AnalyticsData[]): RegimeAnalysis {
  if (data.length < 2) {
    return { regime: 'MIXED', confidence: 0, indicators: { adx: null, bbWidth: null, diSpread: null, atrPct: null }, reason: '데이터 부족', recommended: null };
  }

  const current = data[data.length - 1];
  const adx = current.adx;
  const plusDI = current.plus_di;
  const minusDI = current.minus_di;
  const diSpread = plusDI != null && minusDI != null ? Math.abs(plusDI - minusDI) : null;

  // BB width as %
  let bbWidth: number | null = null;
  if (current.bb_hband != null && current.bb_lband != null && current.close > 0) {
    bbWidth = ((current.bb_hband - current.bb_lband) / current.close) * 100;
  }

  // ATR %
  let atrPct: number | null = null;
  if (current.atr_14 != null && current.close > 0) {
    atrPct = (current.atr_14 / current.close) * 100;
  }

  const indicators = { adx, bbWidth, diSpread, atrPct };

  return classifyRegime(adx, bbWidth, diSpread, atrPct, indicators);
}

/**
 * Detect market regime from OHLC candles (proxy indicators for backtest).
 */
export function detectRegimeFromOHLC(candles: OHLC[], i: number, lookback: number = 20): RegimeAnalysis {
  if (i < lookback) {
    return { regime: 'MIXED', confidence: 0, indicators: { adx: null, bbWidth: null, diSpread: null, atrPct: null }, reason: '데이터 부족', recommended: null };
  }

  const bbWidth = computeBBWidth(candles, i, lookback);
  const adxData = computeADXProxy(candles, i, 14);
  const adx = adxData?.adx ?? null;
  const diSpread = adxData ? Math.abs(adxData.plusDI - adxData.minusDI) : null;

  const atr = computeATR(candles, i, 14);
  const atrPct = candles[i].c > 0 ? (atr / candles[i].c) * 100 : null;

  const indicators = { adx, bbWidth, diSpread, atrPct };

  return classifyRegime(adx, bbWidth, diSpread, atrPct, indicators);
}

function classifyRegime(
  adx: number | null,
  bbWidth: number | null,
  diSpread: number | null,
  atrPct: number | null,
  indicators: RegimeAnalysis['indicators'],
): RegimeAnalysis {
  // SQUEEZE: very tight BB + no trend
  if (bbWidth != null && bbWidth < 4 && (adx == null || adx < 20)) {
    return {
      regime: 'SQUEEZE',
      confidence: Math.min(100, Math.round((4 - bbWidth) * 25 + (adx != null ? (20 - adx) * 2 : 20))),
      indicators,
      reason: `BB폭 ${bbWidth.toFixed(1)}% < 4%, ADX ${adx?.toFixed(0) ?? 'N/A'} — 스퀴즈 (돌파 대기)`,
      recommended: null,
    };
  }

  // VOLATILE: wide BB or high ATR
  if ((bbWidth != null && bbWidth > 12) || (atrPct != null && atrPct > 3)) {
    const conf = Math.min(100, Math.round(
      (bbWidth != null && bbWidth > 12 ? (bbWidth - 12) * 10 : 0) +
      (atrPct != null && atrPct > 3 ? (atrPct - 3) * 20 : 0) + 30
    ));
    return {
      regime: 'VOLATILE',
      confidence: conf,
      indicators,
      reason: `BB폭 ${bbWidth?.toFixed(1) ?? 'N/A'}%, ATR% ${atrPct?.toFixed(1) ?? 'N/A'} — 고변동`,
      recommended: 'SCALP_MOMENTUM',
    };
  }

  // TRENDING: strong ADX + DI separation
  if (adx != null && adx >= 25 && diSpread != null && diSpread > 10) {
    return {
      regime: 'TRENDING',
      confidence: Math.min(100, Math.round((adx - 20) * 4 + diSpread * 2)),
      indicators,
      reason: `ADX ${adx.toFixed(0)} ≥ 25, DI차 ${diSpread.toFixed(0)} > 10 — 추세 진행 중`,
      recommended: 'TREND_FOLLOWING',
    };
  }

  // RANGE: low ADX, moderate BB
  if (adx != null && adx < 25 && bbWidth != null && bbWidth < 8) {
    return {
      regime: 'RANGE',
      confidence: Math.min(100, Math.round((25 - adx) * 3 + (8 - bbWidth) * 5 + 20)),
      indicators,
      reason: `ADX ${adx.toFixed(0)} < 25, BB폭 ${bbWidth.toFixed(1)}% — 횡보 구간`,
      recommended: 'MEAN_REVERSION',
    };
  }

  // MIXED
  return {
    regime: 'MIXED',
    confidence: 30,
    indicators,
    reason: `ADX ${adx?.toFixed(0) ?? 'N/A'}, BB폭 ${bbWidth?.toFixed(1) ?? 'N/A'}% — 혼조 구간`,
    recommended: 'SCALP_MOMENTUM',
  };
}

// ── Strategy Signal Generators ────────────────────────────────────────

/**
 * Mean Reversion Swing signal from OHLC at bar index i.
 */
export function generateMeanReversionSignal(
  candles: OHLC[], i: number, lookback: number = 20
): MeanReversionSignal {
  const base: MeanReversionSignal = {
    strategy: 'MEAN_REVERSION',
    action: 'WAIT',
    confidence: 0,
    direction: 'NEUTRAL',
    stopLoss: null,
    takeProfit: null,
    reason: '',
    zScore: 0,
    rsiProxy: null,
    targetZ: 0,
    holdDays: '2~10',
  };

  if (i < lookback) {
    base.reason = '데이터 부족';
    return base;
  }

  const ma = computeMA(candles, i, lookback);
  const sd = computeStdDev(candles, i, lookback);
  const price = candles[i].c;
  const z = sd > 0 ? (price - ma) / sd : 0;
  const rsi = computeRSI(candles, i, 14);
  const atr = computeATR(candles, i, 14);

  base.zScore = z;
  base.rsiProxy = rsi;

  // LONG: Z <= -2.0 and RSI oversold (< 35)
  if (z <= -2.0 && (rsi == null || rsi < 35)) {
    base.action = 'LONG';
    base.direction = 'BULL';
    base.confidence = Math.min(100, Math.round(Math.abs(z) * 20 + (rsi != null ? (35 - rsi) : 10)));
    base.stopLoss = price - atr * 2.5;
    base.takeProfit = ma;  // target = mean
    base.targetZ = 0;
    base.reason = `Z=${z.toFixed(2)} ≤ -2.0, RSI=${rsi?.toFixed(0) ?? 'N/A'} — 과매도 반등 기대`;
    return base;
  }

  // SHORT: Z >= 2.0 and RSI overbought (> 65)
  if (z >= 2.0 && (rsi == null || rsi > 65)) {
    base.action = 'SHORT';
    base.direction = 'BEAR';
    base.confidence = Math.min(100, Math.round(Math.abs(z) * 20 + (rsi != null ? (rsi - 65) : 10)));
    base.stopLoss = price + atr * 2.5;
    base.takeProfit = ma;
    base.targetZ = 0;
    base.reason = `Z=${z.toFixed(2)} ≥ 2.0, RSI=${rsi?.toFixed(0) ?? 'N/A'} — 과매수 조정 기대`;
    return base;
  }

  // Mild signals
  if (z <= -1.5) {
    base.action = 'WAIT';
    base.direction = 'BULL';
    base.confidence = 30;
    base.reason = `Z=${z.toFixed(2)} — 매수 관심 구간 (신호 미충족)`;
  } else if (z >= 1.5) {
    base.action = 'WAIT';
    base.direction = 'BEAR';
    base.confidence = 30;
    base.reason = `Z=${z.toFixed(2)} — 매도 관심 구간 (신호 미충족)`;
  } else {
    base.reason = `Z=${z.toFixed(2)} — 평균 근처, 진입 조건 미충족`;
  }

  return base;
}

/**
 * Mean Reversion exit check — returns true if should exit.
 */
function shouldExitMeanReversion(
  candles: OHLC[], i: number, entryDir: 'LONG' | 'SHORT',
  lookback: number, entryBar: number, maxHold: number
): { exit: boolean; reason: string } {
  if (i - entryBar >= maxHold) return { exit: true, reason: 'MAX_HOLD' };

  const ma = computeMA(candles, i, lookback);
  const sd = computeStdDev(candles, i, lookback);
  const z = sd > 0 ? (candles[i].c - ma) / sd : 0;

  // Exit when Z crosses back past target
  if (entryDir === 'LONG' && z >= 0) return { exit: true, reason: 'Z=0 (평균 회귀 완료)' };
  if (entryDir === 'SHORT' && z <= 0) return { exit: true, reason: 'Z=0 (평균 회귀 완료)' };

  return { exit: false, reason: '' };
}

/**
 * Trend Following signal from OHLC at bar index i.
 */
export function generateTrendFollowingSignal(
  candles: OHLC[], i: number, lookback: number = 20
): TrendFollowingSignal {
  const base: TrendFollowingSignal = {
    strategy: 'TREND_FOLLOWING',
    action: 'WAIT',
    confidence: 0,
    direction: 'NEUTRAL',
    stopLoss: null,
    takeProfit: null,
    reason: '',
    adxValue: null,
    diSpread: null,
    chandelierStop: null,
    trailingStop: null,
    holdDays: '5~20',
  };

  if (i < lookback + 5) {
    base.reason = '데이터 부족';
    return base;
  }

  const adxData = computeADXProxy(candles, i, 14);
  if (!adxData) {
    base.reason = 'ADX 계산 불가';
    return base;
  }

  const { adx, plusDI, minusDI } = adxData;
  const diSpread = Math.abs(plusDI - minusDI);
  const ma20 = computeMA(candles, i, 20);
  const atr = computeATR(candles, i, 14);
  const price = candles[i].c;

  base.adxValue = adx;
  base.diSpread = diSpread;

  // Chandelier stops
  let highest = -Infinity, lowest = Infinity;
  for (let j = Math.max(0, i - 22); j <= i; j++) {
    if (candles[j].h > highest) highest = candles[j].h;
    if (candles[j].l < lowest) lowest = candles[j].l;
  }
  const chandelierLong = highest - 3 * atr;
  const chandelierShort = lowest + 3 * atr;

  // LONG: ADX >= 25, +DI > -DI, spread > 10, price > SMA20
  if (adx >= 25 && plusDI > minusDI && diSpread > 10 && price > ma20) {
    base.action = 'LONG';
    base.direction = 'BULL';
    base.confidence = Math.min(100, Math.round((adx - 20) * 3 + diSpread * 2));
    base.stopLoss = chandelierLong;
    base.takeProfit = price + atr * 3;
    base.chandelierStop = chandelierLong;
    base.trailingStop = price - atr * 1.5;
    base.reason = `ADX=${adx.toFixed(0)}, +DI>${'-'}DI (${diSpread.toFixed(0)}), 가격>MA20 — 상승 추세`;
    return base;
  }

  // SHORT: ADX >= 25, -DI > +DI, spread > 10, price < SMA20
  if (adx >= 25 && minusDI > plusDI && diSpread > 10 && price < ma20) {
    base.action = 'SHORT';
    base.direction = 'BEAR';
    base.confidence = Math.min(100, Math.round((adx - 20) * 3 + diSpread * 2));
    base.stopLoss = chandelierShort;
    base.takeProfit = price - atr * 3;
    base.chandelierStop = chandelierShort;
    base.trailingStop = price + atr * 1.5;
    base.reason = `ADX=${adx.toFixed(0)}, ${'-'}DI>+DI (${diSpread.toFixed(0)}), 가격<MA20 — 하락 추세`;
    return base;
  }

  // Weak trend
  if (adx >= 20) {
    base.confidence = 20;
    base.reason = `ADX=${adx.toFixed(0)} — 약한 추세, DI차 ${diSpread.toFixed(0)} 부족`;
  } else {
    base.reason = `ADX=${adx.toFixed(0)} < 25 — 추세 부재`;
  }

  return base;
}

/**
 * Trend Following exit check.
 */
function shouldExitTrendFollowing(
  candles: OHLC[], i: number, entryDir: 'LONG' | 'SHORT',
  entryBar: number, maxHold: number, trailingHigh: number, trailingLow: number
): { exit: boolean; reason: string } {
  if (i - entryBar >= maxHold) return { exit: true, reason: 'MAX_HOLD' };

  const atr = computeATR(candles, i, 14);
  const adxData = computeADXProxy(candles, i, 14);
  const adx = adxData?.adx ?? 0;

  // ADX < 20 = trend exhaustion
  if (adx < 20 && i - entryBar > 3) return { exit: true, reason: 'ADX < 20 (추세 소멸)' };

  // Chandelier exit
  if (entryDir === 'LONG') {
    const chandelierExit = trailingHigh - 3 * atr;
    if (candles[i].c < chandelierExit) return { exit: true, reason: `Chandelier exit (${chandelierExit.toFixed(1)})` };
  } else {
    const chandelierExit = trailingLow + 3 * atr;
    if (candles[i].c > chandelierExit) return { exit: true, reason: `Chandelier exit (${chandelierExit.toFixed(1)})` };
  }

  return { exit: false, reason: '' };
}

/**
 * Scalp/Momentum signal from OHLC (simplified Fabio logic).
 */
export function generateScalpSignal(
  candles: OHLC[], i: number, lookback: number = 20,
  fabioAnalysis?: FabioAnalysis | null,
): ScalpMomentumSignal {
  const base: ScalpMomentumSignal = {
    strategy: 'SCALP_MOMENTUM',
    action: 'WAIT',
    confidence: 0,
    direction: 'NEUTRAL',
    stopLoss: null,
    takeProfit: null,
    reason: '',
    tripleAPhase: 'NONE',
    grade: 'NO_TRADE',
    holdBars: '1~3',
  };

  // If live Fabio analysis available, use it
  if (fabioAnalysis) {
    base.tripleAPhase = fabioAnalysis.tripleA.phase;
    base.grade = fabioAnalysis.grade.grade;

    if (fabioAnalysis.grade.grade === 'A' || fabioAnalysis.grade.grade === 'B') {
      const isLong = fabioAnalysis.amt.aggression.direction === 'BULL';
      base.action = isLong ? 'LONG' : 'SHORT';
      base.direction = isLong ? 'BULL' : 'BEAR';
      base.confidence = Math.min(100, fabioAnalysis.grade.confluenceCount * 15 + 20);
      base.reason = `Grade ${fabioAnalysis.grade.grade}, Triple-A: ${fabioAnalysis.tripleA.phase}, ${fabioAnalysis.grade.confluenceCount}개 합류`;
    } else {
      base.reason = `Grade ${fabioAnalysis.grade.grade} — 진입 조건 미달`;
    }
    return base;
  }

  // Backtest proxy: simplified aggression + momentum detection
  if (i < lookback) {
    base.reason = '데이터 부족';
    return base;
  }

  const slice = candles.slice(Math.max(0, i - 5), i + 1);
  const last = candles[i];

  // Body ratio and range expansion
  const ranges = candles.slice(Math.max(0, i - 20), i + 1).map(c => c.h - c.l);
  const avgRange = ranges.reduce((a, b) => a + b, 0) / ranges.length;
  const lastRange = last.h - last.l;
  const lastBody = Math.abs(last.c - last.o);
  const bodyRatio = lastRange > 0 ? lastBody / lastRange : 0;
  const rangeExp = avgRange > 0 ? lastRange / avgRange : 1;

  // Consecutive directional candles
  let consDir = 0;
  let dir: 'BULL' | 'BEAR' = 'BULL';
  for (let j = slice.length - 1; j >= 0; j--) {
    const bull = slice[j].c > slice[j].o;
    if (consDir === 0) { dir = bull ? 'BULL' : 'BEAR'; consDir = 1; }
    else if ((bull && dir === 'BULL') || (!bull && dir === 'BEAR')) consDir++;
    else break;
  }

  // Aggression score
  let score = 0;
  score += bodyRatio > 0.7 ? 40 : bodyRatio > 0.5 ? 25 : 10;
  score += rangeExp > 2 ? 30 : rangeExp > 1.5 ? 20 : rangeExp > 1.2 ? 10 : 0;
  score += consDir >= 3 ? 30 : consDir >= 2 ? 15 : 0;
  score = Math.min(100, score);

  const ma = computeMA(candles, i, lookback);
  const sd = computeStdDev(candles, i, lookback);
  const z = sd > 0 ? (last.c - ma) / sd : 0;
  const atr = computeATR(candles, i, 14);

  if (score >= 50 && Math.abs(z) >= 1.0) {
    const isLong = dir === 'BULL';
    base.action = isLong ? 'LONG' : 'SHORT';
    base.direction = dir;
    base.confidence = score;
    base.stopLoss = isLong ? last.c - atr * 1.5 : last.c + atr * 1.5;
    base.takeProfit = isLong ? last.c + atr * 2.0 : last.c - atr * 2.0;
    base.tripleAPhase = score >= 80 ? 'FULL_ALIGNMENT' : 'AGGRESSION';
    base.grade = score >= 70 ? 'A' : 'B';
    base.reason = `공격성 ${score}점, Z=${z.toFixed(1)}, 연속${consDir}봉 ${dir}`;
  } else {
    base.reason = `공격성 ${score}점 — 진입 조건 미달`;
  }

  return base;
}

// ── Live Multi-Strategy Analysis ──────────────────────────────────────

/**
 * Comprehensive multi-strategy analysis for live data.
 */
export function analyzeMultiStrategy(
  data: AnalyticsData[],
  candles: OHLC[],
  fabioAnalysis?: FabioAnalysis | null,
): MultiStrategyAnalysis {
  const regime = detectRegime(data);
  const n = candles.length - 1;

  const meanRev = generateMeanReversionSignal(candles, n, 20);
  const trendFollow = generateTrendFollowingSignal(candles, n, 20);
  const scalp = generateScalpSignal(candles, n, 20, fabioAnalysis);

  return {
    regime,
    recommended: regime.recommended,
    signals: { meanRev, trendFollow, scalp },
  };
}

// ── Multi-Strategy Backtest ───────────────────────────────────────────

function emptyStats(): StrategyStats {
  return { trades: 0, wins: 0, losses: 0, winRate: 0, totalPnL: 0, profitFactor: 0, avgWin: 0, avgLoss: 0, maxDD: 0, sharpe: 0 };
}

function computeStrategyStats(trades: MSBacktestTrade[]): StrategyStats {
  if (trades.length === 0) return emptyStats();

  const wins = trades.filter(t => t.pnlPoints > 0);
  const losses = trades.filter(t => t.pnlPoints <= 0);
  const totalPnL = trades.reduce((s, t) => s + t.pnlPoints, 0);
  const grossProfit = wins.reduce((s, t) => s + t.pnlPoints, 0);
  const grossLoss = Math.abs(losses.reduce((s, t) => s + t.pnlPoints, 0));

  // Max drawdown
  let peak = 0, maxDD = 0, equity = 0;
  for (const t of trades) {
    equity += t.pnlPoints;
    if (equity > peak) peak = equity;
    const dd = peak - equity;
    if (dd > maxDD) maxDD = dd;
  }

  // Sharpe
  const pnls = trades.map(t => t.pnlPoints);
  const avgPnl = pnls.reduce((a, b) => a + b, 0) / pnls.length;
  const variance = pnls.reduce((s, p) => s + (p - avgPnl) ** 2, 0) / pnls.length;
  const stdPnl = Math.sqrt(variance);
  const sharpe = stdPnl > 0 ? (avgPnl / stdPnl) * Math.sqrt(252) : 0;

  return {
    trades: trades.length,
    wins: wins.length,
    losses: losses.length,
    winRate: (wins.length / trades.length) * 100,
    totalPnL,
    profitFactor: grossLoss > 0 ? grossProfit / grossLoss : grossProfit > 0 ? Infinity : 0,
    avgWin: wins.length > 0 ? grossProfit / wins.length : 0,
    avgLoss: losses.length > 0 ? grossLoss / losses.length : 0,
    maxDD,
    sharpe,
  };
}

/**
 * Run multi-strategy backtest on OHLC candles.
 */
export function runMultiStrategyBacktest(
  candles: OHLC[],
  config: MultiStrategyBacktestConfig = DEFAULT_MS_CONFIG,
  _asset: string = 'MES',
): MSBacktestResult {
  const n = candles.length;
  const lookback = config.lookback;

  const allTrades: MSBacktestTrade[] = [];
  const regimeHistory: MarketRegime[] = [];

  // Track active positions per strategy
  interface Position {
    strategy: StrategyName;
    direction: 'LONG' | 'SHORT';
    entryBar: number;
    entryPrice: number;
    stopLoss: number;
    takeProfit: number;
    trailingHigh: number;
    trailingLow: number;
  }

  const positions: Record<StrategyName, Position | null> = {
    MEAN_REVERSION: null,
    TREND_FOLLOWING: null,
    SCALP_MOMENTUM: null,
  };

  for (let i = 0; i < n; i++) {
    // Regime detection
    const regime = i >= lookback
      ? detectRegimeFromOHLC(candles, i, lookback)
      : { regime: 'MIXED' as MarketRegime, confidence: 0, indicators: { adx: null, bbWidth: null, diSpread: null, atrPct: null }, reason: '', recommended: null };
    regimeHistory.push(regime.regime);

    if (i < lookback) continue;

    const price = candles[i].c;
    const atr = computeATR(candles, i, 14);

    // ── Check exits for active positions ──

    // Mean Reversion exit
    if (positions.MEAN_REVERSION) {
      const pos = positions.MEAN_REVERSION;
      const { exit, reason } = shouldExitMeanReversion(candles, i, pos.direction, lookback, pos.entryBar, config.mrMaxHoldBars);
      const hitSL = pos.direction === 'LONG' ? price <= pos.stopLoss : price >= pos.stopLoss;
      const hitTP = pos.direction === 'LONG' ? price >= pos.takeProfit : price <= pos.takeProfit;

      if (exit || hitSL || hitTP) {
        const exitPrice = hitSL ? pos.stopLoss : hitTP ? pos.takeProfit : price;
        const pnl = pos.direction === 'LONG' ? exitPrice - pos.entryPrice : pos.entryPrice - exitPrice;
        allTrades.push({
          strategy: 'MEAN_REVERSION',
          regime: regimeHistory[pos.entryBar] || 'MIXED',
          direction: pos.direction,
          entryBar: pos.entryBar,
          entryPrice: pos.entryPrice,
          exitBar: i,
          exitPrice,
          pnlPoints: pnl,
          bars: i - pos.entryBar,
          exitReason: hitSL ? 'STOP_LOSS' : hitTP ? 'TAKE_PROFIT' : reason,
        });
        positions.MEAN_REVERSION = null;
      }
    }

    // Trend Following exit
    if (positions.TREND_FOLLOWING) {
      const pos = positions.TREND_FOLLOWING;
      // Update trailing
      if (candles[i].h > pos.trailingHigh) pos.trailingHigh = candles[i].h;
      if (candles[i].l < pos.trailingLow) pos.trailingLow = candles[i].l;

      const { exit, reason } = shouldExitTrendFollowing(candles, i, pos.direction, pos.entryBar, config.tfMaxHoldBars, pos.trailingHigh, pos.trailingLow);
      const hitSL = pos.direction === 'LONG' ? price <= pos.stopLoss : price >= pos.stopLoss;

      // Trailing stop
      const trailStop = pos.direction === 'LONG'
        ? pos.trailingHigh - atr * 1.5
        : pos.trailingLow + atr * 1.5;
      const hitTrail = pos.direction === 'LONG' ? price < trailStop : price > trailStop;

      if (exit || hitSL || hitTrail) {
        const exitPrice = hitSL ? pos.stopLoss : price;
        const pnl = pos.direction === 'LONG' ? exitPrice - pos.entryPrice : pos.entryPrice - exitPrice;
        allTrades.push({
          strategy: 'TREND_FOLLOWING',
          regime: regimeHistory[pos.entryBar] || 'MIXED',
          direction: pos.direction,
          entryBar: pos.entryBar,
          entryPrice: pos.entryPrice,
          exitBar: i,
          exitPrice,
          pnlPoints: pnl,
          bars: i - pos.entryBar,
          exitReason: hitSL ? 'STOP_LOSS' : hitTrail ? 'TRAILING_STOP' : reason,
        });
        positions.TREND_FOLLOWING = null;
      }
    }

    // Scalp exit
    if (positions.SCALP_MOMENTUM) {
      const pos = positions.SCALP_MOMENTUM;
      const hitSL = pos.direction === 'LONG' ? price <= pos.stopLoss : price >= pos.stopLoss;
      const hitTP = pos.direction === 'LONG' ? price >= pos.takeProfit : price <= pos.takeProfit;
      const maxHold = i - pos.entryBar >= config.scalpMaxHoldBars;

      if (hitSL || hitTP || maxHold) {
        const exitPrice = hitSL ? pos.stopLoss : hitTP ? pos.takeProfit : price;
        const pnl = pos.direction === 'LONG' ? exitPrice - pos.entryPrice : pos.entryPrice - exitPrice;
        allTrades.push({
          strategy: 'SCALP_MOMENTUM',
          regime: regimeHistory[pos.entryBar] || 'MIXED',
          direction: pos.direction,
          entryBar: pos.entryBar,
          entryPrice: pos.entryPrice,
          exitBar: i,
          exitPrice,
          pnlPoints: pnl,
          bars: i - pos.entryBar,
          exitReason: hitSL ? 'STOP_LOSS' : hitTP ? 'TAKE_PROFIT' : 'MAX_HOLD',
        });
        positions.SCALP_MOMENTUM = null;
      }
    }

    // ── Generate new entries (only if no active position for that strategy) ──

    // Mean Reversion
    if (!positions.MEAN_REVERSION) {
      const sig = generateMeanReversionSignal(candles, i, lookback);
      if (sig.action === 'LONG' || sig.action === 'SHORT') {
        positions.MEAN_REVERSION = {
          strategy: 'MEAN_REVERSION',
          direction: sig.action,
          entryBar: i,
          entryPrice: price,
          stopLoss: sig.stopLoss ?? (sig.action === 'LONG' ? price - atr * 2.5 : price + atr * 2.5),
          takeProfit: sig.takeProfit ?? (sig.action === 'LONG' ? price + atr * 3 : price - atr * 3),
          trailingHigh: candles[i].h,
          trailingLow: candles[i].l,
        };
      }
    }

    // Trend Following
    if (!positions.TREND_FOLLOWING) {
      const sig = generateTrendFollowingSignal(candles, i, lookback);
      if (sig.action === 'LONG' || sig.action === 'SHORT') {
        positions.TREND_FOLLOWING = {
          strategy: 'TREND_FOLLOWING',
          direction: sig.action,
          entryBar: i,
          entryPrice: price,
          stopLoss: sig.stopLoss ?? (sig.action === 'LONG' ? price - atr * 3 : price + atr * 3),
          takeProfit: sig.takeProfit ?? (sig.action === 'LONG' ? price + atr * 3 : price - atr * 3),
          trailingHigh: candles[i].h,
          trailingLow: candles[i].l,
        };
      }
    }

    // Scalp
    if (!positions.SCALP_MOMENTUM) {
      const sig = generateScalpSignal(candles, i, lookback);
      if (sig.action === 'LONG' || sig.action === 'SHORT') {
        positions.SCALP_MOMENTUM = {
          strategy: 'SCALP_MOMENTUM',
          direction: sig.action,
          entryBar: i,
          entryPrice: price,
          stopLoss: sig.stopLoss ?? (sig.action === 'LONG' ? price - atr * 1.5 : price + atr * 1.5),
          takeProfit: sig.takeProfit ?? (sig.action === 'LONG' ? price + atr * 2 : price - atr * 2),
          trailingHigh: candles[i].h,
          trailingLow: candles[i].l,
        };
      }
    }
  }

  // Close any remaining positions at last price
  const lastPrice = candles[n - 1].c;
  for (const key of Object.keys(positions) as StrategyName[]) {
    const pos = positions[key];
    if (pos) {
      const pnl = pos.direction === 'LONG' ? lastPrice - pos.entryPrice : pos.entryPrice - lastPrice;
      allTrades.push({
        strategy: key,
        regime: regimeHistory[pos.entryBar] || 'MIXED',
        direction: pos.direction,
        entryBar: pos.entryBar,
        entryPrice: pos.entryPrice,
        exitBar: n - 1,
        exitPrice: lastPrice,
        pnlPoints: pnl,
        bars: n - 1 - pos.entryBar,
        exitReason: 'END_OF_DATA',
      });
    }
  }

  // Compute per-strategy stats
  const strategyStats: Record<StrategyName, StrategyStats> = {
    MEAN_REVERSION: computeStrategyStats(allTrades.filter(t => t.strategy === 'MEAN_REVERSION')),
    TREND_FOLLOWING: computeStrategyStats(allTrades.filter(t => t.strategy === 'TREND_FOLLOWING')),
    SCALP_MOMENTUM: computeStrategyStats(allTrades.filter(t => t.strategy === 'SCALP_MOMENTUM')),
  };

  // Compute regime stats
  const regimeNames: MarketRegime[] = ['SQUEEZE', 'RANGE', 'TRENDING', 'VOLATILE', 'MIXED'];
  const regimeStats: RegimeStats[] = regimeNames.map(r => {
    const bars = regimeHistory.filter(rh => rh === r).length;
    const rTrades = allTrades.filter(t => t.regime === r);
    const wins = rTrades.filter(t => t.pnlPoints > 0).length;
    return {
      regime: r,
      bars,
      barsPct: n > 0 ? (bars / n) * 100 : 0,
      trades: rTrades.length,
      winRate: rTrades.length > 0 ? (wins / rTrades.length) * 100 : 0,
      totalPnL: rTrades.reduce((s, t) => s + t.pnlPoints, 0),
    };
  });

  // Auto-select: only count trades that match the recommended strategy for their regime
  const autoSelectTrades = allTrades.filter(t => {
    const recommended = getRecommendedForRegime(t.regime);
    return recommended === t.strategy;
  });
  const autoSelectStats = computeStrategyStats(autoSelectTrades);

  return {
    trades: allTrades,
    strategyStats,
    regimeStats,
    autoSelectStats,
    regimeHistory,
    totalBars: n,
  };
}

function getRecommendedForRegime(regime: MarketRegime): StrategyName | null {
  switch (regime) {
    case 'RANGE': return 'MEAN_REVERSION';
    case 'TRENDING': return 'TREND_FOLLOWING';
    case 'VOLATILE': return 'SCALP_MOMENTUM';
    case 'MIXED': return 'SCALP_MOMENTUM';
    case 'SQUEEZE': return null;
  }
}
