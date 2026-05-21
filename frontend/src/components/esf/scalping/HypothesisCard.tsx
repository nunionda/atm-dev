/**
 * HypothesisCard — extracted from ESFuturesScalping page.
 *
 * Phase 3.C 분할: pages/ESFuturesScalping.tsx → components/esf/scalping/HypothesisCard.tsx
 */

import type { ESFHypothesis } from '@lib/api';
import { fmtPts } from './format';

export function HypothesisCard({ hypothesis: h, onRecordResult, onSkip }: {
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

