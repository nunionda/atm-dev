import type { RebalanceRecommendation } from '../../lib/api';

interface RecommendationTableProps {
    title: string;
    icon: string;
    items: RebalanceRecommendation[];
    type: 'BUY' | 'HOLD' | 'SELL';
    currencySymbol: string;
}

export function RecommendationTable({ title, icon, items, type, currencySymbol }: RecommendationTableProps) {
    const typeClass = type.toLowerCase();

    if (items.length === 0) {
        return (
            <div className={`rec-table glass-panel rec-${typeClass}`}>
                <div className="rec-table-header">
                    <h3>{icon} {title} <span className="rec-count">(0)</span></h3>
                </div>
                <div className="rec-empty">No recommendations</div>
            </div>
        );
    }

    return (
        <div className={`rec-table glass-panel rec-${typeClass}`}>
            <div className="rec-table-header">
                <h3>{icon} {title} <span className="rec-count">({items.length})</span></h3>
            </div>
            <table className="rec-data-table">
                <thead>
                    <tr>
                        <th>#</th>
                        <th>Code</th>
                        <th>Name</th>
                        <th>Sector</th>
                        <th>Score</th>
                        <th>Price</th>
                        {type === 'BUY' && <th>6M Return</th>}
                        {type === 'HOLD' && <th>P&L</th>}
                        {type === 'HOLD' && <th>Days</th>}
                        {type === 'SELL' && <th>P&L</th>}
                        {type === 'SELL' && <th>Reason</th>}
                    </tr>
                </thead>
                <tbody>
                    {items.map((item) => (
                        <tr key={item.code}>
                            <td className="rank-cell">{item.rank}</td>
                            <td className="code-cell">{item.code}</td>
                            <td className="name-cell">{item.name}</td>
                            <td className="sector-cell">{item.sector}</td>
                            <td className="score-cell">
                                <span className={`score-badge score-${getScoreLevel(item.score)}`}>
                                    {item.score.toFixed(1)}
                                </span>
                            </td>
                            <td className="price-cell">{currencySymbol}{item.price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                            {type === 'BUY' && (
                                <td className={`return-cell ${(item.return_6m ?? '').startsWith('+') ? 'positive' : 'negative'}`}>
                                    {item.return_6m ?? '-'}
                                </td>
                            )}
                            {type === 'HOLD' && (
                                <>
                                    <td className={`pnl-cell ${(item.pnl_pct ?? 0) >= 0 ? 'positive' : 'negative'}`}>
                                        {item.pnl_pct != null ? `${item.pnl_pct >= 0 ? '+' : ''}${item.pnl_pct.toFixed(1)}%` : '-'}
                                    </td>
                                    <td className="days-cell">{item.days_held ?? '-'}d</td>
                                </>
                            )}
                            {type === 'SELL' && (
                                <>
                                    <td className={`pnl-cell ${(item.pnl_pct ?? 0) >= 0 ? 'positive' : 'negative'}`}>
                                        {item.pnl_pct != null ? `${item.pnl_pct >= 0 ? '+' : ''}${item.pnl_pct.toFixed(1)}%` : '-'}
                                    </td>
                                    <td className="reason-cell">{item.reason ?? '-'}</td>
                                </>
                            )}
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

function getScoreLevel(score: number): string {
    if (score >= 70) return 'high';
    if (score >= 40) return 'mid';
    return 'low';
}
