/**
 * MonteCarloDistribution — extracted from FuturesTrading page.
 *
 * Phase 3.C 분할: pages/FuturesTrading.tsx → components/futures-trading/MonteCarloDistribution.tsx
 */

import type { FuturesMonteCarloResult } from '@lib/api';

export function MonteCarloDistribution({ mc }: { mc: FuturesMonteCarloResult }) {
  if (!mc.return_distribution?.length && !mc.mdd_distribution?.length) return null;

  const renderHistogram = (
    data: { bin: number; count: number }[],
    title: string,
    color: string,
    percentiles?: { p5: number; p25: number; p50: number; p75: number; p95: number },
  ) => {
    if (!data.length) return null;
    const maxCount = Math.max(...data.map(d => d.count), 1);
    return (
      <div className="mc-dist-panel">
        <div className="mc-dist-title">{title}</div>
        {percentiles && (
          <div className="mc-percentiles">
            <span>P5: {percentiles.p5.toFixed(1)}%</span>
            <span>P25: {percentiles.p25.toFixed(1)}%</span>
            <span className="mc-p-median">P50: {percentiles.p50.toFixed(1)}%</span>
            <span>P75: {percentiles.p75.toFixed(1)}%</span>
            <span>P95: {percentiles.p95.toFixed(1)}%</span>
          </div>
        )}
        <div className="mc-histogram">
          {data.map((d, i) => (
            <div key={i} className="mc-bar-col" title={`${d.bin.toFixed(1)}%: ${d.count} sims`}>
              <div
                className="mc-bar"
                style={{
                  height: `${(d.count / maxCount) * 100}%`,
                  background: color,
                }}
              />
              {i % 4 === 0 && <span className="mc-bin-label">{d.bin.toFixed(0)}</span>}
            </div>
          ))}
        </div>
      </div>
    );
  };

  return (
    <div className="mc-distribution">
      {renderHistogram(mc.return_distribution, 'Return Distribution (1000 sims, 252 days)', 'rgba(52, 152, 219, 0.7)', mc.return_percentiles)}
      {renderHistogram(mc.mdd_distribution, 'Max Drawdown Distribution', 'rgba(231, 76, 60, 0.7)')}
    </div>
  );
}

// ══════════════════════════════════════════
// Exit Reason Breakdown
// ══════════════════════════════════════════

