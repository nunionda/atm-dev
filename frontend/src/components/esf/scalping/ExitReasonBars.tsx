/**
 * ExitReasonBars — extracted from ESFuturesScalping page.
 *
 * Phase 3.C 분할: pages/ESFuturesScalping.tsx → components/esf/scalping/ExitReasonBars.tsx
 */

export function ExitReasonBars({ dist }: { dist: Record<string, number> }) {
  const entries = Object.entries(dist).sort((a, b) => b[1] - a[1]);
  if (!entries.length) return null;
  const maxCount = Math.max(...entries.map(([, v]) => v), 1);
  const total = entries.reduce((s, [, v]) => s + v, 0);

  return (
    <div className="esfu-exit-reasons">
      <div className="esfu-panel-title" style={{ marginBottom: 8 }}>Exit Reason Distribution</div>
      {entries.map(([reason, count]) => (
        <div key={reason} className="esfu-exit-row">
          <span className="esfu-exit-label">{reason}</span>
          <div className="esfu-exit-bar-track">
            <div className="esfu-exit-bar-fill" style={{ width: `${(count / maxCount) * 100}%` }} />
          </div>
          <span className="esfu-exit-count">{count} ({(count / total * 100).toFixed(0)}%)</span>
        </div>
      ))}
    </div>
  );
}

// ══════════════════════════════════════════
// Backtest Tab Content
// ══════════════════════════════════════════

