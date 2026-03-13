import { useEffect, useCallback } from 'react';
import { useState } from 'react';
import { Wifi, WifiOff, RefreshCw } from 'lucide-react';
import type { PerformanceSummary, EquityPoint, TradeRecord } from '../lib/api';
import { fetchPerformanceSummary, fetchEquityCurve, fetchTradeHistory, MARKETS, getMarketConfig } from '../lib/api';
import { useSSE, useSSEStatus } from '../hooks/useSSE';
import { useAppState } from '../contexts/AppStateContext';
import { PerformanceMetrics } from '../components/performance/PerformanceMetrics';
import { BenchmarkComparison } from '../components/performance/BenchmarkComparison';
import { EquityCurve } from '../components/performance/EquityCurve';
import { TradeLogTable } from '../components/performance/TradeLogTable';
import './Performance.css';

export function Performance() {
    const { activeMarket, setActiveMarket } = useAppState();
    const { status: sseStatus } = useSSEStatus();

    // SSE 실시간 구독
    const sseSummary = useSSE<PerformanceSummary>(
        `${activeMarket}:performance`,
        () => fetchPerformanceSummary(activeMarket),
    );
    const sseEquity = useSSE<EquityPoint[]>(
        `${activeMarket}:equity_curve`,
        () => fetchEquityCurve(activeMarket),
    );

    // REST 초기 로딩
    const [summary, setSummary] = useState<PerformanceSummary | null>(null);
    const [equity, setEquity] = useState<EquityPoint[]>([]);
    const [trades, setTrades] = useState<TradeRecord[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(false);

    const loadData = useCallback(() => {
        setLoading(true);
        setError(false);
        setSummary(null);
        setEquity([]);
        setTrades([]);

        Promise.all([
            fetchPerformanceSummary(activeMarket),
            fetchEquityCurve(activeMarket),
            fetchTradeHistory(activeMarket),
        ])
            .then(([s, e, t]) => {
                setSummary(s);
                setEquity(e);
                setTrades(t);
            })
            .catch(() => setError(true))
            .finally(() => setLoading(false));
    }, [activeMarket]);

    useEffect(() => { loadData(); }, [loadData]);

    // SSE > REST 머지
    const displaySummary = sseSummary || summary;
    const displayEquity = (sseEquity && sseEquity.length > 0) ? sseEquity : equity;
    const mktConfig = getMarketConfig(activeMarket);

    return (
        <div className="performance-page container">
            {sseStatus !== 'connected' && (
                <div className={`sse-status-banner ${sseStatus === 'error' ? 'error' : 'warn'}`}>
                    {sseStatus === 'error' || sseStatus === 'disconnected'
                        ? <><WifiOff size={14} /> 서버 연결 끊김 — REST 폴링 모드</>
                        : <><Wifi size={14} /> 서버 연결 중...</>}
                </div>
            )}

            <div className="perf-header">
                <div className="perf-header-text">
                    <h1 className="page-title">Performance Analytics</h1>
                    <p className="page-subtitle">전략 성과 분석 및 거래 이력</p>
                </div>
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

            {loading && !displaySummary && (
                <div className="loading-state">
                    <div className="badge-dot pulse-large"></div>
                    <p>성과 데이터를 불러오는 중...</p>
                </div>
            )}

            {error && !displaySummary && !loading && (
                <div className="error-placeholder">
                    서버 연결 실패
                    <button className="retry-btn" onClick={loadData}>
                        <RefreshCw size={12} /> 재시도
                    </button>
                </div>
            )}

            {displaySummary && (
                <>
                    <PerformanceMetrics data={displaySummary} />

                    <BenchmarkComparison market={activeMarket} />

                    <div className="equity-section glass-panel">
                        <h3 className="section-title">자산 곡선 & 드로다운</h3>
                        <EquityCurve data={displayEquity} />
                    </div>

                    <TradeLogTable
                        trades={trades}
                        currencySymbol={mktConfig.currencySymbol}
                    />
                </>
            )}
        </div>
    );
}
