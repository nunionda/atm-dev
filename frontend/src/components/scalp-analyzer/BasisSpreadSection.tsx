/**
 * BasisSpreadSection — 선물/현물 basis 분석 패널 (메인 페이지에서 추출).
 *
 * Phase D 추가 분할: pages/ScalpAnalyzer.tsx → components/scalp-analyzer/BasisSpreadSection.tsx
 *
 * 의존 props만 받는 stateless 컴포넌트. 메인 페이지의 useReducer/computed
 * 결과를 그대로 전달받아 표시만 한다.
 */

import { K, fmt } from '@lib/scalpEngine';
import { Sec } from './Sec';
import { Met } from './Met';
import { BasisBar } from './BasisBar';

export interface BasisSpreadSectionProps {
    spotLabel: string;
    futLabel: string;
    inputs: {
        spotPrice: number;
        futuresPrice: number;
    };
    calc: {
        basis: number;
        basisPct: number;
        basisState: 'CONTANGO' | 'BACKWARDATION' | 'FAIR' | string;
    };
}

export function BasisSpreadSection({ spotLabel, futLabel, inputs, calc }: BasisSpreadSectionProps) {
    const tagColor = calc.basis > 2 ? K.cyn : calc.basis < -2 ? K.org : '#78909c';

    return (
        <div className="scalp-box">
            <Sec icon="📉" title="선현물 스프레드 (Basis)" tag={calc.basisState} tagC={tagColor} infoId="basisSpread" />
            <div className="scalp-flex">
                <Met label={`${spotLabel} (현물)`} value={fmt(inputs.spotPrice, 2)} />
                <Met label={`${futLabel} (선물)`} value={fmt(inputs.futuresPrice, 2)} />
                <Met
                    label="Basis"
                    value={`${calc.basis >= 0 ? '+' : ''}${fmt(calc.basis, 2)}p`}
                    color={tagColor}
                    big
                />
                <Met label="Basis %" value={`${fmt(calc.basisPct, 3)}%`} />
            </div>
            <BasisBar basis={calc.basis} />
            <div className="scalp-detail" style={{ marginTop: 10, fontSize: 9.5, lineHeight: 1.5 }}>
                {calc.basisState === 'CONTANGO'
                    ? '선물 > 현물: 콘탱고 (정상). 보유비용 반영. 만기 수렴 시 선물 하방압력.'
                    : calc.basisState === 'BACKWARDATION'
                        ? '선물 < 현물: 백워데이션. 시장 스트레스 시그널. 차익매수세(프로그램) 유입 가능.'
                        : '현물 ≈ 선물: 적정가(Fair Value) 근처. 차익거래 유인 미미.'}
            </div>
        </div>
    );
}
