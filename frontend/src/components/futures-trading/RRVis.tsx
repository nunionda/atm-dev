/**
 * RRVis — extracted from FuturesTrading page.
 *
 * Phase 3.C 분할: pages/FuturesTrading.tsx → components/futures-trading/RRVis.tsx
 */

import { fmt } from '@lib/futuresScalpEngine';

export function RRVis({ entry, sl, tp15, tp2, tp3, cfg, currentPrice, magneticMA }: {
  entry: number; sl: number; tp15: number; tp2: number; tp3: number;
  cfg: { ptVal: number }; currentPrice?: number; magneticMA?: number;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const risk = Math.abs(entry - sl);
  const pnl = (p: number) => { const pts = Math.abs(p - entry); return { pts, usd: pts * cfg.ptVal }; };
  const rrRatio  = risk > 0 ? (Math.abs(tp15 - entry) / risk).toFixed(1) : '—';
  const rr3      = risk > 0 ? (Math.abs(tp3  - entry) / risk).toFixed(1) : '—';
  const isLong   = tp15 > entry;

  useEffect(() => {
    if (!containerRef.current) return;
    containerRef.current.innerHTML = '';
    const w = containerRef.current.clientWidth;

    const chart = createChart(containerRef.current, {
      width: w, height: 220,
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: '#9ca3af',
        fontFamily: "'IBM Plex Mono', monospace",
        fontSize: 11,
      },
      grid: {
        vertLines: { visible: false },
        horzLines: { color: 'rgba(255,255,255,0.04)' },
      },
      timeScale: { visible: false },
      rightPriceScale: {
        borderColor: 'rgba(255,255,255,0.12)',
        scaleMargins: { top: 0.08, bottom: 0.08 },
      },
      crosshair: { vertLine: { visible: false }, horzLine: { color: 'rgba(255,255,255,0.15)', width: 1 as const, style: 3 as const, labelBackgroundColor: '#334155' } },
      handleScroll: false,
      handleScale: false,
    });

    // ── 합성 타임 포인트 (시간축 숨김, 스케일 앵커용) ──
    const T1 = 100 as Time, T2 = 200 as Time;
    const all = [sl, tp3, ...(magneticMA ? [magneticMA] : []), ...(currentPrice ? [currentPrice] : [])];
    const lo = Math.min(...all), hi = Math.max(...all), rng = hi - lo || 1, pad = rng * 0.12;

    // ── 투명 앵커 시리즈 (Y 스케일 범위 확보) ──
    const anchor = chart.addLineSeries({ color: 'transparent', lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
    anchor.setData([{ time: T1, value: lo - pad }, { time: T2, value: hi + pad }]);

    // ── 존 배경 (entry 기준: 위=Reward 초록, 아래=Risk 빨강) ──
    // BaselineSeries: baseValue=entry → 위쪽 green fill, 아래쪽 red fill
    const zoneSeries = chart.addBaselineSeries({
      baseValue: { type: 'price', price: entry },
      topFillColor1: 'rgba(0,230,118,0.13)',
      topFillColor2: 'rgba(0,230,118,0.04)',
      bottomFillColor1: 'rgba(255,23,68,0.04)',
      bottomFillColor2: 'rgba(255,23,68,0.14)',
      topLineColor: 'transparent',
      bottomLineColor: 'transparent',
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    });
    // 평탄 선을 entry에 고정 → fill이 entry 위/아래로 정확히 나뉨
    zoneSeries.setData([{ time: T1, value: entry }, { time: T2, value: entry }]);

    // ── Price Lines ──
    const { pts: sl_pts, usd: sl_usd } = pnl(sl);
    const { pts: tp15_pts, usd: tp15_usd } = pnl(tp15);
    const { pts: tp2_pts,  usd: tp2_usd  } = pnl(tp2);
    const { pts: tp3_pts,  usd: tp3_usd  } = pnl(tp3);

    anchor.createPriceLine({ price: entry, color: '#60a5fa', lineWidth: 2, lineStyle: 0, axisLabelVisible: true, title: '▶ ENTRY' });
    anchor.createPriceLine({ price: sl,    color: '#f87171', lineWidth: 2, lineStyle: 2, axisLabelVisible: true, title: `STOP  −${fmt(sl_pts,1)}p / −$${sl_usd.toFixed(0)}` });
    anchor.createPriceLine({ price: tp15,  color: '#6ee7b7', lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: `TP 1.5R  +${fmt(tp15_pts,1)}p / +$${tp15_usd.toFixed(0)}` });
    anchor.createPriceLine({ price: tp2,   color: '#34d399', lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: `TP 2R    +${fmt(tp2_pts,1)}p / +$${tp2_usd.toFixed(0)}` });
    anchor.createPriceLine({ price: tp3,   color: '#10b981', lineWidth: 2, lineStyle: 0, axisLabelVisible: true, title: `TP 3R    +${fmt(tp3_pts,1)}p / +$${tp3_usd.toFixed(0)}` });

    if (magneticMA && magneticMA > 0)
      anchor.createPriceLine({ price: magneticMA, color: '#fb923c', lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: 'Mag MA' });

    if (currentPrice && Math.abs(currentPrice - entry) > 0.25)
      anchor.createPriceLine({ price: currentPrice, color: 'rgba(255,255,255,0.55)', lineWidth: 1, lineStyle: 3, axisLabelVisible: true, title: 'NOW' });

    chart.timeScale().fitContent();

    const handleResize = () => {
      if (containerRef.current) chart.applyOptions({ width: containerRef.current.clientWidth });
    };
    window.addEventListener('resize', handleResize);
    return () => { window.removeEventListener('resize', handleResize); chart.remove(); };
  }, [entry, sl, tp15, tp2, tp3, magneticMA, currentPrice, cfg.ptVal]);

  // ── 렌더 ──
  const MONO = "'IBM Plex Mono', monospace";
  return (
    <div className="scalp-rr-map">
      {/* R:R 헤더 바 */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '2px 4px 8px', fontFamily: MONO }}>
        <div style={{ display: 'flex', gap: 16, fontSize: '0.7rem', color: 'rgba(255,255,255,0.35)' }}>
          <span style={{ color: '#f87171' }}>SL {fmt(sl, 2)}</span>
          <span style={{ color: '#6ee7b7' }}>TP1 {fmt(tp15, 2)}</span>
          <span style={{ color: '#34d399' }}>TP2 {fmt(tp2, 2)}</span>
          <span style={{ color: '#10b981' }}>TP3 {fmt(tp3, 2)}</span>
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'baseline' }}>
          <span style={{ color: '#60a5fa', fontWeight: 700, fontSize: '0.85rem' }}>R:R 1:{rrRatio}</span>
          <span style={{ color: 'rgba(16,185,129,0.6)', fontSize: '0.7rem' }}>(max 1:{rr3})</span>
        </div>
      </div>
      {/* lightweight-charts 컨테이너 */}
      <div ref={containerRef} />
    </div>
  );
}


