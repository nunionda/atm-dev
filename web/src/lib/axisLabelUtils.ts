/**
 * Right-axis label deconfliction overlay — shared between TechnicalChart & ESFIntradayChart.
 *
 * Renders indicator labels (S/R levels, MA values, entry/TP/SL) as HTML elements
 * positioned next to the y-axis, with automatic overlap prevention.
 */
import type { ISeriesApi, SeriesType } from 'lightweight-charts';

export interface AxisLabelItem {
  price: number;
  text: string;
  color: string;
}

/**
 * Renders axis label items as positioned HTML inside the overlay DIV.
 *
 * 1. Maps prices → Y coordinates via `series.priceToCoordinate()`
 * 2. Two-pass deconfliction (downward + upward) prevents overlap
 * 3. Draws small horizontal ticks when a label is displaced from its price
 */
export function updateAxisLabels(
  series: ISeriesApi<SeriesType>,
  items: AxisLabelItem[],
  overlay: HTMLDivElement,
  chartHeight: number,
): void {
  const MIN_GAP = 16;
  const LABEL_H = 14;

  const mapped = items
    .map((item) => {
      const y = series.priceToCoordinate(item.price);
      return { ...item, origY: (y ?? -1) as number, labelY: (y ?? -1) as number };
    })
    .filter((r) => r.origY >= 0 && r.origY <= chartHeight)
    .sort((a, b) => a.origY - b.origY);

  // Downward pass — push overlapping labels down
  for (let i = 1; i < mapped.length; i++) {
    if (mapped[i].labelY - mapped[i - 1].labelY < MIN_GAP) {
      mapped[i].labelY = mapped[i - 1].labelY + MIN_GAP;
    }
  }
  // Upward pass — fix any that got pushed below bottom
  for (let i = mapped.length - 2; i >= 0; i--) {
    if (mapped[i + 1].labelY - mapped[i].labelY < MIN_GAP) {
      mapped[i].labelY = mapped[i + 1].labelY - MIN_GAP;
    }
  }

  overlay.innerHTML = '';
  mapped.forEach((item) => {
    const lY = Math.round(item.labelY) - Math.floor(LABEL_H / 2);
    if (lY < -LABEL_H || lY > chartHeight + LABEL_H) return;

    // Horizontal tick at original price when label was moved
    if (Math.abs(item.labelY - item.origY) > 4) {
      const tick = document.createElement('div');
      tick.style.cssText = [
        'position:absolute', 'right:0',
        `top:${Math.round(item.origY)}px`,
        'width:6px', 'height:1px',
        `background:${item.color}`, 'opacity:0.6',
      ].join(';');
      overlay.appendChild(tick);
    }

    const el = document.createElement('div');
    el.style.cssText = [
      'position:absolute', 'right:0',
      `top:${lY}px`,
      `background:${item.color}`,
      'color:#fff',
      'font-size:9px',
      "font-family:'IBM Plex Mono',monospace",
      'font-weight:700',
      'padding:1px 4px',
      'border-radius:2px 0 0 2px',
      'white-space:nowrap',
      'line-height:1.4',
      'text-shadow:0 1px 2px rgba(0,0,0,0.6)',
      'pointer-events:none',
      'max-width:100px',
      'overflow:hidden',
      'text-overflow:ellipsis',
    ].join(';');
    const shortText = item.text
      .replace(/^VWATR /, '')
      .replace(/\s*\([^)]*\)/, '');
    el.textContent = `${shortText} ${item.price.toFixed(1)}`;
    overlay.appendChild(el);
  });
}

/**
 * Creates the overlay DIV and appends it to the chart container.
 * Returns the overlay element for ref storage.
 */
export function createAxisOverlay(container: HTMLElement): HTMLDivElement {
  const overlay = document.createElement('div');
  overlay.style.cssText =
    'position:absolute;top:0;right:0;width:100px;height:100%;pointer-events:none;z-index:5;';
  container.appendChild(overlay);
  return overlay;
}

/**
 * Binds refresh callbacks to chart events (time scale changes, y-axis drag, resize).
 * Returns a cleanup function to remove listeners.
 */
export function bindAxisLabelRefresh(
  container: HTMLElement,
  refresh: () => void,
): () => void {
  // Y-axis drag
  const priceAxis = container.querySelector('[class*="price-axis"]') as HTMLElement | null;
  const cleanups: (() => void)[] = [];

  if (priceAxis) {
    const onPointerDown = () => {
      const onMove = () => refresh();
      const onUp = () => {
        window.removeEventListener('pointermove', onMove);
      };
      window.addEventListener('pointermove', onMove);
      window.addEventListener('pointerup', onUp, { once: true });
    };
    priceAxis.addEventListener('pointerdown', onPointerDown);
    cleanups.push(() => priceAxis.removeEventListener('pointerdown', onPointerDown));
  }

  // Window resize
  const onResize = () => refresh();
  window.addEventListener('resize', onResize);
  cleanups.push(() => window.removeEventListener('resize', onResize));

  return () => cleanups.forEach((fn) => fn());
}
