import { useState, useEffect, useCallback } from 'react';
import { Play, Square, RotateCcw, Zap, ChevronDown, Pause, Calendar, FastForward, Save, Check } from 'lucide-react';
import type { MarketId, StrategyMode, SimControllerStatus, ReplayProgress } from '../../lib/api';
import {
    fetchSimControllerStatus, simStart, simStop, simReset,
    replayPause, replayResume, replaySetSpeed, getMarketConfig,
    saveReplayResult,
} from '../../lib/api';
import { useSSE } from '../../hooks/useSSE';
import { DateRangePicker } from '../common/DateRangePicker';
import './SimControlBar.css';

const STRATEGY_LABELS: Record<string, { label: string; desc: string }> = {
    // 그룹1
    multi: { label: 'Stock Strategy 통합매매엔진', desc: '시장 추세 자동 감지 → 동적 전략 배분' },
    // 그룹2 (regime 모드 — 레짐 잠금)
    regime_strong_bull: { label: '🚀 강한상승 | 공격적 추세추종', desc: '모멘텀 40% + 돌파 20% + 평균회귀 20%' },
    regime_bull:        { label: '📈 상승 | 추세추종',             desc: '평균회귀 35% + 모멘텀 30% + 헤지 15%' },
    regime_neutral:     { label: '↔️ 횡보 | 평균회귀',            desc: '평균회귀 60% + 헤지 25% + 차익 10%' },
    regime_range_bound: { label: '📦 박스권 | 박스권 회귀',        desc: '평균회귀 55% + 차익 20% + 헤지 20%' },
    regime_bear:        { label: '🛡️ 하락 | 하락방어',            desc: '인버스 헤지 55% + 평균회귀 25% + 변동성 15%' },
    regime_crisis:      { label: '🚨 위기 | 자본 보존',            desc: '인버스 헤지 85% + 평균회귀 15%' },
    // 그룹3 (단일 전략)
    momentum:       { label: '모멘텀 스윙 엔진',         desc: '6-Phase 파이프라인 | ADX + MACD + MA 정렬' },
    smc:            { label: 'Smart Money Concept 엔진', desc: 'BOS/CHoCH + Order Block + FVG | 4-Layer 스코어링' },
    mean_reversion: { label: '평균회귀 알파 엔진',        desc: '과매도 반등 포착 | BB + RSI 역추세 진입' },
    arbitrage:      { label: '통계차익 ARB 엔진',         desc: 'Z-Score 페어트레이딩 | 공적분 기반' },
};

/** 전략 선택기에 표시할 모드 */
const SELECTABLE_STRATEGIES: StrategyMode[] = [
    'multi',
    'regime_strong_bull', 'regime_bull', 'regime_neutral',
    'regime_range_bound', 'regime_bear', 'regime_crisis',
    'momentum', 'smc', 'mean_reversion', 'arbitrage',
];

const REGIME_MODES = [
    { key: 'regime_strong_bull', label: '🚀 강한상승 | 공격적 추세추종',
        weights: [
            { name: '모멘텀 스윙', pct: 40 }, { name: '돌파 리테스트', pct: 20 },
            { name: '평균회귀', pct: 20 }, { name: 'Smart Money Concept', pct: 10 }, { name: '인버스 헤지', pct: 10 },
        ] },
    { key: 'regime_bull', label: '📈 상승 | 추세추종',
        weights: [
            { name: '평균회귀', pct: 35 }, { name: '모멘텀 스윙', pct: 30 },
            { name: '인버스 헤지', pct: 15 }, { name: 'Smart Money Concept', pct: 15 }, { name: '돌파 리테스트', pct: 5 },
        ] },
    { key: 'regime_neutral', label: '↔️ 횡보 | 평균회귀',
        weights: [
            { name: '평균회귀', pct: 60 }, { name: '인버스 헤지', pct: 25 },
            { name: '통계차익', pct: 10 }, { name: 'Smart Money Concept', pct: 5 },
        ] },
    { key: 'regime_range_bound', label: '📦 박스권 | 박스권 회귀',
        weights: [
            { name: '평균회귀', pct: 55 }, { name: '통계차익', pct: 20 },
            { name: '인버스 헤지', pct: 20 }, { name: 'Smart Money Concept', pct: 5 },
        ] },
    { key: 'regime_bear', label: '🛡️ 하락 | 하락방어',
        weights: [
            { name: '인버스 헤지', pct: 55 }, { name: '평균회귀', pct: 25 },
            { name: '변동성 프리미엄', pct: 15 }, { name: 'Smart Money Concept', pct: 5 },
        ] },
    { key: 'regime_crisis', label: '🚨 위기 | 자본 보존',
        weights: [
            { name: '인버스 헤지', pct: 85 }, { name: '평균회귀', pct: 15 },
        ] },
];

const SPEED_OPTIONS = [
    { value: 0.5, label: '0.5x' },
    { value: 1, label: '1x' },
    { value: 2, label: '2x' },
    { value: 5, label: '5x' },
    { value: 10, label: '10x' },
    { value: 0, label: 'MAX' },
];

type SimMode = 'realtime' | 'replay';

interface Props {
    market: MarketId;
}

/** YYYYMMDD → YYYY-MM-DD */
function toDateInput(yyyymmdd: string): string {
    if (yyyymmdd.length === 8) {
        return `${yyyymmdd.slice(0, 4)}-${yyyymmdd.slice(4, 6)}-${yyyymmdd.slice(6)}`;
    }
    return yyyymmdd;
}

/** YYYY-MM-DD → YYYYMMDD */
function toApiDate(dateInput: string): string {
    return dateInput.replace(/-/g, '');
}

/** 오늘 기준 N년 전 날짜 (YYYY-MM-DD) */
function yearsAgo(n: number): string {
    const d = new Date();
    d.setFullYear(d.getFullYear() - n);
    return d.toISOString().slice(0, 10);
}

/** 오늘 날짜 (YYYY-MM-DD) */
function today(): string {
    return new Date().toISOString().slice(0, 10);
}

export function SimControlBar({ market }: Props) {
    const [status, setStatus] = useState<SimControllerStatus | null>(null);
    const [loading, setLoading] = useState(false);
    const [actionLabel, setActionLabel] = useState('');
    const [selectedStrategy, setSelectedStrategy] = useState<StrategyMode>('multi');
    const [showStrategyDropdown, setShowStrategyDropdown] = useState(false);

    // Replay 상태
    const [simMode, setSimMode] = useState<SimMode>('realtime');
    const [startDate, setStartDate] = useState(yearsAgo(1));
    const [endDate, setEndDate] = useState(today());
    const [replaySpeed, setReplaySpeed] = useState(5);

    // SSE 리플레이 진행 상태
    const replayProgress = useSSE<ReplayProgress>(`${market}:replay_progress`);

    const refreshStatus = useCallback(async () => {
        try {
            const s = await fetchSimControllerStatus();
            setStatus(s);
            const marketStatus = s.markets[market];
            if (marketStatus?.is_running) {
                setSelectedStrategy(marketStatus.strategy_mode);
            }
            // 리플레이 활성 시 모드 동기화 (엔진 실행 중일 때만)
            if (marketStatus?.is_running && (marketStatus?.replay?.active || marketStatus?.replay?.completed)) {
                setSimMode('replay');
            }
        } catch {
            // API not available yet
        }
    }, [market]);

    useEffect(() => {
        refreshStatus();
        const interval = setInterval(refreshStatus, 5000);
        return () => clearInterval(interval);
    }, [refreshStatus]);

    const marketStatus = status?.markets[market];
    const isRunning = marketStatus?.is_running ?? false;
    const currentStrategy = marketStatus?.strategy_mode ?? selectedStrategy;
    const mktConfig = getMarketConfig(market);

    // 리플레이 상태 판별
    const isReplayActive = marketStatus?.replay?.active ?? false;
    const isReplayPaused = replayProgress?.paused ?? marketStatus?.replay?.paused ?? false;
    const isReplayCompleted = replayProgress?.completed ?? marketStatus?.replay?.completed ?? false;

    const handleAction = async (action: 'start' | 'stop' | 'reset') => {
        setLoading(true);
        const labels = { start: '시작 중...', stop: '정지 중...', reset: '리셋 중...' };
        setActionLabel(labels[action]);
        try {
            if (action === 'start') {
                if (simMode === 'replay') {
                    await simStart(market, selectedStrategy, {
                        startDate: toApiDate(startDate),
                        endDate: toApiDate(endDate),
                        replaySpeed: replaySpeed,
                    });
                } else {
                    await simStart(market, selectedStrategy);
                }
            } else if (action === 'stop') {
                await simStop(market);
            } else {
                await simReset(market, selectedStrategy);
            }
            await new Promise(r => setTimeout(r, 800));
            await refreshStatus();
        } catch (err) {
            console.error(`Sim ${action} error:`, err);
        } finally {
            setLoading(false);
            setActionLabel('');
        }
    };

    const handleReplayPauseResume = async () => {
        try {
            if (isReplayPaused) {
                await replayResume(market);
            } else {
                await replayPause(market);
            }
        } catch (err) {
            console.error('Replay pause/resume error:', err);
        }
    };

    const handleSpeedChange = async (speed: number) => {
        setReplaySpeed(speed);
        if (isReplayActive) {
            try {
                await replaySetSpeed(market, speed);
            } catch (err) {
                console.error('Speed change error:', err);
            }
        }
    };

    // 결과 저장 상태
    const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved'>('idle');

    const handleSaveResult = async () => {
        setSaveState('saving');
        try {
            await saveReplayResult(market);
            setSaveState('saved');
            setTimeout(() => setSaveState('idle'), 3000);
        } catch (err) {
            console.error('Save replay result error:', err);
            setSaveState('idle');
        }
    };

    const handleStrategySelect = (strategy: StrategyMode) => {
        setSelectedStrategy(strategy);
        setShowStrategyDropdown(false);
    };

    // 현재 리플레이 날짜 포맷
    const currentReplayDate = replayProgress?.current_date
        ? toDateInput(replayProgress.current_date)
        : marketStatus?.replay?.current_date
            ? toDateInput(marketStatus.replay.current_date)
            : '';

    const progressPct = replayProgress?.progress_pct ?? marketStatus?.replay?.progress_pct ?? 0;
    const dayIndex = replayProgress?.day_index ?? 0;
    const totalDays = replayProgress?.total_days ?? marketStatus?.replay?.total_days ?? 0;

    return (
        <div className="sim-control-bar glass-panel">
            <div className="sim-control-left">
                <div className="sim-control-title">
                    <Zap size={14} className="sim-icon" />
                    <span>시뮬레이션</span>
                </div>

                <span className="status-divider" />

                {/* 모드 토글 */}
                <div className="sim-mode-toggle">
                    <button
                        className={`mode-toggle-btn ${simMode === 'realtime' ? 'active' : ''}`}
                        onClick={() => !isRunning && setSimMode('realtime')}
                        disabled={isRunning}
                    >
                        실시간
                    </button>
                    <button
                        className={`mode-toggle-btn ${simMode === 'replay' ? 'active' : ''}`}
                        onClick={() => !isRunning && setSimMode('replay')}
                        disabled={isRunning}
                    >
                        <Calendar size={11} />
                        리플레이
                    </button>
                </div>

                <span className="status-divider" />

                {/* 엔진 상태 */}
                <div className={`sim-engine-status ${isRunning ? 'running' : 'stopped'}`}>
                    <span className="sim-status-dot" />
                    <span>
                        {isRunning
                            ? (isReplayActive ? '리플레이 중' : isReplayCompleted ? '완료' : '실행 중')
                            : '정지'}
                    </span>
                </div>

                <span className="status-divider" />

                {/* 전략 선택 */}
                <div className="strategy-selector-wrap">
                    <button
                        className="strategy-selector-btn"
                        onClick={() => setShowStrategyDropdown(!showStrategyDropdown)}
                        disabled={loading || isRunning}
                    >
                        <span className="strategy-current">
                            {(STRATEGY_LABELS[isRunning ? currentStrategy : selectedStrategy] ?? { label: currentStrategy }).label}
                        </span>
                        <ChevronDown size={12} />
                    </button>
                    {showStrategyDropdown && (
                        <div className="strategy-dropdown">
                            {/* 그룹 1: 통합 */}
                            <div className="strategy-group-header">통합 자동 적응형</div>
                            <button
                                className={`strategy-option multi-option ${(isRunning ? currentStrategy : selectedStrategy) === 'multi' ? 'active' : ''}`}
                                onClick={() => handleStrategySelect('multi' as StrategyMode)}
                            >
                                <span className="strategy-name">{STRATEGY_LABELS['multi'].label}</span>
                                <span className="strategy-desc">{STRATEGY_LABELS['multi'].desc}</span>
                            </button>

                            {/* 그룹 2: 추세별 고정 */}
                            <div className="strategy-group-header">추세별 고정 모드</div>
                            {REGIME_MODES.map(({ key, label, weights }) => (
                                <button
                                    key={key}
                                    className={`strategy-option regime-option ${(isRunning ? currentStrategy : selectedStrategy) === key ? 'active' : ''}`}
                                    onClick={() => handleStrategySelect(key as StrategyMode)}
                                >
                                    <span className="strategy-name">{label}</span>
                                    <div className="strategy-weight-bars">
                                        {weights.map(({ name, pct }) => (
                                            <div key={name} className="weight-bar-row">
                                                <span className="weight-name">{name}</span>
                                                <div
                                                    className="weight-bar"
                                                    style={{ width: `${Math.round(pct * 0.8)}px` }}
                                                />
                                                <span className="weight-pct">{pct}%</span>
                                            </div>
                                        ))}
                                    </div>
                                </button>
                            ))}

                            {/* 그룹 3: 단일 전략 */}
                            <div className="strategy-group-header">단일 전략 (테스트용)</div>
                            {(['momentum', 'smc', 'mean_reversion', 'arbitrage'] as StrategyMode[]).map(s => (
                                <button
                                    key={s}
                                    className={`strategy-option ${(isRunning ? currentStrategy : selectedStrategy) === s ? 'active' : ''}`}
                                    onClick={() => handleStrategySelect(s)}
                                >
                                    <span className="strategy-name">{STRATEGY_LABELS[s].label}</span>
                                    <span className="strategy-desc">{STRATEGY_LABELS[s].desc}</span>
                                </button>
                            ))}
                        </div>
                    )}
                </div>

                {/* 실행 중 메트릭 */}
                {isRunning && marketStatus && (
                    <>
                        <span className="status-divider" />
                        <div className="sim-metric">
                            <span className="sim-metric-label">자산</span>
                            <span className="sim-metric-value">
                                {mktConfig.currencySymbol}{marketStatus.total_equity.toLocaleString()}
                            </span>
                        </div>
                        <span className="status-divider" />
                        <div className="sim-metric">
                            <span className="sim-metric-label">포지션</span>
                            <span className="sim-metric-value">{marketStatus.position_count}</span>
                        </div>
                    </>
                )}
            </div>

            {/* 리플레이 날짜/속도 설정 (미실행 + 리플레이 모드) */}
            {simMode === 'replay' && !isRunning && (
                <div className="replay-config">
                    <DateRangePicker
                        startDate={startDate}
                        endDate={endDate}
                        onChange={(s, e) => { setStartDate(s); setEndDate(e); }}
                        maxDate={today()}
                        disabled={isRunning}
                        presets={[
                            { label: '1Y', years: 1 },
                            { label: '2Y', years: 2 },
                            { label: '3Y', years: 3 },
                        ]}
                    />
                    <div className="replay-speed-wrap">
                        <FastForward size={12} />
                        <select
                            className="replay-speed-select"
                            value={replaySpeed}
                            onChange={e => setReplaySpeed(Number(e.target.value))}
                        >
                            {SPEED_OPTIONS.map(o => (
                                <option key={o.value} value={o.value}>{o.label}</option>
                            ))}
                        </select>
                    </div>
                </div>
            )}

            {/* 리플레이 진행률 (실행 중) */}
            {simMode === 'replay' && isRunning && (isReplayActive || isReplayCompleted) && (
                <div className="replay-progress-wrap">
                    <span className="replay-current-date">{currentReplayDate}</span>
                    <div className="replay-progress-bar">
                        <div
                            className="replay-progress-fill"
                            style={{ width: `${progressPct}%` }}
                        />
                    </div>
                    <span className="replay-progress-text">
                        {dayIndex}/{totalDays}일 ({Math.round(progressPct)}%)
                    </span>
                    <div className="replay-speed-wrap">
                        <FastForward size={12} />
                        <select
                            className="replay-speed-select"
                            value={replaySpeed}
                            onChange={e => handleSpeedChange(Number(e.target.value))}
                        >
                            {SPEED_OPTIONS.map(o => (
                                <option key={o.value} value={o.value}>{o.label}</option>
                            ))}
                        </select>
                    </div>
                </div>
            )}

            {/* 리플레이 완료 시 결과 저장 */}
            {simMode === 'replay' && isReplayCompleted && (
                <div className="replay-result-actions">
                    <button
                        className={`sim-btn ${saveState === 'saved' ? 'sim-btn-saved' : 'sim-btn-start'}`}
                        onClick={handleSaveResult}
                        disabled={saveState !== 'idle'}
                    >
                        {saveState === 'saved' ? <Check size={14} /> : <Save size={14} />}
                        <span>
                            {saveState === 'saving' ? '저장 중...' : saveState === 'saved' ? '저장됨' : '결과 저장'}
                        </span>
                    </button>
                </div>
            )}

            <div className="sim-control-right">
                {actionLabel && (
                    <span className="sim-action-label">{actionLabel}</span>
                )}

                {!isRunning ? (
                    <button
                        className="sim-btn sim-btn-start"
                        onClick={() => handleAction('start')}
                        disabled={loading}
                    >
                        <Play size={14} />
                        <span>{simMode === 'replay' ? '리플레이 시작' : '시작'}</span>
                    </button>
                ) : (
                    <>
                        {/* 리플레이 일시정지/재개 */}
                        {isReplayActive && (
                            <button
                                className={`sim-btn ${isReplayPaused ? 'sim-btn-start' : 'sim-btn-reset'}`}
                                onClick={handleReplayPauseResume}
                                disabled={loading}
                                title={isReplayPaused ? '재개' : '일시정지'}
                            >
                                {isReplayPaused ? <Play size={14} /> : <Pause size={14} />}
                                <span>{isReplayPaused ? '재개' : '일시정지'}</span>
                            </button>
                        )}
                        {!isReplayActive && (
                            <button
                                className="sim-btn sim-btn-reset"
                                onClick={() => handleAction('reset')}
                                disabled={loading}
                                title="리셋 (포트폴리오 초기화 후 재시작)"
                            >
                                <RotateCcw size={14} />
                                <span>리셋</span>
                            </button>
                        )}
                        <button
                            className="sim-btn sim-btn-stop"
                            onClick={() => handleAction('stop')}
                            disabled={loading}
                        >
                            <Square size={14} />
                            <span>정지</span>
                        </button>
                    </>
                )}
            </div>
        </div>
    );
}
