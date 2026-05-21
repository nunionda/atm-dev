/**
 * BasisBar — extracted from FuturesTrading page.
 *
 * Phase 3.C 분할: pages/FuturesTrading.tsx → components/futures-trading/BasisBar.tsx
 */

import { clamp } from '@lib/futuresScalpEngine';

export function BasisBar({ basis }: { basis: number }) {
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

