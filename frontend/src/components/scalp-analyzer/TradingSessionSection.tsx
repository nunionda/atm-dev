/**
 * TradingSessionSection — 트레이딩 세션 라이프사이클 패널.
 *
 * Phase D 추가 분할: pages/ScalpAnalyzer.tsx → components/scalp-analyzer/TradingSessionSection.tsx
 *
 * Stateful section. session state + 4개 핸들러를 prop으로 받아 위임. 페이지에서
 * useState/useCallback으로 관리되는 값들을 그대로 표시·트리거하는 stateless wrapper.
 */

import { K, fmtMoney, type ScalpInputs, type ScalpResult } from '@lib/scalpEngine';
import {
    checkAlerts, evaluatePosition, suggestExitAction, formatHoldTime,
    PHASE_LABELS, PHASE_COLORS,
    type SessionState,
} from '@lib/tradingSession';
import { Sec } from './Sec';
import { Met } from './Met';

export interface TradingSessionSectionProps {
    inputs: ScalpInputs;
    calc: ScalpResult;
    session: SessionState | null;
    setSession: (next: SessionState | null) => void;
    entryFormOpen: boolean;
    setEntryFormOpen: (v: boolean) => void;
    entryPrice: string;
    setEntryPrice: (v: string) => void;
    entryContracts: string;
    setEntryContracts: (v: string) => void;
    onStartSession: () => void;
    onRecordEntry: () => void;
    onRecordExit: (reason: string) => void;
    onEndSession: () => void;
}

export function TradingSessionSection({
    inputs, calc, session, setSession,
    entryFormOpen, setEntryFormOpen,
    entryPrice, setEntryPrice, entryContracts, setEntryContracts,
    onStartSession, onRecordEntry, onRecordExit, onEndSession,
}: TradingSessionSectionProps) {
    return (
        <div className="scalp-box">
            <Sec
                icon="📋"
                title="트레이딩 세션 (Trading Session)"
                tag={session ? session.phase : 'OFF'}
                tagC={session ? PHASE_COLORS[session.phase] : K.dim}
            />
            {!session ? (
                <button className="scalp-session-btn primary" style={{ width: '100%', marginTop: 8 }} onClick={onStartSession}>
                    🚀 세션 시작 — 시나리오 생성
                </button>
            ) : (
                <>
                    <div className="scalp-session-bar">
                        <span className={`scalp-session-phase ${session.phase}`}>{PHASE_LABELS[session.phase]}</span>
                        <span style={{ fontSize: 10, color: K.dim }}>{formatHoldTime(Date.now() - session.startedAt)}</span>
                        <div style={{ flex: 1 }} />
                        {(session.phase === 'ALERT' || session.phase === 'WATCHING') && (
                            <button
                                className="scalp-session-btn"
                                onClick={() => { setEntryFormOpen(true); setEntryPrice(inputs.currentPrice.toFixed(2)); }}
                            >
                                📝 진입 기록
                            </button>
                        )}
                        {(session.phase === 'ENTERED' || session.phase === 'MANAGING') && (
                            <button className="scalp-session-btn danger" onClick={() => onRecordExit('MANUAL')}>
                                ✕ 청산 기록
                            </button>
                        )}
                        {session.phase === 'CLOSED' && (
                            <button className="scalp-session-btn" onClick={() => { setSession(null); onStartSession(); }}>
                                🔄 새 세션
                            </button>
                        )}
                        <button className="scalp-session-btn danger" onClick={onEndSession} style={{ fontSize: 10 }}>종료</button>
                    </div>

                    {/* Entry Form */}
                    {entryFormOpen && (
                        <div className="scalp-entry-form">
                            <label>진입 가격<input value={entryPrice} onChange={e => setEntryPrice(e.target.value)} /></label>
                            <label>계약 수<input value={entryContracts} onChange={e => setEntryContracts(e.target.value)} /></label>
                            <button
                                className="scalp-session-btn primary"
                                onClick={onRecordEntry}
                                style={{ gridColumn: 'span 2', marginTop: 4 }}
                            >
                                ✅ 진입 확정 ({calc.isLong ? 'LONG' : 'SHORT'})
                            </button>
                        </div>
                    )}

                    {/* Scenarios (PLANNING / WATCHING / ALERT) */}
                    {['PLANNING', 'WATCHING', 'ALERT'].includes(session.phase) && session.scenarios.length > 0 && (
                        <>
                            <div className="scalp-opt-divider">🎯 오늘의 시나리오 (Game Plan)</div>
                            {session.scenarios.slice(0, 4).map(sc => (
                                <div key={sc.id} className={`scalp-scenario-card ${sc.confidence}`}>
                                    <div className="scalp-scenario-header">
                                        <span className="scalp-scenario-name">{sc.type === 'LONG' ? '▲' : '▼'} {sc.name}</span>
                                        <span className={`scalp-scenario-badge ${sc.confidence}`}>{sc.confidence}</span>
                                    </div>
                                    <div className="scalp-scenario-detail">
                                        📍 트리거: <span>{sc.trigger}</span><br />
                                        ✅ 조건: {sc.condition}<br />
                                        🎯 TP: <span>{sc.targetPrice.toFixed(2)}</span> │ 🛑 SL: <span>{sc.stopPrice.toFixed(2)}</span> │ R:R <span>{sc.rr}:1</span>
                                    </div>
                                </div>
                            ))}
                        </>
                    )}

                    {/* Key Level Monitor (WATCHING / ALERT) */}
                    {['WATCHING', 'ALERT'].includes(session.phase) && session.keyLevels.length > 0 && (
                        <>
                            <div className="scalp-opt-divider">📍 키 레벨 모니터</div>
                            {(() => {
                                const alerts = session.activeAlerts.length > 0
                                    ? session.activeAlerts
                                    : checkAlerts(inputs.currentPrice, session.keyLevels);
                                const sortedAlerts = [...alerts].sort((a, b) => b.level.price - a.level.price);
                                let currentInserted = false;
                                return sortedAlerts.map((alert, i) => {
                                    const items = [];
                                    if (!currentInserted && alert.level.price < inputs.currentPrice) {
                                        items.push(
                                            <div key="current" className="scalp-level-current">
                                                ── {inputs.currentPrice.toFixed(2)} (현재가) ──
                                            </div>,
                                        );
                                        currentInserted = true;
                                    }
                                    const dotColor = alert.level.type === 'SUPPORT'
                                        ? K.grn
                                        : alert.level.type === 'RESISTANCE' ? K.red : K.acc;
                                    items.push(
                                        <div key={i} className="scalp-level-row">
                                            <span className="scalp-level-dot" style={{ background: dotColor }} />
                                            <span className="scalp-level-price">{alert.level.price.toFixed(2)}</span>
                                            <span className="scalp-level-label">{alert.level.label} ({'★'.repeat(alert.level.strength)})</span>
                                            <span className="scalp-level-dist">{alert.proximityPct > 0 ? `${alert.proximityPct.toFixed(2)}%` : '—'}</span>
                                            <span className={`scalp-level-status ${alert.status}`}>{alert.status.replace('_', ' ')}</span>
                                        </div>,
                                    );
                                    return items;
                                });
                            })()}
                        </>
                    )}

                    {/* Position Management (ENTERED / MANAGING) */}
                    {session.entry && ['ENTERED', 'MANAGING'].includes(session.phase) && (() => {
                        const posEval = evaluatePosition(session.entry!, inputs.currentPrice, calc, calc.cfg);
                        const exitSugg = suggestExitAction(session.entry!, inputs.currentPrice, calc);
                        return (
                            <>
                                <div className="scalp-opt-divider">📊 포지션 관리</div>
                                <div className={`scalp-position-panel ${session.entry!.direction}`}>
                                    <div className="scalp-flex">
                                        <Met label="방향" value={`${session.entry!.direction} ${session.entry!.contracts}계약`} color={session.entry!.direction === 'LONG' ? K.grn : K.red} />
                                        <Met label="진입가" value={session.entry!.price.toFixed(2)} />
                                        <Met label="P&L" value={`${posEval.pnlPoints >= 0 ? '+' : ''}${posEval.pnlPoints}pt`} color={posEval.pnlPoints >= 0 ? K.grn : K.red} big />
                                        <Met label="R배수" value={`${posEval.currentR >= 0 ? '+' : ''}${posEval.currentR}R`} color={posEval.currentR >= 0 ? K.grn : K.red} />
                                    </div>
                                    <div className="scalp-flex" style={{ marginTop: 6 }}>
                                        <Met label="스탑 모드" value={posEval.stopMode} />
                                        <Met label="현재 SL" value={posEval.currentSL.toFixed(2)} color={K.red} />
                                        <Met label="보유시간" value={formatHoldTime(posEval.holdMs)} />
                                        <Met label="P&L ($)" value={fmtMoney(Math.abs(posEval.pnlUSD), calc.cfg.sym)} color={posEval.pnlUSD >= 0 ? K.grn : K.red} />
                                    </div>
                                    <div className="scalp-position-action" style={{ marginTop: 8 }}>
                                        <span style={{ fontWeight: 600 }}>{posEval.action}</span><br />
                                        <span style={{ color: K.dim }}>{posEval.reason}</span>
                                    </div>
                                    {exitSugg.shouldExit && (
                                        <div style={{ marginTop: 6, padding: '6px 10px', background: 'rgba(255,23,68,0.08)', borderRadius: 4, fontSize: 11, color: K.red }}>
                                            ⚠ 청산 권고: {exitSugg.reason}
                                        </div>
                                    )}
                                </div>
                            </>
                        );
                    })()}

                    {/* Closed Result */}
                    {session.phase === 'CLOSED' && session.exitRecord && (
                        <>
                            <div className="scalp-opt-divider">✅ 세션 결과</div>
                            <div className="scalp-flex">
                                <Met label="결과" value={session.exitRecord.pnlPoints >= 0 ? 'WIN' : 'LOSS'} color={session.exitRecord.pnlPoints >= 0 ? K.grn : K.red} big />
                                <Met label="P&L" value={`${session.exitRecord.pnlPoints >= 0 ? '+' : ''}${session.exitRecord.pnlPoints}pt`} color={session.exitRecord.pnlPoints >= 0 ? K.grn : K.red} />
                                <Met label="P&L ($)" value={fmtMoney(Math.abs(session.exitRecord.pnlUSD), calc.cfg.sym)} color={session.exitRecord.pnlUSD >= 0 ? K.grn : K.red} />
                                <Met label="보유시간" value={formatHoldTime(session.exitRecord.holdDuration)} />
                                <Met label="사유" value={session.exitRecord.reason} />
                            </div>
                        </>
                    )}
                </>
            )}
        </div>
    );
}
