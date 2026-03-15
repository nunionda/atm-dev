/**
 * ESF Intraday Chart — lightweight-charts 기반 캔들스틱 + 진입 계획 시각화.
 *
 * Features:
 *   - 15m 캔들스틱 + 볼륨 히스토그램
 *   - EMA 오버레이 (8/21/55)
 *   - Volume Profile 레벨 (POC/VAH/VAL/LVN)
 *   - 진입 계획: Entry/SL/TP 수평선
 *   - 서브차트: RSI, MACD, Z-Score (synchronized crosshair)
 */

import { useEffect, useRef, useCallback } from 'react';
import {
  createChart,
  ColorType,
  CrosshairMode,
  type IChartApi,
  type ISeriesApi,
  type SeriesType,
  type Time,
} from 'lightweight-charts';
import type { ESFCandle } from '../../lib/api';

// ── Types ──

export interface EntryPlan {
  direction: 'LONG' | 'SHORT';
  entry: number;
  stopLoss: number;
  takeProfit: number;
  rrRatio: number;
  multiplier: number; // 5 (MES) or 50 (ES)
}

interface SubchartState {
  rsi: boolean;
  macd: boolean;
  zscore: boolean;
}

interface ESFIntradayChartProps {
  candles: ESFCandle[];
  volumeProfile?: {
    poc: number;
    vah: number;
    val: number;
    lvn_levels: number[];
  };
  entryPlan?: EntryPlan | null;
  subcharts?: SubchartState;
  height?: number;
  ticker?: string;
}

// ── Helpers ──

function parseTime(dt: string): Time {
  const d = new Date(dt);
  return (d.getTime() / 1000) as Time;
}

/** Remove duplicate timestamps (keep last). */
function dedupByTime<T extends { time: Time }>(arr: T[]): T[] {
  const map = new Map<Time, T>();
  arr.forEach((item) => map.set(item.time, item));
  return Array.from(map.values());
}

const SHARED_CHART_OPTIONS = {
  layout: {
    background: { type: ColorType.Solid as const, color: 'transparent' },
    textColor: '#787b86',
    fontFamily: "'Inter', -apple-system, sans-serif",
    fontSize: 11,
  },
  grid: {
    vertLines: { color: 'rgba(255, 255, 255, 0.04)' },
    horzLines: { color: 'rgba(255, 255, 255, 0.04)' },
  },
  crosshair: {
    mode: CrosshairMode.Normal,
    vertLine: { color: 'rgba(99, 102, 241, 0.4)', width: 1 as const, style: 2 as const, labelBackgroundColor: '#6366f1' },
    horzLine: { color: 'rgba(99, 102, 241, 0.4)', width: 1 as const, style: 2 as const, labelBackgroundColor: '#6366f1' },
  },
  timeScale: {
    borderColor: 'rgba(255, 255, 255, 0.06)',
    timeVisible: true,
    secondsVisible: false,
    rightOffset: 5,
    barSpacing: 6,
  },
  rightPriceScale: {
    borderColor: 'rgba(255, 255, 255, 0.06)',
  },
};

const SUBCHART_OPTIONS = {
  ...SHARED_CHART_OPTIONS,
  rightPriceScale: {
    borderColor: 'rgba(255, 255, 255, 0.06)',
    scaleMargins: { top: 0.1, bottom: 0.1 },
  },
};

// ══════════════════════════════════════════
// Component
// ══════════════════════════════════════════

export default function ESFIntradayChart({
  candles,
  volumeProfile,
  entryPlan,
  subcharts = { rsi: true, macd: true, zscore: false },
  height = 420,
  ticker = 'ES=F',
}: ESFIntradayChartProps) {
  const mainRef = useRef<HTMLDivElement>(null);
  const rsiRef = useRef<HTMLDivElement>(null);
  const macdRef = useRef<HTMLDivElement>(null);
  const zscoreRef = useRef<HTMLDivElement>(null);
  const chartApiRef = useRef<IChartApi | null>(null);

  const buildChart = useCallback(() => {
    if (!mainRef.current || candles.length < 2) return;

    // Cleanup
    mainRef.current.innerHTML = '';
    if (rsiRef.current) rsiRef.current.innerHTML = '';
    if (macdRef.current) macdRef.current.innerHTML = '';
    if (zscoreRef.current) zscoreRef.current.innerHTML = '';

    // ── Parse candle data ──
    const chartData = dedupByTime(
      candles.map((c) => ({
        time: parseTime(c.datetime),
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      }))
    );

    const volumeData = dedupByTime(
      candles.map((c) => ({
        time: parseTime(c.datetime),
        value: c.volume,
        color: c.close >= c.open ? 'rgba(38, 166, 154, 0.35)' : 'rgba(239, 83, 80, 0.35)',
      }))
    );

    // ── Main Chart ──
    const chart = createChart(mainRef.current, {
      ...SHARED_CHART_OPTIONS,
      width: mainRef.current.clientWidth,
      height,
      rightPriceScale: {
        borderColor: 'rgba(255, 255, 255, 0.06)',
        scaleMargins: { top: 0.05, bottom: 0.2 },
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

    // Candlestick series
    const mainSeries: ISeriesApi<SeriesType> = chart.addCandlestickSeries({
      upColor: '#26a69a',
      downColor: '#ef5350',
      borderVisible: false,
      wickUpColor: '#26a69a',
      wickDownColor: '#ef5350',
    });
    mainSeries.setData(chartData);

    // ── EMA Overlays ──
    const emaColors = [
      { key: 'ema_fast', color: '#f59e0b', label: 'EMA8' },
      { key: 'ema_mid', color: '#3b82f6', label: 'EMA21' },
      { key: 'ema_slow', color: '#a855f7', label: 'EMA55' },
    ] as const;

    emaColors.forEach(({ key, color }) => {
      const emaData = dedupByTime(
        candles
          .filter((c) => (c as any)[key] != null)
          .map((c) => ({ time: parseTime(c.datetime), value: (c as any)[key] as number }))
      );
      if (emaData.length > 0) {
        const emaSeries = chart.addLineSeries({
          color,
          lineWidth: 1,
          crosshairMarkerVisible: false,
          lastValueVisible: false,
          priceLineVisible: false,
        });
        emaSeries.setData(emaData);
      }
    });

    // ── Bollinger Bands ──
    const bbUpper = dedupByTime(
      candles.filter((c) => c.bb_hband != null).map((c) => ({ time: parseTime(c.datetime), value: c.bb_hband! }))
    );
    const bbLower = dedupByTime(
      candles.filter((c) => c.bb_lband != null).map((c) => ({ time: parseTime(c.datetime), value: c.bb_lband! }))
    );
    if (bbUpper.length > 0) {
      const bbUpSeries = chart.addLineSeries({
        color: 'rgba(99, 102, 241, 0.3)',
        lineWidth: 1,
        lineStyle: 2,
        crosshairMarkerVisible: false,
        lastValueVisible: false,
        priceLineVisible: false,
      });
      bbUpSeries.setData(bbUpper);
    }
    if (bbLower.length > 0) {
      const bbLowSeries = chart.addLineSeries({
        color: 'rgba(99, 102, 241, 0.3)',
        lineWidth: 1,
        lineStyle: 2,
        crosshairMarkerVisible: false,
        lastValueVisible: false,
        priceLineVisible: false,
      });
      bbLowSeries.setData(bbLower);
    }

    // ── Volume Histogram ──
    const volumeSeries = chart.addHistogramSeries({
      priceFormat: { type: 'volume' },
      priceScaleId: '',
    });
    volumeSeries.priceScale().applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });
    volumeSeries.setData(volumeData);

    // ── Volume Profile Levels ──
    if (volumeProfile) {
      if (volumeProfile.poc > 0) {
        mainSeries.createPriceLine({
          price: volumeProfile.poc,
          color: 'rgba(59, 130, 246, 0.7)',
          lineWidth: 2,
          lineStyle: 0, // solid
          axisLabelVisible: true,
          title: 'POC',
        });
      }
      if (volumeProfile.vah > 0) {
        mainSeries.createPriceLine({
          price: volumeProfile.vah,
          color: 'rgba(255, 255, 255, 0.35)',
          lineWidth: 1,
          lineStyle: 2, // dashed
          axisLabelVisible: true,
          title: 'VAH',
        });
      }
      if (volumeProfile.val > 0) {
        mainSeries.createPriceLine({
          price: volumeProfile.val,
          color: 'rgba(255, 255, 255, 0.35)',
          lineWidth: 1,
          lineStyle: 2,
          axisLabelVisible: true,
          title: 'VAL',
        });
      }
      // LVN levels
      (volumeProfile.lvn_levels || []).slice(0, 5).forEach((lvn, i) => {
        if (lvn > 0) {
          mainSeries.createPriceLine({
            price: lvn,
            color: 'rgba(234, 179, 8, 0.3)',
            lineWidth: 1,
            lineStyle: 3, // dotted
            axisLabelVisible: false,
            title: i === 0 ? 'LVN' : '',
          });
        }
      });
    }

    // ── Entry Plan Overlay ──
    if (entryPlan && entryPlan.entry > 0) {
      const { direction, entry, stopLoss, takeProfit, multiplier } = entryPlan;
      const riskPts = Math.abs(entry - stopLoss);
      const rewardPts = Math.abs(takeProfit - entry);
      const riskDollar = riskPts * multiplier;
      const rewardDollar = rewardPts * multiplier;

      // Entry line (blue solid)
      mainSeries.createPriceLine({
        price: entry,
        color: '#3b82f6',
        lineWidth: 2,
        lineStyle: 0,
        axisLabelVisible: true,
        title: `${direction === 'LONG' ? '\u25B2' : '\u25BC'} Entry`,
      });

      // Stop Loss (red dashed)
      if (stopLoss > 0) {
        mainSeries.createPriceLine({
          price: stopLoss,
          color: '#ef4444',
          lineWidth: 2,
          lineStyle: 2,
          axisLabelVisible: true,
          title: `SL -$${riskDollar.toFixed(0)}`,
        });
      }

      // Take Profit (green dashed)
      if (takeProfit > 0) {
        mainSeries.createPriceLine({
          price: takeProfit,
          color: '#22c55e',
          lineWidth: 2,
          lineStyle: 2,
          axisLabelVisible: true,
          title: `TP +$${rewardDollar.toFixed(0)}`,
        });
      }
    }

    // ══════════════════════════════════════════
    // Subcharts
    // ══════════════════════════════════════════

    const subchartList: IChartApi[] = [];

    // ── RSI ──
    if (subcharts.rsi && rsiRef.current) {
      const rsiChart = createChart(rsiRef.current, {
        ...SUBCHART_OPTIONS,
        width: rsiRef.current.clientWidth,
        height: 120,
      });
      subchartList.push(rsiChart);
      const rsiSeries = rsiChart.addLineSeries({ color: '#a855f7', lineWidth: 2 });
      rsiSeries.createPriceLine({ price: 70, color: 'rgba(239, 68, 68, 0.4)', lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: 'OB' });
      rsiSeries.createPriceLine({ price: 30, color: 'rgba(34, 197, 94, 0.4)', lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: 'OS' });
      rsiSeries.createPriceLine({ price: 50, color: 'rgba(255, 255, 255, 0.1)', lineWidth: 1, lineStyle: 3, axisLabelVisible: false, title: '' });
      const rsiData = dedupByTime(
        candles.filter((c) => c.rsi_14 != null).map((c) => ({ time: parseTime(c.datetime), value: c.rsi_14! }))
      );
      rsiSeries.setData(rsiData);
    }

    // ── MACD ──
    if (subcharts.macd && macdRef.current) {
      const macdChart = createChart(macdRef.current, {
        ...SUBCHART_OPTIONS,
        width: macdRef.current.clientWidth,
        height: 120,
      });
      subchartList.push(macdChart);

      const macdLine = macdChart.addLineSeries({ color: '#3b82f6', lineWidth: 2 });
      const signalLine = macdChart.addLineSeries({ color: '#f59e0b', lineWidth: 1 });
      const histSeries = macdChart.addHistogramSeries();

      const mData: { time: Time; value: number }[] = [];
      const sData: { time: Time; value: number }[] = [];
      const hData: { time: Time; value: number; color: string }[] = [];

      candles.forEach((c) => {
        const t = parseTime(c.datetime);
        if (c.macd != null) mData.push({ time: t, value: c.macd });
        if (c.macd_signal != null) sData.push({ time: t, value: c.macd_signal });
        if (c.macd_diff != null) {
          hData.push({
            time: t,
            value: c.macd_diff,
            color: c.macd_diff >= 0 ? 'rgba(38, 166, 154, 0.6)' : 'rgba(239, 83, 80, 0.6)',
          });
        }
      });

      macdLine.setData(dedupByTime(mData));
      signalLine.setData(dedupByTime(sData));
      histSeries.setData(dedupByTime(hData));
    }

    // ── Z-Score ──
    if (subcharts.zscore && zscoreRef.current) {
      const zsChart = createChart(zscoreRef.current, {
        ...SUBCHART_OPTIONS,
        width: zscoreRef.current.clientWidth,
        height: 120,
      });
      subchartList.push(zsChart);

      const zsSeries = zsChart.addLineSeries({ color: '#06b6d4', lineWidth: 2 });
      // Zone lines
      zsSeries.createPriceLine({ price: 2, color: 'rgba(239, 68, 68, 0.4)', lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: 'Sell' });
      zsSeries.createPriceLine({ price: -2, color: 'rgba(34, 197, 94, 0.4)', lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: 'Buy' });
      zsSeries.createPriceLine({ price: 0, color: 'rgba(255, 255, 255, 0.15)', lineWidth: 1, lineStyle: 3, axisLabelVisible: false, title: '' });

      const zsData = dedupByTime(
        candles.filter((c) => c.zscore != null).map((c) => ({ time: parseTime(c.datetime), value: c.zscore! }))
      );
      zsSeries.setData(zsData);
    }

    // ── Time Scale Sync ──
    let syncing = false;
    chart.timeScale().subscribeVisibleTimeRangeChange((range) => {
      if (syncing || !range) return;
      syncing = true;
      subchartList.forEach((c) => c.timeScale().setVisibleRange(range));
      syncing = false;
    });
    subchartList.forEach((src) => {
      src.timeScale().subscribeVisibleTimeRangeChange((range) => {
        if (syncing || !range) return;
        syncing = true;
        chart.timeScale().setVisibleRange(range);
        subchartList.forEach((t) => {
          if (t !== src) t.timeScale().setVisibleRange(range);
        });
        syncing = false;
      });
    });

    // ── Crosshair Sync ──
    const allCharts = [chart, ...subchartList];
    allCharts.forEach((sourceChart) => {
      sourceChart.subscribeCrosshairMove((param) => {
        const { time, point } = param;
        if (!time || !point || point.x < 0 || point.y < 0) {
          allCharts.forEach((t) => {
            if (t !== sourceChart) t.clearCrosshairPosition();
          });
          return;
        }
        allCharts.forEach((targetChart) => {
          if (targetChart !== sourceChart) {
            targetChart.setCrosshairPosition(0, time, targetChart.timeScale() as any);
          }
        });
      });
    });

    // ── Resize Handler ──
    const handleResize = () => {
      if (!mainRef.current) return;
      const w = mainRef.current.clientWidth;
      chart.applyOptions({ width: w });
      subchartList.forEach((c) => c.applyOptions({ width: w }));
    };
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      subchartList.forEach((c) => c.remove());
      chart.remove();
    };
  }, [candles, volumeProfile, entryPlan, subcharts, height, ticker]);

  useEffect(() => {
    const cleanup = buildChart();
    return () => {
      if (cleanup) cleanup();
    };
  }, [buildChart]);

  if (candles.length < 2) {
    return (
      <div className="esf-chart-section" style={{ padding: '40px 0', textAlign: 'center', color: '#666' }}>
        Loading chart data...
      </div>
    );
  }

  return (
    <div className="esf-chart-section">
      <div ref={mainRef} className="esf-chart-container" />
      {subcharts.rsi && <div ref={rsiRef} className="esf-subchart-container" />}
      {subcharts.macd && <div ref={macdRef} className="esf-subchart-container" />}
      {subcharts.zscore && <div ref={zscoreRef} className="esf-subchart-container" />}
    </div>
  );
}
