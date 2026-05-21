/**
 * QuickReference — Fabio Playbook 요약 참조 카드.
 *
 * Phase D 추가 분할: pages/FabioStrategy.tsx → components/fabio-strategy/QuickReference.tsx
 *
 * 완전 정적 (props 없음).
 */

import { K } from '@lib/scalpEngine';
import { Sec } from './Sec';

const REFERENCES: { t: string; rules: string[] }[] = [
    { t: 'AMT 3단계',     rules: ['Market State → Location → Aggression', '하나라도 빠지면 관망'] },
    { t: 'Trend Model',   rules: ['임펄스 VP → LVN 대기', '공격성 확인 후 진입', 'TP = 이전 Balance POC'] },
    { t: 'Mean Rev Model', rules: ['브레이크아웃 실패 확인', '리클레임 → 풀백 → LVN', 'TP = Balance POC'] },
    { t: '리스크 규칙',   rules: ['0.25~0.5% / 트레이드', '3회 연속 손절 → 중단', '손절 확대 절대 금지'] },
    { t: 'DO',            rules: ['내러티브 설정', '작게 시작 → 컴파운딩', '1아이디어 = 1티켓'] },
    { t: "DON'T",         rules: ['조건 불완전 진입', '복수 트레이딩', '비활성 시간대 스캘핑'] },
];

export function QuickReference() {
    return (
        <div className="fb-box">
            <Sec icon="📖" title="Fabio 요약 참조" tag="RULES" tagC={K.dim} />
            <div className="fb-ref-grid">
                {REFERENCES.map((ref, i) => (
                    <div key={i} className="fb-ref-card">
                        <div className="fb-ref-title">{ref.t}</div>
                        {ref.rules.map((r, j) => (
                            <div key={j} className="fb-ref-rule">• {r}</div>
                        ))}
                    </div>
                ))}
            </div>
        </div>
    );
}
