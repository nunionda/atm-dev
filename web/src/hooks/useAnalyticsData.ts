import { useState, useEffect } from 'react';
import { fetchAnalyticsData, type AnalyticsResponse } from '../lib/api';

export function useAnalyticsData(ticker: string, period: string = 'ytd', interval: string = '1d') {
    const [data, setData] = useState<AnalyticsResponse | null>(null);
    const [loading, setLoading] = useState<boolean>(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        let mounted = true;

        async function loadData() {
            try {
                setLoading(true);
                setError(null);
                const result = await fetchAnalyticsData(ticker, period, interval);
                if (mounted) {
                    setData(result);
                    setLoading(false);
                }
            } catch (err: any) {
                if (mounted) {
                    setError(err.message || 'An error occurred fetching data.');
                    setLoading(false);
                }
            }
        }

        loadData();

        return () => {
            mounted = false;
        };
    }, [ticker, period, interval]);

    return { data, loading, error };
}
