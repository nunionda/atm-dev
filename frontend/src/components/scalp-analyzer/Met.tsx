/**
 * Met — extracted from ScalpAnalyzer page.
 *
 * Phase 3.C 분할: pages/ScalpAnalyzer.tsx → components/scalp-analyzer/Met.tsx
 */

import { K } from '@lib/scalpEngine';

export function Met({ label, value, sub, color, big }: {
  label: string; value: string; sub?: string; color?: string; big?: boolean;
}) {
  return (
    <div className={`scalp-met ${big ? 'big' : ''}`}>
      <div className="scalp-met-label">{label}</div>
      <div className={`scalp-met-value ${big ? 'big' : ''}`} style={{ color: color || K.txt }}>{value}</div>
      {sub && <div className="scalp-met-sub">{sub}</div>}
    </div>
  );
}

