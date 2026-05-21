"""
리플레이 결과 저장/조회/삭제 API 라우트.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from infra.db.connection import Database
from infra.db.repository import Repository

replay_results_router = APIRouter()

# DB 인스턴스 (app.py에서 공유하면 더 좋지만, 현재 구조에서는 별도 생성)
_db = Database()
_db.init_tables()
_repo = Repository(_db)


class SaveReplayRequest(BaseModel):
    market: str = "sp500"


# ── 저장 (컨트롤러에서 캐시된 결과를 DB로 persist) ──

@replay_results_router.post("/replay/results/save")
async def save_replay_result(req: SaveReplayRequest):
    """현재 캐시된 리플레이 결과를 DB에 저장한다."""
    # app.py의 sim_controller에 접근
    from api.app import sim_controller

    result_data = sim_controller.get_replay_result(req.market)
    if not result_data:
        raise HTTPException(status_code=404, detail="리플레이 결과가 없습니다. 먼저 리플레이를 완료하세요.")

    result_id = _repo.save_replay_result(result_data)
    return {
        "status": "saved",
        "result_id": result_id,
        "market": req.market,
    }


# ── 목록 조회 ──

@replay_results_router.get("/replay/results")
def list_replay_results(
    market: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
):
    """저장된 리플레이 결과 목록을 반환한다."""
    results = _repo.list_replay_results(market=market, limit=limit, offset=offset)
    return {"results": results, "count": len(results)}


# ── 상세 조회 ──

@replay_results_router.get("/replay/results/{result_id}")
def get_replay_result(result_id: str):
    """리플레이 결과 상세를 반환한다 (에쿼티 커브, 트레이드 포함)."""
    result = _repo.get_replay_result(result_id)
    if not result:
        raise HTTPException(status_code=404, detail="결과를 찾을 수 없습니다.")
    return result


# ── 삭제 ──

@replay_results_router.delete("/replay/results/{result_id}")
def delete_replay_result(result_id: str):
    """리플레이 결과를 삭제한다."""
    deleted = _repo.delete_replay_result(result_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="결과를 찾을 수 없습니다.")
    return {"status": "deleted", "result_id": result_id}
