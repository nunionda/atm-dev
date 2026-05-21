/**
 * SignalCard — extracted from ESFuturesScalping page.
 *
 * Phase 3.C 분할: pages/ESFuturesScalping.tsx → components/esf/scalping/SignalCard.tsx
 */

import type { ESFAnalysis } from '@lib/api';
import { fmtPts } from './format';

export function SignalCard({ analysis }: { analysis: ESFAnalysis }) {
  const dir = analysis.direction;
  const dirColor = dir === 'LONG' ? '#2ecc71' : dir === 'SHORT' ? '#e74c3c' : '#95a5a6';

  const zClamped = Math.max(-3, Math.min(3, analysis.z_score));
  const zPct = ((zClamped + 3) / 6) * 100;

  const rows = [
    { label: 'Direction', val: <span style={{ color: dirColor, fontWeight: 700, fontSize: '1.1rem' }}>{dir}{dir === 'LONG' ? ' ^' : dir === 'SHORT' ? ' v' : ''}</span> },
    { label: 'Entry Price', val: fmtPts(analysis.entry_price) },
    { label: 'Stop Loss', val: dir !== 'NEUTRAL' ? <span style={{ color: '#e74c3c' }}>{fmtPts(analysis.stop_loss)}</span> : '--' },
    { label: 'Take Profit', val: dir !== 'NEUTRAL' ? <span style={{ color: '#2ecc71' }}>{fmtPts(analysis.take_profit)}</span> : '--' },
    { label: 'R:R Ratio', val: dir !== 'NEUTRAL' ? `${analysis.risk_reward_ratio.toFixed(2)} : 1` : '--' },
    { label: 'Contracts', val: analysis.contracts },
  ];

  return (
    <div className="esfu-panel">
      <h3 className="esfu-panel-title">Signal</h3>
      <div style={{ marginBottom: 14 }}>
        {rows.map((r, i) => (
          <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '5px 0', borderBottom: i < rows.length - 1 ? '1px solid rgba(255,255,255,0.04)' : 'none' }}>
            <span style={{ fontSize: '0.78rem', color: '#888' }}>{r.label}</span>
            <span style={{ fontSize: '0.85rem' }}>{r.val}</span>
          </div>
        ))}
      </div>

      {/* Z-Score Gauge */}
      <div style={{ marginTop: 14, paddingTop: 12, borderTop: '1px solid rgba(255,255,255,0.06)' }}>
        <div style={{ fontSize: '0.76rem', color: '#888', marginBottom: 6 }}>Z-Score</div>
        <div style={{ position: 'relative', height: 12, borderRadius: 6, display: 'flex', overflow: 'hidden' }}>
          <div style={{ flex: 1, background: 'linear-gradient(90deg, rgba(46,204,113,0.4), rgba(46,204,113,0.15))' }} />
          <div style={{ flex: 1, background: 'rgba(149,165,166,0.15)' }} />
          <div style={{ flex: 1, background: 'linear-gradient(90deg, rgba(231,76,60,0.15), rgba(231,76,60,0.4))' }} />
          <div style={{ position: 'absolute', top: -2, width: 4, height: 16, background: '#fff', borderRadius: 2, transform: 'translateX(-50%)', left: `${zPct}%`, boxShadow: '0 0 6px rgba(255,255,255,0.5)' }} />
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.6rem', color: '#666', marginTop: 3 }}>
          <span>-3</span><span>-2</span><span>-1</span><span>0</span>
          <span>+1</span><span>+2</span><span>+3</span>
        </div>
        <div style={{ textAlign: 'center', fontSize: '0.9rem', fontWeight: 700, marginTop: 4 }}>
          {analysis.z_score.toFixed(2)}
        </div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════
// Indicator Panel (ATR / ADX / BB / EMA)
// ══════════════════════════════════════════

