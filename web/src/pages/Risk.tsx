import { useState, useEffect } from 'react';
import { Shield, AlertOctagon, Banknote, BarChart3, Repeat, Pause, Zap, ArrowRight } from 'lucide-react';
import type { RiskMetrics, SystemState } from '../lib/api';
import { MARKETS, fetchRiskMetrics, fetchSystemState, simStop, forceLiquidateAll } from '../lib/api';
import { useSSE } from '../hooks/useSSE';
import { useAppState } from '../contexts/AppStateContext';
import { RiskGauge } from '../components/risk/RiskGauge';
import { RiskGateStatus } from '../components/risk/RiskGateStatus';
import { DrawdownChart } from '../components/risk/DrawdownChart';
import { PositionRiskTable } from '../components/risk/PositionRiskTable';
import { RiskEventLog } from '../components/risk/RiskEventLog';
import './Risk.css';

export function Risk() {
    const { activeMarket, setActiveMarket, navigateToOperations } = useAppState();
    const [metrics, setMetrics] = useState<RiskMetrics | null>(null);
    const [systemState, setSystemState] = useState<SystemState | null>(null);
    const [showLiquidateModal, setShowLiquidateModal] = useState(false);
    const [isLiquidating, setIsLiquidating] = useState(false);
    const [liquidateResult, setLiquidateResult] = useState<string | null>(null);
    const sseData = useSSE<RiskMetrics>(`${activeMarket}:risk_metrics`, () => fetchRiskMetrics(activeMarket));

    useEffect(() => {
        fetchRiskMetrics(activeMarket).then(setMetrics).catch(() => {});
        fetchSystemState(activeMarket).then(setSystemState).catch(() => {});
    }, [activeMarket]);

    const displayMetrics = sseData || metrics;
    const positionCount = systemState?.position_count ?? 0;

    const handlePauseTrading = async () => {
        try {
            await simStop(activeMarket);
            setLiquidateResult('매매가 중단되었습니다.');
            fetchSystemState(activeMarket).then(setSystemState).catch(() => {});
        } catch {
            setLiquidateResult('매매 중단 실패');
        }
    };

    const handleForceLiquidate = async () => {
        setIsLiquidating(true);
        try {
            const result = await forceLiquidateAll(activeMarket);
            setLiquidateResult(`${result.positions_closed}개 포지션이 청산되었습니다.`);
            setShowLiquidateModal(false);
            fetchSystemState(activeMarket).then(setSystemState).catch(() => {});
        } catch {
            setLiquidateResult('강제 청산 실패');
        } finally {
            setIsLiquidating(false);
        }
    };

    return (
        <div className="risk-page container">
            <div className="risk-header">
                <div className="risk-header-text">
                    <h1 className="page-title">Risk Management</h1>
                    <p className="page-subtitle">실시간 리스크 지표 모니터링 및 제한 현황</p>
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

            {/* Emergency Actions */}
            <div className="emergency-actions glass-panel">
                <h3 className="section-title">
                    <AlertOctagon size={16} />
                    Emergency Controls
                </h3>
                <div className="emergency-btn-group">
                    <button className="emergency-btn pause-btn" onClick={handlePauseTrading}>
                        <Pause size={14} />
                        Pause Trading
                    </button>
                    <button
                        className="emergency-btn liquidate-btn"
                        onClick={() => setShowLiquidateModal(true)}
                    >
                        <Zap size={14} />
                        Force Liquidate All
                    </button>
                    <button
                        className="emergency-btn ops-btn"
                        onClick={() => navigateToOperations()}
                    >
                        <ArrowRight size={14} />
                        Go to Operations
                    </button>
                </div>
                {liquidateResult && (
                    <div className="emergency-result">{liquidateResult}</div>
                )}
            </div>

            {/* Force Liquidate Confirmation Modal */}
            {showLiquidateModal && (
                <div className="modal-overlay" onClick={() => !isLiquidating && setShowLiquidateModal(false)}>
                    <div className="modal-content glass-panel" onClick={e => e.stopPropagation()}>
                        <h3 className="modal-title">
                            <Zap size={18} />
                            Force Liquidate All Positions
                        </h3>
                        <p className="modal-message">
                            현재 <strong>{positionCount}개</strong> 포지션을 시장가로 즉시 청산합니다.
                            <br />이 작업은 되돌릴 수 없습니다.
                        </p>
                        <div className="modal-actions">
                            <button
                                className="modal-cancel"
                                onClick={() => setShowLiquidateModal(false)}
                                disabled={isLiquidating}
                            >
                                Cancel
                            </button>
                            <button
                                className="modal-confirm-danger"
                                onClick={handleForceLiquidate}
                                disabled={isLiquidating}
                            >
                                {isLiquidating ? 'Liquidating...' : 'Confirm Liquidate'}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {displayMetrics && (
                <>
                    {displayMetrics.is_trading_halted && (
                        <div className="halt-banner glass-panel">
                            <AlertOctagon size={20} />
                            <div>
                                <strong>매매 정지</strong>
                                <span>{displayMetrics.halt_reason || '리스크 한도 초과로 매매가 중단되었습니다.'}</span>
                            </div>
                        </div>
                    )}

                    <div className="risk-top-grid">
                        <div className="risk-gauges glass-panel">
                            <h3 className="section-title">
                                <Shield size={16} />
                                핵심 리스크 지표
                            </h3>
                            <RiskGauge
                                label="일일 손익"
                                value={displayMetrics.daily_pnl_pct}
                                limit={displayMetrics.daily_loss_limit}
                            />
                            <RiskGauge
                                label="최대 낙폭 (MDD)"
                                value={displayMetrics.mdd}
                                limit={displayMetrics.mdd_limit}
                            />
                            <RiskGauge
                                label="현금 비율"
                                value={displayMetrics.cash_ratio}
                                limit={displayMetrics.min_cash_ratio}
                                invertColor
                            />
                        </div>

                        <div className="risk-right-panel">
                            <RiskGateStatus
                                metrics={displayMetrics}
                                positionCount={systemState?.position_count ?? 0}
                                maxPositions={systemState?.max_positions ?? 10}
                            />

                            <div className="risk-counters glass-panel">
                                <h3 className="section-title">
                                    <BarChart3 size={16} />
                                    거래 한도
                                </h3>
                                <div className="counter-grid">
                                    <div className="counter-item">
                                        <Repeat size={18} className="counter-icon" />
                                        <div className="counter-info">
                                            <span className="counter-label">연속 손절</span>
                                            <span className={`counter-value ${displayMetrics.consecutive_stops >= displayMetrics.max_consecutive_stops - 1 ? 'danger' : ''}`}>
                                                {displayMetrics.consecutive_stops} / {displayMetrics.max_consecutive_stops}
                                            </span>
                                            <span className="counter-desc">
                                                {displayMetrics.max_consecutive_stops}회 연속 시 1일 매매 정지
                                            </span>
                                        </div>
                                    </div>
                                    <div className="counter-item">
                                        <Banknote size={18} className="counter-icon" />
                                        <div className="counter-info">
                                            <span className="counter-label">일일 거래대금</span>
                                            <span className="counter-value">
                                                ₩{displayMetrics.daily_trade_amount.toLocaleString()}
                                            </span>
                                            <span className="counter-desc">
                                                한도 ₩{displayMetrics.max_daily_trade_amount.toLocaleString()}
                                            </span>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <DrawdownChart market={activeMarket} mddLimit={displayMetrics.mdd_limit} />

                    <PositionRiskTable
                        market={activeMarket}
                        onPositionClick={(ticker) => navigateToOperations({ ticker })}
                    />

                    <div className="risk-events glass-panel">
                        <RiskEventLog market={activeMarket} />
                    </div>
                </>
            )}

            {!displayMetrics && (
                <div className="loading-state">
                    <div className="badge-dot pulse-large"></div>
                    <p>리스크 데이터를 불러오는 중...</p>
                </div>
            )}
        </div>
    );
}
