/**
 * Trading Session Engine — 상태 머신 + 시나리오 빌더 + 레벨 알림 + 포지션 관리
 *
 * 5가지 핵심 질문 해결:
 *   Q1. 오늘 어떤 시나리오가 가능한가?  → buildScenarios()
 *   Q2. 가격이 어디에 도달하면 주목?     → extractKeyLevels() + checkAlerts()
 *   Q3. 지금 진입 조건 충족?             → (기존 scalpEngine 유지)
 *   Q4. 진입 후 어떻게 관리?             → evaluatePosition()
 *   Q5. 언제 끝내나?                     → suggestExitAction()
 *
 * Phase Flow: PLANNING → WATCHING → ALERT → ENTERED → MANAGING → CLOSED
 */

import type { ScalpResult, ScalpInputs, AutoStats, VolumeSRLevel, OHLC, AssetConfig } from './scalpEngine';
import { ASSETS, fmt, fmtPct } from './scalpEngine';

// ── Types ──────────────────────────────────────────────────────────────

export type TradingPhase =
  | 'PLANNING'    // 장 시작 전: 시나리오 수립, 키 레벨 설정
  | 'WATCHING'    // 대기: 가격이 키 레벨에 접근 중인지 모니터링
  | 'ALERT'       // 주목: 키 레벨 도달, 진입 조건 점검 중
  | 'ENTERED'     // 진입: 포지션 보유, 관리 시작
  | 'MANAGING'    // 관리: TP 일부 도달 or BE스탑 이동
  | 'CLOSED';     // 종료: 결과 기록

export interface Scenario {
  id: string;
  name: string;                   // e.g., "지지선 롱 스캘프"
  type: 'LONG' | 'SHORT';
  trigger: string;                // e.g., "가격 5,870 도달 시"
  condition: string;              // e.g., "Z ≥ 2.0 + Volume S/R 지지 확인"
  targetPrice: number;
  stopPrice: number;
  rr: number;
  confidence: 'HIGH' | 'MEDIUM' | 'LOW';
  reasoning: string;
}

export interface KeyLevel {
  price: number;
  label: string;                  // e.g., "POC", "VAH", "-2σ"
  type: 'SUPPORT' | 'RESISTANCE' | 'PIVOT';
  source: 'VOLUME_SR' | 'SIGMA_BAND' | 'MA' | 'ATR_STOP' | 'SWING';
  strength: 1 | 2 | 3;
}

export interface LevelAlert {
  level: KeyLevel;
  proximityPct: number;           // 현재가 대비 거리 (%)
  status: 'FAR' | 'APPROACHING' | 'AT_LEVEL' | 'BREACHED';
  direction: 'FROM_ABOVE' | 'FROM_BELOW';
}

export interface EntryRecord {
  price: number;
  contracts: number;
  time: number;                   // timestamp
  direction: 'LONG' | 'SHORT';
  z: number;
  verdict: string;
  scenario: string;               // 어떤 시나리오로 진입했는지
  initialSL: number;
  initialTP: number;
}

export interface PartialExit {
  price: number;
  contracts: number;
  time: number;
  reason: string;                 // "1R TP", "Trail Stop", etc.
}

export interface ExitRecord {
  price: number;
  contracts: number;
  time: number;
  reason: 'SL' | 'TP' | 'TRAIL' | 'MANUAL' | 'TIMEOUT';
  pnlPoints: number;
  pnlUSD: number;
  holdDuration: number;           // ms
}

export type StopMode = 'INITIAL' | 'BREAKEVEN' | 'TRAILING';

export interface PositionEval {
  currentR: number;               // R 배수 (양수 = 수익)
  pnlPoints: number;
  pnlUSD: number;
  holdMs: number;
  stopMode: StopMode;
  currentSL: number;              // 현재 스탑 레벨
  action: string;                 // 추천 액션
  actionType: 'HOLD' | 'PARTIAL_TP' | 'TRAIL_STOP' | 'CLOSE' | 'WARNING';
  reason: string;
}

export interface SessionState {
  phase: TradingPhase;
  startedAt: number;
  asset: string;

  // Planning
  scenarios: Scenario[];
  keyLevels: KeyLevel[];

  // Watching
  activeAlerts: LevelAlert[];

  // Entry
  entry: EntryRecord | null;

  // Managing
  partialExits: PartialExit[];
  currentStopMode: StopMode;

  // Closed
  exitRecord: ExitRecord | null;
}

// ── Phase Transition ───────────────────────────────────────────────────

const VALID_TRANSITIONS: Record<TradingPhase, TradingPhase[]> = {
  PLANNING: ['WATCHING'],
  WATCHING: ['ALERT', 'PLANNING'],
  ALERT:    ['ENTERED', 'WATCHING', 'PLANNING'],
  ENTERED:  ['MANAGING', 'CLOSED'],
  MANAGING: ['CLOSED'],
  CLOSED:   ['PLANNING'],
};

export function canTransition(state: SessionState, to: TradingPhase): boolean {
  return VALID_TRANSITIONS[state.phase]?.includes(to) ?? false;
}

export function initSession(asset: string): SessionState {
  return {
    phase: 'PLANNING',
    startedAt: Date.now(),
    asset,
    scenarios: [],
    keyLevels: [],
    activeAlerts: [],
    entry: null,
    partialExits: [],
    currentStopMode: 'INITIAL',
    exitRecord: null,
  };
}

export function transitionPhase(state: SessionState, to: TradingPhase): SessionState {
  if (!canTransition(state, to)) return state;
  return { ...state, phase: to };
}

// ── Scenario Builder (Q1) ──────────────────────────────────────────────

let scenarioCounter = 0;
function nextScenarioId(): string { return `SC-${++scenarioCounter}`; }

export function buildScenarios(
  calc: ScalpResult,
  inputs: ScalpInputs,
  autoStats: AutoStats | null,
): Scenario[] {
  const scenarios: Scenario[] = [];
  const { currentPrice, ma, stdDev, atr } = inputs;
  const cfg = calc.cfg;
  if (!autoStats || stdDev <= 0 || atr <= 0) return scenarios;

  const adaptiveStop = calc.adaptiveStop;
  const fmtP = (p: number) => p.toFixed(2);

  // ── 시나리오 1: Volume S/R 지지선 롱 ──
  if (calc.volumeSR?.nearestSupport != null) {
    const sup = calc.volumeSR.nearestSupport;
    const dist = currentPrice - sup;
    if (dist > 0 && dist < atr * 3) {
      const sl = sup - adaptiveStop;
      const tp = ma;
      const reward = Math.abs(tp - sup);
      const risk = Math.abs(sup - sl);
      const rr = risk > 0 ? reward / risk : 0;
      scenarios.push({
        id: nextScenarioId(),
        name: '지지선 롱 스캘프',
        type: 'LONG',
        trigger: `가격 ${fmtP(sup)} 도달 시`,
        condition: 'Z ≥ 1.5 + Volume S/R 지지 확인',
        targetPrice: tp,
        stopPrice: sl,
        rr: +rr.toFixed(2),
        confidence: rr >= 1.5 ? 'HIGH' : rr >= 1.0 ? 'MEDIUM' : 'LOW',
        reasoning: `거래량 기반 지지선(${fmtP(sup)})에서 MA(${fmtP(ma)})까지 평균회귀 기대. R:R ${rr.toFixed(1)}:1`,
      });
    }
  }

  // ── 시나리오 2: Volume S/R 저항선 숏 ──
  if (calc.volumeSR?.nearestResistance != null) {
    const res = calc.volumeSR.nearestResistance;
    const dist = res - currentPrice;
    if (dist > 0 && dist < atr * 3) {
      const sl = res + adaptiveStop;
      const tp = ma;
      const reward = Math.abs(res - tp);
      const risk = Math.abs(sl - res);
      const rr = risk > 0 ? reward / risk : 0;
      scenarios.push({
        id: nextScenarioId(),
        name: '저항선 숏 스캘프',
        type: 'SHORT',
        trigger: `가격 ${fmtP(res)} 도달 시`,
        condition: 'Z ≥ +1.5 + Volume S/R 저항 확인',
        targetPrice: tp,
        stopPrice: sl,
        rr: +rr.toFixed(2),
        confidence: rr >= 1.5 ? 'HIGH' : rr >= 1.0 ? 'MEDIUM' : 'LOW',
        reasoning: `거래량 기반 저항선(${fmtP(res)})에서 MA(${fmtP(ma)})까지 평균회귀 기대. R:R ${rr.toFixed(1)}:1`,
      });
    }
  }

  // ── 시나리오 3: -2σ 평균회귀 롱 ──
  const minus2s = ma - 2 * stdDev;
  {
    const sl = minus2s - adaptiveStop;
    const tp = ma;
    const reward = Math.abs(tp - minus2s);
    const risk = Math.abs(minus2s - sl);
    const rr = risk > 0 ? reward / risk : 0;
    scenarios.push({
      id: nextScenarioId(),
      name: '-2σ 평균회귀 롱',
      type: 'LONG',
      trigger: `가격 ${fmtP(minus2s)} 이탈 시`,
      condition: 'Z ≥ 2.0 (95% 신뢰 이탈) + 거래량 확인',
      targetPrice: tp,
      stopPrice: sl,
      rr: +rr.toFixed(2),
      confidence: rr >= 2.0 ? 'HIGH' : rr >= 1.3 ? 'MEDIUM' : 'LOW',
      reasoning: `95% 신뢰구간 이탈(-2σ = ${fmtP(minus2s)})에서 강한 평균회귀 기대. 통계적 우위.`,
    });
  }

  // ── 시나리오 4: +2σ 평균회귀 숏 ──
  const plus2s = ma + 2 * stdDev;
  {
    const sl = plus2s + adaptiveStop;
    const tp = ma;
    const reward = Math.abs(plus2s - tp);
    const risk = Math.abs(sl - plus2s);
    const rr = risk > 0 ? reward / risk : 0;
    scenarios.push({
      id: nextScenarioId(),
      name: '+2σ 평균회귀 숏',
      type: 'SHORT',
      trigger: `가격 ${fmtP(plus2s)} 이탈 시`,
      condition: 'Z ≥ +2.0 (95% 신뢰 이탈) + 거래량 확인',
      targetPrice: tp,
      stopPrice: sl,
      rr: +rr.toFixed(2),
      confidence: rr >= 2.0 ? 'HIGH' : rr >= 1.3 ? 'MEDIUM' : 'LOW',
      reasoning: `95% 신뢰구간 상방이탈(+2σ = ${fmtP(plus2s)})에서 강한 하방회귀 기대. 통계적 우위.`,
    });
  }

  // ── 시나리오 5: 현재 시그널 기반 즉시 진입 ──
  if (Math.abs(calc.z) >= 1.5 && calc.netEV > 0) {
    const dir: 'LONG' | 'SHORT' = calc.isLong ? 'LONG' : 'SHORT';
    const tp = calc.tp15;
    const sl = calc.adaptiveSL;
    const reward = Math.abs(tp - currentPrice);
    const risk = Math.abs(currentPrice - sl);
    const rr = risk > 0 ? reward / risk : 0;
    scenarios.push({
      id: nextScenarioId(),
      name: `현재 시그널 ${dir}`,
      type: dir,
      trigger: '현재가 — 즉시 진입 가능',
      condition: `Z = ${fmt(calc.z)} | EV = ${fmt(calc.netEV)}t | ${calc.verdict}`,
      targetPrice: tp,
      stopPrice: sl,
      rr: +rr.toFixed(2),
      confidence: calc.verdict === 'GO' ? 'HIGH' : calc.verdict === 'CAUTION' ? 'MEDIUM' : 'LOW',
      reasoning: `현재 Z-Score ${fmt(calc.z)}로 ${dir} 시그널 활성. 순 기대값 ${fmt(calc.netEV)}t.`,
    });
  }

  // ── Composite Trend 반영 — 역추세 시나리오 confidence 하향 ──
  const ct = calc.compositeTrend;
  if (ct && ct.bias !== 'SIDEWAYS' && ct.confidence >= 30) {
    for (const sc of scenarios) {
      const isCounterTrend =
        (sc.type === 'LONG' && ct.bias === 'BEARISH') ||
        (sc.type === 'SHORT' && ct.bias === 'BULLISH');
      if (isCounterTrend) {
        // Confidence 한 단계 하향
        if (sc.confidence === 'HIGH') sc.confidence = 'MEDIUM';
        else if (sc.confidence === 'MEDIUM') sc.confidence = 'LOW';
        sc.reasoning += ` ⚠ 역추세(${ct.bias}) — 리스크 증가.`;
      }
    }
  }

  // 높은 신뢰도 먼저 정렬
  const confOrder = { HIGH: 0, MEDIUM: 1, LOW: 2 };
  scenarios.sort((a, b) => confOrder[a.confidence] - confOrder[b.confidence]);

  return scenarios;
}

// ── Key Level Extraction (Q2) ──────────────────────────────────────────

export function extractKeyLevels(
  calc: ScalpResult,
  inputs: ScalpInputs,
  autoStats: AutoStats | null,
): KeyLevel[] {
  const levels: KeyLevel[] = [];
  const { currentPrice, ma, stdDev, atr } = inputs;
  if (!autoStats || stdDev <= 0) return levels;

  // MA (피벗)
  levels.push({
    price: ma,
    label: `MA${autoStats.maPeriod}`,
    type: 'PIVOT',
    source: 'MA',
    strength: 3,
  });

  // Sigma bands
  const sigmaLevels = [
    { mult: 1.0, label: '1σ' },
    { mult: 1.5, label: '1.5σ' },
    { mult: 2.0, label: '2σ' },
  ];
  for (const { mult, label } of sigmaLevels) {
    const upper = ma + stdDev * mult;
    const lower = ma - stdDev * mult;
    levels.push({
      price: upper,
      label: `+${label}`,
      type: upper > currentPrice ? 'RESISTANCE' : 'SUPPORT',
      source: 'SIGMA_BAND',
      strength: mult >= 2 ? 3 : mult >= 1.5 ? 2 : 1,
    });
    levels.push({
      price: lower,
      label: `-${label}`,
      type: lower < currentPrice ? 'SUPPORT' : 'RESISTANCE',
      source: 'SIGMA_BAND',
      strength: mult >= 2 ? 3 : mult >= 1.5 ? 2 : 1,
    });
  }

  // ATR stop levels
  levels.push({
    price: calc.adaptiveSL,
    label: 'SL (적응형)',
    type: calc.isLong ? 'SUPPORT' : 'RESISTANCE',
    source: 'ATR_STOP',
    strength: 2,
  });

  // TP levels
  levels.push({
    price: calc.tp15,
    label: 'TP 1.5R',
    type: calc.isLong ? 'RESISTANCE' : 'SUPPORT',
    source: 'ATR_STOP',
    strength: 2,
  });
  levels.push({
    price: calc.tp2,
    label: 'TP 2R',
    type: calc.isLong ? 'RESISTANCE' : 'SUPPORT',
    source: 'ATR_STOP',
    strength: 1,
  });

  // Volume S/R levels
  if (calc.volumeSR) {
    for (const lv of calc.volumeSR.levels.slice(0, 6)) {
      const srcLabel =
        lv.source === 'poc' ? 'POC' :
        lv.source === 'vah' ? 'VAH' :
        lv.source === 'val' ? 'VAL' :
        lv.source === 'high_vol_high' ? 'HV-High' : 'HV-Low';
      levels.push({
        price: lv.price,
        label: srcLabel,
        type: lv.type === 'support' ? 'SUPPORT' : 'RESISTANCE',
        source: 'VOLUME_SR',
        strength: lv.strength,
      });
    }
  }

  // 가격순 정렬 (높은 가격 → 낮은 가격)
  levels.sort((a, b) => b.price - a.price);

  // 중복 제거 (매우 가까운 레벨 병합)
  const merged: KeyLevel[] = [];
  const clusterDist = atr * 0.2;
  for (const lv of levels) {
    const existing = merged.find(m => Math.abs(m.price - lv.price) < clusterDist);
    if (existing) {
      // 더 높은 strength 유지
      if (lv.strength > existing.strength) {
        existing.strength = lv.strength;
        existing.label = `${existing.label}/${lv.label}`;
      }
    } else {
      merged.push({ ...lv });
    }
  }

  return merged;
}

// ── Level Alert System (Q2 실시간) ─────────────────────────────────────

export function checkAlerts(
  currentPrice: number,
  keyLevels: KeyLevel[],
  thresholdPct: number = 0.3,     // 0.3% 이내 = APPROACHING
  atLevelPct: number = 0.1,       // 0.1% 이내 = AT_LEVEL
): LevelAlert[] {
  if (keyLevels.length === 0 || currentPrice <= 0) return [];

  return keyLevels.map(level => {
    const diff = currentPrice - level.price;
    const absPct = Math.abs(diff / currentPrice) * 100;
    const direction: LevelAlert['direction'] = diff > 0 ? 'FROM_ABOVE' : 'FROM_BELOW';

    let status: LevelAlert['status'];
    if (absPct <= atLevelPct) {
      status = 'AT_LEVEL';
    } else if (absPct <= thresholdPct) {
      status = 'APPROACHING';
    } else if (
      (level.type === 'SUPPORT' && diff < 0) ||
      (level.type === 'RESISTANCE' && diff > 0)
    ) {
      status = 'BREACHED';
    } else {
      status = 'FAR';
    }

    return { level, proximityPct: +absPct.toFixed(3), status, direction };
  });
}

/** 주목할 알림만 필터 — APPROACHING, AT_LEVEL, BREACHED */
export function getActiveAlerts(alerts: LevelAlert[]): LevelAlert[] {
  return alerts.filter(a => a.status !== 'FAR');
}

// ── Position Management (Q4, Q5) ───────────────────────────────────────

export function evaluatePosition(
  entry: EntryRecord,
  currentPrice: number,
  calc: ScalpResult,
  cfg: AssetConfig,
): PositionEval {
  const isLong = entry.direction === 'LONG';
  const pnlPoints = isLong ? (currentPrice - entry.price) : (entry.price - currentPrice);
  const pnlUSD = pnlPoints * cfg.ptVal * entry.contracts;
  const holdMs = Date.now() - entry.time;

  // R 배수 = 현재 수익 / 초기 리스크
  const initialRisk = Math.abs(entry.price - entry.initialSL);
  const currentR = initialRisk > 0 ? pnlPoints / initialRisk : 0;

  // 스탑 모드 결정
  let stopMode: StopMode = 'INITIAL';
  let currentSL = entry.initialSL;

  if (currentR >= 1.5) {
    // 1.5R 이상: 트레일링 스탑 (1R 수준으로 이동)
    stopMode = 'TRAILING';
    currentSL = isLong
      ? entry.price + initialRisk * 1.0
      : entry.price - initialRisk * 1.0;
  } else if (currentR >= 0.5) {
    // 0.5R 이상: BE 스탑 (진입가로 이동)
    stopMode = 'BREAKEVEN';
    currentSL = entry.price;
  }

  // 액션 추천
  let action: string;
  let actionType: PositionEval['actionType'];
  let reason: string;

  const holdMin = holdMs / 60000;

  if (pnlPoints < 0 && Math.abs(currentPrice - currentSL) < calc.atrStop * 0.2) {
    // 손절 접근
    actionType = 'WARNING';
    action = '⚠ 손절 레벨 접근';
    reason = `SL(${currentSL.toFixed(2)})까지 ${Math.abs(currentPrice - currentSL).toFixed(2)}pt — 계획 유지 또는 축소`;
  } else if (currentR >= 2.0) {
    // 2R 이상 수익
    actionType = 'CLOSE';
    action = '🎯 2R 도달 — 전량 청산 고려';
    reason = `R배수 ${currentR.toFixed(1)}R, 수익 ${pnlPoints.toFixed(2)}pt. 목표 달성.`;
  } else if (currentR >= 1.5) {
    // 1.5R 수익
    actionType = 'PARTIAL_TP';
    action = '💰 1.5R 도달 — 부분 익절 추천 (50%)';
    reason = `R배수 ${currentR.toFixed(1)}R. 절반 청산 후 나머지 트레일링.`;
  } else if (currentR >= 1.0) {
    // 1R 수익
    actionType = 'TRAIL_STOP';
    action = '📈 1R 도달 — BE 스탑 확인';
    reason = `스탑을 진입가(${entry.price.toFixed(2)})로 이동. 무손실 보장.`;
  } else if (Math.abs(calc.z) < 0.5 && Math.abs(entry.z) >= 1.5) {
    // Z 회귀 — 평균회귀 완료
    actionType = 'CLOSE';
    action = '🔄 Z-Score 회귀 — 포지션 정리 고려';
    reason = `진입 시 Z=${fmt(entry.z)} → 현재 Z=${fmt(calc.z)}. 평균회귀 완료.`;
  } else if (holdMin >= 30) {
    // 시간 경과
    actionType = 'WARNING';
    action = `⏰ ${Math.floor(holdMin)}분 경과 — 모멘텀 확인`;
    reason = `장기 보유 중. R배수 ${currentR.toFixed(1)}R. 모멘텀 약화 시 정리.`;
  } else {
    actionType = 'HOLD';
    action = '✅ 계획대로 보유';
    reason = `R배수 ${currentR.toFixed(1)}R. 스탑 모드: ${stopMode}.`;
  }

  return {
    currentR: +currentR.toFixed(2),
    pnlPoints: +pnlPoints.toFixed(2),
    pnlUSD: +pnlUSD.toFixed(2),
    holdMs,
    stopMode,
    currentSL: +currentSL.toFixed(2),
    action,
    actionType,
    reason,
  };
}

export function suggestExitAction(
  entry: EntryRecord,
  currentPrice: number,
  calc: ScalpResult,
): { shouldExit: boolean; reason: string; exitType: ExitRecord['reason'] } {
  const isLong = entry.direction === 'LONG';
  const pnlPoints = isLong ? (currentPrice - entry.price) : (entry.price - currentPrice);
  const initialRisk = Math.abs(entry.price - entry.initialSL);
  const currentR = initialRisk > 0 ? pnlPoints / initialRisk : 0;

  // SL 히트
  if ((isLong && currentPrice <= entry.initialSL) || (!isLong && currentPrice >= entry.initialSL)) {
    return { shouldExit: true, reason: `손절 히트 (SL ${entry.initialSL.toFixed(2)})`, exitType: 'SL' };
  }

  // TP 히트 (2R)
  if (currentR >= 2.0) {
    return { shouldExit: true, reason: `목표 달성 (2R = ${pnlPoints.toFixed(2)}pt)`, exitType: 'TP' };
  }

  // Z 회귀 완료
  if (Math.abs(calc.z) < 0.3 && Math.abs(entry.z) >= 1.5) {
    return { shouldExit: true, reason: `Z-Score 회귀 완료 (${fmt(entry.z)} → ${fmt(calc.z)})`, exitType: 'MANUAL' };
  }

  // 시간 초과 (60분)
  const holdMin = (Date.now() - entry.time) / 60000;
  if (holdMin >= 60) {
    return { shouldExit: true, reason: `60분 경과 — 타임아웃`, exitType: 'TIMEOUT' };
  }

  return { shouldExit: false, reason: '', exitType: 'MANUAL' };
}

// ── Session Utilities ──────────────────────────────────────────────────

export const PHASE_LABELS: Record<TradingPhase, string> = {
  PLANNING: '📋 시나리오 수립',
  WATCHING: '👀 대기 중',
  ALERT:    '🔔 레벨 도달',
  ENTERED:  '📊 포지션 보유',
  MANAGING: '⚡ 포지션 관리',
  CLOSED:   '✅ 세션 종료',
};

export const PHASE_COLORS: Record<TradingPhase, string> = {
  PLANNING: '#7986cb',
  WATCHING: '#ffab40',
  ALERT:    '#ff1744',
  ENTERED:  '#00e676',
  MANAGING: '#42a5f5',
  CLOSED:   '#6b7594',
};

/** 포맷: 보유 시간 표시 */
export function formatHoldTime(ms: number): string {
  const sec = Math.floor(ms / 1000);
  if (sec < 60) return `${sec}초`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}분`;
  const hr = Math.floor(min / 60);
  return `${hr}시간 ${min % 60}분`;
}
