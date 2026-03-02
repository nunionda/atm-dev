/**
 * lightweight-charts ISeriesPrimitive for rendering OB/FVG zones as filled rectangles.
 */

import type {
    ISeriesPrimitive,
    ISeriesPrimitivePaneView,
    ISeriesPrimitivePaneRenderer,
    SeriesAttachedParameter,
    Time,
    SeriesType,
    Coordinate,
} from 'lightweight-charts';
import type { CanvasRenderingTarget2D } from 'fancy-canvas';

export interface ZoneData {
    startTime: Time;
    endTime: Time;
    top: number;
    bottom: number;
    color: string;
    borderColor: string;
    label: string;
}

interface ZoneRenderData {
    x1: Coordinate | null;
    x2: Coordinate | null;
    y1: Coordinate | null;
    y2: Coordinate | null;
    color: string;
    borderColor: string;
    label: string;
}

class ZoneRenderer implements ISeriesPrimitivePaneRenderer {
    private _zones: ZoneRenderData[];

    constructor(zones: ZoneRenderData[]) {
        this._zones = zones;
    }

    draw(target: CanvasRenderingTarget2D): void {
        target.useBitmapCoordinateSpace(scope => {
            const ctx = scope.context;
            const hr = scope.horizontalPixelRatio;
            const vr = scope.verticalPixelRatio;

            for (const zone of this._zones) {
                if (zone.x1 === null || zone.x2 === null ||
                    zone.y1 === null || zone.y2 === null) continue;

                const x = Math.min(zone.x1 as number, zone.x2 as number) * hr;
                const w = Math.abs((zone.x2 as number) - (zone.x1 as number)) * hr;
                const y = Math.min(zone.y1 as number, zone.y2 as number) * vr;
                const h = Math.abs((zone.y2 as number) - (zone.y1 as number)) * vr;

                if (w < 1 || h < 1) continue;

                // Fill
                ctx.fillStyle = zone.color;
                ctx.fillRect(x, y, w, h);

                // Border
                ctx.strokeStyle = zone.borderColor;
                ctx.lineWidth = 1 * hr;
                ctx.strokeRect(x, y, w, h);

                // Label
                ctx.fillStyle = zone.borderColor;
                ctx.font = `${Math.round(10 * vr)}px Inter, sans-serif`;
                ctx.fillText(zone.label, x + 4 * hr, y + 12 * vr);
            }
        });
    }
}

class ZonePaneView implements ISeriesPrimitivePaneView {
    private _primitive: SmcZonePrimitive;

    constructor(primitive: SmcZonePrimitive) {
        this._primitive = primitive;
    }

    zOrder(): 'bottom' {
        return 'bottom';
    }

    renderer(): ISeriesPrimitivePaneRenderer | null {
        return new ZoneRenderer(this._primitive.getRenderData());
    }
}

export class SmcZonePrimitive implements ISeriesPrimitive<Time> {
    private _zones: ZoneData[];
    private _paneView: ZonePaneView;
    private _chart: any = null;
    private _series: any = null;

    constructor(zones: ZoneData[]) {
        this._zones = zones;
        this._paneView = new ZonePaneView(this);
    }

    attached(param: SeriesAttachedParameter<Time, SeriesType>): void {
        this._chart = param.chart;
        this._series = param.series;
    }

    detached(): void {
        this._chart = null;
        this._series = null;
    }

    paneViews(): readonly ISeriesPrimitivePaneView[] {
        return [this._paneView];
    }

    updateAllViews(): void {
        // Called on viewport changes; getRenderData recalculates coordinates
    }

    getRenderData(): ZoneRenderData[] {
        if (!this._chart || !this._series) return [];

        const timeScale = this._chart.timeScale();

        return this._zones.map(zone => ({
            x1: timeScale.timeToCoordinate(zone.startTime) as Coordinate | null,
            x2: timeScale.timeToCoordinate(zone.endTime) as Coordinate | null,
            y1: this._series.priceToCoordinate(zone.top) as Coordinate | null,
            y2: this._series.priceToCoordinate(zone.bottom) as Coordinate | null,
            color: zone.color,
            borderColor: zone.borderColor,
            label: zone.label,
        }));
    }
}
