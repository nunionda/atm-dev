"""
ESF Strategy Journal API — 가설 생성, 결과 기록, A/B 실험, 통계.

전략 가설(hypothesis) 생성 → 실제 결과 기록 → 누적 통계 갱신 →
A/B 실험을 통한 전략 변형 비교 파이프라인.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from infra.logger import get_logger

logger = get_logger("esf_journal_api")

esf_journal_router = APIRouter(tags=["esf-journal"])

# ── Lazy init singletons ──
_repo = None
_generator = None
_recorder = None
_ab_engine = None


def _get_repo():
    global _repo
    if _repo is None:
        from infra.db.connection import Database
        from infra.db.esf_journal_repo import ESFJournalRepo
        db = Database()
        db.init_tables()
        _repo = ESFJournalRepo(db)
    return _repo


def _get_generator():
    global _generator
    if _generator is None:
        from data.config_manager import ConfigManager
        from strategy.esf_hypothesis_generator import ESFHypothesisGenerator
        config = ConfigManager().load()
        _generator = ESFHypothesisGenerator(config, _get_repo())
    return _generator


def _get_recorder():
    global _recorder
    if _recorder is None:
        from strategy.esf_result_recorder import ESFResultRecorder
        _recorder = ESFResultRecorder(_get_repo())
    return _recorder


def _get_ab_engine():
    global _ab_engine
    if _ab_engine is None:
        from strategy.esf_ab_engine import ESFABEngine
        _ab_engine = ESFABEngine(_get_repo())
    return _ab_engine


# ── Request Models ──

class HypothesisRequest(BaseModel):
    ticker: str = "ES=F"
    variant_id: Optional[int] = None


class ABHypothesisRequest(BaseModel):
    ticker: str = "ES=F"
    experiment_id: int


class RecordResultRequest(BaseModel):
    hypothesis_id: int
    actual_entry_price: float
    actual_exit_price: float
    actual_direction: str = ""
    contracts: int = 1
    exit_reason: str = ""
    holding_minutes: int = 0
    actual_high: Optional[float] = None
    actual_low: Optional[float] = None
    actual_close: Optional[float] = None


class SkipRequest(BaseModel):
    reason: str = ""


class CreateVariantRequest(BaseModel):
    name: str
    description: str = ""
    param_overrides: dict = {}


class CreateExperimentRequest(BaseModel):
    name: str
    variant_a_id: int
    variant_b_id: int
    min_trades: int = 20
    max_days: int = 30
    description: str = ""


# ══════════════════════════════════════════
# Hypotheses
# ══════════════════════════════════════════

@esf_journal_router.post("/esf/journal/hypothesis")
async def generate_hypothesis(req: HypothesisRequest):
    """오늘의 전략 가설을 생성한다."""
    try:
        result = _get_generator().generate_daily_hypothesis(
            ticker=req.ticker,
            variant_id=req.variant_id,
        )
        if "error" in result:
            return JSONResponse(status_code=400, content=result)
        return JSONResponse(content=result)
    except Exception as e:
        logger.error("generate_hypothesis failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@esf_journal_router.post("/esf/journal/hypothesis/ab")
async def generate_ab_hypotheses(req: ABHypothesisRequest):
    """A/B 실험의 두 variant에 대해 가설을 생성한다."""
    try:
        results = _get_generator().generate_ab_hypotheses(
            ticker=req.ticker,
            experiment_id=req.experiment_id,
        )
        if not results:
            return JSONResponse(status_code=400, content={"error": "no_hypotheses_generated"})
        return JSONResponse(content={"hypotheses": results})
    except Exception as e:
        logger.error("generate_ab_hypotheses failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@esf_journal_router.get("/esf/journal/hypothesis/today")
async def get_today_hypotheses():
    """오늘 생성된 가설 목록을 반환한다."""
    try:
        today_str = datetime.now().strftime("%Y-%m-%d")
        items = _get_repo().get_hypotheses_by_date(today_str)
        return JSONResponse(content={"items": items, "date": today_str})
    except Exception as e:
        logger.error("get_today_hypotheses failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@esf_journal_router.get("/esf/journal/hypotheses")
async def list_hypotheses(
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    direction: Optional[str] = Query(None),
    regime: Optional[str] = Query(None),
    grade: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
):
    """가설 목록을 페이지네이션으로 반환한다."""
    try:
        result = _get_repo().get_hypotheses_paginated(
            offset=offset,
            limit=limit,
            direction=direction,
            regime=regime,
            grade=grade,
            date_from=date_from,
            date_to=date_to,
        )
        return JSONResponse(content=result)
    except Exception as e:
        logger.error("list_hypotheses failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@esf_journal_router.get("/esf/journal/hypothesis/{hypothesis_id}")
async def get_hypothesis(hypothesis_id: int):
    """단일 가설을 반환한다."""
    try:
        item = _get_repo().get_hypothesis(hypothesis_id)
        if not item:
            return JSONResponse(status_code=404, content={"error": "hypothesis_not_found"})
        return JSONResponse(content=item)
    except Exception as e:
        logger.error("get_hypothesis failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ══════════════════════════════════════════
# Results
# ══════════════════════════════════════════

@esf_journal_router.post("/esf/journal/result")
async def record_result(req: RecordResultRequest):
    """가설에 대한 실제 결과를 기록한다."""
    try:
        result_data = {
            "actual_entry_price": req.actual_entry_price,
            "actual_exit_price": req.actual_exit_price,
            "actual_direction": req.actual_direction,
            "contracts": req.contracts,
            "exit_reason": req.exit_reason,
            "holding_minutes": req.holding_minutes,
            "actual_high": req.actual_high,
            "actual_low": req.actual_low,
            "actual_close": req.actual_close,
        }
        result = _get_recorder().record_result(req.hypothesis_id, result_data)
        if "error" in result:
            return JSONResponse(status_code=400, content=result)
        return JSONResponse(content=result)
    except Exception as e:
        logger.error("record_result failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@esf_journal_router.patch("/esf/journal/hypothesis/{hypothesis_id}/skip")
async def skip_hypothesis(hypothesis_id: int, req: SkipRequest):
    """가설을 SKIPPED로 마킹한다."""
    try:
        result = _get_recorder().record_skip(hypothesis_id, req.reason)
        if "error" in result:
            return JSONResponse(status_code=400, content=result)
        return JSONResponse(content=result)
    except Exception as e:
        logger.error("skip_hypothesis failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ══════════════════════════════════════════
# Stats
# ══════════════════════════════════════════

@esf_journal_router.get("/esf/journal/stats")
async def get_cumulative_stats(
    dimension: Optional[str] = Query(None),
    variant_id: Optional[int] = Query(None),
):
    """누적 통계를 반환한다."""
    try:
        items = _get_repo().get_cumulative_stats(
            dimension=dimension,
            variant_id=variant_id,
        )
        return JSONResponse(content={"items": items})
    except Exception as e:
        logger.error("get_cumulative_stats failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@esf_journal_router.get("/esf/journal/stats/comparison")
async def get_stats_comparison(
    variant_a_id: int = Query(...),
    variant_b_id: int = Query(...),
):
    """두 variant의 통계를 비교한다."""
    try:
        result = _get_repo().get_stats_comparison(variant_a_id, variant_b_id)
        return JSONResponse(content=result)
    except Exception as e:
        logger.error("get_stats_comparison failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@esf_journal_router.get("/esf/journal/stats/trends")
async def get_trends(days: int = Query(30, ge=1, le=365)):
    """최근 N일 결과 트렌드를 반환한다."""
    try:
        items = _get_repo().get_results_for_trends(last_n_days=days)
        return JSONResponse(content={"items": items, "days": days})
    except Exception as e:
        logger.error("get_trends failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ══════════════════════════════════════════
# Variants
# ══════════════════════════════════════════

@esf_journal_router.post("/esf/journal/variants")
async def create_variant(req: CreateVariantRequest):
    """전략 변형을 생성한다."""
    try:
        result = _get_repo().create_variant(
            name=req.name,
            description=req.description,
            param_overrides=req.param_overrides,
        )
        return JSONResponse(status_code=201, content=result)
    except Exception as e:
        logger.error("create_variant failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@esf_journal_router.get("/esf/journal/variants")
async def list_variants():
    """활성 변형 목록을 반환한다."""
    try:
        items = _get_repo().list_variants()
        return JSONResponse(content={"items": items})
    except Exception as e:
        logger.error("list_variants failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ══════════════════════════════════════════
# Experiments
# ══════════════════════════════════════════

@esf_journal_router.post("/esf/journal/experiments")
async def create_experiment(req: CreateExperimentRequest):
    """A/B 실험을 생성한다."""
    try:
        result = _get_repo().create_experiment(
            name=req.name,
            variant_a_id=req.variant_a_id,
            variant_b_id=req.variant_b_id,
            min_trades=req.min_trades,
            max_days=req.max_days,
            description=req.description,
        )
        return JSONResponse(status_code=201, content=result)
    except Exception as e:
        logger.error("create_experiment failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@esf_journal_router.get("/esf/journal/experiments/{experiment_id}")
async def get_experiment_status(experiment_id: int):
    """실험 상태 및 통계를 반환한다."""
    try:
        result = _get_ab_engine().check_experiment_status(experiment_id)
        if "error" in result:
            return JSONResponse(status_code=404, content=result)
        return JSONResponse(content=result)
    except Exception as e:
        logger.error("get_experiment_status failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@esf_journal_router.post("/esf/journal/experiments/{experiment_id}/conclude")
async def conclude_experiment(experiment_id: int):
    """실험을 결론짓고 승자를 선언한다."""
    try:
        result = _get_ab_engine().conclude_experiment(experiment_id)
        if "error" in result:
            return JSONResponse(status_code=400, content=result)
        return JSONResponse(content=result)
    except Exception as e:
        logger.error("conclude_experiment failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@esf_journal_router.post("/esf/journal/experiments/{experiment_id}/graduate")
async def graduate_winner(experiment_id: int):
    """승리한 variant를 baseline으로 승격한다."""
    try:
        result = _get_ab_engine().auto_graduate_winner(experiment_id)
        if "error" in result:
            return JSONResponse(status_code=400, content=result)
        return JSONResponse(content=result)
    except Exception as e:
        logger.error("graduate_winner failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@esf_journal_router.get("/esf/journal/experiments")
async def list_experiments():
    """모든 실험 목록을 반환한다."""
    try:
        items = _get_repo().list_experiments()
        return JSONResponse(content={"items": items})
    except Exception as e:
        logger.error("list_experiments failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
