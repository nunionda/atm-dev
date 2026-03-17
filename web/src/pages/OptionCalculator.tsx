import { useState, useEffect, useRef, useCallback } from 'react';
import { usePolling } from '../hooks/usePolling';
import { PollingControl } from '../components/PollingControl';
import { fetchQuote, type QuoteResponse } from '../lib/api';
import './OptionCalculator.css';

// ── Preset → 티커 매핑 ──────────────────────────────────────────────────
// KOSPI200: @KS200/@KS200F → Naver Finance (routes.py 자동 라우팅)
// US: ^GSPC/ES=F, ^NDX/NQ=F → Yahoo Finance
const PRESET_TICKERS: Record<string, { spot: string; futures: string; label: string }> = {
  kospi200w: { spot: '@KS200',  futures: '@KS200F', label: 'KOSPI200 위클리' },
  kospi200m: { spot: '@KS200',  futures: '@KS200F', label: 'KOSPI200 먼슬리' },
  spx:       { spot: '^GSPC',   futures: 'ES=F',    label: 'S&P500 (SPX)' },
  es_w1:     { spot: '^GSPC',   futures: 'ES=F',    label: 'Mini S&P W1 (ES)' },
  ndx:       { spot: '^NDX',    futures: 'NQ=F',    label: '나스닥100 (NDX)' },
  xsp:       { spot: '^GSPC',   futures: 'ES=F',    label: '미니 S&P (XSP)' },
};

export function OptionCalculator() {
  const [preset, setPreset] = useState('spx');
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const iframeReady = useRef(false);

  const tickers = PRESET_TICKERS[preset];
  const hasSeparateFutures = tickers.spot !== tickers.futures;

  // 현물 폴링
  const spotFetch = useCallback(() => fetchQuote(tickers.spot), [tickers.spot]);
  const spotPoll = usePolling<QuoteResponse>(spotFetch, { interval: 30000, enabled: false });

  // 선물 폴링 (현물과 다른 티커인 경우만)
  const futFetch = useCallback(
    () => hasSeparateFutures ? fetchQuote(tickers.futures) : Promise.resolve(null as unknown as QuoteResponse),
    [tickers.futures, hasSeparateFutures],
  );
  const futPoll = usePolling<QuoteResponse>(futFetch, {
    interval: 30000,
    enabled: false,
  });

  // 폴링 연동: 현물 on/off 시 선물도 같이
  const handlePollingToggle = useCallback((v: boolean) => {
    spotPoll.setEnabled(v);
    if (hasSeparateFutures) futPoll.setEnabled(v);
  }, [spotPoll, futPoll, hasSeparateFutures]);

  const handleIntervalChange = useCallback((ms: number) => {
    spotPoll.setInterval(ms);
    if (hasSeparateFutures) futPoll.setInterval(ms);
  }, [spotPoll, futPoll, hasSeparateFutures]);

  const handleRefresh = useCallback(() => {
    spotPoll.fetchNow();
    if (hasSeparateFutures) futPoll.fetchNow();
  }, [spotPoll, futPoll, hasSeparateFutures]);

  // 가격 추출
  const spotPrice = spotPoll.data?.latest?.price ?? null;
  const futPrice = hasSeparateFutures
    ? (futPoll.data?.latest?.price ?? null)
    : spotPrice;
  const spotChange = spotPoll.data?.latest?.change_pct ?? null;

  // iframe 로드 완료 감지
  const handleIframeLoad = useCallback(() => {
    iframeReady.current = true;
  }, []);

  // iframe에 message 전달 유틸
  const postToIframe = useCallback((msg: Record<string, unknown>) => {
    const iframe = iframeRef.current;
    if (!iframe?.contentWindow || !iframeReady.current) return;
    iframe.contentWindow.postMessage(msg, '*');
  }, []);

  // 프리셋 변경 → iframe 전달
  useEffect(() => {
    postToIframe({ type: 'changePreset', preset });
  }, [preset, postToIframe]);

  // 리셋 → iframe 전달
  const handleReset = useCallback(() => {
    postToIframe({ type: 'resetAll' });
  }, [postToIframe]);

  // 가격 업데이트 → iframe 전달
  // XSP = SPX/10 이므로 live 가격(^GSPC) 수신 시 ÷10 변환
  useEffect(() => {
    if (spotPrice === null) return;
    const divisor = preset === 'xsp' ? 10 : 1;
    postToIframe({
      type: 'updatePrices',
      spot: spotPrice / divisor,
      futures: (futPrice ?? spotPrice) / divisor,
      preset,
    });
  }, [spotPrice, futPrice, preset, postToIframe]);

  // 프리셋 변경 시 기존 선물 폴링도 동기화
  useEffect(() => {
    if (spotPoll.enabled && hasSeparateFutures) {
      futPoll.setEnabled(true);
    } else if (!hasSeparateFutures) {
      futPoll.setEnabled(false);
    }
  }, [preset, hasSeparateFutures]);

  // 현물/선물 가격 포맷
  const fmtPrice = (v: number | null, d = 2) =>
    v === null ? '—' : v.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });

  return (
    <div className="option-calc-page container">
      {/* ── Page Header ── */}
      <div className="option-calc-header">
        <div>
          <h1 className="page-title">Options</h1>
          <p className="page-subtitle">KOSPI200 / SPX 옵션 가격 계산 및 Greeks 분석</p>
        </div>
        <div className="option-calc-header-controls">
          <select
            value={preset}
            onChange={e => {
              const v = e.target.value;
              if (v === 'custom') {
                postToIframe({ type: 'openCustomModal' });
                e.target.value = preset;
              } else {
                setPreset(v);
              }
            }}
            className="option-calc-preset-select"
          >
            {Object.entries(PRESET_TICKERS).map(([k, v]) => (
              <option key={k} value={k}>{v.label}</option>
            ))}
            <option value="custom">사용자 정의</option>
          </select>

          <button
            className="option-calc-reset-btn"
            onClick={handleReset}
            title="리셋"
          >
            ↻
          </button>

          {spotPrice !== null && (
            <div className="option-calc-prices">
              <span className="option-calc-price-tag">현물</span>
              <span className="option-calc-price-val">{fmtPrice(spotPrice)}</span>
              {spotChange !== null && (
                <span className={`option-calc-change ${spotChange >= 0 ? 'up' : 'down'}`}>
                  {spotChange >= 0 ? '+' : ''}{spotChange.toFixed(2)}%
                </span>
              )}
              {hasSeparateFutures && futPrice !== null && (
                <>
                  <span className="option-calc-price-divider">│</span>
                  <span className="option-calc-price-tag">선물</span>
                  <span className="option-calc-price-val">{fmtPrice(futPrice)}</span>
                </>
              )}
            </div>
          )}

          <PollingControl
            enabled={spotPoll.enabled}
            onToggle={handlePollingToggle}
            interval={spotPoll.interval}
            onIntervalChange={handleIntervalChange}
            status={spotPoll.status}
            lastUpdated={spotPoll.lastUpdated}
            consecutiveErrors={spotPoll.consecutiveErrors}
            onRefresh={handleRefresh}
            compact
          />
        </div>
      </div>

      {/* ── Calculator iframe ── */}
      <iframe
        ref={iframeRef}
        src="/option-calculator.html"
        className="option-calc-iframe"
        title="옵션 계산기"
        onLoad={handleIframeLoad}
      />
    </div>
  );
}
