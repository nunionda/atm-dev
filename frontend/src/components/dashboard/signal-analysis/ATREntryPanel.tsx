/**
 * ATREntryPanel — extracted from SignalAnalysis.
 *
 * Phase D3 분할: dashboard/SignalAnalysis.tsx → dashboard/signal-analysis/ATREntryPanel.tsx
 */

import { Target, ChevronDown } from 'lucide-react';
import type { ATREntryCalc } from '@lib/futuresEngine';
import { fmtIndicator } from './_helpers';

export function ATREntryPanel({ calc, fmtPrice }: { calc: ATREntryCalc; fmtPrice: (v: number) => string }) {
    const [expanded, setExpanded] = useState(false);
    const dirClass = calc.direction === 'LONG' ? 'atr-long' : calc.direction === 'SHORT' ? 'atr-short' : 'atr-wait';

    return (
        <div className={`sa-entry-section glass-panel atr-calc-card ${expanded ? 'expanded' : ''}`} onClick={() => setExpanded(e => !e)}>
            <h3 className="sa-section-title">
                <Target size={16} />
                ATR Entry Calculator
                <ChevronDown size={14} className={`atr-calc-chevron ${expanded ? 'open' : ''}`} />
            </h3>

            {/* ATR 현황 + 방향 배지 (항상 표시) */}
            <div className="atr-calc-header">
                <div className="atr-calc-atr-info">
                    <span className="ft-num">ATR (14): {fmtIndicator(calc.atr)}</span>
                    <span className="ft-sub">({calc.atrPct.toFixed(2)}%)</span>
                </div>
                <span className={`atr-direction-badge ${dirClass}`}>
                    {calc.direction === 'LONG' ? '▲ LONG' : calc.direction === 'SHORT' ? '▼ SHORT' : '◆ WAIT'}
                </span>
            </div>

            {/* 판단 근거 (항상 표시) */}
            <div className="ft-signals">
                {calc.reasons.map((r, i) => (
                    <span key={i} className="ft-signal-chip">{r}</span>
                ))}
            </div>

            {/* 상세 내용 (확장 시에만 표시) */}
            <div className="atr-calc-details" onClick={e => e.stopPropagation()}>
                {/* 진입 조건 */}
                <div className="atr-calc-group">
                    <div className="atr-calc-group-title">진입 조건</div>
                    <div className="atr-calc-row">
                        <span className="atr-calc-label">브레이크아웃</span>
                        <span className={`atr-calc-value ${calc.breakoutValid ? 'atr-long' : 'atr-muted'}`}>
                            {calc.breakoutValid ? '✓ 유효' : '✗ 미충족'}
                            <span className="ft-sub"> ({fmtIndicator(calc.breakoutDelta)} {calc.breakoutValid ? '>' : '≤'} {fmtIndicator(calc.breakoutThreshold)})</span>
                        </span>
                    </div>
                </div>

                {/* 추세추종 진입가 */}
                <div className="atr-calc-group">
                    <div className="atr-calc-group-title">추세추종 진입가</div>
                    <div className="atr-calc-row">
                        <span className="atr-calc-label atr-long">Long 진입</span>
                        <span className="atr-calc-value">{fmtPrice(calc.trendLongEntry)} <span className="ft-sub">(1.5x ATR)</span></span>
                    </div>
                    <div className="atr-calc-row">
                        <span className="atr-calc-label atr-long">Long 강력</span>
                        <span className="atr-calc-value">{fmtPrice(calc.trendLongStrong)} <span className="ft-sub">(2.0x ATR)</span></span>
                    </div>
                    <div className="atr-calc-row">
                        <span className="atr-calc-label atr-short">Short 진입</span>
                        <span className="atr-calc-value">{fmtPrice(calc.trendShortEntry)} <span className="ft-sub">(1.5x ATR)</span></span>
                    </div>
                    <div className="atr-calc-row">
                        <span className="atr-calc-label atr-short">Short 강력</span>
                        <span className="atr-calc-value">{fmtPrice(calc.trendShortStrong)} <span className="ft-sub">(2.0x ATR)</span></span>
                    </div>
                </div>

                {/* ATR 밴드 */}
                <div className="atr-calc-group">
                    <div className="atr-calc-group-title">ATR 밴드 (2x)</div>
                    <div className="atr-calc-row">
                        <span className="atr-calc-label">상단</span>
                        <span className="atr-calc-value">{fmtPrice(calc.upperBand)}</span>
                    </div>
                    <div className="atr-calc-row">
                        <span className="atr-calc-label">하단</span>
                        <span className="atr-calc-value">{fmtPrice(calc.lowerBand)}</span>
                    </div>
                </div>

                {/* 트레일링 스톱 */}
                <div className="atr-calc-group">
                    <div className="atr-calc-group-title">손절 (트레일링 스톱)</div>
                    <div className="atr-calc-row">
                        <span className="atr-calc-label atr-short">Long SL</span>
                        <span className="atr-calc-value">{fmtPrice(calc.longStop)} <span className="ft-sub">(1.5x)</span></span>
                    </div>
                    <div className="atr-calc-row">
                        <span className="atr-calc-label atr-short">Long SL (Wide)</span>
                        <span className="atr-calc-value">{fmtPrice(calc.longStopWide)} <span className="ft-sub">(2.0x)</span></span>
                    </div>
                    <div className="atr-calc-row">
                        <span className="atr-calc-label atr-long">Short SL</span>
                        <span className="atr-calc-value">{fmtPrice(calc.shortStop)} <span className="ft-sub">(1.5x)</span></span>
                    </div>
                    <div className="atr-calc-row">
                        <span className="atr-calc-label atr-long">Short SL (Wide)</span>
                        <span className="atr-calc-value">{fmtPrice(calc.shortStopWide)} <span className="ft-sub">(2.0x)</span></span>
                    </div>
                </div>

                {/* 샹들리에 청산 */}
                <div className="atr-calc-group">
                    <div className="atr-calc-group-title">샹들리에 청산 (3x ATR)</div>
                    <div className="atr-calc-row">
                        <span className="atr-calc-label atr-long">Long Exit</span>
                        <span className="atr-calc-value">
                            {fmtPrice(calc.chandelierLongExit)}
                            <span className="ft-sub"> (최고 {fmtPrice(calc.chandelierHighest)} - 3ATR)</span>
                        </span>
                    </div>
                    <div className="atr-calc-row">
                        <span className="atr-calc-label atr-short">Short Exit</span>
                        <span className="atr-calc-value">
                            {fmtPrice(calc.chandelierShortExit)}
                            <span className="ft-sub"> (최저 {fmtPrice(calc.chandelierLowest)} + 3ATR)</span>
                        </span>
                    </div>
                </div>

                {/* 동적 ATR 배수 (ADX 기반) */}
                <div className="atr-calc-group">
                    <div className="atr-calc-group-title">동적 손절 (ADX 기반)</div>
                    <div className="atr-calc-row">
                        <span className="atr-calc-label">ADX / 배수</span>
                        <span className="atr-calc-value">
                            {calc.adxValue != null ? fmtIndicator(calc.adxValue, 1) : 'N/A'}
                            <span className="ft-sub"> → {calc.dynamicMultiplier}x ({calc.dynamicMultiplier === 2.0 ? '횡보 — 넓은 손절' : '추세 — 타이트'})</span>
                        </span>
                    </div>
                    <div className="atr-calc-row">
                        <span className="atr-calc-label atr-short">Long 동적 SL</span>
                        <span className="atr-calc-value">{fmtPrice(calc.dynamicLongStop)} <span className="ft-sub">({calc.dynamicMultiplier}x ATR)</span></span>
                    </div>
                    <div className="atr-calc-row">
                        <span className="atr-calc-label atr-long">Short 동적 SL</span>
                        <span className="atr-calc-value">{fmtPrice(calc.dynamicShortStop)} <span className="ft-sub">({calc.dynamicMultiplier}x ATR)</span></span>
                    </div>
                </div>

                {/* 거래량 가중 ATR */}
                <div className="atr-calc-group">
                    <div className="atr-calc-group-title">통합 ATR (거래량 가중)</div>
                    <div className="atr-calc-row">
                        <span className="atr-calc-label">Volume ROC</span>
                        <span className={`atr-calc-value ${calc.volumeRoc != null && calc.volumeRoc > 0 ? 'atr-long' : calc.volumeRoc != null && calc.volumeRoc < 0 ? 'atr-short' : ''}`}>
                            {calc.volumeRoc != null ? `${calc.volumeRoc >= 0 ? '+' : ''}${(calc.volumeRoc * 100).toFixed(1)}%` : 'N/A'}
                        </span>
                    </div>
                    <div className="atr-calc-row">
                        <span className="atr-calc-label">통합 ATR</span>
                        <span className="atr-calc-value">
                            {calc.integratedATR != null ? fmtIndicator(calc.integratedATR) : 'N/A'}
                            {calc.integratedATR != null && <span className="ft-sub"> (기본 {fmtIndicator(calc.atr)})</span>}
                        </span>
                    </div>
                    <div className="atr-calc-row">
                        <span className="atr-calc-label">통합 브레이크아웃</span>
                        <span className={`atr-calc-value ${calc.integratedBreakoutValid ? 'atr-long' : 'atr-muted'}`}>
                            {calc.integratedBreakoutValid == null ? 'N/A' : calc.integratedBreakoutValid ? '✓ 유효' : '✗ 미충족'}
                        </span>
                    </div>
                </div>

                {/* 피라미딩 간격 */}
                <div className="atr-calc-group">
                    <div className="atr-calc-group-title">피라미딩 간격 (0.5x ATR)</div>
                    {calc.pyramidLong.map((price, i) => (
                        <div key={`pl${i}`} className="atr-calc-row" style={{ opacity: 1 - i * 0.2 }}>
                            <span className="atr-calc-label atr-long">Long #{i + 1}</span>
                            <span className="atr-calc-value">
                                {fmtPrice(price)}
                                <span className="ft-sub"> {i === 0 ? '(진입)' : `(+${(i * 0.5).toFixed(1)} ATR)`}</span>
                            </span>
                        </div>
                    ))}
                    {calc.pyramidShort.map((price, i) => (
                        <div key={`ps${i}`} className="atr-calc-row" style={{ opacity: 1 - i * 0.2 }}>
                            <span className="atr-calc-label atr-short">Short #{i + 1}</span>
                            <span className="atr-calc-value">
                                {fmtPrice(price)}
                                <span className="ft-sub"> {i === 0 ? '(진입)' : `(-${(i * 0.5).toFixed(1)} ATR)`}</span>
                            </span>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}

// --- Technical Analysis Panels (on-demand) ---

