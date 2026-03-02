import { useEffect, useRef } from 'react';
import { createChart, ColorType, type IChartApi, type Time } from 'lightweight-charts';
import type { EquityPoint } from '../../lib/api';

interface EquityCurveProps {
    data: EquityPoint[];
    height?: number;
}

export function EquityCurve({ data, height = 320 }: EquityCurveProps) {
    const equityRef = useRef<HTMLDivElement>(null);
    const ddRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        if (!equityRef.current || !ddRef.current || data.length === 0) return;

        const chartOpts = {
            layout: {
                background: { type: ColorType.Solid as const, color: 'transparent' },
                textColor: '#787b86',
                fontFamily: "'Inter', -apple-system, sans-serif",
                fontSize: 12,
            },
            grid: {
                vertLines: { color: 'rgba(255, 255, 255, 0.04)' },
                horzLines: { color: 'rgba(255, 255, 255, 0.04)' },
            },
            rightPriceScale: { borderColor: 'rgba(255, 255, 255, 0.06)' },
            timeScale: { borderColor: 'rgba(255, 255, 255, 0.06)' },
        };

        // Equity curve
        const equityChart: IChartApi = createChart(equityRef.current, {
            ...chartOpts,
            width: equityRef.current.clientWidth,
            height,
            watermark: {
                visible: true,
                text: 'Equity Curve',
                color: 'rgba(255, 255, 255, 0.03)',
                fontSize: 32,
                horzAlign: 'center',
                vertAlign: 'center',
            },
        });

        const areaSeries = equityChart.addAreaSeries({
            topColor: 'rgba(59, 130, 246, 0.3)',
            bottomColor: 'rgba(59, 130, 246, 0.02)',
            lineColor: '#3b82f6',
            lineWidth: 2,
        });

        areaSeries.setData(
            data.map(d => ({
                time: d.date as Time,
                value: d.equity,
            }))
        );

        // Drawdown chart
        const ddChart: IChartApi = createChart(ddRef.current, {
            ...chartOpts,
            width: ddRef.current.clientWidth,
            height: 140,
            timeScale: { visible: false, borderColor: 'rgba(255, 255, 255, 0.06)' },
        });

        const ddSeries = ddChart.addAreaSeries({
            topColor: 'rgba(239, 68, 68, 0.02)',
            bottomColor: 'rgba(239, 68, 68, 0.2)',
            lineColor: '#ef4444',
            lineWidth: 1,
            invertFilledArea: true,
        });

        ddSeries.setData(
            data.map(d => ({
                time: d.date as Time,
                value: d.drawdown_pct,
            }))
        );

        // Sync timescales
        equityChart.timeScale().subscribeVisibleTimeRangeChange(range => {
            if (range) ddChart.timeScale().setVisibleRange(range);
        });
        ddChart.timeScale().subscribeVisibleTimeRangeChange(range => {
            if (range) equityChart.timeScale().setVisibleRange(range);
        });

        equityChart.timeScale().fitContent();
        ddChart.timeScale().fitContent();

        const handleResize = () => {
            if (equityRef.current) equityChart.applyOptions({ width: equityRef.current.clientWidth });
            if (ddRef.current) ddChart.applyOptions({ width: ddRef.current.clientWidth });
        };

        window.addEventListener('resize', handleResize);
        return () => {
            window.removeEventListener('resize', handleResize);
            equityChart.remove();
            ddChart.remove();
        };
    }, [data, height]);

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <div ref={equityRef} style={{ width: '100%', height }} />
            <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', padding: '0 4px' }}>Drawdown</div>
            <div ref={ddRef} style={{ width: '100%', height: 140 }} />
        </div>
    );
}
