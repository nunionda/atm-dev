import { useState, useEffect } from 'react';
import type { PerformanceSummary, EquityPoint, TradeRecord } from '../lib/api';
import { fetchPerformanceSummary, fetchEquityCurve, fetchTradeHistory } from '../lib/api';
import { PerformanceMetrics } from '../components/performance/PerformanceMetrics';
import { EquityCurve } from '../components/performance/EquityCurve';
import { TradeLogTable } from '../components/performance/TradeLogTable';
import './Performance.css';

export function Performance() {
    const [summary, setSummary] = useState<PerformanceSummary | null>(null);
    const [equity, setEquity] = useState<EquityPoint[]>([]);
    const [trades, setTrades] = useState<TradeRecord[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        Promise.all([
            fetchPerformanceSummary(),
            fetchEquityCurve(),
            fetchTradeHistory(),
        ]).then(([s, e, t]) => {
            setSummary(s);
            setEquity(e);
            setTrades(t);
            setLoading(false);
        });
    }, []);

    return (
        <div className="performance-page container">
            <div className="perf-header">
                <h1 className="page-title">Performance Analytics</h1>
                <p className="page-subtitle">전략 성과 분석 및 거래 이력</p>
            </div>

            {loading && (
                <div className="loading-state">
                    <div className="badge-dot pulse-large"></div>
                    <p>성과 데이터를 불러오는 중...</p>
                </div>
            )}

            {!loading && summary && (
                <>
                    <PerformanceMetrics data={summary} />

                    <div className="equity-section glass-panel">
                        <h3 className="section-title">자산 곡선 & 드로다운</h3>
                        <EquityCurve data={equity} />
                    </div>

                    <TradeLogTable trades={trades} />
                </>
            )}
        </div>
    );
}
