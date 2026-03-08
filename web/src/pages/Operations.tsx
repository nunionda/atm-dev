import { useState } from 'react';
import { SystemStatusBar } from '../components/operations/SystemStatusBar';
import { PositionTable } from '../components/operations/PositionTable';
import { SignalList } from '../components/operations/SignalList';
import { OrderLog } from '../components/operations/OrderLog';
import type { MarketId } from '../lib/api';
import { MARKETS } from '../lib/api';
import './Operations.css';

export function Operations() {
    const [activeMarket, setActiveMarket] = useState<MarketId>('sp500');

    return (
        <div className="operations-page container">
            <SystemStatusBar market={activeMarket} />

            <div className="operations-header">
                <h1 className="page-title">Trading Operations</h1>
                <div className="market-tabs">
                    {MARKETS.map(m => (
                        <button
                            key={m.id}
                            className={`market-tab-btn ${activeMarket === m.id ? 'active' : ''}`}
                            onClick={() => setActiveMarket(m.id)}
                        >
                            <span className="market-flag">{m.flag}</span>
                            <span className="market-label">{m.label}</span>
                        </button>
                    ))}
                </div>
            </div>

            <div className="operations-grid">
                <div className="operations-main">
                    <PositionTable market={activeMarket} />
                </div>
                <div className="operations-side">
                    <SignalList market={activeMarket} />
                </div>
            </div>

            <OrderLog market={activeMarket} />
        </div>
    );
}
