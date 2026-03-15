import { useState, useEffect, useCallback } from 'react';
import { Layers, ChevronDown, ChevronUp, RefreshCw } from 'lucide-react';
import type {
    MarketId,
    MarketIntelligenceData,
    IndexTrend,
} from '../../lib/api';
import { fetchMarketIntelligence, getMarketConfig } from '../../lib/api';
import { usePolling } from '../../hooks/usePolling';
import './StrategyWeightPanel.css';

// ── 추세 컬러 매핑 (MarketIntelligenceBar와 공유) ──
const TREND_COLORS: Record<IndexTrend, { bg: string; border: string; text: string }> = {
    STRONG_BULL: { bg: 'rgba(34,197,94,0.15)', border: 'rgba(34,197,94,0.4)', text: '#4ade80' },
    BULL:        { bg: 'rgba(34,197,94,0.10)', border: 'rgba(34,197,94,0.3)', text: '#22c55e' },
    NEUTRAL:     { bg: 'rgba(234,179,8,0.10)', border: 'rgba(234,179,8,0.3)', text: '#eab308' },
    BEAR:        { bg: 'rgba(239,68,68,0.10)', border: 'rgba(239,68,68,0.3)', text: '#ef4444' },
    CRISIS:      { bg: 'rgba(239,68,68,0.20)', border: 'rgba(239,68,68,0.5)', text: '#f87171' },
};

interface Props {
    market: MarketId;
}

export function StrategyWeightPanel({ market }: Props) {
    const [intel, setIntel] = useState<MarketIntelligenceData | null>(null);
    const [error, setError] = useState(false);
    const [collapsed, setCollapsed] = useState(false);

    const loadData = useCallback(() => {
        setError(false);
        fetchMarketIntelligence()
            .then(res => setIntel(res[market] ?? null))
            .catch(() => setError(true));
    }, [market]);

    useEffect(() => { loadData(); }, [loadData]);

    // 60초 폴링
    const polling = usePolling(fetchMarketIntelligence, { interval: 60000, enabled: true, cacheKey: 'market-intelligence' });
    const polledIntel = polling.data?.[market] ?? null;
    const data = polledIntel || intel;

    const mktCfg = getMarketConfig(market);

    if (error && !data) {
        return (
            <div className="swp-container glass-panel">
                <div className="swp-header" onClick={() => setCollapsed(c => !c)}>
                    <Layers size={15} />
                    <span className="swp-title">전략 배분 현황</span>
                </div>
                <div className="error-placeholder">
                    데이터 로드 실패
                    <button className="retry-btn" onClick={loadData}><RefreshCw size={12} /> 재시도</button>
                </div>
            </div>
        );
    }

    if (!data) return null;

    const t = data.index_trend;
    const trend = (t.trend || 'NEUTRAL') as IndexTrend;
    const tStyle = TREND_COLORS[trend] || TREND_COLORS.NEUTRAL;
    const momScore = t.momentum_score ?? 50;
    const macdVal = t.macd_value ?? 0;
    const rsiVal = t.rsi ?? 0;
    const adxVal = t.adx ?? 0;
    const signals = t.signals || [];

    const weights = data.strategy_weights || {};
    const sortedWeights = Object.entries(weights).sort((a, b) => b[1] - a[1]);

    return (
        <div className="swp-container glass-panel">
            <div className="swp-header" onClick={() => setCollapsed(c => !c)}>
                <Layers size={15} />
                <span className="swp-title">전략 배분 현황</span>
                <span className="swp-market-badge">{mktCfg.flag} {mktCfg.label}</span>
                {collapsed ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
            </div>

            {!collapsed && (
                <div className="swp-body">
                    {/* 추세 뱃지 + 근거 텍스트 */}
                    <div className="swp-trend-section">
                        <span className="swp-section-label">지수 추세</span>
                        <span
                            className="swp-trend-badge"
                            style={{ background: tStyle.bg, borderColor: tStyle.border, color: tStyle.text }}
                        >
                            {trend.replace('_', ' ')}
                        </span>
                    </div>
                    {signals.length > 0 && (
                        <div className="swp-signals">
                            {signals.slice(0, 3).map((s, i) => (
                                <span key={i} className="swp-signal-chip">{s}</span>
                            ))}
                        </div>
                    )}

                    {/* 구성 요소 카드 */}
                    <div className="swp-components">
                        <span className="swp-section-label">구성 요소</span>
                        <div className="swp-comp-grid">
                            <div className="swp-comp-item">
                                <span className="swp-comp-key">MA Alignment</span>
                                <span className={`swp-comp-val ${
                                    t.ma_alignment === 'ALIGNED_BULL' ? 'bull'
                                    : t.ma_alignment === 'ALIGNED_BEAR' ? 'bear' : 'mixed'
                                }`}>
                                    {t.ma_alignment === 'ALIGNED_BULL' ? 'Bullish'
                                        : t.ma_alignment === 'ALIGNED_BEAR' ? 'Bearish'
                                        : 'Mixed'}
                                </span>
                            </div>
                            <div className="swp-comp-item">
                                <span className="swp-comp-key">Momentum</span>
                                <div className="swp-comp-mom">
                                    <div className="swp-comp-mom-bar">
                                        <div
                                            className="swp-comp-mom-fill"
                                            style={{
                                                width: `${Math.min(momScore, 100)}%`,
                                                background: momScore >= 60 ? '#22c55e' : momScore >= 40 ? '#eab308' : '#ef4444',
                                            }}
                                        />
                                    </div>
                                    <span className="swp-comp-mom-val">{momScore.toFixed(1)}</span>
                                </div>
                            </div>
                            <div className="swp-comp-item">
                                <span className="swp-comp-key">VIX</span>
                                <span className={`swp-comp-val ${
                                    t.volatility_state === 'HIGH' || t.volatility_state === 'EXTREME' ? 'bear' : 'mixed'
                                }`}>
                                    {t.volatility_state} {data.vix_ema20.toFixed(1)}
                                </span>
                            </div>
                            <div className="swp-comp-item">
                                <span className="swp-comp-key">MACD</span>
                                <span className={`swp-comp-val ${macdVal >= 0 ? 'bull' : 'bear'}`}>
                                    {macdVal >= 0 ? '+' : ''}{macdVal.toFixed(1)}
                                    {macdVal >= 0 ? ' Bullish' : ' Bearish'}
                                </span>
                            </div>
                            {rsiVal > 0 && (
                                <div className="swp-comp-item">
                                    <span className="swp-comp-key">RSI</span>
                                    <span className={`swp-comp-val ${
                                        rsiVal >= 70 ? 'bear' : rsiVal <= 30 ? 'bull' : 'mixed'
                                    }`}>
                                        {rsiVal.toFixed(1)}
                                    </span>
                                </div>
                            )}
                            {adxVal > 0 && (
                                <div className="swp-comp-item">
                                    <span className="swp-comp-key">ADX</span>
                                    <span className={`swp-comp-val ${adxVal >= 25 ? 'bull' : 'mixed'}`}>
                                        {adxVal.toFixed(1)}
                                    </span>
                                </div>
                            )}
                        </div>
                    </div>

                    {/* 전략 비중 바 */}
                    <div className="swp-weights">
                        <span className="swp-section-label">전략 비중</span>
                        {sortedWeights.map(([strat, w]) => {
                            const pct = (w * 100).toFixed(0);
                            const stratLabel = strat === 'mean_reversion' ? 'Mean Reversion'
                                : strat === 'defensive' ? 'Defensive'
                                : strat === 'momentum' ? 'Momentum'
                                : strat === 'smc' ? 'SMC'
                                : strat;
                            return (
                                <div className="swp-weight-row" key={strat}>
                                    <span className="swp-weight-name">{stratLabel}</span>
                                    <div className="swp-weight-bar">
                                        <div
                                            className="swp-weight-fill"
                                            style={{ width: `${pct}%` }}
                                        />
                                    </div>
                                    <span className="swp-weight-pct">{pct}%</span>
                                </div>
                            );
                        })}
                    </div>
                </div>
            )}
        </div>
    );
}
