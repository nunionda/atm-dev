/**
 * useLivePrice — SSE 기반 실시간 가격 훅.
 *
 * 특정 티커의 가격을 SSE price_update 이벤트로 실시간 수신.
 * mount 시 백엔드에 구독 요청, unmount 시 구독 해제.
 */

import { useState, useEffect, useRef } from 'react';
import { useSSE } from './useSSE';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';

export interface LivePrice {
  ticker: string;
  price: number;
  change: number;
  change_pct: number;
  volume: number;
  timestamp: string;
}

export function useLivePrice(ticker: string): LivePrice | null {
  const allPrices = useSSE<LivePrice>('price_update');
  const [price, setPrice] = useState<LivePrice | null>(null);
  const prevTickerRef = useRef<string>('');

  // Filter by ticker
  useEffect(() => {
    if (allPrices && allPrices.ticker?.toUpperCase() === ticker.toUpperCase()) {
      setPrice(allPrices);
    }
  }, [allPrices, ticker]);

  // Reset on ticker change
  useEffect(() => {
    if (prevTickerRef.current !== ticker) {
      setPrice(null);
      prevTickerRef.current = ticker;
    }
  }, [ticker]);

  // Subscribe/unsubscribe via REST
  useEffect(() => {
    if (!ticker) return;

    const subscribe = () => {
      fetch(`${API_BASE_URL}/live/subscribe?ticker=${encodeURIComponent(ticker)}`, {
        method: 'POST',
      }).catch(() => {});
    };

    const unsubscribe = () => {
      fetch(`${API_BASE_URL}/live/unsubscribe?ticker=${encodeURIComponent(ticker)}`, {
        method: 'POST',
      }).catch(() => {});
    };

    subscribe();
    return () => { unsubscribe(); };
  }, [ticker]);

  return price;
}
