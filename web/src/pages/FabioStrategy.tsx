import { useState, useMemo, useCallback, useEffect } from 'react';
import { Link } from 'react-router-dom';
import {
  clamp, fmt, fmtMoney,
  parseOHLC, statsFromOHLC,
  computeScalp,
  ASSETS, TICKER_MAP, SAMPLE_OHLC, F, K,
  type ScalpInputs, type OHLC,
} from '../lib/scalpEngine';
import {
  computeFabioAnalysis,
  createInitialSession,
  addTradeToSession,
  runBacktest,
  DEFAULT_BACKTEST_CONFIG,
  buildIntradayBarMap,
  type SessionState, type SetupGrade, type SetupModel, type FabioAnalysis,
  type MarketState, type TripleAPhase,
  type BacktestConfig, type BacktestResult,
  type IntradayBarMap,
} from '../lib/fabioEngine';
import { fetchAnalyticsData, fetchQuote } from '../lib/api';
import { usePolling } from '../hooks/usePolling';
import { PollingControl } from '../components/PollingControl';
import { Term, InfoCard } from '../components/glossary/GlossaryComponents';
import {
  analyzeMultiStrategy, runMultiStrategyBacktest,
  REGIME_COLORS, REGIME_LABELS, STRATEGY_LABELS, DEFAULT_MS_CONFIG,
  type MSBacktestResult,
  type StrategyName,
} from '../lib/strategyEngine';
import './FabioStrategy.css';

// ── Atom Components ──────────────────────────────────────────────────

function Pill({ children, color = K.dim }: { children: React.ReactNode; color?: string }) {
  return (
    <span className="fb-pill" style={{ background: `${color}15`, border: `1px solid ${color}35`, color }}>
      {children}
    </span>
  );
}

function Met({ label, value, sub, color, big }: {
  label: string; value: string; sub?: string; color?: string; big?: boolean;
}) {
  return (
    <div className={`fb-met ${big ? 'big' : ''}`}>
      <div className="fb-met-label">{label}</div>
      <div className={`fb-met-value ${big ? 'big' : ''}`} style={{ color: color || K.txt }}>{value}</div>
      {sub && <div className="fb-met-sub">{sub}</div>}
    </div>
  );
}

function Sec({ icon, title, tag, tagC, infoId }: { icon: string; title: string; tag?: string; tagC?: string; infoId?: string }) {
  return (
    <div className="fb-sec">
      <span className="fb-sec-icon">{icon}</span>
      <span className="fb-sec-title">{title}</span>
      {infoId && <InfoCard id={infoId} />}
      {tag && <Pill color={tagC || K.acc}>{tag}</Pill>}
    </div>
  );
}

function NIn({ label, value, onChange, unit, step = 1, min, max, help }: {
  label: string; value: number; onChange: (v: number) => void;
  unit?: string; step?: number; min?: number; max?: number; help?: string;
}) {
  return (
    <div className="fb-input-group">
      <label className="fb-input-label">{label}</label>
      <div className="fb-input-row">
        <input type="number" value={value} step={step} min={min} max={max}
          onChange={e => onChange(parseFloat(e.target.value) || 0)}
          className="fb-input" />
        {unit && <span className="fb-input-unit">{unit}</span>}
      </div>
      {help && <span className="fb-input-help">{help}</span>}
    </div>
  );
}

// ── Color helpers ────────────────────────────────────────────────────

const stateColor = (s: MarketState) =>
  s === 'BALANCE' ? K.cyn : s === 'IMBALANCE_BULL' ? K.grn : s === 'IMBALANCE_BEAR' ? K.red : K.dim;

const gradeColor = (g: SetupGrade) =>
  g === 'A' ? K.grn : g === 'B' ? K.ylw : g === 'C' ? K.org : K.red;

const phaseColor = (p: TripleAPhase) =>
  p === 'FULL_ALIGNMENT' ? K.grn : p === 'AGGRESSION' ? K.org : p === 'ACCUMULATION' ? K.cyn : p === 'ABSORPTION' ? K.ylw : K.dim;

const modelLabel = (m: SetupModel) =>
  m === 'TREND_CONTINUATION' ? 'TREND' : m === 'MEAN_REVERSION' ? 'MEAN REV' : 'NONE';

// ── Main Page ────────────────────────────────────────────────────────

export function FabioStrategy() {
  const [asset, setAsset] = useState("ES");
  const cfg = ASSETS[asset];
  const isKospi = asset === 'K200' || asset === 'MK200';

  const [ohlcText, setOhlcText] = useState(SAMPLE_OHLC);
  const [maPeriod, setMaPeriod] = useState(20);
  const [liveLoaded, setLiveLoaded] = useState(false);
  const [fullCandles, setFullCandles] = useState<OHLC[]>([]); // 1y full data for backtest
  const [liveAnalyticsData, setLiveAnalyticsData] = useState<import('../lib/api').AnalyticsData[]>([]); // for regime detection

  // ── 30분봉 드릴다운 ──
  const [intradayMap, setIntradayMap] = useState<IntradayBarMap>(new Map());
  const [intradayEnabled, setIntradayEnabled] = useState(true);
  const [intradayLoading, setIntradayLoading] = useState(false);
  const [intradayBarCount, setIntradayBarCount] = useState(0);
  const [dailyDates, setDailyDates] = useState<string[]>([]);

  // ── Polling ──
  const tickers = TICKER_MAP[asset];
  const pollFn = useCallback(
    () => fetchQuote(tickers?.futures || 'ES=F', 20),
    [tickers?.futures],
  );
  const poll = usePolling(pollFn, { interval: 30000, enabled: false });

  // 폴링 데이터 수신 시 OHLC + price 업데이트 (fullCandles는 변경하지 않음 — 백테스트용)
  useEffect(() => {
    const q = poll.data;
    if (!q?.candles || q.candles.length < 3) return;
    const ohlcLines = q.candles.map(c => {
      const o = c.open > 0 ? c.open : c.close;
      const h = c.high > 0 ? c.high : c.close;
      const l = c.low > 0 ? c.low : c.close;
      return `${o.toFixed(2)}, ${h.toFixed(2)}, ${l.toFixed(2)}, ${c.close.toFixed(2)}`;
    }).join('\n');
    setOhlcText(ohlcLines);
    if (q.latest) {
      setInputs(p => ({ ...p, futuresPrice: q.latest.price }));
    }
    setLiveLoaded(true);
  }, [poll.data]);

  const candles = useMemo(() => parseOHLC(ohlcText), [ohlcText]);
  const autoStats = useMemo(() => statsFromOHLC(candles, maPeriod), [candles, maPeriod]);
  // Backtest uses full live candles if available, otherwise falls back to textarea candles
  const btCandles = fullCandles.length > candles.length ? fullCandles : candles;

  const [inputs, setInputs] = useState<ScalpInputs>({
    asset: "ES",
    currentPrice: 5920, ma: 5900, stdDev: 15, atr: 12, atrMult: 1.0,
    winRate: 58, avgWin: 6, avgLoss: 4, slippage: 0.5, commission: 2.25,
    accountBalance: 10000, riskPct: 2, spotPrice: 5918, futuresPrice: 5920,
  });
  const s = useCallback((k: keyof ScalpInputs) => (v: number) => setInputs(p => ({ ...p, [k]: v })), []);

  // Session state (persisted in component)
  const [session, setSession] = useState<SessionState>(createInitialSession);
  const [manualChecks, setManualChecks] = useState<Record<string, boolean>>({});
  const [dailyLossLimit, setDailyLossLimit] = useState(20);

  // Trade log form
  const [showTradeForm, setShowTradeForm] = useState(false);
  const [tradeResult, setTradeResult] = useState<'WIN' | 'LOSS' | 'SCRATCH'>('WIN');
  const [tradePnL, setTradePnL] = useState(0);
  const [tradePnLEdited, setTradePnLEdited] = useState(false); // 사용자가 직접 수정했는지
  const [tradeNote, setTradeNote] = useState('');

  // Backtest state
  const [btConfig, setBtConfig] = useState<BacktestConfig>({ ...DEFAULT_BACKTEST_CONFIG });
  const [btResult, setBtResult] = useState<BacktestResult | null>(null);
  const [btRunning, setBtRunning] = useState(false);
  const [btExpanded, setBtExpanded] = useState(false);
  const bc = useCallback((k: keyof BacktestConfig) => (v: number) => setBtConfig(p => ({ ...p, [k]: v })), []);

  // Multi-Strategy state
  const [msBacktest, setMsBacktest] = useState<MSBacktestResult | null>(null);
  const [msExpanded, setMsExpanded] = useState(false);
  const [msRunning, setMsRunning] = useState(false);

  // Sync auto stats
  useEffect(() => {
    if (autoStats) {
      setInputs(p => ({
        ...p,
        currentPrice: autoStats.currentPrice,
        ma: autoStats.ma,
        stdDev: autoStats.stdDev,
        atr: autoStats.atr,
        futuresPrice: autoStats.currentPrice,
      }));
    }
  }, [autoStats]);

  // Asset change
  const ASSET_DEFAULTS: Record<string, Partial<ScalpInputs>> = {
    ES: { currentPrice: 5920, ma: 5900, stdDev: 15, atr: 12, slippage: 0.5, commission: 2.25, accountBalance: 10000, spotPrice: 5918, futuresPrice: 5920 },
    MES: { currentPrice: 5920, ma: 5900, stdDev: 15, atr: 12, slippage: 0.5, commission: 0.62, accountBalance: 5000, spotPrice: 5918, futuresPrice: 5920 },
    K200: { currentPrice: 900, ma: 895, stdDev: 20, atr: 25, slippage: 1, commission: 1500, accountBalance: 200000000, spotPrice: 900, futuresPrice: 900 },
    MK200: { currentPrice: 900, ma: 895, stdDev: 20, atr: 25, slippage: 1, commission: 500, accountBalance: 30000000, spotPrice: 900, futuresPrice: 900 },
  };

  useEffect(() => {
    const defaults = ASSET_DEFAULTS[asset];
    setInputs(p => ({ ...p, asset, ...(defaults || {}) }));
    setOhlcText('');
  }, [asset]);

  // Fetch live data
  useEffect(() => {
    let cancelled = false;
    setLiveLoaded(false);
    const tickers = TICKER_MAP[asset];
    if (!tickers) return;

    async function loadLiveData() {
      try {
        let futuresData;
        try {
          const res = await fetchAnalyticsData(tickers.futures, '1y', '1d');
          if (res?.data && res.data.length >= 3) futuresData = res;
        } catch { /* fall through */ }
        if (!futuresData && tickers.fallback) {
          try {
            const res = await fetchAnalyticsData(tickers.fallback, '1y', '1d');
            if (res?.data && res.data.length >= 3) futuresData = res;
          } catch { /* give up */ }
        }
        if (cancelled || !futuresData?.data || futuresData.data.length < 3) return;
        // Parse ALL candles for backtest
        const allParsed: OHLC[] = futuresData.data.map(d => ({
          o: d.open > 0 ? d.open : d.close,
          h: d.high > 0 ? d.high : d.close,
          l: d.low > 0 ? d.low : d.close,
          c: d.close,
          v: d.volume ?? 0,
        }));
        setFullCandles(allParsed);
        setLiveAnalyticsData(futuresData.data);
        setDailyDates(futuresData.data.map(d => d.datetime.split(' ')[0]));

        // 30분봉 드릴다운 fetch (Yahoo 60일 한계)
        setIntradayLoading(true);
        try {
          const ticker30m = tickers.futures || tickers.fallback || '';
          const r30 = await fetchAnalyticsData(ticker30m, '60d', '30m');
          if (!cancelled && r30?.data?.length > 0) {
            setIntradayBarCount(r30.data.length);
            setIntradayMap(buildIntradayBarMap(r30.data));
          }
        } catch (err) {
          console.warn('[FabioStrategy] 30min data load failed (non-critical):', err);
        } finally {
          setIntradayLoading(false);
        }

        // Textarea shows recent 20 for display/analysis
        const recent = futuresData.data.slice(-20);
        const ohlcLines = recent.map(d => {
          const o = d.open > 0 ? d.open : d.close;
          const h = d.high > 0 ? d.high : d.close;
          const l = d.low > 0 ? d.low : d.close;
          return `${o.toFixed(2)}, ${h.toFixed(2)}, ${l.toFixed(2)}, ${d.close.toFixed(2)}`;
        }).join('\n');
        setOhlcText(ohlcLines);
        const lastClose = futuresData.data[futuresData.data.length - 1].close;
        let spotClose = lastClose;
        if (tickers.spot !== tickers.futures) {
          try {
            const spx = await fetchAnalyticsData(tickers.spot, '3mo', '1d');
            if (spx?.data && spx.data.length > 0) spotClose = spx.data[spx.data.length - 1].close;
          } catch { /* fallback */ }
        }
        if (cancelled) return;
        setInputs(p => ({ ...p, spotPrice: spotClose, futuresPrice: lastClose }));
        setLiveLoaded(true);
      } catch (err) {
        console.error('[FabioStrategy] Live data load failed:', err);
      }
    }
    loadLiveData();
    return () => { cancelled = true; };
  }, [asset]);

  // Compute
  const scalpResult = useMemo(() => computeScalp(inputs), [inputs]);

  // 30분봉 드릴다운: 최근 2거래일의 30분봉을 live 분석에 사용
  const recentIntradayBars = useMemo(() => {
    if (!intradayEnabled || intradayMap.size === 0) return undefined;
    const dates = Array.from(intradayMap.keys()).sort();
    const last2 = dates.slice(-2).flatMap(d => intradayMap.get(d) || []);
    return last2.slice(-20);
  }, [intradayEnabled, intradayMap]);

  const fabio: FabioAnalysis = useMemo(
    () => computeFabioAnalysis(candles, inputs, scalpResult, session, manualChecks, recentIntradayBars),
    [candles, inputs, scalpResult, session, manualChecks, recentIntradayBars],
  );

  // Multi-Strategy analysis (live)
  const multiStrategyResult = useMemo(() => {
    if (liveAnalyticsData.length < 5 || candles.length < 5) return null;
    return analyzeMultiStrategy(liveAnalyticsData, candles, fabio);
  }, [liveAnalyticsData, candles, fabio]);

  const [verifyingId, setVerifyingId] = useState<string | null>(null);
  const [verifiedItems, setVerifiedItems] = useState<Record<string, Set<number>>>({});

  const toggleCheck = (id: string) => {
    setManualChecks(prev => ({ ...prev, [id]: !prev[id] }));
  };

  const toggleVerify = (id: string) => {
    setVerifyingId(prev => prev === id ? null : id);
  };

  const toggleVerifyItem = (checkId: string, idx: number) => {
    setVerifiedItems(prev => {
      const s = new Set(prev[checkId] || []);
      if (s.has(idx)) s.delete(idx); else s.add(idx);
      return { ...prev, [checkId]: s };
    });
  };

  // ── SL/TP ticks auto-suggest ──
  const slTicks = useMemo(() => {
    if (!cfg || cfg.tick <= 0 || scalpResult.adaptiveStop <= 0) return 0;
    return Math.round(scalpResult.adaptiveStop / cfg.tick);
  }, [cfg, scalpResult.adaptiveStop]);

  const tpTicks = useMemo(() => {
    if (slTicks <= 0) return 0;
    const tpMult = fabio.model === 'TREND_CONTINUATION' ? 2.5 : 1.5;
    return Math.round(slTicks * tpMult);
  }, [slTicks, fabio.model]);

  // tradeResult 변경 시 auto-fill (사용자가 직접 수정하지 않은 경우만)
  useEffect(() => {
    if (tradePnLEdited) return;
    if (tradeResult === 'WIN') setTradePnL(tpTicks);
    else if (tradeResult === 'LOSS') setTradePnL(slTicks);
    else setTradePnL(0);
  }, [tradeResult, tpTicks, slTicks, tradePnLEdited]);

  const logTrade = () => {
    const newSession = addTradeToSession(session, {
      result: tradeResult,
      pnlTicks: tradeResult === 'LOSS' ? -Math.abs(tradePnL) : Math.abs(tradePnL),
      grade: fabio.grade.grade,
      model: fabio.model,
      note: tradeNote || undefined,
    }, dailyLossLimit);
    setSession(newSession);
    setShowTradeForm(false);
    setTradePnL(0);
    setTradePnLEdited(false);
    setTradeNote('');
  };

  const resetSession = () => {
    setSession(createInitialSession());
    setManualChecks({});
  };

  const { amt, tripleA, grade, checklist } = fabio;
  const allChecksDone = checklist.filter(c => !c.auto).every(c => c.checked);
  const autoChecksDone = checklist.filter(c => c.auto).every(c => c.checked);

  return (
    <div className="fb-page">

      {/* ── Header ── */}
      <div className="fb-header">
        <div className="fb-header-inner">
          <div className="fb-logo">
            <Link to="/scalp-analyzer" className="fb-back-btn">← Scalp</Link>
            <div className="fb-logo-icon">F</div>
            <div>
              <div className="fb-logo-title">Fabio Strategy Engine</div>
              <div className="fb-logo-sub">경매시장이론 + 주문흐름 + Triple-A + 세션관리</div>
            </div>
          </div>
          <div className="fb-asset-btns">
            {Object.entries(ASSETS).map(([k, v]) => (
              <button key={k} onClick={() => setAsset(k)}
                className={`fb-asset-btn ${asset === k ? 'active' : ''}`}>
                {k}<span style={{ fontSize: 9, marginLeft: 4, opacity: 0.6 }}>{fmtMoney(v.tickVal, v.sym)}/t</span>
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ── Polling Control ── */}
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

      {/* ── Verdict Banner ── */}
      <div className="fb-verdict" style={{
        background: `${gradeColor(grade.grade)}08`,
        borderBottom: `1px solid ${gradeColor(grade.grade)}25`,
        color: gradeColor(grade.grade),
      }}>
        <span className="fb-verdict-grade">Grade {grade.grade}</span>
        <span>—</span>
        <Pill color={stateColor(amt.marketState)}>{amt.marketState.replace('_', ' ')}</Pill>
        <span>→</span>
        <Pill color={K.acc}>{modelLabel(fabio.model)}</Pill>
        <span>—</span>
        <span>{scalpResult.isLong ? '▲ LONG' : '▼ SHORT'}</span>
        <span>—</span>
        <Pill color={phaseColor(tripleA.phase)}>{tripleA.phase.replace('_', ' ')}</Pill>
        {session.shouldStop && <Pill color={K.red}>⛔ STOP</Pill>}
        {liveLoaded && <Pill color={K.grn}>LIVE</Pill>}
        {intradayEnabled && intradayMap.size > 0 && <Pill color={K.cyn}>30M</Pill>}
      </div>

      {/* ── Body ── */}
      <div className="fb-body">
        <div className="fb-layout">

          {/* ── LEFT SIDEBAR: Inputs + Session ── */}
          <div className="fb-sidebar">

            {/* Data Input */}
            <div className="fb-box">
              <Sec icon="📋" title="OHLC Data" tag={liveLoaded ? "LIVE" : `${candles.length}봉`} tagC={liveLoaded ? K.grn : K.dim} />
              <textarea value={ohlcText} onChange={e => setOhlcText(e.target.value)}
                placeholder={"O, H, L, C (한 줄에 1봉)"} rows={4} className="fb-textarea" />
              <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 5 }}>
                <span style={{ fontSize: 9, color: candles.length >= 5 ? K.grn : K.red, fontFamily: F.mono }}>
                  {candles.length}봉 {candles.length < 5 && '(최소 5개)'}
                </span>
                <button onClick={() => setOhlcText(SAMPLE_OHLC)} className="fb-link-btn">샘플</button>
              </div>
              <NIn label="MA 기간" value={maPeriod} onChange={setMaPeriod} step={1} min={2} />
              <NIn label="ATR 배수" value={inputs.atrMult} onChange={s("atrMult")} step={0.1} min={0.1} help="스캘핑 0.5~1.0" />

              {/* 30분봉 드릴다운 토글 */}
              <div style={{
                display: 'flex', alignItems: 'center', gap: 8, marginTop: 8,
                padding: '6px 8px', borderRadius: 6,
                border: `1px solid ${intradayEnabled ? K.cyn + '40' : K.brd}`,
                background: intradayEnabled ? K.cyn + '08' : 'transparent',
              }}>
                <input type="checkbox" checked={intradayEnabled}
                  onChange={e => setIntradayEnabled(e.target.checked)}
                  style={{ accentColor: K.cyn }} />
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 10, fontWeight: 600, color: intradayEnabled ? K.cyn : K.dim }}>
                    30분봉 드릴다운
                  </div>
                  <div style={{ fontSize: 9, color: K.dim, fontFamily: F.mono }}>
                    {intradayLoading ? '로딩 중...' :
                      intradayMap.size > 0
                        ? `${intradayBarCount}봉 / ${intradayMap.size}일 (Triple-A + Aggression)`
                        : '데이터 없음'}
                  </div>
                </div>
                {intradayEnabled && intradayMap.size > 0 && (
                  <span style={{
                    fontSize: 9, fontWeight: 700, padding: '1px 6px', borderRadius: 3,
                    background: K.cyn + '20', color: K.cyn, border: `1px solid ${K.cyn}40`,
                  }}>30M</span>
                )}
              </div>
            </div>

            {/* Backtest Stats */}
            <div className="fb-box">
              <Sec icon="🎯" title="기대값 파라미터 (EV Params)" />
              <NIn label="승률" value={inputs.winRate} onChange={s("winRate")} step={1} unit="%" />
              <NIn label="평균 익절 (Avg Win)" value={inputs.avgWin} onChange={s("avgWin")} step={0.5} unit="t" />
              <NIn label="평균 손절 (Avg Loss)" value={inputs.avgLoss} onChange={s("avgLoss")} step={0.5} unit="t" />
              <NIn label="슬리피지" value={inputs.slippage} onChange={s("slippage")} step={0.25} unit="t" />
              <NIn label="수수료" value={inputs.commission} onChange={s("commission")} step={isKospi ? 100 : 0.05} unit={cfg.sym} />
            </div>

            {/* Account */}
            <div className="fb-box">
              <Sec icon="💰" title="계좌 정보 (Account)" />
              <NIn label="계좌잔고" value={inputs.accountBalance} onChange={s("accountBalance")} step={isKospi ? 1000000 : 100} unit={cfg.sym} />
              <NIn label="리스크" value={inputs.riskPct} onChange={s("riskPct")} step={0.25} min={0.1} unit="%" help="Fabio: 0.25~0.5%" />
              <NIn label="일일손실한도" value={dailyLossLimit} onChange={setDailyLossLimit} step={5} unit="t" help="도달 시 거래 중단" />
            </div>
          </div>

          {/* ── MAIN CONTENT ── */}
          <div className="fb-main">

            {/* ── Panel 1: AMT 3-Step Filter ── */}
            <div className="fb-box" style={{ borderColor: `${stateColor(amt.marketState)}30` }}>
              <Sec icon="🏛️" title="AMT 3단계 필터 (경매시장이론)" tag={amt.allPassed ? "ALL PASS" : "INCOMPLETE"} tagC={amt.allPassed ? K.grn : K.org} infoId="amtFilter" />

              <div className="fb-amt-steps">
                {/* Step 1: Market State */}
                <div className={`fb-amt-step ${amt.marketState !== 'UNKNOWN' ? 'pass' : 'fail'}`}>
                  <div className="fb-amt-step-num" style={{ background: stateColor(amt.marketState) }}>1</div>
                  <div className="fb-amt-step-body">
                    <div className="fb-amt-step-title">
                      시장 상태 (Market State)
                      <Pill color={stateColor(amt.marketState)}>{amt.marketState === 'BALANCE' ? '균형' : amt.marketState === 'IMBALANCE_BULL' ? '불균형 ▲' : amt.marketState === 'IMBALANCE_BEAR' ? '불균형 ▼' : amt.marketState.replace('_', ' ')}</Pill>
                    </div>
                    <div className="fb-amt-step-detail">{amt.marketStateReason}</div>
                    <div className="fb-amt-bar">
                      <div className="fb-amt-bar-fill" style={{
                        width: `${amt.marketStateScore}%`,
                        background: stateColor(amt.marketState),
                      }} />
                    </div>
                  </div>
                </div>

                {/* Step 2: Location */}
                <div className={`fb-amt-step ${amt.location.isAtKeyLevel ? 'pass' : 'fail'}`}>
                  <div className="fb-amt-step-num" style={{ background: amt.location.isAtKeyLevel ? K.grn : K.dim }}>2</div>
                  <div className="fb-amt-step-body">
                    <div className="fb-amt-step-title">
                      가격 위치 (Location)
                      <Pill color={amt.location.isAtKeyLevel ? K.grn : K.dim}>{amt.location.currentZone.replace('_', ' ')}</Pill>
                    </div>
                    <div className="fb-amt-step-detail">
                      <Term id="vah">VAH</Term>: {fmt(amt.location.vah)} | <Term id="poc">POC</Term>: {fmt(amt.location.poc)} | <Term id="val">VAL</Term>: {fmt(amt.location.val)} | POC거리: {fmt(amt.location.distFromPOC, 1)}p
                    </div>
                    {amt.location.lvnZones.length > 0 && (
                      <div className="fb-amt-step-detail" style={{ color: K.ylw }}>
                        <Term id="lvn">LVN</Term>: {amt.location.lvnZones.map(z => fmt(z, 1)).join(', ')}
                      </div>
                    )}
                  </div>
                </div>

                {/* Step 3: Aggression */}
                <div className={`fb-amt-step ${amt.aggression.detected ? 'pass' : 'fail'}`}>
                  <div className="fb-amt-step-num" style={{ background: amt.aggression.detected ? K.grn : K.dim }}>3</div>
                  <div className="fb-amt-step-body">
                    <div className="fb-amt-step-title">
                      공격성 (Aggression)
                      <Pill color={amt.aggression.detected ? K.grn : K.red}>
                        {amt.aggression.detected ? `${amt.aggression.direction} ${amt.aggression.score}pt` : '미감지'}
                      </Pill>
                    </div>
                    <div className="fb-amt-step-detail">{amt.aggression.reason}</div>
                    <div className="fb-amt-bar">
                      <div className="fb-amt-bar-fill" style={{
                        width: `${amt.aggression.score}%`,
                        background: amt.aggression.score >= 50 ? K.grn : amt.aggression.score >= 30 ? K.org : K.red,
                      }} />
                    </div>
                  </div>
                </div>
              </div>

              {/* Model Selection */}
              <div className="fb-model-banner" style={{
                background: `${K.acc}0a`,
                borderColor: `${K.acc}30`,
              }}>
                <span style={{ fontSize: 10, color: K.dim }}>모델 선택 →</span>
                <span style={{ fontSize: 14, fontWeight: 800, color: K.acc, fontFamily: F.mono }}>
                  {fabio.model === 'TREND_CONTINUATION' ? '📈 Trend Continuation' :
                    fabio.model === 'MEAN_REVERSION' ? '🔄 Mean Reversion' : '⏸️ No Model'}
                </span>
                <span style={{ fontSize: 10, color: K.dim }}>{fabio.modelReason}</span>
              </div>
            </div>

            {/* ── Panel 2: Triple-A Detector ── */}
            <div className="fb-box">
              <Sec icon="🔷" title="Triple-A 탐지기 (흡수-축적-공격)" tag={tripleA.phase.replace('_', ' ')} tagC={phaseColor(tripleA.phase)} infoId="tripleA" />
              <div className="fb-triple-a">
                {[
                  { label: '흡수 (Absorption)', sub: 'A1', data: tripleA.absorption, icon: '🛡️' },
                  { label: '축적 (Accumulation)', sub: 'A2', data: tripleA.accumulation, icon: '📦' },
                  { label: '공격 (Aggression)', sub: 'A3', data: { detected: tripleA.aggression.detected, score: tripleA.aggression.score, candles: 0 }, icon: '⚡' },
                ].map((phase, i) => (
                  <div key={i} className={`fb-triple-a-card ${phase.data.detected ? 'active' : ''}`}>
                    <div className="fb-triple-a-header">
                      <span className="fb-triple-a-icon">{phase.icon}</span>
                      <span className="fb-triple-a-label">{phase.label}</span>
                      <span className="fb-triple-a-sub">{phase.sub}</span>
                    </div>
                    <div className="fb-triple-a-bar">
                      <div className="fb-triple-a-bar-fill" style={{
                        width: `${phase.data.score}%`,
                        background: phase.data.detected
                          ? (i === 0 ? K.ylw : i === 1 ? K.cyn : K.grn)
                          : K.dim,
                      }} />
                    </div>
                    <div className="fb-triple-a-score">
                      {phase.data.detected ? '✓' : '—'} {phase.data.score}점
                      {phase.data.candles > 0 && ` (${phase.data.candles}봉)`}
                    </div>
                  </div>
                ))}
              </div>
              {tripleA.fullAlignment && (
                <div className="fb-full-alignment">
                  ✨ FULL ALIGNMENT — 최고 확신도 시그널 — Grade A 자동 부여
                </div>
              )}
            </div>

            {/* ── Panel 3: Grade System ── */}
            <div className="fb-box" style={{ borderColor: `${gradeColor(grade.grade)}30` }}>
              <Sec icon="⭐" title="셋업 등급 (Setup Grade)" tag={`Grade ${grade.grade}`} tagC={gradeColor(grade.grade)} infoId="setupGrade" />

              <div className="fb-grade-header">
                <div className="fb-grade-circle" style={{
                  background: `${gradeColor(grade.grade)}20`,
                  borderColor: gradeColor(grade.grade),
                  color: gradeColor(grade.grade),
                }}>
                  {grade.grade}
                </div>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 700, color: gradeColor(grade.grade) }}>
                    {grade.grade === 'A' ? '최고 확신도 — 풀 리스크' :
                      grade.grade === 'B' ? '중간 확신도 — 50% 리스크' :
                        grade.grade === 'C' ? '낮은 확신도 — 25% 리스크' :
                          '거래 조건 미충족'}
                  </div>
                  <div style={{ fontSize: 10, color: K.dim, fontFamily: F.mono }}>
                    {grade.confluenceCount}/6 <Term id="confluence">컨플루언스</Term> | 리스크 ×{grade.riskMultiplier} | 계약: {grade.adjustedContracts}
                  </div>
                </div>
              </div>

              <div className="fb-confluence-list">
                {grade.confluenceItems.map((item, i) => (
                  <div key={i} className={`fb-confluence-item ${item.met ? 'met' : ''}`}>
                    <span className="fb-confluence-check" style={{ color: item.met ? K.grn : K.red }}>
                      {item.met ? '✓' : '✗'}
                    </span>
                    <div style={{ flex: 1 }}>
                      <div className="fb-confluence-label">{item.label}</div>
                      <div className="fb-confluence-detail">{item.detail}</div>
                    </div>
                  </div>
                ))}
              </div>

              {/* Position sizing result */}
              <div className="fb-grade-position">
                <div>
                  <div style={{ fontSize: 9, color: K.mut, fontFamily: F.mono, textTransform: 'uppercase' }}>등급 조정 계약 수</div>
                  <div className="fb-grade-contracts" style={{ color: gradeColor(grade.grade) }}>
                    {grade.adjustedContracts}
                  </div>
                  <div style={{ fontSize: 9, color: K.dim, fontFamily: F.mono }}>
                    Base {scalpResult.recContracts} × {grade.riskMultiplier} = {grade.adjustedContracts} | <Term id="riskTier">리스크 등급</Term>: {grade.riskTier}
                  </div>
                </div>
              </div>
            </div>

            {/* ── Panel 4: Execution Checklist ── */}
            <div className="fb-box">
              <Sec icon="✅" title="실행 체크리스트" tag={`${checklist.filter(c => c.checked).length}/${checklist.length}`}
                tagC={allChecksDone && autoChecksDone ? K.grn : K.dim} />

              <div className="fb-checklist">
                {checklist.map(item => {
                  const isVerifying = verifyingId === item.id;
                  const manualVerified = verifiedItems[item.id] || new Set<number>();
                  // Count: auto-checked items + manually verified items
                  const totalVerified = item.verifyItems
                    ? item.verifyItems.reduce((n, vi, idx) => n + ((vi.autoChecked || manualVerified.has(idx)) ? 1 : 0), 0)
                    : 0;
                  const allVerified = item.verifyItems ? totalVerified >= item.verifyItems.length : false;
                  const autoCount = item.verifyItems ? item.verifyItems.filter(vi => vi.autoChecked).length : 0;
                  return (
                    <div key={item.id} className="fb-check-group">
                      <div
                        className={`fb-check-item ${item.checked ? 'done' : ''} ${item.auto ? 'auto' : 'manual'}`}
                        onClick={() => !item.auto && toggleCheck(item.id)}
                      >
                        <div className="fb-check-num">{item.step}</div>
                        <div className="fb-check-box" style={{
                          borderColor: item.checked ? K.grn : K.brd,
                          background: item.checked ? `${K.grn}20` : 'transparent',
                        }}>
                          {item.checked && <span style={{ color: K.grn }}>✓</span>}
                        </div>
                        <div style={{ flex: 1 }}>
                          <div className="fb-check-label">
                            {item.label}
                            {item.auto && <span className="fb-check-auto">AUTO</span>}
                          </div>
                          <div className="fb-check-detail">{item.detail}</div>
                        </div>
                        {!item.auto && item.verifyItems && (
                          <button
                            className={`fb-verify-btn ${isVerifying ? 'active' : ''} ${allVerified ? 'all-done' : ''}`}
                            onClick={e => { e.stopPropagation(); toggleVerify(item.id); }}
                          >
                            {allVerified ? '✓ 확인완료' : '실행확인'}
                            {!allVerified && item.verifyItems && (
                              <span className="fb-verify-count">
                                {totalVerified}/{item.verifyItems.length}
                                {autoCount > 0 && liveLoaded && <span className="fb-verify-auto-badge">A{autoCount}</span>}
                              </span>
                            )}
                          </button>
                        )}
                      </div>
                      {isVerifying && item.verifyItems && (
                        <div className="fb-verify-panel">
                          <div className="fb-verify-title">
                            확인 사항
                            {autoCount > 0 && liveLoaded && (
                              <span className="fb-verify-title-auto">LIVE AUTO {autoCount}건</span>
                            )}
                          </div>
                          {item.verifyItems.map((vi, idx) => {
                            const isAuto = !!(vi.autoChecked && liveLoaded);
                            const done = isAuto || manualVerified.has(idx);
                            return (
                              <div key={idx}
                                className={`fb-verify-item ${done ? 'done' : ''} ${isAuto ? 'auto-verified' : ''}`}
                                onClick={() => !isAuto && toggleVerifyItem(item.id, idx)}
                              >
                                <div className="fb-verify-check" style={{
                                  borderColor: done ? (isAuto ? K.cyn : K.grn) : K.brd,
                                  background: done ? (isAuto ? `${K.cyn}20` : `${K.grn}20`) : 'transparent',
                                }}>
                                  {done && <span style={{ color: isAuto ? K.cyn : K.grn, fontSize: 9 }}>✓</span>}
                                </div>
                                <div className="fb-verify-content">
                                  <div className="fb-verify-label">
                                    {vi.label}
                                    {isAuto && <span className="fb-verify-auto-tag">AUTO</span>}
                                  </div>
                                  {isAuto && vi.autoDetail ? (
                                    <div className="fb-verify-auto-detail">{vi.autoDetail}</div>
                                  ) : (
                                    <div className="fb-verify-hint">{vi.hint}</div>
                                  )}
                                </div>
                              </div>
                            );
                          })}
                          {allVerified && !item.checked && (
                            <div className="fb-verify-complete-hint">
                              모든 항목 확인 완료 — 좌측 체크박스를 눌러 완료 처리하세요
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>

              {allChecksDone && autoChecksDone && (
                <div className="fb-ready-banner">🚀 READY TO EXECUTE — 모든 체크 완료</div>
              )}
            </div>

            {/* ── Panel 5: Session Risk Tracker ── */}
            <div className="fb-box" style={{ borderColor: session.shouldStop ? `${K.red}40` : undefined }}>
              <Sec icon="🛡️" title="세션 관리 (Session Tracker)"
                tag={session.shouldStop ? 'STOPPED' : `${session.trades.length} trades`}
                tagC={session.shouldStop ? K.red : K.dim} />

              {session.shouldStop && (
                <div className="fb-stop-banner">⛔ {session.stopReason}</div>
              )}

              <div className="fb-session-stats">
                <Met label="Net P&L" value={`${session.totalPnL >= 0 ? '+' : ''}${session.totalPnL}t`}
                  color={session.totalPnL >= 0 ? K.grn : K.red} big />
                <Met label="Win" value={`${session.winCount}`} color={K.grn} />
                <Met label="Loss" value={`${session.lossCount}`} color={K.red} />
                <Met label="스크래치" value={`${session.scratchCount}`} />
                <Met label="Win Rate" value={session.sessionWinRate > 0 ? `${session.sessionWinRate.toFixed(0)}%` : '—'} />
                <Met label="연속 손실" value={`${session.consecutiveLosses}`}
                  color={session.consecutiveLosses >= 2 ? K.red : K.dim} />
                <Met label="리스크 등급" value={session.currentRiskTier}
                  color={session.currentRiskTier === 'MAX' ? K.grn : session.currentRiskTier === 'HALF' ? K.ylw : K.org} />
              </div>

              {/* Daily loss limit bar */}
              <div style={{ marginTop: 12 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 9, color: K.dim, fontFamily: F.mono }}>
                  <span>일일 손실 진행률</span>
                  <span>{Math.abs(Math.min(session.totalPnL, 0))} / {dailyLossLimit}t</span>
                </div>
                <div className="fb-loss-bar">
                  <div className="fb-loss-bar-fill" style={{
                    width: `${clamp(Math.abs(Math.min(session.totalPnL, 0)) / dailyLossLimit * 100, 0, 100)}%`,
                    background: Math.abs(Math.min(session.totalPnL, 0)) > dailyLossLimit * 0.7 ? K.red : K.org,
                  }} />
                </div>
              </div>

              {/* Trade log */}
              <div className="fb-trade-actions">
                <button className="fb-btn fb-btn-primary" onClick={() => setShowTradeForm(!showTradeForm)}>
                  {showTradeForm ? '취소' : '+ Log Trade'}
                </button>
                <button className="fb-btn fb-btn-ghost" onClick={resetSession}>
                  세션 리셋
                </button>
              </div>

              {showTradeForm && (
                <div className="fb-trade-form">
                  {/* SL/TP 추천값 표시 */}
                  {slTicks > 0 && (
                    <div style={{
                      display: 'flex', gap: 8, fontSize: 10, fontFamily: F.mono, marginBottom: 8,
                      padding: '6px 8px', background: `${K.bg0}cc`, borderRadius: 6, border: `1px solid ${K.brd}`,
                    }}>
                      <span style={{ color: K.dim }}>추천</span>
                      <span style={{ color: K.red }}>SL {slTicks}t</span>
                      <span style={{ color: K.dim }}>│</span>
                      <span style={{ color: K.grn }}>TP {tpTicks}t</span>
                      <span style={{ color: K.dim }}>│</span>
                      <span style={{ color: K.cyn }}>
                        {fabio.model === 'TREND_CONTINUATION' ? 'TREND ×2.5' : 'REV ×1.5'}
                      </span>
                      <span style={{ color: K.dim, marginLeft: 'auto' }}>
                        ATR {scalpResult.adaptiveStop.toFixed(2)}p ÷ {cfg.tick}t
                      </span>
                    </div>
                  )}

                  <div className="fb-trade-form-row">
                    {(['WIN', 'LOSS', 'SCRATCH'] as const).map(r => (
                      <button key={r} onClick={() => { setTradeResult(r); setTradePnLEdited(false); }}
                        className={`fb-btn ${tradeResult === r ? 'fb-btn-active' : 'fb-btn-ghost'}`}
                        style={{ color: r === 'WIN' ? K.grn : r === 'LOSS' ? K.red : K.dim }}>
                        {r}
                        <span style={{ fontSize: 9, opacity: 0.6, marginLeft: 4 }}>
                          {r === 'WIN' ? `+${tpTicks}t` : r === 'LOSS' ? `-${slTicks}t` : '0t'}
                        </span>
                      </button>
                    ))}
                  </div>
                  <NIn label="P&L (ticks)" value={tradePnL}
                    onChange={v => { setTradePnL(v); setTradePnLEdited(true); }}
                    step={1} unit="t"
                    help={tradePnLEdited ? '수동 입력' : '자동 추천값 (수정 가능)'} />
                  <div className="fb-input-group">
                    <label className="fb-input-label">메모</label>
                    <input type="text" value={tradeNote} onChange={e => setTradeNote(e.target.value)}
                      placeholder="optional" className="fb-input" />
                  </div>
                  <button className="fb-btn fb-btn-primary" onClick={logTrade} style={{ width: '100%' }}>
                    기록 저장
                  </button>
                </div>
              )}

              {/* Trade history */}
              {session.trades.length > 0 && (
                <div className="fb-trade-history">
                  {session.trades.slice().reverse().map(t => (
                    <div key={t.id} className="fb-trade-row">
                      <span style={{ fontSize: 9, color: K.dim, fontFamily: F.mono }}>{t.time}</span>
                      <Pill color={t.result === 'WIN' ? K.grn : t.result === 'LOSS' ? K.red : K.dim}>
                        {t.result}
                      </Pill>
                      <span style={{
                        fontSize: 12, fontWeight: 700, fontFamily: F.mono,
                        color: t.pnlTicks >= 0 ? K.grn : K.red,
                      }}>
                        {t.pnlTicks >= 0 ? '+' : ''}{t.pnlTicks}t
                      </span>
                      <Pill color={gradeColor(t.grade)}>{t.grade}</Pill>
                      {t.note && <span style={{ fontSize: 9, color: K.dim }}>{t.note}</span>}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* ── Panel 6: Historical Backtest ── */}
            <div className="fb-box" style={{ borderColor: btResult ? `${K.cyn}30` : undefined }}>
              <div className="fb-sec" style={{ cursor: 'pointer' }} onClick={() => setBtExpanded(!btExpanded)}>
                <span className="fb-sec-icon">📊</span>
                <span className="fb-sec-title">과거 데이터 백테스트</span>
                {btResult && <Pill color={btResult.totalPnLPct >= 0 ? K.grn : K.red}>
                  {btResult.totalTrades}trades / {btResult.winRate.toFixed(0)}% WR
                </Pill>}
                <span style={{ marginLeft: 'auto', fontSize: 11, color: K.dim }}>{btExpanded ? '▲' : '▼'}</span>
              </div>

              {btExpanded && (
                <>
                  {/* Config */}
                  <div className="fb-bt-config">
                    <NIn label="Lookback" value={btConfig.lookback} onChange={bc('lookback')} step={1} min={5} help="MA/분석 윈도우" />
                    <NIn label="ATR 배수" value={btConfig.atrMult} onChange={bc('atrMult')} step={0.1} min={0.1} />
                    <NIn label="최대보유봉" value={btConfig.maxHoldBars} onChange={bc('maxHoldBars')} step={1} min={3} max={20} help="스캘핑 3~5" />
                    <NIn label="TP(추세)" value={btConfig.tpMultTrend} onChange={bc('tpMultTrend')} step={0.25} min={1} max={5} help="SL의 N배" />
                    <NIn label="TP(회귀)" value={btConfig.tpMultReversion} onChange={bc('tpMultReversion')} step={0.25} min={0.5} max={3} />
                    <NIn label="SL(추세)" value={btConfig.slMultTrend} onChange={bc('slMultTrend')} step={0.1} min={0.3} max={2} />
                    <NIn label="SL(회귀)" value={btConfig.slMultReversion} onChange={bc('slMultReversion')} step={0.1} min={0.3} max={2} />
                    <div className="fb-input-group">
                      <label className="fb-input-label">최소 GRADE</label>
                      <div style={{ display: 'flex', gap: 4 }}>
                        {(['A', 'B', 'C'] as const).map(g => (
                          <button key={g} onClick={() => setBtConfig(p => ({ ...p, minGrade: g }))}
                            className={`fb-btn ${btConfig.minGrade === g ? 'fb-btn-active' : 'fb-btn-ghost'}`}
                            style={{ color: gradeColor(g), flex: 1 }}>
                            {g}
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>

                  <button className="fb-btn fb-btn-primary" style={{ width: '100%', marginTop: 8, padding: '10px 0' }}
                    onClick={() => {
                      setBtRunning(true);
                      // Use setTimeout so UI updates
                      setTimeout(() => {
                        const result = runBacktest(
                          btCandles, btConfig, asset,
                          intradayEnabled ? intradayMap : undefined,
                          intradayEnabled ? dailyDates : undefined,
                        );
                        setBtResult(result);
                        setBtRunning(false);
                      }, 50);
                    }}
                    disabled={btRunning || btCandles.length < 10}>
                    {btRunning ? '분석 중...' : `▶ Run Backtest (${btCandles.length}봉)`}
                  </button>

                  {btCandles.length < 10 && (
                    <div style={{ fontSize: 9, color: K.org, marginTop: 6, fontFamily: F.mono }}>
                      ⚠ 최소 10봉 이상 필요. 더 많은 데이터를 입력하거나 LIVE 로드를 이용하세요.
                    </div>
                  )}
                  {fullCandles.length > 0 && (
                    <div style={{ fontSize: 9, color: K.cyn, marginTop: 4, fontFamily: F.mono }}>
                      📊 LIVE 데이터: {fullCandles.length}봉 (1년) / 분석 표시: {candles.length}봉 (최근 20일)
                    </div>
                  )}
                  {intradayEnabled && intradayMap.size > 0 && (
                    <div style={{ fontSize: 9, color: K.cyn, marginTop: 2, fontFamily: F.mono }}>
                      🔷 30분봉 드릴다운: {intradayBarCount}봉 / {intradayMap.size}일 — Triple-A + Aggression
                    </div>
                  )}
                  {btResult?.intradayStats && (
                    <div style={{ fontSize: 9, color: K.cyn, marginTop: 2, fontFamily: F.mono }}>
                      🔷 30M 커버리지: {btResult.intradayStats.intradayUsed}/{btResult.intradayStats.total}일
                      ({btResult.intradayStats.total > 0 ? Math.round(btResult.intradayStats.intradayUsed / btResult.intradayStats.total * 100) : 0}%)
                      {btResult.intradayStats.dailyFallback > 0 && ` / 일봉 폴백: ${btResult.intradayStats.dailyFallback}일`}
                    </div>
                  )}

                  {/* Results */}
                  {btResult && btResult.totalTrades > 0 && (
                    <>
                      <div className="fb-bt-summary">
                        <Met label="총 거래 수" value={`${btResult.totalTrades}`} big />
                        <Met label="승률" value={`${btResult.winRate.toFixed(1)}%`}
                          color={btResult.winRate >= 50 ? K.grn : K.red} big />
                        <Met label="수익팩터 (PF)" value={btResult.profitFactor === Infinity ? '∞' : btResult.profitFactor.toFixed(2)}
                          color={btResult.profitFactor >= 1.5 ? K.grn : btResult.profitFactor >= 1 ? K.ylw : K.red} />
                        <Met label="총 손익" value={`${btResult.totalPnLPoints >= 0 ? '+' : ''}${btResult.totalPnLPoints.toFixed(1)}p`}
                          color={btResult.totalPnLPoints >= 0 ? K.grn : K.red} />
                        <Met label="샤프비율 (≈)" value={btResult.sharpeApprox.toFixed(2)}
                          color={btResult.sharpeApprox >= 1 ? K.grn : btResult.sharpeApprox >= 0 ? K.ylw : K.red} />
                      </div>

                      <div className="fb-bt-details">
                        <Met label="TP / SL / Timeout" value={`${btResult.wins} / ${btResult.losses} / ${btResult.timeouts}`} />
                        <Met label="평균 수익 (Avg +)" value={`+${btResult.avgWinPoints.toFixed(1)}p`} color={K.grn} />
                        <Met label="평균 손실 (Avg −)" value={`-${btResult.avgLossPoints.toFixed(1)}p`} color={K.red} />
                        <Met label="최대낙폭 (MDD)" value={`${btResult.maxDrawdownPct.toFixed(2)}%`} color={K.red} />
                        <Met label="최대연속손" value={`${btResult.maxConsecutiveLosses}`}
                          color={btResult.maxConsecutiveLosses >= 3 ? K.red : K.dim} />
                        <Met label="최대연속승" value={`${btResult.maxConsecutiveWins}`} color={K.grn} />
                      </div>

                      {/* ── Enhanced Equity Curve ── */}
                      <div className="fb-bt-equity">
                        <div style={{ fontSize: 9, color: K.dim, fontFamily: F.mono, marginBottom: 6 }}>EQUITY CURVE (%)</div>
                        {(() => {
                          const eq = btResult.equityCurve;
                          const trades = btResult.trades;
                          const n = eq.length;
                          if (n < 2) return null;

                          const mn = Math.min(...eq, 0);
                          const mx = Math.max(...eq, 0);
                          const rng = mx - mn || 1;

                          // Chart dimensions
                          const W = 600, H = 180;
                          const pad = { l: 48, r: 12, t: 10, b: 22 };
                          const cW = W - pad.l - pad.r;
                          const cH = H - pad.t - pad.b;

                          const toX = (i: number) => pad.l + (i / (n - 1)) * cW;
                          const toY = (v: number) => pad.t + cH - ((v - mn) / rng) * cH;
                          const zeroY = toY(0);

                          // Grid levels
                          const gridSteps = 5;
                          const gridLines: { y: number; label: string }[] = [];
                          for (let i = 0; i <= gridSteps; i++) {
                            const v = mn + (rng * i) / gridSteps;
                            gridLines.push({ y: toY(v), label: `${v >= 0 ? '+' : ''}${v.toFixed(1)}%` });
                          }

                          // Equity path
                          const eqPts = eq.map((v, i) => `${toX(i).toFixed(1)},${toY(v).toFixed(1)}`);
                          const eqPath = `M${eqPts.join(' L')}`;

                          // Fill above/below zero
                          const fillAbove = `M${toX(0).toFixed(1)},${zeroY.toFixed(1)} ${eqPts.join(' ')} L${toX(n - 1).toFixed(1)},${zeroY.toFixed(1)} Z`;

                          // Drawdown curve
                          let peak = eq[0];
                          const dd: number[] = eq.map(v => {
                            if (v > peak) peak = v;
                            return v - peak; // always <= 0
                          });
                          const ddMin = Math.min(...dd);
                          const mddIdx = dd.indexOf(ddMin);

                          // Drawdown fill (from equity to peak)
                          const ddPts = dd.map((d, i) => {
                            if (d >= 0) return null;
                            return { x: toX(i), yTop: toY(eq[i] - d), yBot: toY(eq[i]) };
                          }).filter(Boolean) as { x: number; yTop: number; yBot: number }[];

                          // P&L bar chart data
                          const barH = 40;
                          const pnls = trades.map(t => t.pnlPoints);
                          const pnlMax = Math.max(...pnls.map(Math.abs), 1);

                          return (
                            <div>
                              <svg width="100%" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet"
                                style={{ display: 'block' }}>
                                <defs>
                                  <linearGradient id="eqGradUp" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="0%" stopColor={K.grn} stopOpacity="0.20" />
                                    <stop offset="100%" stopColor={K.grn} stopOpacity="0.02" />
                                  </linearGradient>
                                  <linearGradient id="eqGradDn" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="0%" stopColor={K.red} stopOpacity="0.02" />
                                    <stop offset="100%" stopColor={K.red} stopOpacity="0.18" />
                                  </linearGradient>
                                  <linearGradient id="ddGrad" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="0%" stopColor={K.red} stopOpacity="0.0" />
                                    <stop offset="100%" stopColor={K.red} stopOpacity="0.25" />
                                  </linearGradient>
                                </defs>

                                {/* Background */}
                                <rect x={pad.l} y={pad.t} width={cW} height={cH} fill="#060910" rx="2" />

                                {/* Grid lines */}
                                {gridLines.map((g, i) => (
                                  <g key={i}>
                                    <line x1={pad.l} y1={g.y} x2={W - pad.r} y2={g.y}
                                      stroke={K.brd} strokeWidth="0.5" strokeDasharray="3,3" opacity="0.5" />
                                    <text x={pad.l - 4} y={g.y + 3} textAnchor="end"
                                      fill={K.dim} fontSize="7" fontFamily="'IBM Plex Mono',monospace">{g.label}</text>
                                  </g>
                                ))}

                                {/* Zero line (bold) */}
                                <line x1={pad.l} y1={zeroY} x2={W - pad.r} y2={zeroY}
                                  stroke="#4a5578" strokeWidth="1" />

                                {/* Equity fill */}
                                <path d={fillAbove}
                                  fill={btResult.totalPnLPct >= 0 ? 'url(#eqGradUp)' : 'url(#eqGradDn)'} />

                                {/* Drawdown shading */}
                                {ddPts.length > 0 && ddPts.map((p, i) => (
                                  <line key={i} x1={p.x} y1={p.yTop} x2={p.x} y2={p.yBot}
                                    stroke={K.red} strokeWidth={cW / n + 0.5} opacity="0.12" />
                                ))}

                                {/* Equity curve line */}
                                <path d={eqPath} fill="none"
                                  stroke={btResult.totalPnLPct >= 0 ? K.grn : K.red}
                                  strokeWidth="1.8" strokeLinejoin="round" strokeLinecap="round" />

                                {/* Trade dots */}
                                {trades.map((t, i) => {
                                  if (i >= eq.length) return null;
                                  const cx = toX(i);
                                  const cy = toY(eq[i]);
                                  const c = t.result === 'WIN' ? K.grn : t.result === 'LOSS' ? K.red : K.ylw;
                                  return (
                                    <circle key={i} cx={cx} cy={cy} r={n > 50 ? 1.8 : 2.5}
                                      fill={c} stroke="#060910" strokeWidth="0.5" opacity="0.85" />
                                  );
                                })}

                                {/* Peak marker */}
                                {(() => {
                                  const peakIdx = eq.indexOf(mx);
                                  if (mx <= 0) return null;
                                  const px = toX(peakIdx), py = toY(mx);
                                  return (
                                    <g>
                                      <circle cx={px} cy={py} r="3.5" fill="none" stroke={K.grn} strokeWidth="1" />
                                      <text x={px} y={py - 7} textAnchor="middle"
                                        fill={K.grn} fontSize="7" fontWeight="700"
                                        fontFamily="'IBM Plex Mono',monospace">
                                        +{mx.toFixed(1)}%
                                      </text>
                                    </g>
                                  );
                                })()}

                                {/* MDD marker */}
                                {ddMin < -0.5 && (() => {
                                  const px = toX(mddIdx), py = toY(eq[mddIdx]);
                                  return (
                                    <g>
                                      <circle cx={px} cy={py} r="3.5" fill="none" stroke={K.red} strokeWidth="1" />
                                      <line x1={px} y1={py} x2={px} y2={toY(eq[mddIdx] - dd[mddIdx])}
                                        stroke={K.red} strokeWidth="1" strokeDasharray="2,2" opacity="0.6" />
                                      <text x={px} y={py + 12} textAnchor="middle"
                                        fill={K.red} fontSize="7" fontWeight="700"
                                        fontFamily="'IBM Plex Mono',monospace">
                                        MDD {ddMin.toFixed(1)}%
                                      </text>
                                    </g>
                                  );
                                })()}

                                {/* Final value label */}
                                {(() => {
                                  const last = eq[n - 1];
                                  const lx = toX(n - 1), ly = toY(last);
                                  const c = last >= 0 ? K.grn : K.red;
                                  return (
                                    <g>
                                      <circle cx={lx} cy={ly} r="3" fill={c} stroke="#060910" strokeWidth="1" />
                                      <rect x={lx - 28} y={ly - 14} width="56" height="12" rx="2"
                                        fill="#0b0f18" stroke={c} strokeWidth="0.5" opacity="0.9" />
                                      <text x={lx} y={ly - 5} textAnchor="middle"
                                        fill={c} fontSize="7.5" fontWeight="800"
                                        fontFamily="'IBM Plex Mono',monospace">
                                        {last >= 0 ? '+' : ''}{last.toFixed(2)}%
                                      </text>
                                    </g>
                                  );
                                })()}

                                {/* X-axis labels */}
                                {[0, Math.floor(n / 4), Math.floor(n / 2), Math.floor(3 * n / 4), n - 1]
                                  .filter((v, i, a) => a.indexOf(v) === i)
                                  .map(i => (
                                    <text key={i} x={toX(i)} y={H - 4} textAnchor="middle"
                                      fill={K.dim} fontSize="7" fontFamily="'IBM Plex Mono',monospace">
                                      #{i + 1}
                                    </text>
                                  ))}
                              </svg>

                              {/* ── P&L per Trade bar chart ── */}
                              <div style={{ fontSize: 9, color: K.dim, fontFamily: F.mono, margin: '10px 0 4px' }}>
                                TRADE P&L (points)
                              </div>
                              <svg width="100%" viewBox={`0 0 ${W} ${barH + 14}`} preserveAspectRatio="xMidYMid meet"
                                style={{ display: 'block' }}>
                                <rect x={pad.l} y={0} width={cW} height={barH} fill="#060910" rx="2" />
                                {/* Zero line */}
                                <line x1={pad.l} y1={barH / 2} x2={W - pad.r} y2={barH / 2}
                                  stroke="#4a5578" strokeWidth="0.5" />
                                {/* Bars */}
                                {pnls.map((p, i) => {
                                  const barW = Math.max(cW / pnls.length - 1, 1.5);
                                  const x = pad.l + (i / pnls.length) * cW + 0.5;
                                  const h = (Math.abs(p) / pnlMax) * (barH / 2 - 2);
                                  const y = p >= 0 ? barH / 2 - h : barH / 2;
                                  const c = p >= 0 ? K.grn : K.red;
                                  return (
                                    <rect key={i} x={x} y={y} width={barW} height={h}
                                      fill={c} opacity="0.7" rx="0.5" />
                                  );
                                })}
                                {/* Y labels */}
                                <text x={pad.l - 4} y={5} textAnchor="end"
                                  fill={K.grn} fontSize="6.5" fontFamily="'IBM Plex Mono',monospace">
                                  +{pnlMax.toFixed(0)}
                                </text>
                                <text x={pad.l - 4} y={barH + 2} textAnchor="end"
                                  fill={K.red} fontSize="6.5" fontFamily="'IBM Plex Mono',monospace">
                                  -{pnlMax.toFixed(0)}
                                </text>
                              </svg>
                            </div>
                          );
                        })()}
                      </div>

                      {/* Grade & Model Distribution */}
                      <div className="fb-bt-dist">
                        <div className="fb-bt-dist-col">
                          <div style={{ fontSize: 9, color: K.dim, fontFamily: F.mono, marginBottom: 4 }}>GRADE 분포</div>
                          {Object.entries(btResult.gradeDistribution).map(([g, n]) => (
                            <div key={g} className="fb-bt-dist-row">
                              <Pill color={gradeColor(g as SetupGrade)}>{g}</Pill>
                              <div className="fb-bt-dist-bar">
                                <div style={{
                                  width: `${(n / btResult.totalTrades) * 100}%`, height: '100%',
                                  background: gradeColor(g as SetupGrade), borderRadius: 2
                                }} />
                              </div>
                              <span style={{ fontSize: 10, color: K.dim, fontFamily: F.mono }}>{n} ({((n / btResult.totalTrades) * 100).toFixed(0)}%)</span>
                            </div>
                          ))}
                        </div>
                        <div className="fb-bt-dist-col">
                          <div style={{ fontSize: 9, color: K.dim, fontFamily: F.mono, marginBottom: 4 }}>MODEL 분포</div>
                          {Object.entries(btResult.modelDistribution).map(([m, n]) => (
                            <div key={m} className="fb-bt-dist-row">
                              <Pill color={K.acc}>{m === 'TREND_CONTINUATION' ? 'TREND' : 'MR'}</Pill>
                              <div className="fb-bt-dist-bar">
                                <div style={{
                                  width: `${(n / btResult.totalTrades) * 100}%`, height: '100%',
                                  background: K.acc, borderRadius: 2
                                }} />
                              </div>
                              <span style={{ fontSize: 10, color: K.dim, fontFamily: F.mono }}>{n}</span>
                            </div>
                          ))}
                        </div>
                      </div>

                      {/* Grade & Direction Performance */}
                      <div style={{ marginTop: 16 }}>
                        <div style={{ fontSize: 9, color: K.dim, fontFamily: F.mono, marginBottom: 6 }}>GRADE & DIRECTION PERF</div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                          {Object.entries(btResult.gradeDirectionStats)
                            .sort(([g1], [g2]) => g1.localeCompare(g2))
                            .map(([grade, stats]) => (
                              <div key={grade} style={{ display: 'flex', flexWrap: 'wrap', gap: 12, padding: '10px 14px', background: K.bg1, border: `1px solid ${gradeColor(grade as SetupGrade)}40`, borderRadius: 8 }}>
                                <div style={{ width: 40, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                  <div style={{ width: 32, height: 32, borderRadius: '50%', background: `${gradeColor(grade as SetupGrade)}20`, border: `1px solid ${gradeColor(grade as SetupGrade)}`, color: gradeColor(grade as SetupGrade), display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 'bold' }}>
                                    {grade}
                                  </div>
                                </div>
                                <div style={{ flex: 1, minWidth: 200 }}>
                                  <div style={{ fontSize: 10, color: K.grn, fontFamily: F.mono, marginBottom: 4 }}>LONG (매수)</div>
                                  <div style={{ display: 'flex', gap: 12 }}>
                                    <Met label="Trades" value={`${stats.LONG.trades}`} />
                                    <Met label="Win Rate" value={stats.LONG.trades > 0 ? `${((stats.LONG.wins / stats.LONG.trades) * 100).toFixed(0)}%` : '—'} />
                                    <Met label="PnL" value={`${stats.LONG.pnlPoints >= 0 ? '+' : ''}${stats.LONG.pnlPoints.toFixed(1)}p`} color={stats.LONG.pnlPoints >= 0 ? K.grn : K.red} />
                                  </div>
                                </div>
                                <div style={{ width: 1, background: K.brd }} />
                                <div style={{ flex: 1, minWidth: 200 }}>
                                  <div style={{ fontSize: 10, color: K.red, fontFamily: F.mono, marginBottom: 4 }}>SHORT (매도)</div>
                                  <div style={{ display: 'flex', gap: 12 }}>
                                    <Met label="Trades" value={`${stats.SHORT.trades}`} />
                                    <Met label="Win Rate" value={stats.SHORT.trades > 0 ? `${((stats.SHORT.wins / stats.SHORT.trades) * 100).toFixed(0)}%` : '—'} />
                                    <Met label="PnL" value={`${stats.SHORT.pnlPoints >= 0 ? '+' : ''}${stats.SHORT.pnlPoints.toFixed(1)}p`} color={stats.SHORT.pnlPoints >= 0 ? K.grn : K.red} />
                                  </div>
                                </div>
                              </div>
                            ))}
                        </div>
                      </div>

                      {/* Trade Log */}
                      <div style={{ marginTop: 16 }}>
                        <div style={{ fontSize: 9, color: K.dim, fontFamily: F.mono, marginBottom: 6 }}>TRADE LOG (최근 20)</div>
                        <div className="fb-bt-log">
                          <div className="fb-bt-log-header">
                            <span>#</span><span>Dir</span><span>Entry</span><span>Exit</span><span>P&L</span><span>Grade</span><span>Result</span>
                          </div>
                          {btResult.trades.slice(-20).map((t, i) => (
                            <div key={i} className="fb-bt-log-row" style={{
                              background: t.result === 'WIN' ? `${K.grn}06` : t.result === 'LOSS' ? `${K.red}06` : 'transparent',
                            }}>
                              <span>{t.barIndex}</span>
                              <span style={{ color: t.direction === 'LONG' ? K.grn : K.red }}>{t.direction === 'LONG' ? '▲' : '▼'}</span>
                              <span>{t.entryPrice.toFixed(1)}</span>
                              <span>{t.exitPrice.toFixed(1)}</span>
                              <span style={{ color: t.pnlPoints >= 0 ? K.grn : K.red, fontWeight: 700 }}>
                                {t.pnlPoints >= 0 ? '+' : ''}{t.pnlPoints.toFixed(1)}
                              </span>
                              <span style={{ color: gradeColor(t.grade) }}>{t.grade}</span>
                              <span style={{ color: t.result === 'WIN' ? K.grn : t.result === 'LOSS' ? K.red : K.dim }}>
                                {t.result}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    </>
                  )}

                  {btResult && btResult.totalTrades === 0 && (
                    <div style={{ marginTop: 12, padding: 14, textAlign: 'center', color: K.dim, fontSize: 11, fontFamily: F.mono }}>
                      시그널 없음 — 데이터가 부족하거나 조건을 충족하는 바가 없습니다. Lookback 줄이거나 최소 Grade를 C로 변경해보세요.
                    </div>
                  )}
                </>
              )}
            </div>

            {/* ── Multi-Strategy Panel ── */}
            <div className="fb-box" style={{ borderColor: multiStrategyResult ? `${REGIME_COLORS[multiStrategyResult.regime.regime]}30` : undefined }}>
              <div className="fb-sec" style={{ cursor: 'pointer' }} onClick={() => setMsExpanded(!msExpanded)}>
                <span>&#x1F3AF; Multi-Strategy Selector</span>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  {multiStrategyResult && (
                    <span className="fb-regime-badge" style={{
                      background: `${REGIME_COLORS[multiStrategyResult.regime.regime]}20`,
                      color: REGIME_COLORS[multiStrategyResult.regime.regime],
                      border: `1px solid ${REGIME_COLORS[multiStrategyResult.regime.regime]}40`,
                    }}>
                      {REGIME_LABELS[multiStrategyResult.regime.regime]}
                    </span>
                  )}
                  <span style={{ fontSize: 11, color: K.dim }}>{msExpanded ? '\u25B2' : '\u25BC'}</span>
                </div>
              </div>

              {msExpanded && (
                <div style={{ padding: '8px 0' }}>
                  {/* Regime info */}
                  {multiStrategyResult ? (
                    <>
                      <div className="fb-ms-recommend">
                        <span style={{ fontSize: 16 }}>&#x1F4A1;</span>
                        <span>
                          <strong>{REGIME_LABELS[multiStrategyResult.regime.regime]}</strong>
                          {' \u2192 '}
                          {multiStrategyResult.recommended
                            ? <strong style={{ color: K.acc }}>{STRATEGY_LABELS[multiStrategyResult.recommended]} \uCD94\uCC9C</strong>
                            : <span style={{ color: K.ylw }}>관망 대기 (스퀴즈)</span>
                          }
                          <span style={{ color: K.dim, marginLeft: 8, fontSize: 11 }}>
                            신뢰도 {multiStrategyResult.regime.confidence}%
                          </span>
                        </span>
                      </div>

                      {/* Indicators */}
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8, margin: '8px 0' }}>
                        {[
                          { label: 'ADX', value: multiStrategyResult.regime.indicators.adx?.toFixed(0) ?? 'N/A' },
                          { label: 'BB Width', value: multiStrategyResult.regime.indicators.bbWidth ? `${multiStrategyResult.regime.indicators.bbWidth.toFixed(1)}%` : 'N/A' },
                          { label: 'DI Spread', value: multiStrategyResult.regime.indicators.diSpread?.toFixed(0) ?? 'N/A' },
                          { label: 'ATR%', value: multiStrategyResult.regime.indicators.atrPct ? `${multiStrategyResult.regime.indicators.atrPct.toFixed(2)}%` : 'N/A' },
                        ].map((ind, idx) => (
                          <div key={idx} style={{ textAlign: 'center', fontSize: 11 }}>
                            <div style={{ color: K.dim }}>{ind.label}</div>
                            <div style={{ color: K.txt, fontWeight: 600 }}>{ind.value}</div>
                          </div>
                        ))}
                      </div>

                      {/* 3 Strategy Cards */}
                      <div className="fb-strategy-cards">
                        {/* Mean Reversion */}
                        {(() => {
                          const sig = multiStrategyResult.signals.meanRev;
                          const isRec = multiStrategyResult.recommended === 'MEAN_REVERSION';
                          return (
                            <div className={`fb-strategy-card ${isRec ? 'recommended' : ''}`}>
                              <div className="fb-strategy-card-title">
                                <span style={{ color: K.cyn }}>&#x1F4CA;</span> Mean Reversion
                                {isRec && <span style={{ fontSize: 9, color: K.acc, border: `1px solid ${K.acc}40`, padding: '1px 4px', borderRadius: 3 }}>REC</span>}
                              </div>
                              <span className="fb-strategy-signal-badge" style={{
                                background: sig.action === 'LONG' ? `${K.grn}20` : sig.action === 'SHORT' ? `${K.red}20` : `${K.dim}15`,
                                color: sig.action === 'LONG' ? K.grn : sig.action === 'SHORT' ? K.red : K.dim,
                              }}>
                                {sig.action}
                              </span>
                              <div className="fb-strategy-detail">
                                <div><strong>Z-Score:</strong> {sig.zScore.toFixed(2)}</div>
                                <div><strong>RSI:</strong> {sig.rsiProxy?.toFixed(0) ?? 'N/A'}</div>
                                {sig.stopLoss && <div><strong>SL:</strong> {sig.stopLoss.toFixed(2)}</div>}
                                {sig.takeProfit && <div><strong>TP:</strong> {sig.takeProfit.toFixed(2)}</div>}
                                <div style={{ color: K.dim, fontSize: 10, marginTop: 4 }}>{sig.reason}</div>
                              </div>
                            </div>
                          );
                        })()}

                        {/* Trend Following */}
                        {(() => {
                          const sig = multiStrategyResult.signals.trendFollow;
                          const isRec = multiStrategyResult.recommended === 'TREND_FOLLOWING';
                          return (
                            <div className={`fb-strategy-card ${isRec ? 'recommended' : ''}`}>
                              <div className="fb-strategy-card-title">
                                <span style={{ color: K.grn }}>&#x1F4C8;</span> Trend Following
                                {isRec && <span style={{ fontSize: 9, color: K.acc, border: `1px solid ${K.acc}40`, padding: '1px 4px', borderRadius: 3 }}>REC</span>}
                              </div>
                              <span className="fb-strategy-signal-badge" style={{
                                background: sig.action === 'LONG' ? `${K.grn}20` : sig.action === 'SHORT' ? `${K.red}20` : `${K.dim}15`,
                                color: sig.action === 'LONG' ? K.grn : sig.action === 'SHORT' ? K.red : K.dim,
                              }}>
                                {sig.action}
                              </span>
                              <div className="fb-strategy-detail">
                                <div><strong>ADX:</strong> {sig.adxValue?.toFixed(0) ?? 'N/A'}</div>
                                <div><strong>DI Spread:</strong> {sig.diSpread?.toFixed(0) ?? 'N/A'}</div>
                                {sig.chandelierStop && <div><strong>Chandelier:</strong> {sig.chandelierStop.toFixed(2)}</div>}
                                {sig.trailingStop && <div><strong>Trailing:</strong> {sig.trailingStop.toFixed(2)}</div>}
                                <div style={{ color: K.dim, fontSize: 10, marginTop: 4 }}>{sig.reason}</div>
                              </div>
                            </div>
                          );
                        })()}

                        {/* Scalp/Momentum */}
                        {(() => {
                          const sig = multiStrategyResult.signals.scalp;
                          const isRec = multiStrategyResult.recommended === 'SCALP_MOMENTUM';
                          return (
                            <div className={`fb-strategy-card ${isRec ? 'recommended' : ''}`}>
                              <div className="fb-strategy-card-title">
                                <span style={{ color: K.org }}>&#x26A1;</span> Scalp / Momentum
                                {isRec && <span style={{ fontSize: 9, color: K.acc, border: `1px solid ${K.acc}40`, padding: '1px 4px', borderRadius: 3 }}>REC</span>}
                              </div>
                              <span className="fb-strategy-signal-badge" style={{
                                background: sig.action === 'LONG' ? `${K.grn}20` : sig.action === 'SHORT' ? `${K.red}20` : `${K.dim}15`,
                                color: sig.action === 'LONG' ? K.grn : sig.action === 'SHORT' ? K.red : K.dim,
                              }}>
                                {sig.action}
                              </span>
                              <div className="fb-strategy-detail">
                                <div><strong>Triple-A:</strong> {sig.tripleAPhase}</div>
                                <div><strong>Grade:</strong> {sig.grade}</div>
                                <div style={{ color: K.dim, fontSize: 10, marginTop: 4 }}>{sig.reason}</div>
                              </div>
                            </div>
                          );
                        })()}
                      </div>

                      {/* Regime reason */}
                      <div style={{ fontSize: 11, color: K.dim, marginTop: 6 }}>
                        {multiStrategyResult.regime.reason}
                      </div>
                    </>
                  ) : (
                    <div style={{ color: K.dim, fontSize: 12, padding: 10 }}>
                      라이브 데이터 로드 후 레짐 분석이 표시됩니다.
                    </div>
                  )}

                  <div className="fb-opt-divider" />

                  {/* Multi-Strategy Backtest */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
                    <button
                      className="fb-opt-btn"
                      disabled={msRunning || fullCandles.length < 30}
                      onClick={async () => {
                        setMsRunning(true);
                        try {
                          await new Promise(r => setTimeout(r, 0));
                          const result = runMultiStrategyBacktest(fullCandles, DEFAULT_MS_CONFIG, asset);
                          setMsBacktest(result);
                        } finally {
                          setMsRunning(false);
                        }
                      }}
                    >
                      {msRunning ? 'Running...' : '\u25B6 Multi-Strategy Backtest'}
                    </button>
                    <span style={{ fontSize: 11, color: K.dim }}>
                      {fullCandles.length > 0 ? `${fullCandles.length}봉` : '데이터 없음'}
                    </span>
                  </div>

                  {msBacktest && (() => {
                    const strats: StrategyName[] = ['MEAN_REVERSION', 'TREND_FOLLOWING', 'SCALP_MOMENTUM'];
                    const bestPnL = Math.max(...strats.map(s => msBacktest.strategyStats[s].totalPnL));

                    return (
                      <>
                        {/* Strategy Comparison Table */}
                        <table className="fb-ms-backtest-table">
                          <thead>
                            <tr>
                              <th>Strategy</th>
                              <th>Trades</th>
                              <th>WR%</th>
                              <th>PF</th>
                              <th>Sharpe</th>
                              <th>P&L</th>
                              <th>MDD</th>
                            </tr>
                          </thead>
                          <tbody>
                            {strats.map(s => {
                              const st = msBacktest.strategyStats[s];
                              const isBest = st.totalPnL === bestPnL && st.trades > 0;
                              return (
                                <tr key={s} className={isBest ? 'best-row' : ''}>
                                  <td style={{ fontWeight: 600, fontSize: 10 }}>{STRATEGY_LABELS[s]}</td>
                                  <td>{st.trades}</td>
                                  <td style={{ color: st.winRate >= 50 ? K.grn : st.winRate > 0 ? K.red : K.dim }}>{st.winRate.toFixed(1)}</td>
                                  <td style={{ color: st.profitFactor >= 1 ? K.grn : K.red }}>{st.profitFactor === Infinity ? '\u221E' : st.profitFactor.toFixed(2)}</td>
                                  <td style={{ color: st.sharpe >= 0 ? K.grn : K.red }}>{st.sharpe.toFixed(2)}</td>
                                  <td style={{ color: st.totalPnL >= 0 ? K.grn : K.red, fontWeight: 600 }}>{st.totalPnL.toFixed(1)}p</td>
                                  <td style={{ color: K.red }}>{st.maxDD.toFixed(1)}</td>
                                </tr>
                              );
                            })}
                            {/* Auto-Select row */}
                            <tr style={{ borderTop: `2px solid ${K.brd}` }}>
                              <td style={{ fontWeight: 700, color: K.acc, fontSize: 10 }}>Auto-Select</td>
                              <td>{msBacktest.autoSelectStats.trades}</td>
                              <td style={{ color: msBacktest.autoSelectStats.winRate >= 50 ? K.grn : K.red }}>{msBacktest.autoSelectStats.winRate.toFixed(1)}</td>
                              <td style={{ color: msBacktest.autoSelectStats.profitFactor >= 1 ? K.grn : K.red }}>{msBacktest.autoSelectStats.profitFactor === Infinity ? '\u221E' : msBacktest.autoSelectStats.profitFactor.toFixed(2)}</td>
                              <td style={{ color: msBacktest.autoSelectStats.sharpe >= 0 ? K.grn : K.red }}>{msBacktest.autoSelectStats.sharpe.toFixed(2)}</td>
                              <td style={{ color: msBacktest.autoSelectStats.totalPnL >= 0 ? K.grn : K.red, fontWeight: 700 }}>{msBacktest.autoSelectStats.totalPnL.toFixed(1)}p</td>
                              <td style={{ color: K.red }}>{msBacktest.autoSelectStats.maxDD.toFixed(1)}</td>
                            </tr>
                          </tbody>
                        </table>

                        {/* Regime Distribution */}
                        <div style={{ fontSize: 11, fontWeight: 600, color: K.dim, marginTop: 10, marginBottom: 4 }}>Regime Distribution</div>
                        <div className="fb-regime-bar">
                          {msBacktest.regimeStats.filter(r => r.barsPct > 0).map(r => (
                            <div
                              key={r.regime}
                              className="fb-regime-bar-segment"
                              style={{ width: `${r.barsPct}%`, background: REGIME_COLORS[r.regime] }}
                              title={`${REGIME_LABELS[r.regime]}: ${r.barsPct.toFixed(1)}%`}
                            />
                          ))}
                        </div>
                        <table className="fb-ms-regime-table">
                          <thead>
                            <tr><th>Regime</th><th>Bars</th><th>%</th><th>Trades</th><th>WR%</th><th>P&L</th></tr>
                          </thead>
                          <tbody>
                            {msBacktest.regimeStats.filter(r => r.bars > 0).map(r => (
                              <tr key={r.regime}>
                                <td>
                                  <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: REGIME_COLORS[r.regime], marginRight: 4 }} />
                                  {REGIME_LABELS[r.regime]}
                                </td>
                                <td>{r.bars}</td>
                                <td>{r.barsPct.toFixed(1)}%</td>
                                <td>{r.trades}</td>
                                <td style={{ color: r.winRate >= 50 ? K.grn : r.trades > 0 ? K.red : K.dim }}>{r.trades > 0 ? `${r.winRate.toFixed(0)}%` : '-'}</td>
                                <td style={{ color: r.totalPnL >= 0 ? K.grn : K.red }}>{r.trades > 0 ? `${r.totalPnL.toFixed(1)}p` : '-'}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </>
                    );
                  })()}
                </div>
              )}
            </div>

            {/* ── Quick Reference ── */}
            <div className="fb-box">
              <Sec icon="&#x1F4D6;" title="Fabio 요약 참조" tag="RULES" tagC={K.dim} />
              <div className="fb-ref-grid">
                {[
                  { t: 'AMT 3단계', rules: ['Market State → Location → Aggression', '하나라도 빠지면 관망'] },
                  { t: 'Trend Model', rules: ['임펄스 VP → LVN 대기', '공격성 확인 후 진입', 'TP = 이전 Balance POC'] },
                  { t: 'Mean Rev Model', rules: ['브레이크아웃 실패 확인', '리클레임 → 풀백 → LVN', 'TP = Balance POC'] },
                  { t: '리스크 규칙', rules: ['0.25~0.5% / 트레이드', '3회 연속 손절 → 중단', '손절 확대 절대 금지'] },
                  { t: 'DO', rules: ['내러티브 설정', '작게 시작 → 컴파운딩', '1아이디어 = 1티켓'] },
                  { t: "DON'T", rules: ['조건 불완전 진입', '복수 트레이딩', '비활성 시간대 스캘핑'] },
                ].map((ref, i) => (
                  <div key={i} className="fb-ref-card">
                    <div className="fb-ref-title">{ref.t}</div>
                    {ref.rules.map((r, j) => (
                      <div key={j} className="fb-ref-rule">• {r}</div>
                    ))}
                  </div>
                ))}
              </div>
            </div>

          </div>
        </div>
      </div>

      {/* ── Footer ── */}
      <div className="fb-footer">
        ⚠ 교육/연구 목적. 투자 조언 아님. Fabio Valentini Playbook 기반 분석 도구. 모든 매매 결정의 책임은 본인에게 있습니다.
      </div>
    </div>
  );
}
