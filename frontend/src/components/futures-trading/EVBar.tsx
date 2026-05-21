/**
 * EVBar — extracted from FuturesTrading page.
 *
 * Phase 3.C 분할: pages/FuturesTrading.tsx → components/futures-trading/EVBar.tsx
 */

import { clamp, fmt } from '@lib/futuresScalpEngine';

export function EVBar({ gross, net }: { gross: number; net: number }) {
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

