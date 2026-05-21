import { useState, useReducer, useMemo, useCallback } from 'react';
import { useAnalyticsData } from '@hooks/useAnalyticsData';
import { usePolling } from '@hooks/usePolling';
import { useMarketSession } from '@hooks/useMarketSession';
import { useLivePrice } from '@hooks/useLivePrice';
import { fetchAnalyticsData, type AnalyticsResponse } from '@lib/api';
import { PollingControl } from '@components/PollingControl';
import { TechnicalChart } from '@components/dashboard/TechnicalChart';
import { ChartToolbar } from '@components/dashboard/ChartToolbar';
import { TickerSearch } from '@components/dashboard/TickerSearch';
import { MarketRegimePanel } from '@components/dashboard/MarketRegimePanel';
import { SignalAnalysis } from '@components/dashboard/SignalAnalysis';
import { AlertCircle } from 'lucide-react';
import { ErrorBoundary } from '@components/ErrorBoundary';
import { ChartSkeleton, ScoreCardsSkeleton } from '@components/common/Skeleton';
import { aggregate4HCandles, computeHeikinAshi, type ChartType, type OverlayState } from '@lib/chartUtils';
import type { DrawingToolType, Drawing } from '@lib/drawingTypes';
import { computeTrendSignal } from '@lib/trendSignal';
import './Dashboard.css';

// --- Constants ---

/** Index ticker가 선택됐을 때 표시되는 quick-select 옵션. 모듈 레벨 상수라 매 렌더마다 재생성 안 됨. */
const INDEX_QUICK_SELECT: { label: string; symbol: string }[] = [
    { label: 'S&P 500',   symbol: '^GSPC'  },
    { label: 'NASDAQ',    symbol: '^IXIC'  },
    { label: 'KOSPI',     symbol: '^KS11'  },
    { label: 'KOSPI 200', symbol: '^KS200' },
];

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

type OverlayKey = keyof OverlayState;

type ChartAction =
    | { type: 'SET_CHART_TYPE'; payload: ChartType }
    | { type: 'TOGGLE_SUBCHART'; payload: 'rsi' | 'macd' | 'adx' }
    | { type: 'TOGGLE_OVERLAY'; payload: OverlayKey }
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
            return { ...state, activeOverlays: { ...state.activeOverlays, [action.payload]: !state.activeOverlays[action.payload] } };
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
    const [ticker, setTicker] = useState('^KS200');
    const [stockName, setStockName] = useState({ nameKr: 'KOSPI 200', nameEn: 'KOSPI 200 Index' });
    const [period, setPeriod] = useState('2y');
    const [interval, setInterval] = useState('1d');
    const [visibleBars, setVisibleBars] = useState(130);
    const [chartState, dispatch] = useReducer(chartReducer, initialChartState);

    // 4H fix: fetch 1h data when 4h is selected
    const fetchInterval = interval === '4h' ? '1h' : interval;
    const { data: initialData, loading, error, refetch } = useAnalyticsData(ticker, period, fetchInterval);

    // Real-time polling — 간격을 백엔드 캐시 TTL(300s)과 정렬, 장외시간에는 600s
    const session = useMarketSession(ticker);
    const pollingFetchFn = useCallback(
      () => fetchAnalyticsData(ticker, period, fetchInterval),
      [ticker, period, fetchInterval],
    );
    const polling = usePolling<AnalyticsResponse>(pollingFetchFn, {
      interval: session.interval,
      enabled: true,
      cacheKey: `analytics:${ticker}:${period}:${fetchInterval}`,
    });

    // Merge: polling data takes priority when available
    const data = polling.data ?? initialData;

    // Real-time price via SSE
    const livePrice = useLivePrice(ticker);

    // Data pipeline 1: 무거운 단계 (interval/chartType 변경 시에만)
    //   raw → 4H aggregate → Heikin-Ashi → sort
    // Guard: data.interval 와 expectedInterval 불일치 (stale data during switch) 시 빈 배열
    // Phase D1.3 분리: livePrice 변경 시 4H/HA 재계산하지 않도록 baseChartData를 별도 memo로.
    const baseChartData = useMemo(() => {
        if (!data?.data) return [];
        const expectedInterval = interval === '4h' ? '1h' : interval;
        if (data.interval !== expectedInterval) return [];
        let processed = data.data;
        if (interval === '4h') processed = aggregate4HCandles(processed);
        if (chartState.chartType === 'heikin-ashi') processed = computeHeikinAshi(processed);
        // Pre-sort by datetime so TechnicalChart can skip redundant sorts
        return [...processed].sort((a, b) => a.datetime.localeCompare(b.datetime));
    }, [data, interval, chartState.chartType]);

    // Data pipeline 2: 가벼운 단계 (livePrice 변경 시에만 마지막 캔들 merge)
    const chartData = useMemo(() => {
        if (!livePrice || baseChartData.length === 0) return baseChartData;
        const last = baseChartData[baseChartData.length - 1];
        return [
            ...baseChartData.slice(0, -1),
            { ...last, close: livePrice.price, high: Math.max(last.high, livePrice.price), low: Math.min(last.low, livePrice.price) },
        ];
    }, [baseChartData, livePrice]);

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

    // --- Trend Signal (Phase D1.2: 순수 함수 + useMemo로 분리) ---
    const { label: trendSignal, color: trendColor, bg: trendBg } = useMemo(
        () => computeTrendSignal(currentData),
        [currentData],
    );

    return (
        <div className="dashboard-page container">
            <div className="dashboard-header">
                <div>
                    <h1 className="page-title">Stock Analytics(분석)</h1>
                    <p className="page-subtitle">Real-time quantitative analysis and technical indicators.</p>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: 8, alignItems: 'flex-end' }}>
                    <TickerSearch
                        onSelect={handleSelect}
                        loading={loading}
                        initialValue="^KS200"
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

            <MarketRegimePanel onSelectIndex={(symbol) => { setTicker(symbol); setStockName({ nameKr: '', nameEn: '' }); }} />

            {loading && !error && (
                <div className="dashboard-grid">
                    <div className="chart-section">
                        <ChartSkeleton height={450} />
                    </div>
                    <div className="analysis-section">
                        <ScoreCardsSkeleton />
                    </div>
                </div>
            )}

            {error && (
                <div className="error-banner glass-panel" role="alert" aria-live="polite">
                    <AlertCircle className="text-error" aria-hidden="true" />
                    <span>Error loading data: {error}</span>
                </div>
            )}

            {/* Index Quick-Select — above chart, only for index tickers */}
            {isIndex && (
                <div className="index-quick-bar" role="tablist" aria-label="주요 지수 선택">
                    {INDEX_QUICK_SELECT.map(idx => {
                        const isActive = ticker === idx.symbol;
                        return (
                            <button
                                key={idx.symbol}
                                role="tab"
                                aria-selected={isActive}
                                aria-current={isActive ? 'true' : undefined}
                                className={`index-btn ${isActive ? 'active' : ''}`}
                                onClick={() => handleSelect(idx.symbol)}
                            >
                                {idx.label}
                            </button>
                        );
                    })}
                </div>
            )}

            {!loading && !error && data && (
                <>
                    {/* Main Chart — full width */}
                    <ErrorBoundary>
                    <div className="chart-section glass-panel">
                        {(stockName.nameKr || stockName.nameEn || livePrice) && (
                            <div className="stock-info" style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                                <span className="stock-ticker">{ticker}</span>
                                {stockName.nameKr && <span className="stock-name-kr">{stockName.nameKr}</span>}
                                {stockName.nameEn && <span className="stock-name-en">{stockName.nameEn}</span>}
                                {livePrice && (
                                    <span style={{
                                        fontSize: '0.85rem',
                                        fontWeight: 700,
                                        color: livePrice.change >= 0 ? 'var(--text-success)' : 'var(--text-error)',
                                        marginLeft: 'auto',
                                    }}>
                                        {currencySymbol}{livePrice.price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                        {' '}
                                        <span style={{ fontSize: '0.75rem', opacity: 0.8 }}>
                                            {livePrice.change >= 0 ? '+' : ''}{livePrice.change_pct.toFixed(2)}%
                                        </span>
                                    </span>
                                )}
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
                    </ErrorBoundary>

                    {/* Signal Analysis — below chart in responsive panel grid */}
                    <ErrorBoundary>
                    <div className="signal-panels-below">
                        <SignalAnalysis
                            data={data.data}
                            ticker={ticker}
                            currencySymbol={currencySymbol}
                            isKorean={isKorean}
                            onSelectTicker={setTicker}
                            refetch={refetch}
                            hideIndexButtons
                        />
                    </div>
                    </ErrorBoundary>
                </>
            )}
        </div>
    );
}
