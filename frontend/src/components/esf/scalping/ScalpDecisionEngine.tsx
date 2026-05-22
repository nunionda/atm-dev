/**
 * ScalpDecisionEngine — extracted from ESFuturesScalping page.
 *
 * Phase 3.C 분할: pages/ESFuturesScalping.tsx → components/esf/scalping/ScalpDecisionEngine.tsx
 */

import { useState } from 'react';
import type { ScalpState } from '@hooks/useFuturesScalp';
import type { VWATRZone, FuturesPaperPosition } from '@lib/api';
import { ScalpNIn, ZBar, EVBar, KGauge, BasisBar } from './ScalpControls';
import { RRVis } from './RRVis';
import { fmt, fmtPct, fmtUSD, ASSETS, SAMPLE_CLOSE, SAMPLE_OHLC } from '@lib/futuresScalpEngine';

export interface ScalpDecisionEngineProps {
  scalp: ScalpState;
  magneticMA?: number;
  vwatrZone?: VWATRZone | null;
  // Paper trading flow
  backendDirection?: 'LONG' | 'SHORT' | 'NEUTRAL';
  directionAgrees?: boolean;
  disagreementReason?: 'ok' | 'loading' | 'no_signal' | 'mismatch';
  canTrade?: boolean;
  activePosition?: FuturesPaperPosition | null;
  placingPaperOrder?: boolean;
  paperOrderError?: string | null;
  onPlacePaperTrade?: (contracts: number) => void;
}

export function ScalpDecisionEngine({
  scalp, magneticMA, vwatrZone,
  backendDirection, directionAgrees, disagreementReason, canTrade,
  activePosition, placingPaperOrder, paperOrderError, onPlacePaperTrade,
}: ScalpDecisionEngineProps) {
  const { dataMode, setDataMode, closeText, setCloseText, ohlcText, setOhlcText,
    maPeriod, setMaPeriod, closesCount, candlesCount, autoStats, inputs,
    setInput, setAsset, calc } = scalp;

  const frontendDir: 'LONG' | 'SHORT' = calc.isLong ? 'LONG' : 'SHORT';

  // 사유별 verdict 메시지 (no_signal / mismatch / loading 분리)
  // - no_signal: backend NEUTRAL (Grade NO_TRADE 등) — 백엔드가 진입 권유 안 함. 프론트의 SHORT/LONG은 강제 추정값.
  // - mismatch:  backend LONG/SHORT vs frontend 반대 — 두 분석기 진짜 충돌.
  // - loading:   backend 응답 미수신.
  // - ok / undefined: 정상 흐름 (calc.verdict 그대로 적용).
  let effectiveVerdict: string;
  if (disagreementReason === 'no_signal') {
    effectiveVerdict = 'NO ENTRY (backend NEUTRAL)';
  } else if (disagreementReason === 'mismatch') {
    effectiveVerdict = `NO ENTRY (방향 충돌: BACK ${backendDirection} ≠ FRONT ${frontendDir})`;
  } else if (disagreementReason === 'loading') {
    effectiveVerdict = 'NO ENTRY (backend 응답 대기)';
  } else {
    effectiveVerdict = calc.verdict === 'GO' ? 'GO' : calc.verdict === 'CAUTION' ? 'CAUTION' : 'NO ENTRY';
  }

  // 색상 — no_signal/loading은 회색(노란계열), mismatch만 빨강 강조
  const vc =
    effectiveVerdict === 'GO' ? 'go'
    : effectiveVerdict === 'CAUTION' ? 'caution'
    : disagreementReason === 'mismatch' ? 'no-entry'
    : 'caution';  // no_signal/loading은 caution 톤 — 진짜 충돌 아님

  // Agreement 배지 — 사유별 표시
  const agreementBadge = backendDirection !== undefined
    ? (disagreementReason === 'ok'
        ? <span style={{ color: '#00e676', fontWeight: 700 }}> AGREE ✓</span>
        : disagreementReason === 'no_signal'
          ? <span style={{ color: '#fdd835', fontWeight: 700 }}> NO SIGNAL ⓘ</span>
          : disagreementReason === 'mismatch'
            ? <span style={{ color: '#ff1744', fontWeight: 700 }}> CONFLICT ✗</span>
            : <span style={{ color: '#888', fontWeight: 700 }}> LOADING…</span>)
    : null;

  const [contracts, setContracts] = useState(1);
  const [showConfirm, setShowConfirm] = useState(false);

  return (
    <div className="scalp-section">
      <div className="scalp-section-header">
        <div style={{ width: 34, height: 34, borderRadius: 8, background: 'linear-gradient(135deg, #3b82f6, #1d4ed8)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 17, fontWeight: 900, color: '#fff', fontFamily: "'IBM Plex Mono', monospace" }}>S</div>
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

      <div className={`scalp-verdict-strip ${vc}`}>
        {effectiveVerdict} — [{calc.passN}/4] — {calc.zSignal} — FRONT:{frontendDir}
        {backendDirection !== undefined && (
          <> | BACK:{backendDirection}{agreementBadge}</>
        )}
        {autoStats && <span style={{ opacity: 0.5 }}> — ATR: {autoStats.atrMethod}</span>}
      </div>

      {/* ── Place Paper Trade CTA ── */}
      {onPlacePaperTrade && (
        <div className="scalp-paper-cta" style={{
          padding: '12px 16px', display: 'flex', alignItems: 'center', gap: 12,
          background: 'rgba(255,255,255,0.02)',
          borderRadius: 8,
          marginBottom: 12,
          border: `1px solid ${canTrade ? 'rgba(0,230,118,0.3)' : 'rgba(255,255,255,0.08)'}`,
        }}>
          {activePosition ? (
            <div style={{ flex: 1, fontSize: 13, color: '#ffab40' }}>
              ⚠ OPEN position exists for this ticker — manage in tracker panel
            </div>
          ) : (
            <>
              <div style={{ flex: 1, fontSize: 12, color: '#aaa' }}>
                {canTrade
                  ? <span style={{ color: '#00e676' }}>✓ Ready to place {frontendDir} paper trade</span>
                  : <span>Cannot place: {
                      disagreementReason === 'no_signal' ? 'backend NEUTRAL (Grade NO_TRADE) — 진입 신호 없음'
                      : disagreementReason === 'mismatch' ? `direction conflict (BACK ${backendDirection} ≠ FRONT ${frontendDir})`
                      : disagreementReason === 'loading' ? 'backend 응답 대기 중'
                      : !directionAgrees ? 'direction not aligned'
                      : !calc.verdict || calc.verdict !== 'GO' ? `verdict=${calc.verdict}`
                      : 'signal not active'
                    }</span>
                }
              </div>
              <label style={{ fontSize: 12, color: '#888' }}>
                Contracts:
                <input
                  type="number"
                  min={1}
                  max={5}
                  value={contracts}
                  onChange={e => setContracts(Math.max(1, parseInt(e.target.value) || 1))}
                  style={{
                    width: 50, marginLeft: 6, padding: '4px 6px',
                    background: 'rgba(255,255,255,0.05)', color: '#fff',
                    border: '1px solid rgba(255,255,255,0.15)', borderRadius: 4,
                    fontFamily: "'IBM Plex Mono', monospace",
                  }}
                />
              </label>
              <button
                disabled={!canTrade || placingPaperOrder || !!activePosition}
                onClick={() => setShowConfirm(true)}
                style={{
                  padding: '8px 16px',
                  background: canTrade && !activePosition ? 'linear-gradient(135deg, #00c853, #00e676)' : 'rgba(255,255,255,0.08)',
                  color: canTrade && !activePosition ? '#000' : '#666',
                  border: 'none', borderRadius: 6, fontWeight: 700,
                  cursor: canTrade && !placingPaperOrder && !activePosition ? 'pointer' : 'not-allowed',
                  fontSize: 13,
                }}
              >
                {placingPaperOrder ? 'Placing...' : 'Place Paper Trade'}
              </button>
            </>
          )}
        </div>
      )}

      {paperOrderError && (
        <div style={{
          padding: '8px 12px', marginBottom: 12, background: 'rgba(255,23,68,0.1)',
          border: '1px solid rgba(255,23,68,0.3)', borderRadius: 6,
          color: '#ff8a80', fontSize: 12,
        }}>
          {paperOrderError}
        </div>
      )}

      {showConfirm && onPlacePaperTrade && (
        <div className="scalp-confirm-modal" style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 9999,
        }} onClick={() => setShowConfirm(false)}>
          <div style={{
            background: '#1a1a2e', borderRadius: 12, padding: 24, maxWidth: 420, width: '90%',
            border: '1px solid rgba(255,255,255,0.15)',
          }} onClick={e => e.stopPropagation()}>
            <h3 style={{ margin: 0, marginBottom: 12, color: '#fff' }}>Confirm Paper Trade</h3>
            <div style={{ fontSize: 13, color: '#bbb', lineHeight: 1.8 }}>
              <div>Direction: <b style={{ color: frontendDir === 'LONG' ? '#00e676' : '#ff1744' }}>{frontendDir}</b></div>
              <div>Entry (locked from backend): <b>{fmt(calc.cfg ? inputs.currentPrice : 0, 2)}</b></div>
              <div>Stop Loss (locked): <b style={{ color: '#ff1744' }}>{fmt(calc.sl, 2)}</b></div>
              <div>Take Profit (locked): <b style={{ color: '#00e676' }}>{fmt(calc.tp2, 2)}</b></div>
              <div>Contracts: <b>{contracts}</b> × {calc.cfg.label}</div>
              <div>Risk per contract: <b>{fmtUSD(calc.riskPerContract)}</b></div>
              <div style={{ marginTop: 8, fontSize: 11, color: '#888' }}>
                * 백엔드 /esf/analyze 응답이 canonical SL/TP를 lock-in 합니다. 위 값은 참고용.
              </div>
            </div>
            <div style={{ display: 'flex', gap: 8, marginTop: 20, justifyContent: 'flex-end' }}>
              <button
                onClick={() => setShowConfirm(false)}
                style={{
                  padding: '8px 16px', background: 'rgba(255,255,255,0.05)',
                  color: '#fff', border: '1px solid rgba(255,255,255,0.15)',
                  borderRadius: 6, cursor: 'pointer',
                }}
              >Cancel</button>
              <button
                onClick={() => { onPlacePaperTrade(contracts); setShowConfirm(false); }}
                style={{
                  padding: '8px 16px',
                  background: 'linear-gradient(135deg, #00c853, #00e676)',
                  color: '#000', border: 'none', borderRadius: 6,
                  fontWeight: 700, cursor: 'pointer',
                }}
              >Confirm</button>
            </div>
          </div>
        </div>
      )}

      <div className="scalp-layout">
        {/* LEFT: INPUTS */}
        <div className="scalp-sidebar">
          <div className="scalp-box" style={{ borderColor: dataMode !== 'manual' ? 'rgba(59,130,246,0.4)' : undefined }}>
            <div className="scalp-box-header">
              <span className="icon">Price Data</span>
              <span className="scalp-pill" style={{
                background: dataMode !== 'manual' ? 'rgba(0,230,118,0.1)' : 'rgba(255,255,255,0.05)',
                border: `1px solid ${dataMode !== 'manual' ? 'rgba(0,230,118,0.3)' : 'rgba(255,255,255,0.1)'}`,
                color: dataMode !== 'manual' ? '#00e676' : '#888',
              }}>{dataMode === 'ohlc' ? 'OHLC' : dataMode === 'close' ? 'CLOSE' : 'MANUAL'}</span>
            </div>

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

            {dataMode === 'manual' && (
              <>
                <ScalpNIn label="Current Price" value={inputs.currentPrice} onChange={v => setInput('currentPrice')(v)} step={0.25} unit="pts" />
                <ScalpNIn label="MA (Moving Avg)" value={inputs.ma} onChange={v => setInput('ma')(v)} step={0.25} unit="pts" />
                <ScalpNIn label="Std Dev" value={inputs.stdDev} onChange={v => setInput('stdDev')(v)} step={0.5} unit="pts" />
                <ScalpNIn label="ATR" value={inputs.atr} onChange={v => setInput('atr')(v)} step={0.25} unit="pts" />
              </>
            )}

            {dataMode !== 'manual' && (
              <ScalpNIn label="MA Period" value={maPeriod} onChange={setMaPeriod} step={1} min={2} help="MA & StdDev calculation period" />
            )}

            {dataMode !== 'manual' && autoStats && (
              <div className="scalp-auto-stats">
                <div className="scalp-auto-stats-header">
                  Auto — {autoStats.atrMethod === 'TRUE-RANGE'
                    ? <span style={{ color: '#4fc3f7' }}>True Range ATR</span>
                    : <span style={{ color: '#ffab40' }}>Close-Proxy ATR</span>}
                </div>
                <div className="scalp-auto-stats-grid">
                  {[
                    { l: 'Price', v: fmt(autoStats.currentPrice, 2) },
                    { l: `MA(${autoStats.maPeriod})`, v: fmt(autoStats.ma, 2) },
                    { l: 'StdDev', v: fmt(autoStats.stdDev, 2) },
                    { l: 'ATR(14)', v: fmt(autoStats.atr, 2) },
                  ].map((item, i) => (
                    <div key={i}>
                      <div className="scalp-auto-stat-label">{item.l}</div>
                      <div className="scalp-auto-stat-value">{item.v}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <ScalpNIn label="ATR Mult (Stop)" value={inputs.atrMult} onChange={v => setInput('atrMult')(v)} step={0.1} min={0.1} help="Scalp: 0.5-1.0 / Swing: 1.5-2.0" />
          </div>

          <div className="scalp-box">
            <div className="scalp-box-header">
              <span className="title">Backtest Stats</span>
              <span className="scalp-pill" style={{ background: 'rgba(59,130,246,0.1)', border: '1px solid rgba(59,130,246,0.3)', color: '#3b82f6' }}>EV INPUT</span>
            </div>
            <ScalpNIn label="Win Rate" value={inputs.winRate} onChange={v => setInput('winRate')(v)} step={1} unit="%" />
            <ScalpNIn label="Avg Win" value={inputs.avgWin} onChange={v => setInput('avgWin')(v)} step={0.5} unit="ticks" />
            <ScalpNIn label="Avg Loss" value={inputs.avgLoss} onChange={v => setInput('avgLoss')(v)} step={0.5} unit="ticks" />
            <ScalpNIn label="Slippage" value={inputs.slippage} onChange={v => setInput('slippage')(v)} step={0.25} unit="ticks" />
            <ScalpNIn label="Commission" value={inputs.commission} onChange={v => setInput('commission')(v)} step={0.05} unit="$" />
          </div>

          <div className="scalp-box">
            <div className="scalp-box-header"><span className="title">Account</span></div>
            <ScalpNIn label="Balance" value={inputs.accountBalance} onChange={v => setInput('accountBalance')(v)} step={100} unit="$" />
            <ScalpNIn label="Risk Per Trade" value={inputs.riskPct} onChange={v => setInput('riskPct')(v)} step={0.5} min={0.1} unit="%" />
          </div>

          <div className="scalp-box">
            <div className="scalp-box-header"><span className="title">Basis Spread</span></div>
            <ScalpNIn label="Spot (SPX)" value={inputs.spotPrice} onChange={v => setInput('spotPrice')(v)} step={0.25} unit="pts" />
            <ScalpNIn label="Futures (ES)" value={inputs.futuresPrice} onChange={v => setInput('futuresPrice')(v)} step={0.25} unit="pts" />
          </div>
        </div>

        {/* RIGHT: OUTPUTS */}
        <div className="scalp-main">
          {/* Decision Matrix */}
          <div className="scalp-box" style={{ borderColor: calc.verdict === 'GO' ? 'rgba(0,230,118,0.3)' : calc.verdict === 'CAUTION' ? 'rgba(253,216,53,0.3)' : 'rgba(255,23,68,0.3)' }}>
            <div className="scalp-box-header">
              <span className="title">Decision Matrix</span>
              <span className="scalp-pill" style={{
                background: calc.verdict === 'GO' ? 'rgba(0,230,118,0.1)' : calc.verdict === 'CAUTION' ? 'rgba(253,216,53,0.1)' : 'rgba(255,23,68,0.1)',
                border: `1px solid ${calc.verdict === 'GO' ? 'rgba(0,230,118,0.3)' : calc.verdict === 'CAUTION' ? 'rgba(253,216,53,0.3)' : 'rgba(255,23,68,0.3)'}`,
                color: calc.verdict === 'GO' ? '#00e676' : calc.verdict === 'CAUTION' ? '#fdd835' : '#ff1744',
              }}>ENTRY CHECKLIST</span>
            </div>
            {calc.checks.map((c, i) => (
              <div key={i} className={`scalp-check-item ${c.pass ? 'pass' : 'fail'}`}>
                <span className={`scalp-check-icon ${c.pass ? 'pass' : 'fail'}`}>{c.pass ? 'Y' : 'N'}</span>
                <div style={{ flex: 1 }}>
                  <div className="scalp-check-label">{c.label}</div>
                  <div className="scalp-check-val">{c.val}</div>
                </div>
              </div>
            ))}
            <div className="scalp-verdict-box" style={{
              background: calc.verdict === 'GO' ? 'rgba(0,230,118,0.08)' : calc.verdict === 'CAUTION' ? 'rgba(253,216,53,0.08)' : 'rgba(255,23,68,0.08)',
              border: `1px solid ${calc.verdict === 'GO' ? 'rgba(0,230,118,0.3)' : calc.verdict === 'CAUTION' ? 'rgba(253,216,53,0.3)' : 'rgba(255,23,68,0.3)'}`,
              color: calc.verdict === 'GO' ? '#00e676' : calc.verdict === 'CAUTION' ? '#fdd835' : '#ff1744',
            }}>
              [{calc.passN}/4] {calc.verdict === 'GO' ? 'ALL CLEAR' : calc.verdict === 'CAUTION' ? 'CONDITIONAL' : 'WAIT'}
            </div>
          </div>

          {/* Z-Score Analysis */}
          <div className="scalp-box">
            <div className="scalp-box-header">
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
              </div>
              <div className="scalp-met">
                <div className="scalp-met-label">Deviation</div>
                <div className="scalp-met-value">{fmt(inputs.currentPrice - inputs.ma, 1)}p</div>
              </div>
            </div>
            <ZBar z={calc.z} />
          </div>

          {/* EV Engine */}
          <div className="scalp-box">
            <div className="scalp-box-header">
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
                <div className="scalp-met-sub">{calc.netEV >= 0 ? '+' : '-'} {fmtUSD(Math.abs(calc.netEVusd))}</div>
              </div>
              <div className="scalp-met">
                <div className="scalp-met-label">Gross EV</div>
                <div className="scalp-met-value">{fmt(calc.grossEV)}t</div>
              </div>
              <div className="scalp-met">
                <div className="scalp-met-label">Friction</div>
                <div className="scalp-met-value" style={{ color: '#ffab40' }}>{fmt(calc.friction)}t</div>
              </div>
              <div className="scalp-met">
                <div className="scalp-met-label">R:R</div>
                <div className="scalp-met-value">{fmt(calc.b, 1)}:1</div>
              </div>
            </div>
            <EVBar gross={calc.grossEV} net={calc.netEV} />
          </div>

          {/* Kelly + Position Sizer */}
          <div className="scalp-side-panels">
            <div className="scalp-box">
              <div className="scalp-box-header">
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
            </div>

            <div className="scalp-box">
              <div className="scalp-box-header"><span className="title">Position Sizer</span></div>
              <div className="scalp-met-row">
                <div className="scalp-met">
                  <div className="scalp-met-label">Risk Budget</div>
                  <div className="scalp-met-value">{fmtUSD(calc.riskBudget)}</div>
                  <div className="scalp-met-sub">{inputs.riskPct}% of balance</div>
                </div>
                <div className="scalp-met">
                  <div className="scalp-met-label">Risk/Contract</div>
                  <div className="scalp-met-value">{fmtUSD(calc.riskPerContract)}</div>
                  <div className="scalp-met-sub">{fmt(calc.atrStop)}p x ${calc.cfg.ptVal}</div>
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
              <span className="title">ATR Stop & R:R Map</span>
              <span className="scalp-pill" style={{ background: 'rgba(59,130,246,0.1)', border: '1px solid rgba(59,130,246,0.3)', color: '#3b82f6' }}>ATR x{inputs.atrMult}</span>
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
            <RRVis
              entry={inputs.currentPrice}
              sl={calc.sl} tp15={calc.tp15} tp2={calc.tp2} tp3={calc.tp3}
              cfg={calc.cfg}
              currentPrice={inputs.currentPrice}
              magneticMA={magneticMA}
              vwatrZone={vwatrZone ? { ma_value: vwatrZone.ma_value, zone_type: vwatrZone.zone_type, ma_type: vwatrZone.ma_type, ma_period: vwatrZone.ma_period, strength: vwatrZone.strength } : null}
              lockedSL={activePosition?.stop_loss}
              lockedTP={activePosition?.take_profit}
            />
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
          </div>

          {/* Formula Reference */}
          <div className="scalp-box">
            <div className="scalp-box-header">
              <span className="title">Formula Reference</span>
              <span className="scalp-pill" style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', color: '#888' }}>QUICK REF</span>
            </div>
            <div className="scalp-formula-grid">
              {[
                { t: 'Z-Score', f: 'Z = (Price - MA) / s', d: '+/-2s = 95.4% CI' },
                { t: 'Expected Value', f: 'EV = P(W)*W - P(L)*L - Cost', d: 'Enter only when positive' },
                { t: 'Kelly Criterion', f: 'f* = (b*p - q) / b', d: 'Half-Kelly recommended' },
                { t: 'True Range', f: "TR = max(H-L, |H-C'|, |L-C'|)", d: 'ATR = avg(TR, 14)' },
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
// Session PnL Bar Chart
// ══════════════════════════════════════════

