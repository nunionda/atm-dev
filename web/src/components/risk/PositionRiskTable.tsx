import { useState, useEffect } from 'react';
import { ShieldAlert, TrendingUp, TrendingDown, AlertTriangle } from 'lucide-react';
import type { Position, MarketId } from '../../lib/api';
import { fetchPositions } from '../../lib/api';
import { useSSE } from '../../hooks/useSSE';
import './PositionRiskTable.css';

interface PositionRiskTableProps {
    market: MarketId;
    onPositionClick?: (ticker: string) => void;
}

export function PositionRiskTable({ market, onPositionClick }: PositionRiskTableProps) {
    const [positions, setPositions] = useState<Position[]>([]);
    const sseData = useSSE<Position[]>(`${market}:positions`, () => fetchPositions(market));

    useEffect(() => {
        fetchPositions(market).then(setPositions).catch(() => {});
    }, [market]);

    const allPositions = sseData || positions;
    const activePositions = allPositions.filter(p => p.status === 'ACTIVE' || p.status === 'PENDING');

    // Compute risk metrics per position
    const riskPositions = activePositions.map(pos => {
        const stopDistancePct = pos.stop_loss > 0
            ? ((pos.current_price - pos.stop_loss) / pos.current_price) * 100
            : 999;
        const holdingRatio = pos.max_holding_days > 0
            ? pos.days_held / pos.max_holding_days
            : 0;
        return { ...pos, stopDistancePct, holdingRatio };
    });

    // Sort by risk severity (closest to stop first)
    riskPositions.sort((a, b) => a.stopDistancePct - b.stopDistancePct);

    return (
        <div className="pos-risk-wrapper glass-panel">
            <div className="section-header">
                <h3 className="section-title">
                    <ShieldAlert size={16} />
                    포지션별 리스크
                    <span className="count-badge">{activePositions.length}</span>
                </h3>
            </div>

            {activePositions.length === 0 ? (
                <div className="pos-risk-empty">
                    <p>활성 포지션이 없습니다</p>
                </div>
            ) : (
                <div className="table-scroll">
                    <table className="pos-risk-table">
                        <thead>
                            <tr>
                                <th>종목</th>
                                <th className="num">수익률</th>
                                <th className="num">손절 거리</th>
                                <th className="num">비중</th>
                                <th className="num">보유기간</th>
                                <th className="num">위험</th>
                            </tr>
                        </thead>
                        <tbody>
                            {riskPositions.map(pos => {
                                const isProfit = pos.pnl_pct >= 0;
                                const stopDanger = pos.stopDistancePct < 2;
                                const holdingWarn = pos.holdingRatio >= 0.8;
                                const weightWarn = pos.weight_pct >= 12;
                                const riskLevel = stopDanger || holdingWarn || weightWarn ? 'high' : (pos.stopDistancePct < 5 || pos.holdingRatio >= 0.6) ? 'medium' : 'low';

                                return (
                                    <tr
                                        key={pos.id}
                                        className={`${riskLevel === 'high' ? 'risk-high' : ''} ${onPositionClick ? 'clickable-row' : ''}`}
                                        onClick={() => onPositionClick?.(pos.stock_code)}
                                    >
                                        <td className="stock-cell">
                                            <span className="stock-name">{pos.stock_name}</span>
                                            <span className="stock-code">{pos.stock_code}</span>
                                        </td>
                                        <td className={`num ${isProfit ? 'text-profit' : 'text-loss'}`}>
                                            <span className="pnl-cell">
                                                {isProfit ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                                                {isProfit ? '+' : ''}{pos.pnl_pct.toFixed(2)}%
                                            </span>
                                        </td>
                                        <td className={`num ${stopDanger ? 'text-loss' : ''}`}>
                                            {pos.stopDistancePct < 999 ? `${pos.stopDistancePct.toFixed(1)}%` : '—'}
                                        </td>
                                        <td className={`num ${weightWarn ? 'text-loss' : ''}`}>
                                            {pos.weight_pct.toFixed(1)}%
                                        </td>
                                        <td className={`num ${holdingWarn ? 'holding-warn' : ''}`}>
                                            <div className="holding-progress">
                                                <span>{pos.days_held}/{pos.max_holding_days}일</span>
                                                <div className="holding-bar">
                                                    <div
                                                        className={`holding-fill ${holdingWarn ? 'warn' : ''}`}
                                                        style={{ width: `${Math.min(pos.holdingRatio * 100, 100)}%` }}
                                                    />
                                                </div>
                                            </div>
                                        </td>
                                        <td className="num">
                                            {riskLevel === 'high' && <AlertTriangle size={14} className="risk-icon-high" />}
                                            {riskLevel === 'medium' && <AlertTriangle size={14} className="risk-icon-medium" />}
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
}
