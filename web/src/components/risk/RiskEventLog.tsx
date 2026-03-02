import { useState, useEffect } from 'react';
import { AlertTriangle, Info, XOctagon, ShieldOff } from 'lucide-react';
import type { RiskEvent } from '../../lib/api';
import { fetchRiskEvents } from '../../lib/api';
import { useSSE } from '../../hooks/useSSE';
import './RiskEventLog.css';

const EVENT_ICON: Record<string, typeof Info> = {
    INFO: Info,
    WARNING: AlertTriangle,
    BREACH: XOctagon,
    HALT: ShieldOff,
};

const EVENT_COLOR: Record<string, string> = {
    INFO: '#60a5fa',
    WARNING: '#eab308',
    BREACH: '#ef4444',
    HALT: '#dc2626',
};

export function RiskEventLog() {
    const [events, setEvents] = useState<RiskEvent[]>([]);
    const [loading, setLoading] = useState(true);
    const sseData = useSSE<RiskEvent[]>('risk_events', fetchRiskEvents);

    useEffect(() => {
        fetchRiskEvents()
            .then(data => setEvents(data))
            .catch(() => {})
            .finally(() => setLoading(false));
    }, []);

    const displayEvents = sseData || events;

    if (loading && !sseData) {
        return (
            <div className="risk-event-log">
                <h3 className="section-title">리스크 이벤트</h3>
                <div className="loading-placeholder">로딩 중...</div>
            </div>
        );
    }

    return (
        <div className="risk-event-log">
            <h3 className="section-title">
                <AlertTriangle size={16} />
                리스크 이벤트
                <span className="count-badge">{displayEvents.length}</span>
            </h3>
            <div className="event-list">
                {[...displayEvents].reverse().map(evt => {
                    const Icon = EVENT_ICON[evt.type] || Info;
                    const color = EVENT_COLOR[evt.type] || '#60a5fa';
                    return (
                        <div key={evt.id} className="event-item" style={{ borderLeftColor: color }}>
                            <Icon size={14} style={{ color, flexShrink: 0 }} />
                            <div className="event-content">
                                <span className="event-message">{evt.message}</span>
                                {evt.value !== null && evt.limit !== null && (
                                    <span className="event-values">
                                        {evt.value.toFixed(1)}% / 한도 {evt.limit.toFixed(1)}%
                                    </span>
                                )}
                            </div>
                            <span className="event-time">
                                {new Date(evt.timestamp).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' })}
                            </span>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
