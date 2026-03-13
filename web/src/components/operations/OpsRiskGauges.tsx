import { useState, useEffect, useCallback } from 'react';
import { Shield, AlertOctagon, Repeat, Banknote, RefreshCw } from 'lucide-react';
import type { RiskMetrics, MarketId } from '../../lib/api';
import { fetchRiskMetrics, getMarketConfig } from '../../lib/api';
import { useSSE } from '../../hooks/useSSE';
import { RiskGauge } from '../risk/RiskGauge';
import './OpsRiskGauges.css';

interface OpsRiskGaugesProps {
    market: MarketId;
}

export function OpsRiskGauges({ market }: OpsRiskGaugesProps) {
    const [metrics, setMetrics] = useState<RiskMetrics | null>(null);
    const [error, setError] = useState(false);
    const sseData = useSSE<RiskMetrics>(`${market}:risk_metrics`, () => fetchRiskMetrics(market));

    const loadData = useCallback(() => {
        setError(false);
        setMetrics(null);
        fetchRiskMetrics(market).then(setMetrics).catch(() => setError(true));
    }, [market]);

    useEffect(() => { loadData(); }, [loadData]);

    const data = sseData || metrics;
    const { currencySymbol: sym, currency } = getMarketConfig(market);
    const divisor = currency === 'KRW' ? 1_000_000 : 1_000;
    const suffix = currency === 'KRW' ? 'M' : 'K';

    if (error && !data) {
        return (
            <div className="ops-risk-section">
                <div className="ops-risk-panel glass-panel">
                    <h3 className="section-title"><Shield size={16} /> 리스크 현황</h3>
                    <div className="error-placeholder">
                        서버 연결 실패
                        <button className="retry-btn" onClick={loadData}><RefreshCw size={12} /> 재시도</button>
                    </div>
                </div>
            </div>
        );
    }

    if (!data) return null;

    return (
        <div className="ops-risk-section">
            {data.is_trading_halted && (
                <div className="ops-halt-banner glass-panel">
                    <AlertOctagon size={18} />
                    <div className="ops-halt-text">
                        <strong>매매 정지</strong>
                        <span>{data.halt_reason || '리스크 한도 초과로 매매가 중단되었습니다.'}</span>
                    </div>
                </div>
            )}

            <div className="ops-risk-panel glass-panel">
                <h3 className="section-title">
                    <Shield size={16} />
                    리스크 현황
                </h3>
                <div className="ops-gauges-row">
                    <RiskGauge
                        label="일일 손익"
                        value={data.daily_pnl_pct}
                        limit={data.daily_loss_limit}
                    />
                    <RiskGauge
                        label="최대 낙폭 (MDD)"
                        value={data.mdd}
                        limit={data.mdd_limit}
                    />
                    <RiskGauge
                        label="현금 비율"
                        value={data.cash_ratio}
                        limit={data.min_cash_ratio}
                        invertColor
                    />
                </div>
                <div className="ops-risk-counters">
                    <div className="ops-counter">
                        <Repeat size={13} />
                        <span>연속 손절</span>
                        <span className={`ops-counter-value ${data.consecutive_stops >= data.max_consecutive_stops - 1 ? 'danger' : ''}`}>
                            {data.consecutive_stops} / {data.max_consecutive_stops}
                        </span>
                    </div>
                    <div className="ops-counter">
                        <Banknote size={13} />
                        <span>일일 거래</span>
                        <span className="ops-counter-value">
                            {sym}{(data.daily_trade_amount / divisor).toFixed(1)}{suffix} / {sym}{(data.max_daily_trade_amount / divisor).toFixed(0)}{suffix}
                        </span>
                    </div>
                </div>
            </div>
        </div>
    );
}
