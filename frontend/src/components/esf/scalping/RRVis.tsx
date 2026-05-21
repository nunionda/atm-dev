/**
 * RRVis — extracted from ESFuturesScalping page.
 *
 * Phase 3.C 분할: pages/ESFuturesScalping.tsx → components/esf/scalping/RRVis.tsx
 */

import { clamp, fmt } from '@lib/futuresScalpEngine';
// Note: FuturesTrading.css is loaded by the parent page (ESFuturesScalping).

// ══════════════════════════════════════════
// Trend Regime Panel
// ══════════════════════════════════════════

export function RRVis({ entry, sl, tp15, tp2, tp3, cfg, currentPrice, magneticMA, vwatrZone, lockedSL, lockedTP }: {
  entry: number; sl: number; tp15: number; tp2: number; tp3: number;
  cfg: { ptVal: number }; currentPrice?: number; magneticMA?: number;
  vwatrZone?: { ma_value: number; zone_type: string; ma_type: string; ma_period: number; strength: number } | null;
  /** 활성 OPEN paper position의 canonical SL — 표시되면 ATR-sl은 informational ghost로 강등 */
  lockedSL?: number | null;
  /** 활성 OPEN paper position의 canonical TP */
  lockedTP?: number | null;
}) {
  const hasLocked = lockedSL != null && lockedTP != null;
  const all = [sl, entry, tp15, tp2, tp3];
  if (currentPrice) all.push(currentPrice);
  if (magneticMA) all.push(magneticMA);
  if (vwatrZone) all.push(vwatrZone.ma_value);
  if (lockedSL != null) all.push(lockedSL);
  if (lockedTP != null) all.push(lockedTP);
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
  // hasLocked인 경우 SL/TP 라인을 ghost(투명도↓, dashed↑)로 강등 — Locked 라인이 별도로 그려짐
  const isLong = tp15 > entry;
  const ghostOpacity = hasLocked ? 0.25 : 1;
  const levels = [
    { p: sl,   lb: hasLocked ? 'ATR·SL (info)' : 'STOP',  tag: '1R',   c: '#ff1744', w: 1.5, dash: hasLocked ? '2,4' : '6,4',  marker: 'x'      as const, opacity: ghostOpacity },
    { p: entry,lb: 'ENTRY', tag: '',     c: '#3b82f6', w: 2.5, dash: 'none', marker: 'arrow'   as const, opacity: 1 },
    { p: tp15, lb: '1.5R',  tag: '1.5R', c: '#69f0ae', w: 1.2, dash: '4,3',  marker: 'none'    as const, opacity: ghostOpacity },
    { p: tp2,  lb: '2R',    tag: '2R',   c: '#00e676', w: 1.5, dash: '5,3',  marker: 'diamond' as const, opacity: ghostOpacity },
    { p: tp3,  lb: '3R',    tag: '3R',   c: '#10b981', w: 2,   dash: 'none', marker: 'dot'     as const, opacity: ghostOpacity },
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
                opacity={isEntry ? 1 : 0.85 * l.opacity}
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

        {/* ── Locked SL/TP (canonical from backend) ── */}
        {hasLocked && lockedSL != null && (
          <g>
            <line x1={LM} y1={toY(lockedSL)} x2={W - RM} y2={toY(lockedSL)}
              stroke="#ff1744" strokeWidth="2.5" strokeLinecap="round" />
            <text x={W - RM + 4} y={toY(lockedSL) - 4} textAnchor="start" fill="#ff1744"
              fontSize="9" fontFamily={MONO} fontWeight="800">LOCKED SL {fmt(lockedSL, 2)}</text>
          </g>
        )}
        {hasLocked && lockedTP != null && (
          <g>
            <line x1={LM} y1={toY(lockedTP)} x2={W - RM} y2={toY(lockedTP)}
              stroke="#00e676" strokeWidth="2.5" strokeLinecap="round" />
            <text x={W - RM + 4} y={toY(lockedTP) - 4} textAnchor="start" fill="#00e676"
              fontSize="9" fontFamily={MONO} fontWeight="800">LOCKED TP {fmt(lockedTP, 2)}</text>
          </g>
        )}

        {/* ── Zone labels ── */}
        <text x={LM + 6} y={lossTop + lossH / 2 + 3} fill="rgba(255,23,68,0.28)" fontSize="9"
          fontFamily={MONO} fontWeight="700" letterSpacing="0.08em">RISK ZONE</text>
        <text x={LM + 6} y={profTop + profH / 2 + 3} fill="rgba(0,230,118,0.28)" fontSize="9"
          fontFamily={MONO} fontWeight="700" letterSpacing="0.08em">REWARD ZONE</text>

        {/* ── ATR-informational badge (no locked position) ── */}
        {!hasLocked && (
          <g transform={`translate(${W - RM - 92}, ${TM + 10})`}>
            <rect x="0" y="0" width="88" height="14" rx="3"
              fill="rgba(59,130,246,0.08)" stroke="rgba(59,130,246,0.25)" strokeWidth="0.5" />
            <text x="44" y="10" textAnchor="middle" fill="#3b82f6"
              fontSize="7" fontFamily={MONO} fontWeight="700">
              ATR-INFORMATIONAL
            </text>
          </g>
        )}

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
