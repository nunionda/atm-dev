import React, { useState } from 'react';
import { useESFuturesScalp, type TabKey } from '@hooks/useESFuturesScalp';
import { useESFJournal } from '@hooks/useESFJournal';
import type { ESFHypothesis } from '@lib/api';
import {
  ASSETS, SAMPLE_CLOSE, SAMPLE_OHLC, clamp, fmt, fmtUSD, fmtPct,
  analyzeMA, analyzeATR, computeUnifiedStrategy,
} from '@lib/futuresScalpEngine';
import type {
  ESFAnalysis, ESFRegimeInfo, VolumeProfileData, ESFSessionStatus, ESFCandle, VWATRZone,
} from '@lib/api';
import type { DataMode, ScalpState } from '@hooks/useFuturesScalp';
import ESFIntradayChart, { type EntryPlan } from '@components/esf/ESFIntradayChart';
import ESFEquityCurve from '@components/esf/ESFEquityCurve';
import { EquityCurve } from '@components/performance/EquityCurve';
import { FuturesMonitorGrid } from '@components/esf/FuturesMonitorGrid';

// Phase 3.C extracted modules
import { fmtUSDLocal, fmtPts, fmtPctLocal, timeAgo } from '@components/esf/scalping/format';
import { REGIME_STYLES, STRATEGY_LABELS } from '@components/esf/scalping/constants';
import { LayerBar } from '@components/esf/scalping/LayerBar';
import { MetricCard } from '@components/esf/scalping/MetricCard';
import {
  ScalpNIn, ZBar, EVBar, KGauge, BasisBar,
} from '@components/esf/scalping/ScalpControls';
import { AMTPanel } from '@components/esf/scalping/AMTPanel';
import { VolumeProfileChart } from '@components/esf/scalping/VolumeProfileChart';
import { SessionPanel } from '@components/esf/scalping/SessionPanel';
import { SessionPnLChart } from '@components/esf/scalping/SessionPnLChart';
import { ExitReasonBars } from '@components/esf/scalping/ExitReasonBars';
import { RegimePanel } from '@components/esf/scalping/RegimePanel';
import { ScorePanel } from '@components/esf/scalping/ScorePanel';
import { SignalCard } from '@components/esf/scalping/SignalCard';
import { IndicatorPanel } from '@components/esf/scalping/IndicatorPanel';
import { StrategyDashboard } from '@components/esf/scalping/StrategyDashboard';
import { HypothesisCard } from '@components/esf/scalping/HypothesisCard';
import { RRVis } from '@components/esf/scalping/RRVis';
import { ScalpDecisionEngine } from '@components/esf/scalping/ScalpDecisionEngine';
import { PaperPositionsPanel } from '@components/esf/scalping/PaperPositionsPanel';
import { BacktestTabContent } from '@components/esf/scalping/BacktestTabContent';
import { StrategyProposalsPanel } from '@components/esf/scalping/StrategyProposalsPanel';

import './ESFuturesScalping.css';
// Reuse scalp section CSS from FuturesTrading
import './FuturesTrading.css';

// ══════════════════════════════════════════
// Trend Regime Panel
// ══════════════════════════════════════════

export function ESFuturesScalping() {
  const state = useESFuturesScalp();
  const {
    isMicro, setIsMicro, effectiveTicker,
    activeTab, setActiveTab,
    analysis, volumeProfile, sessionStatus, candles,
    loading, error, lastUpdated,
    chartInterval, setChartInterval, chartPeriod, setChartPeriod,
    activeSubcharts, setActiveSubcharts,
    refresh, scalp,
    backendDirection, directionAgrees, disagreementReason, canTrade,
    openPaperPositions, activePosition, paperRisk,
    placingPaperOrder, paperOrderError,
    placePaperTrade, closePaperTrade,
    strategyMode, setStrategyMode,
  } = state;

  const journal = useESFJournal(effectiveTicker);

  const tabs: { key: TabKey; label: string }[] = [
    { key: 'strategy', label: "Today's Strategy" },
    { key: 'analysis', label: 'Live Analysis' },
    { key: 'decision', label: 'Decision Engine' },
    { key: 'proposals', label: '📋 4-Ticker Proposals' },
    { key: 'backtest', label: 'Backtest' },
    { key: 'evolution', label: 'Evolution' },
  ];

  return (
    <div className="esfu-page container">
      <div className="esfu-header">
        <h1 className="page-title">Futures</h1>
        <p className="page-subtitle">오늘의 단타 스캘핑 전략은? — 가설 → 검증 → 분석 → 진화</p>
      </div>

      {/* 4-Instrument Monitor (2x2) — ES / NQ / CL / GC */}
      <FuturesMonitorGrid />

      {/* Top Bar */}
      <div className="esfu-top-bar">
        <span className="esfu-ticker-label">{effectiveTicker}</span>
        {analysis && (
          <>
            <span className="esfu-price">{fmtPts(analysis.entry_price)}</span>
            <span className="esfu-badge" style={{
              background: analysis.direction === 'LONG' ? 'rgba(46,204,113,0.2)' :
                           analysis.direction === 'SHORT' ? 'rgba(231,76,60,0.2)' : 'rgba(149,165,166,0.15)',
              color: analysis.direction === 'LONG' ? '#2ecc71' :
                     analysis.direction === 'SHORT' ? '#e74c3c' : '#95a5a6',
            }}>
              {analysis.direction === 'LONG' ? '^ LONG' : analysis.direction === 'SHORT' ? 'v SHORT' : '- NEUTRAL'}
            </span>
            {analysis.regime && (() => {
              const rs = REGIME_STYLES[analysis.regime!.regime] || REGIME_STYLES.NEUTRAL;
              return (
                <span className="esfu-badge" style={{ background: rs.bg, color: rs.fg }}>
                  {rs.label} ({analysis.regime!.trend_score > 0 ? '+' : ''}{analysis.regime!.trend_score})
                </span>
              );
            })()}
          </>
        )}
        {sessionStatus && (
          <span className="esfu-badge" style={{
            background: sessionStatus.is_rth ? 'rgba(46,204,113,0.15)' : 'rgba(149,165,166,0.15)',
            color: sessionStatus.is_rth ? '#2ecc71' : '#95a5a6',
          }}>
            {sessionStatus.is_rth ? 'RTH' : 'ETH'}
          </span>
        )}
        {analysis && (
          <span className="esfu-badge" style={{
            background: 'rgba(255,255,255,0.05)',
            color: analysis.grade === 'A' ? '#2ecc71' : analysis.grade === 'B' ? '#f1c40f' : analysis.grade === 'C' ? '#e67e22' : '#95a5a6',
          }}>
            Grade {analysis.grade} ({analysis.total_score.toFixed(0)}/100)
          </span>
        )}
        <span className="esfu-last-updated">
          {lastUpdated ? timeAgo(lastUpdated) : ''}
        </span>
        <button className="esfu-refresh-btn" onClick={refresh} disabled={loading}>
          {loading ? '...' : 'Refresh'}
        </button>
      </div>

      {error && <div className="esfu-error">{error}</div>}

      {/* Tab Bar */}
      <div className="market-tabs">
        {tabs.map(t => (
          <button key={t.key} className={`market-tab-btn ${activeTab === t.key ? 'active' : ''}`}
            onClick={() => setActiveTab(t.key)}>
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}

      {/* ── Tab 0: Today's Strategy ── */}
      {activeTab === 'strategy' && (
        <div className="esfu-strategy-tab">
          {/* ── Hero: Today's Strategy ── */}
          <div className="esfu-strategy-hero">
            <div className="esfu-hero-header">
              <h2>오늘의 단타 전략은?</h2>
              <div className="esfu-hero-actions">
                {journal.activeExperimentStatus ? (
                  <button className="esfu-btn esfu-btn-primary" onClick={() => journal.generateABHypotheses(effectiveTicker, journal.activeExperimentStatus!.experiment_id)} disabled={journal.todayLoading}>
                    A/B 가설 생성
                  </button>
                ) : (
                  <button className="esfu-btn esfu-btn-primary" onClick={() => journal.generateHypothesis()} disabled={journal.todayLoading}>
                    {journal.todayLoading ? 'Generating...' : '전략 생성'}
                  </button>
                )}
              </div>
            </div>

            {journal.todayHypotheses.length === 0 ? (
              <div className="esfu-hero-empty">
                {journal.error === 'no_signal' ? (
                  <p>오늘은 진입 조건 미충족 (Score too low). 내일 다시 확인하세요.</p>
                ) : journal.error === 'no_data' ? (
                  <p>시장 데이터를 불러올 수 없습니다. 잠시 후 다시 시도하세요.</p>
                ) : (
                  <p>오늘의 전략이 아직 없습니다. "전략 생성" 버튼을 클릭하세요.</p>
                )}
              </div>
            ) : (
              <div className="esfu-hero-cards">
                {journal.todayHypotheses.map((h) => (
                  <HypothesisCard key={h.hypothesis_id} hypothesis={h} onRecordResult={journal.recordResult} onSkip={journal.skipHypothesis} />
                ))}
              </div>
            )}
          </div>

          {/* ── Live Tracking ── */}
          {journal.todayHypotheses.some(h => h.status === 'PENDING' || h.status === 'ACTIVE') && analysis && (
            <div className="esfu-live-tracking">
              <div className="esfu-panel">
                <div className="esfu-panel-title">LIVE TRACKING</div>
                {journal.todayHypotheses.filter(h => h.status === 'PENDING' || h.status === 'ACTIVE').map(h => {
                  const isLong = h.direction === 'LONG';
                  const currentPrice = analysis.entry_price;
                  const pnl = isLong ? currentPrice - h.entry_price : h.entry_price - currentPrice;
                  const pnlPct = (pnl / h.entry_price) * 100;
                  const slDist = isLong ? (currentPrice - h.stop_loss) / (h.entry_price - h.stop_loss) : (h.stop_loss - currentPrice) / (h.stop_loss - h.entry_price);
                  const tpDist = isLong ? (currentPrice - h.entry_price) / (h.take_profit - h.entry_price) : (h.entry_price - currentPrice) / (h.entry_price - h.take_profit);
                  return (
                    <div key={h.hypothesis_id} className="esfu-tracking-row">
                      <span className={`esfu-badge ${h.direction === 'LONG' ? 'long' : 'short'}`}>{h.direction}</span>
                      <span className="esfu-tracking-price">Entry: {fmtPts(h.entry_price)}</span>
                      <span className="esfu-tracking-price">Now: {fmtPts(currentPrice)}</span>
                      <span className={`esfu-tracking-pnl ${pnl >= 0 ? 'positive' : 'negative'}`}>
                        {pnl >= 0 ? '+' : ''}{pnl.toFixed(2)} pts ({pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(2)}%)
                      </span>
                      <div className="esfu-progress-container">
                        <div className="esfu-progress-label">SL</div>
                        <div className="esfu-progress-track">
                          <div className="esfu-progress-fill sl" style={{ width: `${Math.max(0, Math.min(100, (1 - slDist) * 100))}%` }} />
                        </div>
                        <div className="esfu-progress-label">TP</div>
                        <div className="esfu-progress-track">
                          <div className="esfu-progress-fill tp" style={{ width: `${Math.max(0, Math.min(100, tpDist * 100))}%` }} />
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* ── Results Journal ── */}
          <div className="esfu-results-journal">
            <div className="esfu-panel">
              <div className="esfu-panel-title">STRATEGY JOURNAL</div>
              {journal.hypotheses.length === 0 ? (
                <p style={{ color: '#7f8c8d', textAlign: 'center', padding: '1rem' }}>No history yet</p>
              ) : (
                <>
                  <table className="esfu-trade-table">
                    <thead>
                      <tr>
                        <th>Date</th>
                        <th>Direction</th>
                        <th>Grade</th>
                        <th>Entry</th>
                        <th>SL</th>
                        <th>TP</th>
                        <th>Status</th>
                        <th>Result</th>
                      </tr>
                    </thead>
                    <tbody>
                      {journal.hypotheses.map(h => (
                        <tr key={h.hypothesis_id}>
                          <td>{h.trade_date}</td>
                          <td className={h.direction === 'LONG' ? 'positive' : h.direction === 'SHORT' ? 'negative' : ''}>{h.direction}</td>
                          <td>{h.grade}</td>
                          <td>{fmtPts(h.entry_price)}</td>
                          <td>{fmtPts(h.stop_loss)}</td>
                          <td>{fmtPts(h.take_profit)}</td>
                          <td><span className={`esfu-status-badge ${h.status.toLowerCase()}`}>{h.status}</span></td>
                          <td>{h.status === 'CLOSED' ? '\u2014' : ''}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {journal.hypothesesTotal > 20 && (
                    <div className="esfu-pagination">
                      <button disabled={journal.historyPage === 0} onClick={() => journal.setHistoryPage(journal.historyPage - 1)}>Prev</button>
                      <span>Page {journal.historyPage + 1} / {Math.ceil(journal.hypothesesTotal / 20)}</span>
                      <button disabled={(journal.historyPage + 1) * 20 >= journal.hypothesesTotal} onClick={() => journal.setHistoryPage(journal.historyPage + 1)}>Next</button>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── Tab 1: Live Analysis ── */}
      {activeTab === 'analysis' && (
        <>
          {analysis ? (
            <div className="esfu-analysis-grid">
              <RegimePanel regime={analysis.regime} />
              <AMTPanel amt={analysis.amt} />
              <ScorePanel analysis={analysis} />
              <SignalCard analysis={analysis} />
              <div style={{ gridColumn: 'span 2' }}>
                <IndicatorPanel analysis={analysis} candles={candles} />
              </div>
            </div>
          ) : (
            !loading && !error && <div className="esfu-empty">No analysis data available</div>
          )}

          {loading && !analysis && (
            <div className="esfu-loading">
              <div className="esfu-spinner" />
              <span>Loading analysis...</span>
            </div>
          )}

          {(volumeProfile || sessionStatus) && (
            <div className="esfu-mid-grid">
              {volumeProfile && (
                <VolumeProfileChart vp={volumeProfile} currentPrice={analysis?.entry_price || 0} />
              )}
              {sessionStatus && (
                <SessionPanel session={sessionStatus} isMicro={isMicro} onToggle={() => setIsMicro(!isMicro)} />
              )}
            </div>
          )}
        </>
      )}

      {/* ── Tab 2: Decision Engine (Chart + Strategy + Scalp) ── */}
      {activeTab === 'decision' && (
        <div className="esfu-decision-layout">
          {/* Embedded Chart */}
          {candles.length > 0 ? (
            <div className="esfu-decision-chart">
              <div className="chart-toolbar" style={{ borderRadius: '8px 8px 0 0' }}>
                {/* INTERVAL */}
                <div className="toolbar-section">
                  <span className="chart-toolbar-label">INTERVAL</span>
                  {(['5m', '15m', '30m', '1h'] as const).map(iv => (
                    <button key={iv} className={`tf-btn ${chartInterval === iv ? 'active' : ''}`}
                      onClick={() => setChartInterval(iv)}>{iv}</button>
                  ))}
                </div>

                <div className="toolbar-divider" />

                {/* PERIOD */}
                <div className="toolbar-section">
                  <span className="chart-toolbar-label">PERIOD</span>
                  {([['1d', '1D'], ['5d', '5D'], ['1mo', '1M']] as const).map(([val, label]) => (
                    <button key={val} className={`tf-btn ${chartPeriod === val ? 'active' : ''}`}
                      onClick={() => setChartPeriod(val)}>{label}</button>
                  ))}
                </div>

                <div className="toolbar-divider" />

                {/* SUBCHARTS */}
                <div className="toolbar-section">
                  <span className="chart-toolbar-label">SUBCHARTS</span>
                  {(['rsi', 'macd', 'zscore', 'atr', 'adx'] as const).map(key => (
                    <button key={key}
                      className={`tf-btn ${activeSubcharts[key] ? 'active' : ''}`}
                      onClick={() => setActiveSubcharts({ ...activeSubcharts, [key]: !activeSubcharts[key] })}>
                      {key.toUpperCase()}
                    </button>
                  ))}
                </div>
              </div>
              {/* Strategy 프리셋 토글 — 차트 overlay 가시성 그룹 */}
              <div style={{
                display: 'flex', gap: 8, padding: '8px 12px',
                background: 'rgba(255,255,255,0.02)',
                borderTop: '1px solid rgba(255,255,255,0.04)',
                alignItems: 'center', flexWrap: 'wrap',
              }}>
                <span style={{ fontSize: 11, color: '#888', fontFamily: "'IBM Plex Mono', monospace", marginRight: 4 }}>
                  STRATEGY:
                </span>
                {([
                  { key: 'scalping', label: 'Scalping', desc: 'EMA8/21 + Mag MA + VWATR + VP + BB' },
                  { key: 'turtle',   label: 'Turtle',   desc: 'EMA55 + POC + VAH/VAL (스윙)' },
                  { key: 'all',      label: 'All',      desc: '모든 overlay (11개)' },
                ] as const).map((opt) => (
                  <button
                    key={opt.key}
                    onClick={() => setStrategyMode(opt.key)}
                    title={opt.desc}
                    style={{
                      padding: '4px 12px', fontSize: 11, fontWeight: 600,
                      fontFamily: "'IBM Plex Mono', monospace",
                      cursor: 'pointer',
                      borderRadius: 4,
                      border: '1px solid ' + (strategyMode === opt.key ? '#3b82f6' : 'rgba(255,255,255,0.1)'),
                      background: strategyMode === opt.key ? 'rgba(59,130,246,0.15)' : 'transparent',
                      color: strategyMode === opt.key ? '#60a5fa' : '#888',
                      transition: 'all 0.15s',
                    }}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
              <ESFIntradayChart
                candles={candles}
                volumeProfile={volumeProfile ? {
                  poc: volumeProfile.poc, vah: volumeProfile.vah, val: volumeProfile.val,
                  lvn_levels: volumeProfile.lvn_levels || [],
                } : undefined}
                entryPlan={analysis && (analysis as any).signal_active ? {
                  direction: analysis.direction as 'LONG' | 'SHORT',
                  entry: analysis.entry_price,
                  stopLoss: analysis.stop_loss,
                  takeProfit: analysis.take_profit,
                  rrRatio: analysis.risk_reward_ratio,
                  multiplier: isMicro ? 5 : 50,
                } as EntryPlan : null}
                vwatrZones={analysis?.vwatr_zones}
                subcharts={activeSubcharts}
                height={380}
                ticker={effectiveTicker}
                strategyMode={strategyMode}
              />
            </div>
          ) : (
            !loading && <div className="esfu-empty">No chart data</div>
          )}

          {/* Strategy Dashboard */}
          <StrategyDashboard regime={analysis?.regime} candles={candles} />

          {/* Scalp Decision Engine */}
          <ScalpDecisionEngine
            scalp={scalp}
            magneticMA={analysis?.magnetic_ma?.best?.current_value}
            vwatrZone={analysis?.vwatr_zones?.[0] ?? null}
            backendDirection={backendDirection}
            directionAgrees={directionAgrees}
            disagreementReason={disagreementReason}
            canTrade={canTrade}
            activePosition={activePosition}
            placingPaperOrder={placingPaperOrder}
            paperOrderError={paperOrderError}
            onPlacePaperTrade={(contracts) => placePaperTrade(contracts)}
          />

          {/* Paper Positions Tracker */}
          <PaperPositionsPanel
            positions={openPaperPositions}
            paperRisk={paperRisk}
            onClose={(positionId) => closePaperTrade(positionId)}
            disabled={placingPaperOrder}
          />
        </div>
      )}

      {/* ── Tab: 4-Ticker Proposals ── */}
      {activeTab === 'proposals' && (
        <StrategyProposalsPanel />
      )}

      {/* ── Tab 4: Backtest ── */}
      {activeTab === 'backtest' && (
        <BacktestTabContent state={state} />
      )}

      {/* ── Tab 4: Evolution ── */}
      {activeTab === 'evolution' && (
        <div className="esfu-evolution-tab">
          {/* ── Cumulative Stats Grid ── */}
          <div className="esfu-panel">
            <div className="esfu-panel-title">CUMULATIVE STATISTICS</div>
            <div className="esfu-evolution-stats-grid">
              {['overall', 'direction', 'regime', 'grade'].map(dim => {
                const dimStats = journal.stats.filter(s => s.dimension === dim);
                if (dimStats.length === 0) return null;
                return (
                  <div key={dim} className="esfu-stat-section">
                    <h4>{dim.toUpperCase()}</h4>
                    <table className="esfu-trade-table compact">
                      <thead>
                        <tr>
                          <th>{dim === 'overall' ? '' : dim}</th>
                          <th>Trades</th>
                          <th>WR</th>
                          <th>Avg PnL</th>
                          <th>Total PnL</th>
                          <th>PF</th>
                          <th>Sharpe</th>
                        </tr>
                      </thead>
                      <tbody>
                        {dimStats.map(s => (
                          <tr key={s.dimension_value}>
                            <td>{s.dimension_value}</td>
                            <td>{s.total_trades}</td>
                            <td className={s.win_rate >= 0.5 ? 'positive' : 'negative'}>{(s.win_rate * 100).toFixed(1)}%</td>
                            <td className={s.avg_pnl >= 0 ? 'positive' : 'negative'}>{fmtUSDLocal(s.avg_pnl)}</td>
                            <td className={s.total_pnl >= 0 ? 'positive' : 'negative'}>{fmtUSDLocal(s.total_pnl)}</td>
                            <td>{s.profit_factor.toFixed(2)}</td>
                            <td>{s.sharpe_approx.toFixed(2)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                );
              })}
              {journal.stats.length === 0 && (
                <p style={{ color: '#7f8c8d', textAlign: 'center', padding: '2rem' }}>No cumulative data yet. Record strategy results to see statistics.</p>
              )}
            </div>
          </div>

          {/* ── A/B Experiment Panel ── */}
          <div className="esfu-panel" style={{ marginTop: '1rem' }}>
            <div className="esfu-panel-title">A/B EXPERIMENTS</div>

            {journal.activeExperimentStatus && (
              <div className="esfu-ab-active">
                <h4>{journal.activeExperimentStatus.experiment_name} (Day {journal.activeExperimentStatus.days_elapsed}/{journal.activeExperimentStatus.max_days})</h4>
                <div className="esfu-ab-comparison">
                  {['variant_a', 'variant_b'].map(vKey => {
                    const v = journal.activeExperimentStatus![vKey as 'variant_a' | 'variant_b'];
                    return (
                      <div key={vKey} className="esfu-ab-variant">
                        <h5>{v.name}</h5>
                        <div className="esfu-ab-stats">
                          <span>Trades: {v.trades}</span>
                          <span>WR: {(v.win_rate * 100).toFixed(1)}%</span>
                          <span>Avg PnL: {fmtUSDLocal(v.avg_pnl)}</span>
                          <span>Sharpe: {v.sharpe.toFixed(2)}</span>
                        </div>
                        <div className="esfu-progress-track">
                          <div className="esfu-progress-fill" style={{ width: `${Math.min(100, (v.trades / journal.activeExperimentStatus!.min_trades_per_variant) * 100)}%` }} />
                        </div>
                        <span className="esfu-progress-label">{v.trades}/{journal.activeExperimentStatus!.min_trades_per_variant} trades</span>
                      </div>
                    );
                  })}
                </div>
                {journal.activeExperimentStatus.p_value != null && (
                  <div className="esfu-ab-pvalue">
                    p-value: {journal.activeExperimentStatus.p_value.toFixed(4)}
                    {journal.activeExperimentStatus.p_value < 0.05 ? ' \u2713 Significant' : ' (not yet significant)'}
                  </div>
                )}
                <div className="esfu-ab-actions">
                  {journal.activeExperimentStatus.ready && (
                    <button className="esfu-btn esfu-btn-primary" onClick={() => journal.concludeExperiment(journal.activeExperimentStatus!.experiment_id)}>
                      Conclude Experiment
                    </button>
                  )}
                </div>
              </div>
            )}

            {/* Variant Manager */}
            <div className="esfu-variant-list" style={{ marginTop: '1rem' }}>
              <h4>Variants ({journal.variants.length})</h4>
              {journal.variants.map(v => (
                <div key={v.variant_id} className="esfu-variant-row">
                  <span className="esfu-variant-name">{v.name}</span>
                  {v.is_baseline ? <span className="esfu-badge" style={{ background: 'rgba(46,204,113,0.2)', color: '#2ecc71' }}>BASELINE</span> : null}
                  <span className="esfu-variant-overrides">{Object.keys(v.param_overrides_json || {}).length} overrides</span>
                </div>
              ))}
              {journal.variants.length === 0 && <p style={{ color: '#7f8c8d' }}>No variants yet</p>}
            </div>

            {/* Experiment History */}
            {journal.experiments.length > 0 && (
              <div className="esfu-experiment-history" style={{ marginTop: '1rem' }}>
                <h4>Experiment History</h4>
                {journal.experiments.map(e => (
                  <div key={e.experiment_id} className="esfu-experiment-row">
                    <span>{e.name}</span>
                    <span className={`esfu-status-badge ${e.status.toLowerCase()}`}>{e.status}</span>
                    {e.winner_variant_id && <span>Winner: V{e.winner_variant_id}</span>}
                    {e.status === 'CONCLUDED' && e.winner_variant_id && (
                      <button className="esfu-btn esfu-btn-sm" onClick={() => journal.graduateWinner(e.experiment_id)}>Graduate</button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
