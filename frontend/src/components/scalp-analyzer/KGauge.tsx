/**
 * KGauge — extracted from ScalpAnalyzer page.
 *
 * Phase 3.C 분할: pages/ScalpAnalyzer.tsx → components/scalp-analyzer/KGauge.tsx
 */

import { clamp, K, F } from '@lib/scalpEngine';
import { Pill } from './Pill';

export function KGauge({ hk, conv }: { hk: number; conv: string }) {
  const pct = clamp(hk * 100 / 25, 0, 100);
  const col = conv === "NO EDGE" ? K.red : (conv === "VERY LOW" || conv === "LOW") ? K.org : conv === "MODERATE" ? K.ylw : K.grn;
  return (
    <div style={{ marginTop: 10 }}>
      <div className="scalp-gauge-track">
        <div className="scalp-gauge-fill" style={{ width: `${pct}%`, background: `linear-gradient(90deg,${col}50,${col})` }} />
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 5 }}>
        <span style={{ fontSize: 8.5, color: K.mut, fontFamily: F.mono }}>0%</span>
        <Pill color={col}>{conv}</Pill>
        <span style={{ fontSize: 8.5, color: K.mut, fontFamily: F.mono }}>25%</span>
      </div>
    </div>
  );
}

