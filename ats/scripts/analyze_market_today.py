#!/usr/bin/env python3
"""오늘 시장 진입 분석 — 지수 추세 기반 자동 전략 선택 결과.

사용법:
    cd ats && python3 scripts/analyze_market_today.py                  # SP500 (기본)
    cd ats && python3 scripts/analyze_market_today.py --market ndx     # NASDAQ
    cd ats && python3 scripts/analyze_market_today.py --market kospi   # KOSPI
    cd ats && python3 scripts/analyze_market_today.py --all            # SP500 + NDX 모두
"""
import sys, os, argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

# 마켓별 설정
MARKET_INFO = {
    "sp500": {"index": "^GSPC", "label": "S&P 500", "flag": "🇺🇸", "fmt": "${:,.1f}"},
    "ndx":   {"index": "^IXIC", "label": "NASDAQ", "flag": "🇺🇸", "fmt": "${:,.1f}"},
    "kospi": {"index": "^KS11", "label": "KOSPI",  "flag": "🇰🇷", "fmt": "₩{:,.1f}"},
}


def analyze_index_trend(market: str):
    """Part 1: 지수 데이터 페치 → 추세 분석 (엔진 _analyze_index_trend 로직 재현)."""
    info = MARKET_INFO[market]
    index_symbol = info["index"]

    print("=" * 70)
    print(f"  Part 1: {info['label']} 지수 ({index_symbol}) 추세 분석")
    print("=" * 70)

    end = datetime.now()
    start = end - timedelta(days=400)
    print(f"\n  데이터 기간: {start.strftime('%Y-%m-%d')} ~ {end.strftime('%Y-%m-%d')}")

    df = yf.download(index_symbol, start=start, end=end, progress=False, auto_adjust=False)
    if df.empty:
        print(f"  ❌ {index_symbol} 데이터 다운로드 실패")
        return None

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]

    closes = df["Close"]
    highs = df["High"]
    lows = df["Low"]
    n = len(closes)
    current_close = closes.iloc[-1]
    print(f"  데이터 수: {n}일")
    print(f"  최근 종가: {info['fmt'].format(current_close)}")

    # ── MA Alignment ──
    ma20 = closes.rolling(20).mean().iloc[-1]
    ma50 = closes.rolling(50).mean().iloc[-1]
    ma200 = closes.rolling(200).mean().iloc[-1] if n >= 200 else None

    print(f"\n  📊 이동평균 분석:")
    print(f"     현재가: {info['fmt'].format(current_close)}")
    print(f"     MA20:   {info['fmt'].format(ma20)} ({'↑' if current_close > ma20 else '↓'})")
    print(f"     MA50:   {info['fmt'].format(ma50)} ({'↑' if current_close > ma50 else '↓'})")
    if ma200 is not None:
        print(f"     MA200:  {info['fmt'].format(ma200)} ({'↑' if current_close > ma200 else '↓'})")

    if ma200 is not None and not pd.isna(ma200):
        if current_close > ma50 > ma200:
            ma_state = "ALIGNED_BULL"
        elif current_close < ma50 < ma200:
            ma_state = "ALIGNED_BEAR"
        else:
            ma_state = "MIXED"
    elif current_close > ma50:
        ma_state = "ALIGNED_BULL"
    else:
        ma_state = "MIXED"
    print(f"     MA 정렬: {ma_state}")

    # ── RSI(14) ──
    delta = closes.diff()
    gain = delta.where(delta > 0, 0.0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
    rs = gain.iloc[-1] / loss.iloc[-1] if loss.iloc[-1] > 0 else 100
    rsi = 100.0 - (100.0 / (1.0 + rs))
    print(f"\n  📈 모멘텀 지표:")
    print(f"     RSI(14): {rsi:.1f}")

    # ── ADX(14) ──
    try:
        from simulation.engine import _compute_adx
        adx_s, _, _ = _compute_adx(
            pd.Series(highs.values), pd.Series(lows.values), pd.Series(closes.values), 14
        )
        adx = float(adx_s.iloc[-1]) if pd.notna(adx_s.iloc[-1]) else 20.0
    except Exception as e:
        adx = 20.0
        print(f"     ADX 계산 오류: {e}")
    print(f"     ADX(14): {adx:.1f}")

    # ── MACD(12, 26, 9) ──
    ema12 = closes.ewm(span=12, adjust=False).mean()
    ema26 = closes.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    macd_hist = macd_line.iloc[-1] - signal_line.iloc[-1]
    macd_positive = macd_hist > 0
    print(f"     MACD Histogram: {macd_hist:.2f} ({'양전환' if macd_positive else '음전환'})")

    # ── Momentum Score ──
    rsi_norm = min(max((rsi - 30) / 40 * 40, 0), 40)
    adx_norm = min(max(adx / 50 * 35, 0), 35)
    macd_bonus = 25 if macd_positive else 0
    momentum_score = min(max(rsi_norm + adx_norm + macd_bonus, 0), 100)
    print(f"     Momentum Score: {momentum_score:.1f}/100 (RSI:{rsi_norm:.0f} + ADX:{adx_norm:.0f} + MACD:{macd_bonus})")

    # ── VIX ──
    print(f"\n  🌡️  변동성 분석:")
    vix_data = yf.download("^VIX", start=start, end=end, progress=False, auto_adjust=False)
    if isinstance(vix_data.columns, pd.MultiIndex):
        vix_data.columns = [c[0] if isinstance(c, tuple) else c for c in vix_data.columns]

    if not vix_data.empty:
        vix_close = vix_data["Close"]
        vix_ema20 = vix_close.ewm(span=20, adjust=False).mean().iloc[-1]
        vix_current = vix_close.iloc[-1]
        print(f"     VIX 현재: {vix_current:.1f}")
        print(f"     VIX EMA20: {vix_ema20:.1f}")
        if vix_ema20 < 16:
            volatility_state = "LOW"
        elif vix_ema20 < 22:
            volatility_state = "NORMAL"
        elif vix_ema20 < 30:
            volatility_state = "HIGH"
        else:
            volatility_state = "EXTREME"
        print(f"     변동성 상태: {volatility_state}")
    else:
        vix_ema20 = 20.0
        volatility_state = "NORMAL"
        print("     VIX 데이터 미수신 → NORMAL 가정")

    # ── Final Trend ──
    if ma_state == "ALIGNED_BULL" and adx > 30 and rsi > 55:
        trend = "STRONG_BULL"
    elif ma_state == "ALIGNED_BULL" or (
        (ma200 is None or current_close > ma200) and momentum_score > 55
    ):
        trend = "BULL"
    elif ma_state == "ALIGNED_BEAR" and volatility_state in ("HIGH", "EXTREME"):
        trend = "CRISIS"
    elif ma_state == "ALIGNED_BEAR":
        trend = "BEAR"
    else:
        trend = "NEUTRAL"

    print(f"\n  {'='*50}")
    print(f"  🎯 최종 지수 추세: {trend}")
    print(f"  {'='*50}")

    return {
        "trend": trend, "ma_alignment": ma_state,
        "momentum_score": round(momentum_score, 1),
        "volatility_state": volatility_state,
        "rsi": round(rsi, 1), "adx": round(adx, 1),
        "macd_hist": round(float(macd_hist), 2),
        "vix_ema20": round(float(vix_ema20), 1),
        "close": round(float(current_close), 1),
    }


def show_strategy_weights(trend: str):
    """Part 2: 추세 → INDEX_TREND_STRATEGY_WEIGHTS 매핑."""
    from simulation.engine import INDEX_TREND_STRATEGY_WEIGHTS, REGIME_STRATEGY_WEIGHTS

    print(f"\n{'=' * 70}")
    print(f"  Part 2: 전략 비중 결정 (INDEX_TREND_STRATEGY_WEIGHTS)")
    print(f"{'=' * 70}")

    weights = INDEX_TREND_STRATEGY_WEIGHTS.get(trend, INDEX_TREND_STRATEGY_WEIGHTS["NEUTRAL"])
    print(f"\n  지수 추세 '{trend}' → 적용 비중:")
    for strat, w in sorted(weights.items(), key=lambda x: -x[1]):
        bar = "█" * int(w * 40)
        print(f"     {strat:20s}: {w:5.0%}  {bar}")

    print(f"\n  참고 — 기존 정적 REGIME_STRATEGY_WEIGHTS (레짐별):")
    for regime, rw in REGIME_STRATEGY_WEIGHTS.items():
        parts = ", ".join(f"{s}:{v:.0%}" for s, v in rw.items())
        print(f"     {regime:12s}: {parts}")


def run_recent_backtest(market: str):
    """Part 3: 최근 백테스트 실행."""
    info = MARKET_INFO[market]
    today = datetime.now().strftime("%Y%m%d")

    print(f"\n{'=' * 70}")
    print(f"  Part 3: 최근 {info['label']} 백테스트 (2026-01-01 ~ {today[:4]}-{today[4:6]}-{today[6:]})")
    print(f"{'=' * 70}")

    from backtest.historical_engine import HistoricalBacktester

    bt = HistoricalBacktester.from_optimal(
        market=market,
        start_date="20260101",
        end_date=today,
        strategy_mode="multi",
    )

    print("\n  백테스트 실행 중...")
    result = bt.run()
    engine = bt.engine

    # ── 전체 성과 ──
    print(f"\n  📊 전체 성과:")
    print(f"     수익률:   {result.total_return:+.2%}")
    print(f"     Sharpe:   {result.sharpe_ratio:.2f}")
    print(f"     MDD:      {result.max_drawdown:.2%}")
    print(f"     Win Rate: {result.win_rate:.1%}")
    print(f"     총 거래:  {result.total_trades}건")
    print(f"     PF:       {result.profit_factor:.2f}")

    # ── 엔진 최종 상태 ──
    print(f"\n  🔍 엔진 최종 상태:")
    print(f"     Market Regime: {engine._market_regime}")
    if engine._index_trend:
        it = engine._index_trend
        print(f"     Index Trend:   {it.get('trend', 'N/A')}")
        print(f"     MA Alignment:  {it.get('ma_alignment', 'N/A')}")
        print(f"     Momentum:      {it.get('momentum_score', 'N/A')}")
        print(f"     Volatility:    {it.get('volatility_state', 'N/A')}")
    else:
        print(f"     Index Trend:   미분석")

    if engine._strategy_allocator:
        print(f"\n     활성 전략 비중:")
        for s, w in sorted(engine._strategy_allocator.weights.items(), key=lambda x: -x[1]):
            print(f"       {s:20s}: {w:.1%}")

    # ── 현재 보유 포지션 ──
    is_krw = market == "kospi"
    print(f"\n  📌 현재 보유 포지션 ({len(engine.positions)}개):")
    if engine.positions:
        for code, pos in engine.positions.items():
            name = pos.stock_name or engine._stock_names.get(code, code)
            entry = pos.entry_price
            cur = pos.current_price
            pnl = pos.pnl_pct
            days = pos.days_held
            tag = pos.strategy_tag or ''
            if is_krw:
                print(f"     {name:12s} ({code:>10s}) | 진입: ₩{entry:>10,.0f} | 현재: ₩{cur:>10,.0f} | PnL: {pnl:+.1f}% | {days}일 | {tag}")
            else:
                print(f"     {name:12s} ({code:>10s}) | 진입: ${entry:>8,.2f} | 현재: ${cur:>8,.2f} | PnL: {pnl:+.1f}% | {days}일 | {tag}")
    else:
        print("     (보유 포지션 없음)")

    # ── 최근 청산 거래 ──
    print(f"\n  📋 최근 청산 거래 (최근 10건):")
    recent_trades = engine.closed_trades[-10:] if engine.closed_trades else []
    if recent_trades:
        for t in recent_trades:
            name = t.stock_name or t.stock_code
            pnl_pct = t.pnl_pct
            strategy = t.strategy_tag or ''
            exit_reason = t.exit_reason or ''
            print(f"     {name:12s} | {t.entry_date} → {t.exit_date} | PnL: {pnl_pct:+.1f}% | 전략: {strategy} | 청산: {exit_reason}")
    else:
        print("     (청산 거래 없음)")

    # ── Phase Stats ──
    ps = engine._phase_stats
    print(f"\n  📈 Phase Funnel:")
    print(f"     Phase 0 스캔:     {ps.get('scanned', 0)}")
    print(f"     Phase 1 추세:     {ps.get('trend_passed', 0)}")
    print(f"     Phase 2 단계:     {ps.get('stage_passed', 0)}")
    print(f"     Phase 3 시그널:   {ps.get('signal_generated', 0)}")
    print(f"     Phase 4 리스크:   {ps.get('risk_passed', 0)}")
    print(f"     진입 체결:        {ps.get('entries_executed', 0)}")
    print(f"     지수추세 업데이트: {ps.get('index_trend_updates', 0)}")

    return result, engine


def analyze_market(market: str):
    """단일 마켓 전체 분석."""
    info = MARKET_INFO[market]
    print("\n" + info["flag"] * 5 + f" {info['label']} 시장 진입 분석 " + info["flag"] * 5)
    print(f"  분석 시점: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print()

    # Part 1: 지수 추세
    trend_result = analyze_index_trend(market)
    if not trend_result:
        print("  분석 실패: 지수 데이터를 가져올 수 없습니다.")
        return

    # Part 2: 전략 비중
    show_strategy_weights(trend_result["trend"])

    # Part 3: 백테스트
    result, engine = run_recent_backtest(market)

    # Summary
    fmt = info["fmt"]
    print(f"\n{'=' * 70}")
    print(f"  🎯 {info['label']} 종합 분석 요약")
    print(f"{'=' * 70}")
    print(f"  지수 현재가:             {fmt.format(trend_result['close'])}")
    print(f"  지수 추세 분류:          {trend_result['trend']}")
    print(f"  MA 정렬:                {trend_result['ma_alignment']}")
    print(f"  RSI / ADX / MACD:       {trend_result['rsi']} / {trend_result['adx']} / {trend_result['macd_hist']}")
    print(f"  VIX EMA20:              {trend_result['vix_ema20']} → {trend_result['volatility_state']}")
    print(f"  적용 전략:              INDEX_TREND_STRATEGY_WEIGHTS['{trend_result['trend']}']")
    print(f"  최근 2.5개월 수익률:     {result.total_return:+.2%}")
    print(f"  현재 보유 종목:          {len(engine.positions)}개")
    print()


def main():
    parser = argparse.ArgumentParser(description="시장 진입 분석 — 지수 추세 기반 자동 전략 선택")
    parser.add_argument("--market", choices=["sp500", "ndx", "kospi"], default="sp500",
                        help="분석할 마켓 (기본: sp500)")
    parser.add_argument("--all", action="store_true",
                        help="SP500 + NDX 모두 분석")
    args = parser.parse_args()

    if args.all:
        for m in ["sp500", "ndx"]:
            analyze_market(m)
            print("\n" + "─" * 70 + "\n")
    else:
        analyze_market(args.market)


if __name__ == "__main__":
    main()
