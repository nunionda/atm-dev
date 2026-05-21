/**
 * FuturesMonitorGrid — 4종목 선물 2x2 모니터링 그래프.
 *
 * 종목: ES=F (S&P500), NQ=F (NASDAQ), CL=F (WTI), GC=F (Gold)
 * 데이터: yfinance 폴링 (60초), 3개월 일봉 캔들
 * 사용: /futures 페이지 상단
 */
import { useEffect, useRef, useState } from 'react';
import {
    createChart,
    type IChartApi,
    type CandlestickData,
    type UTCTimestamp,
} from 'lightweight-charts';
import { fetchAnalyticsData, type AnalyticsResponse } from '@lib/api';
import './FuturesMonitorGrid.css';

interface FuturesInstrument {
    ticker: string;
    name: string;
    flag: string;
}

const INSTRUMENTS: FuturesInstrument[] = [
    { ticker: 'ES=F', name: 'S&P 500',    flag: '🇺🇸' },
    { ticker: 'NQ=F', name: 'NASDAQ 100', flag: '💻' },
    { ticker: 'CL=F', name: 'WTI Crude',  flag: '🛢️' },
    { ticker: 'GC=F', name: 'Gold',       flag: '🥇' },
];

const POLL_INTERVAL_MS = 60_000;
const CHART_PERIOD = '3mo';
const CHART_INTERVAL = '1d';

function toUTCTime(datetime: string): UTCTimestamp {
    // datetime: "YYYY-MM-DD" 또는 ISO. 일봉이므로 날짜만 의미.
    const d = new Date(datetime);
    return Math.floor(d.getTime() / 1000) as UTCTimestamp;
}

interface MiniChartProps {
    inst: FuturesInstrument;
}

function MiniChart({ inst }: MiniChartProps) {
    const chartRef = useRef<HTMLDivElement>(null);
    const chartApiRef = useRef<IChartApi | null>(null);
    const [data, setData] = useState<AnalyticsResponse | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

    // ── 데이터 폴링 ──
    useEffect(() => {
        let cancelled = false;
        const load = async () => {
            try {
                const res = await fetchAnalyticsData(inst.ticker, CHART_PERIOD, CHART_INTERVAL);
                if (!cancelled) {
                    setData(res);
                    setLastUpdated(new Date());
                    setError(null);
                }
            } catch (e: unknown) {
                if (!cancelled) setError(e instanceof Error ? e.message : 'load failed');
            } finally {
                if (!cancelled) setLoading(false);
            }
        };
        load();
        const id = setInterval(load, POLL_INTERVAL_MS);
        return () => {
            cancelled = true;
            clearInterval(id);
        };
    }, [inst.ticker]);

    // ── 차트 렌더 ──
    useEffect(() => {
        if (!chartRef.current || !data || data.data.length === 0) return;

        // 기존 차트 정리
        if (chartApiRef.current) {
            chartApiRef.current.remove();
            chartApiRef.current = null;
        }

        const container = chartRef.current;
        const chart = createChart(container, {
            width: container.clientWidth,
            height: 180,
            layout: {
                background: { color: 'transparent' },
                textColor: '#94a3b8',
                fontSize: 10,
            },
            grid: {
                vertLines: { color: 'rgba(255,255,255,0.04)' },
                horzLines: { color: 'rgba(255,255,255,0.04)' },
            },
            rightPriceScale: {
                borderColor: 'rgba(255,255,255,0.06)',
                scaleMargins: { top: 0.1, bottom: 0.05 },
            },
            timeScale: {
                borderColor: 'rgba(255,255,255,0.06)',
                timeVisible: false,
                rightOffset: 2,
            },
            crosshair: { mode: 1 },
            handleScroll: false,
            handleScale: false,
        });
        chartApiRef.current = chart;

        const series = chart.addCandlestickSeries({
            upColor: '#26a69a',
            downColor: '#ef5350',
            borderVisible: false,
            wickUpColor: '#26a69a',
            wickDownColor: '#ef5350',
        });

        // dedupe by time (lightweight-charts 요구사항)
        const seen = new Set<number>();
        const candleData: CandlestickData[] = [];
        for (const d of data.data) {
            const t = toUTCTime(d.datetime);
            if (seen.has(t)) continue;
            seen.add(t);
            candleData.push({
                time: t,
                open: d.open,
                high: d.high,
                low: d.low,
                close: d.close,
            });
        }
        // 시간순 정렬
        candleData.sort((a, b) => (a.time as number) - (b.time as number));
        series.setData(candleData);
        chart.timeScale().fitContent();

        // resize
        const onResize = () => {
            if (chartApiRef.current && chartRef.current) {
                chartApiRef.current.applyOptions({ width: chartRef.current.clientWidth });
            }
        };
        window.addEventListener('resize', onResize);

        return () => {
            window.removeEventListener('resize', onResize);
            if (chartApiRef.current) {
                chartApiRef.current.remove();
                chartApiRef.current = null;
            }
        };
    }, [data]);

    // ── 가격/변동률 ──
    const last = data?.data[data.data.length - 1];
    const prev = data?.data[data.data.length - 2];
    const price = last?.close ?? 0;
    const change = last && prev ? last.close - prev.close : 0;
    const changePct = prev?.close ? (change / prev.close) * 100 : 0;
    const isUp = change >= 0;

    const lastAgo = lastUpdated
        ? (() => {
            const s = Math.floor((Date.now() - lastUpdated.getTime()) / 1000);
            if (s < 60) return `${s}s ago`;
            return `${Math.floor(s / 60)}m ago`;
        })()
        : '';

    return (
        <div className="fmg-card">
            <div className="fmg-card-head">
                <div className="fmg-card-title">
                    <span className="fmg-flag">{inst.flag}</span>
                    <span className="fmg-ticker">{inst.ticker}</span>
                    <span className="fmg-name">{inst.name}</span>
                </div>
                <div className="fmg-card-price">
                    {loading && !data ? (
                        <span className="fmg-loading">…</span>
                    ) : (
                        <>
                            <span className="fmg-price">
                                {price >= 1000 ? price.toLocaleString(undefined, { maximumFractionDigits: 2 }) : price.toFixed(2)}
                            </span>
                            <span className={`fmg-change ${isUp ? 'up' : 'down'}`}>
                                {isUp ? '+' : ''}{change.toFixed(2)} ({isUp ? '+' : ''}{changePct.toFixed(2)}%)
                            </span>
                        </>
                    )}
                </div>
            </div>
            <div className="fmg-chart" ref={chartRef} />
            <div className="fmg-card-foot">
                <span className="fmg-period">3M Daily</span>
                {error ? (
                    <span className="fmg-error">⚠ {error.slice(0, 40)}</span>
                ) : (
                    <span className="fmg-updated">{lastAgo}</span>
                )}
            </div>
        </div>
    );
}

export function FuturesMonitorGrid() {
    return (
        <div className="fmg-grid">
            {INSTRUMENTS.map(inst => (
                <MiniChart key={inst.ticker} inst={inst} />
            ))}
        </div>
    );
}
