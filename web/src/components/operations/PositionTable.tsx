import { useState, useEffect } from 'react';
import { TrendingUp, TrendingDown, Clock, ShieldAlert } from 'lucide-react';
import type { Position, MarketId } from '../../lib/api';
import { fetchPositions, getMarketConfig } from '../../lib/api';
import { useSSE } from '../../hooks/useSSE';
import './PositionTable.css';

const STATUS_BADGE: Record<string, { label: string; color: string }> = {
    ACTIVE: { label: '보유', color: '#22c55e' },
    PENDING: { label: '대기', color: '#eab308' },
    CLOSING: { label: '청산중', color: '#f59e0b' },
    CLOSED: { label: '청산', color: '#6b7280' },
};

interface Props {
    market: MarketId;
}

export function PositionTable({ market }: Props) {
    const [positions, setPositions] = useState<Position[]>([]);
    const [loading, setLoading] = useState(true);
    const sseData = useSSE<Position[]>(`${market}:positions`, () => fetchPositions(market));

    useEffect(() => {
        setLoading(true);
        setPositions([]);
        fetchPositions(market)
            .then(data => setPositions(data))
            .catch(() => {})
            .finally(() => setLoading(false));
    }, [market]);

    const displayPositions = sseData || positions;
    const sym = getMarketConfig(market).currencySymbol;

    if (loading && !sseData) {
        return (
            <div className="position-table-wrapper glass-panel">
                <h3 className="section-title">보유 포지션</h3>
                <div className="loading-placeholder">로딩 중...</div>
            </div>
        );
    }

    const totalPnl = displayPositions.reduce((sum, p) => sum + p.pnl, 0);

    return (
        <div className="position-table-wrapper glass-panel">
            <div className="section-header">
                <h3 className="section-title">
                    <ShieldAlert size={16} />
                    보유 포지션
                    <span className="count-badge">{displayPositions.length}</span>
                </h3>
                <div className={`total-pnl ${totalPnl >= 0 ? 'positive' : 'negative'}`}>
                    합계 {totalPnl >= 0 ? '+' : ''}{sym}{totalPnl.toLocaleString()}
                </div>
            </div>
            <div className="table-scroll">
                <table className="position-table">
                    <thead>
                        <tr>
                            <th>상태</th>
                            <th>종목</th>
                            <th className="num">수량</th>
                            <th className="num">진입가</th>
                            <th className="num">현재가</th>
                            <th className="num">수익률</th>
                            <th className="num">손익</th>
                            <th className="num">손절가</th>
                            <th className="num">익절가</th>
                            <th className="num">
                                <Clock size={12} /> 보유
                            </th>
                            <th className="num">비중</th>
                        </tr>
                    </thead>
                    <tbody>
                        {displayPositions.map(pos => {
                            const badge = STATUS_BADGE[pos.status];
                            const isProfit = pos.pnl >= 0;
                            const holdingWarn = pos.days_held >= pos.max_holding_days - 2;
                            return (
                                <tr key={pos.id}>
                                    <td>
                                        <span className="pos-status-badge" style={{ borderColor: badge.color, color: badge.color }}>
                                            {badge.label}
                                        </span>
                                    </td>
                                    <td className="stock-cell">
                                        <span className="stock-name">{pos.stock_name}</span>
                                        <span className="stock-code">{pos.stock_code}</span>
                                    </td>
                                    <td className="num">{pos.quantity.toLocaleString()}</td>
                                    <td className="num">{sym}{pos.entry_price.toLocaleString()}</td>
                                    <td className="num">{sym}{pos.current_price.toLocaleString()}</td>
                                    <td className={`num ${isProfit ? 'text-profit' : 'text-loss'}`}>
                                        <span className="pnl-cell">
                                            {isProfit ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                                            {isProfit ? '+' : ''}{pos.pnl_pct.toFixed(2)}%
                                        </span>
                                    </td>
                                    <td className={`num ${isProfit ? 'text-profit' : 'text-loss'}`}>
                                        {isProfit ? '+' : ''}{sym}{pos.pnl.toLocaleString()}
                                    </td>
                                    <td className="num stop-price">{sym}{pos.stop_loss.toLocaleString()}</td>
                                    <td className="num tp-price">{sym}{pos.take_profit.toLocaleString()}</td>
                                    <td className={`num ${holdingWarn ? 'holding-warn' : ''}`}>
                                        {pos.days_held}/{pos.max_holding_days}일
                                    </td>
                                    <td className="num">{pos.weight_pct.toFixed(1)}%</td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
