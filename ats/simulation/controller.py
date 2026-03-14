"""
시뮬레이션 컨트롤러 — 엔진 라이프사이클 관리 서비스 레이어.

향후 확장 설계:
  - SimulationController: 현재 (yfinance 기반 모의투자)
  - PaperTradingController: KIS 모의투자 API 연동 (향후)
  - LiveTradingController: KIS 실전 API 연동 (향후)

모든 컨트롤러는 동일한 인터페이스(start/stop/reset/get_engine)를 제공하므로
프론트엔드는 모드에 관계없이 동일한 API로 제어 가능.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional

from simulation.engine import SimulationEngine
from simulation.event_bus import SSEEventBus
from simulation.watchlists import MARKET_CONFIG, VALID_MARKETS

from infra.logger import get_logger

logger = get_logger("sim_controller")

OnEventType = Callable[[str, Any], Coroutine[Any, Any, None]]


class SimMode(str, Enum):
    """시뮬레이션 실행 모드."""
    SIMULATION = "simulation"     # yfinance 기반 가상 매매
    # 향후 확장:
    # PAPER = "paper"             # KIS 모의투자 API
    # LIVE = "live"               # KIS 실전 API


class SimulationController:
    """멀티마켓 시뮬레이션 엔진 라이프사이클 관리.

    책임:
      - 마켓별 엔진 생성/시작/정지/리셋
      - 전략 모드 전환
      - 하트비트 루프 관리
      - 향후 PaperTrading/LiveTrading 모드 전환 준비

    사용법 (app.py lifespan):
        controller = SimulationController(event_bus)
        await controller.start_all()       # 서버 시작 시
        await controller.shutdown_all()    # 서버 종료 시
    """

    def __init__(self, event_bus: SSEEventBus):
        self._event_bus = event_bus
        self._engines: Dict[str, SimulationEngine] = {}
        self._tasks: Dict[str, asyncio.Task] = {}
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._mode = SimMode.SIMULATION

        # Historical Replay 상태
        self._replay_providers: Dict[str, Any] = {}  # HistoricalDataProvider
        self._replay_state: Dict[str, Dict] = {}
        self._replay_results: Dict[str, Dict] = {}  # 마켓별 최근 결과 캐시

    # ── 속성 ──────────────────────────────────────────────

    @property
    def mode(self) -> SimMode:
        return self._mode

    @property
    def engines(self) -> Dict[str, SimulationEngine]:
        return self._engines

    def get_engine(self, market_id: str) -> Optional[SimulationEngine]:
        return self._engines.get(market_id)

    # ── 전체 라이프사이클 ─────────────────────────────────

    async def start_all(self) -> None:
        """모든 마켓 엔진을 생성하고 시작한다."""
        for market_id, config in MARKET_CONFIG.items():
            await self.start_market(market_id)

        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info(
            "SimulationController 시작 완료 | mode=%s | markets=%s",
            self._mode.value, list(self._engines.keys()),
        )

    async def shutdown_all(self) -> None:
        """모든 엔진과 하트비트를 종료한다."""
        for market_id in list(self._engines.keys()):
            await self.stop_market(market_id)

        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None

        logger.info("SimulationController 종료 완료")

    # ── 개별 마켓 제어 ────────────────────────────────────

    async def start_market(
        self,
        market_id: str,
        strategy_mode: str = "momentum",
    ) -> Dict[str, str]:
        """특정 마켓의 시뮬레이션을 시작한다.

        이미 실행 중이면 무시한다.

        Args:
            market_id: "kospi" | "sp500" | "ndx"
            strategy_mode: "momentum" | "smc" | "breakout_retest" | "mean_reversion"

        Returns:
            {"status": "started", "market": market_id, ...}
        """
        if market_id not in MARKET_CONFIG:
            return {"status": "error", "detail": f"Unknown market: {market_id}"}

        # 이미 실행 중이면 건너뜀
        existing = self._engines.get(market_id)
        if existing and existing._is_running:
            return {
                "status": "already_running",
                "market": market_id,
                "strategy": existing.strategy_mode,
            }

        config = MARKET_CONFIG[market_id]

        # 전략 모드: 명시적 파라미터 우선, 없으면 MARKET_CONFIG 기본값 사용
        actual_strategy = strategy_mode or config.get("strategy_mode", "momentum")

        engine = SimulationEngine(
            on_event=self._event_bus.publish,
            market_id=market_id,
            watchlist=config["watchlist"],
            initial_capital=config["initial_capital"],
            currency=config["currency"],
            currency_symbol=config["currency_symbol"],
            market_label=config["label"],
            strategy_mode=actual_strategy,
        )
        self._engines[market_id] = engine
        self._tasks[market_id] = asyncio.create_task(engine.start())

        logger.info(
            "마켓 시작 | market=%s | strategy=%s | capital=%s",
            market_id, actual_strategy, config["initial_capital"],
        )
        return {
            "status": "started",
            "market": market_id,
            "strategy": actual_strategy,
            "initial_capital": config["initial_capital"],
        }

    async def stop_market(self, market_id: str) -> Dict[str, str]:
        """특정 마켓의 시뮬레이션을 정지한다."""
        engine = self._engines.get(market_id)
        if not engine:
            return {"status": "not_found", "market": market_id}

        await engine.stop()

        task = self._tasks.get(market_id)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            del self._tasks[market_id]

        logger.info("마켓 정지 | market=%s", market_id)
        return {"status": "stopped", "market": market_id}

    async def reset_market(
        self,
        market_id: str,
        strategy_mode: Optional[str] = None,
    ) -> Dict[str, str]:
        """특정 마켓을 리셋(정지 후 재시작)한다.

        포트폴리오를 초기 자본금으로 리셋하고 새로 시작.
        전략 모드 변경 시 strategy_mode 파라미터 전달.
        """
        # 기존 엔진 정지
        await self.stop_market(market_id)

        # 재시작 (기존 strategy 유지 또는 새로운 것 적용)
        old_engine = self._engines.get(market_id)
        fallback_strategy = (
            old_engine.strategy_mode if old_engine else "momentum"
        )
        actual_strategy = strategy_mode or fallback_strategy

        # 엔진 인스턴스 제거 후 새로 생성
        self._engines.pop(market_id, None)
        result = await self.start_market(market_id, actual_strategy)

        logger.info(
            "마켓 리셋 | market=%s | strategy=%s",
            market_id, actual_strategy,
        )
        result["status"] = "reset"
        return result

    # ── Historical Replay ───────────────────────────────────

    async def start_replay(
        self,
        market_id: str,
        start_date: str,
        end_date: str,
        strategy_mode: str = "momentum",
        speed: float = 1.0,
    ) -> Dict[str, Any]:
        """히스토리컬 리플레이 시작.

        과거 데이터를 다운로드하고, 날짜별로 시뮬레이션 엔진을 실행하면서
        SSE로 브로드캐스트하여 프론트엔드에서 실시간처럼 관찰할 수 있게 한다.

        Args:
            market_id: "kospi" | "sp500" | "ndx"
            start_date: YYYYMMDD (백테스트 시작일)
            end_date: YYYYMMDD (백테스트 종료일)
            strategy_mode: "momentum" | "smc" | "breakout_retest" | "mean_reversion"
            speed: 재생 속도 (1.0 = 1초/일, 5.0 = 0.2초/일, 0 = 즉시)
        """
        if market_id not in MARKET_CONFIG:
            return {"status": "error", "detail": f"Unknown market: {market_id}"}

        # 기존 엔진 정지 및 정리
        await self.stop_market(market_id)
        self._engines.pop(market_id, None)
        self._replay_state.pop(market_id, None)
        self._replay_providers.pop(market_id, None)

        config = MARKET_CONFIG[market_id]
        actual_strategy = strategy_mode or config.get("strategy_mode", "momentum")

        # 워밍업 시작일 계산 (MA200 계산용: start_date - 365일)
        try:
            sd = datetime.strptime(start_date, "%Y%m%d")
        except ValueError:
            return {"status": "error", "detail": f"Invalid start_date format: {start_date}. Use YYYYMMDD."}
        warmup_start = (sd - timedelta(days=365)).strftime("%Y%m%d")

        logger.info(
            "리플레이 시작 | market=%s | strategy=%s | %s ~ %s | speed=%.1f",
            market_id, actual_strategy, start_date, end_date, speed,
        )

        # 데이터 다운로드 (블로킹 → run_in_executor 사용)
        from backtest.data_downloader import download_and_cache, download_and_cache_batched

        watchlist = config["watchlist"]
        cache_dir = os.path.join("data_store/historical", market_id)
        loop = asyncio.get_event_loop()

        await self._event_bus.publish(f"{market_id}:replay_progress", {
            "current_date": "", "progress_pct": 0,
            "day_index": 0, "total_days": 0,
            "speed": speed, "paused": False,
            "status": "downloading",
        })

        try:
            if len(watchlist) > 50:
                ohlcv_map = await loop.run_in_executor(
                    None, download_and_cache_batched,
                    watchlist, warmup_start, end_date, cache_dir,
                )
            else:
                ohlcv_map = await loop.run_in_executor(
                    None, download_and_cache,
                    watchlist, warmup_start, end_date, cache_dir,
                )
        except Exception as e:
            logger.error("리플레이 데이터 다운로드 실패: %s", e)
            return {"status": "error", "detail": f"Data download failed: {e}"}

        if not ohlcv_map:
            return {"status": "error", "detail": "No OHLCV data loaded"}

        # HistoricalDataProvider 초기화
        from backtest.data_provider import HistoricalDataProvider
        provider = HistoricalDataProvider(ohlcv_map)

        # 거래일 분리
        warmup_dates = provider.get_warmup_dates(start_date)
        backtest_dates = provider.get_dates_in_range(start_date, end_date)

        if not backtest_dates:
            return {
                "status": "error",
                "detail": f"No trading dates in range {start_date} ~ {end_date}",
            }

        # 엔진 생성 (SSE 브로드캐스트 활성화)
        engine = SimulationEngine(
            on_event=self._event_bus.publish,
            market_id=market_id,
            watchlist=watchlist,
            initial_capital=config["initial_capital"],
            currency=config["currency"],
            currency_symbol=config["currency_symbol"],
            market_label=config["label"],
            strategy_mode=actual_strategy,
        )
        engine._is_running = True
        engine._replay_mode = True

        # 워밍업 (MA200 계산용, 거래 없이 데이터만 주입)
        if warmup_dates:
            last_warmup = warmup_dates[-1]
            provider.set_current_date(last_warmup)
            warmup_ohlcv = provider.get_ohlcv_up_to_date(watchlist)
            warmup_prices = provider.get_current_prices(watchlist)
            engine._ohlcv_cache = warmup_ohlcv
            engine._current_prices = warmup_prices
            engine._market_regime = engine._judge_market_regime()

        # 상태 저장
        self._engines[market_id] = engine
        self._replay_providers[market_id] = provider
        self._replay_state[market_id] = {
            "dates": backtest_dates,
            "current_index": 0,
            "current_date": backtest_dates[0],
            "speed": speed,
            "paused": False,
            "completed": False,
            "start_date": start_date,
            "end_date": end_date,
            "strategy": actual_strategy,
        }

        # 리플레이 루프 시작
        self._tasks[market_id] = asyncio.create_task(
            self._run_replay_loop(market_id)
        )

        logger.info(
            "리플레이 준비 완료 | market=%s | 워밍업=%d일 | 백테스트=%d일 | 종목=%d",
            market_id, len(warmup_dates), len(backtest_dates), len(ohlcv_map),
        )
        return {
            "status": "replay_started",
            "market": market_id,
            "strategy": actual_strategy,
            "total_days": len(backtest_dates),
            "start_date": start_date,
            "end_date": end_date,
            "initial_capital": config["initial_capital"],
        }

    async def _run_replay_loop(self, market_id: str) -> None:
        """히스토리컬 리플레이 날짜 루프.

        각 거래일마다 engine.run_backtest_day()를 실행하고
        SSE로 브로드캐스트한다. 속도/일시정지 제어 지원.
        """
        state = self._replay_state[market_id]
        engine = self._engines[market_id]
        provider = self._replay_providers[market_id]
        dates = state["dates"]
        watchlist = MARKET_CONFIG[market_id]["watchlist"]

        try:
            for i, date in enumerate(dates):
                if not engine._is_running:
                    break

                # 일시정지 대기
                while state.get("paused") and engine._is_running:
                    await asyncio.sleep(0.1)

                if not engine._is_running:
                    break

                provider.set_current_date(date)
                engine.reset_daily_state()

                day_ohlcv = provider.get_ohlcv_up_to_date(watchlist)
                day_prices = provider.get_current_prices(watchlist)
                engine.run_backtest_day(date, day_ohlcv, day_prices)

                # SSE 브로드캐스트 (포지션, 시그널, 리스크 등)
                await engine._broadcast_all()

                # 에쿼티 커브 브로드캐스트
                await self._event_bus.publish(
                    f"{market_id}:equity_curve",
                    [p.model_dump() for p in engine.equity_curve[-200:]],
                )

                # 진행 상태 업데이트 + SSE 발행
                state["current_index"] = i
                state["current_date"] = date
                await self._event_bus.publish(f"{market_id}:replay_progress", {
                    "current_date": date,
                    "progress_pct": round((i + 1) / len(dates) * 100, 1),
                    "day_index": i + 1,
                    "total_days": len(dates),
                    "speed": state["speed"],
                    "paused": False,
                })

                # 속도 제어
                spd = state["speed"]
                if spd > 0:
                    await asyncio.sleep(1.0 / spd)

            # 리플레이 완료 → 결과 캐싱
            state["completed"] = True
            summary = engine.get_performance_summary()
            self._replay_results[market_id] = {
                "market": market_id,
                "strategy": state.get("strategy", "momentum"),
                "start_date": state["start_date"],
                "end_date": state["end_date"],
                "initial_capital": engine.initial_capital,
                "final_equity": engine._get_total_equity(),
                "total_return_pct": summary.total_return_pct,
                "sharpe_ratio": summary.sharpe_ratio,
                "max_drawdown_pct": summary.max_drawdown_pct,
                "total_trades": summary.total_trades,
                "win_rate": summary.win_rate,
                "profit_factor": summary.profit_factor,
                "metrics": {**summary.model_dump(), "phase_stats": dict(engine._phase_stats)},
                "equity_curve": [p.model_dump() for p in engine.equity_curve],
                "trades": [t.model_dump() for t in engine.closed_trades],
            }

            await self._event_bus.publish(f"{market_id}:replay_progress", {
                "current_date": dates[-1] if dates else "",
                "progress_pct": 100,
                "day_index": len(dates),
                "total_days": len(dates),
                "speed": 0,
                "paused": False,
                "completed": True,
            })
            logger.info("리플레이 완료 | market=%s | %d일 처리", market_id, len(dates))

        except asyncio.CancelledError:
            logger.info("리플레이 취소됨 | market=%s", market_id)
        except Exception as e:
            logger.error("리플레이 오류 | market=%s | %s", market_id, e)
            state["completed"] = True
            await self._event_bus.publish(f"{market_id}:replay_progress", {
                "current_date": state.get("current_date", ""),
                "progress_pct": 0,
                "day_index": 0,
                "total_days": len(dates),
                "speed": 0,
                "paused": False,
                "completed": True,
                "error": str(e),
            })

    async def pause_replay(self, market_id: str) -> Dict[str, str]:
        """리플레이 일시정지."""
        state = self._replay_state.get(market_id)
        if not state:
            return {"status": "error", "detail": "No replay active"}
        state["paused"] = True
        logger.info("리플레이 일시정지 | market=%s", market_id)
        return {"status": "paused", "market": market_id}

    async def resume_replay(self, market_id: str) -> Dict[str, str]:
        """리플레이 재개."""
        state = self._replay_state.get(market_id)
        if not state:
            return {"status": "error", "detail": "No replay active"}
        state["paused"] = False
        logger.info("리플레이 재개 | market=%s", market_id)
        return {"status": "resumed", "market": market_id}

    def set_replay_speed(self, market_id: str, speed: float) -> Dict[str, Any]:
        """리플레이 속도 변경."""
        state = self._replay_state.get(market_id)
        if not state:
            return {"status": "error", "detail": "No replay active"}
        state["speed"] = max(0, speed)
        logger.info("리플레이 속도 변경 | market=%s | speed=%.1f", market_id, speed)
        return {"status": "speed_changed", "market": market_id, "speed": state["speed"]}

    def get_replay_result(self, market_id: str) -> Optional[Dict]:
        """마켓의 최근 리플레이 결과를 반환한다."""
        return self._replay_results.get(market_id)

    # ── 상태 조회 ─────────────────────────────────────────

    def get_status(self) -> Dict[str, Any]:
        """전체 컨트롤러 상태를 반환한다."""
        markets = {}
        for market_id, engine in self._engines.items():
            market_info: Dict[str, Any] = {
                "is_running": engine._is_running,
                "strategy_mode": engine.strategy_mode,
                "total_equity": engine._get_total_equity(),
                "cash": engine.cash,
                "position_count": len([
                    p for p in engine.positions.values()
                    if p.status == "ACTIVE"
                ]),
            }
            # 리플레이 상태 포함
            rs = self._replay_state.get(market_id)
            if rs:
                total = len(rs.get("dates", []))
                idx = rs.get("current_index", 0)
                market_info["replay"] = {
                    "active": not rs.get("completed", False),
                    "current_date": rs.get("current_date", ""),
                    "progress_pct": round((idx + 1) / max(total, 1) * 100, 1),
                    "total_days": total,
                    "speed": rs.get("speed", 1),
                    "paused": rs.get("paused", False),
                    "completed": rs.get("completed", False),
                    "start_date": rs.get("start_date", ""),
                    "end_date": rs.get("end_date", ""),
                }
            markets[market_id] = market_info
        return {
            "mode": self._mode.value,
            "markets": markets,
            "available_markets": VALID_MARKETS,
            "available_strategies": ["momentum", "smc", "breakout_retest", "mean_reversion"],
        }

    # ── 내부 ──────────────────────────────────────────────

    async def _heartbeat_loop(self) -> None:
        """15초마다 heartbeat + 컨트롤러 상태 발행."""
        while True:
            await asyncio.sleep(15)
            await self._event_bus.publish("heartbeat", {
                "clients": self._event_bus.client_count,
                "mode": self._mode.value,
            })
