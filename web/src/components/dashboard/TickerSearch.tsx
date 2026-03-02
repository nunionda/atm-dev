import { useState, useEffect, useRef, useCallback } from 'react';
import { Search, RefreshCw } from 'lucide-react';
import { searchTickers, type SearchResult } from '../../lib/api';
import './TickerSearch.css';

interface TickerSearchProps {
    onSelect: (ticker: string, nameKr?: string, nameEn?: string) => void;
    loading?: boolean;
    initialValue?: string;
}

const MARKET_LABELS: Record<string, string> = {
    KS: '코스피',
    KQ: '코스닥',
    US: 'US',
    CRYPTO: 'Crypto',
};

export function TickerSearch({ onSelect, loading = false, initialValue = '' }: TickerSearchProps) {
    const [query, setQuery] = useState(initialValue);
    const [results, setResults] = useState<SearchResult[]>([]);
    const [isOpen, setIsOpen] = useState(false);
    const [activeIndex, setActiveIndex] = useState(-1);
    const containerRef = useRef<HTMLFormElement>(null);
    const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    // Debounced search
    const doSearch = useCallback(async (q: string) => {
        if (q.length < 1) {
            setResults([]);
            setIsOpen(false);
            return;
        }
        const res = await searchTickers(q);
        setResults(res);
        setIsOpen(res.length > 0);
        setActiveIndex(-1);
    }, []);

    const handleInputChange = (value: string) => {
        setQuery(value);
        if (debounceRef.current) clearTimeout(debounceRef.current);
        debounceRef.current = setTimeout(() => doSearch(value), 300);
    };

    // Click outside to close
    useEffect(() => {
        const handleClickOutside = (e: MouseEvent) => {
            if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
                setIsOpen(false);
            }
        };
        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    // Keyboard navigation
    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (!isOpen) return;

        switch (e.key) {
            case 'ArrowDown':
                e.preventDefault();
                setActiveIndex(prev => Math.min(prev + 1, results.length - 1));
                break;
            case 'ArrowUp':
                e.preventDefault();
                setActiveIndex(prev => Math.max(prev - 1, 0));
                break;
            case 'Enter':
                e.preventDefault();
                if (activeIndex >= 0 && activeIndex < results.length) {
                    selectItem(results[activeIndex]);
                } else if (query.trim()) {
                    // Submit raw query
                    onSelect(query.trim());
                    setIsOpen(false);
                }
                break;
            case 'Escape':
                setIsOpen(false);
                break;
        }
    };

    const selectItem = (item: SearchResult) => {
        setQuery(item.code);
        setIsOpen(false);
        onSelect(item.ticker, item.name_kr, item.name_en);
    };

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        if (query.trim()) {
            onSelect(query.trim());
            setIsOpen(false);
        }
    };

    return (
        <form className="ticker-search glass-panel" onSubmit={handleSubmit} ref={containerRef}>
            <div className="ticker-search-input-wrap">
                <input
                    type="text"
                    placeholder="종목명 또는 코드 검색 (예: 삼성, AAPL)"
                    value={query}
                    onChange={(e) => handleInputChange(e.target.value)}
                    onFocus={() => { if (results.length > 0) setIsOpen(true); }}
                    onKeyDown={handleKeyDown}
                    autoComplete="off"
                />

                {isOpen && (
                    <div className="ticker-dropdown">
                        {results.map((item, idx) => (
                            <div
                                key={item.ticker}
                                className={`ticker-dropdown-item ${idx === activeIndex ? 'active' : ''}`}
                                onMouseDown={() => selectItem(item)}
                                onMouseEnter={() => setActiveIndex(idx)}
                            >
                                <span className="ticker-item-code">{item.code}</span>
                                <div className="ticker-item-name">
                                    <span className="ticker-item-name-kr">{item.name_kr}</span>
                                    <span className="ticker-item-name-en">{item.name_en}</span>
                                </div>
                                <span className={`ticker-market-badge badge-${item.market}`}>
                                    {MARKET_LABELS[item.market] || item.market}
                                </span>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            <button type="submit" className="btn-primary" disabled={loading}>
                {loading ? <RefreshCw size={18} className="animate-spin" /> : <Search size={18} />}
            </button>
        </form>
    );
}
