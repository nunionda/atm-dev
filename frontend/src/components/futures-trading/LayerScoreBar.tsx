/**
 * LayerScoreBar — extracted from FuturesTrading page.
 *
 * Phase 3.C 분할: pages/FuturesTrading.tsx → components/futures-trading/LayerScoreBar.tsx
 */


export function LayerScoreBar({ label, score, maxScore, layerClass, signals }: {
  label: string; score: number; maxScore: number; layerClass: string; signals: string[];
}) {
  const pct = maxScore > 0 ? (score / maxScore) * 100 : 0;
  return (
    <div>
      <div className="layer-row">
        <span className="layer-label">{label}</span>
        <div className="layer-bar-container">
          <div
            className={`layer-bar-fill ${layerClass}`}
            style={{ width: `${pct}%` }}
          />
        </div>
        <span className="layer-score-text">{score.toFixed(1)} / {maxScore}</span>
      </div>
      {signals.length > 0 && (
        <div className="layer-signals" style={{ marginLeft: 90 }}>
          {signals.map((s, i) => <span key={i} className="signal-tag">{s}</span>)}
        </div>
      )}
    </div>
  );
}

// ══════════════════════════════════════════
// Z-Score Gauge
// ══════════════════════════════════════════

