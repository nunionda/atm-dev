import './RiskGauge.css';

interface RiskGaugeProps {
    label: string;
    value: number;
    limit: number;
    unit?: string;
    invertColor?: boolean;
}

export function RiskGauge({ label, value, limit, unit = '%', invertColor = false }: RiskGaugeProps) {
    const absValue = Math.abs(value);
    const absLimit = Math.abs(limit);
    const ratio = absLimit > 0 ? (absValue / absLimit) * 100 : 0;
    const clampedRatio = Math.min(ratio, 100);

    let severity: 'safe' | 'caution' | 'danger';
    if (invertColor) {
        // For cash ratio: lower is worse
        severity = ratio > 150 ? 'safe' : ratio > 110 ? 'caution' : 'danger';
    } else {
        severity = ratio < 50 ? 'safe' : ratio < 80 ? 'caution' : 'danger';
    }

    return (
        <div className="risk-gauge">
            <div className="gauge-header">
                <span className="gauge-label">{label}</span>
                <span className={`gauge-value ${severity}`}>
                    {value >= 0 && !invertColor ? '' : ''}{value.toFixed(1)}{unit}
                </span>
            </div>
            <div className="gauge-bar-track">
                <div
                    className={`gauge-bar-fill ${severity}`}
                    style={{ width: `${clampedRatio}%` }}
                />
                <div className="gauge-limit-mark" style={{ left: '100%' }} />
            </div>
            <div className="gauge-footer">
                <span className="gauge-current">현재</span>
                <span className="gauge-limit-label">한도 {limit}{unit}</span>
            </div>
        </div>
    );
}
