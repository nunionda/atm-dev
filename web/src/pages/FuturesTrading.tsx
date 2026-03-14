import { useState, useEffect, useCallback, useRef } from 'react';
import { createChart, ColorType, type IChartApi, type Time } from 'lightweight-charts';
import {
  fetchFuturesAnalysis,
  fetchFuturesTickers,
  triggerFuturesBacktest,
  fetchAnalyticsData,
  type FuturesAnalysis,
  type FuturesTickerInfo,
  type FuturesBacktestResult,
} from '../lib/api';
import { ChartSkeleton, ScoreCardsSkeleton } from '../components/common/Skeleton';
import './FuturesTrading.css';

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
// Equity Curve Chart
// ══════════════════════════════════════════

function EquityCurveChart({ data }: { data: { date: string; total_value: number; drawdown_pct: number }[] }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!containerRef.current || !data.length) return;

    if (chartRef.current) {
      chartRef.current.remove();
    }

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height: 250,
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

    const areaSeries = chart.addAreaSeries({
      lineColor: '#3498db',
      topColor: 'rgba(52, 152, 219, 0.3)',
      bottomColor: 'rgba(52, 152, 219, 0.0)',
      lineWidth: 2,
    });

    const seen = new Set<string>();
    const dedupedData = data
      .filter(d => {
        // 날짜 부분만 추출 (시간 포함 시 중복 발생 방지)
        const dateKey = d.date.split(' ')[0].split('T')[0];
        if (seen.has(dateKey)) return false;
        seen.add(dateKey);
        return true;
      })
      .sort((a, b) => a.date.split(' ')[0].localeCompare(b.date.split(' ')[0]));

    areaSeries.setData(
      dedupedData.map(d => ({
        time: d.date.split(' ')[0].split('T')[0] as Time,
        value: d.total_value,
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
  }, [data]);

  return <div ref={containerRef} className="equity-curve-container" />;
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

  // Backtest state
  const [btOpen, setBtOpen] = useState(false);
  const [btStartDate, setBtStartDate] = useState('20240101');
  const [btEndDate, setBtEndDate] = useState('20260101');
  const [btEquity, setBtEquity] = useState(100000);
  const [btMicro, setBtMicro] = useState(false);
  const [btRunning, setBtRunning] = useState(false);
  const [btResult, setBtResult] = useState<FuturesBacktestResult | null>(null);

  // Load tickers on mount
  useEffect(() => {
    fetchFuturesTickers().then(t => setTickers(t));
  }, []);

  // Load analysis
  const loadAnalysis = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchFuturesAnalysis(ticker);
      if (data) setAnalysis(data);
    } finally {
      setLoading(false);
    }
  }, [ticker]);

  useEffect(() => { loadAnalysis(); }, [loadAnalysis]);

  // Auto-refresh
  useEffect(() => {
    if (!autoRefresh) return;
    const id = setInterval(loadAnalysis, 60000);
    return () => clearInterval(id);
  }, [autoRefresh, loadAnalysis]);

  // Run backtest
  const runBacktest = async () => {
    setBtRunning(true);
    setBtResult(null);
    try {
      const result = await triggerFuturesBacktest(ticker, btStartDate, btEndDate, btEquity, btMicro);
      if (result) setBtResult(result);
    } finally {
      setBtRunning(false);
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
                <span className="value">{analysis.entry_price.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
              </div>
              <div className="signal-card-row">
                <span className="label">Stop Loss</span>
                <span className="value loss">
                  {analysis.stop_loss.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                  {' '}({((analysis.stop_loss - analysis.entry_price) / analysis.entry_price * 100).toFixed(1)}%)
                </span>
              </div>
              <div className="signal-card-row">
                <span className="label">Take Profit</span>
                <span className="value profit">
                  {analysis.take_profit.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                  {' '}(+{((analysis.take_profit - analysis.entry_price) / analysis.entry_price * 100).toFixed(1)}%)
                </span>
              </div>
              <div className="signal-card-row">
                <span className="label">R:R Ratio</span>
                <span className="value">{analysis.risk_reward_ratio.toFixed(2)} : 1</span>
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
                <label>Equity ($)</label>
                <input type="number" value={btEquity} onChange={e => setBtEquity(Number(e.target.value))} />
              </div>
              <div className="backtest-field">
                <label style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                  <input type="checkbox" checked={btMicro} onChange={e => setBtMicro(e.target.checked)} />
                  Micro
                </label>
              </div>
              <button className="backtest-run-btn" onClick={runBacktest} disabled={btRunning}>
                {btRunning ? 'Running...' : 'Run Backtest'}
              </button>
            </div>

            {btResult && (
              <>
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
                  <MetricCard label="Total P&L" value={`$${btResult.metrics.total_pnl.toLocaleString()}`} colorize />
                  <MetricCard label="Costs" value={`$${btResult.metrics.total_costs?.toLocaleString() ?? 0}`} />
                  <MetricCard label="Best Trade" value={`${btResult.metrics.best_trade_pct?.toFixed(1) ?? 0}%`} colorize />
                  <MetricCard label="Worst Trade" value={`${btResult.metrics.worst_trade_pct?.toFixed(1) ?? 0}%`} colorize />
                  <MetricCard label="Max W Streak" value={String(btResult.metrics.max_consecutive_wins ?? 0)} />
                  <MetricCard label="Max L Streak" value={String(btResult.metrics.max_consecutive_losses ?? 0)} />
                  <MetricCard label="Avg Hold" value={`${btResult.metrics.avg_holding_days}d`} />
                </div>

                {/* Monte Carlo */}
                {btResult.metrics.monte_carlo && btResult.metrics.monte_carlo.var_95 > 0 && (
                  <div className="monte-carlo-section">
                    <h4 style={{ color: 'var(--text-secondary)', marginBottom: 8, fontSize: 13 }}>MONTE CARLO STRESS TEST (1000 sims)</h4>
                    <div className="backtest-metrics-grid">
                      <MetricCard label="VaR 95%" value={`${btResult.metrics.monte_carlo.var_95.toFixed(1)}%`} />
                      <MetricCard label="CVaR 99%" value={`${btResult.metrics.monte_carlo.cvar_99.toFixed(1)}%`} />
                      <MetricCard label="Worst MDD" value={`${btResult.metrics.monte_carlo.worst_mdd.toFixed(1)}%`} />
                      <MetricCard label="Median Return" value={`${btResult.metrics.monte_carlo.median_return.toFixed(1)}%`} colorize />
                      <MetricCard label="Bankruptcy" value={`${btResult.metrics.monte_carlo.bankruptcy_prob.toFixed(1)}%`} />
                    </div>
                  </div>
                )}

                {/* Equity Curve */}
                {btResult.equity_curve.length > 0 && (
                  <EquityCurveChart data={btResult.equity_curve} />
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
                          <th>Entry $</th>
                          <th>Exit $</th>
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
                            <td>{t.entry_price.toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
                            <td>{t.exit_price.toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
                            <td>{t.contracts}</td>
                            <td style={{ color: t.pnl_dollar >= 0 ? '#2ecc71' : '#e74c3c' }}>
                              ${t.pnl_dollar.toLocaleString()}
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
