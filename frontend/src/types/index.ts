/**
 * Type Hub — Phase 2 Refactor
 *
 * 모든 타입을 단일 진입점으로 노출. 새 코드는 `@/types`에서 import 권장.
 *
 * Layers:
 *   api.types.ts      : 백엔드 응답 / 도메인 모델 (Position, SystemState, ...)
 *   futures.types.ts  : 선물/ESF 스캘핑 도메인
 *   chart.types.ts    : 차트/그리기 도구
 *
 * Usage:
 *   import type { Position, SystemState, MarketId } from '@/types';
 */

export type * from './api.types';
export type * from './futures.types';
export type * from './chart.types';
