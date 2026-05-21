import { useState, useEffect, useMemo } from 'react';
import { TrendingUp, TrendingDown, CheckCircle, XCircle, Target, LogOut, Compass, Activity, Gauge, ChevronDown, BarChart2, RefreshCw, ExternalLink } from 'lucide-react';
import type { AnalyticsData } from '@lib/api';
import { useAppState } from '@contexts/AppStateContext';
import {
    analyzeEntrySignals,
    calculateExitLevels,
    computeVolumeMA,
    type SignalCheck,
    type Verdict,
    type TrendFilter,
    type SMCAnalysis,
} from '@lib/signalEngine';
import { analyzeFutures, computeATREntry, type FuturesAnalysis, type SetupBias, type ATREntryCalc } from '@lib/futuresEngine';

// Phase D3 extracted sub-components
import { SignalItem }          from './signal-analysis/SignalItem';
import { StrengthBar }         from './signal-analysis/StrengthBar';
import { ATREntryPanel }       from './signal-analysis/ATREntryPanel';
import { TechAnalysisPanels }  from './signal-analysis/TechAnalysisPanels';
import { ConfidenceBar }       from './signal-analysis/ConfidenceBar';
import { TrendOverviewPanel }  from './signal-analysis/TrendOverviewPanel';
import { SMCPanel }            from './signal-analysis/SMCPanel';

import './SignalAnalysis.css';

interface SignalAnalysisProps {
    data: AnalyticsData[];
    ticker: string;
    currencySymbol: string;
    isKorean: boolean;
    onSelectTicker?: (symbol: string) => void;
    refetch?: () => void;
    hideIndexButtons?: boolean;
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

export function SignalAnalysis({ data, ticker, currencySymbol, isKorean, onSelectTicker, refetch, hideIndexButtons }: SignalAnalysisProps) {
    const { navigateToOperations } = useAppState();
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

    // Stock analysis (auto-computed for non-index tickers, memoized)
    const volumeMA = useMemo(() => computeVolumeMA(data, 20), [data]);
    const analysis = useMemo(() => {
        if (isIndex || !current || !previous) return null;
        return analyzeEntrySignals(current, previous, volumeMA, data);
    }, [data, current, previous, isIndex, volumeMA]);
    const exitLevels = useMemo(() => {
        if (isIndex || !current || !previous || !current.close) return null;
        return calculateExitLevels(current.close, current, previous, data);
    }, [data, current, previous, isIndex]);

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

            {/* View in Operations (non-index tickers only) */}
            {!isIndex && (
                <button
                    className="sa-view-ops-btn"
                    onClick={() => navigateToOperations({ ticker })}
                >
                    <ExternalLink size={14} />
                    View in Operations
                </button>
            )}

            {/* Index Quick Select */}
            {isIndex && onSelectTicker && !hideIndexButtons && (
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
