#!/usr/bin/env python3
"""
3-Market Alpha/Beta Verification & Losing Trade Analysis

SP500, NASDAQ100, KOSPI200 각 시장별로 백테스트 실행 후:
1. 알파/베타 검증 (Sharpe, Sortino, 벤치마크 대비 수익률)
2. 손절 종목 상세 분석 (exit reason별, 전략별, 레짐별, 종목별)
3. 패턴 식별 및 개선 포인트 도출
"""

import os
import sys
import json
from collections import defaultdict, Counter
from datetime import datetime

# 프로젝트 루트 설정
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(project_root, "ats"))

from backtest.historical_engine import HistoricalBacktester


def run_backtest(market: str, strategy: str = "multi") -> dict:
    """단일 마켓 백테스트 실행 및 결과 반환"""
    bt = HistoricalBacktester.from_optimal(
        market=market,
        start_date="20240101",
        end_date="20260228",
        strategy_mode=strategy,
    )
    result = bt.run()

    # 엔진에서 closed_trades 추출
    engine = bt.engine
    closed_trades = []
    for t in engine.closed_trades:
        closed_trades.append({
            "stock_code": t.stock_code,
            "stock_name": t.stock_name,
            "entry_date": t.entry_date,
            "exit_date": t.exit_date,
            "entry_price": t.entry_price,
            "exit_price": t.exit_price,
            "quantity": t.quantity,
            "pnl": t.pnl,
            "pnl_pct": t.pnl_pct,
            "exit_reason": t.exit_reason,
            "holding_days": t.holding_days,
            "strategy_tag": getattr(t, "strategy_tag", "unknown"),
        })

    return {
        "market": market,
        "strategy": strategy,
        "result": result,
        "closed_trades": closed_trades,
        "engine": engine,
    }


def analyze_alpha_beta(data: dict):
    """알파/베타 로직 검증"""
    r = data["result"]
    market = data["market"]
    trades = data["closed_trades"]

    print(f"\n{'='*70}")
    print(f"  📊 알파/베타 분석: {market.upper()}")
    print(f"{'='*70}")

    # 핵심 성과 지표 — 메트릭 값은 비율(decimal) 형태 → ×100 표시
    print(f"\n  [핵심 지표]")
    print(f"  총 수익률     : {r.total_return*100:+.2f}%")
    print(f"  CAGR          : {r.cagr*100:.2f}%")
    print(f"  Sharpe Ratio  : {r.sharpe_ratio:.2f}")
    print(f"  Sortino Ratio : {r.sortino_ratio:.2f}")
    print(f"  Profit Factor : {r.profit_factor:.2f}")
    print(f"  Win Rate      : {r.win_rate*100:.1f}%")
    print(f"  Max Drawdown  : {r.max_drawdown*100:.2f}%")
    print(f"  총 거래 수    : {r.total_trades}")
    print(f"  Best Trade    : {r.best_trade_pct*100:+.2f}%")
    print(f"  Worst Trade   : {r.worst_trade_pct*100:+.2f}%")
    print(f"  Avg Win       : {r.avg_win_pct*100:+.2f}%")
    print(f"  Avg Loss      : {r.avg_loss_pct*100:+.2f}%")

    # 연속 손실
    if hasattr(r, 'max_consecutive_losses'):
        print(f"  최대 연속 손실 : {r.max_consecutive_losses}회")
    if hasattr(r, 'max_consecutive_wins'):
        print(f"  최대 연속 승리 : {r.max_consecutive_wins}회")

    # Phase Stats (dataclass → vars())
    if hasattr(r, 'phase_stats') and r.phase_stats:
        ps = vars(r.phase_stats) if not isinstance(r.phase_stats, dict) else r.phase_stats
        print(f"\n  [Phase Funnel]")
        print(f"  총 스캔       : {ps.get('total_scans', 0)}")
        print(f"  Phase 1 거부  : {ps.get('phase1_trend_rejects', 0)}")
        print(f"  Phase 3 거부  : {ps.get('phase3_no_primary', 0)}")
        print(f"  Phase 4 차단  : {ps.get('phase4_risk_blocks', 0)}")
        print(f"  MR 진입       : {ps.get('mr_entries', 0)}")
        print(f"  SMC 진입      : {ps.get('smc_entries', 0)}")
        print(f"  BRT 돌파 감지 : {ps.get('brt_breakouts_detected', 0)}")

        # exit별 카운트
        exit_keys = [k for k in ps.keys() if k.startswith("es")]
        if exit_keys:
            print(f"\n  [Exit 통계]")
            for ek in sorted(exit_keys):
                if ps[ek] > 0:
                    print(f"  {ek:25s}: {ps[ek]:4d}회")

    # 레짐 전환 정보
    if hasattr(r, 'regime_transitions') and r.regime_transitions:
        regimes = r.regime_transitions
        try:
            regime_counts = Counter()
            for rt in regimes:
                if isinstance(rt, dict):
                    regime_counts[rt.get("regime", rt.get("to", "?"))] += 1
                elif hasattr(rt, 'regime'):
                    regime_counts[rt.regime] += 1
                elif hasattr(rt, 'to'):
                    regime_counts[rt.to] += 1
                else:
                    regime_counts[str(rt)] += 1
            print(f"\n  [레짐 전환] 총 {len(regimes)}회")
            for reg, cnt in regime_counts.most_common():
                print(f"  {reg:15s}: {cnt}회")
        except Exception as e:
            print(f"\n  [레짐 전환] 총 {len(regimes)}회 (상세: {e})")


def analyze_losing_trades(data: dict):
    """손절 종목 상세 분석"""
    trades = data["closed_trades"]
    market = data["market"]
    engine = data["engine"]

    losers = [t for t in trades if t["pnl"] < 0]
    winners = [t for t in trades if t["pnl"] > 0]

    print(f"\n{'='*70}")
    print(f"  🔴 손절 종목 분석: {market.upper()}")
    print(f"{'='*70}")

    total = len(trades)
    n_loss = len(losers)
    n_win = len(winners)
    print(f"\n  전체 {total}건 → 승리 {n_win}건 ({n_win/total*100:.1f}%) / 패배 {n_loss}건 ({n_loss/total*100:.1f}%)")

    if not losers:
        print("  손절 트레이드 없음")
        return

    total_loss = sum(t["pnl"] for t in losers)
    total_gain = sum(t["pnl"] for t in winners) if winners else 0
    avg_loss_pct = sum(t["pnl_pct"] for t in losers) / len(losers)
    avg_win_pct = sum(t["pnl_pct"] for t in winners) / len(winners) if winners else 0

    currency_sym = engine.currency_symbol
    print(f"  총 손실 금액    : {currency_sym}{total_loss:,.0f}")
    print(f"  총 이익 금액    : {currency_sym}{total_gain:,.0f}")
    print(f"  손실 평균 %     : {avg_loss_pct:+.2f}%")
    print(f"  이익 평균 %     : {avg_win_pct:+.2f}%")

    # 1. Exit Reason별 분포
    print(f"\n  ── Exit Reason별 분포 ──")
    reason_groups = defaultdict(list)
    for t in losers:
        # exit reason에서 핵심 키워드 추출
        reason = t["exit_reason"]
        if "ES1" in reason or "손절" in reason:
            key = "ES1_STOP_LOSS(-5%)"
        elif "ATR" in reason and ("SL" in reason or "손절" in reason.upper()):
            key = "ATR_STOP_LOSS"
        elif "트레일링" in reason or "ES3" in reason:
            key = "ES3_TRAILING_STOP"
        elif "보유기간" in reason or "ES5" in reason:
            key = "ES5_MAX_HOLDING"
        elif "CHoCH" in reason or "CHOCH" in reason:
            key = "CHOCH_EXIT"
        elif "데드크로스" in reason or "ES4" in reason:
            key = "ES4_DEAD_CROSS"
        elif "리밸런스" in reason or "ES7" in reason:
            key = "ES7_REBALANCE"
        elif "과매수" in reason or "OB" in reason:
            key = "OVERBOUGHT_EXIT"
        elif "TP" in reason or "익절" in reason:
            key = "TAKE_PROFIT(소폭손실)"
        else:
            key = reason[:30]
        reason_groups[key].append(t)

    for reason, grp in sorted(reason_groups.items(), key=lambda x: len(x[1]), reverse=True):
        avg_pnl = sum(t["pnl_pct"] for t in grp) / len(grp)
        avg_hold = sum(t["holding_days"] for t in grp) / len(grp)
        total_pnl = sum(t["pnl"] for t in grp)
        print(f"  {reason:25s}: {len(grp):3d}건 | 평균 {avg_pnl:+.2f}% | 평균보유 {avg_hold:.0f}일 | 합계 {currency_sym}{total_pnl:,.0f}")

    # 2. 종목별 손실 빈도 (Top 10)
    print(f"\n  ── 손실 빈도 Top 10 종목 ──")
    stock_loss = defaultdict(lambda: {"count": 0, "total_pnl": 0, "pcts": []})
    for t in losers:
        key = f"{t['stock_code']} ({t['stock_name']})"
        stock_loss[key]["count"] += 1
        stock_loss[key]["total_pnl"] += t["pnl"]
        stock_loss[key]["pcts"].append(t["pnl_pct"])

    top_losers = sorted(stock_loss.items(), key=lambda x: x[1]["count"], reverse=True)[:10]
    for stock, info in top_losers:
        avg_pct = sum(info["pcts"]) / len(info["pcts"])
        print(f"  {stock:35s}: {info['count']:2d}회 | 평균 {avg_pct:+.2f}% | 합계 {currency_sym}{info['total_pnl']:,.0f}")

    # 3. 전략별 분석
    print(f"\n  ── 전략별 손실 분석 ──")
    strat_groups = defaultdict(list)
    for t in losers:
        strat_groups[t.get("strategy_tag", "unknown")].append(t)

    for strat, grp in sorted(strat_groups.items(), key=lambda x: len(x[1]), reverse=True):
        avg_pnl = sum(t["pnl_pct"] for t in grp) / len(grp)
        total_pnl = sum(t["pnl"] for t in grp)
        # 해당 전략의 승리 트레이드
        strat_wins = [t for t in winners if t.get("strategy_tag") == strat]
        win_rate = len(strat_wins) / (len(grp) + len(strat_wins)) * 100 if (len(grp) + len(strat_wins)) > 0 else 0
        print(f"  {strat:20s}: {len(grp):3d}건 손실 | 승률 {win_rate:.1f}% | 평균 {avg_pnl:+.2f}% | 합계 {currency_sym}{total_pnl:,.0f}")

    # 4. 보유기간별 분석
    print(f"\n  ── 보유기간별 손실 분석 ──")
    hold_bins = [(0, 1, "당일~1일"), (2, 5, "2~5일"), (6, 10, "6~10일"),
                 (11, 20, "11~20일"), (21, 40, "21~40일"), (41, 999, "41일+")]
    for lo, hi, label in hold_bins:
        grp = [t for t in losers if lo <= t["holding_days"] <= hi]
        if grp:
            avg_pnl = sum(t["pnl_pct"] for t in grp) / len(grp)
            total_pnl = sum(t["pnl"] for t in grp)
            print(f"  {label:12s}: {len(grp):3d}건 | 평균 {avg_pnl:+.2f}% | 합계 {currency_sym}{total_pnl:,.0f}")

    # 5. 월별 손실 분포
    print(f"\n  ── 월별 손실 발생 빈도 ──")
    month_loss = defaultdict(lambda: {"count": 0, "total_pnl": 0})
    for t in losers:
        # exit_date format: YYYYMMDD or YYYY-MM-DD
        d = t["exit_date"].replace("-", "")
        if len(d) >= 6:
            ym = f"{d[:4]}-{d[4:6]}"
            month_loss[ym]["count"] += 1
            month_loss[ym]["total_pnl"] += t["pnl"]

    for ym in sorted(month_loss.keys()):
        info = month_loss[ym]
        bar = "█" * min(info["count"], 30)
        print(f"  {ym}: {info['count']:3d}건 {currency_sym}{info['total_pnl']:>10,.0f} {bar}")

    # 6. Worst 10 트레이드
    print(f"\n  ── Worst 10 트레이드 ──")
    worst = sorted(losers, key=lambda t: t["pnl_pct"])[:10]
    for i, t in enumerate(worst, 1):
        print(f"  {i:2d}. {t['stock_name']:15s} | {t['entry_date']}→{t['exit_date']} | "
              f"{t['pnl_pct']:+.2f}% ({currency_sym}{t['pnl']:,.0f}) | "
              f"{t['holding_days']}일 | {t['exit_reason'][:30]}")


def main():
    markets = ["sp500", "ndx", "kospi"]
    all_data = {}

    for mkt in markets:
        print(f"\n{'#'*70}")
        print(f"#  {mkt.upper()} 백테스트 시작 (multi strategy)")
        print(f"{'#'*70}")
        try:
            data = run_backtest(mkt, "multi")
            all_data[mkt] = data
        except Exception as e:
            print(f"  ❌ {mkt} 백테스트 실패: {e}")
            import traceback
            traceback.print_exc()

    # 분석 실행
    for mkt, data in all_data.items():
        analyze_alpha_beta(data)
        analyze_losing_trades(data)

    # 3개 시장 비교 요약
    print(f"\n{'='*70}")
    print(f"  📈 3-Market 비교 요약")
    print(f"{'='*70}")
    print(f"  {'시장':8s} | {'수익률':>8s} | {'Sharpe':>7s} | {'승률':>6s} | {'PF':>5s} | {'MDD':>6s} | {'거래':>5s} | {'손절':>5s}")
    print(f"  {'-'*65}")
    for mkt, data in all_data.items():
        r = data["result"]
        n_loss = sum(1 for t in data["closed_trades"] if t["pnl"] < 0)
        print(f"  {mkt:8s} | {r.total_return*100:>+7.1f}% | {r.sharpe_ratio:>7.2f} | {r.win_rate*100:>5.1f}% | {r.profit_factor:>5.2f} | {r.max_drawdown*100:>+5.1f}% | {r.total_trades:>5d} | {n_loss:>5d}")


if __name__ == "__main__":
    main()
