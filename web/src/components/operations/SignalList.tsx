import { useState, useEffect } from 'react';
import { Zap, ArrowUpCircle, ArrowDownCircle } from 'lucide-react';
import type { Signal } from '../../lib/api';
import { fetchSignals } from '../../lib/api';
import { useSSE } from '../../hooks/useSSE';
import './SignalList.css';

export function SignalList() {
    const [signals, setSignals] = useState<Signal[]>([]);
    const [loading, setLoading] = useState(true);
    const sseData = useSSE<Signal[]>('signals', fetchSignals);

    useEffect(() => {
        fetchSignals()
            .then(data => setSignals(data))
            .catch(() => {})
            .finally(() => setLoading(false));
    }, []);

    const displaySignals = sseData || signals;

    if (loading && !sseData) {
        return (
            <div className="signal-list-wrapper glass-panel">
                <h3 className="section-title"><Zap size={16} /> 오늘의 시그널</h3>
                <div className="loading-placeholder">로딩 중...</div>
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
                                <div className="signal-price">₩{sig.price.toLocaleString()}</div>
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
                                <div className="signal-price">₩{sig.price.toLocaleString()}</div>
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
