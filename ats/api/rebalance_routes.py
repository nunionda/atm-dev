"""
리밸런싱 REST 엔드포인트.

수동 리밸런스 스캔 + 추천 조회 + 상태 조회.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

from simulation.universe import UNIVERSE_CONFIG, UniverseScanner

rebalance_router = APIRouter()

# 스캔 결과 캐시 (마켓별)
_scan_cache: Dict[str, Dict[str, Any]] = {}
_scan_in_progress: Dict[str, bool] = {}


def _get_universe_config(market: str) -> Dict[str, Any]:
    """마켓에 대응하는 유니버스 설정을 찾는다."""
    mapping = {
        "sp500": "sp500_full",
        "ndx": "ndx_full",
        "kospi": "kospi_full",
    }
    universe_id = mapping.get(market)
    if not universe_id or universe_id not in UNIVERSE_CONFIG:
        raise HTTPException(
            status_code=400,
            detail=f"No universe configured for market '{market}'"
        )
    return UNIVERSE_CONFIG[universe_id]


@rebalance_router.post("/rebalance/scan")
async def trigger_scan(market: str = Query("sp500")):
    """
    수동 리밸런스 스캔 실행.

    yfinance에서 최신 데이터 다운로드 → 모멘텀 랭킹 → 추천 생성.
    """
    if _scan_in_progress.get(market, False):
        raise HTTPException(status_code=409, detail="Scan already in progress")

    _scan_in_progress[market] = True

    try:
        ucfg = _get_universe_config(market)
        constituents = ucfg["constituents"]
        top_n = ucfg.get("top_n", 15)

        # 데이터 다운로드
        from backtest.data_downloader import download_and_cache_batched
        from simulation.watchlists import MARKET_CONFIG

        market_cache = os.path.join("data_store/historical", market)

        # 최근 1년 데이터 (MA200 계산에 필요)
        end_date = datetime.now().strftime("%Y%m%d")
        # 워밍업 포함 약 14개월
        from datetime import timedelta
        start_dt = datetime.now() - timedelta(days=420)
        start_date = start_dt.strftime("%Y%m%d")

        ohlcv_map = download_and_cache_batched(
            watchlist=constituents,
            start_date=start_date,
            end_date=end_date,
            cache_dir=market_cache,
            batch_size=50,
            delay_between_batches=1.0,
        )

        # 스캐너 실행
        scanner = UniverseScanner(
            constituents=constituents,
            top_n=top_n,
        )

        # 활성 포지션 가져오기
        active_positions = {}
        try:
            from api.app import sim_controller
            engine = sim_controller.get_engine(market)
            if engine and engine._is_running:
                active_positions = {
                    code: pos
                    for code, pos in engine.positions.items()
                    if pos.status == "ACTIVE"
                }
        except Exception:
            pass

        result = scanner.scan_with_recommendations(
            ohlcv_map=ohlcv_map,
            current_date=end_date,
            active_positions=active_positions,
        )

        # 캐시 저장
        result["market"] = market
        _scan_cache[market] = result

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scan failed: {str(e)}")
    finally:
        _scan_in_progress[market] = False


@rebalance_router.get("/rebalance/recommendations")
def get_recommendations(market: str = Query("sp500")):
    """마지막 스캔 결과 조회 (캐시)."""
    cached = _scan_cache.get(market)
    if not cached:
        return {
            "market": market,
            "scan_date": None,
            "total_scanned": 0,
            "passed_prefilter": 0,
            "buy": [],
            "hold": [],
            "sell": [],
        }
    return cached


@rebalance_router.get("/rebalance/status")
def get_rebalance_status(market: str = Query("sp500")):
    """리밸런스 상태: 마지막 스캔일, 스캔 진행 여부, 현재 워치리스트."""
    cached = _scan_cache.get(market)

    # 현재 워치리스트 수
    watchlist_count = 0
    try:
        from simulation.watchlists import MARKET_CONFIG
        cfg = MARKET_CONFIG.get(market, {})
        watchlist_count = len(cfg.get("watchlist", []))
    except Exception:
        pass

    return {
        "market": market,
        "last_scan_date": cached.get("scan_date") if cached else None,
        "next_scan_date": None,
        "current_watchlist_count": watchlist_count,
        "is_scanning": _scan_in_progress.get(market, False),
    }
