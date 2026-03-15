import { useState, useEffect, useCallback, useRef } from 'react';
import {
  fetchESFAnalysis,
  fetchESFVolumeProfile,
  fetchESFSessionStatus,
  fetchESFCandles,
  triggerESFBacktest,
  fetchESFBacktestStatus,
  fetchESFBacktestResult,
  type ESFAnalysis,
  type ESFCandle,
  type VolumeProfileData,
  type ESFSessionStatus,
  type ESFBacktestResult,
} from '../lib/api';
import ESFIntradayChart, { type EntryPlan } from '../components/esf/ESFIntradayChart';
import ESFEquityCurve from '../components/esf/ESFEquityCurve';
import './ESFScalping.css';

// ══════════════════════════════════════════
// Helpers
// ══════════════════════════════════════════

function fmtUSD(v: number, decimals = 2): string {
  if (v < 0) return `-$${Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}`;
  return `$${v.toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}`;
}

function fmtPct(v: number): string {
  return `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`;
}

// ══════════════════════════════════════════
// AMT Panel
// ══════════════════════════════════════════

function AMTPanel({ amt }: { amt?: ESFAnalysis['amt'] }) {
  const defaultAmt: ESFAnalysis['amt'] = {
    market_state: 'BALANCE', market_state_score: 0,
    location: { zone: 'IN_VALUE', score: 0, poc: 0, vah: 0, val: 0 },
    aggression: { detected: false, direction: 'NEUTRAL', score: 0 },
  };
  const a = amt || defaultAmt;

  const stateColors: Record<string, { bg: string; fg: string }> = {
    BALANCE: { bg: 'rgba(149,165,166,0.2)', fg: '#95a5a6' },
    IMBALANCE_BULL: { bg: 'rgba(46,204,113,0.2)', fg: '#2ecc71' },
    IMBALANCE_BEAR: { bg: 'rgba(231,76,60,0.2)', fg: '#e74c3c' },
  };
  const sc = stateColors[a.market_state] || stateColors.BALANCE;

  const zoneLabels: Record<string, string> = {
    AT_POC: 'At POC',
    ABOVE_VAH: 'Above VAH',
    BELOW_VAL: 'Below VAL',
    IN_VALUE: 'In Value Area',
    AT_LVN: 'At LVN',
  };

  return (
    <div className="esf-panel">
      <h3 className="esf-panel-title">AMT 3-Stage Filter</h3>

      <div className="esf-amt-row">
        <span className="esf-label">Market State</span>
        <span className="esf-badge" style={{ background: sc.bg, color: sc.fg }}>
          {a.market_state.replace('_', ' ')}
        </span>
      </div>

      <div className="esf-amt-row">
        <span className="esf-label">Location</span>
        <span className="esf-value">
          {zoneLabels[a.location.zone] || a.location.zone}
          <span className="esf-sub"> (score: {a.location.score})</span>
        </span>
      </div>
      <div className="esf-amt-levels">
        <span>POC {a.location.poc.toFixed(2)}</span>
        <span>VAH {a.location.vah.toFixed(2)}</span>
        <span>VAL {a.location.val.toFixed(2)}</span>
      </div>

      <div className="esf-amt-row">
        <span className="esf-label">Aggression</span>
        <span className="esf-value">
          <span style={{
            color: a.aggression.direction === 'BULLISH' ? '#2ecc71' :
                   a.aggression.direction === 'BEARISH' ? '#e74c3c' : '#95a5a6',
          }}>
            {a.aggression.direction}
          </span>
          {' '}{a.aggression.detected ? '(Detected)' : '(Not detected)'}
        </span>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════
// Layer Score Bar
// ══════════════════════════════════════════

function LayerBar({ label, score, maxScore, color, signals }: {
  label: string; score: number; maxScore: number; color: string; signals: string[];
}) {
  const pct = maxScore > 0 ? (score / maxScore) * 100 : 0;
  return (
    <div className="esf-layer">
      <div className="esf-layer-header">
        <span className="esf-layer-label">{label}</span>
        <span className="esf-layer-score">{score.toFixed(1)} / {maxScore}</span>
      </div>
      <div className="esf-layer-track">
        <div className="esf-layer-fill" style={{ width: `${pct}%`, background: color }} />
      </div>
      {signals.length > 0 && (
        <div className="esf-layer-signals">
          {signals.map((s, i) => <span key={i} className="esf-signal-tag">{s}</span>)}
        </div>
      )}
    </div>
  );
}

// ══════════════════════════════════════════
// Score Panel
// ══════════════════════════════════════════

function ScorePanel({ analysis }: { analysis: ESFAnalysis }) {
  const gradeColors: Record<string, { bg: string; fg: string }> = {
    A: { bg: 'rgba(46,204,113,0.2)', fg: '#2ecc71' },
    B: { bg: 'rgba(241,196,15,0.2)', fg: '#f1c40f' },
    C: { bg: 'rgba(230,126,34,0.2)', fg: '#e67e22' },
    NO_TRADE: { bg: 'rgba(149,165,166,0.15)', fg: '#95a5a6' },
  };
  const gc = gradeColors[analysis.grade] || gradeColors.NO_TRADE;

  return (
    <div className="esf-panel">
      <h3 className="esf-panel-title">4-Layer Score</h3>
      <div className="esf-layers">
        <LayerBar label="L1: AMT + Location" score={analysis.layers.amt_location.score}
          maxScore={analysis.layers.amt_location.max_score} color="#3498db"
          signals={analysis.layers.amt_location.signals} />
        <LayerBar label="L2: Z-Score" score={analysis.layers.zscore.score}
          maxScore={analysis.layers.zscore.max_score} color="#9b59b6"
          signals={analysis.layers.zscore.signals} />
        <LayerBar label="L3: Momentum" score={analysis.layers.momentum.score}
          maxScore={analysis.layers.momentum.max_score} color="#e67e22"
          signals={analysis.layers.momentum.signals} />
        <LayerBar label="L4: Volume + Aggr." score={analysis.layers.volume_aggression.score}
          maxScore={analysis.layers.volume_aggression.max_score} color="#2ecc71"
          signals={analysis.layers.volume_aggression.signals} />
      </div>

      <div className="esf-total-row">
        <div className="esf-total-score">{analysis.total_score.toFixed(1)} / 100</div>
        <span className="esf-grade-badge" style={{ background: gc.bg, color: gc.fg }}>
          Grade {analysis.grade}
        </span>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════
// Signal Card
// ══════════════════════════════════════════

function SignalCard({ analysis }: { analysis: ESFAnalysis }) {
  const dir = analysis.direction;
  const dirColor = dir === 'LONG' ? '#2ecc71' : dir === 'SHORT' ? '#e74c3c' : '#95a5a6';
  const dirArrow = dir === 'LONG' ? ' ^' : dir === 'SHORT' ? ' v' : '';

  // Z-Score gauge
  const zClamped = Math.max(-3, Math.min(3, analysis.z_score));
  const zPct = ((zClamped + 3) / 6) * 100;

  return (
    <div className="esf-panel">
      <h3 className="esf-panel-title">Signal</h3>
      <div className="esf-signal-card">
        <div className="esf-signal-row">
          <span className="esf-label">Direction</span>
          <span style={{ color: dirColor, fontWeight: 700, fontSize: '1.1rem' }}>
            {dir}{dirArrow}
          </span>
        </div>
        <div className="esf-signal-row">
          <span className="esf-label">Entry Price</span>
          <span className="esf-value">{fmtUSD(analysis.entry_price)}</span>
        </div>
        <div className="esf-signal-row">
          <span className="esf-label">Stop Loss</span>
          <span className="esf-value" style={{ color: '#e74c3c' }}>
            {dir !== 'NEUTRAL' ? fmtUSD(analysis.stop_loss) : '--'}
          </span>
        </div>
        <div className="esf-signal-row">
          <span className="esf-label">Take Profit</span>
          <span className="esf-value" style={{ color: '#2ecc71' }}>
            {dir !== 'NEUTRAL' ? fmtUSD(analysis.take_profit) : '--'}
          </span>
        </div>
        <div className="esf-signal-row">
          <span className="esf-label">R:R Ratio</span>
          <span className="esf-value">
            {dir !== 'NEUTRAL' ? `${analysis.risk_reward_ratio.toFixed(2)} : 1` : '--'}
          </span>
        </div>
        <div className="esf-signal-row">
          <span className="esf-label">Contracts</span>
          <span className="esf-value">{analysis.contracts}</span>
        </div>
      </div>

      {/* Z-Score Gauge */}
      <div className="esf-zscore-section">
        <div className="esf-zscore-label">Z-Score</div>
        <div className="esf-zscore-track">
          <div className="esf-zscore-zone esf-zone-sell" />
          <div className="esf-zscore-zone esf-zone-neutral" />
          <div className="esf-zscore-zone esf-zone-buy" />
          <div className="esf-zscore-needle" style={{ left: `${zPct}%` }} />
        </div>
        <div className="esf-zscore-labels">
          <span>-3</span><span>-2</span><span>-1</span><span>0</span>
          <span>+1</span><span>+2</span><span>+3</span>
        </div>
        <div className="esf-zscore-value">{analysis.z_score.toFixed(2)}</div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════
// Volume Profile Chart (div-based)
// ══════════════════════════════════════════

function VolumeProfileChart({ vp, currentPrice }: { vp: VolumeProfileData; currentPrice: number }) {
  const maxVol = Math.max(...vp.nodes.map(n => n.volume), 1);
  const sortedNodes = [...vp.nodes].sort((a, b) => b.price - a.price);

  return (
    <div className="esf-panel esf-vp-panel">
      <h3 className="esf-panel-title">Volume Profile</h3>
      <div className="esf-vp-container">
        {sortedNodes.map((node, i) => {
          const pct = (node.volume / maxVol) * 100;
          const isPOC = Math.abs(node.price - vp.poc) < 0.5;
          const isVAH = Math.abs(node.price - vp.vah) < 0.5;
          const isVAL = Math.abs(node.price - vp.val) < 0.5;
          const isCurrent = Math.abs(node.price - currentPrice) < 1;
          const isLVN = vp.lvn_levels.some(l => Math.abs(node.price - l) < 0.5);

          let barColor = 'rgba(52,152,219,0.5)';
          if (isPOC) barColor = 'rgba(52,152,219,0.9)';
          else if (isLVN) barColor = 'rgba(241,196,15,0.7)';

          return (
            <div key={i} className="esf-vp-row">
              <span className={`esf-vp-price ${isCurrent ? 'esf-vp-current' : ''}`}>
                {node.price.toFixed(1)}
                {isPOC && <span className="esf-vp-tag esf-tag-poc">POC</span>}
                {isVAH && <span className="esf-vp-tag esf-tag-vah">VAH</span>}
                {isVAL && <span className="esf-vp-tag esf-tag-val">VAL</span>}
                {isCurrent && <span className="esf-vp-tag esf-tag-price">NOW</span>}
              </span>
              <div className="esf-vp-bar-wrap">
                <div className="esf-vp-bar" style={{ width: `${pct}%`, background: barColor }} />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ══════════════════════════════════════════
// Session Status Panel
// ══════════════════════════════════════════

function SessionPanel({ session, isMicro, onToggle }: {
  session: ESFSessionStatus; isMicro: boolean; onToggle: () => void;
}) {
  return (
    <div className="esf-panel">
      <h3 className="esf-panel-title">Session Status</h3>
      <div className="esf-session-grid">
        <div className="esf-session-row">
          <span className="esf-label">Status</span>
          <span className="esf-badge" style={{
            background: session.is_rth ? 'rgba(46,204,113,0.2)' : 'rgba(231,76,60,0.2)',
            color: session.is_rth ? '#2ecc71' : '#e74c3c',
          }}>
            {session.is_rth ? 'RTH Active' : 'RTH Closed'}
          </span>
        </div>
        <div className="esf-session-row">
          <span className="esf-label">Session</span>
          <span className="esf-value">{session.session}</span>
        </div>
        <div className="esf-session-row">
          <span className="esf-label">Time (ET)</span>
          <span className="esf-value">{session.current_time_et}</span>
        </div>
        <div className="esf-session-row">
          <span className="esf-label">RTH Window</span>
          <span className="esf-value">{session.rth_start} - {session.rth_end}</span>
        </div>
      </div>

      <div className="esf-toggle-row">
        <span className={!isMicro ? 'esf-toggle-active' : ''}>ES</span>
        <button className="esf-toggle-switch" onClick={onToggle}>
          <div className={`esf-toggle-thumb ${isMicro ? 'on' : ''}`} />
        </button>
        <span className={isMicro ? 'esf-toggle-active' : ''}>MES</span>
      </div>

      <div className="esf-specs-mini">
        <div><span className="esf-label">Ticker</span> {isMicro ? 'MES=F' : 'ES=F'}</div>
        <div><span className="esf-label">Multiplier</span> ${isMicro ? '5' : '50'}/pt</div>
        <div><span className="esf-label">Tick</span> 0.25 pts = ${isMicro ? '1.25' : '12.50'}</div>
        <div><span className="esf-label">Margin</span> ~${isMicro ? '1,500' : '15,000'}</div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════
// Metric Card
// ══════════════════════════════════════════

function MetricCard({ label, value, colorize }: { label: string; value: string; colorize?: boolean }) {
  let cls = '';
  if (colorize) {
    const num = parseFloat(value.replace(/[$,%+]/g, ''));
    if (!isNaN(num)) cls = num >= 0 ? 'positive' : 'negative';
  }
  return (
    <div className="esf-metric-card">
      <div className="esf-metric-label">{label}</div>
      <div className={`esf-metric-value ${cls}`}>{value}</div>
    </div>
  );
}

// ══════════════════════════════════════════
// Session PnL Bar Chart
// ══════════════════════════════════════════

function SessionPnLChart({ sessions }: { sessions: { date: string; total_pnl: number }[] }) {
  if (!sessions.length) return null;
  const maxAbs = Math.max(...sessions.map(s => Math.abs(s.total_pnl)), 1);

  return (
    <div className="esf-session-chart">
      <div className="esf-panel-title" style={{ marginBottom: 8 }}>Session P&L</div>
      <div className="esf-session-bars">
        {sessions.map((s, i) => {
          const height = (Math.abs(s.total_pnl) / maxAbs) * 80;
          const isPos = s.total_pnl >= 0;
          return (
            <div key={i} className="esf-session-bar-col" title={`${s.date}: ${fmtUSD(s.total_pnl)}`}>
              <div className="esf-session-bar-area">
                <div
                  className="esf-session-bar"
                  style={{
                    height: `${height}px`,
                    background: isPos ? 'rgba(46,204,113,0.7)' : 'rgba(231,76,60,0.7)',
                    [isPos ? 'bottom' : 'top']: '50%',
                    position: 'absolute',
                    left: 0,
                    right: 0,
                  }}
                />
              </div>
              {i % Math.max(1, Math.floor(sessions.length / 10)) === 0 && (
                <span className="esf-session-bar-label">{s.date.slice(5)}</span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ══════════════════════════════════════════
// Equity Spark (SVG)
// ══════════════════════════════════════════

function EquitySpark({ data }: { data: { timestamp: string; equity: number }[] }) {
  if (data.length < 2) return null;
  const w = 600;
  const h = 140;
  const minE = Math.min(...data.map(d => d.equity));
  const maxE = Math.max(...data.map(d => d.equity));
  const range = maxE - minE || 1;

  const points = data.map((d, i) => {
    const x = (i / (data.length - 1)) * w;
    const y = h - ((d.equity - minE) / range) * (h - 10) - 5;
    return `${x},${y}`;
  }).join(' ');

  return (
    <div className="esf-equity-spark">
      <div className="esf-panel-title" style={{ marginBottom: 8 }}>Equity Curve</div>
      <svg viewBox={`0 0 ${w} ${h}`} className="esf-spark-svg">
        <polyline points={points} fill="none" stroke="#3498db" strokeWidth="1.5" />
      </svg>
      <div className="esf-spark-labels">
        <span>{fmtUSD(minE, 0)}</span>
        <span>{fmtUSD(maxE, 0)}</span>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════
// Exit Reason Bars
// ══════════════════════════════════════════

function ExitReasonBars({ dist }: { dist: Record<string, number> }) {
  const entries = Object.entries(dist).sort((a, b) => b[1] - a[1]);
  if (!entries.length) return null;
  const maxCount = Math.max(...entries.map(([, v]) => v), 1);
  const total = entries.reduce((s, [, v]) => s + v, 0);

  return (
    <div className="esf-exit-reasons">
      <div className="esf-panel-title" style={{ marginBottom: 8 }}>Exit Reason Distribution</div>
      {entries.map(([reason, count]) => (
        <div key={reason} className="esf-exit-row">
          <span className="esf-exit-label">{reason}</span>
          <div className="esf-exit-bar-track">
            <div className="esf-exit-bar-fill" style={{ width: `${(count / maxCount) * 100}%` }} />
          </div>
          <span className="esf-exit-count">{count} ({(count / total * 100).toFixed(0)}%)</span>
        </div>
      ))}
    </div>
  );
}

// ══════════════════════════════════════════
// Main Page
// ══════════════════════════════════════════

export function ESFScalping() {
  const [isMicro, setIsMicro] = useState(true);
  const [analysis, setAnalysis] = useState<ESFAnalysis | null>(null);
  const [volumeProfile, setVolumeProfile] = useState<VolumeProfileData | null>(null);
  const [sessionStatus, setSessionStatus] = useState<ESFSessionStatus | null>(null);
  const [candles, setCandles] = useState<ESFCandle[]>([]);
  const [chartInterval, setChartInterval] = useState('15m');
  const [chartPeriod, setChartPeriod] = useState('5d');
  const [activeSubcharts, setActiveSubcharts] = useState({ rsi: true, macd: true, zscore: false });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Backtest state
  const [btPeriod, setBtPeriod] = useState('60d');
  const [btEquity, setBtEquity] = useState(10000);
  const [btRunning, setBtRunning] = useState(false);
  const [btProgress, setBtProgress] = useState(0);
  const [btResult, setBtResult] = useState<ESFBacktestResult | null>(null);
  const [btOpen, setBtOpen] = useState(false);
  const [btError, setBtError] = useState<string | null>(null);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const refreshRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const effectiveTicker = isMicro ? 'MES=F' : 'ES=F';

  // Timeout wrapper for fetch calls (5s)
  const withTimeout = useCallback(<T,>(promise: Promise<T>, ms = 5000): Promise<T> => {
    return Promise.race([
      promise,
      new Promise<never>((_, reject) =>
        setTimeout(() => reject(new Error('Request timeout')), ms),
      ),
    ]);
  }, []);

  // Load all data
  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [analysisData, vpData, sessData, candleData] = await Promise.allSettled([
        withTimeout(fetchESFAnalysis(effectiveTicker)),
        withTimeout(fetchESFVolumeProfile(effectiveTicker)),
        withTimeout(fetchESFSessionStatus()),
        withTimeout(fetchESFCandles(effectiveTicker, chartInterval, chartPeriod), 15000),
      ]);

      if (analysisData.status === 'fulfilled') setAnalysis(analysisData.value);
      else setError('Backend not available — start API server (python3 main.py api)');

      if (vpData.status === 'fulfilled') setVolumeProfile(vpData.value);
      if (sessData.status === 'fulfilled') setSessionStatus(sessData.value);
      if (candleData.status === 'fulfilled') setCandles(candleData.value.candles);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load data');
    } finally {
      setLoading(false);
    }
  }, [effectiveTicker, chartInterval, chartPeriod, withTimeout]);

  useEffect(() => {
    setAnalysis(null);
    setVolumeProfile(null);
    loadData();
  }, [loadData]);

  // Auto-refresh every 3 minutes
  useEffect(() => {
    refreshRef.current = setInterval(loadData, 180_000);
    return () => { if (refreshRef.current) clearInterval(refreshRef.current); };
  }, [loadData]);

  // Run backtest
  const runBacktest = async () => {
    setBtRunning(true);
    setBtResult(null);
    setBtError(null);
    setBtProgress(0);

    try {
      await triggerESFBacktest({
        ticker: effectiveTicker,
        period: btPeriod,
        initial_equity: btEquity,
        is_micro: isMicro,
      });

      // Poll status
      pollRef.current = setInterval(async () => {
        try {
          const status = await fetchESFBacktestStatus();
          setBtProgress(status.progress);
          if (status.status === 'completed') {
            if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
            const result = await fetchESFBacktestResult();
            setBtResult(result);
            setBtRunning(false);
          } else if (status.status === 'failed') {
            if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
            setBtError('Backtest failed on server');
            setBtRunning(false);
          }
        } catch {
          // keep polling
        }
      }, 2000);
    } catch (e: unknown) {
      setBtError(e instanceof Error ? e.message : 'Failed to start backtest');
      setBtRunning(false);
    }
  };

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  return (
    <div className="esf-page container">
      <div className="esf-header">
        <h1>ES-F Intraday Scalping</h1>
        <p>AMT 3-Stage Filter + 4-Layer Scoring + Volume Profile</p>
      </div>

      {/* Top bar */}
      <div className="esf-top-bar">
        <span className="esf-ticker-label">{effectiveTicker}</span>
        {analysis && (
          <span className="esf-badge" style={{
            background: analysis.direction === 'LONG' ? 'rgba(46,204,113,0.2)' :
                         analysis.direction === 'SHORT' ? 'rgba(231,76,60,0.2)' : 'rgba(149,165,166,0.15)',
            color: analysis.direction === 'LONG' ? '#2ecc71' :
                   analysis.direction === 'SHORT' ? '#e74c3c' : '#95a5a6',
          }}>
            {analysis.direction === 'LONG' ? '^ LONG' : analysis.direction === 'SHORT' ? 'v SHORT' : '- NEUTRAL'}
          </span>
        )}
        {sessionStatus && (
          <span className="esf-badge" style={{
            background: sessionStatus.is_rth ? 'rgba(46,204,113,0.15)' : 'rgba(149,165,166,0.15)',
            color: sessionStatus.is_rth ? '#2ecc71' : '#95a5a6',
          }}>
            {sessionStatus.is_rth ? 'RTH' : 'ETH'}
          </span>
        )}
        <button className="esf-refresh-btn" onClick={loadData} disabled={loading}>
          {loading ? '...' : 'Refresh'}
        </button>
      </div>

      {error && <div className="esf-error">{error}</div>}

      {/* Chart Section */}
      {candles.length > 0 && (
        <div className="esf-chart-wrapper">
          <div className="esf-chart-toolbar">
            <div className="esf-chart-controls">
              <select value={chartInterval} onChange={e => setChartInterval(e.target.value)} className="esf-chart-select">
                <option value="5m">5m</option>
                <option value="15m">15m</option>
                <option value="30m">30m</option>
                <option value="1h">1h</option>
              </select>
              <select value={chartPeriod} onChange={e => setChartPeriod(e.target.value)} className="esf-chart-select">
                <option value="1d">1 Day</option>
                <option value="5d">5 Days</option>
                <option value="1mo">1 Month</option>
              </select>
            </div>
            <div className="esf-subchart-toggles">
              {(['rsi', 'macd', 'zscore'] as const).map(key => (
                <label key={key} className="esf-subchart-toggle">
                  <input
                    type="checkbox"
                    checked={activeSubcharts[key]}
                    onChange={() => setActiveSubcharts(prev => ({ ...prev, [key]: !prev[key] }))}
                  />
                  <span>{key.toUpperCase()}</span>
                </label>
              ))}
            </div>
          </div>
          <ESFIntradayChart
            candles={candles}
            volumeProfile={volumeProfile ? {
              poc: volumeProfile.poc,
              vah: volumeProfile.vah,
              val: volumeProfile.val,
              lvn_levels: volumeProfile.lvn_levels || [],
            } : undefined}
            entryPlan={analysis && (analysis as any).signal_active ? {
              direction: analysis.direction as 'LONG' | 'SHORT',
              entry: analysis.entry_price,
              stopLoss: analysis.stop_loss,
              takeProfit: analysis.take_profit,
              rrRatio: analysis.risk_reward_ratio,
              multiplier: isMicro ? 5 : 50,
            } as EntryPlan : null}
            subcharts={activeSubcharts}
            height={420}
            ticker={effectiveTicker}
          />
        </div>
      )}

      {/* Section 1: Live Analysis */}
      {analysis ? (
        <div className="esf-analysis-grid">
          <AMTPanel amt={analysis.amt} />
          <ScorePanel analysis={analysis} />
          <SignalCard analysis={analysis} />
        </div>
      ) : (
        !loading && !error && <div className="esf-empty">No analysis data available</div>
      )}

      {loading && !analysis && (
        <div className="esf-loading">
          <div className="esf-spinner" />
          <span>Loading analysis...</span>
        </div>
      )}

      {/* Section 2: Volume Profile + Session */}
      {(volumeProfile || sessionStatus) && (
        <div className="esf-mid-grid">
          {volumeProfile && (
            <VolumeProfileChart
              vp={volumeProfile}
              currentPrice={analysis?.entry_price || 0}
            />
          )}
          {sessionStatus && (
            <SessionPanel
              session={sessionStatus}
              isMicro={isMicro}
              onToggle={() => setIsMicro(!isMicro)}
            />
          )}
        </div>
      )}

      {/* Section 3: Backtest */}
      <div className="esf-backtest-section">
        <button className="esf-backtest-toggle" onClick={() => setBtOpen(!btOpen)}>
          {btOpen ? 'v' : '>'} Intraday Backtest
        </button>

        {btOpen && (
          <div className="esf-backtest-content">
            <div className="esf-bt-controls">
              <div className="esf-bt-field">
                <label>Period</label>
                <select value={btPeriod} onChange={e => setBtPeriod(e.target.value)}>
                  <option value="7d">7 days</option>
                  <option value="14d">14 days</option>
                  <option value="30d">30 days</option>
                  <option value="60d">60 days</option>
                </select>
              </div>
              <div className="esf-bt-field">
                <label>Contract</label>
                <select value={isMicro ? 'MES' : 'ES'} onChange={e => setIsMicro(e.target.value === 'MES')}>
                  <option value="MES">MES (Micro)</option>
                  <option value="ES">ES (E-mini)</option>
                </select>
              </div>
              <div className="esf-bt-field">
                <label>Equity ($)</label>
                <input
                  type="number"
                  value={btEquity}
                  onChange={e => setBtEquity(Number(e.target.value))}
                  min={1000}
                  step={1000}
                />
              </div>
              <button className="esf-bt-run" onClick={runBacktest} disabled={btRunning}>
                {btRunning ? `Running... ${btProgress}%` : 'Run Backtest'}
              </button>
            </div>

            {btError && <div className="esf-error">{btError}</div>}

            {btRunning && (
              <div className="esf-progress-bar">
                <div className="esf-progress-fill" style={{ width: `${btProgress}%` }} />
              </div>
            )}

            {btResult && (
              <div className="esf-bt-results">
                {/* Metric cards */}
                <div className="esf-metrics-grid">
                  <MetricCard label="Return" value={fmtPct(btResult.metrics.total_return_pct)} colorize />
                  <MetricCard label="Sharpe" value={btResult.metrics.sharpe_ratio.toFixed(2)} />
                  <MetricCard label="MDD" value={fmtPct(btResult.metrics.max_drawdown_pct)} colorize />
                  <MetricCard label="Win Rate" value={`${btResult.metrics.win_rate.toFixed(1)}%`} />
                  <MetricCard label="Profit Factor" value={btResult.metrics.profit_factor.toFixed(2)} />
                  <MetricCard label="Trades" value={String(btResult.metrics.total_trades)} />
                  <MetricCard label="Sessions" value={String(btResult.metrics.sessions_traded)} />
                  <MetricCard label="Avg Trades/Day" value={btResult.metrics.avg_trades_per_session.toFixed(1)} />
                  <MetricCard label="Total P&L" value={fmtUSD(btResult.metrics.total_pnl)} colorize />
                  <MetricCard label="Sortino" value={btResult.metrics.sortino_ratio.toFixed(2)} />
                  <MetricCard label="Long / Short" value={`${btResult.metrics.long_trades} / ${btResult.metrics.short_trades}`} />
                  <MetricCard label="Avg Hold" value={`${btResult.metrics.avg_holding_minutes.toFixed(0)}m`} />
                  <MetricCard label="Best Session" value={fmtUSD(btResult.metrics.best_session_pnl)} colorize />
                  <MetricCard label="Worst Session" value={fmtUSD(btResult.metrics.worst_session_pnl)} colorize />
                  <MetricCard label="Win Streak" value={String(btResult.metrics.max_consecutive_wins)} />
                  <MetricCard label="Loss Streak" value={String(btResult.metrics.max_consecutive_losses)} />
                </div>

                {/* Session PnL Chart */}
                {btResult.sessions.length > 0 && (
                  <SessionPnLChart sessions={btResult.sessions} />
                )}

                {/* Equity Curve */}
                {btResult.equity_curve.length > 0 && (
                  <ESFEquityCurve
                    equityCurve={btResult.equity_curve}
                    trades={btResult.trades}
                    height={220}
                  />
                )}

                {/* Exit Reasons */}
                {btResult.metrics.exit_reason_distribution &&
                  Object.keys(btResult.metrics.exit_reason_distribution).length > 0 && (
                  <ExitReasonBars dist={btResult.metrics.exit_reason_distribution} />
                )}

                {/* Monte Carlo */}
                {btResult.monte_carlo && (
                  <div className="esf-mc-section">
                    <div className="esf-panel-title" style={{ marginBottom: 8 }}>Monte Carlo (1000 paths)</div>
                    <div className="esf-metrics-grid">
                      <MetricCard label="VaR 95%" value={fmtPct(btResult.monte_carlo.var_95)} />
                      <MetricCard label="CVaR 99%" value={fmtPct(btResult.monte_carlo.cvar_99)} />
                      <MetricCard label="Worst MDD" value={fmtPct(btResult.monte_carlo.worst_mdd)} />
                      <MetricCard label="Bankruptcy" value={`${btResult.monte_carlo.bankruptcy_prob.toFixed(1)}%`} />
                      <MetricCard label="Median Return" value={fmtPct(btResult.monte_carlo.median_return)} colorize />
                    </div>
                  </div>
                )}

                {/* Trade Log */}
                {btResult.trades.length > 0 && (
                  <div className="esf-trade-log">
                    <div className="esf-panel-title" style={{ marginBottom: 8 }}>Trade Log</div>
                    <div className="esf-trade-table-wrap">
                      <table className="esf-trade-table">
                        <thead>
                          <tr>
                            <th>Time</th>
                            <th>Dir</th>
                            <th>Entry</th>
                            <th>Exit</th>
                            <th>P&L</th>
                            <th>Bars</th>
                            <th>Reason</th>
                            <th>Grade</th>
                          </tr>
                        </thead>
                        <tbody>
                          {btResult.trades.map((t, i) => (
                            <tr key={i}>
                              <td>{t.entry_time}</td>
                              <td className={t.direction === 'LONG' ? 'esf-dir-long' : 'esf-dir-short'}>
                                {t.direction}
                              </td>
                              <td>{fmtUSD(t.entry_price)}</td>
                              <td>{fmtUSD(t.exit_price)}</td>
                              <td style={{ color: t.pnl >= 0 ? '#2ecc71' : '#e74c3c' }}>
                                {fmtUSD(t.pnl)}
                              </td>
                              <td>{t.holding_bars}</td>
                              <td>{t.exit_reason}</td>
                              <td>
                                <span className={`esf-grade-mini esf-grade-${t.grade.toLowerCase()}`}>
                                  {t.grade}
                                </span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
