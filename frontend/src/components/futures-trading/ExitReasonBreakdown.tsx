/**
 * ExitReasonBreakdown — extracted from FuturesTrading page.
 *
 * Phase 3.C 분할: pages/FuturesTrading.tsx → components/futures-trading/ExitReasonBreakdown.tsx
 */


export function ExitReasonBreakdown({ reasons }: { reasons: Record<string, number> }) {
  const entries = Object.entries(reasons).sort((a, b) => b[1] - a[1]);
  if (entries.length === 0) return null;
  const total = entries.reduce((s, [, v]) => s + v, 0);
  const maxCount = Math.max(...entries.map(([, v]) => v), 1);

  const reasonLabels: Record<string, string> = {
    ES1: 'Hard Stop (-5%)',
    ES_ATR_SL: 'ATR Stop Loss',
    ES_ATR_TP: 'ATR Take Profit',
    ES_CHANDELIER: 'Chandelier Exit',
    ES3: 'Trailing Stop',
    ES_CHOCH: 'CHoCH Reversal',
    ES5: 'Max Holding Days',
    FORCED_CLOSE: 'End of Period',
  };

  return (
    <div className="exit-breakdown">
      <div className="exit-breakdown-title">EXIT REASONS</div>
      {entries.map(([reason, count]) => (
        <div key={reason} className="exit-row">
          <span className="exit-label">{reasonLabels[reason] || reason}</span>
          <div className="exit-bar-wrap">
            <div className="exit-bar" style={{ width: `${(count / maxCount) * 100}%` }} />
          </div>
          <span className="exit-count">{count} ({(count / total * 100).toFixed(0)}%)</span>
        </div>
      ))}
    </div>
  );
}

// ══════════════════════════════════════════
// Price Chart
// ══════════════════════════════════════════

