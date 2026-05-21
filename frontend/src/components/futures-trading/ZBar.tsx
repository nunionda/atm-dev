/**
 * ZBar — extracted from FuturesTrading page.
 *
 * Phase 3.C 분할: pages/FuturesTrading.tsx → components/futures-trading/ZBar.tsx
 */

import { clamp } from '@lib/futuresScalpEngine';

export function ZBar({ z }: { z: number }) {
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

