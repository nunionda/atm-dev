import { useState, useEffect, useCallback } from 'react';
import type { IChartApi, ISeriesApi, SeriesType, Time } from 'lightweight-charts';
import './MeasurementOverlay.css';

export interface MeasurePoint {
    x: number;
    y: number;
    price: number;
    time: string;
    barIndex: number;
}

export interface MeasureState {
    mode: 'idle' | 'anchored' | 'locked';
    anchor: MeasurePoint | null;
    target: MeasurePoint | null;
}

interface MeasurementOverlayProps {
    state: MeasureState;
    isKorean: boolean;
    chart: IChartApi | null;
    series: ISeriesApi<SeriesType> | null;
    parseTime: ((datetime: string) => Time) | null;
}

function fmtPrice(v: number, isKr: boolean): string {
    return v.toLocaleString(undefined, { maximumFractionDigits: isKr ? 0 : 2 });
}

function resolveCoords(
    point: MeasurePoint,
    chart: IChartApi | null,
    series: ISeriesApi<SeriesType> | null,
    parseTime: ((datetime: string) => Time) | null,
): { x: number; y: number } | null {
    if (!chart || !series || !parseTime) return { x: point.x, y: point.y };
    const t = parseTime(point.time);
    const x = chart.timeScale().timeToCoordinate(t);
    const y = series.priceToCoordinate(point.price);
    if (x === null || y === null) return null;
    return { x: x as number, y: y as number };
}

export function MeasurementOverlay({ state, isKorean, chart, series, parseTime }: MeasurementOverlayProps) {
    const { anchor, target } = state;

    // Re-render on viewport changes (pan/zoom)
    const [, setTick] = useState(0);
    const refresh = useCallback(() => setTick(t => t + 1), []);

    useEffect(() => {
        if (!chart || state.mode === 'idle') return;
        chart.timeScale().subscribeVisibleLogicalRangeChange(refresh);
        return () => chart.timeScale().unsubscribeVisibleLogicalRangeChange(refresh);
    }, [chart, state.mode, refresh]);

    if (!anchor) return null;

    const anchorCoords = resolveCoords(anchor, chart, series, parseTime);
    if (!anchorCoords) return null;

    const showLine = target && (state.mode === 'anchored' || state.mode === 'locked');

    if (!showLine || !target) {
        return (
            <div className="measure-overlay">
                <div
                    className="measure-anchor"
                    style={{ left: anchorCoords.x, top: anchorCoords.y }}
                />
            </div>
        );
    }

    const targetCoords = resolveCoords(target, chart, series, parseTime);
    if (!targetCoords) return null;

    const priceDiff = target.price - anchor.price;
    const pctChange = anchor.price !== 0 ? (priceDiff / anchor.price) * 100 : 0;
    const barCount = Math.abs(target.barIndex - anchor.barIndex);
    const isUp = priceDiff >= 0;

    const midX = (anchorCoords.x + targetCoords.x) / 2;
    const midY = (anchorCoords.y + targetCoords.y) / 2;

    return (
        <div className="measure-overlay">
            <svg>
                <line
                    x1={anchorCoords.x} y1={anchorCoords.y}
                    x2={targetCoords.x} y2={targetCoords.y}
                    stroke="rgba(99, 102, 241, 0.8)"
                    strokeWidth={1.5}
                    strokeDasharray="4,3"
                />
            </svg>
            <div className="measure-anchor" style={{ left: anchorCoords.x, top: anchorCoords.y }} />
            <div className="measure-anchor" style={{ left: targetCoords.x, top: targetCoords.y }} />
            <div className="measure-label" style={{ left: midX, top: midY }}>
                <span className={`measure-pct ${isUp ? 'up' : 'down'}`}>
                    {isUp ? '+' : ''}{pctChange.toFixed(2)}%
                </span>
                <span className="measure-price">
                    {isUp ? '+' : ''}{fmtPrice(priceDiff, isKorean)}
                </span>
                <span className="measure-bars">{barCount} bars</span>
            </div>
        </div>
    );
}
