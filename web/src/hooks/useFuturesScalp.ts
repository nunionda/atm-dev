import { useMemo, useState, useCallback, useEffect } from 'react';
import {
  computeScalpAnalysis,
  parseCloses,
  parseOHLC,
  statsFromCloses,
  statsFromOHLC,
  SAMPLE_CLOSE,
  SAMPLE_OHLC,
  type ScalpInputs,
  type ScalpAnalysis,
  type AutoStats,
  type OHLCCandle,
} from '../lib/futuresScalpEngine';
import type { FuturesAnalysis } from '../lib/api';

export type DataMode = 'ohlc' | 'close' | 'manual';

export interface ScalpState {
  // Data input
  dataMode: DataMode;
  setDataMode: (mode: DataMode) => void;
  closeText: string;
  setCloseText: (text: string) => void;
  ohlcText: string;
  setOhlcText: (text: string) => void;
  maPeriod: number;
  setMaPeriod: (p: number) => void;
  // Parsed counts
  closesCount: number;
  candlesCount: number;
  // Auto stats
  autoStats: AutoStats | null;
  // Inputs (editable)
  inputs: ScalpInputs;
  setInput: (key: keyof ScalpInputs) => (value: number | string) => void;
  setAsset: (asset: 'ES' | 'MES') => void;
  // Calculation result
  calc: ScalpAnalysis;
  // Data validity
  dataValid: boolean;
}

const DEFAULT_INPUTS: ScalpInputs = {
  asset: 'ES',
  currentPrice: 5920,
  ma: 5900,
  stdDev: 15,
  atr: 12,
  atrMult: 1.0,
  winRate: 58,
  avgWin: 6,
  avgLoss: 4,
  slippage: 0.5,
  commission: 2.25,
  accountBalance: 10000,
  riskPct: 2,
  spotPrice: 5918,
  futuresPrice: 5920,
};

export function useFuturesScalp(apiAnalysis: FuturesAnalysis | null): ScalpState {
  const [dataMode, setDataMode] = useState<DataMode>('ohlc');
  const [closeText, setCloseText] = useState(SAMPLE_CLOSE);
  const [ohlcText, setOhlcText] = useState(SAMPLE_OHLC);
  const [maPeriod, setMaPeriod] = useState(20);
  const [inputs, setInputs] = useState<ScalpInputs>(DEFAULT_INPUTS);

  // Parse data
  const closes = useMemo(() => parseCloses(closeText), [closeText]);
  const candles: OHLCCandle[] = useMemo(() => parseOHLC(ohlcText), [ohlcText]);

  // Auto stats
  const autoStats = useMemo(() => {
    if (dataMode === 'close') return statsFromCloses(closes, maPeriod);
    if (dataMode === 'ohlc') return statsFromOHLC(candles, maPeriod);
    return null;
  }, [dataMode, closes, candles, maPeriod]);

  // Sync auto stats → inputs
  useEffect(() => {
    if (dataMode !== 'manual' && autoStats) {
      setInputs(p => ({
        ...p,
        currentPrice: autoStats.currentPrice,
        ma: autoStats.ma,
        stdDev: autoStats.stdDev,
        atr: autoStats.atr,
        futuresPrice: autoStats.currentPrice,
      }));
    }
  }, [dataMode, autoStats]);

  // Sync API analysis → inputs (when switching to manual or on first load)
  useEffect(() => {
    if (apiAnalysis && dataMode === 'manual') {
      setInputs(p => ({
        ...p,
        currentPrice: apiAnalysis.entry_price || p.currentPrice,
        atr: apiAnalysis.indicators.atr || p.atr,
        futuresPrice: apiAnalysis.entry_price || p.futuresPrice,
      }));
    }
  }, [apiAnalysis, dataMode]);

  const setInput = useCallback(
    (key: keyof ScalpInputs) => (value: number | string) => {
      setInputs(p => ({ ...p, [key]: typeof value === 'string' ? value : value }));
    },
    [],
  );

  const setAsset = useCallback((asset: 'ES' | 'MES') => {
    setInputs(p => ({ ...p, asset }));
  }, []);

  // Core calculation
  const calc = useMemo(() => computeScalpAnalysis(inputs), [inputs]);

  const dataValid = dataMode === 'manual' || (dataMode === 'close' ? closes.length >= 3 : candles.length >= 3);

  return {
    dataMode, setDataMode,
    closeText, setCloseText,
    ohlcText, setOhlcText,
    maPeriod, setMaPeriod,
    closesCount: closes.length,
    candlesCount: candles.length,
    autoStats,
    inputs, setInput, setAsset,
    calc,
    dataValid,
  };
}
