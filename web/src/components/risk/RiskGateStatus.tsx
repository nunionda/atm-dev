import { CheckCircle2, XCircle, ShieldCheck } from 'lucide-react';
import type { RiskMetrics } from '../../lib/api';
import './RiskGateStatus.css';

interface RiskGateStatusProps {
    metrics: RiskMetrics;
    positionCount: number;
    maxPositions: number;
}

interface GateItem {
    id: string;
    label: string;
    pass: boolean;
    current: string;
    limit: string;
}

export function RiskGateStatus({ metrics, positionCount, maxPositions }: RiskGateStatusProps) {
    const gates: GateItem[] = [
        {
            id: 'RG1',
            label: '일일 손실',
            pass: metrics.daily_pnl_pct > metrics.daily_loss_limit,
            current: `${metrics.daily_pnl_pct.toFixed(1)}%`,
            limit: `${metrics.daily_loss_limit}%`,
        },
        {
            id: 'RG2',
            label: 'MDD',
            pass: metrics.mdd > metrics.mdd_limit,
            current: `${metrics.mdd.toFixed(1)}%`,
            limit: `${metrics.mdd_limit}%`,
        },
        {
            id: 'RG3',
            label: '보유 한도',
            pass: positionCount < maxPositions,
            current: `${positionCount}종목`,
            limit: `최대 ${maxPositions}`,
        },
        {
            id: 'RG4',
            label: '현금 비율',
            pass: metrics.cash_ratio >= metrics.min_cash_ratio,
            current: `${metrics.cash_ratio.toFixed(1)}%`,
            limit: `≥${metrics.min_cash_ratio}%`,
        },
    ];

    const allPass = gates.every(g => g.pass);

    return (
        <div className="risk-gate-panel glass-panel">
            <h3 className="section-title">
                <ShieldCheck size={16} />
                리스크 게이트 현황
                <span className={`gate-summary-badge ${allPass ? 'pass' : 'fail'}`}>
                    {allPass ? 'ALL PASS' : 'BLOCKED'}
                </span>
            </h3>
            <div className="gate-list">
                {gates.map(gate => (
                    <div key={gate.id} className={`gate-item ${gate.pass ? 'pass' : 'fail'}`}>
                        <div className="gate-icon">
                            {gate.pass
                                ? <CheckCircle2 size={16} />
                                : <XCircle size={16} />
                            }
                        </div>
                        <div className="gate-info">
                            <span className="gate-id">{gate.id}</span>
                            <span className="gate-label">{gate.label}</span>
                        </div>
                        <div className="gate-values">
                            <span className="gate-current">{gate.current}</span>
                            <span className="gate-limit">{gate.limit}</span>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}
