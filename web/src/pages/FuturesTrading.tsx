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
  type RollScheduleEntry,
  type ContractSpecs,
} from '../lib/api';
import { EquityCurve } from '../components/performance/EquityCurve';
import { ChartSkeleton, ScoreCardsSkeleton } from '../components/common/Skeleton';
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
