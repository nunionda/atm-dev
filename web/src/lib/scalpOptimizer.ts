/**
 * Scalp Engine — Backtest + Confluence + A/B Test.
 * Z-Score 기반 평균회귀 시그널 백테스트 엔진.
 *
 * 승률 가중 피트니스: WR 40% + PF 25% + Sharpe 15% - DD 10% + Trades 10%
 */

import type { OHLC, VolumeSRResult } from './scalpEngine';
import { ASSETS, computeVolumeSR, computeCompositeTrend } from './scalpEngine';
import { detectRegimeFromOHLC } from './strategyEngine';

/** Clamp value to [min,max] then normalize to [0,1] */
function clampNorm(value: number, min: number, max: number): number {
  return (Math.max(min, Math.min(max, value)) - min) / (max - min);
}
import { buildVolumeProfile } from './fabioEngine';

// ── Types ────────────────────────────────────────────────────────────

export interface ScalpParamSpec {
  key: string;
  label: string;
  min: number;
  max: number;
  step: number;
  default: number;
}

export interface ScalpBacktestConfig {
  lookback: number;
  atrMult: number;
  zEntryThreshold: number;
  tpMultiplier: number;
  maxHoldBars: number;
  trailingActivation: number;
  minRR: number;
  zExitThreshold: number;
  volumeFilter: number;
  momentumConfirm: number;   // legacy — kept for compat
  rsiEntryThreshold: number; // Cycle 1: 0=off, 30~45 = RSI filter
  regimeFilter: number;      // Cycle 2: 0=off, 1=skip trending counter, 2=+volatile counter
  tpMultRange: number;       // Cycle 4: TP mult in RANGE regime
  tpMultTrend: number;       // Cycle 4: TP mult in TRENDING regime
  tpMultVolatile: number;    // Cycle 4: TP mult in VOLATILE regime
  useMATarget: number;       // Cycle 4: 0=off, 1=use MA as TP target in RANGE
  volumeProfileFilter: number; // Cycle 3: 0=off, 1=only enter near key levels
  confluenceMinScore: number;  // Cycle 5: minimum confluence score (0~100)
  compositeTrendFilter: number; // Cycle 6: 0=off, 1=skip counter-trend entries, 2=boost aligned entries
  slippage: number;
  commission: number;
}

export interface ScalpBacktestTrade {
  barIndex: number;
  entryBar: number;
  exitBar: number;
  direction: 'LONG' | 'SHORT';
  entryPrice: number;
  exitPrice: number;
  stopPrice: number;
  targetPrice: number;
  result: 'WIN' | 'LOSS' | 'TIMEOUT' | 'Z_EXIT';
  pnlPoints: number;
  pnlPct: number;
  zAtEntry: number;
  reason: string;
  mae: number;   // Maximum Adverse Excursion (points)
  mfe: number;   // Maximum Favorable Excursion (points)
}

export interface ScalpBacktestResult {
  trades: ScalpBacktestTrade[];
  totalTrades: number;
  wins: number;
  losses: number;
  winRate: number;
  avgWin: number;
  avgLoss: number;
  profitFactor: number;
  sharpeApprox: number;
  maxDrawdownPct: number;
  maxConsecutiveLoss: number;
  netPnlPoints: number;
  avgHoldBars: number;
  // Component metrics (Cycle 0)
  entryAccuracy: number;      // % of trades where MFE > 0 (entered profitably at some point)
  directionAccuracy: number;  // % of trades where 1st bar moved favorably
  exitEfficiency: number;     // avg(realizedPnL / MFE) for winning trades
  avgMAE: number;
  avgMFE: number;
}

// ── Constants ────────────────────────────────────────────────────────

export const SCALP_PARAM_SPECS: ScalpParamSpec[] = [
  { key: 'lookback',           label: 'MA/σ 기간',          min: 5,   max: 50,  step: 1,    default: 20 },
  { key: 'atrMult',            label: 'ATR 손절 배수',      min: 0.5, max: 3.0, step: 0.1,  default: 1.5 },
  { key: 'zEntryThreshold',    label: 'Z 진입 임계',        min: 1.0, max: 3.0, step: 0.1,  default: 2.0 },
  { key: 'tpMultiplier',       label: 'TP 배수 (R:R)',      min: 1.0, max: 4.0, step: 0.25, default: 1.5 },
  { key: 'maxHoldBars',        label: '최대 보유봉',        min: 3,   max: 20,  step: 1,    default: 8 },
  { key: 'trailingActivation', label: 'BE스탑 활성화(R)',   min: 0.3, max: 2.0, step: 0.1,  default: 0.5 },
  { key: 'minRR',              label: '최소 R:R 필터',      min: 1.0, max: 3.0, step: 0.1,  default: 1.5 },
  { key: 'zExitThreshold',     label: 'Z 회귀 청산 임계',   min: 0.0, max: 1.0, step: 0.1,  default: 0.5 },
  { key: 'volumeFilter',       label: '거래량 필터',        min: 0.5, max: 2.0, step: 0.1,  default: 0.8 },
  { key: 'rsiEntryThreshold',  label: 'RSI 진입 필터',       min: 0,   max: 45,  step: 5,    default: 35 },
  { key: 'regimeFilter',       label: '레짐 필터',           min: 0,   max: 2,   step: 1,    default: 1 },
  { key: 'tpMultRange',        label: 'TP 횡보장',           min: 1.0, max: 3.0, step: 0.25, default: 1.5 },
  { key: 'tpMultTrend',        label: 'TP 추세장',           min: 1.5, max: 5.0, step: 0.25, default: 2.5 },
  { key: 'tpMultVolatile',     label: 'TP 변동장',           min: 1.0, max: 3.0, step: 0.25, default: 2.0 },
  { key: 'useMATarget',        label: 'MA 타겟 (횡보)',      min: 0,   max: 1,   step: 1,    default: 1 },
  { key: 'volumeProfileFilter', label: '볼륨프로파일 필터',  min: 0,   max: 1,   step: 1,    default: 0 },
  { key: 'confluenceMinScore', label: '합류 최소점수',       min: 0,   max: 80,  step: 5,    default: 0 },
  { key: 'compositeTrendFilter', label: '복합추세 필터',    min: 0,   max: 2,   step: 1,    default: 0 },
];

export const SCALP_FITNESS_WEIGHTS = {
  winRate: 0.40,
  profitFactor: 0.25,
  sharpe: 0.15,
  drawdown: 0.10,
  tradeCount: 0.10,
};

// ── Default Config ──────────────────────────────────────────────────

export function buildDefaultScalpConfig(asset: string): ScalpBacktestConfig {
  const cfg = ASSETS[asset] || ASSETS['ES'];
  return {
    lookback: 20,
    atrMult: 1.5,
    zEntryThreshold: 2.0,
    tpMultiplier: 1.5,
    maxHoldBars: 8,
    trailingActivation: 0.5,
    minRR: 1.5,
    zExitThreshold: 0.5,
    volumeFilter: 0.8,
    momentumConfirm: 0,
    rsiEntryThreshold: 35,
    regimeFilter: 1,
    tpMultRange: 1.5,
    tpMultTrend: 2.5,
    tpMultVolatile: 2.0,
    useMATarget: 1,
    volumeProfileFilter: 0,
    confluenceMinScore: 0,
    compositeTrendFilter: 0,
    slippage: asset.includes('K200') ? 1 : 0.5,
    commission: cfg.defaultCommission,
  };
}

// ── RSI Proxy (lightweight, no external deps) ───────────────────────

function computeRSI(closes: number[], period = 14): number | null {
  if (closes.length < period + 1) return null;
  let gainSum = 0, lossSum = 0;
  for (let i = closes.length - period; i < closes.length; i++) {
    const diff = closes[i] - closes[i - 1];
    if (diff > 0) gainSum += diff;
    else lossSum += Math.abs(diff);
  }
  const avgGain = gainSum / period;
  const avgLoss = lossSum / period;
  if (avgLoss === 0) return 100;
  const rs = avgGain / avgLoss;
  return 100 - 100 / (1 + rs);
}

// ── Confluence Scoring (Cycle 5) ────────────────────────────────────

export interface ConfluenceItem { label: string; met: boolean; weight: number }
export interface ConfluenceResult { score: number; grade: 'A' | 'B' | 'C' | 'NO_TRADE'; items: ConfluenceItem[] }

export function computeConfluence(
  z: number, rsi: number | null, regimeType: string,
  volumeRatio: number, nearVolumeSR: boolean, rr: number,
  volumeTrendAligned?: boolean,
  compositeTrendAligned?: boolean,
): ConfluenceResult {
  const items: ConfluenceItem[] = [
    { label: 'Z-Score ≥ 1.5', met: Math.abs(z) >= 1.5, weight: 20 },
    { label: 'RSI 확인', met: rsi !== null && ((z < 0 && rsi < 40) || (z > 0 && rsi > 60)), weight: 15 },
    { label: '레짐 정합', met: regimeType === 'RANGE' || regimeType === 'VOLATILE' || regimeType === 'MIXED', weight: 10 },
    { label: '거래량 ≥ 평균', met: volumeRatio >= 1.0, weight: 10 },
    { label: '일봉 S/R 근접', met: nearVolumeSR, weight: 10 },
    { label: 'R:R ≥ 1.5', met: rr >= 1.5, weight: 10 },
    { label: '거래량 추세 정합', met: volumeTrendAligned === true, weight: 5 },
    { label: '복합추세 정합', met: compositeTrendAligned === true, weight: 20 },
  ];
  const score = items.reduce((s, item) => s + (item.met ? item.weight : 0), 0);
  const grade = score >= 80 ? 'A' as const : score >= 55 ? 'B' as const : score >= 35 ? 'C' as const : 'NO_TRADE' as const;
  return { score, grade, items };
}

// ── Scalp Backtest ──────────────────────────────────────────────────

export function runScalpBacktest(
  allCandles: OHLC[],
  config: ScalpBacktestConfig,
  _asset: string,
): ScalpBacktestResult {
  const {
    lookback, atrMult, zEntryThreshold, tpMultiplier, maxHoldBars,
    trailingActivation, minRR, zExitThreshold, volumeFilter,
    slippage, commission,
  } = config;

  const trades: ScalpBacktestTrade[] = [];
  const minBars = Math.max(lookback + 2, 7);

  if (allCandles.length < minBars) return computeScalpBacktestStats([]);

  // Pre-compute 14-day volume S/R levels (cached for entire backtest)
  const srCandles = allCandles.slice(0, Math.min(14, allCandles.length));
  const srATR = srCandles.length >= 2
    ? srCandles.slice(1).reduce((s, c, j) => s + Math.max(c.h - c.l, Math.abs(c.h - srCandles[j].c), Math.abs(c.l - srCandles[j].c)), 0) / (srCandles.length - 1)
    : 1;
  const volumeSR: VolumeSRResult | null = allCandles.length >= 14
    ? computeVolumeSR(allCandles.slice(0, 14), allCandles[13].c, srATR)
    : null;

  let inPosition = false;
  let positionExitBar = 0;

  for (let i = minBars; i < allCandles.length; i++) {
    if (inPosition && i <= positionExitBar) continue;
    inPosition = false;

    // Compute window stats
    const cw = allCandles.slice(Math.max(0, i - lookback), i + 1);
    const closes = cw.map(c => c.c);
    const maSlice = closes.slice(-Math.min(lookback, closes.length));
    const ma = maSlice.reduce((a, b) => a + b, 0) / maSlice.length;
    const variance = maSlice.reduce((acc, p) => acc + (p - ma) ** 2, 0) / maSlice.length;
    const stdDev = Math.sqrt(variance);
    const currentPrice = closes[closes.length - 1];

    // ATR
    let atrSum = 0, atrCount = 0;
    for (let j = 1; j < cw.length; j++) {
      const tr = Math.max(
        cw[j].h - cw[j].l,
        Math.abs(cw[j].h - cw[j - 1].c),
        Math.abs(cw[j].l - cw[j - 1].c),
      );
      atrSum += tr;
      atrCount++;
    }
    const atr = atrCount > 0 ? atrSum / atrCount : 0;
    if (stdDev <= 0 || atr <= 0) continue;

    // Z-Score
    const z = (currentPrice - ma) / stdDev;

    // Minimum Z requirement (must be at least 1.0 to consider any entry)
    if (Math.abs(z) < 1.0) continue;

    const isLong = z < 0; // below mean → expect reversion up

    // Compute context signals for confluence scoring
    const volumes = cw.map(c => (c?.v) ?? 0);
    const avgVol = volumes.reduce((a, b) => a + b, 0) / volumes.length;
    const curVol = (allCandles[i]?.v) ?? 0;
    const volumeRatio = avgVol > 0 ? curVol / avgVol : 1;

    const rsiCloses = allCandles.slice(Math.max(0, i - 20), i + 1).map(c => c.c);
    const rsi = computeRSI(rsiCloses);

    const regime = detectRegimeFromOHLC(allCandles, i, lookback);

    // Volume S/R proximity check (14-day daily volume-based)
    let nearVolumeSR = false;
    let volumeTrendAligned = false;
    if (volumeSR && volumeSR.levels.length > 0) {
      const srDist = atr * 0.5;
      nearVolumeSR = volumeSR.levels.some(lv => Math.abs(currentPrice - lv.price) < srDist);
      // Volume trend alignment: increasing volume + Z direction matches mean reversion
      volumeTrendAligned = volumeSR.volumeTrend === 'INCREASING' && Math.abs(z) >= 1.5;
    }

    // Legacy volume profile filter (Cycle 3) — fallback if no volume S/R
    let nearKeyLevel = nearVolumeSR;
    if (!nearKeyLevel && (config.volumeProfileFilter ?? 0) >= 1) {
      const vpWindow = allCandles.slice(Math.max(0, i - lookback * 2), i + 1);
      if (vpWindow.length >= 5) {
        const profile = buildVolumeProfile(vpWindow, 0.25);
        const atrDist = atr * 0.5;
        nearKeyLevel = Math.abs(currentPrice - profile.poc) < atrDist
          || Math.abs(currentPrice - profile.vah) < atrDist
          || Math.abs(currentPrice - profile.val) < atrDist;
      }
    }

    const confMinScore = config.confluenceMinScore ?? 0;
    if (confMinScore > 0) {
      // Cycle 5: Confluence-based entry (replaces individual gates)
      const tentativeRR = tpMultiplier; // approximate R:R before regime adjustment
      // Composite trend alignment check for confluence
      let ctAligned = false;
      const ctConfWindow = allCandles.slice(Math.max(0, i - lookback * 2), i + 1);
      if (ctConfWindow.length >= 6) {
        const ctResult = computeCompositeTrend(ctConfWindow, currentPrice, atr);
        ctAligned = (isLong && ctResult.bias !== 'BEARISH') || (!isLong && ctResult.bias !== 'BULLISH');
      }
      const confluence = computeConfluence(z, rsi, regime.regime, volumeRatio, nearKeyLevel, tentativeRR, volumeTrendAligned, ctAligned);
      if (confluence.score < confMinScore) continue;
    } else {
      // Legacy mode: individual filters
      if (Math.abs(z) < zEntryThreshold) continue;

      // Volume filter
      if (volumeFilter > 0 && avgVol > 0 && volumeRatio < volumeFilter) continue;

      // RSI confirmation (Cycle 1)
      const rsiThresh = config.rsiEntryThreshold ?? 0;
      if (rsiThresh > 0 && rsi !== null) {
        if (isLong && rsi > (100 - rsiThresh)) continue;
        if (!isLong && rsi < rsiThresh) continue;
      }

      // Regime gate (Cycle 2)
      const regFilter = config.regimeFilter ?? 0;
      if (regFilter > 0) {
        if (regime.regime === 'SQUEEZE') continue;
        if (regime.regime === 'TRENDING' && regime.confidence >= 50) continue;
        if (regFilter >= 2 && regime.regime === 'VOLATILE' && regime.confidence >= 70) continue;
      }

      // Volume profile filter (Cycle 3)
      if ((config.volumeProfileFilter ?? 0) >= 1 && !nearKeyLevel) continue;
    }

    // Composite Trend filter (Cycle 6: SMC + OBV + Volume)
    const ctFilter = config.compositeTrendFilter ?? 0;
    if (ctFilter >= 1) {
      const trendWindow = allCandles.slice(Math.max(0, i - lookback * 2), i + 1);
      if (trendWindow.length >= 6) {
        const ct = computeCompositeTrend(trendWindow, currentPrice, atr);
        // Mode 1: skip counter-trend entries (mean reversion into strong trend)
        if (ct.bias === 'BULLISH' && !isLong && ct.confidence >= 40) continue;
        if (ct.bias === 'BEARISH' && isLong && ct.confidence >= 40) continue;
        // Mode 2: also skip weak signals in sideways (require higher Z)
        if (ctFilter >= 2 && ct.bias === 'SIDEWAYS' && Math.abs(z) < 2.0) continue;
      }
    }

    // SL & TP (Cycle 4: regime-adaptive TP)
    const atrStop = atr * atrMult;
    const regimeTP = regime.regime === 'TRENDING' ? (config.tpMultTrend ?? tpMultiplier)
      : regime.regime === 'VOLATILE' ? (config.tpMultVolatile ?? tpMultiplier)
      : regime.regime === 'RANGE' ? (config.tpMultRange ?? tpMultiplier)
      : tpMultiplier;
    let target = atrStop * regimeTP;
    // MA target override in RANGE (Cycle 4)
    if ((config.useMATarget ?? 0) >= 1 && regime.regime === 'RANGE') {
      const maDistance = Math.abs(currentPrice - ma);
      if (maDistance > 0 && maDistance < target) target = maDistance;
    }
    // S/R target adjustment: cap TP at next S/R level if closer
    if (volumeSR) {
      const nextSR = isLong
        ? volumeSR.resistances.find(r => r.price > currentPrice)
        : volumeSR.supports.find(s => s.price < currentPrice);
      if (nextSR) {
        const srDist = Math.abs(nextSR.price - currentPrice);
        if (srDist > atrStop && srDist < target) target = srDist;
      }
    }

    // Min R:R filter
    const actualRR = target / atrStop;
    if (actualRR < minRR) continue;

    const stopPrice = isLong ? currentPrice - atrStop : currentPrice + atrStop;
    const targetPrice = isLong ? currentPrice + target : currentPrice - target;

    // Forward Simulation
    let exitBar = i;
    let exitPrice = currentPrice;
    let result: ScalpBacktestTrade['result'] = 'TIMEOUT';
    let reason = '';
    const maxHold = Math.min(maxHoldBars, allCandles.length - i - 1);
    let activeStop = stopPrice;
    let tradeMFE = 0; // track max favorable excursion
    let tradeMAE = 0; // track max adverse excursion

    for (let j = 1; j <= maxHold; j++) {
      const bar = allCandles[i + j];
      if (!bar) break;
      exitBar = i + j;

      // Track MFE and MAE
      const barMFE = isLong ? bar.h - currentPrice : currentPrice - bar.l;
      const barMAE = isLong ? currentPrice - bar.l : bar.h - currentPrice;
      if (barMFE > tradeMFE) tradeMFE = barMFE;
      if (barMAE > tradeMAE) tradeMAE = barMAE;

      // Multi-stage trailing stop (Cycle 4)
      // Stage 1: BE stop when MFE >= trailingActivation × SL distance
      if (barMFE >= atrStop * trailingActivation) {
        const beStop = currentPrice;
        if (isLong && beStop > activeStop) activeStop = beStop;
        if (!isLong && beStop < activeStop) activeStop = beStop;
      }
      // Stage 2: Trail at 50% of MFE after 1R profit
      if (tradeMFE >= atrStop * 1.0) {
        const trailStop = isLong
          ? currentPrice + tradeMFE * 0.5
          : currentPrice - tradeMFE * 0.5;
        if (isLong && trailStop > activeStop) activeStop = trailStop;
        if (!isLong && trailStop < activeStop) activeStop = trailStop;
      }

      // Check SL
      if (isLong) {
        if (bar.l <= activeStop) { exitPrice = activeStop; result = 'LOSS'; reason = `SL@+${j}`; break; }
        if (bar.h >= targetPrice) { exitPrice = targetPrice; result = 'WIN'; reason = `TP@+${j}`; break; }
      } else {
        if (bar.h >= activeStop) { exitPrice = activeStop; result = 'LOSS'; reason = `SL@+${j}`; break; }
        if (bar.l <= targetPrice) { exitPrice = targetPrice; result = 'WIN'; reason = `TP@+${j}`; break; }
      }

      // Z-Exit: if Z reverts past threshold, exit at current close
      if (zExitThreshold > 0) {
        const exitWindow = allCandles.slice(Math.max(0, exitBar - lookback), exitBar + 1);
        const exitCloses = exitWindow.map(c => c.c);
        const exitMaSlice = exitCloses.slice(-Math.min(lookback, exitCloses.length));
        const exitMa = exitMaSlice.reduce((a, b) => a + b, 0) / exitMaSlice.length;
        const exitVar = exitMaSlice.reduce((acc, p) => acc + (p - exitMa) ** 2, 0) / exitMaSlice.length;
        const exitStd = Math.sqrt(exitVar);
        if (exitStd > 0) {
          const exitZ = (bar.c - exitMa) / exitStd;
          if (Math.abs(exitZ) < zExitThreshold) {
            exitPrice = bar.c;
            result = 'Z_EXIT';
            reason = `Z-revert@+${j}`;
            break;
          }
        }
      }
    }

    if (result === 'TIMEOUT') {
      const timeoutPrice = allCandles[exitBar]?.c ?? currentPrice;
      exitPrice = timeoutPrice;
      reason = `Timeout ${maxHold}bars`;
    }

    // Friction cost
    const frictionPoints = slippage * 2 + commission;
    const rawPnl = isLong ? exitPrice - currentPrice : currentPrice - exitPrice;
    const pnlPoints = rawPnl - frictionPoints;
    const pnlPct = currentPrice > 0 ? (pnlPoints / currentPrice) * 100 : 0;

    trades.push({
      barIndex: i, entryBar: i, exitBar,
      direction: isLong ? 'LONG' : 'SHORT',
      entryPrice: currentPrice, exitPrice, stopPrice, targetPrice,
      result: result === 'TIMEOUT'
        ? (pnlPoints > 0 ? 'WIN' : 'LOSS')
        : result === 'Z_EXIT'
          ? (pnlPoints > 0 ? 'WIN' : 'LOSS')
          : result,
      pnlPoints, pnlPct, zAtEntry: z, reason,
      mae: tradeMAE, mfe: tradeMFE,
    });

    inPosition = true;
    positionExitBar = exitBar;
  }

  return computeScalpBacktestStats(trades);
}

// ── Stats Computation ───────────────────────────────────────────────

export function computeScalpBacktestStats(trades: ScalpBacktestTrade[]): ScalpBacktestResult {
  if (trades.length === 0) {
    return {
      trades, totalTrades: 0, wins: 0, losses: 0, winRate: 0,
      avgWin: 0, avgLoss: 0, profitFactor: 0, sharpeApprox: 0,
      maxDrawdownPct: 0, maxConsecutiveLoss: 0, netPnlPoints: 0, avgHoldBars: 0,
      entryAccuracy: 0, directionAccuracy: 0, exitEfficiency: 0, avgMAE: 0, avgMFE: 0,
    };
  }

  const wins = trades.filter(t => t.result === 'WIN').length;
  const losses = trades.length - wins;
  const winRate = (wins / trades.length) * 100;

  const winTrades = trades.filter(t => t.result === 'WIN');
  const lossTrades = trades.filter(t => t.result !== 'WIN');
  const avgWin = winTrades.length > 0 ? winTrades.reduce((s, t) => s + t.pnlPoints, 0) / winTrades.length : 0;
  const avgLoss = lossTrades.length > 0 ? Math.abs(lossTrades.reduce((s, t) => s + t.pnlPoints, 0) / lossTrades.length) : 0;

  const grossWin = winTrades.reduce((s, t) => s + t.pnlPoints, 0);
  const grossLoss = Math.abs(lossTrades.reduce((s, t) => s + t.pnlPoints, 0));
  const profitFactor = grossLoss > 0 ? grossWin / grossLoss : grossWin > 0 ? 99 : 0;

  const netPnlPoints = trades.reduce((s, t) => s + t.pnlPoints, 0);

  // Sharpe approximation
  const pnls = trades.map(t => t.pnlPoints);
  const avgPnl = pnls.reduce((a, b) => a + b, 0) / pnls.length;
  const pnlVar = pnls.reduce((acc, p) => acc + (p - avgPnl) ** 2, 0) / pnls.length;
  const pnlStd = Math.sqrt(pnlVar);
  const sharpeApprox = pnlStd > 0 ? (avgPnl / pnlStd) * Math.sqrt(252) : 0;

  // Max drawdown
  let peak = 0, equity = 0, maxDD = 0;
  for (const t of trades) {
    equity += t.pnlPoints;
    if (equity > peak) peak = equity;
    const dd = peak > 0 ? ((peak - equity) / peak) * 100 : 0;
    if (dd > maxDD) maxDD = dd;
  }

  // Max consecutive losses
  let consLoss = 0, maxConsLoss = 0;
  for (const t of trades) {
    if (t.result !== 'WIN') { consLoss++; maxConsLoss = Math.max(maxConsLoss, consLoss); }
    else consLoss = 0;
  }

  // Avg hold bars
  const avgHoldBars = trades.reduce((s, t) => s + (t.exitBar - t.entryBar), 0) / trades.length;

  // Component metrics (Cycle 0)
  const entryAccuracy = (trades.filter(t => t.mfe > 0).length / trades.length) * 100;
  const directionAccuracy = (trades.filter(t => t.pnlPoints > 0 || t.mfe > 0).length / trades.length) * 100;
  const winTradesWithMFE = winTrades.filter(t => t.mfe > 0);
  const exitEfficiency = winTradesWithMFE.length > 0
    ? winTradesWithMFE.reduce((s, t) => s + (t.pnlPoints / t.mfe), 0) / winTradesWithMFE.length
    : 0;
  const avgMAE = trades.reduce((s, t) => s + t.mae, 0) / trades.length;
  const avgMFE = trades.reduce((s, t) => s + t.mfe, 0) / trades.length;

  return {
    trades, totalTrades: trades.length, wins, losses, winRate,
    avgWin, avgLoss, profitFactor, sharpeApprox,
    maxDrawdownPct: maxDD, maxConsecutiveLoss: maxConsLoss,
    netPnlPoints, avgHoldBars,
    entryAccuracy, directionAccuracy, exitEfficiency, avgMAE, avgMFE,
  };
}

// ── Fitness Function ────────────────────────────────────────────────

export function computeScalpFitness(
  result: ScalpBacktestResult,
  totalBars: number,
): number {
  if (result.totalTrades < 5) return -1000;

  const wrNorm = result.winRate / 100;
  const pfNorm = clampNorm(result.profitFactor, 0, 4);
  const shNorm = clampNorm(result.sharpeApprox, -2, 3);
  const ddPenalty = clampNorm(result.maxDrawdownPct, 0, 20);

  const idealTradeRate = totalBars / 8; // expect ~1 trade per 8 bars
  const tradeRateRatio = result.totalTrades / idealTradeRate;
  const tradeRegularizer = Math.exp(-2 * (tradeRateRatio - 1) ** 2);

  return (
    SCALP_FITNESS_WEIGHTS.winRate * wrNorm +
    SCALP_FITNESS_WEIGHTS.profitFactor * pfNorm +
    SCALP_FITNESS_WEIGHTS.sharpe * shNorm -
    SCALP_FITNESS_WEIGHTS.drawdown * ddPenalty +
    SCALP_FITNESS_WEIGHTS.tradeCount * tradeRegularizer
  );
}

// ── Decomposed Fitness (Cycle 6) ────────────────────────────────────

export interface DecomposedFitness {
  composite: number;
  entryQuality: number;      // entry accuracy + direction accuracy
  exitQuality: number;       // exit efficiency + avg MFE capture
  riskQuality: number;       // (1 - MDD) + Sharpe
  tradeFrequency: number;    // regularizer
}

export function computeDecomposedFitness(
  result: ScalpBacktestResult,
  totalBars: number,
): DecomposedFitness {
  const composite = computeScalpFitness(result, totalBars);
  if (result.totalTrades < 2) {
    return { composite, entryQuality: 0, exitQuality: 0, riskQuality: 0, tradeFrequency: 0 };
  }

  const entryQuality = (result.entryAccuracy / 100) * 0.6 + (result.directionAccuracy / 100) * 0.4;
  const exitQuality = Math.min(1, result.exitEfficiency) * 0.7 + clampNorm(result.avgMFE, 0, 20) * 0.3;
  const riskQuality = (1 - clampNorm(result.maxDrawdownPct, 0, 20)) * 0.5
    + clampNorm(result.sharpeApprox, -2, 3) * 0.5;
  const idealRate = totalBars / 8;
  const tradeFrequency = Math.exp(-2 * ((result.totalTrades / idealRate) - 1) ** 2);

  return { composite, entryQuality, exitQuality, riskQuality, tradeFrequency };
}

// ── A/B Test Runner (Cycle 6) ───────────────────────────────────────

export interface ABTestResult {
  configA: ScalpBacktestConfig;
  configB: ScalpBacktestConfig;
  resultA: ScalpBacktestResult;
  resultB: ScalpBacktestResult;
  fitnessA: DecomposedFitness;
  fitnessB: DecomposedFitness;
  winner: 'A' | 'B' | 'TIE';
  deltas: Record<string, number>;
}

export function runABTest(
  candles: OHLC[],
  asset: string,
  configA: ScalpBacktestConfig,
  configB: ScalpBacktestConfig,
): ABTestResult {
  const resultA = runScalpBacktest(candles, configA, asset);
  const resultB = runScalpBacktest(candles, configB, asset);
  const fitnessA = computeDecomposedFitness(resultA, candles.length);
  const fitnessB = computeDecomposedFitness(resultB, candles.length);

  const deltas: Record<string, number> = {
    composite: fitnessB.composite - fitnessA.composite,
    entryQuality: fitnessB.entryQuality - fitnessA.entryQuality,
    exitQuality: fitnessB.exitQuality - fitnessA.exitQuality,
    riskQuality: fitnessB.riskQuality - fitnessA.riskQuality,
    winRate: resultB.winRate - resultA.winRate,
    profitFactor: resultB.profitFactor - resultA.profitFactor,
    sharpe: resultB.sharpeApprox - resultA.sharpeApprox,
    maxDD: resultB.maxDrawdownPct - resultA.maxDrawdownPct,
    trades: resultB.totalTrades - resultA.totalTrades,
  };

  const margin = 0.02; // 2% margin for TIE
  const winner = fitnessB.composite > fitnessA.composite + margin ? 'B'
    : fitnessA.composite > fitnessB.composite + margin ? 'A' : 'TIE';

  return { configA, configB, resultA, resultB, fitnessA, fitnessB, winner, deltas };
}

// (Optimizer infrastructure removed — 50 daily bars insufficient for 17-param optimization)
