/**
 * ConfidenceBar — extracted from SignalAnalysis.
 *
 * Phase D3 분할: dashboard/SignalAnalysis.tsx → dashboard/signal-analysis/ConfidenceBar.tsx
 */


export function ConfidenceBar({ score, label }: { score: number; label: string }) {
    const getColor = (s: number) => {
        if (s >= 75) return '#22c55e';
        if (s >= 55) return '#84cc16';
        if (s >= 35) return '#eab308';
        return '#ef4444';
    };
    const color = getColor(score);

    return (
        <div className="confidence-bar-container">
            <div className="confidence-bar-meta">
                <span className="confidence-bar-score" style={{ color }}>{score}</span>
                <span className="confidence-bar-label-text" style={{ color, background: `${color}20`, border: `1px solid ${color}40` }}>{label}</span>
            </div>
            <div className="confidence-bar-track">
                <div className="confidence-bar-fill" style={{ width: `${score}%`, background: color }} />
            </div>
        </div>
    );
}

// --- Trend Overview Panel ---

