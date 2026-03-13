/**
 * PollingControl — 실시간 폴링 상태 표시 + 제어 UI
 *
 * 기능:
 * - 상태 LED (green=LIVE, orange=RETRY, red=STALE, gray=OFF)
 * - POLLING ON/OFF 토글
 * - 간격 선택 (10s / 30s / 60s)
 * - 마지막 업데이트 시간
 * - 수동 새로고침 버튼
 */

import { useState, useEffect } from 'react';
import { K, F } from '../lib/scalpEngine';
import type { PollingStatus } from '../hooks/usePolling';

interface PollingControlProps {
  enabled: boolean;
  onToggle: (v: boolean) => void;
  interval: number;
  onIntervalChange: (ms: number) => void;
  status: PollingStatus;
  lastUpdated: number | null;
  consecutiveErrors: number;
  onRefresh: () => void;
  compact?: boolean;
}

const INTERVALS = [
  { label: '10s', value: 10000 },
  { label: '30s', value: 30000 },
  { label: '60s', value: 60000 },
];

export function PollingControl({
  enabled, onToggle, interval, onIntervalChange,
  status, lastUpdated, consecutiveErrors, onRefresh,
  compact = false,
}: PollingControlProps) {
  // 마지막 업데이트 시간 실시간 표시 (only tick when polling is active)
  const [, tick] = useState(0);
  useEffect(() => {
    if (!lastUpdated || !enabled) return;
    const id = setInterval(() => tick(v => v + 1), 1000);
    return () => clearInterval(id);
  }, [lastUpdated, enabled]);

  const statusColor =
    status === 'polling' ? K.grn :
    status === 'error' ? '#ff9800' :
    status === 'stale' ? K.red :
    '#555';

  const statusLabel =
    status === 'polling' ? 'LIVE' :
    status === 'error' ? `RETRY(${consecutiveErrors})` :
    status === 'stale' ? 'STALE' :
    'OFF';

  const timeSince = lastUpdated
    ? `${Math.round((Date.now() - lastUpdated) / 1000)}s ago`
    : '—';

  const btnBase: React.CSSProperties = {
    padding: compact ? '2px 6px' : '3px 8px',
    fontSize: compact ? 8 : 9,
    fontFamily: F.mono,
    borderRadius: 4,
    cursor: 'pointer',
    transition: 'all 0.15s',
  };

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: compact ? 4 : 8, flexWrap: 'wrap',
      padding: compact ? '3px 8px' : '5px 12px',
      fontSize: compact ? 9 : 10,
      fontFamily: F.mono,
      background: `${statusColor}08`,
      border: `1px solid ${statusColor}30`,
      borderRadius: 8,
    }}>
      {/* Status LED */}
      <span style={{
        width: 7, height: 7, borderRadius: '50%',
        background: statusColor,
        boxShadow: enabled ? `0 0 8px ${statusColor}80` : 'none',
        flexShrink: 0,
      }} />

      {/* Toggle button */}
      <button onClick={() => onToggle(!enabled)} style={{
        ...btnBase,
        background: enabled ? `${K.grn}18` : 'transparent',
        border: `1px solid ${enabled ? K.grn : '#444'}`,
        color: enabled ? K.grn : '#666',
        fontWeight: 700,
      }}>
        {enabled ? '● POLLING' : '○ POLLING'}
      </button>

      {/* Interval selector */}
      {enabled && (
        <div style={{ display: 'flex', gap: 2 }}>
          {INTERVALS.map(opt => (
            <button key={opt.value}
              onClick={() => onIntervalChange(opt.value)}
              style={{
                ...btnBase,
                background: interval === opt.value ? '#00bcd415' : 'transparent',
                border: `1px solid ${interval === opt.value ? '#00bcd4' : '#333'}`,
                color: interval === opt.value ? '#00bcd4' : '#555',
                fontWeight: interval === opt.value ? 700 : 400,
              }}>
              {opt.label}
            </button>
          ))}
        </div>
      )}

      {/* Status label */}
      <span style={{ color: statusColor, fontWeight: 700, fontSize: compact ? 8 : 9 }}>
        {statusLabel}
      </span>

      {/* Last updated */}
      {lastUpdated && (
        <span style={{ color: '#666', fontSize: compact ? 8 : 9 }}>
          {timeSince}
        </span>
      )}

      {/* Refresh button */}
      <button onClick={onRefresh} title="수동 새로고침" style={{
        ...btnBase,
        background: 'transparent',
        border: `1px solid #333`,
        color: '#888',
        lineHeight: 1,
      }}>
        ↻
      </button>
    </div>
  );
}
