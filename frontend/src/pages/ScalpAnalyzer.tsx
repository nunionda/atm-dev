import { useState, useMemo, useCallback, useEffect, useRef, memo } from 'react';
import { Link } from 'react-router-dom';
import { createChart, ColorType, CrosshairMode, type IChartApi, type Time, LineStyle } from 'lightweight-charts';
import {
  clamp, fmt, fmtPct, fmtMoney,
  parseCloses, parseOHLC, statsFromCloses, statsFromOHLC,
  computeScalp,
  ASSETS, TICKER_MAP, SAMPLE_CLOSE, SAMPLE_OHLC, F, K,
  type OHLC, type ScalpInputs, type AutoStats, type VolumeSRResult,
} from '@lib/scalpEngine';
import { fetchAnalyticsData, fetchQuote, fetchMTFData } from '@lib/api';
import { usePolling } from '@hooks/usePolling';
import { PollingControl } from '@components/PollingControl';
import { Term, InfoCard } from '@components/glossary/GlossaryComponents';
import {
  initSession, buildScenarios, extractKeyLevels,
  checkAlerts, getActiveAlerts, evaluatePosition, suggestExitAction, formatHoldTime,
  PHASE_LABELS, PHASE_COLORS,
  type SessionState, type TradingPhase, type EntryRecord, type KeyLevel,
} from '@lib/tradingSession';
import { analyzeMTF, type MTFAnalysis } from '@lib/mtfEngine';

// Phase 3.C extracted sub-components
import { NIn }        from '@components/scalp-analyzer/NIn';
import { Pill }       from '@components/scalp-analyzer/Pill';
import { Met }        from '@components/scalp-analyzer/Met';
import { Sec }        from '@components/scalp-analyzer/Sec';
import { ZBar }       from '@components/scalp-analyzer/ZBar';
import { EVBar }      from '@components/scalp-analyzer/EVBar';
import { KGauge }     from '@components/scalp-analyzer/KGauge';
import { BasisBar }   from '@components/scalp-analyzer/BasisBar';
import { RRVis }      from '@components/scalp-analyzer/RRVis';
import { PriceChart } from '@components/scalp-analyzer/PriceChart';
import { Footer }              from '@components/scalp-analyzer/Footer';
import { FormulaReference }    from '@components/scalp-analyzer/FormulaReference';
import { BasisSpreadSection }  from '@components/scalp-analyzer/BasisSpreadSection';
import { ZScoreSection }       from '@components/scalp-analyzer/ZScoreSection';
import { ATRStopSection }      from '@components/scalp-analyzer/ATRStopSection';
import { MTFStructureSection } from '@components/scalp-analyzer/MTFStructureSection';
import { TradingSessionSection } from '@components/scalp-analyzer/TradingSessionSection';

import './ScalpAnalyzer.css';

// ASSETS 데이터에서 자동 생성 — 증거금/수수료/계좌잔고 자동 기입
const ASSET_DEFAULTS: Record<string, Partial<ScalpInputs>> = Object.fromEntries(
  Object.entries(ASSETS).map(([k, a]) => {
    const isKR = a.sym === '₩';
    return [k, {
      currentPrice: isKR ? 360 : (k.includes('NQ') || k.includes('MNQ') ? 21000 : 5900),
      ma: isKR ? 355 : (k.includes('NQ') || k.includes('MNQ') ? 20900 : 5880),
      stdDev: isKR ? 5 : (k.includes('NQ') || k.includes('MNQ') ? 80 : 15),
      atr: isKR ? 8 : (k.includes('NQ') || k.includes('MNQ') ? 60 : 12),
      slippage: isKR ? 1 : 0.5,
      commission: a.defaultCommission,
      accountBalance: a.recommendedBalance,
      spotPrice: isKR ? 360 : (k.includes('NQ') || k.includes('MNQ') ? 20980 : 5898),
      futuresPrice: isKR ? 360 : (k.includes('NQ') || k.includes('MNQ') ? 21000 : 5900),
    }];
  }),
);

// ── Atom Components ─────────────────────────────────────────────────

export function ScalpAnalyzer() {
  const [asset, setAsset] = useState("ES");
  const cfg = ASSETS[asset];

  const [dataMode, setDataMode] = useState<"close" | "ohlc" | "manual">("ohlc");
  const [closeText, setCloseText] = useState(SAMPLE_CLOSE);
  const [ohlcText, setOhlcText] = useState(SAMPLE_OHLC);
  const [maPeriod, setMaPeriod] = useState(20);
  const [liveLoaded, setLiveLoaded] = useState(false);
  const [candleDates, setCandleDates] = useState<string[]>([]);

  // ── Polling ──
  const tickers = TICKER_MAP[asset];
  const pollFn = useCallback(
    () => fetchQuote(tickers?.futures || 'ES=F', 50),
    [tickers?.futures],
  );
  const poll = usePolling(pollFn, { interval: 30000, enabled: false });

  // 폴링 데이터 수신 시 자동 업데이트
  useEffect(() => {
    const q = poll.data;
    if (!q?.candles || q.candles.length < 3) return;
    const ohlcLines = q.candles.map(c => {
      const o = c.open > 0 ? c.open : c.close;
      const h = c.high > 0 ? c.high : c.close;
      const l = c.low > 0 ? c.low : c.close;
      const v = c.volume ?? 0;
      return `${o.toFixed(2)}, ${h.toFixed(2)}, ${l.toFixed(2)}, ${c.close.toFixed(2)}, ${v}`;
    }).join('\n');
    const closeLines = q.candles.map(c => c.close.toFixed(2)).join(', ');
    setOhlcText(ohlcLines);
    setCloseText(closeLines);
    if (q.latest) {
      setInputs(p => ({ ...p, futuresPrice: q.latest.price }));
    }
    setLiveLoaded(true);
  }, [poll.data]);

  const closes = useMemo(() => parseCloses(closeText), [closeText]);
  const candles = useMemo(() => parseOHLC(ohlcText), [ohlcText]);

  const autoStats: AutoStats | null = useMemo(() => {
    if (dataMode === "close") return statsFromCloses(closes, maPeriod);
    if (dataMode === "ohlc") return statsFromOHLC(candles, maPeriod);
    return null;
  }, [dataMode, closes, candles, maPeriod]);

  const [inputs, setInputs] = useState<ScalpInputs>({
    asset: "ES",
    currentPrice: 5920, ma: 5900, stdDev: 15, atr: 12, atrMult: 1.0,
    winRate: 58, avgWin: 6, avgLoss: 4, slippage: 0.5, commission: 2.25,
    accountBalance: 10000, riskPct: 2, spotPrice: 5918, futuresPrice: 5920,
  });
  const s = useCallback((k: keyof ScalpInputs) => (v: number) => setInputs(p => ({ ...p, [k]: v })), []);

  // ── Session & MTF State ──
  const [session, setSession] = useState<SessionState | null>(null);
  const [mtfHTF, setMtfHTF] = useState<OHLC[]>([]);
  const [mtfLTF, setMtfLTF] = useState<OHLC[]>([]);
  const [mtfAnalysis, setMtfAnalysis] = useState<MTFAnalysis | null>(null);
  const [mtfLoading, setMtfLoading] = useState(false);
  const [mtfError, setMtfError] = useState<string | null>(null);
  const [mtfExpanded, setMtfExpanded] = useState(true);
  const [entryFormOpen, setEntryFormOpen] = useState(false);
  const [entryPrice, setEntryPrice] = useState('');
  const [entryContracts, setEntryContracts] = useState('1');

  useEffect(() => {
    if (dataMode !== "manual" && autoStats) {
      setInputs(p => ({
        ...p,
        currentPrice: autoStats.currentPrice,
        ma: autoStats.ma,
        stdDev: autoStats.stdDev,
        atr: autoStats.atr,
        futuresPrice: autoStats.currentPrice,
        dailyCandles: candles.length >= 14 ? candles.slice(-14) : undefined,
      }));
    }
  }, [dataMode, autoStats, candles]);

  const isInitialMount = useRef(true);
  useEffect(() => {
    const defaults = ASSET_DEFAULTS[asset];
    setInputs(p => ({ ...p, asset, ...(defaults || {}) }));
    // 초기 마운트 시에는 SAMPLE 데이터 유지, 에셋 변경 시에만 클리어
    if (isInitialMount.current) {
      isInitialMount.current = false;
    } else {
      setOhlcText('');
      setCloseText('');
    }
  }, [asset]);

  // Fetch live futures data based on selected asset
  useEffect(() => {
    let cancelled = false;
    setLiveLoaded(false);

    const tickers = TICKER_MAP[asset];
    if (!tickers) return;

    async function loadLiveData() {
      try {
        let futuresData;
        try {
          const res = await fetchAnalyticsData(tickers.futures, '3mo', '1d');
          if (res?.data && res.data.length >= 3) futuresData = res;
        } catch { /* fall through */ }

        if (!futuresData && tickers.fallback) {
          try {
            const res = await fetchAnalyticsData(tickers.fallback, '3mo', '1d');
            if (res?.data && res.data.length >= 3) futuresData = res;
          } catch { /* give up */ }
        }

        if (cancelled || !futuresData?.data || futuresData.data.length < 3) return;

        const recent = futuresData.data.slice(-50);
        // Fix incomplete bars (e.g. ^KS200 returns O/H/L=0 for latest bar)
        const ohlcLines = recent.map(d => {
          const o = d.open > 0 ? d.open : d.close;
          const h = d.high > 0 ? d.high : d.close;
          const l = d.low > 0 ? d.low : d.close;
          const v = d.volume ?? 0;
          return `${o.toFixed(2)}, ${h.toFixed(2)}, ${l.toFixed(2)}, ${d.close.toFixed(2)}, ${v}`;
        }).join('\n');
        const closeLines = recent.map(d => d.close.toFixed(2)).join(', ');

        setOhlcText(ohlcLines);
        setCloseText(closeLines);
        setCandleDates(recent.map(d => d.datetime.split(' ')[0]));

        const lastClose = futuresData.data[futuresData.data.length - 1].close;

        // Fetch spot price for basis spread (if different ticker)
        let spotClose = lastClose;
        if (tickers.spot !== tickers.futures) {
          try {
            const spx = await fetchAnalyticsData(tickers.spot, '3mo', '1d');
            if (spx?.data && spx.data.length > 0) {
              spotClose = spx.data[spx.data.length - 1].close;
            }
          } catch { /* use futures price as fallback */ }
        }

        if (cancelled) return;
        setInputs(p => ({ ...p, spotPrice: spotClose, futuresPrice: lastClose }));
        setLiveLoaded(true);
      } catch (err) {
        console.error('[ScalpAnalyzer] Live data load failed:', err);
      }
    }
    loadLiveData();
    return () => { cancelled = true; };
  }, [asset]);

  // ── Session Handlers ──
  const handleStartSession = useCallback(() => {
    const s = initSession(asset);
    const calc0 = computeScalp(inputs);
    const scenarios = buildScenarios(calc0, inputs, autoStats);
    const levels = extractKeyLevels(calc0, inputs, autoStats);
    setSession({ ...s, scenarios, keyLevels: levels, phase: 'WATCHING' });
  }, [asset, inputs, autoStats]);

  const handleEndSession = useCallback(() => {
    setSession(null);
    setEntryFormOpen(false);
  }, []);

  const handleRecordEntry = useCallback(() => {
    if (!session) return;
    const price = parseFloat(entryPrice) || inputs.currentPrice;
    const contracts = parseInt(entryContracts) || 1;
    const calc0 = computeScalp(inputs);
    const entry: EntryRecord = {
      price,
      contracts,
      time: Date.now(),
      direction: calc0.isLong ? 'LONG' : 'SHORT',
      z: calc0.z,
      verdict: calc0.verdict,
      scenario: session.scenarios[0]?.name || '직접 진입',
      initialSL: calc0.adaptiveSL,
      initialTP: calc0.tp15,
    };
    setSession(prev => prev ? { ...prev, phase: 'ENTERED', entry } : null);
    setEntryFormOpen(false);
  }, [session, entryPrice, entryContracts, inputs]);

  const handleRecordExit = useCallback((reason: string) => {
    if (!session?.entry) return;
    const calc0 = computeScalp(inputs);
    const isLong = session.entry.direction === 'LONG';
    const pnlPts = isLong ? (inputs.currentPrice - session.entry.price) : (session.entry.price - inputs.currentPrice);
    setSession(prev => prev ? {
      ...prev,
      phase: 'CLOSED',
      exitRecord: {
        price: inputs.currentPrice,
        contracts: session.entry!.contracts,
        time: Date.now(),
        reason: reason as any,
        pnlPoints: +pnlPts.toFixed(2),
        pnlUSD: +(pnlPts * calc0.cfg.ptVal * session.entry!.contracts).toFixed(2),
        holdDuration: Date.now() - session.entry!.time,
      },
    } : null);
  }, [session, inputs]);

  // 폴링 시 알림 체크 (WATCHING/ALERT phase)
  useEffect(() => {
    if (!session || !session.keyLevels.length) return;
    if (session.phase !== 'WATCHING' && session.phase !== 'ALERT') return;
    const alerts = checkAlerts(inputs.currentPrice, session.keyLevels);
    const active = getActiveAlerts(alerts);
    setSession(prev => {
      if (!prev) return null;
      const newPhase = active.some(a => a.status === 'AT_LEVEL') ? 'ALERT' as TradingPhase : prev.phase;
      return { ...prev, activeAlerts: alerts, phase: newPhase };
    });
  }, [inputs.currentPrice, session?.phase, session?.keyLevels]);

  // 폴링 시 포지션 평가 + ENTERED→MANAGING 자동 전환
  useEffect(() => {
    if (!session?.entry) return;
    if (session.phase !== 'ENTERED' && session.phase !== 'MANAGING') return;
    const posEval = evaluatePosition(session.entry, inputs.currentPrice, calc, calc.cfg);
    // ENTERED → MANAGING 자동 전환: 스탑 모드가 INITIAL이 아니면 (BE or TRAILING)
    if (session.phase === 'ENTERED' && posEval.stopMode !== 'INITIAL') {
      setSession(prev => prev ? { ...prev, phase: 'MANAGING', currentStopMode: posEval.stopMode } : null);
    } else if (session.phase === 'MANAGING') {
      setSession(prev => prev ? { ...prev, currentStopMode: posEval.stopMode } : null);
    }
    // 자동 청산 감지: SL / TP / TIMEOUT 히트
    const exitSugg = suggestExitAction(session.entry, inputs.currentPrice, calc);
    if (exitSugg.shouldExit && (exitSugg.exitType === 'SL' || exitSugg.exitType === 'TP' || exitSugg.exitType === 'TIMEOUT')) {
      const isLong = session.entry.direction === 'LONG';
      const pnlPts = isLong ? (inputs.currentPrice - session.entry.price) : (session.entry.price - inputs.currentPrice);
      const exitReason = exitSugg.exitType as 'SL' | 'TP' | 'TRAIL' | 'MANUAL' | 'TIMEOUT';
      setSession(prev => prev?.entry ? {
        ...prev,
        phase: 'CLOSED',
        exitRecord: {
          price: inputs.currentPrice,
          contracts: prev.entry!.contracts,
          time: Date.now(),
          reason: exitReason,
          pnlPoints: +pnlPts.toFixed(2),
          pnlUSD: +(pnlPts * calc.cfg.ptVal * prev.entry!.contracts).toFixed(2),
          holdDuration: Date.now() - prev.entry!.time,
        },
      } : null);
    }
  }, [inputs.currentPrice, session?.entry, session?.phase]);

  // MTF data loader
  const loadMTFData = useCallback(async () => {
    const tickers = TICKER_MAP[asset];
    if (!tickers) return;
    setMtfLoading(true);
    setMtfError(null);
    try {
      const result = await fetchMTFData(tickers.futures);
      const toOHLC = (data: typeof result.htf.data): OHLC[] =>
        data.map(d => ({
          o: d.open > 0 ? d.open : d.close,
          h: d.high > 0 ? d.high : d.close,
          l: d.low > 0 ? d.low : d.close,
          c: d.close,
          v: d.volume ?? 0,
        }));
      const htf = toOHLC(result.htf.data);
      const ltf = toOHLC(result.ltf.data);
      setMtfHTF(htf);
      setMtfLTF(ltf);
      if (htf.length >= 10 && ltf.length >= 10) {
        const analysis = analyzeMTF(htf, ltf, inputs.currentPrice);
        setMtfAnalysis(analysis);
      } else {
        setMtfError(`데이터 부족 (HTF: ${htf.length}봉, LTF: ${ltf.length}봉)`);
      }
    } catch (err) {
      setMtfError(err instanceof Error ? err.message : 'MTF 데이터 로드 실패');
    } finally {
      setMtfLoading(false);
    }
  }, [asset, inputs.currentPrice]);

  // MTF → Session 키 레벨 연동: MTF 분석 결과의 HTF 스윙 포인트를 세션 키 레벨에 추가
  useEffect(() => {
    if (!session || !mtfAnalysis) return;
    if (session.phase === 'CLOSED') return;

    const htf = mtfAnalysis.htf;
    const mtfLevels: KeyLevel[] = [];

    // HTF 스윙 고점 → 저항 키 레벨
    for (const sh of htf.swingHighs.filter(s => s.confirmed).slice(-3)) {
      mtfLevels.push({
        price: sh.price,
        label: `HTF 스윙고 (1H)`,
        type: 'RESISTANCE',
        source: 'SWING',
        strength: 2,
      });
    }

    // HTF 스윙 저점 → 지지 키 레벨
    for (const sl of htf.swingLows.filter(s => s.confirmed).slice(-3)) {
      mtfLevels.push({
        price: sl.price,
        label: `HTF 스윙저 (1H)`,
        type: 'SUPPORT',
        source: 'SWING',
        strength: 2,
      });
    }

    // HTF BOS/CHoCH 돌파 레벨
    if (htf.lastBOS) {
      mtfLevels.push({
        price: htf.lastBOS.breakPrice,
        label: `BOS ${htf.lastBOS.direction} (1H)`,
        type: htf.lastBOS.direction === 'BULLISH' ? 'SUPPORT' : 'RESISTANCE',
        source: 'SWING',
        strength: 3,
      });
    }
    if (htf.lastCHoCH) {
      mtfLevels.push({
        price: htf.lastCHoCH.breakPrice,
        label: `CHoCH ${htf.lastCHoCH.direction} (1H)`,
        type: htf.lastCHoCH.direction === 'BULLISH' ? 'SUPPORT' : 'RESISTANCE',
        source: 'SWING',
        strength: 3,
      });
    }

    if (mtfLevels.length === 0) return;

    // 기존 키 레벨에서 SWING 소스가 아닌 것만 유지 + 새 MTF 레벨 추가
    setSession(prev => {
      if (!prev) return null;
      const existingNonSwing = prev.keyLevels.filter(kl => kl.source !== 'SWING');
      return { ...prev, keyLevels: [...existingNonSwing, ...mtfLevels] };
    });
  }, [mtfAnalysis, session?.phase]);

  // MTF 자동 로드: 폴링 활성 시 3분 간격으로 MTF 데이터 자동 갱신
  const mtfAutoLoadRef = useRef<number>(0);
  useEffect(() => {
    if (!poll.enabled || !poll.data) return;

    const now = Date.now();
    const MTF_REFRESH_MS = 3 * 60 * 1000; // 3분

    // 마지막 로드로부터 3분 이상 경과했으면 자동 로드
    if (now - mtfAutoLoadRef.current >= MTF_REFRESH_MS && !mtfLoading) {
      mtfAutoLoadRef.current = now;
      loadMTFData();
    }
  }, [poll.enabled, poll.data, mtfLoading, loadMTFData]);

  const calc = computeScalp(inputs);
  const vc = calc.verdict === "GO" ? K.grn : calc.verdict === "CAUTION" ? K.ylw : K.red;
  const isKospi = asset === 'K200' || asset === 'MK200';
  const isNasdaq = asset === 'NQ' || asset === 'MNQ';
  const spotLabel = isKospi ? 'KOSPI200' : isNasdaq ? 'NDX' : 'SPX';
  const futLabel = isKospi ? 'K200' : isNasdaq ? 'NQ' : 'ES';

  return (
    <div className="scalp-page">

      {/* Header */}
      <div className="scalp-header">
        <div className="scalp-header-inner">
          <div className="scalp-logo">
            <div className="scalp-logo-icon">Σ</div>
            <div>
              <div className="scalp-logo-title">Futures Scalp Analyzer</div>
              <div className="scalp-logo-sub">PROBABILITY-BASED DECISION ENGINE v1.2</div>
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div className="scalp-asset-btns">
              {Object.entries(ASSETS).map(([k, v]) => (
                <button key={k} onClick={() => setAsset(k)}
                  className={`scalp-asset-btn ${asset === k ? 'active' : ''}`}>
                  {k}<span style={{ fontSize: 9, marginLeft: 4, opacity: 0.6 }}>{fmtMoney(v.tickVal, v.sym)}/t</span>
                </button>
              ))}
            </div>
            <Link to="/scalp-analyzer/fabio" style={{
              padding: '6px 14px', borderRadius: 6, fontSize: 11, fontWeight: 700,
              fontFamily: F.mono, textDecoration: 'none', transition: 'all 0.15s',
              border: '1px solid #c2185b', background: 'rgba(194,24,91,0.10)', color: '#ff6b9d',
              display: 'flex', alignItems: 'center', gap: 5,
            }}>
              🔥 Fabio Strategy
            </Link>
          </div>
        </div>
      </div>

      {/* Polling Control */}
      <div style={{ padding: '6px 24px', display: 'flex', justifyContent: 'flex-end' }}>
        <PollingControl
          enabled={poll.enabled}
          onToggle={poll.setEnabled}
          interval={poll.interval}
          onIntervalChange={poll.setInterval}
          status={poll.status}
          lastUpdated={poll.lastUpdated}
          consecutiveErrors={poll.consecutiveErrors}
          onRefresh={poll.fetchNow}
          compact
        />
      </div>

      {/* Verdict */}
      <div className="scalp-verdict" style={{ background: `${vc}08`, borderBottom: `1px solid ${vc}25`, color: vc }}>
        {calc.verdict === "GO" ? "✅" : calc.verdict === "CAUTION" ? "⚠️" : "🚫"}{" "}
        {calc.verdict} — [{calc.passN}/{calc.checks.length}] — {calc.zSignal} — {calc.isLong ? "▲ LONG" : "▼ SHORT"}
        {autoStats && <span style={{ opacity: 0.5 }}> — ATR: {autoStats.atrMethod}</span>}
        {calc.trendConflict && <span style={{ color: K.org, marginLeft: 8, fontSize: 12 }}>⚠ 역추세 진입 — 추세 하락 중 롱 권고</span>}
      </div>

      {/* Body */}
      <div className="scalp-body">
        <div className="scalp-layout">

          {/* ── LEFT: INPUTS ── */}
          <div className="scalp-sidebar">

            {/* Price Data */}
            <div className="scalp-box" style={{ borderColor: dataMode !== "manual" ? `${K.acc}40` : undefined }}>
              <Sec icon="📋" title="가격 데이터 (Price Data)" tag={liveLoaded ? "LIVE" : dataMode === "ohlc" ? "OHLC" : dataMode === "close" ? "CLOSE" : "MANUAL"} tagC={liveLoaded ? K.grn : dataMode !== "manual" ? K.grn : K.dim} />

              <div className="scalp-mode-btns">
                {([
                  { key: "ohlc" as const, label: "OHLC", desc: "True ATR" },
                  { key: "close" as const, label: "Close", desc: "근사 ATR" },
                  { key: "manual" as const, label: "수동", desc: "직접입력" },
                ]).map(m => (
                  <button key={m.key} onClick={() => setDataMode(m.key)}
                    className={`scalp-mode-btn ${dataMode === m.key ? 'active' : ''}`}>
                    <span>{m.label}</span>
                    <span className="scalp-mode-btn-sub">{m.desc}</span>
                  </button>
                ))}
              </div>

              {dataMode === "ohlc" && (
                <>
                  <label className="scalp-input-label">OHLC 데이터 (한 줄에 O, H, L, C)</label>
                  <textarea value={ohlcText} onChange={e => setOhlcText(e.target.value)}
                    placeholder={"5870.00, 5878.50, 5868.25, 5872.50\n..."}
                    rows={5} className="scalp-textarea" />
                  <div style={{ display: "flex", justifyContent: "space-between", marginTop: 5, marginBottom: 8 }}>
                    <span className="scalp-data-count" style={{ color: candles.length >= 3 ? K.grn : K.red }}>
                      {candles.length}개 캔들 파싱 {candles.length < 3 && "(최소 3개)"}
                    </span>
                    <button onClick={() => setOhlcText(SAMPLE_OHLC)} className="scalp-sample-btn">샘플</button>
                  </div>
                </>
              )}

              {dataMode === "close" && (
                <>
                  <label className="scalp-input-label">종가 데이터 (콤마/줄바꿈 구분)</label>
                  <textarea value={closeText} onChange={e => setCloseText(e.target.value)}
                    placeholder="5880.50, 5885.25, 5890.00 ..." rows={4} className="scalp-textarea" />
                  <div style={{ display: "flex", justifyContent: "space-between", marginTop: 5, marginBottom: 8 }}>
                    <span className="scalp-data-count" style={{ color: closes.length >= 3 ? K.grn : K.red }}>
                      {closes.length}개 가격 파싱 {closes.length < 3 && "(최소 3개)"}
                    </span>
                    <button onClick={() => setCloseText(SAMPLE_CLOSE)} className="scalp-sample-btn">샘플</button>
                  </div>
                </>
              )}

              {dataMode === "manual" && (
                <>
                  <NIn label="현재가" value={inputs.currentPrice} onChange={s("currentPrice")} step={cfg.tick} unit="pts" />
                  <NIn label="이동평균 (MA)" value={inputs.ma} onChange={s("ma")} step={cfg.tick} unit="pts" />
                  <NIn label="표준편차 (σ)" value={inputs.stdDev} onChange={s("stdDev")} step={cfg.tick} unit="pts" />
                  <NIn label="ATR" value={inputs.atr} onChange={s("atr")} step={cfg.tick} unit="pts" />
                </>
              )}

              {dataMode !== "manual" && (
                <NIn label="MA 기간" value={maPeriod} onChange={setMaPeriod} step={1} min={2} help="이동평균 & 표준편차 산출 기간" />
              )}

              {dataMode !== "manual" && autoStats && (
                <div className="scalp-auto-stats">
                  <div className="scalp-auto-stats-header">
                    ● 자동 산출 — {autoStats.atrMethod === "TRUE-RANGE"
                      ? <span style={{ color: K.cyn }}>True Range ATR ✓</span>
                      : <span style={{ color: K.org }}>Close-Proxy ATR (근사)</span>}
                  </div>
                  <div className="scalp-stats-grid">
                    {[
                      { l: "현재가", v: fmt(autoStats.currentPrice, 2) },
                      { l: `MA(${autoStats.maPeriod})`, v: fmt(autoStats.ma, 2) },
                      { l: "표준편차 (σ)", v: fmt(autoStats.stdDev, 2) },
                      { l: "평균변동폭 ATR(14)", v: fmt(autoStats.atr, 2) },
                    ].map((item, i) => (
                      <div key={i}>
                        <div className="scalp-stats-label">{item.l}</div>
                        <div className="scalp-stats-value">{item.v}</div>
                      </div>
                    ))}
                  </div>
                  {autoStats.atrMethod === "CLOSE-PROXY" && (
                    <div className="scalp-auto-warn">
                      ⚠ 종가 간 차이로 ATR 근사 중. OHLC 모드 사용 시 True Range 기반 정확한 ATR 산출.
                    </div>
                  )}
                </div>
              )}

              <NIn label="ATR 배수 (Stop)" value={inputs.atrMult} onChange={s("atrMult")} step={0.1} min={0.1} help="스캘핑: 0.5~1.0 / 스윙: 1.5~2.0" />
            </div>

            {/* Backtest Stats */}
            <div className="scalp-box">
              <Sec icon="🎯" title="승률/손익 통계 (EV Input)" />
              <NIn label="승률 (Win Rate)" value={inputs.winRate} onChange={s("winRate")} step={1} unit="%" />
              <NIn label="평균 익절 (Avg Win)" value={inputs.avgWin} onChange={s("avgWin")} step={0.5} unit="ticks" />
              <NIn label="평균 손절 (Avg Loss)" value={inputs.avgLoss} onChange={s("avgLoss")} step={0.5} unit="ticks" />
              <NIn label="슬리피지" value={inputs.slippage} onChange={s("slippage")} step={0.25} unit="ticks" help="스캘핑 0.25~0.5t" />
              <NIn label="수수료 (편도)" value={inputs.commission} onChange={s("commission")} step={isKospi ? 100 : 0.05} unit={cfg.sym} />
            </div>

            {/* Account */}
            <div className="scalp-box">
              <Sec icon="💰" title="계좌 정보 (Account)" />
              <NIn label="계좌잔고" value={inputs.accountBalance} onChange={s("accountBalance")} step={isKospi ? 1000000 : 100} unit={cfg.sym} />
              <NIn label="허용 리스크" value={inputs.riskPct} onChange={s("riskPct")} step={0.5} min={0.1} unit="%" />

              {/* 증거금 정보 */}
              <div style={{
                marginTop: 10, padding: '8px 10px', borderRadius: 6,
                background: '#0d1117', border: `1px solid ${K.brd}`,
                fontSize: 10, fontFamily: F.mono, lineHeight: 1.7,
              }}>
                <div style={{ fontWeight: 700, color: K.acc, marginBottom: 4, fontSize: 11 }}>
                  📋 {cfg.label} — {cfg.exchange}
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '2px 12px' }}>
                  <span style={{ color: '#888' }}><Term id="multiplier" position="bottom">승수 (Multiplier)</Term></span>
                  <span style={{ color: '#ccc', textAlign: 'right' }}>{cfg.sym === '₩' ? `₩${cfg.multiplier.toLocaleString()}` : `$${cfg.multiplier}`}</span>

                  <span style={{ color: '#888' }}><Term id="notional" position="bottom">1계약 명목가치</Term></span>
                  <span style={{ color: '#ccc', textAlign: 'right' }}>
                    {cfg.sym === '₩'
                      ? `₩${cfg.notional.toLocaleString()}`
                      : `$${cfg.notional.toLocaleString()}`}
                  </span>

                  <span style={{ color: '#f9a825' }}><Term id="initialMargin" position="bottom">개시증거금 (Initial)</Term></span>
                  <span style={{ color: '#f9a825', textAlign: 'right', fontWeight: 700 }}>
                    {cfg.sym === '₩'
                      ? `₩${cfg.initialMargin.toLocaleString()}`
                      : `$${cfg.initialMargin.toLocaleString()}`}
                    {cfg.marginRatePct && <span style={{ fontSize: 8, opacity: 0.7 }}> ({cfg.marginRatePct}%)</span>}
                  </span>

                  <span style={{ color: '#ff7043' }}><Term id="maintMargin" position="bottom">유지증거금 (Maint.)</Term></span>
                  <span style={{ color: '#ff7043', textAlign: 'right', fontWeight: 700 }}>
                    {cfg.sym === '₩'
                      ? `₩${cfg.maintMargin.toLocaleString()}`
                      : `$${cfg.maintMargin.toLocaleString()}`}
                    {cfg.marginRatePct && <span style={{ fontSize: 8, opacity: 0.7 }}> ({(cfg.marginRatePct * 2 / 3).toFixed(1)}%)</span>}
                  </span>

                  <span style={{ color: '#888' }}>수수료 (편도)</span>
                  <span style={{ color: '#ccc', textAlign: 'right' }}>
                    {cfg.sym === '₩'
                      ? `₩${cfg.defaultCommission.toLocaleString()}`
                      : `$${cfg.defaultCommission}`}
                  </span>

                  <span style={{ color: '#888' }}><Term id="tickValue" position="bottom">틱 가치 (Tick Value)</Term></span>
                  <span style={{ color: '#ccc', textAlign: 'right' }}>
                    {cfg.sym === '₩' ? `₩${cfg.tickVal.toLocaleString()}` : `$${cfg.tickVal}`} / {cfg.tick}pt
                  </span>
                </div>
                {inputs.accountBalance > 0 && (
                  <div style={{
                    marginTop: 6, paddingTop: 6, borderTop: `1px solid ${K.brd}`,
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  }}>
                    <span style={{ color: '#888' }}>잔고 ÷ 개시증거금</span>
                    <span style={{
                      color: inputs.accountBalance >= cfg.initialMargin ? K.grn : K.red,
                      fontWeight: 700, fontSize: 12,
                    }}>
                      {(inputs.accountBalance / cfg.initialMargin).toFixed(2)}계약
                    </span>
                  </div>
                )}
              </div>
            </div>

            {/* Basis */}
            <div className="scalp-box">
              <Sec icon="📉" title="선현물 스프레드 (Basis)" />
              <NIn label={`현물 (${spotLabel})`} value={inputs.spotPrice} onChange={s("spotPrice")} step={cfg.tick} unit="pts" />
              <NIn label={`선물 (${futLabel})`} value={inputs.futuresPrice} onChange={s("futuresPrice")} step={cfg.tick} unit="pts" />
            </div>
          </div>

          {/* ── RIGHT: OUTPUTS ── */}
          <div className="scalp-main">

            {/* Decision Matrix */}
            <div className="scalp-box" style={{ borderColor: `${vc}30` }}>
              <Sec icon="🎯" title="진입 판정표 (Decision Matrix)" tag="ENTRY CHECKLIST" tagC={vc} />
              <div className="scalp-flex-col">
                {calc.checks.map((c, i) => (
                  <div key={i} className={`scalp-check ${c.pass ? 'pass' : 'fail'}`}>
                    <span className="scalp-check-icon" style={{
                      background: c.pass ? `${K.grn}18` : `${K.red}18`,
                      color: c.pass ? K.grn : K.red,
                    }}>{c.pass ? "✓" : "✗"}</span>
                    <div style={{ flex: 1 }}>
                      <div className="scalp-check-label">{c.label}</div>
                      <div className="scalp-check-val">{c.val}</div>
                    </div>
                  </div>
                ))}
              </div>
              <div style={{ marginTop: 12, padding: "9px 14px", background: `${vc}0c`, border: `1px solid ${vc}30`, borderRadius: 6, textAlign: "center" }}>
                <span style={{ fontSize: 14, fontWeight: 800, color: vc, fontFamily: F.mono, letterSpacing: "0.06em" }}>
                  [{calc.passN}/{calc.checks.length}] {calc.verdict === "GO" ? "ALL CLEAR — 진입 가능" : calc.verdict === "CAUTION" ? "CAUTION — 조건부 진입" : "NO ENTRY — 대기"}
                  {calc.trendConflict && " | ⚠ 역추세(Counter-Trend)"}
                </span>
              </div>
            </div>

            {/* ── Trading Session ── */}
            <TradingSessionSection
                inputs={inputs}
                calc={calc}
                session={session}
                setSession={setSession}
                entryFormOpen={entryFormOpen}
                setEntryFormOpen={setEntryFormOpen}
                entryPrice={entryPrice}
                setEntryPrice={setEntryPrice}
                entryContracts={entryContracts}
                setEntryContracts={setEntryContracts}
                onStartSession={handleStartSession}
                onRecordEntry={handleRecordEntry}
                onRecordExit={handleRecordExit}
                onEndSession={handleEndSession}
            />

            {/* Z-Score */}
            <ZScoreSection inputs={inputs} calc={calc} />


            {/* ── Composite Trend (SMC + OBV + Volume) ── */}
            {calc.compositeTrend && (
              <div className="scalp-box">
                <Sec icon="📊" title="복합 추세 판단 (Smart Money Concept + OBV + Volume)"
                  tag={calc.compositeTrend.bias}
                  tagC={calc.compositeTrend.bias === 'BULLISH' ? K.grn : calc.compositeTrend.bias === 'BEARISH' ? K.red : K.ylw}
                  infoId="compositeTrend" />
                <div className="scalp-flex" style={{ marginTop: 10, marginBottom: 8 }}>
                  <Met label="추세 방향" value={calc.compositeTrend.bias === 'BULLISH' ? '상승' : calc.compositeTrend.bias === 'BEARISH' ? '하락' : '횡보'}
                    color={calc.compositeTrend.bias === 'BULLISH' ? K.grn : calc.compositeTrend.bias === 'BEARISH' ? K.red : K.ylw} big />
                  <Met label="복합 점수" value={`${calc.compositeTrend.score > 0 ? '+' : ''}${calc.compositeTrend.score.toFixed(0)}`}
                    color={calc.compositeTrend.score > 0 ? K.grn : calc.compositeTrend.score < 0 ? K.red : K.dim} big />
                  <Met label="확신도" value={`${calc.compositeTrend.confidence}%`} />
                </div>

                {/* Component bars */}
                <div style={{ display: 'grid', gridTemplateColumns: '80px 1fr 50px', gap: '6px 8px', alignItems: 'center', fontSize: 9.5, marginTop: 8 }}>
                  {Object.entries(calc.compositeTrend.components).map(([key, comp]) => {
                    const pct = clamp((comp.score + 100) / 200 * 100, 2, 98);
                    const barColor = comp.score > 15 ? K.grn : comp.score < -15 ? K.red : K.dim;
                    return (
                      <div key={key} style={{ display: 'contents' }}>
                        <span style={{ color: K.dim, fontFamily: F.mono }}>
                          {key === 'smcTrend' ? 'Smart Money Concept 구조' : key === 'obvMomentum' ? 'OBV 모멘텀' : '거래량 추세'}
                          <span style={{ opacity: 0.5, marginLeft: 4 }}>({comp.weight}%)</span>
                        </span>
                        <div style={{ height: 6, background: `${K.brd}`, borderRadius: 3, position: 'relative', overflow: 'hidden' }}>
                          <div style={{ position: 'absolute', left: '50%', top: 0, bottom: 0, width: 1, background: K.dim }} />
                          <div style={{
                            position: 'absolute',
                            left: comp.score >= 0 ? '50%' : `${pct}%`,
                            width: `${Math.abs(pct - 50)}%`,
                            top: 0, bottom: 0,
                            background: barColor,
                            borderRadius: 3,
                            transition: 'all 0.3s',
                          }} />
                        </div>
                        <span style={{ color: barColor, fontFamily: F.mono, textAlign: 'right' }}>
                          {comp.label}
                        </span>
                      </div>
                    );
                  })}
                </div>

                {/* Interpretation */}
                <div className="scalp-detail" style={{ marginTop: 10 }}>
                  {calc.compositeTrend.reason}
                  {calc.trendConflict && (
                    <div style={{ marginTop: 8, padding: '8px 12px', background: `${K.org}15`, border: `1px solid ${K.org}40`, borderRadius: 6 }}>
                      <span style={{ color: K.org, fontWeight: 700 }}>
                        ⚠ 추세-방향 충돌: 복합추세 {calc.compositeTrend.bias === 'BEARISH' ? '하락' : '상승'} vs Z-Score {calc.isLong ? '롱' : '숏'}
                      </span>
                      <div style={{ color: K.org, fontSize: 11, marginTop: 4, opacity: 0.8 }}>
                        평균회귀(Z-Score)는 "가격이 MA 아래 → 매수" 판단, 추세지표(Smart Money Concept+OBV+Vol)는 "{calc.compositeTrend.bias === 'BEARISH' ? '하락 구조 지속' : '상승 구조 지속'}" 판단. 역추세 진입은 리스크 증가.
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* ── MTF Structure Analysis ── */}
            <MTFStructureSection
                mtfAnalysis={mtfAnalysis}
                mtfHTF={mtfHTF}
                mtfLTF={mtfLTF}
                mtfLoading={mtfLoading}
                mtfError={mtfError}
                mtfExpanded={mtfExpanded}
                setMtfExpanded={setMtfExpanded}
                loadMTFData={loadMTFData}
            />

            {/* EV Engine */}
            <div className="scalp-box">
              <Sec icon="⚡" title="기대값 엔진 (EV Engine)" tag="기대값" tagC={calc.netEV >= 0 ? K.grn : K.red} infoId="evEngine" />
              <div className="scalp-flex">
                <Met label="순 기대값 (Net EV)" value={`${calc.netEV >= 0 ? "+" : ""}${fmt(calc.netEV)}t`} color={calc.netEV >= 0 ? K.grn : K.red} big sub={`${calc.netEV >= 0 ? "+" : "−"} ${fmtMoney(Math.abs(calc.netEVusd), cfg.sym)}`} />
                <Met label="총 기대값 (Gross EV)" value={`${fmt(calc.grossEV)}t`} sub="비용 차감 전" />
                <Met label="마찰비용 (Friction)" value={`${fmt(calc.friction)}t`} color={K.org} sub="슬리피지+수수료" />
                <Met label="손익비 (R:R)" value={`${fmt(calc.b, 1)}:1`} />
              </div>
              <EVBar gross={calc.grossEV} net={calc.netEV} />
              <div className="scalp-detail" style={{ marginTop: 12 }}>
                <Term id="ev">EV</Term> = {fmtPct(calc.p)}×{inputs.avgWin} − {fmtPct(calc.q)}×{inputs.avgLoss} − <Term id="friction">{fmt(calc.friction)}t</Term> = <span style={{ color: calc.netEV >= 0 ? K.grn : K.red, fontWeight: 700 }}>{fmt(calc.netEV)}t</span>
                {calc.netEV > 0
                  ? <> | 100회 기대순익: <span style={{ color: K.grn }}>+{fmtMoney(Math.abs(calc.netEVusd) * 100, cfg.sym)}</span></>
                  : <> | ⚠ 반복매매 시 손실 누적</>}
              </div>
            </div>

            {/* Kelly + Position */}
            <div className="scalp-two-col">
              <div className="scalp-box">
                <Sec icon="🎰" title="켈리 기준 (Kelly)" tag="확신도" tagC={calc.kelly > 0 ? K.grn : K.red} infoId="kellyCriterion" />
                <div className="scalp-flex">
                  <Met label="풀 켈리" value={fmtPct(calc.kelly)} />
                  <Met label="하프 켈리 (½K)" value={fmtPct(calc.halfKelly)} color={K.acc} sub="권장 배팅비중" big />
                </div>
                <KGauge hk={calc.halfKelly} conv={calc.conviction} />
                <div style={{ marginTop: 10, fontSize: 9.5, color: K.dim, fontFamily: F.mono }}>
                  <Term id="kelly">f*</Term> = (<Term id="rr">b</Term>×p − q) / <Term id="rr">b</Term> = ({fmt(calc.b, 1)}×{fmtPct(calc.p)} − {fmtPct(calc.q)}) / {fmt(calc.b, 1)} = {fmtPct(calc.kelly)}
                </div>
              </div>
              <div className="scalp-box">
                <Sec icon="📏" title="포지션 계산기 (Position Sizer)" />
                <div className="scalp-flex">
                  <Met label="리스크 예산" value={fmtMoney(calc.riskBudget, cfg.sym)} sub={`잔고의 ${inputs.riskPct}%`} />
                  <Met label="계약당 위험" value={fmtMoney(calc.riskPerContract, cfg.sym)} sub={`${fmt(calc.adaptiveStop)}p × ${cfg.sym}${cfg.ptVal.toLocaleString()}`} />
                </div>
                <div className="scalp-position-center">
                  <div style={{ fontSize: 9, color: K.mut, fontFamily: F.mono, textTransform: "uppercase", marginBottom: 6 }}>권장 계약 수</div>
                  <div className="scalp-position-number">{calc.recContracts}</div>
                  <div style={{ fontSize: 9.5, color: K.dim, fontFamily: F.mono, marginTop: 4 }}>최대 {calc.maxContracts}계약 / 스캘핑 2계약 상한</div>
                </div>
              </div>
            </div>

            {/* ATR + RR Map */}
            <ATRStopSection
                inputs={inputs}
                calc={calc}
                candles={candles}
                candleDates={candleDates}
                maPeriod={maPeriod}
            />


            {/* Volume S/R Levels */}
            {calc.volumeSR && calc.volumeSR.levels.length > 0 && (
              <div className="scalp-box">
                <Sec icon="📊" title="일봉 거래량 S/R" tag={calc.volumeSR.volumeTrend} tagC={calc.volumeSR.volumeTrend === 'INCREASING' ? K.grn : calc.volumeSR.volumeTrend === 'DECREASING' ? K.red : '#78909c'} />
                <div style={{ display: 'flex', gap: 6, marginBottom: 8 }}>
                  <div style={{ flex: 1, padding: '4px 8px', borderRadius: 6, background: calc.volumeSR.priceInZone === 'SUPPORT' ? `${K.grn}15` : calc.volumeSR.priceInZone === 'RESISTANCE' ? `${K.red}15` : '#ffffff06', border: `1px solid ${calc.volumeSR.priceInZone === 'SUPPORT' ? K.grn : calc.volumeSR.priceInZone === 'RESISTANCE' ? K.red : '#333'}30`, textAlign: 'center' }}>
                    <div style={{ fontSize: 9, color: '#888' }}>현재 위치</div>
                    <div style={{ fontSize: 13, fontWeight: 700, color: calc.volumeSR.priceInZone === 'SUPPORT' ? K.grn : calc.volumeSR.priceInZone === 'RESISTANCE' ? K.red : '#ccc' }}>
                      {calc.volumeSR.priceInZone === 'SUPPORT' ? '지지구간' : calc.volumeSR.priceInZone === 'RESISTANCE' ? '저항구간' : '중립'}
                    </div>
                  </div>
                  {calc.volumeSR.nearestSupport && (
                    <div style={{ flex: 1, padding: '4px 8px', borderRadius: 6, background: `${K.grn}08`, textAlign: 'center' }}>
                      <div style={{ fontSize: 9, color: '#888' }}>최근접 지지</div>
                      <div style={{ fontSize: 13, fontWeight: 700, color: K.grn }}>{fmt(calc.volumeSR.nearestSupport, 2)}</div>
                    </div>
                  )}
                  {calc.volumeSR.nearestResistance && (
                    <div style={{ flex: 1, padding: '4px 8px', borderRadius: 6, background: `${K.red}08`, textAlign: 'center' }}>
                      <div style={{ fontSize: 9, color: '#888' }}>최근접 저항</div>
                      <div style={{ fontSize: 13, fontWeight: 700, color: K.red }}>{fmt(calc.volumeSR.nearestResistance, 2)}</div>
                    </div>
                  )}
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4 }}>
                  {calc.volumeSR.supports.map((s, i) => (
                    <div key={`s${i}`} style={{ padding: '3px 6px', borderRadius: 4, background: `${K.grn}08`, border: `1px solid ${K.grn}18`, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontSize: 9, color: K.grn }}>S{i + 1}</span>
                      <span style={{ fontSize: 11, fontWeight: 600, color: '#ccc', fontFamily: 'monospace' }}>{fmt(s.price, 2)}</span>
                      <span style={{ fontSize: 8, color: '#888' }}>{s.volumeScore.toFixed(1)}x {'●'.repeat(s.strength)}</span>
                    </div>
                  ))}
                  {calc.volumeSR.resistances.map((r, i) => (
                    <div key={`r${i}`} style={{ padding: '3px 6px', borderRadius: 4, background: `${K.red}08`, border: `1px solid ${K.red}18`, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontSize: 9, color: K.red }}>R{i + 1}</span>
                      <span style={{ fontSize: 11, fontWeight: 600, color: '#ccc', fontFamily: 'monospace' }}>{fmt(r.price, 2)}</span>
                      <span style={{ fontSize: 8, color: '#888' }}>{r.volumeScore.toFixed(1)}x {'●'.repeat(r.strength)}</span>
                    </div>
                  ))}
                </div>
                <div style={{ marginTop: 6, fontSize: 9, color: '#666', lineHeight: 1.4 }}>
                  14일 일봉 거래량 기반. 고거래량일 고가/저가 = 기관 매물대. 강도(●): 거래량 비율 ≥2x=강, ≥1.5x=보통, ≥1.2x=약.
                </div>
              </div>
            )}

            {/* Basis Spread */}
            <BasisSpreadSection
                spotLabel={spotLabel}
                futLabel={futLabel}
                inputs={inputs}
                calc={calc}
            />


            {/* Formula Ref */}
            <FormulaReference />

          </div>
        </div>
      </div>

      <Footer />
    </div>
  );
}
