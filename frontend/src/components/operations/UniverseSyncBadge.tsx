/**
 * UniverseSyncBadge — Rebalance → Universe 동기화 상태 표시 (Phase A/C).
 *
 * "Synced 14:32 (2h ago) · 12 active · 8 protected" 형태의 칩.
 * 클릭 시 drawer로 최근 7건 sync log 표시.
 */
import { useEffect, useState } from 'react';
import { RefreshCw, Shield, X } from 'lucide-react';
import type { MarketId } from '@lib/api';
import {
    fetchRebalanceSyncStatus,
    fetchRebalanceSyncLog,
    triggerRebalanceSync,
    type RebalanceSyncStatus,
    type RebalanceSyncLogEntry,
} from '@lib/api';
import './UniverseSyncBadge.css';

interface Props {
    market: MarketId;
}

function timeAgo(iso: string | null | undefined): string {
    if (!iso) return 'never';
    const t = new Date(iso).getTime();
    if (Number.isNaN(t)) return iso;
    const diff = Math.floor((Date.now() - t) / 1000);
    if (diff < 60) return `${diff}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
}

export function UniverseSyncBadge({ market }: Props) {
    const [status, setStatus] = useState<RebalanceSyncStatus | null>(null);
    const [drawerOpen, setDrawerOpen] = useState(false);
    const [log, setLog] = useState<RebalanceSyncLogEntry[]>([]);
    const [logLoading, setLogLoading] = useState(false);
    const [syncing, setSyncing] = useState(false);

    const refresh = async () => {
        try {
            const s = await fetchRebalanceSyncStatus(market);
            setStatus(s);
        } catch (e) {
            console.warn('sync status fetch failed', e);
        }
    };

    useEffect(() => {
        refresh();
        const id = setInterval(refresh, 60_000);
        return () => clearInterval(id);
    }, [market]);

    const openDrawer = async () => {
        setDrawerOpen(true);
        setLogLoading(true);
        try {
            const items = await fetchRebalanceSyncLog(market, 7);
            setLog(items);
        } catch (e) {
            console.warn('sync log fetch failed', e);
        } finally {
            setLogLoading(false);
        }
    };

    const handleManualSync = async () => {
        if (syncing) return;
        setSyncing(true);
        try {
            await triggerRebalanceSync(market, { commit: true, trigger: 'MANUAL' });
            await refresh();
            if (drawerOpen) {
                const items = await fetchRebalanceSyncLog(market, 7);
                setLog(items);
            }
        } catch (e) {
            console.error('manual sync failed', e);
        } finally {
            setSyncing(false);
        }
    };

    const latest = status?.latest_sync ?? null;
    const lastTime = latest?.created_at;
    const activeCount = status?.active_count ?? 0;
    const protectedCount = status?.protected_count ?? 0;

    return (
        <>
            <button
                type="button"
                className="universe-sync-badge"
                onClick={openDrawer}
                title="Open sync log"
            >
                <RefreshCw size={13} className={syncing ? 'spin' : ''} />
                <span className="usb-label">
                    {latest
                        ? `Synced ${timeAgo(lastTime)} · ${activeCount} active`
                        : `Universe not synced · ${activeCount} active`}
                </span>
                {protectedCount > 0 && (
                    <span className="usb-protected">
                        <Shield size={11} /> {protectedCount}
                    </span>
                )}
            </button>

            {drawerOpen && (
                <div className="usb-drawer-backdrop" onClick={() => setDrawerOpen(false)}>
                    <div className="usb-drawer" onClick={e => e.stopPropagation()}>
                        <div className="usb-drawer-head">
                            <div>
                                <h3>Universe Sync — {market.toUpperCase()}</h3>
                                <p className="usb-drawer-sub">
                                    {latest
                                        ? `Last: ${latest.created_at} (${latest.trigger})`
                                        : 'No sync log yet'}
                                </p>
                            </div>
                            <div className="usb-drawer-actions">
                                <button
                                    type="button"
                                    className="usb-btn usb-btn-primary"
                                    onClick={handleManualSync}
                                    disabled={syncing}
                                >
                                    {syncing ? 'Syncing…' : 'Sync now'}
                                </button>
                                <button
                                    type="button"
                                    className="usb-btn"
                                    onClick={() => setDrawerOpen(false)}
                                >
                                    <X size={14} />
                                </button>
                            </div>
                        </div>

                        <div className="usb-drawer-body">
                            {logLoading && <p className="usb-empty">Loading…</p>}
                            {!logLoading && log.length === 0 && (
                                <p className="usb-empty">No sync history yet. Click "Sync now" to run.</p>
                            )}
                            {!logLoading && log.length > 0 && (
                                <table className="usb-table">
                                    <thead>
                                        <tr>
                                            <th>When</th>
                                            <th>Trigger</th>
                                            <th>BUY</th>
                                            <th>HOLD</th>
                                            <th>KEEP</th>
                                            <th>Total</th>
                                            <th>Protected</th>
                                            <th>Duration</th>
                                            <th>Status</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {log.map(row => (
                                            <tr key={row.sync_id}>
                                                <td>{row.created_at.slice(0, 19).replace('T', ' ')}</td>
                                                <td>{row.trigger}</td>
                                                <td>{row.buy_count}</td>
                                                <td>{row.hold_count}</td>
                                                <td>{row.kept_count}</td>
                                                <td>{row.total_active}</td>
                                                <td>{row.protected_count}</td>
                                                <td>{row.duration_ms}ms</td>
                                                <td>
                                                    {row.error
                                                        ? <span className="usb-bad">{row.error}</span>
                                                        : <span className="usb-ok">OK</span>}
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            )}
                        </div>
                    </div>
                </div>
            )}
        </>
    );
}
