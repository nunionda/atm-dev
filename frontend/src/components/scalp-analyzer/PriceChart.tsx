/**
 * PriceChart — extracted from ScalpAnalyzer page.
 *
 * Phase 3.C 분할: pages/ScalpAnalyzer.tsx → components/scalp-analyzer/PriceChart.tsx
 */

import { K } from '@lib/scalpEngine';
import { useEffect, useRef, memo } from 'react';
import { createChart, ColorType, CrosshairMode, type IChartApi, type Time, LineStyle } from 'lightweight-charts';

export const PriceChart = memo(function PriceChart({ candles, ma, stdDev, entry, sl, tp15, tp2, tp3, isLong, volumeSR, maPeriod, z, dates }: {
  candles: OHLC[]; ma: number; stdDev: number;
  entry: number; sl: number; tp15: number; tp2: number; tp3: number; isLong: boolean;
  volumeSR?: VolumeSRResult | null; maPeriod: number; z: number; dates?: string[];
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!containerRef.current || candles.length < 5) return;

    // Destroy previous chart
    if (chartRef.current) { chartRef.current.remove(); chartRef.current = null; }

    const chart = createChart(containerRef.current, {
      layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: '#787b86', fontFamily: "'IBM Plex Mono','Fira Code',monospace", fontSize: 10 },
      grid: { vertLines: { color: 'rgba(255,255,255,0.03)' }, horzLines: { color: 'rgba(255,255,255,0.03)' } },
      width: containerRef.current.clientWidth,
      height: 340,
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: 'rgba(99,102,241,0.3)', width: 1, style: LineStyle.Dashed, labelBackgroundColor: '#6366f1' },
        horzLine: { color: 'rgba(99,102,241,0.3)', width: 1, style: LineStyle.Dashed, labelBackgroundColor: '#6366f1' },
      },
      timeScale: { borderColor: 'rgba(255,255,255,0.06)', rightOffset: 3, barSpacing: 8 },
      rightPriceScale: { borderColor: 'rgba(255,255,255,0.06)', scaleMargins: { top: 0.05, bottom: 0.05 } },
    });
    chartRef.current = chart;

    const show = candles.slice(-50);
    const offset = candles.length - show.length;

    // Use real dates if available, otherwise generate synthetic dates
    const hasRealDates = dates && dates.length === candles.length;
    const toTime = (i: number): Time => {
      if (hasRealDates) {
        return dates[i] as Time;
      }
      const baseDate = new Date('2025-01-01');
      const d = new Date(baseDate);
      d.setDate(d.getDate() + i);
      return d.toISOString().slice(0, 10) as Time;
    };

    // ── Candlestick series ──
    const mainSeries = chart.addCandlestickSeries({
      upColor: '#26a69a', downColor: '#ef5350',
      borderUpColor: '#26a69a', borderDownColor: '#ef5350',
      wickUpColor: '#26a69a', wickDownColor: '#ef5350',
    });
    mainSeries.setData(show.map((c, i) => ({
      time: toTime(offset + i), open: c.o, high: c.h, low: c.l, close: c.c,
    })));

    // ── Volume histogram ──
    const volSeries = chart.addHistogramSeries({
      priceFormat: { type: 'volume' },
      priceScaleId: 'vol',
    });
    chart.priceScale('vol').applyOptions({ scaleMargins: { top: 0.85, bottom: 0 } });
    volSeries.setData(show.map((c, i) => ({
      time: toTime(offset + i),
      value: c.v,
      color: c.c >= c.o ? 'rgba(38,166,154,0.25)' : 'rgba(239,83,80,0.25)',
    })));

    // ── MA line ──
    const allCloses = candles.map(c => c.c);
    const maSeries = chart.addLineSeries({
      color: '#42a5f5', lineWidth: 2, crosshairMarkerVisible: false,
      lastValueVisible: false, priceLineVisible: false, title: `MA${maPeriod}`,
    });
    const maData: { time: Time; value: number }[] = [];
    show.forEach((_, i) => {
      const idx = offset + i;
      if (idx >= maPeriod - 1) {
        let sum = 0;
        for (let j = idx - maPeriod + 1; j <= idx; j++) sum += allCloses[j];
        maData.push({ time: toTime(offset + i), value: sum / maPeriod });
      }
    });
    maSeries.setData(maData);

    // ── σ band lines ──
    const addBandLine = (price: number, color: string, title: string) => {
      const s = chart.addLineSeries({
        color, lineWidth: 1, lineStyle: LineStyle.Dotted,
        crosshairMarkerVisible: false, lastValueVisible: false, priceLineVisible: false, title,
      });
      s.setData(show.map((_, i) => ({ time: toTime(offset + i), value: price })));
    };
    addBandLine(ma + 2 * stdDev, 'rgba(249,168,37,0.5)', '+2σ');
    addBandLine(ma - 2 * stdDev, 'rgba(249,168,37,0.5)', '-2σ');
    addBandLine(ma + 1.5 * stdDev, 'rgba(120,144,156,0.4)', '+1.5σ');
    addBandLine(ma - 1.5 * stdDev, 'rgba(120,144,156,0.4)', '-1.5σ');

    // ── Price lines: Entry, SL, TP ──
    const absZ = Math.abs(z);
    const hasSignal = absZ >= 1.5;

    mainSeries.createPriceLine({
      price: entry, color: hasSignal ? K.acc : '#546e7a', lineWidth: 2,
      lineStyle: LineStyle.Solid, axisLabelVisible: true,
      title: hasSignal ? (absZ >= 2 ? 'ENTRY (STRONG)' : 'ENTRY (LEAN)') : 'NO ENTRY',
    });

    if (hasSignal) {
      mainSeries.createPriceLine({ price: sl, color: K.red, lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: 'STOP' });
      mainSeries.createPriceLine({ price: tp15, color: '#69f0ae', lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: '1.5R' });
      mainSeries.createPriceLine({ price: tp2, color: K.grn, lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: '2R' });
      mainSeries.createPriceLine({ price: tp3, color: K.grn, lineWidth: 1, lineStyle: LineStyle.Solid, axisLabelVisible: true, title: '3R' });
    }

    // ── S/R levels ──
    volumeSR?.levels.slice(0, 6).forEach((lv, i) => {
      const isS = lv.type === 'support';
      mainSeries.createPriceLine({
        price: lv.price,
        color: isS ? 'rgba(105,240,174,0.5)' : 'rgba(255,82,82,0.5)',
        lineWidth: lv.strength >= 2 ? 1 : 1,
        lineStyle: LineStyle.LargeDashed,
        axisLabelVisible: false,
        title: `${isS ? 'S' : 'R'}${i + 1} (${lv.volumeScore.toFixed(1)}x)`,
      });
    });

    // ── Signal marker on last candle ──
    const lastTime = toTime(offset + show.length - 1);
    if (hasSignal) {
      mainSeries.setMarkers([{
        time: lastTime,
        position: isLong ? 'belowBar' : 'aboveBar',
        color: isLong ? K.grn : K.red,
        shape: isLong ? 'arrowUp' : 'arrowDown',
        text: `${isLong ? 'LONG' : 'SHORT'} Z=${z.toFixed(2)}`,
      }]);
    } else {
      mainSeries.setMarkers([{
        time: lastTime,
        position: 'aboveBar',
        color: '#546e7a',
        shape: 'circle',
        text: `NO ENTRY Z=${z.toFixed(2)}`,
      }]);
    }

    // ── Resize handler ──
    const ro = new ResizeObserver(entries => {
      for (const e of entries) chart.applyOptions({ width: e.contentRect.width });
    });
    ro.observe(containerRef.current);

    return () => { ro.disconnect(); chart.remove(); chartRef.current = null; };
  }, [candles, ma, stdDev, entry, sl, tp15, tp2, tp3, isLong, volumeSR, maPeriod, z]);

  if (candles.length < 5) return null;
  return <div ref={containerRef} className="scalp-rr-vis" style={{ minHeight: 340 }} />;
});

