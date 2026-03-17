"""
ATS Analytics API + 시뮬레이션 SSE 스트림.
멀티마켓 (KOSPI, S&P 500, NASDAQ 100) 지원.

아키텍처:
  SimulationController → SimulationEngine(s) → SSEEventBus → Frontend
  향후 확장: PaperTradingController, LiveTradingController
"""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .routes import router
from .sim_routes import sim_router
from .rebalance_routes import rebalance_router
from .backtest_routes import backtest_router
from .replay_results_routes import replay_results_router
from .futures_routes import futures_router
from .esf_intraday_routes import esf_router
from .esf_journal_routes import esf_journal_router
from simulation.event_bus import SSEEventBus
from simulation.controller import SimulationController

event_bus = SSEEventBus()
sim_controller = SimulationController(event_bus)


def _prewarm_cache():
    """서버 시작 시 주요 티커 캐시 프리워밍."""
    import logging
    import yfinance as yf
    logger = logging.getLogger(__name__)
    warm_tickers = ["ES=F", "NQ=F", "^GSPC", "^IXIC"]
    for ticker in warm_tickers:
        try:
            yf.download(ticker, period="6mo", interval="1d", progress=False)
            logger.info("Cache pre-warmed: %s", ticker)
        except Exception as e:
            logger.warning("Pre-warm failed for %s: %s", ticker, e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 캐시 프리워밍 (백그라운드)
    asyncio.create_task(asyncio.to_thread(_prewarm_cache))
    # 모든 마켓 엔진 시작
    await sim_controller.start_all()
    yield
    # 모든 엔진 종료
    await sim_controller.shutdown_all()


app = FastAPI(
    title="ATS Analytics API",
    description="API for Automated Trading System Analytics",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS Middleware for Frontend (React)
import os
_cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")
app.include_router(sim_router, prefix="/api/v1")
app.include_router(rebalance_router, prefix="/api/v1")
app.include_router(backtest_router, prefix="/api/v1")
app.include_router(replay_results_router, prefix="/api/v1")
app.include_router(futures_router, prefix="/api/v1")
app.include_router(esf_router, prefix="/api/v1")
app.include_router(esf_journal_router, prefix="/api/v1")


@app.get("/health")
def health_check():
    return {"status": "ok", "mode": sim_controller.mode.value}


@app.get("/api/v1/stream")
async def sse_stream(request: Request):
    """SSE 스트림 엔드포인트. 프론트엔드가 EventSource로 연결한다."""
    queue = event_bus.subscribe()

    async def generate():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=30.0)
                    event_type = message["event"]
                    data = json.dumps(message["data"], ensure_ascii=False, default=str)
                    yield f"event: {event_type}\ndata: {data}\nid: {message['timestamp']}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            event_bus.unsubscribe(queue)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
