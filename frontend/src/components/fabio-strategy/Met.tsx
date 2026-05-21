/**
 * Met — extracted from FabioStrategy page.
 *
 * Phase 3.C 분할: pages/FabioStrategy.tsx → components/fabio-strategy/Met.tsx
 */

import { K } from '@lib/scalpEngine';

export function Met({ label, value, sub, color, big }: {
  label: string; value: string; sub?: string; color?: string; big?: boolean;
}) {
  return (
    <div className={`fb-met ${big ? 'big' : ''}`}>
      <div className="fb-met-label">{label}</div>
      <div className={`fb-met-value ${big ? 'big' : ''}`} style={{ color: color || K.txt }}>{value}</div>
      {sub && <div className="fb-met-sub">{sub}</div>}
    </div>
  );
}

