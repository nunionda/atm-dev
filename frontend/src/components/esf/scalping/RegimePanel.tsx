/**
 * RegimePanel — extracted from ESFuturesScalping page.
 *
 * Phase 3.C 분할: pages/ESFuturesScalping.tsx → components/esf/scalping/RegimePanel.tsx
 */

import type { ESFRegimeInfo } from '@lib/api';
import { REGIME_STYLES, STRATEGY_LABELS } from './constants';

export function RegimePanel({ regime }: { regime?: ESFRegimeInfo }) {
  if (!regime) return null;

  const style = REGIME_STYLES[regime.regime] || REGIME_STYLES.NEUTRAL;
  const scoreMin = -10, scoreMax = 10;
  const scorePct = ((regime.trend_score - scoreMin) / (scoreMax - scoreMin)) * 100;

  const componentLabels: Record<string, string> = {
    ma200_position: 'MA200 Position',
    ma200_slope: 'MA200 Slope',
    ema_alignment: 'EMA Alignment',
    macd: 'MACD',
    rsi_breadth: 'RSI Breadth',
    vix_level: 'VIX Level',
    vix: 'VIX Level',
  };

  return (
    <div className="esfu-panel">
      <h3 className="esfu-panel-title">Trend Regime</h3>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
        <span style={{ fontSize: '0.78rem', color: '#888' }}>Regime</span>
        <span className="esfu-badge" style={{ background: style.bg, color: style.fg, fontWeight: 700 }}>
          {style.label}
        </span>
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
        <span style={{ fontSize: '0.78rem', color: '#888' }}>Strategy</span>
        <span style={{ fontSize: '0.85rem', color: '#ccc' }}>
          {STRATEGY_LABELS[regime.recommended_strategy] || regime.recommended_strategy}
        </span>
      </div>
      <div style={{ marginBottom: 10 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
          <span style={{ fontSize: '0.76rem', color: '#aaa' }}>Trend Score</span>
          <span style={{ fontSize: '0.76rem', color: style.fg, fontWeight: 600 }}>{regime.trend_score > 0 ? '+' : ''}{regime.trend_score}</span>
        </div>
        <div style={{ height: 8, background: 'rgba(255,255,255,0.06)', borderRadius: 4, overflow: 'hidden', position: 'relative' }}>
          <div style={{
            position: 'absolute', left: '50%', top: 0, bottom: 0, width: 1,
            background: 'rgba(255,255,255,0.15)',
          }} />
          <div style={{
            height: '100%',
            width: `${Math.abs(scorePct - 50)}%`,
            marginLeft: regime.trend_score >= 0 ? '50%' : `${scorePct}%`,
            background: regime.trend_score >= 0 ? '#2ecc71' : '#e74c3c',
            borderRadius: 4,
            transition: 'width 0.3s, margin-left 0.3s',
          }} />
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.62rem', color: '#555', marginTop: 2 }}>
          <span>-10</span><span>0</span><span>+10</span>
        </div>
      </div>
      {regime.components && Object.keys(regime.components).length > 0 && (
        <div style={{ borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: 8, marginTop: 4 }}>
          <div style={{ fontSize: '0.7rem', color: '#666', marginBottom: 4 }}>Components</div>
          {Object.entries(regime.components).map(([key, val]) => (
            <div key={key} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem', marginBottom: 2 }}>
              <span style={{ color: '#888' }}>{componentLabels[key] || key}</span>
              <span style={{ color: (val as number) > 0 ? '#2ecc71' : (val as number) < 0 ? '#e74c3c' : '#666', fontWeight: 500 }}>
                {(val as number) > 0 ? '+' : ''}{val as number}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ══════════════════════════════════════════
// AMT Panel
// ══════════════════════════════════════════

