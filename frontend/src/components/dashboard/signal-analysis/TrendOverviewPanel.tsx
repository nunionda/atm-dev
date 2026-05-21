/**
 * TrendOverviewPanel — extracted from SignalAnalysis.
 *
 * Phase D3 분할: dashboard/SignalAnalysis.tsx → dashboard/signal-analysis/TrendOverviewPanel.tsx
 */

import { TrendingUp } from 'lucide-react';
import type { TrendFilter } from '@lib/signalEngine';

export function TrendOverviewPanel({ trend }: { trend: TrendFilter }) {
    const biasColor = trend.bias.includes('BULL') ? '#22c55e' : trend.bias.includes('BEAR') ? '#ef4444' : '#94a3b8';

    return (
        <div className="sa-entry-section glass-panel">
            <h3 className="sa-section-title">
                <TrendingUp size={16} />
                Trend Overview
            </h3>
            <div className="ft-indicator-grid">
                <div className="ft-row">
                    <span className="ft-label">MA 배열</span>
                    <span className="ft-value">{trend.maAlignment}</span>
                </div>
                <div className="ft-row">
                    <span className="ft-label">ADX 추세강도</span>
                    <span className="ft-value">
                        {trend.adxStrength}
                        {trend.adxValue != null && <span className="ft-num"> ({trend.adxValue.toFixed(1)})</span>}
                    </span>
                </div>
                <div className="ft-row">
                    <span className="ft-label">방향지표 (DI)</span>
                    <span className="ft-value">{trend.diSignal}</span>
                </div>
                {trend.pctFrom200 != null && (
                    <div className="ft-row">
                        <span className="ft-label">200MA 대비</span>
                        <span className="ft-value" style={{ color: trend.pctFrom200 >= 0 ? '#22c55e' : '#ef4444' }}>
                            {trend.pctFrom200 >= 0 ? '+' : ''}{trend.pctFrom200.toFixed(1)}%
                        </span>
                    </div>
                )}
                {trend.pctFrom50 != null && (
                    <div className="ft-row">
                        <span className="ft-label">50MA 대비</span>
                        <span className="ft-value" style={{ color: trend.pctFrom50 >= 0 ? '#22c55e' : '#ef4444' }}>
                            {trend.pctFrom50 >= 0 ? '+' : ''}{trend.pctFrom50.toFixed(1)}%
                        </span>
                    </div>
                )}
            </div>
            <div className="trend-bias-badge" style={{ color: biasColor, background: `${biasColor}1a`, border: `1px solid ${biasColor}40` }}>
                {trend.biasLabel}
            </div>
        </div>
    );
}

// --- SMC Panel ---

