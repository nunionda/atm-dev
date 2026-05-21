/**
 * ESF Scalping page — number / time formatting helpers
 *
 * Phase 3.C 분할: pages/ESFuturesScalping.tsx → components/esf/scalping/format.ts
 */

/** USD value with $ prefix and N decimals. Negatives rendered as `-$xx`. */
export function fmtUSDLocal(v: number, decimals = 2): string {
  if (v < 0) {
    return `-$${Math.abs(v).toLocaleString('en-US', {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    })}`;
  }
  return `$${v.toLocaleString('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })}`;
}

/** Index points formatter (no currency symbol). */
export function fmtPts(v: number, decimals = 2): string {
  return v.toLocaleString('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

/** Signed percent with 2 decimals (e.g., `+1.23%` / `-0.45%`). */
export function fmtPctLocal(v: number): string {
  return `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`;
}

/** Relative time since epoch ms — `just now` / `5s ago` / `3m ago`. */
export function timeAgo(ts: number | null): string {
  if (!ts) return '';
  const secs = Math.floor((Date.now() - ts) / 1000);
  if (secs < 5) return 'just now';
  if (secs < 60) return `${secs}s ago`;
  return `${Math.floor(secs / 60)}m ago`;
}
