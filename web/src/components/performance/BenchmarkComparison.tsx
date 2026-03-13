import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { BarChart3, ChevronDown, ChevronUp, AlertTriangle, ArrowRight } from 'lucide-react';
import type { MarketId, PerformanceComparison, ComparisonMetrics } from '../../lib/api';
import { fetchPerformanceComparison } from '../../lib/api';
import './BenchmarkComparison.css';

interface Props {
    market: MarketId;
}

interface MetricDef {
    key: keyof ComparisonMetrics;
    label: string;
    unit: string;
    higherIsBetter: boolean;
}

const METRICS: MetricDef[] = [
    { key: 'total_return_pct', label: '총 수익률', unit: '%', higherIsBetter: true },
    { key: 'sharpe_ratio', label: 'Sharpe Ratio', unit: '', higherIsBetter: true },
    { key: 'max_drawdown_pct', label: 'MDD', unit: '%', higherIsBetter: false },
    { key: 'win_rate', label: '승률', unit: '%', higherIsBetter: true },
    { key: 'profit_factor', label: 'Profit Factor', unit: '', higherIsBetter: true },
];

function formatValue(val: number, unit: string): string {
    if (unit === '%') return `${val.toFixed(2)}%`;
    return val.toFixed(2);
}

function getDeltaClass(delta: number, higherIsBetter: boolean): string {
    if (delta === 0) return 'neutral';
    const isGood = higherIsBetter ? delta > 0 : delta < 0;
    return isGood ? 'positive' : 'negative';
}

export function BenchmarkComparison({ market }: Props) {
    const navigate = useNavigate();
    const [data, setData] = useState<PerformanceComparison | null>(null);
    const [loading, setLoading] = useState(true);
    const [collapsed, setCollapsed] = useState(false);

    const loadData = useCallback(() => {
        setLoading(true);
        fetchPerformanceComparison(market)
            .then(setData)
            .catch(() => setData(null))
            .finally(() => setLoading(false));
    }, [market]);

    useEffect(() => { loadData(); }, [loadData]);

    if (loading) {
        return (
            <div className="bench-panel glass-panel">
                <div className="bench-header">
                    <h3 className="section-title"><BarChart3 size={16} /> Live vs Backtest</h3>
                </div>
                <div className="bench-loading">로딩 중...</div>
            </div>
        );
    }

    if (!data) return null;

    const sharpeDelta = data.deltas?.sharpe_ratio ?? 0;
    const hasDrift = data.has_backtest && sharpeDelta < -0.5;

    return (
        <div className="bench-panel glass-panel">
            <div className="bench-header" onClick={() => setCollapsed(!collapsed)}>
                <h3 className="section-title">
                    <BarChart3 size={16} />
                    Live vs Backtest
                    {data.has_backtest && (
                        <span className={`bench-status ${hasDrift ? 'drift' : 'ok'}`}>
                            {hasDrift ? 'Drift' : 'Aligned'}
                        </span>
                    )}
                </h3>
                <button className="bench-toggle">
                    {collapsed ? <ChevronDown size={16} /> : <ChevronUp size={16} />}
                </button>
            </div>

            {!collapsed && (
                <div className="bench-body">
                    {hasDrift && (
                        <div className="bench-drift-alert">
                            <AlertTriangle size={14} />
                            <span>
                                <strong>Strategy Drift 감지</strong> — Sharpe 차이 {sharpeDelta.toFixed(2)}.
                                전략 파라미터 점검이 필요합니다.
                            </span>
                        </div>
                    )}

                    {!data.has_backtest ? (
                        <div className="bench-no-backtest">
                            <p>백테스트 결과가 없습니다. Rebalance 페이지에서 백테스트를 실행하세요.</p>
                            <button
                                className="bench-go-backtest"
                                onClick={() => navigate('/rebalance')}
                            >
                                백테스트 실행 <ArrowRight size={14} />
                            </button>
                        </div>
                    ) : (
                        <div className="bench-metrics-grid">
                            {METRICS.map(m => {
                                const liveVal = data.live[m.key];
                                const btVal = data.backtest?.[m.key] ?? 0;
                                const delta = data.deltas?.[m.key] ?? 0;
                                const deltaClass = getDeltaClass(delta, m.higherIsBetter);

                                return (
                                    <div key={m.key} className="bench-metric-card">
                                        <div className="bench-metric-label">{m.label}</div>
                                        <div className="bench-metric-row">
                                            <div className="bench-metric-col">
                                                <span className="bench-col-label">Live</span>
                                                <span className="bench-col-value">{formatValue(liveVal, m.unit)}</span>
                                            </div>
                                            <div className="bench-metric-col">
                                                <span className="bench-col-label">Backtest</span>
                                                <span className="bench-col-value bench-bt-value">{formatValue(btVal, m.unit)}</span>
                                            </div>
                                            <div className="bench-metric-col">
                                                <span className="bench-col-label">Delta</span>
                                                <span className={`bench-col-value bench-delta ${deltaClass}`}>
                                                    {delta > 0 ? '+' : ''}{formatValue(delta, m.unit)}
                                                </span>
                                            </div>
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
