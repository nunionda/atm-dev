import { useState, useEffect } from 'react';
import { fetchMarketOverview, type MarketOverview } from '../../lib/api';
import './MarketPulse.css';

interface MarketPulseProps {
    onSelectIndex?: (symbol: string) => void;
}

export function MarketPulse({ onSelectIndex }: MarketPulseProps) {
    const [data, setData] = useState<MarketOverview | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        let mounted = true;

        async function load() {
            const result = await fetchMarketOverview();
            if (mounted) {
                setData(result);
                setLoading(false);
            }
        }

        load();

        // Auto-refresh every 5 minutes
        const interval = setInterval(load, 5 * 60 * 1000);
        return () => {
            mounted = false;
            clearInterval(interval);
        };
    }, []);

    if (loading) {
        return (
            <div className="market-pulse">
                <div className="market-pulse-bar">
                    <div className="pulse-loading">
                        <span>시장 데이터 로딩 중...</span>
                    </div>
                </div>
            </div>
        );
    }

    if (!data) return null;

    const regimeClass = data.regime.regime === 'RISK_ON'
        ? 'risk-on'
        : data.regime.regime === 'RISK_OFF'
            ? 'risk-off'
            : 'neutral';

    const globalIndices = data.indices.filter(i => i.group === 'global');
    const koreaIndices = data.indices.filter(i => i.group === 'korea');

    const renderItem = (idx: typeof data.indices[0]) => {
        const changeClass = (idx.change_pct ?? 0) > 0
            ? 'up'
            : (idx.change_pct ?? 0) < 0
                ? 'down'
                : 'flat';
        const sign = (idx.change_pct ?? 0) >= 0 ? '+' : '';

        return (
            <div
                key={idx.symbol}
                className="pulse-item"
                onClick={() => onSelectIndex?.(idx.symbol)}
                title={idx.name_kr}
            >
                <span className="pulse-item-name">{idx.name}</span>
                <span className="pulse-item-price">
                    {idx.price?.toLocaleString(undefined, { maximumFractionDigits: 2 }) ?? '—'}
                </span>
                <span className={`pulse-item-change ${changeClass}`}>
                    {idx.change_pct !== null
                        ? `${sign}${idx.change_pct.toFixed(2)}%`
                        : '—'}
                </span>
            </div>
        );
    };

    return (
        <div className="market-pulse">
            <div className="market-pulse-bar">
                <div className="pulse-group-label">🌐 Global</div>
                {globalIndices.map(renderItem)}

                <div className="pulse-divider"></div>

                <div className="pulse-group-label kr">🇰🇷 한국</div>
                {koreaIndices.map(renderItem)}

                {/* Regime Badge */}
                <div className="regime-section">
                    <div className={`regime-badge ${regimeClass}`}>
                        <span className="regime-dot"></span>
                        {data.regime.label_kr}
                    </div>
                    <span className="regime-label">Market Regime</span>
                </div>
            </div>
        </div>
    );
}
