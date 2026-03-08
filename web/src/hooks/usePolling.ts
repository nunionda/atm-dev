/**
 * usePolling — 범용 HTTP 폴링 훅
 *
 * 기능:
 * - 설정 가능한 폴링 간격 (10s / 30s / 60s)
 * - on/off 토글
 * - 에러 시 exponential backoff (1.5배, max 120s)
 * - 3회 연속 실패 → stale 상태
 * - 수동 즉시 새로고침 (fetchNow)
 * - unmount 시 타이머 자동 정리
 */

import { useState, useEffect, useRef, useCallback } from 'react';

export type PollingStatus = 'idle' | 'polling' | 'error' | 'stale';

export interface PollingOptions {
  /** 폴링 간격 (ms). 기본 30000 (30초) */
  interval?: number;
  /** 폴링 활성화 여부. 기본 false */
  enabled?: boolean;
  /** stale 판정 전 최대 연속 에러 횟수. 기본 3 */
  maxRetries?: number;
  /** 에러 시 간격 배수. 기본 1.5 */
  backoffMult?: number;
}

export interface PollingState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  status: PollingStatus;
  lastUpdated: number | null;
  consecutiveErrors: number;
  /** 폴링 on/off 토글 */
  setEnabled: (v: boolean) => void;
  /** 간격 변경 (ms) */
  setInterval: (ms: number) => void;
  /** 현재 간격 */
  interval: number;
  /** 즉시 fetch */
  fetchNow: () => void;
  /** 폴링 활성화 여부 */
  enabled: boolean;
}

export function usePolling<T>(
  fetchFn: () => Promise<T>,
  options: PollingOptions = {},
): PollingState<T> {
  const {
    interval: initInterval = 30000,
    enabled: initEnabled = false,
    maxRetries = 3,
    backoffMult = 1.5,
  } = options;

  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<PollingStatus>('idle');
  const [lastUpdated, setLastUpdated] = useState<number | null>(null);
  const [enabled, setEnabled] = useState(initEnabled);
  const [interval, setIntervalMs] = useState(initInterval);

  const fetchRef = useRef(fetchFn);
  fetchRef.current = fetchFn;

  const mountedRef = useRef(true);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const errCountRef = useRef(0);

  const clearTimer = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const doFetch = useCallback(async () => {
    if (!mountedRef.current) return;
    setLoading(true);

    try {
      const result = await fetchRef.current();
      if (!mountedRef.current) return;
      setData(result);
      setError(null);
      errCountRef.current = 0;
      setLastUpdated(Date.now());
      setStatus('polling');
    } catch (err: unknown) {
      if (!mountedRef.current) return;
      errCountRef.current += 1;
      const msg = err instanceof Error ? err.message : 'Polling error';
      setError(msg);
      setStatus(errCountRef.current >= maxRetries ? 'stale' : 'error');
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, [maxRetries]);

  // 폴링 루프
  useEffect(() => {
    if (!enabled) {
      setStatus(prev => prev === 'idle' ? 'idle' : 'idle');
      clearTimer();
      return;
    }

    // 활성화 시 즉시 1회 fetch
    doFetch();

    const schedule = () => {
      // backoff 적용
      const eff = errCountRef.current > 0
        ? Math.min(interval * Math.pow(backoffMult, errCountRef.current), 120000)
        : interval;

      timerRef.current = setTimeout(async () => {
        await doFetch();
        if (mountedRef.current && enabled) schedule();
      }, eff);
    };

    schedule();

    return () => { clearTimer(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, interval]);

  // unmount 정리
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      clearTimer();
    };
  }, [clearTimer]);

  const fetchNow = useCallback(() => {
    doFetch();
  }, [doFetch]);

  return {
    data,
    loading,
    error,
    status,
    lastUpdated,
    consecutiveErrors: errCountRef.current,
    setEnabled,
    setInterval: setIntervalMs,
    interval,
    fetchNow,
    enabled,
  };
}
