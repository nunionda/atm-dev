/**
 * useMarketSession — 클라이언트 사이드 장시간 판단 훅
 *
 * 티커 기반으로 US/KR 마켓을 자동 감지하고,
 * 장중/장외에 따라 적절한 폴링 간격을 반환한다.
 *
 * - US: 09:30-16:00 ET 평일
 * - KR: 09:00-15:30 KST 평일
 * - 60초마다 재평가
 */

import { useState, useEffect, useMemo } from 'react';

type Market = 'US' | 'KR';

interface MarketSession {
  /** 현재 장이 열려 있는지 */
  isOpen: boolean;
  /** 추천 폴링 간격 (ms) — 백엔드 캐시 TTL과 정렬 */
  interval: number;
  /** 감지된 마켓 */
  market: Market;
}

/** 장중 폴링 간격: 5분 (백엔드 CACHE_TTL = 300s) */
const MARKET_OPEN_INTERVAL = 300_000;
/** 장외 폴링 간격: 10분 (가격 변동 없음) */
const MARKET_CLOSED_INTERVAL = 600_000;

function detectMarket(ticker: string): Market {
  if (
    ticker.endsWith('.KS') ||
    ticker.endsWith('.KQ') ||
    ticker.startsWith('^KS') ||
    ticker.startsWith('^KQ') ||
    ticker.startsWith('@KS') ||
    ticker === 'KRW=X'
  ) {
    return 'KR';
  }
  return 'US';
}

function isWeekday(date: Date): boolean {
  const day = date.getDay();
  return day >= 1 && day <= 5;
}

function isUSMarketOpen(now: Date): boolean {
  // UTC → ET (EDT = UTC-4, EST = UTC-5)
  // 간소화: EDT 기준 (3월~11월)
  const utcH = now.getUTCHours();
  const utcM = now.getUTCMinutes();
  const etMinutes = (utcH * 60 + utcM) - 4 * 60; // EDT offset
  const etH = Math.floor(((etMinutes % 1440) + 1440) % 1440 / 60);
  const etM = ((etMinutes % 1440) + 1440) % 1440 % 60;

  // ET 기준 요일 판단
  const etDate = new Date(now.getTime() - 4 * 60 * 60 * 1000);
  if (!isWeekday(etDate)) return false;

  const totalMin = etH * 60 + etM;
  // 09:30 ~ 16:00
  return totalMin >= 570 && totalMin < 960;
}

function isKRMarketOpen(now: Date): boolean {
  // UTC → KST (UTC+9)
  const kstDate = new Date(now.getTime() + 9 * 60 * 60 * 1000);
  if (!isWeekday(kstDate)) return false;

  const h = kstDate.getUTCHours();
  const m = kstDate.getUTCMinutes();
  const totalMin = h * 60 + m;
  // 09:00 ~ 15:30
  return totalMin >= 540 && totalMin < 930;
}

function getSession(ticker: string): MarketSession {
  const market = detectMarket(ticker);
  const now = new Date();
  const isOpen = market === 'US' ? isUSMarketOpen(now) : isKRMarketOpen(now);

  return {
    isOpen,
    interval: isOpen ? MARKET_OPEN_INTERVAL : MARKET_CLOSED_INTERVAL,
    market,
  };
}

export function useMarketSession(ticker: string): MarketSession {
  const market = useMemo(() => detectMarket(ticker), [ticker]);
  const [session, setSession] = useState<MarketSession>(() => getSession(ticker));

  useEffect(() => {
    // 즉시 업데이트
    setSession(getSession(ticker));

    // 60초마다 재평가 (장 개장/마감 전환 감지)
    const timer = setInterval(() => {
      setSession(getSession(ticker));
    }, 60_000);

    return () => clearInterval(timer);
  }, [ticker, market]);

  return session;
}
