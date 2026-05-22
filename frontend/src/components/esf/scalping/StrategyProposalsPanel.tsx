/**
 * Strategy Proposals Panel — 4종목(ES/NQ/CL/GC) 실시간 진입 전략 카드.
 *
 * 각 카드:
 *   - Direction, Grade, Score, Regime
 *   - AMT Location (AT_LVN, AT_POC, ABOVE_VAH 등)
 *   - Mag MA, POC, VAH/VAL 자석/균형 가격
 *   - 진입 시나리오 (entry/stop/target/R:R/$ risk)
 *   - 권장 (WAIT / 시험적 micro / 진입 OK)
 *
 * 데이터 소스: /esf/analyze/{ticker} + /esf/volume-profile/{ticker}
 * 자동 갱신: 60초마다 4종 fetch (Promise.all 병렬)
 */
import { useEffect, useState, useCallback } from 'react';
import { fetchESFAnalysis, fetchESFVolumeProfile, type ESFAnalysis, type VolumeProfileData } from '@lib/api';

const TICKERS = [
  { ticker: 'ES=F', name: 'S&P 500',    flag: '🇺🇸', mult: 50,   microMult: 5,   microTicker: 'MES=F', decimals: 2 },
  { ticker: 'NQ=F', name: 'NASDAQ 100', flag: '💻', mult: 20,   microMult: 2,   microTicker: 'MNQ=F', decimals: 2 },
  { ticker: 'CL=F', name: 'WTI Crude',  flag: '🛢️', mult: 1000, microMult: 100, microTicker: 'MCL=F', decimals: 2 },
  { ticker: 'GC=F', name: 'Gold',       flag: '🥇', mult: 100,  microMult: 10,  microTicker: 'MGC=F', decimals: 1 },
] as const;

interface ProposalData {
  ticker: string;
  analysis: ESFAnalysis | null;
  vp: VolumeProfileData | null;
  error?: string;
}

interface Scenario {
  label: string;          // '🟢 LONG' / '🔴 SHORT' / '⏸ WAIT'
  emoji: 'long' | 'short' | 'wait';
  entry: number;
  stop: number;
  target: number;
  rr: number;
  riskDollarFull: number;
  riskDollarMicro: number;
  desc: string;
}

function assessLocation(current: number, poc: number, vah: number, val: number, lvnLevels: number[]): { code: string; hint: string } {
  for (const lvn of (lvnLevels || []).slice(0, 5)) {
    if (Math.abs(current - lvn) / current < 0.003) return { code: 'AT_LVN', hint: 'LVN — 빠른 통과 예상' };
  }
  if (Math.abs(current - poc) / current < 0.002) return { code: 'AT_POC', hint: '균형점 — mean-reversion 후보' };
  if (val > 0 && vah > 0 && val <= current && current <= vah) return { code: 'IN_VALUE', hint: 'Value Area 안 — 횡보' };
  if (vah > 0 && current > vah) return { code: 'ABOVE_VAH', hint: 'Imbalance Bullish — 추세/fade' };
  if (val > 0 && current < val) return { code: 'BELOW_VAL', hint: 'Imbalance Bearish — 추세/fade' };
  return { code: 'UNKNOWN', hint: '—' };
}

function buildScenarios(data: ProposalData, spec: typeof TICKERS[number]): Scenario[] {
  const an = data.analysis;
  const vp = data.vp;
  if (!an || !vp) return [];

  const current = an.entry_price || 0;
  const direction = an.direction;
  const indicators = an.indicators || {};
  const atr = indicators.atr || 0;
  const magMA = an.magnetic_ma?.best?.current_value || 0;
  const poc = vp.poc || 0;
  const vah = vp.vah || 0;
  const val = vp.val || 0;
  const lvn = vp.lvn_levels || [];

  if (current <= 0 || atr <= 0) return [];
  const loc = assessLocation(current, poc, vah, val, lvn);

  const mkScenario = (
    label: string, emoji: 'long' | 'short' | 'wait',
    entry: number, stop: number, target: number, desc: string,
  ): Scenario => {
    const riskPt = Math.abs(entry - stop);
    const rewardPt = Math.abs(target - entry);
    return {
      label, emoji, entry, stop, target,
      rr: riskPt > 0 ? rewardPt / riskPt : 0,
      riskDollarFull: riskPt * spec.mult,
      riskDollarMicro: riskPt * spec.microMult,
      desc,
    };
  };

  const scenarios: Scenario[] = [];

  if (loc.code === 'AT_LVN') {
    if (direction === 'LONG') {
      const stop = magMA > 0 && magMA < current ? magMA : current - atr;
      scenarios.push(mkScenario('🟢 LONG', 'long', current, Math.max(stop, current - atr), current + 2 * atr, 'LVN 통과 → 추세 추종'));
    } else if (direction === 'SHORT') {
      const stop = magMA > 0 && magMA > current ? magMA : current + atr;
      scenarios.push(mkScenario('🔴 SHORT', 'short', current, Math.min(stop, current + atr), current - 2 * atr, 'LVN 통과 → 추세 추종'));
    }
  } else if (loc.code === 'AT_POC') {
    if (magMA > 0 && magMA > current) {
      scenarios.push(mkScenario('🟢 LONG (Reversion)', 'long', current, current - atr, magMA, 'POC → Mag MA 회귀'));
    } else if (magMA > 0 && magMA < current) {
      scenarios.push(mkScenario('🔴 SHORT (Reversion)', 'short', current, current + atr, magMA, 'POC → Mag MA 회귀'));
    }
  } else if (loc.code === 'ABOVE_VAH') {
    scenarios.push(mkScenario('🟢 LONG (Trend)', 'long', current, vah, current + 3 * atr, 'VAH 위 → 추세 추종'));
    scenarios.push(mkScenario('🔴 SHORT (Fade)', 'short', current, current + atr, vah, 'VAH 거부 → POC 회귀'));
  } else if (loc.code === 'BELOW_VAL') {
    scenarios.push(mkScenario('🔴 SHORT (Trend)', 'short', current, val, current - 3 * atr, 'VAL 아래 → 추세 추종'));
    scenarios.push(mkScenario('🟢 LONG (Fade)', 'long', current, current - atr, val, 'VAL 거부 → POC 회귀'));
  } else if (loc.code === 'IN_VALUE') {
    scenarios.push({
      label: '⏸ WAIT', emoji: 'wait',
      entry: current, stop: val, target: vah,
      rr: 0, riskDollarFull: 0, riskDollarMicro: 0,
      desc: 'Value Area 내부 — VAH/VAL brake 대기',
    });
  }
  return scenarios;
}

function ProposalCard({ data, spec }: { data: ProposalData; spec: typeof TICKERS[number] }) {
  const an = data.analysis;
  const vp = data.vp;

  if (data.error) {
    return (
      <div style={{ ...cardStyle, borderColor: 'rgba(239,68,68,0.3)' }}>
        <div style={{ color: '#ff8a80' }}>{spec.flag} {spec.ticker} — {data.error}</div>
      </div>
    );
  }
  if (!an || !vp) {
    return (
      <div style={cardStyle}>
        <div style={{ color: '#888' }}>{spec.flag} {spec.ticker} — Loading...</div>
      </div>
    );
  }

  const current = an.entry_price || 0;
  const direction = an.direction;
  const grade = (an as any).grade || '?';
  const score = an.total_score || 0;
  const magMA = an.magnetic_ma?.best?.current_value || 0;
  const indicators = an.indicators || {};
  const atr = indicators.atr || 0;
  const regime = (an.regime as any)?.regime || '?';
  const trendScore = (an.regime as any)?.trend_score || 0;
  const poc = vp.poc || 0;
  const vah = vp.vah || 0;
  const val = vp.val || 0;
  const lvn = vp.lvn_levels || [];
  const loc = assessLocation(current, poc, vah, val, lvn);
  const scenarios = buildScenarios(data, spec);
  const dec = spec.decimals;

  // 권장
  const gradeOk = grade === 'A' || grade === 'B';
  const recommendation = gradeOk && direction !== 'NEUTRAL'
    ? { txt: `✅ 진입 OK (Grade ${grade})`, color: '#00e676' }
    : score >= 30
      ? { txt: `⚠ 시험적 Micro 진입 (Score ${score.toFixed(0)})`, color: '#fdd835' }
      : { txt: `❌ 관망 권장 (Score ${score.toFixed(0)})`, color: '#888' };

  // direction badge color
  const dirColor = direction === 'LONG' ? '#00e676' : direction === 'SHORT' ? '#ff1744' : '#95a5a6';

  // regime color
  const regimeColor: Record<string, string> = {
    BULL: '#00e676', BEAR: '#ff1744', NEUTRAL: '#95a5a6', CRISIS: '#ff8a80',
  };

  return (
    <div style={cardStyle}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 10 }}>
        <div>
          <span style={{ fontSize: 18, marginRight: 6 }}>{spec.flag}</span>
          <span style={{ fontSize: 14, fontWeight: 700, fontFamily: MONO }}>{spec.ticker}</span>
          <span style={{ fontSize: 11, color: '#888', marginLeft: 6 }}>{spec.name}</span>
        </div>
        <div style={{ fontSize: 18, fontWeight: 700, fontFamily: MONO, color: '#fff' }}>{current.toFixed(dec)}</div>
      </div>

      {/* Badges row */}
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 10 }}>
        <Badge label={direction} color={dirColor} />
        <Badge label={`Grade ${grade}`} color={gradeOk ? '#00e676' : '#888'} />
        <Badge label={`Score ${score.toFixed(0)}`} color={score >= 50 ? '#00e676' : score >= 30 ? '#fdd835' : '#888'} />
        <Badge label={regime} color={regimeColor[regime] || '#888'} subtle />
        <Badge label={loc.code} color="#3b82f6" subtle />
      </div>

      {/* 자석/균형 grid */}
      <div style={{
        display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4,
        fontSize: 10, fontFamily: MONO, color: '#bbb', marginBottom: 10,
        padding: 8, background: 'rgba(255,255,255,0.02)', borderRadius: 4,
      }}>
        <div>Mag MA: <b style={{ color: '#ff6b6b' }}>{magMA.toFixed(dec)}</b></div>
        <div>POC: <b style={{ color: '#3b82f6' }}>{poc.toFixed(dec)}</b></div>
        <div>VAH: <b>{vah.toFixed(dec)}</b></div>
        <div>VAL: <b>{val.toFixed(dec)}</b></div>
        <div>ATR: <b>{atr.toFixed(dec)}</b></div>
        <div>Vol: <b>{((atr / current) * 100).toFixed(2)}%</b></div>
      </div>

      {/* Location hint */}
      <div style={{ fontSize: 10, color: '#aaa', marginBottom: 8, fontStyle: 'italic' }}>
        💡 {loc.hint}
      </div>

      {/* Scenarios */}
      {scenarios.length === 0 ? (
        <div style={{ fontSize: 11, color: '#777', padding: 8, background: 'rgba(255,255,255,0.03)', borderRadius: 4 }}>
          ⏸ 명확한 진입 신호 없음
        </div>
      ) : (
        scenarios.map((s, i) => <ScenarioRow key={i} sc={s} spec={spec} />)
      )}

      {/* Recommendation */}
      <div style={{
        marginTop: 10, padding: 6, fontSize: 11, fontWeight: 600,
        color: recommendation.color, textAlign: 'center',
        borderTop: '1px solid rgba(255,255,255,0.06)',
      }}>
        {recommendation.txt}
      </div>
    </div>
  );
}

function ScenarioRow({ sc, spec }: { sc: Scenario; spec: typeof TICKERS[number] }) {
  const dec = spec.decimals;
  const bg = sc.emoji === 'long' ? 'rgba(0,230,118,0.06)' : sc.emoji === 'short' ? 'rgba(255,23,68,0.06)' : 'rgba(255,255,255,0.03)';
  const border = sc.emoji === 'long' ? 'rgba(0,230,118,0.25)' : sc.emoji === 'short' ? 'rgba(255,23,68,0.25)' : 'rgba(255,255,255,0.1)';
  return (
    <div style={{
      padding: 8, marginBottom: 6, background: bg,
      border: `1px solid ${border}`, borderRadius: 4,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, fontWeight: 700, marginBottom: 4 }}>
        <span>{sc.label}</span>
        <span style={{ color: '#888', fontWeight: 400 }}>{sc.desc}</span>
      </div>
      <div style={{
        display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 4,
        fontSize: 10, fontFamily: MONO, color: '#ddd',
      }}>
        <div>Entry: <b style={{ color: '#3b82f6' }}>{sc.entry.toFixed(dec)}</b></div>
        <div>Stop: <b style={{ color: '#ff1744' }}>{sc.stop.toFixed(dec)}</b></div>
        <div>TP: <b style={{ color: '#00e676' }}>{sc.target.toFixed(dec)}</b></div>
        <div>R:R: <b>{sc.rr.toFixed(2)}</b></div>
      </div>
      {sc.emoji !== 'wait' && (
        <div style={{ fontSize: 10, color: '#888', marginTop: 4, fontFamily: MONO }}>
          Full 1ct: <b style={{ color: '#ff8a80' }}>-${sc.riskDollarFull.toFixed(0)}</b> ·
          {' '}{spec.microTicker} 1ct: <b style={{ color: '#fdd835' }}>-${sc.riskDollarMicro.toFixed(0)}</b>
          {' '}({((sc.riskDollarMicro / 100000) * 100).toFixed(2)}% of $100k)
        </div>
      )}
    </div>
  );
}

function Badge({ label, color, subtle }: { label: string; color: string; subtle?: boolean }) {
  return (
    <span style={{
      padding: '2px 6px', borderRadius: 3,
      background: subtle ? 'rgba(255,255,255,0.05)' : `${color}22`,
      border: `1px solid ${color}55`,
      color: color,
      fontSize: 10, fontWeight: 700, fontFamily: MONO,
    }}>{label}</span>
  );
}

const MONO = "'IBM Plex Mono', monospace";
const cardStyle: React.CSSProperties = {
  padding: 12,
  background: 'rgba(255,255,255,0.02)',
  border: '1px solid rgba(255,255,255,0.08)',
  borderRadius: 8,
};

export function StrategyProposalsPanel() {
  const [data, setData] = useState<ProposalData[]>(TICKERS.map(t => ({ ticker: t.ticker, analysis: null, vp: null })));
  const [loading, setLoading] = useState(true);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    const results = await Promise.all(
      TICKERS.map(async (spec) => {
        try {
          const [an, vp] = await Promise.all([
            fetchESFAnalysis(spec.ticker).catch((e: Error) => { throw new Error(`analyze: ${e.message}`); }),
            fetchESFVolumeProfile(spec.ticker).catch((e: Error) => { throw new Error(`vp: ${e.message}`); }),
          ]);
          return { ticker: spec.ticker, analysis: an, vp };
        } catch (e: unknown) {
          return { ticker: spec.ticker, analysis: null, vp: null, error: e instanceof Error ? e.message : 'unknown' };
        }
      })
    );
    setData(results);
    setLastUpdate(new Date());
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchAll();
    const id = setInterval(fetchAll, 60_000);
    return () => clearInterval(id);
  }, [fetchAll]);

  return (
    <div style={{ padding: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 16, color: '#fff' }}>📋 4종목 실시간 진입 전략</h2>
          <p style={{ margin: '2px 0 0 0', fontSize: 11, color: '#888' }}>
            ESF 15m analyze + Volume Profile · $100k equity · 60s auto-refresh
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {lastUpdate && (
            <span style={{ fontSize: 10, color: '#666', fontFamily: MONO }}>
              {lastUpdate.toLocaleTimeString()}
            </span>
          )}
          <button
            onClick={fetchAll}
            disabled={loading}
            style={{
              padding: '4px 10px', fontSize: 11, fontWeight: 600,
              background: 'rgba(59,130,246,0.15)', color: '#60a5fa',
              border: '1px solid rgba(59,130,246,0.3)', borderRadius: 4,
              cursor: loading ? 'wait' : 'pointer',
            }}
          >
            {loading ? '...' : '↻ Refresh'}
          </button>
        </div>
      </div>

      <div style={{
        display: 'grid', gap: 12,
        gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))',
      }}>
        {TICKERS.map((spec) => {
          const d = data.find(x => x.ticker === spec.ticker)!;
          return <ProposalCard key={spec.ticker} data={d} spec={spec} />;
        })}
      </div>

      <div style={{
        marginTop: 16, padding: 10, fontSize: 10, color: '#888',
        background: 'rgba(255,255,255,0.02)', borderRadius: 4,
        border: '1px solid rgba(255,255,255,0.05)',
      }}>
        <b style={{ color: '#aaa' }}>📖 사용법:</b><br />
        - <b>Grade A/B + direction 명확</b> → 풀 진입 검토<br />
        - <b>Grade C + Score 30+</b> → 시험적 Micro (1-2 ct)<br />
        - <b>Grade D 또는 NEUTRAL</b> → 관망<br />
        - 모든 stop은 즉시 limit order로 설정. mental stop 금지.<br />
        - 60초마다 자동 갱신. backend Score는 매 15분 봉 종료마다 업데이트.
      </div>
    </div>
  );
}
