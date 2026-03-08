/**
 * Fabio Valentini Scalping Strategy Engine
 * AMT 3-Step Filter + Triple-A + Grade System + Session Tracker
 *
 * Playbook Reference: stock_theory/scalpingPlaybook.md
 */

import type { OHLC, ScalpResult, ScalpInputs } from './scalpEngine';

// ── Types ─────────────────────────────────────────────────────────────

export type MarketState = 'BALANCE' | 'IMBALANCE_BULL' | 'IMBALANCE_BEAR' | 'UNKNOWN';
export type SetupModel = 'TREND_CONTINUATION' | 'MEAN_REVERSION' | 'NONE';
export type SetupGrade = 'A' | 'B' | 'C' | 'NO_TRADE';
export type TripleAPhase = 'NONE' | 'ABSORPTION' | 'ACCUMULATION' | 'AGGRESSION' | 'FULL_ALIGNMENT';
export type RiskTier = 'MAX' | 'HALF' | 'QUARTER';

export interface AMTFilter {
  marketState: MarketState;
  marketStateScore: number;      // 0~100 confidence
  marketStateReason: string;
  location: LocationAnalysis;
  aggression: AggressionAnalysis;
  allPassed: boolean;
}

export interface LocationAnalysis {
  currentZone: 'ABOVE_VAH' | 'IN_VALUE' | 'BELOW_VAL' | 'AT_POC' | 'AT_LVN';
  vah: number;      // Value Area High (MA + 1σ proxy)
  val: number;      // Value Area Low (MA - 1σ proxy)
  poc: number;      // Point of Control (MA proxy)
  lvnZones: number[];  // Low Volume Nodes
  distFromPOC: number;
  isAtKeyLevel: boolean;
}

export interface AggressionAnalysis {
  detected: boolean;
  direction: 'BULL' | 'BEAR' | 'NEUTRAL';
  score: number;          // 0~100
  bodyRatio: number;      // avg body/range ratio of last N candles
  rangeExpansion: number; // current range vs avg range ratio
  consecutiveDir: number; // consecutive directional candles
  reason: string;
}

export interface TripleAResult {
  phase: TripleAPhase;
  absorption: { detected: boolean; score: number; candles: number };
  accumulation: { detected: boolean; score: number; candles: number };
  aggression: { detected: boolean; score: number; direction: 'BULL' | 'BEAR' | 'NEUTRAL' };
  fullAlignment: boolean;
}

export interface GradeResult {
  grade: SetupGrade;
  confluenceCount: number;
  confluenceItems: { label: string; met: boolean; detail: string }[];
  riskMultiplier: number;
  riskTier: RiskTier;
  adjustedContracts: number;
}

export interface SessionTrade {
  id: string;
  time: string;
  result: 'WIN' | 'LOSS' | 'SCRATCH';
  pnlTicks: number;
  grade: SetupGrade;
  model: SetupModel;
  note?: string;
}

export interface SessionState {
  trades: SessionTrade[];
  totalPnL: number;
  winCount: number;
  lossCount: number;
  scratchCount: number;
  consecutiveLosses: number;
  currentRiskTier: RiskTier;
  shouldStop: boolean;
  stopReason: string;
  canScaleUp: boolean;
  sessionWinRate: number;
}

export interface VerifyItem {
  label: string;
  hint: string;
  autoChecked?: boolean;
  autoDetail?: string;
}

export interface ChecklistItem {
  id: string;
  step: number;
  label: string;
  detail: string;
  auto: boolean;
  checked: boolean;
  autoValue?: string;
  verifyItems?: VerifyItem[];
}

export interface FabioAnalysis {
  amt: AMTFilter;
  model: SetupModel;
  modelReason: string;
  tripleA: TripleAResult;
  grade: GradeResult;
  session: SessionState;
  checklist: ChecklistItem[];
  intradaySource?: 'INTRADAY_30M' | 'DAILY_FALLBACK';
}

/** 날짜별 장중 30분봉 맵 (date string → OHLC[]) */
export type IntradayBarMap = Map<string, OHLC[]>;

// ── Volume Profile Building ───────────────────────────────────────────

export interface VolumeProfile {
  poc: number; // Point of Control
  vah: number; // Value Area High
  val: number; // Value Area Low
  nodes: { price: number; volume: number }[];
}

export function buildVolumeProfile(candles: OHLC[], tickSize = 0.25): VolumeProfile {
  if (candles.length === 0) return { poc: 0, vah: 0, val: 0, nodes: [] };

  const buckets = new Map<number, number>();
  let totalVolume = 0;

  for (const c of candles) {
    const v = c.v || 100; // fallback if missing

    // simpler pure binning for POC calculation
    const binC = Math.round(c.c / tickSize) * tickSize;
    buckets.set(binC, (buckets.get(binC) || 0) + v * 0.5); // 50% at close

    const binO = Math.round(c.o / tickSize) * tickSize;
    buckets.set(binO, (buckets.get(binO) || 0) + v * 0.3); // 30% at open

    const binHL = Math.round((c.h + c.l) / 2 / tickSize) * tickSize;
    buckets.set(binHL, (buckets.get(binHL) || 0) + v * 0.2); // 20% at mid-range

    totalVolume += v;
  }

  // Sort nodes by price
  const nodes = Array.from(buckets.entries())
    .map(([price, volume]) => ({ price, volume }))
    .sort((a, b) => a.price - b.price);

  if (nodes.length === 0) return { poc: 0, vah: 0, val: 0, nodes: [] };

  // Find POC
  let pocBase = nodes[0];
  for (const n of nodes) {
    if (n.volume > pocBase.volume) {
      pocBase = n;
    }
  }
  const poc = pocBase.price;

  // Calculate Value Area (70% of total volume)
  const targetVA = totalVolume * 0.70;
  let currentVA = pocBase.volume;

  let pocIdx = nodes.findIndex(n => n.price === pocBase.price);
  let upperIdx = pocIdx;
  let lowerIdx = pocIdx;

  while (currentVA < targetVA && (upperIdx < nodes.length - 1 || lowerIdx > 0)) {
    const nextUpper = upperIdx < nodes.length - 1 ? nodes[upperIdx + 1].volume : -1;
    const nextLower = lowerIdx > 0 ? nodes[lowerIdx - 1].volume : -1;

    if (nextUpper === -1 && nextLower === -1) break;

    // Check two steps out for dual-distribution handling (simplified)
    const upper2 = upperIdx < nodes.length - 2 ? nodes[upperIdx + 1].volume + nodes[upperIdx + 2].volume : nextUpper;
    const lower2 = lowerIdx > 1 ? nodes[lowerIdx - 1].volume + nodes[lowerIdx - 2].volume : nextLower;

    if (upper2 > lower2) {
      upperIdx++;
      currentVA += nodes[upperIdx].volume;
    } else {
      lowerIdx--;
      currentVA += nodes[lowerIdx].volume;
    }
  }

  return {
    poc,
    vah: nodes[upperIdx].price,
    val: nodes[lowerIdx].price,
    nodes
  };
}

// ── AMT Market State Detection ────────────────────────────────────────

function detectMarketState(candles: OHLC[], z: number): {
  state: MarketState; score: number; reason: string; profile: VolumeProfile;
} {
  const profile = buildVolumeProfile(candles);
  if (candles.length < 5) return { state: 'UNKNOWN', score: 0, reason: '데이터 부족 (최소 5봉 필요)', profile };

  const { vah, val } = profile;
  const recent = candles.slice(-10);

  // Count candles within Value Area
  const inVA = recent.filter(c => c.c >= val && c.c <= vah).length;
  const inVAPct = inVA / recent.length;

  // Directional momentum: consecutive closes in one direction
  let bullMomentum = 0, bearMomentum = 0;
  for (let i = recent.length - 1; i >= 1; i--) {
    if (recent[i].c > recent[i - 1].c) bullMomentum++;
    else if (recent[i].c < recent[i - 1].c) bearMomentum++;
    else break;
  }

  // Range expansion check
  const ranges = recent.map(c => c.h - c.l);
  const avgRange = ranges.reduce((a, b) => a + b, 0) / ranges.length;
  const lastRange = ranges[ranges.length - 1];
  const rangeExpansion = avgRange > 0 ? lastRange / avgRange : 1;

  // Balance: 70%+ of candles in VA, no strong momentum
  if (inVAPct >= 0.6 && Math.abs(z) < 1.5 && rangeExpansion < 1.5) {
    const score = Math.min(100, Math.round(inVAPct * 100 + (1.5 - Math.abs(z)) * 20));
    return {
      state: 'BALANCE',
      score,
      reason: `VA 내 체류 ${Math.round(inVAPct * 100)}%, Z=${z.toFixed(1)}, 방향성 약함`,
      profile,
    };
  }

  // Imbalance: price outside VA with momentum
  if (Math.abs(z) >= 1.0 || inVAPct < 0.5) {
    const isBull = z < -1.0 || (bullMomentum >= 3 && candles[candles.length - 1].c > vah);
    const isBear = z > 1.0 || (bearMomentum >= 3 && candles[candles.length - 1].c < val);

    if (isBull && !isBear) {
      const score = Math.min(100, Math.round(Math.abs(z) * 25 + bullMomentum * 15 + rangeExpansion * 10));
      return {
        state: 'IMBALANCE_BULL',
        score,
        reason: `상방 이탈 Z=${z.toFixed(1)}, 연속상승 ${bullMomentum}봉, 레인지확장 ${rangeExpansion.toFixed(1)}x`,
        profile
      };
    }
    if (isBear && !isBull) {
      const score = Math.min(100, Math.round(Math.abs(z) * 25 + bearMomentum * 15 + rangeExpansion * 10));
      return {
        state: 'IMBALANCE_BEAR',
        score,
        reason: `하방 이탈 Z=${z.toFixed(1)}, 연속하락 ${bearMomentum}봉, 레인지확장 ${rangeExpansion.toFixed(1)}x`,
        profile
      };
    }

    // Ambiguous imbalance
    const dir = z <= 0 ? 'IMBALANCE_BULL' : 'IMBALANCE_BEAR';
    return {
      state: dir as MarketState,
      score: Math.round(Math.abs(z) * 20 + 20),
      reason: `VA 밖 ${Math.round((1 - inVAPct) * 100)}%, Z=${z.toFixed(1)}, 방향성 미약`,
      profile
    };
  }

  // Transitional
  return {
    state: 'BALANCE',
    score: Math.round(inVAPct * 80),
    reason: `전환 구간 — VA 내 ${Math.round(inVAPct * 100)}%, Z=${z.toFixed(1)}`,
    profile
  };
}

// ── Location Analysis ─────────────────────────────────────────────────

function analyzeLocation(profile: VolumeProfile, currentPrice: number, stdDev: number): LocationAnalysis {
  const { vah, val, poc, nodes } = profile;

  // LVN detection: find local minimums in the volume profile
  const lvnZones: number[] = [];
  if (nodes.length > 5) {
    // Smoothed search for valleys
    for (let i = 2; i < nodes.length - 2; i++) {
      const vPrev2 = nodes[i - 2].volume;
      const vPrev = nodes[i - 1].volume;
      const vCur = nodes[i].volume;
      const vNext = nodes[i + 1].volume;
      const vNext2 = nodes[i + 2].volume;

      // True valley + low absolute volume relative to POC
      if (vCur < vPrev && vCur < vNext && vCur < vPrev2 && vCur < vNext2) {
        if (vCur < nodes.reduce((a, b) => Math.max(a, b.volume), 0) * 0.3) {
          lvnZones.push(nodes[i].price);
        }
      }
    }
  }

  const distFromPOC = currentPrice - poc;
  let currentZone: LocationAnalysis['currentZone'] = 'IN_VALUE';
  if (currentPrice > vah) currentZone = 'ABOVE_VAH';
  else if (currentPrice < val) currentZone = 'BELOW_VAL';
  else if (Math.abs(currentPrice - poc) < stdDev * 0.2) currentZone = 'AT_POC';

  // Check if near an LVN
  const nearLVN = lvnZones.some(z => Math.abs(currentPrice - z) < stdDev * 0.3);
  if (nearLVN) currentZone = 'AT_LVN';

  const isAtKeyLevel = currentZone !== 'IN_VALUE';

  return { currentZone, vah, val, poc, lvnZones, distFromPOC, isAtKeyLevel };
}

// ── Aggression Analysis ───────────────────────────────────────────────

export function analyzeAggression(candles: OHLC[]): AggressionAnalysis {
  if (candles.length < 3) {
    return { detected: false, direction: 'NEUTRAL', score: 0, bodyRatio: 0, rangeExpansion: 0, consecutiveDir: 0, reason: '데이터 부족' };
  }

  const recent = candles.slice(-5);
  const last = recent[recent.length - 1];

  // Body/range ratio (proxy for aggression — large body = aggressive directional move)
  const bodyRatios = recent.map(c => {
    const range = c.h - c.l;
    const body = Math.abs(c.c - c.o);
    return range > 0 ? body / range : 0;
  });
  const lastBodyRatio = bodyRatios[bodyRatios.length - 1];

  // Range expansion
  const allCandles = candles.slice(-20);
  const ranges = allCandles.map(c => c.h - c.l);
  const avgRange = ranges.reduce((a, b) => a + b, 0) / ranges.length || 1;
  const lastRange = last.h - last.l;
  const rangeExpansion = lastRange / avgRange;

  // Volume surge
  const vols = allCandles.map(c => c.v || 0);
  const avgVol = vols.reduce((a, b) => a + b, 0) / vols.length || 1;
  const volExpansion = (last.v || 0) / avgVol;

  let consecutiveDir = 0;
  const dir = last.c > last.o ? 'BULL' : 'BEAR'; // Determine direction based on last candle
  let direction: 'BULL' | 'BEAR' | 'NEUTRAL' = 'NEUTRAL';
  for (let i = candles.length - 1; i >= Math.max(0, candles.length - 5); i--) {
    const isBull = candles[i].c > candles[i].o;
    if (consecutiveDir === 0) {
      direction = isBull ? 'BULL' : 'BEAR';
      consecutiveDir = 1;
    } else if ((isBull && direction === 'BULL') || (!isBull && direction === 'BEAR')) {
      consecutiveDir++;
    } else {
      break;
    }
  }

  // Scoring
  const isAggressive = lastBodyRatio > 0.6 && rangeExpansion > 1.2 && volExpansion > 1.2;

  let score = 0;
  if (isAggressive) {
    score = Math.min(100, Math.round(lastBodyRatio * 40 + rangeExpansion * 20 + volExpansion * 20 + consecutiveDir * 10));
  }

  return {
    detected: isAggressive,
    direction: dir,
    score,
    bodyRatio: lastBodyRatio,
    rangeExpansion,
    consecutiveDir,
    reason: isAggressive
      ? `방향성 폭발 (${dir}) — 바디 ${(lastBodyRatio * 100).toFixed(0)}%, 레인지 ${rangeExpansion.toFixed(1)}x, 볼륨 ${volExpansion.toFixed(1)}x`
      : `공격성 미달 — 바디 ${(lastBodyRatio * 100).toFixed(0)}%, 레인지 ${rangeExpansion.toFixed(1)}x`,
  };
}

// ── Triple-A Detection ────────────────────────────────────────────────

export function detectTripleA(candles: OHLC[]): TripleAResult {
  const result: TripleAResult = {
    phase: 'NONE',
    absorption: { detected: false, score: 0, candles: 0 },
    accumulation: { detected: false, score: 0, candles: 0 },
    aggression: { detected: false, score: 0, direction: 'NEUTRAL' },
    fullAlignment: false,
  };

  if (candles.length < 5) return result;

  const recent = candles.slice(-10);

  const ranges = recent.map(c => c.h - c.l);
  const vols = recent.map(c => c.v || 0);
  const avgRange = ranges.reduce((a, b) => a + b, 0) / ranges.length || 1;
  const avgVol = vols.reduce((a, b) => a + b, 0) / vols.length || 1;

  // 1. Absorption: High volume + narrow range -> passive absorbing active
  // Look in the last 3-5 bars for this signature
  let absScore = 0;
  let absCount = 0;
  for (let i = recent.length - 5; i < recent.length - 1; i++) {
    if (i < 0) continue;
    const c = recent[i];
    const rExp = (c.h - c.l) / avgRange;
    const vExp = (c.v || 0) / avgVol;
    if (vExp > 1.2 && rExp < 0.8) {
      absScore += (vExp - rExp) * 20; // Volume high, range low -> high score
      absCount++;
    }
  }
  if (absScore > 30) {
    result.absorption = { detected: true, score: Math.min(100, Math.round(absScore)), candles: absCount };
  }

  // 2. Accumulation: Declining volume + tight consolidation
  let accScore = 0;
  let accCount = 0;
  // Check last 3 candles for narrowing range and lower volume
  const accCandles = recent.slice(-3);
  const accRanges = accCandles.map(c => c.h - c.l);
  const accVols = accCandles.map(c => c.v || 0);

  if (accRanges.every(r => r < avgRange * 0.8) && accVols.every(v => v < avgVol * 0.8)) {
    accScore = 60; // Base score for tight range
    accCount = accCandles.length;
  }
  if (accScore > 0) {
    result.accumulation = { detected: true, score: accScore, candles: accCount };
  }

  // 3. Aggression: Final bar large expansion (Aggression Analysis already handles part of this)
  const aggAnalysis = analyzeAggression(candles);
  if (aggAnalysis.detected) {
    result.aggression = { detected: true, score: aggAnalysis.score, direction: aggAnalysis.direction };
  }

  // Synthesis
  if (result.absorption.detected && result.accumulation.detected && result.aggression.detected) {
    result.fullAlignment = true;
    result.phase = 'FULL_ALIGNMENT';
  } else if (result.aggression.detected) {
    result.phase = 'AGGRESSION';
  } else if (result.accumulation.detected) {
    result.phase = 'ACCUMULATION';
  } else if (result.absorption.detected) {
    result.phase = 'ABSORPTION';
  }

  return result;
}

// ── Intraday Drilldown (30min → Triple-A + Aggression) ────────────────

/**
 * AnalyticsData[] → 날짜별 OHLC[] 맵 구축.
 * datetime "2024-01-15 09:30:00" → date key "2024-01-15"
 */
export function buildIntradayBarMap(
  data: Array<{ datetime: string; open: number; high: number; low: number; close: number; volume: number }>,
): IntradayBarMap {
  const map: IntradayBarMap = new Map();
  for (const d of data) {
    const dateStr = d.datetime.split(' ')[0];
    if (!map.has(dateStr)) map.set(dateStr, []);
    map.get(dateStr)!.push({
      o: d.open > 0 ? d.open : d.close,
      h: d.high > 0 ? d.high : d.close,
      l: d.low > 0 ? d.low : d.close,
      c: d.close,
      v: d.volume ?? 0,
    });
  }
  return map;
}

/**
 * 30분봉 드릴다운: 해당 날짜의 장중 봉이 있으면 사용, 없으면 일봉 폴백.
 */
export function drilldownIntradayAnalysis(
  dailyWindow: OHLC[],
  intradayMap: IntradayBarMap | undefined,
  dateStr: string | undefined,
): { tripleA: TripleAResult; aggression: AggressionAnalysis; source: 'INTRADAY_30M' | 'DAILY_FALLBACK' } {
  if (intradayMap && dateStr) {
    const bars = intradayMap.get(dateStr);
    if (bars && bars.length >= 5) {
      return {
        tripleA: detectTripleA(bars),
        aggression: analyzeAggression(bars),
        source: 'INTRADAY_30M',
      };
    }
  }
  return {
    tripleA: detectTripleA(dailyWindow),
    aggression: analyzeAggression(dailyWindow),
    source: 'DAILY_FALLBACK',
  };
}

// ── Momentum Proxies (for backtest confluence) ────────────────────────

/** RSI proxy from OHLC closes */
export function computeRSIProxy(candles: OHLC[], period: number = 14): number | null {
  if (candles.length < period + 1) return null;
  let gains = 0, losses = 0;
  for (let i = candles.length - period; i < candles.length; i++) {
    const delta = candles[i].c - candles[i - 1].c;
    if (delta > 0) gains += delta;
    else losses -= delta;
  }
  const avgGain = gains / period;
  const avgLoss = losses / period;
  if (avgLoss === 0) return 100;
  const rs = avgGain / avgLoss;
  return 100 - (100 / (1 + rs));
}

/** MACD proxy using EMA approximation */
export function computeMACDProxy(candles: OHLC[]): {
  histogram: number; bullCross: boolean; bearCross: boolean;
} | null {
  if (candles.length < 27) return null;
  const closes = candles.map(c => c.c);

  const ema = (data: number[], period: number): number[] => {
    const k = 2 / (period + 1);
    const result = [data[0]];
    for (let i = 1; i < data.length; i++) {
      result.push(data[i] * k + result[i - 1] * (1 - k));
    }
    return result;
  };

  const ema12 = ema(closes, 12);
  const ema26 = ema(closes, 26);
  const macdLine = ema12.map((v, i) => v - ema26[i]);
  const signalLine = ema(macdLine.slice(25), 9);

  const macd = macdLine[macdLine.length - 1];
  const signal = signalLine[signalLine.length - 1];
  const histogram = macd - signal;

  const prevMacd = macdLine[macdLine.length - 2];
  const prevSignal = signalLine.length > 1 ? signalLine[signalLine.length - 2] : signal;

  return {
    histogram,
    bullCross: prevMacd <= prevSignal && macd > signal,
    bearCross: prevMacd >= prevSignal && macd < signal,
  };
}

// ── Setup Model Selection ─────────────────────────────────────────────

function selectModel(marketState: MarketState): { model: SetupModel; reason: string } {
  switch (marketState) {
    case 'IMBALANCE_BULL':
      return { model: 'TREND_CONTINUATION', reason: '불균형 상방 → LVN 풀백 매수 대기' };
    case 'IMBALANCE_BEAR':
      return { model: 'TREND_CONTINUATION', reason: '불균형 하방 → LVN 풀백 매도 대기' };
    case 'BALANCE':
      return { model: 'MEAN_REVERSION', reason: '균형 상태 → 브레이크아웃 실패 시 평균회귀' };
    default:
      return { model: 'NONE', reason: '시장 상태 판단 불가 — 관망' };
  }
}

// ── Grade System ──────────────────────────────────────────────────────

function computeGrade(
  amt: AMTFilter,
  tripleA: TripleAResult,
  scalpResult: ScalpResult,
  session: SessionState,
): GradeResult {
  const items: GradeResult['confluenceItems'] = [
    {
      label: '구조 (Z방향성)',
      met: Math.abs(scalpResult.z) >= 1.0,
      detail: `Z = ${scalpResult.z.toFixed(2)}, 방향: ${scalpResult.zSignal}`,
    },
    {
      label: 'VWAP/MA 레벨 위치',
      met: amt.location.isAtKeyLevel,
      detail: `Zone: ${amt.location.currentZone}, POC거리: ${amt.location.distFromPOC.toFixed(1)}p`,
    },
    {
      label: '임밸런스/흡수 (Triple-A)',
      met: tripleA.absorption.detected || tripleA.fullAlignment,
      detail: tripleA.fullAlignment
        ? 'FULL ALIGNMENT 감지'
        : tripleA.absorption.detected
          ? `흡수 감지 (${tripleA.absorption.candles}봉)`
          : '미감지',
    },
    {
      label: '모멘텀 전환 / 공격성',
      met: amt.aggression.detected,
      detail: `공격성 ${amt.aggression.score}점, ${amt.aggression.direction}`,
    },
    {
      label: '순 기대값 양수',
      met: scalpResult.netEV > 0,
      detail: `Net EV = ${scalpResult.netEV.toFixed(2)}t`,
    },
    {
      label: 'Kelly 양수',
      met: scalpResult.kelly > 0,
      detail: `Kelly = ${(scalpResult.kelly * 100).toFixed(1)}%`,
    },
  ];

  const confluenceCount = items.filter(i => i.met).length;

  let grade: SetupGrade;
  let riskMultiplier: number;
  let riskTier: RiskTier;

  // Apply session scaling rules
  if (session.shouldStop) {
    grade = 'NO_TRADE';
    riskMultiplier = 0;
    riskTier = 'QUARTER';
  } else if (session.consecutiveLosses >= 2) {
    // Scale down after 2 consecutive losses
    grade = 'C';
    riskMultiplier = 0.25;
    riskTier = 'QUARTER';
  } else if (confluenceCount >= 5) {
    grade = 'A';
    riskMultiplier = session.canScaleUp ? 1.0 : 0.75;
    riskTier = 'MAX';
  } else if (confluenceCount >= 3) {
    grade = 'B';
    riskMultiplier = 0.5;
    riskTier = 'HALF';
  } else if (confluenceCount >= 2) {
    grade = 'C';
    riskMultiplier = 0.25;
    riskTier = 'QUARTER';
  } else {
    grade = 'NO_TRADE';
    riskMultiplier = 0;
    riskTier = 'QUARTER';
  }

  const adjustedContracts = Math.max(0, Math.round(scalpResult.recContracts * riskMultiplier));

  return { grade, confluenceCount, confluenceItems: items, riskMultiplier, riskTier, adjustedContracts };
}

// ── Session Tracker ───────────────────────────────────────────────────

export function createInitialSession(): SessionState {
  return {
    trades: [],
    totalPnL: 0,
    winCount: 0,
    lossCount: 0,
    scratchCount: 0,
    consecutiveLosses: 0,
    currentRiskTier: 'QUARTER',  // Start small
    shouldStop: false,
    stopReason: '',
    canScaleUp: false,
    sessionWinRate: 0,
  };
}

export function addTradeToSession(session: SessionState, trade: Omit<SessionTrade, 'id' | 'time'>, dailyLossLimit: number): SessionState {
  const newTrade: SessionTrade = {
    ...trade,
    id: `T${Date.now()}`,
    time: new Date().toLocaleTimeString('ko-KR'),
  };

  const trades = [...session.trades, newTrade];
  const totalPnL = trades.reduce((sum, t) => sum + t.pnlTicks, 0);
  const winCount = trades.filter(t => t.result === 'WIN').length;
  const lossCount = trades.filter(t => t.result === 'LOSS').length;
  const scratchCount = trades.filter(t => t.result === 'SCRATCH').length;

  // Consecutive losses
  let consecutiveLosses = 0;
  for (let i = trades.length - 1; i >= 0; i--) {
    if (trades[i].result === 'LOSS') consecutiveLosses++;
    else break;
  }

  // Stop conditions
  let shouldStop = false;
  let stopReason = '';
  if (consecutiveLosses >= 3) {
    shouldStop = true;
    stopReason = '연속 3회 손절 — 당일 거래 중단';
  }
  if (dailyLossLimit > 0 && totalPnL <= -dailyLossLimit) {
    shouldStop = true;
    stopReason = `일일 손실 한도 (${dailyLossLimit}t) 도달 — 거래 중단`;
  }

  // Scale rules
  const canScaleUp = totalPnL > 0 && consecutiveLosses === 0;

  let currentRiskTier: RiskTier = 'QUARTER';
  if (shouldStop) currentRiskTier = 'QUARTER';
  else if (consecutiveLosses >= 2) currentRiskTier = 'QUARTER';
  else if (canScaleUp && totalPnL > 5) currentRiskTier = 'MAX';
  else if (totalPnL > 0) currentRiskTier = 'HALF';

  const totalDecided = winCount + lossCount;
  const sessionWinRate = totalDecided > 0 ? (winCount / totalDecided) * 100 : 0;

  return {
    trades, totalPnL, winCount, lossCount, scratchCount,
    consecutiveLosses, currentRiskTier, shouldStop, stopReason,
    canScaleUp, sessionWinRate,
  };
}

// ── Checklist Generator ───────────────────────────────────────────────

export function generateChecklist(
  amt: AMTFilter,
  model: SetupModel,
  grade: GradeResult,
  scalpResult: ScalpResult,
  manualChecks: Record<string, boolean>,
): ChecklistItem[] {
  const fmtNum = (v: number, d = 1) => v.toFixed(d);
  const hasPOC = amt.location.poc > 0;
  const hasVAH = amt.location.vah > 0;
  const hasVAL = amt.location.val > 0;
  const hasLVN = amt.location.lvnZones.length > 0;
  const atKeyLevel = amt.location.isAtKeyLevel;
  const hasAggression = amt.aggression.detected;
  const dirMatch = (scalpResult.isLong && amt.aggression.direction === 'BULL') ||
    (!scalpResult.isLong && amt.aggression.direction === 'BEAR');
  return [
    {
      id: 'prep', step: 1, label: '세션 준비',
      detail: 'POC/VAH/VAL/LVN 마킹, VWAP 확인, 내러티브 설정',
      auto: false, checked: manualChecks['prep'] ?? false,
      verifyItems: [
        {
          label: 'POC 마킹', hint: '전일 POC (Point of Control) 가격을 차트에 수평선으로 표시했는가?',
          autoChecked: hasPOC, autoDetail: hasPOC ? `POC = ${fmtNum(amt.location.poc, 2)}` : undefined
        },
        {
          label: 'VAH/VAL 마킹', hint: 'Value Area High / Low 경계를 차트에 표시했는가?',
          autoChecked: hasVAH && hasVAL, autoDetail: hasVAH ? `VAH ${fmtNum(amt.location.vah, 2)} / VAL ${fmtNum(amt.location.val, 2)}` : undefined
        },
        {
          label: 'LVN 식별', hint: '주요 Low Volume Node (거래량 공백 구간) 위치를 확인했는가?',
          autoChecked: hasLVN, autoDetail: hasLVN ? `LVN: ${amt.location.lvnZones.map(z => fmtNum(z, 1)).join(', ')}` : '감지된 LVN 없음'
        },
        {
          label: 'VWAP 확인', hint: '당일 VWAP 기울기와 현재가 위치 (상/하) 를 파악했는가?',
          autoChecked: hasPOC, autoDetail: hasPOC ? `MA(POC proxy) = ${fmtNum(amt.location.poc, 2)}` : undefined
        },
        { label: '내러티브 설정', hint: '오늘 시장 시나리오 (상승/하락/횡보) 를 미리 정했는가?' },
      ],
    },
    {
      id: 'state', step: 2, label: 'Market State 판단',
      detail: `${amt.marketState} (${amt.marketStateScore}점)`,
      auto: true, checked: amt.marketState !== 'UNKNOWN',
      autoValue: amt.marketState,
    },
    {
      id: 'model', step: 3, label: '모델 선택',
      detail: model === 'TREND_CONTINUATION' ? 'Trend Continuation' : model === 'MEAN_REVERSION' ? 'Mean Reversion' : '선택 불가',
      auto: true, checked: model !== 'NONE',
      autoValue: model,
    },
    {
      id: 'level', step: 4, label: '핵심 레벨 대기',
      detail: `Zone: ${amt.location.currentZone}, POC 거리: ${fmtNum(amt.location.distFromPOC)}p`,
      auto: false, checked: manualChecks['level'] ?? false,
      verifyItems: [
        {
          label: '핵심 레벨 접근', hint: '가격이 POC / VAH / VAL / LVN 등 핵심 레벨에 근접했는가?',
          autoChecked: atKeyLevel, autoDetail: atKeyLevel ? `Zone: ${amt.location.currentZone}, POC거리 ${fmtNum(amt.location.distFromPOC)}p` : `POC거리 ${fmtNum(amt.location.distFromPOC)}p — 아직 핵심 레벨 아님`
        },
        {
          label: '프라이스 액션', hint: '핵심 레벨에서 반전 캔들 (핀바, 엔걸핑 등) 이 출현했는가?',
          autoChecked: hasAggression && amt.aggression.bodyRatio > 0.6, autoDetail: `Body비율 ${(amt.aggression.bodyRatio * 100).toFixed(0)}%, Range확장 ${amt.aggression.rangeExpansion.toFixed(1)}x`
        },
        { label: '오더플로 확인', hint: '레벨에서 델타 전환 또는 흡수 (Absorption) 패턴이 보이는가?' },
        { label: '내러티브 일치', hint: '현재 가격 움직임이 사전 설정한 시나리오와 부합하는가?' },
      ],
    },
    {
      id: 'aggression', step: 5, label: '공격성 확인',
      detail: amt.aggression.reason,
      auto: true, checked: amt.aggression.detected,
      autoValue: `${amt.aggression.score}점`,
    },
    {
      id: 'grade', step: 6, label: '셋업 등급 판정',
      detail: `Grade ${grade.grade} — ${grade.confluenceCount}개 컨플루언스`,
      auto: true, checked: grade.grade !== 'NO_TRADE',
      autoValue: grade.grade,
    },
    {
      id: 'entry', step: 7, label: '진입 실행',
      detail: `${scalpResult.isLong ? 'LONG' : 'SHORT'} @ ${fmtNum(scalpResult.cfg.tick < 1 ? scalpResult.cfg.tick : scalpResult.cfg.tick, 2)}`,
      auto: false, checked: manualChecks['entry'] ?? false,
      verifyItems: [
        {
          label: '방향 재확인', hint: `${scalpResult.isLong ? 'LONG' : 'SHORT'} 방향이 시장 구조와 일치하는가?`,
          autoChecked: dirMatch, autoDetail: `${scalpResult.isLong ? 'LONG' : 'SHORT'} — 시장: ${amt.marketState} / 공격성: ${amt.aggression.direction}`
        },
        { label: '진입가 확인', hint: '지정가 주문이 핵심 레벨 가격에 정확히 설정되었는가?' },
        {
          label: '수량 확인', hint: `계산된 ${grade.adjustedContracts}계약이 리스크 한도 내인가?`,
          autoChecked: grade.adjustedContracts > 0, autoDetail: `Grade ${grade.grade} → ×${grade.riskMultiplier} = ${grade.adjustedContracts}계약`
        },
        {
          label: '손절 동시 설정', hint: `SL ${fmtNum(scalpResult.sl, 2)} 주문이 함께 설정되었는가?`,
          autoChecked: scalpResult.atrStop > 0, autoDetail: `SL ${fmtNum(scalpResult.sl, 2)} (ATR ${fmtNum(scalpResult.atrStop, 2)}p)`
        },
        { label: '뉴스/이벤트', hint: '진입 직후 경제지표 발표, FOMC 등 이벤트가 없는가?' },
      ],
    },
    {
      id: 'stop', step: 8, label: '손절 배치 확인',
      detail: `SL: ${fmtNum(scalpResult.sl, 2)} (ATR×${fmtNum(scalpResult.atrStop / (scalpResult.cfg.tick || 1))}t)`,
      auto: true, checked: scalpResult.atrStop > 0,
      autoValue: `${fmtNum(scalpResult.sl, 2)}`,
    },
    {
      id: 'manage', step: 9, label: '포지션 관리',
      detail: 'CVD 강하면 BE 이동. 흡수 실패 시 스크래치.',
      auto: false, checked: manualChecks['manage'] ?? false,
      verifyItems: [
        { label: 'CVD 방향 확인', hint: 'CVD (Cumulative Volume Delta) 가 포지션 방향으로 유지되고 있는가?' },
        { label: 'BE 이동 판단', hint: '1R 수익 도달 시 손절을 진입가 (Break Even) 로 이동했는가?' },
        { label: '부분 청산', hint: '1.5R 도달 시 50% 물량 청산을 실행했는가?' },
        { label: '흡수 패턴 모니터링', hint: '상대측 흡수 (Absorption) 실패 신호가 감지되면 스크래치 준비가 되었는가?' },
      ],
    },
    {
      id: 'exit', step: 10, label: '청산 실행',
      detail: `TP: ${fmtNum(scalpResult.tp15, 2)} (1.5R) / ${fmtNum(scalpResult.tp2, 2)} (2R)`,
      auto: false, checked: manualChecks['exit'] ?? false,
      verifyItems: [
        {
          label: 'TP 도달 확인', hint: `목표가 ${fmtNum(scalpResult.tp15, 2)} (1.5R) 또는 ${fmtNum(scalpResult.tp2, 2)} (2R) 에 도달했는가?`,
          autoChecked: scalpResult.tp15 > 0, autoDetail: `TP1 ${fmtNum(scalpResult.tp15, 2)} (1.5R) / TP2 ${fmtNum(scalpResult.tp2, 2)} (2R)`
        },
        {
          label: '트레일링 스탑', hint: '수익 구간에서 트레일링 스탑이 활성화되어 있는가?',
          autoChecked: scalpResult.atrStop > 0, autoDetail: `ATR Stop ${fmtNum(scalpResult.atrStop, 2)}p`
        },
        { label: '시간 기반 청산', hint: '진입 후 일정 시간 경과 후에도 목표 미달이면 청산 고려했는가?' },
        { label: '잔여 포지션', hint: '모든 수량이 정상 청산되었고, 잔여 물량이 없는가?' },
      ],
    },
    {
      id: 'review', step: 11, label: '후처리 (기록/복기)',
      detail: '거래 기록, 스크린샷, 복기 완료',
      auto: false, checked: manualChecks['review'] ?? false,
      verifyItems: [
        { label: '거래 기록 작성', hint: '진입가, 청산가, 수량, P&L 을 세션 트래커에 기록했는가?' },
        { label: '차트 스크린샷', hint: '진입/청산 시점의 차트 스크린샷을 저장했는가?' },
        { label: '복기 메모', hint: '잘된 점, 개선할 점, 감정 상태를 기록했는가?' },
        { label: '규칙 준수 점검', hint: '손절 규칙, 수량 규칙, 세션 한도 등 모든 규칙을 준수했는가?' },
      ],
    },
  ];
}

// ── Main Composite Analysis ───────────────────────────────────────────

export function computeFabioAnalysis(
  candles: OHLC[],
  inputs: ScalpInputs,
  scalpResult: ScalpResult,
  session: SessionState,
  manualChecks: Record<string, boolean>,
  intradayBars?: OHLC[],  // 30분봉 드릴다운 (있으면 Triple-A + Aggression에 사용)
): FabioAnalysis {
  const { stdDev, currentPrice } = inputs;
  const z = scalpResult.z;

  // 1. AMT 3-Step Filter
  // Market State + Location → 일봉(구조), Aggression → 30분봉(실행) 우선
  const { state, score, reason, profile } = detectMarketState(candles, z);
  const location = analyzeLocation(profile, currentPrice, stdDev);
  const aggrSrc = (intradayBars && intradayBars.length >= 5) ? intradayBars : candles;
  const aggression = analyzeAggression(aggrSrc);

  const amt: AMTFilter = {
    marketState: state,
    marketStateScore: score,
    marketStateReason: reason,
    location,
    aggression,
    allPassed: state !== 'UNKNOWN' && location.isAtKeyLevel && aggression.detected,
  };

  // 2. Model Selection
  const { model, reason: modelReason } = selectModel(state);

  // 3. Triple-A → 30분봉 우선
  const tripleA = detectTripleA(aggrSrc);

  // 4. Grade
  const grade = computeGrade(amt, tripleA, scalpResult, session);

  // 5. Checklist
  const checklist = generateChecklist(amt, model, grade, scalpResult, manualChecks);

  const intradaySource = aggrSrc === intradayBars ? 'INTRADAY_30M' as const : 'DAILY_FALLBACK' as const;
  return { amt, model, modelReason, tripleA, grade, session, checklist, intradaySource };
}

// ══════════════════════════════════════════════════════════════════════
// ── Historical Walk-Forward Backtest Engine ──────────────────────────
// ══════════════════════════════════════════════════════════════════════

export interface BacktestConfig {
  lookback: number;        // candles for MA/stats window (10~20)
  atrMult: number;         // stop distance multiplier
  tpMultiplier: number;    // take profit as multiple of stop (1.5, 2, 3)
  minGrade: SetupGrade;    // minimum grade to enter (A, B, C)
  maxConsecutiveLoss: number;  // session stop rule
  riskPct: number;         // % of account per trade
  accountBalance: number;
  winRate: number;          // assumed backtest stats
  avgWin: number;
  avgLoss: number;
  slippage: number;
  commission: number;
  maxHoldBars: number;     // max bars to hold position (default: 5)
  tpMultTrend: number;     // TP multiplier for trend trades (default: 2.5)
  tpMultReversion: number; // TP multiplier for mean reversion (default: 1.5)
  slMultTrend: number;     // SL multiplier for trend trades (default: 1.0)
  slMultReversion: number; // SL multiplier for mean reversion (default: 0.75)
}

export interface BacktestTrade {
  barIndex: number;
  entryBar: number;
  exitBar: number;
  direction: 'LONG' | 'SHORT';
  entryPrice: number;
  exitPrice: number;
  stopPrice: number;
  targetPrice: number;
  result: 'WIN' | 'LOSS' | 'TIMEOUT';
  pnlPoints: number;
  pnlPct: number;
  grade: SetupGrade;
  model: SetupModel;
  marketState: MarketState;
  reason: string;
}

export interface BacktestResult {
  trades: BacktestTrade[];
  totalTrades: number;
  wins: number;
  losses: number;
  timeouts: number;
  winRate: number;
  totalPnLPoints: number;
  totalPnLPct: number;
  avgWinPoints: number;
  avgLossPoints: number;
  profitFactor: number;
  maxDrawdownPct: number;
  maxConsecutiveLosses: number;
  maxConsecutiveWins: number;
  sharpeApprox: number;
  equityCurve: number[];
  gradeDistribution: Record<string, number>;
  modelDistribution: Record<string, number>;
  gradeDirectionStats: Record<string, {
    LONG: { trades: number; wins: number; losses: number; pnlPoints: number };
    SHORT: { trades: number; wins: number; losses: number; pnlPoints: number };
  }>;
  intradayStats?: {
    total: number;
    intradayUsed: number;
    dailyFallback: number;
  };
}

export const DEFAULT_BACKTEST_CONFIG: BacktestConfig = {
  lookback: 14,
  atrMult: 1.0,
  tpMultiplier: 2.0,
  minGrade: 'C',
  maxConsecutiveLoss: 3,
  riskPct: 0.5,
  accountBalance: 10000,
  winRate: 58,
  avgWin: 6,
  avgLoss: 4,
  slippage: 0.5,
  commission: 2.25,
  maxHoldBars: 5,
  tpMultTrend: 2.5,
  tpMultReversion: 1.5,
  slMultTrend: 1.0,
  slMultReversion: 0.75,
};

/**
 * Walk-forward backtest: slides a window through candles,
 * runs Fabio analysis at each bar, simulates trades based on signals.
 */
export function runBacktest(
  allCandles: OHLC[],
  config: BacktestConfig,
  _asset: string,
  intradayMap?: IntradayBarMap,  // 30분봉 드릴다운 맵
  dailyDates?: string[],         // 일봉별 날짜 (allCandles와 병렬)
): BacktestResult {
  const { lookback, atrMult, minGrade, maxConsecutiveLoss } = config;
  const trades: BacktestTrade[] = [];
  const minBars = Math.max(lookback + 2, 7);
  let intradayUsed = 0;
  let dailyFallback = 0;


  if (allCandles.length < minBars) {
    return emptyResult();
  }

  // Grade hierarchy for filtering
  const gradeRank: Record<string, number> = { 'A': 3, 'B': 2, 'C': 1, 'NO_TRADE': 0 };
  const minGradeRank = gradeRank[minGrade] ?? 1;

  let consecutiveLosses = 0;
  let inPosition = false;
  let positionExitBar = 0;

  // Slide window through data
  for (let i = minBars; i < allCandles.length; i++) {
    // Skip if already in a position
    if (inPosition && i <= positionExitBar) continue;
    inPosition = false;

    // Session stop rule
    if (consecutiveLosses >= maxConsecutiveLoss) {
      consecutiveLosses = 0; // Reset for next "session"
    }

    // Build window for analysis
    const window = allCandles.slice(Math.max(0, i - lookback), i + 1);
    // Extended window for momentum indicators (MACD needs 27+, RSI needs 15+)
    const extWindow = allCandles.slice(Math.max(0, i - Math.max(lookback, 34)), i + 1);
    const closes = window.map(c => c.c);
    const maSlice = closes.slice(-Math.min(config.lookback, closes.length));
    const ma = maSlice.reduce((a, b) => a + b, 0) / maSlice.length;
    const variance = maSlice.reduce((acc, p) => acc + (p - ma) ** 2, 0) / maSlice.length;
    const stdDev = Math.sqrt(variance);
    const currentPrice = closes[closes.length - 1];

    // ATR from window
    let atrSum = 0, atrCount = 0;
    for (let j = 1; j < window.length; j++) {
      const tr = Math.max(
        window[j].h - window[j].l,
        Math.abs(window[j].h - window[j - 1].c),
        Math.abs(window[j].l - window[j - 1].c),
      );
      atrSum += tr;
      atrCount++;
    }
    const atr = atrCount > 0 ? atrSum / atrCount : 0;

    if (stdDev <= 0 || atr <= 0) continue;

    const z = (currentPrice - ma) / stdDev;

    // Run AMT analysis
    const amtState = detectMarketState(window, z);
    const { state, profile } = amtState;
    if (state === 'UNKNOWN') continue;

    const location = analyzeLocation(profile, currentPrice, stdDev);

    // 30분봉 드릴다운: 해당 날짜의 장중 봉이 있으면 사용
    const dateStr = dailyDates?.[i];
    const dd = drilldownIntradayAnalysis(window, intradayMap, dateStr);
    const aggression = dd.aggression;
    const tripleA = dd.tripleA;
    if (dd.source === 'INTRADAY_30M') intradayUsed++;
    else dailyFallback++;

    // Momentum indicators (use extended window for sufficient lookback)
    const rsi = computeRSIProxy(extWindow);
    const macdData = computeMACDProxy(extWindow);

    // Determine direction with model-specific logic (Cycle 6)
    const { model } = selectModel(state);
    let isLong: boolean;

    if (model === 'TREND_CONTINUATION') {
      // Trend: follow the imbalance direction, require MACD agreement
      isLong = state === 'IMBALANCE_BULL';
      if (macdData && ((isLong && macdData.histogram < 0) || (!isLong && macdData.histogram > 0))) continue;
    } else if (model === 'MEAN_REVERSION') {
      // Mean reversion: go against extreme Z, require RSI confirmation
      isLong = z < -1.0;
      if (rsi != null && ((isLong && rsi > 50) || (!isLong && rsi < 50))) continue;
    } else {
      continue;  // NONE model → skip
    }

    // Grade calculation with 6 confluence items (all earned, no bonus)
    let confluenceCount = 0;
    // 1. Structure: Z-score >= 1.5 (raised from 1.0)
    if (Math.abs(z) >= 1.5) confluenceCount++;
    // 2. Location: at key level
    if (location.isAtKeyLevel) confluenceCount++;
    // 3. Triple-A pattern
    if (tripleA.absorption.detected || tripleA.fullAlignment) confluenceCount++;
    // 4. Aggression detected
    if (aggression.detected) confluenceCount++;
    // 5. RSI momentum confirmation
    if (rsi != null && ((isLong && rsi < 45) || (!isLong && rsi > 55))) confluenceCount++;
    // 6. MACD momentum confirmation
    if (macdData != null && ((isLong && macdData.histogram > 0) || (!isLong && macdData.histogram < 0))) confluenceCount++;

    let grade: SetupGrade;
    if (confluenceCount >= 5) grade = 'A';
    else if (confluenceCount >= 4) grade = 'B';
    else if (confluenceCount >= 3) grade = 'C';
    else grade = 'NO_TRADE';

    // Filter by minimum grade
    if ((gradeRank[grade] ?? 0) < minGradeRank) continue;
    if (grade === 'NO_TRADE') continue;

    // Volume filter: reject low-volume signals, bonus for high volume
    const volumes = window.map(c => c.v || 0);
    const avgVolume = volumes.reduce((a, b) => a + b, 0) / volumes.length;
    const currentVolume = allCandles[i].v || 0;
    const volumeRatio = avgVolume > 0 ? currentVolume / avgVolume : 1;
    if (avgVolume > 0 && volumeRatio < 0.8) continue;  // skip low-volume bars

    // Calculate adaptive stop and target based on model + grade
    const isTrend = model === 'TREND_CONTINUATION';
    const slMult = isTrend ? (config.slMultTrend ?? 1.0) : (config.slMultReversion ?? 0.75);
    const tpMult = isTrend ? (config.tpMultTrend ?? 2.5) : (config.tpMultReversion ?? 1.5);
    // Grade adjustment: A gets wider TP, C gets tighter TP + tighter SL
    const gradeTPScale = grade === 'A' ? 1.2 : grade === 'C' ? 0.8 : 1.0;
    const gradeSLScale = grade === 'C' ? 0.9 : 1.0;

    const atrStop = atr * atrMult * slMult * gradeSLScale;
    const atrTarget = atr * atrMult * slMult * tpMult * gradeTPScale;
    const stopPrice = isLong ? currentPrice - atrStop : currentPrice + atrStop;
    const targetPrice = isLong
      ? currentPrice + atrTarget
      : currentPrice - atrTarget;

    // Simulate forward: check next bars for SL or TP hit
    let exitBar = i;
    let exitPrice = currentPrice;
    let result: BacktestTrade['result'] = 'TIMEOUT';
    let reason = '';
    const maxHold = Math.min(config.maxHoldBars, allCandles.length - i - 1);
    let activeStop = stopPrice;  // can move to BE

    for (let j = 1; j <= maxHold; j++) {
      const bar = allCandles[i + j];
      if (!bar) break;
      exitBar = i + j;

      // Break-even stop: if price moved 0.5R in our favor, move stop to entry
      const mfe = isLong ? bar.h - currentPrice : currentPrice - bar.l;
      if (mfe >= atrStop * 0.5 && activeStop !== currentPrice) {
        activeStop = currentPrice;  // move to break-even
      }

      if (isLong) {
        // Check stop first (conservative)
        if (bar.l <= activeStop) {
          exitPrice = activeStop;
          result = activeStop === currentPrice ? 'TIMEOUT' : 'LOSS';
          reason = activeStop === currentPrice ? `BE stop @ bar+${j}` : `SL hit @ bar+${j}`;
          break;
        }
        // Check target
        if (bar.h >= targetPrice) {
          exitPrice = targetPrice;
          result = 'WIN';
          reason = `TP hit @ bar+${j}`;
          break;
        }
      } else {
        // SHORT
        if (bar.h >= activeStop) {
          exitPrice = activeStop;
          result = activeStop === currentPrice ? 'TIMEOUT' : 'LOSS';
          reason = activeStop === currentPrice ? `BE stop @ bar+${j}` : `SL hit @ bar+${j}`;
          break;
        }
        if (bar.l <= targetPrice) {
          exitPrice = targetPrice;
          result = 'WIN';
          reason = `TP hit @ bar+${j}`;
          break;
        }
      }
    }

    // Timeout: exit at last bar's close with slippage penalty
    if (result === 'TIMEOUT') {
      const timeoutPrice = allCandles[exitBar]?.c ?? currentPrice;
      exitPrice = isLong ? timeoutPrice - config.slippage : timeoutPrice + config.slippage;
      reason = `Timeout ${maxHold}bars`;
    }

    // Apply friction: slippage (entry + exit) + commission
    const frictionPoints = config.slippage * 2 + config.commission;
    const rawPnlPoints = isLong ? exitPrice - currentPrice : currentPrice - exitPrice;
    const pnlPoints = rawPnlPoints - frictionPoints;
    const pnlPct = currentPrice > 0 ? (pnlPoints / currentPrice) * 100 : 0;

    trades.push({
      barIndex: i,
      entryBar: i,
      exitBar,
      direction: isLong ? 'LONG' : 'SHORT',
      entryPrice: currentPrice,
      exitPrice,
      stopPrice,
      targetPrice,
      result,
      pnlPoints,
      pnlPct,
      grade,
      model,
      marketState: state,
      reason,
    });

    // Update consecutive loss tracking
    if (result === 'LOSS') {
      consecutiveLosses++;
    } else {
      consecutiveLosses = 0;
    }

    // Mark position occupied until exit
    inPosition = true;
    positionExitBar = exitBar;
  }

  const result = computeBacktestStats(trades);
  if (intradayMap) {
    result.intradayStats = {
      total: intradayUsed + dailyFallback,
      intradayUsed,
      dailyFallback,
    };
  }
  return result;
}

export function computeBacktestStats(trades: BacktestTrade[]): BacktestResult {
  if (trades.length === 0) return emptyResult();

  // Exit-type counts (how the trade closed)
  const wins = trades.filter(t => t.result === 'WIN').length;
  const losses = trades.filter(t => t.result === 'LOSS').length;
  const timeouts = trades.filter(t => t.result === 'TIMEOUT').length;

  // P&L-based effective win/loss (통일 기준: pnlPoints > 0 = 수익, <= 0 = 손실)
  const winTrades = trades.filter(t => t.pnlPoints > 0);
  const lossTrades = trades.filter(t => t.pnlPoints <= 0);
  const winRate = trades.length > 0 ? (winTrades.length / trades.length) * 100 : 0;

  const totalPnLPoints = trades.reduce((s, t) => s + t.pnlPoints, 0);
  const totalPnLPct = trades.reduce((s, t) => s + t.pnlPct, 0);

  const avgWinPoints = winTrades.length > 0 ? winTrades.reduce((s, t) => s + t.pnlPoints, 0) / winTrades.length : 0;
  const avgLossPoints = lossTrades.length > 0 ? Math.abs(lossTrades.reduce((s, t) => s + t.pnlPoints, 0) / lossTrades.length) : 0;
  const grossProfit = winTrades.reduce((s, t) => s + t.pnlPoints, 0);
  const grossLoss = Math.abs(lossTrades.reduce((s, t) => s + t.pnlPoints, 0));
  const profitFactor = grossLoss > 0 ? grossProfit / grossLoss : grossProfit > 0 ? Infinity : 0;

  // Equity curve & drawdown
  const equityCurve: number[] = [0];
  let peak = 0, maxDD = 0;
  let cumPnL = 0;
  for (const t of trades) {
    cumPnL += t.pnlPct;
    equityCurve.push(cumPnL);
    if (cumPnL > peak) peak = cumPnL;
    const dd = peak - cumPnL;
    if (dd > maxDD) maxDD = dd;
  }

  // Consecutive streaks (P&L 기준 — 수익 TIMEOUT도 연승에 포함)
  let maxConsWins = 0, maxConsLosses = 0, cw = 0, cl = 0;
  for (const t of trades) {
    if (t.pnlPoints > 0) { cw++; cl = 0; maxConsWins = Math.max(maxConsWins, cw); }
    else { cl++; cw = 0; maxConsLosses = Math.max(maxConsLosses, cl); }
  }

  // Sharpe approximation
  const pnlArr = trades.map(t => t.pnlPct);
  const avgPnl = pnlArr.reduce((a, b) => a + b, 0) / pnlArr.length;
  const pnlStd = Math.sqrt(pnlArr.reduce((acc, p) => acc + (p - avgPnl) ** 2, 0) / pnlArr.length);
  const sharpeApprox = pnlStd > 0 ? (avgPnl / pnlStd) * Math.sqrt(252) : 0;

  // Distributions
  const gradeDistribution: Record<string, number> = {};
  const modelDistribution: Record<string, number> = {};
  const gradeDirectionStats: Record<string, {
    LONG: { trades: number; wins: number; losses: number; pnlPoints: number };
    SHORT: { trades: number; wins: number; losses: number; pnlPoints: number };
  }> = {};

  for (const t of trades) {
    gradeDistribution[t.grade] = (gradeDistribution[t.grade] || 0) + 1;
    modelDistribution[t.model] = (modelDistribution[t.model] || 0) + 1;

    if (!gradeDirectionStats[t.grade]) {
      gradeDirectionStats[t.grade] = {
        LONG: { trades: 0, wins: 0, losses: 0, pnlPoints: 0 },
        SHORT: { trades: 0, wins: 0, losses: 0, pnlPoints: 0 }
      };
    }
    const stats = gradeDirectionStats[t.grade][t.direction];
    stats.trades++;
    stats.pnlPoints += t.pnlPoints;
    if (t.pnlPoints > 0) stats.wins++;
    else stats.losses++;
  }

  return {
    trades, totalTrades: trades.length,
    wins, losses, timeouts, winRate,
    totalPnLPoints, totalPnLPct,
    avgWinPoints, avgLossPoints, profitFactor,
    maxDrawdownPct: maxDD, maxConsecutiveLosses: maxConsLosses, maxConsecutiveWins: maxConsWins,
    sharpeApprox, equityCurve,
    gradeDistribution, modelDistribution,
    gradeDirectionStats,
  };
}

function emptyResult(): BacktestResult {
  return {
    trades: [], totalTrades: 0,
    wins: 0, losses: 0, timeouts: 0, winRate: 0,
    totalPnLPoints: 0, totalPnLPct: 0,
    avgWinPoints: 0, avgLossPoints: 0, profitFactor: 0,
    maxDrawdownPct: 0, maxConsecutiveLosses: 0, maxConsecutiveWins: 0,
    sharpeApprox: 0, equityCurve: [0],
    gradeDistribution: {}, modelDistribution: {},
    gradeDirectionStats: {},
  };
}
