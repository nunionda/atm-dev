/**
 * ScorePanel — extracted from ESFuturesScalping page.
 *
 * Phase 3.C 분할: pages/ESFuturesScalping.tsx → components/esf/scalping/ScorePanel.tsx
 */

import type { ESFAnalysis } from '@lib/api';
import { LayerBar } from './LayerBar';

export function ScorePanel({ analysis }: { analysis: ESFAnalysis }) {
  const gradeColors: Record<string, { bg: string; fg: string }> = {
    A: { bg: 'rgba(46,204,113,0.2)', fg: '#2ecc71' },
    B: { bg: 'rgba(241,196,15,0.2)', fg: '#f1c40f' },
    C: { bg: 'rgba(230,126,34,0.2)', fg: '#e67e22' },
    NO_TRADE: { bg: 'rgba(149,165,166,0.15)', fg: '#95a5a6' },
  };
  const gc = gradeColors[analysis.grade] || gradeColors.NO_TRADE;

  return (
    <div className="esfu-panel">
      <h3 className="esfu-panel-title">4-Layer Score</h3>
      <LayerBar label="L1: AMT + Location" score={analysis.layers.amt_location.score}
        maxScore={analysis.layers.amt_location.max_score} color="#3498db"
        signals={analysis.layers.amt_location.signals} />
      <LayerBar label="L2: Z-Score" score={analysis.layers.zscore.score}
        maxScore={analysis.layers.zscore.max_score} color="#9b59b6"
        signals={analysis.layers.zscore.signals} />
      <LayerBar label="L3: Momentum" score={analysis.layers.momentum.score}
        maxScore={analysis.layers.momentum.max_score} color="#e67e22"
        signals={analysis.layers.momentum.signals} />
      <LayerBar label="L4: Volume + Aggr." score={analysis.layers.volume_aggression.score}
        maxScore={analysis.layers.volume_aggression.max_score} color="#2ecc71"
        signals={analysis.layers.volume_aggression.signals} />

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 14, paddingTop: 10, borderTop: '1px solid rgba(255,255,255,0.06)' }}>
        <div style={{ fontSize: '1.3rem', fontWeight: 700 }}>{analysis.total_score.toFixed(1)} / 100</div>
        <span className="esfu-badge" style={{ background: gc.bg, color: gc.fg, fontWeight: 700 }}>
          Grade {analysis.grade}
        </span>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════
// Signal Card
// ══════════════════════════════════════════

