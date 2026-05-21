/**
 * lib/api.ts — Barrel
 *
 * Phase 3.A-2 완료: 모든 도메인은 ./api/* 로 분할됨.
 * 75+ 기존 import 호환성을 위해 단일 진입점으로 re-export.
 *
 * 분할 구조:
 *   ./api/_client.ts    : API_BASE_URL, USE_MOCK, fetchOrMock (공유 헬퍼)
 *   ./api/analyze.ts    : analytics, quote, MTF, search       (~171 lines)
 *   ./api/market.ts     : market overview, MarketId, intel    (~156 lines)
 *   ./api/operations.ts : system, positions, orders, signals, risk, performance  (~210)
 *   ./api/sim.ts        : force-liquidate, sim control, replay (~231)
 *   ./api/rebalance.ts  : rebalance, universe backtest         (~166)
 *   ./api/futures.ts    : KOSPI200/E-mini 선물                 (~279)
 *   ./api/esf.ts        : ESF 스캘핑 + journal/experiments     (~619)
 *
 * Before: 1,770 lines monolith.
 * After:  ~30 lines barrel + 1,830 lines split across 8 domain files.
 *
 * 새 코드 권장 import 패턴:
 *   import { fetchPositions } from '@lib/api';         // works (barrel)
 *   import { fetchPositions } from '@lib/api/operations'; // also works (direct)
 *   import type { Position } from '@/types';           // type-only via hub
 */

export * from './api/_client';
export * from './api/analyze';
export * from './api/market';
export * from './api/operations';
export * from './api/sim';
export * from './api/rebalance';
export * from './api/futures';
export * from './api/esf';
