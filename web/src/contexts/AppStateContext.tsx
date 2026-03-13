import { createContext, useContext, useState, useCallback, useRef, type ReactNode } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import type { MarketId } from '../lib/api';

interface HighlightTarget {
    ticker?: string;
    positionId?: string;
}

interface AppState {
    activeMarket: MarketId;
    setActiveMarket: (market: MarketId) => void;
    highlightedPosition: HighlightTarget | null;
    navigateToOperations: (highlight?: HighlightTarget) => void;
    clearHighlight: () => void;
}

const AppStateContext = createContext<AppState | null>(null);

export function AppStateProvider({ children }: { children: ReactNode }) {
    const [activeMarket, setActiveMarket] = useState<MarketId>('sp500');
    const [highlightedPosition, setHighlightedPosition] = useState<HighlightTarget | null>(null);
    const highlightTimerRef = useRef<ReturnType<typeof setTimeout>>();
    const navigate = useNavigate();
    const location = useLocation();

    const clearHighlight = useCallback(() => {
        setHighlightedPosition(null);
        if (highlightTimerRef.current) {
            clearTimeout(highlightTimerRef.current);
            highlightTimerRef.current = undefined;
        }
    }, []);

    const navigateToOperations = useCallback((highlight?: HighlightTarget) => {
        if (highlight?.ticker) {
            setHighlightedPosition(highlight);
            // Auto-clear after 5 seconds
            if (highlightTimerRef.current) clearTimeout(highlightTimerRef.current);
            highlightTimerRef.current = setTimeout(() => {
                setHighlightedPosition(null);
            }, 5000);
        }

        const params = highlight?.ticker ? `?highlight=${encodeURIComponent(highlight.ticker)}` : '';
        if (location.pathname === '/operations') {
            // Already on Operations — just set highlight, no navigate
            return;
        }
        navigate(`/operations${params}`);
    }, [navigate, location.pathname]);

    return (
        <AppStateContext.Provider value={{
            activeMarket,
            setActiveMarket,
            highlightedPosition,
            navigateToOperations,
            clearHighlight,
        }}>
            {children}
        </AppStateContext.Provider>
    );
}

export function useAppState(): AppState {
    const ctx = useContext(AppStateContext);
    if (!ctx) {
        throw new Error('useAppState must be used within <AppStateProvider>');
    }
    return ctx;
}
