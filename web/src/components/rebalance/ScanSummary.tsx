import type { RebalanceResult } from '../../lib/api';

interface ScanSummaryProps {
    result: RebalanceResult | null;
}

export function ScanSummary({ result }: ScanSummaryProps) {
    if (!result || !result.scan_date) {
        return (
            <div className="scan-summary glass-panel">
                <div className="scan-summary-empty">
                    Click "Run Scan" to analyze the universe and generate recommendations.
                </div>
            </div>
        );
    }

    const passRate = result.total_scanned > 0
        ? ((result.passed_prefilter / result.total_scanned) * 100).toFixed(1)
        : '0';

    return (
        <div className="scan-summary glass-panel">
            <div className="scan-summary-grid">
                <div className="scan-stat">
                    <span className="scan-stat-value">{result.total_scanned}</span>
                    <span className="scan-stat-label">Total Scanned</span>
                </div>
                <div className="scan-stat">
                    <span className="scan-stat-value">{result.passed_prefilter}</span>
                    <span className="scan-stat-label">Passed Filter</span>
                </div>
                <div className="scan-stat">
                    <span className="scan-stat-value">{passRate}%</span>
                    <span className="scan-stat-label">Pass Rate</span>
                </div>
                <div className="scan-stat">
                    <span className="scan-stat-value">{result.buy.length}</span>
                    <span className="scan-stat-label">Buy Signals</span>
                </div>
            </div>
        </div>
    );
}
