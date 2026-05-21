/**
 * ATRStopSection — Z-zone adaptive ATR stop / Take-Profit / Risk-Reward visualization.
 *
 * Phase D 추가 분할: pages/ScalpAnalyzer.tsx → components/scalp-analyzer/ATRStopSection.tsx
 *
 * ScalpInputs + ScalpResult 타입을 직접 받아 표시. RRVis / PriceChart는
 * 기존 추출 컴포넌트 재사용.
 */

import { K, F, fmt, fmtMoney, type ScalpInputs, type ScalpResult, type OHLC } from '@lib/scalpEngine';
import { Sec } from './Sec';
import { Met } from './Met';
import { RRVis } from './RRVis';
import { PriceChart } from './PriceChart';

export interface ATRStopSectionProps {
    inputs: ScalpInputs;
    calc: ScalpResult;
    candles: OHLC[];
    candleDates: string[];
    maPeriod: number;
}

export function ATRStopSection({ inputs, calc, candles, candleDates, maPeriod }: ATRStopSectionProps) {
    const zoneColor =
        calc.zZone === 'STRONG' ? '#f9a825'
            : calc.zZone === 'MILD' ? '#78909c'
                : '#546e7a';
    const zoneAccent =
        calc.zZone === 'STRONG' ? '#f9a825'
            : calc.zZone === 'MILD' ? '#90a4ae'
                : '#78909c';

    return (
        <div className="scalp-box">
            <Sec icon="🛡️" title="변동성 손절 & 손익비 (ATR Stop)" tag={`Z-${calc.zZone}`} tagC={zoneColor} />
            {/* Z-Zone adaptive info */}
            <div style={{
                padding: '8px 10px', marginBottom: 8, borderRadius: 6,
                background: calc.zZone === 'STRONG' ? '#f9a82508' : calc.zZone === 'MILD' ? '#78909c08' : '#546e7a08',
                border: `1px solid ${calc.zZone === 'STRONG' ? '#f9a82530' : calc.zZone === 'MILD' ? '#78909c20' : '#546e7a20'}`,
                fontSize: 10, fontFamily: F.mono, lineHeight: 1.6,
            }}>
                <div style={{ fontWeight: 700, color: zoneAccent, marginBottom: 3 }}>
                    Z-Zone: {calc.zZoneLabel}
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '2px 8px' }}>
                    <span style={{ color: '#888' }}>기본 ATR</span>
                    <span style={{ color: '#ccc', textAlign: 'right' }}>{fmt(calc.atrStop, 2)}p</span>
                    <span style={{ color: '#666', fontSize: 9 }}>ATR×{inputs.atrMult}</span>
                    <span style={{ color: '#888' }}>Z보정 배수</span>
                    <span style={{ color: calc.zZone === 'STRONG' ? '#f9a825' : '#ccc', textAlign: 'right', fontWeight: 700 }}>×{calc.zStopMult}</span>
                    <span style={{ color: '#666', fontSize: 9 }}>{calc.zZone === 'STRONG' ? '넓은 스탑' : calc.zZone === 'NORMAL' ? '타이트 스탑' : '표준'}</span>
                    <span style={{ color: K.red }}>적응형 SL</span>
                    <span style={{ color: K.red, textAlign: 'right', fontWeight: 700 }}>{fmt(calc.adaptiveStop, 2)}p</span>
                    <span style={{ color: '#666', fontSize: 9 }}>{fmt(calc.atrStop, 2)}×{calc.zStopMult}</span>
                </div>
                <div style={{ marginTop: 4, paddingTop: 4, borderTop: '1px solid #ffffff08', color: '#78909c', fontSize: 9 }}>
                    MA까지 {fmt(calc.maDistance, 2)}p ({calc.maDistR.toFixed(1)}R) | 회귀확률 {(calc.revertProb * 100).toFixed(0)}%
                </div>
            </div>
            <div className="scalp-flex" style={{ marginBottom: 6 }}>
                <Met label="적응형 손절" value={`${fmt(calc.adaptiveStop)}p`} sub={`ATR ${fmt(calc.atrStop)}p × ${calc.zStopMult}`} color={K.red} />
                <Met label="손절가 (SL)" value={fmt(calc.sl, 2)} color={K.red} />
                <Met label="익절 1.5R" value={fmt(calc.tp15, 2)} color="#69f0ae" />
                <Met label="익절 2R" value={fmt(calc.tp2, 2)} color={K.grn} />
                <Met label="익절 3R" value={fmt(calc.tp3, 2)} color={K.grn} />
            </div>
            <RRVis
                entry={inputs.currentPrice}
                sl={calc.sl}
                tp15={calc.tp15}
                tp2={calc.tp2}
                tp3={calc.tp3}
                isLong={calc.isLong}
                ma={inputs.ma}
                zZone={calc.zZone}
                zStopMult={calc.zStopMult}
                maDistR={calc.maDistR}
                revertProb={calc.revertProb}
                stdDev={inputs.stdDev}
                z={calc.z}
                volumeSR={calc.volumeSR}
            />
            {candles.length >= 5 && (
                <PriceChart
                    candles={candles}
                    ma={inputs.ma}
                    stdDev={inputs.stdDev}
                    entry={inputs.currentPrice}
                    sl={calc.sl}
                    tp15={calc.tp15}
                    tp2={calc.tp2}
                    tp3={calc.tp3}
                    isLong={calc.isLong}
                    volumeSR={calc.volumeSR}
                    maPeriod={maPeriod}
                    z={calc.z}
                    dates={candleDates}
                />
            )}
            <div className="scalp-pnl-row">
                <div className="scalp-pnl-card" style={{ background: `${K.grn}0a`, border: `1px solid ${K.grn}20` }}>
                    <div className="scalp-pnl-label">익절 1.5R 손익 ({calc.recContracts}ct)</div>
                    <div className="scalp-pnl-value" style={{ color: K.grn }}>+{fmtMoney(calc.pnlTP1, calc.cfg.sym)}</div>
                </div>
                <div className="scalp-pnl-card" style={{ background: `${K.red}0a`, border: `1px solid ${K.red}20` }}>
                    <div className="scalp-pnl-label">손절 손익 ({calc.recContracts}ct)</div>
                    <div className="scalp-pnl-value" style={{ color: K.red }}>-{fmtMoney(calc.pnlSL, calc.cfg.sym)}</div>
                </div>
            </div>
        </div>
    );
}
