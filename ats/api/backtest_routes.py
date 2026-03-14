"""
유니버스 모드 백테스트 REST 엔드포인트.

/rebalance 페이지에서 마켓 선택 → 기간 설정 → 백테스트 실행 → 결과 확인.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query

backtest_router = APIRouter()

# 마켓별 캐시 & 락
_backtest_in_progress: Dict[str, bool] = {}
_backtest_cache: Dict[str, Dict[str, Any]] = {}


def _market_to_universe(market: str) -> str:
    """마켓 ID → 유니버스 ID 매핑."""
    mapping = {"sp500": "sp500_full", "ndx": "ndx_full", "kospi": "kospi_full"}
    uid = mapping.get(market)
    if not uid:
        raise HTTPException(status_code=400, detail=f"Unknown market: {market}")
    return uid


def _fmt_date(d: str) -> str:
    """YYYYMMDD → YYYY-MM-DD."""
    if len(d) == 8:
        return f"{d[:4]}-{d[4:6]}-{d[6:]}"
    return d


def _safe_float(v: float, decimals: int = 2) -> float:
    """NaN/Infinity → 0.0 변환 후 반올림."""
    import math
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return 0.0
    return round(v, decimals)


def _serialize_metrics(metrics: Any) -> Dict[str, Any]:
    """ExtendedMetrics → JSON-safe dict 변환."""
    # --- 핵심 메트릭 ---
    m: Dict[str, Any] = {
        "metrics": {
            "total_return": _safe_float(metrics.total_return * 100, 2),
            "cagr": _safe_float(metrics.cagr * 100, 2),
            "sharpe_ratio": _safe_float(metrics.sharpe_ratio, 2),
            "sortino_ratio": _safe_float(metrics.sortino_ratio, 2),
            "calmar_ratio": _safe_float(metrics.calmar_ratio, 2),
            "max_drawdown": _safe_float(metrics.max_drawdown * 100, 2),
            "max_drawdown_date": _fmt_date(metrics.max_drawdown_date),
            "total_trades": metrics.total_trades,
            "win_rate": _safe_float(metrics.win_rate * 100, 1),
            "profit_factor": _safe_float(metrics.profit_factor, 2),
            "avg_pnl_pct": _safe_float(metrics.avg_pnl_pct * 100, 2),
            "avg_holding_days": _safe_float(metrics.avg_holding_days, 1),
            "final_value": _safe_float(metrics.final_value, 0),
            "avg_win_pct": _safe_float(metrics.avg_win_pct * 100, 2),
            "avg_loss_pct": _safe_float(metrics.avg_loss_pct * 100, 2),
            "best_trade_pct": _safe_float(metrics.best_trade_pct * 100, 2),
            "worst_trade_pct": _safe_float(metrics.worst_trade_pct * 100, 2),
            "max_consecutive_wins": metrics.max_consecutive_wins,
            "max_consecutive_losses": metrics.max_consecutive_losses,
            "total_rebalances": metrics.total_rebalances,
            "avg_turnover_pct": _safe_float(metrics.avg_turnover_pct, 1),
            "time_in_bull_pct": _safe_float(metrics.time_in_bull_pct, 1),
            "time_in_bear_pct": _safe_float(metrics.time_in_bear_pct, 1),
            "time_in_neutral_pct": _safe_float(metrics.time_in_neutral_pct, 1),
        },
    }

    # --- 에쿼티 커브 ---
    m["equity_curve"] = [
        {
            "date": _fmt_date(eq.date),
            "equity": _safe_float(eq.total_value, 0),
            "drawdown_pct": _safe_float(eq.drawdown * 100, 2),
        }
        for eq in metrics.equity_curve
    ]

    # --- 트레이드 ---
    m["trades"] = [
        {
            "id": f"{t.stock_code}_{t.entry_date}",
            "stock_code": t.stock_code,
            "stock_name": t.stock_name,
            "entry_date": _fmt_date(t.entry_date),
            "exit_date": _fmt_date(t.exit_date),
            "entry_price": _safe_float(t.entry_price, 2),
            "exit_price": _safe_float(t.exit_price, 2),
            "quantity": t.quantity,
            "pnl": _safe_float(t.pnl, 2),
            "pnl_pct": _safe_float(t.pnl_pct * 100, 2),
            "exit_reason": t.exit_reason,
            "holding_days": t.holding_days,
        }
        for t in metrics.trades
    ]

    # --- Phase Stats ---
    ps = metrics.phase_stats
    m["phase_stats"] = {
        "total_scans": ps.total_scans,
        "entries_executed": ps.entries_executed,
        "phase0_bear_blocks": ps.phase0_bear_blocks,
        "phase1_trend_rejects": ps.phase1_trend_rejects,
        "phase2_late_rejects": ps.phase2_late_rejects,
        "phase3_no_primary": ps.phase3_no_primary,
        "phase3_no_confirm": ps.phase3_no_confirm,
        "phase4_risk_blocks": ps.phase4_risk_blocks,
        "es1_stop_loss": ps.es1_stop_loss,
        "es2_take_profit": ps.es2_take_profit,
        "es3_trailing_stop": ps.es3_trailing_stop,
        "es4_dead_cross": ps.es4_dead_cross,
        "es5_max_holding": ps.es5_max_holding,
        "es6_time_decay": ps.es6_time_decay,
        "es7_rebalance_exit": ps.es7_rebalance_exit,
        "total_commission_paid": _safe_float(ps.total_commission_paid, 2),
        # SMC 전용
        "es_smc_sl": ps.es_smc_sl,
        "es_smc_tp": ps.es_smc_tp,
        "es_choch_exit": ps.es_choch_exit,
        "smc_avg_score": _safe_float(ps.smc_avg_score, 1),
        "smc_entries": ps.smc_entries,
        # Breakout-Retest 전용
        "brt_breakouts_detected": ps.brt_breakouts_detected,
        "brt_fakeout_blocked": ps.brt_fakeout_blocked,
        "brt_retests_entered": ps.brt_retests_entered,
        "brt_retests_expired": ps.brt_retests_expired,
        "es_brt_sl": ps.es_brt_sl,
        "es_brt_tp": ps.es_brt_tp,
        "es_zone_break": ps.es_zone_break,
        # Mean Reversion 전용
        "mr_entries": ps.mr_entries,
        "es_mr_sl": ps.es_mr_sl,
        "es_mr_tp": ps.es_mr_tp,
        "es_mr_bb": ps.es_mr_bb,
        "es_mr_ob": ps.es_mr_ob,
        # Arbitrage 전용
        "arb_pairs_scanned": ps.arb_pairs_scanned,
        "arb_spreads_detected": ps.arb_spreads_detected,
        "arb_correlation_rejects": ps.arb_correlation_rejects,
        "arb_entries": ps.arb_entries,
        "arb_short_entries": ps.arb_short_entries,
        "arb_total_score": ps.arb_total_score,
        "es_arb_sl": ps.es_arb_sl,
        "es_arb_tp": ps.es_arb_tp,
        "es_arb_corr": ps.es_arb_corr,
        # v5: Basis Gate + Fixed Pair
        "arb_basis_gate_blocks": ps.arb_basis_gate_blocks,
        "arb_basis_window_opens": ps.arb_basis_window_opens,
        "arb_fixed_pairs_loaded": ps.arb_fixed_pairs_loaded,
        # 레짐별 전략 모듈화
        "phase3_ps4_donchian": ps.phase3_ps4_donchian,
        "es_neutral_time_decay": ps.es_neutral_time_decay,
        "es_range_box_breakout": ps.es_range_box_breakout,
        "es_disp_partial_sell": ps.es_disp_partial_sell,
        "regime_pyramid_entries": ps.regime_pyramid_entries,
        "regime_sizing_reductions": ps.regime_sizing_reductions,
        # 종목별 레짐 분류
        "stock_regime_distribution": ps.stock_regime_distribution,
        "stock_regime_strategy_map": ps.stock_regime_strategy_map,
    }

    # --- Monthly Returns ---
    m["monthly_returns"] = {
        k: _safe_float(v * 100, 2) for k, v in metrics.monthly_returns.items()
    }

    return m


def _run_backtest_sync(market: str, universe_id: str, start_date: str, end_date: str, strategy: str = "momentum") -> Any:
    """동기 백테스트 실행 (스레드에서 호출)."""
    import sys
    import os

    # ats 디렉토리를 sys.path에 추가 (import 해결)
    ats_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if ats_dir not in sys.path:
        sys.path.insert(0, ats_dir)

    from backtest.historical_engine import HistoricalBacktester

    bt = HistoricalBacktester(
        market=market,
        scenario="custom",
        start_date=start_date,
        end_date=end_date,
        universe=universe_id,
        rebalance_days=14,
        top_n=15,
        strategy_mode=strategy,
    )
    return bt.run()


@backtest_router.post("/rebalance/backtest")
async def trigger_backtest(
    market: str = Query("sp500"),
    start_date: str = Query(..., description="Start date YYYYMMDD"),
    end_date: str = Query(..., description="End date YYYYMMDD"),
    strategy: str = Query("momentum", description="Strategy: momentum, smc, breakout_retest, mean_reversion, arbitrage, defensive, volatility, multi, or regime_*"),
):
    """
    유니버스 모드 백테스트 실행.

    마켓의 전체 유니버스를 대상으로 14일 리밸런싱 백테스트를 실행한다.
    10~60초 소요. 실행 중 동일 마켓 중복 요청 시 409.
    strategy: 개별(momentum/smc/breakout_retest/mean_reversion/arbitrage/defensive/volatility),
              적응형(multi), 레짐별(regime_strong_bull/regime_bull/regime_neutral/regime_range_bound/regime_bear/regime_crisis)
    """
    # strategy 검증
    VALID_STRATEGIES = {
        "momentum", "smc", "breakout_retest", "mean_reversion", "arbitrage",
        "defensive", "volatility", "multi",
        "regime_strong_bull", "regime_bull", "regime_neutral",
        "regime_range_bound", "regime_bear", "regime_crisis",
    }
    if strategy not in VALID_STRATEGIES:
        raise HTTPException(status_code=400, detail=f"Invalid strategy '{strategy}'. Valid: {sorted(VALID_STRATEGIES)}")

    # 입력 검증
    if len(start_date) != 8 or len(end_date) != 8:
        raise HTTPException(status_code=400, detail="Dates must be YYYYMMDD format")
    if start_date >= end_date:
        raise HTTPException(status_code=400, detail="start_date must be before end_date")

    # 최소 3개월 차이 검증
    try:
        start_y, start_m = int(start_date[:4]), int(start_date[4:6])
        end_y, end_m = int(end_date[:4]), int(end_date[4:6])
        month_diff = (end_y - start_y) * 12 + (end_m - start_m)
        if month_diff < 3:
            raise HTTPException(status_code=400, detail="Minimum 3-month period required")
    except (ValueError, HTTPException):
        raise

    universe_id = _market_to_universe(market)

    # 중복 실행 방지
    if _backtest_in_progress.get(market, False):
        raise HTTPException(status_code=409, detail="Backtest already in progress for this market")

    _backtest_in_progress[market] = True

    try:
        # asyncio.to_thread로 블로킹 백테스트를 스레드에서 실행
        result = await asyncio.to_thread(
            _run_backtest_sync, market, universe_id, start_date, end_date, strategy
        )

        # 결과 직렬화 + 캐시
        serialized = _serialize_metrics(result)
        serialized["market"] = market
        serialized["strategy"] = strategy
        serialized["start_date"] = _fmt_date(start_date)
        serialized["end_date"] = _fmt_date(end_date)

        _backtest_cache[market] = serialized
        return serialized

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backtest failed: {str(e)}")
    finally:
        _backtest_in_progress[market] = False


@backtest_router.get("/rebalance/backtest/status")
def get_backtest_status(market: str = Query("sp500")):
    """백테스트 진행 상태 조회."""
    cached = _backtest_cache.get(market)
    return {
        "market": market,
        "is_running": _backtest_in_progress.get(market, False),
        "has_result": cached is not None,
        "start_date": cached.get("start_date") if cached else None,
        "end_date": cached.get("end_date") if cached else None,
    }


@backtest_router.get("/rebalance/backtest/result")
def get_backtest_result(market: str = Query("sp500")):
    """캐시된 백테스트 결과 조회."""
    cached = _backtest_cache.get(market)
    if not cached:
        raise HTTPException(status_code=404, detail="No backtest result available. Run a backtest first.")
    return cached
