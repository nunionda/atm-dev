import { useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Wifi, WifiOff } from 'lucide-react';
import { SystemStatusBar } from '../components/operations/SystemStatusBar';
import { SimControlBar } from '../components/operations/SimControlBar';
import { PositionTable } from '../components/operations/PositionTable';
import { SignalList } from '../components/operations/SignalList';
import { OrderLog } from '../components/operations/OrderLog';
import { OpsRiskGauges } from '../components/operations/OpsRiskGauges';
import { OpsPerformanceCards } from '../components/operations/OpsPerformanceCards';
import { MiniEquityCurve } from '../components/operations/MiniEquityCurve';
import { MarketIntelligenceBar } from '../components/operations/MarketIntelligenceBar';
import { StrategyWeightPanel } from '../components/operations/StrategyWeightPanel';
import { IndexTrendTimeline } from '../components/operations/IndexTrendTimeline';
import { RiskEventLog } from '../components/risk/RiskEventLog';
import { ReplayHistory } from '../components/operations/ReplayHistory';
import { useSSEStatus } from '../hooks/useSSE';
import { useAppState } from '../contexts/AppStateContext';
import { MARKETS } from '../lib/api';
import './Operations.css';

export function Operations() {
    const { activeMarket, setActiveMarket, highlightedPosition, clearHighlight } = useAppState();
    const [searchParams, setSearchParams] = useSearchParams();
    const { status: sseStatus } = useSSEStatus();

    // Read highlight from URL params (for direct links like /operations?highlight=AAPL)
    useEffect(() => {
        const urlHighlight = searchParams.get('highlight');
        if (urlHighlight && !highlightedPosition) {
            // Set highlight from URL and clear the param
            clearHighlight();
        }
        if (urlHighlight) {
            // Clean up the URL param after reading
            setSearchParams({}, { replace: true });
        }
    }, [searchParams, setSearchParams, highlightedPosition, clearHighlight]);

    const highlightTicker = highlightedPosition?.ticker || searchParams.get('highlight') || null;

    return (
        <div className="operations-page container">
            {sseStatus !== 'connected' && (
                <div className={`sse-status-banner ${sseStatus === 'error' ? 'error' : 'warn'}`}>
                    {sseStatus === 'error' || sseStatus === 'disconnected'
                        ? <><WifiOff size={14} /> 서버 연결 끊김 — REST 폴링 모드</>
                        : <><Wifi size={14} /> 서버 연결 중...</>}
                </div>
            )}
            <SystemStatusBar market={activeMarket} />
            <SimControlBar market={activeMarket} />

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

            {/* 마켓 인텔리전스 — 3마켓 한눈에 비교 */}
            <MarketIntelligenceBar activeMarket={activeMarket} />

            <OpsRiskGauges market={activeMarket} />

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

            <OpsPerformanceCards market={activeMarket} />

            <MiniEquityCurve market={activeMarket} />

            <div className="operations-bottom-grid">
                <OrderLog market={activeMarket} />
                <div className="operations-bottom-side">
                    <div className="operations-risk-events glass-panel">
                        <RiskEventLog market={activeMarket} maxItems={15} />
                    </div>
                    {/* 추세 변경 이력 */}
                    <IndexTrendTimeline market={activeMarket} />
                </div>
            </div>

            <ReplayHistory market={activeMarket} />
        </div>
    );
}
