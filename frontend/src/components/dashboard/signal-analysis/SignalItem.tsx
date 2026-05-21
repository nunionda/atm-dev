/**
 * SignalItem — extracted from SignalAnalysis.
 *
 * Phase D3 분할: dashboard/SignalAnalysis.tsx → dashboard/signal-analysis/SignalItem.tsx
 */

import { CheckCircle, XCircle } from 'lucide-react';
import type { SignalCheck } from '@lib/signalEngine';

export function SignalItem({ check }: { check: SignalCheck }) {
    return (
        <div className={`signal-item ${check.passed ? 'passed' : 'failed'}`}>
            <div className="signal-item-header">
                {check.passed
                    ? <CheckCircle size={14} className="signal-icon pass" />
                    : <XCircle size={14} className="signal-icon fail" />}
                <span className="signal-id">{check.id}</span>
                <span className="signal-label">{check.label}</span>
            </div>
            <div className="signal-detail">{check.detail}</div>
        </div>
    );
}

