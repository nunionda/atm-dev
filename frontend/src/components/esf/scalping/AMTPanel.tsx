/**
 * AMTPanel — extracted from ESFuturesScalping page.
 *
 * Phase 3.C 분할: pages/ESFuturesScalping.tsx → components/esf/scalping/AMTPanel.tsx
 */

import type { ESFAnalysis } from '@lib/api';

export function AMTPanel({ amt }: { amt?: ESFAnalysis['amt'] }) {
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
    AT_POC: 'At POC', ABOVE_VAH: 'Above VAH', BELOW_VAL: 'Below VAL',
    IN_VALUE: 'In Value Area', AT_LVN: 'At LVN',
  };

  return (
    <div className="esfu-panel">
      <h3 className="esfu-panel-title">AMT 3-Stage Filter</h3>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
        <span style={{ fontSize: '0.78rem', color: '#888' }}>Market State</span>
        <span className="esfu-badge" style={{ background: sc.bg, color: sc.fg }}>
          {a.market_state.replace('_', ' ')}
        </span>
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
        <span style={{ fontSize: '0.78rem', color: '#888' }}>Location</span>
        <span style={{ fontSize: '0.85rem' }}>
          {zoneLabels[a.location.zone] || a.location.zone}
          <span style={{ fontSize: '0.72rem', color: '#666', marginLeft: 4 }}>(score: {a.location.score})</span>
        </span>
      </div>
      <div style={{ display: 'flex', gap: 10, fontSize: '0.72rem', color: '#666', marginBottom: 10 }}>
        <span>POC {a.location.poc.toFixed(2)}</span>
        <span>VAH {a.location.vah.toFixed(2)}</span>
        <span>VAL {a.location.val.toFixed(2)}</span>
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: '0.78rem', color: '#888' }}>Aggression</span>
        <span style={{ fontSize: '0.85rem' }}>
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
// Score Panel
// ══════════════════════════════════════════

