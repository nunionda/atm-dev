/**
 * Futures Scalp Analyzer — Pure calculation engine.
 * Probability-based decision engine for ES/MES scalping.
 *
 * Layer 1: Pure math, parsers, constants (no React dependency)
 * Layer 2: Engine computation
 */

// ── Math Utilities ─────────────────────────────────────────────────

export const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));

export const fmt = (v: number, d = 2): string =>
  isNaN(v) || !isFinite(v) ? "—" : v.toFixed(d);

export const fmtUSD = (v: number): string =>
  isNaN(v) || !isFinite(v)
    ? "—"
    : "$" + Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export const fmtMoney = (v: number, sym = "$"): string =>
  isNaN(v) || !isFinite(v)
    ? "—"
    : sym + Math.abs(v).toLocaleString("en-US", {
      minimumFractionDigits: sym === "₩" ? 0 : 2,
      maximumFractionDigits: sym === "₩" ? 0 : 2,
    });

export const fmtPct = (v: number): string =>
  isNaN(v) || !isFinite(v) ? "—" : (v * 100).toFixed(1) + "%";

/** Normal CDF — Abramowitz & Stegun approximation (error < 1.5e-7) */
export function normCDF(z: number): number {
  if (z < -6) return 0;
  if (z > 6) return 1;
  const a1 = 0.254829592, a2 = -0.284496736, a3 = 1.421413741,
    a4 = -1.453152027, a5 = 1.061405429, p = 0.3275911;
  const s = z < 0 ? -1 : 1, x = Math.abs(z) / Math.SQRT2, t = 1 / (1 + p * x);
  return 0.5 * (1 + s * (1 - ((((a5 * t + a4) * t + a3) * t + a2) * t + a1) * t * Math.exp(-x * x)));
}

/** True Range = max(H-L, |H-prevC|, |L-prevC|) */
function trueRange(high: number, low: number, prevClose: number | null): number {
  if (prevClose === null) return high - low;
  return Math.max(high - low, Math.abs(high - prevClose), Math.abs(low - prevClose));
}

// ── Parsers ────────────────────────────────────────────────────────

export function parseCloses(text: string): number[] {
  if (!text.trim()) return [];
  return text.split(/[,\s;|\t\n]+/).map(s => s.trim()).filter(Boolean).map(Number).filter(n => !isNaN(n) && n > 0);
}

export interface OHLC { o: number; h: number; l: number; c: number; v: number }

export function parseOHLC(text: string): OHLC[] {
  if (!text.trim()) return [];
  const lines = text.split(/\n/).map(l => l.trim()).filter(Boolean);
  const candles: OHLC[] = [];
  for (const line of lines) {
    const tokens = line.split(/[,\s\t;|]+/).map(Number);
    if (tokens.length >= 4 && tokens.every(n => !isNaN(n) && n > 0)) {
      candles.push({
        o: tokens[0],
        h: tokens[1],
        l: tokens[2],
        c: tokens[3],
        v: tokens.length >= 5 && !isNaN(tokens[4]) ? tokens[4] : Math.floor(Math.random() * 500) + 100
      });
    }
  }
  return candles;
}

// ── Volume-based Support/Resistance (14-day daily) ──────────────────

export interface VolumeSRLevel {
  price: number;
  type: 'support' | 'resistance';
  strength: 1 | 2 | 3;
  volumeScore: number;   // normalized 0~1
  touchCount: number;
  source: 'high_vol_high' | 'high_vol_low' | 'poc' | 'vah' | 'val';
}

export interface VolumeSRResult {
  levels: VolumeSRLevel[];
  supports: VolumeSRLevel[];
  resistances: VolumeSRLevel[];
  nearestSupport: number | null;
  nearestResistance: number | null;
  priceInZone: 'SUPPORT' | 'RESISTANCE' | 'NEUTRAL';
  volumeTrend: 'INCREASING' | 'DECREASING' | 'FLAT';
}

export function computeVolumeSR(candles: OHLC[], currentPrice: number, atr: number): VolumeSRResult | null {
  if (candles.length < 5 || atr <= 0) return null;

  const avgVol = candles.reduce((s, c) => s + (c.v || 0), 0) / candles.length;
  if (avgVol <= 0) return null;

  const clusterDist = atr * 0.3;
  const rawLevels: { price: number; volScore: number; source: VolumeSRLevel['source'] }[] = [];

  // High-volume day highs/lows → S/R candidates
  for (const c of candles) {
    const ratio = (c.v || 0) / avgVol;
    if (ratio >= 1.2) {
      const score = Math.min(1, (ratio - 1) / 1.5); // normalize: 1.0→0, 2.5→1
      rawLevels.push({ price: c.h, volScore: score, source: 'high_vol_high' });
      rawLevels.push({ price: c.l, volScore: score, source: 'high_vol_low' });
    }
  }

  // Volume profile POC/VAH/VAL
  const totalVol = candles.reduce((s, c) => s + (c.v || 100), 0);
  const priceMap = new Map<number, number>();
  const tick = atr > 50 ? 1 : atr > 5 ? 0.25 : 0.01;
  for (const c of candles) {
    const v = c.v || 100;
    const bucket = (p: number) => Math.round(p / tick) * tick;
    const cBucket = bucket(c.c), oBucket = bucket(c.o), mBucket = bucket((c.h + c.l) / 2);
    priceMap.set(cBucket, (priceMap.get(cBucket) || 0) + v * 0.5);
    priceMap.set(oBucket, (priceMap.get(oBucket) || 0) + v * 0.3);
    priceMap.set(mBucket, (priceMap.get(mBucket) || 0) + v * 0.2);
  }

  let pocPrice = 0, pocVol = 0;
  for (const [p, vol] of priceMap) {
    if (vol > pocVol) { pocVol = vol; pocPrice = p; }
  }

  // Value Area (70%)
  const sorted = [...priceMap.entries()].sort((a, b) => a[0] - b[0]);
  const targetVol = totalVol * 0.7;
  let pocIdx = sorted.findIndex(([p]) => p === pocPrice);
  if (pocIdx < 0) pocIdx = Math.floor(sorted.length / 2);
  let lo = pocIdx, hi = pocIdx, areaVol = sorted[pocIdx]?.[1] ?? 0;
  while (areaVol < targetVol && (lo > 0 || hi < sorted.length - 1)) {
    const loVol = lo > 0 ? sorted[lo - 1][1] : 0;
    const hiVol = hi < sorted.length - 1 ? sorted[hi + 1][1] : 0;
    if (loVol >= hiVol && lo > 0) { lo--; areaVol += sorted[lo][1]; }
    else if (hi < sorted.length - 1) { hi++; areaVol += sorted[hi][1]; }
    else break;
  }
  const val = sorted[lo]?.[0] ?? currentPrice;
  const vah = sorted[hi]?.[0] ?? currentPrice;

  rawLevels.push({ price: pocPrice, volScore: 0.9, source: 'poc' });
  rawLevels.push({ price: vah, volScore: 0.7, source: 'vah' });
  rawLevels.push({ price: val, volScore: 0.7, source: 'val' });

  // Cluster nearby levels
  rawLevels.sort((a, b) => a.price - b.price);
  const clustered: typeof rawLevels = [];
  for (const lv of rawLevels) {
    const existing = clustered.find(c => Math.abs(c.price - lv.price) < clusterDist);
    if (existing) {
      // Merge: keep higher score, average price
      existing.price = (existing.price + lv.price) / 2;
      existing.volScore = Math.max(existing.volScore, lv.volScore);
    } else {
      clustered.push({ ...lv });
    }
  }

  // Count touches (how many candles touched each level)
  const levels: VolumeSRLevel[] = clustered.map(lv => {
    let touches = 0;
    for (const c of candles) {
      if (c.l <= lv.price + clusterDist && c.h >= lv.price - clusterDist) touches++;
    }
    const strength: 1 | 2 | 3 = lv.volScore >= 0.7 ? 3 : lv.volScore >= 0.4 ? 2 : 1;
    return {
      price: lv.price,
      type: lv.price <= currentPrice ? 'support' as const : 'resistance' as const,
      strength,
      volumeScore: lv.volScore,
      touchCount: touches,
      source: lv.source,
    };
  });

  // Sort by strength desc, then by proximity to current price
  levels.sort((a, b) => b.strength - a.strength || Math.abs(a.price - currentPrice) - Math.abs(b.price - currentPrice));

  const supports = levels.filter(l => l.type === 'support').slice(0, 3);
  const resistances = levels.filter(l => l.type === 'resistance').slice(0, 3);
  const nearestSupport = supports.length > 0 ? Math.max(...supports.map(s => s.price)) : null;
  const nearestResistance = resistances.length > 0 ? Math.min(...resistances.map(r => r.price)) : null;

  // Price zone classification
  const proxDist = atr * 0.5;
  const nearSup = nearestSupport !== null && Math.abs(currentPrice - nearestSupport) < proxDist;
  const nearRes = nearestResistance !== null && Math.abs(currentPrice - nearestResistance) < proxDist;
  const priceInZone = nearSup ? 'SUPPORT' as const : nearRes ? 'RESISTANCE' as const : 'NEUTRAL' as const;

  // Volume trend: recent 5 vs prior candles
  const recentN = Math.min(5, Math.floor(candles.length / 2));
  const priorN = candles.length - recentN;
  const recentAvg = candles.slice(-recentN).reduce((s, c) => s + (c.v || 0), 0) / recentN;
  const priorAvg = priorN > 0 ? candles.slice(0, priorN).reduce((s, c) => s + (c.v || 0), 0) / priorN : recentAvg;
  const trendRatio = priorAvg > 0 ? recentAvg / priorAvg : 1;
  const volumeTrend = trendRatio > 1.15 ? 'INCREASING' as const : trendRatio < 0.85 ? 'DECREASING' as const : 'FLAT' as const;

  return { levels, supports, resistances, nearestSupport, nearestResistance, priceInZone, volumeTrend };
}

// ── OBV (On-Balance Volume) ──────────────────────────────────────────

export interface OBVResult {
  obv: number[];              // cumulative OBV series
  obvMA5: number;             // short-term OBV MA
  obvMA20: number;            // long-term OBV MA
  obvSlope: number;           // normalized slope: (MA5 - MA20) / MA20
  momentum: 'RISING' | 'FALLING' | 'FLAT';
  score: number;              // -100 to +100
}

export function computeOBV(candles: OHLC[]): OBVResult | null {
  if (candles.length < 6) return null;

  // Build cumulative OBV
  const obv: number[] = [0];
  for (let i = 1; i < candles.length; i++) {
    const diff = candles[i].c - candles[i - 1].c;
    const vol = candles[i].v || 0;
    obv.push(obv[i - 1] + (diff > 0 ? vol : diff < 0 ? -vol : 0));
  }

  // OBV moving averages
  const maSlice = (arr: number[], period: number) => {
    const s = arr.slice(-Math.min(period, arr.length));
    return s.reduce((a, b) => a + b, 0) / s.length;
  };
  const obvMA5 = maSlice(obv, 5);
  const obvMA20 = maSlice(obv, Math.min(20, obv.length));

  // Normalized slope — dual approach:
  // 1) Ratio-based: (MA5 - MA20) / |MA20| (may saturate when OBV absolute is small)
  // 2) Directional: recent OBV direction (last 5 bars) to compensate
  const ratioSlope = Math.abs(obvMA20) > 0 ? (obvMA5 - obvMA20) / Math.abs(obvMA20) : 0;

  // Directional score: count of rising vs falling OBV in last 5 bars
  const recentOBV = obv.slice(-Math.min(6, obv.length));
  let risingCount = 0, fallingCount = 0;
  for (let i = 1; i < recentOBV.length; i++) {
    if (recentOBV[i] > recentOBV[i - 1]) risingCount++;
    else if (recentOBV[i] < recentOBV[i - 1]) fallingCount++;
  }
  const dirScore = (risingCount - fallingCount) / Math.max(1, recentOBV.length - 1); // -1 to +1

  // Blend: 60% ratio + 40% directional (reduces sensitivity to absolute OBV magnitude)
  const obvSlope = ratioSlope * 0.6 + dirScore * 0.4 * 0.15; // scale dirScore to similar range

  // Momentum classification
  const momentum: OBVResult['momentum'] =
    obvSlope > 0.03 ? 'RISING' : obvSlope < -0.03 ? 'FALLING' : 'FLAT';

  // Score: -100 to +100 (clamped)
  const rawScore = obvSlope * 300;
  const score = clamp(rawScore, -100, 100);

  return { obv, obvMA5, obvMA20, obvSlope, momentum, score };
}

// ── Swing Point Detection (shared utility) ──────────────────────────
// Used by both scalpEngine (SMC trend) and mtfEngine (BOS/CHoCH).

export interface SwingPoint {
  index: number;            // 캔들 배열 내 인덱스
  price: number;            // 스윙 포인트 가격
  type: 'HIGH' | 'LOW';
  confirmed: boolean;       // 좌우 N봉 확인 완료
}

/**
 * 스윙 고점 탐지 — 좌측 leftBars + 우측 rightBars 모두보다 높은 고가
 * 마지막 rightBars개는 unconfirmed (우측 확인 불가)
 */
export function findSwingHighs(
  candles: OHLC[],
  leftBars: number = 3,
  rightBars: number = 3,
): SwingPoint[] {
  const swings: SwingPoint[] = [];
  if (candles.length < leftBars + rightBars + 1) return swings;

  for (let i = leftBars; i < candles.length; i++) {
    const high = candles[i].h;
    let isSwing = true;

    for (let j = i - leftBars; j < i; j++) {
      if (candles[j].h >= high) { isSwing = false; break; }
    }
    if (!isSwing) continue;

    const rightEnd = Math.min(i + rightBars, candles.length - 1);
    const confirmed = (rightEnd - i) >= rightBars;
    for (let j = i + 1; j <= rightEnd; j++) {
      if (candles[j].h >= high) { isSwing = false; break; }
    }
    if (!isSwing) continue;

    swings.push({ index: i, price: high, type: 'HIGH', confirmed });
  }

  return swings;
}

/**
 * 스윙 저점 탐지
 */
export function findSwingLows(
  candles: OHLC[],
  leftBars: number = 3,
  rightBars: number = 3,
): SwingPoint[] {
  const swings: SwingPoint[] = [];
  if (candles.length < leftBars + rightBars + 1) return swings;

  for (let i = leftBars; i < candles.length; i++) {
    const low = candles[i].l;
    let isSwing = true;

    for (let j = i - leftBars; j < i; j++) {
      if (candles[j].l <= low) { isSwing = false; break; }
    }
    if (!isSwing) continue;

    const rightEnd = Math.min(i + rightBars, candles.length - 1);
    const confirmed = (rightEnd - i) >= rightBars;
    for (let j = i + 1; j <= rightEnd; j++) {
      if (candles[j].l <= low) { isSwing = false; break; }
    }
    if (!isSwing) continue;

    swings.push({ index: i, price: low, type: 'LOW', confirmed });
  }

  return swings;
}

// ── SMC Structure Trend (uses shared swing detection) ────────────────

export type CompositeTrendBias = 'BULLISH' | 'BEARISH' | 'SIDEWAYS';

export interface CompositeTrendResult {
  bias: CompositeTrendBias;
  score: number;               // -100 to +100
  confidence: number;          // 0~100%
  components: {
    smcTrend: { label: string; score: number; weight: number };
    obvMomentum: { label: string; score: number; weight: number };
    volumeTrend: { label: string; score: number; weight: number };
  };
  reason: string;
}

/**
 * Detect SMC-style structure trend from OHLC candles.
 * Uses shared findSwingHighs/findSwingLows to determine HH/HL (bullish) vs LH/LL (bearish).
 */
function detectSMCTrend(candles: OHLC[], leftBars = 3, rightBars = 2): { trend: string; score: number; label: string } {
  if (candles.length < leftBars + rightBars + 3) {
    return { trend: 'NEUTRAL', score: 0, label: '데이터 부족' };
  }

  const highs = findSwingHighs(candles, leftBars, rightBars);
  const lows = findSwingLows(candles, leftBars, rightBars);

  let score = 0;
  const labels: string[] = [];

  // Compare recent swing highs (last 3)
  const rh = highs.slice(-3);
  for (let i = 1; i < rh.length; i++) {
    if (rh[i].price > rh[i - 1].price) { score++; labels.push('HH'); }
    else if (rh[i].price < rh[i - 1].price) { score--; labels.push('LH'); }
  }

  // Compare recent swing lows (last 3)
  const rl = lows.slice(-3);
  for (let i = 1; i < rl.length; i++) {
    if (rl[i].price > rl[i - 1].price) { score++; labels.push('HL'); }
    else if (rl[i].price < rl[i - 1].price) { score--; labels.push('LL'); }
  }

  const maxScore = Math.max(1, (rh.length - 1) + (rl.length - 1));
  const normalizedScore = clamp((score / maxScore) * 100, -100, 100);
  const trend = score >= 2 ? 'BULLISH' : score <= -2 ? 'BEARISH' : 'NEUTRAL';
  const label = labels.length > 0 ? labels.join('+') : 'N/A';

  return { trend, score: normalizedScore, label };
}

/**
 * Composite Trend Indicator: SMC Structure(40%) + OBV Momentum(35%) + Volume Trend(25%)
 * Returns a unified trend bias with confidence score.
 *
 * @param existingVolumeSR — 이미 계산된 VolumeSRResult (computeScalp에서 전달) → 중복 호출 방지
 */
export function computeCompositeTrend(candles: OHLC[], currentPrice: number, atr: number, existingVolumeSR?: VolumeSRResult | null): CompositeTrendResult {
  // 1. SMC Market Structure (weight: 40%)
  const smc = detectSMCTrend(candles);
  const smcScore = smc.score;

  // 2. OBV Momentum (weight: 35%)
  const obvResult = computeOBV(candles);
  const obvScore = obvResult?.score ?? 0;
  const obvLabel = obvResult?.momentum ?? 'N/A';

  // 3. Volume Trend (weight: 25%) — 이미 계산된 것 재활용, 없으면 새로 계산
  const volumeSR = existingVolumeSR !== undefined ? existingVolumeSR : computeVolumeSR(candles, currentPrice, atr);
  const volTrend = volumeSR?.volumeTrend ?? 'FLAT';
  const volScore = volTrend === 'INCREASING' ? 50 : volTrend === 'DECREASING' ? -50 : 0;

  // Weighted composite
  const compositeScore = clamp(
    smcScore * 0.40 + obvScore * 0.35 + volScore * 0.25,
    -100, 100,
  );

  const bias: CompositeTrendBias =
    compositeScore > 25 ? 'BULLISH' :
    compositeScore < -25 ? 'BEARISH' :
    'SIDEWAYS';

  const confidence = Math.min(100, Math.round(Math.abs(compositeScore)));

  const reason = [
    `SMC: ${smc.label} (${smcScore > 0 ? '+' : ''}${smcScore.toFixed(0)})`,
    `OBV: ${obvLabel} (${obvScore > 0 ? '+' : ''}${obvScore.toFixed(0)})`,
    `Vol: ${volTrend} (${volScore > 0 ? '+' : ''}${volScore})`,
  ].join(' | ');

  return {
    bias,
    score: compositeScore,
    confidence,
    components: {
      smcTrend: { label: smc.label, score: smcScore, weight: 40 },
      obvMomentum: { label: obvLabel, score: obvScore, weight: 35 },
      volumeTrend: { label: volTrend, score: volScore, weight: 25 },
    },
    reason,
  };
}

// ── Statistics ──────────────────────────────────────────────────────

export interface AutoStats {
  ma: number;
  stdDev: number;
  atr: number;
  currentPrice: number;
  count: number;
  maPeriod: number;
  atrMethod: "CLOSE-PROXY" | "TRUE-RANGE";
}

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
  return { ma: +ma.toFixed(2), stdDev: +stdDev.toFixed(2), atr: +atr.toFixed(2), currentPrice: closes[n - 1], count: n, maPeriod: maSlice.length, atrMethod: "CLOSE-PROXY" };
}

export function statsFromOHLC(candles: OHLC[], maPeriod = 20): AutoStats | null {
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
  return { ma: +ma.toFixed(2), stdDev: +stdDev.toFixed(2), atr: +atr.toFixed(2), currentPrice: closes[n - 1], count: n, maPeriod: maSlice.length, atrMethod: "TRUE-RANGE" };
}

// ── Constants ──────────────────────────────────────────────────────

export interface AssetConfig {
  label: string;
  tick: number;
  tickVal: number;
  ptVal: number;
  sym: string;
  /** 거래소 */
  exchange: string;
  /** 승수 (multiplier) */
  multiplier: number;
  /** 개시증거금 (Initial margin) — USD or KRW */
  initialMargin: number;
  /** 유지증거금 (Maintenance margin) — USD or KRW */
  maintMargin: number;
  /** KRX 증거금율 방식일 경우 개시증거금율 (%) — 선물가 × multiplier × rate */
  marginRatePct?: number;
  /** 대략적 1계약 명목가치 (Notional) */
  notional: number;
  /** 편도 수수료 기본값 */
  defaultCommission: number;
  /** 추천 계좌 잔고 (1계약 기준 최소 권장) */
  recommendedBalance: number;
}

export const ASSETS: Record<string, AssetConfig> = {
  ES: {
    label: "E-mini S&P 500", tick: 0.25, tickVal: 12.50, ptVal: 50, sym: "$",
    exchange: "CME", multiplier: 50,
    initialMargin: 15300, maintMargin: 13900,
    notional: 295000, defaultCommission: 2.25,
    recommendedBalance: 20000,
  },
  MES: {
    label: "Micro E-mini S&P", tick: 0.25, tickVal: 1.25, ptVal: 5, sym: "$",
    exchange: "CME", multiplier: 5,
    initialMargin: 1530, maintMargin: 1390,
    notional: 29500, defaultCommission: 0.62,
    recommendedBalance: 2500,
  },
  NQ: {
    label: "E-mini Nasdaq 100", tick: 0.25, tickVal: 5.00, ptVal: 20, sym: "$",
    exchange: "CME", multiplier: 20,
    initialMargin: 21200, maintMargin: 19300,
    notional: 420000, defaultCommission: 2.25,
    recommendedBalance: 28000,
  },
  MNQ: {
    label: "Micro Nasdaq 100", tick: 0.25, tickVal: 0.50, ptVal: 2, sym: "$",
    exchange: "CME", multiplier: 2,
    initialMargin: 2120, maintMargin: 1930,
    notional: 42000, defaultCommission: 0.62,
    recommendedBalance: 3500,
  },
  K200: {
    label: "KOSPI 200 선물", tick: 0.05, tickVal: 12500, ptVal: 250000, sym: "₩",
    exchange: "KRX", multiplier: 250000,
    initialMargin: 14040000, maintMargin: 9360000,
    marginRatePct: 15.6,
    notional: 90000000, defaultCommission: 1500,
    recommendedBalance: 20000000,
  },
  MK200: {
    label: "Mini KOSPI 200", tick: 0.05, tickVal: 2500, ptVal: 50000, sym: "₩",
    exchange: "KRX", multiplier: 50000,
    initialMargin: 2808000, maintMargin: 1872000,
    marginRatePct: 15.6,
    notional: 18000000, defaultCommission: 500,
    recommendedBalance: 4000000,
  },
};

export const TICKER_MAP: Record<string, { futures: string; spot: string; fallback?: string }> = {
  ES: { futures: "ES=F", spot: "^GSPC", fallback: "^GSPC" },
  MES: { futures: "ES=F", spot: "^GSPC", fallback: "^GSPC" },
  NQ: { futures: "NQ=F", spot: "^NDX", fallback: "^NDX" },
  MNQ: { futures: "NQ=F", spot: "^NDX", fallback: "^NDX" },
  K200: { futures: "@KS200F", spot: "@KS200" },
  MK200: { futures: "@KS200F", spot: "@KS200" },
};

export const SAMPLE_CLOSE = "5872.50, 5878.25, 5865.00, 5880.75, 5889.50, 5895.25, 5887.00, 5892.75, 5901.50, 5898.00, 5905.25, 5910.75, 5903.50, 5908.00, 5915.25, 5911.50, 5918.75, 5922.00, 5916.50, 5920.00, 5914.00, 5908.25, 5902.50, 5910.00, 5918.50, 5925.00, 5930.75, 5924.50, 5918.00, 5912.25, 5905.50, 5898.75, 5892.00, 5900.50, 5908.25, 5915.75, 5922.50, 5928.00, 5935.25, 5929.50, 5923.75, 5917.00, 5910.25, 5903.50, 5896.75, 5904.50, 5912.25, 5920.00, 5927.50, 5935.00";

export const SAMPLE_OHLC = `5870.00, 5878.50, 5868.25, 5872.50, 1250
5873.00, 5882.75, 5871.50, 5878.25, 2100
5879.00, 5880.00, 5862.50, 5865.00, 3500
5866.00, 5884.25, 5864.75, 5880.75, 4200
5881.00, 5893.00, 5879.25, 5889.50, 3100
5890.00, 5899.75, 5888.00, 5895.25, 2800
5895.50, 5896.00, 5884.50, 5887.00, 1500
5887.25, 5896.50, 5886.00, 5892.75, 1900
5893.00, 5905.25, 5891.75, 5901.50, 4800
5901.75, 5903.50, 5895.00, 5898.00, 1200
5898.25, 5909.00, 5897.50, 5905.25, 3300
5905.50, 5914.50, 5904.25, 5910.75, 2600
5911.00, 5912.00, 5901.00, 5903.50, 2900
5903.75, 5911.25, 5902.50, 5908.00, 1800
5908.25, 5918.75, 5907.00, 5915.25, 3700
5915.50, 5917.00, 5909.25, 5911.50, 1400
5912.00, 5922.50, 5911.25, 5918.75, 4100
5919.00, 5925.75, 5918.00, 5922.00, 2200
5922.25, 5923.00, 5914.50, 5916.50, 1900
5917.00, 5923.50, 5916.25, 5920.00, 2500
5920.25, 5921.00, 5911.75, 5914.00, 1800
5914.25, 5915.50, 5905.00, 5908.25, 3200
5908.50, 5910.00, 5898.75, 5902.50, 4500
5903.00, 5914.00, 5901.50, 5910.00, 2800
5910.25, 5922.75, 5909.00, 5918.50, 5100
5919.00, 5929.50, 5917.75, 5925.00, 3900
5925.25, 5935.00, 5924.00, 5930.75, 4600
5931.00, 5932.50, 5922.25, 5924.50, 2100
5924.75, 5926.00, 5915.50, 5918.00, 3400
5918.25, 5919.75, 5909.00, 5912.25, 4200
5912.50, 5913.00, 5902.25, 5905.50, 3800
5905.75, 5907.50, 5895.00, 5898.75, 5500
5899.00, 5901.25, 5888.50, 5892.00, 6200
5892.25, 5905.75, 5890.00, 5900.50, 3100
5901.00, 5912.50, 5899.75, 5908.25, 2900
5908.50, 5920.00, 5907.25, 5915.75, 3600
5916.00, 5926.75, 5914.50, 5922.50, 4100
5922.75, 5932.00, 5921.50, 5928.00, 3300
5928.25, 5940.50, 5927.00, 5935.25, 5800
5935.50, 5937.00, 5926.75, 5929.50, 2400
5929.75, 5931.25, 5921.00, 5923.75, 3100
5924.00, 5925.50, 5914.25, 5917.00, 4500
5917.25, 5918.00, 5907.50, 5910.25, 3700
5910.50, 5912.25, 5900.00, 5903.50, 5200
5903.75, 5905.00, 5893.25, 5896.75, 6800
5897.00, 5909.50, 5895.75, 5904.50, 3200
5905.00, 5916.75, 5903.50, 5912.25, 2800
5912.50, 5924.00, 5911.25, 5920.00, 4300
5920.25, 5931.50, 5919.00, 5927.50, 3900
5928.00, 5939.25, 5926.50, 5935.00, 5100`;

// ── Design Tokens ──────────────────────────────────────────────────

export const F = {
  mono: "'IBM Plex Mono','Fira Code',monospace",
  sans: "'DM Sans','Manrope',-apple-system,sans-serif",
};

export const K = {
  bg0: "#060910", bg1: "#0b0f18", bg2: "#101520", bg3: "#161c2a",
  brd: "#1c2336", brdL: "#273048",
  txt: "#dfe3ed", dim: "#6b7594", mut: "#3e4868",
  acc: "#3b82f6", grn: "#00e676", red: "#ff1744",
  cyn: "#4fc3f7", org: "#ffab40", ylw: "#fdd835",
};

// ── Engine ──────────────────────────────────────────────────────────

export interface ScalpInputs {
  asset: string;
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
  dailyCandles?: OHLC[];  // 14-day daily candles for volume S/R
}

export interface CheckItem {
  label: string;
  pass: boolean;
  val: string;
}

export interface ScalpResult {
  cfg: AssetConfig;
  z: number;
  pVal: number;
  zSignal: string;
  zColor: string;
  p: number;
  q: number;
  b: number;
  grossEV: number;
  friction: number;
  netEV: number;
  netEVusd: number;
  kelly: number;
  halfKelly: number;
  conviction: string;
  atrStop: number;
  isLong: boolean;
  sl: number;
  riskPerContract: number;
  riskBudget: number;
  maxContracts: number;
  recContracts: number;
  tp15: number;
  tp2: number;
  tp3: number;
  basis: number;
  basisPct: number;
  basisState: string;
  pnlTP1: number;
  pnlSL: number;
  // Z-Zone adaptive stop
  zZone: 'NORMAL' | 'MILD' | 'STRONG';
  zZoneLabel: string;
  zStopMult: number;       // zone-based stop multiplier
  adaptiveStop: number;    // ATR × atrMult × zStopMult
  adaptiveSL: number;      // adaptive stop-loss price
  maTarget: number;        // MA price (mean reversion target)
  maDistance: number;       // |currentPrice - MA| in points
  maDistR: number;         // maDistance expressed as R-multiple of adaptiveStop
  revertProb: number;      // probability of reversion (1 - pVal/2 for one-sided)
  checks: CheckItem[];
  passN: number;
  verdict: string;
  volumeSR: VolumeSRResult | null;
  compositeTrend: CompositeTrendResult | null;
  trendConflict: boolean;           // true when Z-direction opposes composite trend
}

export function computeScalp(inputs: ScalpInputs): ScalpResult {
  const { asset, currentPrice, ma, stdDev, atr, atrMult, winRate, avgWin, avgLoss, slippage, commission, accountBalance, riskPct, spotPrice, futuresPrice } = inputs;
  const cfg = ASSETS[asset];

  // Z-Score
  const z = stdDev > 0 ? (currentPrice - ma) / stdDev : 0;
  const pVal = normCDF(-Math.abs(z)) * 2;
  const zSignal = z < -2 ? "STRONG LONG" : z > 2 ? "STRONG SHORT" : z < -1.5 ? "LEAN LONG" : z > 1.5 ? "LEAN SHORT" : "NEUTRAL";
  const zColor = z < -2 ? K.grn : z > 2 ? K.red : z < -1.5 ? "#69f0ae" : z > 1.5 ? "#ff8a80" : "#78909c";

  // EV (net of friction)
  const p = winRate / 100, q = 1 - p;
  const grossEV = p * avgWin - q * avgLoss;
  const friction = slippage + (commission / cfg.tickVal);
  const netEV = grossEV - friction;
  const netEVusd = netEV * cfg.tickVal;

  // Kelly
  const b = avgLoss > 0 ? avgWin / avgLoss : 0;
  const kelly = b > 0 ? (b * p - q) / b : 0;
  const halfKelly = kelly / 2;
  const conviction = kelly <= 0 ? "NO EDGE" : halfKelly < 0.02 ? "VERY LOW" : halfKelly < 0.05 ? "LOW" : halfKelly < 0.1 ? "MODERATE" : halfKelly < 0.2 ? "HIGH" : "VERY HIGH";

  // Z-Zone classification & adaptive stop
  const absZ = Math.abs(z);
  const zZone: ScalpResult['zZone'] = absZ >= 2 ? 'STRONG' : absZ >= 1 ? 'MILD' : 'NORMAL';
  // Stop rationale:
  //   STRONG (|Z|≥2, 95%+ 이탈): 강한 회귀 신호, 변동성 감안 넉넉한 스탑 → 1.25×
  //   MILD   (|Z|1~2, 68~95%):   보통 신호, 표준 스탑 → 1.0×
  //   NORMAL (|Z|<1, 68% 이내):   약한 신호, 리스크 제한 타이트 스탑 → 0.75×
  const zStopMult = zZone === 'STRONG' ? 1.25 : zZone === 'MILD' ? 1.0 : 0.75;
  const zZoneLabel = zZone === 'STRONG'
    ? `강한 이탈 (${(absZ).toFixed(1)}σ, ${((1 - pVal) * 100).toFixed(0)}% 신뢰)`
    : zZone === 'MILD'
      ? `약간 이탈 (${(absZ).toFixed(1)}σ)`
      : `정상 범위 (${(absZ).toFixed(1)}σ)`;

  const atrStop = atr * atrMult;
  const adaptiveStop = atrStop * zStopMult;
  const isLong = z <= 0;
  const sl = isLong ? currentPrice - adaptiveStop : currentPrice + adaptiveStop;
  const adaptiveSL = sl;
  const riskPerContract = adaptiveStop * cfg.ptVal;

  // Mean reversion reference
  const maTarget = ma;
  const maDistance = Math.abs(currentPrice - ma);
  const maDistR = adaptiveStop > 0 ? maDistance / adaptiveStop : 0;
  const revertProb = absZ > 0 ? 1 - normCDF(-absZ) : 0.5; // one-sided reversion probability

  // Position
  const riskBudget = accountBalance * (riskPct / 100);
  const maxContracts = riskPerContract > 0 ? Math.floor(riskBudget / riskPerContract) : 0;
  const recContracts = Math.min(maxContracts, 2);

  // TP levels (based on adaptive stop)
  const tp15 = isLong ? currentPrice + adaptiveStop * 1.5 : currentPrice - adaptiveStop * 1.5;
  const tp2 = isLong ? currentPrice + adaptiveStop * 2 : currentPrice - adaptiveStop * 2;
  const tp3 = isLong ? currentPrice + adaptiveStop * 3 : currentPrice - adaptiveStop * 3;

  // Basis
  const basis = futuresPrice - spotPrice;
  const basisPct = spotPrice > 0 ? (basis / spotPrice) * 100 : 0;
  const basisState = basis > 2 ? "CONTANGO" : basis < -2 ? "BACKWARDATION" : "FAIR VALUE";

  // P&L
  const lots = Math.max(recContracts, 1);
  const pnlTP1 = Math.abs(tp15 - currentPrice) * cfg.ptVal * lots;
  const pnlSL = adaptiveStop * cfg.ptVal * lots;

  // Volume S/R from daily candles (computed early for trend check)
  const volumeSR = inputs.dailyCandles && inputs.dailyCandles.length >= 5
    ? computeVolumeSR(inputs.dailyCandles, currentPrice, atr)
    : null;

  // Composite Trend: SMC + OBV + Volume (computed early for verdict)
  // 이미 계산된 volumeSR을 전달하여 중복 computeVolumeSR() 호출 방지
  const compositeTrend = inputs.dailyCandles && inputs.dailyCandles.length >= 6
    ? computeCompositeTrend(inputs.dailyCandles, currentPrice, atr, volumeSR)
    : null;

  // Trend alignment check: is the Z-Score direction consistent with composite trend?
  const trendAligned = !compositeTrend
    || compositeTrend.bias === 'SIDEWAYS'
    || (isLong && compositeTrend.bias === 'BULLISH')
    || (!isLong && compositeTrend.bias === 'BEARISH');
  const trendConflict = !!(compositeTrend
    && compositeTrend.bias !== 'SIDEWAYS'
    && compositeTrend.confidence >= 30
    && !trendAligned);

  // Confluence-based decision (Cycle 5 + trend awareness)
  const checks: CheckItem[] = [
    { label: "Z-Score ≥ 1.5", pass: Math.abs(z) >= 1.5, val: `Z = ${fmt(z)}` },
    { label: "순 기대값 > 0", pass: netEV > 0, val: `${fmt(netEV)}t` },
    { label: "Kelly 양수", pass: kelly > 0, val: fmtPct(kelly) },
    { label: "손익비 ≥ 1.5", pass: b >= 1.5, val: `${fmt(b, 1)}:1` },
    { label: "회귀확률 ≥ 70%", pass: revertProb >= 0.70, val: `${(revertProb * 100).toFixed(0)}%` },
    { label: "Z-Zone ≥ MILD", pass: zZone !== 'NORMAL', val: zZone },
    { label: "추세 정합", pass: trendAligned, val: compositeTrend ? `${compositeTrend.bias} (${compositeTrend.confidence}%)` : 'N/A' },
  ];
  const confScore = checks.reduce((s, c) => s + (c.pass ? Math.round(100 / checks.length) : 0), 0);
  const passN = checks.filter(c => c.pass).length;
  // Downgrade verdict when strong trend conflict exists
  const rawVerdict = confScore >= 80 ? "GO" : confScore >= 50 ? "CAUTION" : "NO ENTRY";
  const verdict = (rawVerdict === "GO" && trendConflict) ? "CAUTION" : rawVerdict;

  return { cfg, z, pVal, zSignal, zColor, p, q, b, grossEV, friction, netEV, netEVusd, kelly, halfKelly, conviction, atrStop, isLong, sl, riskPerContract, riskBudget, maxContracts, recContracts, tp15, tp2, tp3, basis, basisPct, basisState, pnlTP1, pnlSL, zZone, zZoneLabel, zStopMult, adaptiveStop, adaptiveSL, maTarget, maDistance, maDistR, revertProb, checks, passN, verdict, volumeSR, compositeTrend, trendConflict };
}
