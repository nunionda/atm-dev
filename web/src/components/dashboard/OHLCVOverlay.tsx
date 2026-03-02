import type { AnalyticsData } from '../../lib/api';
import './OHLCVOverlay.css';

export interface CrosshairData {
    datetime: string;
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
    change: number;
    changePct: number;
    sma_20?: number | null;
    bb_hband?: number | null;
    bb_lband?: number | null;
    rsi_14?: number | null;
    macd?: number | null;
}

interface OHLCVOverlayProps {
    data: CrosshairData | null;
    latest: AnalyticsData | null;
    ticker: string;
    interval: string;
    isKorean: boolean;
}

function fmtP(v: number | null | undefined, isKr: boolean): string {
    if (v == null) return '—';
    return v.toLocaleString(undefined, { maximumFractionDigits: isKr ? 0 : 2 });
}

function fmtVol(v: number): string {
    if (v >= 1_000_000_000) return `${(v / 1_000_000_000).toFixed(1)}B`;
    if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
    if (v >= 1_000) return `${(v / 1_000).toFixed(0)}K`;
    return v.toLocaleString();
}

export function OHLCVOverlay({ data, latest, ticker, interval, isKorean }: OHLCVOverlayProps) {
    // Use crosshair data if available, otherwise latest candle
    const d = data ?? (latest ? {
        datetime: latest.datetime,
        open: latest.open,
        high: latest.high,
        low: latest.low,
        close: latest.close,
        volume: latest.volume,
        change: latest.close - latest.open,
        changePct: latest.open ? ((latest.close - latest.open) / latest.open) * 100 : 0,
        sma_20: latest.sma_20,
        bb_hband: latest.bb_hband,
        bb_lband: latest.bb_lband,
        rsi_14: latest.rsi_14,
        macd: latest.macd,
    } : null);

    if (!d) return null;

    const isUp = d.change >= 0;

    return (
        <div className="ohlcv-overlay">
            <div className="ohlcv-row">
                <span className="ohlcv-ticker">{ticker} · {interval.toUpperCase()}</span>
                <span className="ohlcv-lbl">O</span>
                <span className={`ohlcv-val ${isUp ? 'up' : 'down'}`}>{fmtP(d.open, isKorean)}</span>
                <span className="ohlcv-lbl">H</span>
                <span className="ohlcv-val up">{fmtP(d.high, isKorean)}</span>
                <span className="ohlcv-lbl">L</span>
                <span className="ohlcv-val down">{fmtP(d.low, isKorean)}</span>
                <span className="ohlcv-lbl">C</span>
                <span className={`ohlcv-val ${isUp ? 'up' : 'down'}`}>{fmtP(d.close, isKorean)}</span>
                <span className={`ohlcv-change ${isUp ? 'up' : 'down'}`}>
                    {isUp ? '+' : ''}{d.changePct.toFixed(2)}%
                </span>
                <span className="ohlcv-vol">V {fmtVol(d.volume)}</span>
            </div>
            <div className="ohlcv-row ohlcv-indicators">
                {d.sma_20 != null && <span className="ohlcv-ind"><b>SMA20</b> {fmtP(d.sma_20, isKorean)}</span>}
                {d.bb_hband != null && <span className="ohlcv-ind"><b>BB↑</b> {fmtP(d.bb_hband, isKorean)}</span>}
                {d.bb_lband != null && <span className="ohlcv-ind"><b>BB↓</b> {fmtP(d.bb_lband, isKorean)}</span>}
                {d.rsi_14 != null && <span className="ohlcv-ind"><b>RSI</b> {d.rsi_14.toFixed(1)}</span>}
                {d.macd != null && <span className="ohlcv-ind"><b>MACD</b> {d.macd.toFixed(2)}</span>}
            </div>
        </div>
    );
}
