import { useState, useEffect, useRef } from 'react';
import { createChart, ColorType, type IChartApi, type Time } from 'lightweight-charts';
import { TrendingUp } from 'lucide-react';
import type { EquityPoint, MarketId } from '../../lib/api';
import { fetchEquityCurve } from '../../lib/api';
import { useSSE } from '../../hooks/useSSE';
import './MiniEquityCurve.css';

interface MiniEquityCurveProps {
    market: MarketId;
}

export function MiniEquityCurve({ market }: MiniEquityCurveProps) {
    const [data, setData] = useState<EquityPoint[]>([]);
    const chartRef = useRef<HTMLDivElement>(null);

    // SSE 실시간 업데이트 구독
    const sseData = useSSE<EquityPoint[]>(`${market}:equity_curve`);

    // 초기 로딩: REST fetch (마켓 전환 시 stale 데이터 즉시 클리어)
    useEffect(() => {
        setData([]);
        fetchEquityCurve(market).then(setData).catch(() => {});
    }, [market]);

    // SSE 데이터 수신 시 차트 업데이트
    useEffect(() => {
        if (sseData && sseData.length > 0) {
            setData(sseData);
        }
    }, [sseData]);

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
                text: 'Equity',
                color: 'rgba(255, 255, 255, 0.03)',
                fontSize: 24,
                horzAlign: 'center',
                vertAlign: 'center',
            },
        });

        const areaSeries = chart.addAreaSeries({
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
    }, [data]);

    if (data.length === 0) return null;

    return (
        <div className="mini-equity-section glass-panel">
            <h3 className="section-title">
                <TrendingUp size={16} />
                자산 곡선
            </h3>
            <div ref={chartRef} style={{ width: '100%', height: 180 }} />
        </div>
    );
}
