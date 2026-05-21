// --- Drawing Tool Types ---

export type DrawingToolType = 'trendline' | 'hline' | 'fibonacci' | null;

export interface DrawingPoint {
    price: number;
    time: string; // original datetime string
}

// --- Completed Drawing Types ---

export interface TrendLineDrawing {
    id: string;
    type: 'trendline';
    p1: DrawingPoint;
    p2: DrawingPoint;
}

export interface HorizontalLineDrawing {
    id: string;
    type: 'hline';
    price: number;
}

export interface FibonacciDrawing {
    id: string;
    type: 'fibonacci';
    p1: DrawingPoint;
    p2: DrawingPoint;
}

export type Drawing = TrendLineDrawing | HorizontalLineDrawing | FibonacciDrawing;

// --- Fibonacci Constants ---

export const FIB_LEVELS = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0] as const;

export const FIB_COLORS: Record<number, string> = {
    0:     'rgba(239, 68, 68, 0.8)',
    0.236: 'rgba(249, 115, 22, 0.7)',
    0.382: 'rgba(234, 179, 8, 0.7)',
    0.5:   'rgba(99, 102, 241, 0.8)',
    0.618: 'rgba(34, 197, 94, 0.7)',
    0.786: 'rgba(6, 182, 212, 0.7)',
    1.0:   'rgba(239, 68, 68, 0.8)',
};

// --- Pending Drawing State ---

export interface PendingDrawing {
    tool: DrawingToolType;
    anchor: DrawingPoint | null;
    cursor: DrawingPoint | null;
}

export const INITIAL_PENDING: PendingDrawing = {
    tool: null,
    anchor: null,
    cursor: null,
};
