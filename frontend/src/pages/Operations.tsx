import { useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Wifi, WifiOff } from 'lucide-react';
import { SystemStatusBar } from '@components/operations/SystemStatusBar';
import { SimControlBar } from '@components/operations/SimControlBar';
import { PositionTable } from '@components/operations/PositionTable';
import { SignalList } from '@components/operations/SignalList';
import { OrderLog } from '@components/operations/OrderLog';
import { OpsRiskGauges } from '@components/operations/OpsRiskGauges';
import { OpsPerformanceCards } from '@components/operations/OpsPerformanceCards';
import { MiniEquityCurve } from '@components/operations/MiniEquityCurve';
import { MarketIntelligenceBar } from '@components/operations/MarketIntelligenceBar';
import { StrategyWeightPanel } from '@components/operations/StrategyWeightPanel';
import { IndexTrendTimeline } from '@components/operations/IndexTrendTimeline';
import { RiskEventLog } from '@components/risk/RiskEventLog';
import { ReplayHistory } from '@components/operations/ReplayHistory';
import { RebalanceHeader } from '@components/rebalance/RebalanceHeader';
import { RecommendationTable } from '@components/rebalance/RecommendationTable';
import { ScanSummary } from '@components/rebalance/ScanSummary';
import { BacktestSection } from '@components/rebalance/BacktestSection';
import { useSSEStatus } from '@hooks/useSSE';
import { useAppState } from '@contexts/AppStateContext';
import type { RebalanceResult, RebalanceStatus } from '@lib/api';
import {
    MARKETS,
    getMarketConfig,
    triggerRebalanceScan,
    fetchRebalanceRecommendations,
    fetchRebalanceStatus,
} from '@lib/api';
import './Operations.css';
import './Rebalance.css';

export function Operations() {
    const { activeMarket, setActiveMarket, highlightedPosition, navigateToOperations } = useAppState();
    const [searchParams, setSearchParams] = useSearchParams();
    const { status: sseStatus } = useSSEStatus();

    // Rebalance state
    const [rebalResult, setRebalResult] = useState<RebalanceResult | null>(null);
    const [rebalStatus, setRebalStatus] = useState<RebalanceStatus | null>(null);
    const [isScanning, setIsScanning] = useState(false);
    const [rebalError, setRebalError] = useState<string | null>(null);
    const marketConfig = getMarketConfig(activeMarket);

    // Read highlight from URL params (for direct links like /operations?highlight=AAPL)
    useEffect(() => {
        const urlHighlight = searchParams.get('highlight');
        if (urlHighlight) {
            if (!highlightedPosition || highlightedPosition.ticker !== urlHighlight) {
                navigateToOperations({ ticker: urlHighlight });
            }
            setSearchParams({}, { replace: true });
        }
    }, [searchParams, setSearchParams, highlightedPosition, navigateToOperations]);

    // Load cached rebalance recommendations and status on mount / market change
    useEffect(() => {
        let cancelled = false;
        (async () => {
            try {
                const [rec, st] = await Promise.all([
                    fetchRebalanceRecommendations(activeMarket),
                    fetchRebalanceStatus(activeMarket),
                ]);
                if (!cancelled) {
                    setRebalResult(rec);
                    setRebalStatus(st);
                    setRebalError(null);
                }
            } catch (err) {
                if (!cancelled) console.error('Failed to load rebalance data:', err);
            }
        })();
        return () => { cancelled = true; };
    }, [activeMarket]);

    const handleScan = useCallback(async () => {
        setIsScanning(true);
        setRebalError(null);
        try {
            const scanResult = await triggerRebalanceScan(activeMarket);
            setRebalResult(scanResult);
            const st = await fetchRebalanceStatus(activeMarket);
            setRebalStatus(st);
        } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : 'Scan failed';
            setRebalError(msg);
        } finally {
            setIsScanning(false);
        }
    }, [activeMarket]);

    const highlightTicker = highlightedPosition?.ticker || null;

    return (
        <div className="operations-page container">
            {sseStatus !== 'connected' && (
                <div className={`sse-status-banner ${sseStatus === 'error' ? 'error' : 'warn'}`}>
                    {sseStatus === 'error' || sseStatus === 'disconnected'
                        ? <><WifiOff size={14} /> 서버 연결 끊김 — REST 폴링 모드</>
                        : <><Wifi size={14} /> 서버 연결 중...</>}
                </div>
            )}
            {/* ═══ 헤더: 마켓 선택 → 시스템 상태 → 컨트롤 ═══ */}
            {/* H4.1: 마켓 탭을 컨트롤바 위로 이동 — 자본/포지션의 마켓 컨텍스트 명확화 */}
            <div className="operations-header">
                <h1 className="page-title">Trading Operations</h1>
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

            <SystemStatusBar market={activeMarket} />
            <SimControlBar market={activeMarket} />

            {/* ═══ Phase 0: 거시 분석 (시장 체제 + 지수 추세 변화) ═══ */}
            {/* H4.2: MarketIntelligenceBar + IndexTrendTimeline 한 묶음 — 시장 컨텍스트 일관성 */}
            <MarketIntelligenceBar activeMarket={activeMarket} />
            <IndexTrendTimeline market={activeMarket} />

            {/* ═══ Phase 4: 리스크 (게이지 + 이벤트) ═══ */}
            {/* H4.3: OpsRiskGauges + RiskEventLog 한 묶음 — 게이지가 빨개진 이유를 옆에서 즉시 확인 */}
            <div className="operations-risk-grid">
                <OpsRiskGauges market={activeMarket} />
                <div className="operations-risk-events glass-panel">
                    <RiskEventLog market={activeMarket} maxItems={15} />
                </div>
            </div>

            {/* ═══ 보유 + 시그널 (메인 운영 영역) ═══ */}
            <div className="operations-grid">
                <div className="operations-main">
                    <PositionTable market={activeMarket} highlightTicker={highlightTicker} />
                </div>
                <div className="operations-side">
                    {/* 전략 배분 상세 — 선택된 마켓 */}
                    <StrategyWeightPanel market={activeMarket} />
                    <SignalList market={activeMarket} />
                </div>
            </div>

            {/* ═══ 매수/매도 이력 ═══ */}
            <OrderLog market={activeMarket} />

            {/* ═══ 성과 ═══ */}
            <OpsPerformanceCards market={activeMarket} />
            <MiniEquityCurve market={activeMarket} />

            {/* ─── Universe Rebalancing ─── */}
            <div className="ops-section-divider" />
            <div className="rebalance-section-header">
                <h2 className="section-title">Universe Rebalancing</h2>
            </div>
            <RebalanceHeader
                status={rebalStatus}
                isScanning={isScanning}
                onScan={handleScan}
            />
            {rebalError && (
                <div className="rebalance-error glass-panel">{rebalError}</div>
            )}
            <ScanSummary result={rebalResult} />
            <div className="rebalance-grid">
                <RecommendationTable
                    title="BUY Recommendations"
                    icon="📈"
                    items={rebalResult?.buy ?? []}
                    type="BUY"
                    currencySymbol={marketConfig.currencySymbol}
                />
                <RecommendationTable
                    title="HOLD Positions"
                    icon="📊"
                    items={rebalResult?.hold ?? []}
                    type="HOLD"
                    currencySymbol={marketConfig.currencySymbol}
                />
            </div>
            <RecommendationTable
                title="SELL Recommendations"
                icon="📉"
                items={rebalResult?.sell ?? []}
                type="SELL"
                currencySymbol={marketConfig.currencySymbol}
            />

            {/* ─── History & Validation ─── */}
            {/* H4.4: ReplayHistory + BacktestSection 한 묶음 (검증/이력 카테고리) */}
            <div className="ops-section-divider" />
            <div className="rebalance-section-header">
                <h2 className="section-title">History &amp; Validation</h2>
            </div>
            <ReplayHistory market={activeMarket} />
            <BacktestSection activeMarket={activeMarket} />
        </div>
    );
}
