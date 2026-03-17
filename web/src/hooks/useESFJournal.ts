import { useState, useEffect, useCallback } from 'react';
import type {
  ESFHypothesis, ESFResult, ESFVariant, ESFExperiment,
  ESFCumulativeStat, ESFExperimentStatus,
} from '../lib/api';
import {
  createHypothesis, createABHypotheses, fetchTodayHypotheses, fetchHypotheses,
  recordResult as apiRecordResult, skipHypothesis as apiSkipHypothesis,
  fetchCumulativeStats, fetchVariants as apiFetchVariants,
  fetchExperiments as apiFetchExperiments, fetchExperimentStatus,
  createVariant as apiCreateVariant, createExperiment as apiCreateExperiment,
  concludeExperiment as apiConcludeExperiment, graduateWinner as apiGraduateWinner,
  fetchStatsTrends,
} from '../lib/api';

export interface ESFJournalState {
  // Today's hypothesis
  todayHypotheses: ESFHypothesis[];
  todayLoading: boolean;

  // History
  hypotheses: ESFHypothesis[];
  hypothesesTotal: number;
  historyPage: number;
  setHistoryPage: (p: number) => void;

  // Stats
  stats: ESFCumulativeStat[];
  statsLoading: boolean;

  // Variants
  variants: ESFVariant[];

  // Experiments
  experiments: ESFExperiment[];
  activeExperimentStatus: ESFExperimentStatus | null;

  // Trends
  trends: any[];

  // Actions
  generateHypothesis: (ticker?: string, variantId?: number) => Promise<ESFHypothesis | null>;
  generateABHypotheses: (ticker: string, experimentId: number) => Promise<ESFHypothesis[]>;
  recordResult: (data: Parameters<typeof apiRecordResult>[0]) => Promise<ESFResult | null>;
  skipHypothesis: (hypothesisId: number, reason?: string) => Promise<void>;
  refreshStats: (dimension?: string) => Promise<void>;
  refreshToday: () => Promise<void>;
  refreshHistory: (filters?: Record<string, any>) => Promise<void>;
  createVariant: (data: { name: string; description?: string; param_overrides?: Record<string, any> }) => Promise<ESFVariant | null>;
  createExperiment: (data: { name: string; variant_a_id: number; variant_b_id: number; min_trades?: number; max_days?: number }) => Promise<ESFExperiment | null>;
  concludeExperiment: (experimentId: number) => Promise<any>;
  graduateWinner: (experimentId: number) => Promise<any>;

  // Error
  error: string | null;
}

export function useESFJournal(effectiveTicker: string = 'ES=F'): ESFJournalState {
  const [todayHypotheses, setTodayHypotheses] = useState<ESFHypothesis[]>([]);
  const [todayLoading, setTodayLoading] = useState(false);
  const [hypotheses, setHypotheses] = useState<ESFHypothesis[]>([]);
  const [hypothesesTotal, setHypothesesTotal] = useState(0);
  const [historyPage, setHistoryPage] = useState(0);
  const [stats, setStats] = useState<ESFCumulativeStat[]>([]);
  const [statsLoading, setStatsLoading] = useState(false);
  const [variants, setVariants] = useState<ESFVariant[]>([]);
  const [experiments, setExperiments] = useState<ESFExperiment[]>([]);
  const [activeExperimentStatus, setActiveExperimentStatus] = useState<ESFExperimentStatus | null>(null);
  const [trends, setTrends] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);

  // ── Refresh functions ──
  const refreshToday = useCallback(async () => {
    setTodayLoading(true);
    try {
      const data = await fetchTodayHypotheses();
      setTodayHypotheses(data);
      setError(null);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setTodayLoading(false);
    }
  }, []);

  const refreshHistory = useCallback(async (filters: Record<string, any> = {}) => {
    try {
      const data = await fetchHypotheses({ offset: historyPage * 20, limit: 20, ...filters });
      setHypotheses(data.items);
      setHypothesesTotal(data.total);
    } catch (e: any) {
      setError(e.message);
    }
  }, [historyPage]);

  const refreshStats = useCallback(async (dimension?: string) => {
    setStatsLoading(true);
    try {
      const data = await fetchCumulativeStats(dimension);
      setStats(data);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setStatsLoading(false);
    }
  }, []);

  const refreshVariantsAndExperiments = useCallback(async () => {
    try {
      const [v, e] = await Promise.all([apiFetchVariants(), apiFetchExperiments()]);
      setVariants(v);
      setExperiments(e);
      // Check active experiment
      const running = e.find((exp: ESFExperiment) => exp.status === 'RUNNING');
      if (running) {
        const status = await fetchExperimentStatus(running.experiment_id);
        setActiveExperimentStatus(status);
      } else {
        setActiveExperimentStatus(null);
      }
    } catch (e: any) {
      setError(e.message);
    }
  }, []);

  const refreshTrends = useCallback(async () => {
    try {
      const data = await fetchStatsTrends(30);
      setTrends(data);
    } catch {
      // Non-critical
    }
  }, []);

  // ── Actions ──
  const generateHypothesis = useCallback(async (ticker?: string, variantId?: number) => {
    try {
      const h = await createHypothesis(ticker || effectiveTicker, variantId);
      if (h && !('error' in h)) {
        await refreshToday();
        return h;
      }
      setError((h as any)?.error || 'Failed to generate');
      return null;
    } catch (e: any) {
      setError(e.message);
      return null;
    }
  }, [effectiveTicker, refreshToday]);

  const generateABHypothesesAction = useCallback(async (ticker: string, experimentId: number) => {
    try {
      const result = await createABHypotheses(ticker, experimentId);
      await refreshToday();
      return result;
    } catch (e: any) {
      setError(e.message);
      return [];
    }
  }, [refreshToday]);

  const recordResultAction = useCallback(async (data: Parameters<typeof apiRecordResult>[0]) => {
    try {
      const result = await apiRecordResult(data);
      await Promise.all([refreshToday(), refreshStats(), refreshHistory()]);
      return result;
    } catch (e: any) {
      setError(e.message);
      return null;
    }
  }, [refreshToday, refreshStats, refreshHistory]);

  const skipAction = useCallback(async (hypothesisId: number, reason?: string) => {
    try {
      await apiSkipHypothesis(hypothesisId, reason);
      await refreshToday();
    } catch (e: any) {
      setError(e.message);
    }
  }, [refreshToday]);

  const createVariantAction = useCallback(async (data: { name: string; description?: string; param_overrides?: Record<string, any> }) => {
    try {
      const v = await apiCreateVariant(data);
      await refreshVariantsAndExperiments();
      return v;
    } catch (e: any) {
      setError(e.message);
      return null;
    }
  }, [refreshVariantsAndExperiments]);

  const createExperimentAction = useCallback(async (data: { name: string; variant_a_id: number; variant_b_id: number; min_trades?: number; max_days?: number }) => {
    try {
      const exp = await apiCreateExperiment(data);
      await refreshVariantsAndExperiments();
      return exp;
    } catch (e: any) {
      setError(e.message);
      return null;
    }
  }, [refreshVariantsAndExperiments]);

  const concludeAction = useCallback(async (experimentId: number) => {
    try {
      const result = await apiConcludeExperiment(experimentId);
      await refreshVariantsAndExperiments();
      return result;
    } catch (e: any) {
      setError(e.message);
      return null;
    }
  }, [refreshVariantsAndExperiments]);

  const graduateAction = useCallback(async (experimentId: number) => {
    try {
      const result = await apiGraduateWinner(experimentId);
      await refreshVariantsAndExperiments();
      return result;
    } catch (e: any) {
      setError(e.message);
      return null;
    }
  }, [refreshVariantsAndExperiments]);

  // ── Initial load ──
  useEffect(() => {
    refreshToday();
    refreshStats();
    refreshVariantsAndExperiments();
    refreshTrends();
  }, []);  // eslint-disable-line react-hooks/exhaustive-deps

  // Refresh history when page changes
  useEffect(() => {
    refreshHistory();
  }, [historyPage]);  // eslint-disable-line react-hooks/exhaustive-deps

  return {
    todayHypotheses, todayLoading,
    hypotheses, hypothesesTotal, historyPage, setHistoryPage,
    stats, statsLoading,
    variants,
    experiments, activeExperimentStatus,
    trends,
    generateHypothesis, generateABHypotheses: generateABHypothesesAction,
    recordResult: recordResultAction, skipHypothesis: skipAction,
    refreshStats, refreshToday, refreshHistory,
    createVariant: createVariantAction, createExperiment: createExperimentAction,
    concludeExperiment: concludeAction, graduateWinner: graduateAction,
    error,
  };
}
