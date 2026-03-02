import { useEffect, useRef, useState, useCallback } from 'react';
import { createChart, ColorType, CrosshairMode, type IChartApi, type ISeriesApi, type SeriesType, type Time } from 'lightweight-charts';
import type { AnalyticsData } from '../../lib/api';
import { MA_CONFIG, computeSupportResistance, type ChartType, type OverlayState } from '../../lib/chartUtils';
// smcZonePrimitive available if OB/FVG zones are re-enabled
import { OHLCVOverlay, type CrosshairData } from './OHLCVOverlay';
import { VolumeProfile } from './VolumeProfile';
import { MeasurementOverlay, type MeasureState, type MeasurePoint } from './MeasurementOverlay';
import { DrawingOverlay } from './DrawingOverlay';
import type { DrawingToolType, Drawing, PendingDrawing, DrawingPoint } from '../../lib/drawingTypes';
import { INITIAL_PENDING } from '../../lib/drawingTypes';

interface TechnicalChartProps {
    data: AnalyticsData[];
    ticker?: string;
    interval?: string;
    height?: number;
    activeSubcharts?: { rsi: boolean; macd: boolean; adx: boolean };
    chartType?: ChartType;
    activeOverlays?: OverlayState;
    showVolumeProfile?: boolean;
    measureMode?: boolean;
    isKorean?: boolean;
    showSR?: boolean;
    visibleBars?: number;
    drawingTool?: DrawingToolType;
    drawings?: Drawing[];
    onAddDrawing?: (drawing: Drawing) => void;
}

function toChartTime(datetime: string): Time {
    const d = datetime.split(' ')[0];
    return d as Time;
}

// --- Sort helper (reused everywhere) ---
function sortByTime<T extends { time: Time }>(arr: T[]): T[] {
    return arr.sort((a, b) => {
        if (typeof a.time === 'number' && typeof b.time === 'number') return a.time - b.time;
        return new Date(a.time as string).getTime() - new Date(b.time as string).getTime();
    });
}

export function TechnicalChart({
    data,
    ticker = '',
    interval = '1d',
    height = 520,
    activeSubcharts = { rsi: false, macd: false, adx: false },
    chartType = 'candlestick',
    activeOverlays = { sma5: false, sma20: true, sma50: false, sma60: false, sma120: false, sma200: false, ema20: false },
    showVolumeProfile = false,
    measureMode = false,
    isKorean = false,
    showSR = false,
    visibleBars,
    drawingTool,
    drawings = [],
    onAddDrawing,
}: TechnicalChartProps) {
    const chartContainerRef = useRef<HTMLDivElement>(null);
    const rsiContainerRef = useRef<HTMLDivElement>(null);
    const macdContainerRef = useRef<HTMLDivElement>(null);
    const adxContainerRef = useRef<HTMLDivElement>(null);
    const chartApiRef = useRef<IChartApi | null>(null);
    const mainSeriesRef = useRef<ISeriesApi<SeriesType> | null>(null);
    const parseTimeRef = useRef<((datetime: string) => Time) | null>(null);

    // OHLCV overlay state (throttled)
    const [crosshairData, setCrosshairData] = useState<CrosshairData | null>(null);
    const rafRef = useRef<number>(0);

    // Measurement state
    const [measureState, setMeasureState] = useState<MeasureState>({ mode: 'idle', anchor: null, target: null });

    // Drawing state
    const [pendingDrawing, setPendingDrawing] = useState<PendingDrawing>(INITIAL_PENDING);

    // Reset measurement when mode is toggled off
    useEffect(() => {
        if (!measureMode) {
            setMeasureState({ mode: 'idle', anchor: null, target: null });
        }
    }, [measureMode]);

    // Reset pending drawing when tool changes
    useEffect(() => {
        setPendingDrawing({ tool: drawingTool ?? null, anchor: null, cursor: null });
    }, [drawingTool]);

    // Escape key to cancel pending drawing
    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === 'Escape' && drawingTool) {
                setPendingDrawing({ tool: drawingTool, anchor: null, cursor: null });
            }
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [drawingTool]);

    // Build time→data lookup map
    const dataMapRef = useRef<Map<string, AnalyticsData>>(new Map());

    const latest = data.length > 0 ? data[data.length - 1] : null;

    // Stable reference for measure mode
    const measureModeRef = useRef(measureMode);
    measureModeRef.current = measureMode;
    const measureStateRef = useRef(measureState);
    measureStateRef.current = measureState;

    // Stable references for drawing tool
    const drawingToolRef = useRef(drawingTool);
    drawingToolRef.current = drawingTool;
    const pendingDrawingRef = useRef(pendingDrawing);
    pendingDrawingRef.current = pendingDrawing;
    const onAddDrawingRef = useRef(onAddDrawing);
    onAddDrawingRef.current = onAddDrawing;

    const handleCrosshairData = useCallback((d: CrosshairData | null) => {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = requestAnimationFrame(() => setCrosshairData(d));
    }, []);

    useEffect(() => {
        if (!chartContainerRef.current || !data || data.length === 0) return;

        const isIntraday = ['1m', '2m', '5m', '15m', '30m', '60m', '1h', '4h', '90m'].includes(interval);

        const parseTime = (datetime: string): Time => {
            if (isIntraday) {
                const ts = new Date(datetime).getTime() / 1000;
                return ts as unknown as Time;
            }
            return toChartTime(datetime);
        };
        parseTimeRef.current = parseTime;

        // Build lookup map
        const dataMap = new Map<string, AnalyticsData>();
        data.forEach(item => {
            const t = parseTime(item.datetime);
            dataMap.set(String(t), item);
        });
        dataMapRef.current = dataMap;

        // === Chart Data ===
        const chartData = sortByTime(data.map(item => ({
            time: parseTime(item.datetime),
            open: item.open,
            high: item.high,
            low: item.low,
            close: item.close,
        })).filter(d => d.time && !isNaN(d.close)));

        // === Volume Data ===
        const volumeData = sortByTime(data.map(item => ({
            time: parseTime(item.datetime),
            value: item.volume ?? 0,
            color: item.close >= item.open
                ? 'rgba(34, 197, 94, 0.5)'
                : 'rgba(239, 68, 68, 0.5)',
        })).filter(d => d.time && d.value > 0));

        // === Bollinger Bands ===
        const bbUpper = sortByTime(data
            .filter(item => item.bb_hband != null)
            .map(item => ({ time: parseTime(item.datetime), value: item.bb_hband! })));

        const bbLower = sortByTime(data
            .filter(item => item.bb_lband != null)
            .map(item => ({ time: parseTime(item.datetime), value: item.bb_lband! })));

        // === Create Chart ===
        const chart = createChart(chartContainerRef.current, {
            layout: {
                background: { type: ColorType.Solid, color: 'transparent' },
                textColor: '#787b86',
                fontFamily: "'Inter', -apple-system, sans-serif",
                fontSize: 12,
            },
            grid: {
                vertLines: { color: 'rgba(255, 255, 255, 0.04)' },
                horzLines: { color: 'rgba(255, 255, 255, 0.04)' },
            },
            width: chartContainerRef.current.clientWidth,
            height,
            crosshair: {
                mode: CrosshairMode.Normal,
                vertLine: { color: 'rgba(99, 102, 241, 0.4)', width: 1, style: 2, labelBackgroundColor: '#6366f1' },
                horzLine: { color: 'rgba(99, 102, 241, 0.4)', width: 1, style: 2, labelBackgroundColor: '#6366f1' },
            },
            timeScale: {
                borderColor: 'rgba(255, 255, 255, 0.06)',
                timeVisible: isIntraday,
                secondsVisible: false,
                rightOffset: 5,
                barSpacing: isIntraday ? 6 : 8,
            },
            rightPriceScale: {
                borderColor: 'rgba(255, 255, 255, 0.06)',
                scaleMargins: { top: 0.05, bottom: 0.25 },
            },
            watermark: {
                visible: true,
                text: ticker,
                color: 'rgba(255, 255, 255, 0.04)',
                fontSize: 48,
                horzAlign: 'center',
                vertAlign: 'center',
            },
        });

        chartApiRef.current = chart;

        // === Main Series (based on chartType) ===
        let mainSeries: ISeriesApi<SeriesType>;

        if (chartType === 'line') {
            mainSeries = chart.addLineSeries({
                color: '#2962ff',
                lineWidth: 2,
                crosshairMarkerVisible: true,
                lastValueVisible: true,
            });
            mainSeries.setData(sortByTime(chartData.map(d => ({ time: d.time, value: d.close }))));
        } else if (chartType === 'area') {
            mainSeries = chart.addAreaSeries({
                topColor: 'rgba(41, 98, 255, 0.4)',
                bottomColor: 'rgba(41, 98, 255, 0.0)',
                lineColor: '#2962ff',
                lineWidth: 2,
            });
            mainSeries.setData(sortByTime(chartData.map(d => ({ time: d.time, value: d.close }))));
        } else {
            // candlestick or heikin-ashi (HA data is pre-computed in Dashboard)
            mainSeries = chart.addCandlestickSeries({
                upColor: '#26a69a',
                downColor: '#ef5350',
                borderVisible: false,
                wickUpColor: '#26a69a',
                wickDownColor: '#ef5350',
            });
            mainSeries.setData(chartData);
        }

        mainSeriesRef.current = mainSeries;

        // === SMC Markers (BOS/CHoCH arrows only) ===
        const useCandles = chartType === 'candlestick' || chartType === 'heikin-ashi';
        const markers: any[] = [];

        if (useCandles) {
            data.forEach(item => {
                const time = parseTime(item.datetime);
                if (item.marker === 'BOS_BULL') {
                    markers.push({ time, position: 'belowBar', color: '#26a69a', shape: 'arrowUp', text: 'BOS' });
                } else if (item.marker === 'BOS_BEAR') {
                    markers.push({ time, position: 'aboveBar', color: '#ef5350', shape: 'arrowDown', text: 'BOS' });
                } else if (item.marker === 'CHOCH_BULL') {
                    markers.push({ time, position: 'belowBar', color: '#26a69a', shape: 'arrowUp', text: 'CHoCH' });
                } else if (item.marker === 'CHOCH_BEAR') {
                    markers.push({ time, position: 'aboveBar', color: '#ef5350', shape: 'arrowDown', text: 'CHoCH' });
                }
            });
            if (markers.length > 0) {
                (mainSeries as any).setMarkers(markers);
            }
        }

        // Last price line
        if (chartData.length > 0) {
            const lastPrice = chartData[chartData.length - 1].close;
            mainSeries.createPriceLine({
                price: lastPrice,
                color: '#2962ff',
                lineWidth: 1,
                lineStyle: 2,
                axisLabelVisible: true,
                title: '',
            });

            // Support/Resistance lines
            if (showSR) {
                const srLevels = computeSupportResistance(data, lastPrice);
                srLevels.forEach(level => {
                    mainSeries.createPriceLine({
                        price: level.price,
                        color: level.type === 'resistance'
                            ? 'rgba(239, 68, 68, 0.6)'
                            : 'rgba(34, 197, 94, 0.6)',
                        lineWidth: level.touches >= 3 ? 2 : 1,
                        lineStyle: 2,
                        axisLabelVisible: true,
                        title: `${level.type === 'resistance' ? 'R' : 'S'} (${level.touches})`,
                    });
                });
            }
        }

        // === Volume Series ===
        const volumeSeries = chart.addHistogramSeries({
            priceFormat: { type: 'volume' },
            priceScaleId: '',
        });
        volumeSeries.priceScale().applyOptions({
            scaleMargins: { top: 0.8, bottom: 0 },
        });
        volumeSeries.setData(volumeData);

        // === Bollinger Bands ===
        if (bbUpper.length > 0) {
            const upperBB = chart.addLineSeries({
                color: 'rgba(139, 92, 246, 0.4)',
                lineWidth: 1,
                crosshairMarkerVisible: false,
                lastValueVisible: false,
                priceLineVisible: false,
            });
            upperBB.setData(bbUpper);

            const lowerBB = chart.addLineSeries({
                color: 'rgba(139, 92, 246, 0.4)',
                lineWidth: 1,
                crosshairMarkerVisible: false,
                lastValueVisible: false,
                priceLineVisible: false,
            });
            lowerBB.setData(bbLower);
        }

        // === Dynamic Moving Averages ===
        if (activeOverlays) {
            Object.entries(activeOverlays).forEach(([key, enabled]) => {
                if (!enabled) return;
                const config = MA_CONFIG[key];
                if (!config) return;

                const maData = sortByTime(data
                    .filter(item => (item as any)[config.field] != null)
                    .map(item => ({
                        time: parseTime(item.datetime),
                        value: (item as any)[config.field] as number,
                    })));

                if (maData.length > 0) {
                    const maSeries = chart.addLineSeries({
                        color: config.color,
                        lineWidth: key === 'sma20' ? 2 : 1,
                        crosshairMarkerVisible: true,
                        lastValueVisible: true,
                        priceLineVisible: false,
                        title: config.label,
                    });
                    maSeries.setData(maData);
                }
            });
        }

        // === Subchart shared options ===
        const subchartLayoutOptions = {
            layout: {
                background: { type: ColorType.Solid, color: 'transparent' },
                textColor: '#787b86',
                fontFamily: "'Inter', -apple-system, sans-serif",
                fontSize: 11,
            },
            grid: {
                vertLines: { color: 'rgba(255, 255, 255, 0.04)' },
                horzLines: { color: 'rgba(255, 255, 255, 0.04)' },
            },
            timeScale: { visible: false },
            rightPriceScale: { borderColor: 'rgba(255, 255, 255, 0.06)' },
            crosshair: {
                mode: CrosshairMode.Normal,
                vertLine: { color: 'rgba(99, 102, 241, 0.4)', width: 1 as const, style: 2 as const, labelBackgroundColor: '#6366f1' },
                horzLine: { color: 'rgba(99, 102, 241, 0.4)', width: 1 as const, style: 2 as const, labelBackgroundColor: '#6366f1' },
            },
        };

        const subcharts: IChartApi[] = [];

        // === RSI Subchart ===
        let rsiChart: IChartApi | null = null;
        if (activeSubcharts.rsi && rsiContainerRef.current) {
            rsiChart = createChart(rsiContainerRef.current, {
                ...subchartLayoutOptions,
                width: rsiContainerRef.current.clientWidth,
                height: 160,
            });
            subcharts.push(rsiChart);
            const rsiSeries = rsiChart.addLineSeries({ color: '#a855f7', lineWidth: 2 });
            rsiSeries.createPriceLine({ price: 70, color: 'rgba(239, 68, 68, 0.4)', lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: 'OB' });
            rsiSeries.createPriceLine({ price: 30, color: 'rgba(34, 197, 94, 0.4)', lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: 'OS' });
            const rsiData = sortByTime(data
                .filter(d => d.rsi_14 !== null)
                .map(d => ({ time: parseTime(d.datetime), value: d.rsi_14! })));
            rsiSeries.setData(rsiData);
        }

        // === MACD Subchart ===
        let macdChart: IChartApi | null = null;
        if (activeSubcharts.macd && macdContainerRef.current) {
            macdChart = createChart(macdContainerRef.current, {
                ...subchartLayoutOptions,
                width: macdContainerRef.current.clientWidth,
                height: 160,
            });
            subcharts.push(macdChart);
            const macdLine = macdChart.addLineSeries({ color: '#3b82f6', lineWidth: 2 });
            const signalLine = macdChart.addLineSeries({ color: '#f59e0b', lineWidth: 2 });
            const histSeries = macdChart.addHistogramSeries();

            const mData: { time: Time; value: number }[] = [];
            const sData: { time: Time; value: number }[] = [];
            const hData: { time: Time; value: number; color: string }[] = [];

            data.forEach(d => {
                const t = parseTime(d.datetime);
                if (d.macd !== null) mData.push({ time: t, value: d.macd });
                if (d.macd_signal !== null) sData.push({ time: t, value: d.macd_signal });
                if (d.macd_diff !== null) {
                    hData.push({ time: t, value: d.macd_diff, color: d.macd_diff >= 0 ? 'rgba(38, 166, 154, 0.6)' : 'rgba(239, 83, 80, 0.6)' });
                }
            });

            macdLine.setData(sortByTime(mData));
            signalLine.setData(sortByTime(sData));
            histSeries.setData(sortByTime(hData));
        }

        // === ADX Subchart ===
        let adxChart: IChartApi | null = null;
        if (activeSubcharts.adx && adxContainerRef.current) {
            adxChart = createChart(adxContainerRef.current, {
                ...subchartLayoutOptions,
                width: adxContainerRef.current.clientWidth,
                height: 160,
            });
            subcharts.push(adxChart);
            const adxSeries = adxChart.addLineSeries({ color: '#f43f5e', lineWidth: 2 });
            const plusDi = adxChart.addLineSeries({ color: '#26a69a', lineWidth: 1, lineStyle: 2 });
            const minusDi = adxChart.addLineSeries({ color: '#ef5350', lineWidth: 1, lineStyle: 2 });
            adxSeries.createPriceLine({ price: 25, color: 'rgba(255, 255, 255, 0.2)', lineWidth: 1, lineStyle: 2, title: 'Trend Threshold' });

            const aData: { time: Time; value: number }[] = [];
            const pData: { time: Time; value: number }[] = [];
            const mDiData: { time: Time; value: number }[] = [];
            data.forEach(d => {
                const t = parseTime(d.datetime);
                if (d.adx !== null) aData.push({ time: t, value: d.adx });
                if (d.plus_di !== null) pData.push({ time: t, value: d.plus_di });
                if (d.minus_di !== null) mDiData.push({ time: t, value: d.minus_di });
            });
            adxSeries.setData(sortByTime(aData));
            plusDi.setData(sortByTime(pData));
            minusDi.setData(sortByTime(mDiData));
        }

        // === Time Scale Sync ===
        chart.timeScale().subscribeVisibleTimeRangeChange((range) => {
            if (range) subcharts.forEach(c => c.timeScale().setVisibleRange(range));
        });
        subcharts.forEach(srcChart => {
            srcChart.timeScale().subscribeVisibleTimeRangeChange((range) => {
                if (range) {
                    chart.timeScale().setVisibleRange(range);
                    subcharts.forEach(t => { if (t !== srcChart) t.timeScale().setVisibleRange(range); });
                }
            });
        });

        // === Crosshair Sync + OHLCV Overlay ===
        const allCharts = [chart, ...subcharts];
        allCharts.forEach(sourceChart => {
            sourceChart.subscribeCrosshairMove(param => {
                const { time, point } = param;
                if (!time || !point || point.x < 0 || point.y < 0) {
                    allCharts.forEach(t => { if (t !== sourceChart) t.clearCrosshairPosition(); });
                    handleCrosshairData(null);
                    return;
                }

                // Sync crosshair
                allCharts.forEach(targetChart => {
                    if (targetChart !== sourceChart) {
                        try {
                            const x = targetChart.timeScale().timeToCoordinate(time);
                            if (x !== null) targetChart.setCrosshairPosition(50, time, mainSeries);
                        } catch (_) { /* suppress */ }
                    }
                });

                // OHLCV overlay
                const matched = dataMap.get(String(time));
                if (matched) {
                    handleCrosshairData({
                        datetime: matched.datetime,
                        open: matched.open,
                        high: matched.high,
                        low: matched.low,
                        close: matched.close,
                        volume: matched.volume,
                        change: matched.close - matched.open,
                        changePct: matched.open ? ((matched.close - matched.open) / matched.open) * 100 : 0,
                        sma_20: matched.sma_20,
                        bb_hband: matched.bb_hband,
                        bb_lband: matched.bb_lband,
                        rsi_14: matched.rsi_14,
                        macd: matched.macd,
                    });
                }

                // Measurement tool: live update when anchored
                if (measureModeRef.current && measureStateRef.current.mode === 'anchored' && matched) {
                    const x = chart.timeScale().timeToCoordinate(time);
                    const y = mainSeries.priceToCoordinate(matched.close);
                    if (x !== null && y !== null) {
                        const barIndex = data.findIndex(d => d.datetime === matched.datetime);
                        setMeasureState(prev => ({
                            ...prev,
                            target: {
                                x: x as number,
                                y: y as number,
                                price: matched.close,
                                time: matched.datetime,
                                barIndex,
                            },
                        }));
                    }
                }

                // Drawing tool: live preview
                const currentDrawingTool = drawingToolRef.current;
                if (currentDrawingTool && point && matched) {
                    const cursorPrice = (mainSeries as any).coordinateToPrice(point.y) as number | null;
                    if (cursorPrice !== null) {
                        const cursorPoint: DrawingPoint = { price: cursorPrice, time: matched.datetime };
                        if (currentDrawingTool === 'hline') {
                            setPendingDrawing(prev => ({ ...prev, cursor: cursorPoint }));
                        } else if (pendingDrawingRef.current.anchor) {
                            setPendingDrawing(prev => ({ ...prev, cursor: cursorPoint }));
                        }
                    }
                }
            });
        });

        // === Click Handler (Drawing + Measurement) ===
        chart.subscribeClick(param => {
            const { time, point } = param;
            if (!time || !point) return;

            const matched = dataMap.get(String(time));

            // --- Drawing Tool Click ---
            const currentTool = drawingToolRef.current;
            if (currentTool && matched) {
                const clickPrice = (mainSeries as any).coordinateToPrice(point.y) as number | null;
                if (clickPrice === null) return;

                const clickPoint: DrawingPoint = { price: clickPrice, time: matched.datetime };

                if (currentTool === 'hline') {
                    onAddDrawingRef.current?.({
                        id: crypto.randomUUID(),
                        type: 'hline',
                        price: clickPrice,
                    });
                    return;
                }

                // Two-click tools (trendline, fibonacci)
                const pending = pendingDrawingRef.current;
                if (!pending.anchor) {
                    setPendingDrawing(prev => ({ ...prev, anchor: clickPoint }));
                } else {
                    if (currentTool === 'trendline') {
                        onAddDrawingRef.current?.({
                            id: crypto.randomUUID(),
                            type: 'trendline',
                            p1: pending.anchor,
                            p2: clickPoint,
                        });
                    } else if (currentTool === 'fibonacci') {
                        onAddDrawingRef.current?.({
                            id: crypto.randomUUID(),
                            type: 'fibonacci',
                            p1: pending.anchor,
                            p2: clickPoint,
                        });
                    }
                }
                return;
            }

            // --- Measurement Click ---
            if (!measureModeRef.current) return;
            if (!matched) return;

            const x = chart.timeScale().timeToCoordinate(time);
            const y = mainSeries.priceToCoordinate(matched.close);
            if (x === null || y === null) return;

            const barIndex = data.findIndex(d => d.datetime === matched.datetime);
            const pt: MeasurePoint = { x: x as number, y: y as number, price: matched.close, time: matched.datetime, barIndex };

            setMeasureState(prev => {
                if (prev.mode === 'idle') {
                    return { mode: 'anchored', anchor: pt, target: null };
                } else if (prev.mode === 'anchored') {
                    return { mode: 'locked', anchor: prev.anchor, target: pt };
                } else {
                    return { mode: 'idle', anchor: null, target: null };
                }
            });
        });

        // === Resize Handler ===
        const handleResize = () => {
            if (chartContainerRef.current) chart.applyOptions({ width: chartContainerRef.current.clientWidth });
            if (activeSubcharts.rsi && rsiContainerRef.current && rsiChart) rsiChart.applyOptions({ width: rsiContainerRef.current.clientWidth });
            if (activeSubcharts.macd && macdContainerRef.current && macdChart) macdChart.applyOptions({ width: macdContainerRef.current.clientWidth });
            if (activeSubcharts.adx && adxContainerRef.current && adxChart) adxChart.applyOptions({ width: adxContainerRef.current.clientWidth });
        };

        window.addEventListener('resize', handleResize);
        if (visibleBars && chartData.length > visibleBars) {
            chart.timeScale().setVisibleLogicalRange({
                from: chartData.length - visibleBars,
                to: chartData.length - 1,
            });
        } else {
            chart.timeScale().fitContent();
        }

        return () => {
            window.removeEventListener('resize', handleResize);
            cancelAnimationFrame(rafRef.current);
            chart.remove();
            subcharts.forEach(c => c.remove());
            chartApiRef.current = null;
            mainSeriesRef.current = null;
        };
    }, [data, height, ticker, interval, activeSubcharts, chartType, activeOverlays, showSR, visibleBars, handleCrosshairData]);

    return (
        <div className="technical-chart-wrapper" style={{ display: 'flex', flexDirection: 'column', gap: '8px', width: '100%' }}>
            {/* Main Chart */}
            <div style={{ position: 'relative', width: '100%', height }}>
                <OHLCVOverlay
                    data={crosshairData}
                    latest={latest}
                    ticker={ticker}
                    interval={interval}
                    isKorean={isKorean}
                />
                <VolumeProfile
                    chart={chartApiRef.current}
                    series={mainSeriesRef.current}
                    data={data}
                    visible={showVolumeProfile}
                />
                {measureMode && (
                    <MeasurementOverlay
                        state={measureState}
                        isKorean={isKorean}
                        chart={chartApiRef.current}
                        series={mainSeriesRef.current}
                        parseTime={parseTimeRef.current}
                    />
                )}
                <DrawingOverlay
                    drawings={drawings}
                    pending={pendingDrawing}
                    chart={chartApiRef.current}
                    series={mainSeriesRef.current}
                    parseTime={parseTimeRef.current}
                    isKorean={isKorean}
                />
                <div ref={chartContainerRef} style={{
                    width: '100%',
                    height: '100%',
                    cursor: drawingTool || measureMode ? 'crosshair' : 'default',
                }} />
            </div>

            {/* Subcharts */}
            {activeSubcharts.rsi && (
                <div style={{ position: 'relative', width: '100%', height: 160 }}>
                    <div ref={rsiContainerRef} style={{ width: '100%', height: '100%' }} />
                </div>
            )}
            {activeSubcharts.macd && (
                <div style={{ position: 'relative', width: '100%', height: 160 }}>
                    <div ref={macdContainerRef} style={{ width: '100%', height: '100%' }} />
                </div>
            )}
            {activeSubcharts.adx && (
                <div style={{ position: 'relative', width: '100%', height: 160 }}>
                    <div ref={adxContainerRef} style={{ width: '100%', height: '100%' }} />
                </div>
            )}
        </div>
    );
}
