import { useState, useEffect, useCallback } from 'react';
import { fetchAnalyticsData, type AnalyticsResponse } from '../lib/api';

export function useAnalyticsData(ticker: string, period: string = 'ytd', interval: string = '1d') {
    const [data, setData] = useState<AnalyticsResponse | null>(null);
    const [loading, setLoading] = useState<boolean>(true);
    const [error, setError] = useState<string | null>(null);
    const [fetchKey, setFetchKey] = useState(0);

    useEffect(() => {
        const controller = new AbortController();

        async function loadData() {
            try {
                setLoading(true);
                setError(null);
                const result = await fetchAnalyticsData(ticker, period, interval, controller.signal);
                if (!controller.signal.aborted) {
                    setData(result);
                    setLoading(false);
                }
            } catch (err: any) {
                if (controller.signal.aborted || err?.name === 'AbortError') return; // Ignore aborted requests
                setError(err.message || 'An error occurred fetching data.');
                setLoading(false);
            }
        }

        loadData();

        return () => {
            controller.abort();
        };
    }, [ticker, period, interval, fetchKey]);

    const refetch = useCallback(() => setFetchKey(k => k + 1), []);

    return { data, loading, error, refetch };
}
