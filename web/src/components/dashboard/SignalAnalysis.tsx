import { useState, useEffect } from 'react';
import { TrendingUp, TrendingDown, CheckCircle, XCircle, Target, LogOut, Compass, Activity, Gauge, ChevronDown, BarChart2, RefreshCw } from 'lucide-react';
import type { AnalyticsData } from '../../lib/api';
import {
    analyzeEntrySignals,
    calculateExitLevels,
    computeVolumeMA,
    type SignalCheck,
    type Verdict,
    type TrendFilter,
    type SMCAnalysis,
} from '../../lib/signalEngine';
import { analyzeFutures, computeATREntry, type FuturesAnalysis, type SetupBias, type ATREntryCalc } from '../../lib/futuresEngine';
import './SignalAnalysis.css';

interface SignalAnalysisProps {
    data: AnalyticsData[];
    ticker: string;
    currencySymbol: string;
    isKorean: boolean;
    onSelectTicker?: (symbol: string) => void;
    refetch?: () => void;
}

const INDEX_BUTTONS = [
    { label: 'S&P 500', symbol: '^GSPC' },
    { label: 'NASDAQ', symbol: '^IXIC' },
    { label: 'KOSPI', symbol: '^KS11' },
    { label: 'KOSPI 200', symbol: '^KS200' },
];

const VERDICT_STYLE: Record<Verdict, { className: string; icon: string }> = {
    BUY_SUITABLE: { className: 'verdict-buy', icon: '🟢' },
    WATCH: { className: 'verdict-watch', icon: '🟡' },
    NOT_SUITABLE: { className: 'verdict-avoid', icon: '🔴' },
};

const BIAS_STYLE: Record<SetupBias, { className: string; icon: string }> = {
    LONG: { className: 'verdict-buy', icon: '🟢' },
    NEUTRAL: { className: 'verdict-watch', icon: '🟡' },
    SHORT: { className: 'verdict-avoid', icon: '🔴' },
};

function SignalItem({ check }: { check: SignalCheck }) {
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

function StrengthBar({ strength, max = 4 }: { strength: number; max?: number }) {
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

function fmtIndicator(v: number | null | undefined, decimals = 2): string {
    if (v === null || v === undefined) return 'N/A';
    return v.toLocaleString(undefined, { maximumFractionDigits: decimals });
}

// --- ATR Entry Panel ---

function ATREntryPanel({ calc, fmtPrice }: { calc: ATREntryCalc; fmtPrice: (v: number) => string }) {
    const [expanded, setExpanded] = useState(false);
    const dirClass = calc.direction === 'LONG' ? 'atr-long' : calc.direction === 'SHORT' ? 'atr-short' : 'atr-wait';

    return (
        <div className={`sa-entry-section glass-panel atr-calc-card ${expanded ? 'expanded' : ''}`} onClick={() => setExpanded(e => !e)}>
            <h3 className="sa-section-title">
                <Target size={16} />
                ATR Entry Calculator
                <ChevronDown size={14} className={`atr-calc-chevron ${expanded ? 'open' : ''}`} />
            </h3>

            {/* ATR 현황 + 방향 배지 (항상 표시) */}
            <div className="atr-calc-header">
                <div className="atr-calc-atr-info">
                    <span className="ft-num">ATR (14): {fmtIndicator(calc.atr)}</span>
                    <span className="ft-sub">({calc.atrPct.toFixed(2)}%)</span>
                </div>
                <span className={`atr-direction-badge ${dirClass}`}>
                    {calc.direction === 'LONG' ? '▲ LONG' : calc.direction === 'SHORT' ? '▼ SHORT' : '◆ WAIT'}
                </span>
            </div>

            {/* 판단 근거 (항상 표시) */}
            <div className="ft-signals">
                {calc.reasons.map((r, i) => (
                    <span key={i} className="ft-signal-chip">{r}</span>
                ))}
            </div>

            {/* 상세 내용 (확장 시에만 표시) */}
            <div className="atr-calc-details" onClick={e => e.stopPropagation()}>
                {/* 진입 조건 */}
                <div className="atr-calc-group">
                    <div className="atr-calc-group-title">진입 조건</div>
                    <div className="atr-calc-row">
                        <span className="atr-calc-label">브레이크아웃</span>
                        <span className={`atr-calc-value ${calc.breakoutValid ? 'atr-long' : 'atr-muted'}`}>
                            {calc.breakoutValid ? '✓ 유효' : '✗ 미충족'}
                            <span className="ft-sub"> ({fmtIndicator(calc.breakoutDelta)} {calc.breakoutValid ? '>' : '≤'} {fmtIndicator(calc.breakoutThreshold)})</span>
                        </span>
                    </div>
                </div>

                {/* 추세추종 진입가 */}
                <div className="atr-calc-group">
                    <div className="atr-calc-group-title">추세추종 진입가</div>
                    <div className="atr-calc-row">
                        <span className="atr-calc-label atr-long">Long 진입</span>
                        <span className="atr-calc-value">{fmtPrice(calc.trendLongEntry)} <span className="ft-sub">(1.5x ATR)</span></span>
                    </div>
                    <div className="atr-calc-row">
                        <span className="atr-calc-label atr-long">Long 강력</span>
                        <span className="atr-calc-value">{fmtPrice(calc.trendLongStrong)} <span className="ft-sub">(2.0x ATR)</span></span>
                    </div>
                    <div className="atr-calc-row">
                        <span className="atr-calc-label atr-short">Short 진입</span>
                        <span className="atr-calc-value">{fmtPrice(calc.trendShortEntry)} <span className="ft-sub">(1.5x ATR)</span></span>
                    </div>
                    <div className="atr-calc-row">
                        <span className="atr-calc-label atr-short">Short 강력</span>
                        <span className="atr-calc-value">{fmtPrice(calc.trendShortStrong)} <span className="ft-sub">(2.0x ATR)</span></span>
                    </div>
                </div>

                {/* ATR 밴드 */}
                <div className="atr-calc-group">
                    <div className="atr-calc-group-title">ATR 밴드 (2x)</div>
                    <div className="atr-calc-row">
                        <span className="atr-calc-label">상단</span>
                        <span className="atr-calc-value">{fmtPrice(calc.upperBand)}</span>
                    </div>
                    <div className="atr-calc-row">
                        <span className="atr-calc-label">하단</span>
                        <span className="atr-calc-value">{fmtPrice(calc.lowerBand)}</span>
                    </div>
                </div>

                {/* 트레일링 스톱 */}
                <div className="atr-calc-group">
                    <div className="atr-calc-group-title">손절 (트레일링 스톱)</div>
                    <div className="atr-calc-row">
                        <span className="atr-calc-label atr-short">Long SL</span>
                        <span className="atr-calc-value">{fmtPrice(calc.longStop)} <span className="ft-sub">(1.5x)</span></span>
                    </div>
                    <div className="atr-calc-row">
                        <span className="atr-calc-label atr-short">Long SL (Wide)</span>
                        <span className="atr-calc-value">{fmtPrice(calc.longStopWide)} <span className="ft-sub">(2.0x)</span></span>
                    </div>
                    <div className="atr-calc-row">
                        <span className="atr-calc-label atr-long">Short SL</span>
                        <span className="atr-calc-value">{fmtPrice(calc.shortStop)} <span className="ft-sub">(1.5x)</span></span>
                    </div>
                    <div className="atr-calc-row">
                        <span className="atr-calc-label atr-long">Short SL (Wide)</span>
                        <span className="atr-calc-value">{fmtPrice(calc.shortStopWide)} <span className="ft-sub">(2.0x)</span></span>
                    </div>
                </div>

                {/* 샹들리에 청산 */}
                <div className="atr-calc-group">
                    <div className="atr-calc-group-title">샹들리에 청산 (3x ATR)</div>
                    <div className="atr-calc-row">
                        <span className="atr-calc-label atr-long">Long Exit</span>
                        <span className="atr-calc-value">
                            {fmtPrice(calc.chandelierLongExit)}
                            <span className="ft-sub"> (최고 {fmtPrice(calc.chandelierHighest)} - 3ATR)</span>
                        </span>
                    </div>
                    <div className="atr-calc-row">
                        <span className="atr-calc-label atr-short">Short Exit</span>
                        <span className="atr-calc-value">
                            {fmtPrice(calc.chandelierShortExit)}
                            <span className="ft-sub"> (최저 {fmtPrice(calc.chandelierLowest)} + 3ATR)</span>
                        </span>
                    </div>
                </div>

                {/* 동적 ATR 배수 (ADX 기반) */}
                <div className="atr-calc-group">
                    <div className="atr-calc-group-title">동적 손절 (ADX 기반)</div>
                    <div className="atr-calc-row">
                        <span className="atr-calc-label">ADX / 배수</span>
                        <span className="atr-calc-value">
                            {calc.adxValue != null ? fmtIndicator(calc.adxValue, 1) : 'N/A'}
                            <span className="ft-sub"> → {calc.dynamicMultiplier}x ({calc.dynamicMultiplier === 2.0 ? '횡보 — 넓은 손절' : '추세 — 타이트'})</span>
                        </span>
                    </div>
                    <div className="atr-calc-row">
                        <span className="atr-calc-label atr-short">Long 동적 SL</span>
                        <span className="atr-calc-value">{fmtPrice(calc.dynamicLongStop)} <span className="ft-sub">({calc.dynamicMultiplier}x ATR)</span></span>
                    </div>
                    <div className="atr-calc-row">
                        <span className="atr-calc-label atr-long">Short 동적 SL</span>
                        <span className="atr-calc-value">{fmtPrice(calc.dynamicShortStop)} <span className="ft-sub">({calc.dynamicMultiplier}x ATR)</span></span>
                    </div>
                </div>

                {/* 거래량 가중 ATR */}
                <div className="atr-calc-group">
                    <div className="atr-calc-group-title">통합 ATR (거래량 가중)</div>
                    <div className="atr-calc-row">
                        <span className="atr-calc-label">Volume ROC</span>
                        <span className={`atr-calc-value ${calc.volumeRoc != null && calc.volumeRoc > 0 ? 'atr-long' : calc.volumeRoc != null && calc.volumeRoc < 0 ? 'atr-short' : ''}`}>
                            {calc.volumeRoc != null ? `${calc.volumeRoc >= 0 ? '+' : ''}${(calc.volumeRoc * 100).toFixed(1)}%` : 'N/A'}
                        </span>
                    </div>
                    <div className="atr-calc-row">
                        <span className="atr-calc-label">통합 ATR</span>
                        <span className="atr-calc-value">
                            {calc.integratedATR != null ? fmtIndicator(calc.integratedATR) : 'N/A'}
                            {calc.integratedATR != null && <span className="ft-sub"> (기본 {fmtIndicator(calc.atr)})</span>}
                        </span>
                    </div>
                    <div className="atr-calc-row">
                        <span className="atr-calc-label">통합 브레이크아웃</span>
                        <span className={`atr-calc-value ${calc.integratedBreakoutValid ? 'atr-long' : 'atr-muted'}`}>
                            {calc.integratedBreakoutValid == null ? 'N/A' : calc.integratedBreakoutValid ? '✓ 유효' : '✗ 미충족'}
                        </span>
                    </div>
                </div>

                {/* 피라미딩 간격 */}
                <div className="atr-calc-group">
                    <div className="atr-calc-group-title">피라미딩 간격 (0.5x ATR)</div>
                    {calc.pyramidLong.map((price, i) => (
                        <div key={`pl${i}`} className="atr-calc-row" style={{ opacity: 1 - i * 0.2 }}>
                            <span className="atr-calc-label atr-long">Long #{i + 1}</span>
                            <span className="atr-calc-value">
                                {fmtPrice(price)}
                                <span className="ft-sub"> {i === 0 ? '(진입)' : `(+${(i * 0.5).toFixed(1)} ATR)`}</span>
                            </span>
                        </div>
                    ))}
                    {calc.pyramidShort.map((price, i) => (
                        <div key={`ps${i}`} className="atr-calc-row" style={{ opacity: 1 - i * 0.2 }}>
                            <span className="atr-calc-label atr-short">Short #{i + 1}</span>
                            <span className="atr-calc-value">
                                {fmtPrice(price)}
                                <span className="ft-sub"> {i === 0 ? '(진입)' : `(-${(i * 0.5).toFixed(1)} ATR)`}</span>
                            </span>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}

// --- Technical Analysis Panels (on-demand) ---

function TechAnalysisPanels({ analysis, fmtPrice }: {
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

function getRsiClass(rsi: number | null): string {
    if (rsi == null) return '';
    if (rsi >= 70) return 'rsi-overbought';
    if (rsi <= 30) return 'rsi-oversold';
    return '';
}

// --- Confidence Bar ---

function ConfidenceBar({ score, label }: { score: number; label: string }) {
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

function TrendOverviewPanel({ trend }: { trend: TrendFilter }) {
    const biasColor = trend.bias.includes('BULL') ? '#22c55e' : trend.bias.includes('BEAR') ? '#ef4444' : '#94a3b8';

    return (
        <div className="sa-entry-section glass-panel">
            <h3 className="sa-section-title">
                <TrendingUp size={16} />
                Trend Overview
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
                        {trend.adxValue != null && <span className="ft-num"> ({trend.adxValue.toFixed(1)})</span>}
                    </span>
                </div>
                <div className="ft-row">
                    <span className="ft-label">방향지표 (DI)</span>
                    <span className="ft-value">{trend.diSignal}</span>
                </div>
                {trend.pctFrom200 != null && (
                    <div className="ft-row">
                        <span className="ft-label">200MA 대비</span>
                        <span className="ft-value" style={{ color: trend.pctFrom200 >= 0 ? '#22c55e' : '#ef4444' }}>
                            {trend.pctFrom200 >= 0 ? '+' : ''}{trend.pctFrom200.toFixed(1)}%
                        </span>
                    </div>
                )}
                {trend.pctFrom50 != null && (
                    <div className="ft-row">
                        <span className="ft-label">50MA 대비</span>
                        <span className="ft-value" style={{ color: trend.pctFrom50 >= 0 ? '#22c55e' : '#ef4444' }}>
                            {trend.pctFrom50 >= 0 ? '+' : ''}{trend.pctFrom50.toFixed(1)}%
                        </span>
                    </div>
                )}
            </div>
            <div className="trend-bias-badge" style={{ color: biasColor, background: `${biasColor}1a`, border: `1px solid ${biasColor}40` }}>
                {trend.biasLabel}
            </div>
        </div>
    );
}

// --- SMC Panel ---

function SMCPanel({ smc, fmtPrice }: { smc: SMCAnalysis; fmtPrice: (v: number) => string }) {
    const hasData = smc.markers.length > 0 || smc.orderBlocks.length > 0 || smc.fvgs.length > 0;
    if (!hasData) return null;

    return (
        <div className="sa-entry-section glass-panel">
            <h3 className="sa-section-title">
                <Compass size={16} />
                Smart Money Concepts
            </h3>

            {smc.markers.length > 0 && (
                <div className="smc-section">
                    <div className="sa-group-label">Market Structure</div>
                    <div className="smc-marker-list">
                        {smc.markers.map((m, i) => (
                            <div key={i} className="smc-marker-item">
                                <span className={`smc-marker-badge ${m.type.includes('BULL') ? 'bull' : 'bear'}`}>
                                    {m.type}
                                </span>
                                <span className="ft-sub">{m.barsAgo === 0 ? '현재 봉' : `${m.barsAgo}봉 전`}</span>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {smc.orderBlocks.length > 0 && (
                <div className="smc-section">
                    <div className="sa-group-label">Order Block</div>
                    {smc.orderBlocks.slice(0, 3).map((ob, i) => (
                        <div key={i} className="smc-zone-item">
                            <span className="smc-zone-label">OB #{i + 1}</span>
                            <span className="smc-zone-prices">
                                {fmtPrice(ob.bottom)} ~ {fmtPrice(ob.top)}
                                <span className={`smc-relation-badge ${ob.relation.toLowerCase()}`}>{ob.relation}</span>
                            </span>
                        </div>
                    ))}
                </div>
            )}

            {smc.fvgs.length > 0 && (
                <div className="smc-section">
                    <div className="sa-group-label">Fair Value Gap</div>
                    {smc.fvgs.slice(0, 3).map((fvg, i) => (
                        <div key={i} className="smc-zone-item">
                            <span className="smc-zone-label">{fvg.type} FVG</span>
                            <span className="smc-zone-prices">
                                {fmtPrice(fvg.bottom)} ~ {fmtPrice(fvg.top)}
                                <span className={`smc-relation-badge ${fvg.relation.toLowerCase()}`}>{fvg.relation}</span>
                            </span>
                        </div>
                    ))}
                </div>
            )}

            <div className={`smc-bias-badge ${smc.smcBias.toLowerCase()}`}>
                SMC: {smc.smcLabel}
            </div>
        </div>
    );
}

// --- Main Component ---

export function SignalAnalysis({ data, ticker, currencySymbol, isKorean, onSelectTicker, refetch }: SignalAnalysisProps) {
    const isIndex = ticker.startsWith('^');
    const current = data.length > 0 ? data[data.length - 1] : null;
    const previous = data.length > 1 ? data[data.length - 2] : null;

    // On-demand technical analysis state
    const [techAnalysis, setTechAnalysis] = useState<FuturesAnalysis | null>(null);
    const [atrEntry, setAtrEntry] = useState<ATREntryCalc | null>(null);
    const [isAnalyzed, setIsAnalyzed] = useState(false);

    // Clear analysis when ticker changes
    useEffect(() => {
        setTechAnalysis(null);
        setAtrEntry(null);
        setIsAnalyzed(false);
    }, [ticker]);

    const handleAnalyze = () => {
        const result = analyzeFutures(data);
        const atr = computeATREntry(data);
        setTechAnalysis(result);
        setAtrEntry(atr);
        setIsAnalyzed(true);
    };

    const handleRefreshAnalyze = () => {
        setTechAnalysis(null);
        setAtrEntry(null);
        setIsAnalyzed(false);
        if (refetch) refetch();
    };

    // Price info
    const priceChange = current && previous
        ? (current.close || 0) - (previous.close || 0)
        : 0;
    const priceChangePct = current && previous && previous.close
        ? (priceChange / previous.close) * 100
        : 0;
    const fmtPrice = (v: number) => `${currencySymbol}${v.toLocaleString(undefined, { maximumFractionDigits: isKorean ? 0 : 2 })}`;

    // Stock analysis (auto-computed for non-index tickers)
    const volumeMA = computeVolumeMA(data, 20);
    const analysis = !isIndex && current && previous
        ? analyzeEntrySignals(current, previous, volumeMA, data)
        : null;
    const exitLevels = !isIndex && current && previous && current.close
        ? calculateExitLevels(current.close, current, previous, data)
        : null;

    const verdictStyle = analysis ? VERDICT_STYLE[analysis.verdict] : null;

    return (
        <div className="signal-analysis">
            {/* Price Card */}
            {current && (
                <div className="sa-price-card glass-panel">
                    <div className="sa-price-header">Last Price</div>
                    <div className="sa-price-value">{fmtPrice(current.close || 0)}</div>
                    <div className={`sa-price-change ${priceChange >= 0 ? 'up' : 'down'}`}>
                        {priceChange >= 0 ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
                        {priceChange >= 0 ? '+' : ''}{isKorean ? priceChange.toLocaleString() : priceChange.toFixed(2)} ({priceChangePct.toFixed(2)}%)
                    </div>
                </div>
            )}

            {/* Index Quick Select */}
            {isIndex && onSelectTicker && (
                <div className="index-quick-btns">
                    {INDEX_BUTTONS.map(idx => (
                        <button
                            key={idx.symbol}
                            className={`index-btn ${ticker === idx.symbol ? 'active' : ''}`}
                            onClick={() => onSelectTicker(idx.symbol)}
                        >
                            {idx.label}
                        </button>
                    ))}
                </div>
            )}

            {/* Technical Analysis Trigger */}
            <div className="sa-analyze-section glass-panel">
                <div className="sa-analyze-header">
                    <h3 className="sa-section-title">
                        <Activity size={16} />
                        Technical Analysis
                    </h3>
                    {isAnalyzed && (
                        <span className="sa-analyze-badge">Analyzed</span>
                    )}
                </div>
                <div className="sa-analyze-actions">
                    <button
                        className={`sa-analyze-btn ${isAnalyzed ? 'analyzed' : ''}`}
                        onClick={handleAnalyze}
                    >
                        <BarChart2 size={16} />
                        {isAnalyzed ? 'Re-analyze' : 'Analyze'}
                    </button>
                    {refetch && (
                        <button
                            className="sa-refresh-btn"
                            onClick={handleRefreshAnalyze}
                            title="Refresh data from server"
                        >
                            <RefreshCw size={14} />
                        </button>
                    )}
                </div>
                {!isAnalyzed && (
                    <p className="sa-analyze-hint">
                        Trend, Momentum, Volatility, Key Levels 분석을 실행합니다.
                    </p>
                )}
            </div>

            {/* On-demand: ATR Entry Calculator */}
            {isAnalyzed && atrEntry && (
                <ATREntryPanel calc={atrEntry} fmtPrice={fmtPrice} />
            )}

            {/* On-demand: Technical Analysis Panels */}
            {isAnalyzed && techAnalysis && (
                <TechAnalysisPanels analysis={techAnalysis} fmtPrice={fmtPrice} />
            )}

            {/* Trend Overview (auto-computed for stocks) */}
            {!isIndex && analysis?.trendFilter && (
                <TrendOverviewPanel trend={analysis.trendFilter} />
            )}

            {/* SMC Panel (auto-computed for stocks) */}
            {!isIndex && analysis?.smcAnalysis && (
                <SMCPanel smc={analysis.smcAnalysis} fmtPrice={fmtPrice} />
            )}

            {/* Stock Signal Analysis (auto-computed, enhanced) */}
            {!isIndex && analysis && (
                <div className="sa-entry-section glass-panel">
                    <h3 className="sa-section-title">
                        <Target size={16} />
                        Entry Signal Analysis
                    </h3>

                    {/* Confidence Score */}
                    <ConfidenceBar score={analysis.confidenceScore} label={analysis.confidenceLabel} />

                    {/* Strength + Verdict */}
                    <div className="sa-verdict-area">
                        <div className="sa-strength-row">
                            <span className="sa-label">Signal Strength</span>
                            <StrengthBar strength={analysis.strength} max={8} />
                        </div>
                        {verdictStyle && (
                            <div className={`sa-verdict ${verdictStyle.className}`}>
                                <span>{verdictStyle.icon}</span>
                                <span>{analysis.verdictLabel}</span>
                            </div>
                        )}
                    </div>

                    {/* Primary Signals */}
                    <div className="sa-signal-group">
                        <div className="sa-group-label">Primary Signals</div>
                        {analysis.primarySignals.map(s => <SignalItem key={s.id} check={s} />)}
                    </div>

                    {/* Confirmation Filters */}
                    <div className="sa-signal-group">
                        <div className="sa-group-label">Confirmation Filters</div>
                        {analysis.confirmations.map(s => <SignalItem key={s.id} check={s} />)}
                    </div>

                    {/* Risk Gates */}
                    <div className="sa-signal-group">
                        <div className="sa-group-label">Risk Gates</div>
                        {analysis.riskGates.map(s => <SignalItem key={s.id} check={s} />)}
                    </div>
                </div>
            )}

            {/* Enhanced Exit Reference */}
            {!isIndex && exitLevels && current?.close && (
                <div className="sa-exit-section glass-panel">
                    <h3 className="sa-section-title">
                        <LogOut size={16} />
                        Exit Reference
                    </h3>
                    <div className="exit-levels">
                        {/* Fixed Exits */}
                        <div className="exit-group">
                            <div className="exit-group-title">고정 청산</div>
                            <div className="exit-item">
                                <span className="exit-label exit-loss">ES1 손절 -3%</span>
                                <span className="exit-value">{fmtPrice(exitLevels.stopLoss)}</span>
                            </div>
                            <div className="exit-item">
                                <span className="exit-label exit-profit">ES2 익절 +7%</span>
                                <span className="exit-value">{fmtPrice(exitLevels.takeProfit)}</span>
                            </div>
                        </div>

                        {/* ATR Dynamic Exits */}
                        {exitLevels.atrValue != null && (
                            <div className="exit-group">
                                <div className="exit-group-title">ATR 동적 청산 ({exitLevels.dynamicMultiplier}x ATR)</div>
                                {exitLevels.atrStopLoss != null && (
                                    <div className="exit-item">
                                        <span className="exit-label exit-loss">ATR 손절</span>
                                        <span className="exit-value">{fmtPrice(exitLevels.atrStopLoss)}</span>
                                    </div>
                                )}
                                {exitLevels.atrTakeProfit != null && (
                                    <div className="exit-item">
                                        <span className="exit-label exit-profit">ATR 익절 (2x)</span>
                                        <span className="exit-value">{fmtPrice(exitLevels.atrTakeProfit)}</span>
                                    </div>
                                )}
                                {exitLevels.trailingStop != null && (
                                    <div className="exit-item">
                                        <span className="exit-label">ES3 트레일링 (1.5x)</span>
                                        <span className="exit-value">{fmtPrice(exitLevels.trailingStop)}</span>
                                    </div>
                                )}
                                {exitLevels.chandelierExit != null && (
                                    <div className="exit-item">
                                        <span className="exit-label">샹들리에 (3x)</span>
                                        <span className="exit-value">{fmtPrice(exitLevels.chandelierExit)}</span>
                                    </div>
                                )}
                            </div>
                        )}

                        {/* Effective Levels */}
                        <div className="exit-group">
                            <div className="exit-group-title">적용 청산가</div>
                            <div className="exit-item exit-effective-highlight">
                                <span className="exit-label exit-effective-label">적용 손절</span>
                                <span className="exit-value">{fmtPrice(exitLevels.effectiveStopLoss)}</span>
                            </div>
                            <div className="exit-item exit-effective-highlight">
                                <span className="exit-label exit-effective-label">적용 익절</span>
                                <span className="exit-value">{fmtPrice(exitLevels.effectiveTakeProfit)}</span>
                            </div>
                        </div>

                        {/* Other Exit Conditions */}
                        <div className="exit-group">
                            <div className="exit-group-title">기타 청산 조건</div>
                            <div className="exit-item">
                                <span className="exit-label">ES4 데드크로스</span>
                                <span className={`exit-value ${exitLevels.deadCrossActive ? 'exit-loss' : ''}`}>
                                    {exitLevels.deadCrossActive ? '발생 중' : '미발생'}
                                </span>
                            </div>
                            <div className="exit-item">
                                <span className="exit-label">ES5 보유한도</span>
                                <span className="exit-value">{exitLevels.maxHoldingDays}일</span>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
