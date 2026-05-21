/**
 * KGauge — extracted from FuturesTrading page.
 *
 * Phase 3.C 분할: pages/FuturesTrading.tsx → components/futures-trading/KGauge.tsx
 */

import { clamp } from '@lib/futuresScalpEngine';

export function KGauge({ hk, conv }: { hk: number; conv: string }) {
  const pct = clamp(hk * 100 / 25, 0, 100);
  const col = conv === 'NO EDGE' ? '#ff1744' : (conv === 'VERY LOW' || conv === 'LOW') ? '#ffab40' : conv === 'MODERATE' ? '#fdd835' : '#00e676';
  return (
    <>
      <div className="scalp-kgauge-track">
        <div className="scalp-kgauge-fill" style={{ width: `${pct}%`, background: `linear-gradient(90deg, ${col}50, ${col})` }} />
      </div>
      <div className="scalp-kgauge-labels">
        <span>0%</span>
        <span className="scalp-pill" style={{ background: `${col}15`, border: `1px solid ${col}35`, color: col }}>{conv}</span>
        <span>25%</span>
      </div>
    </>
  );
}

