import { useState, useEffect, useCallback } from 'react';
import { RebalanceHeader } from '../components/rebalance/RebalanceHeader';
import { RecommendationTable } from '../components/rebalance/RecommendationTable';
import { ScanSummary } from '../components/rebalance/ScanSummary';
import type { RebalanceResult, RebalanceStatus } from '../lib/api';
import {
    MARKETS,
    getMarketConfig,
    triggerRebalanceScan,
    fetchRebalanceRecommendations,
    fetchRebalanceStatus,
} from '../lib/api';
import { useAppState } from '../contexts/AppStateContext';
import './Rebalance.css';

export function Rebalance() {
    const { activeMarket, setActiveMarket } = useAppState();
    const [result, setResult] = useState<RebalanceResult | null>(null);
    const [status, setStatus] = useState<RebalanceStatus | null>(null);
    const [isScanning, setIsScanning] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const marketConfig = getMarketConfig(activeMarket);

    // Load cached recommendations and status on mount / market change
    useEffect(() => {
        let cancelled = false;
        (async () => {
            try {
                const [rec, st] = await Promise.all([
                    fetchRebalanceRecommendations(activeMarket),
                    fetchRebalanceStatus(activeMarket),
                ]);
                if (!cancelled) {
                    setResult(rec);
                    setStatus(st);
                    setError(null);
                }
            } catch (err) {
                if (!cancelled) {
                    console.error('Failed to load rebalance data:', err);
                }
            }
        })();
        return () => { cancelled = true; };
    }, [activeMarket]);

    const handleScan = useCallback(async () => {
        setIsScanning(true);
        setError(null);
        try {
            const scanResult = await triggerRebalanceScan(activeMarket);
            setResult(scanResult);
            // Refresh status
            const st = await fetchRebalanceStatus(activeMarket);
            setStatus(st);
        } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : 'Scan failed';
            setError(msg);
        } finally {
            setIsScanning(false);
        }
    }, [activeMarket]);

    return (
        <div className="rebalance-page container">
            <div className="rebalance-page-header">
                <h1 className="page-title">Universe Rebalancing</h1>
                <div className="market-tabs">
                    {MARKETS.map(m => (
                        <button
                            key={m.id}
                            className={`market-tab-btn ${activeMarket === m.id ? 'active' : ''}`}
                            onClick={() => setActiveMarket(m.id)}
                        >
                            <span className="market-flag">{m.flag}</span>
                            <span className="market-label">{m.label}</span>
                        </button>
                    ))}
                </div>
            </div>

            <RebalanceHeader
                status={status}
                isScanning={isScanning}
                onScan={handleScan}
            />

            {error && (
                <div className="rebalance-error glass-panel">
                    {error}
                </div>
            )}

            <ScanSummary result={result} />

            <div className="rebalance-grid">
                <RecommendationTable
                    title="BUY Recommendations"
                    icon="📈"
                    items={result?.buy ?? []}
                    type="BUY"
                    currencySymbol={marketConfig.currencySymbol}
                />
                <RecommendationTable
                    title="HOLD Positions"
                    icon="📊"
                    items={result?.hold ?? []}
                    type="HOLD"
                    currencySymbol={marketConfig.currencySymbol}
                />
            </div>

            <RecommendationTable
                title="SELL Recommendations"
                icon="📉"
                items={result?.sell ?? []}
                type="SELL"
                currencySymbol={marketConfig.currencySymbol}
            />
        </div>
    );
}
