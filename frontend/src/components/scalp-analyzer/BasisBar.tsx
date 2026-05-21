/**
 * BasisBar — extracted from ScalpAnalyzer page.
 *
 * Phase 3.C 분할: pages/ScalpAnalyzer.tsx → components/scalp-analyzer/BasisBar.tsx
 */

import { clamp, K } from '@lib/scalpEngine';
import { Term } from '@components/glossary/GlossaryComponents';

export function BasisBar({ basis }: { basis: number }) {
  const bP = clamp((basis + 20) / 40 * 100, 2, 98);
  const bC = basis > 2 ? K.cyn : basis < -2 ? K.org : "#78909c";
  return (
    <>
      <div className="scalp-basis-bar">
        <div className="scalp-basis-center" />
        <div className="scalp-bar-dot" style={{ left: `${bP}%`, background: bC, boxShadow: `0 0 10px ${bC}80`, width: 12, height: 12 }} />
      </div>
      <div className="scalp-bar-labels">
        <Term id="backwardation">← 백워데이션 (선물&lt;현물)</Term><span>적정가</span><Term id="contango">콘탱고 (선물&gt;현물) →</Term>
      </div>
    </>
  );
}

// ── Main Page ───────────────────────────────────────────────────────

