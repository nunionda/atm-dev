/**
 * ZScoreGauge — extracted from FuturesTrading page.
 *
 * Phase 3.C 분할: pages/FuturesTrading.tsx → components/futures-trading/ZScoreGauge.tsx
 */


export function ZScoreGauge({ zscore }: { zscore: number }) {
  // Map zscore -3..+3 to 0..100%
  const clamped = Math.max(-3, Math.min(3, zscore));
  const pct = ((clamped + 3) / 6) * 100;

  let color = '#95a5a6';
  if (zscore <= -2) color = '#e74c3c';
  else if (zscore <= -1) color = '#e67e22';
  else if (zscore >= 2) color = '#e74c3c';
  else if (zscore >= 1) color = '#e67e22';

  return (
    <div className="zscore-gauge-container">
      <div className="zscore-gauge">
        <span className="zscore-gauge-label">Z-Score</span>
        <div className="zscore-gauge-track">
          <div className="zscore-gauge-needle" style={{ left: `${pct}%` }} />
        </div>
        <span className="zscore-gauge-value" style={{ color }}>{zscore.toFixed(2)}</span>
      </div>
      <div className="zscore-gauge-labels">
        <span>-3 (Oversold)</span>
        <span>-2</span>
        <span>-1</span>
        <span>0</span>
        <span>+1</span>
        <span>+2</span>
        <span>+3 (Overbought)</span>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════
// Backtest Metrics Cards
// ══════════════════════════════════════════

