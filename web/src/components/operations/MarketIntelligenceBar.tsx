import { useState, useEffect, useCallback } from 'react';
import { Globe, RefreshCw } from 'lucide-react';
import type {
    MarketId,
    MarketIntelligenceResponse,
    MarketIntelligenceData,
    IndexTrend,
} from '../../lib/api';
import { fetchMarketIntelligence, MARKETS } from '../../lib/api';
import { usePolling } from '../../hooks/usePolling';
import './MarketIntelligenceBar.css';

// ── 5단계 추세 컬러 매핑 ──
const TREND_COLORS: Record<IndexTrend, { bg: string; border: string; text: string }> = {
    STRONG_BULL: { bg: 'rgba(34,197,94,0.15)', border: 'rgba(34,197,94,0.4)', text: '#4ade80' },
    BULL:        { bg: 'rgba(34,197,94,0.10)', border: 'rgba(34,197,94,0.3)', text: '#22c55e' },
    NEUTRAL:     { bg: 'rgba(234,179,8,0.10)', border: 'rgba(234,179,8,0.3)', text: '#eab308' },
    BEAR:        { bg: 'rgba(239,68,68,0.10)', border: 'rgba(239,68,68,0.3)', text: '#ef4444' },
    CRISIS:      { bg: 'rgba(239,68,68,0.20)', border: 'rgba(239,68,68,0.5)', text: '#f87171' },
};

const TREND_LABELS: Record<IndexTrend, string> = {
    STRONG_BULL: '강세', BULL: '상승', NEUTRAL: '중립', BEAR: '하락', CRISIS: '위기',
};

function getTrendStyle(trend: IndexTrend) {
    return TREND_COLORS[trend] || TREND_COLORS.NEUTRAL;
}

// ── MA 정렬 뱃지 ──
function maAlignmentLabel(ma: string) {
    if (ma === 'ALIGNED_BULL') return { label: 'Bullish Aligned', cls: 'ma-bull' };
    if (ma === 'ALIGNED_BEAR') return { label: 'Bearish Aligned', cls: 'ma-bear' };
    return { label: 'Mixed', cls: 'ma-mixed' };
}

// ── VIX 뱃지 ──
function vixBadge(state: string, value: number) {
    const cls = state === 'EXTREME' ? 'vix-extreme'
              : state === 'HIGH' ? 'vix-high'
              : state === 'LOW' ? 'vix-low' : 'vix-normal';
    return { label: `${state} ${value.toFixed(1)}`, cls };
}

interface Props {
    activeMarket: MarketId;
}

export function MarketIntelligenceBar({ activeMarket }: Props) {
    const [data, setData] = useState<MarketIntelligenceResponse | null>(null);
    const [error, setError] = useState(false);

    const loadData = useCallback(() => {
        setError(false);
        fetchMarketIntelligence().then(setData).catch(() => setError(true));
    }, []);

    // Initial load
    useEffect(() => { loadData(); }, [loadData]);

    // 60초 폴링
    const polling = usePolling(fetchMarketIntelligence, { interval: 60000, enabled: true });

    // Merge SSE / polling data
    const effective = polling.data || data;

    if (error && !effective) {
        return (
            <div className="mib-container glass-panel">
                <div className="mib-header">
                    <Globe size={15} />
                    <span className="mib-title">마켓 인텔리전스</span>
                </div>
                <div className="error-placeholder">
                    서버 연결 실패
                    <button className="retry-btn" onClick={loadData}><RefreshCw size={12} /> 재시도</button>
                </div>
            </div>
        );
    }

    if (!effective) return null;

    const hasAnyData = Object.values(effective).some(v => v !== null);
    if (!hasAnyData) return null;

    return (
        <div className="mib-container glass-panel">
            <div className="mib-header">
                <Globe size={15} />
                <span className="mib-title">마켓 인텔리전스</span>
                {polling.lastUpdated && (
                    <span className="mib-updated">
                        Updated: {new Date(polling.lastUpdated).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' })}
                    </span>
                )}
            </div>
            <div className="mib-grid">
                {MARKETS.map(m => (
                    <MarketColumn
                        key={m.id}
                        marketId={m.id}
                        flag={m.flag}
                        label={m.label}
                        intel={effective[m.id] ?? null}
                        isActive={activeMarket === m.id}
                    />
                ))}
            </div>
        </div>
    );
}


// ── 개별 마켓 컬럼 ──

interface MarketColumnProps {
    marketId: MarketId;
    flag: string;
    label: string;
    intel: MarketIntelligenceData | null;
    isActive: boolean;
}

function MarketColumn({ marketId, flag, label, intel, isActive }: MarketColumnProps) {
    if (!intel) {
        return (
            <div className={`mib-col ${isActive ? 'mib-col--active' : ''}`}>
                <div className="mib-col-header">
                    <span className="mib-col-flag">{flag}</span>
                    <span className="mib-col-label">{label}</span>
                </div>
                <div className="mib-col-empty">데이터 없음</div>
            </div>
        );
    }

    const t = intel.index_trend;
    const trend = (t.trend || 'NEUTRAL') as IndexTrend;
    const tStyle = getTrendStyle(trend);
    const ma = maAlignmentLabel(t.ma_alignment);
    const vix = vixBadge(t.volatility_state, intel.vix_ema20);
    const macdVal = t.macd_value ?? 0;
    const macdPositive = macdVal >= 0;
    const momScore = t.momentum_score ?? 50;

    // 전략 비중
    const weights = intel.strategy_weights || {};
    const sortedWeights = Object.entries(weights).sort((a, b) => b[1] - a[1]);

    return (
        <div className={`mib-col ${isActive ? 'mib-col--active' : ''}`}>
            <div className="mib-col-header">
                <span className="mib-col-flag">{flag}</span>
                <span className="mib-col-label">{label}</span>
            </div>

            {/* 추세 뱃지 */}
            <div
                className="mib-trend-badge"
                style={{ background: tStyle.bg, borderColor: tStyle.border, color: tStyle.text }}
            >
                {trend.replace('_', ' ')}
                <span className="mib-trend-label">{TREND_LABELS[trend]}</span>
            </div>

            {/* 구성 요소 */}
            <div className="mib-indicators">
                <div className="mib-ind-row">
                    <span className="mib-ind-label">MA</span>
                    <span className={`mib-ma-badge ${ma.cls}`}>{ma.label}</span>
                </div>
                <div className="mib-ind-row">
                    <span className="mib-ind-label">Momentum</span>
                    <div className="mib-mom-bar-wrap">
                        <div className="mib-mom-bar" style={{ width: `${Math.min(momScore, 100)}%` }}>
                            <div
                                className="mib-mom-fill"
                                style={{
                                    width: '100%',
                                    background: momScore >= 60 ? '#22c55e' : momScore >= 40 ? '#eab308' : '#ef4444',
                                }}
                            />
                        </div>
                        <span className="mib-mom-val">{momScore.toFixed(1)}</span>
                    </div>
                </div>
                <div className="mib-ind-row">
                    <span className="mib-ind-label">VIX</span>
                    <span className={`mib-vix-badge ${vix.cls}`}>{vix.label}</span>
                </div>
                <div className="mib-ind-row">
                    <span className="mib-ind-label">MACD</span>
                    <span className={`mib-macd-val ${macdPositive ? 'pos' : 'neg'}`}>
                        {macdPositive ? '+' : ''}{macdVal.toFixed(1)}
                        {macdPositive ? ' Bullish' : ' Bearish'}
                    </span>
                </div>
            </div>

            {/* 전략 비중 바 */}
            <div className="mib-weights">
                {sortedWeights.map(([strat, w]) => {
                    const pct = (w * 100).toFixed(0);
                    const stratLabel = strat === 'mean_reversion' ? 'Mean Rev.'
                        : strat === 'defensive' ? 'Defensive'
                        : strat === 'momentum' ? 'Momentum'
                        : strat === 'smc' ? 'SMC'
                        : strat;
                    return (
                        <div className="mib-weight-row" key={strat}>
                            <span className="mib-weight-label">{stratLabel}</span>
                            <div className="mib-weight-bar">
                                <div
                                    className="mib-weight-fill"
                                    style={{ width: `${pct}%` }}
                                />
                            </div>
                            <span className="mib-weight-pct">{pct}%</span>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
