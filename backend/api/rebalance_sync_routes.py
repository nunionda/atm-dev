"""
Rebalance → Universe 동기화 REST 엔드포인트.

- POST /api/v1/rebalance/sync?market=&commit=&trigger=  : 수동 트리거
- GET  /api/v1/rebalance/sync/status?market=            : 마지막 sync 메타
- GET  /api/v1/rebalance/sync/log?market=&limit=        : 최근 N건 sync 로그
"""
from __future__ import annotations

import threading
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from core.rebalance_sync import RebalanceSyncJob
from data.config_manager import ConfigManager
from infra.db.connection import Database
from infra.db.repository import Repository
from infra.logger import get_logger

logger = get_logger("api.rebalance_sync")

rebalance_sync_router = APIRouter(tags=["rebalance-sync"])

# 요청 간 재사용을 위해 모듈 단위 캐시
_db: Database | None = None
_repo: Repository | None = None
_repo_init_lock = threading.Lock()

# 마켓별 sync 동시 실행 방지 — yfinance가 thread-safe 하지 않아 동시 호출 시 hang 위험
_sync_locks: dict[str, threading.Lock] = {}
_sync_locks_meta_lock = threading.Lock()

# 전역 sync lock — 한 번에 한 마켓만 sync 가능 (외부 API 부하 + DB ALTER 안전)
_global_sync_lock = threading.Lock()


def _market_lock(market: str) -> threading.Lock:
    with _sync_locks_meta_lock:
        if market not in _sync_locks:
            _sync_locks[market] = threading.Lock()
        return _sync_locks[market]


def _get_repo() -> Repository:
    """Repository singleton — multi-thread init 경합 방지."""
    global _db, _repo
    if _repo is not None:
        return _repo
    with _repo_init_lock:
        if _repo is None:
            cfg = ConfigManager().load()
            _db = Database(cfg.db_path)
            _db.init_tables()  # idempotent — 신규 컬럼 마이그레이션 보장
            _repo = Repository(_db)
    return _repo


def _build_job() -> RebalanceSyncJob:
    cfg = ConfigManager().load()
    ucfg = cfg.universe
    return RebalanceSyncJob(
        repo=_get_repo(),
        top_n=getattr(ucfg, "top_n", 10),
        min_universe_size=getattr(ucfg, "min_universe_size", 3),
        always_active=getattr(ucfg, "always_active", []),
    )


@rebalance_sync_router.post("/rebalance/sync")
def trigger_sync(
    market: str = Query("sp500", description="sp500 | ndx | kospi"),
    commit: bool = Query(True, description="False면 dry-run"),
    trigger: str = Query("MANUAL", description="MANUAL | AUTO"),
):
    """수동 Rebalance → Universe sync 실행.

    동시 호출 차단:
      - per-market lock: 동일 market 중복 호출 시 409
      - global lock: 다른 market sync 진행 중이면 409 (yfinance hang 회피)
    """
    market_lock = _market_lock(market)
    if not market_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail=f"sync already in progress for market={market}")
    try:
        if not _global_sync_lock.acquire(blocking=False):
            raise HTTPException(status_code=409, detail="another market sync is running; please retry shortly")
        try:
            job = _build_job()
            result = job.run(market=market, trigger=trigger, commit=commit)
            return result.to_dict()
        finally:
            _global_sync_lock.release()
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("sync route failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"sync failed: {e}")
    finally:
        market_lock.release()


@rebalance_sync_router.get("/rebalance/sync/status")
def get_sync_status(market: str = Query("sp500")):
    """해당 market의 마지막 sync 메타 + 활성 universe 카운트."""
    try:
        repo = _get_repo()
        latest = repo.get_latest_rebalance_sync(market)
        active = repo.get_active_universe(market=market)
        protected = [
            u for u in active
            if u.rebalance_action in ("BUY", "HOLD")
            and (u.return_6m or 0) > 0
        ]
        return {
            "market": market,
            "latest_sync": latest,
            "active_count": len(active),
            "protected_count": len(protected),
        }
    except Exception as e:
        logger.error("status route failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"status fetch failed: {e}")


@rebalance_sync_router.get("/rebalance/sync/log")
def get_sync_log(
    market: Optional[str] = Query(None),
    limit: int = Query(7, ge=1, le=50),
):
    """최근 sync 로그 N건."""
    try:
        repo = _get_repo()
        return {"items": repo.list_rebalance_sync_logs(market=market, limit=limit)}
    except Exception as e:
        logger.error("log route failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"log fetch failed: {e}")
