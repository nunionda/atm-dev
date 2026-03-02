import { useState, useEffect } from 'react';
import { Shield, AlertOctagon, Banknote, BarChart3, Repeat } from 'lucide-react';
import type { RiskMetrics } from '../lib/api';
import { fetchRiskMetrics } from '../lib/api';
import { useSSE } from '../hooks/useSSE';
import { RiskGauge } from '../components/risk/RiskGauge';
import { RiskEventLog } from '../components/risk/RiskEventLog';
import './Risk.css';

export function Risk() {
    const [metrics, setMetrics] = useState<RiskMetrics | null>(null);
    const sseData = useSSE<RiskMetrics>('risk_metrics', fetchRiskMetrics);

    useEffect(() => {
        fetchRiskMetrics().then(setMetrics).catch(() => {});
    }, []);

    const displayMetrics = sseData || metrics;

    return (
        <div className="risk-page container">
            <div className="risk-header">
                <h1 className="page-title">Risk Management</h1>
                <p className="page-subtitle">실시간 리스크 지표 모니터링 및 제한 현황</p>
            </div>

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

                    <div className="risk-grid">
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

                        <div className="risk-events glass-panel">
                            <RiskEventLog />
                        </div>
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
