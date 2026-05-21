/**
 * ESF Scalping page — UI constants (style palettes, labels)
 *
 * Phase 3.C 분할: pages/ESFuturesScalping.tsx → components/esf/scalping/constants.ts
 */

export const REGIME_STYLES: Record<string, { bg: string; fg: string; label: string }> = {
  BULL:    { bg: 'rgba(46,204,113,0.2)',  fg: '#2ecc71', label: 'BULL' },
  NEUTRAL: { bg: 'rgba(241,196,15,0.2)',  fg: '#f1c40f', label: 'NEUTRAL' },
  BEAR:    { bg: 'rgba(231,76,60,0.2)',   fg: '#e74c3c', label: 'BEAR' },
  CRISIS:  { bg: 'rgba(155,89,182,0.2)',  fg: '#9b59b6', label: 'CRISIS' },
};

export const STRATEGY_LABELS: Record<string, string> = {
  long: 'Long',
  mean_reversion: 'Mean Reversion',
  short_mr_hybrid: 'Short + MR Hybrid',
  short: 'Short',
};
