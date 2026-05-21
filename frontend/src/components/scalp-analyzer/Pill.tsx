/**
 * Pill — extracted from ScalpAnalyzer page.
 *
 * Phase 3.C 분할: pages/ScalpAnalyzer.tsx → components/scalp-analyzer/Pill.tsx
 */

import { K } from '@lib/scalpEngine';
import React from 'react';

export function Pill({ children, color = K.dim }: { children: React.ReactNode; color?: string }) {
  return (
    <span className="scalp-pill" style={{ background: `${color}15`, border: `1px solid ${color}35`, color }}>
      {children}
    </span>
  );
}

