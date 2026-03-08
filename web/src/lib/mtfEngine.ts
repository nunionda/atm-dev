/**
 * Multi-Timeframe BOS/CHoCH Structure Engine
 *
 * HTF (1H) = WHERE + DIRECTION → 어디서, 어느 방향으로 매매할지
 * LTF (5min) = WHEN → 언제 들어갈지 (BOS/CHoCH 신호)
 *
 * BOS (Break of Structure): 추세 방향으로 직전 스윙 고/저점 돌파 → 추세 지속
 * CHoCH (Change of Character): 추세 반대 방향 돌파 → 반전 신호
 *
 * 사용법:
 *   const result = analyzeMTF(htfCandles_1H, ltfCandles_5min, currentPrice);
 *   // result.direction → 'LONG' | 'SHORT' | 'NEUTRAL'
 *   // result.signalType → 'BOS_CONTINUATION' | 'CHOCH_REVERSAL' | 'NO_SIGNAL'
 */

import { type OHLC, type SwingPoint, findSwingHighs, findSwingLows } from './scalpEngine';
import { detectRegimeFromOHLC, type RegimeAnalysis } from './strategyEngine';

// ── Types ──────────────────────────────────────────────────────────────

export type StructureTrend = 'BULLISH' | 'BEARISH' | 'CONSOLIDATION';
export type MTFDirection = 'LONG' | 'SHORT' | 'NEUTRAL';
export type MTFSignalType = 'BOS_CONTINUATION' | 'CHOCH_REVERSAL' | 'NO_SIGNAL';
export type MTFConfidence = 'HIGH' | 'MEDIUM' | 'LOW';

// SwingPoint is imported from scalpEngine.ts (shared utility)
export type { SwingPoint } from './scalpEngine';

export interface StructureBreak {
  type: 'BOS' | 'CHoCH';
  direction: 'BULLISH' | 'BEARISH';
  breakPrice: number;       // 돌파된 스윙 레벨 가격
  breakIndex: number;       // 돌파 발생 캔들 인덱스
  triggerPrice: number;     // 돌파를 일으킨 캔들 종가
  swingBroken: SwingPoint;  // 돌파된 스윙 포인트
  volumeConfirmed: boolean; // 거래량 확인 여부
  bodyStrength: number;     // 캔들 바디/레인지 비율 (0~1)
  confidence: number;       // 0~100
}

export interface HTFContext {
  trend: StructureTrend;
  trendConfidence: number;  // 0~100
  swingHighs: SwingPoint[];
  swingLows: SwingPoint[];
  keyResistance: number | null;
  keySupport: number | null;
  lastBOS: StructureBreak | null;
  lastCHoCH: StructureBreak | null;
  pricePosition: 'ABOVE_STRUCTURE' | 'BELOW_STRUCTURE' | 'IN_RANGE';
  regime: string;
  regimeConfidence: number;
}

export interface LTFSignal {
  signal: StructureBreak | null;
  alignedWithHTF: boolean;
  signalType: MTFSignalType;
  confidence: MTFConfidence;
  reason: string;
}

export interface MTFAnalysis {
  htf: HTFContext;
  ltf: LTFSignal;
  direction: MTFDirection;
  signalType: MTFSignalType;
  confidence: MTFConfidence;
  entryZone: string;
  stopLoss: number | null;
  takeProfit: number | null;
  summary: string;
}

// ── Defaults ───────────────────────────────────────────────────────────

export const MTF_DEFAULTS = {
  htfLeftBars: 3,
  htfRightBars: 3,
  ltfLeftBars: 2,
  ltfRightBars: 2,
  bosLookback: 10,
  chochLookback: 10,
  minBodyRatio: 0.4,         // 최소 바디/레인지 비율
  minVolumeRatio: 1.1,       // 최소 거래량 비율 (vs 평균)
};

// ── Swing Detection ────────────────────────────────────────────────────
// findSwingHighs / findSwingLows are imported from scalpEngine.ts (shared utility)
// Re-export them for consumers that import from mtfEngine
export { findSwingHighs, findSwingLows } from './scalpEngine';

// ── Structure Trend Detection ──────────────────────────────────────────

/**
 * 스윙 시퀀스에서 추세 판별
 * HH + HL = BULLISH, LH + LL = BEARISH, 혼합 = CONSOLIDATION
 */
export function detectStructureTrend(
  swingHighs: SwingPoint[],
  swingLows: SwingPoint[],
): { trend: StructureTrend; confidence: number; reason: string } {
  // 최근 스윙 포인트 충분해야
  if (swingHighs.length < 2 && swingLows.length < 2) {
    return { trend: 'CONSOLIDATION', confidence: 0, reason: '스윙 포인트 부족' };
  }

  let score = 0;
  let maxScore = 0;
  const reasons: string[] = [];

  // 스윙 고점 비교 (최근 3개까지)
  const recentHighs = swingHighs.slice(-3);
  for (let i = 1; i < recentHighs.length; i++) {
    maxScore++;
    if (recentHighs[i].price > recentHighs[i - 1].price) {
      score++;
      reasons.push('HH');  // Higher High
    } else if (recentHighs[i].price < recentHighs[i - 1].price) {
      score--;
      reasons.push('LH');  // Lower High
    }
  }

  // 스윙 저점 비교
  const recentLows = swingLows.slice(-3);
  for (let i = 1; i < recentLows.length; i++) {
    maxScore++;
    if (recentLows[i].price > recentLows[i - 1].price) {
      score++;
      reasons.push('HL');  // Higher Low
    } else if (recentLows[i].price < recentLows[i - 1].price) {
      score--;
      reasons.push('LL');  // Lower Low
    }
  }

  const confidence = maxScore > 0 ? Math.round(Math.abs(score) / maxScore * 100) : 0;
  const trend: StructureTrend =
    score >= 2 ? 'BULLISH' :
    score <= -2 ? 'BEARISH' :
    'CONSOLIDATION';

  return {
    trend,
    confidence,
    reason: reasons.length > 0 ? reasons.join(' + ') : '판별 불가',
  };
}

// ── BOS / CHoCH Detection ──────────────────────────────────────────────

/**
 * 캔들 body 강도 (바디 비율): |close - open| / (high - low)
 */
function bodyRatio(c: OHLC): number {
  const range = c.h - c.l;
  return range > 0 ? Math.abs(c.c - c.o) / range : 0;
}

/**
 * 최근 N봉 평균 거래량
 */
function avgVolume(candles: OHLC[], endIdx: number, lookback: number = 20): number {
  const start = Math.max(0, endIdx - lookback);
  let sum = 0, count = 0;
  for (let i = start; i < endIdx; i++) {
    sum += candles[i].v || 0;
    count++;
  }
  return count > 0 ? sum / count : 0;
}

/**
 * BOS 감지 — 추세 방향으로 구조 돌파
 * BULLISH 추세: 직전 스윙 고점 상향돌파 = Bullish BOS
 * BEARISH 추세: 직전 스윙 저점 하향돌파 = Bearish BOS
 */
export function detectBOS(
  candles: OHLC[],
  swingHighs: SwingPoint[],
  swingLows: SwingPoint[],
  trend: StructureTrend,
  lookbackBars: number = 10,
): StructureBreak | null {
  if (trend === 'CONSOLIDATION') return null;

  if (trend === 'BULLISH') {
    // 마지막 confirmed 스윙 고점 찾기
    const lastSH = [...swingHighs].filter(s => s.confirmed).pop();
    if (!lastSH) return null;

    // 최근 lookbackBars 내에서 돌파 확인
    const startIdx = Math.max(lastSH.index + 1, candles.length - lookbackBars);
    for (let i = startIdx; i < candles.length; i++) {
      if (candles[i].c > lastSH.price) {
        const br = bodyRatio(candles[i]);
        const avgVol = avgVolume(candles, i);
        const volConfirmed = avgVol > 0 ? (candles[i].v || 0) / avgVol >= MTF_DEFAULTS.minVolumeRatio : false;
        const conf = Math.round(
          (br >= MTF_DEFAULTS.minBodyRatio ? 40 : 20) +
          (volConfirmed ? 30 : 10) +
          (candles[i].c > lastSH.price * 1.001 ? 30 : 15) // 의미 있는 돌파
        );
        return {
          type: 'BOS',
          direction: 'BULLISH',
          breakPrice: lastSH.price,
          breakIndex: i,
          triggerPrice: candles[i].c,
          swingBroken: lastSH,
          volumeConfirmed: volConfirmed,
          bodyStrength: +br.toFixed(2),
          confidence: Math.min(100, conf),
        };
      }
    }
  }

  if (trend === 'BEARISH') {
    const lastSL = [...swingLows].filter(s => s.confirmed).pop();
    if (!lastSL) return null;

    const startIdx = Math.max(lastSL.index + 1, candles.length - lookbackBars);
    for (let i = startIdx; i < candles.length; i++) {
      if (candles[i].c < lastSL.price) {
        const br = bodyRatio(candles[i]);
        const avgVol = avgVolume(candles, i);
        const volConfirmed = avgVol > 0 ? (candles[i].v || 0) / avgVol >= MTF_DEFAULTS.minVolumeRatio : false;
        const conf = Math.round(
          (br >= MTF_DEFAULTS.minBodyRatio ? 40 : 20) +
          (volConfirmed ? 30 : 10) +
          (candles[i].c < lastSL.price * 0.999 ? 30 : 15)
        );
        return {
          type: 'BOS',
          direction: 'BEARISH',
          breakPrice: lastSL.price,
          breakIndex: i,
          triggerPrice: candles[i].c,
          swingBroken: lastSL,
          volumeConfirmed: volConfirmed,
          bodyStrength: +br.toFixed(2),
          confidence: Math.min(100, conf),
        };
      }
    }
  }

  return null;
}

/**
 * CHoCH 감지 — 추세 반대 방향 구조 돌파 (반전 신호)
 * BEARISH 추세에서 스윙 고점 상향돌파 = Bullish CHoCH
 * BULLISH 추세에서 스윙 저점 하향돌파 = Bearish CHoCH
 */
export function detectCHoCH(
  candles: OHLC[],
  swingHighs: SwingPoint[],
  swingLows: SwingPoint[],
  trend: StructureTrend,
  lookbackBars: number = 10,
): StructureBreak | null {
  if (trend === 'CONSOLIDATION') return null;

  if (trend === 'BEARISH') {
    // 하락 추세에서 스윙 고점 상향돌파 = Bullish CHoCH (반전)
    const lastSH = [...swingHighs].filter(s => s.confirmed).pop();
    if (!lastSH) return null;

    const startIdx = Math.max(lastSH.index + 1, candles.length - lookbackBars);
    for (let i = startIdx; i < candles.length; i++) {
      if (candles[i].c > lastSH.price) {
        const br = bodyRatio(candles[i]);
        const avgVol = avgVolume(candles, i);
        const volConfirmed = avgVol > 0 ? (candles[i].v || 0) / avgVol >= MTF_DEFAULTS.minVolumeRatio : false;
        const conf = Math.round(
          (br >= MTF_DEFAULTS.minBodyRatio ? 40 : 20) +
          (volConfirmed ? 30 : 10) +
          (candles[i].c > lastSH.price * 1.001 ? 30 : 15)
        );
        return {
          type: 'CHoCH',
          direction: 'BULLISH',
          breakPrice: lastSH.price,
          breakIndex: i,
          triggerPrice: candles[i].c,
          swingBroken: lastSH,
          volumeConfirmed: volConfirmed,
          bodyStrength: +br.toFixed(2),
          confidence: Math.min(100, conf),
        };
      }
    }
  }

  if (trend === 'BULLISH') {
    // 상승 추세에서 스윙 저점 하향돌파 = Bearish CHoCH (반전)
    const lastSL = [...swingLows].filter(s => s.confirmed).pop();
    if (!lastSL) return null;

    const startIdx = Math.max(lastSL.index + 1, candles.length - lookbackBars);
    for (let i = startIdx; i < candles.length; i++) {
      if (candles[i].c < lastSL.price) {
        const br = bodyRatio(candles[i]);
        const avgVol = avgVolume(candles, i);
        const volConfirmed = avgVol > 0 ? (candles[i].v || 0) / avgVol >= MTF_DEFAULTS.minVolumeRatio : false;
        const conf = Math.round(
          (br >= MTF_DEFAULTS.minBodyRatio ? 40 : 20) +
          (volConfirmed ? 30 : 10) +
          (candles[i].c < lastSL.price * 0.999 ? 30 : 15)
        );
        return {
          type: 'CHoCH',
          direction: 'BEARISH',
          breakPrice: lastSL.price,
          breakIndex: i,
          triggerPrice: candles[i].c,
          swingBroken: lastSL,
          volumeConfirmed: volConfirmed,
          bodyStrength: +br.toFixed(2),
          confidence: Math.min(100, conf),
        };
      }
    }
  }

  return null;
}

// ── HTF Context Builder ────────────────────────────────────────────────

/**
 * HTF (1H) 컨텍스트 분석
 * 1시간봉에서: 추세 방향, 핵심 구간, 가격 위치, 레짐 판별
 */
export function buildHTFContext(htfCandles: OHLC[], currentPrice: number): HTFContext {
  const swingHighs = findSwingHighs(htfCandles, MTF_DEFAULTS.htfLeftBars, MTF_DEFAULTS.htfRightBars);
  const swingLows = findSwingLows(htfCandles, MTF_DEFAULTS.htfLeftBars, MTF_DEFAULTS.htfRightBars);

  // 구조적 추세 판별
  const { trend, confidence: trendConfidence } = detectStructureTrend(swingHighs, swingLows);

  // BOS / CHoCH 감지
  const lastBOS = detectBOS(htfCandles, swingHighs, swingLows, trend, MTF_DEFAULTS.bosLookback);
  const lastCHoCH = detectCHoCH(htfCandles, swingHighs, swingLows, trend, MTF_DEFAULTS.chochLookback);

  // 핵심 저항/지지 (최근 confirmed 스윙 포인트)
  const confirmedHighs = swingHighs.filter(s => s.confirmed);
  const confirmedLows = swingLows.filter(s => s.confirmed);
  const keyResistance = confirmedHighs.length > 0 ? confirmedHighs[confirmedHighs.length - 1].price : null;
  const keySupport = confirmedLows.length > 0 ? confirmedLows[confirmedLows.length - 1].price : null;

  // 가격 위치
  let pricePosition: HTFContext['pricePosition'] = 'IN_RANGE';
  if (keyResistance !== null && currentPrice > keyResistance) {
    pricePosition = 'ABOVE_STRUCTURE';
  } else if (keySupport !== null && currentPrice < keySupport) {
    pricePosition = 'BELOW_STRUCTURE';
  }

  // 레짐 (strategyEngine.ts 재활용)
  let regime = 'MIXED';
  let regimeConfidence = 0;
  if (htfCandles.length >= 20) {
    try {
      const regimeResult: RegimeAnalysis = detectRegimeFromOHLC(htfCandles, htfCandles.length - 1, 20);
      regime = regimeResult.regime;
      regimeConfidence = regimeResult.confidence;
    } catch {
      // strategyEngine 호환 문제 시 기본값 유지
    }
  }

  return {
    trend,
    trendConfidence,
    swingHighs,
    swingLows,
    keyResistance,
    keySupport,
    lastBOS,
    lastCHoCH,
    pricePosition,
    regime,
    regimeConfidence,
  };
}

// ── LTF Signal Scanner ─────────────────────────────────────────────────

/**
 * LTF (5min) 시그널 스캔
 * 5분봉에서 BOS/CHoCH 감지 후 HTF 맥락과 정합성 확인
 */
export function scanLTFSignal(ltfCandles: OHLC[], htfContext: HTFContext): LTFSignal {
  const noSignal: LTFSignal = {
    signal: null,
    alignedWithHTF: false,
    signalType: 'NO_SIGNAL',
    confidence: 'LOW',
    reason: 'LTF 시그널 없음',
  };

  if (ltfCandles.length < 10) return { ...noSignal, reason: 'LTF 데이터 부족 (10봉 미만)' };

  // LTF 스윙 탐지 (5분봉은 빠른 감지: leftBars=2, rightBars=2)
  const ltfHighs = findSwingHighs(ltfCandles, MTF_DEFAULTS.ltfLeftBars, MTF_DEFAULTS.ltfRightBars);
  const ltfLows = findSwingLows(ltfCandles, MTF_DEFAULTS.ltfLeftBars, MTF_DEFAULTS.ltfRightBars);

  // LTF 구조 추세
  const { trend: ltfTrend } = detectStructureTrend(ltfHighs, ltfLows);

  // LTF BOS 감지
  const ltfBOS = detectBOS(ltfCandles, ltfHighs, ltfLows, ltfTrend, MTF_DEFAULTS.bosLookback);

  // LTF CHoCH 감지
  const ltfCHoCH = detectCHoCH(ltfCandles, ltfHighs, ltfLows, ltfTrend, MTF_DEFAULTS.chochLookback);

  // HTF 정합성 확인 — BOS 우선 (더 강한 시그널)
  if (ltfBOS) {
    const aligned =
      (ltfBOS.direction === 'BULLISH' && htfContext.trend === 'BULLISH') ||
      (ltfBOS.direction === 'BEARISH' && htfContext.trend === 'BEARISH');

    if (aligned) {
      const confScore = ltfBOS.confidence;
      const confidence: MTFConfidence =
        confScore >= 70 ? 'HIGH' : confScore >= 45 ? 'MEDIUM' : 'LOW';

      return {
        signal: ltfBOS,
        alignedWithHTF: true,
        signalType: 'BOS_CONTINUATION',
        confidence,
        reason: `5min ${ltfBOS.direction} BOS @ ${ltfBOS.breakPrice.toFixed(2)} → 1H ${htfContext.trend} 추세 지속` +
                (ltfBOS.volumeConfirmed ? ' (거래량 확인)' : ''),
      };
    }
  }

  // CHoCH — 반전 시그널
  if (ltfCHoCH) {
    const aligned =
      (ltfCHoCH.direction === 'BULLISH' && (htfContext.trend === 'BULLISH' || htfContext.trend === 'CONSOLIDATION')) ||
      (ltfCHoCH.direction === 'BEARISH' && (htfContext.trend === 'BEARISH' || htfContext.trend === 'CONSOLIDATION'));

    if (aligned) {
      const confScore = ltfCHoCH.confidence;
      // CHoCH는 BOS보다 낮은 confidence (반전은 더 위험)
      const confidence: MTFConfidence =
        confScore >= 80 ? 'HIGH' : confScore >= 55 ? 'MEDIUM' : 'LOW';

      return {
        signal: ltfCHoCH,
        alignedWithHTF: aligned,
        signalType: 'CHOCH_REVERSAL',
        confidence,
        reason: `5min ${ltfCHoCH.direction} CHoCH @ ${ltfCHoCH.breakPrice.toFixed(2)} → 추세 반전 감지` +
                (ltfCHoCH.volumeConfirmed ? ' (거래량 확인)' : ''),
      };
    }
  }

  // BOS/CHoCH 있지만 HTF와 불일치
  if (ltfBOS || ltfCHoCH) {
    const sig = ltfBOS || ltfCHoCH!;
    return {
      signal: sig,
      alignedWithHTF: false,
      signalType: 'NO_SIGNAL',
      confidence: 'LOW',
      reason: `LTF ${sig.type} ${sig.direction} 감지됐으나 HTF(${htfContext.trend})와 불일치`,
    };
  }

  return noSignal;
}

// ── MTF Confluence ─────────────────────────────────────────────────────

/**
 * MTF 합류 분석 — HTF 컨텍스트 + LTF 시그널 통합
 * 최상위 오케스트레이터
 */
export function analyzeMTF(
  htfCandles: OHLC[],
  ltfCandles: OHLC[],
  currentPrice: number,
): MTFAnalysis {
  // 1. HTF 컨텍스트 구축
  const htf = buildHTFContext(htfCandles, currentPrice);

  // 2. LTF 시그널 스캔
  const ltf = scanLTFSignal(ltfCandles, htf);

  // 3. 방향 결정
  let direction: MTFDirection = 'NEUTRAL';
  if (ltf.alignedWithHTF && ltf.signal) {
    direction = ltf.signal.direction === 'BULLISH' ? 'LONG' : 'SHORT';
  }

  // 4. 진입 구간 설명
  let entryZone = '시그널 없음';
  if (direction === 'LONG') {
    entryZone = htf.keySupport
      ? `${htf.keySupport.toFixed(2)} ~ ${currentPrice.toFixed(2)} (지지 구간)`
      : `${currentPrice.toFixed(2)} 부근`;
  } else if (direction === 'SHORT') {
    entryZone = htf.keyResistance
      ? `${currentPrice.toFixed(2)} ~ ${htf.keyResistance.toFixed(2)} (저항 구간)`
      : `${currentPrice.toFixed(2)} 부근`;
  }

  // 5. 손절: LTF 마지막 스윙 기준
  let stopLoss: number | null = null;
  const ltfHighs = findSwingHighs(ltfCandles, MTF_DEFAULTS.ltfLeftBars, MTF_DEFAULTS.ltfRightBars);
  const ltfLows = findSwingLows(ltfCandles, MTF_DEFAULTS.ltfLeftBars, MTF_DEFAULTS.ltfRightBars);

  if (direction === 'LONG' && ltfLows.length > 0) {
    stopLoss = ltfLows[ltfLows.length - 1].price;
  } else if (direction === 'SHORT' && ltfHighs.length > 0) {
    stopLoss = ltfHighs[ltfHighs.length - 1].price;
  }

  // 6. 목표가: HTF 구조 레벨
  let takeProfit: number | null = null;
  if (direction === 'LONG') {
    takeProfit = htf.keyResistance;
  } else if (direction === 'SHORT') {
    takeProfit = htf.keySupport;
  }

  // 7. 한줄 요약
  let summary: string;
  if (direction === 'NEUTRAL') {
    summary = htf.trend === 'CONSOLIDATION'
      ? '1H 보합 — 방향성 없음. 구조 돌파 대기.'
      : `1H ${htf.trend} 추세이나 5min 시그널 미확인. 대기.`;
  } else {
    const sigLabel = ltf.signalType === 'BOS_CONTINUATION' ? 'BOS 추세 지속' : 'CHoCH 반전';
    summary = `1H ${htf.trend} 추세에서 5min ${sigLabel} 확인 → ${direction}`;
    if (stopLoss !== null && takeProfit !== null) {
      const rr = Math.abs(takeProfit - currentPrice) / Math.abs(currentPrice - stopLoss);
      summary += ` (R:R ${rr.toFixed(1)}:1)`;
    }
  }

  return {
    htf,
    ltf,
    direction,
    signalType: ltf.signalType,
    confidence: ltf.confidence,
    entryZone,
    stopLoss,
    takeProfit,
    summary,
  };
}
