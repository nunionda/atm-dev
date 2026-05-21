/**
 * MetricCard — labeled metric tile (auto-coloring optional).
 *
 * Phase 3.C 분할: pages/ESFuturesScalping.tsx → components/esf/scalping/MetricCard.tsx
 */

export function MetricCard({
  label, value, colorize,
}: {
  label: string;
  value: string;
  colorize?: boolean;
}) {
  let cls = '';
  if (colorize) {
    const num = parseFloat(value.replace(/[$,%+]/g, ''));
    if (!isNaN(num)) cls = num >= 0 ? 'positive' : 'negative';
  }
  return (
    <div className="esfu-metric-card">
      <div className="esfu-metric-label">{label}</div>
      <div className={`esfu-metric-value ${cls}`}>{value}</div>
    </div>
  );
}
