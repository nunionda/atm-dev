/**
 * FuturesPriceChart — extracted from FuturesTrading page.
 *
 * Phase 3.C 분할: pages/FuturesTrading.tsx → components/futures-trading/FuturesPriceChart.tsx
 */

import { useState, useEffect, useRef } from 'react';
import { createChart, ColorType, type IChartApi, type Time } from 'lightweight-charts';
import { fetchAnalyticsData } from '@lib/api';
import { ChartSkeleton } from '@components/common/Skeleton';

export function FuturesPriceChart({ ticker }: { ticker: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    let cancelled = false;

    (async () => {
      try {
        const resp = await fetchAnalyticsData(ticker, '6mo', '1d');
        const data = resp?.data;
        if (cancelled || !data || !data.length || !containerRef.current) return;

        if (chartRef.current) {
          chartRef.current.remove();
        }

        const chart = createChart(containerRef.current, {
          width: containerRef.current.clientWidth,
          height: 400,
          layout: {
            background: { type: ColorType.Solid, color: 'transparent' },
            textColor: '#888',
          },
          grid: {
            vertLines: { color: 'rgba(255,255,255,0.03)' },
            horzLines: { color: 'rgba(255,255,255,0.03)' },
          },
          rightPriceScale: { borderColor: '#333' },
          timeScale: { borderColor: '#333' },
        });
        chartRef.current = chart;

        const candleSeries = chart.addCandlestickSeries({
          upColor: '#2ecc71',
          downColor: '#e74c3c',
          borderUpColor: '#2ecc71',
          borderDownColor: '#e74c3c',
          wickUpColor: '#2ecc71',
          wickDownColor: '#e74c3c',
        });

        // Deduplicate and sort (API uses 'datetime' field)
        const seen = new Set<string>();
        const candles = data
          .filter((d: any) => {
            const dt = d.datetime || d.date;
            if (!dt || seen.has(dt)) return false;
            seen.add(dt);
            return d.open && d.high && d.low && d.close;
          })
          .sort((a: any, b: any) => (a.datetime || a.date).localeCompare(b.datetime || b.date))
          .map((d: any) => ({
            time: (d.datetime || d.date) as Time,
            open: d.open,
            high: d.high,
            low: d.low,
            close: d.close,
          }));

        candleSeries.setData(candles);

        // SMA overlays (API uses sma_5, sma_20, sma_50)
        const smaConfigs = [
          { key: 'sma_5', color: '#3498db' },
          { key: 'sma_20', color: '#e67e22' },
          { key: 'sma_50', color: '#9b59b6' },
        ];
        for (const { key, color } of smaConfigs) {
          const smaData = data
            .filter((d: any) => d[key] != null)
            .map((d: any) => ({ time: (d.datetime || d.date) as Time, value: d[key] }));
          if (smaData.length > 10) {
            const line = chart.addLineSeries({ color, lineWidth: 1 });
            line.setData(smaData);
          }
        }

        // Volume
        const volSeries = chart.addHistogramSeries({
          color: '#555',
          priceFormat: { type: 'volume' },
          priceScaleId: '',
        });
        volSeries.priceScale().applyOptions({
          scaleMargins: { top: 0.85, bottom: 0 },
        });
        volSeries.setData(
          data
            .filter((d: any) => d.volume)
            .map((d: any) => ({
              time: (d.datetime || d.date) as Time,
              value: d.volume,
              color: d.close >= d.open ? 'rgba(46,204,113,0.3)' : 'rgba(231,76,60,0.3)',
            }))
        );

        chart.timeScale().fitContent();

        const ro = new ResizeObserver(() => {
          if (containerRef.current) {
            chart.applyOptions({ width: containerRef.current.clientWidth });
          }
        });
        ro.observe(containerRef.current);

        return () => {
          ro.disconnect();
          chart.remove();
          chartRef.current = null;
        };
      } catch (err: any) {
        // AbortError는 React StrictMode 이중 마운트로 인한 정상 동작 — 무시
        if (err?.name === 'AbortError') return;
        console.error('Chart load error:', err);
      }
    })();

    return () => {
      cancelled = true;
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
      }
    };
  }, [ticker]);

  return (
    <div className="futures-chart-container">
      <div ref={containerRef} style={{ minHeight: 400 }} />
    </div>
  );
}

// ══════════════════════════════════════════
// Scalp Analyzer — Gauge Components
// ══════════════════════════════════════════

