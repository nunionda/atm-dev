/**
 * Pill — extracted from FabioStrategy page.
 *
 * Phase 3.C 분할: pages/FabioStrategy.tsx → components/fabio-strategy/Pill.tsx
 */

import React from 'react';
import { K } from '@lib/scalpEngine';

export function Pill({ children, color = K.dim }: { children: React.ReactNode; color?: string }) {
  return (
    <span className="fb-pill" style={{ background: `${color}15`, border: `1px solid ${color}35`, color }}>
      {children}
    </span>
  );
}

