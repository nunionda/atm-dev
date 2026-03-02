import { useState, useEffect, useCallback } from 'react';
import type { IChartApi, ISeriesApi, SeriesType } from 'lightweight-charts';
import type { AnalyticsData } from '../../lib/api';
import { computeVolumeProfile, type VolumeBucket } from '../../lib/chartUtils';
import './VolumeProfile.css';

interface VolumeProfileProps {
    chart: IChartApi | null;
    series: ISeriesApi<SeriesType> | null;
    data: AnalyticsData[];
    visible: boolean;
}

export function VolumeProfile({ chart, series, data, visible }: VolumeProfileProps) {
    const [buckets, setBuckets] = useState<(VolumeBucket & { top: number; height: number })[]>([]);

    const recalculate = useCallback(() => {
        if (!chart || !series || !visible || data.length === 0) {
            setBuckets([]);
            return;
        }

        const profile = computeVolumeProfile(data, 24);
        if (profile.length < 2) return;

        const priceGap = profile.length > 1
            ? profile[1].priceLevel - profile[0].priceLevel
            : 0;

        const rendered = profile.map(bucket => {
            const yTop = series!.priceToCoordinate(bucket.priceLevel + priceGap / 2);
            const yBottom = series!.priceToCoordinate(bucket.priceLevel - priceGap / 2);

            if (yTop === null || yBottom === null) {
                return { ...bucket, top: 0, height: 0 };
            }

            return {
                ...bucket,
                top: Math.min(yTop as number, yBottom as number),
                height: Math.abs((yBottom as number) - (yTop as number)),
            };
        }).filter(b => b.height > 0);

        setBuckets(rendered);
    }, [chart, series, data, visible]);

    useEffect(() => {
        if (!chart || !visible) return;

        recalculate();
        chart.timeScale().subscribeVisibleLogicalRangeChange(recalculate);
        return () => chart.timeScale().unsubscribeVisibleLogicalRangeChange(recalculate);
    }, [chart, visible, recalculate]);

    if (!visible || buckets.length === 0) return null;

    const maxPct = Math.max(...buckets.map(b => b.pct));

    return (
        <div className="vp-overlay">
            {buckets.map((b, i) => {
                const barWidth = maxPct > 0 ? (b.pct / maxPct) * 100 : 0;
                const buyRatio = b.totalVolume > 0 ? (b.buyVolume / b.totalVolume) * 100 : 50;
                const isPoc = b.pct === maxPct;

                return (
                    <div
                        key={i}
                        className={`vp-bar ${isPoc ? 'vp-poc' : ''}`}
                        style={{
                            top: b.top,
                            height: Math.max(b.height, 1),
                            width: `${barWidth}%`,
                        }}
                    >
                        <div className="vp-buy" style={{ width: `${buyRatio}%` }} />
                        <div className="vp-sell" style={{ width: `${100 - buyRatio}%` }} />
                    </div>
                );
            })}
        </div>
    );
}
