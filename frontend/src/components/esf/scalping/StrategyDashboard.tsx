/**
 * StrategyDashboard — extracted from ESFuturesScalping page.
 *
 * Phase 3.C 분할: pages/ESFuturesScalping.tsx → components/esf/scalping/StrategyDashboard.tsx
 */

import type { ESFRegimeInfo, ESFCandle } from '@lib/api';
import { REGIME_STYLES, STRATEGY_LABELS } from './constants';
import { analyzeMA, analyzeATR, computeUnifiedStrategy } from '@lib/futuresScalpEngine';

export function StrategyDashboard({ regime, candles }: {
  regime?: ESFRegimeInfo;
  candles: { close: number; atr_14: number | null; ema_fast: number | null; ema_mid: number | null; ema_slow: number | null; rsi_14: number | null; macd_diff: number | null; adx: number | null; zscore: number | null }[];
}) {
  const ma = analyzeMA(candles);
  const atr = analyzeATR(candles);
  const lastZ = candles.length > 0 ? candles[candles.length - 1].zscore : null;
  const unified = computeUnifiedStrategy(regime?.regime, ma, atr, lastZ);

  const maAlignColor = ma.alignment === 'BULLISH' ? '#2ecc71' : ma.alignment === 'BEARISH' ? '#e74c3c' : '#f1c40f';
  const atrStateColor = atr.state === 'EXPANDING' ? '#e74c3c' : atr.state === 'CONTRACTING' ? '#3498db' : '#95a5a6';
  const dirColor = unified.direction === 'LONG' ? '#2ecc71' : unified.direction === 'SHORT' ? '#e74c3c' : '#95a5a6';
  const confColor = unified.confidence >= 70 ? '#2ecc71' : unified.confidence >= 50 ? '#f1c40f' : '#e74c3c';

  const strategyLabels: Record<string, string> = {
    TREND_CONTINUATION: 'Trend Follow',
    MEAN_REVERSION: 'Mean Reversion',
    STAND_ASIDE: 'Stand Aside',
  };
  const timingLabels: Record<string, string> = {
    IMMEDIATE: 'Now',
    WAIT_PULLBACK: 'Wait Pullback',
    NO_ENTRY: 'No Entry',
  };

  return (
    <div className="esfu-strategy-dashboard">
      {/* Regime Panel (compact) */}
      <div className="esfu-panel">
        <h3 className="esfu-panel-title">Regime</h3>
        {regime ? (
          <>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
              <span className="esfu-badge" style={{
                background: (REGIME_STYLES[regime.regime] || REGIME_STYLES.NEUTRAL).bg,
                color: (REGIME_STYLES[regime.regime] || REGIME_STYLES.NEUTRAL).fg,
                fontWeight: 700,
              }}>{regime.regime}</span>
              <span style={{ fontSize: '0.82rem', fontWeight: 600, color: regime.trend_score >= 0 ? '#2ecc71' : '#e74c3c' }}>
                {regime.trend_score > 0 ? '+' : ''}{regime.trend_score}
              </span>
            </div>
            <div style={{ fontSize: '0.78rem', color: '#aaa' }}>
              {STRATEGY_LABELS[regime.recommended_strategy] || regime.recommended_strategy}
            </div>
            <div style={{ fontSize: '0.72rem', color: '#666', marginTop: 4 }}>
              Confidence: {(regime.confidence * 100).toFixed(0)}%
            </div>
          </>
        ) : (
          <div style={{ color: '#666', fontSize: '0.8rem' }}>No regime data</div>
        )}
      </div>

      {/* MA Trend Panel */}
      <div className="esfu-panel">
        <h3 className="esfu-panel-title">MA Trend</h3>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
          <span style={{ fontSize: '0.78rem', color: '#888' }}>Alignment</span>
          <span className="esfu-badge" style={{
            background: `${maAlignColor}20`,
            color: maAlignColor,
            fontWeight: 700,
          }}>{ma.alignment}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
          <span style={{ fontSize: '0.78rem', color: '#888' }}>Slope</span>
          <span style={{ fontSize: '0.85rem', color: ma.slope === 'RISING' ? '#2ecc71' : ma.slope === 'FALLING' ? '#e74c3c' : '#95a5a6' }}>
            {ma.slope} {ma.slope === 'RISING' ? '^' : ma.slope === 'FALLING' ? 'v' : '-'}
          </span>
        </div>
        <div style={{ fontSize: '0.72rem', color: '#666', display: 'flex', gap: 8 }}>
          <span>F:{ma.emaFast.toFixed(1)}</span>
          <span>M:{ma.emaMid.toFixed(1)}</span>
          <span>S:{ma.emaSlow.toFixed(1)}</span>
        </div>
        <div style={{ marginTop: 6 }}>
          <div style={{ height: 4, background: 'rgba(255,255,255,0.06)', borderRadius: 2, overflow: 'hidden' }}>
            <div style={{ height: '100%', width: `${ma.strength}%`, background: maAlignColor, borderRadius: 2 }} />
          </div>
          <div style={{ fontSize: '0.65rem', color: '#555', marginTop: 2, textAlign: 'right' }}>Strength {ma.strength.toFixed(0)}%</div>
        </div>
      </div>

      {/* ATR Volatility Panel */}
      <div className="esfu-panel">
        <h3 className="esfu-panel-title">ATR Volatility</h3>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
          <span style={{ fontSize: '0.78rem', color: '#888' }}>State</span>
          <span className="esfu-badge" style={{
            background: `${atrStateColor}20`,
            color: atrStateColor,
            fontWeight: 700,
          }}>{atr.state}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
          <span style={{ fontSize: '0.78rem', color: '#888' }}>Current ATR</span>
          <span style={{ fontSize: '0.85rem', fontFamily: "'IBM Plex Mono', monospace" }}>{atr.current.toFixed(2)}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
          <span style={{ fontSize: '0.78rem', color: '#888' }}>Avg ATR (20)</span>
          <span style={{ fontSize: '0.85rem', fontFamily: "'IBM Plex Mono', monospace" }}>{atr.average.toFixed(2)}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
          <span style={{ fontSize: '0.78rem', color: '#888' }}>Ratio</span>
          <span style={{ fontSize: '0.85rem', color: atrStateColor, fontWeight: 600 }}>{atr.ratio.toFixed(2)}x</span>
        </div>
        <div style={{ fontSize: '0.72rem', color: '#666', marginTop: 4 }}>
          Size Adj: {atr.positionSizeAdj.toFixed(1)}x
        </div>
      </div>

      {/* Position Strategy Bar */}
      <div className="esfu-strategy-bar">
        <div className="esfu-strategy-item">
          <span className="label">Direction</span>
          <span style={{ color: dirColor, fontWeight: 700, fontSize: '0.92rem' }}>
            {unified.direction} {unified.direction === 'LONG' ? '^' : unified.direction === 'SHORT' ? 'v' : '-'}
          </span>
        </div>
        <div className="esfu-strategy-item">
          <span className="label">Strategy</span>
          <span style={{ color: '#ccc' }}>{strategyLabels[unified.strategyType]}</span>
        </div>
        <div className="esfu-strategy-item">
          <span className="label">Entry</span>
          <span style={{ color: unified.entryTiming === 'IMMEDIATE' ? '#2ecc71' : unified.entryTiming === 'NO_ENTRY' ? '#e74c3c' : '#f1c40f' }}>
            {timingLabels[unified.entryTiming]}
          </span>
        </div>
        <div className="esfu-strategy-item">
          <span className="label">Size</span>
          <span style={{ color: '#ccc' }}>{unified.positionSizePct.toFixed(0)}%</span>
        </div>
        <div className="esfu-strategy-item">
          <span className="label">Confidence</span>
          <div className="esfu-confidence-bar">
            <div className="esfu-confidence-fill" style={{ width: `${unified.confidence}%`, background: confColor }} />
          </div>
          <span style={{ fontSize: '0.75rem', color: confColor }}>{unified.confidence}%</span>
        </div>
        {unified.reasons.length > 0 && (
          <div className="esfu-reason-tags" style={{ width: '100%' }}>
            {unified.reasons.map((r, i) => <span key={i} className="esfu-reason-tag">{r}</span>)}
          </div>
        )}
      </div>
    </div>
  );
}

// ══════════════════════════════════════════
// Scalp Decision Engine Section
// ══════════════════════════════════════════

