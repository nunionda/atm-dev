/**
 * Sec — extracted from ScalpAnalyzer page.
 *
 * Phase 3.C 분할: pages/ScalpAnalyzer.tsx → components/scalp-analyzer/Sec.tsx
 */

import { K } from '@lib/scalpEngine';
import { Pill } from './Pill';
import { InfoCard } from '@components/glossary/GlossaryComponents';

export function Sec({ icon, title, tag, tagC, infoId }: { icon: string; title: string; tag?: string; tagC?: string; infoId?: string }) {
  return (
    <div className="scalp-sec">
      <span className="scalp-sec-icon">{icon}</span>
      <span className="scalp-sec-title">{title}</span>
      {infoId && <InfoCard id={infoId} />}
      {tag && <Pill color={tagC || K.acc}>{tag}</Pill>}
    </div>
  );
}

// ── Gauge Components ────────────────────────────────────────────────

