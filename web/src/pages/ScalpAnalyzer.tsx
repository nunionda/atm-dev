import { useState, useMemo, useCallback, useEffect, useRef, memo } from 'react';
import { Link } from 'react-router-dom';
import { createChart, ColorType, CrosshairMode, type IChartApi, type Time, LineStyle } from 'lightweight-charts';
import {
  clamp, fmt, fmtPct, fmtMoney,
  parseCloses, parseOHLC, statsFromCloses, statsFromOHLC,
  computeScalp,
  ASSETS, TICKER_MAP, SAMPLE_CLOSE, SAMPLE_OHLC, F, K,
  type OHLC, type ScalpInputs, type AutoStats, type VolumeSRResult,
} from '../lib/scalpEngine';
import { fetchAnalyticsData, fetchQuote, fetchMTFData } from '../lib/api';
import { usePolling } from '../hooks/usePolling';
import { PollingControl } from '../components/PollingControl';
import { Term, InfoCard } from '../components/glossary/GlossaryComponents';
import {
  initSession, transitionPhase, buildScenarios, extractKeyLevels,
  checkAlerts, getActiveAlerts, evaluatePosition, suggestExitAction, formatHoldTime,
  PHASE_LABELS, PHASE_COLORS,
  type SessionState, type TradingPhase, type EntryRecord, type KeyLevel,
} from '../lib/tradingSession';
import { analyzeMTF, type MTFAnalysis } from '../lib/mtfEngine';
import './ScalpAnalyzer.css';

// ASSETS 데이터에서 자동 생성 — 증거금/수수료/계좌잔고 자동 기입
const ASSET_DEFAULTS: Record<string, Partial<ScalpInputs>> = Object.fromEntries(
  Object.entries(ASSETS).map(([k, a]) => {
    const isKR = a.sym === '₩';
    return [k, {
      currentPrice: isKR ? 360 : (k.includes('NQ') || k.includes('MNQ') ? 21000 : 5900),
      ma: isKR ? 355 : (k.includes('NQ') || k.includes('MNQ') ? 20900 : 5880),
      stdDev: isKR ? 5 : (k.includes('NQ') || k.includes('MNQ') ? 80 : 15),
      atr: isKR ? 8 : (k.includes('NQ') || k.includes('MNQ') ? 60 : 12),
      slippage: isKR ? 1 : 0.5,
      commission: a.defaultCommission,
      accountBalance: a.recommendedBalance,
      spotPrice: isKR ? 360 : (k.includes('NQ') || k.includes('MNQ') ? 20980 : 5898),
      futuresPrice: isKR ? 360 : (k.includes('NQ') || k.includes('MNQ') ? 21000 : 5900),
    }];
  }),
);

// ── Atom Components ─────────────────────────────────────────────────

function NIn({ label, value, onChange, unit, step = 1, min, help, highlight }: {
  label: string; value: number; onChange: (v: number) => void;
  unit?: string; step?: number; min?: number; help?: string; highlight?: boolean;
}) {
  return (
    <div className="scalp-input-group">
      <label className={`scalp-input-label ${highlight ? 'highlight' : ''}`}>
        {label} {highlight && <span style={{ fontSize: 8, color: K.grn }}>● AUTO</span>}
      </label>
      <div className="scalp-input-row">
        <input type="number" value={value} step={step} min={min}
          onChange={e => onChange(parseFloat(e.target.value) || 0)}
          className={`scalp-input ${highlight ? 'highlight' : ''}`} />
        {unit && <span className="scalp-input-unit">{unit}</span>}
      </div>
      {help && <span className="scalp-input-help">{help}</span>}
    </div>
  );
}

function Pill({ children, color = K.dim }: { children: React.ReactNode; color?: string }) {
  return (
    <span className="scalp-pill" style={{ background: `${color}15`, border: `1px solid ${color}35`, color }}>
      {children}
    </span>
  );
}

function Met({ label, value, sub, color, big }: {
  label: string; value: string; sub?: string; color?: string; big?: boolean;
}) {
  return (
    <div className={`scalp-met ${big ? 'big' : ''}`}>
      <div className="scalp-met-label">{label}</div>
      <div className={`scalp-met-value ${big ? 'big' : ''}`} style={{ color: color || K.txt }}>{value}</div>
      {sub && <div className="scalp-met-sub">{sub}</div>}
    </div>
  );
}

function Sec({ icon, title, tag, tagC, infoId }: { icon: string; title: string; tag?: string; tagC?: string; infoId?: string }) {
  return (
    <div className="scalp-sec">
      <span className="scalp-sec-icon">{icon}</span>
      <span className="scalp-sec-title">{title}</span>
      {infoId && <InfoCard id={infoId} />}
      {tag && <Pill color={tagC || K.acc}>{tag}</Pill>}
    </div>
  );
}

// ── Gauge Components ────────────────────────────────────────────────

function ZBar({ z }: { z: number }) {
  const pct = clamp((z + 4) / 8 * 100, 2, 98);
  const col = z < -2 ? K.grn : z > 2 ? K.red : z < -1 ? "#69f0ae" : z > 1 ? "#ff8a80" : "#78909c";
  return (
    <div style={{ marginTop: 12 }}>
      <div className="scalp-bar-track">
        <div style={{ position: "absolute", left: 0, width: "25%", height: "100%", background: `${K.grn}0c`, borderRadius: "5px 0 0 5px" }} />
        <div style={{ position: "absolute", right: 0, width: "25%", height: "100%", background: `${K.red}0c`, borderRadius: "0 5px 5px 0" }} />
        {[12.5, 25, 37.5, 50, 62.5, 75, 87.5].map((p, i) => (
          <div key={i} style={{ position: "absolute", left: `${p}%`, top: 0, bottom: 0, width: 1, background: K.brd }} />
        ))}
        <div className="scalp-bar-dot" style={{ left: `${pct}%`, background: col, boxShadow: `0 0 12px ${col}90` }} />
      </div>
      <div className="scalp-bar-labels">
        <Term id="sigma">-4σ</Term><Term id="sigma">-2σ</Term><span>μ</span><Term id="sigma">+2σ</Term><Term id="sigma">+4σ</Term>
      </div>
    </div>
  );
}

function EVBar({ gross, net }: { gross: number; net: number }) {
  const max = 8;
  const nP = clamp(net / max * 50, -50, 50);
  return (
    <div style={{ marginTop: 10 }}>
      <div className="scalp-ev-info">
        <span style={{ color: K.dim }}>총 EV: <span style={{ color: gross >= 0 ? K.grn : K.red }}>{fmt(gross)}t</span></span>
        <span style={{ color: K.dim }}>마찰: <span style={{ color: K.org }}>-{fmt(gross - net)}t</span></span>
        <span style={{ color: K.dim }}>순 EV: <span style={{ color: net >= 0 ? K.grn : K.red, fontWeight: 700 }}>{fmt(net)}t</span></span>
      </div>
      <div className="scalp-ev-bar">
        <div className="scalp-ev-center" />
        <div className="scalp-ev-fill" style={{
          left: nP >= 0 ? "50%" : `${50 + nP}%`,
          width: `${Math.abs(nP)}%`,
          background: nP >= 0 ? K.grn : K.red,
        }} />
      </div>
    </div>
  );
}

function KGauge({ hk, conv }: { hk: number; conv: string }) {
  const pct = clamp(hk * 100 / 25, 0, 100);
  const col = conv === "NO EDGE" ? K.red : (conv === "VERY LOW" || conv === "LOW") ? K.org : conv === "MODERATE" ? K.ylw : K.grn;
  return (
    <div style={{ marginTop: 10 }}>
      <div className="scalp-gauge-track">
        <div className="scalp-gauge-fill" style={{ width: `${pct}%`, background: `linear-gradient(90deg,${col}50,${col})` }} />
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 5 }}>
        <span style={{ fontSize: 8.5, color: K.mut, fontFamily: F.mono }}>0%</span>
        <Pill color={col}>{conv}</Pill>
        <span style={{ fontSize: 8.5, color: K.mut, fontFamily: F.mono }}>25%</span>
      </div>
    </div>
  );
}

function RRVis({ entry, sl, tp15, tp2, tp3, isLong, ma, zZone, zStopMult, maDistR, revertProb, stdDev, z, volumeSR }: {
  entry: number; sl: number; tp15: number; tp2: number; tp3: number; isLong: boolean;
  ma: number; zZone: 'NORMAL' | 'MILD' | 'STRONG'; zStopMult: number; maDistR: number; revertProb: number;
  stdDev: number; z: number; volumeSR?: VolumeSRResult | null;
}) {
  // σ band price levels
  const s15p = ma + 1.5 * stdDev, s15n = ma - 1.5 * stdDev;
  const s2p = ma + 2 * stdDev, s2n = ma - 2 * stdDev;
  // Collect S/R prices for range calculation
  const srPrices = volumeSR?.levels.map(l => l.price) ?? [];
  const all = [sl, entry, tp15, tp2, tp3, ma, s15p, s15n, s2p, s2n, ...srPrices];
  const lo = Math.min(...all), hi = Math.max(...all), rng = hi - lo || 1, pad = rng * 0.18;
  const svgH = 290;
  const toY = (p: number) => clamp(((hi + pad - p) / (rng + pad * 2)) * (svgH - 20), 8, svgH - 12);
  const lines: { p: number; lb: string; c: string; d: boolean }[] = [
    { p: sl, lb: "STOP", c: K.red, d: true }, { p: entry, lb: "ENTRY", c: K.acc, d: false },
    { p: tp15, lb: "1.5R", c: "#69f0ae", d: true }, { p: tp2, lb: "2R", c: K.grn, d: true }, { p: tp3, lb: "3R", c: K.grn, d: false },
  ];
  const dirColor = isLong ? K.grn : K.red;
  const dirLabel = isLong ? "LONG" : "SHORT";
  const dirIcon = isLong ? "▲" : "▼";
  const entryY = toY(entry);
  const maY = toY(ma);
  const arrowTipY = isLong ? toY(tp15) + 8 : toY(tp15) - 8;
  const arrowMidY = (entryY + arrowTipY) / 2;
  const zoneColor = zZone === 'STRONG' ? '#f9a825' : zZone === 'MILD' ? '#78909c' : '#546e7a';
  const zoneTag = zZone === 'STRONG' ? `×${zStopMult} 넓은 스탑` : zZone === 'MILD' ? `×${zStopMult} 표준` : `×${zStopMult} 타이트`;
  const W = 370;

  // Entry signal logic: |Z| ≥ 2 → STRONG, 1.5 ≤ |Z| < 2 → LEAN, else NO SIGNAL
  const absZ = Math.abs(z);
  const hasSignal = absZ >= 1.5;
  const signalStrength = absZ >= 2 ? 'STRONG' : 'LEAN';
  const signalDir = z < -1.5 ? 'LONG' : z > 1.5 ? 'SHORT' : '';
  const signalLabel = hasSignal ? `${signalStrength} ${signalDir}` : 'NO SIGNAL';
  const signalColor = hasSignal ? (signalDir === 'LONG' ? K.grn : K.red) : '#546e7a';

  return (
    <div className="scalp-rr-vis">
      <svg width="100%" height={svgH} viewBox={`0 0 ${W} ${svgH}`} style={{ display: "block" }}>
        {/* ±2σ outer zone shading */}
        <rect x="48" y={toY(s2p)} width="230" height={Math.abs(toY(s2p) - toY(s15p))} fill="#f9a82508" rx="2" />
        <rect x="48" y={toY(s15n)} width="230" height={Math.abs(toY(s15n) - toY(s2n))} fill="#f9a82508" rx="2" />
        {/* ±1.5σ inner zone shading */}
        <rect x="48" y={toY(s15p)} width="230" height={Math.abs(toY(s15p) - toY(s15n))} fill="#42a5f505" rx="2" />

        {/* Loss zone */}
        <rect x="48" y={Math.min(entryY, toY(sl))} width="230" height={Math.abs(toY(sl) - entryY)} fill={`${K.red}0e`} rx="3" />
        {/* Profit zone */}
        <rect x="48" y={Math.min(entryY, toY(tp3))} width="230" height={Math.abs(toY(tp3) - entryY)} fill={`${K.grn}08`} rx="3" />

        {/* σ band lines */}
        <line x1="48" y1={toY(s2p)} x2="298" y2={toY(s2p)} stroke="#f9a825" strokeWidth="0.8" strokeDasharray="2,3" strokeOpacity="0.5" />
        <line x1="48" y1={toY(s2n)} x2="298" y2={toY(s2n)} stroke="#f9a825" strokeWidth="0.8" strokeDasharray="2,3" strokeOpacity="0.5" />
        <line x1="48" y1={toY(s15p)} x2="298" y2={toY(s15p)} stroke="#78909c" strokeWidth="0.8" strokeDasharray="2,3" strokeOpacity="0.4" />
        <line x1="48" y1={toY(s15n)} x2="298" y2={toY(s15n)} stroke="#78909c" strokeWidth="0.8" strokeDasharray="2,3" strokeOpacity="0.4" />
        {/* σ labels (right side) */}
        <text x="302" y={toY(s2p) + 3} textAnchor="start" fill="#f9a825" fontSize="7" fontFamily="monospace" opacity="0.7">+2σ</text>
        <text x="302" y={toY(s2n) + 3} textAnchor="start" fill="#f9a825" fontSize="7" fontFamily="monospace" opacity="0.7">-2σ</text>
        <text x="302" y={toY(s15p) + 3} textAnchor="start" fill="#78909c" fontSize="7" fontFamily="monospace" opacity="0.6">+1.5σ</text>
        <text x="302" y={toY(s15n) + 3} textAnchor="start" fill="#78909c" fontSize="7" fontFamily="monospace" opacity="0.6">-1.5σ</text>
        {/* σ zone labels (left side) */}
        <text x="45" y={toY(s2p) - 3} textAnchor="end" fill="#f9a825" fontSize="6.5" fontFamily="monospace" opacity="0.5">SHORT zone</text>
        <text x="45" y={toY(s2n) + 9} textAnchor="end" fill="#f9a825" fontSize="6.5" fontFamily="monospace" opacity="0.5">LONG zone</text>

        {/* MA reference line */}
        <line x1="48" y1={maY} x2="298" y2={maY} stroke="#42a5f5" strokeWidth="1.5" strokeDasharray="3,3" strokeOpacity="0.7" />
        <rect x="2" y={maY - 8} width="42" height="16" rx="3" fill="#42a5f510" stroke="#42a5f540" strokeWidth="0.5" />
        <text x="23" y={maY + 4} textAnchor="middle" fill="#42a5f5" fontSize="8" fontFamily="monospace" fontWeight="700">MA</text>
        <text x="302" y={maY + 3.5} textAnchor="start" fill="#42a5f5" fontSize="8" fontFamily="monospace">{fmt(ma, 2)}</text>
        {/* MA→Entry distance marker */}
        {Math.abs(maY - entryY) > 14 && (
          <g>
            <line x1="36" y1={Math.min(maY, entryY) + 3} x2="36" y2={Math.max(maY, entryY) - 3} stroke="#42a5f5" strokeWidth="0.8" strokeOpacity="0.5" />
            <text x="34" y={(maY + entryY) / 2 + 3} textAnchor="end" fill="#42a5f5" fontSize="7" fontFamily="monospace" opacity="0.7">{maDistR.toFixed(1)}R</text>
          </g>
        )}

        {/* Direction arrow */}
        <line x1="165" y1={entryY} x2="165" y2={arrowTipY} stroke={dirColor} strokeWidth="2.5" strokeOpacity="0.6" />
        <polygon
          points={isLong
            ? `165,${arrowTipY - 6} 159,${arrowTipY + 2} 171,${arrowTipY + 2}`
            : `165,${arrowTipY + 6} 159,${arrowTipY - 2} 171,${arrowTipY - 2}`}
          fill={dirColor} fillOpacity="0.7"
        />
        {/* Direction badge */}
        <rect x="125" y={arrowMidY - 10} width="80" height="20" rx="10" fill={`${dirColor}18`} stroke={dirColor} strokeWidth="1" strokeOpacity="0.5" />
        <text x="165" y={arrowMidY + 4} textAnchor="middle" fill={dirColor} fontSize="11" fontFamily={F.mono} fontWeight="800" letterSpacing="0.08em">
          {dirIcon} {dirLabel}
        </text>

        {/* Volume S/R levels */}
        {volumeSR?.levels.slice(0, 6).map((lv, i) => {
          const isS = lv.type === 'support';
          const c = isS ? '#69f0ae' : '#ff5252';
          const sw = lv.strength === 3 ? 1.5 : lv.strength === 2 ? 1 : 0.5;
          const label = `${isS ? 'S' : 'R'}${i + 1} (${lv.volumeScore.toFixed(1)}x)`;
          return (
            <g key={`sr-${i}`}>
              <line x1="48" y1={toY(lv.price)} x2="298" y2={toY(lv.price)} stroke={c} strokeWidth={sw} strokeDasharray="3,4" strokeOpacity="0.6" />
              <text x="302" y={toY(lv.price) + 3} textAnchor="start" fill={c} fontSize="7" fontFamily="monospace" opacity="0.8">{label}</text>
            </g>
          );
        })}

        {/* Price level lines */}
        {lines.map((l, i) => (
          <g key={i}>
            <line x1="48" y1={toY(l.p)} x2="298" y2={toY(l.p)} stroke={l.c} strokeWidth={l.d ? 1.2 : 2} strokeDasharray={l.d ? "5,4" : "none"} />
            <text x="44" y={toY(l.p) + 3.5} textAnchor="end" fill={l.c} fontSize="8.5" fontFamily="monospace" fontWeight={l.d ? 400 : 700}>{l.lb}</text>
            <text x="302" y={toY(l.p) + 3.5} textAnchor="start" fill={l.c} fontSize="8.5" fontFamily="monospace">{fmt(l.p, 2)}</text>
          </g>
        ))}

        {/* Entry signal badge (top) */}
        <rect x="90" y="2" width="190" height="22" rx="11" fill={`${signalColor}18`} stroke={signalColor} strokeWidth="1" strokeOpacity="0.6" />
        {hasSignal && <circle cx="102" cy="13" r="4" fill={signalColor} opacity="0.9"><animate attributeName="opacity" values="0.9;0.3;0.9" dur="1.5s" repeatCount="indefinite" /></circle>}
        <text x="185" y="17" textAnchor="middle" fill={signalColor} fontSize="10" fontFamily={F.mono} fontWeight="700" letterSpacing="0.05em">
          {hasSignal ? `SIGNAL: ${signalLabel}` : 'NO SIGNAL'} (Z={z.toFixed(2)})
        </text>

        {/* Z-Zone badge (bottom) */}
        <rect x="48" y={svgH - 22} width="250" height="18" rx="4" fill={`${zoneColor}12`} stroke={`${zoneColor}40`} strokeWidth="0.5" />
        <text x="55" y={svgH - 10} fill={zoneColor} fontSize="8.5" fontFamily="monospace" fontWeight="600">
          Z-Zone: {zZone} {zoneTag} | 회귀확률 {(revertProb * 100).toFixed(0)}%
        </text>
      </svg>
    </div>
  );
}

const PriceChart = memo(function PriceChart({ candles, ma, stdDev, entry, sl, tp15, tp2, tp3, isLong, volumeSR, maPeriod, z, dates }: {
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

function BasisBar({ basis }: { basis: number }) {
  const bP = clamp((basis + 20) / 40 * 100, 2, 98);
  const bC = basis > 2 ? K.cyn : basis < -2 ? K.org : "#78909c";
  return (
    <>
      <div className="scalp-basis-bar">
        <div className="scalp-basis-center" />
        <div className="scalp-bar-dot" style={{ left: `${bP}%`, background: bC, boxShadow: `0 0 10px ${bC}80`, width: 12, height: 12 }} />
      </div>
      <div className="scalp-bar-labels">
        <Term id="backwardation">← 백워데이션 (선물&lt;현물)</Term><span>적정가</span><Term id="contango">콘탱고 (선물&gt;현물) →</Term>
      </div>
    </>
  );
}

// ── Main Page ───────────────────────────────────────────────────────

export function ScalpAnalyzer() {
  const [asset, setAsset] = useState("ES");
  const cfg = ASSETS[asset];

  const [dataMode, setDataMode] = useState<"close" | "ohlc" | "manual">("ohlc");
  const [closeText, setCloseText] = useState(SAMPLE_CLOSE);
  const [ohlcText, setOhlcText] = useState(SAMPLE_OHLC);
  const [maPeriod, setMaPeriod] = useState(20);
  const [liveLoaded, setLiveLoaded] = useState(false);
  const [candleDates, setCandleDates] = useState<string[]>([]);

  // ── Polling ──
  const tickers = TICKER_MAP[asset];
  const pollFn = useCallback(
    () => fetchQuote(tickers?.futures || 'ES=F', 50),
    [tickers?.futures],
  );
  const poll = usePolling(pollFn, { interval: 30000, enabled: false });

  // 폴링 데이터 수신 시 자동 업데이트
  useEffect(() => {
    const q = poll.data;
    if (!q?.candles || q.candles.length < 3) return;
    const ohlcLines = q.candles.map(c => {
      const o = c.open > 0 ? c.open : c.close;
      const h = c.high > 0 ? c.high : c.close;
      const l = c.low > 0 ? c.low : c.close;
      const v = c.volume ?? 0;
      return `${o.toFixed(2)}, ${h.toFixed(2)}, ${l.toFixed(2)}, ${c.close.toFixed(2)}, ${v}`;
    }).join('\n');
    const closeLines = q.candles.map(c => c.close.toFixed(2)).join(', ');
    setOhlcText(ohlcLines);
    setCloseText(closeLines);
    if (q.latest) {
      setInputs(p => ({ ...p, futuresPrice: q.latest.price }));
    }
    setLiveLoaded(true);
  }, [poll.data]);

  const closes = useMemo(() => parseCloses(closeText), [closeText]);
  const candles = useMemo(() => parseOHLC(ohlcText), [ohlcText]);

  const autoStats: AutoStats | null = useMemo(() => {
    if (dataMode === "close") return statsFromCloses(closes, maPeriod);
    if (dataMode === "ohlc") return statsFromOHLC(candles, maPeriod);
    return null;
  }, [dataMode, closes, candles, maPeriod]);

  const [inputs, setInputs] = useState<ScalpInputs>({
    asset: "ES",
    currentPrice: 5920, ma: 5900, stdDev: 15, atr: 12, atrMult: 1.0,
    winRate: 58, avgWin: 6, avgLoss: 4, slippage: 0.5, commission: 2.25,
    accountBalance: 10000, riskPct: 2, spotPrice: 5918, futuresPrice: 5920,
  });
  const s = useCallback((k: keyof ScalpInputs) => (v: number) => setInputs(p => ({ ...p, [k]: v })), []);

  // ── Session & MTF State ──
  const [session, setSession] = useState<SessionState | null>(null);
  const [mtfHTF, setMtfHTF] = useState<OHLC[]>([]);
  const [mtfLTF, setMtfLTF] = useState<OHLC[]>([]);
  const [mtfAnalysis, setMtfAnalysis] = useState<MTFAnalysis | null>(null);
  const [mtfLoading, setMtfLoading] = useState(false);
  const [mtfError, setMtfError] = useState<string | null>(null);
  const [mtfExpanded, setMtfExpanded] = useState(true);
  const [entryFormOpen, setEntryFormOpen] = useState(false);
  const [entryPrice, setEntryPrice] = useState('');
  const [entryContracts, setEntryContracts] = useState('1');

  useEffect(() => {
    if (dataMode !== "manual" && autoStats) {
      setInputs(p => ({
        ...p,
        currentPrice: autoStats.currentPrice,
        ma: autoStats.ma,
        stdDev: autoStats.stdDev,
        atr: autoStats.atr,
        futuresPrice: autoStats.currentPrice,
        dailyCandles: candles.length >= 14 ? candles.slice(-14) : undefined,
      }));
    }
  }, [dataMode, autoStats, candles]);

  const isInitialMount = useRef(true);
  useEffect(() => {
    const defaults = ASSET_DEFAULTS[asset];
    setInputs(p => ({ ...p, asset, ...(defaults || {}) }));
    // 초기 마운트 시에는 SAMPLE 데이터 유지, 에셋 변경 시에만 클리어
    if (isInitialMount.current) {
      isInitialMount.current = false;
    } else {
      setOhlcText('');
      setCloseText('');
    }
  }, [asset]);

  // Fetch live futures data based on selected asset
  useEffect(() => {
    let cancelled = false;
    setLiveLoaded(false);

    const tickers = TICKER_MAP[asset];
    if (!tickers) return;

    async function loadLiveData() {
      try {
        let futuresData;
        try {
          const res = await fetchAnalyticsData(tickers.futures, '3mo', '1d');
          if (res?.data && res.data.length >= 3) futuresData = res;
        } catch { /* fall through */ }

        if (!futuresData && tickers.fallback) {
          try {
            const res = await fetchAnalyticsData(tickers.fallback, '3mo', '1d');
            if (res?.data && res.data.length >= 3) futuresData = res;
          } catch { /* give up */ }
        }

        if (cancelled || !futuresData?.data || futuresData.data.length < 3) return;

        const recent = futuresData.data.slice(-50);
        // Fix incomplete bars (e.g. ^KS200 returns O/H/L=0 for latest bar)
        const ohlcLines = recent.map(d => {
          const o = d.open > 0 ? d.open : d.close;
          const h = d.high > 0 ? d.high : d.close;
          const l = d.low > 0 ? d.low : d.close;
          const v = d.volume ?? 0;
          return `${o.toFixed(2)}, ${h.toFixed(2)}, ${l.toFixed(2)}, ${d.close.toFixed(2)}, ${v}`;
        }).join('\n');
        const closeLines = recent.map(d => d.close.toFixed(2)).join(', ');

        setOhlcText(ohlcLines);
        setCloseText(closeLines);
        setCandleDates(recent.map(d => d.datetime.split(' ')[0]));

        const lastClose = futuresData.data[futuresData.data.length - 1].close;

        // Fetch spot price for basis spread (if different ticker)
        let spotClose = lastClose;
        if (tickers.spot !== tickers.futures) {
          try {
            const spx = await fetchAnalyticsData(tickers.spot, '3mo', '1d');
            if (spx?.data && spx.data.length > 0) {
              spotClose = spx.data[spx.data.length - 1].close;
            }
          } catch { /* use futures price as fallback */ }
        }

        if (cancelled) return;
        setInputs(p => ({ ...p, spotPrice: spotClose, futuresPrice: lastClose }));
        setLiveLoaded(true);
      } catch (err) {
        console.error('[ScalpAnalyzer] Live data load failed:', err);
      }
    }
    loadLiveData();
    return () => { cancelled = true; };
  }, [asset]);

  // ── Session Handlers ──
  const handleStartSession = useCallback(() => {
    const s = initSession(asset);
    const calc0 = computeScalp(inputs);
    const scenarios = buildScenarios(calc0, inputs, autoStats);
    const levels = extractKeyLevels(calc0, inputs, autoStats);
    setSession({ ...s, scenarios, keyLevels: levels, phase: 'WATCHING' });
  }, [asset, inputs, autoStats]);

  const handleEndSession = useCallback(() => {
    setSession(null);
    setEntryFormOpen(false);
  }, []);

  const handleRecordEntry = useCallback(() => {
    if (!session) return;
    const price = parseFloat(entryPrice) || inputs.currentPrice;
    const contracts = parseInt(entryContracts) || 1;
    const calc0 = computeScalp(inputs);
    const entry: EntryRecord = {
      price,
      contracts,
      time: Date.now(),
      direction: calc0.isLong ? 'LONG' : 'SHORT',
      z: calc0.z,
      verdict: calc0.verdict,
      scenario: session.scenarios[0]?.name || '직접 진입',
      initialSL: calc0.adaptiveSL,
      initialTP: calc0.tp15,
    };
    setSession(prev => prev ? { ...prev, phase: 'ENTERED', entry } : null);
    setEntryFormOpen(false);
  }, [session, entryPrice, entryContracts, inputs]);

  const handleRecordExit = useCallback((reason: string) => {
    if (!session?.entry) return;
    const calc0 = computeScalp(inputs);
    const isLong = session.entry.direction === 'LONG';
    const pnlPts = isLong ? (inputs.currentPrice - session.entry.price) : (session.entry.price - inputs.currentPrice);
    setSession(prev => prev ? {
      ...prev,
      phase: 'CLOSED',
      exitRecord: {
        price: inputs.currentPrice,
        contracts: session.entry!.contracts,
        time: Date.now(),
        reason: reason as any,
        pnlPoints: +pnlPts.toFixed(2),
        pnlUSD: +(pnlPts * calc0.cfg.ptVal * session.entry!.contracts).toFixed(2),
        holdDuration: Date.now() - session.entry!.time,
      },
    } : null);
  }, [session, inputs]);

  // 폴링 시 알림 체크 (WATCHING/ALERT phase)
  useEffect(() => {
    if (!session || !session.keyLevels.length) return;
    if (session.phase !== 'WATCHING' && session.phase !== 'ALERT') return;
    const alerts = checkAlerts(inputs.currentPrice, session.keyLevels);
    const active = getActiveAlerts(alerts);
    setSession(prev => {
      if (!prev) return null;
      const newPhase = active.some(a => a.status === 'AT_LEVEL') ? 'ALERT' as TradingPhase : prev.phase;
      return { ...prev, activeAlerts: alerts, phase: newPhase };
    });
  }, [inputs.currentPrice, session?.phase, session?.keyLevels]);

  // 폴링 시 포지션 평가 + ENTERED→MANAGING 자동 전환
  useEffect(() => {
    if (!session?.entry) return;
    if (session.phase !== 'ENTERED' && session.phase !== 'MANAGING') return;
    const posEval = evaluatePosition(session.entry, inputs.currentPrice, calc, calc.cfg);
    // ENTERED → MANAGING 자동 전환: 스탑 모드가 INITIAL이 아니면 (BE or TRAILING)
    if (session.phase === 'ENTERED' && posEval.stopMode !== 'INITIAL') {
      setSession(prev => prev ? { ...prev, phase: 'MANAGING', currentStopMode: posEval.stopMode } : null);
    } else if (session.phase === 'MANAGING') {
      setSession(prev => prev ? { ...prev, currentStopMode: posEval.stopMode } : null);
    }
    // 자동 청산 감지: SL / TP / TIMEOUT 히트
    const exitSugg = suggestExitAction(session.entry, inputs.currentPrice, calc);
    if (exitSugg.shouldExit && (exitSugg.exitType === 'SL' || exitSugg.exitType === 'TP' || exitSugg.exitType === 'TIMEOUT')) {
      const isLong = session.entry.direction === 'LONG';
      const pnlPts = isLong ? (inputs.currentPrice - session.entry.price) : (session.entry.price - inputs.currentPrice);
      const exitReason = exitSugg.exitType as 'SL' | 'TP' | 'TRAIL' | 'MANUAL' | 'TIMEOUT';
      setSession(prev => prev?.entry ? {
        ...prev,
        phase: 'CLOSED',
        exitRecord: {
          price: inputs.currentPrice,
          contracts: prev.entry!.contracts,
          time: Date.now(),
          reason: exitReason,
          pnlPoints: +pnlPts.toFixed(2),
          pnlUSD: +(pnlPts * calc.cfg.ptVal * prev.entry!.contracts).toFixed(2),
          holdDuration: Date.now() - prev.entry!.time,
        },
      } : null);
    }
  }, [inputs.currentPrice, session?.entry, session?.phase]);

  // MTF data loader
  const loadMTFData = useCallback(async () => {
    const tickers = TICKER_MAP[asset];
    if (!tickers) return;
    setMtfLoading(true);
    setMtfError(null);
    try {
      const result = await fetchMTFData(tickers.futures);
      const toOHLC = (data: typeof result.htf.data): OHLC[] =>
        data.map(d => ({
          o: d.open > 0 ? d.open : d.close,
          h: d.high > 0 ? d.high : d.close,
          l: d.low > 0 ? d.low : d.close,
          c: d.close,
          v: d.volume ?? 0,
        }));
      const htf = toOHLC(result.htf.data);
      const ltf = toOHLC(result.ltf.data);
      setMtfHTF(htf);
      setMtfLTF(ltf);
      if (htf.length >= 10 && ltf.length >= 10) {
        const analysis = analyzeMTF(htf, ltf, inputs.currentPrice);
        setMtfAnalysis(analysis);
      } else {
        setMtfError(`데이터 부족 (HTF: ${htf.length}봉, LTF: ${ltf.length}봉)`);
      }
    } catch (err) {
      setMtfError(err instanceof Error ? err.message : 'MTF 데이터 로드 실패');
    } finally {
      setMtfLoading(false);
    }
  }, [asset, inputs.currentPrice]);

  // MTF → Session 키 레벨 연동: MTF 분석 결과의 HTF 스윙 포인트를 세션 키 레벨에 추가
  useEffect(() => {
    if (!session || !mtfAnalysis) return;
    if (session.phase === 'CLOSED') return;

    const htf = mtfAnalysis.htf;
    const mtfLevels: KeyLevel[] = [];

    // HTF 스윙 고점 → 저항 키 레벨
    for (const sh of htf.swingHighs.filter(s => s.confirmed).slice(-3)) {
      mtfLevels.push({
        price: sh.price,
        label: `HTF 스윙고 (1H)`,
        type: 'RESISTANCE',
        source: 'SWING',
        strength: 2,
      });
    }

    // HTF 스윙 저점 → 지지 키 레벨
    for (const sl of htf.swingLows.filter(s => s.confirmed).slice(-3)) {
      mtfLevels.push({
        price: sl.price,
        label: `HTF 스윙저 (1H)`,
        type: 'SUPPORT',
        source: 'SWING',
        strength: 2,
      });
    }

    // HTF BOS/CHoCH 돌파 레벨
    if (htf.lastBOS) {
      mtfLevels.push({
        price: htf.lastBOS.breakPrice,
        label: `BOS ${htf.lastBOS.direction} (1H)`,
        type: htf.lastBOS.direction === 'BULLISH' ? 'SUPPORT' : 'RESISTANCE',
        source: 'SWING',
        strength: 3,
      });
    }
    if (htf.lastCHoCH) {
      mtfLevels.push({
        price: htf.lastCHoCH.breakPrice,
        label: `CHoCH ${htf.lastCHoCH.direction} (1H)`,
        type: htf.lastCHoCH.direction === 'BULLISH' ? 'SUPPORT' : 'RESISTANCE',
        source: 'SWING',
        strength: 3,
      });
    }

    if (mtfLevels.length === 0) return;

    // 기존 키 레벨에서 SWING 소스가 아닌 것만 유지 + 새 MTF 레벨 추가
    setSession(prev => {
      if (!prev) return null;
      const existingNonSwing = prev.keyLevels.filter(kl => kl.source !== 'SWING');
      return { ...prev, keyLevels: [...existingNonSwing, ...mtfLevels] };
    });
  }, [mtfAnalysis, session?.phase]);

  // MTF 자동 로드: 폴링 활성 시 3분 간격으로 MTF 데이터 자동 갱신
  const mtfAutoLoadRef = useRef<number>(0);
  useEffect(() => {
    if (!poll.enabled || !poll.data) return;

    const now = Date.now();
    const MTF_REFRESH_MS = 3 * 60 * 1000; // 3분

    // 마지막 로드로부터 3분 이상 경과했으면 자동 로드
    if (now - mtfAutoLoadRef.current >= MTF_REFRESH_MS && !mtfLoading) {
      mtfAutoLoadRef.current = now;
      loadMTFData();
    }
  }, [poll.enabled, poll.data, mtfLoading, loadMTFData]);

  const calc = computeScalp(inputs);
  const vc = calc.verdict === "GO" ? K.grn : calc.verdict === "CAUTION" ? K.ylw : K.red;
  const isKospi = asset === 'K200' || asset === 'MK200';
  const isNasdaq = asset === 'NQ' || asset === 'MNQ';
  const spotLabel = isKospi ? 'KOSPI200' : isNasdaq ? 'NDX' : 'SPX';
  const futLabel = isKospi ? 'K200' : isNasdaq ? 'NQ' : 'ES';

  return (
    <div className="scalp-page">

      {/* Header */}
      <div className="scalp-header">
        <div className="scalp-header-inner">
          <div className="scalp-logo">
            <div className="scalp-logo-icon">Σ</div>
            <div>
              <div className="scalp-logo-title">Futures Scalp Analyzer</div>
              <div className="scalp-logo-sub">PROBABILITY-BASED DECISION ENGINE v1.2</div>
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div className="scalp-asset-btns">
              {Object.entries(ASSETS).map(([k, v]) => (
                <button key={k} onClick={() => setAsset(k)}
                  className={`scalp-asset-btn ${asset === k ? 'active' : ''}`}>
                  {k}<span style={{ fontSize: 9, marginLeft: 4, opacity: 0.6 }}>{fmtMoney(v.tickVal, v.sym)}/t</span>
                </button>
              ))}
            </div>
            <Link to="/scalp-analyzer/fabio" style={{
              padding: '6px 14px', borderRadius: 6, fontSize: 11, fontWeight: 700,
              fontFamily: F.mono, textDecoration: 'none', transition: 'all 0.15s',
              border: '1px solid #c2185b', background: 'rgba(194,24,91,0.10)', color: '#ff6b9d',
              display: 'flex', alignItems: 'center', gap: 5,
            }}>
              🔥 Fabio Strategy
            </Link>
          </div>
        </div>
      </div>

      {/* Polling Control */}
      <div style={{ padding: '6px 24px', display: 'flex', justifyContent: 'flex-end' }}>
        <PollingControl
          enabled={poll.enabled}
          onToggle={poll.setEnabled}
          interval={poll.interval}
          onIntervalChange={poll.setInterval}
          status={poll.status}
          lastUpdated={poll.lastUpdated}
          consecutiveErrors={poll.consecutiveErrors}
          onRefresh={poll.fetchNow}
          compact
        />
      </div>

      {/* Verdict */}
      <div className="scalp-verdict" style={{ background: `${vc}08`, borderBottom: `1px solid ${vc}25`, color: vc }}>
        {calc.verdict === "GO" ? "✅" : calc.verdict === "CAUTION" ? "⚠️" : "🚫"}{" "}
        {calc.verdict} — [{calc.passN}/{calc.checks.length}] — {calc.zSignal} — {calc.isLong ? "▲ LONG" : "▼ SHORT"}
        {autoStats && <span style={{ opacity: 0.5 }}> — ATR: {autoStats.atrMethod}</span>}
        {calc.trendConflict && <span style={{ color: K.org, marginLeft: 8, fontSize: 12 }}>⚠ 역추세 진입 — 추세 하락 중 롱 권고</span>}
      </div>

      {/* Body */}
      <div className="scalp-body">
        <div className="scalp-layout">

          {/* ── LEFT: INPUTS ── */}
          <div className="scalp-sidebar">

            {/* Price Data */}
            <div className="scalp-box" style={{ borderColor: dataMode !== "manual" ? `${K.acc}40` : undefined }}>
              <Sec icon="📋" title="가격 데이터 (Price Data)" tag={liveLoaded ? "LIVE" : dataMode === "ohlc" ? "OHLC" : dataMode === "close" ? "CLOSE" : "MANUAL"} tagC={liveLoaded ? K.grn : dataMode !== "manual" ? K.grn : K.dim} />

              <div className="scalp-mode-btns">
                {([
                  { key: "ohlc" as const, label: "OHLC", desc: "True ATR" },
                  { key: "close" as const, label: "Close", desc: "근사 ATR" },
                  { key: "manual" as const, label: "수동", desc: "직접입력" },
                ]).map(m => (
                  <button key={m.key} onClick={() => setDataMode(m.key)}
                    className={`scalp-mode-btn ${dataMode === m.key ? 'active' : ''}`}>
                    <span>{m.label}</span>
                    <span className="scalp-mode-btn-sub">{m.desc}</span>
                  </button>
                ))}
              </div>

              {dataMode === "ohlc" && (
                <>
                  <label className="scalp-input-label">OHLC 데이터 (한 줄에 O, H, L, C)</label>
                  <textarea value={ohlcText} onChange={e => setOhlcText(e.target.value)}
                    placeholder={"5870.00, 5878.50, 5868.25, 5872.50\n..."}
                    rows={5} className="scalp-textarea" />
                  <div style={{ display: "flex", justifyContent: "space-between", marginTop: 5, marginBottom: 8 }}>
                    <span className="scalp-data-count" style={{ color: candles.length >= 3 ? K.grn : K.red }}>
                      {candles.length}개 캔들 파싱 {candles.length < 3 && "(최소 3개)"}
                    </span>
                    <button onClick={() => setOhlcText(SAMPLE_OHLC)} className="scalp-sample-btn">샘플</button>
                  </div>
                </>
              )}

              {dataMode === "close" && (
                <>
                  <label className="scalp-input-label">종가 데이터 (콤마/줄바꿈 구분)</label>
                  <textarea value={closeText} onChange={e => setCloseText(e.target.value)}
                    placeholder="5880.50, 5885.25, 5890.00 ..." rows={4} className="scalp-textarea" />
                  <div style={{ display: "flex", justifyContent: "space-between", marginTop: 5, marginBottom: 8 }}>
                    <span className="scalp-data-count" style={{ color: closes.length >= 3 ? K.grn : K.red }}>
                      {closes.length}개 가격 파싱 {closes.length < 3 && "(최소 3개)"}
                    </span>
                    <button onClick={() => setCloseText(SAMPLE_CLOSE)} className="scalp-sample-btn">샘플</button>
                  </div>
                </>
              )}

              {dataMode === "manual" && (
                <>
                  <NIn label="현재가" value={inputs.currentPrice} onChange={s("currentPrice")} step={cfg.tick} unit="pts" />
                  <NIn label="이동평균 (MA)" value={inputs.ma} onChange={s("ma")} step={cfg.tick} unit="pts" />
                  <NIn label="표준편차 (σ)" value={inputs.stdDev} onChange={s("stdDev")} step={cfg.tick} unit="pts" />
                  <NIn label="ATR" value={inputs.atr} onChange={s("atr")} step={cfg.tick} unit="pts" />
                </>
              )}

              {dataMode !== "manual" && (
                <NIn label="MA 기간" value={maPeriod} onChange={setMaPeriod} step={1} min={2} help="이동평균 & 표준편차 산출 기간" />
              )}

              {dataMode !== "manual" && autoStats && (
                <div className="scalp-auto-stats">
                  <div className="scalp-auto-stats-header">
                    ● 자동 산출 — {autoStats.atrMethod === "TRUE-RANGE"
                      ? <span style={{ color: K.cyn }}>True Range ATR ✓</span>
                      : <span style={{ color: K.org }}>Close-Proxy ATR (근사)</span>}
                  </div>
                  <div className="scalp-stats-grid">
                    {[
                      { l: "현재가", v: fmt(autoStats.currentPrice, 2) },
                      { l: `MA(${autoStats.maPeriod})`, v: fmt(autoStats.ma, 2) },
                      { l: "표준편차 (σ)", v: fmt(autoStats.stdDev, 2) },
                      { l: "평균변동폭 ATR(14)", v: fmt(autoStats.atr, 2) },
                    ].map((item, i) => (
                      <div key={i}>
                        <div className="scalp-stats-label">{item.l}</div>
                        <div className="scalp-stats-value">{item.v}</div>
                      </div>
                    ))}
                  </div>
                  {autoStats.atrMethod === "CLOSE-PROXY" && (
                    <div className="scalp-auto-warn">
                      ⚠ 종가 간 차이로 ATR 근사 중. OHLC 모드 사용 시 True Range 기반 정확한 ATR 산출.
                    </div>
                  )}
                </div>
              )}

              <NIn label="ATR 배수 (Stop)" value={inputs.atrMult} onChange={s("atrMult")} step={0.1} min={0.1} help="스캘핑: 0.5~1.0 / 스윙: 1.5~2.0" />
            </div>

            {/* Backtest Stats */}
            <div className="scalp-box">
              <Sec icon="🎯" title="승률/손익 통계 (EV Input)" />
              <NIn label="승률 (Win Rate)" value={inputs.winRate} onChange={s("winRate")} step={1} unit="%" />
              <NIn label="평균 익절 (Avg Win)" value={inputs.avgWin} onChange={s("avgWin")} step={0.5} unit="ticks" />
              <NIn label="평균 손절 (Avg Loss)" value={inputs.avgLoss} onChange={s("avgLoss")} step={0.5} unit="ticks" />
              <NIn label="슬리피지" value={inputs.slippage} onChange={s("slippage")} step={0.25} unit="ticks" help="스캘핑 0.25~0.5t" />
              <NIn label="수수료 (편도)" value={inputs.commission} onChange={s("commission")} step={isKospi ? 100 : 0.05} unit={cfg.sym} />
            </div>

            {/* Account */}
            <div className="scalp-box">
              <Sec icon="💰" title="계좌 정보 (Account)" />
              <NIn label="계좌잔고" value={inputs.accountBalance} onChange={s("accountBalance")} step={isKospi ? 1000000 : 100} unit={cfg.sym} />
              <NIn label="허용 리스크" value={inputs.riskPct} onChange={s("riskPct")} step={0.5} min={0.1} unit="%" />

              {/* 증거금 정보 */}
              <div style={{
                marginTop: 10, padding: '8px 10px', borderRadius: 6,
                background: '#0d1117', border: `1px solid ${K.brd}`,
                fontSize: 10, fontFamily: F.mono, lineHeight: 1.7,
              }}>
                <div style={{ fontWeight: 700, color: K.acc, marginBottom: 4, fontSize: 11 }}>
                  📋 {cfg.label} — {cfg.exchange}
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '2px 12px' }}>
                  <span style={{ color: '#888' }}><Term id="multiplier" position="bottom">승수 (Multiplier)</Term></span>
                  <span style={{ color: '#ccc', textAlign: 'right' }}>{cfg.sym === '₩' ? `₩${cfg.multiplier.toLocaleString()}` : `$${cfg.multiplier}`}</span>

                  <span style={{ color: '#888' }}><Term id="notional" position="bottom">1계약 명목가치</Term></span>
                  <span style={{ color: '#ccc', textAlign: 'right' }}>
                    {cfg.sym === '₩'
                      ? `₩${cfg.notional.toLocaleString()}`
                      : `$${cfg.notional.toLocaleString()}`}
                  </span>

                  <span style={{ color: '#f9a825' }}><Term id="initialMargin" position="bottom">개시증거금 (Initial)</Term></span>
                  <span style={{ color: '#f9a825', textAlign: 'right', fontWeight: 700 }}>
                    {cfg.sym === '₩'
                      ? `₩${cfg.initialMargin.toLocaleString()}`
                      : `$${cfg.initialMargin.toLocaleString()}`}
                    {cfg.marginRatePct && <span style={{ fontSize: 8, opacity: 0.7 }}> ({cfg.marginRatePct}%)</span>}
                  </span>

                  <span style={{ color: '#ff7043' }}><Term id="maintMargin" position="bottom">유지증거금 (Maint.)</Term></span>
                  <span style={{ color: '#ff7043', textAlign: 'right', fontWeight: 700 }}>
                    {cfg.sym === '₩'
                      ? `₩${cfg.maintMargin.toLocaleString()}`
                      : `$${cfg.maintMargin.toLocaleString()}`}
                    {cfg.marginRatePct && <span style={{ fontSize: 8, opacity: 0.7 }}> ({(cfg.marginRatePct * 2 / 3).toFixed(1)}%)</span>}
                  </span>

                  <span style={{ color: '#888' }}>수수료 (편도)</span>
                  <span style={{ color: '#ccc', textAlign: 'right' }}>
                    {cfg.sym === '₩'
                      ? `₩${cfg.defaultCommission.toLocaleString()}`
                      : `$${cfg.defaultCommission}`}
                  </span>

                  <span style={{ color: '#888' }}><Term id="tickValue" position="bottom">틱 가치 (Tick Value)</Term></span>
                  <span style={{ color: '#ccc', textAlign: 'right' }}>
                    {cfg.sym === '₩' ? `₩${cfg.tickVal.toLocaleString()}` : `$${cfg.tickVal}`} / {cfg.tick}pt
                  </span>
                </div>
                {inputs.accountBalance > 0 && (
                  <div style={{
                    marginTop: 6, paddingTop: 6, borderTop: `1px solid ${K.brd}`,
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  }}>
                    <span style={{ color: '#888' }}>잔고 ÷ 개시증거금</span>
                    <span style={{
                      color: inputs.accountBalance >= cfg.initialMargin ? K.grn : K.red,
                      fontWeight: 700, fontSize: 12,
                    }}>
                      {(inputs.accountBalance / cfg.initialMargin).toFixed(2)}계약
                    </span>
                  </div>
                )}
              </div>
            </div>

            {/* Basis */}
            <div className="scalp-box">
              <Sec icon="📉" title="선현물 스프레드 (Basis)" />
              <NIn label={`현물 (${spotLabel})`} value={inputs.spotPrice} onChange={s("spotPrice")} step={cfg.tick} unit="pts" />
              <NIn label={`선물 (${futLabel})`} value={inputs.futuresPrice} onChange={s("futuresPrice")} step={cfg.tick} unit="pts" />
            </div>
          </div>

          {/* ── RIGHT: OUTPUTS ── */}
          <div className="scalp-main">

            {/* Decision Matrix */}
            <div className="scalp-box" style={{ borderColor: `${vc}30` }}>
              <Sec icon="🎯" title="진입 판정표 (Decision Matrix)" tag="ENTRY CHECKLIST" tagC={vc} />
              <div className="scalp-flex-col">
                {calc.checks.map((c, i) => (
                  <div key={i} className={`scalp-check ${c.pass ? 'pass' : 'fail'}`}>
                    <span className="scalp-check-icon" style={{
                      background: c.pass ? `${K.grn}18` : `${K.red}18`,
                      color: c.pass ? K.grn : K.red,
                    }}>{c.pass ? "✓" : "✗"}</span>
                    <div style={{ flex: 1 }}>
                      <div className="scalp-check-label">{c.label}</div>
                      <div className="scalp-check-val">{c.val}</div>
                    </div>
                  </div>
                ))}
              </div>
              <div style={{ marginTop: 12, padding: "9px 14px", background: `${vc}0c`, border: `1px solid ${vc}30`, borderRadius: 6, textAlign: "center" }}>
                <span style={{ fontSize: 14, fontWeight: 800, color: vc, fontFamily: F.mono, letterSpacing: "0.06em" }}>
                  [{calc.passN}/{calc.checks.length}] {calc.verdict === "GO" ? "ALL CLEAR — 진입 가능" : calc.verdict === "CAUTION" ? "CAUTION — 조건부 진입" : "NO ENTRY — 대기"}
                  {calc.trendConflict && " | ⚠ 역추세(Counter-Trend)"}
                </span>
              </div>
            </div>

            {/* ── Trading Session ── */}
            <div className="scalp-box">
              <Sec icon="📋" title="트레이딩 세션 (Trading Session)" tag={session ? session.phase : 'OFF'} tagC={session ? PHASE_COLORS[session.phase] : K.dim} />
              {!session ? (
                <button className="scalp-session-btn primary" style={{ width: '100%', marginTop: 8 }} onClick={handleStartSession}>
                  🚀 세션 시작 — 시나리오 생성
                </button>
              ) : (
                <>
                  <div className="scalp-session-bar">
                    <span className={`scalp-session-phase ${session.phase}`}>
                      {PHASE_LABELS[session.phase]}
                    </span>
                    <span style={{ fontSize: 10, color: K.dim }}>{formatHoldTime(Date.now() - session.startedAt)}</span>
                    <div style={{ flex: 1 }} />
                    {(session.phase === 'ALERT' || session.phase === 'WATCHING') && (
                      <button className="scalp-session-btn" onClick={() => { setEntryFormOpen(true); setEntryPrice(inputs.currentPrice.toFixed(2)); }}>
                        📝 진입 기록
                      </button>
                    )}
                    {(session.phase === 'ENTERED' || session.phase === 'MANAGING') && (
                      <button className="scalp-session-btn danger" onClick={() => handleRecordExit('MANUAL')}>
                        ✕ 청산 기록
                      </button>
                    )}
                    {session.phase === 'CLOSED' && (
                      <button className="scalp-session-btn" onClick={() => { setSession(null); handleStartSession(); }}>
                        🔄 새 세션
                      </button>
                    )}
                    <button className="scalp-session-btn danger" onClick={handleEndSession} style={{ fontSize: 10 }}>종료</button>
                  </div>

                  {/* Entry Form */}
                  {entryFormOpen && (
                    <div className="scalp-entry-form">
                      <label>진입 가격<input value={entryPrice} onChange={e => setEntryPrice(e.target.value)} /></label>
                      <label>계약 수<input value={entryContracts} onChange={e => setEntryContracts(e.target.value)} /></label>
                      <button className="scalp-session-btn primary" onClick={handleRecordEntry} style={{ gridColumn: 'span 2', marginTop: 4 }}>
                        ✅ 진입 확정 ({calc.isLong ? 'LONG' : 'SHORT'})
                      </button>
                    </div>
                  )}

                  {/* Scenarios (PLANNING/WATCHING/ALERT) */}
                  {['PLANNING', 'WATCHING', 'ALERT'].includes(session.phase) && session.scenarios.length > 0 && (
                    <>
                      <div className="scalp-opt-divider">🎯 오늘의 시나리오 (Game Plan)</div>
                      {session.scenarios.slice(0, 4).map(sc => (
                        <div key={sc.id} className={`scalp-scenario-card ${sc.confidence}`}>
                          <div className="scalp-scenario-header">
                            <span className="scalp-scenario-name">{sc.type === 'LONG' ? '▲' : '▼'} {sc.name}</span>
                            <span className={`scalp-scenario-badge ${sc.confidence}`}>{sc.confidence}</span>
                          </div>
                          <div className="scalp-scenario-detail">
                            📍 트리거: <span>{sc.trigger}</span><br />
                            ✅ 조건: {sc.condition}<br />
                            🎯 TP: <span>{sc.targetPrice.toFixed(2)}</span> │ 🛑 SL: <span>{sc.stopPrice.toFixed(2)}</span> │ R:R <span>{sc.rr}:1</span>
                          </div>
                        </div>
                      ))}
                    </>
                  )}

                  {/* Key Level Monitor (WATCHING/ALERT) */}
                  {['WATCHING', 'ALERT'].includes(session.phase) && session.keyLevels.length > 0 && (
                    <>
                      <div className="scalp-opt-divider">📍 키 레벨 모니터</div>
                      {(() => {
                        const alerts = session.activeAlerts.length > 0 ? session.activeAlerts : checkAlerts(inputs.currentPrice, session.keyLevels);
                        const sortedAlerts = [...alerts].sort((a, b) => b.level.price - a.level.price);
                        let currentInserted = false;
                        return sortedAlerts.map((alert, i) => {
                          const items = [];
                          if (!currentInserted && alert.level.price < inputs.currentPrice) {
                            items.push(
                              <div key="current" className="scalp-level-current">
                                ── {inputs.currentPrice.toFixed(2)} (현재가) ──
                              </div>
                            );
                            currentInserted = true;
                          }
                          const dotColor = alert.level.type === 'SUPPORT' ? K.grn : alert.level.type === 'RESISTANCE' ? K.red : K.acc;
                          items.push(
                            <div key={i} className="scalp-level-row">
                              <span className="scalp-level-dot" style={{ background: dotColor }} />
                              <span className="scalp-level-price">{alert.level.price.toFixed(2)}</span>
                              <span className="scalp-level-label">{alert.level.label} ({'★'.repeat(alert.level.strength)})</span>
                              <span className="scalp-level-dist">{alert.proximityPct > 0 ? `${alert.proximityPct.toFixed(2)}%` : '—'}</span>
                              <span className={`scalp-level-status ${alert.status}`}>{alert.status.replace('_', ' ')}</span>
                            </div>
                          );
                          return items;
                        });
                      })()}
                    </>
                  )}

                  {/* Position Management (ENTERED/MANAGING) */}
                  {session.entry && ['ENTERED', 'MANAGING'].includes(session.phase) && (() => {
                    const posEval = evaluatePosition(session.entry!, inputs.currentPrice, calc, calc.cfg);
                    const exitSugg = suggestExitAction(session.entry!, inputs.currentPrice, calc);
                    return (
                      <>
                        <div className="scalp-opt-divider">📊 포지션 관리</div>
                        <div className={`scalp-position-panel ${session.entry!.direction}`}>
                          <div className="scalp-flex">
                            <Met label="방향" value={`${session.entry!.direction} ${session.entry!.contracts}계약`} color={session.entry!.direction === 'LONG' ? K.grn : K.red} />
                            <Met label="진입가" value={session.entry!.price.toFixed(2)} />
                            <Met label="P&L" value={`${posEval.pnlPoints >= 0 ? '+' : ''}${posEval.pnlPoints}pt`} color={posEval.pnlPoints >= 0 ? K.grn : K.red} big />
                            <Met label="R배수" value={`${posEval.currentR >= 0 ? '+' : ''}${posEval.currentR}R`} color={posEval.currentR >= 0 ? K.grn : K.red} />
                          </div>
                          <div className="scalp-flex" style={{ marginTop: 6 }}>
                            <Met label="스탑 모드" value={posEval.stopMode} />
                            <Met label="현재 SL" value={posEval.currentSL.toFixed(2)} color={K.red} />
                            <Met label="보유시간" value={formatHoldTime(posEval.holdMs)} />
                            <Met label="P&L ($)" value={fmtMoney(Math.abs(posEval.pnlUSD), cfg.sym)} color={posEval.pnlUSD >= 0 ? K.grn : K.red} />
                          </div>
                          <div className="scalp-position-action" style={{ marginTop: 8 }}>
                            <span style={{ fontWeight: 600 }}>{posEval.action}</span><br />
                            <span style={{ color: K.dim }}>{posEval.reason}</span>
                          </div>
                          {exitSugg.shouldExit && (
                            <div style={{ marginTop: 6, padding: '6px 10px', background: 'rgba(255,23,68,0.08)', borderRadius: 4, fontSize: 11, color: K.red }}>
                              ⚠ 청산 권고: {exitSugg.reason}
                            </div>
                          )}
                        </div>
                      </>
                    );
                  })()}

                  {/* Closed Result */}
                  {session.phase === 'CLOSED' && session.exitRecord && (
                    <>
                      <div className="scalp-opt-divider">✅ 세션 결과</div>
                      <div className="scalp-flex">
                        <Met label="결과" value={session.exitRecord.pnlPoints >= 0 ? 'WIN' : 'LOSS'} color={session.exitRecord.pnlPoints >= 0 ? K.grn : K.red} big />
                        <Met label="P&L" value={`${session.exitRecord.pnlPoints >= 0 ? '+' : ''}${session.exitRecord.pnlPoints}pt`} color={session.exitRecord.pnlPoints >= 0 ? K.grn : K.red} />
                        <Met label="P&L ($)" value={fmtMoney(Math.abs(session.exitRecord.pnlUSD), cfg.sym)} color={session.exitRecord.pnlUSD >= 0 ? K.grn : K.red} />
                        <Met label="보유시간" value={formatHoldTime(session.exitRecord.holdDuration)} />
                        <Met label="사유" value={session.exitRecord.reason} />
                      </div>
                    </>
                  )}
                </>
              )}
            </div>

            {/* Z-Score */}
            <div className="scalp-box">
              <Sec icon="📐" title="Z-스코어 분석" tag="통계적 위치" infoId="zscore" />
              <div className="scalp-flex">
                <Met label="Z-스코어 (Z)" value={fmt(calc.z)} color={calc.zColor} big />
                <Met label="시그널" value={calc.zSignal} color={calc.zColor} />
                <Met label="유의확률 (P-Value)" value={fmtPct(calc.pVal)} sub="양측검정" />
                <Met label="이격" value={fmt(inputs.currentPrice - inputs.ma, 1) + "p"} sub="vs MA" />
              </div>
              <ZBar z={calc.z} />
              <div className="scalp-detail" style={{ marginTop: 12 }}>
                <Term id="zscore">Z</Term> = ({fmt(inputs.currentPrice, 2)} − {fmt(inputs.ma, 2)}) / {fmt(inputs.stdDev, 2)} = <span style={{ color: calc.zColor, fontWeight: 700 }}>{fmt(calc.z)}</span>
                {" "}→ <Term id="ma">MA</Term>에서 {fmt(Math.abs(calc.z))}<Term id="sigma">σ</Term> {calc.z < 0 ? "하방" : "상방"} | 이격 확률 {fmtPct(calc.pVal)}
              </div>
            </div>

            {/* ── Composite Trend (SMC + OBV + Volume) ── */}
            {calc.compositeTrend && (
              <div className="scalp-box">
                <Sec icon="📊" title="복합 추세 판단 (SMC + OBV + Volume)"
                  tag={calc.compositeTrend.bias}
                  tagC={calc.compositeTrend.bias === 'BULLISH' ? K.grn : calc.compositeTrend.bias === 'BEARISH' ? K.red : K.ylw}
                  infoId="compositeTrend" />
                <div className="scalp-flex" style={{ marginTop: 10, marginBottom: 8 }}>
                  <Met label="추세 방향" value={calc.compositeTrend.bias === 'BULLISH' ? '상승' : calc.compositeTrend.bias === 'BEARISH' ? '하락' : '횡보'}
                    color={calc.compositeTrend.bias === 'BULLISH' ? K.grn : calc.compositeTrend.bias === 'BEARISH' ? K.red : K.ylw} big />
                  <Met label="복합 점수" value={`${calc.compositeTrend.score > 0 ? '+' : ''}${calc.compositeTrend.score.toFixed(0)}`}
                    color={calc.compositeTrend.score > 0 ? K.grn : calc.compositeTrend.score < 0 ? K.red : K.dim} big />
                  <Met label="확신도" value={`${calc.compositeTrend.confidence}%`} />
                </div>

                {/* Component bars */}
                <div style={{ display: 'grid', gridTemplateColumns: '80px 1fr 50px', gap: '6px 8px', alignItems: 'center', fontSize: 9.5, marginTop: 8 }}>
                  {Object.entries(calc.compositeTrend.components).map(([key, comp]) => {
                    const pct = clamp((comp.score + 100) / 200 * 100, 2, 98);
                    const barColor = comp.score > 15 ? K.grn : comp.score < -15 ? K.red : K.dim;
                    return (
                      <div key={key} style={{ display: 'contents' }}>
                        <span style={{ color: K.dim, fontFamily: F.mono }}>
                          {key === 'smcTrend' ? 'SMC 구조' : key === 'obvMomentum' ? 'OBV 모멘텀' : '거래량 추세'}
                          <span style={{ opacity: 0.5, marginLeft: 4 }}>({comp.weight}%)</span>
                        </span>
                        <div style={{ height: 6, background: `${K.brd}`, borderRadius: 3, position: 'relative', overflow: 'hidden' }}>
                          <div style={{ position: 'absolute', left: '50%', top: 0, bottom: 0, width: 1, background: K.dim }} />
                          <div style={{
                            position: 'absolute',
                            left: comp.score >= 0 ? '50%' : `${pct}%`,
                            width: `${Math.abs(pct - 50)}%`,
                            top: 0, bottom: 0,
                            background: barColor,
                            borderRadius: 3,
                            transition: 'all 0.3s',
                          }} />
                        </div>
                        <span style={{ color: barColor, fontFamily: F.mono, textAlign: 'right' }}>
                          {comp.label}
                        </span>
                      </div>
                    );
                  })}
                </div>

                {/* Interpretation */}
                <div className="scalp-detail" style={{ marginTop: 10 }}>
                  {calc.compositeTrend.reason}
                  {calc.trendConflict && (
                    <div style={{ marginTop: 8, padding: '8px 12px', background: `${K.org}15`, border: `1px solid ${K.org}40`, borderRadius: 6 }}>
                      <span style={{ color: K.org, fontWeight: 700 }}>
                        ⚠ 추세-방향 충돌: 복합추세 {calc.compositeTrend.bias === 'BEARISH' ? '하락' : '상승'} vs Z-Score {calc.isLong ? '롱' : '숏'}
                      </span>
                      <div style={{ color: K.org, fontSize: 11, marginTop: 4, opacity: 0.8 }}>
                        평균회귀(Z-Score)는 "가격이 MA 아래 → 매수" 판단, 추세지표(SMC+OBV+Vol)는 "{calc.compositeTrend.bias === 'BEARISH' ? '하락 구조 지속' : '상승 구조 지속'}" 판단. 역추세 진입은 리스크 증가.
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* ── MTF Structure Analysis ── */}
            <div className="scalp-box">
              <div className="scalp-opt-header" onClick={() => setMtfExpanded(v => !v)}>
                <Sec icon="🔀" title="멀티타임프레임 구조 (MTF Structure)"
                  tag={mtfAnalysis ? mtfAnalysis.signalType.replace(/_/g, ' ') : 'READY'}
                  tagC={mtfAnalysis?.direction === 'LONG' ? K.grn : mtfAnalysis?.direction === 'SHORT' ? K.red : K.dim} />
                <button className={`scalp-opt-toggle ${mtfExpanded ? 'open' : ''}`}>▼</button>
              </div>
              {mtfExpanded && (
                <div className="scalp-opt-content">
                  <button onClick={loadMTFData} disabled={mtfLoading} className="scalp-opt-run-btn">
                    {mtfLoading ? '⏳ Loading HTF + LTF...' : '📡 Load MTF Data (1H + 5min)'}
                  </button>
                  {mtfError && <div style={{ marginTop: 8, fontSize: 10, color: K.red }}>⚠ {mtfError}</div>}
                  {(mtfHTF.length > 0 || mtfLTF.length > 0) && (
                    <div className="scalp-opt-run-info">
                      <span>HTF: {mtfHTF.length}봉 (1H)</span>
                      <span>LTF: {mtfLTF.length}봉 (5min)</span>
                    </div>
                  )}
                  {mtfAnalysis && (
                    <>
                      <div className="scalp-opt-divider">HTF CONTEXT (1H)</div>
                      <div className="scalp-flex" style={{ marginBottom: 10 }}>
                        <Met label="추세 (Trend)" value={mtfAnalysis.htf.trend}
                          color={mtfAnalysis.htf.trend === 'BULLISH' ? K.grn : mtfAnalysis.htf.trend === 'BEARISH' ? K.red : K.dim} />
                        <Met label="추세 확신도" value={`${mtfAnalysis.htf.trendConfidence}%`} />
                        <Met label="가격 위치" value={mtfAnalysis.htf.pricePosition.replace(/_/g, ' ')} />
                        <Met label="레짐" value={mtfAnalysis.htf.regime} />
                      </div>
                      <div className="scalp-opt-params-grid">
                        <div className="scalp-opt-param">
                          <span className="scalp-opt-param-label">저항 (Resistance)</span>
                          <span className="scalp-opt-param-val" style={{ color: K.red }}>
                            {mtfAnalysis.htf.keyResistance?.toFixed(2) ?? '—'}
                          </span>
                        </div>
                        <div className="scalp-opt-param">
                          <span className="scalp-opt-param-label">지지 (Support)</span>
                          <span className="scalp-opt-param-val" style={{ color: K.grn }}>
                            {mtfAnalysis.htf.keySupport?.toFixed(2) ?? '—'}
                          </span>
                        </div>
                        <div className="scalp-opt-param">
                          <span className="scalp-opt-param-label">마지막 BOS</span>
                          <span className="scalp-opt-param-val">
                            {mtfAnalysis.htf.lastBOS ? `${mtfAnalysis.htf.lastBOS.direction} @ ${mtfAnalysis.htf.lastBOS.breakPrice.toFixed(2)}` : '—'}
                          </span>
                        </div>
                        <div className="scalp-opt-param">
                          <span className="scalp-opt-param-label">마지막 CHoCH</span>
                          <span className="scalp-opt-param-val">
                            {mtfAnalysis.htf.lastCHoCH ? `${mtfAnalysis.htf.lastCHoCH.direction} @ ${mtfAnalysis.htf.lastCHoCH.breakPrice.toFixed(2)}` : '—'}
                          </span>
                        </div>
                      </div>
                      <div className="scalp-detail" style={{ marginTop: 10 }}>
                        <span style={{ color: K.acc, fontWeight: 700 }}>스윙 구조: </span>
                        {mtfAnalysis.htf.swingHighs.slice(-4).map((sh, i) =>
                          <span key={`h${i}`} style={{ color: K.red, marginRight: 6 }}>H:{sh.price.toFixed(2)}</span>
                        )}
                        {mtfAnalysis.htf.swingLows.slice(-4).map((sl, i) =>
                          <span key={`l${i}`} style={{ color: K.grn, marginRight: 6 }}>L:{sl.price.toFixed(2)}</span>
                        )}
                      </div>

                      <div className="scalp-opt-divider">LTF SIGNAL (5min)</div>
                      <div className="scalp-flex" style={{ marginBottom: 10 }}>
                        <Met label="시그널" value={mtfAnalysis.ltf.signalType.replace(/_/g, ' ')}
                          color={mtfAnalysis.ltf.alignedWithHTF ? K.grn : K.dim} big />
                        <Met label="HTF 정합" value={mtfAnalysis.ltf.alignedWithHTF ? 'YES' : 'NO'}
                          color={mtfAnalysis.ltf.alignedWithHTF ? K.grn : K.red} />
                        <Met label="확신도" value={mtfAnalysis.ltf.confidence}
                          color={mtfAnalysis.ltf.confidence === 'HIGH' ? K.grn : mtfAnalysis.ltf.confidence === 'MEDIUM' ? K.org : K.dim} />
                      </div>

                      {/* Combined Verdict */}
                      <div style={{
                        marginTop: 12, padding: '10px 14px',
                        background: mtfAnalysis.direction === 'LONG' ? `${K.grn}0c` :
                                    mtfAnalysis.direction === 'SHORT' ? `${K.red}0c` : `${K.dim}08`,
                        border: `1px solid ${
                          mtfAnalysis.direction === 'LONG' ? `${K.grn}30` :
                          mtfAnalysis.direction === 'SHORT' ? `${K.red}30` : `${K.dim}20`
                        }`,
                        borderRadius: 6, textAlign: 'center',
                      }}>
                        <div style={{
                          fontSize: 14, fontWeight: 800, fontFamily: F.mono, letterSpacing: '0.06em',
                          color: mtfAnalysis.direction === 'LONG' ? K.grn :
                                 mtfAnalysis.direction === 'SHORT' ? K.red : K.dim,
                        }}>
                          {mtfAnalysis.direction} — {mtfAnalysis.signalType.replace(/_/g, ' ')} ({mtfAnalysis.confidence})
                        </div>
                        <div style={{ fontSize: 10, color: K.dim, marginTop: 4 }}>
                          {mtfAnalysis.summary}
                        </div>
                      </div>

                      {mtfAnalysis.direction !== 'NEUTRAL' && (
                        <div className="scalp-opt-params-grid" style={{ marginTop: 10 }}>
                          <div className="scalp-opt-param">
                            <span className="scalp-opt-param-label">진입 구간</span>
                            <span className="scalp-opt-param-val">{mtfAnalysis.entryZone}</span>
                          </div>
                          <div className="scalp-opt-param">
                            <span className="scalp-opt-param-label">구조 손절 (SL)</span>
                            <span className="scalp-opt-param-val" style={{ color: K.red }}>
                              {mtfAnalysis.stopLoss?.toFixed(2) ?? '—'}
                            </span>
                          </div>
                          <div className="scalp-opt-param">
                            <span className="scalp-opt-param-label">구조 목표 (TP)</span>
                            <span className="scalp-opt-param-val" style={{ color: K.grn }}>
                              {mtfAnalysis.takeProfit?.toFixed(2) ?? '—'}
                            </span>
                          </div>
                          <div className="scalp-opt-param">
                            <span className="scalp-opt-param-label">LTF 사유</span>
                            <span className="scalp-opt-param-val" style={{ fontSize: 9 }}>{mtfAnalysis.ltf.reason}</span>
                          </div>
                        </div>
                      )}
                    </>
                  )}
                </div>
              )}
            </div>

            {/* EV Engine */}
            <div className="scalp-box">
              <Sec icon="⚡" title="기대값 엔진 (EV Engine)" tag="기대값" tagC={calc.netEV >= 0 ? K.grn : K.red} infoId="evEngine" />
              <div className="scalp-flex">
                <Met label="순 기대값 (Net EV)" value={`${calc.netEV >= 0 ? "+" : ""}${fmt(calc.netEV)}t`} color={calc.netEV >= 0 ? K.grn : K.red} big sub={`${calc.netEV >= 0 ? "+" : "−"} ${fmtMoney(Math.abs(calc.netEVusd), cfg.sym)}`} />
                <Met label="총 기대값 (Gross EV)" value={`${fmt(calc.grossEV)}t`} sub="비용 차감 전" />
                <Met label="마찰비용 (Friction)" value={`${fmt(calc.friction)}t`} color={K.org} sub="슬리피지+수수료" />
                <Met label="손익비 (R:R)" value={`${fmt(calc.b, 1)}:1`} />
              </div>
              <EVBar gross={calc.grossEV} net={calc.netEV} />
              <div className="scalp-detail" style={{ marginTop: 12 }}>
                <Term id="ev">EV</Term> = {fmtPct(calc.p)}×{inputs.avgWin} − {fmtPct(calc.q)}×{inputs.avgLoss} − <Term id="friction">{fmt(calc.friction)}t</Term> = <span style={{ color: calc.netEV >= 0 ? K.grn : K.red, fontWeight: 700 }}>{fmt(calc.netEV)}t</span>
                {calc.netEV > 0
                  ? <> | 100회 기대순익: <span style={{ color: K.grn }}>+{fmtMoney(Math.abs(calc.netEVusd) * 100, cfg.sym)}</span></>
                  : <> | ⚠ 반복매매 시 손실 누적</>}
              </div>
            </div>

            {/* Kelly + Position */}
            <div className="scalp-two-col">
              <div className="scalp-box">
                <Sec icon="🎰" title="켈리 기준 (Kelly)" tag="확신도" tagC={calc.kelly > 0 ? K.grn : K.red} infoId="kellyCriterion" />
                <div className="scalp-flex">
                  <Met label="풀 켈리" value={fmtPct(calc.kelly)} />
                  <Met label="하프 켈리 (½K)" value={fmtPct(calc.halfKelly)} color={K.acc} sub="권장 배팅비중" big />
                </div>
                <KGauge hk={calc.halfKelly} conv={calc.conviction} />
                <div style={{ marginTop: 10, fontSize: 9.5, color: K.dim, fontFamily: F.mono }}>
                  <Term id="kelly">f*</Term> = (<Term id="rr">b</Term>×p − q) / <Term id="rr">b</Term> = ({fmt(calc.b, 1)}×{fmtPct(calc.p)} − {fmtPct(calc.q)}) / {fmt(calc.b, 1)} = {fmtPct(calc.kelly)}
                </div>
              </div>
              <div className="scalp-box">
                <Sec icon="📏" title="포지션 계산기 (Position Sizer)" />
                <div className="scalp-flex">
                  <Met label="리스크 예산" value={fmtMoney(calc.riskBudget, cfg.sym)} sub={`잔고의 ${inputs.riskPct}%`} />
                  <Met label="계약당 위험" value={fmtMoney(calc.riskPerContract, cfg.sym)} sub={`${fmt(calc.adaptiveStop)}p × ${cfg.sym}${cfg.ptVal.toLocaleString()}`} />
                </div>
                <div className="scalp-position-center">
                  <div style={{ fontSize: 9, color: K.mut, fontFamily: F.mono, textTransform: "uppercase", marginBottom: 6 }}>권장 계약 수</div>
                  <div className="scalp-position-number">{calc.recContracts}</div>
                  <div style={{ fontSize: 9.5, color: K.dim, fontFamily: F.mono, marginTop: 4 }}>최대 {calc.maxContracts}계약 / 스캘핑 2계약 상한</div>
                </div>
              </div>
            </div>

            {/* ATR + RR Map */}
            <div className="scalp-box">
              <Sec icon="🛡️" title="변동성 손절 & 손익비 (ATR Stop)" tag={`Z-${calc.zZone}`} tagC={calc.zZone === 'STRONG' ? '#f9a825' : calc.zZone === 'MILD' ? '#78909c' : '#546e7a'} />
              {/* Z-Zone adaptive info */}
              <div style={{
                padding: '8px 10px', marginBottom: 8, borderRadius: 6,
                background: calc.zZone === 'STRONG' ? '#f9a82508' : calc.zZone === 'MILD' ? '#78909c08' : '#546e7a08',
                border: `1px solid ${calc.zZone === 'STRONG' ? '#f9a82530' : calc.zZone === 'MILD' ? '#78909c20' : '#546e7a20'}`,
                fontSize: 10, fontFamily: F.mono, lineHeight: 1.6,
              }}>
                <div style={{ fontWeight: 700, color: calc.zZone === 'STRONG' ? '#f9a825' : calc.zZone === 'MILD' ? '#90a4ae' : '#78909c', marginBottom: 3 }}>
                  Z-Zone: {calc.zZoneLabel}
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '2px 8px' }}>
                  <span style={{ color: '#888' }}>기본 ATR</span>
                  <span style={{ color: '#ccc', textAlign: 'right' }}>{fmt(calc.atrStop, 2)}p</span>
                  <span style={{ color: '#666', fontSize: 9 }}>ATR×{inputs.atrMult}</span>
                  <span style={{ color: '#888' }}>Z보정 배수</span>
                  <span style={{ color: calc.zZone === 'STRONG' ? '#f9a825' : '#ccc', textAlign: 'right', fontWeight: 700 }}>×{calc.zStopMult}</span>
                  <span style={{ color: '#666', fontSize: 9 }}>{calc.zZone === 'STRONG' ? '넓은 스탑' : calc.zZone === 'NORMAL' ? '타이트 스탑' : '표준'}</span>
                  <span style={{ color: K.red }}>적응형 SL</span>
                  <span style={{ color: K.red, textAlign: 'right', fontWeight: 700 }}>{fmt(calc.adaptiveStop, 2)}p</span>
                  <span style={{ color: '#666', fontSize: 9 }}>{fmt(calc.atrStop, 2)}×{calc.zStopMult}</span>
                </div>
                <div style={{ marginTop: 4, paddingTop: 4, borderTop: '1px solid #ffffff08', color: '#78909c', fontSize: 9 }}>
                  MA까지 {fmt(calc.maDistance, 2)}p ({calc.maDistR.toFixed(1)}R) | 회귀확률 {(calc.revertProb * 100).toFixed(0)}%
                </div>
              </div>
              <div className="scalp-flex" style={{ marginBottom: 6 }}>
                <Met label="적응형 손절" value={`${fmt(calc.adaptiveStop)}p`} sub={`ATR ${fmt(calc.atrStop)}p × ${calc.zStopMult}`} color={K.red} />
                <Met label="손절가 (SL)" value={fmt(calc.sl, 2)} color={K.red} />
                <Met label="익절 1.5R" value={fmt(calc.tp15, 2)} color="#69f0ae" />
                <Met label="익절 2R" value={fmt(calc.tp2, 2)} color={K.grn} />
                <Met label="익절 3R" value={fmt(calc.tp3, 2)} color={K.grn} />
              </div>
              <RRVis entry={inputs.currentPrice} sl={calc.sl} tp15={calc.tp15} tp2={calc.tp2} tp3={calc.tp3} isLong={calc.isLong} ma={inputs.ma} zZone={calc.zZone} zStopMult={calc.zStopMult} maDistR={calc.maDistR} revertProb={calc.revertProb} stdDev={inputs.stdDev} z={calc.z} volumeSR={calc.volumeSR} />
              {candles.length >= 5 && (
                <PriceChart candles={candles} ma={inputs.ma} stdDev={inputs.stdDev} entry={inputs.currentPrice} sl={calc.sl} tp15={calc.tp15} tp2={calc.tp2} tp3={calc.tp3} isLong={calc.isLong} volumeSR={calc.volumeSR} maPeriod={maPeriod} z={calc.z} dates={candleDates} />
              )}
              <div className="scalp-pnl-row">
                <div className="scalp-pnl-card" style={{ background: `${K.grn}0a`, border: `1px solid ${K.grn}20` }}>
                  <div className="scalp-pnl-label">익절 1.5R 손익 ({calc.recContracts}ct)</div>
                  <div className="scalp-pnl-value" style={{ color: K.grn }}>+{fmtMoney(calc.pnlTP1, cfg.sym)}</div>
                </div>
                <div className="scalp-pnl-card" style={{ background: `${K.red}0a`, border: `1px solid ${K.red}20` }}>
                  <div className="scalp-pnl-label">손절 손익 ({calc.recContracts}ct)</div>
                  <div className="scalp-pnl-value" style={{ color: K.red }}>-{fmtMoney(calc.pnlSL, cfg.sym)}</div>
                </div>
              </div>
            </div>

            {/* Volume S/R Levels */}
            {calc.volumeSR && calc.volumeSR.levels.length > 0 && (
              <div className="scalp-box">
                <Sec icon="📊" title="일봉 거래량 S/R" tag={calc.volumeSR.volumeTrend} tagC={calc.volumeSR.volumeTrend === 'INCREASING' ? K.grn : calc.volumeSR.volumeTrend === 'DECREASING' ? K.red : '#78909c'} />
                <div style={{ display: 'flex', gap: 6, marginBottom: 8 }}>
                  <div style={{ flex: 1, padding: '4px 8px', borderRadius: 6, background: calc.volumeSR.priceInZone === 'SUPPORT' ? `${K.grn}15` : calc.volumeSR.priceInZone === 'RESISTANCE' ? `${K.red}15` : '#ffffff06', border: `1px solid ${calc.volumeSR.priceInZone === 'SUPPORT' ? K.grn : calc.volumeSR.priceInZone === 'RESISTANCE' ? K.red : '#333'}30`, textAlign: 'center' }}>
                    <div style={{ fontSize: 9, color: '#888' }}>현재 위치</div>
                    <div style={{ fontSize: 13, fontWeight: 700, color: calc.volumeSR.priceInZone === 'SUPPORT' ? K.grn : calc.volumeSR.priceInZone === 'RESISTANCE' ? K.red : '#ccc' }}>
                      {calc.volumeSR.priceInZone === 'SUPPORT' ? '지지구간' : calc.volumeSR.priceInZone === 'RESISTANCE' ? '저항구간' : '중립'}
                    </div>
                  </div>
                  {calc.volumeSR.nearestSupport && (
                    <div style={{ flex: 1, padding: '4px 8px', borderRadius: 6, background: `${K.grn}08`, textAlign: 'center' }}>
                      <div style={{ fontSize: 9, color: '#888' }}>최근접 지지</div>
                      <div style={{ fontSize: 13, fontWeight: 700, color: K.grn }}>{fmt(calc.volumeSR.nearestSupport, 2)}</div>
                    </div>
                  )}
                  {calc.volumeSR.nearestResistance && (
                    <div style={{ flex: 1, padding: '4px 8px', borderRadius: 6, background: `${K.red}08`, textAlign: 'center' }}>
                      <div style={{ fontSize: 9, color: '#888' }}>최근접 저항</div>
                      <div style={{ fontSize: 13, fontWeight: 700, color: K.red }}>{fmt(calc.volumeSR.nearestResistance, 2)}</div>
                    </div>
                  )}
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4 }}>
                  {calc.volumeSR.supports.map((s, i) => (
                    <div key={`s${i}`} style={{ padding: '3px 6px', borderRadius: 4, background: `${K.grn}08`, border: `1px solid ${K.grn}18`, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontSize: 9, color: K.grn }}>S{i + 1}</span>
                      <span style={{ fontSize: 11, fontWeight: 600, color: '#ccc', fontFamily: 'monospace' }}>{fmt(s.price, 2)}</span>
                      <span style={{ fontSize: 8, color: '#888' }}>{s.volumeScore.toFixed(1)}x {'●'.repeat(s.strength)}</span>
                    </div>
                  ))}
                  {calc.volumeSR.resistances.map((r, i) => (
                    <div key={`r${i}`} style={{ padding: '3px 6px', borderRadius: 4, background: `${K.red}08`, border: `1px solid ${K.red}18`, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontSize: 9, color: K.red }}>R{i + 1}</span>
                      <span style={{ fontSize: 11, fontWeight: 600, color: '#ccc', fontFamily: 'monospace' }}>{fmt(r.price, 2)}</span>
                      <span style={{ fontSize: 8, color: '#888' }}>{r.volumeScore.toFixed(1)}x {'●'.repeat(r.strength)}</span>
                    </div>
                  ))}
                </div>
                <div style={{ marginTop: 6, fontSize: 9, color: '#666', lineHeight: 1.4 }}>
                  14일 일봉 거래량 기반. 고거래량일 고가/저가 = 기관 매물대. 강도(●): 거래량 비율 ≥2x=강, ≥1.5x=보통, ≥1.2x=약.
                </div>
              </div>
            )}

            {/* Basis Spread */}
            <div className="scalp-box">
              <Sec icon="📉" title="선현물 스프레드 (Basis)" tag={calc.basisState} tagC={calc.basis > 2 ? K.cyn : calc.basis < -2 ? K.org : "#78909c"} infoId="basisSpread" />
              <div className="scalp-flex">
                <Met label={`${spotLabel} (현물)`} value={fmt(inputs.spotPrice, 2)} />
                <Met label={`${futLabel} (선물)`} value={fmt(inputs.futuresPrice, 2)} />
                <Met label="Basis" value={`${calc.basis >= 0 ? "+" : ""}${fmt(calc.basis, 2)}p`} color={calc.basis > 2 ? K.cyn : calc.basis < -2 ? K.org : "#78909c"} big />
                <Met label="Basis %" value={`${fmt(calc.basisPct, 3)}%`} />
              </div>
              <BasisBar basis={calc.basis} />
              <div className="scalp-detail" style={{ marginTop: 10, fontSize: 9.5, lineHeight: 1.5 }}>
                {calc.basisState === "CONTANGO"
                  ? "선물 > 현물: 콘탱고 (정상). 보유비용 반영. 만기 수렴 시 선물 하방압력."
                  : calc.basisState === "BACKWARDATION"
                    ? "선물 < 현물: 백워데이션. 시장 스트레스 시그널. 차익매수세(프로그램) 유입 가능."
                    : "현물 ≈ 선물: 적정가(Fair Value) 근처. 차익거래 유인 미미."}
              </div>
            </div>

            {/* Formula Ref */}
            <div className="scalp-box">
              <Sec icon="📖" title="공식 참조 (Formula Reference)" tag="QUICK REF" tagC={K.dim} />
              <div className="scalp-formula-grid">
                {[
                  { t: "Z-Score", f: "Z = (Price − MA) / σ", d: "±2σ → 95.4% 신뢰구간 이탈" },
                  { t: "Expected Value", f: "EV = P(W)·W − P(L)·L − Cost", d: "양수일 때만 진입" },
                  { t: "Kelly Criterion", f: "f* = (b·p − q) / b", d: "Half-Kelly 실전 권장" },
                  { t: "True Range", f: "TR = max(H−L, |H−C'|, |L−C'|)", d: "ATR = avg(TR, 14)" },
                ].map((r, i) => (
                  <div key={i} className="scalp-formula-card">
                    <div className="scalp-formula-title">{r.t}</div>
                    <div className="scalp-formula-expr">{r.f}</div>
                    <div className="scalp-formula-desc">{r.d}</div>
                  </div>
                ))}
              </div>
            </div>

          </div>
        </div>
      </div>

      {/* Footer */}
      <div className="scalp-footer">
        ⚠ 매매 보조 도구이며 투자 권유가 아닙니다. 모든 매매 결정의 책임은 본인에게 있습니다.
      </div>
    </div>
  );
}
