/**
 * ESFEquityCurve — lightweight-charts 기반 인터랙티브 Equity Curve.
 *
 * Features:
 *   - Line + Area fill for equity
 *   - Trade markers (win ▲ green, loss ▼ red)
 *   - Drawdown band (red-tinted area below equity)
 *   - Crosshair for exact values
 */

import { useEffect, useRef, useCallback } from 'react';
import {
  createChart,
  ColorType,
  CrosshairMode,
  type IChartApi,
  type Time,
} from 'lightweight-charts';
import type { IntradayTrade } from '../../lib/api';

interface ESFEquityCurveProps {
  equityCurve: { timestamp: string; equity: number }[];
  trades?: IntradayTrade[];
  height?: number;
}

function parseTime(dt: string): Time {
  const d = new Date(dt);
  return (d.getTime() / 1000) as Time;
}

function dedupByTime<T extends { time: Time }>(arr: T[]): T[] {
  const map = new Map<Time, T>();
  arr.forEach((item) => map.set(item.time, item));
  return Array.from(map.values());
}

export default function ESFEquityCurve({
  equityCurve,
  trades,
  height = 200,
}: ESFEquityCurveProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  const buildChart = useCallback(() => {
    if (!containerRef.current || equityCurve.length < 2) return;

    containerRef.current.innerHTML = '';

    const chart = createChart(containerRef.current, {
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
      width: containerRef.current.clientWidth,
      height,
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: 'rgba(99, 102, 241, 0.4)', width: 1, style: 2, labelBackgroundColor: '#6366f1' },
        horzLine: { color: 'rgba(99, 102, 241, 0.4)', width: 1, style: 2, labelBackgroundColor: '#6366f1' },
      },
      timeScale: {
        borderColor: 'rgba(255, 255, 255, 0.06)',
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 3,
        barSpacing: 4,
      },
      rightPriceScale: {
        borderColor: 'rgba(255, 255, 255, 0.06)',
        scaleMargins: { top: 0.1, bottom: 0.15 },
      },
    });

    chartRef.current = chart;

    // ── Equity Line + Area ──
    const equityData = dedupByTime(
      equityCurve.map((d) => ({
        time: parseTime(d.timestamp),
        value: d.equity,
      }))
    );

    const areaSeries = chart.addAreaSeries({
      topColor: 'rgba(59, 130, 246, 0.25)',
      bottomColor: 'rgba(59, 130, 246, 0.02)',
      lineColor: '#3b82f6',
      lineWidth: 2,
      crosshairMarkerVisible: true,
      lastValueVisible: true,
      priceLineVisible: true,
    });
    areaSeries.setData(equityData);

    // ── Drawdown Band ──
    let runningMax = equityCurve[0].equity;
    const ddData = dedupByTime(
      equityCurve.map((d) => {
        const eq = d.equity;
        if (eq > runningMax) runningMax = eq;
        const dd = ((eq - runningMax) / runningMax) * 100;
        return { time: parseTime(d.timestamp), value: dd };
      })
    );

    const ddSeries = chart.addHistogramSeries({
      priceScaleId: 'dd',
      color: 'rgba(239, 68, 68, 0.3)',
    });
    ddSeries.priceScale().applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });
    ddSeries.setData(ddData);

    // ── Trade Markers ──
    if (trades && trades.length > 0) {
      const markers = trades.map((t) => {
        const isWin = (t.pnl ?? 0) > 0;
        return {
          time: parseTime(t.exit_time || t.entry_time),
          position: isWin ? ('belowBar' as const) : ('aboveBar' as const),
          color: isWin ? '#22c55e' : '#ef4444',
          shape: isWin ? ('arrowUp' as const) : ('arrowDown' as const),
          text: `$${Math.abs(t.pnl ?? 0).toFixed(0)}`,
        };
      });

      // Sort markers by time (required by lightweight-charts)
      markers.sort((a, b) => (a.time as number) - (b.time as number));
      (areaSeries as any).setMarkers(markers);
    }

    // ── Initial equity line ──
    if (equityCurve.length > 0) {
      areaSeries.createPriceLine({
        price: equityCurve[0].equity,
        color: 'rgba(255, 255, 255, 0.2)',
        lineWidth: 1,
        lineStyle: 2,
        axisLabelVisible: true,
        title: 'Initial',
      });
    }

    // ── Resize ──
    const handleResize = () => {
      if (!containerRef.current) return;
      chart.applyOptions({ width: containerRef.current.clientWidth });
    };
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
    };
  }, [equityCurve, trades, height]);

  useEffect(() => {
    const cleanup = buildChart();
    return () => {
      if (cleanup) cleanup();
    };
  }, [buildChart]);

  if (equityCurve.length < 2) return null;

  return (
    <div className="esf-equity-curve-interactive">
      <div className="esf-panel-title" style={{ marginBottom: 8 }}>
        Equity Curve
      </div>
      <div ref={containerRef} style={{ borderRadius: 8, overflow: 'hidden' }} />
    </div>
  );
}
