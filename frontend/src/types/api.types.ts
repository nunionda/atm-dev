/**
 * API Response Types — Phase 2 Refactor
 *
 * 백엔드 (`/api/v1/...`) 응답 스키마 및 도메인 모델 타입의 중앙 허브.
 * 현재는 `web/src/lib/api.ts` 의 정의를 re-export 하는 형태로,
 * 기존 import 호환성을 깨지 않으면서 새 코드가 `@/types` 단일 경로로
 * 접근할 수 있도록 한다. Phase 3에서 api.ts 분할 시 실제 정의를
 * 이 폴더로 이관한다.
 *
 * Usage:
 *   import type { Position, SystemState } from '@/types';
 *   import type { Position, SystemState } from '@types/api.types';
 */

export type {
    // Analytics / Quote
    AnalyticsData,
    AnalyticsResponse,
    QuoteCandle,
    QuoteLatest,
    QuoteResponse,
    // Search
    SearchResult,
    // Market Overview
    MarketIndex,
    MarketRegime,
    MarketOverview,
    // Markets
    MarketId,
    MarketConfig,
    // System
    SystemStatus,
    SystemMarketRegime,
    SystemState,
    // Positions / Orders / Signals
    PositionStatus,
    Position,
    OrderSide,
    OrderType,
    OrderStatus,
    Order,
    SignalType,
    Signal,
    // Risk
    RiskMetrics,
    RiskEvent,
    // Performance
    PerformanceSummary,
    EquityPoint,
    TradeRecord,
    ComparisonMetrics,
    PerformanceComparison,
    // Market Intelligence
    IndexTrend,
    MAAlignment,
    VolatilityState,
    IndexTrendData,
    TrendChangeEntry,
    MarketIntelligenceData,
    MarketIntelligenceResponse,
    // Simulation Control
    StrategyMode,
    ReplayStatus,
    ReplayProgress,
    SimControllerStatus,
    SimControlResult,
    ForceLiquidateResult,
    // Replay Results
    ReplayResultSummary,
    ReplayResultFull,
    // Rebalance
    RebalanceRecommendation,
    RebalanceResult,
    RebalanceStatus,
    // Backtest
    BacktestMetrics,
    UniverseBacktestResult,
    BacktestStatus,
} from '@lib/api';
