import { useState, useEffect, useCallback } from 'react';
import { Zap, ArrowUpCircle, ArrowDownCircle, RefreshCw } from 'lucide-react';
import type { Signal, MarketId } from '../../lib/api';
import { fetchSignals, getMarketConfig } from '../../lib/api';
import { useSSE } from '../../hooks/useSSE';
import './SignalList.css';

interface Props {
    market: MarketId;
}

export function SignalList({ market }: Props) {
    const [signals, setSignals] = useState<Signal[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(false);
    const sseData = useSSE<Signal[]>(`${market}:signals`, () => fetchSignals(market));

    const loadData = useCallback(() => {
        setLoading(true);
        setError(false);
        setSignals([]);
        fetchSignals(market)
            .then(data => setSignals(data))
            .catch(() => setError(true))
            .finally(() => setLoading(false));
    }, [market]);

    useEffect(() => { loadData(); }, [loadData]);

    const displaySignals = sseData || signals;
    const sym = getMarketConfig(market).currencySymbol;

    if (loading && !sseData) {
        return (
            <div className="signal-list-wrapper glass-panel">
                <h3 className="section-title"><Zap size={16} /> 오늘의 시그널</h3>
                <div className="loading-placeholder">로딩 중...</div>
            </div>
        );
    }

    if (error && !sseData && displaySignals.length === 0) {
        return (
            <div className="signal-list-wrapper glass-panel">
                <h3 className="section-title"><Zap size={16} /> 오늘의 시그널</h3>
                <div className="error-placeholder">
                    서버 연결 실패
                    <button className="retry-btn" onClick={loadData}><RefreshCw size={12} /> 재시도</button>
                </div>
            </div>
        );
    }

    const buySignals = displaySignals.filter(s => s.type === 'BUY');
    const sellSignals = displaySignals.filter(s => s.type === 'SELL');

    return (
        <div className="signal-list-wrapper glass-panel">
            <div className="section-header">
                <h3 className="section-title">
                    <Zap size={16} />
                    오늘의 시그널
                    <span className="count-badge">{displaySignals.length}</span>
                </h3>
            </div>
            <div className="signal-groups">
                {buySignals.length > 0 && (
                    <div className="signal-group">
                        <div className="signal-group-label buy-label">
                            <ArrowUpCircle size={14} /> 매수 시그널
                        </div>
                        {buySignals.map(sig => (
                            <div key={sig.id} className="signal-card buy-card">
                                <div className="signal-top">
                                    <span className="signal-stock">{sig.stock_name}</span>
                                    <span className="signal-code">{sig.stock_code}</span>
                                    <span className="signal-strength">
                                        강도 {sig.strength}
                                    </span>
                                </div>
                                <div className="signal-price">{sym}{sig.price.toLocaleString()}</div>
                                <div className="signal-reason">{sig.reason}</div>
                                <div className="signal-time">
                                    {new Date(sig.detected_at).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' })}
                                </div>
                            </div>
                        ))}
                    </div>
                )}
                {sellSignals.length > 0 && (
                    <div className="signal-group">
                        <div className="signal-group-label sell-label">
                            <ArrowDownCircle size={14} /> 매도 시그널
                        </div>
                        {sellSignals.map(sig => (
                            <div key={sig.id} className="signal-card sell-card">
                                <div className="signal-top">
                                    <span className="signal-stock">{sig.stock_name}</span>
                                    <span className="signal-code">{sig.stock_code}</span>
                                    <span className="signal-strength">
                                        강도 {sig.strength}
                                    </span>
                                </div>
                                <div className="signal-price">{sym}{sig.price.toLocaleString()}</div>
                                <div className="signal-reason">{sig.reason}</div>
                                <div className="signal-time">
                                    {new Date(sig.detected_at).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' })}
                                </div>
                            </div>
                        ))}
                    </div>
                )}
                {displaySignals.length === 0 && (
                    <div className="no-signals">오늘 감지된 시그널이 없습니다</div>
                )}
            </div>
        </div>
    );
}
