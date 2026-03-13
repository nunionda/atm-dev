/**
 * 싱글톤 EventSource SSE 훅.
 * 모든 컴포넌트가 하나의 SSE 연결을 공유한다.
 * Mock 모드(VITE_USE_MOCK=true)에서는 SSE를 사용하지 않는다.
 */

import { useState, useEffect, useRef, useCallback } from 'react';

const API_BASE_URL = 'http://localhost:8000/api/v1';
const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true';

// --- Singleton EventSource ---

type SSEStatus = 'disconnected' | 'connecting' | 'connected' | 'error';
type Listener = (data: unknown) => void;

let eventSource: EventSource | null = null;
let refCount = 0;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let reconnectCount = 0;
const MAX_BACKOFF = 30_000;

const sharedListeners = new Map<string, Set<Listener>>();
const statusListeners = new Set<(status: SSEStatus) => void>();
let currentStatus: SSEStatus = 'disconnected';
let lastEventTime: number = 0;

function setStatus(s: SSEStatus) {
    currentStatus = s;
    statusListeners.forEach(fn => fn(s));
}

function connect() {
    if (eventSource) return;
    setStatus('connecting');

    const es = new EventSource(`${API_BASE_URL}/stream`);
    eventSource = es;

    es.onopen = () => {
        setStatus('connected');
        reconnectCount = 0;
    };

    es.onerror = () => {
        setStatus('error');
        es.close();
        eventSource = null;
        scheduleReconnect();
    };

    // 각 이벤트 타입에 대한 리스너 등록 (마켓별 접두사)
    const BASE_EVENTS = ['system_state', 'positions', 'signals', 'orders', 'risk_metrics', 'risk_events', 'replay_progress', 'equity_curve', 'performance'];
    const MARKET_IDS = ['kospi', 'sp500', 'ndx'];
    const eventTypes = [
        'heartbeat',
        ...MARKET_IDS.flatMap(m => BASE_EVENTS.map(e => `${m}:${e}`)),
    ];
    for (const type of eventTypes) {
        es.addEventListener(type, (event: MessageEvent) => {
            lastEventTime = Date.now();
            try {
                const data = JSON.parse(event.data);
                const listeners = sharedListeners.get(type);
                if (listeners) {
                    listeners.forEach(fn => fn(data));
                }
            } catch {
                // JSON 파싱 실패 무시
            }
        });
    }
}

function disconnect() {
    if (eventSource) {
        eventSource.close();
        eventSource = null;
    }
    if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
    }
    setStatus('disconnected');
    reconnectCount = 0;
}

function scheduleReconnect() {
    if (reconnectTimer) return;
    const delay = Math.min(1000 * Math.pow(2, reconnectCount), MAX_BACKOFF);
    reconnectCount++;
    reconnectTimer = setTimeout(() => {
        reconnectTimer = null;
        if (refCount > 0) connect();
    }, delay);
}

function addListener(eventType: string, fn: Listener) {
    let set = sharedListeners.get(eventType);
    if (!set) {
        set = new Set();
        sharedListeners.set(eventType, set);
    }
    set.add(fn);
}

function removeListener(eventType: string, fn: Listener) {
    const set = sharedListeners.get(eventType);
    if (set) {
        set.delete(fn);
        if (set.size === 0) sharedListeners.delete(eventType);
    }
}

// --- Hooks ---

/**
 * SSE 이벤트를 구독하여 최신 데이터를 반환한다.
 * Mock 모드에서는 항상 null을 반환한다.
 *
 * @param eventType - SSE 이벤트 타입 (e.g. 'system_state', 'positions')
 * @param fallbackFetch - SSE 연결 실패 시 REST 폴링에 사용할 fetch 함수 (선택)
 */
export function useSSE<T>(
    eventType: string,
    fallbackFetch?: () => Promise<T>,
): T | null {
    const [data, setData] = useState<T | null>(null);
    const fallbackRef = useRef(fallbackFetch);
    fallbackRef.current = fallbackFetch;

    useEffect(() => {
        // 이벤트 타입 변경 시 이전 마켓의 stale 데이터 초기화
        setData(null);

        if (USE_MOCK) return;

        // ref count 관리: 첫 구독 시 connect
        refCount++;
        if (refCount === 1) connect();

        const handler: Listener = (d) => setData(d as T);
        addListener(eventType, handler);

        return () => {
            removeListener(eventType, handler);
            refCount--;
            if (refCount <= 0) {
                refCount = 0;
                disconnect();
            }
        };
    }, [eventType]);

    // 폴백: SSE 연결 실패 또는 지연 시 REST 폴링
    useEffect(() => {
        if (USE_MOCK) return;
        if (!fallbackRef.current) return;

        let interval: ReturnType<typeof setInterval> | null = null;
        let initialTimer: ReturnType<typeof setTimeout> | null = null;
        let cancelled = false;
        let initialFetched = false;

        const doFetch = () => {
            if (!cancelled && fallbackRef.current) {
                fallbackRef.current().then(d => { if (!cancelled) setData(d); }).catch(() => {});
            }
        };

        const startPolling = () => {
            if (!interval && !cancelled) {
                doFetch();
                interval = setInterval(doFetch, 30_000);
            }
        };

        const statusHandler = (status: SSEStatus) => {
            if (status === 'error' || status === 'disconnected') {
                startPolling();
            } else if (status === 'connected') {
                if (interval) {
                    clearInterval(interval);
                    interval = null;
                }
            }
        };

        statusListeners.add(statusHandler);
        // 현재 상태 체크
        statusHandler(currentStatus);

        // SSE가 3초 내 연결되지 않으면 1회 REST 폴백 실행
        if (currentStatus !== 'connected' && !initialFetched) {
            initialTimer = setTimeout(() => {
                if (!cancelled && currentStatus !== 'connected' && !initialFetched) {
                    initialFetched = true;
                    doFetch();
                }
            }, 3000);
        }

        return () => {
            cancelled = true;
            statusListeners.delete(statusHandler);
            if (interval) clearInterval(interval);
            if (initialTimer) clearTimeout(initialTimer);
        };
    }, [eventType]);

    return data;
}

/**
 * SSE 연결 상태를 반환한다.
 */
export function useSSEStatus(): {
    status: SSEStatus;
    lastEventTime: number;
    reconnectCount: number;
} {
    const [status, setStatus_] = useState<SSEStatus>(currentStatus);

    const handler = useCallback((s: SSEStatus) => setStatus_(s), []);

    useEffect(() => {
        if (USE_MOCK) return;
        statusListeners.add(handler);
        return () => { statusListeners.delete(handler); };
    }, [handler]);

    return { status, lastEventTime, reconnectCount };
}
