import { useState, useEffect, useCallback } from 'react';
import { FileText, ArrowUpRight, ArrowDownRight, RefreshCw } from 'lucide-react';
import type { Order, MarketId } from '../../lib/api';
import { fetchOrders, getMarketConfig } from '../../lib/api';
import { useSSE } from '../../hooks/useSSE';
import './OrderLog.css';

const ORDER_STATUS_STYLE: Record<string, { label: string; color: string }> = {
    PENDING: { label: '대기', color: '#eab308' },
    FILLED: { label: '체결', color: '#22c55e' },
    PARTIAL: { label: '부분체결', color: '#3b82f6' },
    CANCELLED: { label: '취소', color: '#6b7280' },
    REJECTED: { label: '거부', color: '#ef4444' },
};

interface Props {
    market: MarketId;
}

export function OrderLog({ market }: Props) {
    const [orders, setOrders] = useState<Order[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(false);
    const sseData = useSSE<Order[]>(`${market}:orders`, () => fetchOrders(market));

    const loadData = useCallback(() => {
        setLoading(true);
        setError(false);
        setOrders([]);
        fetchOrders(market)
            .then(data => setOrders(data))
            .catch(() => setError(true))
            .finally(() => setLoading(false));
    }, [market]);

    useEffect(() => { loadData(); }, [loadData]);

    const displayOrders = sseData || orders;
    const sym = getMarketConfig(market).currencySymbol;

    if (loading && !sseData) {
        return (
            <div className="order-log-wrapper glass-panel">
                <h3 className="section-title"><FileText size={16} /> 주문 내역</h3>
                <div className="loading-placeholder">로딩 중...</div>
            </div>
        );
    }

    if (error && !sseData && displayOrders.length === 0) {
        return (
            <div className="order-log-wrapper glass-panel">
                <h3 className="section-title"><FileText size={16} /> 주문 내역</h3>
                <div className="error-placeholder">
                    서버 연결 실패
                    <button className="retry-btn" onClick={loadData}><RefreshCw size={12} /> 재시도</button>
                </div>
            </div>
        );
    }

    return (
        <div className="order-log-wrapper glass-panel">
            <div className="section-header">
                <h3 className="section-title">
                    <FileText size={16} />
                    주문 내역
                    <span className="count-badge">{displayOrders.length}</span>
                </h3>
            </div>
            <div className="table-scroll">
                <table className="order-table">
                    <thead>
                        <tr>
                            <th>시간</th>
                            <th>종목</th>
                            <th>구분</th>
                            <th>유형</th>
                            <th className="num">주문가</th>
                            <th className="num">체결가</th>
                            <th className="num">수량</th>
                            <th>상태</th>
                            <th>사유</th>
                        </tr>
                    </thead>
                    <tbody>
                        {displayOrders.map(order => {
                            const statusStyle = ORDER_STATUS_STYLE[order.status];
                            return (
                                <tr key={order.id}>
                                    <td className="time-cell">
                                        {new Date(order.created_at).toLocaleString('ko-KR', {
                                            year: 'numeric', month: '2-digit', day: '2-digit',
                                            hour: '2-digit', minute: '2-digit'
                                        })}
                                    </td>
                                    <td>
                                        <span className="order-stock">{order.stock_name}</span>
                                    </td>
                                    <td>
                                        <span className={`side-badge ${order.side === 'BUY' ? 'buy' : 'sell'}`}>
                                            {order.side === 'BUY'
                                                ? <><ArrowUpRight size={12} /> 매수</>
                                                : <><ArrowDownRight size={12} /> 매도</>}
                                        </span>
                                    </td>
                                    <td className="type-cell">
                                        {order.order_type === 'LIMIT' ? '지정가' : '시장가'}
                                    </td>
                                    <td className="num">{sym}{order.price.toLocaleString()}</td>
                                    <td className="num">
                                        {order.filled_price ? `${sym}${order.filled_price.toLocaleString()}` : '—'}
                                    </td>
                                    <td className="num">
                                        {order.filled_quantity}/{order.quantity}
                                    </td>
                                    <td>
                                        <span className="order-status-badge" style={{ color: statusStyle.color, borderColor: statusStyle.color }}>
                                            {statusStyle.label}
                                        </span>
                                    </td>
                                    <td className="reason-cell">{order.reason}</td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
