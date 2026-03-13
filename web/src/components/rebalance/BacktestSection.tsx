import { useState, useEffect, useCallback, useRef } from 'react';
import { ChevronDown, ChevronUp, Loader2, Play } from 'lucide-react';
import { EquityCurve } from '../performance/EquityCurve';
import type { MarketId, UniverseBacktestResult } from '../../lib/api';
import {
    getMarketConfig,
    triggerUniverseBacktest,
    fetchBacktestResult,
} from '../../lib/api';

interface BacktestSectionProps {
    activeMarket: MarketId;
}

const EXIT_LABELS: Record<string, string> = {
    'ES1 손절 -3%': '손절',
    'ES2 익절 +7%': '익절',
    'ES3 트레일링스탑': '트레일링',
    'ES4 데드크로스': '데드크로스',
    'ES5 보유기간 초과 10일': '기간초과',
    'ES6 시간감쇠': '시간감쇠',
    'ES7 리밸런스 청산': '리밸런스',
    'ES_SMC ATR SL': 'ATR 손절',
    'ES_SMC ATR TP': 'ATR 익절',
    'ES_CHOCH 추세반전': 'CHoCH 반전',
    'ES_BRT ATR SL (1.5x)': 'BRT SL',
    'ES_BRT ATR TP (3.0x)': 'BRT TP',
    'ES_ZONE_BREAK 존 무효화': 'Zone Break',
    'ES_ARB ATR SL': 'ARB SL',
    'ES_ARB Z-Score TP': 'Z-Score TP',
    'ES_ARB Corr Decay': 'Corr Decay',
};

function getExitBadgeClass(reason: string): string {
    if (reason.includes('손절') || reason.includes('SL') || reason.startsWith('ES1')) return 'exit-stop';
    if (reason.includes('익절') || reason.includes('TP') || reason.startsWith('ES2')) return 'exit-profit';
    if (reason.includes('리밸런스') || reason.startsWith('ES7')) return 'exit-rebal';
    if (reason.includes('CHOCH') || reason.includes('추세반전')) return 'exit-choch';
    if (reason.includes('ZONE_BREAK') || reason.includes('존 무효화')) return 'exit-stop';
    return 'exit-other';
}

function toYYYYMMDD(dateStr: string): string {
    return dateStr.replace(/-/g, '');
}

function getPresetDates(years: number): { start: string; end: string } {
    const end = new Date();
    const start = new Date();
    start.setFullYear(start.getFullYear() - years);
    const fmt = (d: Date) =>
        `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    return { start: fmt(start), end: fmt(end) };
}

export function BacktestSection({ activeMarket }: BacktestSectionProps) {
    const [isExpanded, setIsExpanded] = useState(true);
    const [startDate, setStartDate] = useState('');
    const [endDate, setEndDate] = useState('');
    const [strategy, setStrategy] = useState<'momentum' | 'smc' | 'breakout_retest' | 'mean_reversion' | 'arbitrage'>('momentum');
    const [isRunning, setIsRunning] = useState(false);
    const [result, setResult] = useState<UniverseBacktestResult | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [elapsedSec, setElapsedSec] = useState(0);
    const [showAllTrades, setShowAllTrades] = useState(false);
    const [showAdvanced, setShowAdvanced] = useState(false);
    const [tradeFilter, setTradeFilter] = useState('');
    const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

    const marketConfig = getMarketConfig(activeMarket);

    // Set default dates (2Y preset)
    useEffect(() => {
        const { start, end } = getPresetDates(2);
        setStartDate(start);
        setEndDate(end);
    }, []);

    // Load cached result on mount / market change
    useEffect(() => {
        let cancelled = false;
        (async () => {
            try {
                const cached = await fetchBacktestResult(activeMarket);
                if (!cancelled && cached) {
                    setResult(cached);
                    setError(null);
                }
            } catch {
                // ignore
            }
        })();
        return () => { cancelled = true; };
    }, [activeMarket]);

    // Elapsed timer
    useEffect(() => {
        if (isRunning) {
            setElapsedSec(0);
            timerRef.current = setInterval(() => setElapsedSec(s => s + 1), 1000);
        } else if (timerRef.current) {
            clearInterval(timerRef.current);
            timerRef.current = null;
        }
        return () => {
            if (timerRef.current) clearInterval(timerRef.current);
        };
    }, [isRunning]);

    const handlePreset = (years: number) => {
        const { start, end } = getPresetDates(years);
        setStartDate(start);
        setEndDate(end);
    };

    const handleRunBacktest = useCallback(async () => {
        if (!startDate || !endDate) return;
        setIsRunning(true);
        setError(null);
        setShowAllTrades(false);
        try {
            const res = await triggerUniverseBacktest(
                activeMarket,
                toYYYYMMDD(startDate),
                toYYYYMMDD(endDate),
                strategy,
            );
            setResult(res);
        } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : 'Backtest failed';
            setError(msg);
        } finally {
            setIsRunning(false);
        }
    }, [activeMarket, startDate, endDate, strategy]);

    const m = result?.metrics;
    const trades = result?.trades ?? [];
    const filteredTrades = tradeFilter
        ? trades.filter(t =>
            t.stock_name.toLowerCase().includes(tradeFilter.toLowerCase()) ||
            t.stock_code.toLowerCase().includes(tradeFilter.toLowerCase())
        )
        : trades;
    const displayTrades = showAllTrades ? filteredTrades : filteredTrades.slice(-20);
    const ps = result?.phase_stats;
    const isSmc = result?.strategy === 'smc';
    const isBrt = result?.strategy === 'breakout_retest';
    const isMr = result?.strategy === 'mean_reversion';
    const isArb = result?.strategy === 'arbitrage';

    return (
        <div className="backtest-section">
            {/* Header */}
            <div
                className="backtest-section-header glass-panel"
                onClick={() => setIsExpanded(!isExpanded)}
            >
                <div className="backtest-section-title">
                    <span>Universe Backtest</span>
                    {m && (
                        <>
                            {isSmc && (
                                <span className="backtest-pill strategy-smc">Smart Money Concept</span>
                            )}
                            {isBrt && (
                                <span className="backtest-pill strategy-smc">BRT</span>
                            )}
                            {isMr && (
                                <span className="backtest-pill strategy-smc">Mean Reversion</span>
                            )}
                            {isArb && (
                                <span className="backtest-pill strategy-smc">Arbitrage</span>
                            )}
                            <span className={`backtest-pill ${m.total_return >= 0 ? 'positive' : 'negative'}`}>
                                {m.total_return >= 0 ? '+' : ''}{m.total_return.toFixed(1)}% / {m.total_trades} trades
                            </span>
                        </>
                    )}
                </div>
                {isExpanded ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
            </div>

            {isExpanded && (
                <div className="backtest-content glass-panel">
                    {/* Controls */}
                    <div className="backtest-controls">
                        <div className="backtest-strategy-selector">
                            <button
                                className={`strategy-btn ${strategy === 'momentum' ? 'active' : ''}`}
                                onClick={() => setStrategy('momentum')}
                                disabled={isRunning}
                            >
                                Momentum
                            </button>
                            <button
                                className={`strategy-btn ${strategy === 'smc' ? 'active' : ''}`}
                                onClick={() => setStrategy('smc')}
                                disabled={isRunning}
                            >
                                Smart Money Concept
                            </button>
                            <button
                                className={`strategy-btn ${strategy === 'breakout_retest' ? 'active' : ''}`}
                                onClick={() => setStrategy('breakout_retest')}
                                disabled={isRunning}
                            >
                                BRT
                            </button>
                            <button
                                className={`strategy-btn ${strategy === 'mean_reversion' ? 'active' : ''}`}
                                onClick={() => setStrategy('mean_reversion')}
                                disabled={isRunning}
                            >
                                Mean Reversion
                            </button>
                            <button
                                className={`strategy-btn ${strategy === 'arbitrage' ? 'active' : ''}`}
                                onClick={() => setStrategy('arbitrage')}
                                disabled={isRunning}
                            >
                                Arbitrage
                            </button>
                        </div>
                        <div className="backtest-presets">
                            {[1, 2, 3, 5].map(y => (
                                <button
                                    key={y}
                                    className="backtest-preset-btn"
                                    onClick={() => handlePreset(y)}
                                    disabled={isRunning}
                                >
                                    {y}Y
                                </button>
                            ))}
                        </div>
                        <div className="backtest-date-inputs">
                            <input
                                type="date"
                                className="backtest-date-input"
                                value={startDate}
                                onChange={e => setStartDate(e.target.value)}
                                disabled={isRunning}
                            />
                            <span className="backtest-date-sep">~</span>
                            <input
                                type="date"
                                className="backtest-date-input"
                                value={endDate}
                                onChange={e => setEndDate(e.target.value)}
                                disabled={isRunning}
                            />
                        </div>
                        <button
                            className="btn-primary backtest-run-btn"
                            onClick={handleRunBacktest}
                            disabled={isRunning || !startDate || !endDate}
                        >
                            {isRunning ? (
                                <>
                                    <Loader2 size={16} className="spin-icon" />
                                    <span>Running... {elapsedSec}s</span>
                                </>
                            ) : (
                                <>
                                    <Play size={16} />
                                    <span>Run Backtest</span>
                                </>
                            )}
                        </button>
                    </div>

                    {/* Error */}
                    {error && (
                        <div className="rebalance-error">
                            {error}
                        </div>
                    )}

                    {/* Results */}
                    {m && (
                        <>
                            {/* Metrics Grid */}
                            <div className="backtest-metrics-grid">
                                <div className="backtest-stat">
                                    <span className={`backtest-stat-value ${m.total_return >= 0 ? 'positive' : 'negative'}`}>
                                        {m.total_return >= 0 ? '+' : ''}{m.total_return.toFixed(1)}%
                                    </span>
                                    <span className="backtest-stat-label">Total Return</span>
                                </div>
                                <div className="backtest-stat">
                                    <span className={`backtest-stat-value ${m.cagr >= 0 ? 'positive' : 'negative'}`}>
                                        {m.cagr >= 0 ? '+' : ''}{m.cagr.toFixed(1)}%
                                    </span>
                                    <span className="backtest-stat-label">CAGR</span>
                                </div>
                                <div className="backtest-stat">
                                    <span className="backtest-stat-value">{m.sharpe_ratio.toFixed(2)}</span>
                                    <span className="backtest-stat-label">Sharpe</span>
                                </div>
                                <div className="backtest-stat">
                                    <span className="backtest-stat-value negative">{m.max_drawdown.toFixed(1)}%</span>
                                    <span className="backtest-stat-label">Max DD</span>
                                </div>
                                <div className="backtest-stat">
                                    <span className="backtest-stat-value">{m.win_rate.toFixed(1)}%</span>
                                    <span className="backtest-stat-label">Win Rate</span>
                                </div>
                                <div className="backtest-stat">
                                    <span className="backtest-stat-value">{m.profit_factor.toFixed(2)}</span>
                                    <span className="backtest-stat-label">Profit Factor</span>
                                </div>
                                <div className="backtest-stat">
                                    <span className="backtest-stat-value">{m.total_trades}</span>
                                    <span className="backtest-stat-label">Trades</span>
                                </div>
                                <div className="backtest-stat">
                                    <span className="backtest-stat-value">{m.avg_holding_days.toFixed(1)}d</span>
                                    <span className="backtest-stat-label">Avg Hold</span>
                                </div>
                            </div>

                            {/* Equity Curve */}
                            {result?.equity_curve && result.equity_curve.length > 0 && (
                                <div className="backtest-equity-wrapper">
                                    <EquityCurve data={result.equity_curve} height={280} />
                                </div>
                            )}

                            {/* Phase Stats */}
                            {ps && (
                                <div className="backtest-phase-section">
                                    <div
                                        className="backtest-phase-header"
                                        onClick={() => setShowAdvanced(!showAdvanced)}
                                    >
                                        <span>Advanced Stats</span>
                                        {showAdvanced ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                                    </div>
                                    {showAdvanced && (
                                        <div className="backtest-advanced-content">
                                            <div className="backtest-advanced-grid">
                                                <div className="backtest-adv-group">
                                                    <h4>Exit Breakdown</h4>
                                                    <div className="backtest-exit-list">
                                                        {ps.es1_stop_loss > 0 && <div className="exit-row"><span className="exit-label">ES1 Stop Loss</span><span className="exit-count">{ps.es1_stop_loss}</span></div>}
                                                        {ps.es2_take_profit > 0 && <div className="exit-row"><span className="exit-label">ES2 Take Profit</span><span className="exit-count">{ps.es2_take_profit}</span></div>}
                                                        {ps.es3_trailing_stop > 0 && <div className="exit-row"><span className="exit-label">ES3 Trailing</span><span className="exit-count">{ps.es3_trailing_stop}</span></div>}
                                                        {ps.es4_dead_cross > 0 && <div className="exit-row"><span className="exit-label">ES4 Dead Cross</span><span className="exit-count">{ps.es4_dead_cross}</span></div>}
                                                        {ps.es5_max_holding > 0 && <div className="exit-row"><span className="exit-label">ES5 Max Hold</span><span className="exit-count">{ps.es5_max_holding}</span></div>}
                                                        {ps.es6_time_decay > 0 && <div className="exit-row"><span className="exit-label">ES6 Time Decay</span><span className="exit-count">{ps.es6_time_decay}</span></div>}
                                                        {ps.es7_rebalance_exit > 0 && <div className="exit-row"><span className="exit-label">ES7 Rebalance</span><span className="exit-count">{ps.es7_rebalance_exit}</span></div>}
                                                        {ps.es_smc_sl > 0 && <div className="exit-row"><span className="exit-label">ATR Stop Loss</span><span className="exit-count">{ps.es_smc_sl}</span></div>}
                                                        {ps.es_smc_tp > 0 && <div className="exit-row"><span className="exit-label">ATR Take Profit</span><span className="exit-count">{ps.es_smc_tp}</span></div>}
                                                        {ps.es_choch_exit > 0 && <div className="exit-row"><span className="exit-label">CHoCH Exit</span><span className="exit-count">{ps.es_choch_exit}</span></div>}
                                                        {ps.es_brt_sl > 0 && <div className="exit-row"><span className="exit-label">BRT ATR SL</span><span className="exit-count">{ps.es_brt_sl}</span></div>}
                                                        {ps.es_brt_tp > 0 && <div className="exit-row"><span className="exit-label">BRT ATR TP</span><span className="exit-count">{ps.es_brt_tp}</span></div>}
                                                        {ps.es_zone_break > 0 && <div className="exit-row"><span className="exit-label">Zone Break</span><span className="exit-count">{ps.es_zone_break}</span></div>}
                                                        {ps.es_mr_sl > 0 && <div className="exit-row"><span className="exit-label">MR ATR SL</span><span className="exit-count">{ps.es_mr_sl}</span></div>}
                                                        {ps.es_mr_tp > 0 && <div className="exit-row"><span className="exit-label">MR TP (MA20/RSI)</span><span className="exit-count">{ps.es_mr_tp}</span></div>}
                                                        {ps.es_mr_bb > 0 && <div className="exit-row"><span className="exit-label">MR BB Mid</span><span className="exit-count">{ps.es_mr_bb}</span></div>}
                                                        {ps.es_mr_ob > 0 && <div className="exit-row"><span className="exit-label">MR Overbought</span><span className="exit-count">{ps.es_mr_ob}</span></div>}
                                                        {ps.es_arb_sl > 0 && <div className="exit-row"><span className="exit-label">ARB ATR SL</span><span className="exit-count">{ps.es_arb_sl}</span></div>}
                                                        {ps.es_arb_tp > 0 && <div className="exit-row"><span className="exit-label">ARB Z-Score TP</span><span className="exit-count">{ps.es_arb_tp}</span></div>}
                                                        {ps.es_arb_corr > 0 && <div className="exit-row"><span className="exit-label">ARB Corr Decay</span><span className="exit-count">{ps.es_arb_corr}</span></div>}
                                                    </div>
                                                </div>
                                                <div className="backtest-adv-group">
                                                    <h4>Pipeline</h4>
                                                    <div className="backtest-exit-list">
                                                        <div className="exit-row"><span className="exit-label">Total Scans</span><span className="exit-count">{ps.total_scans}</span></div>
                                                        <div className="exit-row"><span className="exit-label">Entries</span><span className="exit-count">{ps.entries_executed}</span></div>
                                                        <div className="exit-row"><span className="exit-label">Commissions</span><span className="exit-count">{marketConfig.currencySymbol}{ps.total_commission_paid?.toLocaleString()}</span></div>
                                                    </div>
                                                </div>
                                                {isSmc && (
                                                    <div className="backtest-adv-group">
                                                        <h4>Smart Money Concept Scoring</h4>
                                                        <div className="backtest-exit-list">
                                                            <div className="exit-row"><span className="exit-label">Smart Money Concept Entries</span><span className="exit-count">{ps.smc_entries}</span></div>
                                                            <div className="exit-row"><span className="exit-label">Avg Score</span><span className="exit-count">{ps.smc_avg_score?.toFixed(1)}</span></div>
                                                            <div className="exit-row"><span className="exit-label">ATR Stop Loss</span><span className="exit-count">{ps.es_smc_sl}</span></div>
                                                            <div className="exit-row"><span className="exit-label">ATR Take Profit</span><span className="exit-count">{ps.es_smc_tp}</span></div>
                                                            <div className="exit-row"><span className="exit-label">CHoCH Exit</span><span className="exit-count">{ps.es_choch_exit}</span></div>
                                                        </div>
                                                    </div>
                                                )}
                                                {isBrt && (
                                                    <div className="backtest-adv-group">
                                                        <h4>BRT Pipeline</h4>
                                                        <div className="backtest-exit-list">
                                                            <div className="exit-row"><span className="exit-label">Breakouts Detected</span><span className="exit-count">{ps.brt_breakouts_detected}</span></div>
                                                            <div className="exit-row"><span className="exit-label">Fakeout Blocked</span><span className="exit-count">{ps.brt_fakeout_blocked}</span></div>
                                                            <div className="exit-row"><span className="exit-label">Retest Entries</span><span className="exit-count">{ps.brt_retests_entered}</span></div>
                                                            <div className="exit-row"><span className="exit-label">Retests Expired</span><span className="exit-count">{ps.brt_retests_expired}</span></div>
                                                            <div className="exit-row"><span className="exit-label">Zone Break Exit</span><span className="exit-count">{ps.es_zone_break}</span></div>
                                                        </div>
                                                    </div>
                                                )}
                                                {isMr && (
                                                    <div className="backtest-adv-group">
                                                        <h4>Mean Reversion Scoring</h4>
                                                        <div className="backtest-exit-list">
                                                            <div className="exit-row"><span className="exit-label">MR Entries</span><span className="exit-count">{ps.mr_entries}</span></div>
                                                            <div className="exit-row"><span className="exit-label">Avg Score</span><span className="exit-count">{ps.mr_entries > 0 ? (ps.mr_total_score / ps.mr_entries).toFixed(1) : '—'}</span></div>
                                                            <div className="exit-row"><span className="exit-label">MR ATR SL</span><span className="exit-count">{ps.es_mr_sl}</span></div>
                                                            <div className="exit-row"><span className="exit-label">MR TP (MA20/RSI)</span><span className="exit-count">{ps.es_mr_tp}</span></div>
                                                            <div className="exit-row"><span className="exit-label">MR BB Mid</span><span className="exit-count">{ps.es_mr_bb}</span></div>
                                                            <div className="exit-row"><span className="exit-label">MR Overbought</span><span className="exit-count">{ps.es_mr_ob}</span></div>
                                                        </div>
                                                    </div>
                                                )}
                                                {isArb && (
                                                    <div className="backtest-adv-group">
                                                        <h4>Arbitrage Pairs Trading</h4>
                                                        <div className="backtest-exit-list">
                                                            <div className="exit-row"><span className="exit-label">Pairs Scanned</span><span className="exit-count">{ps.arb_pairs_scanned}</span></div>
                                                            <div className="exit-row"><span className="exit-label">Spreads Detected</span><span className="exit-count">{ps.arb_spreads_detected}</span></div>
                                                            <div className="exit-row"><span className="exit-label">Corr Rejects</span><span className="exit-count">{ps.arb_correlation_rejects}</span></div>
                                                            <div className="exit-row"><span className="exit-label">Long Entries</span><span className="exit-count">{ps.arb_entries}</span></div>
                                                            <div className="exit-row"><span className="exit-label">Short Entries</span><span className="exit-count">{ps.arb_short_entries}</span></div>
                                                            <div className="exit-row"><span className="exit-label">Avg Score</span><span className="exit-count">{ps.arb_entries > 0 ? (ps.arb_total_score / ps.arb_entries).toFixed(1) : '—'}</span></div>
                                                            <div className="exit-row"><span className="exit-label">ARB ATR SL</span><span className="exit-count">{ps.es_arb_sl}</span></div>
                                                            <div className="exit-row"><span className="exit-label">ARB Z-Score TP</span><span className="exit-count">{ps.es_arb_tp}</span></div>
                                                            <div className="exit-row"><span className="exit-label">ARB Corr Decay</span><span className="exit-count">{ps.es_arb_corr}</span></div>
                                                        </div>
                                                    </div>
                                                )}
                                                <div className="backtest-adv-group">
                                                    <h4>Rebalancing</h4>
                                                    <div className="backtest-exit-list">
                                                        <div className="exit-row"><span className="exit-label">Rebalances</span><span className="exit-count">{m.total_rebalances}</span></div>
                                                        <div className="exit-row"><span className="exit-label">Avg Turnover</span><span className="exit-count">{m.avg_turnover_pct.toFixed(1)}%</span></div>
                                                    </div>
                                                </div>
                                                <div className="backtest-adv-group">
                                                    <h4>Extended</h4>
                                                    <div className="backtest-exit-list">
                                                        <div className="exit-row"><span className="exit-label">Sortino</span><span className="exit-count">{m.sortino_ratio.toFixed(2)}</span></div>
                                                        <div className="exit-row"><span className="exit-label">Calmar</span><span className="exit-count">{m.calmar_ratio.toFixed(2)}</span></div>
                                                        <div className="exit-row"><span className="exit-label">Best Trade</span><span className="exit-count positive">{m.best_trade_pct >= 0 ? '+' : ''}{m.best_trade_pct.toFixed(2)}%</span></div>
                                                        <div className="exit-row"><span className="exit-label">Worst Trade</span><span className="exit-count negative">{m.worst_trade_pct.toFixed(2)}%</span></div>
                                                        <div className="exit-row"><span className="exit-label">Max Win Streak</span><span className="exit-count">{m.max_consecutive_wins}</span></div>
                                                        <div className="exit-row"><span className="exit-label">Max Loss Streak</span><span className="exit-count">{m.max_consecutive_losses}</span></div>
                                                    </div>
                                                </div>
                                            </div>
                                            {/* Regime Distribution */}
                                            <div className="backtest-regime-bar">
                                                <div className="regime-segment regime-bull" style={{ width: `${m.time_in_bull_pct}%` }}>
                                                    {m.time_in_bull_pct > 10 && `Bull ${m.time_in_bull_pct.toFixed(0)}%`}
                                                </div>
                                                <div className="regime-segment regime-neutral" style={{ width: `${m.time_in_neutral_pct}%` }}>
                                                    {m.time_in_neutral_pct > 10 && `Neutral ${m.time_in_neutral_pct.toFixed(0)}%`}
                                                </div>
                                                <div className="regime-segment regime-bear" style={{ width: `${m.time_in_bear_pct}%` }}>
                                                    {m.time_in_bear_pct > 10 && `Bear ${m.time_in_bear_pct.toFixed(0)}%`}
                                                </div>
                                            </div>
                                        </div>
                                    )}
                                </div>
                            )}

                            {/* Trade Log */}
                            {trades.length > 0 && (
                                <div className="backtest-trades-section">
                                    <div className="backtest-trades-header">
                                        <span>Trade Log ({tradeFilter ? `${filteredTrades.length}/${trades.length}` : trades.length})</span>
                                        <input
                                            type="text"
                                            className="backtest-trade-filter"
                                            placeholder="Filter by name or code..."
                                            value={tradeFilter}
                                            onChange={e => setTradeFilter(e.target.value)}
                                        />
                                    </div>
                                    <div className="backtest-trades-table-wrapper">
                                        <table className="rec-data-table">
                                            <thead>
                                                <tr>
                                                    <th>Stock</th>
                                                    <th>Entry</th>
                                                    <th>Exit</th>
                                                    <th>Entry Price</th>
                                                    <th>Exit Price</th>
                                                    <th>Return</th>
                                                    <th>P&L</th>
                                                    <th>Days</th>
                                                    <th>Exit</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {displayTrades.map((t, i) => (
                                                    <tr key={`${t.stock_code}-${t.entry_date}-${i}`}>
                                                        <td className="code-cell">{t.stock_code}</td>
                                                        <td>{t.entry_date}</td>
                                                        <td>{t.exit_date}</td>
                                                        <td className="price-cell">{marketConfig.currencySymbol}{t.entry_price.toLocaleString()}</td>
                                                        <td className="price-cell">{marketConfig.currencySymbol}{t.exit_price.toLocaleString()}</td>
                                                        <td className={`return-cell ${t.pnl_pct >= 0 ? 'positive' : 'negative'}`}>
                                                            {t.pnl_pct >= 0 ? '+' : ''}{t.pnl_pct.toFixed(2)}%
                                                        </td>
                                                        <td className={`pnl-cell ${t.pnl >= 0 ? 'positive' : 'negative'}`}>
                                                            {t.pnl >= 0 ? '+' : ''}{marketConfig.currencySymbol}{Math.abs(t.pnl).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                                                        </td>
                                                        <td className="days-cell">{t.holding_days}d</td>
                                                        <td>
                                                            <span className={`exit-badge ${getExitBadgeClass(t.exit_reason)}`}>
                                                                {EXIT_LABELS[t.exit_reason] ?? t.exit_reason}
                                                            </span>
                                                        </td>
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    </div>
                                    {filteredTrades.length > 20 && (
                                        <button
                                            className="backtest-show-all-btn"
                                            onClick={() => setShowAllTrades(!showAllTrades)}
                                        >
                                            {showAllTrades ? 'Show Recent 20' : `Show All ${filteredTrades.length} Trades`}
                                        </button>
                                    )}
                                </div>
                            )}
                        </>
                    )}

                    {/* Empty state */}
                    {!m && !isRunning && !error && (
                        <div className="backtest-empty">
                            Select a strategy and date range, then click "Run Backtest" to analyze universe rebalancing performance.
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
