/**
 * LayerBar — 4-Layer score visualization bar (one row per layer).
 *
 * Phase 3.C 분할: pages/ESFuturesScalping.tsx → components/esf/scalping/LayerBar.tsx
 */

export function LayerBar({
  label, score, maxScore, color, signals,
}: {
  label: string;
  score: number;
  maxScore: number;
  color: string;
  signals: string[];
}) {
  const pct = maxScore > 0 ? (score / maxScore) * 100 : 0;
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
        <span style={{ fontSize: '0.76rem', color: '#aaa' }}>{label}</span>
        <span style={{ fontSize: '0.76rem', color: '#ccc', fontWeight: 600 }}>{score.toFixed(1)} / {maxScore}</span>
      </div>
      <div style={{ height: 8, background: 'rgba(255,255,255,0.06)', borderRadius: 4, overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${pct}%`, background: color, borderRadius: 4, transition: 'width 0.3s' }} />
      </div>
      {signals.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 3 }}>
          {signals.map((s, i) => (
            <span key={i} style={{ fontSize: '0.65rem', padding: '1px 6px', background: 'rgba(255,255,255,0.06)', borderRadius: 3, color: '#999' }}>{s}</span>
          ))}
        </div>
      )}
    </div>
  );
}
