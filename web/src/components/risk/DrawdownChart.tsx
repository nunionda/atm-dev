import { useState, useEffect, useRef } from 'react';
import { createChart, ColorType, LineStyle, type IChartApi, type Time } from 'lightweight-charts';
import { TrendingDown } from 'lucide-react';
import type { EquityPoint, MarketId } from '../../lib/api';
import { fetchEquityCurve } from '../../lib/api';
import './DrawdownChart.css';

interface DrawdownChartProps {
    market: MarketId;
    mddLimit: number;
}

export function DrawdownChart({ market, mddLimit }: DrawdownChartProps) {
    const [data, setData] = useState<EquityPoint[]>([]);
    const chartRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        fetchEquityCurve(market).then(setData).catch(() => {});
    }, [market]);

    useEffect(() => {
        if (!chartRef.current || data.length === 0) return;

        const chart: IChartApi = createChart(chartRef.current, {
            width: chartRef.current.clientWidth,
            height: 180,
            layout: {
                background: { type: ColorType.Solid, color: 'transparent' },
                textColor: '#787b86',
                fontFamily: "'Inter', -apple-system, sans-serif",
                fontSize: 11,
            },
            grid: {
                vertLines: { color: 'rgba(255, 255, 255, 0.03)' },
                horzLines: { color: 'rgba(255, 255, 255, 0.03)' },
            },
            rightPriceScale: { borderColor: 'rgba(255, 255, 255, 0.06)' },
            timeScale: { borderColor: 'rgba(255, 255, 255, 0.06)' },
            watermark: {
                visible: true,
                text: 'Drawdown',
                color: 'rgba(255, 255, 255, 0.03)',
                fontSize: 24,
                horzAlign: 'center',
                vertAlign: 'center',
            },
        });

        // Drawdown area (inverted — fill goes downward)
        const ddSeries = chart.addAreaSeries({
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

        // MDD limit line (dashed red horizontal)
        if (data.length >= 2) {
            const limitSeries = chart.addLineSeries({
                color: 'rgba(239, 68, 68, 0.5)',
                lineWidth: 1,
                lineStyle: LineStyle.Dashed,
                crosshairMarkerVisible: false,
                lastValueVisible: true,
                priceLineVisible: false,
            });

            limitSeries.setData([
                { time: data[0].date as Time, value: mddLimit },
                { time: data[data.length - 1].date as Time, value: mddLimit },
            ]);
        }

        chart.timeScale().fitContent();

        const handleResize = () => {
            if (chartRef.current) {
                chart.applyOptions({ width: chartRef.current.clientWidth });
            }
        };

        window.addEventListener('resize', handleResize);
        return () => {
            window.removeEventListener('resize', handleResize);
            chart.remove();
        };
    }, [data, mddLimit]);

    if (data.length === 0) return null;

    return (
        <div className="drawdown-section glass-panel">
            <h3 className="section-title">
                <TrendingDown size={16} />
                드로다운 추이
                <span className="dd-limit-label">MDD 한도 {mddLimit}%</span>
            </h3>
            <div ref={chartRef} style={{ width: '100%', height: 180 }} />
        </div>
    );
}
