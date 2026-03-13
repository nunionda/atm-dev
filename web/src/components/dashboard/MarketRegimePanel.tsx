import { useState, useEffect, useCallback } from 'react';
import { Globe, TrendingUp, TrendingDown, Activity, Shield, RefreshCw } from 'lucide-react';
import { fetchMarketOverview, type MarketOverview, type MarketIndex } from '../../lib/api';
import './MarketRegimePanel.css';

interface MarketRegimePanelProps {
    onSelectIndex?: (symbol: string) => void;
}

const US_SYMBOLS = ['^GSPC', '^IXIC', '^SOX'];
const KR_SYMBOLS = ['^KS11', '^KQ11', '^KS200', '091160.KS', 'KRW=X'];

function getVixLabel(price: number): { text: string; color: string } {
    if (price < 16) return { text: 'Low Fear', color: '#22c55e' };
    if (price < 20) return { text: 'Normal', color: '#94a3b8' };
    if (price < 25) return { text: 'Elevated', color: '#f59e0b' };
    if (price < 30) return { text: 'High', color: '#ef4444' };
    return { text: 'Extreme Fear', color: '#dc2626' };
}

function getDxyLabel(changePct: number): { text: string; color: string } {
    if (changePct > 0.3) return { text: '달러 강세', color: '#ef4444' };
    if (changePct < -0.3) return { text: '달러 약세', color: '#22c55e' };
    return { text: '안정', color: '#94a3b8' };
}

function changeColor(pct: number | null): string {
    if (pct === null) return 'var(--text-muted)';
    return pct > 0 ? '#22c55e' : pct < 0 ? '#ef4444' : 'var(--text-muted)';
}

function changeSign(pct: number | null): string {
    if (pct === null) return '—';
    return `${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%`;
}

function findIndex(indices: MarketIndex[], symbol: string): MarketIndex | undefined {
    return indices.find(i => i.symbol === symbol);
}

export function MarketRegimePanel({ onSelectIndex }: MarketRegimePanelProps) {
    const [data, setData] = useState<MarketOverview | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(false);

    const load = useCallback(async (signal?: AbortSignal) => {
        setLoading(true);
        setError(false);
        const result = await fetchMarketOverview(signal);
        if (signal?.aborted) return;
        if (result) {
            setData(result);
        } else {
            setError(true);
        }
        setLoading(false);
    }, []);

    useEffect(() => {
        const controller = new AbortController();
        load(controller.signal);
        const interval = setInterval(() => load(), 5 * 60 * 1000);
        return () => { controller.abort(); clearInterval(interval); };
    }, [load]);

    if (loading && !data) {
        return (
            <div className="regime-panel glass-panel">
                <div className="regime-loading">
                    <RefreshCw size={14} className="animate-spin" style={{ display: 'inline-block', marginRight: 6 }} />
                    시장 데이터 로딩 중...
                </div>
            </div>
        );
    }
    if (error && !data) {
        return (
            <div className="regime-panel glass-panel">
                <div className="regime-loading">
                    시장 데이터를 불러올 수 없습니다.
                    <button
                        onClick={() => load()}
                        style={{
                            marginLeft: 8,
                            padding: '3px 10px',
                            borderRadius: 6,
                            border: '1px solid rgba(255,255,255,0.15)',
                            background: 'rgba(255,255,255,0.05)',
                            color: 'var(--text-secondary)',
                            cursor: 'pointer',
                            fontSize: '0.8rem',
                        }}
                    >
                        재시도
                    </button>
                </div>
            </div>
        );
    }
    if (!data) return null;

    const regimeClass = data.regime.regime === 'RISK_ON' ? 'risk-on'
        : data.regime.regime === 'RISK_OFF' ? 'risk-off' : 'neutral';

    const usIndices = US_SYMBOLS.map(s => findIndex(data.indices, s)).filter(Boolean) as MarketIndex[];
    const vix = findIndex(data.indices, '^VIX');
    const dxy = findIndex(data.indices, 'DX-Y.NYB');
    const krIndices = KR_SYMBOLS.map(s => findIndex(data.indices, s)).filter(Boolean) as MarketIndex[];

    const vixInfo = vix?.price ? getVixLabel(vix.price) : null;
    const dxyInfo = dxy?.change_pct != null ? getDxyLabel(dxy.change_pct) : null;

    return (
        <div className="regime-panel glass-panel">
            {/* Header */}
            <div className="regime-header">
                <div className="regime-title">
                    <Globe size={16} />
                    <span>Market Regime</span>
                </div>
                <div className={`regime-badge ${regimeClass}`}>
                    <span className="regime-dot" />
                    {data.regime.label_kr}
                </div>
            </div>

            {/* US Major Indices */}
            <div className="regime-us-row">
                {usIndices.map(idx => {
                    const pct = idx.change_pct ?? 0;
                    const barWidth = Math.min(Math.abs(pct), 3) / 3 * 100;
                    return (
                        <div
                            key={idx.symbol}
                            className="regime-index-card"
                            onClick={() => onSelectIndex?.(idx.symbol)}
                        >
                            <div className="idx-name">{idx.name}</div>
                            <div className="idx-price">{idx.price?.toLocaleString(undefined, { maximumFractionDigits: 2 }) ?? '—'}</div>
                            <div className="idx-change" style={{ color: changeColor(idx.change_pct) }}>
                                {pct >= 0 ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                                {changeSign(idx.change_pct)}
                            </div>
                            <div className="idx-bar-track">
                                <div
                                    className={`idx-bar-fill ${pct >= 0 ? 'up' : 'down'}`}
                                    style={{ width: `${barWidth}%` }}
                                />
                            </div>
                        </div>
                    );
                })}

                {/* VIX Card */}
                {vix && (
                    <div className="regime-index-card risk-card" onClick={() => onSelectIndex?.(vix.symbol)}>
                        <div className="idx-name">
                            <Shield size={12} /> VIX
                        </div>
                        <div className="idx-price">{vix.price?.toFixed(2) ?? '—'}</div>
                        <div className="idx-change" style={{ color: changeColor(vix.change_pct) }}>
                            {changeSign(vix.change_pct)}
                        </div>
                        {vixInfo && (
                            <div className="idx-interpret" style={{ color: vixInfo.color }}>{vixInfo.text}</div>
                        )}
                    </div>
                )}

                {/* DXY Card */}
                {dxy && (
                    <div className="regime-index-card risk-card" onClick={() => onSelectIndex?.(dxy.symbol)}>
                        <div className="idx-name">DXY</div>
                        <div className="idx-price">{dxy.price?.toFixed(2) ?? '—'}</div>
                        <div className="idx-change" style={{ color: changeColor(dxy.change_pct) }}>
                            {changeSign(dxy.change_pct)}
                        </div>
                        {dxyInfo && (
                            <div className="idx-interpret" style={{ color: dxyInfo.color }}>{dxyInfo.text}</div>
                        )}
                    </div>
                )}
            </div>

            {/* Bottom Row: KR + Analysis */}
            <div className="regime-bottom">
                <div className="regime-kr-section">
                    <div className="regime-section-label">한국 시장</div>
                    {krIndices.map(idx => (
                        <div
                            key={idx.symbol}
                            className="kr-item"
                            onClick={() => onSelectIndex?.(idx.symbol)}
                        >
                            <span className="kr-name">{idx.name_kr || idx.name}</span>
                            <span className="kr-price">{idx.price?.toLocaleString(undefined, { maximumFractionDigits: 2 }) ?? '—'}</span>
                            <span className="kr-change" style={{ color: changeColor(idx.change_pct) }}>
                                {changeSign(idx.change_pct)}
                            </span>
                        </div>
                    ))}
                </div>

                <div className="regime-analysis-section">
                    <div className="regime-section-label">
                        <Activity size={12} /> 레짐 분석
                    </div>
                    <ul className="regime-signals">
                        {data.regime.signals.map((sig, i) => (
                            <li key={i}>{sig}</li>
                        ))}
                    </ul>
                    {/* Score Bar */}
                    <div className="score-bar-wrapper">
                        <span className="score-label">Score</span>
                        <div className="score-bar">
                            <div className="score-track">
                                <div
                                    className="score-marker"
                                    style={{ left: `${((data.regime.score + 3) / 6) * 100}%` }}
                                />
                            </div>
                            <div className="score-labels">
                                <span>-3</span>
                                <span>0</span>
                                <span>+3</span>
                            </div>
                        </div>
                        <span className="score-value">{data.regime.score >= 0 ? '+' : ''}{data.regime.score}</span>
                    </div>
                </div>
            </div>
        </div>
    );
}
