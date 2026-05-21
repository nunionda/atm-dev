/**
 * SessionPanel — extracted from ESFuturesScalping page.
 *
 * Phase 3.C 분할: pages/ESFuturesScalping.tsx → components/esf/scalping/SessionPanel.tsx
 */

import type { ESFSessionStatus } from '@lib/api';
import { timeAgo } from './format';

export function SessionPanel({ session, isMicro, onToggle }: {
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


