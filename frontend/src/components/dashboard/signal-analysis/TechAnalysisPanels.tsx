/**
 * TechAnalysisPanels — extracted from SignalAnalysis.
 *
 * Phase D3 분할: dashboard/SignalAnalysis.tsx → dashboard/signal-analysis/TechAnalysisPanels.tsx
 */

import { TrendingUp, Target, Compass, Activity, Gauge } from 'lucide-react';
import type { FuturesAnalysis } from '@lib/futuresEngine';
import { fmtIndicator, getRsiClass } from './_helpers';
import { StrengthBar } from './StrengthBar';

export function TechAnalysisPanels({ analysis, fmtPrice }: {
    analysis: FuturesAnalysis;
    fmtPrice: (v: number) => string;
}) {
    const { trend, momentum, volatility, levels, setup } = analysis;
    const biasStyle = BIAS_STYLE[setup.bias];

    return (
        <>
            {/* Setup Overview */}
            <div className="sa-entry-section glass-panel">
                <h3 className="sa-section-title">
                    <Compass size={16} />
                    Trade Setup
                </h3>

                <div className="sa-verdict-area">
                    <div className="sa-strength-row">
                        <span className="sa-label">Confidence</span>
                        <StrengthBar strength={setup.confidence} max={5} />
                    </div>
                    <div className={`sa-verdict ${biasStyle.className}`}>
                        <span>{biasStyle.icon}</span>
                        <span>{setup.biasLabel}</span>
                    </div>
                </div>

                <div className="ft-signals">
                    {setup.signals.map((s, i) => (
                        <span key={i} className="ft-signal-chip">{s}</span>
                    ))}
                </div>
            </div>

            {/* Trend Direction */}
            <div className="sa-entry-section glass-panel">
                <h3 className="sa-section-title">
                    <TrendingUp size={16} />
                    Trend Direction
                </h3>
                <div className="ft-indicator-grid">
                    <div className="ft-row">
                        <span className="ft-label">MA 배열</span>
                        <span className="ft-value">{trend.maAlignment}</span>
                    </div>
                    <div className="ft-row">
                        <span className="ft-label">ADX 추세강도</span>
                        <span className="ft-value">
                            {trend.adxStrength}
                            {trend.adxValue != null && <span className="ft-num"> ({fmtIndicator(trend.adxValue, 1)})</span>}
                        </span>
                    </div>
                    <div className="ft-row">
                        <span className="ft-label">방향지표 (DI)</span>
                        <span className="ft-value">{trend.diSignal}</span>
                    </div>
                    {trend.details.map((d, i) => (
                        <div key={i} className="ft-row">
                            <span className="ft-detail">{d}</span>
                        </div>
                    ))}
                </div>
            </div>

            {/* Momentum */}
            <div className="sa-entry-section glass-panel">
                <h3 className="sa-section-title">
                    <Activity size={16} />
                    Momentum
                </h3>
                <div className="ft-indicator-grid">
                    <div className="ft-row">
                        <span className="ft-label">RSI (14)</span>
                        <span className="ft-value">
                            <span className={`ft-rsi ${getRsiClass(momentum.rsiValue)}`}>
                                {fmtIndicator(momentum.rsiValue, 1)}
                            </span>
                            <span className="ft-sub">{momentum.rsiZone}</span>
                        </span>
                    </div>
                    <div className="ft-row">
                        <span className="ft-label">MACD</span>
                        <span className="ft-value">{momentum.macdStatus}</span>
                    </div>
                    <div className="ft-row">
                        <span className="ft-label">히스토그램</span>
                        <span className="ft-value">{momentum.macdHistogram}</span>
                    </div>
                    {momentum.macdValue != null && (
                        <div className="ft-row">
                            <span className="ft-detail">
                                MACD: {fmtIndicator(momentum.macdValue)} / Signal: {fmtIndicator(momentum.macdSignalValue)} / Hist: {fmtIndicator(momentum.macdDiffValue)}
                            </span>
                        </div>
                    )}
                </div>
            </div>

            {/* Volatility */}
            <div className="sa-entry-section glass-panel">
                <h3 className="sa-section-title">
                    <Gauge size={16} />
                    Volatility
                </h3>
                <div className="ft-indicator-grid">
                    <div className="ft-row">
                        <span className="ft-label">변동성 국면</span>
                        <span className={`ft-value ft-vol-${volatility.regime.toLowerCase()}`}>
                            {volatility.label}
                            {volatility.squeezeDetected && ' ⚠️'}
                        </span>
                    </div>
                    <div className="ft-row">
                        <span className="ft-label">BB %B</span>
                        <span className="ft-value">
                            {volatility.bbPercentB != null ? (
                                <>
                                    <span className="ft-num">{(volatility.bbPercentB * 100).toFixed(1)}%</span>
                                    <span className="ft-sub">
                                        {volatility.bbPercentB >= 0.8 ? '상단 근접' : volatility.bbPercentB <= 0.2 ? '하단 근접' : '중간'}
                                    </span>
                                </>
                            ) : 'N/A'}
                        </span>
                    </div>
                    <div className="ft-row">
                        <span className="ft-label">ATR (14)</span>
                        <span className="ft-value">
                            {volatility.atrValue != null ? (
                                <>
                                    <span className="ft-num">{fmtIndicator(volatility.atrValue)}</span>
                                    {volatility.atrPct != null && <span className="ft-sub">({volatility.atrPct.toFixed(2)}%)</span>}
                                </>
                            ) : 'N/A'}
                        </span>
                    </div>
                    {volatility.bbWidth != null && (
                        <div className="ft-row">
                            <span className="ft-detail">BB Width: {volatility.bbWidth.toFixed(2)}%</span>
                        </div>
                    )}
                </div>
            </div>

            {/* Key Levels */}
            <div className="sa-exit-section glass-panel">
                <h3 className="sa-section-title">
                    <Target size={16} />
                    Key Levels
                </h3>
                <div className="exit-levels">
                    {levels.nearestResistance != null && (
                        <div className="exit-item">
                            <span className="exit-label exit-loss">최근접 저항</span>
                            <span className="exit-value">{fmtPrice(levels.nearestResistance)}</span>
                        </div>
                    )}
                    {levels.pivot && (
                        <>
                            <div className="exit-item">
                                <span className="exit-label exit-loss">R2</span>
                                <span className="exit-value">{fmtPrice(levels.pivot.r2)}</span>
                            </div>
                            <div className="exit-item">
                                <span className="exit-label exit-loss">R1</span>
                                <span className="exit-value">{fmtPrice(levels.pivot.r1)}</span>
                            </div>
                            <div className="exit-item ft-pivot-pp">
                                <span className="exit-label">Pivot</span>
                                <span className="exit-value">{fmtPrice(levels.pivot.pp)}</span>
                            </div>
                            <div className="exit-item">
                                <span className="exit-label exit-profit">S1</span>
                                <span className="exit-value">{fmtPrice(levels.pivot.s1)}</span>
                            </div>
                            <div className="exit-item">
                                <span className="exit-label exit-profit">S2</span>
                                <span className="exit-value">{fmtPrice(levels.pivot.s2)}</span>
                            </div>
                        </>
                    )}
                    {levels.nearestSupport != null && (
                        <div className="exit-item">
                            <span className="exit-label exit-profit">최근접 지지</span>
                            <span className="exit-value">{fmtPrice(levels.nearestSupport)}</span>
                        </div>
                    )}
                    {levels.atrLevels && (
                        <>
                            <div className="exit-item ft-atr-sep">
                                <span className="exit-label">ATR +1</span>
                                <span className="exit-value">{fmtPrice(levels.atrLevels.plus1)}</span>
                            </div>
                            <div className="exit-item">
                                <span className="exit-label">ATR -1</span>
                                <span className="exit-value">{fmtPrice(levels.atrLevels.minus1)}</span>
                            </div>
                        </>
                    )}
                </div>
            </div>
        </>
    );
}

