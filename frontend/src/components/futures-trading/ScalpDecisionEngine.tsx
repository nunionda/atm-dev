/**
 * ScalpDecisionEngine — extracted from FuturesTrading page.
 *
 * Phase 3.C 분할: pages/FuturesTrading.tsx → components/futures-trading/ScalpDecisionEngine.tsx
 */

import { useFuturesScalp } from '@hooks/useFuturesScalp';
import { ScalpNIn } from './ScalpNIn';
import { ZBar } from './ZBar';
import { EVBar } from './EVBar';
import { KGauge } from './KGauge';
import { BasisBar } from './BasisBar';
import { RRVis } from './RRVis';
import { fmt, fmtUSD, fmtPct, ASSETS, SAMPLE_CLOSE, SAMPLE_OHLC } from '@lib/futuresScalpEngine';

export function ScalpDecisionEngine({ scalp }: { scalp: ReturnType<typeof useFuturesScalp> }) {
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

