import { useState, useEffect, useCallback } from 'react';
import { Trash2, ChevronDown, ChevronUp, History } from 'lucide-react';
import type { MarketId, ReplayResultSummary } from '../../lib/api';
import { listReplayResults, deleteReplayResult } from '../../lib/api';
import './ReplayHistory.css';

const STRATEGY_LABELS: Record<string, string> = {
    momentum: 'Momentum',
    smc: 'Smart Money Concept',
    breakout_retest: 'BRT',
};

function formatDate(d: string): string {
    if (!d) return '';
    // YYYY-MM-DD → YY.MM.DD
    if (d.length === 10) return d.slice(2).replace(/-/g, '.');
    return d;
}

function formatPct(v: number): string {
    return `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`;
}

function formatNumber(v: number, digits = 0): string {
    return v.toLocaleString(undefined, { maximumFractionDigits: digits });
}

interface Props {
    market: MarketId;
}

export function ReplayHistory({ market }: Props) {
    const [results, setResults] = useState<ReplayResultSummary[]>([]);
    const [loading, setLoading] = useState(false);
    const [expandedId, setExpandedId] = useState<string | null>(null);

    const refresh = useCallback(async () => {
        setLoading(true);
        try {
            const data = await listReplayResults(market, 20);
            setResults(data.results);
        } catch {
            // API not available
        } finally {
            setLoading(false);
        }
    }, [market]);

    useEffect(() => {
        refresh();
    }, [refresh]);

    const handleDelete = async (resultId: string, e: React.MouseEvent) => {
        e.stopPropagation();
        try {
            await deleteReplayResult(resultId);
            setResults(prev => prev.filter(r => r.result_id !== resultId));
        } catch (err) {
            console.error('Delete error:', err);
        }
    };

    const toggleExpand = (id: string) => {
        setExpandedId(prev => prev === id ? null : id);
    };

    if (results.length === 0 && !loading) {
        return null; // 결과 없으면 숨김
    }

    return (
        <div className="replay-history glass-panel">
            <div className="replay-history-header">
                <div className="replay-history-title">
                    <History size={14} />
                    <span>리플레이 이력</span>
                </div>
                <button className="replay-history-refresh" onClick={refresh} disabled={loading}>
                    {loading ? '로딩...' : '새로고침'}
                </button>
            </div>

            <div className="replay-history-table">
                <div className="replay-history-thead">
                    <span className="rh-col rh-col-period">기간</span>
                    <span className="rh-col rh-col-strategy">전략</span>
                    <span className="rh-col rh-col-return">수익률</span>
                    <span className="rh-col rh-col-sharpe">Sharpe</span>
                    <span className="rh-col rh-col-mdd">MDD</span>
                    <span className="rh-col rh-col-trades">거래</span>
                    <span className="rh-col rh-col-winrate">승률</span>
                    <span className="rh-col rh-col-date">저장일</span>
                    <span className="rh-col rh-col-actions" />
                </div>

                {results.map(r => (
                    <div key={r.result_id}>
                        <div
                            className={`replay-history-row ${expandedId === r.result_id ? 'expanded' : ''}`}
                            onClick={() => toggleExpand(r.result_id)}
                        >
                            <span className="rh-col rh-col-period">
                                {formatDate(r.start_date)} ~ {formatDate(r.end_date)}
                            </span>
                            <span className="rh-col rh-col-strategy">
                                <span className="rh-strategy-badge">
                                    {STRATEGY_LABELS[r.strategy] || r.strategy}
                                </span>
                            </span>
                            <span className={`rh-col rh-col-return ${r.total_return_pct >= 0 ? 'positive' : 'negative'}`}>
                                {formatPct(r.total_return_pct)}
                            </span>
                            <span className="rh-col rh-col-sharpe">{r.sharpe_ratio.toFixed(2)}</span>
                            <span className="rh-col rh-col-mdd negative">{formatPct(r.max_drawdown_pct)}</span>
                            <span className="rh-col rh-col-trades">{r.total_trades}</span>
                            <span className="rh-col rh-col-winrate">{r.win_rate.toFixed(1)}%</span>
                            <span className="rh-col rh-col-date">{formatDate(r.created_at?.slice(0, 10))}</span>
                            <span className="rh-col rh-col-actions">
                                <button
                                    className="rh-delete-btn"
                                    onClick={(e) => handleDelete(r.result_id, e)}
                                    title="삭제"
                                >
                                    <Trash2 size={12} />
                                </button>
                                {expandedId === r.result_id
                                    ? <ChevronUp size={12} className="rh-expand-icon" />
                                    : <ChevronDown size={12} className="rh-expand-icon" />
                                }
                            </span>
                        </div>

                        {expandedId === r.result_id && (
                            <div className="replay-history-detail">
                                <div className="rh-detail-grid">
                                    <div className="rh-detail-item">
                                        <span className="rh-detail-label">초기자본</span>
                                        <span className="rh-detail-value">${formatNumber(r.initial_capital)}</span>
                                    </div>
                                    <div className="rh-detail-item">
                                        <span className="rh-detail-label">최종자산</span>
                                        <span className="rh-detail-value">${formatNumber(r.final_equity)}</span>
                                    </div>
                                    <div className="rh-detail-item">
                                        <span className="rh-detail-label">Profit Factor</span>
                                        <span className="rh-detail-value">{r.profit_factor.toFixed(2)}</span>
                                    </div>
                                    <div className="rh-detail-item">
                                        <span className="rh-detail-label">마켓</span>
                                        <span className="rh-detail-value">{r.market.toUpperCase()}</span>
                                    </div>
                                </div>
                            </div>
                        )}
                    </div>
                ))}
            </div>
        </div>
    );
}
