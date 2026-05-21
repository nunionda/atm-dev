/**
 * Sec — extracted from FabioStrategy page.
 *
 * Phase 3.C 분할: pages/FabioStrategy.tsx → components/fabio-strategy/Sec.tsx
 */

import { K } from '@lib/scalpEngine';
import { Pill } from './Pill';
import { InfoCard } from '@components/glossary/GlossaryComponents';

export function Sec({ icon, title, tag, tagC, infoId }: { icon: string; title: string; tag?: string; tagC?: string; infoId?: string }) {
  return (
    <div className="fb-sec">
      <span className="fb-sec-icon">{icon}</span>
      <span className="fb-sec-title">{title}</span>
      {infoId && <InfoCard id={infoId} />}
      {tag && <Pill color={tagC || K.acc}>{tag}</Pill>}
    </div>
  );
}

