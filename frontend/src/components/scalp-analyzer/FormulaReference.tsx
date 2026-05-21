/**
 * FormulaReference — quick reference card listing the 4 core formulas
 * (Z-Score, Expected Value, Kelly, True Range) used elsewhere in ScalpAnalyzer.
 *
 * Phase 4.D 분할: pages/ScalpAnalyzer.tsx → components/scalp-analyzer/FormulaReference.tsx
 *
 * Static content. Only depends on the local `Sec` header component and the
 * `K` color palette from the scalp engine.
 */

import { K } from '@lib/scalpEngine';
import { Sec } from './Sec';

const FORMULAS: { t: string; f: string; d: string }[] = [
  { t: 'Z-Score',         f: 'Z = (Price − MA) / σ',            d: '±2σ → 95.4% 신뢰구간 이탈' },
  { t: 'Expected Value',  f: 'EV = P(W)·W − P(L)·L − Cost',     d: '양수일 때만 진입' },
  { t: 'Kelly Criterion', f: 'f* = (b·p − q) / b',              d: 'Half-Kelly 실전 권장' },
  { t: 'True Range',      f: "TR = max(H−L, |H−C'|, |L−C'|)",   d: 'ATR = avg(TR, 14)' },
];

export function FormulaReference() {
  return (
    <div className="scalp-box">
      <Sec icon="📖" title="공식 참조 (Formula Reference)" tag="QUICK REF" tagC={K.dim} />
      <div className="scalp-formula-grid">
        {FORMULAS.map((r, i) => (
          <div key={i} className="scalp-formula-card">
            <div className="scalp-formula-title">{r.t}</div>
            <div className="scalp-formula-expr">{r.f}</div>
            <div className="scalp-formula-desc">{r.d}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
