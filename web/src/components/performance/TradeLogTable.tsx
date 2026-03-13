import { TrendingUp, TrendingDown } from 'lucide-react';
import type { TradeRecord } from '../../lib/api';
import './TradeLogTable.css';

interface TradeLogTableProps {
    trades: TradeRecord[];
    currencySymbol?: string;
}

const EXIT_LABELS: Record<string, string> = {
    'ES1 손절 -3%': '손절',
    'ES2 익절 +7%': '익절',
    'ES3 트레일링스탑': '트레일링',
    'ES4 데드크로스': '데드크로스',
    'ES5 보유기간 초과 10일': '기간초과',
};

export function TradeLogTable({ trades, currencySymbol = '₩' }: TradeLogTableProps) {
    return (
        <div className="trade-log-wrapper glass-panel">
            <h3 className="section-title">거래 내역</h3>
            <div className="table-scroll">
                <table className="trade-log-table">
                    <thead>
                        <tr>
                            <th>종목</th>
                            <th>진입일</th>
                            <th>청산일</th>
                            <th className="num">진입가</th>
                            <th className="num">청산가</th>
                            <th className="num">수량</th>
                            <th className="num">수익률</th>
                            <th className="num">손익</th>
                            <th>청산사유</th>
                            <th className="num">보유일</th>
                        </tr>
                    </thead>
                    <tbody>
                        {trades.map(trade => {
                            const isWin = trade.pnl >= 0;
                            const shortReason = EXIT_LABELS[trade.exit_reason] || trade.exit_reason;
                            return (
                                <tr key={trade.id}>
                                    <td className="stock-cell">
                                        <span className="stock-name">{trade.stock_name}</span>
                                        <span className="stock-code">{trade.stock_code}</span>
                                    </td>
                                    <td className="date-cell">{trade.entry_date}</td>
                                    <td className="date-cell">{trade.exit_date}</td>
                                    <td className="num">{currencySymbol}{trade.entry_price.toLocaleString()}</td>
                                    <td className="num">{currencySymbol}{trade.exit_price.toLocaleString()}</td>
                                    <td className="num">{trade.quantity}</td>
                                    <td className={`num ${isWin ? 'text-profit' : 'text-loss'}`}>
                                        <span className="pnl-cell">
                                            {isWin ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                                            {isWin ? '+' : ''}{trade.pnl_pct.toFixed(2)}%
                                        </span>
                                    </td>
                                    <td className={`num ${isWin ? 'text-profit' : 'text-loss'}`}>
                                        {isWin ? '+' : ''}{currencySymbol}{trade.pnl.toLocaleString()}
                                    </td>
                                    <td>
                                        <span className={`exit-badge ${isWin ? 'win' : 'loss'}`}>
                                            {shortReason}
                                        </span>
                                    </td>
                                    <td className="num">{trade.holding_days}일</td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
