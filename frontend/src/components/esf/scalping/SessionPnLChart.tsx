/**
 * SessionPnLChart — extracted from ESFuturesScalping page.
 *
 * Phase 3.C 분할: pages/ESFuturesScalping.tsx → components/esf/scalping/SessionPnLChart.tsx
 */

import { fmtUSDLocal } from './format';

export function SessionPnLChart({ sessions }: { sessions: { date: string; total_pnl: number }[] }) {
  if (!sessions.length) return null;
  const maxAbs = Math.max(...sessions.map(s => Math.abs(s.total_pnl)), 1);

  return (
    <div className="esfu-session-chart">
      <div className="esfu-panel-title" style={{ marginBottom: 8 }}>Session P&L</div>
      <div className="esfu-session-bars">
        {sessions.map((s, i) => {
          const height = (Math.abs(s.total_pnl) / maxAbs) * 80;
          const isPos = s.total_pnl >= 0;
          return (
            <div key={i} className="esfu-session-bar-col" title={`${s.date}: ${fmtUSDLocal(s.total_pnl)}`}>
              <div className="esfu-session-bar-area">
                <div className="esfu-session-bar" style={{
                  height: `${height}px`,
                  background: isPos ? 'rgba(46,204,113,0.7)' : 'rgba(231,76,60,0.7)',
                  [isPos ? 'bottom' : 'top']: '50%',
                  position: 'absolute', left: 0, right: 0,
                }} />
              </div>
              {i % Math.max(1, Math.floor(sessions.length / 10)) === 0 && (
                <span className="esfu-session-bar-label">{s.date.slice(5)}</span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ══════════════════════════════════════════
// Exit Reason Bars
// ══════════════════════════════════════════

