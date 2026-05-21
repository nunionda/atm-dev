/**
 * IndicatorPanel — extracted from ESFuturesScalping page.
 *
 * Phase 3.C 분할: pages/ESFuturesScalping.tsx → components/esf/scalping/IndicatorPanel.tsx
 */

import type { ESFAnalysis, ESFCandle } from '@lib/api';

export function IndicatorPanel({ analysis, candles }: { analysis: ESFAnalysis; candles: ESFCandle[] }) {
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

