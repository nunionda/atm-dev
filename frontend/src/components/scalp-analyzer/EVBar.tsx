/**
 * EVBar — extracted from ScalpAnalyzer page.
 *
 * Phase 3.C 분할: pages/ScalpAnalyzer.tsx → components/scalp-analyzer/EVBar.tsx
 */

import { clamp, fmt, K } from '@lib/scalpEngine';

export function EVBar({ gross, net }: { gross: number; net: number }) {
  const max = 8;
  const nP = clamp(net / max * 50, -50, 50);
  return (
    <div style={{ marginTop: 10 }}>
      <div className="scalp-ev-info">
        <span style={{ color: K.dim }}>총 EV: <span style={{ color: gross >= 0 ? K.grn : K.red }}>{fmt(gross)}t</span></span>
        <span style={{ color: K.dim }}>마찰: <span style={{ color: K.org }}>-{fmt(gross - net)}t</span></span>
        <span style={{ color: K.dim }}>순 EV: <span style={{ color: net >= 0 ? K.grn : K.red, fontWeight: 700 }}>{fmt(net)}t</span></span>
      </div>
      <div className="scalp-ev-bar">
        <div className="scalp-ev-center" />
        <div className="scalp-ev-fill" style={{
          left: nP >= 0 ? "50%" : `${50 + nP}%`,
          width: `${Math.abs(nP)}%`,
          background: nP >= 0 ? K.grn : K.red,
        }} />
      </div>
    </div>
  );
}

