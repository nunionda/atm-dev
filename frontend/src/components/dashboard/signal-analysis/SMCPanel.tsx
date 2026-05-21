/**
 * SMCPanel — extracted from SignalAnalysis.
 *
 * Phase D3 분할: dashboard/SignalAnalysis.tsx → dashboard/signal-analysis/SMCPanel.tsx
 */

import { Compass } from 'lucide-react';
import type { SMCAnalysis } from '@lib/signalEngine';

export function SMCPanel({ smc, fmtPrice }: { smc: SMCAnalysis; fmtPrice: (v: number) => string }) {
    const hasData = smc.markers.length > 0 || smc.orderBlocks.length > 0 || smc.fvgs.length > 0;
    if (!hasData) return null;

    return (
        <div className="sa-entry-section glass-panel">
            <h3 className="sa-section-title">
                <Compass size={16} />
                Smart Money Concepts
            </h3>

            {smc.markers.length > 0 && (
                <div className="smc-section">
                    <div className="sa-group-label">Market Structure</div>
                    <div className="smc-marker-list">
                        {smc.markers.map((m, i) => (
                            <div key={i} className="smc-marker-item">
                                <span className={`smc-marker-badge ${m.type.includes('BULL') ? 'bull' : 'bear'}`}>
                                    {m.type}
                                </span>
                                <span className="ft-sub">{m.barsAgo === 0 ? '현재 봉' : `${m.barsAgo}봉 전`}</span>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {smc.orderBlocks.length > 0 && (
                <div className="smc-section">
                    <div className="sa-group-label">Order Block</div>
                    {smc.orderBlocks.slice(0, 3).map((ob, i) => (
                        <div key={i} className="smc-zone-item">
                            <span className="smc-zone-label">OB #{i + 1}</span>
                            <span className="smc-zone-prices">
                                {fmtPrice(ob.bottom)} ~ {fmtPrice(ob.top)}
                                <span className={`smc-relation-badge ${ob.relation.toLowerCase()}`}>{ob.relation}</span>
                            </span>
                        </div>
                    ))}
                </div>
            )}

            {smc.fvgs.length > 0 && (
                <div className="smc-section">
                    <div className="sa-group-label">Fair Value Gap</div>
                    {smc.fvgs.slice(0, 3).map((fvg, i) => (
                        <div key={i} className="smc-zone-item">
                            <span className="smc-zone-label">{fvg.type} FVG</span>
                            <span className="smc-zone-prices">
                                {fmtPrice(fvg.bottom)} ~ {fmtPrice(fvg.top)}
                                <span className={`smc-relation-badge ${fvg.relation.toLowerCase()}`}>{fvg.relation}</span>
                            </span>
                        </div>
                    ))}
                </div>
            )}

            <div className={`smc-bias-badge ${smc.smcBias.toLowerCase()}`}>
                Smart Money Concept: {smc.smcLabel}
            </div>
        </div>
    );
}

// --- Main Component ---

