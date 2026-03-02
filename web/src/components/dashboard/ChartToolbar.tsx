import { Ruler, TrendingUp, Minus, Trash2 } from 'lucide-react';
import { MA_CONFIG, type ChartType, type OverlayState } from '../../lib/chartUtils';
import type { DrawingToolType } from '../../lib/drawingTypes';
import './ChartToolbar.css';

export interface TimeframeOption {
    label: string;
    interval: string;
    period: string;       // data fetch period (large, for indicator accuracy)
    visibleBars: number;  // initial visible bars on chart (~50% of fetched)
}

const TIMEFRAMES: TimeframeOption[] = [
    { label: '1m', interval: '1m', period: '5d', visibleBars: 390 },
    { label: '5m', interval: '5m', period: '1mo', visibleBars: 240 },
    { label: '15m', interval: '15m', period: '60d', visibleBars: 200 },
    { label: '30m', interval: '30m', period: '60d', visibleBars: 130 },
    { label: '1H', interval: '1h', period: '6mo', visibleBars: 160 },
    { label: '4H', interval: '4h', period: '1y', visibleBars: 130 },
    { label: '1D', interval: '1d', period: '2y', visibleBars: 130 },
    { label: '1W', interval: '1wk', period: '10y', visibleBars: 104 },
    { label: '1M', interval: '1mo', period: 'max', visibleBars: 60 },
];

const CHART_TYPES: { label: string; value: ChartType }[] = [
    { label: '🕯', value: 'candlestick' },
    { label: '📈', value: 'line' },
    { label: '📊', value: 'area' },
    { label: 'HA', value: 'heikin-ashi' },
];

interface ChartToolbarProps {
    activeInterval: string;
    activePeriod: string;
    onTimeframeChange: (interval: string, period: string, visibleBars: number) => void;
    activeSubcharts: { rsi: boolean; macd: boolean; adx: boolean };
    onSubchartToggle: (subchart: 'rsi' | 'macd' | 'adx') => void;
    chartType: ChartType;
    onChartTypeChange: (type: ChartType) => void;
    activeOverlays: OverlayState;
    onOverlayToggle: (key: string) => void;
    showVolumeProfile: boolean;
    onToggleVolumeProfile: () => void;
    measureMode: boolean;
    onToggleMeasure: () => void;
    showSR: boolean;
    onToggleSR: () => void;
    drawingTool: DrawingToolType;
    onSetDrawingTool: (tool: DrawingToolType) => void;
    onClearDrawings: () => void;
}

export function ChartToolbar({
    activeInterval, activePeriod, onTimeframeChange,
    activeSubcharts, onSubchartToggle,
    chartType, onChartTypeChange,
    activeOverlays, onOverlayToggle,
    showVolumeProfile, onToggleVolumeProfile,
    measureMode, onToggleMeasure,
    showSR, onToggleSR,
    drawingTool, onSetDrawingTool, onClearDrawings,
}: ChartToolbarProps) {
    const isActive = (tf: TimeframeOption) =>
        tf.interval === activeInterval && tf.period === activePeriod;

    return (
        <div className="chart-toolbar">
            {/* Chart Type */}
            <div className="toolbar-section">
                <span className="chart-toolbar-label">TYPE</span>
                {CHART_TYPES.map(ct => (
                    <button
                        key={ct.value}
                        className={`tf-btn ${chartType === ct.value ? 'active' : ''}`}
                        onClick={() => onChartTypeChange(ct.value)}
                    >
                        {ct.label}
                    </button>
                ))}
            </div>

            <div className="toolbar-divider" />

            {/* Timeframe */}
            <div className="toolbar-section">
                <span className="chart-toolbar-label">INTERVAL</span>
                {TIMEFRAMES.map(tf => (
                    <button
                        key={tf.label}
                        className={`tf-btn ${isActive(tf) ? 'active' : ''}`}
                        onClick={() => onTimeframeChange(tf.interval, tf.period, tf.visibleBars)}
                    >
                        {tf.label}
                    </button>
                ))}
            </div>

            <div className="toolbar-divider" />

            {/* Subcharts */}
            <div className="toolbar-section">
                <span className="chart-toolbar-label">SUBCHARTS</span>
                <button className={`tf-btn ${activeSubcharts.rsi ? 'active' : ''}`} onClick={() => onSubchartToggle('rsi')}>RSI</button>
                <button className={`tf-btn ${activeSubcharts.macd ? 'active' : ''}`} onClick={() => onSubchartToggle('macd')}>MACD</button>
                <button className={`tf-btn ${activeSubcharts.adx ? 'active' : ''}`} onClick={() => onSubchartToggle('adx')}>ADX</button>
            </div>

            <div className="toolbar-divider" />

            {/* Overlays (MAs) */}
            <div className="toolbar-section">
                <span className="chart-toolbar-label">OVERLAYS</span>
                {Object.entries(MA_CONFIG).map(([key, conf]) => (
                    <button
                        key={key}
                        className={`tf-btn ${(activeOverlays as any)[key] ? 'active' : ''}`}
                        onClick={() => onOverlayToggle(key)}
                        style={(activeOverlays as any)[key] ? { color: conf.color, boxShadow: `0 0 0 1px ${conf.color}40` } : {}}
                    >
                        {conf.label}
                    </button>
                ))}
            </div>

            <div className="toolbar-divider" />

            {/* Tools */}
            <div className="toolbar-section">
                <span className="chart-toolbar-label">TOOLS</span>
                <button
                    className={`tf-btn ${showVolumeProfile ? 'active' : ''}`}
                    onClick={onToggleVolumeProfile}
                >
                    VP
                </button>
                <button
                    className={`tf-btn ${showSR ? 'active' : ''}`}
                    onClick={onToggleSR}
                    title="Support/Resistance"
                >
                    S/R
                </button>
                <button
                    className={`tf-btn ${measureMode ? 'active' : ''}`}
                    onClick={onToggleMeasure}
                    title="Measure Tool"
                >
                    <Ruler size={14} />
                </button>
            </div>

            <div className="toolbar-divider" />

            {/* Drawing Tools */}
            <div className="toolbar-section">
                <span className="chart-toolbar-label">DRAW</span>
                <button
                    className={`tf-btn ${drawingTool === 'trendline' ? 'active' : ''}`}
                    onClick={() => onSetDrawingTool(drawingTool === 'trendline' ? null : 'trendline')}
                    title="Trend Line (2 clicks)"
                >
                    <TrendingUp size={14} />
                </button>
                <button
                    className={`tf-btn ${drawingTool === 'hline' ? 'active' : ''}`}
                    onClick={() => onSetDrawingTool(drawingTool === 'hline' ? null : 'hline')}
                    title="Horizontal Line (1 click)"
                >
                    <Minus size={14} />
                </button>
                <button
                    className={`tf-btn ${drawingTool === 'fibonacci' ? 'active' : ''}`}
                    onClick={() => onSetDrawingTool(drawingTool === 'fibonacci' ? null : 'fibonacci')}
                    title="Fibonacci Retracement (2 clicks)"
                >
                    Fib
                </button>
                <button
                    className="tf-btn"
                    onClick={onClearDrawings}
                    title="Clear All Drawings"
                >
                    <Trash2 size={14} />
                </button>
            </div>
        </div>
    );
}
