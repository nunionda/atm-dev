/**
 * VolumeProfileChart — extracted from ESFuturesScalping page.
 *
 * Phase 3.C 분할: pages/ESFuturesScalping.tsx → components/esf/scalping/VolumeProfileChart.tsx
 */

import type { VolumeProfileData } from '@lib/api';

export function VolumeProfileChart({ vp, currentPrice }: { vp: VolumeProfileData; currentPrice: number }) {
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

