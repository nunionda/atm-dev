import { Wifi, WifiOff, Loader } from 'lucide-react';
import { useSSEStatus } from '../../hooks/useSSE';
import './ConnectionIndicator.css';

const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true';

export function ConnectionIndicator() {
    const { status } = useSSEStatus();

    if (USE_MOCK) {
        return (
            <div className="connection-indicator mock">
                <span className="conn-dot" />
                <span className="conn-label">Mock 모드</span>
            </div>
        );
    }

    const config = {
        connected: { icon: Wifi, label: '실시간 연결됨', className: 'connected' },
        connecting: { icon: Loader, label: '연결 중...', className: 'connecting' },
        error: { icon: WifiOff, label: '연결 오류', className: 'error' },
        disconnected: { icon: WifiOff, label: '연결 끊김', className: 'disconnected' },
    }[status];

    const Icon = config.icon;

    return (
        <div className={`connection-indicator ${config.className}`}>
            <Icon size={14} className={status === 'connecting' ? 'spin' : ''} />
            <span className="conn-label">{config.label}</span>
        </div>
    );
}
