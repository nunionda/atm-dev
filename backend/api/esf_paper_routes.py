"""
ESF Paper Trading API — Decision Engine "GO" → 시뮬 포지션 라이프사이클.

매매 플로우:
  1. 프론트가 POST /esf/paper/open (ticker, frontend_direction, contracts)
  2. 서버가 /esf/analyze 재조회 → backend `direction`/SL/TP를 canonical로 lock
  3. 방향 일치(frontend_direction == backend_direction), signal_active 검증
  4. 리스크 체크 (동일 ticker OPEN, max_concurrent, 일일 손실 한도)
  5. ESFHypothesis 생성 → FuturesPaperPosition OPEN
  6. live_data tick 루프가 가격 모니터 → SL/TP hit 시 자동 청산
  7. close 시 ESFResultRecorder.record_result로 자동 journaling
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from infra.logger import get_logger

logger = get_logger("esf_paper_api")

esf_paper_router = APIRouter(tags=["esf-paper"])

# 리스크 한도
PAPER_STARTING_EQUITY = 10_000.0
PAPER_DAILY_LOSS_LIMIT_PCT = 0.05  # -5% (BR-R01 미러)
PAPER_MAX_CONCURRENT = 3

# ── Lazy singletons ──
_engine = None
_recorder_cache = None


def _get_engine():
    """FuturesPaperEngine 지연 초기화. app.py가 set_engine으로 주입할 수 있게 한다."""
    global _engine
    if _engine is None:
        from infra.db.connection import Database
        from simulation.futures_paper_engine import FuturesPaperEngine
        from .esf_journal_routes import _get_recorder
        db = Database()
        db.init_tables()
        _engine = FuturesPaperEngine(
            database=db,
            recorder=_get_recorder(),
            publish=None,  # app.py가 set_engine으로 재주입
            max_concurrent=PAPER_MAX_CONCURRENT,
        )
    return _engine


def set_engine(engine):
    """app.py에서 EventBus·LiveDataService와 연결된 엔진을 주입한다."""
    global _engine
    _engine = engine


# ── Request Models ──

class OpenPaperPositionRequest(BaseModel):
    ticker: str
    frontend_direction: str  # 'LONG' | 'SHORT' — 프론트 Z-Score 기반
    contracts: int = 1
    interval: str = "15m"
    period: str = "60d"


class ClosePaperPositionRequest(BaseModel):
    price: Optional[float] = None  # None이면 last_price 사용


# ══════════════════════════════════════════
# Endpoints
# ══════════════════════════════════════════


@esf_paper_router.post("/esf/paper/open")
async def open_paper_position(req: OpenPaperPositionRequest):
    """Decision Engine GO → 페이퍼 포지션 OPEN.

    서버측 검증·lock-in 순서:
      1. /esf/analyze 재조회 → 백엔드 SL/TP/direction 확보
      2. signal_active=true 확인
      3. backend.direction == frontend_direction 확인
      4. 리스크 체크 (FuturesPaperEngine.open_position 내에서 ticker/concurrent 검사)
      5. 일일 손실 한도 체크
      6. ESFHypothesis 생성 (status ACTIVE) → position에 hypothesis_id 바인딩
    """
    if req.frontend_direction not in ("LONG", "SHORT"):
        raise HTTPException(
            status_code=400,
            detail=f"frontend_direction must be LONG or SHORT, got {req.frontend_direction}",
        )

    # ── 1. /esf/analyze 재호출로 canonical SL/TP/direction 확보 ──
    from .esf_intraday_routes import analyze_esf_intraday
    try:
        analyze_resp = await analyze_esf_intraday(
            ticker=req.ticker, interval=req.interval, period=req.period,
        )
        # JSONResponse.body는 bytes — render된 콘텐츠 사용
        import json as _json
        analysis = _json.loads(analyze_resp.body.decode("utf-8")) if hasattr(analyze_resp, "body") else analyze_resp
    except HTTPException:
        raise
    except Exception as e:
        logger.error("analyze 재호출 실패: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"analyze fetch failed: {e}")

    backend_dir = analysis.get("direction")
    signal_active = analysis.get("signal_active", False)
    entry_price = analysis.get("entry_price")
    stop_loss = analysis.get("stop_loss")
    take_profit = analysis.get("take_profit")

    # ── 2. signal_active 검증 ──
    if not signal_active:
        raise HTTPException(
            status_code=409,
            detail=f"signal_active=false for {req.ticker} (grade={analysis.get('grade')})",
        )

    # ── 3. 방향 일치 검증 (SSOT) ──
    if backend_dir != req.frontend_direction:
        raise HTTPException(
            status_code=409,
            detail=f"direction disagreement: backend={backend_dir} != frontend={req.frontend_direction}",
        )

    if backend_dir not in ("LONG", "SHORT"):
        raise HTTPException(
            status_code=409,
            detail=f"backend direction must be LONG or SHORT, got {backend_dir}",
        )

    engine = _get_engine()

    # ── 4. 일일 손실 한도 (BR-R01 미러) ──
    realized_today = engine.realized_pnl_today()
    loss_limit = -PAPER_STARTING_EQUITY * PAPER_DAILY_LOSS_LIMIT_PCT
    if realized_today <= loss_limit:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Daily paper loss limit reached: ${realized_today:.2f} <= ${loss_limit:.2f}"
            ),
        )

    # ── 5. ESFHypothesis 생성 (status=ACTIVE) ──
    from .esf_journal_routes import _get_repo
    repo = _get_repo()

    trade_date = datetime.now().strftime("%Y-%m-%d")
    regime_info = analysis.get("regime", {}) or {}
    regime_str = regime_info.get("regime", "NEUTRAL") if isinstance(regime_info, dict) else "NEUTRAL"

    try:
        hypothesis = repo.create_hypothesis(
            trade_date=trade_date,
            ticker=req.ticker,
            direction=backend_dir,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            total_score=analysis.get("total_score", 0.0),
            grade=analysis.get("grade", "C"),
            confidence=analysis.get("confidence", 0.0),
            regime=regime_str,
            reasoning_json={
                "source": "paper_open",
                "layers": analysis.get("layers", {}),
                "magnetic_ma": analysis.get("magnetic_ma"),
                "vwatr_zones": analysis.get("vwatr_zones", []),
                "amt_state": analysis.get("amt_state"),
            },
            entry_hour_et=datetime.now().hour,
        )
        hypothesis_id = hypothesis["hypothesis_id"]
        repo.update_hypothesis_status(hypothesis_id, "ACTIVE")
    except Exception as e:
        logger.error("Hypothesis 생성 실패: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"hypothesis creation failed: {e}")

    # ── 6. FuturesPaperPosition OPEN ──
    try:
        position = engine.open_position(
            ticker=req.ticker,
            direction=backend_dir,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            contracts=req.contracts,
            hypothesis_id=hypothesis_id,
        )
    except ValueError as e:
        # 가설 롤백 (SKIPPED 처리)
        try:
            repo.update_hypothesis_status(hypothesis_id, "SKIPPED")
        except Exception:
            pass
        msg = str(e)
        if "already exists" in msg or "Max concurrent" in msg:
            raise HTTPException(status_code=409, detail=msg)
        raise HTTPException(status_code=400, detail=msg)

    # ── 7. live_data subscribe ──
    try:
        from .app import live_data
        live_data.subscribe_ticker(req.ticker)
    except Exception as e:
        logger.warning("live_data subscribe 실패 (계속 진행): %s", e)

    return JSONResponse(content={"position": position, "hypothesis_id": hypothesis_id})


@esf_paper_router.get("/esf/paper/positions")
async def list_paper_positions(
    status: Optional[str] = Query(None, description="OPEN | CLOSED | etc"),
    limit: int = Query(50, ge=1, le=500),
):
    """페이퍼 포지션 목록."""
    engine = _get_engine()
    if status == "OPEN":
        items = engine.list_open()
    else:
        items = engine.list_all(status=status, limit=limit)
    return JSONResponse(content={"items": items, "total": len(items)})


@esf_paper_router.get("/esf/paper/positions/{position_id}")
async def get_paper_position(position_id: str):
    """단일 포지션 상세."""
    engine = _get_engine()
    pos = engine.get(position_id)
    if not pos:
        raise HTTPException(status_code=404, detail=f"Position not found: {position_id}")
    return JSONResponse(content=pos)


@esf_paper_router.post("/esf/paper/positions/{position_id}/close")
async def close_paper_position(position_id: str, req: ClosePaperPositionRequest):
    """수동 청산."""
    engine = _get_engine()
    pos = engine.get(position_id)
    if not pos:
        raise HTTPException(status_code=404, detail=f"Position not found: {position_id}")
    if pos["status"] != "OPEN":
        raise HTTPException(status_code=409, detail=f"Position not OPEN: status={pos['status']}")

    price = req.price if req.price is not None else pos.get("last_price") or pos["entry_price"]
    try:
        final = engine.close_position(position_id, price=price, reason="MANUAL")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return JSONResponse(content=final)


@esf_paper_router.get("/esf/paper/risk-status")
async def paper_risk_status():
    """오늘 누적 paper PnL + 한도 정보."""
    engine = _get_engine()
    realized = engine.realized_pnl_today()
    limit = -PAPER_STARTING_EQUITY * PAPER_DAILY_LOSS_LIMIT_PCT
    return JSONResponse(content={
        "realized_pnl_today": round(realized, 2),
        "daily_loss_limit": round(limit, 2),
        "limit_reached": realized <= limit,
        "starting_equity": PAPER_STARTING_EQUITY,
        "max_concurrent": PAPER_MAX_CONCURRENT,
        "open_count": len(engine.list_open()),
    })
