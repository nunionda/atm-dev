import { useState, useEffect, useCallback, useMemo } from 'react';
import { FileText, ArrowUpRight, ArrowDownRight, RefreshCw, ArrowUpDown } from 'lucide-react';
import type { Order, MarketId } from '@lib/api';
import { fetchOrders, getMarketConfig } from '@lib/api';
import { useSSE } from '@hooks/useSSE';
import './OrderLog.css';

type SortKey = 'created_at' | 'stock_name' | 'side' | 'price';
type SortDir = 'asc' | 'desc';
type SideFilter = 'ALL' | 'BUY' | 'SELL';

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
    // C6.2: 정렬/필터 상태
    const [filter, setFilter] = useState('');
    const [sideFilter, setSideFilter] = useState<SideFilter>('ALL');
    const [sortKey, setSortKey] = useState<SortKey>('created_at');
    const [sortDir, setSortDir] = useState<SortDir>('desc');

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

    const rawOrders = sseData || orders;
    const sym = getMarketConfig(market).currencySymbol;

    // C6.2: 필터 + 정렬 적용
    const displayOrders = useMemo(() => {
        let result = rawOrders;
        if (sideFilter !== 'ALL') {
            result = result.filter(o => o.side === sideFilter);
        }
        if (filter) {
            const q = filter.toLowerCase();
            result = result.filter(o =>
                (o.stock_name || '').toLowerCase().includes(q) ||
                (o.stock_code || '').toLowerCase().includes(q) ||
                (o.reason || '').toLowerCase().includes(q)
            );
        }
        const sorted = [...result].sort((a, b) => {
            let cmp = 0;
            if (sortKey === 'created_at') cmp = (a.created_at || '').localeCompare(b.created_at || '');
            else if (sortKey === 'stock_name') cmp = (a.stock_name || '').localeCompare(b.stock_name || '');
            else if (sortKey === 'side') cmp = (a.side || '').localeCompare(b.side || '');
            else if (sortKey === 'price') cmp = (a.price || 0) - (b.price || 0);
            return sortDir === 'asc' ? cmp : -cmp;
        });
        return sorted;
    }, [rawOrders, filter, sideFilter, sortKey, sortDir]);

    const toggleSort = (key: SortKey) => {
        if (sortKey === key) setSortDir(sortDir === 'asc' ? 'desc' : 'asc');
        else { setSortKey(key); setSortDir('desc'); }
    };

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
                    <span className="count-badge">{displayOrders.length}{filter || sideFilter !== 'ALL' ? `/${rawOrders.length}` : ''}</span>
                </h3>
                {/* C6.2: 필터 + 정렬 */}
                <div className="order-controls">
                    <select
                        className="order-side-filter"
                        value={sideFilter}
                        onChange={e => setSideFilter(e.target.value as SideFilter)}
                    >
                        <option value="ALL">전체</option>
                        <option value="BUY">매수</option>
                        <option value="SELL">매도</option>
                    </select>
                    <input
                        type="text"
                        className="order-filter-input"
                        placeholder="종목/사유 검색..."
                        value={filter}
                        onChange={e => setFilter(e.target.value)}
                    />
                </div>
            </div>
            <div className="table-scroll">
                <table className="order-table">
                    <thead>
                        <tr>
                            <th className="sortable" onClick={() => toggleSort('created_at')}>
                                시간 {sortKey === 'created_at' && <ArrowUpDown size={10} />}
                            </th>
                            <th className="sortable" onClick={() => toggleSort('stock_name')}>
                                종목 {sortKey === 'stock_name' && <ArrowUpDown size={10} />}
                            </th>
                            <th className="sortable" onClick={() => toggleSort('side')}>
                                구분 {sortKey === 'side' && <ArrowUpDown size={10} />}
                            </th>
                            <th>유형</th>
                            <th className="num sortable" onClick={() => toggleSort('price')}>
                                주문가 {sortKey === 'price' && <ArrowUpDown size={10} />}
                            </th>
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
                                    <td className="num">{sym}{order.price.toLocaleString(undefined, { maximumFractionDigits: 0 })}</td>
                                    <td className="num">
                                        {order.filled_price ? `${sym}${order.filled_price.toLocaleString(undefined, { maximumFractionDigits: 0 })}` : '—'}
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
