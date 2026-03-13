import { useState, useEffect, useCallback } from 'react';
import { TrendingUp, Target, BarChart3, Skull, RefreshCw } from 'lucide-react';
import type { PerformanceSummary, MarketId } from '../../lib/api';
import { fetchPerformanceSummary } from '../../lib/api';
import { useSSE } from '../../hooks/useSSE';
import './OpsPerformanceCards.css';

interface OpsPerformanceCardsProps {
    market: MarketId;
}

export function OpsPerformanceCards({ market }: OpsPerformanceCardsProps) {
    const [data, setData] = useState<PerformanceSummary | null>(null);
    const [error, setError] = useState(false);
    const sseData = useSSE<PerformanceSummary>(`${market}:performance`, () => fetchPerformanceSummary(market));

    const loadData = useCallback(() => {
        setError(false);
        setData(null);
        fetchPerformanceSummary(market).then(setData).catch(() => setError(true));
    }, [market]);

    useEffect(() => { loadData(); }, [loadData]);

    const displayData = sseData || data;

    if (error && !displayData) {
        return (
            <div className="ops-perf-section">
                <h3 className="section-title"><BarChart3 size={16} /> 성과 요약</h3>
                <div className="error-placeholder">
                    서버 연결 실패
                    <button className="retry-btn" onClick={loadData}><RefreshCw size={12} /> 재시도</button>
                </div>
            </div>
        );
    }

    if (!displayData) return null;

    return (
        <div className="ops-perf-section">
            <h3 className="section-title">
                <BarChart3 size={16} />
                성과 요약
            </h3>
            <div className="ops-perf-cards">
                <div className="ops-perf-card glass-panel">
                    <TrendingUp size={16} className="ops-perf-icon" />
                    <div className="ops-perf-info">
                        <span className="ops-perf-label">총 수익률</span>
                        <span className={`ops-perf-value ${displayData.total_return_pct >= 0 ? 'positive' : 'negative'}`}>
                            {displayData.total_return_pct >= 0 ? '+' : ''}{displayData.total_return_pct.toFixed(2)}%
                        </span>
                    </div>
                </div>
                <div className="ops-perf-card glass-panel">
                    <Target size={16} className="ops-perf-icon" />
                    <div className="ops-perf-info">
                        <span className="ops-perf-label">승률</span>
                        <span className="ops-perf-value">{displayData.win_rate.toFixed(1)}%</span>
                        <span className="ops-perf-sub">{displayData.total_trades}건</span>
                    </div>
                </div>
                <div className="ops-perf-card glass-panel">
                    <BarChart3 size={16} className="ops-perf-icon" />
                    <div className="ops-perf-info">
                        <span className="ops-perf-label">Profit Factor</span>
                        <span className="ops-perf-value">{displayData.profit_factor.toFixed(2)}</span>
                    </div>
                </div>
                <div className="ops-perf-card glass-panel">
                    <Skull size={16} className="ops-perf-icon" />
                    <div className="ops-perf-info">
                        <span className="ops-perf-label">MDD</span>
                        <span className="ops-perf-value negative">{displayData.max_drawdown_pct.toFixed(1)}%</span>
                    </div>
                </div>
            </div>
        </div>
    );
}
