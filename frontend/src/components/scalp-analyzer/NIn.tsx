/**
 * NIn — extracted from ScalpAnalyzer page.
 *
 * Phase 3.C 분할: pages/ScalpAnalyzer.tsx → components/scalp-analyzer/NIn.tsx
 */

import { K } from '@lib/scalpEngine';

export function NIn({ label, value, onChange, unit, step = 1, min, help, highlight }: {
  label: string; value: number; onChange: (v: number) => void;
  unit?: string; step?: number; min?: number; help?: string; highlight?: boolean;
}) {
  return (
    <div className="scalp-input-group">
      <label className={`scalp-input-label ${highlight ? 'highlight' : ''}`}>
        {label} {highlight && <span style={{ fontSize: 8, color: K.grn }}>● AUTO</span>}
      </label>
      <div className="scalp-input-row">
        <input type="number" value={value} step={step} min={min}
          onChange={e => onChange(parseFloat(e.target.value) || 0)}
          className={`scalp-input ${highlight ? 'highlight' : ''}`} />
        {unit && <span className="scalp-input-unit">{unit}</span>}
      </div>
      {help && <span className="scalp-input-help">{help}</span>}
    </div>
  );
}

