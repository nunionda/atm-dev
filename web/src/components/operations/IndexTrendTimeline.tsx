import { useState, useEffect, useCallback } from 'react';
import { GitBranch, RefreshCw } from 'lucide-react';
import type {
    MarketId,
    TrendChangeEntry,
    IndexTrend,
} from '../../lib/api';
import { fetchMarketIntelligence, getMarketConfig } from '../../lib/api';
import { usePolling } from '../../hooks/usePolling';
import './IndexTrendTimeline.css';

const TREND_COLORS: Record<IndexTrend, { bg: string; border: string; text: string }> = {
    STRONG_BULL: { bg: 'rgba(34,197,94,0.15)', border: 'rgba(34,197,94,0.4)', text: '#4ade80' },
    BULL:        { bg: 'rgba(34,197,94,0.10)', border: 'rgba(34,197,94,0.3)', text: '#22c55e' },
    NEUTRAL:     { bg: 'rgba(234,179,8,0.10)', border: 'rgba(234,179,8,0.3)', text: '#eab308' },
    BEAR:        { bg: 'rgba(239,68,68,0.10)', border: 'rgba(239,68,68,0.3)', text: '#ef4444' },
    CRISIS:      { bg: 'rgba(239,68,68,0.20)', border: 'rgba(239,68,68,0.5)', text: '#f87171' },
};

function TrendBadge({ trend }: { trend: IndexTrend | string | null }) {
    if (!trend) return <span className="itt-badge itt-badge--none">N/A</span>;
    const t = trend as IndexTrend;
    const c = TREND_COLORS[t] || TREND_COLORS.NEUTRAL;
    return (
        <span
            className="itt-badge"
            style={{ background: c.bg, borderColor: c.border, color: c.text }}
        >
            {t.replace('_', ' ')}
        </span>
    );
}

function formatWeight(w: Record<string, number>) {
    return Object.entries(w)
        .filter(([, v]) => v > 0)
        .map(([k, v]) => {
            const label = k === 'mean_reversion' ? 'MeanRev'
                : k === 'defensive' ? 'Defensive'
                : k === 'momentum' ? 'Momentum'
                : k;
            return `${label} ${(v * 100).toFixed(0)}%`;
        })
        .join('  ');
}

interface Props {
    market: MarketId;
}

export function IndexTrendTimeline({ market }: Props) {
    const [history, setHistory] = useState<TrendChangeEntry[]>([]);
    const [error, setError] = useState(false);

    const loadData = useCallback(() => {
        setError(false);
        fetchMarketIntelligence()
            .then(res => {
                const intel = res[market];
                setHistory(intel?.trend_history ?? []);
            })
            .catch(() => setError(true));
    }, [market]);

    useEffect(() => { loadData(); }, [loadData]);

    // 60초 폴링
    const polling = usePolling(fetchMarketIntelligence, { interval: 60000, enabled: true, cacheKey: 'market-intelligence' });
    const polledHistory = polling.data?.[market]?.trend_history ?? null;
    const entries = polledHistory || history;

    const mktCfg = getMarketConfig(market);

    if (error && entries.length === 0) {
        return (
            <div className="itt-container glass-panel">
                <div className="itt-header">
                    <GitBranch size={14} />
                    <span className="itt-title">추세 변경 이력</span>
                </div>
                <div className="error-placeholder">
                    데이터 없음
                    <button className="retry-btn" onClick={loadData}><RefreshCw size={12} /> 재시도</button>
                </div>
            </div>
        );
    }

    if (entries.length === 0) {
        return (
            <div className="itt-container glass-panel">
                <div className="itt-header">
                    <GitBranch size={14} />
                    <span className="itt-title">추세 변경 이력</span>
                    <span className="itt-count">0건</span>
                </div>
                <div className="itt-empty">추세 변경 없음</div>
            </div>
        );
    }

    // 최신 순 정렬
    const sorted = [...entries].reverse();

    return (
        <div className="itt-container glass-panel">
            <div className="itt-header">
                <GitBranch size={14} />
                <span className="itt-title">추세 변경 이력</span>
                <span className="itt-count">{entries.length}건</span>
            </div>
            <div className="itt-scroll">
                {sorted.map((entry, idx) => (
                    <div className="itt-entry" key={idx}>
                        <div className="itt-entry-time">{entry.timestamp}</div>
                        <div className="itt-entry-badges">
                            <TrendBadge trend={entry.from_trend} />
                            <span className="itt-arrow">&rarr;</span>
                            <TrendBadge trend={entry.to_trend} />
                        </div>
                        {entry.trigger_signals.length > 0 && (
                            <div className="itt-entry-signals">
                                {entry.trigger_signals.map((s, si) => (
                                    <span key={si} className="itt-signal-chip">{s}</span>
                                ))}
                            </div>
                        )}
                        <div className="itt-entry-weights">
                            {entry.from_weights && Object.keys(entry.from_weights).length > 0 && (
                                <span className="itt-weight-old">{formatWeight(entry.from_weights)}</span>
                            )}
                            {entry.from_weights && Object.keys(entry.from_weights).length > 0 && (
                                <span className="itt-weight-arrow">&rarr;</span>
                            )}
                            <span className="itt-weight-new">{formatWeight(entry.to_weights)}</span>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}
