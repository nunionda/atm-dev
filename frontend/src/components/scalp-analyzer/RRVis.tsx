/**
 * RRVis — extracted from ScalpAnalyzer page.
 *
 * Phase 3.C 분할: pages/ScalpAnalyzer.tsx → components/scalp-analyzer/RRVis.tsx
 */

import { clamp, fmt, K, F } from '@lib/scalpEngine';

export function RRVis({ entry, sl, tp15, tp2, tp3, isLong, ma, zZone, zStopMult, maDistR, revertProb, stdDev, z, volumeSR }: {
  entry: number; sl: number; tp15: number; tp2: number; tp3: number; isLong: boolean;
  ma: number; zZone: 'NORMAL' | 'MILD' | 'STRONG'; zStopMult: number; maDistR: number; revertProb: number;
  stdDev: number; z: number; volumeSR?: VolumeSRResult | null;
}) {
  // σ band price levels
  const s15p = ma + 1.5 * stdDev, s15n = ma - 1.5 * stdDev;
  const s2p = ma + 2 * stdDev, s2n = ma - 2 * stdDev;
  // Collect S/R prices for range calculation
  const srPrices = volumeSR?.levels.map(l => l.price) ?? [];
  const all = [sl, entry, tp15, tp2, tp3, ma, s15p, s15n, s2p, s2n, ...srPrices];
  const lo = Math.min(...all), hi = Math.max(...all), rng = hi - lo || 1, pad = rng * 0.18;
  const svgH = 290;
  const toY = (p: number) => clamp(((hi + pad - p) / (rng + pad * 2)) * (svgH - 20), 8, svgH - 12);
  const lines: { p: number; lb: string; c: string; d: boolean }[] = [
    { p: sl, lb: "STOP", c: K.red, d: true }, { p: entry, lb: "ENTRY", c: K.acc, d: false },
    { p: tp15, lb: "1.5R", c: "#69f0ae", d: true }, { p: tp2, lb: "2R", c: K.grn, d: true }, { p: tp3, lb: "3R", c: K.grn, d: false },
  ];
  const dirColor = isLong ? K.grn : K.red;
  const dirLabel = isLong ? "LONG" : "SHORT";
  const dirIcon = isLong ? "▲" : "▼";
  const entryY = toY(entry);
  const maY = toY(ma);
  const arrowTipY = isLong ? toY(tp15) + 8 : toY(tp15) - 8;
  const arrowMidY = (entryY + arrowTipY) / 2;
  const zoneColor = zZone === 'STRONG' ? '#f9a825' : zZone === 'MILD' ? '#78909c' : '#546e7a';
  const zoneTag = zZone === 'STRONG' ? `×${zStopMult} 넓은 스탑` : zZone === 'MILD' ? `×${zStopMult} 표준` : `×${zStopMult} 타이트`;
  const W = 370;

  // Entry signal logic: |Z| ≥ 2 → STRONG, 1.5 ≤ |Z| < 2 → LEAN, else NO SIGNAL
  const absZ = Math.abs(z);
  const hasSignal = absZ >= 1.5;
  const signalStrength = absZ >= 2 ? 'STRONG' : 'LEAN';
  const signalDir = z < -1.5 ? 'LONG' : z > 1.5 ? 'SHORT' : '';
  const signalLabel = hasSignal ? `${signalStrength} ${signalDir}` : 'NO SIGNAL';
  const signalColor = hasSignal ? (signalDir === 'LONG' ? K.grn : K.red) : '#546e7a';

  return (
    <div className="scalp-rr-vis">
      <svg width="100%" height={svgH} viewBox={`0 0 ${W} ${svgH}`} style={{ display: "block" }}>
        {/* ±2σ outer zone shading */}
        <rect x="48" y={toY(s2p)} width="230" height={Math.abs(toY(s2p) - toY(s15p))} fill="#f9a82508" rx="2" />
        <rect x="48" y={toY(s15n)} width="230" height={Math.abs(toY(s15n) - toY(s2n))} fill="#f9a82508" rx="2" />
        {/* ±1.5σ inner zone shading */}
        <rect x="48" y={toY(s15p)} width="230" height={Math.abs(toY(s15p) - toY(s15n))} fill="#42a5f505" rx="2" />

        {/* Loss zone */}
        <rect x="48" y={Math.min(entryY, toY(sl))} width="230" height={Math.abs(toY(sl) - entryY)} fill={`${K.red}0e`} rx="3" />
        {/* Profit zone */}
        <rect x="48" y={Math.min(entryY, toY(tp3))} width="230" height={Math.abs(toY(tp3) - entryY)} fill={`${K.grn}08`} rx="3" />

        {/* σ band lines */}
        <line x1="48" y1={toY(s2p)} x2="298" y2={toY(s2p)} stroke="#f9a825" strokeWidth="0.8" strokeDasharray="2,3" strokeOpacity="0.5" />
        <line x1="48" y1={toY(s2n)} x2="298" y2={toY(s2n)} stroke="#f9a825" strokeWidth="0.8" strokeDasharray="2,3" strokeOpacity="0.5" />
        <line x1="48" y1={toY(s15p)} x2="298" y2={toY(s15p)} stroke="#78909c" strokeWidth="0.8" strokeDasharray="2,3" strokeOpacity="0.4" />
        <line x1="48" y1={toY(s15n)} x2="298" y2={toY(s15n)} stroke="#78909c" strokeWidth="0.8" strokeDasharray="2,3" strokeOpacity="0.4" />
        {/* σ labels (right side) */}
        <text x="302" y={toY(s2p) + 3} textAnchor="start" fill="#f9a825" fontSize="7" fontFamily="monospace" opacity="0.7">+2σ</text>
        <text x="302" y={toY(s2n) + 3} textAnchor="start" fill="#f9a825" fontSize="7" fontFamily="monospace" opacity="0.7">-2σ</text>
        <text x="302" y={toY(s15p) + 3} textAnchor="start" fill="#78909c" fontSize="7" fontFamily="monospace" opacity="0.6">+1.5σ</text>
        <text x="302" y={toY(s15n) + 3} textAnchor="start" fill="#78909c" fontSize="7" fontFamily="monospace" opacity="0.6">-1.5σ</text>
        {/* σ zone labels (left side) */}
        <text x="45" y={toY(s2p) - 3} textAnchor="end" fill="#f9a825" fontSize="6.5" fontFamily="monospace" opacity="0.5">SHORT zone</text>
        <text x="45" y={toY(s2n) + 9} textAnchor="end" fill="#f9a825" fontSize="6.5" fontFamily="monospace" opacity="0.5">LONG zone</text>

        {/* MA reference line */}
        <line x1="48" y1={maY} x2="298" y2={maY} stroke="#42a5f5" strokeWidth="1.5" strokeDasharray="3,3" strokeOpacity="0.7" />
        <rect x="2" y={maY - 8} width="42" height="16" rx="3" fill="#42a5f510" stroke="#42a5f540" strokeWidth="0.5" />
        <text x="23" y={maY + 4} textAnchor="middle" fill="#42a5f5" fontSize="8" fontFamily="monospace" fontWeight="700">MA</text>
        <text x="302" y={maY + 3.5} textAnchor="start" fill="#42a5f5" fontSize="8" fontFamily="monospace">{fmt(ma, 2)}</text>
        {/* MA→Entry distance marker */}
        {Math.abs(maY - entryY) > 14 && (
          <g>
            <line x1="36" y1={Math.min(maY, entryY) + 3} x2="36" y2={Math.max(maY, entryY) - 3} stroke="#42a5f5" strokeWidth="0.8" strokeOpacity="0.5" />
            <text x="34" y={(maY + entryY) / 2 + 3} textAnchor="end" fill="#42a5f5" fontSize="7" fontFamily="monospace" opacity="0.7">{maDistR.toFixed(1)}R</text>
          </g>
        )}

        {/* Direction arrow */}
        <line x1="165" y1={entryY} x2="165" y2={arrowTipY} stroke={dirColor} strokeWidth="2.5" strokeOpacity="0.6" />
        <polygon
          points={isLong
            ? `165,${arrowTipY - 6} 159,${arrowTipY + 2} 171,${arrowTipY + 2}`
            : `165,${arrowTipY + 6} 159,${arrowTipY - 2} 171,${arrowTipY - 2}`}
          fill={dirColor} fillOpacity="0.7"
        />
        {/* Direction badge */}
        <rect x="125" y={arrowMidY - 10} width="80" height="20" rx="10" fill={`${dirColor}18`} stroke={dirColor} strokeWidth="1" strokeOpacity="0.5" />
        <text x="165" y={arrowMidY + 4} textAnchor="middle" fill={dirColor} fontSize="11" fontFamily={F.mono} fontWeight="800" letterSpacing="0.08em">
          {dirIcon} {dirLabel}
        </text>

        {/* Volume S/R levels */}
        {volumeSR?.levels.slice(0, 6).map((lv, i) => {
          const isS = lv.type === 'support';
          const c = isS ? '#69f0ae' : '#ff5252';
          const sw = lv.strength === 3 ? 1.5 : lv.strength === 2 ? 1 : 0.5;
          const label = `${isS ? 'S' : 'R'}${i + 1} (${lv.volumeScore.toFixed(1)}x)`;
          return (
            <g key={`sr-${i}`}>
              <line x1="48" y1={toY(lv.price)} x2="298" y2={toY(lv.price)} stroke={c} strokeWidth={sw} strokeDasharray="3,4" strokeOpacity="0.6" />
              <text x="302" y={toY(lv.price) + 3} textAnchor="start" fill={c} fontSize="7" fontFamily="monospace" opacity="0.8">{label}</text>
            </g>
          );
        })}

        {/* Price level lines */}
        {lines.map((l, i) => (
          <g key={i}>
            <line x1="48" y1={toY(l.p)} x2="298" y2={toY(l.p)} stroke={l.c} strokeWidth={l.d ? 1.2 : 2} strokeDasharray={l.d ? "5,4" : "none"} />
            <text x="44" y={toY(l.p) + 3.5} textAnchor="end" fill={l.c} fontSize="8.5" fontFamily="monospace" fontWeight={l.d ? 400 : 700}>{l.lb}</text>
            <text x="302" y={toY(l.p) + 3.5} textAnchor="start" fill={l.c} fontSize="8.5" fontFamily="monospace">{fmt(l.p, 2)}</text>
          </g>
        ))}

        {/* Entry signal badge (top) */}
        <rect x="90" y="2" width="190" height="22" rx="11" fill={`${signalColor}18`} stroke={signalColor} strokeWidth="1" strokeOpacity="0.6" />
        {hasSignal && <circle cx="102" cy="13" r="4" fill={signalColor} opacity="0.9"><animate attributeName="opacity" values="0.9;0.3;0.9" dur="1.5s" repeatCount="indefinite" /></circle>}
        <text x="185" y="17" textAnchor="middle" fill={signalColor} fontSize="10" fontFamily={F.mono} fontWeight="700" letterSpacing="0.05em">
          {hasSignal ? `SIGNAL: ${signalLabel}` : 'NO SIGNAL'} (Z={z.toFixed(2)})
        </text>

        {/* Z-Zone badge (bottom) */}
        <rect x="48" y={svgH - 22} width="250" height="18" rx="4" fill={`${zoneColor}12`} stroke={`${zoneColor}40`} strokeWidth="0.5" />
        <text x="55" y={svgH - 10} fill={zoneColor} fontSize="8.5" fontFamily="monospace" fontWeight="600">
          Z-Zone: {zZone} {zoneTag} | 회귀확률 {(revertProb * 100).toFixed(0)}%
        </text>
      </svg>
    </div>
  );
}

