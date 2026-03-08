import { useState, useEffect, useCallback } from 'react';
import type { IChartApi, ISeriesApi, SeriesType, Time } from 'lightweight-charts';
import type {
    Drawing, TrendLineDrawing, HorizontalLineDrawing, FibonacciDrawing,
    PendingDrawing,
} from '../../lib/drawingTypes';
import { FIB_LEVELS, FIB_COLORS } from '../../lib/drawingTypes';
import './DrawingOverlay.css';

interface DrawingOverlayProps {
    drawings: Drawing[];
    pending: PendingDrawing;
    chart: IChartApi | null;
    series: ISeriesApi<SeriesType> | null;
    parseTime: ((datetime: string) => Time) | null;
    isKorean: boolean;
}

function resolveX(
    time: string,
    chart: IChartApi | null,
    parseTime: ((datetime: string) => Time) | null,
): number | null {
    if (!chart || !parseTime || !time) return null;
    const t = parseTime(time);
    const x = chart.timeScale().timeToCoordinate(t);
    return x !== null ? (x as number) : null;
}

function resolveY(
    price: number,
    series: ISeriesApi<SeriesType> | null,
): number | null {
    if (!series) return null;
    const y = series.priceToCoordinate(price);
    return y !== null ? (y as number) : null;
}

function fmtPrice(v: number, isKr: boolean): string {
    return v.toLocaleString(undefined, { maximumFractionDigits: isKr ? 0 : 2 });
}

// --- Trend Line ---

function renderTrendLine(
    d: TrendLineDrawing,
    chart: IChartApi | null,
    series: ISeriesApi<SeriesType> | null,
    parseTime: ((datetime: string) => Time) | null,
) {
    const x1 = resolveX(d.p1.time, chart, parseTime);
    const y1 = resolveY(d.p1.price, series);
    const x2 = resolveX(d.p2.time, chart, parseTime);
    const y2 = resolveY(d.p2.price, series);
    if (x1 === null || y1 === null || x2 === null || y2 === null) return null;

    return (
        <g key={d.id}>
            <line x1={x1} y1={y1} x2={x2} y2={y2}
                stroke="rgba(99, 102, 241, 0.9)" strokeWidth={1.5} />
            <circle cx={x1} cy={y1} r={3} fill="#6366f1" />
            <circle cx={x2} cy={y2} r={3} fill="#6366f1" />
        </g>
    );
}

// --- Horizontal Line ---

function renderHorizontalLine(
    d: HorizontalLineDrawing,
    series: ISeriesApi<SeriesType> | null,
    isKorean: boolean,
) {
    const y = resolveY(d.price, series);
    if (y === null) return null;

    return (
        <g key={d.id}>
            <line x1={0} y1={y} x2="100%" y2={y}
                stroke="rgba(234, 179, 8, 0.8)" strokeWidth={1} strokeDasharray="6,4" />
            <text x={8} y={y - 4}
                fill="rgba(234, 179, 8, 0.9)" fontSize={10} fontFamily="monospace">
                {fmtPrice(d.price, isKorean)}
            </text>
        </g>
    );
}

// --- Fibonacci Retracement ---

function renderFibonacci(
    d: FibonacciDrawing,
    chart: IChartApi | null,
    series: ISeriesApi<SeriesType> | null,
    parseTime: ((datetime: string) => Time) | null,
    isKorean: boolean,
) {
    const x1 = resolveX(d.p1.time, chart, parseTime);
    const x2 = resolveX(d.p2.time, chart, parseTime);
    if (x1 === null || x2 === null) return null;

    const highPrice = Math.max(d.p1.price, d.p2.price);
    const lowPrice = Math.min(d.p1.price, d.p2.price);
    const range = highPrice - lowPrice;
    const leftX = Math.min(x1, x2);
    const rightX = Math.max(x1, x2);

    // Golden pocket shading (38.2% ~ 61.8%)
    const y382 = resolveY(highPrice - range * 0.382, series);
    const y618 = resolveY(highPrice - range * 0.618, series);

    return (
        <g key={d.id}>
            {y382 !== null && y618 !== null && (
                <rect
                    x={leftX} y={Math.min(y382, y618)}
                    width={rightX - leftX}
                    height={Math.abs(y618 - y382)}
                    fill="rgba(99, 102, 241, 0.06)"
                />
            )}
            {FIB_LEVELS.map(level => {
                const price = highPrice - range * level;
                const y = resolveY(price, series);
                if (y === null) return null;
                const color = FIB_COLORS[level];
                const isKey = level === 0.5 || level === 0.618;

                return (
                    <g key={level}>
                        <line x1={leftX} y1={y} x2={rightX} y2={y}
                            stroke={color} strokeWidth={isKey ? 1.5 : 1}
                            strokeDasharray={isKey ? 'none' : '4,3'} />
                        <line x1={0} y1={y} x2="100%" y2={y}
                            stroke={color.replace(/[\d.]+\)$/, '0.15)')}
                            strokeWidth={0.5} />
                        <text x={rightX + 6} y={y + 3}
                            fill={color} fontSize={9} fontFamily="monospace"
                            fontWeight={isKey ? 700 : 400}>
                            {(level * 100).toFixed(1)}% ({fmtPrice(price, isKorean)})
                        </text>
                    </g>
                );
            })}
        </g>
    );
}

// --- Render completed drawing ---

function renderDrawing(
    drawing: Drawing,
    chart: IChartApi | null,
    series: ISeriesApi<SeriesType> | null,
    parseTime: ((datetime: string) => Time) | null,
    isKorean: boolean,
) {
    switch (drawing.type) {
        case 'trendline':
            return renderTrendLine(drawing, chart, series, parseTime);
        case 'hline':
            return renderHorizontalLine(drawing, series, isKorean);
        case 'fibonacci':
            return renderFibonacci(drawing, chart, series, parseTime, isKorean);
    }
}

// --- Render pending preview ---

function renderPending(
    pending: PendingDrawing,
    chart: IChartApi | null,
    series: ISeriesApi<SeriesType> | null,
    parseTime: ((datetime: string) => Time) | null,
    isKorean: boolean,
) {
    if (!pending.tool || !pending.cursor) return null;

    if (pending.tool === 'hline') {
        const y = resolveY(pending.cursor.price, series);
        if (y === null) return null;
        return (
            <g key="pending-hline" opacity={0.5}>
                <line x1={0} y1={y} x2="100%" y2={y}
                    stroke="rgba(234, 179, 8, 0.6)" strokeWidth={1} strokeDasharray="6,4" />
                <text x={8} y={y - 4}
                    fill="rgba(234, 179, 8, 0.6)" fontSize={10} fontFamily="monospace">
                    {fmtPrice(pending.cursor.price, isKorean)}
                </text>
            </g>
        );
    }

    if (!pending.anchor) return null;

    const x1 = resolveX(pending.anchor.time, chart, parseTime);
    const y1 = resolveY(pending.anchor.price, series);
    const x2 = resolveX(pending.cursor.time, chart, parseTime);
    const y2 = resolveY(pending.cursor.price, series);
    if (x1 === null || y1 === null || x2 === null || y2 === null) return null;

    if (pending.tool === 'trendline') {
        return (
            <g key="pending-trendline" opacity={0.5}>
                <line x1={x1} y1={y1} x2={x2} y2={y2}
                    stroke="rgba(99, 102, 241, 0.6)" strokeWidth={1.5} strokeDasharray="4,3" />
                <circle cx={x1} cy={y1} r={3} fill="#6366f1" />
            </g>
        );
    }

    if (pending.tool === 'fibonacci') {
        const highPrice = Math.max(pending.anchor.price, pending.cursor.price);
        const lowPrice = Math.min(pending.anchor.price, pending.cursor.price);
        const range = highPrice - lowPrice;
        const leftX = Math.min(x1, x2);
        const rightX = Math.max(x1, x2);

        return (
            <g key="pending-fib" opacity={0.4}>
                {FIB_LEVELS.map(level => {
                    const price = highPrice - range * level;
                    const y = resolveY(price, series);
                    if (y === null) return null;
                    return (
                        <line key={level}
                            x1={leftX} y1={y} x2={rightX} y2={y}
                            stroke={FIB_COLORS[level]} strokeWidth={1} strokeDasharray="3,3" />
                    );
                })}
            </g>
        );
    }

    return null;
}

// --- Main Component ---

export function DrawingOverlay({ drawings, pending, chart, series, parseTime, isKorean }: DrawingOverlayProps) {
    const [, setTick] = useState(0);
    const refresh = useCallback(() => setTick(t => t + 1), []);

    useEffect(() => {
        if (!chart) return;
        chart.timeScale().subscribeVisibleLogicalRangeChange(refresh);
        return () => chart.timeScale().unsubscribeVisibleLogicalRangeChange(refresh);
    }, [chart, refresh]);

    const hasContent = drawings.length > 0 || pending.tool !== null;
    if (!hasContent) return null;

    return (
        <div className="drawing-overlay">
            <svg>
                {drawings.map(d => renderDrawing(d, chart, series, parseTime, isKorean))}
                {renderPending(pending, chart, series, parseTime, isKorean)}
            </svg>
        </div>
    );
}
