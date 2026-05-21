/**
 * ZBar — extracted from ScalpAnalyzer page.
 *
 * Phase 3.C 분할: pages/ScalpAnalyzer.tsx → components/scalp-analyzer/ZBar.tsx
 */

import { clamp, K } from '@lib/scalpEngine';
import { Term } from '@components/glossary/GlossaryComponents';

export function ZBar({ z }: { z: number }) {
  const pct = clamp((z + 4) / 8 * 100, 2, 98);
  const col = z < -2 ? K.grn : z > 2 ? K.red : z < -1 ? "#69f0ae" : z > 1 ? "#ff8a80" : "#78909c";
  return (
    <div style={{ marginTop: 12 }}>
      <div className="scalp-bar-track">
        <div style={{ position: "absolute", left: 0, width: "25%", height: "100%", background: `${K.grn}0c`, borderRadius: "5px 0 0 5px" }} />
        <div style={{ position: "absolute", right: 0, width: "25%", height: "100%", background: `${K.red}0c`, borderRadius: "0 5px 5px 0" }} />
        {[12.5, 25, 37.5, 50, 62.5, 75, 87.5].map((p, i) => (
          <div key={i} style={{ position: "absolute", left: `${p}%`, top: 0, bottom: 0, width: 1, background: K.brd }} />
        ))}
        <div className="scalp-bar-dot" style={{ left: `${pct}%`, background: col, boxShadow: `0 0 12px ${col}90` }} />
      </div>
      <div className="scalp-bar-labels">
        <Term id="sigma">-4σ</Term><Term id="sigma">-2σ</Term><span>μ</span><Term id="sigma">+2σ</Term><Term id="sigma">+4σ</Term>
      </div>
    </div>
  );
}

