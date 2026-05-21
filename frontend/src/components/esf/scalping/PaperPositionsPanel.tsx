/**
 * PaperPositionsPanel — Decision Engine GO로 생성된 OPEN paper position 트래커.
 *
 * 표시:
 *   - ticker / direction / entry / SL / TP / last / unrealized PnL / age / 수동 close
 *
 * 데이터:
 *   - useESFuturesScalp.openPaperPositions (10s polling fallback)
 *   - useESFuturesScalp.paperRisk (오늘 누적 paper PnL, 한도)
 */

import { useMemo } from 'react';
import type { FuturesPaperPosition, PaperRiskStatus } from '@lib/api';

interface Props {
  positions: FuturesPaperPosition[];
  paperRisk: PaperRiskStatus | null;
  onClose: (positionId: string) => void;
  disabled?: boolean;
}

function fmt(v: number | null | undefined, d = 2): string {
  if (v === null || v === undefined || isNaN(v) || !isFinite(v)) return '—';
  return v.toFixed(d);
}

function fmtUSD(v: number | null | undefined): string {
  if (v === null || v === undefined || isNaN(v) || !isFinite(v)) return '—';
  const sign = v >= 0 ? '+' : '-';
  return `${sign}$${Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function computeUnrealizedPnl(p: FuturesPaperPosition): number {
  if (p.last_price === null) return 0;
  const mult = p.direction === 'LONG' ? 1 : -1;
  return (p.last_price - p.entry_price) * p.contracts * p.contract_multiplier * mult;
}

function computeAge(openedAt: string): string {
  const opened = new Date(openedAt).getTime();
  const now = Date.now();
  const mins = Math.floor((now - opened) / 60000);
  if (mins < 60) return `${mins}m`;
  const hours = Math.floor(mins / 60);
  const rem = mins % 60;
  return `${hours}h${rem}m`;
}

export function PaperPositionsPanel({ positions, paperRisk, onClose, disabled }: Props) {
  const sorted = useMemo(
    () => [...positions].sort((a, b) => b.opened_at.localeCompare(a.opened_at)),
    [positions],
  );

  const riskPctOfLimit = paperRisk && paperRisk.daily_loss_limit !== 0
    ? Math.min(100, Math.max(0, (paperRisk.realized_pnl_today / paperRisk.daily_loss_limit) * 100))
    : 0;

  return (
    <div className="esfu-panel" style={{ marginTop: 12 }}>
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12,
      }}>
        <h3 className="esfu-panel-title" style={{ margin: 0 }}>
          Paper Positions ({sorted.length} OPEN)
        </h3>
        {paperRisk && (
          <div style={{ display: 'flex', gap: 16, fontSize: 12, color: '#aaa' }}>
            <span>
              오늘 PnL: <b style={{ color: paperRisk.realized_pnl_today >= 0 ? '#00e676' : '#ff1744' }}>
                {fmtUSD(paperRisk.realized_pnl_today)}
              </b>
            </span>
            <span>
              한도: <b>{fmtUSD(paperRisk.daily_loss_limit)}</b>
              {paperRisk.limit_reached && <span style={{ color: '#ff1744', marginLeft: 4 }}>⛔ HIT</span>}
            </span>
            <span>
              슬롯: <b>{paperRisk.open_count}/{paperRisk.max_concurrent}</b>
            </span>
          </div>
        )}
      </div>

      {paperRisk && paperRisk.realized_pnl_today < 0 && (
        <div style={{
          height: 4, background: 'rgba(255,255,255,0.05)',
          borderRadius: 2, marginBottom: 12, overflow: 'hidden',
        }}>
          <div style={{
            height: '100%',
            width: `${riskPctOfLimit}%`,
            background: riskPctOfLimit > 80 ? '#ff1744' : '#ffab40',
            transition: 'width 0.3s',
          }} />
        </div>
      )}

      {sorted.length === 0 ? (
        <div style={{ color: '#666', fontSize: 13, padding: '24px 0', textAlign: 'center' }}>
          오픈된 페이퍼 포지션이 없습니다. Decision Engine GO 상태에서 "Place Paper Trade"를 클릭하세요.
        </div>
      ) : (
        <table style={{ width: '100%', fontSize: 12, color: '#ccc', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.08)', color: '#888' }}>
              <th style={{ padding: '6px 8px', textAlign: 'left' }}>Ticker</th>
              <th style={{ padding: '6px 8px', textAlign: 'center' }}>Dir</th>
              <th style={{ padding: '6px 8px', textAlign: 'right' }}>Entry</th>
              <th style={{ padding: '6px 8px', textAlign: 'right' }}>SL</th>
              <th style={{ padding: '6px 8px', textAlign: 'right' }}>TP</th>
              <th style={{ padding: '6px 8px', textAlign: 'right' }}>Last</th>
              <th style={{ padding: '6px 8px', textAlign: 'right' }}>Unrealized</th>
              <th style={{ padding: '6px 8px', textAlign: 'center' }}>Ct</th>
              <th style={{ padding: '6px 8px', textAlign: 'center' }}>Age</th>
              <th style={{ padding: '6px 8px', textAlign: 'center' }}></th>
            </tr>
          </thead>
          <tbody>
            {sorted.map(p => {
              const unrealized = computeUnrealizedPnl(p);
              const dirColor = p.direction === 'LONG' ? '#00e676' : '#ff1744';
              return (
                <tr key={p.position_id} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                  <td style={{ padding: '8px', fontFamily: "'IBM Plex Mono', monospace" }}>{p.ticker}</td>
                  <td style={{ padding: '8px', textAlign: 'center', color: dirColor, fontWeight: 700 }}>
                    {p.direction}
                  </td>
                  <td style={{ padding: '8px', textAlign: 'right', fontFamily: "'IBM Plex Mono', monospace" }}>
                    {fmt(p.entry_price)}
                  </td>
                  <td style={{ padding: '8px', textAlign: 'right', color: '#ff8a80', fontFamily: "'IBM Plex Mono', monospace" }}>
                    {fmt(p.stop_loss)}
                  </td>
                  <td style={{ padding: '8px', textAlign: 'right', color: '#69f0ae', fontFamily: "'IBM Plex Mono', monospace" }}>
                    {fmt(p.take_profit)}
                  </td>
                  <td style={{ padding: '8px', textAlign: 'right', fontFamily: "'IBM Plex Mono', monospace" }}>
                    {fmt(p.last_price)}
                  </td>
                  <td style={{
                    padding: '8px', textAlign: 'right',
                    color: unrealized >= 0 ? '#00e676' : '#ff1744',
                    fontFamily: "'IBM Plex Mono', monospace", fontWeight: 600,
                  }}>
                    {fmtUSD(unrealized)}
                  </td>
                  <td style={{ padding: '8px', textAlign: 'center' }}>{p.contracts}</td>
                  <td style={{ padding: '8px', textAlign: 'center', color: '#888' }}>
                    {computeAge(p.opened_at)}
                  </td>
                  <td style={{ padding: '8px', textAlign: 'center' }}>
                    <button
                      onClick={() => onClose(p.position_id)}
                      disabled={disabled}
                      style={{
                        padding: '4px 10px',
                        background: 'rgba(255,23,68,0.1)',
                        color: '#ff8a80',
                        border: '1px solid rgba(255,23,68,0.3)',
                        borderRadius: 4, cursor: disabled ? 'not-allowed' : 'pointer',
                        fontSize: 11,
                      }}
                    >Close</button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
