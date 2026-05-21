/**
 * ZScoreSection — Z-스코어 통계 분석 패널 (메인 페이지에서 추출).
 *
 * Phase D 추가 분할: pages/ScalpAnalyzer.tsx → components/scalp-analyzer/ZScoreSection.tsx
 */

import { fmt, fmtPct } from '@lib/scalpEngine';
import { Sec } from './Sec';
import { Met } from './Met';
import { ZBar } from './ZBar';
import { Term } from '@components/glossary/GlossaryComponents';

export interface ZScoreSectionProps {
    inputs: {
        currentPrice: number;
        ma: number;
        stdDev: number;
    };
    calc: {
        z: number;
        zColor: string;
        zSignal: string;
        pVal: number;
    };
}

export function ZScoreSection({ inputs, calc }: ZScoreSectionProps) {
    return (
        <div className="scalp-box">
            <Sec icon="📐" title="Z-스코어 분석" tag="통계적 위치" infoId="zscore" />
            <div className="scalp-flex">
                <Met label="Z-스코어 (Z)" value={fmt(calc.z)} color={calc.zColor} big />
                <Met label="시그널" value={calc.zSignal} color={calc.zColor} />
                <Met label="유의확률 (P-Value)" value={fmtPct(calc.pVal)} sub="양측검정" />
                <Met label="이격" value={fmt(inputs.currentPrice - inputs.ma, 1) + 'p'} sub="vs MA" />
            </div>
            <ZBar z={calc.z} />
            <div className="scalp-detail" style={{ marginTop: 12 }}>
                <Term id="zscore">Z</Term> = ({fmt(inputs.currentPrice, 2)} − {fmt(inputs.ma, 2)}) / {fmt(inputs.stdDev, 2)} ={' '}
                <span style={{ color: calc.zColor, fontWeight: 700 }}>{fmt(calc.z)}</span>
                {' '}→ <Term id="ma">MA</Term>에서 {fmt(Math.abs(calc.z))}<Term id="sigma">σ</Term>{' '}
                {calc.z < 0 ? '하방' : '상방'} | 이격 확률 {fmtPct(calc.pVal)}
            </div>
        </div>
    );
}
