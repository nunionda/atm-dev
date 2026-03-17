import { useState, useEffect, useCallback, useRef } from 'react';
import { createChart, ColorType, type IChartApi, type Time } from 'lightweight-charts';
import {
  fetchFuturesAnalysis,
  fetchFuturesTickers,
  triggerFuturesBacktest,
  fetchAnalyticsData,
  fetchRollSchedule,
  fetchContractSpecs,
  type FuturesAnalysis,
  type FuturesTickerInfo,
  type FuturesBacktestResult,
  type FuturesMonteCarloResult,
  type ContractSpecs,
} from '../lib/api';
import { EquityCurve } from '../components/performance/EquityCurve';
import { ChartSkeleton, ScoreCardsSkeleton } from '../components/common/Skeleton';
import { useFuturesScalp, type DataMode } from '../hooks/useFuturesScalp';
import {
  ASSETS,
  SAMPLE_CLOSE,
  SAMPLE_OHLC,
  clamp,
  fmt,
  fmtUSD,
  fmtPct,
} from '../lib/futuresScalpEngine';
import './FuturesTrading.css';

// ══════════════════════════════════════════
// Currency Helper — 한국 지수는 ₩, 나머지는 $
// ══════════════════════════════════════════

const KRW_TICKERS = new Set(['^KS200', '^KQ11', '^KQ150']);

function getTickerCurrency(ticker: string): { symbol: string; locale: string; code: string } {
  if (KRW_TICKERS.has(ticker)) {
    return { symbol: '₩', locale: 'ko-KR', code: 'KRW' };
  }
  return { symbol: '$', locale: 'en-US', code: 'USD' };
}

function formatPrice(value: number, ticker: string, decimals = 2): string {
  const { symbol, locale } = getTickerCurrency(ticker);
  return `${symbol}${value.toLocaleString(locale, { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}`;
}

function formatPnL(value: number, ticker: string): string {
  const { symbol, locale } = getTickerCurrency(ticker);
  if (value < 0) return `-${symbol}${Math.abs(value).toLocaleString(locale)}`;
  return `${symbol}${value.toLocaleString(locale)}`;
}

// ══════════════════════════════════════════
// Layer Score Bar
// ══════════════════════════════════════════

function LayerScoreBar({ label, score, maxScore, layerClass, signals }: {
  label: string; score: number; maxScore: number; layerClass: string; signals: string[];
}) {
  const pct = maxScore > 0 ? (score / maxScore) * 100 : 0;
  return (
    <div>
      <div className="layer-row">
        <span className="layer-label">{label}</span>
        <div className="layer-bar-container">
          <div
            className={`layer-bar-fill ${layerClass}`}
            style={{ width: `${pct}%` }}
          />
        </div>
        <span className="layer-score-text">{score.toFixed(1)} / {maxScore}</span>
      </div>
      {signals.length > 0 && (
        <div className="layer-signals" style={{ marginLeft: 90 }}>
          {signals.map((s, i) => <span key={i} className="signal-tag">{s}</span>)}
        </div>
      )}
    </div>
  );
}

// ══════════════════════════════════════════
// Z-Score Gauge
// ══════════════════════════════════════════

function ZScoreGauge({ zscore }: { zscore: number }) {
  // Map zscore -3..+3 to 0..100%
  const clamped = Math.max(-3, Math.min(3, zscore));
  const pct = ((clamped + 3) / 6) * 100;

  let color = '#95a5a6';
  if (zscore <= -2) color = '#e74c3c';
  else if (zscore <= -1) color = '#e67e22';
  else if (zscore >= 2) color = '#e74c3c';
  else if (zscore >= 1) color = '#e67e22';

  return (
    <div className="zscore-gauge-container">
      <div className="zscore-gauge">
        <span className="zscore-gauge-label">Z-Score</span>
        <div className="zscore-gauge-track">
          <div className="zscore-gauge-needle" style={{ left: `${pct}%` }} />
        </div>
        <span className="zscore-gauge-value" style={{ color }}>{zscore.toFixed(2)}</span>
      </div>
      <div className="zscore-gauge-labels">
        <span>-3 (Oversold)</span>
        <span>-2</span>
        <span>-1</span>
        <span>0</span>
        <span>+1</span>
        <span>+2</span>
        <span>+3 (Overbought)</span>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════
// Backtest Metrics Cards
// ══════════════════════════════════════════

function MetricCard({ label, value, colorize }: { label: string; value: string; colorize?: boolean }) {
  let cls = '';
  if (colorize) {
    const num = parseFloat(value);
    if (!isNaN(num)) cls = num >= 0 ? 'positive' : 'negative';
  }
  return (
    <div className="backtest-metric-card">
      <div className="metric-label">{label}</div>
      <div className={`metric-value ${cls}`}>{value}</div>
    </div>
  );
}

// ══════════════════════════════════════════
// Monte Carlo Distribution Histogram
// ══════════════════════════════════════════

function MonteCarloDistribution({ mc }: { mc: FuturesMonteCarloResult }) {
  if (!mc.return_distribution?.length && !mc.mdd_distribution?.length) return null;

  const renderHistogram = (
    data: { bin: number; count: number }[],
    title: string,
    color: string,
    percentiles?: { p5: number; p25: number; p50: number; p75: number; p95: number },
  ) => {
    if (!data.length) return null;
    const maxCount = Math.max(...data.map(d => d.count), 1);
    return (
      <div className="mc-dist-panel">
        <div className="mc-dist-title">{title}</div>
        {percentiles && (
          <div className="mc-percentiles">
            <span>P5: {percentiles.p5.toFixed(1)}%</span>
            <span>P25: {percentiles.p25.toFixed(1)}%</span>
            <span className="mc-p-median">P50: {percentiles.p50.toFixed(1)}%</span>
            <span>P75: {percentiles.p75.toFixed(1)}%</span>
            <span>P95: {percentiles.p95.toFixed(1)}%</span>
          </div>
        )}
        <div className="mc-histogram">
          {data.map((d, i) => (
            <div key={i} className="mc-bar-col" title={`${d.bin.toFixed(1)}%: ${d.count} sims`}>
              <div
                className="mc-bar"
                style={{
                  height: `${(d.count / maxCount) * 100}%`,
                  background: color,
                }}
              />
              {i % 4 === 0 && <span className="mc-bin-label">{d.bin.toFixed(0)}</span>}
            </div>
          ))}
        </div>
      </div>
    );
  };

  return (
    <div className="mc-distribution">
      {renderHistogram(mc.return_distribution, 'Return Distribution (1000 sims, 252 days)', 'rgba(52, 152, 219, 0.7)', mc.return_percentiles)}
      {renderHistogram(mc.mdd_distribution, 'Max Drawdown Distribution', 'rgba(231, 76, 60, 0.7)')}
    </div>
  );
}

// ══════════════════════════════════════════
// Exit Reason Breakdown
// ══════════════════════════════════════════

function ExitReasonBreakdown({ reasons }: { reasons: Record<string, number> }) {
  const entries = Object.entries(reasons).sort((a, b) => b[1] - a[1]);
  if (entries.length === 0) return null;
  const total = entries.reduce((s, [, v]) => s + v, 0);
  const maxCount = Math.max(...entries.map(([, v]) => v), 1);

  const reasonLabels: Record<string, string> = {
    ES1: 'Hard Stop (-5%)',
    ES_ATR_SL: 'ATR Stop Loss',
    ES_ATR_TP: 'ATR Take Profit',
    ES_CHANDELIER: 'Chandelier Exit',
    ES3: 'Trailing Stop',
    ES_CHOCH: 'CHoCH Reversal',
    ES5: 'Max Holding Days',
    FORCED_CLOSE: 'End of Period',
  };

  return (
    <div className="exit-breakdown">
      <div className="exit-breakdown-title">EXIT REASONS</div>
      {entries.map(([reason, count]) => (
        <div key={reason} className="exit-row">
          <span className="exit-label">{reasonLabels[reason] || reason}</span>
          <div className="exit-bar-wrap">
            <div className="exit-bar" style={{ width: `${(count / maxCount) * 100}%` }} />
          </div>
          <span className="exit-count">{count} ({(count / total * 100).toFixed(0)}%)</span>
        </div>
      ))}
    </div>
  );
}

// ══════════════════════════════════════════
// Price Chart
// ══════════════════════════════════════════

function FuturesPriceChart({ ticker }: { ticker: string }) {
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

function ScalpNIn({ label, value, onChange, unit, step = 1, min, help, highlight }: {
  label: string; value: number; onChange: (v: number) => void; unit?: string;
  step?: number; min?: number; help?: string; highlight?: boolean;
}) {
  return (
    <div className="scalp-input-group">
      <label className={`scalp-input-label ${highlight ? 'auto' : ''}`}>
        {label} {highlight && <span style={{ fontSize: '0.5rem', color: '#00e676' }}>● AUTO</span>}
      </label>
      <div className="scalp-input-row">
        <input type="number" value={value} step={step} min={min}
          onChange={e => onChange(parseFloat(e.target.value) || 0)} />
        {unit && <span className="scalp-input-unit">{unit}</span>}
      </div>
      {help && <span className="scalp-input-help">{help}</span>}
    </div>
  );
}

function ZBar({ z }: { z: number }) {
  const pct = clamp((z + 4) / 8 * 100, 2, 98);
  const col = z < -2 ? '#00e676' : z > 2 ? '#ff1744' : z < -1 ? '#69f0ae' : z > 1 ? '#ff8a80' : '#78909c';
  return (
    <div className="scalp-zbar">
      <div className="scalp-zbar-track">
        <div className="scalp-zbar-zone-left" />
        <div className="scalp-zbar-zone-right" />
        {[12.5, 25, 37.5, 50, 62.5, 75, 87.5].map((p, i) => (
          <div key={i} style={{ position: 'absolute', left: `${p}%`, top: 0, bottom: 0, width: 1, background: 'var(--border-color, #333)' }} />
        ))}
        <div className="scalp-zbar-dot" style={{ left: `${pct}%`, background: col, boxShadow: `0 0 12px ${col}90` }} />
      </div>
      <div className="scalp-zbar-labels">
        <span>-4σ</span><span>-2σ</span><span>μ</span><span>+2σ</span><span>+4σ</span>
      </div>
    </div>
  );
}

function EVBar({ gross, net }: { gross: number; net: number }) {
  const max = 8;
  const nP = clamp(net / max * 50, -50, 50);
  return (
    <div style={{ marginTop: 10 }}>
      <div className="scalp-evbar-meta">
        <span>Gross: <span style={{ color: gross >= 0 ? '#00e676' : '#ff1744' }}>{fmt(gross)}t</span></span>
        <span>Friction: <span style={{ color: '#ffab40' }}>-{fmt(gross - net)}t</span></span>
        <span>Net: <span style={{ color: net >= 0 ? '#00e676' : '#ff1744', fontWeight: 700 }}>{fmt(net)}t</span></span>
      </div>
      <div className="scalp-evbar-track">
        <div className="scalp-evbar-center" />
        <div className="scalp-evbar-fill" style={{
          left: nP >= 0 ? '50%' : `${50 + nP}%`,
          width: `${Math.abs(nP)}%`,
          background: nP >= 0 ? '#00e676' : '#ff1744',
        }} />
      </div>
    </div>
  );
}

function KGauge({ hk, conv }: { hk: number; conv: string }) {
  const pct = clamp(hk * 100 / 25, 0, 100);
  const col = conv === 'NO EDGE' ? '#ff1744' : (conv === 'VERY LOW' || conv === 'LOW') ? '#ffab40' : conv === 'MODERATE' ? '#fdd835' : '#00e676';
  return (
    <>
      <div className="scalp-kgauge-track">
        <div className="scalp-kgauge-fill" style={{ width: `${pct}%`, background: `linear-gradient(90deg, ${col}50, ${col})` }} />
      </div>
      <div className="scalp-kgauge-labels">
        <span>0%</span>
        <span className="scalp-pill" style={{ background: `${col}15`, border: `1px solid ${col}35`, color: col }}>{conv}</span>
        <span>25%</span>
      </div>
    </>
  );
}

function RRVis({ entry, sl, tp15, tp2, tp3, cfg, currentPrice, magneticMA }: {
  entry: number; sl: number; tp15: number; tp2: number; tp3: number;
  cfg: { ptVal: number }; currentPrice?: number; magneticMA?: number;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const risk = Math.abs(entry - sl);
  const pnl = (p: number) => { const pts = Math.abs(p - entry); return { pts, usd: pts * cfg.ptVal }; };
  const rrRatio  = risk > 0 ? (Math.abs(tp15 - entry) / risk).toFixed(1) : '—';
  const rr3      = risk > 0 ? (Math.abs(tp3  - entry) / risk).toFixed(1) : '—';
  const isLong   = tp15 > entry;

  useEffect(() => {
    if (!containerRef.current) return;
    containerRef.current.innerHTML = '';
    const w = containerRef.current.clientWidth;

    const chart = createChart(containerRef.current, {
      width: w, height: 220,
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: '#9ca3af',
        fontFamily: "'IBM Plex Mono', monospace",
        fontSize: 11,
      },
      grid: {
        vertLines: { visible: false },
        horzLines: { color: 'rgba(255,255,255,0.04)' },
      },
      timeScale: { visible: false },
      rightPriceScale: {
        borderColor: 'rgba(255,255,255,0.12)',
        scaleMargins: { top: 0.08, bottom: 0.08 },
      },
      crosshair: { vertLine: { visible: false }, horzLine: { color: 'rgba(255,255,255,0.15)', width: 1 as const, style: 3 as const, labelBackgroundColor: '#334155' } },
      handleScroll: false,
      handleScale: false,
    });

    // ── 합성 타임 포인트 (시간축 숨김, 스케일 앵커용) ──
    const T1 = 100 as Time, T2 = 200 as Time;
    const all = [sl, tp3, ...(magneticMA ? [magneticMA] : []), ...(currentPrice ? [currentPrice] : [])];
    const lo = Math.min(...all), hi = Math.max(...all), rng = hi - lo || 1, pad = rng * 0.12;

    // ── 투명 앵커 시리즈 (Y 스케일 범위 확보) ──
    const anchor = chart.addLineSeries({ color: 'transparent', lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
    anchor.setData([{ time: T1, value: lo - pad }, { time: T2, value: hi + pad }]);

    // ── 존 배경 (entry 기준: 위=Reward 초록, 아래=Risk 빨강) ──
    // BaselineSeries: baseValue=entry → 위쪽 green fill, 아래쪽 red fill
    const zoneSeries = chart.addBaselineSeries({
      baseValue: { type: 'price', price: entry },
      topFillColor1: 'rgba(0,230,118,0.13)',
      topFillColor2: 'rgba(0,230,118,0.04)',
      bottomFillColor1: 'rgba(255,23,68,0.04)',
      bottomFillColor2: 'rgba(255,23,68,0.14)',
      topLineColor: 'transparent',
      bottomLineColor: 'transparent',
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    });
    // 평탄 선을 entry에 고정 → fill이 entry 위/아래로 정확히 나뉨
    zoneSeries.setData([{ time: T1, value: entry }, { time: T2, value: entry }]);

    // ── Price Lines ──
    const { pts: sl_pts, usd: sl_usd } = pnl(sl);
    const { pts: tp15_pts, usd: tp15_usd } = pnl(tp15);
    const { pts: tp2_pts,  usd: tp2_usd  } = pnl(tp2);
    const { pts: tp3_pts,  usd: tp3_usd  } = pnl(tp3);

    anchor.createPriceLine({ price: entry, color: '#60a5fa', lineWidth: 2, lineStyle: 0, axisLabelVisible: true, title: '▶ ENTRY' });
    anchor.createPriceLine({ price: sl,    color: '#f87171', lineWidth: 2, lineStyle: 2, axisLabelVisible: true, title: `STOP  −${fmt(sl_pts,1)}p / −$${sl_usd.toFixed(0)}` });
    anchor.createPriceLine({ price: tp15,  color: '#6ee7b7', lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: `TP 1.5R  +${fmt(tp15_pts,1)}p / +$${tp15_usd.toFixed(0)}` });
    anchor.createPriceLine({ price: tp2,   color: '#34d399', lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: `TP 2R    +${fmt(tp2_pts,1)}p / +$${tp2_usd.toFixed(0)}` });
    anchor.createPriceLine({ price: tp3,   color: '#10b981', lineWidth: 2, lineStyle: 0, axisLabelVisible: true, title: `TP 3R    +${fmt(tp3_pts,1)}p / +$${tp3_usd.toFixed(0)}` });

    if (magneticMA && magneticMA > 0)
      anchor.createPriceLine({ price: magneticMA, color: '#fb923c', lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: 'Mag MA' });

    if (currentPrice && Math.abs(currentPrice - entry) > 0.25)
      anchor.createPriceLine({ price: currentPrice, color: 'rgba(255,255,255,0.55)', lineWidth: 1, lineStyle: 3, axisLabelVisible: true, title: 'NOW' });

    chart.timeScale().fitContent();

    const handleResize = () => {
      if (containerRef.current) chart.applyOptions({ width: containerRef.current.clientWidth });
    };
    window.addEventListener('resize', handleResize);
    return () => { window.removeEventListener('resize', handleResize); chart.remove(); };
  }, [entry, sl, tp15, tp2, tp3, magneticMA, currentPrice, cfg.ptVal]);

  // ── 렌더 ──
  const MONO = "'IBM Plex Mono', monospace";
  return (
    <div className="scalp-rr-map">
      {/* R:R 헤더 바 */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '2px 4px 8px', fontFamily: MONO }}>
        <div style={{ display: 'flex', gap: 16, fontSize: '0.7rem', color: 'rgba(255,255,255,0.35)' }}>
          <span style={{ color: '#f87171' }}>SL {fmt(sl, 2)}</span>
          <span style={{ color: '#6ee7b7' }}>TP1 {fmt(tp15, 2)}</span>
          <span style={{ color: '#34d399' }}>TP2 {fmt(tp2, 2)}</span>
          <span style={{ color: '#10b981' }}>TP3 {fmt(tp3, 2)}</span>
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'baseline' }}>
          <span style={{ color: '#60a5fa', fontWeight: 700, fontSize: '0.85rem' }}>R:R 1:{rrRatio}</span>
          <span style={{ color: 'rgba(16,185,129,0.6)', fontSize: '0.7rem' }}>(max 1:{rr3})</span>
        </div>
      </div>
      {/* lightweight-charts 컨테이너 */}
      <div ref={containerRef} />
    </div>
  );
}


function BasisBar({ basis }: { basis: number }) {
  const bP = clamp((basis + 20) / 40 * 100, 2, 98);
  const bC = basis > 2 ? '#4fc3f7' : basis < -2 ? '#ffab40' : '#78909c';
  return (
    <>
      <div className="scalp-basis-track">
        <div className="scalp-basis-center" />
        <div className="scalp-basis-dot" style={{ left: `${bP}%`, background: bC, boxShadow: `0 0 10px ${bC}80` }} />
      </div>
      <div className="scalp-basis-labels">
        <span>BACKWARDATION</span><span>FAIR</span><span>CONTANGO</span>
      </div>
    </>
  );
}

// ══════════════════════════════════════════
// Scalp Decision Engine — Main Section
// ══════════════════════════════════════════

function ScalpDecisionEngine({ scalp }: { scalp: ReturnType<typeof useFuturesScalp> }) {
  const { dataMode, setDataMode, closeText, setCloseText, ohlcText, setOhlcText,
    maPeriod, setMaPeriod, closesCount, candlesCount, autoStats, inputs,
    setInput, setAsset, calc } = scalp;

  const vc = calc.verdict === 'GO' ? 'go' : calc.verdict === 'CAUTION' ? 'caution' : 'no-entry';

  return (
    <div className="scalp-section">
      {/* Section Header */}
      <div className="scalp-section-header">
        <div style={{ width: 34, height: 34, borderRadius: 8, background: 'linear-gradient(135deg, #3b82f6, #1d4ed8)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 17, fontWeight: 900, color: '#fff', fontFamily: "'IBM Plex Mono', monospace" }}>Σ</div>
        <div>
          <h2>Scalp Decision Engine</h2>
          <span className="scalp-subtitle">PROBABILITY-BASED FUTURES ANALYSIS v1.2</span>
        </div>
        <div className="scalp-asset-picker">
          {Object.entries(ASSETS).map(([k, v]) => (
            <button key={k} onClick={() => setAsset(k as 'ES' | 'MES')}
              className={`scalp-asset-btn ${inputs.asset === k ? 'active' : ''}`}>
              {k}<span className="tick-info">${v.tickVal}/t</span>
            </button>
          ))}
        </div>
      </div>

      {/* Verdict Strip */}
      <div className={`scalp-verdict-strip ${vc}`}>
        {calc.verdict === 'GO' ? '✅' : calc.verdict === 'CAUTION' ? '⚠️' : '🚫'}{' '}
        {calc.verdict} — [{calc.passN}/4] — {calc.zSignal} — {calc.isLong ? '▲ LONG' : '▼ SHORT'}
        {autoStats && <span style={{ opacity: 0.5 }}> — ATR: {autoStats.atrMethod}</span>}
      </div>

      {/* Layout: Sidebar + Main */}
      <div className="scalp-layout">
        {/* ══ LEFT: INPUTS ══ */}
        <div className="scalp-sidebar">
          {/* Price Data Input */}
          <div className="scalp-box" style={{ borderColor: dataMode !== 'manual' ? 'rgba(59,130,246,0.4)' : undefined }}>
            <div className="scalp-box-header">
              <span className="icon">📋</span>
              <span className="title">Price Data</span>
              <span className="scalp-pill" style={{
                background: dataMode !== 'manual' ? 'rgba(0,230,118,0.1)' : 'rgba(255,255,255,0.05)',
                border: `1px solid ${dataMode !== 'manual' ? 'rgba(0,230,118,0.3)' : 'rgba(255,255,255,0.1)'}`,
                color: dataMode !== 'manual' ? '#00e676' : '#888',
              }}>{dataMode === 'ohlc' ? 'OHLC' : dataMode === 'close' ? 'CLOSE' : 'MANUAL'}</span>
            </div>

            {/* 3-Mode Toggle */}
            <div className="scalp-mode-toggle">
              {([
                { key: 'ohlc' as DataMode, label: 'OHLC', desc: 'True ATR' },
                { key: 'close' as DataMode, label: 'Close', desc: 'Approx' },
                { key: 'manual' as DataMode, label: 'Manual', desc: 'Direct' },
              ]).map(m => (
                <button key={m.key} onClick={() => setDataMode(m.key)}
                  className={`scalp-mode-btn ${dataMode === m.key ? 'active' : ''}`}>
                  <span>{m.label}</span>
                  <span className="mode-desc">{m.desc}</span>
                </button>
              ))}
            </div>

            {/* OHLC Mode */}
            {dataMode === 'ohlc' && (
              <>
                <label className="scalp-input-label">OHLC DATA (O, H, L, C per line)</label>
                <textarea className="scalp-textarea" value={ohlcText} onChange={e => setOhlcText(e.target.value)}
                  placeholder="5870.00, 5878.50, 5868.25, 5872.50" rows={5} />
                <div className="scalp-data-meta">
                  <span className={`scalp-data-count ${candlesCount >= 3 ? 'valid' : 'invalid'}`}>
                    {candlesCount} candles {candlesCount < 3 && '(min 3)'}
                  </span>
                  <button className="scalp-sample-btn" onClick={() => setOhlcText(SAMPLE_OHLC)}>Sample</button>
                </div>
              </>
            )}

            {/* Close Mode */}
            {dataMode === 'close' && (
              <>
                <label className="scalp-input-label">CLOSE PRICES (comma/newline)</label>
                <textarea className="scalp-textarea" value={closeText} onChange={e => setCloseText(e.target.value)}
                  placeholder="5880.50, 5885.25, 5890.00 ..." rows={4} />
                <div className="scalp-data-meta">
                  <span className={`scalp-data-count ${closesCount >= 3 ? 'valid' : 'invalid'}`}>
                    {closesCount} prices {closesCount < 3 && '(min 3)'}
                  </span>
                  <button className="scalp-sample-btn" onClick={() => setCloseText(SAMPLE_CLOSE)}>Sample</button>
                </div>
              </>
            )}

            {/* Manual Mode */}
            {dataMode === 'manual' && (
              <>
                <ScalpNIn label="Current Price" value={inputs.currentPrice} onChange={v => setInput('currentPrice')(v)} step={0.25} unit="pts" />
                <ScalpNIn label="MA (Moving Avg)" value={inputs.ma} onChange={v => setInput('ma')(v)} step={0.25} unit="pts" />
                <ScalpNIn label="Std Dev (σ)" value={inputs.stdDev} onChange={v => setInput('stdDev')(v)} step={0.5} unit="pts" />
                <ScalpNIn label="ATR" value={inputs.atr} onChange={v => setInput('atr')(v)} step={0.25} unit="pts" />
              </>
            )}

            {/* MA Period (auto modes) */}
            {dataMode !== 'manual' && (
              <ScalpNIn label="MA Period" value={maPeriod} onChange={setMaPeriod} step={1} min={2} help="MA & StdDev calculation period" />
            )}

            {/* Auto Stats Display */}
            {dataMode !== 'manual' && autoStats && (
              <div className="scalp-auto-stats">
                <div className="scalp-auto-stats-header">
                  ● Auto —{' '}
                  {autoStats.atrMethod === 'TRUE-RANGE'
                    ? <span style={{ color: '#4fc3f7' }}>True Range ATR ✓</span>
                    : <span style={{ color: '#ffab40' }}>Close-Proxy ATR</span>}
                </div>
                <div className="scalp-auto-stats-grid">
                  {[
                    { l: 'Price', v: fmt(autoStats.currentPrice, 2) },
                    { l: `MA(${autoStats.maPeriod})`, v: fmt(autoStats.ma, 2) },
                    { l: 'σ (StdDev)', v: fmt(autoStats.stdDev, 2) },
                    { l: 'ATR(14)', v: fmt(autoStats.atr, 2) },
                  ].map((item, i) => (
                    <div key={i}>
                      <div className="scalp-auto-stat-label">{item.l}</div>
                      <div className="scalp-auto-stat-value">{item.v}</div>
                    </div>
                  ))}
                </div>
                {autoStats.atrMethod === 'CLOSE-PROXY' && (
                  <div className="scalp-auto-warn">
                    ⚠ Close-to-close ATR approximation. Use OHLC mode for True Range ATR.
                  </div>
                )}
              </div>
            )}

            <ScalpNIn label="ATR Mult (Stop)" value={inputs.atrMult} onChange={v => setInput('atrMult')(v)} step={0.1} min={0.1} help="Scalp: 0.5-1.0 / Swing: 1.5-2.0" />
          </div>

          {/* Backtest Stats */}
          <div className="scalp-box">
            <div className="scalp-box-header">
              <span className="icon">🎯</span>
              <span className="title">Backtest Stats</span>
              <span className="scalp-pill" style={{ background: 'rgba(59,130,246,0.1)', border: '1px solid rgba(59,130,246,0.3)', color: '#3b82f6' }}>EV INPUT</span>
            </div>
            <ScalpNIn label="Win Rate" value={inputs.winRate} onChange={v => setInput('winRate')(v)} step={1} unit="%" />
            <ScalpNIn label="Avg Win" value={inputs.avgWin} onChange={v => setInput('avgWin')(v)} step={0.5} unit="ticks" />
            <ScalpNIn label="Avg Loss" value={inputs.avgLoss} onChange={v => setInput('avgLoss')(v)} step={0.5} unit="ticks" />
            <ScalpNIn label="Slippage" value={inputs.slippage} onChange={v => setInput('slippage')(v)} step={0.25} unit="ticks" help="Scalp 0.25-0.5t" />
            <ScalpNIn label="Commission (1-way)" value={inputs.commission} onChange={v => setInput('commission')(v)} step={0.05} unit="$" />
          </div>

          {/* Account */}
          <div className="scalp-box">
            <div className="scalp-box-header">
              <span className="icon">💰</span>
              <span className="title">Account</span>
            </div>
            <ScalpNIn label="Balance" value={inputs.accountBalance} onChange={v => setInput('accountBalance')(v)} step={100} unit="$" />
            <ScalpNIn label="Risk Per Trade" value={inputs.riskPct} onChange={v => setInput('riskPct')(v)} step={0.5} min={0.1} unit="%" />
          </div>

          {/* Basis */}
          <div className="scalp-box">
            <div className="scalp-box-header">
              <span className="icon">📉</span>
              <span className="title">Basis Spread</span>
            </div>
            <ScalpNIn label="Spot (SPX)" value={inputs.spotPrice} onChange={v => setInput('spotPrice')(v)} step={0.25} unit="pts" />
            <ScalpNIn label="Futures (ES)" value={inputs.futuresPrice} onChange={v => setInput('futuresPrice')(v)} step={0.25} unit="pts" />
          </div>
        </div>

        {/* ══ RIGHT: OUTPUTS ══ */}
        <div className="scalp-main">
          {/* Decision Matrix */}
          <div className="scalp-box" style={{ borderColor: calc.verdict === 'GO' ? 'rgba(0,230,118,0.3)' : calc.verdict === 'CAUTION' ? 'rgba(253,216,53,0.3)' : 'rgba(255,23,68,0.3)' }}>
            <div className="scalp-box-header">
              <span className="icon">🎯</span>
              <span className="title">Decision Matrix</span>
              <span className="scalp-pill" style={{
                background: calc.verdict === 'GO' ? 'rgba(0,230,118,0.1)' : calc.verdict === 'CAUTION' ? 'rgba(253,216,53,0.1)' : 'rgba(255,23,68,0.1)',
                border: `1px solid ${calc.verdict === 'GO' ? 'rgba(0,230,118,0.3)' : calc.verdict === 'CAUTION' ? 'rgba(253,216,53,0.3)' : 'rgba(255,23,68,0.3)'}`,
                color: calc.verdict === 'GO' ? '#00e676' : calc.verdict === 'CAUTION' ? '#fdd835' : '#ff1744',
              }}>ENTRY CHECKLIST</span>
            </div>
            <div>
              {calc.checks.map((c, i) => (
                <div key={i} className={`scalp-check-item ${c.pass ? 'pass' : 'fail'}`}>
                  <span className={`scalp-check-icon ${c.pass ? 'pass' : 'fail'}`}>{c.pass ? '✓' : '✗'}</span>
                  <div style={{ flex: 1 }}>
                    <div className="scalp-check-label">{c.label}</div>
                    <div className="scalp-check-val">{c.val}</div>
                  </div>
                </div>
              ))}
            </div>
            <div className={`scalp-verdict-box ${vc}`} style={{
              background: calc.verdict === 'GO' ? 'rgba(0,230,118,0.08)' : calc.verdict === 'CAUTION' ? 'rgba(253,216,53,0.08)' : 'rgba(255,23,68,0.08)',
              border: `1px solid ${calc.verdict === 'GO' ? 'rgba(0,230,118,0.3)' : calc.verdict === 'CAUTION' ? 'rgba(253,216,53,0.3)' : 'rgba(255,23,68,0.3)'}`,
              color: calc.verdict === 'GO' ? '#00e676' : calc.verdict === 'CAUTION' ? '#fdd835' : '#ff1744',
            }}>
              [{calc.passN}/4] {calc.verdict === 'GO' ? 'ALL CLEAR — Entry OK' : calc.verdict === 'CAUTION' ? 'CAUTION — Conditional' : 'NO ENTRY — Wait'}
            </div>
          </div>

          {/* Z-Score Analysis */}
          <div className="scalp-box">
            <div className="scalp-box-header">
              <span className="icon">📐</span>
              <span className="title">Z-Score Analysis</span>
              <span className="scalp-pill" style={{ background: 'rgba(59,130,246,0.1)', border: '1px solid rgba(59,130,246,0.3)', color: '#3b82f6' }}>Statistical Position</span>
            </div>
            <div className="scalp-met-row">
              <div className="scalp-met big">
                <div className="scalp-met-label">Z-Score</div>
                <div className="scalp-met-value big" style={{ color: calc.zColor }}>{fmt(calc.z)}</div>
              </div>
              <div className="scalp-met">
                <div className="scalp-met-label">Signal</div>
                <div className="scalp-met-value" style={{ color: calc.zColor }}>{calc.zSignal}</div>
              </div>
              <div className="scalp-met">
                <div className="scalp-met-label">P-Value</div>
                <div className="scalp-met-value">{fmtPct(calc.pVal)}</div>
                <div className="scalp-met-sub">two-tailed</div>
              </div>
              <div className="scalp-met">
                <div className="scalp-met-label">Deviation</div>
                <div className="scalp-met-value">{fmt(inputs.currentPrice - inputs.ma, 1)}p</div>
                <div className="scalp-met-sub">vs MA</div>
              </div>
            </div>
            <ZBar z={calc.z} />
            <div className="scalp-explain">
              Z = ({fmt(inputs.currentPrice, 2)} − {fmt(inputs.ma, 2)}) / {fmt(inputs.stdDev, 2)} ={' '}
              <span style={{ color: calc.zColor, fontWeight: 700 }}>{fmt(calc.z)}</span>
              {' '}→ {fmt(Math.abs(calc.z))}σ from MA {calc.z < 0 ? 'below' : 'above'} | P = {fmtPct(calc.pVal)}
            </div>
          </div>

          {/* EV Engine */}
          <div className="scalp-box">
            <div className="scalp-box-header">
              <span className="icon">⚡</span>
              <span className="title">Scalp EV Engine</span>
              <span className="scalp-pill" style={{
                background: calc.netEV >= 0 ? 'rgba(0,230,118,0.1)' : 'rgba(255,23,68,0.1)',
                border: `1px solid ${calc.netEV >= 0 ? 'rgba(0,230,118,0.3)' : 'rgba(255,23,68,0.3)'}`,
                color: calc.netEV >= 0 ? '#00e676' : '#ff1744',
              }}>Expected Value</span>
            </div>
            <div className="scalp-met-row">
              <div className="scalp-met big">
                <div className="scalp-met-label">Net EV/Trade</div>
                <div className="scalp-met-value big" style={{ color: calc.netEV >= 0 ? '#00e676' : '#ff1744' }}>
                  {calc.netEV >= 0 ? '+' : ''}{fmt(calc.netEV)}t
                </div>
                <div className="scalp-met-sub">{calc.netEV >= 0 ? '+' : '−'} {fmtUSD(Math.abs(calc.netEVusd))}</div>
              </div>
              <div className="scalp-met">
                <div className="scalp-met-label">Gross EV</div>
                <div className="scalp-met-value">{fmt(calc.grossEV)}t</div>
                <div className="scalp-met-sub">before cost</div>
              </div>
              <div className="scalp-met">
                <div className="scalp-met-label">Friction</div>
                <div className="scalp-met-value" style={{ color: '#ffab40' }}>{fmt(calc.friction)}t</div>
                <div className="scalp-met-sub">slip+comm</div>
              </div>
              <div className="scalp-met">
                <div className="scalp-met-label">R:R</div>
                <div className="scalp-met-value">{fmt(calc.b, 1)}:1</div>
              </div>
            </div>
            <EVBar gross={calc.grossEV} net={calc.netEV} />
            <div className="scalp-explain">
              EV = {fmtPct(calc.p)}×{inputs.avgWin} − {fmtPct(calc.q)}×{inputs.avgLoss} − {fmt(calc.friction)}t ={' '}
              <span style={{ color: calc.netEV >= 0 ? '#00e676' : '#ff1744', fontWeight: 700 }}>{fmt(calc.netEV)}t</span>
              {calc.netEV > 0
                ? <> | 100 trades expected: <span style={{ color: '#00e676' }}>+{fmtUSD(Math.abs(calc.netEVusd) * 100)}</span></>
                : <> | ⚠ Repeated trading = cumulative loss</>}
            </div>
          </div>

          {/* Kelly + Position Sizer */}
          <div className="scalp-side-panels">
            <div className="scalp-box">
              <div className="scalp-box-header">
                <span className="icon">🎰</span>
                <span className="title">Kelly Criterion</span>
                <span className="scalp-pill" style={{
                  background: calc.kelly > 0 ? 'rgba(0,230,118,0.1)' : 'rgba(255,23,68,0.1)',
                  border: `1px solid ${calc.kelly > 0 ? 'rgba(0,230,118,0.3)' : 'rgba(255,23,68,0.3)'}`,
                  color: calc.kelly > 0 ? '#00e676' : '#ff1744',
                }}>Conviction</span>
              </div>
              <div className="scalp-met-row">
                <div className="scalp-met">
                  <div className="scalp-met-label">Full Kelly</div>
                  <div className="scalp-met-value">{fmtPct(calc.kelly)}</div>
                </div>
                <div className="scalp-met big">
                  <div className="scalp-met-label">Half Kelly</div>
                  <div className="scalp-met-value big" style={{ color: '#3b82f6' }}>{fmtPct(calc.halfKelly)}</div>
                  <div className="scalp-met-sub">recommended bet size</div>
                </div>
              </div>
              <KGauge hk={calc.halfKelly} conv={calc.conviction} />
              <div className="scalp-explain">
                f* = ({fmt(calc.b, 1)}×{fmtPct(calc.p)} − {fmtPct(calc.q)}) / {fmt(calc.b, 1)} = {fmtPct(calc.kelly)}
              </div>
            </div>

            <div className="scalp-box">
              <div className="scalp-box-header">
                <span className="icon">📏</span>
                <span className="title">Position Sizer</span>
              </div>
              <div className="scalp-met-row">
                <div className="scalp-met">
                  <div className="scalp-met-label">Risk Budget</div>
                  <div className="scalp-met-value">{fmtUSD(calc.riskBudget)}</div>
                  <div className="scalp-met-sub">{inputs.riskPct}% of balance</div>
                </div>
                <div className="scalp-met">
                  <div className="scalp-met-label">Risk/Contract</div>
                  <div className="scalp-met-value">{fmtUSD(calc.riskPerContract)}</div>
                  <div className="scalp-met-sub">{fmt(calc.atrStop)}p × ${calc.cfg.ptVal}</div>
                </div>
              </div>
              <div className="scalp-contracts-display">
                <div className="scalp-contracts-label">Recommended Contracts</div>
                <div className="scalp-contracts-number">{calc.recContracts}</div>
                <div className="scalp-contracts-sub">max {calc.maxContracts} / scalp cap 2</div>
              </div>
            </div>
          </div>

          {/* ATR Stop & R:R Map */}
          <div className="scalp-box">
            <div className="scalp-box-header">
              <span className="icon">🛡️</span>
              <span className="title">ATR Stop & R:R Map</span>
              <span className="scalp-pill" style={{ background: 'rgba(59,130,246,0.1)', border: '1px solid rgba(59,130,246,0.3)', color: '#3b82f6' }}>ATR×{inputs.atrMult}</span>
            </div>
            <div className="scalp-met-row" style={{ marginBottom: 6 }}>
              <div className="scalp-met">
                <div className="scalp-met-label">ATR Stop</div>
                <div className="scalp-met-value" style={{ color: '#ff1744' }}>{fmt(calc.atrStop)}p</div>
                <div className="scalp-met-sub">{fmtUSD(calc.riskPerContract)}/ct</div>
              </div>
              <div className="scalp-met">
                <div className="scalp-met-label">Stop</div>
                <div className="scalp-met-value" style={{ color: '#ff1744' }}>{fmt(calc.sl, 2)}</div>
              </div>
              <div className="scalp-met">
                <div className="scalp-met-label">TP 1.5R</div>
                <div className="scalp-met-value" style={{ color: '#69f0ae' }}>{fmt(calc.tp15, 2)}</div>
              </div>
              <div className="scalp-met">
                <div className="scalp-met-label">TP 2R</div>
                <div className="scalp-met-value" style={{ color: '#00e676' }}>{fmt(calc.tp2, 2)}</div>
              </div>
              <div className="scalp-met">
                <div className="scalp-met-label">TP 3R</div>
                <div className="scalp-met-value" style={{ color: '#00e676' }}>{fmt(calc.tp3, 2)}</div>
              </div>
            </div>
            <RRVis entry={inputs.currentPrice} sl={calc.sl} tp15={calc.tp15} tp2={calc.tp2} tp3={calc.tp3} cfg={calc.cfg} currentPrice={inputs.currentPrice} />
            <div className="scalp-pnl-row">
              <div className="scalp-pnl-box profit">
                <div className="scalp-pnl-label">TP 1.5R P&L ({calc.recContracts}ct)</div>
                <div className="scalp-pnl-value" style={{ color: '#00e676' }}>+{fmtUSD(calc.pnlTP1)}</div>
              </div>
              <div className="scalp-pnl-box loss">
                <div className="scalp-pnl-label">SL Hit P&L ({calc.recContracts}ct)</div>
                <div className="scalp-pnl-value" style={{ color: '#ff1744' }}>-{fmtUSD(calc.pnlSL)}</div>
              </div>
            </div>
          </div>

          {/* Basis Spread */}
          <div className="scalp-box">
            <div className="scalp-box-header">
              <span className="icon">📉</span>
              <span className="title">Basis Spread</span>
              <span className="scalp-pill" style={{
                background: calc.basis > 2 ? 'rgba(79,195,247,0.1)' : calc.basis < -2 ? 'rgba(255,171,64,0.1)' : 'rgba(255,255,255,0.05)',
                border: `1px solid ${calc.basis > 2 ? 'rgba(79,195,247,0.3)' : calc.basis < -2 ? 'rgba(255,171,64,0.3)' : 'rgba(255,255,255,0.1)'}`,
                color: calc.basis > 2 ? '#4fc3f7' : calc.basis < -2 ? '#ffab40' : '#78909c',
              }}>{calc.basisState}</span>
            </div>
            <div className="scalp-met-row">
              <div className="scalp-met">
                <div className="scalp-met-label">SPX (Spot)</div>
                <div className="scalp-met-value">{fmt(inputs.spotPrice, 2)}</div>
              </div>
              <div className="scalp-met">
                <div className="scalp-met-label">ES (Futures)</div>
                <div className="scalp-met-value">{fmt(inputs.futuresPrice, 2)}</div>
              </div>
              <div className="scalp-met big">
                <div className="scalp-met-label">Basis</div>
                <div className="scalp-met-value big" style={{ color: calc.basis > 2 ? '#4fc3f7' : calc.basis < -2 ? '#ffab40' : '#78909c' }}>
                  {calc.basis >= 0 ? '+' : ''}{fmt(calc.basis, 2)}p
                </div>
              </div>
              <div className="scalp-met">
                <div className="scalp-met-label">Basis %</div>
                <div className="scalp-met-value">{fmt(calc.basisPct, 3)}%</div>
              </div>
            </div>
            <BasisBar basis={calc.basis} />
            <div className="scalp-explain">
              {calc.basisState === 'CONTANGO'
                ? 'Futures > Spot: Contango (normal). Cost-of-carry reflected. Downward pressure at expiry.'
                : calc.basisState === 'BACKWARDATION'
                  ? 'Futures < Spot: Backwardation. Market stress signal. Program buying possible.'
                  : 'Spot ≈ Futures: Near Fair Value. Minimal arbitrage incentive.'}
            </div>
          </div>

          {/* Formula Reference */}
          <div className="scalp-box">
            <div className="scalp-box-header">
              <span className="icon">📖</span>
              <span className="title">Formula Reference</span>
              <span className="scalp-pill" style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', color: '#888' }}>QUICK REF</span>
            </div>
            <div className="scalp-formula-grid">
              {[
                { t: 'Z-Score', f: 'Z = (Price − MA) / σ', d: '±2σ → 95.4% confidence interval' },
                { t: 'Expected Value', f: 'EV = P(W)·W − P(L)·L − Cost', d: 'Enter only when positive' },
                { t: 'Kelly Criterion', f: 'f* = (b·p − q) / b', d: 'Half-Kelly recommended' },
                { t: 'True Range', f: 'TR = max(H−L, |H−C′|, |L−C′|)', d: 'ATR = avg(TR, 14)' },
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
  );
}

// ══════════════════════════════════════════
// Main Page
// ══════════════════════════════════════════

export function FuturesTrading() {
  const [ticker, setTicker] = useState('ES=F');
  const [tickers, setTickers] = useState<FuturesTickerInfo[]>([]);
  const [analysis, setAnalysis] = useState<FuturesAnalysis | null>(null);
  const [loading, setLoading] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(false);

  // Backtest state — default: 2년 전 ~ 오늘
  const [btOpen, setBtOpen] = useState(false);
  const [btStartDate, setBtStartDate] = useState(() => {
    const d = new Date();
    d.setFullYear(d.getFullYear() - 2);
    return `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}${String(d.getDate()).padStart(2, '0')}`;
  });
  const [btEndDate, setBtEndDate] = useState(() => {
    const d = new Date();
    return `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}${String(d.getDate()).padStart(2, '0')}`;
  });
  const [btEquity, setBtEquity] = useState(() => 100000);
  const [btMicro, setBtMicro] = useState(false);
  const [btRunning, setBtRunning] = useState(false);
  const [btResult, setBtResult] = useState<FuturesBacktestResult | null>(null);
  const [btError, setBtError] = useState<string | null>(null);
  const [btElapsed, setBtElapsed] = useState(0);

  // 롤오버 + 상품 규격
  const [nextRoll, setNextRoll] = useState<{ contract: string; roll_date: string; days_remaining: number } | null>(null);
  const [contractSpecs, setContractSpecs] = useState<ContractSpecs | null>(null);
  const [specsOpen, setSpecsOpen] = useState(false);
  const btTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Load tickers on mount
  useEffect(() => {
    fetchFuturesTickers().then(t => setTickers(t));
    fetchRollSchedule().then(r => setNextRoll(r.next_roll));
    fetchContractSpecs().then(s => setContractSpecs(s));
  }, []);

  // Load analysis — 종목 전환 시 이전 데이터 즉시 클리어
  const loadAnalysis = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchFuturesAnalysis(ticker);
      if (data) setAnalysis(data);
    } finally {
      setLoading(false);
    }
  }, [ticker]);

  useEffect(() => {
    setAnalysis(null);  // 이전 종목 데이터 클리어
    loadAnalysis();
  }, [loadAnalysis]);

  // Auto-refresh
  useEffect(() => {
    if (!autoRefresh) return;
    const id = setInterval(loadAnalysis, 60000);
    return () => clearInterval(id);
  }, [autoRefresh, loadAnalysis]);

  // Preset date helpers
  const setPreset = (years: number) => {
    const now = new Date();
    const end = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}`;
    const start = new Date(now);
    start.setFullYear(start.getFullYear() - years);
    const startStr = `${start.getFullYear()}${String(start.getMonth() + 1).padStart(2, '0')}${String(start.getDate()).padStart(2, '0')}`;
    setBtStartDate(startStr);
    setBtEndDate(end);
  };

  // Run backtest
  const runBacktest = async () => {
    setBtRunning(true);
    setBtResult(null);
    setBtError(null);
    setBtElapsed(0);
    btTimerRef.current = setInterval(() => setBtElapsed(s => s + 1), 1000);
    try {
      const result = await triggerFuturesBacktest(ticker, btStartDate, btEndDate, btEquity, btMicro);
      if (result) {
        setBtResult(result);
      } else {
        setBtError('Backtest returned no result');
      }
    } catch (e: unknown) {
      setBtError(e instanceof Error ? e.message : 'Unknown error');
    } finally {
      setBtRunning(false);
      if (btTimerRef.current) { clearInterval(btTimerRef.current); btTimerRef.current = null; }
    }
  };

  // Scalp Decision Engine
  const scalp = useFuturesScalp(analysis);

  const dir = analysis?.direction || 'NEUTRAL';
  const dirClass = dir === 'LONG' ? 'long' : dir === 'SHORT' ? 'short' : 'neutral';

  return (
    <div className="futures-trading container">
      <div className="page-header">
        <h1>Futures Trading</h1>
        <p>4-Layer Scoring Engine — Z-Score + Trend + Momentum + Volume</p>
      </div>

      {/* ── Top Bar ── */}
      <div className="futures-top-bar">
        <select
          className="futures-ticker-select"
          value={ticker}
          onChange={e => setTicker(e.target.value)}
        >
          {tickers.map(t => (
            <option key={t.ticker} value={t.ticker}>
              {t.ticker} — {t.name} (×{t.multiplier})
            </option>
          ))}
          {tickers.length === 0 && <option value="ES=F">ES=F — E-mini S&P 500</option>}
        </select>

        <span className={`futures-direction-badge ${dirClass}`}>
          {dir === 'LONG' ? '▲' : dir === 'SHORT' ? '▼' : '●'} {dir}
        </span>

        {analysis && (
          <span style={{ fontSize: '0.85rem', color: '#888' }}>
            Last: {analysis.last_updated}
          </span>
        )}

        <div className="futures-auto-refresh">
          <label>
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={e => setAutoRefresh(e.target.checked)}
            />
            Auto (60s)
          </label>
          <button className="futures-refresh-btn" onClick={loadAnalysis} disabled={loading}>
            {loading ? '...' : '↻'}
          </button>
        </div>
      </div>

      {/* ── Rollover Warning Banner ── */}
      {nextRoll && nextRoll.days_remaining <= 7 && (
        <div className="futures-roll-banner">
          Roll Approaching: {nextRoll.contract} on {nextRoll.roll_date} (D-{nextRoll.days_remaining})
        </div>
      )}

      {/* ── Contract Specs Panel ── */}
      <div className="futures-panel" style={{ marginBottom: 12 }}>
        <div
          className="backtest-toggle"
          onClick={() => setSpecsOpen(!specsOpen)}
          style={{ cursor: 'pointer', userSelect: 'none', display: 'flex', alignItems: 'center', gap: 8 }}
        >
          <span style={{ transform: specsOpen ? 'rotate(90deg)' : 'none', transition: 'transform 0.2s', display: 'inline-block' }}>▶</span>
          <strong>Contract Specifications</strong>
          {contractSpecs?.current_session && (
            <span style={{
              marginLeft: 'auto',
              fontSize: '0.75rem',
              padding: '2px 8px',
              borderRadius: 4,
              background: contractSpecs.current_session.status === 'RTH' ? 'rgba(46,204,113,0.2)' :
                          contractSpecs.current_session.status === 'HALT' ? 'rgba(231,76,60,0.2)' : 'rgba(241,196,15,0.2)',
              color: contractSpecs.current_session.status === 'RTH' ? '#2ecc71' :
                     contractSpecs.current_session.status === 'HALT' ? '#e74c3c' : '#f1c40f',
            }}>
              {contractSpecs.current_session.name} {contractSpecs.current_session.is_dst ? '(DST)' : ''}
            </span>
          )}
        </div>
        {specsOpen && contractSpecs && (
          <div style={{ marginTop: 12 }}>
            <table className="futures-trade-table" style={{ fontSize: '0.78rem' }}>
              <thead>
                <tr>
                  <th>Spec</th><th>E-mini (ES)</th><th>Micro (MES)</th>
                </tr>
              </thead>
              <tbody>
                <tr><td>Multiplier</td><td>${contractSpecs.es.multiplier}/pt</td><td>${contractSpecs.mes.multiplier}/pt</td></tr>
                <tr><td>Tick Size</td><td>{contractSpecs.es.tick_size} pts</td><td>{contractSpecs.mes.tick_size} pts</td></tr>
                <tr><td>Tick Value</td><td>${contractSpecs.es.tick_value}</td><td>${contractSpecs.mes.tick_value}</td></tr>
                <tr><td>Notional</td><td>${contractSpecs.es.notional.toLocaleString()}</td><td>${contractSpecs.mes.notional.toLocaleString()}</td></tr>
                <tr><td>Initial Margin</td><td>${contractSpecs.es.initial_margin.toLocaleString()}</td><td>${contractSpecs.mes.initial_margin.toLocaleString()}</td></tr>
                <tr><td>Maint. Margin</td><td>${contractSpecs.es.maintenance_margin.toLocaleString()}</td><td>${contractSpecs.mes.maintenance_margin.toLocaleString()}</td></tr>
                <tr><td>RT Cost</td><td>${contractSpecs.cost_breakdown.es_round_trip.toFixed(2)}</td><td>${contractSpecs.cost_breakdown.mes_round_trip.toFixed(2)}</td></tr>
              </tbody>
            </table>
            <div style={{ fontSize: '0.72rem', color: '#888', marginTop: 6 }}>
              Cost as % of notional: ~{(contractSpecs.cost_breakdown.cost_pct_of_notional * 100).toFixed(4)}% round-trip
            </div>
          </div>
        )}
      </div>

      {/* ── Main Grid: Score + Signal ── */}
      {analysis ? (
        <div className="futures-main-grid">
          {/* Left: 4-Layer Score */}
          <div className="futures-panel">
            <h3>4-Layer Score</h3>
            <div className="layer-scores">
              <LayerScoreBar
                label="Z-Score"
                score={analysis.layers.zscore.score}
                maxScore={analysis.layers.zscore.max_score}
                layerClass="zscore"
                signals={analysis.layers.zscore.signals}
              />
              <LayerScoreBar
                label="Trend"
                score={analysis.layers.trend.score}
                maxScore={analysis.layers.trend.max_score}
                layerClass="trend"
                signals={analysis.layers.trend.signals}
              />
              <LayerScoreBar
                label="Momentum"
                score={analysis.layers.momentum.score}
                maxScore={analysis.layers.momentum.max_score}
                layerClass="momentum"
                signals={analysis.layers.momentum.signals}
              />
              <LayerScoreBar
                label="Volume"
                score={analysis.layers.volume.score}
                maxScore={analysis.layers.volume.max_score}
                layerClass="volume"
                signals={analysis.layers.volume.signals}
              />
            </div>

            <div className="total-score-row">
              <div>
                <span
                  className={`total-score-value ${analysis.total_score >= analysis.entry_threshold ? 'pass' : 'fail'}`}
                >
                  {analysis.total_score.toFixed(1)} / 100
                </span>
              </div>
              <span className="total-score-threshold">
                Threshold: {analysis.entry_threshold} {analysis.signal_active ? '✓ ACTIVE' : '✗ INACTIVE'}
              </span>
            </div>
          </div>

          {/* Right: Signal Card */}
          <div className="futures-panel">
            <h3>Signal Details</h3>
            <div className={`signal-card ${dirClass}`}>
              <div className="signal-card-row">
                <span className="label">Direction</span>
                <span className={`value ${dirClass === 'long' ? 'profit' : dirClass === 'short' ? 'loss' : ''}`}>
                  {dir}
                </span>
              </div>
              <div className="signal-card-row">
                <span className="label">Entry Price</span>
                <span className="value">{formatPrice(analysis.entry_price, ticker)}</span>
              </div>
              <div className="signal-card-row">
                <span className="label">Stop Loss</span>
                {analysis.direction !== 'NEUTRAL' && analysis.indicators.atr > 0 ? (
                  <span className="value loss">
                    {formatPrice(analysis.stop_loss, ticker)}
                    {' '}({((analysis.stop_loss - analysis.entry_price) / analysis.entry_price * 100).toFixed(1)}%)
                  </span>
                ) : (
                  <span className="value muted">—</span>
                )}
              </div>
              <div className="signal-card-row">
                <span className="label">Take Profit</span>
                {analysis.direction !== 'NEUTRAL' && analysis.indicators.atr > 0 ? (
                  <span className="value profit">
                    {formatPrice(analysis.take_profit, ticker)}
                    {' '}(+{((analysis.take_profit - analysis.entry_price) / analysis.entry_price * 100).toFixed(1)}%)
                  </span>
                ) : (
                  <span className="value muted">—</span>
                )}
              </div>
              <div className="signal-card-row">
                <span className="label">R:R Ratio</span>
                <span className="value">
                  {analysis.direction !== 'NEUTRAL' && analysis.indicators.atr > 0
                    ? `${analysis.risk_reward_ratio.toFixed(2)} : 1`
                    : '—'}
                </span>
              </div>
              <div className="signal-card-row">
                <span className="label">Contracts</span>
                <span className="value">{analysis.position_size_contracts}</span>
              </div>

              <div style={{ marginTop: '1rem', paddingTop: '0.75rem', borderTop: '1px solid var(--border-color, #333)' }}>
                <h3 style={{ marginBottom: '0.5rem' }}>Indicators</h3>
                <div className="signal-card-row">
                  <span className="label">RSI</span>
                  <span className="value">{analysis.indicators.rsi.toFixed(1)}</span>
                </div>
                <div className="signal-card-row">
                  <span className="label">ADX</span>
                  <span className="value">{analysis.indicators.adx.toFixed(1)}</span>
                </div>
                <div className="signal-card-row">
                  <span className="label">MACD Hist</span>
                  <span className="value">{analysis.indicators.macd_hist.toFixed(3)}</span>
                </div>
                <div className="signal-card-row">
                  <span className="label">ATR</span>
                  <span className="value">{analysis.indicators.atr.toFixed(2)}</span>
                </div>
                <div className="signal-card-row">
                  <span className="label">BB Squeeze</span>
                  <span className="value">{analysis.indicators.bb_squeeze_ratio.toFixed(3)}</span>
                </div>
                <div className="signal-card-row">
                  <span className="label">Vol Ratio</span>
                  <span className="value">{analysis.indicators.volume_ratio.toFixed(2)}x</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="futures-loading">
          {loading ? (
            <>
              <ScoreCardsSkeleton />
              <ChartSkeleton height={300} />
            </>
          ) : 'No analysis data available'}
        </div>
      )}

      {/* ── Z-Score Gauge ── */}
      {analysis && <ZScoreGauge zscore={analysis.indicators.zscore} />}

      {/* ── Price Chart ── */}
      <div className="futures-chart-section">
        <FuturesPriceChart ticker={ticker} />
      </div>

      {/* ══════════════════════════════════════════════════
          Scalp Decision Engine (from FuturesScalpAnalyzer v1.2)
          ══════════════════════════════════════════════════ */}
      <ScalpDecisionEngine scalp={scalp} />

      {/* ── Backtest Section ── */}
      <div className="futures-backtest-section">
        <button className="backtest-toggle" onClick={() => setBtOpen(!btOpen)}>
          {btOpen ? '▾' : '▸'} Backtest
        </button>

        {btOpen && (
          <div className="backtest-content">
            {/* Preset buttons */}
            <div className="bt-presets">
              {[1, 2, 3, 5].map(y => (
                <button key={y} className="bt-preset-btn" onClick={() => setPreset(y)}>{y}Y</button>
              ))}
            </div>

            <div className="backtest-form">
              <div className="backtest-field">
                <label>Start Date</label>
                <input value={btStartDate} onChange={e => setBtStartDate(e.target.value)} placeholder="YYYYMMDD" />
              </div>
              <div className="backtest-field">
                <label>End Date</label>
                <input value={btEndDate} onChange={e => setBtEndDate(e.target.value)} placeholder="YYYYMMDD" />
              </div>
              <div className="backtest-field">
                <label>Equity ({getTickerCurrency(ticker).symbol})</label>
                <input type="number" value={btEquity} onChange={e => setBtEquity(Number(e.target.value))} />
              </div>
              <div className="backtest-field">
                <label style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                  <input type="checkbox" checked={btMicro} onChange={e => setBtMicro(e.target.checked)} />
                  Micro
                </label>
              </div>
              <button className="backtest-run-btn" onClick={runBacktest} disabled={btRunning}>
                {btRunning ? `Running…${btElapsed > 0 ? ` (${btElapsed}s)` : ''}` : 'Run Backtest'}
              </button>
            </div>

            {btError && (
              <div className="bt-error">{btError}</div>
            )}

            {btResult && (
              <>
                {/* Actual date range from equity curve */}
                {btResult.equity_curve.length > 0 && (
                  <div style={{ fontSize: '0.8rem', color: '#888', marginBottom: 8 }}>
                    Data Range: {btResult.equity_curve[0].date} ~ {btResult.equity_curve[btResult.equity_curve.length - 1].date}
                    {' '}({btResult.equity_curve.length} trading days)
                  </div>
                )}
                {/* Metrics */}
                <div className="backtest-metrics-grid">
                  <MetricCard label="Return" value={`${btResult.metrics.total_return_pct.toFixed(1)}%`} colorize />
                  <MetricCard label="CAGR" value={`${btResult.metrics.cagr?.toFixed(1) ?? 0}%`} colorize />
                  <MetricCard label="Sharpe" value={btResult.metrics.sharpe_ratio.toFixed(2)} />
                  <MetricCard label="Sortino" value={btResult.metrics.sortino_ratio?.toFixed(2) ?? '0'} />
                  <MetricCard label="Calmar" value={btResult.metrics.calmar_ratio?.toFixed(2) ?? '0'} />
                  <MetricCard label="MDD" value={`${btResult.metrics.max_drawdown_pct.toFixed(1)}%`} colorize />
                  <MetricCard label="MDD Duration" value={`${btResult.metrics.mdd_duration_days ?? 0}d`} />
                  <MetricCard label="Trades" value={String(btResult.metrics.total_trades)} />
                  <MetricCard label="Win Rate" value={`${btResult.metrics.win_rate.toFixed(1)}%`} />
                  <MetricCard label="Profit Factor" value={btResult.metrics.profit_factor.toFixed(2)} />
                  <MetricCard label="Avg R:R" value={btResult.metrics.avg_rr.toFixed(2)} />
                  <MetricCard label="Long / Short" value={`${btResult.metrics.long_trades} / ${btResult.metrics.short_trades}`} />
                  <MetricCard label="Total P&L" value={formatPnL(btResult.metrics.total_pnl, ticker)} colorize />
                  <MetricCard label="Costs" value={formatPnL(btResult.metrics.total_costs ?? 0, ticker)} />
                  <MetricCard label="Best Trade" value={`${btResult.metrics.best_trade_pct?.toFixed(1) ?? 0}%`} colorize />
                  <MetricCard label="Worst Trade" value={`${btResult.metrics.worst_trade_pct?.toFixed(1) ?? 0}%`} colorize />
                  <MetricCard label="Max W Streak" value={String(btResult.metrics.max_consecutive_wins ?? 0)} />
                  <MetricCard label="Max L Streak" value={String(btResult.metrics.max_consecutive_losses ?? 0)} />
                  <MetricCard label="Avg Hold" value={`${btResult.metrics.avg_holding_days}d`} />
                  {/* 증거금/CB/롤오버 메트릭 */}
                  <MetricCard label="Margin Calls" value={String(btResult.metrics.margin_call_count ?? 0)} />
                  <MetricCard label="Max Leverage" value={`${(btResult.metrics.max_effective_leverage ?? 0).toFixed(1)}x`} />
                  <MetricCard label="Margin Util" value={`${(btResult.metrics.avg_margin_utilization ?? 0).toFixed(1)}%`} />
                  <MetricCard label="CB Events" value={String(btResult.metrics.cb_event_count ?? 0)} />
                  <MetricCard label="Rollovers" value={String(btResult.metrics.roll_count ?? 0)} />
                  <MetricCard label="Roll Costs" value={formatPnL(btResult.metrics.total_roll_costs ?? 0, ticker)} />
                </div>

                {/* Equity Curve (dual: equity + drawdown) */}
                {btResult.equity_curve.length > 0 && (
                  <EquityCurve
                    data={btResult.equity_curve.map(e => ({
                      date: e.date.split(' ')[0].split('T')[0],
                      equity: e.total_value,
                      drawdown_pct: e.drawdown_pct,
                    }))}
                    height={280}
                  />
                )}

                {/* Exit Reasons */}
                {btResult.metrics.exit_reasons && Object.keys(btResult.metrics.exit_reasons).length > 0 && (
                  <ExitReasonBreakdown reasons={btResult.metrics.exit_reasons} />
                )}

                {/* Monte Carlo Summary */}
                {btResult.metrics.monte_carlo && btResult.metrics.total_trades > 0 && (
                  <div className="monte-carlo-section">
                    <h4 style={{ color: 'var(--text-secondary)', marginBottom: 8, fontSize: 13 }}>MONTE CARLO STRESS TEST (1000 sims)</h4>
                    <div className="backtest-metrics-grid">
                      <MetricCard label="VaR 95%" value={`${btResult.metrics.monte_carlo.var_95.toFixed(1)}%`} />
                      <MetricCard label="CVaR 99%" value={`${btResult.metrics.monte_carlo.cvar_99.toFixed(1)}%`} />
                      <MetricCard label="Worst MDD" value={`${btResult.metrics.monte_carlo.worst_mdd.toFixed(1)}%`} />
                      <MetricCard label="Median Return" value={`${btResult.metrics.monte_carlo.median_return.toFixed(1)}%`} colorize />
                      <MetricCard label="Bankruptcy" value={`${btResult.metrics.monte_carlo.bankruptcy_prob.toFixed(1)}%`} />
                    </div>
                    <MonteCarloDistribution mc={btResult.metrics.monte_carlo} />
                  </div>
                )}

                {/* Trade Table */}
                {btResult.trades.length > 0 && (
                  <div style={{ maxHeight: 300, overflowY: 'auto' }}>
                    <table className="futures-trade-table">
                      <thead>
                        <tr>
                          <th>Entry</th>
                          <th>Exit</th>
                          <th>Dir</th>
                          <th>Entry {getTickerCurrency(ticker).symbol}</th>
                          <th>Exit {getTickerCurrency(ticker).symbol}</th>
                          <th>Contracts</th>
                          <th>P&L</th>
                          <th>P&L %</th>
                          <th>Days</th>
                          <th>Reason</th>
                        </tr>
                      </thead>
                      <tbody>
                        {btResult.trades.map((t, i) => (
                          <tr key={i}>
                            <td>{t.entry_date}</td>
                            <td>{t.exit_date}</td>
                            <td className={t.direction === 'LONG' ? 'dir-long' : 'dir-short'}>{t.direction}</td>
                            <td>{formatPrice(t.entry_price, ticker)}</td>
                            <td>{formatPrice(t.exit_price, ticker)}</td>
                            <td>{t.contracts}</td>
                            <td style={{ color: t.pnl_dollar >= 0 ? '#2ecc71' : '#e74c3c' }}>
                              {formatPnL(t.pnl_dollar, ticker)}
                            </td>
                            <td style={{ color: t.pnl_pct >= 0 ? '#2ecc71' : '#e74c3c' }}>
                              {t.pnl_pct.toFixed(1)}%
                            </td>
                            <td>{t.holding_days}</td>
                            <td>{t.exit_reason}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
