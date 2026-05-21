"""
장 시간 기반 스케줄러
문서: ATS-SAD-001 §5.1

08:50  시스템 기동 (INIT → READY)
09:30  매매 루프 시작 (READY → RUNNING)
15:20  신규 매수 중단 (→ STOPPING 시작)
15:30  장 마감
15:35  일일 리포트 생성 → STOPPED
"""

from __future__ import annotations

import signal
import time
from datetime import datetime, time as dtime

from common.enums import SystemState
from core.main_loop import MainLoop
from core.state_manager import SystemStateManager
from data.config_manager import ATSConfig
from infra.logger import get_logger

logger = get_logger("scheduler")


class Scheduler:
    """시간 기반 매매 스케줄러."""

    def __init__(
        self,
        config: ATSConfig,
        state_manager: SystemStateManager,
        main_loop: MainLoop,
    ):
        self.config = config
        self.state = state_manager
        self.loop = main_loop
        self._running = False
        self._setup_signal_handlers()

    def _setup_signal_handlers(self):
        """Ctrl+C / kill 시그널 핸들러."""
        def handler(signum, frame):
            logger.info("Received signal %d - initiating shutdown", signum)
            self._running = False
        signal.signal(signal.SIGINT, handler)
        signal.signal(signal.SIGTERM, handler)

    def run(self):
        """
        메인 실행 루프.
        시스템을 초기화하고, 장 시간에 맞춰 매매 루프를 실행한다.
        """
        logger.info("=" * 60)
        logger.info("ATS Scheduler starting")

        # ── 초기화 (UC-01) ──
        if not self.loop.initialize():
            logger.critical("Initialization failed - exiting")
            return

        self._running = True
        sc = self.config.schedule
        scan_interval = sc.scan_interval_sec

        # 시간 파싱
        buy_start = self._parse_time(sc.buy_start)
        buy_end = self._parse_time(sc.buy_end)
        market_close = self._parse_time(sc.market_close)
        report_time = self._parse_time(sc.report_time)

        # ── 매매 루프 ──
        while self._running:
            now = datetime.now()
            current_time = now.time()

            try:
                # READY → RUNNING 전이 (매매 시작 시간)
                if self.state.is_ready and current_time >= buy_start:
                    self.state.transition_to(SystemState.RUNNING)
                    logger.info("Trading session started")

                # RUNNING: 매매 주기 실행
                if self.state.is_running:
                    self.loop.run_cycle()

                    # 장 마감 임박 (15:20) → STOPPING
                    stopping_time = self._parse_time(sc.buy_end)
                    if current_time >= stopping_time:
                        logger.info("Market closing soon - stopping new buys")
                        self.state.transition_to(SystemState.STOPPING)

                # STOPPING: 청산/미체결만 처리
                if self.state.state == SystemState.STOPPING:
                    self.loop.run_cycle()  # 모니터링만 실행 (매수는 시간 체크로 자동 차단)

                    if current_time >= market_close:
                        # 장 마감 후 처리
                        self.loop.on_market_close()
                        self.loop.shutdown()
                        break

                # 이미 장 마감 시간 이후면 종료
                if current_time >= report_time and self.state.is_stopped:
                    break

                # 스캔 간격 대기
                time.sleep(scan_interval)

            except KeyboardInterrupt:
                logger.info("Keyboard interrupt received")
                self._running = False
            except Exception as e:
                logger.error("Scheduler error: %s", e, exc_info=True)
                time.sleep(5)  # 에러 후 짧은 대기

        # ── 정리 ──
        if not self.state.is_stopped:
            self.loop.shutdown()

        logger.info("ATS Scheduler stopped")
        logger.info("=" * 60)

    def _parse_time(self, time_str: str) -> dtime:
        """'HH:MM' 형식 문자열을 time 객체로 변환."""
        parts = time_str.split(":")
        return dtime(int(parts[0]), int(parts[1]))
