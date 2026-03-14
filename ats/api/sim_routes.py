"""
시뮬레이션 REST 엔드포인트.
  - 폴백 조회: SSE 연결 실패 시 프론트엔드가 폴링
  - 제어 API: 시뮬레이션 시작/정지/리셋/전략 변경
멀티마켓 지원: ?market=kospi|sp500|ndx (기본값: kospi)
"""

from fastapi import APIRouter, Query
from pydantic import BaseModel
from typing import List, Optional

sim_router = APIRouter()


def _get_engine(market: str = "kospi"):
    from api.app import sim_controller
    return sim_controller.get_engine(market)


def _get_controller():
    from api.app import sim_controller
    return sim_controller


@sim_router.get("/system/state")
def get_system_state(market: str = Query("kospi")):
    engine = _get_engine(market)
    if not engine or not engine._is_running:
        # 엔진이 존재하면 실제 포트폴리오 값 반환 (정지 상태라도)
        # 없으면 MARKET_CONFIG의 initial_capital 사용
        if engine:
            capital = engine.initial_capital
            cash = engine.cash
            equity = engine._get_total_equity()
        else:
            from simulation.watchlists import MARKET_CONFIG
            cfg = MARKET_CONFIG.get(market, {})
            capital = cfg.get("initial_capital", 0)
            cash = capital
            equity = capital
        return {
            "status": "STOPPED", "mode": "PAPER", "started_at": None,
            "market_phase": "CLOSED", "next_scan_at": None,
            "total_equity": equity, "cash": cash, "invested": 0,
            "daily_pnl": 0, "daily_pnl_pct": 0,
            "position_count": 0, "max_positions": 10,
        }
    state = engine.get_system_state().model_dump()
    state["market_id"] = engine.market_id
    state["currency"] = engine.currency
    state["currency_symbol"] = engine.currency_symbol
    state["market_label"] = engine.market_label
    return state


@sim_router.get("/positions")
def get_positions(market: str = Query("kospi")) -> List[dict]:
    engine = _get_engine(market)
    if not engine:
        return []
    return [p.model_dump() for p in engine.positions.values() if p.status == "ACTIVE"]


@sim_router.get("/orders")
def get_orders(market: str = Query("kospi")) -> List[dict]:
    engine = _get_engine(market)
    if not engine:
        return []
    return [o.model_dump() for o in engine.orders[-50:]]


@sim_router.get("/signals/today")
def get_signals(market: str = Query("kospi")) -> List[dict]:
    engine = _get_engine(market)
    if not engine:
        return []
    return [s.model_dump() for s in engine.signals[-20:]]


@sim_router.get("/risk/metrics")
def get_risk_metrics(market: str = Query("kospi")):
    engine = _get_engine(market)
    if not engine:
        return {"daily_pnl_pct": 0, "daily_loss_limit": -3.0, "mdd": 0, "mdd_limit": -10.0,
                "cash_ratio": 100, "min_cash_ratio": 20, "consecutive_stops": 0,
                "max_consecutive_stops": 3, "daily_trade_amount": 0,
                "max_daily_trade_amount": 30000000, "is_trading_halted": False, "halt_reason": None}
    return engine.get_risk_metrics().model_dump()


@sim_router.get("/risk/events")
def get_risk_events(market: str = Query("kospi")) -> List[dict]:
    engine = _get_engine(market)
    if not engine:
        return []
    return engine.risk_events[-30:]


@sim_router.get("/market-intelligence")
def get_market_intelligence():
    """3마켓 마켓 인텔리전스 집계 데이터."""
    ctrl = _get_controller()
    result = {}
    for mid in ("sp500", "ndx", "kospi"):
        engine = ctrl.get_engine(mid)
        if engine and hasattr(engine, "get_market_intelligence"):
            result[mid] = engine.get_market_intelligence()
        else:
            result[mid] = None
    return result


@sim_router.get("/performance/summary")
def get_performance_summary(market: str = Query("kospi")):
    engine = _get_engine(market)
    if not engine:
        return {
            "total_return_pct": 0, "total_trades": 0, "win_rate": 0,
            "avg_win_pct": 0, "avg_loss_pct": 0, "profit_factor": 0,
            "sharpe_ratio": 0, "max_drawdown_pct": 0, "avg_holding_days": 0,
            "best_trade_pct": 0, "worst_trade_pct": 0,
        }
    return engine.get_performance_summary().model_dump()


@sim_router.get("/performance/equity")
def get_equity_curve(market: str = Query("kospi")) -> List[dict]:
    engine = _get_engine(market)
    if not engine:
        return []
    return [p.model_dump() for p in engine.equity_curve]


@sim_router.get("/trades")
def get_trade_history(market: str = Query("kospi")) -> List[dict]:
    engine = _get_engine(market)
    if not engine:
        return []
    return [t.model_dump() for t in engine.closed_trades[-50:]]


# ══════════════════════════════════════════════════════════
# 시뮬레이션 제어 API (시작/정지/리셋/상태)
# ══════════════════════════════════════════════════════════


class SimControlRequest(BaseModel):
    """시뮬레이션 제어 요청."""
    market: str = "kospi"
    strategy_mode: Optional[str] = None  # momentum | smc | breakout_retest
    # Historical Replay 필드
    start_date: Optional[str] = None   # YYYYMMDD (리플레이 모드)
    end_date: Optional[str] = None     # YYYYMMDD
    replay_speed: Optional[float] = None  # 1.0=1초/일, 5.0=0.2초/일, 0=즉시


class ReplayControlRequest(BaseModel):
    """리플레이 제어 요청."""
    market: str = "kospi"
    speed: Optional[float] = None


@sim_router.get("/sim/status")
def get_sim_controller_status():
    """전체 시뮬레이션 컨트롤러 상태를 반환한다."""
    ctrl = _get_controller()
    return ctrl.get_status()


@sim_router.post("/sim/start")
async def start_simulation(req: SimControlRequest):
    """특정 마켓의 시뮬레이션을 시작한다.

    start_date/end_date가 있으면 Historical Replay 모드로 실행.
    없으면 기존 실시간 시뮬레이션 모드.
    """
    ctrl = _get_controller()
    if req.start_date and req.end_date:
        # Historical Replay 모드
        result = await ctrl.start_replay(
            req.market,
            start_date=req.start_date,
            end_date=req.end_date,
            strategy_mode=req.strategy_mode or "momentum",
            speed=req.replay_speed or 1.0,
        )
    else:
        # 실시간 시뮬레이션 모드
        result = await ctrl.start_market(
            req.market,
            strategy_mode=req.strategy_mode or "momentum",
        )
    return result


@sim_router.post("/sim/stop")
async def stop_simulation(req: SimControlRequest):
    """특정 마켓의 시뮬레이션을 정지한다."""
    ctrl = _get_controller()
    result = await ctrl.stop_market(req.market)
    return result


@sim_router.post("/sim/force-liquidate")
async def force_liquidate_all(req: SimControlRequest):
    """모든 ACTIVE 포지션을 현재가로 즉시 강제 청산한다."""
    engine = _get_engine(req.market)
    if not engine:
        return {"status": "error", "detail": "Engine not found for market"}
    result = engine.force_liquidate_all_immediate()
    return {"status": "ok", "market": req.market, **result}


@sim_router.post("/sim/reset")
async def reset_simulation(req: SimControlRequest):
    """특정 마켓을 리셋(정지 → 재시작)한다.

    포트폴리오를 초기 자본금으로 되돌리고 새로 시작.
    strategy_mode를 지정하면 전략도 변경 가능.
    """
    ctrl = _get_controller()
    result = await ctrl.reset_market(
        req.market,
        strategy_mode=req.strategy_mode,
    )
    return result


# ══════════════════════════════════════════════════════════
# Historical Replay 제어 API
# ══════════════════════════════════════════════════════════


@sim_router.post("/sim/replay/pause")
async def pause_replay(req: ReplayControlRequest):
    """리플레이 일시정지."""
    ctrl = _get_controller()
    return await ctrl.pause_replay(req.market)


@sim_router.post("/sim/replay/resume")
async def resume_replay(req: ReplayControlRequest):
    """리플레이 재개."""
    ctrl = _get_controller()
    return await ctrl.resume_replay(req.market)


@sim_router.post("/sim/replay/speed")
async def set_replay_speed(req: ReplayControlRequest):
    """리플레이 속도 변경."""
    ctrl = _get_controller()
    return ctrl.set_replay_speed(req.market, req.speed or 1.0)


# ══════════════════════════════════════════════════════════
# Performance 비교 API
# ══════════════════════════════════════════════════════════


@sim_router.get("/performance/vs-backtest")
def get_performance_vs_backtest(market: str = Query("sp500")):
    """시뮬레이션 실시간 성과와 백테스트 결과를 비교한다."""
    engine = _get_engine(market)

    # --- Live metrics ---
    if engine:
        ps = engine.get_performance_summary()
        live = {
            "total_return_pct": round(ps.total_return_pct, 2),
            "sharpe_ratio": round(ps.sharpe_ratio, 2),
            "max_drawdown_pct": round(ps.max_drawdown_pct, 2),
            "win_rate": round(ps.win_rate, 1),
            "profit_factor": round(ps.profit_factor, 2),
        }
    else:
        live = {
            "total_return_pct": 0, "sharpe_ratio": 0,
            "max_drawdown_pct": 0, "win_rate": 0, "profit_factor": 0,
        }

    # --- Backtest metrics (deferred import to avoid circular) ---
    from api.backtest_routes import _backtest_cache
    cached = _backtest_cache.get(market)

    if cached and "metrics" in cached:
        bm = cached["metrics"]
        backtest = {
            "total_return_pct": bm.get("total_return", 0),
            "sharpe_ratio": bm.get("sharpe_ratio", 0),
            "max_drawdown_pct": bm.get("max_drawdown", 0),
            "win_rate": bm.get("win_rate", 0),
            "profit_factor": bm.get("profit_factor", 0),
        }
        deltas = {
            k: round(live[k] - backtest[k], 2) for k in live
        }
    else:
        backtest = None
        deltas = None

    return {
        "market": market,
        "live": live,
        "backtest": backtest,
        "deltas": deltas,
        "has_backtest": backtest is not None,
    }
