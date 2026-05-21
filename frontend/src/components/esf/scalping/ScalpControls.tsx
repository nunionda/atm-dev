/**
 * Scalp Decision Engine — gauge / input UI primitives.
 *
 * Phase 3.C 분할: pages/ESFuturesScalping.tsx → components/esf/scalping/ScalpControls.tsx
 *
 * Components: ScalpNIn, ZBar, EVBar, KGauge, BasisBar
 *   - ScalpNIn  : labeled number input row (with AUTO badge + unit + help)
 *   - ZBar      : Z-score horizontal scale (-4..+4) with color zones
 *   - EVBar     : Expected-value bar (gross / net split, ± centered)
 *   - KGauge    : Kelly conviction gauge (0–25%)
 *   - BasisBar  : Futures basis bar (BACKWARDATION ↔ FAIR ↔ CONTANGO)
 *
 * 외부 의존: `clamp`, `fmt` from '@lib/futuresScalpEngine'.
 */

import { clamp, fmt } from '@lib/futuresScalpEngine';

export function ScalpNIn({ label, value, onChange, unit, step = 1, min, help, highlight }: {
  label: string; value: number; onChange: (v: number) => void; unit?: string;
  step?: number; min?: number; help?: string; highlight?: boolean;
}) {
  return (
    <div className="scalp-input-group">
      <label className={`scalp-input-label ${highlight ? 'auto' : ''}`}>
        {label} {highlight && <span style={{ fontSize: '0.5rem', color: '#00e676' }}>AUTO</span>}
      </label>
      <div className="scalp-input-row">
        <input type="number" value={value} step={step} min={min}
          onChange={e => onChange(parseFloat(e.target.value) || 0)} />
        {unit && <span className="scalp-input-unit">{unit}</span>}
      </div>
      {help && <span className="scalp-input-help">{help}</span>}
    </div>
  );
}

export function ZBar({ z }: { z: number }) {
  const pct = clamp((z + 4) / 8 * 100, 2, 98);
  const col = z < -2 ? '#00e676' : z > 2 ? '#ff1744' : z < -1 ? '#69f0ae' : z > 1 ? '#ff8a80' : '#78909c';
  return (
    <div className="scalp-zbar">
      <div className="scalp-zbar-track">
        <div className="scalp-zbar-zone-left" />
        <div className="scalp-zbar-zone-right" />
        {[12.5, 25, 37.5, 50, 62.5, 75, 87.5].map((p, i) => (
          <div key={i} style={{ position: 'absolute', left: `${p}%`, top: 0, bottom: 0, width: 1, background: 'var(--border-color, #333)' }} />
        ))}
        <div className="scalp-zbar-dot" style={{ left: `${pct}%`, background: col, boxShadow: `0 0 12px ${col}90` }} />
      </div>
      <div className="scalp-zbar-labels">
        <span>-4</span><span>-2</span><span>0</span><span>+2</span><span>+4</span>
      </div>
    </div>
  );
}

export function EVBar({ gross, net }: { gross: number; net: number }) {
  const max = 8;
  const nP = clamp(net / max * 50, -50, 50);
  return (
    <div style={{ marginTop: 10 }}>
      <div className="scalp-evbar-meta">
        <span>Gross: <span style={{ color: gross >= 0 ? '#00e676' : '#ff1744' }}>{fmt(gross)}t</span></span>
        <span>Friction: <span style={{ color: '#ffab40' }}>-{fmt(gross - net)}t</span></span>
        <span>Net: <span style={{ color: net >= 0 ? '#00e676' : '#ff1744', fontWeight: 700 }}>{fmt(net)}t</span></span>
      </div>
      <div className="scalp-evbar-track">
        <div className="scalp-evbar-center" />
        <div className="scalp-evbar-fill" style={{
          left: nP >= 0 ? '50%' : `${50 + nP}%`,
          width: `${Math.abs(nP)}%`,
          background: nP >= 0 ? '#00e676' : '#ff1744',
        }} />
      </div>
    </div>
  );
}

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

export function BasisBar({ basis }: { basis: number }) {
  const bP = clamp((basis + 20) / 40 * 100, 2, 98);
  const bC = basis > 2 ? '#4fc3f7' : basis < -2 ? '#ffab40' : '#78909c';
  return (
    <>
      <div className="scalp-basis-track">
        <div className="scalp-basis-center" />
        <div className="scalp-basis-dot" style={{ left: `${bP}%`, background: bC, boxShadow: `0 0 10px ${bC}80` }} />
      </div>
      <div className="scalp-basis-labels">
        <span>BACKWARDATION</span><span>FAIR</span><span>CONTANGO</span>
      </div>
    </>
  );
}

// ══════════════════════════════════════════
