/**
 * useLiveMarketOverview — SSE 기반 실시간 마켓 오버뷰 훅.
 *
 * SSE market_overview 이벤트를 primary로, REST fetchMarketOverview를 fallback으로 사용.
 */

import { useSSE } from './useSSE';
import { fetchMarketOverview, type MarketOverview } from '../lib/api';

export function useLiveMarketOverview(): MarketOverview | null {
  return useSSE<MarketOverview>('market_overview', fetchMarketOverview);
}
