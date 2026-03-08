import { RefreshCw, Loader2 } from 'lucide-react';
import type { RebalanceStatus } from '../../lib/api';

interface RebalanceHeaderProps {
    status: RebalanceStatus | null;
    isScanning: boolean;
    onScan: () => void;
}

export function RebalanceHeader({ status, isScanning, onScan }: RebalanceHeaderProps) {
    const lastScan = status?.last_scan_date;
    const formatDate = (d: string) => {
        if (d.length === 8) return `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6)}`;
        return d;
    };

    return (
        <div className="rebalance-header glass-panel">
            <div className="rebalance-header-info">
                <div className="rebalance-header-status">
                    {lastScan ? (
                        <>
                            <span className="status-dot active" />
                            <span>Last scan: {formatDate(lastScan)}</span>
                        </>
                    ) : (
                        <>
                            <span className="status-dot inactive" />
                            <span>No scan results yet</span>
                        </>
                    )}
                </div>
                {status && (
                    <span className="rebalance-watchlist-count">
                        Watchlist: {status.current_watchlist_count} stocks
                    </span>
                )}
            </div>
            <button
                className="btn-primary rebalance-scan-btn"
                onClick={onScan}
                disabled={isScanning}
            >
                {isScanning ? (
                    <>
                        <Loader2 size={16} className="spin-icon" />
                        <span>Scanning...</span>
                    </>
                ) : (
                    <>
                        <RefreshCw size={16} />
                        <span>Run Scan</span>
                    </>
                )}
            </button>
        </div>
    );
}
