/**
 * BacktestTabContent — extracted from ESFuturesScalping page.
 *
 * Phase 3.C 분할: pages/ESFuturesScalping.tsx → components/esf/scalping/BacktestTabContent.tsx
 */

import type { useESFuturesScalp } from '@hooks/useESFuturesScalp';
import { fmtUSDLocal, fmtPts, fmtPctLocal } from './format';
import { MetricCard } from './MetricCard';
import { SessionPnLChart } from './SessionPnLChart';
import { ExitReasonBars } from './ExitReasonBars';
import { HypothesisCard } from './HypothesisCard';
import { EquityCurve } from '@components/performance/EquityCurve';
import ESFEquityCurve from '@components/esf/ESFEquityCurve';

export function BacktestTabContent({ state }: { state: ReturnType<typeof useESFuturesScalp> }) {
  const {
    btMode, setBtMode, btPeriod, setBtPeriod, btEquity, setBtEquity,
    btRunning, btProgress, btResult, btError, runBacktest,
    intradayBtTicker, setIntradayBtTicker,
    dailyBtTicker, setDailyBtTicker,
    dailyBtStartDate, setDailyBtStartDate, dailyBtEndDate, setDailyBtEndDate,
    dailyBtResult, dailyBtRunning, dailyBtError, dailyBtElapsed,
    runDailyBacktest, setDailyPreset,
    wfTicker, setWfTicker, wfIsMicro, setWfIsMicro,
    wfRunning, wfResult, wfError, runWalkForward,
  } = state;

  // ticker → 자산군별 권장 윈도우 라벨
  const wfRecommendation = (() => {
    if (['ES=F', 'MES=F', 'NQ=F', 'MNQ=F'].includes(wfTicker)) {
      return { window: '3개월', count: 4, asset: 'Equity Index (분기 만기)' };
    }
    if (wfTicker === 'CL=F') return { window: '1개월', count: 12, asset: 'Energy (월 만기)' };
    if (wfTicker === 'GC=F') return { window: '1개월', count: 12, asset: 'Metal (격월 active)' };
    return { window: '—', count: 0, asset: '—' };
  })();

  return (
    <div className="esfu-backtest-section">
      {/* Mode Toggle */}
      <div className="esfu-bt-mode-toggle">
        <button className={`esfu-bt-mode-btn ${btMode === 'intraday' ? 'active' : ''}`}
          onClick={() => setBtMode('intraday')}>
          Intraday (15m bars)
          <span className="esfu-bt-mode-desc">Max 60 days</span>
        </button>
        <button className={`esfu-bt-mode-btn ${btMode === 'daily' ? 'active' : ''}`}
          onClick={() => setBtMode('daily')}>
          Daily (1D bars)
          <span className="esfu-bt-mode-desc">Up to 10+ years</span>
        </button>
        <button className={`esfu-bt-mode-btn ${btMode === 'walk-forward' ? 'active' : ''}`}
          onClick={() => setBtMode('walk-forward')}>
          Walk-Forward
          <span className="esfu-bt-mode-desc">Contract life windows</span>
        </button>
      </div>

      {/* Intraday Mode */}
      {btMode === 'intraday' && (
        <>
          <div className="esfu-bt-controls">
            <div className="esfu-bt-field">
              <label>Period</label>
              <select value={btPeriod} onChange={e => setBtPeriod(e.target.value)}>
                <option value="7d">7 days</option>
                <option value="14d">14 days</option>
                <option value="30d">30 days</option>
                <option value="60d">60 days</option>
              </select>
            </div>
            <div className="esfu-bt-field">
              <label>Ticker</label>
              <select value={intradayBtTicker} onChange={e => setIntradayBtTicker(e.target.value)}>
                <optgroup label="Equity Index">
                  <option value="ES=F">ES=F (E-mini S&P)</option>
                  <option value="MES=F">MES=F (Micro)</option>
                  <option value="NQ=F">NQ=F (E-mini Nasdaq)</option>
                  <option value="MNQ=F">MNQ=F (Micro)</option>
                </optgroup>
                <optgroup label="Commodity">
                  <option value="CL=F">CL=F (WTI Crude)</option>
                  <option value="MCL=F">MCL=F (Micro)</option>
                  <option value="GC=F">GC=F (Gold)</option>
                  <option value="MGC=F">MGC=F (Micro)</option>
                </optgroup>
              </select>
            </div>
            <div className="esfu-bt-field">
              <label>Equity ($)</label>
              <input type="number" value={btEquity} onChange={e => setBtEquity(Number(e.target.value))} min={1000} step={1000} />
            </div>
            <button className="esfu-bt-run" onClick={runBacktest} disabled={btRunning}>
              {btRunning ? `Running... ${btProgress}%` : 'Run Intraday Backtest'}
            </button>
          </div>

          {btError && <div className="esfu-error">{btError}</div>}
          {btRunning && (
            <div className="esfu-progress-bar">
              <div className="esfu-progress-fill" style={{ width: `${btProgress}%` }} />
            </div>
          )}

          {btResult && (
            <div className="esfu-bt-results">
              <div className="esfu-metrics-grid">
                <MetricCard label="Return" value={fmtPctLocal(btResult.metrics.total_return_pct)} colorize />
                <MetricCard label="Sharpe" value={btResult.metrics.sharpe_ratio.toFixed(2)} />
                <MetricCard label="MDD" value={fmtPctLocal(btResult.metrics.max_drawdown_pct)} colorize />
                <MetricCard label="Win Rate" value={`${btResult.metrics.win_rate.toFixed(1)}%`} />
                <MetricCard label="Profit Factor" value={btResult.metrics.profit_factor.toFixed(2)} />
                <MetricCard label="Trades" value={String(btResult.metrics.total_trades)} />
                <MetricCard label="Sessions" value={String(btResult.metrics.sessions_traded)} />
                <MetricCard label="Avg Trades/Day" value={btResult.metrics.avg_trades_per_session.toFixed(1)} />
                <MetricCard label="Total P&L" value={fmtUSDLocal(btResult.metrics.total_pnl)} colorize />
                <MetricCard label="Sortino" value={btResult.metrics.sortino_ratio.toFixed(2)} />
                <MetricCard label="Long / Short" value={`${btResult.metrics.long_trades} / ${btResult.metrics.short_trades}`} />
                <MetricCard label="Avg Hold" value={`${btResult.metrics.avg_holding_minutes.toFixed(0)}m`} />
                <MetricCard label="Best Session" value={fmtUSDLocal(btResult.metrics.best_session_pnl)} colorize />
                <MetricCard label="Worst Session" value={fmtUSDLocal(btResult.metrics.worst_session_pnl)} colorize />
                <MetricCard label="Win Streak" value={String(btResult.metrics.max_consecutive_wins)} />
                <MetricCard label="Loss Streak" value={String(btResult.metrics.max_consecutive_losses)} />
              </div>

              {btResult.sessions.length > 0 && <SessionPnLChart sessions={btResult.sessions} />}
              {btResult.equity_curve.length > 0 && (
                <ESFEquityCurve equityCurve={btResult.equity_curve} trades={btResult.trades} height={220} />
              )}
              {btResult.metrics.exit_reason_distribution && Object.keys(btResult.metrics.exit_reason_distribution).length > 0 && (
                <ExitReasonBars dist={btResult.metrics.exit_reason_distribution} />
              )}

              {btResult.monte_carlo && (
                <div className="esfu-mc-section">
                  <div className="esfu-panel-title" style={{ marginBottom: 8 }}>Monte Carlo (1000 paths)</div>
                  <div className="esfu-metrics-grid">
                    <MetricCard label="VaR 95%" value={fmtPctLocal(btResult.monte_carlo.var_95)} />
                    <MetricCard label="CVaR 99%" value={fmtPctLocal(btResult.monte_carlo.cvar_99)} />
                    <MetricCard label="Worst MDD" value={fmtPctLocal(btResult.monte_carlo.worst_mdd)} />
                    <MetricCard label="Bankruptcy" value={`${btResult.monte_carlo.bankruptcy_prob.toFixed(1)}%`} />
                    <MetricCard label="Median Return" value={fmtPctLocal(btResult.monte_carlo.median_return)} colorize />
                  </div>
                </div>
              )}

              {btResult.trades.length > 0 && (
                <div className="esfu-trade-log">
                  <div className="esfu-panel-title" style={{ marginBottom: 8 }}>Trade Log</div>
                  <div className="esfu-trade-table-wrap">
                    <table className="esfu-trade-table">
                      <thead>
                        <tr>
                          <th>Time</th><th>Dir</th><th>Entry</th><th>Exit</th>
                          <th>P&L</th><th>Bars</th><th>Reason</th><th>Grade</th>
                        </tr>
                      </thead>
                      <tbody>
                        {btResult.trades.map((t, i) => (
                          <tr key={i}>
                            <td>{t.entry_time}</td>
                            <td className={t.direction === 'LONG' ? 'esfu-dir-long' : 'esfu-dir-short'}>{t.direction}</td>
                            <td>{fmtPts(t.entry_price)}</td>
                            <td>{fmtPts(t.exit_price)}</td>
                            <td style={{ color: t.pnl >= 0 ? '#2ecc71' : '#e74c3c' }}>{fmtUSDLocal(t.pnl)}</td>
                            <td>{t.holding_bars}</td>
                            <td>{t.exit_reason}</td>
                            <td><span className={`esfu-grade-mini esfu-grade-${t.grade.toLowerCase()}`}>{t.grade}</span></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}
        </>
      )}

      {/* Daily Mode */}
      {btMode === 'daily' && (
        <>
          <div className="esfu-bt-presets">
            {[1, 2, 3, 5, 10].map(y => (
              <button key={y} className="esfu-bt-preset-btn" onClick={() => setDailyPreset(y)}>{y}Y</button>
            ))}
          </div>

          <div className="esfu-bt-controls">
            <div className="esfu-bt-field">
              <label>Ticker</label>
              <select value={dailyBtTicker} onChange={e => setDailyBtTicker(e.target.value)}>
                <optgroup label="Equity Index">
                  <option value="ES=F">ES=F (E-mini S&P)</option>
                  <option value="MES=F">MES=F (Micro)</option>
                  <option value="NQ=F">NQ=F (E-mini Nasdaq)</option>
                  <option value="MNQ=F">MNQ=F (Micro)</option>
                </optgroup>
                <optgroup label="Commodity">
                  <option value="CL=F">CL=F (WTI Crude)</option>
                  <option value="MCL=F">MCL=F (Micro)</option>
                  <option value="GC=F">GC=F (Gold)</option>
                  <option value="MGC=F">MGC=F (Micro)</option>
                </optgroup>
              </select>
            </div>
            <div className="esfu-bt-field">
              <label>Start Date</label>
              <input value={dailyBtStartDate} onChange={e => setDailyBtStartDate(e.target.value)} placeholder="YYYYMMDD" />
            </div>
            <div className="esfu-bt-field">
              <label>End Date</label>
              <input value={dailyBtEndDate} onChange={e => setDailyBtEndDate(e.target.value)} placeholder="YYYYMMDD" />
            </div>
            <div className="esfu-bt-field">
              <label>Equity ($)</label>
              <input type="number" value={btEquity} onChange={e => setBtEquity(Number(e.target.value))} />
            </div>
            <button className="esfu-bt-run" onClick={runDailyBacktest} disabled={dailyBtRunning}>
              {dailyBtRunning ? `Running... (${dailyBtElapsed}s)` : 'Run Daily Backtest'}
            </button>
          </div>

          {dailyBtError && <div className="esfu-error">{dailyBtError}</div>}

          {dailyBtResult && (
            <div className="esfu-bt-results">
              {dailyBtResult.equity_curve.length > 0 && (
                <div style={{ fontSize: '0.8rem', color: '#888', marginBottom: 8 }}>
                  Data Range: {dailyBtResult.equity_curve[0].date} ~ {dailyBtResult.equity_curve[dailyBtResult.equity_curve.length - 1].date}
                  {' '}({dailyBtResult.equity_curve.length} trading days)
                </div>
              )}
              <div className="esfu-metrics-grid">
                <MetricCard label="Return" value={`${dailyBtResult.metrics.total_return_pct.toFixed(1)}%`} colorize />
                <MetricCard label="CAGR" value={`${dailyBtResult.metrics.cagr?.toFixed(1) ?? 0}%`} colorize />
                <MetricCard label="Sharpe" value={dailyBtResult.metrics.sharpe_ratio.toFixed(2)} />
                <MetricCard label="MDD" value={`${dailyBtResult.metrics.max_drawdown_pct.toFixed(1)}%`} colorize />
                <MetricCard label="Trades" value={String(dailyBtResult.metrics.total_trades)} />
                <MetricCard label="Win Rate" value={`${dailyBtResult.metrics.win_rate.toFixed(1)}%`} />
                <MetricCard label="Profit Factor" value={dailyBtResult.metrics.profit_factor.toFixed(2)} />
                <MetricCard label="Long / Short" value={`${dailyBtResult.metrics.long_trades} / ${dailyBtResult.metrics.short_trades}`} />
                <MetricCard label="Total P&L" value={fmtUSDLocal(dailyBtResult.metrics.total_pnl)} colorize />
                <MetricCard label="Avg R:R" value={dailyBtResult.metrics.avg_rr.toFixed(2)} />
                <MetricCard label="Avg Hold" value={`${dailyBtResult.metrics.avg_holding_days}d`} />
                <MetricCard label="Margin Calls" value={String(dailyBtResult.metrics.margin_call_count ?? 0)} />
                <MetricCard label="Rollovers" value={String(dailyBtResult.metrics.roll_count ?? 0)} />
                <MetricCard label="Roll Costs" value={fmtUSDLocal(dailyBtResult.metrics.total_roll_costs ?? 0)} />
              </div>

              {dailyBtResult.equity_curve.length > 0 && (
                <EquityCurve
                  data={dailyBtResult.equity_curve.map(e => ({
                    date: e.date.split(' ')[0].split('T')[0],
                    equity: e.total_value,
                    drawdown_pct: e.drawdown_pct,
                  }))}
                  height={280}
                />
              )}

              {dailyBtResult.trades.length > 0 && (
                <div style={{ maxHeight: 300, overflowY: 'auto' }}>
                  <table className="esfu-trade-table">
                    <thead>
                      <tr>
                        <th>Entry</th><th>Exit</th><th>Dir</th><th>Entry $</th>
                        <th>Exit $</th><th>Contracts</th><th>P&L</th><th>Days</th><th>Reason</th>
                      </tr>
                    </thead>
                    <tbody>
                      {dailyBtResult.trades.map((t, i) => (
                        <tr key={i}>
                          <td>{t.entry_date}</td>
                          <td>{t.exit_date}</td>
                          <td className={t.direction === 'LONG' ? 'esfu-dir-long' : 'esfu-dir-short'}>{t.direction}</td>
                          <td>{fmtPts(t.entry_price)}</td>
                          <td>{fmtPts(t.exit_price)}</td>
                          <td>{t.contracts}</td>
                          <td style={{ color: t.pnl_dollar >= 0 ? '#2ecc71' : '#e74c3c' }}>{fmtUSDLocal(t.pnl_dollar)}</td>
                          <td>{t.holding_days}</td>
                          <td>{t.exit_reason}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </>
      )}

      {/* Walk-Forward Mode */}
      {btMode === 'walk-forward' && (
        <>
          <div style={{
            padding: '12px 16px', marginBottom: 12, background: 'rgba(59,130,246,0.05)',
            border: '1px solid rgba(59,130,246,0.2)', borderRadius: 8, fontSize: 12, color: '#aaa',
          }}>
            <div style={{ fontWeight: 700, color: '#3b82f6', marginBottom: 6 }}>Walk-Forward 시뮬레이션</div>
            <div>자산군별 contract life cycle에 맞춰 자동 윈도우 분할 → 각 윈도우 독립 백테스트 → 분포 통계 집계.</div>
            <div style={{ marginTop: 4 }}>roll 직전 ±2 영업일 신규 진입 차단(blackout)으로 유동성 이전기 회피.</div>
          </div>

          <div className="esfu-bt-controls">
            <div className="esfu-bt-field">
              <label>Ticker</label>
              <select value={wfTicker} onChange={e => { setWfTicker(e.target.value); setWfIsMicro(['MES=F', 'MNQ=F'].includes(e.target.value)); }}>
                <optgroup label="Equity Index (분기, 3m × 4)">
                  <option value="ES=F">ES=F (E-mini S&P)</option>
                  <option value="MES=F">MES=F (Micro)</option>
                  <option value="NQ=F">NQ=F (E-mini Nasdaq)</option>
                  <option value="MNQ=F">MNQ=F (Micro)</option>
                </optgroup>
                <optgroup label="Commodity (1m × 12)">
                  <option value="CL=F">CL=F (WTI Crude)</option>
                  <option value="GC=F">GC=F (Gold)</option>
                </optgroup>
              </select>
            </div>
            <div className="esfu-bt-field">
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                <input type="checkbox" checked={wfIsMicro} onChange={e => setWfIsMicro(e.target.checked)} />
                Micro contract
              </label>
            </div>
            <button className="esfu-bt-run" onClick={runWalkForward} disabled={wfRunning}>
              {wfRunning ? 'Running...' : `Run Walk-Forward (${wfRecommendation.window} × ${wfRecommendation.count})`}
            </button>
          </div>

          <div style={{ fontSize: 11, color: '#666', marginBottom: 12 }}>
            대상: <b style={{ color: '#ccc' }}>{wfRecommendation.asset}</b> — {wfRecommendation.window} 윈도우 × {wfRecommendation.count}
          </div>

          {wfError && <div className="esfu-error">{wfError}</div>}

          {wfResult && (
            <div className="esfu-bt-results">
              <div style={{ fontSize: 12, color: '#888', marginBottom: 12 }}>
                {wfResult.ticker} · {wfResult.asset_class.replace('_', ' ')} · {wfResult.window_size_months}개월 × {wfResult.n_windows}개 윈도우
                {wfResult.errors.length > 0 && (
                  <span style={{ color: '#ff8a80', marginLeft: 8 }}>⚠ {wfResult.errors.length}개 실패</span>
                )}
              </div>

              {/* Distribution cards */}
              <div className="esfu-metrics-grid" style={{ marginBottom: 16 }}>
                {wfResult.distributions.slice(0, 6).map(d => {
                  const isReturn = d.metric === 'total_return_pct';
                  const isDD = d.metric === 'max_drawdown_pct';
                  const labelMap: Record<string, string> = {
                    total_return_pct: 'Return',
                    sharpe_ratio: 'Sharpe',
                    max_drawdown_pct: 'MDD',
                    profit_factor: 'PF',
                    win_rate: 'Win Rate',
                    total_trades: 'Trades',
                  };
                  return (
                    <div key={d.metric} style={{
                      background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)',
                      borderRadius: 8, padding: '10px 12px',
                    }}>
                      <div style={{ fontSize: 10, color: '#888', marginBottom: 4 }}>{labelMap[d.metric] || d.metric}</div>
                      <div style={{
                        fontSize: 16, fontWeight: 700,
                        color: isDD ? '#ff8a80' : (isReturn && d.median < 0 ? '#ff8a80' : (isReturn ? '#00e676' : '#ccc')),
                        fontFamily: "'IBM Plex Mono', monospace",
                      }}>{d.median.toFixed(2)}{(isReturn || isDD || d.metric === 'win_rate') ? '%' : ''}</div>
                      <div style={{ fontSize: 9, color: '#666', marginTop: 4 }}>
                        median · p25 {d.p25.toFixed(1)} / p75 {d.p75.toFixed(1)}
                      </div>
                      <div style={{ fontSize: 9, color: '#666' }}>
                        worst {d.worst.toFixed(1)} · best {d.best.toFixed(1)}
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Window grid */}
              <div style={{ overflowX: 'auto' }}>
                <table className="esfu-trade-table" style={{ width: '100%', fontSize: 11 }}>
                  <thead>
                    <tr>
                      <th>#</th><th>Label</th><th>Contract</th><th>Start</th><th>End</th>
                      <th>Days</th><th>Return%</th><th>Sharpe</th><th>MDD%</th>
                      <th>WR%</th><th>PF</th><th>Trades</th><th>L/S</th><th>Avg Hold</th>
                    </tr>
                  </thead>
                  <tbody>
                    {wfResult.windows.map(w => (
                      <tr key={w.index} style={{ opacity: w.error ? 0.4 : 1 }}>
                        <td>{w.index + 1}</td>
                        <td>{w.label}</td>
                        <td style={{ fontFamily: "'IBM Plex Mono', monospace" }}>{w.contract_code}</td>
                        <td>{w.start_date}</td>
                        <td>{w.end_date}</td>
                        <td>{w.duration_days}</td>
                        <td style={{ color: w.error ? '#666' : (w.total_return_pct >= 0 ? '#00e676' : '#ff1744') }}>
                          {w.error ? '—' : w.total_return_pct.toFixed(2)}
                        </td>
                        <td>{w.error ? '—' : w.sharpe_ratio.toFixed(2)}</td>
                        <td style={{ color: '#ff8a80' }}>{w.error ? '—' : w.max_drawdown_pct.toFixed(1)}</td>
                        <td>{w.error ? '—' : w.win_rate.toFixed(0)}</td>
                        <td>{w.error ? '—' : w.profit_factor.toFixed(2)}</td>
                        <td>{w.error ? '—' : w.total_trades}</td>
                        <td>{w.error ? '—' : `${w.long_trades}/${w.short_trades}`}</td>
                        <td>{w.error ? '—' : `${w.avg_holding_days.toFixed(1)}d`}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ══════════════════════════════════════════
// HypothesisCard
// ══════════════════════════════════════════

