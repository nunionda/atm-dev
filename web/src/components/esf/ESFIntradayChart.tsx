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
import type { ESFCandle, VWATRZone } from '../../lib/api';

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
  atr: boolean;
  adx: boolean;
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
  vwatrZones?: VWATRZone[];
  subcharts?: SubchartState;
  height?: number;
  ticker?: string;
}

// Rolling average helper
function rollingAvg(candles: ESFCandle[], key: 'atr_14', window: number): { time: Time; value: number }[] {
  return dedupByTime(
    candles
      .filter((c) => c[key] != null)
      .map((c, idx, arr) => {
        const slice = arr.slice(Math.max(0, idx - window + 1), idx + 1).filter((x) => x[key] != null);
        const avg = slice.reduce((s, x) => s + (x[key] as number), 0) / slice.length;
        return { time: parseTime(c.datetime), value: avg };
      })
  );
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
  handleScroll: {
    mouseWheel: false,
    pressedMouseMove: true,
    horzTouchDrag: true,
    vertTouchDrag: false,
  },
  handleScale: {
    mouseWheel: false,
    pinch: false,
    axisPressedMouseMove: { time: true, price: true }, // 축 드래그로 스케일 조정 허용
    axisDoubleClickReset: true,
  },
  timeScale: {
    borderColor: 'rgba(255, 255, 255, 0.06)',
    timeVisible: true,
    secondsVisible: false,
    rightOffset: 12,
    barSpacing: 6,
  },
  rightPriceScale: {
    borderColor: 'rgba(255, 255, 255, 0.06)',
    minimumWidth: 72,
  },
};

const SUBCHART_OPTIONS = {
  ...SHARED_CHART_OPTIONS,
  rightPriceScale: {
    borderColor: 'rgba(255, 255, 255, 0.06)',
    scaleMargins: { top: 0.1, bottom: 0.1 },
  },
};

// ── Right-axis label deconfliction overlay ──
interface AxisLabelItem {
  price: number;
  text: string;
  color: string;
}

function updateAxisLabels(
  series: ISeriesApi<SeriesType>,
  items: AxisLabelItem[],
  overlay: HTMLDivElement,
  chartHeight: number,
) {
  const MIN_GAP = 16;
  const LABEL_H = 14;

  const mapped = items
    .map((item) => {
      const y = series.priceToCoordinate(item.price);
      return { ...item, origY: (y ?? -1) as number, labelY: (y ?? -1) as number };
    })
    .filter((r) => r.origY >= 0 && r.origY <= chartHeight)
    .sort((a, b) => a.origY - b.origY);

  // Downward pass — push overlapping labels down
  for (let i = 1; i < mapped.length; i++) {
    if (mapped[i].labelY - mapped[i - 1].labelY < MIN_GAP) {
      mapped[i].labelY = mapped[i - 1].labelY + MIN_GAP;
    }
  }
  // Upward pass — fix any that got pushed below bottom
  for (let i = mapped.length - 2; i >= 0; i--) {
    if (mapped[i + 1].labelY - mapped[i].labelY < MIN_GAP) {
      mapped[i].labelY = mapped[i + 1].labelY - MIN_GAP;
    }
  }

  overlay.innerHTML = '';
  mapped.forEach((item) => {
    const lY = Math.round(item.labelY) - Math.floor(LABEL_H / 2);
    if (lY < -LABEL_H || lY > chartHeight + LABEL_H) return;

    // Horizontal tick at original price when label was moved
    if (Math.abs(item.labelY - item.origY) > 4) {
      const tick = document.createElement('div');
      tick.style.cssText = [
        'position:absolute', 'right:0',
        `top:${Math.round(item.origY)}px`,
        'width:6px', 'height:1px',
        `background:${item.color}`, 'opacity:0.6',
      ].join(';');
      overlay.appendChild(tick);
    }

    const el = document.createElement('div');
    el.style.cssText = [
      'position:absolute', 'right:0',
      `top:${lY}px`,
      `background:${item.color}`,
      'color:#fff',
      'font-size:9px',
      "font-family:'IBM Plex Mono',monospace",
      'font-weight:700',
      'padding:1px 4px',
      'border-radius:2px 0 0 2px',
      'white-space:nowrap',
      'line-height:1.4',
      'text-shadow:0 1px 2px rgba(0,0,0,0.6)',
      'pointer-events:none',
      'max-width:70px',
      'overflow:hidden',
      'text-overflow:ellipsis',
    ].join(';');
    // Shorten label: "VWATR S1 (SMA9)" → "S1", "Mag MA" → "Mag"
    const shortText = item.text
      .replace(/^VWATR /, '')
      .replace(/\s*\([^)]*\)/, '');
    el.textContent = `${shortText} ${item.price.toFixed(1)}`;
    overlay.appendChild(el);
  });
}

// ══════════════════════════════════════════
// Component
// ══════════════════════════════════════════

export default function ESFIntradayChart({
  candles,
  volumeProfile,
  entryPlan,
  vwatrZones,
  subcharts = { rsi: true, macd: true, zscore: false, atr: true, adx: true },
  height = 420,
  ticker = 'ES=F',
}: ESFIntradayChartProps) {
  const mainRef = useRef<HTMLDivElement>(null);
  const overlayRef = useRef<HTMLDivElement>(null);
  const rsiRef = useRef<HTMLDivElement>(null);
  const macdRef = useRef<HTMLDivElement>(null);
  const zscoreRef = useRef<HTMLDivElement>(null);
  const atrRef = useRef<HTMLDivElement>(null);
  const adxRef = useRef<HTMLDivElement>(null);
  const chartApiRef = useRef<IChartApi | null>(null);

  const buildChart = useCallback(() => {
    if (!mainRef.current || candles.length < 2) return;

    // Cleanup
    mainRef.current.innerHTML = '';
    if (rsiRef.current) rsiRef.current.innerHTML = '';
    if (macdRef.current) macdRef.current.innerHTML = '';
    if (zscoreRef.current) zscoreRef.current.innerHTML = '';
    if (atrRef.current) atrRef.current.innerHTML = '';
    if (adxRef.current) adxRef.current.innerHTML = '';

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

    // ── Main Chart — 16:9 동적 높이 ──
    const containerWidth = mainRef.current.clientWidth;
    const chartHeight = Math.max(Math.round(containerWidth * 9 / 16), 300);
    const chart = createChart(mainRef.current, {
      ...SHARED_CHART_OPTIONS,
      width: containerWidth,
      height: chartHeight,
      rightPriceScale: {
        borderColor: 'rgba(255, 255, 255, 0.06)',
        scaleMargins: { top: 0.08, bottom: 0.22 },
        minimumWidth: 72,
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

    // ── Right-axis label overlay (deconflicted) ──
    // overlayRef is rendered in JSX as a sibling, outside chart canvas control
    const axisOverlay = overlayRef.current;
    if (axisOverlay) {
      axisOverlay.innerHTML = '';
      axisOverlay.style.height = `${chartHeight}px`;
    }
    const axisLabelItems: AxisLabelItem[] = [];

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
          lineWidth: 2,
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

    // ── Magnetic MA (가장 자력 강한 MA) ──
    const magneticData = dedupByTime(
      candles
        .filter((c) => c.magnetic_ma != null)
        .map((c) => ({ time: parseTime(c.datetime), value: c.magnetic_ma! }))
    );
    if (magneticData.length > 0) {
      const magneticSeries = chart.addLineSeries({
        color: '#ff6b6b',
        lineWidth: 2,
        lineStyle: 0,
        crosshairMarkerVisible: true,
        lastValueVisible: false, // overlay handles label
        priceLineVisible: false,
        title: '',
      });
      magneticSeries.setData(magneticData);
      const lastMag = magneticData[magneticData.length - 1]?.value;
      if (lastMag) axisLabelItems.push({ price: lastMag, text: 'Mag MA', color: '#c0392b' });
    }

    // ── VWATR S/R Zones (top 2 SUPPORT + top 2 RESISTANCE) ──
    if (vwatrZones && vwatrZones.length > 0) {
      // strength 순으로 이미 정렬됨 — 타입별 최대 2개씩 선택
      const supZones = vwatrZones.filter((z) => z.zone_type === 'SUPPORT').slice(0, 2);
      const resZones = vwatrZones.filter((z) => z.zone_type === 'RESISTANCE').slice(0, 2);
      const topZones = [...supZones, ...resZones];
      // 타입별 독립 카운터 (S1/S2, R1/R2)
      const typeCounter: Record<string, number> = { SUPPORT: 0, RESISTANCE: 0 };
      topZones.forEach((zone) => {
        const isSup = zone.zone_type === 'SUPPORT';
        typeCounter[zone.zone_type] += 1;
        const rank = typeCounter[zone.zone_type];
        const color = isSup ? 'rgba(34, 197, 94, 0.6)' : 'rgba(239, 68, 68, 0.6)';
        const label = `VWATR ${isSup ? 'S' : 'R'}${rank} (${zone.ma_type}${zone.ma_period})`;

        // Zone upper edge
        mainSeries.createPriceLine({
          price: isSup ? zone.support_upper : zone.resistance_upper,
          color: color,
          lineWidth: 2,
          lineStyle: 2, // Dashed
          axisLabelVisible: false,
          title: '',
        });
        // Zone lower edge
        mainSeries.createPriceLine({
          price: isSup ? zone.support_lower : zone.resistance_lower,
          color: color,
          lineWidth: 2,
          lineStyle: 2,
          axisLabelVisible: false,
          title: '',
        });
        // Zone center (MA value) — overlay handles axis label
        mainSeries.createPriceLine({
          price: zone.ma_value,
          color: color,
          lineWidth: 3,
          lineStyle: 0, // Solid — 중심선은 실선으로 강조
          axisLabelVisible: false,
          title: '',
        });
        // Solid color for overlay label
        const solidColor = isSup ? '#22c55e' : '#ef4444';
        axisLabelItems.push({ price: zone.ma_value, text: label, color: solidColor });
      });
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
          lineStyle: 0,
          axisLabelVisible: false,
          title: '',
        });
        axisLabelItems.push({ price: volumeProfile.poc, text: 'POC', color: '#3b82f6' });
      }
      if (volumeProfile.vah > 0) {
        mainSeries.createPriceLine({
          price: volumeProfile.vah,
          color: 'rgba(255, 255, 255, 0.35)',
          lineWidth: 1,
          lineStyle: 2,
          axisLabelVisible: false,
          title: '',
        });
        axisLabelItems.push({ price: volumeProfile.vah, text: 'VAH', color: '#6b7280' });
      }
      if (volumeProfile.val > 0) {
        mainSeries.createPriceLine({
          price: volumeProfile.val,
          color: 'rgba(255, 255, 255, 0.35)',
          lineWidth: 1,
          lineStyle: 2,
          axisLabelVisible: false,
          title: '',
        });
        axisLabelItems.push({ price: volumeProfile.val, text: 'VAL', color: '#6b7280' });
      }
      // LVN levels
      (volumeProfile.lvn_levels || []).slice(0, 5).forEach((lvn) => {
        if (lvn > 0) {
          mainSeries.createPriceLine({
            price: lvn,
            color: 'rgba(234, 179, 8, 0.3)',
            lineWidth: 1,
            lineStyle: 3, // dotted
            axisLabelVisible: false,
            title: '',
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

    // ── ATR(14) ──
    if (subcharts.atr && atrRef.current) {
      const atrChart = createChart(atrRef.current, {
        ...SUBCHART_OPTIONS,
        width: atrRef.current.clientWidth,
        height: 100,
        watermark: {
          visible: true,
          text: 'ATR(14)',
          color: 'rgba(245, 158, 11, 0.08)',
          fontSize: 28,
          horzAlign: 'center',
          vertAlign: 'center',
        },
      });
      subchartList.push(atrChart);

      // ATR line
      const atrSeries = atrChart.addLineSeries({
        color: '#f59e0b',
        lineWidth: 2,
        crosshairMarkerVisible: true,
        lastValueVisible: true,
        priceLineVisible: false,
        title: 'ATR',
      });

      // 20-bar rolling average (reference)
      const atrAvgSeries = atrChart.addLineSeries({
        color: 'rgba(255, 255, 255, 0.25)',
        lineWidth: 1,
        lineStyle: 2,
        crosshairMarkerVisible: false,
        lastValueVisible: false,
        priceLineVisible: false,
        title: 'Avg',
      });

      const atrData = dedupByTime(
        candles
          .filter((c) => c.atr_14 != null)
          .map((c) => ({ time: parseTime(c.datetime), value: c.atr_14! }))
      );
      const atrAvgData = rollingAvg(candles, 'atr_14', 20);

      atrSeries.setData(atrData);
      atrAvgSeries.setData(atrAvgData);
    }

    // ── ADX / DMI ──
    if (subcharts.adx && adxRef.current) {
      const adxChart = createChart(adxRef.current, {
        ...SUBCHART_OPTIONS,
        width: adxRef.current.clientWidth,
        height: 100,
        watermark: {
          visible: true,
          text: 'ADX / DMI',
          color: 'rgba(255, 255, 255, 0.05)',
          fontSize: 28,
          horzAlign: 'center',
          vertAlign: 'center',
        },
      });
      subchartList.push(adxChart);

      // ADX line (trend strength)
      const adxLine = adxChart.addLineSeries({
        color: '#e0e0e0',
        lineWidth: 2,
        crosshairMarkerVisible: true,
        lastValueVisible: true,
        priceLineVisible: false,
        title: 'ADX',
      });
      // +DI (bullish pressure)
      const plusDiLine = adxChart.addLineSeries({
        color: '#22c55e',
        lineWidth: 1.5,
        crosshairMarkerVisible: false,
        lastValueVisible: true,
        priceLineVisible: false,
        title: '+DI',
      });
      // -DI (bearish pressure)
      const minusDiLine = adxChart.addLineSeries({
        color: '#ef4444',
        lineWidth: 1.5,
        crosshairMarkerVisible: false,
        lastValueVisible: true,
        priceLineVisible: false,
        title: '-DI',
      });

      // Reference levels
      adxLine.createPriceLine({ price: 40, color: 'rgba(245, 158, 11, 0.45)', lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: 'Strong' });
      adxLine.createPriceLine({ price: 25, color: 'rgba(59, 130, 246, 0.45)', lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: 'Trend' });
      adxLine.createPriceLine({ price: 20, color: 'rgba(255, 255, 255, 0.12)', lineWidth: 1, lineStyle: 3, axisLabelVisible: false, title: '' });

      const adxData = dedupByTime(
        candles.filter((c) => c.adx != null).map((c) => ({ time: parseTime(c.datetime), value: c.adx! }))
      );
      const plusDiData = dedupByTime(
        candles.filter((c) => c.plus_di != null).map((c) => ({ time: parseTime(c.datetime), value: c.plus_di! }))
      );
      const minusDiData = dedupByTime(
        candles.filter((c) => c.minus_di != null).map((c) => ({ time: parseTime(c.datetime), value: c.minus_di! }))
      );

      adxLine.setData(adxData);
      plusDiLine.setData(plusDiData);
      minusDiLine.setData(minusDiData);
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

    // ── Axis Label Overlay — subscribe + initial render ──
    const refreshAxisLabels = () => {
      if (axisOverlay) updateAxisLabels(mainSeries, axisLabelItems, axisOverlay, chartHeight);
    };
    chart.timeScale().subscribeVisibleLogicalRangeChange(refreshAxisLabels);
    // Initial render after layout settles
    setTimeout(refreshAxisLabels, 80);

    // Y축 드래그 시에도 라벨 갱신 — pointerdown 중 pointermove에서 호출
    let dragging = false;
    const chartContainer = mainRef.current!;
    const onPointerDown = () => { dragging = true; };
    const onPointerUp = () => { dragging = false; refreshAxisLabels(); };
    const onPointerMove = () => { if (dragging) refreshAxisLabels(); };
    chartContainer.addEventListener('pointerdown', onPointerDown);
    window.addEventListener('pointerup', onPointerUp);
    chartContainer.addEventListener('pointermove', onPointerMove);

    // ── Resize Handler — 16:9 비율 유지 ──
    const handleResize = () => {
      if (!mainRef.current) return;
      const w = mainRef.current.clientWidth;
      const h = Math.max(Math.round(w * 9 / 16), 300);
      chart.applyOptions({ width: w, height: h });
      if (axisOverlay) axisOverlay.style.height = `${h}px`;
      subchartList.forEach((c) => c.applyOptions({ width: w }));
      refreshAxisLabels();
    };
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chartContainer.removeEventListener('pointerdown', onPointerDown);
      window.removeEventListener('pointerup', onPointerUp);
      chartContainer.removeEventListener('pointermove', onPointerMove);
      subchartList.forEach((c) => c.remove());
      chart.remove();
    };
  }, [candles, volumeProfile, entryPlan, vwatrZones, subcharts, ticker]);

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

  // ── Legend items ──
  const MONO = "'IBM Plex Mono', monospace";
  type LegendItem = { color: string; dash?: boolean; label: string; desc: string };
  const legendItems: LegendItem[] = [
    { color: '#f59e0b',                     label: 'EMA8',    desc: 'Fast EMA (8)' },
    { color: '#3b82f6',                     label: 'EMA21',   desc: 'Mid EMA (21)' },
    { color: '#a855f7',                     label: 'EMA55',   desc: 'Slow EMA (55)' },
    { color: 'rgba(99,102,241,0.7)',  dash: true, label: 'BB',      desc: 'Bollinger Bands 20·2σ' },
    { color: '#ff6b6b',              dash: true, label: 'Mag MA',  desc: 'Magnetic MA — Mean-Rev. Target' },
    ...(vwatrZones && vwatrZones.length > 0 ? [
      { color: '#22c55e', dash: true, label: 'VWATR S', desc: 'VWATR Support Zone' },
      { color: '#ef4444', dash: true, label: 'VWATR R', desc: 'VWATR Resistance Zone' },
    ] as LegendItem[] : []),
    ...(volumeProfile ? [
      { color: '#3b82f6',                     label: 'POC', desc: 'Point of Control — 최대거래량' },
      { color: 'rgba(255,255,255,0.55)', dash: true, label: 'VAH', desc: 'Value Area High — 상위 70%' },
      { color: 'rgba(255,255,255,0.55)', dash: true, label: 'VAL', desc: 'Value Area Low — 하위 70%' },
      { color: 'rgba(234,179,8,0.6)',    dash: true, label: 'LVN', desc: 'Low Volume Node — 저항 약함' },
    ] as LegendItem[] : []),
  ];

  return (
    <div className="esf-chart-section">

      {/* ── Price Line Legend Bar (차트 위 수평 스트립) ── */}
      <div style={{
        display: 'flex',
        flexWrap: 'nowrap',
        gap: '4px 10px',
        padding: '4px 10px',
        background: 'rgba(255,255,255,0.03)',
        borderBottom: '1px solid rgba(255,255,255,0.06)',
        marginBottom: 2,
        overflowX: 'auto',
      }}>
        {legendItems.map((item) => (
          <div key={item.label} style={{
            display: 'flex',
            alignItems: 'center',
            gap: 4,
            flexShrink: 0,
          }}>
            {/* Line swatch */}
            <svg width="16" height="8" style={{ flexShrink: 0 }}>
              {item.dash
                ? <line x1="0" y1="4" x2="16" y2="4" stroke={item.color} strokeWidth="1.5" strokeDasharray="4,2" />
                : <line x1="0" y1="4" x2="16" y2="4" stroke={item.color} strokeWidth="2.5" />}
            </svg>
            {/* Label */}
            <span style={{
              fontSize: '0.6rem',
              fontFamily: MONO,
              fontWeight: 700,
              color: item.color,
              letterSpacing: '0.02em',
              whiteSpace: 'nowrap',
            }}>{item.label}</span>
          </div>
        ))}
      </div>

      <div style={{ position: 'relative', display: 'block' }}>
        <div ref={mainRef} className="esf-chart-container" />
        <div ref={overlayRef} style={{
          position: 'absolute', top: 0, right: 0,
          width: '72px', height: '0',
          pointerEvents: 'none', zIndex: 10, overflow: 'visible',
        }} />
      </div>
      {subcharts.rsi && <div ref={rsiRef} className="esf-subchart-container" />}
      {subcharts.macd && <div ref={macdRef} className="esf-subchart-container" />}
      {subcharts.zscore && <div ref={zscoreRef} className="esf-subchart-container" />}
      {subcharts.atr && <div ref={atrRef} className="esf-subchart-container" />}
      {subcharts.adx && <div ref={adxRef} className="esf-subchart-container" />}
    </div>
  );
}
