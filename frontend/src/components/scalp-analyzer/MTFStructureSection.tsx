/**
 * MTFStructureSection — Multi-Timeframe (HTF 1H + LTF 5min) 구조 분석 패널.
 *
 * Phase D 추가 분할: pages/ScalpAnalyzer.tsx → components/scalp-analyzer/MTFStructureSection.tsx
 */

import { K, F } from '@lib/scalpEngine';
import type { MTFAnalysis } from '@lib/mtfEngine';
import type { AnalyticsData } from '@/types';
import { Sec } from './Sec';
import { Met } from './Met';

export interface MTFStructureSectionProps {
    mtfAnalysis: MTFAnalysis | null;
    mtfHTF: AnalyticsData[];
    mtfLTF: AnalyticsData[];
    mtfLoading: boolean;
    mtfError: string | null;
    mtfExpanded: boolean;
    setMtfExpanded: (updater: (v: boolean) => boolean) => void;
    loadMTFData: () => void;
}

export function MTFStructureSection({
    mtfAnalysis, mtfHTF, mtfLTF, mtfLoading, mtfError, mtfExpanded, setMtfExpanded, loadMTFData,
}: MTFStructureSectionProps) {
    const dirColor = mtfAnalysis?.direction === 'LONG' ? K.grn
        : mtfAnalysis?.direction === 'SHORT' ? K.red : K.dim;

    return (
        <div className="scalp-box">
            <div className="scalp-opt-header" onClick={() => setMtfExpanded(v => !v)}>
                <Sec
                    icon="🔀"
                    title="멀티타임프레임 구조 (MTF Structure)"
                    tag={mtfAnalysis ? mtfAnalysis.signalType.replace(/_/g, ' ') : 'READY'}
                    tagC={dirColor}
                />
                <button className={`scalp-opt-toggle ${mtfExpanded ? 'open' : ''}`}>▼</button>
            </div>
            {mtfExpanded && (
                <div className="scalp-opt-content">
                    <button onClick={loadMTFData} disabled={mtfLoading} className="scalp-opt-run-btn">
                        {mtfLoading ? '⏳ Loading HTF + LTF...' : '📡 Load MTF Data (1H + 5min)'}
                    </button>
                    {mtfError && <div style={{ marginTop: 8, fontSize: 10, color: K.red }}>⚠ {mtfError}</div>}
                    {(mtfHTF.length > 0 || mtfLTF.length > 0) && (
                        <div className="scalp-opt-run-info">
                            <span>HTF: {mtfHTF.length}봉 (1H)</span>
                            <span>LTF: {mtfLTF.length}봉 (5min)</span>
                        </div>
                    )}
                    {mtfAnalysis && (
                        <>
                            <div className="scalp-opt-divider">HTF CONTEXT (1H)</div>
                            <div className="scalp-flex" style={{ marginBottom: 10 }}>
                                <Met
                                    label="추세 (Trend)"
                                    value={mtfAnalysis.htf.trend}
                                    color={
                                        mtfAnalysis.htf.trend === 'BULLISH' ? K.grn
                                            : mtfAnalysis.htf.trend === 'BEARISH' ? K.red : K.dim
                                    }
                                />
                                <Met label="추세 확신도" value={`${mtfAnalysis.htf.trendConfidence}%`} />
                                <Met label="가격 위치" value={mtfAnalysis.htf.pricePosition.replace(/_/g, ' ')} />
                                <Met label="레짐" value={mtfAnalysis.htf.regime} />
                            </div>
                            <div className="scalp-opt-params-grid">
                                <div className="scalp-opt-param">
                                    <span className="scalp-opt-param-label">저항 (Resistance)</span>
                                    <span className="scalp-opt-param-val" style={{ color: K.red }}>
                                        {mtfAnalysis.htf.keyResistance?.toFixed(2) ?? '—'}
                                    </span>
                                </div>
                                <div className="scalp-opt-param">
                                    <span className="scalp-opt-param-label">지지 (Support)</span>
                                    <span className="scalp-opt-param-val" style={{ color: K.grn }}>
                                        {mtfAnalysis.htf.keySupport?.toFixed(2) ?? '—'}
                                    </span>
                                </div>
                                <div className="scalp-opt-param">
                                    <span className="scalp-opt-param-label">마지막 BOS</span>
                                    <span className="scalp-opt-param-val">
                                        {mtfAnalysis.htf.lastBOS
                                            ? `${mtfAnalysis.htf.lastBOS.direction} @ ${mtfAnalysis.htf.lastBOS.breakPrice.toFixed(2)}`
                                            : '—'}
                                    </span>
                                </div>
                                <div className="scalp-opt-param">
                                    <span className="scalp-opt-param-label">마지막 CHoCH</span>
                                    <span className="scalp-opt-param-val">
                                        {mtfAnalysis.htf.lastCHoCH
                                            ? `${mtfAnalysis.htf.lastCHoCH.direction} @ ${mtfAnalysis.htf.lastCHoCH.breakPrice.toFixed(2)}`
                                            : '—'}
                                    </span>
                                </div>
                            </div>
                            <div className="scalp-detail" style={{ marginTop: 10 }}>
                                <span style={{ color: K.acc, fontWeight: 700 }}>스윙 구조: </span>
                                {mtfAnalysis.htf.swingHighs.slice(-4).map((sh, i) =>
                                    <span key={`h${i}`} style={{ color: K.red, marginRight: 6 }}>H:{sh.price.toFixed(2)}</span>
                                )}
                                {mtfAnalysis.htf.swingLows.slice(-4).map((sl, i) =>
                                    <span key={`l${i}`} style={{ color: K.grn, marginRight: 6 }}>L:{sl.price.toFixed(2)}</span>
                                )}
                            </div>

                            <div className="scalp-opt-divider">LTF SIGNAL (5min)</div>
                            <div className="scalp-flex" style={{ marginBottom: 10 }}>
                                <Met
                                    label="시그널"
                                    value={mtfAnalysis.ltf.signalType.replace(/_/g, ' ')}
                                    color={mtfAnalysis.ltf.alignedWithHTF ? K.grn : K.dim}
                                    big
                                />
                                <Met
                                    label="HTF 정합"
                                    value={mtfAnalysis.ltf.alignedWithHTF ? 'YES' : 'NO'}
                                    color={mtfAnalysis.ltf.alignedWithHTF ? K.grn : K.red}
                                />
                                <Met
                                    label="확신도"
                                    value={mtfAnalysis.ltf.confidence}
                                    color={
                                        mtfAnalysis.ltf.confidence === 'HIGH' ? K.grn
                                            : mtfAnalysis.ltf.confidence === 'MEDIUM' ? K.org : K.dim
                                    }
                                />
                            </div>

                            {/* Combined Verdict */}
                            <div style={{
                                marginTop: 12, padding: '10px 14px',
                                background: mtfAnalysis.direction === 'LONG' ? `${K.grn}0c`
                                    : mtfAnalysis.direction === 'SHORT' ? `${K.red}0c` : `${K.dim}08`,
                                border: `1px solid ${
                                    mtfAnalysis.direction === 'LONG' ? `${K.grn}30`
                                        : mtfAnalysis.direction === 'SHORT' ? `${K.red}30` : `${K.dim}20`
                                }`,
                                borderRadius: 6, textAlign: 'center',
                            }}>
                                <div style={{
                                    fontSize: 14, fontWeight: 800, fontFamily: F.mono, letterSpacing: '0.06em',
                                    color: dirColor,
                                }}>
                                    {mtfAnalysis.direction} — {mtfAnalysis.signalType.replace(/_/g, ' ')} ({mtfAnalysis.confidence})
                                </div>
                                <div style={{ fontSize: 10, color: K.dim, marginTop: 4 }}>
                                    {mtfAnalysis.summary}
                                </div>
                            </div>

                            {mtfAnalysis.direction !== 'NEUTRAL' && (
                                <div className="scalp-opt-params-grid" style={{ marginTop: 10 }}>
                                    <div className="scalp-opt-param">
                                        <span className="scalp-opt-param-label">진입 구간</span>
                                        <span className="scalp-opt-param-val">{mtfAnalysis.entryZone}</span>
                                    </div>
                                    <div className="scalp-opt-param">
                                        <span className="scalp-opt-param-label">구조 손절 (SL)</span>
                                        <span className="scalp-opt-param-val" style={{ color: K.red }}>
                                            {mtfAnalysis.stopLoss?.toFixed(2) ?? '—'}
                                        </span>
                                    </div>
                                    <div className="scalp-opt-param">
                                        <span className="scalp-opt-param-label">구조 목표 (TP)</span>
                                        <span className="scalp-opt-param-val" style={{ color: K.grn }}>
                                            {mtfAnalysis.takeProfit?.toFixed(2) ?? '—'}
                                        </span>
                                    </div>
                                    <div className="scalp-opt-param">
                                        <span className="scalp-opt-param-label">LTF 사유</span>
                                        <span className="scalp-opt-param-val" style={{ fontSize: 9 }}>{mtfAnalysis.ltf.reason}</span>
                                    </div>
                                </div>
                            )}
                        </>
                    )}
                </div>
            )}
        </div>
    );
}
