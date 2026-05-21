/**
 * NIn — extracted from FabioStrategy page.
 *
 * Phase 3.C 분할: pages/FabioStrategy.tsx → components/fabio-strategy/NIn.tsx
 */

import { K } from '@lib/scalpEngine';

export function NIn({ label, value, onChange, unit, step = 1, min, max, help }: {
  label: string; value: number; onChange: (v: number) => void;
  unit?: string; step?: number; min?: number; max?: number; help?: string;
}) {
  return (
    <div className="fb-input-group">
      <label className="fb-input-label">{label}</label>
      <div className="fb-input-row">
        <input type="number" value={value} step={step} min={min} max={max}
          onChange={e => onChange(parseFloat(e.target.value) || 0)}
          className="fb-input" />
        {unit && <span className="fb-input-unit">{unit}</span>}
      </div>
      {help && <span className="fb-input-help">{help}</span>}
    </div>
  );
}

// ── Color helpers ────────────────────────────────────────────────────

const stateColor = (s: MarketState) =>
  s === 'BALANCE' ? K.cyn : s === 'IMBALANCE_BULL' ? K.grn : s === 'IMBALANCE_BEAR' ? K.red : K.dim;

const gradeColor = (g: SetupGrade) =>
  g === 'A' ? K.grn : g === 'B' ? K.ylw : g === 'C' ? K.org : K.red;

const phaseColor = (p: TripleAPhase) =>
  p === 'FULL_ALIGNMENT' ? K.grn : p === 'AGGRESSION' ? K.org : p === 'ACCUMULATION' ? K.cyn : p === 'ABSORPTION' ? K.ylw : K.dim;

const modelLabel = (m: SetupModel) =>
  m === 'TREND_CONTINUATION' ? 'TREND' : m === 'MEAN_REVERSION' ? 'MEAN REV' : 'NONE';

// ── Main Page ────────────────────────────────────────────────────────

