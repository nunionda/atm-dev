import { TrendingUp, Target, BarChart3, Calendar, Award, Skull } from 'lucide-react';
import type { PerformanceSummary } from '../../lib/api';
import './PerformanceMetrics.css';

interface PerformanceMetricsProps {
    data: PerformanceSummary;
}

export function PerformanceMetrics({ data }: PerformanceMetricsProps) {
    return (
        <div className="perf-metrics">
            <div className="perf-metric-card glass-panel">
                <TrendingUp size={18} className="perf-icon" />
                <div className="perf-metric-info">
                    <span className="perf-metric-label">총 수익률</span>
                    <span className={`perf-metric-value ${data.total_return_pct >= 0 ? 'positive' : 'negative'}`}>
                        {data.total_return_pct >= 0 ? '+' : ''}{data.total_return_pct.toFixed(2)}%
                    </span>
                </div>
            </div>
            <div className="perf-metric-card glass-panel">
                <Target size={18} className="perf-icon" />
                <div className="perf-metric-info">
                    <span className="perf-metric-label">승률</span>
                    <span className="perf-metric-value">{data.win_rate.toFixed(1)}%</span>
                    <span className="perf-metric-sub">{data.total_trades}건 중</span>
                </div>
            </div>
            <div className="perf-metric-card glass-panel">
                <BarChart3 size={18} className="perf-icon" />
                <div className="perf-metric-info">
                    <span className="perf-metric-label">Profit Factor</span>
                    <span className="perf-metric-value">{data.profit_factor.toFixed(2)}</span>
                </div>
            </div>
            <div className="perf-metric-card glass-panel">
                <Award size={18} className="perf-icon" />
                <div className="perf-metric-info">
                    <span className="perf-metric-label">Sharpe Ratio</span>
                    <span className="perf-metric-value">{data.sharpe_ratio.toFixed(2)}</span>
                </div>
            </div>
            <div className="perf-metric-card glass-panel">
                <Skull size={18} className="perf-icon" />
                <div className="perf-metric-info">
                    <span className="perf-metric-label">MDD</span>
                    <span className="perf-metric-value negative">{data.max_drawdown_pct.toFixed(1)}%</span>
                </div>
            </div>
            <div className="perf-metric-card glass-panel">
                <Calendar size={18} className="perf-icon" />
                <div className="perf-metric-info">
                    <span className="perf-metric-label">평균 보유일</span>
                    <span className="perf-metric-value">{data.avg_holding_days.toFixed(1)}일</span>
                </div>
            </div>
        </div>
    );
}
