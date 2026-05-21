import { useState, useRef, useEffect, useCallback } from 'react';
import { Calendar, ChevronLeft, ChevronRight } from 'lucide-react';
import './DateRangePicker.css';

interface Preset {
    label: string;
    years: number;
}

interface DateRangePickerProps {
    startDate: string;       // YYYY-MM-DD
    endDate: string;         // YYYY-MM-DD
    onChange: (start: string, end: string) => void;
    maxDate?: string;        // YYYY-MM-DD, defaults to today
    disabled?: boolean;
    presets?: Preset[];
}

const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토'];

function pad(n: number): string {
    return n < 10 ? `0${n}` : `${n}`;
}

function toDateStr(y: number, m: number, d: number): string {
    return `${y}-${pad(m + 1)}-${pad(d)}`;
}

function parseDate(s: string): { year: number; month: number; day: number } {
    const [y, m, d] = s.split('-').map(Number);
    return { year: y, month: m - 1, day: d };
}

function todayStr(): string {
    return new Date().toISOString().slice(0, 10);
}

function yearsAgo(n: number): string {
    const d = new Date();
    d.setFullYear(d.getFullYear() - n);
    return d.toISOString().slice(0, 10);
}

function formatDisplay(dateStr: string): string {
    const { year, month, day } = parseDate(dateStr);
    return `${year}.${pad(month + 1)}.${pad(day)}`;
}

/** 해당 월의 일 수 */
function daysInMonth(year: number, month: number): number {
    return new Date(year, month + 1, 0).getDate();
}

/** 해당 월 1일의 요일 (0=일, 6=토) */
function firstDayOfMonth(year: number, month: number): number {
    return new Date(year, month, 1).getDay();
}

interface SingleCalendarProps {
    year: number;
    month: number;
    selectedDate: string;
    maxDate: string;
    minDate?: string;
    onDayClick: (dateStr: string) => void;
    onPrev: () => void;
    onNext: () => void;
}

function SingleCalendar({
    year, month, selectedDate, maxDate, minDate, onDayClick, onPrev, onNext,
}: SingleCalendarProps) {
    const days = daysInMonth(year, month);
    const firstDay = firstDayOfMonth(year, month);
    const today = todayStr();

    const cells: (number | null)[] = [];
    for (let i = 0; i < firstDay; i++) cells.push(null);
    for (let d = 1; d <= days; d++) cells.push(d);
    while (cells.length < 42) cells.push(null);

    const monthLabel = `${year}년 ${month + 1}월`;

    return (
        <div className="drp-calendar">
            <div className="drp-calendar-header">
                <button className="drp-nav-btn" onClick={onPrev} type="button">
                    <ChevronLeft size={14} />
                </button>
                <span className="drp-month-label">{monthLabel}</span>
                <button className="drp-nav-btn" onClick={onNext} type="button">
                    <ChevronRight size={14} />
                </button>
            </div>

            <div className="drp-weekdays">
                {WEEKDAYS.map(w => (
                    <span key={w} className="drp-weekday">{w}</span>
                ))}
            </div>

            <div className="drp-days">
                {cells.map((day, idx) => {
                    if (day === null) {
                        return <span key={`e-${idx}`} className="drp-day drp-day-empty" />;
                    }

                    const dateStr = toDateStr(year, month, day);
                    const isDisabled = dateStr > maxDate || (minDate ? dateStr < minDate : false);
                    const isToday = dateStr === today;
                    const isSelected = dateStr === selectedDate;

                    const classes = [
                        'drp-day',
                        isDisabled && 'drp-day-disabled',
                        isToday && 'drp-day-today',
                        isSelected && 'drp-day-selected',
                    ].filter(Boolean).join(' ');

                    return (
                        <button
                            key={dateStr}
                            className={classes}
                            disabled={isDisabled}
                            onClick={() => !isDisabled && onDayClick(dateStr)}
                            type="button"
                        >
                            {day}
                        </button>
                    );
                })}
            </div>
        </div>
    );
}

type OpenTarget = 'start' | 'end' | null;

export function DateRangePicker({
    startDate, endDate, onChange, maxDate, disabled, presets,
}: DateRangePickerProps) {
    const effectiveMax = maxDate ?? todayStr();
    const [openTarget, setOpenTarget] = useState<OpenTarget>(null);
    const containerRef = useRef<HTMLDivElement>(null);

    // 시작일 캘린더 뷰 월
    const startParsed = parseDate(startDate);
    const [startViewYear, setStartViewYear] = useState(startParsed.year);
    const [startViewMonth, setStartViewMonth] = useState(startParsed.month);

    // 종료일 캘린더 뷰 월
    const endParsed = parseDate(endDate);
    const [endViewYear, setEndViewYear] = useState(endParsed.year);
    const [endViewMonth, setEndViewMonth] = useState(endParsed.month);

    // 외부 클릭 시 닫기
    useEffect(() => {
        function handleClickOutside(e: MouseEvent) {
            if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
                setOpenTarget(null);
            }
        }
        if (openTarget) {
            document.addEventListener('mousedown', handleClickOutside);
            return () => document.removeEventListener('mousedown', handleClickOutside);
        }
    }, [openTarget]);

    // props 변경 시 뷰 동기화
    useEffect(() => {
        const p = parseDate(startDate);
        setStartViewYear(p.year);
        setStartViewMonth(p.month);
    }, [startDate]);

    useEffect(() => {
        const p = parseDate(endDate);
        setEndViewYear(p.year);
        setEndViewMonth(p.month);
    }, [endDate]);

    const handleToggle = useCallback((target: 'start' | 'end') => {
        setOpenTarget(prev => prev === target ? null : target);
    }, []);

    const handleStartDayClick = useCallback((dateStr: string) => {
        if (dateStr > endDate) {
            onChange(dateStr, dateStr);
        } else {
            onChange(dateStr, endDate);
        }
        setOpenTarget(null);
    }, [endDate, onChange]);

    const handleEndDayClick = useCallback((dateStr: string) => {
        if (dateStr < startDate) {
            onChange(dateStr, dateStr);
        } else {
            onChange(startDate, dateStr);
        }
        setOpenTarget(null);
    }, [startDate, onChange]);

    const handlePreset = useCallback((years: number) => {
        onChange(yearsAgo(years), todayStr());
        setOpenTarget(null);
    }, [onChange]);

    // 시작 캘린더 네비게이션
    const startPrev = useCallback(() => {
        if (startViewMonth === 0) { setStartViewYear(y => y - 1); setStartViewMonth(11); }
        else { setStartViewMonth(m => m - 1); }
    }, [startViewMonth]);

    const startNext = useCallback(() => {
        if (startViewMonth === 11) { setStartViewYear(y => y + 1); setStartViewMonth(0); }
        else { setStartViewMonth(m => m + 1); }
    }, [startViewMonth]);

    // 종료 캘린더 네비게이션
    const endPrev = useCallback(() => {
        if (endViewMonth === 0) { setEndViewYear(y => y - 1); setEndViewMonth(11); }
        else { setEndViewMonth(m => m - 1); }
    }, [endViewMonth]);

    const endNext = useCallback(() => {
        if (endViewMonth === 11) { setEndViewYear(y => y + 1); setEndViewMonth(0); }
        else { setEndViewMonth(m => m + 1); }
    }, [endViewMonth]);

    return (
        <div className={`drp-container ${disabled ? 'drp-disabled' : ''}`} ref={containerRef}>
            <div className="drp-triggers">
                {/* 시작일 */}
                <div className="drp-trigger-wrap">
                    <button
                        className={`drp-trigger ${openTarget === 'start' ? 'drp-trigger-active' : ''}`}
                        onClick={() => !disabled && handleToggle('start')}
                        disabled={disabled}
                        type="button"
                    >
                        <Calendar size={12} className="drp-trigger-icon" />
                        <span className="drp-trigger-text">{formatDisplay(startDate)}</span>
                    </button>

                    {openTarget === 'start' && (
                        <div className="drp-popover drp-popover-start">
                            <div className="drp-popover-label">시작일</div>
                            <SingleCalendar
                                year={startViewYear}
                                month={startViewMonth}
                                selectedDate={startDate}
                                maxDate={effectiveMax}
                                onDayClick={handleStartDayClick}
                                onPrev={startPrev}
                                onNext={startNext}
                            />
                            {presets && presets.length > 0 && (
                                <div className="drp-presets">
                                    {presets.map(p => (
                                        <button
                                            key={p.label}
                                            className="drp-preset-btn"
                                            onClick={() => handlePreset(p.years)}
                                            type="button"
                                        >
                                            {p.label}
                                        </button>
                                    ))}
                                </div>
                            )}
                        </div>
                    )}
                </div>

                <span className="drp-separator">~</span>

                {/* 종료일 */}
                <div className="drp-trigger-wrap">
                    <button
                        className={`drp-trigger ${openTarget === 'end' ? 'drp-trigger-active' : ''}`}
                        onClick={() => !disabled && handleToggle('end')}
                        disabled={disabled}
                        type="button"
                    >
                        <Calendar size={12} className="drp-trigger-icon" />
                        <span className="drp-trigger-text">{formatDisplay(endDate)}</span>
                    </button>

                    {openTarget === 'end' && (
                        <div className="drp-popover drp-popover-end">
                            <div className="drp-popover-label">종료일</div>
                            <SingleCalendar
                                year={endViewYear}
                                month={endViewMonth}
                                selectedDate={endDate}
                                maxDate={effectiveMax}
                                minDate={startDate}
                                onDayClick={handleEndDayClick}
                                onPrev={endPrev}
                                onNext={endNext}
                            />
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
