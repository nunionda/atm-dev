import type {
    SystemState, Position, Order, Signal,
    RiskMetrics, RiskEvent,
    PerformanceSummary, EquityPoint, TradeRecord,
} from './api';

// config.yaml 기반 현실적 Mock 데이터
// 초기 자본금: 1억원, KOSPI200 모멘텀 스윙 전략

export function mockSystemState(): SystemState {
    return {
        status: 'RUNNING',
        mode: 'PAPER',
        started_at: '2026-03-02T08:50:00',
        market_phase: 'OPEN',
        next_scan_at: '2026-03-02T10:40:00',
        total_equity: 102_450_000,
        cash: 24_890_000,
        invested: 77_560_000,
        daily_pnl: 385_000,
        daily_pnl_pct: 0.38,
        position_count: 5,
        max_positions: 10,
    };
}

export function mockPositions(): Position[] {
    return [
        {
            id: 'pos-001',
            stock_code: '005930',
            stock_name: '삼성전자',
            status: 'ACTIVE',
            quantity: 120,
            entry_price: 72_500,
            current_price: 73_800,
            pnl: 156_000,
            pnl_pct: 1.79,
            stop_loss: 70_325,
            take_profit: 77_575,
            trailing_stop: 71_586,
            highest_price: 73_800,
            entry_date: '2026-02-26',
            days_held: 3,
            max_holding_days: 10,
            weight_pct: 8.64,
        },
        {
            id: 'pos-002',
            stock_code: '000660',
            stock_name: 'SK하이닉스',
            status: 'ACTIVE',
            quantity: 50,
            entry_price: 198_000,
            current_price: 203_500,
            pnl: 275_000,
            pnl_pct: 2.78,
            stop_loss: 192_060,
            take_profit: 211_860,
            trailing_stop: 197_395,
            highest_price: 203_500,
            entry_date: '2026-02-25',
            days_held: 4,
            max_holding_days: 10,
            weight_pct: 9.93,
        },
        {
            id: 'pos-003',
            stock_code: '035420',
            stock_name: 'NAVER',
            status: 'ACTIVE',
            quantity: 40,
            entry_price: 215_000,
            current_price: 211_500,
            pnl: -140_000,
            pnl_pct: -1.63,
            stop_loss: 208_550,
            take_profit: 230_050,
            trailing_stop: 208_550,
            highest_price: 217_200,
            entry_date: '2026-02-27',
            days_held: 2,
            max_holding_days: 10,
            weight_pct: 8.26,
        },
        {
            id: 'pos-004',
            stock_code: '006400',
            stock_name: '삼성SDI',
            status: 'ACTIVE',
            quantity: 25,
            entry_price: 412_000,
            current_price: 418_500,
            pnl: 162_500,
            pnl_pct: 1.58,
            stop_loss: 399_640,
            take_profit: 440_840,
            trailing_stop: 405_945,
            highest_price: 418_500,
            entry_date: '2026-02-28',
            days_held: 1,
            max_holding_days: 10,
            weight_pct: 10.21,
        },
        {
            id: 'pos-005',
            stock_code: '051910',
            stock_name: 'LG화학',
            status: 'PENDING',
            quantity: 15,
            entry_price: 358_000,
            current_price: 358_000,
            pnl: 0,
            pnl_pct: 0,
            stop_loss: 347_260,
            take_profit: 383_060,
            trailing_stop: 347_260,
            highest_price: 358_000,
            entry_date: '2026-03-02',
            days_held: 0,
            max_holding_days: 10,
            weight_pct: 5.24,
        },
    ];
}

export function mockOrders(): Order[] {
    return [
        {
            id: 'ord-010',
            stock_code: '051910',
            stock_name: 'LG화학',
            side: 'BUY',
            order_type: 'LIMIT',
            status: 'PENDING',
            price: 358_000,
            filled_price: null,
            quantity: 15,
            filled_quantity: 0,
            created_at: '2026-03-02T10:15:00',
            filled_at: null,
            reason: 'PS1 골든크로스 + CF1 RSI 회복',
        },
        {
            id: 'ord-009',
            stock_code: '005930',
            stock_name: '삼성전자',
            side: 'BUY',
            order_type: 'LIMIT',
            status: 'FILLED',
            price: 72_500,
            filled_price: 72_500,
            quantity: 120,
            filled_quantity: 120,
            created_at: '2026-02-26T09:32:00',
            filled_at: '2026-02-26T09:33:15',
            reason: 'PS1 골든크로스 + CF2 거래량 돌파',
        },
        {
            id: 'ord-008',
            stock_code: '000660',
            stock_name: 'SK하이닉스',
            side: 'BUY',
            order_type: 'LIMIT',
            status: 'FILLED',
            price: 198_000,
            filled_price: 198_000,
            quantity: 50,
            filled_quantity: 50,
            created_at: '2026-02-25T10:05:00',
            filled_at: '2026-02-25T10:06:22',
            reason: 'PS1 골든크로스 + CF1 RSI 회복',
        },
        {
            id: 'ord-007',
            stock_code: '035720',
            stock_name: '카카오',
            side: 'SELL',
            order_type: 'MARKET',
            status: 'FILLED',
            price: 48_200,
            filled_price: 48_150,
            quantity: 60,
            filled_quantity: 60,
            created_at: '2026-02-25T14:22:00',
            filled_at: '2026-02-25T14:22:03',
            reason: 'ES1 손절 -3% 도달',
        },
        {
            id: 'ord-006',
            stock_code: '055550',
            stock_name: '신한지주',
            side: 'SELL',
            order_type: 'LIMIT',
            status: 'FILLED',
            price: 52_800,
            filled_price: 52_800,
            quantity: 80,
            filled_quantity: 80,
            created_at: '2026-02-24T13:45:00',
            filled_at: '2026-02-24T13:46:10',
            reason: 'ES2 익절 +7% 도달',
        },
    ];
}

export function mockSignals(): Signal[] {
    return [
        {
            id: 'sig-001',
            stock_code: '051910',
            stock_name: 'LG화학',
            type: 'BUY',
            price: 358_000,
            reason: 'PS1 골든크로스 (5MA > 20MA) + CF1 RSI(14) 38.5 회복구간',
            strength: 82,
            detected_at: '2026-03-02T10:10:00',
        },
        {
            id: 'sig-002',
            stock_code: '003670',
            stock_name: '포스코퓨처엠',
            type: 'BUY',
            price: 268_500,
            reason: 'PS1 골든크로스 + CF2 거래량 1.8배 돌파',
            strength: 75,
            detected_at: '2026-03-02T10:10:00',
        },
        {
            id: 'sig-003',
            stock_code: '035420',
            stock_name: 'NAVER',
            type: 'SELL',
            price: 211_500,
            reason: 'ES3 트레일링스탑 접근 (-2.6%, 한도 -3%)',
            strength: 60,
            detected_at: '2026-03-02T10:10:00',
        },
    ];
}

export function mockRiskMetrics(): RiskMetrics {
    return {
        daily_pnl_pct: 0.38,
        daily_loss_limit: -3.0,
        mdd: -2.8,
        mdd_limit: -10.0,
        cash_ratio: 24.3,
        min_cash_ratio: 20.0,
        consecutive_stops: 1,
        max_consecutive_stops: 3,
        daily_trade_amount: 5_370_000,
        max_daily_trade_amount: 10_000_000,
        is_trading_halted: false,
        halt_reason: null,
    };
}

export function mockRiskEvents(): RiskEvent[] {
    return [
        {
            id: 'evt-001',
            type: 'INFO',
            message: '시스템 정상 가동 시작',
            value: null,
            limit: null,
            timestamp: '2026-03-02T08:50:00',
        },
        {
            id: 'evt-002',
            type: 'INFO',
            message: '매수 시그널 감지: LG화학 (PS1+CF1)',
            value: null,
            limit: null,
            timestamp: '2026-03-02T10:10:00',
        },
        {
            id: 'evt-003',
            type: 'WARNING',
            message: 'NAVER 트레일링스탑 접근 (-2.6%)',
            value: -2.6,
            limit: -3.0,
            timestamp: '2026-03-02T10:12:00',
        },
        {
            id: 'evt-004',
            type: 'INFO',
            message: 'LG화학 매수 주문 발행 (지정가 ₩358,000)',
            value: null,
            limit: null,
            timestamp: '2026-03-02T10:15:00',
        },
        {
            id: 'evt-005',
            type: 'WARNING',
            message: '현금비율 24.3% — 최소 기준(20%) 근접',
            value: 24.3,
            limit: 20.0,
            timestamp: '2026-03-02T10:16:00',
        },
    ];
}

export function mockPerformanceSummary(): PerformanceSummary {
    return {
        total_return_pct: 2.45,
        total_trades: 23,
        win_rate: 60.87,
        avg_win_pct: 4.2,
        avg_loss_pct: -2.1,
        profit_factor: 1.85,
        sharpe_ratio: 1.42,
        max_drawdown_pct: -4.8,
        avg_holding_days: 4.3,
        best_trade_pct: 7.0,
        worst_trade_pct: -3.0,
    };
}

export function mockEquityCurve(): EquityPoint[] {
    const base = 100_000_000;
    const points: EquityPoint[] = [];
    let equity = base;
    let peak = base;

    const startDate = new Date('2026-01-05');
    for (let i = 0; i < 40; i++) {
        const date = new Date(startDate);
        date.setDate(date.getDate() + i);
        if (date.getDay() === 0 || date.getDay() === 6) continue;

        const dailyReturn = (Math.random() - 0.45) * 0.015;
        equity = equity * (1 + dailyReturn);
        peak = Math.max(peak, equity);
        const drawdown = ((equity - peak) / peak) * 100;

        points.push({
            date: date.toISOString().split('T')[0],
            equity: Math.round(equity),
            drawdown_pct: Math.round(drawdown * 100) / 100,
        });
    }
    return points;
}

export function mockTradeHistory(): TradeRecord[] {
    return [
        {
            id: 'trade-001',
            stock_code: '055550',
            stock_name: '신한지주',
            entry_date: '2026-02-17',
            exit_date: '2026-02-24',
            entry_price: 49_350,
            exit_price: 52_800,
            quantity: 80,
            pnl: 276_000,
            pnl_pct: 6.99,
            exit_reason: 'ES2 익절 +7%',
            holding_days: 5,
        },
        {
            id: 'trade-002',
            stock_code: '035720',
            stock_name: '카카오',
            entry_date: '2026-02-20',
            exit_date: '2026-02-25',
            entry_price: 49_650,
            exit_price: 48_150,
            quantity: 60,
            pnl: -90_000,
            pnl_pct: -3.02,
            exit_reason: 'ES1 손절 -3%',
            holding_days: 3,
        },
        {
            id: 'trade-003',
            stock_code: '068270',
            stock_name: '셀트리온',
            entry_date: '2026-02-12',
            exit_date: '2026-02-19',
            entry_price: 185_500,
            exit_price: 193_200,
            quantity: 20,
            pnl: 154_000,
            pnl_pct: 4.15,
            exit_reason: 'ES4 데드크로스',
            holding_days: 5,
        },
        {
            id: 'trade-004',
            stock_code: '105560',
            stock_name: 'KB금융',
            entry_date: '2026-02-10',
            exit_date: '2026-02-18',
            entry_price: 68_200,
            exit_price: 72_974,
            quantity: 40,
            pnl: 190_960,
            pnl_pct: 7.0,
            exit_reason: 'ES2 익절 +7%',
            holding_days: 6,
        },
        {
            id: 'trade-005',
            stock_code: '012330',
            stock_name: '현대모비스',
            entry_date: '2026-02-05',
            exit_date: '2026-02-14',
            entry_price: 232_000,
            exit_price: 225_040,
            quantity: 12,
            pnl: -83_520,
            pnl_pct: -3.0,
            exit_reason: 'ES1 손절 -3%',
            holding_days: 7,
        },
        {
            id: 'trade-006',
            stock_code: '028260',
            stock_name: '삼성물산',
            entry_date: '2026-02-03',
            exit_date: '2026-02-12',
            entry_price: 128_500,
            exit_price: 133_640,
            quantity: 25,
            pnl: 128_500,
            pnl_pct: 4.0,
            exit_reason: 'ES5 보유기간 초과 10일',
            holding_days: 7,
        },
    ];
}
