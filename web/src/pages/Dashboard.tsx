import { useState, useReducer, useMemo, useCallback } from 'react';
import { useAnalyticsData } from '../hooks/useAnalyticsData';
import { usePolling } from '../hooks/usePolling';
import { fetchAnalyticsData, type AnalyticsResponse } from '../lib/api';
import { PollingControl } from '../components/PollingControl';
import { TechnicalChart } from '../components/dashboard/TechnicalChart';
import { ChartToolbar } from '../components/dashboard/ChartToolbar';
import { TickerSearch } from '../components/dashboard/TickerSearch';
import { MarketRegimePanel } from '../components/dashboard/MarketRegimePanel';
import { SignalAnalysis } from '../components/dashboard/SignalAnalysis';
import { AlertCircle } from 'lucide-react';
import { aggregate4HCandles, computeHeikinAshi, type ChartType, type OverlayState } from '../lib/chartUtils';
import type { DrawingToolType, Drawing } from '../lib/drawingTypes';
import './Dashboard.css';

// --- Chart State Reducer ---

interface ChartState {
    chartType: ChartType;
    activeSubcharts: { rsi: boolean; macd: boolean; adx: boolean };
    activeOverlays: OverlayState;
    showVolumeProfile: boolean;
    measureMode: boolean;
    showSR: boolean;
    drawingTool: DrawingToolType;
    drawings: Drawing[];
}

type ChartAction =
    | { type: 'SET_CHART_TYPE'; payload: ChartType }
    | { type: 'TOGGLE_SUBCHART'; payload: 'rsi' | 'macd' | 'adx' }
    | { type: 'TOGGLE_OVERLAY'; payload: string }
    | { type: 'TOGGLE_VOLUME_PROFILE' }
    | { type: 'TOGGLE_MEASURE' }
    | { type: 'TOGGLE_SR' }
    | { type: 'SET_DRAWING_TOOL'; payload: DrawingToolType }
    | { type: 'ADD_DRAWING'; payload: Drawing }
    | { type: 'CLEAR_DRAWINGS' };

const initialChartState: ChartState = {
    chartType: 'candlestick',
    activeSubcharts: { rsi: false, macd: false, adx: false },
    activeOverlays: { sma5: false, sma20: true, sma50: false, sma60: false, sma120: false, sma200: false, ema20: false },
    showVolumeProfile: false,
    measureMode: false,
    showSR: false,
    drawingTool: null,
    drawings: [],
};

function chartReducer(state: ChartState, action: ChartAction): ChartState {
    switch (action.type) {
        case 'SET_CHART_TYPE':
            return { ...state, chartType: action.payload };
        case 'TOGGLE_SUBCHART':
            return { ...state, activeSubcharts: { ...state.activeSubcharts, [action.payload]: !state.activeSubcharts[action.payload] } };
        case 'TOGGLE_OVERLAY':
            return { ...state, activeOverlays: { ...state.activeOverlays, [action.payload]: !(state.activeOverlays as any)[action.payload] } };
        case 'TOGGLE_VOLUME_PROFILE':
            return { ...state, showVolumeProfile: !state.showVolumeProfile };
        case 'TOGGLE_MEASURE':
            return { ...state, measureMode: !state.measureMode, drawingTool: !state.measureMode ? null : state.drawingTool };
        case 'TOGGLE_SR':
            return { ...state, showSR: !state.showSR };
        case 'SET_DRAWING_TOOL':
            return { ...state, drawingTool: action.payload, measureMode: action.payload !== null ? false : state.measureMode };
        case 'ADD_DRAWING':
            return { ...state, drawings: [...state.drawings, action.payload], drawingTool: null };
        case 'CLEAR_DRAWINGS':
            return { ...state, drawings: [] };
        default:
            return state;
    }
}

export function Dashboard() {
    const [ticker, setTicker] = useState('005930.KS');
    const [stockName, setStockName] = useState({ nameKr: '삼성전자', nameEn: 'Samsung Electronics' });
    const [period, setPeriod] = useState('2y');
    const [interval, setInterval] = useState('1d');
    const [visibleBars, setVisibleBars] = useState(130);
    const [chartState, dispatch] = useReducer(chartReducer, initialChartState);

    // 4H fix: fetch 1h data when 4h is selected
    const fetchInterval = interval === '4h' ? '1h' : interval;
    const { data: initialData, loading, error, refetch } = useAnalyticsData(ticker, period, fetchInterval);

    // Real-time polling
    const pollingFetchFn = useCallback(
      () => fetchAnalyticsData(ticker, period, fetchInterval),
      [ticker, period, fetchInterval],
    );
    const polling = usePolling<AnalyticsResponse>(pollingFetchFn, { interval: 30000, enabled: false });

    // Merge: polling data takes priority when available
    const data = polling.data ?? initialData;

    // Data pipeline: raw → 4H aggregate → Heikin-Ashi
    // Guard: skip processing if data interval doesn't match current interval (stale data during switch)
    const chartData = useMemo(() => {
        if (!data?.data) return [];
        const expectedInterval = interval === '4h' ? '1h' : interval;
        if (data.interval !== expectedInterval) return [];
        let processed = data.data;
        if (interval === '4h') processed = aggregate4HCandles(processed);
        if (chartState.chartType === 'heikin-ashi') processed = computeHeikinAshi(processed);
        return processed;
    }, [data, interval, chartState.chartType]);

    const handleSelect = (newTicker: string, nameKr?: string, nameEn?: string) => {
        setTicker(newTicker);
        setStockName({ nameKr: nameKr || '', nameEn: nameEn || '' });
    };

    const handleTimeframeChange = (newInterval: string, newPeriod: string, newVisibleBars: number) => {
        setInterval(newInterval);
        setPeriod(newPeriod);
        setVisibleBars(newVisibleBars);
    };

    // Currency symbol
    const isKorean = ticker.endsWith('.KS') || ticker.endsWith('.KQ');
    const isIndex = ticker.startsWith('^');
    const currencySymbol = isKorean ? '₩' : isIndex ? '' : '$';

    const currentData = data?.data && data.data.length > 0
        ? data.data[data.data.length - 1]
        : null;

    // --- Trend Signal Logic ---
    let trendSignal = "Neutral Phase";
    let trendColor = "text-muted";
    let trendBg = "rgba(148, 163, 184, 0.1)";

    if (currentData) {
        const { close, sma_5, sma_20, sma_60, sma_120, sma_200, bb_width } = currentData;
        const isSqueeze = bb_width && close && (bb_width / close) < 0.05;

        if (isSqueeze) {
            trendSignal = "Volatility Squeeze ⚠️";
            trendColor = "text-warning";
            trendBg = "rgba(234, 179, 8, 0.1)";
        }
        else if (sma_5 && sma_20 && sma_60 && sma_120 && sma_200) {
            if (close > sma_5 && sma_5 > sma_20 && sma_20 > sma_60 && sma_60 > sma_120 && sma_120 > sma_200) {
                trendSignal = "Strong Bull Trend 🚀";
                trendColor = "text-success";
                trendBg = "rgba(34, 197, 94, 0.1)";
            }
            else if (close > sma_200 && sma_20 > sma_60) {
                trendSignal = "Bullish Phase 🟢";
                trendColor = "text-success";
                trendBg = "rgba(34, 197, 94, 0.1)";
            }
            else if (close < sma_5 && sma_5 < sma_20 && sma_20 < sma_60 && sma_60 < sma_120 && sma_120 < sma_200) {
                trendSignal = "Strong Bear Trend 🩸";
                trendColor = "text-error";
                trendBg = "rgba(239, 68, 68, 0.1)";
            }
            else if (close < sma_200 && sma_20 < sma_60) {
                trendSignal = "Bearish Phase 🔴";
                trendColor = "text-error";
                trendBg = "rgba(239, 68, 68, 0.1)";
            }
        }
    }

    return (
        <div className="dashboard-page container">
            <MarketRegimePanel onSelectIndex={(symbol) => { setTicker(symbol); setStockName({ nameKr: '', nameEn: '' }); }} />

            <div className="dashboard-header">
                <div>
                    <h1 className="page-title">Stock Analytics(분석)</h1>
                    <p className="page-subtitle">Real-time quantitative analysis and technical indicators.</p>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: 8, alignItems: 'flex-end' }}>
                    <TickerSearch
                        onSelect={handleSelect}
                        loading={loading}
                        initialValue="005930"
                    />
                    <PollingControl
                        enabled={polling.enabled}
                        onToggle={polling.setEnabled}
                        interval={polling.interval}
                        onIntervalChange={polling.setInterval}
                        status={polling.status}
                        lastUpdated={polling.lastUpdated}
                        consecutiveErrors={polling.consecutiveErrors}
                        onRefresh={() => { polling.fetchNow(); refetch(); }}
                        compact
                    />
                </div>
            </div>

            {loading && !error && (
                <div className="loading-state">
                    <div className="badge-dot pulse-large"></div>
                    <p>Processing quantitative models...</p>
                </div>
            )}

            {error && (
                <div className="error-banner glass-panel">
                    <AlertCircle className="text-error" />
                    <span>Error loading data: {error}</span>
                </div>
            )}

            {!loading && !error && data && (
                <div className="dashboard-grid">
                    {/* Main Chart Area */}
                    <div className="chart-section glass-panel">
                        {(stockName.nameKr || stockName.nameEn) && (
                            <div className="stock-info">
                                <span className="stock-ticker">{ticker}</span>
                                {stockName.nameKr && <span className="stock-name-kr">{stockName.nameKr}</span>}
                                {stockName.nameEn && <span className="stock-name-en">{stockName.nameEn}</span>}
                            </div>
                        )}
                        <div className="section-head" style={{ padding: 0, borderBottom: 'none', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                            <ChartToolbar
                                activeInterval={interval}
                                activePeriod={period}
                                onTimeframeChange={handleTimeframeChange}
                                activeSubcharts={chartState.activeSubcharts}
                                onSubchartToggle={(s) => dispatch({ type: 'TOGGLE_SUBCHART', payload: s })}
                                chartType={chartState.chartType}
                                onChartTypeChange={(t) => dispatch({ type: 'SET_CHART_TYPE', payload: t })}
                                activeOverlays={chartState.activeOverlays}
                                onOverlayToggle={(k) => dispatch({ type: 'TOGGLE_OVERLAY', payload: k })}
                                showVolumeProfile={chartState.showVolumeProfile}
                                onToggleVolumeProfile={() => dispatch({ type: 'TOGGLE_VOLUME_PROFILE' })}
                                measureMode={chartState.measureMode}
                                onToggleMeasure={() => dispatch({ type: 'TOGGLE_MEASURE' })}
                                showSR={chartState.showSR}
                                onToggleSR={() => dispatch({ type: 'TOGGLE_SR' })}
                                drawingTool={chartState.drawingTool}
                                onSetDrawingTool={(tool) => dispatch({ type: 'SET_DRAWING_TOOL', payload: tool })}
                                onClearDrawings={() => dispatch({ type: 'CLEAR_DRAWINGS' })}
                            />
                            {currentData && (
                                <div style={{
                                    marginRight: '12px',
                                    marginTop: '6px',
                                    padding: '4px 10px',
                                    borderRadius: '6px',
                                    fontSize: '0.75rem',
                                    fontWeight: 600,
                                    color: `var(--${trendColor})`,
                                    backgroundColor: trendBg,
                                    border: `1px solid var(--${trendColor})`,
                                    opacity: 0.8,
                                    whiteSpace: 'nowrap',
                                    flexShrink: 0,
                                }}>
                                    {trendSignal}
                                </div>
                            )}
                        </div>
                        <div className="chart-container" style={{ paddingTop: 0 }}>
                            <TechnicalChart
                                data={chartData}
                                ticker={data.ticker}
                                interval={interval}
                                height={480}
                                activeSubcharts={chartState.activeSubcharts}
                                chartType={chartState.chartType}
                                activeOverlays={chartState.activeOverlays}
                                showVolumeProfile={chartState.showVolumeProfile}
                                measureMode={chartState.measureMode}
                                isKorean={isKorean}
                                showSR={chartState.showSR}
                                visibleBars={visibleBars}
                                drawingTool={chartState.drawingTool}
                                drawings={chartState.drawings}
                                onAddDrawing={(d: Drawing) => dispatch({ type: 'ADD_DRAWING', payload: d })}
                            />
                        </div>
                    </div>

                    {/* Signal Analysis Sidebar */}
                    <div className="metrics-sidebar">
                        <SignalAnalysis
                            data={data.data}
                            ticker={ticker}
                            currencySymbol={currencySymbol}
                            isKorean={isKorean}
                            onSelectTicker={setTicker}
                            refetch={refetch}
                        />
                    </div>
                </div>
            )}
        </div>
    );
}
