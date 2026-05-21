import { useState, useEffect, useCallback } from 'react';
import { RefreshCw, Shield } from 'lucide-react';
import { RebalanceHeader } from '@components/rebalance/RebalanceHeader';
import { RecommendationTable } from '@components/rebalance/RecommendationTable';
import { ScanSummary } from '@components/rebalance/ScanSummary';
import { BacktestSection } from '@components/rebalance/BacktestSection';
import type { RebalanceResult, RebalanceStatus, RebalanceSyncStatus } from '@lib/api';
import {
    MARKETS,
    getMarketConfig,
    triggerRebalanceScan,
    fetchRebalanceRecommendations,
    fetchRebalanceStatus,
    fetchRebalanceSyncStatus,
    triggerRebalanceSync,
} from '@lib/api';
import { useAppState } from '@contexts/AppStateContext';
import './Rebalance.css';

function syncTimeAgo(iso: string | null | undefined): string {
    if (!iso) return 'never synced';
    const t = new Date(iso).getTime();
    if (Number.isNaN(t)) return iso;
    const diff = Math.floor((Date.now() - t) / 1000);
    if (diff < 60) return `${diff}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
}

export function Rebalance() {
    const { activeMarket, setActiveMarket } = useAppState();
    const [result, setResult] = useState<RebalanceResult | null>(null);
    const [status, setStatus] = useState<RebalanceStatus | null>(null);
    const [syncStatus, setSyncStatus] = useState<RebalanceSyncStatus | null>(null);
    const [isScanning, setIsScanning] = useState(false);
    const [isSyncing, setIsSyncing] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const marketConfig = getMarketConfig(activeMarket);

    // Load cached recommendations and status on mount / market change
    useEffect(() => {
        let cancelled = false;
        (async () => {
            try {
                const [rec, st, syncSt] = await Promise.all([
                    fetchRebalanceRecommendations(activeMarket),
                    fetchRebalanceStatus(activeMarket),
                    fetchRebalanceSyncStatus(activeMarket),
                ]);
                if (!cancelled) {
                    setResult(rec);
                    setStatus(st);
                    setSyncStatus(syncSt);
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

    const handleSyncToOperations = useCallback(async () => {
        if (isSyncing) return;
        setIsSyncing(true);
        setError(null);
        try {
            await triggerRebalanceSync(activeMarket, { commit: true, trigger: 'MANUAL' });
            const syncSt = await fetchRebalanceSyncStatus(activeMarket);
            setSyncStatus(syncSt);
        } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : 'Sync to Operations failed';
            setError(msg);
        } finally {
            setIsSyncing(false);
        }
    }, [activeMarket, isSyncing]);

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

            {/* Phase A/C — Universe sync 상태 + 수동 Sync 버튼 */}
            <div className="rebalance-sync-bar glass-panel">
                <div className="rebalance-sync-info">
                    <Shield size={14} />
                    <span>
                        {syncStatus?.latest_sync
                            ? `Last auto-sync to Operations: ${syncStatus.latest_sync.created_at.slice(0, 19).replace('T', ' ')} (${syncTimeAgo(syncStatus.latest_sync.created_at)}, ${syncStatus.latest_sync.trigger})`
                            : 'Universe has not been synced to Operations yet.'}
                    </span>
                    {syncStatus && syncStatus.active_count > 0 && (
                        <span className="rebalance-sync-stat">
                            {syncStatus.active_count} active · {syncStatus.protected_count} protected
                        </span>
                    )}
                </div>
                <button
                    type="button"
                    className="rebalance-sync-btn"
                    onClick={handleSyncToOperations}
                    disabled={isSyncing}
                    title="Replace Operations universe with current BUY+HOLD recommendations"
                >
                    <RefreshCw size={13} className={isSyncing ? 'spin' : ''} />
                    {isSyncing ? 'Syncing…' : 'Sync to Operations now'}
                </button>
            </div>

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

            <BacktestSection activeMarket={activeMarket} />
        </div>
    );
}
