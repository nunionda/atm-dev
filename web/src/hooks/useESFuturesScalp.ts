import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import {
  fetchESFAnalysis,
  fetchESFVolumeProfile,
  fetchESFSessionStatus,
  fetchESFCandles,
  triggerESFBacktest,
  fetchESFBacktestStatus,
  fetchESFBacktestResult,
  triggerFuturesBacktest,
  type ESFAnalysis,
  type ESFCandle,
  type VolumeProfileData,
  type ESFSessionStatus,
  type ESFBacktestResult,
  type FuturesBacktestResult,
} from '../lib/api';
import { useFuturesScalp, type ScalpState } from './useFuturesScalp';
import type { FuturesAnalysis } from '../lib/api';

// ══════════════════════════════════════════
// Types
// ══════════════════════════════════════════

export type TabKey = 'strategy' | 'analysis' | 'decision' | 'backtest' | 'evolution';
export type BacktestMode = 'intraday' | 'daily';

export interface ESFuturesState {
  // Contract
  isMicro: boolean;
  setIsMicro: (v: boolean) => void;
  effectiveTicker: string;

  // Tab
  activeTab: TabKey;
  setActiveTab: (t: TabKey) => void;

  // Analysis data
  analysis: ESFAnalysis | null;
  volumeProfile: VolumeProfileData | null;
  sessionStatus: ESFSessionStatus | null;
  candles: ESFCandle[];
  loading: boolean;
  error: string | null;
  lastUpdated: number | null;

  // Chart controls
  chartInterval: string;
  setChartInterval: (v: string) => void;
  chartPeriod: string;
  setChartPeriod: (v: string) => void;
  activeSubcharts: { rsi: boolean; macd: boolean; zscore: boolean; atr: boolean; adx: boolean };
  setActiveSubcharts: (v: { rsi: boolean; macd: boolean; zscore: boolean; atr: boolean; adx: boolean }) => void;

  // Actions
  refresh: () => void;

  // Scalp Decision Engine (from useFuturesScalp)
  scalp: ScalpState;

  // Backtest (intraday)
  btMode: BacktestMode;
  setBtMode: (m: BacktestMode) => void;
  btPeriod: string;
  setBtPeriod: (v: string) => void;
  btEquity: number;
  setBtEquity: (v: number) => void;
  btRunning: boolean;
  btProgress: number;
  btResult: ESFBacktestResult | null;
  btError: string | null;
  runBacktest: () => void;
  btOpen: boolean;
  setBtOpen: (v: boolean) => void;

  // Daily backtest
  dailyBtStartDate: string;
  setDailyBtStartDate: (v: string) => void;
  dailyBtEndDate: string;
  setDailyBtEndDate: (v: string) => void;
  dailyBtResult: FuturesBacktestResult | null;
  dailyBtRunning: boolean;
  dailyBtError: string | null;
  dailyBtElapsed: number;
  runDailyBacktest: () => void;
  setDailyPreset: (years: number) => void;
}

// ══════════════════════════════════════════
// Hook
// ══════════════════════════════════════════

export function useESFuturesScalp(): ESFuturesState {
  const [isMicro, setIsMicro] = useState(true);
  const [activeTab, setActiveTab] = useState<TabKey>('strategy');

  // Analysis state
  const [analysis, setAnalysis] = useState<ESFAnalysis | null>(null);
  const [volumeProfile, setVolumeProfile] = useState<VolumeProfileData | null>(null);
  const [sessionStatus, setSessionStatus] = useState<ESFSessionStatus | null>(null);
  const [candles, setCandles] = useState<ESFCandle[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<number | null>(null);

  // Chart
  const [chartInterval, setChartInterval] = useState('15m');
  const [chartPeriod, setChartPeriod] = useState('5d');
  const [activeSubcharts, setActiveSubcharts] = useState({ rsi: true, macd: true, zscore: false, atr: true, adx: true });

  // Backtest (intraday)
  const [btMode, setBtMode] = useState<BacktestMode>('intraday');
  const [btPeriod, setBtPeriod] = useState('60d');
  const [btEquity, setBtEquity] = useState(10000);
  const [btRunning, setBtRunning] = useState(false);
  const [btProgress, setBtProgress] = useState(0);
  const [btResult, setBtResult] = useState<ESFBacktestResult | null>(null);
  const [btError, setBtError] = useState<string | null>(null);
  const [btOpen, setBtOpen] = useState(false);

  // Daily backtest
  const [dailyBtStartDate, setDailyBtStartDate] = useState(() => {
    const d = new Date();
    d.setFullYear(d.getFullYear() - 2);
    return `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}${String(d.getDate()).padStart(2, '0')}`;
  });
  const [dailyBtEndDate, setDailyBtEndDate] = useState(() => {
    const d = new Date();
    return `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}${String(d.getDate()).padStart(2, '0')}`;
  });
  const [dailyBtResult, setDailyBtResult] = useState<FuturesBacktestResult | null>(null);
  const [dailyBtRunning, setDailyBtRunning] = useState(false);
  const [dailyBtError, setDailyBtError] = useState<string | null>(null);
  const [dailyBtElapsed, setDailyBtElapsed] = useState(0);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const refreshRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const dailyTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const effectiveTicker = isMicro ? 'MES=F' : 'ES=F';

  // Timeout wrapper
  const withTimeout = useCallback(<T,>(promise: Promise<T>, ms = 5000): Promise<T> => {
    return Promise.race([
      promise,
      new Promise<never>((_, reject) =>
        setTimeout(() => reject(new Error('Request timeout')), ms),
      ),
    ]);
  }, []);

  // Load all data
  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [analysisData, vpData, sessData, candleData] = await Promise.allSettled([
        withTimeout(fetchESFAnalysis(effectiveTicker)),
        withTimeout(fetchESFVolumeProfile(effectiveTicker)),
        withTimeout(fetchESFSessionStatus()),
        withTimeout(fetchESFCandles(effectiveTicker, chartInterval, chartPeriod), 15000),
      ]);

      if (analysisData.status === 'fulfilled') setAnalysis(analysisData.value);
      else setError('Backend not available — start API server (python3 main.py api)');

      if (vpData.status === 'fulfilled') setVolumeProfile(vpData.value);
      if (sessData.status === 'fulfilled') setSessionStatus(sessData.value);
      if (candleData.status === 'fulfilled') setCandles(candleData.value.candles);
      setLastUpdated(Date.now());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load data');
    } finally {
      setLoading(false);
    }
  }, [effectiveTicker, chartInterval, chartPeriod, withTimeout]);

  // Initial load + on ticker change
  useEffect(() => {
    setAnalysis(null);
    setVolumeProfile(null);
    loadData();
  }, [loadData]);

  // Session-aware auto-refresh polling
  useEffect(() => {
    const getInterval = () => {
      if (!sessionStatus) return 30_000;  // unknown: 30s
      if (sessionStatus.is_rth) return 15_000; // RTH: 15s
      if (sessionStatus.session === 'ETH' || sessionStatus.session === 'GLOBEX') return 60_000; // ETH: 60s
      return 120_000; // closed: 2min (catch session open)
    };

    const interval = getInterval();
    if (interval === 0) {
      if (refreshRef.current) { clearInterval(refreshRef.current); refreshRef.current = null; }
      return;
    }

    refreshRef.current = setInterval(loadData, interval);
    return () => { if (refreshRef.current) clearInterval(refreshRef.current); };
  }, [loadData, sessionStatus]);

  // Bridge ESF analysis to FuturesAnalysis shape for useFuturesScalp
  const futuresAnalysisBridge = useMemo((): FuturesAnalysis | null => {
    if (!analysis) return null;
    return {
      entry_price: analysis.entry_price,
      indicators: { atr: analysis.atr || 0 },
    } as FuturesAnalysis;
  }, [analysis]);

  // Scalp Decision Engine
  const scalp = useFuturesScalp(futuresAnalysisBridge);

  // Auto-populate Decision Engine from live candles (OHLC + Close + Manual)
  useEffect(() => {
    if (candles.length >= 3) {
      const slice = candles.slice(-50);
      // OHLC text
      const ohlcText = slice
        .map(c => `${c.open.toFixed(2)}, ${c.high.toFixed(2)}, ${c.low.toFixed(2)}, ${c.close.toFixed(2)}`)
        .join('\n');
      scalp.setOhlcText(ohlcText);
      // Close text
      const closeText = slice.map(c => c.close.toFixed(2)).join(', ');
      scalp.setCloseText(closeText);
    }
  }, [candles]); // eslint-disable-line react-hooks/exhaustive-deps

  // Sync spotPrice + futuresPrice from live analysis (dataMode 무관)
  useEffect(() => {
    if (analysis) {
      scalp.setInput('spotPrice')(analysis.entry_price);
      scalp.setInput('futuresPrice')(analysis.entry_price);
    }
  }, [analysis]); // eslint-disable-line react-hooks/exhaustive-deps

  // Intraday backtest
  const runBacktest = useCallback(async () => {
    setBtRunning(true);
    setBtResult(null);
    setBtError(null);
    setBtProgress(0);

    try {
      await triggerESFBacktest({
        ticker: effectiveTicker,
        period: btPeriod,
        initial_equity: btEquity,
        is_micro: isMicro,
      });

      pollRef.current = setInterval(async () => {
        try {
          const status = await fetchESFBacktestStatus();
          setBtProgress(status.progress);
          if (status.status === 'completed') {
            if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
            const result = await fetchESFBacktestResult();
            setBtResult(result);
            setBtRunning(false);
          } else if (status.status === 'failed') {
            if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
            setBtError('Backtest failed on server');
            setBtRunning(false);
          }
        } catch { /* keep polling */ }
      }, 2000);
    } catch (e: unknown) {
      setBtError(e instanceof Error ? e.message : 'Failed to start backtest');
      setBtRunning(false);
    }
  }, [effectiveTicker, btPeriod, btEquity, isMicro]);

  // Daily backtest
  const setDailyPreset = useCallback((years: number) => {
    const now = new Date();
    const end = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}`;
    const start = new Date(now);
    start.setFullYear(start.getFullYear() - years);
    const startStr = `${start.getFullYear()}${String(start.getMonth() + 1).padStart(2, '0')}${String(start.getDate()).padStart(2, '0')}`;
    setDailyBtStartDate(startStr);
    setDailyBtEndDate(end);
  }, []);

  const runDailyBacktest = useCallback(async () => {
    setDailyBtRunning(true);
    setDailyBtResult(null);
    setDailyBtError(null);
    setDailyBtElapsed(0);
    dailyTimerRef.current = setInterval(() => setDailyBtElapsed(s => s + 1), 1000);
    try {
      const result = await triggerFuturesBacktest(effectiveTicker, dailyBtStartDate, dailyBtEndDate, btEquity, isMicro);
      if (result) {
        setDailyBtResult(result);
      } else {
        setDailyBtError('Backtest returned no result');
      }
    } catch (e: unknown) {
      setDailyBtError(e instanceof Error ? e.message : 'Unknown error');
    } finally {
      setDailyBtRunning(false);
      if (dailyTimerRef.current) { clearInterval(dailyTimerRef.current); dailyTimerRef.current = null; }
    }
  }, [effectiveTicker, dailyBtStartDate, dailyBtEndDate, btEquity, isMicro]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
      if (refreshRef.current) clearInterval(refreshRef.current);
      if (dailyTimerRef.current) clearInterval(dailyTimerRef.current);
    };
  }, []);

  return {
    isMicro, setIsMicro, effectiveTicker,
    activeTab, setActiveTab,
    analysis, volumeProfile, sessionStatus, candles,
    loading, error, lastUpdated,
    chartInterval, setChartInterval,
    chartPeriod, setChartPeriod,
    activeSubcharts, setActiveSubcharts,
    refresh: loadData,
    scalp,
    btMode, setBtMode,
    btPeriod, setBtPeriod,
    btEquity, setBtEquity,
    btRunning, btProgress,
    btResult, btError,
    runBacktest,
    btOpen, setBtOpen,
    dailyBtStartDate, setDailyBtStartDate,
    dailyBtEndDate, setDailyBtEndDate,
    dailyBtResult, dailyBtRunning, dailyBtError, dailyBtElapsed,
    runDailyBacktest, setDailyPreset,
  };
}
