/**
 * StrengthBar — extracted from SignalAnalysis.
 *
 * Phase D3 분할: dashboard/SignalAnalysis.tsx → dashboard/signal-analysis/StrengthBar.tsx
 */


export function StrengthBar({ strength, max = 4 }: { strength: number; max?: number }) {
    return (
        <div className="strength-bar-wrapper">
            <div className="strength-bar">
                {Array.from({ length: max }, (_, i) => (
                    <div
                        key={i}
                        className={`strength-seg ${i < strength ? 'filled' : ''}`}
                    />
                ))}
            </div>
            <span className="strength-label">{strength}/{max}</span>
        </div>
    );
}

