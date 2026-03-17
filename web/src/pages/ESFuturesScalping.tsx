import React, { useState } from 'react';
import { useESFuturesScalp, type TabKey } from '../hooks/useESFuturesScalp';
import { useESFJournal } from '../hooks/useESFJournal';
import type { ESFHypothesis } from '../lib/api';
import {
  ASSETS, SAMPLE_CLOSE, SAMPLE_OHLC, clamp, fmt, fmtUSD, fmtPct,
  analyzeMA, analyzeATR, computeUnifiedStrategy,
} from '../lib/futuresScalpEngine';
import type {
  ESFAnalysis, ESFRegimeInfo, VolumeProfileData, ESFSessionStatus, ESFCandle, VWATRZone,
} from '../lib/api';
import type { DataMode, ScalpState } from '../hooks/useFuturesScalp';
import ESFIntradayChart, { type EntryPlan } from '../components/esf/ESFIntradayChart';
import ESFEquityCurve from '../components/esf/ESFEquityCurve';
import { EquityCurve } from '../components/performance/EquityCurve';
import './ESFuturesScalping.css';
// Reuse scalp section CSS from FuturesTrading
import './FuturesTrading.css';

// ══════════════════════════════════════════
// Helpers
// ══════════════════════════════════════════

function fmtUSDLocal(v: number, decimals = 2): string {
  if (v < 0) return `-$${Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}`;
  return `$${v.toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}`;
}

/** 지수 포인트 포맷 (달러 기호 없음) */
function fmtPts(v: number, decimals = 2): string {
  return v.toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

function fmtPctLocal(v: number): string {
  return `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`;
}

function timeAgo(ts: number | null): string {
  if (!ts) return '';
  const secs = Math.floor((Date.now() - ts) / 1000);
  if (secs < 5) return 'just now';
  if (secs < 60) return `${secs}s ago`;
  return `${Math.floor(secs / 60)}m ago`;
}

// ══════════════════════════════════════════
// AMT Panel (from ESFScalping)
// ══════════════════════════════════════════

// ══════════════════════════════════════════
// Trend Regime Panel
// ══════════════════════════════════════════

const REGIME_STYLES: Record<string, { bg: string; fg: string; label: string }> = {
  BULL:    { bg: 'rgba(46,204,113,0.2)',  fg: '#2ecc71', label: 'BULL' },
  NEUTRAL: { bg: 'rgba(241,196,15,0.2)',  fg: '#f1c40f', label: 'NEUTRAL' },
  BEAR:    { bg: 'rgba(231,76,60,0.2)',   fg: '#e74c3c', label: 'BEAR' },
  CRISIS:  { bg: 'rgba(155,89,182,0.2)',  fg: '#9b59b6', label: 'CRISIS' },
};

const STRATEGY_LABELS: Record<string, string> = {
  long: 'Long',
  mean_reversion: 'Mean Reversion',
  short_mr_hybrid: 'Short + MR Hybrid',
  short: 'Short',
};

function RegimePanel({ regime }: { regime?: ESFRegimeInfo }) {
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

function AMTPanel({ amt }: { amt?: ESFAnalysis['amt'] }) {
  const defaultAmt: ESFAnalysis['amt'] = {
    market_state: 'BALANCE', market_state_score: 0,
    location: { zone: 'IN_VALUE', score: 0, poc: 0, vah: 0, val: 0 },
    aggression: { detected: false, direction: 'NEUTRAL', score: 0 },
  };
  const a = amt || defaultAmt;

  const stateColors: Record<string, { bg: string; fg: string }> = {
    BALANCE: { bg: 'rgba(149,165,166,0.2)', fg: '#95a5a6' },
    IMBALANCE_BULL: { bg: 'rgba(46,204,113,0.2)', fg: '#2ecc71' },
    IMBALANCE_BEAR: { bg: 'rgba(231,76,60,0.2)', fg: '#e74c3c' },
  };
  const sc = stateColors[a.market_state] || stateColors.BALANCE;

  const zoneLabels: Record<string, string> = {
    AT_POC: 'At POC', ABOVE_VAH: 'Above VAH', BELOW_VAL: 'Below VAL',
    IN_VALUE: 'In Value Area', AT_LVN: 'At LVN',
  };

  return (
    <div className="esfu-panel">
      <h3 className="esfu-panel-title">AMT 3-Stage Filter</h3>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
        <span style={{ fontSize: '0.78rem', color: '#888' }}>Market State</span>
        <span className="esfu-badge" style={{ background: sc.bg, color: sc.fg }}>
          {a.market_state.replace('_', ' ')}
        </span>
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
        <span style={{ fontSize: '0.78rem', color: '#888' }}>Location</span>
        <span style={{ fontSize: '0.85rem' }}>
          {zoneLabels[a.location.zone] || a.location.zone}
          <span style={{ fontSize: '0.72rem', color: '#666', marginLeft: 4 }}>(score: {a.location.score})</span>
        </span>
      </div>
      <div style={{ display: 'flex', gap: 10, fontSize: '0.72rem', color: '#666', marginBottom: 10 }}>
        <span>POC {a.location.poc.toFixed(2)}</span>
        <span>VAH {a.location.vah.toFixed(2)}</span>
        <span>VAL {a.location.val.toFixed(2)}</span>
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: '0.78rem', color: '#888' }}>Aggression</span>
        <span style={{ fontSize: '0.85rem' }}>
          <span style={{
            color: a.aggression.direction === 'BULLISH' ? '#2ecc71' :
                   a.aggression.direction === 'BEARISH' ? '#e74c3c' : '#95a5a6',
          }}>
            {a.aggression.direction}
          </span>
          {' '}{a.aggression.detected ? '(Detected)' : '(Not detected)'}
        </span>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════
// Layer Score Bar
// ══════════════════════════════════════════

function LayerBar({ label, score, maxScore, color, signals }: {
  label: string; score: number; maxScore: number; color: string; signals: string[];
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

// ══════════════════════════════════════════
// Score Panel
// ══════════════════════════════════════════

function ScorePanel({ analysis }: { analysis: ESFAnalysis }) {
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

function SignalCard({ analysis }: { analysis: ESFAnalysis }) {
  const dir = analysis.direction;
  const dirColor = dir === 'LONG' ? '#2ecc71' : dir === 'SHORT' ? '#e74c3c' : '#95a5a6';

  const zClamped = Math.max(-3, Math.min(3, analysis.z_score));
  const zPct = ((zClamped + 3) / 6) * 100;

  const rows = [
    { label: 'Direction', val: <span style={{ color: dirColor, fontWeight: 700, fontSize: '1.1rem' }}>{dir}{dir === 'LONG' ? ' ^' : dir === 'SHORT' ? ' v' : ''}</span> },
    { label: 'Entry Price', val: fmtPts(analysis.entry_price) },
    { label: 'Stop Loss', val: dir !== 'NEUTRAL' ? <span style={{ color: '#e74c3c' }}>{fmtPts(analysis.stop_loss)}</span> : '--' },
    { label: 'Take Profit', val: dir !== 'NEUTRAL' ? <span style={{ color: '#2ecc71' }}>{fmtPts(analysis.take_profit)}</span> : '--' },
    { label: 'R:R Ratio', val: dir !== 'NEUTRAL' ? `${analysis.risk_reward_ratio.toFixed(2)} : 1` : '--' },
    { label: 'Contracts', val: analysis.contracts },
  ];

  return (
    <div className="esfu-panel">
      <h3 className="esfu-panel-title">Signal</h3>
      <div style={{ marginBottom: 14 }}>
        {rows.map((r, i) => (
          <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '5px 0', borderBottom: i < rows.length - 1 ? '1px solid rgba(255,255,255,0.04)' : 'none' }}>
            <span style={{ fontSize: '0.78rem', color: '#888' }}>{r.label}</span>
            <span style={{ fontSize: '0.85rem' }}>{r.val}</span>
          </div>
        ))}
      </div>

      {/* Z-Score Gauge */}
      <div style={{ marginTop: 14, paddingTop: 12, borderTop: '1px solid rgba(255,255,255,0.06)' }}>
        <div style={{ fontSize: '0.76rem', color: '#888', marginBottom: 6 }}>Z-Score</div>
        <div style={{ position: 'relative', height: 12, borderRadius: 6, display: 'flex', overflow: 'hidden' }}>
          <div style={{ flex: 1, background: 'linear-gradient(90deg, rgba(46,204,113,0.4), rgba(46,204,113,0.15))' }} />
          <div style={{ flex: 1, background: 'rgba(149,165,166,0.15)' }} />
          <div style={{ flex: 1, background: 'linear-gradient(90deg, rgba(231,76,60,0.15), rgba(231,76,60,0.4))' }} />
          <div style={{ position: 'absolute', top: -2, width: 4, height: 16, background: '#fff', borderRadius: 2, transform: 'translateX(-50%)', left: `${zPct}%`, boxShadow: '0 0 6px rgba(255,255,255,0.5)' }} />
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.6rem', color: '#666', marginTop: 3 }}>
          <span>-3</span><span>-2</span><span>-1</span><span>0</span>
          <span>+1</span><span>+2</span><span>+3</span>
        </div>
        <div style={{ textAlign: 'center', fontSize: '0.9rem', fontWeight: 700, marginTop: 4 }}>
          {analysis.z_score.toFixed(2)}
        </div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════
// Indicator Panel (ATR / ADX / BB / EMA)
// ══════════════════════════════════════════

function IndicatorPanel({ analysis, candles }: { analysis: ESFAnalysis; candles: ESFCandle[] }) {
  const last = candles.length > 0 ? candles[candles.length - 1] : null;
  const prev = candles.length > 1 ? candles[candles.length - 2] : null;

  // ATR
  const atr = last?.atr_14 ?? analysis.atr ?? 0;
  const atrPrev = prev?.atr_14 ?? 0;
  const atrPct = analysis.entry_price > 0 ? (atr / analysis.entry_price) * 100 : 0;
  const atrTrend = atrPrev > 0
    ? atr > atrPrev * 1.05 ? 'EXPANDING' : atr < atrPrev * 0.95 ? 'CONTRACTING' : 'NORMAL'
    : 'NORMAL';
  const atrColor = atrTrend === 'EXPANDING' ? '#e74c3c' : atrTrend === 'CONTRACTING' ? '#2ecc71' : '#f1c40f';

  // ADX / DMI
  const adx = last?.adx ?? 0;
  const plusDI = last?.plus_di ?? 0;
  const minusDI = last?.minus_di ?? 0;
  const adxLabel = adx >= 40 ? 'STRONG' : adx >= 25 ? 'TRENDING' : adx >= 20 ? 'WEAK' : 'NO TREND';
  const adxColor = adx >= 40 ? '#2ecc71' : adx >= 25 ? '#3498db' : adx >= 20 ? '#f1c40f' : '#95a5a6';
  const diMax = Math.max(plusDI, minusDI, 40);

  // Bollinger Bands
  const bbH = last?.bb_hband ?? 0;
  const bbL = last?.bb_lband ?? 0;
  const bbMid = last?.bb_mavg ?? 0;
  const bw = bbMid > 0 ? ((bbH - bbL) / bbMid) * 100 : 0;
  const pctB = (bbH - bbL) > 0 ? Math.max(0, Math.min(100, ((analysis.entry_price - bbL) / (bbH - bbL)) * 100)) : 50;
  const bbState = bw < 2 ? 'SQUEEZE' : bw > 5 ? 'WIDE' : 'NORMAL';
  const bbStateColor = bbState === 'SQUEEZE' ? '#9b59b6' : bbState === 'WIDE' ? '#e67e22' : '#3498db';

  // EMA Stack
  const ef = last?.ema_fast ?? 0;
  const em = last?.ema_mid ?? 0;
  const es = last?.ema_slow ?? 0;
  const price = analysis.entry_price;
  const emaAlign =
    price > ef && ef > em && em > es ? 'BULL STACK' :
    price < ef && ef < em && em < es ? 'BEAR STACK' :
    ef > em && em > es ? 'BULLISH' :
    ef < em && em < es ? 'BEARISH' : 'MIXED';
  const emaColor = emaAlign === 'BULL STACK' ? '#2ecc71' : emaAlign === 'BEAR STACK' ? '#e74c3c' : emaAlign === 'BULLISH' ? '#27ae60' : emaAlign === 'BEARISH' ? '#c0392b' : '#95a5a6';

  const subStyle: React.CSSProperties = {
    background: 'rgba(0,0,0,0.2)',
    borderRadius: 8,
    padding: '10px 12px',
  };
  const labelStyle: React.CSSProperties = { fontSize: '0.72rem', color: '#888', marginBottom: 6, fontWeight: 600, letterSpacing: '0.04em' };
  const valueStyle: React.CSSProperties = { fontSize: '1.1rem', fontWeight: 700, color: '#e0e0e0' };

  return (
    <div className="esfu-panel" style={{ height: '100%' }}>
      <h3 className="esfu-panel-title">Technical Indicators</h3>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>

        {/* ATR */}
        <div style={subStyle}>
          <div style={labelStyle}>ATR (14)</div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 6 }}>
            <span style={valueStyle}>{atr.toFixed(2)}</span>
            <span style={{ fontSize: '0.75rem', color: '#999' }}>pts</span>
            <span style={{ fontSize: '0.75rem', color: '#aaa', marginLeft: 'auto' }}>{atrPct.toFixed(2)}% of price</span>
          </div>
          <span className="esfu-badge" style={{ background: `${atrColor}22`, color: atrColor, fontSize: '0.7rem' }}>{atrTrend}</span>
        </div>

        {/* ADX / DMI */}
        <div style={subStyle}>
          <div style={labelStyle}>ADX / DMI</div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 6 }}>
            <span style={valueStyle}>{adx.toFixed(1)}</span>
            <span className="esfu-badge" style={{ background: `${adxColor}22`, color: adxColor, fontSize: '0.7rem' }}>{adxLabel}</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ fontSize: '0.68rem', color: '#2ecc71', minWidth: 24 }}>+DI</span>
              <div style={{ flex: 1, height: 5, background: 'rgba(255,255,255,0.08)', borderRadius: 3, overflow: 'hidden' }}>
                <div style={{ width: `${(plusDI / diMax) * 100}%`, height: '100%', background: '#2ecc71', borderRadius: 3 }} />
              </div>
              <span style={{ fontSize: '0.68rem', color: '#aaa', minWidth: 28, textAlign: 'right' }}>{plusDI.toFixed(1)}</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ fontSize: '0.68rem', color: '#e74c3c', minWidth: 24 }}>-DI</span>
              <div style={{ flex: 1, height: 5, background: 'rgba(255,255,255,0.08)', borderRadius: 3, overflow: 'hidden' }}>
                <div style={{ width: `${(minusDI / diMax) * 100}%`, height: '100%', background: '#e74c3c', borderRadius: 3 }} />
              </div>
              <span style={{ fontSize: '0.68rem', color: '#aaa', minWidth: 28, textAlign: 'right' }}>{minusDI.toFixed(1)}</span>
            </div>
          </div>
        </div>

        {/* Bollinger Bands */}
        <div style={subStyle}>
          <div style={labelStyle}>Bollinger Bands</div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 6 }}>
            <span style={{ fontSize: '0.88rem', fontWeight: 700, color: '#e0e0e0' }}>BW {bw.toFixed(2)}%</span>
            <span className="esfu-badge" style={{ background: `${bbStateColor}22`, color: bbStateColor, fontSize: '0.7rem', marginLeft: 'auto' }}>{bbState}</span>
          </div>
          <div style={{ marginBottom: 4 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.66rem', color: '#666', marginBottom: 2 }}>
              <span>0%</span><span style={{ color: '#aaa' }}>%B {pctB.toFixed(0)}%</span><span>100%</span>
            </div>
            <div style={{ position: 'relative', height: 8, background: 'rgba(255,255,255,0.06)', borderRadius: 4, overflow: 'visible' }}>
              <div style={{ position: 'absolute', top: -1, left: `${pctB}%`, width: 3, height: 10, background: '#f1c40f', borderRadius: 2, transform: 'translateX(-50%)' }} />
            </div>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.64rem', color: '#666', marginTop: 4 }}>
            <span>L {bbL.toFixed(1)}</span>
            <span>Mid {bbMid.toFixed(1)}</span>
            <span>H {bbH.toFixed(1)}</span>
          </div>
        </div>

        {/* EMA Stack */}
        <div style={subStyle}>
          <div style={labelStyle}>EMA Alignment</div>
          <div style={{ marginBottom: 8 }}>
            <span className="esfu-badge" style={{ background: `${emaColor}22`, color: emaColor, fontSize: '0.75rem', fontWeight: 700 }}>{emaAlign}</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
            {[
              { label: 'Fast (9)', val: ef, above: price > ef },
              { label: 'Mid (21)', val: em, above: price > em },
              { label: 'Slow (50)', val: es, above: price > es },
            ].map(({ label, val, above }) => (
              <div key={label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: '0.67rem', color: '#777' }}>{label}</span>
                <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                  <span style={{ fontSize: '0.67rem', color: above ? '#2ecc71' : '#e74c3c' }}>{above ? '▲' : '▼'}</span>
                  <span style={{ fontSize: '0.72rem', color: '#ccc' }}>{val > 0 ? val.toFixed(2) : '--'}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Magnetic MA */}
        {analysis.magnetic_ma?.best && (() => {
          const mag = analysis.magnetic_ma!.best!;
          const distColor = Math.abs(mag.current_distance_atr) < 0.5 ? '#2ecc71' : Math.abs(mag.current_distance_atr) < 1.5 ? '#f1c40f' : '#e74c3c';
          return (
            <div style={{ ...subStyle, gridColumn: 'span 2' }}>
              <div style={labelStyle}>Magnetic MA (Mean-Reversion Target)</div>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 8 }}>
                <span style={{ ...valueStyle, color: '#ff6b6b' }}>{mag.type} {mag.period}</span>
                <span style={{ fontSize: '0.85rem', color: '#ccc' }}>{mag.current_value.toFixed(2)}</span>
                <span className="esfu-badge" style={{ background: `${distColor}22`, color: distColor, fontSize: '0.7rem', marginLeft: 'auto' }}>
                  {mag.current_distance_atr > 0 ? '+' : ''}{mag.current_distance_atr.toFixed(2)} ATR
                </span>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
                <div>
                  <div style={{ fontSize: '0.64rem', color: '#666' }}>Reversion Rate</div>
                  <div style={{ fontSize: '0.85rem', fontWeight: 700, color: mag.reversion_rate >= 60 ? '#2ecc71' : '#f1c40f' }}>
                    {mag.reversion_rate.toFixed(1)}%
                  </div>
                </div>
                <div>
                  <div style={{ fontSize: '0.64rem', color: '#666' }}>Avg Bars</div>
                  <div style={{ fontSize: '0.85rem', fontWeight: 700, color: '#ccc' }}>{mag.avg_reversion_bars.toFixed(1)}</div>
                </div>
                <div>
                  <div style={{ fontSize: '0.64rem', color: '#666' }}>Mag Score</div>
                  <div style={{ fontSize: '0.85rem', fontWeight: 700, color: '#ff6b6b' }}>{mag.magnetic_score.toFixed(1)}</div>
                </div>
              </div>
            </div>
          );
        })()}

        {/* VWATR S/R Zones */}
        {analysis.vwatr_zones && analysis.vwatr_zones.length > 0 && (
          <div style={{ ...subStyle, gridColumn: 'span 2' }}>
            <div style={labelStyle}>VWATR S/R Zones</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {analysis.vwatr_zones.slice(0, 3).map((zone, i) => {
                const isSup = zone.zone_type === 'SUPPORT';
                const zColor = isSup ? '#2ecc71' : '#e74c3c';
                const inZone = zone.distance_atr <= 0;
                return (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 6px', borderRadius: 4, background: inZone ? `${zColor}15` : 'transparent' }}>
                    <span style={{ fontSize: '0.7rem', fontWeight: 700, color: zColor, minWidth: 20 }}>
                      {isSup ? 'S' : 'R'}{i + 1}
                    </span>
                    <span style={{ fontSize: '0.72rem', color: '#ccc', minWidth: 70 }}>
                      {zone.ma_type}{zone.ma_period}
                    </span>
                    <span style={{ fontSize: '0.78rem', fontWeight: 600, color: '#e0e0e0' }}>
                      {zone.ma_value.toFixed(2)}
                    </span>
                    <div style={{ flex: 1, height: 5, background: 'rgba(255,255,255,0.08)', borderRadius: 3, overflow: 'hidden', maxWidth: 60 }}>
                      <div style={{ width: `${Math.min(zone.strength, 100)}%`, height: '100%', background: zColor, borderRadius: 3 }} />
                    </div>
                    <span style={{ fontSize: '0.65rem', color: '#888', minWidth: 28, textAlign: 'right' }}>
                      {zone.strength.toFixed(0)}
                    </span>
                    <span style={{ fontSize: '0.65rem', color: zone.distance_atr <= 0 ? zColor : '#666', minWidth: 50, textAlign: 'right' }}>
                      {zone.distance_atr > 0 ? '+' : ''}{zone.distance_atr.toFixed(2)} ATR
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        )}

      </div>
    </div>
  );
}

// ══════════════════════════════════════════
// Volume Profile Chart
// ══════════════════════════════════════════

function VolumeProfileChart({ vp, currentPrice }: { vp: VolumeProfileData; currentPrice: number }) {
  const maxVol = Math.max(...vp.nodes.map(n => n.volume), 1);
  const sortedNodes = [...vp.nodes].sort((a, b) => b.price - a.price);

  return (
    <div className="esfu-panel" style={{ maxHeight: 420, overflowY: 'auto' }}>
      <h3 className="esfu-panel-title">Volume Profile</h3>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
        {sortedNodes.map((node, i) => {
          const pct = (node.volume / maxVol) * 100;
          const isPOC = Math.abs(node.price - vp.poc) < 0.5;
          const isVAH = Math.abs(node.price - vp.vah) < 0.5;
          const isVAL = Math.abs(node.price - vp.val) < 0.5;
          const isCurrent = Math.abs(node.price - currentPrice) < 1;
          const isLVN = vp.lvn_levels.some(l => Math.abs(node.price - l) < 0.5);

          let barColor = 'rgba(52,152,219,0.5)';
          if (isPOC) barColor = 'rgba(52,152,219,0.9)';
          else if (isLVN) barColor = 'rgba(241,196,15,0.7)';

          return (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6, minHeight: 16 }}>
              <span style={{ fontSize: '0.7rem', color: isCurrent ? '#f1c40f' : '#aaa', fontWeight: isCurrent ? 700 : 400, minWidth: 80, textAlign: 'right', whiteSpace: 'nowrap' }}>
                {node.price.toFixed(1)}
                {isPOC && <span style={{ fontSize: '0.55rem', padding: '0 3px', borderRadius: 2, marginLeft: 3, fontWeight: 600, background: 'rgba(52,152,219,0.3)', color: '#3498db' }}>POC</span>}
                {isVAH && <span style={{ fontSize: '0.55rem', padding: '0 3px', borderRadius: 2, marginLeft: 3, fontWeight: 600, background: 'rgba(46,204,113,0.2)', color: '#2ecc71' }}>VAH</span>}
                {isVAL && <span style={{ fontSize: '0.55rem', padding: '0 3px', borderRadius: 2, marginLeft: 3, fontWeight: 600, background: 'rgba(231,76,60,0.2)', color: '#e74c3c' }}>VAL</span>}
                {isCurrent && <span style={{ fontSize: '0.55rem', padding: '0 3px', borderRadius: 2, marginLeft: 3, fontWeight: 600, background: 'rgba(241,196,15,0.3)', color: '#f1c40f' }}>NOW</span>}
              </span>
              <div style={{ flex: 1, height: 10, background: 'rgba(255,255,255,0.03)', borderRadius: 3, overflow: 'hidden' }}>
                <div style={{ height: '100%', width: `${pct}%`, background: barColor, borderRadius: 3, transition: 'width 0.2s' }} />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ══════════════════════════════════════════
// Session Panel
// ══════════════════════════════════════════

function SessionPanel({ session, isMicro, onToggle }: {
  session: ESFSessionStatus; isMicro: boolean; onToggle: () => void;
}) {
  return (
    <div className="esfu-panel">
      <h3 className="esfu-panel-title">Session Status</h3>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 14 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: '0.78rem', color: '#888' }}>Status</span>
          <span className="esfu-badge" style={{
            background: session.is_rth ? 'rgba(46,204,113,0.2)' : 'rgba(231,76,60,0.2)',
            color: session.is_rth ? '#2ecc71' : '#e74c3c',
          }}>
            {session.is_rth ? 'RTH Active' : 'RTH Closed'}
          </span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: '0.78rem', color: '#888' }}>Session</span>
          <span style={{ fontSize: '0.85rem' }}>{session.session}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: '0.78rem', color: '#888' }}>Time (ET)</span>
          <span style={{ fontSize: '0.85rem' }}>{session.current_time_et}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: '0.78rem', color: '#888' }}>RTH Window</span>
          <span style={{ fontSize: '0.85rem' }}>{session.rth_start} - {session.rth_end}</span>
        </div>
      </div>

      <div className="esfu-toggle-row" style={{ justifyContent: 'center', margin: '14px 0' }}>
        <span className={!isMicro ? 'esfu-toggle-active' : ''}>ES</span>
        <button className="esfu-toggle-switch" onClick={onToggle}>
          <div className={`esfu-toggle-thumb ${isMicro ? 'on' : ''}`} />
        </button>
        <span className={isMicro ? 'esfu-toggle-active' : ''}>MES</span>
      </div>

      <div className="esfu-specs-mini">
        <div><span style={{ fontSize: '0.78rem', color: '#888', marginRight: 4 }}>Ticker</span> {isMicro ? 'MES=F' : 'ES=F'}</div>
        <div><span style={{ fontSize: '0.78rem', color: '#888', marginRight: 4 }}>Multiplier</span> ${isMicro ? '5' : '50'}/pt</div>
        <div><span style={{ fontSize: '0.78rem', color: '#888', marginRight: 4 }}>Tick</span> 0.25 pts = ${isMicro ? '1.25' : '12.50'}</div>
        <div><span style={{ fontSize: '0.78rem', color: '#888', marginRight: 4 }}>Margin</span> ~${isMicro ? '1,500' : '15,000'}</div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════
// Metric Card
// ══════════════════════════════════════════

function MetricCard({ label, value, colorize }: { label: string; value: string; colorize?: boolean }) {
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

// ══════════════════════════════════════════
// Scalp Decision Engine Gauge Components
// (reused from FuturesTrading.tsx)
// ══════════════════════════════════════════

function ScalpNIn({ label, value, onChange, unit, step = 1, min, help, highlight }: {
  label: string; value: number; onChange: (v: number) => void; unit?: string;
  step?: number; min?: number; help?: string; highlight?: boolean;
}) {
  return (
    <div className="scalp-input-group">
      <label className={`scalp-input-label ${highlight ? 'auto' : ''}`}>
        {label} {highlight && <span style={{ fontSize: '0.5rem', color: '#00e676' }}>AUTO</span>}
      </label>
      <div className="scalp-input-row">
        <input type="number" value={value} step={step} min={min}
          onChange={e => onChange(parseFloat(e.target.value) || 0)} />
        {unit && <span className="scalp-input-unit">{unit}</span>}
      </div>
      {help && <span className="scalp-input-help">{help}</span>}
    </div>
  );
}

function ZBar({ z }: { z: number }) {
  const pct = clamp((z + 4) / 8 * 100, 2, 98);
  const col = z < -2 ? '#00e676' : z > 2 ? '#ff1744' : z < -1 ? '#69f0ae' : z > 1 ? '#ff8a80' : '#78909c';
  return (
    <div className="scalp-zbar">
      <div className="scalp-zbar-track">
        <div className="scalp-zbar-zone-left" />
        <div className="scalp-zbar-zone-right" />
        {[12.5, 25, 37.5, 50, 62.5, 75, 87.5].map((p, i) => (
          <div key={i} style={{ position: 'absolute', left: `${p}%`, top: 0, bottom: 0, width: 1, background: 'var(--border-color, #333)' }} />
        ))}
        <div className="scalp-zbar-dot" style={{ left: `${pct}%`, background: col, boxShadow: `0 0 12px ${col}90` }} />
      </div>
      <div className="scalp-zbar-labels">
        <span>-4</span><span>-2</span><span>0</span><span>+2</span><span>+4</span>
      </div>
    </div>
  );
}

function EVBar({ gross, net }: { gross: number; net: number }) {
  const max = 8;
  const nP = clamp(net / max * 50, -50, 50);
  return (
    <div style={{ marginTop: 10 }}>
      <div className="scalp-evbar-meta">
        <span>Gross: <span style={{ color: gross >= 0 ? '#00e676' : '#ff1744' }}>{fmt(gross)}t</span></span>
        <span>Friction: <span style={{ color: '#ffab40' }}>-{fmt(gross - net)}t</span></span>
        <span>Net: <span style={{ color: net >= 0 ? '#00e676' : '#ff1744', fontWeight: 700 }}>{fmt(net)}t</span></span>
      </div>
      <div className="scalp-evbar-track">
        <div className="scalp-evbar-center" />
        <div className="scalp-evbar-fill" style={{
          left: nP >= 0 ? '50%' : `${50 + nP}%`,
          width: `${Math.abs(nP)}%`,
          background: nP >= 0 ? '#00e676' : '#ff1744',
        }} />
      </div>
    </div>
  );
}

function KGauge({ hk, conv }: { hk: number; conv: string }) {
  const pct = clamp(hk * 100 / 25, 0, 100);
  const col = conv === 'NO EDGE' ? '#ff1744' : (conv === 'VERY LOW' || conv === 'LOW') ? '#ffab40' : conv === 'MODERATE' ? '#fdd835' : '#00e676';
  return (
    <>
      <div className="scalp-kgauge-track">
        <div className="scalp-kgauge-fill" style={{ width: `${pct}%`, background: `linear-gradient(90deg, ${col}50, ${col})` }} />
      </div>
      <div className="scalp-kgauge-labels">
        <span>0%</span>
        <span className="scalp-pill" style={{ background: `${col}15`, border: `1px solid ${col}35`, color: col }}>{conv}</span>
        <span>25%</span>
      </div>
    </>
  );
}

function RRVis({ entry, sl, tp15, tp2, tp3, cfg, currentPrice, magneticMA, vwatrZone }: {
  entry: number; sl: number; tp15: number; tp2: number; tp3: number;
  cfg: { ptVal: number }; currentPrice?: number; magneticMA?: number;
  vwatrZone?: { ma_value: number; zone_type: string; ma_type: string; ma_period: number; strength: number } | null;
}) {
  const all = [sl, entry, tp15, tp2, tp3];
  if (currentPrice) all.push(currentPrice);
  if (magneticMA) all.push(magneticMA);
  if (vwatrZone) all.push(vwatrZone.ma_value);
  const lo = Math.min(...all), hi = Math.max(...all), rng = hi - lo || 1, pad = rng * 0.32;
  const H = 320, W = 420, LM = 60, RM = 110, TM = 28, BM = 32;
  const MONO = "'IBM Plex Mono', monospace";
  const toY = (p: number) => clamp(TM + ((hi + pad - p) / (rng + pad * 2)) * (H - TM - BM), TM, H - BM);

  // ── Label deconfliction: push items apart vertically to avoid overlap ──
  type LabelItem = { origY: number; idx: number; color: string };
  const deconflict = (items: LabelItem[], minGap: number): Map<number, number> => {
    const s = items.map(it => ({ ...it, labelY: it.origY })).sort((a, b) => a.origY - b.origY);
    for (let i = 1; i < s.length; i++)
      if (s[i].labelY - s[i - 1].labelY < minGap) s[i].labelY = s[i - 1].labelY + minGap;
    for (let i = s.length - 2; i >= 0; i--)
      if (s[i + 1].labelY - s[i].labelY < minGap) s[i].labelY = s[i + 1].labelY - minGap;
    s.forEach(x => { x.labelY = Math.max(TM + 2, Math.min(H - BM - 2, x.labelY)); });
    return new Map(s.map(x => [x.idx, x.labelY]));
  };

  // R:R ratio
  const risk = Math.abs(entry - sl);
  const reward = Math.abs(tp15 - entry);
  const rrRatio = risk > 0 ? (reward / risk).toFixed(1) : '—';
  const rr3 = risk > 0 ? (Math.abs(tp3 - entry) / risk).toFixed(1) : '—';

  // Grid lines
  const gridCount = 7;
  const gridLines = Array.from({ length: gridCount }, (_, i) => {
    const frac = i / (gridCount - 1);
    const price = hi + pad - frac * (rng + pad * 2);
    return { y: TM + frac * (H - TM - BM), price };
  });

  // Level definitions (idx 0-4)
  const isLong = tp15 > entry;
  const levels = [
    { p: sl,   lb: 'STOP',  tag: '1R',   c: '#ff1744', w: 1.5, dash: '6,4',  marker: 'x'      as const },
    { p: entry,lb: 'ENTRY', tag: '',     c: '#3b82f6', w: 2.5, dash: 'none', marker: 'arrow'   as const },
    { p: tp15, lb: '1.5R',  tag: '1.5R', c: '#69f0ae', w: 1.2, dash: '4,3',  marker: 'none'    as const },
    { p: tp2,  lb: '2R',    tag: '2R',   c: '#00e676', w: 1.5, dash: '5,3',  marker: 'diamond' as const },
    { p: tp3,  lb: '3R',    tag: '3R',   c: '#10b981', w: 2,   dash: 'none', marker: 'dot'     as const },
  ];

  const pnl = (price: number) => {
    const pts = Math.abs(price - entry);
    return { pts, usd: pts * cfg.ptVal };
  };

  const entryY = toY(entry);
  const slY = toY(sl);
  const tp3Y = toY(tp3);
  const lossTop = Math.min(entryY, slY);
  const lossH = Math.abs(slY - entryY);
  const profTop = Math.min(entryY, tp3Y);
  const profH = Math.abs(tp3Y - entryY);
  const nowY = currentPrice ? toY(currentPrice) : null;

  // ── Build label position maps (left + right sides independently) ──
  // idx: 0-4 = levels, 100 = Mag MA, 101 = VWATR, 102 = NOW
  const leftItems: LabelItem[] = levels.map((l, i) => ({ origY: toY(l.p), idx: i, color: l.c }));
  if (magneticMA && magneticMA > 0) leftItems.push({ origY: toY(magneticMA), idx: 100, color: '#ff6b6b' });
  if (vwatrZone?.ma_value > 0) {
    leftItems.push({ origY: toY(vwatrZone.ma_value), idx: 101, color: vwatrZone.zone_type === 'SUPPORT' ? '#22c55e' : '#ef4444' });
  }
  if (nowY != null) leftItems.push({ origY: nowY, idx: 102, color: 'rgba(255,255,255,0.6)' });
  const leftMap = deconflict(leftItems, 14);

  const rightItems: LabelItem[] = levels.map((l, i) => ({ origY: toY(l.p), idx: i, color: l.c }));
  if (magneticMA && magneticMA > 0) rightItems.push({ origY: toY(magneticMA), idx: 100, color: '#ff6b6b' });
  if (vwatrZone?.ma_value > 0) {
    rightItems.push({ origY: toY(vwatrZone.ma_value), idx: 101, color: vwatrZone.zone_type === 'SUPPORT' ? '#22c55e' : '#ef4444' });
  }
  const rightMap = deconflict(rightItems, 20);

  return (
    <div className="scalp-rr-map">
      <svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`} style={{ display: 'block' }}>
        <defs>
          <linearGradient id="rr-loss-grad" x1="0" y1={isLong ? '0' : '1'} x2="0" y2={isLong ? '1' : '0'}>
            <stop offset="0%" stopColor="rgba(255,23,68,0.04)" />
            <stop offset="100%" stopColor="rgba(255,23,68,0.18)" />
          </linearGradient>
          <linearGradient id="rr-prof-grad" x1="0" y1={isLong ? '1' : '0'} x2="0" y2={isLong ? '0' : '1'}>
            <stop offset="0%" stopColor="rgba(0,230,118,0.04)" />
            <stop offset="100%" stopColor="rgba(0,230,118,0.16)" />
          </linearGradient>
          <filter id="rr-entry-glow">
            <feDropShadow dx="0" dy="0" stdDeviation="2.5" floodColor="#3b82f6" floodOpacity="0.5" />
          </filter>
        </defs>

        {/* ── Title bar ── */}
        <text x={LM} y={14} fill="rgba(255,255,255,0.35)" fontSize="8" fontFamily={MONO}
          fontWeight="600" letterSpacing="0.08em">ATR STOP & R:R MAP</text>
        <text x={W - RM} y={14} textAnchor="end" fill="#3b82f6" fontSize="9.5" fontFamily={MONO} fontWeight="700">
          R:R 1:{rrRatio}
        </text>
        <text x={W - RM + 50} y={14} textAnchor="end" fill="rgba(0,230,118,0.5)" fontSize="7.5" fontFamily={MONO}>
          (max 1:{rr3})
        </text>

        {/* ── Background grid ── */}
        {gridLines.map((g, i) => (
          <g key={`grid-${i}`}>
            <line x1={LM} y1={g.y} x2={W - RM} y2={g.y} stroke="rgba(255,255,255,0.04)" strokeWidth="0.5" />
            <line x1={LM - 3} y1={g.y} x2={LM} y2={g.y} stroke="rgba(255,255,255,0.12)" strokeWidth="1" />
            <text x={LM - 5} y={g.y + 3} textAnchor="end" fill="rgba(255,255,255,0.2)" fontSize="7" fontFamily={MONO}>{g.price.toFixed(0)}</text>
          </g>
        ))}

        {/* ── Axes ── */}
        <line x1={LM} y1={TM} x2={LM} y2={H - BM} stroke="rgba(255,255,255,0.1)" strokeWidth="1" />
        <line x1={LM} y1={H - BM} x2={W - RM} y2={H - BM} stroke="rgba(255,255,255,0.06)" strokeWidth="1" />

        {/* ── Zone fills ── */}
        <rect x={LM} y={lossTop} width={W - LM - RM} height={lossH} fill="url(#rr-loss-grad)" rx="2" />
        <rect x={LM} y={profTop} width={W - LM - RM} height={profH} fill="url(#rr-prof-grad)" rx="2" />

        {/* ── Current price marker (NOW) ── */}
        {nowY != null && (() => {
          const lY = leftMap.get(102) ?? nowY;
          return (
            <g>
              <line x1={LM} y1={nowY} x2={W - RM} y2={nowY}
                stroke="rgba(255,255,255,0.45)" strokeWidth="1" strokeDasharray="2,3" />
              <polygon points={`${LM - 1},${nowY - 4} ${LM - 1},${nowY + 4} ${LM + 5},${nowY}`}
                fill="rgba(255,255,255,0.7)" />
              {Math.abs(lY - nowY) > 1 && (
                <line x1={LM - 5} y1={nowY} x2={LM - 7} y2={lY}
                  stroke="rgba(255,255,255,0.25)" strokeWidth="0.7" />
              )}
              <text x={LM - 9} y={lY + 3.5} textAnchor="end" fill="rgba(255,255,255,0.6)"
                fontSize="8" fontFamily={MONO} fontWeight="600">NOW</text>
            </g>
          );
        })()}

        {/* ── Magnetic MA target ── */}
        {magneticMA != null && magneticMA > 0 && (() => {
          const maY = toY(magneticMA);
          const maAbove = magneticMA > entry;
          const lY = leftMap.get(100) ?? maY;
          const rY = rightMap.get(100) ?? maY;
          return (
            <g>
              <line x1={LM} y1={maY} x2={W - RM} y2={maY}
                stroke="#ff6b6b" strokeWidth="1.5" strokeDasharray="6,3" opacity="0.8" />
              {Math.abs(lY - maY) > 1 && (
                <line x1={LM - 5} y1={maY} x2={LM - 7} y2={lY}
                  stroke="#ff6b6b" strokeWidth="0.6" opacity="0.35" />
              )}
              <text x={LM - 9} y={lY + 3.5} textAnchor="end" fill="#ff6b6b"
                fontSize="8" fontFamily={MONO} fontWeight="600">MAG</text>
              {Math.abs(rY - maY) > 1 && (
                <line x1={W - RM + 1} y1={maY} x2={W - RM + 3} y2={rY}
                  stroke="#ff6b6b" strokeWidth="0.6" opacity="0.35" />
              )}
              <text x={W - RM + 4} y={rY + 3.5} textAnchor="start" fill="#ff6b6b"
                fontSize="8.5" fontFamily={MONO} fontWeight="600">{fmt(magneticMA, 2)}</text>
              <polygon
                points={maAbove
                  ? `${LM + 4},${maY + 7} ${LM + 8},${maY + 3} ${LM + 4},${maY + 3}`
                  : `${LM + 4},${maY - 7} ${LM + 8},${maY - 3} ${LM + 4},${maY - 3}`}
                fill="#ff6b6b" opacity="0.6" />
            </g>
          );
        })()}

        {/* ── VWATR S/R Zone ── */}
        {vwatrZone && vwatrZone.ma_value > 0 && (() => {
          const zy = toY(vwatrZone.ma_value);
          const isSup = vwatrZone.zone_type === 'SUPPORT';
          const zColor = isSup ? '#22c55e' : '#ef4444';
          const lY = leftMap.get(101) ?? zy;
          const rY = rightMap.get(101) ?? zy;
          return (
            <g>
              <line x1={LM} y1={zy} x2={W - RM} y2={zy}
                stroke={zColor} strokeWidth="1.3" strokeDasharray="4,3" opacity="0.75" />
              {Math.abs(lY - zy) > 1 && (
                <line x1={LM - 5} y1={zy} x2={LM - 7} y2={lY}
                  stroke={zColor} strokeWidth="0.6" opacity="0.35" />
              )}
              <text x={LM - 9} y={lY + 3.5} textAnchor="end" fill={zColor}
                fontSize="8" fontFamily={MONO} fontWeight="600">{isSup ? 'S' : 'R'}</text>
              {Math.abs(rY - zy) > 1 && (
                <line x1={W - RM + 1} y1={zy} x2={W - RM + 3} y2={rY}
                  stroke={zColor} strokeWidth="0.6" opacity="0.35" />
              )}
              <text x={W - RM + 4} y={rY + 3.5} textAnchor="start" fill={zColor}
                fontSize="8" fontFamily={MONO} fontWeight="600">
                {fmt(vwatrZone.ma_value, 2)}
              </text>
            </g>
          );
        })()}

        {/* ── Level lines + deconflicted labels ── */}
        {levels.map((l, i) => {
          const y = toY(l.p);
          const { pts, usd } = pnl(l.p);
          const isSL = l.lb === 'STOP';
          const isEntry = l.lb === 'ENTRY';
          const pnlLabel = isEntry ? '' : `${isSL ? '-' : '+'}${fmt(pts, 1)}p / ${isSL ? '-' : '+'}$${usd.toFixed(0)}`;
          const lY = leftMap.get(i) ?? y;
          const rY = rightMap.get(i) ?? y;
          return (
            <g key={i}>
              {/* Horizontal price line */}
              <line x1={LM} y1={y} x2={W - RM} y2={y}
                stroke={l.c} strokeWidth={l.w} strokeDasharray={l.dash}
                opacity={isEntry ? 1 : 0.85}
                filter={isEntry ? 'url(#rr-entry-glow)' : undefined} />

              {/* Left leader line (connects price level to offset label) */}
              {Math.abs(lY - y) > 1 && (
                <line x1={LM - 5} y1={y} x2={LM - 7} y2={lY}
                  stroke={l.c} strokeWidth="0.6" opacity="0.35" />
              )}
              {/* Left label */}
              <text x={LM - 9} y={lY + 3.5} textAnchor="end" fill={l.c}
                fontSize={isEntry ? '9.5' : '8'} fontFamily={MONO}
                fontWeight={isEntry ? 700 : 600}>{l.lb}</text>

              {/* R-multiple badge (right side) */}
              {l.tag && !isEntry && (
                <g>
                  <rect x={W - RM + 74} y={rY - 7} width={30} height={14} rx="3"
                    fill={isSL ? 'rgba(255,23,68,0.15)' : 'rgba(0,230,118,0.12)'}
                    stroke={isSL ? 'rgba(255,23,68,0.3)' : 'rgba(0,230,118,0.25)'} strokeWidth="0.5" />
                  <text x={W - RM + 89} y={rY + 3.5} textAnchor="middle"
                    fill={isSL ? '#ff5252' : l.c} fontSize="7.5" fontFamily={MONO} fontWeight="700">
                    {l.tag}
                  </text>
                </g>
              )}

              {/* Right leader line */}
              {Math.abs(rY - y) > 1 && (
                <line x1={W - RM + 1} y1={y} x2={W - RM + 3} y2={rY}
                  stroke={l.c} strokeWidth="0.6" opacity="0.35" />
              )}
              {/* Right price */}
              <text x={W - RM + 4} y={rY + 3.5} textAnchor="start" fill={l.c}
                fontSize="8.5" fontFamily={MONO} fontWeight={600}>
                {fmt(l.p, 2)}
              </text>
              {/* P&L (stacked below price) */}
              {pnlLabel && (
                <text x={W - RM + 4} y={rY + 13} textAnchor="start"
                  fill={isSL ? 'rgba(255,82,82,0.6)' : 'rgba(0,230,118,0.6)'}
                  fontSize="6.5" fontFamily={MONO}>
                  {pnlLabel}
                </text>
              )}

              {/* Markers */}
              {l.marker === 'arrow' && (
                <polygon points={`${LM + 2},${y - 5} ${LM + 2},${y + 5} ${LM + 9},${y}`}
                  fill={l.c} opacity="0.9" />
              )}
              {l.marker === 'x' && (
                <g stroke={l.c} strokeWidth="1.8" opacity="0.75">
                  <line x1={LM + 3} y1={y - 3.5} x2={LM + 9.5} y2={y + 3.5} />
                  <line x1={LM + 9.5} y1={y - 3.5} x2={LM + 3} y2={y + 3.5} />
                </g>
              )}
              {l.marker === 'diamond' && (
                <polygon points={`${LM + 6},${y - 3.5} ${LM + 9.5},${y} ${LM + 6},${y + 3.5} ${LM + 2.5},${y}`}
                  fill={l.c} opacity="0.6" />
              )}
              {l.marker === 'dot' && (
                <circle cx={LM + 6} cy={y} r="3.5" fill={l.c} opacity="0.7" />
              )}
            </g>
          );
        })}

        {/* ── Zone labels ── */}
        <text x={LM + 6} y={lossTop + lossH / 2 + 3} fill="rgba(255,23,68,0.28)" fontSize="9"
          fontFamily={MONO} fontWeight="700" letterSpacing="0.08em">RISK ZONE</text>
        <text x={LM + 6} y={profTop + profH / 2 + 3} fill="rgba(0,230,118,0.28)" fontSize="9"
          fontFamily={MONO} fontWeight="700" letterSpacing="0.08em">REWARD ZONE</text>

        {/* ── Legend ── */}
        <g transform={`translate(${LM}, ${H - 12})`}>
          <polygon points="0,-3 0,3 5,0" fill="#3b82f6" opacity="0.7" />
          <text x="8" y="3" fill="rgba(255,255,255,0.3)" fontSize="6.5" fontFamily={MONO}>ENTRY</text>
          <g transform="translate(52,0)">
            <line x1="0" y1="-2" x2="5" y2="2" stroke="#ff1744" strokeWidth="1.2" opacity="0.7" />
            <line x1="5" y1="-2" x2="0" y2="2" stroke="#ff1744" strokeWidth="1.2" opacity="0.7" />
            <text x="8" y="3" fill="rgba(255,255,255,0.3)" fontSize="6.5" fontFamily={MONO}>STOP</text>
          </g>
          <g transform="translate(98,0)">
            <circle cx="2.5" cy="0" r="2.5" fill="#00e676" opacity="0.7" />
            <text x="8" y="3" fill="rgba(255,255,255,0.3)" fontSize="6.5" fontFamily={MONO}>TARGET</text>
          </g>
          <g transform="translate(152,0)">
            <polygon points="0,-3 3,0 0,3 -3,0" fill="rgba(255,255,255,0.5)" />
            <text x="6" y="3" fill="rgba(255,255,255,0.3)" fontSize="6.5" fontFamily={MONO}>NOW</text>
          </g>
          <g transform="translate(190,0)">
            <line x1="0" y1="0" x2="6" y2="0" stroke="#ff6b6b" strokeWidth="1.5" strokeDasharray="2,1" />
            <text x="9" y="3" fill="rgba(255,255,255,0.3)" fontSize="6.5" fontFamily={MONO}>MAG MA</text>
          </g>
          <g transform="translate(245,0)">
            <line x1="0" y1="0" x2="6" y2="0" stroke="#22c55e" strokeWidth="1.2" strokeDasharray="2,2" />
            <text x="9" y="3" fill="rgba(255,255,255,0.3)" fontSize="6.5" fontFamily={MONO}>VWATR</text>
          </g>
        </g>
      </svg>
    </div>
  );
}

function BasisBar({ basis }: { basis: number }) {
  const bP = clamp((basis + 20) / 40 * 100, 2, 98);
  const bC = basis > 2 ? '#4fc3f7' : basis < -2 ? '#ffab40' : '#78909c';
  return (
    <>
      <div className="scalp-basis-track">
        <div className="scalp-basis-center" />
        <div className="scalp-basis-dot" style={{ left: `${bP}%`, background: bC, boxShadow: `0 0 10px ${bC}80` }} />
      </div>
      <div className="scalp-basis-labels">
        <span>BACKWARDATION</span><span>FAIR</span><span>CONTANGO</span>
      </div>
    </>
  );
}

// ══════════════════════════════════════════
// Strategy Dashboard
// ══════════════════════════════════════════

function StrategyDashboard({ regime, candles }: {
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

function ScalpDecisionEngine({ scalp, magneticMA, vwatrZone }: { scalp: ScalpState; magneticMA?: number; vwatrZone?: VWATRZone | null }) {
  const { dataMode, setDataMode, closeText, setCloseText, ohlcText, setOhlcText,
    maPeriod, setMaPeriod, closesCount, candlesCount, autoStats, inputs,
    setInput, setAsset, calc } = scalp;

  const vc = calc.verdict === 'GO' ? 'go' : calc.verdict === 'CAUTION' ? 'caution' : 'no-entry';

  return (
    <div className="scalp-section">
      <div className="scalp-section-header">
        <div style={{ width: 34, height: 34, borderRadius: 8, background: 'linear-gradient(135deg, #3b82f6, #1d4ed8)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 17, fontWeight: 900, color: '#fff', fontFamily: "'IBM Plex Mono', monospace" }}>S</div>
        <div>
          <h2>Scalp Decision Engine</h2>
          <span className="scalp-subtitle">PROBABILITY-BASED FUTURES ANALYSIS v1.2</span>
        </div>
        <div className="scalp-asset-picker">
          {Object.entries(ASSETS).map(([k, v]) => (
            <button key={k} onClick={() => setAsset(k as 'ES' | 'MES')}
              className={`scalp-asset-btn ${inputs.asset === k ? 'active' : ''}`}>
              {k}<span className="tick-info">${v.tickVal}/t</span>
            </button>
          ))}
        </div>
      </div>

      <div className={`scalp-verdict-strip ${vc}`}>
        {calc.verdict === 'GO' ? 'GO' : calc.verdict === 'CAUTION' ? 'CAUTION' : 'NO ENTRY'} — [{calc.passN}/4] — {calc.zSignal} — {calc.isLong ? 'LONG' : 'SHORT'}
        {autoStats && <span style={{ opacity: 0.5 }}> — ATR: {autoStats.atrMethod}</span>}
      </div>

      <div className="scalp-layout">
        {/* LEFT: INPUTS */}
        <div className="scalp-sidebar">
          <div className="scalp-box" style={{ borderColor: dataMode !== 'manual' ? 'rgba(59,130,246,0.4)' : undefined }}>
            <div className="scalp-box-header">
              <span className="icon">Price Data</span>
              <span className="scalp-pill" style={{
                background: dataMode !== 'manual' ? 'rgba(0,230,118,0.1)' : 'rgba(255,255,255,0.05)',
                border: `1px solid ${dataMode !== 'manual' ? 'rgba(0,230,118,0.3)' : 'rgba(255,255,255,0.1)'}`,
                color: dataMode !== 'manual' ? '#00e676' : '#888',
              }}>{dataMode === 'ohlc' ? 'OHLC' : dataMode === 'close' ? 'CLOSE' : 'MANUAL'}</span>
            </div>

            <div className="scalp-mode-toggle">
              {([
                { key: 'ohlc' as DataMode, label: 'OHLC', desc: 'True ATR' },
                { key: 'close' as DataMode, label: 'Close', desc: 'Approx' },
                { key: 'manual' as DataMode, label: 'Manual', desc: 'Direct' },
              ]).map(m => (
                <button key={m.key} onClick={() => setDataMode(m.key)}
                  className={`scalp-mode-btn ${dataMode === m.key ? 'active' : ''}`}>
                  <span>{m.label}</span>
                  <span className="mode-desc">{m.desc}</span>
                </button>
              ))}
            </div>

            {dataMode === 'ohlc' && (
              <>
                <label className="scalp-input-label">OHLC DATA (O, H, L, C per line)</label>
                <textarea className="scalp-textarea" value={ohlcText} onChange={e => setOhlcText(e.target.value)}
                  placeholder="5870.00, 5878.50, 5868.25, 5872.50" rows={5} />
                <div className="scalp-data-meta">
                  <span className={`scalp-data-count ${candlesCount >= 3 ? 'valid' : 'invalid'}`}>
                    {candlesCount} candles {candlesCount < 3 && '(min 3)'}
                  </span>
                  <button className="scalp-sample-btn" onClick={() => setOhlcText(SAMPLE_OHLC)}>Sample</button>
                </div>
              </>
            )}

            {dataMode === 'close' && (
              <>
                <label className="scalp-input-label">CLOSE PRICES (comma/newline)</label>
                <textarea className="scalp-textarea" value={closeText} onChange={e => setCloseText(e.target.value)}
                  placeholder="5880.50, 5885.25, 5890.00 ..." rows={4} />
                <div className="scalp-data-meta">
                  <span className={`scalp-data-count ${closesCount >= 3 ? 'valid' : 'invalid'}`}>
                    {closesCount} prices {closesCount < 3 && '(min 3)'}
                  </span>
                  <button className="scalp-sample-btn" onClick={() => setCloseText(SAMPLE_CLOSE)}>Sample</button>
                </div>
              </>
            )}

            {dataMode === 'manual' && (
              <>
                <ScalpNIn label="Current Price" value={inputs.currentPrice} onChange={v => setInput('currentPrice')(v)} step={0.25} unit="pts" />
                <ScalpNIn label="MA (Moving Avg)" value={inputs.ma} onChange={v => setInput('ma')(v)} step={0.25} unit="pts" />
                <ScalpNIn label="Std Dev" value={inputs.stdDev} onChange={v => setInput('stdDev')(v)} step={0.5} unit="pts" />
                <ScalpNIn label="ATR" value={inputs.atr} onChange={v => setInput('atr')(v)} step={0.25} unit="pts" />
              </>
            )}

            {dataMode !== 'manual' && (
              <ScalpNIn label="MA Period" value={maPeriod} onChange={setMaPeriod} step={1} min={2} help="MA & StdDev calculation period" />
            )}

            {dataMode !== 'manual' && autoStats && (
              <div className="scalp-auto-stats">
                <div className="scalp-auto-stats-header">
                  Auto — {autoStats.atrMethod === 'TRUE-RANGE'
                    ? <span style={{ color: '#4fc3f7' }}>True Range ATR</span>
                    : <span style={{ color: '#ffab40' }}>Close-Proxy ATR</span>}
                </div>
                <div className="scalp-auto-stats-grid">
                  {[
                    { l: 'Price', v: fmt(autoStats.currentPrice, 2) },
                    { l: `MA(${autoStats.maPeriod})`, v: fmt(autoStats.ma, 2) },
                    { l: 'StdDev', v: fmt(autoStats.stdDev, 2) },
                    { l: 'ATR(14)', v: fmt(autoStats.atr, 2) },
                  ].map((item, i) => (
                    <div key={i}>
                      <div className="scalp-auto-stat-label">{item.l}</div>
                      <div className="scalp-auto-stat-value">{item.v}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <ScalpNIn label="ATR Mult (Stop)" value={inputs.atrMult} onChange={v => setInput('atrMult')(v)} step={0.1} min={0.1} help="Scalp: 0.5-1.0 / Swing: 1.5-2.0" />
          </div>

          <div className="scalp-box">
            <div className="scalp-box-header">
              <span className="title">Backtest Stats</span>
              <span className="scalp-pill" style={{ background: 'rgba(59,130,246,0.1)', border: '1px solid rgba(59,130,246,0.3)', color: '#3b82f6' }}>EV INPUT</span>
            </div>
            <ScalpNIn label="Win Rate" value={inputs.winRate} onChange={v => setInput('winRate')(v)} step={1} unit="%" />
            <ScalpNIn label="Avg Win" value={inputs.avgWin} onChange={v => setInput('avgWin')(v)} step={0.5} unit="ticks" />
            <ScalpNIn label="Avg Loss" value={inputs.avgLoss} onChange={v => setInput('avgLoss')(v)} step={0.5} unit="ticks" />
            <ScalpNIn label="Slippage" value={inputs.slippage} onChange={v => setInput('slippage')(v)} step={0.25} unit="ticks" />
            <ScalpNIn label="Commission" value={inputs.commission} onChange={v => setInput('commission')(v)} step={0.05} unit="$" />
          </div>

          <div className="scalp-box">
            <div className="scalp-box-header"><span className="title">Account</span></div>
            <ScalpNIn label="Balance" value={inputs.accountBalance} onChange={v => setInput('accountBalance')(v)} step={100} unit="$" />
            <ScalpNIn label="Risk Per Trade" value={inputs.riskPct} onChange={v => setInput('riskPct')(v)} step={0.5} min={0.1} unit="%" />
          </div>

          <div className="scalp-box">
            <div className="scalp-box-header"><span className="title">Basis Spread</span></div>
            <ScalpNIn label="Spot (SPX)" value={inputs.spotPrice} onChange={v => setInput('spotPrice')(v)} step={0.25} unit="pts" />
            <ScalpNIn label="Futures (ES)" value={inputs.futuresPrice} onChange={v => setInput('futuresPrice')(v)} step={0.25} unit="pts" />
          </div>
        </div>

        {/* RIGHT: OUTPUTS */}
        <div className="scalp-main">
          {/* Decision Matrix */}
          <div className="scalp-box" style={{ borderColor: calc.verdict === 'GO' ? 'rgba(0,230,118,0.3)' : calc.verdict === 'CAUTION' ? 'rgba(253,216,53,0.3)' : 'rgba(255,23,68,0.3)' }}>
            <div className="scalp-box-header">
              <span className="title">Decision Matrix</span>
              <span className="scalp-pill" style={{
                background: calc.verdict === 'GO' ? 'rgba(0,230,118,0.1)' : calc.verdict === 'CAUTION' ? 'rgba(253,216,53,0.1)' : 'rgba(255,23,68,0.1)',
                border: `1px solid ${calc.verdict === 'GO' ? 'rgba(0,230,118,0.3)' : calc.verdict === 'CAUTION' ? 'rgba(253,216,53,0.3)' : 'rgba(255,23,68,0.3)'}`,
                color: calc.verdict === 'GO' ? '#00e676' : calc.verdict === 'CAUTION' ? '#fdd835' : '#ff1744',
              }}>ENTRY CHECKLIST</span>
            </div>
            {calc.checks.map((c, i) => (
              <div key={i} className={`scalp-check-item ${c.pass ? 'pass' : 'fail'}`}>
                <span className={`scalp-check-icon ${c.pass ? 'pass' : 'fail'}`}>{c.pass ? 'Y' : 'N'}</span>
                <div style={{ flex: 1 }}>
                  <div className="scalp-check-label">{c.label}</div>
                  <div className="scalp-check-val">{c.val}</div>
                </div>
              </div>
            ))}
            <div className="scalp-verdict-box" style={{
              background: calc.verdict === 'GO' ? 'rgba(0,230,118,0.08)' : calc.verdict === 'CAUTION' ? 'rgba(253,216,53,0.08)' : 'rgba(255,23,68,0.08)',
              border: `1px solid ${calc.verdict === 'GO' ? 'rgba(0,230,118,0.3)' : calc.verdict === 'CAUTION' ? 'rgba(253,216,53,0.3)' : 'rgba(255,23,68,0.3)'}`,
              color: calc.verdict === 'GO' ? '#00e676' : calc.verdict === 'CAUTION' ? '#fdd835' : '#ff1744',
            }}>
              [{calc.passN}/4] {calc.verdict === 'GO' ? 'ALL CLEAR' : calc.verdict === 'CAUTION' ? 'CONDITIONAL' : 'WAIT'}
            </div>
          </div>

          {/* Z-Score Analysis */}
          <div className="scalp-box">
            <div className="scalp-box-header">
              <span className="title">Z-Score Analysis</span>
              <span className="scalp-pill" style={{ background: 'rgba(59,130,246,0.1)', border: '1px solid rgba(59,130,246,0.3)', color: '#3b82f6' }}>Statistical Position</span>
            </div>
            <div className="scalp-met-row">
              <div className="scalp-met big">
                <div className="scalp-met-label">Z-Score</div>
                <div className="scalp-met-value big" style={{ color: calc.zColor }}>{fmt(calc.z)}</div>
              </div>
              <div className="scalp-met">
                <div className="scalp-met-label">Signal</div>
                <div className="scalp-met-value" style={{ color: calc.zColor }}>{calc.zSignal}</div>
              </div>
              <div className="scalp-met">
                <div className="scalp-met-label">P-Value</div>
                <div className="scalp-met-value">{fmtPct(calc.pVal)}</div>
              </div>
              <div className="scalp-met">
                <div className="scalp-met-label">Deviation</div>
                <div className="scalp-met-value">{fmt(inputs.currentPrice - inputs.ma, 1)}p</div>
              </div>
            </div>
            <ZBar z={calc.z} />
          </div>

          {/* EV Engine */}
          <div className="scalp-box">
            <div className="scalp-box-header">
              <span className="title">Scalp EV Engine</span>
              <span className="scalp-pill" style={{
                background: calc.netEV >= 0 ? 'rgba(0,230,118,0.1)' : 'rgba(255,23,68,0.1)',
                border: `1px solid ${calc.netEV >= 0 ? 'rgba(0,230,118,0.3)' : 'rgba(255,23,68,0.3)'}`,
                color: calc.netEV >= 0 ? '#00e676' : '#ff1744',
              }}>Expected Value</span>
            </div>
            <div className="scalp-met-row">
              <div className="scalp-met big">
                <div className="scalp-met-label">Net EV/Trade</div>
                <div className="scalp-met-value big" style={{ color: calc.netEV >= 0 ? '#00e676' : '#ff1744' }}>
                  {calc.netEV >= 0 ? '+' : ''}{fmt(calc.netEV)}t
                </div>
                <div className="scalp-met-sub">{calc.netEV >= 0 ? '+' : '-'} {fmtUSD(Math.abs(calc.netEVusd))}</div>
              </div>
              <div className="scalp-met">
                <div className="scalp-met-label">Gross EV</div>
                <div className="scalp-met-value">{fmt(calc.grossEV)}t</div>
              </div>
              <div className="scalp-met">
                <div className="scalp-met-label">Friction</div>
                <div className="scalp-met-value" style={{ color: '#ffab40' }}>{fmt(calc.friction)}t</div>
              </div>
              <div className="scalp-met">
                <div className="scalp-met-label">R:R</div>
                <div className="scalp-met-value">{fmt(calc.b, 1)}:1</div>
              </div>
            </div>
            <EVBar gross={calc.grossEV} net={calc.netEV} />
          </div>

          {/* Kelly + Position Sizer */}
          <div className="scalp-side-panels">
            <div className="scalp-box">
              <div className="scalp-box-header">
                <span className="title">Kelly Criterion</span>
                <span className="scalp-pill" style={{
                  background: calc.kelly > 0 ? 'rgba(0,230,118,0.1)' : 'rgba(255,23,68,0.1)',
                  border: `1px solid ${calc.kelly > 0 ? 'rgba(0,230,118,0.3)' : 'rgba(255,23,68,0.3)'}`,
                  color: calc.kelly > 0 ? '#00e676' : '#ff1744',
                }}>Conviction</span>
              </div>
              <div className="scalp-met-row">
                <div className="scalp-met">
                  <div className="scalp-met-label">Full Kelly</div>
                  <div className="scalp-met-value">{fmtPct(calc.kelly)}</div>
                </div>
                <div className="scalp-met big">
                  <div className="scalp-met-label">Half Kelly</div>
                  <div className="scalp-met-value big" style={{ color: '#3b82f6' }}>{fmtPct(calc.halfKelly)}</div>
                  <div className="scalp-met-sub">recommended bet size</div>
                </div>
              </div>
              <KGauge hk={calc.halfKelly} conv={calc.conviction} />
            </div>

            <div className="scalp-box">
              <div className="scalp-box-header"><span className="title">Position Sizer</span></div>
              <div className="scalp-met-row">
                <div className="scalp-met">
                  <div className="scalp-met-label">Risk Budget</div>
                  <div className="scalp-met-value">{fmtUSD(calc.riskBudget)}</div>
                  <div className="scalp-met-sub">{inputs.riskPct}% of balance</div>
                </div>
                <div className="scalp-met">
                  <div className="scalp-met-label">Risk/Contract</div>
                  <div className="scalp-met-value">{fmtUSD(calc.riskPerContract)}</div>
                  <div className="scalp-met-sub">{fmt(calc.atrStop)}p x ${calc.cfg.ptVal}</div>
                </div>
              </div>
              <div className="scalp-contracts-display">
                <div className="scalp-contracts-label">Recommended Contracts</div>
                <div className="scalp-contracts-number">{calc.recContracts}</div>
                <div className="scalp-contracts-sub">max {calc.maxContracts} / scalp cap 2</div>
              </div>
            </div>
          </div>

          {/* ATR Stop & R:R Map */}
          <div className="scalp-box">
            <div className="scalp-box-header">
              <span className="title">ATR Stop & R:R Map</span>
              <span className="scalp-pill" style={{ background: 'rgba(59,130,246,0.1)', border: '1px solid rgba(59,130,246,0.3)', color: '#3b82f6' }}>ATR x{inputs.atrMult}</span>
            </div>
            <div className="scalp-met-row" style={{ marginBottom: 6 }}>
              <div className="scalp-met">
                <div className="scalp-met-label">ATR Stop</div>
                <div className="scalp-met-value" style={{ color: '#ff1744' }}>{fmt(calc.atrStop)}p</div>
                <div className="scalp-met-sub">{fmtUSD(calc.riskPerContract)}/ct</div>
              </div>
              <div className="scalp-met">
                <div className="scalp-met-label">Stop</div>
                <div className="scalp-met-value" style={{ color: '#ff1744' }}>{fmt(calc.sl, 2)}</div>
              </div>
              <div className="scalp-met">
                <div className="scalp-met-label">TP 1.5R</div>
                <div className="scalp-met-value" style={{ color: '#69f0ae' }}>{fmt(calc.tp15, 2)}</div>
              </div>
              <div className="scalp-met">
                <div className="scalp-met-label">TP 2R</div>
                <div className="scalp-met-value" style={{ color: '#00e676' }}>{fmt(calc.tp2, 2)}</div>
              </div>
              <div className="scalp-met">
                <div className="scalp-met-label">TP 3R</div>
                <div className="scalp-met-value" style={{ color: '#00e676' }}>{fmt(calc.tp3, 2)}</div>
              </div>
            </div>
            <RRVis entry={inputs.currentPrice} sl={calc.sl} tp15={calc.tp15} tp2={calc.tp2} tp3={calc.tp3} cfg={calc.cfg} currentPrice={inputs.currentPrice} magneticMA={magneticMA} vwatrZone={vwatrZone ? { ma_value: vwatrZone.ma_value, zone_type: vwatrZone.zone_type, ma_type: vwatrZone.ma_type, ma_period: vwatrZone.ma_period, strength: vwatrZone.strength } : null} />
            <div className="scalp-pnl-row">
              <div className="scalp-pnl-box profit">
                <div className="scalp-pnl-label">TP 1.5R P&L ({calc.recContracts}ct)</div>
                <div className="scalp-pnl-value" style={{ color: '#00e676' }}>+{fmtUSD(calc.pnlTP1)}</div>
              </div>
              <div className="scalp-pnl-box loss">
                <div className="scalp-pnl-label">SL Hit P&L ({calc.recContracts}ct)</div>
                <div className="scalp-pnl-value" style={{ color: '#ff1744' }}>-{fmtUSD(calc.pnlSL)}</div>
              </div>
            </div>
          </div>

          {/* Basis Spread */}
          <div className="scalp-box">
            <div className="scalp-box-header">
              <span className="title">Basis Spread</span>
              <span className="scalp-pill" style={{
                background: calc.basis > 2 ? 'rgba(79,195,247,0.1)' : calc.basis < -2 ? 'rgba(255,171,64,0.1)' : 'rgba(255,255,255,0.05)',
                border: `1px solid ${calc.basis > 2 ? 'rgba(79,195,247,0.3)' : calc.basis < -2 ? 'rgba(255,171,64,0.3)' : 'rgba(255,255,255,0.1)'}`,
                color: calc.basis > 2 ? '#4fc3f7' : calc.basis < -2 ? '#ffab40' : '#78909c',
              }}>{calc.basisState}</span>
            </div>
            <div className="scalp-met-row">
              <div className="scalp-met">
                <div className="scalp-met-label">SPX (Spot)</div>
                <div className="scalp-met-value">{fmt(inputs.spotPrice, 2)}</div>
              </div>
              <div className="scalp-met">
                <div className="scalp-met-label">ES (Futures)</div>
                <div className="scalp-met-value">{fmt(inputs.futuresPrice, 2)}</div>
              </div>
              <div className="scalp-met big">
                <div className="scalp-met-label">Basis</div>
                <div className="scalp-met-value big" style={{ color: calc.basis > 2 ? '#4fc3f7' : calc.basis < -2 ? '#ffab40' : '#78909c' }}>
                  {calc.basis >= 0 ? '+' : ''}{fmt(calc.basis, 2)}p
                </div>
              </div>
              <div className="scalp-met">
                <div className="scalp-met-label">Basis %</div>
                <div className="scalp-met-value">{fmt(calc.basisPct, 3)}%</div>
              </div>
            </div>
            <BasisBar basis={calc.basis} />
          </div>

          {/* Formula Reference */}
          <div className="scalp-box">
            <div className="scalp-box-header">
              <span className="title">Formula Reference</span>
              <span className="scalp-pill" style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', color: '#888' }}>QUICK REF</span>
            </div>
            <div className="scalp-formula-grid">
              {[
                { t: 'Z-Score', f: 'Z = (Price - MA) / s', d: '+/-2s = 95.4% CI' },
                { t: 'Expected Value', f: 'EV = P(W)*W - P(L)*L - Cost', d: 'Enter only when positive' },
                { t: 'Kelly Criterion', f: 'f* = (b*p - q) / b', d: 'Half-Kelly recommended' },
                { t: 'True Range', f: "TR = max(H-L, |H-C'|, |L-C'|)", d: 'ATR = avg(TR, 14)' },
              ].map((r, i) => (
                <div key={i} className="scalp-formula-card">
                  <div className="scalp-formula-title">{r.t}</div>
                  <div className="scalp-formula-expr">{r.f}</div>
                  <div className="scalp-formula-desc">{r.d}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════
// Session PnL Bar Chart
// ══════════════════════════════════════════

function SessionPnLChart({ sessions }: { sessions: { date: string; total_pnl: number }[] }) {
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

function ExitReasonBars({ dist }: { dist: Record<string, number> }) {
  const entries = Object.entries(dist).sort((a, b) => b[1] - a[1]);
  if (!entries.length) return null;
  const maxCount = Math.max(...entries.map(([, v]) => v), 1);
  const total = entries.reduce((s, [, v]) => s + v, 0);

  return (
    <div className="esfu-exit-reasons">
      <div className="esfu-panel-title" style={{ marginBottom: 8 }}>Exit Reason Distribution</div>
      {entries.map(([reason, count]) => (
        <div key={reason} className="esfu-exit-row">
          <span className="esfu-exit-label">{reason}</span>
          <div className="esfu-exit-bar-track">
            <div className="esfu-exit-bar-fill" style={{ width: `${(count / maxCount) * 100}%` }} />
          </div>
          <span className="esfu-exit-count">{count} ({(count / total * 100).toFixed(0)}%)</span>
        </div>
      ))}
    </div>
  );
}

// ══════════════════════════════════════════
// Backtest Tab Content
// ══════════════════════════════════════════

function BacktestTabContent({ state }: { state: ReturnType<typeof useESFuturesScalp> }) {
  const {
    btMode, setBtMode, btPeriod, setBtPeriod, btEquity, setBtEquity,
    btRunning, btProgress, btResult, btError, runBacktest, isMicro, setIsMicro,
    dailyBtStartDate, setDailyBtStartDate, dailyBtEndDate, setDailyBtEndDate,
    dailyBtResult, dailyBtRunning, dailyBtError, dailyBtElapsed,
    runDailyBacktest, setDailyPreset,
  } = state;

  return (
    <div className="esfu-backtest-section">
      {/* Mode Toggle */}
      <div className="esfu-bt-mode-toggle">
        <button className={`esfu-bt-mode-btn ${btMode === 'intraday' ? 'active' : ''}`}
          onClick={() => setBtMode('intraday')}>
          Intraday (15m bars)
          <span className="esfu-bt-mode-desc">Max 60 days</span>
        </button>
        <button className={`esfu-bt-mode-btn ${btMode === 'daily' ? 'active' : ''}`}
          onClick={() => setBtMode('daily')}>
          Daily (1D bars)
          <span className="esfu-bt-mode-desc">Up to 10+ years</span>
        </button>
      </div>

      {/* Intraday Mode */}
      {btMode === 'intraday' && (
        <>
          <div className="esfu-bt-controls">
            <div className="esfu-bt-field">
              <label>Period</label>
              <select value={btPeriod} onChange={e => setBtPeriod(e.target.value)}>
                <option value="7d">7 days</option>
                <option value="14d">14 days</option>
                <option value="30d">30 days</option>
                <option value="60d">60 days</option>
              </select>
            </div>
            <div className="esfu-bt-field">
              <label>Contract</label>
              <select value={isMicro ? 'MES' : 'ES'} onChange={e => setIsMicro(e.target.value === 'MES')}>
                <option value="MES">MES (Micro)</option>
                <option value="ES">ES (E-mini)</option>
              </select>
            </div>
            <div className="esfu-bt-field">
              <label>Equity ($)</label>
              <input type="number" value={btEquity} onChange={e => setBtEquity(Number(e.target.value))} min={1000} step={1000} />
            </div>
            <button className="esfu-bt-run" onClick={runBacktest} disabled={btRunning}>
              {btRunning ? `Running... ${btProgress}%` : 'Run Intraday Backtest'}
            </button>
          </div>

          {btError && <div className="esfu-error">{btError}</div>}
          {btRunning && (
            <div className="esfu-progress-bar">
              <div className="esfu-progress-fill" style={{ width: `${btProgress}%` }} />
            </div>
          )}

          {btResult && (
            <div className="esfu-bt-results">
              <div className="esfu-metrics-grid">
                <MetricCard label="Return" value={fmtPctLocal(btResult.metrics.total_return_pct)} colorize />
                <MetricCard label="Sharpe" value={btResult.metrics.sharpe_ratio.toFixed(2)} />
                <MetricCard label="MDD" value={fmtPctLocal(btResult.metrics.max_drawdown_pct)} colorize />
                <MetricCard label="Win Rate" value={`${btResult.metrics.win_rate.toFixed(1)}%`} />
                <MetricCard label="Profit Factor" value={btResult.metrics.profit_factor.toFixed(2)} />
                <MetricCard label="Trades" value={String(btResult.metrics.total_trades)} />
                <MetricCard label="Sessions" value={String(btResult.metrics.sessions_traded)} />
                <MetricCard label="Avg Trades/Day" value={btResult.metrics.avg_trades_per_session.toFixed(1)} />
                <MetricCard label="Total P&L" value={fmtUSDLocal(btResult.metrics.total_pnl)} colorize />
                <MetricCard label="Sortino" value={btResult.metrics.sortino_ratio.toFixed(2)} />
                <MetricCard label="Long / Short" value={`${btResult.metrics.long_trades} / ${btResult.metrics.short_trades}`} />
                <MetricCard label="Avg Hold" value={`${btResult.metrics.avg_holding_minutes.toFixed(0)}m`} />
                <MetricCard label="Best Session" value={fmtUSDLocal(btResult.metrics.best_session_pnl)} colorize />
                <MetricCard label="Worst Session" value={fmtUSDLocal(btResult.metrics.worst_session_pnl)} colorize />
                <MetricCard label="Win Streak" value={String(btResult.metrics.max_consecutive_wins)} />
                <MetricCard label="Loss Streak" value={String(btResult.metrics.max_consecutive_losses)} />
              </div>

              {btResult.sessions.length > 0 && <SessionPnLChart sessions={btResult.sessions} />}
              {btResult.equity_curve.length > 0 && (
                <ESFEquityCurve equityCurve={btResult.equity_curve} trades={btResult.trades} height={220} />
              )}
              {btResult.metrics.exit_reason_distribution && Object.keys(btResult.metrics.exit_reason_distribution).length > 0 && (
                <ExitReasonBars dist={btResult.metrics.exit_reason_distribution} />
              )}

              {btResult.monte_carlo && (
                <div className="esfu-mc-section">
                  <div className="esfu-panel-title" style={{ marginBottom: 8 }}>Monte Carlo (1000 paths)</div>
                  <div className="esfu-metrics-grid">
                    <MetricCard label="VaR 95%" value={fmtPctLocal(btResult.monte_carlo.var_95)} />
                    <MetricCard label="CVaR 99%" value={fmtPctLocal(btResult.monte_carlo.cvar_99)} />
                    <MetricCard label="Worst MDD" value={fmtPctLocal(btResult.monte_carlo.worst_mdd)} />
                    <MetricCard label="Bankruptcy" value={`${btResult.monte_carlo.bankruptcy_prob.toFixed(1)}%`} />
                    <MetricCard label="Median Return" value={fmtPctLocal(btResult.monte_carlo.median_return)} colorize />
                  </div>
                </div>
              )}

              {btResult.trades.length > 0 && (
                <div className="esfu-trade-log">
                  <div className="esfu-panel-title" style={{ marginBottom: 8 }}>Trade Log</div>
                  <div className="esfu-trade-table-wrap">
                    <table className="esfu-trade-table">
                      <thead>
                        <tr>
                          <th>Time</th><th>Dir</th><th>Entry</th><th>Exit</th>
                          <th>P&L</th><th>Bars</th><th>Reason</th><th>Grade</th>
                        </tr>
                      </thead>
                      <tbody>
                        {btResult.trades.map((t, i) => (
                          <tr key={i}>
                            <td>{t.entry_time}</td>
                            <td className={t.direction === 'LONG' ? 'esfu-dir-long' : 'esfu-dir-short'}>{t.direction}</td>
                            <td>{fmtPts(t.entry_price)}</td>
                            <td>{fmtPts(t.exit_price)}</td>
                            <td style={{ color: t.pnl >= 0 ? '#2ecc71' : '#e74c3c' }}>{fmtUSDLocal(t.pnl)}</td>
                            <td>{t.holding_bars}</td>
                            <td>{t.exit_reason}</td>
                            <td><span className={`esfu-grade-mini esfu-grade-${t.grade.toLowerCase()}`}>{t.grade}</span></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}
        </>
      )}

      {/* Daily Mode */}
      {btMode === 'daily' && (
        <>
          <div className="esfu-bt-presets">
            {[1, 2, 3, 5, 10].map(y => (
              <button key={y} className="esfu-bt-preset-btn" onClick={() => setDailyPreset(y)}>{y}Y</button>
            ))}
          </div>

          <div className="esfu-bt-controls">
            <div className="esfu-bt-field">
              <label>Start Date</label>
              <input value={dailyBtStartDate} onChange={e => setDailyBtStartDate(e.target.value)} placeholder="YYYYMMDD" />
            </div>
            <div className="esfu-bt-field">
              <label>End Date</label>
              <input value={dailyBtEndDate} onChange={e => setDailyBtEndDate(e.target.value)} placeholder="YYYYMMDD" />
            </div>
            <div className="esfu-bt-field">
              <label>Equity ($)</label>
              <input type="number" value={btEquity} onChange={e => setBtEquity(Number(e.target.value))} />
            </div>
            <div className="esfu-bt-field">
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                <input type="checkbox" checked={isMicro} onChange={e => setIsMicro(e.target.checked)} />
                Micro
              </label>
            </div>
            <button className="esfu-bt-run" onClick={runDailyBacktest} disabled={dailyBtRunning}>
              {dailyBtRunning ? `Running... (${dailyBtElapsed}s)` : 'Run Daily Backtest'}
            </button>
          </div>

          {dailyBtError && <div className="esfu-error">{dailyBtError}</div>}

          {dailyBtResult && (
            <div className="esfu-bt-results">
              {dailyBtResult.equity_curve.length > 0 && (
                <div style={{ fontSize: '0.8rem', color: '#888', marginBottom: 8 }}>
                  Data Range: {dailyBtResult.equity_curve[0].date} ~ {dailyBtResult.equity_curve[dailyBtResult.equity_curve.length - 1].date}
                  {' '}({dailyBtResult.equity_curve.length} trading days)
                </div>
              )}
              <div className="esfu-metrics-grid">
                <MetricCard label="Return" value={`${dailyBtResult.metrics.total_return_pct.toFixed(1)}%`} colorize />
                <MetricCard label="CAGR" value={`${dailyBtResult.metrics.cagr?.toFixed(1) ?? 0}%`} colorize />
                <MetricCard label="Sharpe" value={dailyBtResult.metrics.sharpe_ratio.toFixed(2)} />
                <MetricCard label="MDD" value={`${dailyBtResult.metrics.max_drawdown_pct.toFixed(1)}%`} colorize />
                <MetricCard label="Trades" value={String(dailyBtResult.metrics.total_trades)} />
                <MetricCard label="Win Rate" value={`${dailyBtResult.metrics.win_rate.toFixed(1)}%`} />
                <MetricCard label="Profit Factor" value={dailyBtResult.metrics.profit_factor.toFixed(2)} />
                <MetricCard label="Long / Short" value={`${dailyBtResult.metrics.long_trades} / ${dailyBtResult.metrics.short_trades}`} />
                <MetricCard label="Total P&L" value={fmtUSDLocal(dailyBtResult.metrics.total_pnl)} colorize />
                <MetricCard label="Avg R:R" value={dailyBtResult.metrics.avg_rr.toFixed(2)} />
                <MetricCard label="Avg Hold" value={`${dailyBtResult.metrics.avg_holding_days}d`} />
                <MetricCard label="Margin Calls" value={String(dailyBtResult.metrics.margin_call_count ?? 0)} />
                <MetricCard label="Rollovers" value={String(dailyBtResult.metrics.roll_count ?? 0)} />
                <MetricCard label="Roll Costs" value={fmtUSDLocal(dailyBtResult.metrics.total_roll_costs ?? 0)} />
              </div>

              {dailyBtResult.equity_curve.length > 0 && (
                <EquityCurve
                  data={dailyBtResult.equity_curve.map(e => ({
                    date: e.date.split(' ')[0].split('T')[0],
                    equity: e.total_value,
                    drawdown_pct: e.drawdown_pct,
                  }))}
                  height={280}
                />
              )}

              {dailyBtResult.trades.length > 0 && (
                <div style={{ maxHeight: 300, overflowY: 'auto' }}>
                  <table className="esfu-trade-table">
                    <thead>
                      <tr>
                        <th>Entry</th><th>Exit</th><th>Dir</th><th>Entry $</th>
                        <th>Exit $</th><th>Contracts</th><th>P&L</th><th>Days</th><th>Reason</th>
                      </tr>
                    </thead>
                    <tbody>
                      {dailyBtResult.trades.map((t, i) => (
                        <tr key={i}>
                          <td>{t.entry_date}</td>
                          <td>{t.exit_date}</td>
                          <td className={t.direction === 'LONG' ? 'esfu-dir-long' : 'esfu-dir-short'}>{t.direction}</td>
                          <td>{fmtPts(t.entry_price)}</td>
                          <td>{fmtPts(t.exit_price)}</td>
                          <td>{t.contracts}</td>
                          <td style={{ color: t.pnl_dollar >= 0 ? '#2ecc71' : '#e74c3c' }}>{fmtUSDLocal(t.pnl_dollar)}</td>
                          <td>{t.holding_days}</td>
                          <td>{t.exit_reason}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ══════════════════════════════════════════
// HypothesisCard
// ══════════════════════════════════════════

function HypothesisCard({ hypothesis: h, onRecordResult, onSkip }: {
  hypothesis: ESFHypothesis;
  onRecordResult: (data: any) => Promise<any>;
  onSkip: (id: number, reason?: string) => Promise<void>;
}) {
  const [showRecord, setShowRecord] = useState(false);
  const [exitPrice, setExitPrice] = useState('');
  const [exitReason, setExitReason] = useState('');

  const dirColor = h.direction === 'LONG' ? '#2ecc71' : h.direction === 'SHORT' ? '#e74c3c' : '#95a5a6';
  const gradeColor = h.grade === 'A' ? '#2ecc71' : h.grade === 'B' ? '#f39c12' : '#e67e22';
  const reasoning = typeof h.reasoning_json === 'string' ? JSON.parse(h.reasoning_json) : (h.reasoning_json || {});

  return (
    <div className="esfu-hypothesis-card">
      <div className="esfu-hyp-direction" style={{ borderLeftColor: dirColor }}>
        <span className="esfu-hyp-arrow" style={{ color: dirColor }}>
          {h.direction === 'LONG' ? '\u25B2' : h.direction === 'SHORT' ? '\u25BC' : '\u25CF'}
        </span>
        <span className="esfu-hyp-dir-text" style={{ color: dirColor }}>{h.direction}</span>
        <span className="esfu-badge" style={{ background: gradeColor + '22', color: gradeColor }}>
          Grade {h.grade} ({h.total_score.toFixed(0)})
        </span>
        <span className="esfu-badge" style={{ background: 'rgba(52,152,219,0.15)', color: '#3498db' }}>
          {h.regime}
        </span>
        {h.variant_id && <span className="esfu-badge" style={{ background: 'rgba(155,89,182,0.15)', color: '#9b59b6' }}>V{h.variant_id}</span>}
      </div>

      <div className="esfu-hyp-levels">
        <div className="esfu-hyp-level">
          <span className="esfu-hyp-level-label">Entry</span>
          <span className="esfu-hyp-level-value">{fmtPts(h.entry_price)}</span>
        </div>
        <div className="esfu-hyp-level sl">
          <span className="esfu-hyp-level-label">Stop Loss</span>
          <span className="esfu-hyp-level-value">{fmtPts(h.stop_loss)}</span>
        </div>
        <div className="esfu-hyp-level tp">
          <span className="esfu-hyp-level-label">Take Profit</span>
          <span className="esfu-hyp-level-value">{fmtPts(h.take_profit)}</span>
        </div>
      </div>

      <div className="esfu-hyp-confidence">
        <span>Confidence: {(h.confidence * 100).toFixed(0)}%</span>
        <div className="esfu-confidence-bar">
          <div className="esfu-confidence-fill" style={{ width: `${h.confidence * 100}%`, background: h.confidence > 0.6 ? '#2ecc71' : h.confidence > 0.4 ? '#f39c12' : '#e74c3c' }} />
        </div>
      </div>

      {/* Reasoning toggle */}
      <details className="esfu-hyp-reasoning">
        <summary>Reasoning (Layer Scores)</summary>
        <div className="esfu-reasoning-grid">
          <span>L1 AMT: {reasoning.l1_amt_location ?? '\u2014'}</span>
          <span>L2 Z-Score: {reasoning.l2_zscore ?? '\u2014'}</span>
          <span>L3 Momentum: {reasoning.l3_momentum ?? '\u2014'}</span>
          <span>L4 Vol/Agg: {reasoning.l4_volume_aggression ?? '\u2014'}</span>
          <span>Z: {reasoning.z_score != null ? Number(reasoning.z_score).toFixed(2) : '\u2014'}</span>
          <span>RSI: {reasoning.rsi != null ? Number(reasoning.rsi).toFixed(1) : '\u2014'}</span>
        </div>
      </details>

      {/* Actions */}
      {(h.status === 'PENDING' || h.status === 'ACTIVE') && (
        <div className="esfu-hyp-actions">
          {!showRecord ? (
            <>
              <button className="esfu-btn esfu-btn-sm" onClick={() => setShowRecord(true)}>Record Result</button>
              <button className="esfu-btn esfu-btn-sm esfu-btn-ghost" onClick={() => onSkip(h.hypothesis_id)}>Skip</button>
            </>
          ) : (
            <div className="esfu-record-form">
              <input type="number" placeholder="Exit Price" value={exitPrice} onChange={e => setExitPrice(e.target.value)} step="0.25" />
              <input type="text" placeholder="Exit Reason" value={exitReason} onChange={e => setExitReason(e.target.value)} />
              <button className="esfu-btn esfu-btn-sm esfu-btn-primary" onClick={async () => {
                if (!exitPrice) return;
                await onRecordResult({
                  hypothesis_id: h.hypothesis_id,
                  actual_entry_price: h.entry_price,
                  actual_exit_price: parseFloat(exitPrice),
                  actual_direction: h.direction,
                  contracts: 1,
                  exit_reason: exitReason || 'MANUAL',
                  holding_minutes: 0,
                });
                setShowRecord(false);
                setExitPrice('');
                setExitReason('');
              }}>Save</button>
              <button className="esfu-btn esfu-btn-sm esfu-btn-ghost" onClick={() => setShowRecord(false)}>Cancel</button>
            </div>
          )}
        </div>
      )}

      {h.status === 'CLOSED' && <div className="esfu-hyp-status closed">CLOSED</div>}
      {h.status === 'SKIPPED' && <div className="esfu-hyp-status skipped">SKIPPED</div>}
    </div>
  );
}

// ══════════════════════════════════════════
// Main Page
// ══════════════════════════════════════════

export function ESFuturesScalping() {
  const state = useESFuturesScalp();
  const {
    isMicro, setIsMicro, effectiveTicker,
    activeTab, setActiveTab,
    analysis, volumeProfile, sessionStatus, candles,
    loading, error, lastUpdated,
    chartInterval, setChartInterval, chartPeriod, setChartPeriod,
    activeSubcharts, setActiveSubcharts,
    refresh, scalp,
  } = state;

  const journal = useESFJournal(effectiveTicker);

  const tabs: { key: TabKey; label: string }[] = [
    { key: 'strategy', label: "Today's Strategy" },
    { key: 'analysis', label: 'Live Analysis' },
    { key: 'decision', label: 'Decision Engine' },
    { key: 'backtest', label: 'Backtest' },
    { key: 'evolution', label: 'Evolution' },
  ];

  return (
    <div className="esfu-page container">
      <div className="esfu-header">
        <h1 className="page-title">Futures</h1>
        <p className="page-subtitle">오늘의 단타 스캘핑 전략은? — 가설 → 검증 → 분석 → 진화</p>
      </div>

      {/* Top Bar */}
      <div className="esfu-top-bar">
        <span className="esfu-ticker-label">{effectiveTicker}</span>
        {analysis && (
          <>
            <span className="esfu-price">{fmtPts(analysis.entry_price)}</span>
            <span className="esfu-badge" style={{
              background: analysis.direction === 'LONG' ? 'rgba(46,204,113,0.2)' :
                           analysis.direction === 'SHORT' ? 'rgba(231,76,60,0.2)' : 'rgba(149,165,166,0.15)',
              color: analysis.direction === 'LONG' ? '#2ecc71' :
                     analysis.direction === 'SHORT' ? '#e74c3c' : '#95a5a6',
            }}>
              {analysis.direction === 'LONG' ? '^ LONG' : analysis.direction === 'SHORT' ? 'v SHORT' : '- NEUTRAL'}
            </span>
            {analysis.regime && (() => {
              const rs = REGIME_STYLES[analysis.regime!.regime] || REGIME_STYLES.NEUTRAL;
              return (
                <span className="esfu-badge" style={{ background: rs.bg, color: rs.fg }}>
                  {rs.label} ({analysis.regime!.trend_score > 0 ? '+' : ''}{analysis.regime!.trend_score})
                </span>
              );
            })()}
          </>
        )}
        {sessionStatus && (
          <span className="esfu-badge" style={{
            background: sessionStatus.is_rth ? 'rgba(46,204,113,0.15)' : 'rgba(149,165,166,0.15)',
            color: sessionStatus.is_rth ? '#2ecc71' : '#95a5a6',
          }}>
            {sessionStatus.is_rth ? 'RTH' : 'ETH'}
          </span>
        )}
        {analysis && (
          <span className="esfu-badge" style={{
            background: 'rgba(255,255,255,0.05)',
            color: analysis.grade === 'A' ? '#2ecc71' : analysis.grade === 'B' ? '#f1c40f' : analysis.grade === 'C' ? '#e67e22' : '#95a5a6',
          }}>
            Grade {analysis.grade} ({analysis.total_score.toFixed(0)}/100)
          </span>
        )}
        <span className="esfu-last-updated">
          {lastUpdated ? timeAgo(lastUpdated) : ''}
        </span>
        <button className="esfu-refresh-btn" onClick={refresh} disabled={loading}>
          {loading ? '...' : 'Refresh'}
        </button>
      </div>

      {error && <div className="esfu-error">{error}</div>}

      {/* Tab Bar */}
      <div className="market-tabs">
        {tabs.map(t => (
          <button key={t.key} className={`market-tab-btn ${activeTab === t.key ? 'active' : ''}`}
            onClick={() => setActiveTab(t.key)}>
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}

      {/* ── Tab 0: Today's Strategy ── */}
      {activeTab === 'strategy' && (
        <div className="esfu-strategy-tab">
          {/* ── Hero: Today's Strategy ── */}
          <div className="esfu-strategy-hero">
            <div className="esfu-hero-header">
              <h2>오늘의 단타 전략은?</h2>
              <div className="esfu-hero-actions">
                {journal.activeExperimentStatus ? (
                  <button className="esfu-btn esfu-btn-primary" onClick={() => journal.generateABHypotheses(effectiveTicker, journal.activeExperimentStatus!.experiment_id)} disabled={journal.todayLoading}>
                    A/B 가설 생성
                  </button>
                ) : (
                  <button className="esfu-btn esfu-btn-primary" onClick={() => journal.generateHypothesis()} disabled={journal.todayLoading}>
                    {journal.todayLoading ? 'Generating...' : '전략 생성'}
                  </button>
                )}
              </div>
            </div>

            {journal.todayHypotheses.length === 0 ? (
              <div className="esfu-hero-empty">
                {journal.error === 'no_signal' ? (
                  <p>오늘은 진입 조건 미충족 (Score too low). 내일 다시 확인하세요.</p>
                ) : journal.error === 'no_data' ? (
                  <p>시장 데이터를 불러올 수 없습니다. 잠시 후 다시 시도하세요.</p>
                ) : (
                  <p>오늘의 전략이 아직 없습니다. "전략 생성" 버튼을 클릭하세요.</p>
                )}
              </div>
            ) : (
              <div className="esfu-hero-cards">
                {journal.todayHypotheses.map((h) => (
                  <HypothesisCard key={h.hypothesis_id} hypothesis={h} onRecordResult={journal.recordResult} onSkip={journal.skipHypothesis} />
                ))}
              </div>
            )}
          </div>

          {/* ── Live Tracking ── */}
          {journal.todayHypotheses.some(h => h.status === 'PENDING' || h.status === 'ACTIVE') && analysis && (
            <div className="esfu-live-tracking">
              <div className="esfu-panel">
                <div className="esfu-panel-title">LIVE TRACKING</div>
                {journal.todayHypotheses.filter(h => h.status === 'PENDING' || h.status === 'ACTIVE').map(h => {
                  const isLong = h.direction === 'LONG';
                  const currentPrice = analysis.entry_price;
                  const pnl = isLong ? currentPrice - h.entry_price : h.entry_price - currentPrice;
                  const pnlPct = (pnl / h.entry_price) * 100;
                  const slDist = isLong ? (currentPrice - h.stop_loss) / (h.entry_price - h.stop_loss) : (h.stop_loss - currentPrice) / (h.stop_loss - h.entry_price);
                  const tpDist = isLong ? (currentPrice - h.entry_price) / (h.take_profit - h.entry_price) : (h.entry_price - currentPrice) / (h.entry_price - h.take_profit);
                  return (
                    <div key={h.hypothesis_id} className="esfu-tracking-row">
                      <span className={`esfu-badge ${h.direction === 'LONG' ? 'long' : 'short'}`}>{h.direction}</span>
                      <span className="esfu-tracking-price">Entry: {fmtPts(h.entry_price)}</span>
                      <span className="esfu-tracking-price">Now: {fmtPts(currentPrice)}</span>
                      <span className={`esfu-tracking-pnl ${pnl >= 0 ? 'positive' : 'negative'}`}>
                        {pnl >= 0 ? '+' : ''}{pnl.toFixed(2)} pts ({pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(2)}%)
                      </span>
                      <div className="esfu-progress-container">
                        <div className="esfu-progress-label">SL</div>
                        <div className="esfu-progress-track">
                          <div className="esfu-progress-fill sl" style={{ width: `${Math.max(0, Math.min(100, (1 - slDist) * 100))}%` }} />
                        </div>
                        <div className="esfu-progress-label">TP</div>
                        <div className="esfu-progress-track">
                          <div className="esfu-progress-fill tp" style={{ width: `${Math.max(0, Math.min(100, tpDist * 100))}%` }} />
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* ── Results Journal ── */}
          <div className="esfu-results-journal">
            <div className="esfu-panel">
              <div className="esfu-panel-title">STRATEGY JOURNAL</div>
              {journal.hypotheses.length === 0 ? (
                <p style={{ color: '#7f8c8d', textAlign: 'center', padding: '1rem' }}>No history yet</p>
              ) : (
                <>
                  <table className="esfu-trade-table">
                    <thead>
                      <tr>
                        <th>Date</th>
                        <th>Direction</th>
                        <th>Grade</th>
                        <th>Entry</th>
                        <th>SL</th>
                        <th>TP</th>
                        <th>Status</th>
                        <th>Result</th>
                      </tr>
                    </thead>
                    <tbody>
                      {journal.hypotheses.map(h => (
                        <tr key={h.hypothesis_id}>
                          <td>{h.trade_date}</td>
                          <td className={h.direction === 'LONG' ? 'positive' : h.direction === 'SHORT' ? 'negative' : ''}>{h.direction}</td>
                          <td>{h.grade}</td>
                          <td>{fmtPts(h.entry_price)}</td>
                          <td>{fmtPts(h.stop_loss)}</td>
                          <td>{fmtPts(h.take_profit)}</td>
                          <td><span className={`esfu-status-badge ${h.status.toLowerCase()}`}>{h.status}</span></td>
                          <td>{h.status === 'CLOSED' ? '\u2014' : ''}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {journal.hypothesesTotal > 20 && (
                    <div className="esfu-pagination">
                      <button disabled={journal.historyPage === 0} onClick={() => journal.setHistoryPage(journal.historyPage - 1)}>Prev</button>
                      <span>Page {journal.historyPage + 1} / {Math.ceil(journal.hypothesesTotal / 20)}</span>
                      <button disabled={(journal.historyPage + 1) * 20 >= journal.hypothesesTotal} onClick={() => journal.setHistoryPage(journal.historyPage + 1)}>Next</button>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── Tab 1: Live Analysis ── */}
      {activeTab === 'analysis' && (
        <>
          {analysis ? (
            <div className="esfu-analysis-grid">
              <RegimePanel regime={analysis.regime} />
              <AMTPanel amt={analysis.amt} />
              <ScorePanel analysis={analysis} />
              <SignalCard analysis={analysis} />
              <div style={{ gridColumn: 'span 2' }}>
                <IndicatorPanel analysis={analysis} candles={candles} />
              </div>
            </div>
          ) : (
            !loading && !error && <div className="esfu-empty">No analysis data available</div>
          )}

          {loading && !analysis && (
            <div className="esfu-loading">
              <div className="esfu-spinner" />
              <span>Loading analysis...</span>
            </div>
          )}

          {(volumeProfile || sessionStatus) && (
            <div className="esfu-mid-grid">
              {volumeProfile && (
                <VolumeProfileChart vp={volumeProfile} currentPrice={analysis?.entry_price || 0} />
              )}
              {sessionStatus && (
                <SessionPanel session={sessionStatus} isMicro={isMicro} onToggle={() => setIsMicro(!isMicro)} />
              )}
            </div>
          )}
        </>
      )}

      {/* ── Tab 2: Decision Engine (Chart + Strategy + Scalp) ── */}
      {activeTab === 'decision' && (
        <div className="esfu-decision-layout">
          {/* Embedded Chart */}
          {candles.length > 0 ? (
            <div className="esfu-decision-chart">
              <div className="chart-toolbar" style={{ borderRadius: '8px 8px 0 0' }}>
                {/* INTERVAL */}
                <div className="toolbar-section">
                  <span className="chart-toolbar-label">INTERVAL</span>
                  {(['5m', '15m', '30m', '1h'] as const).map(iv => (
                    <button key={iv} className={`tf-btn ${chartInterval === iv ? 'active' : ''}`}
                      onClick={() => setChartInterval(iv)}>{iv}</button>
                  ))}
                </div>

                <div className="toolbar-divider" />

                {/* PERIOD */}
                <div className="toolbar-section">
                  <span className="chart-toolbar-label">PERIOD</span>
                  {([['1d', '1D'], ['5d', '5D'], ['1mo', '1M']] as const).map(([val, label]) => (
                    <button key={val} className={`tf-btn ${chartPeriod === val ? 'active' : ''}`}
                      onClick={() => setChartPeriod(val)}>{label}</button>
                  ))}
                </div>

                <div className="toolbar-divider" />

                {/* SUBCHARTS */}
                <div className="toolbar-section">
                  <span className="chart-toolbar-label">SUBCHARTS</span>
                  {(['rsi', 'macd', 'zscore', 'atr', 'adx'] as const).map(key => (
                    <button key={key}
                      className={`tf-btn ${activeSubcharts[key] ? 'active' : ''}`}
                      onClick={() => setActiveSubcharts({ ...activeSubcharts, [key]: !activeSubcharts[key] })}>
                      {key.toUpperCase()}
                    </button>
                  ))}
                </div>
              </div>
              <ESFIntradayChart
                candles={candles}
                volumeProfile={volumeProfile ? {
                  poc: volumeProfile.poc, vah: volumeProfile.vah, val: volumeProfile.val,
                  lvn_levels: volumeProfile.lvn_levels || [],
                } : undefined}
                entryPlan={analysis && (analysis as any).signal_active ? {
                  direction: analysis.direction as 'LONG' | 'SHORT',
                  entry: analysis.entry_price,
                  stopLoss: analysis.stop_loss,
                  takeProfit: analysis.take_profit,
                  rrRatio: analysis.risk_reward_ratio,
                  multiplier: isMicro ? 5 : 50,
                } as EntryPlan : null}
                vwatrZones={analysis?.vwatr_zones}
                subcharts={activeSubcharts}
                height={380}
                ticker={effectiveTicker}
              />
            </div>
          ) : (
            !loading && <div className="esfu-empty">No chart data</div>
          )}

          {/* Strategy Dashboard */}
          <StrategyDashboard regime={analysis?.regime} candles={candles} />

          {/* Scalp Decision Engine */}
          <ScalpDecisionEngine scalp={scalp} magneticMA={analysis?.magnetic_ma?.best?.current_value} vwatrZone={analysis?.vwatr_zones?.[0] ?? null} />
        </div>
      )}

      {/* ── Tab 4: Backtest ── */}
      {activeTab === 'backtest' && (
        <BacktestTabContent state={state} />
      )}

      {/* ── Tab 4: Evolution ── */}
      {activeTab === 'evolution' && (
        <div className="esfu-evolution-tab">
          {/* ── Cumulative Stats Grid ── */}
          <div className="esfu-panel">
            <div className="esfu-panel-title">CUMULATIVE STATISTICS</div>
            <div className="esfu-evolution-stats-grid">
              {['overall', 'direction', 'regime', 'grade'].map(dim => {
                const dimStats = journal.stats.filter(s => s.dimension === dim);
                if (dimStats.length === 0) return null;
                return (
                  <div key={dim} className="esfu-stat-section">
                    <h4>{dim.toUpperCase()}</h4>
                    <table className="esfu-trade-table compact">
                      <thead>
                        <tr>
                          <th>{dim === 'overall' ? '' : dim}</th>
                          <th>Trades</th>
                          <th>WR</th>
                          <th>Avg PnL</th>
                          <th>Total PnL</th>
                          <th>PF</th>
                          <th>Sharpe</th>
                        </tr>
                      </thead>
                      <tbody>
                        {dimStats.map(s => (
                          <tr key={s.dimension_value}>
                            <td>{s.dimension_value}</td>
                            <td>{s.total_trades}</td>
                            <td className={s.win_rate >= 0.5 ? 'positive' : 'negative'}>{(s.win_rate * 100).toFixed(1)}%</td>
                            <td className={s.avg_pnl >= 0 ? 'positive' : 'negative'}>{fmtUSDLocal(s.avg_pnl)}</td>
                            <td className={s.total_pnl >= 0 ? 'positive' : 'negative'}>{fmtUSDLocal(s.total_pnl)}</td>
                            <td>{s.profit_factor.toFixed(2)}</td>
                            <td>{s.sharpe_approx.toFixed(2)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                );
              })}
              {journal.stats.length === 0 && (
                <p style={{ color: '#7f8c8d', textAlign: 'center', padding: '2rem' }}>No cumulative data yet. Record strategy results to see statistics.</p>
              )}
            </div>
          </div>

          {/* ── A/B Experiment Panel ── */}
          <div className="esfu-panel" style={{ marginTop: '1rem' }}>
            <div className="esfu-panel-title">A/B EXPERIMENTS</div>

            {journal.activeExperimentStatus && (
              <div className="esfu-ab-active">
                <h4>{journal.activeExperimentStatus.experiment_name} (Day {journal.activeExperimentStatus.days_elapsed}/{journal.activeExperimentStatus.max_days})</h4>
                <div className="esfu-ab-comparison">
                  {['variant_a', 'variant_b'].map(vKey => {
                    const v = journal.activeExperimentStatus![vKey as 'variant_a' | 'variant_b'];
                    return (
                      <div key={vKey} className="esfu-ab-variant">
                        <h5>{v.name}</h5>
                        <div className="esfu-ab-stats">
                          <span>Trades: {v.trades}</span>
                          <span>WR: {(v.win_rate * 100).toFixed(1)}%</span>
                          <span>Avg PnL: {fmtUSDLocal(v.avg_pnl)}</span>
                          <span>Sharpe: {v.sharpe.toFixed(2)}</span>
                        </div>
                        <div className="esfu-progress-track">
                          <div className="esfu-progress-fill" style={{ width: `${Math.min(100, (v.trades / journal.activeExperimentStatus!.min_trades_per_variant) * 100)}%` }} />
                        </div>
                        <span className="esfu-progress-label">{v.trades}/{journal.activeExperimentStatus!.min_trades_per_variant} trades</span>
                      </div>
                    );
                  })}
                </div>
                {journal.activeExperimentStatus.p_value != null && (
                  <div className="esfu-ab-pvalue">
                    p-value: {journal.activeExperimentStatus.p_value.toFixed(4)}
                    {journal.activeExperimentStatus.p_value < 0.05 ? ' \u2713 Significant' : ' (not yet significant)'}
                  </div>
                )}
                <div className="esfu-ab-actions">
                  {journal.activeExperimentStatus.ready && (
                    <button className="esfu-btn esfu-btn-primary" onClick={() => journal.concludeExperiment(journal.activeExperimentStatus!.experiment_id)}>
                      Conclude Experiment
                    </button>
                  )}
                </div>
              </div>
            )}

            {/* Variant Manager */}
            <div className="esfu-variant-list" style={{ marginTop: '1rem' }}>
              <h4>Variants ({journal.variants.length})</h4>
              {journal.variants.map(v => (
                <div key={v.variant_id} className="esfu-variant-row">
                  <span className="esfu-variant-name">{v.name}</span>
                  {v.is_baseline ? <span className="esfu-badge" style={{ background: 'rgba(46,204,113,0.2)', color: '#2ecc71' }}>BASELINE</span> : null}
                  <span className="esfu-variant-overrides">{Object.keys(v.param_overrides_json || {}).length} overrides</span>
                </div>
              ))}
              {journal.variants.length === 0 && <p style={{ color: '#7f8c8d' }}>No variants yet</p>}
            </div>

            {/* Experiment History */}
            {journal.experiments.length > 0 && (
              <div className="esfu-experiment-history" style={{ marginTop: '1rem' }}>
                <h4>Experiment History</h4>
                {journal.experiments.map(e => (
                  <div key={e.experiment_id} className="esfu-experiment-row">
                    <span>{e.name}</span>
                    <span className={`esfu-status-badge ${e.status.toLowerCase()}`}>{e.status}</span>
                    {e.winner_variant_id && <span>Winner: V{e.winner_variant_id}</span>}
                    {e.status === 'CONCLUDED' && e.winner_variant_id && (
                      <button className="esfu-btn esfu-btn-sm" onClick={() => journal.graduateWinner(e.experiment_id)}>Graduate</button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
