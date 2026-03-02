import { useState, useEffect } from 'react';
import { Activity, Clock, Wallet, BarChart3 } from 'lucide-react';
import type { SystemState } from '../../lib/api';
import { fetchSystemState } from '../../lib/api';
import { useSSE } from '../../hooks/useSSE';
import { ConnectionIndicator } from './ConnectionIndicator';
import './SystemStatusBar.css';

const STATUS_COLORS: Record<string, string> = {
    RUNNING: '#22c55e',
    READY: '#3b82f6',
    INIT: '#eab308',
    STOPPING: '#f59e0b',
    STOPPED: '#6b7280',
    ERROR: '#ef4444',
};

const STATUS_LABELS: Record<string, string> = {
    RUNNING: '운영 중',
    READY: '대기',
    INIT: '초기화',
    STOPPING: '종료 중',
    STOPPED: '정지',
    ERROR: '오류',
};

const PHASE_LABELS: Record<string, string> = {
    PRE_MARKET: '장전',
    OPEN: '장중',
    CLOSED: '장후',
};

export function SystemStatusBar() {
    const [state, setState] = useState<SystemState | null>(null);
    const sseData = useSSE<SystemState>('system_state', fetchSystemState);

    useEffect(() => {
        fetchSystemState().then(setState).catch(() => {});
    }, []);

    const displayState = sseData || state;
    if (!displayState) return null;

    const statusColor = STATUS_COLORS[displayState.status] || '#6b7280';

    return (
        <div className="system-status-bar glass-panel">
            <div className="status-left">
                <div className="status-badge" style={{ borderColor: statusColor }}>
                    <span className="status-dot" style={{ backgroundColor: statusColor }} />
                    <span className="status-label">{STATUS_LABELS[displayState.status]}</span>
                </div>
                <span className="status-divider" />
                <div className="status-item">
                    <Clock size={14} />
                    <span>{PHASE_LABELS[displayState.market_phase]} 09:00–15:30</span>
                </div>
                <span className="status-divider" />
                <div className="status-item mode-badge" data-mode={displayState.mode}>
                    {displayState.mode === 'PAPER' ? '모의투자' : '실전투자'}
                </div>
                <span className="status-divider" />
                <ConnectionIndicator />
            </div>
            <div className="status-right">
                <div className="status-metric">
                    <Wallet size={14} />
                    <span className="metric-label">현금</span>
                    <span className="metric-value">₩{displayState.cash.toLocaleString()}</span>
                </div>
                <span className="status-divider" />
                <div className="status-metric">
                    <BarChart3 size={14} />
                    <span className="metric-label">총자산</span>
                    <span className="metric-value">₩{displayState.total_equity.toLocaleString()}</span>
                </div>
                <span className="status-divider" />
                <div className="status-metric">
                    <Activity size={14} />
                    <span className="metric-label">포지션</span>
                    <span className="metric-value">{displayState.position_count}/{displayState.max_positions}</span>
                </div>
                <span className="status-divider" />
                <div className="status-metric">
                    <span className="metric-label">일일 P&L</span>
                    <span className={`metric-value ${displayState.daily_pnl >= 0 ? 'text-success' : 'text-error'}`}>
                        {displayState.daily_pnl >= 0 ? '+' : ''}{displayState.daily_pnl_pct.toFixed(2)}%
                    </span>
                </div>
            </div>
        </div>
    );
}
