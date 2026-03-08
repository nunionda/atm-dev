"""
매매 메인 루프
문서: ATS-SAD-001 §5.7

장중 매매의 핵심 루프:
  Phase 1: 포지션 모니터링 (UC-04) — 청산이 진입보다 우선
  Phase 2: 일일 손실 한도 체크 (BR-R01)
  Phase 3: 시그널 스캔 (UC-02) + 매수 (UC-03)
  Phase 4: 미체결 주문 처리
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Optional

from common.enums import SystemState
from core.state_manager import SystemStateManager
from data.config_manager import ATSConfig
from data.market_data import MarketDataProvider
from infra.broker.base import BaseBroker
from infra.db.repository import Repository
from infra.logger import get_logger
from infra.notifier.base import BaseNotifier
from order.order_executor import OrderExecutor
from position.position_manager import PositionManager
from report.report_generator import ReportGenerator
from risk.risk_manager import RiskManager
from strategy.base import BaseStrategy

logger = get_logger("main_loop")


class MainLoop:
    """장중 매매 루프를 관리한다."""

    def __init__(
        self,
        config: ATSConfig,
        state_manager: SystemStateManager,
        strategy: BaseStrategy,
        risk_manager: RiskManager,
        order_executor: OrderExecutor,
        position_manager: PositionManager,
        market_data: MarketDataProvider,
        report_generator: ReportGenerator,
        broker: BaseBroker,
        notifier: BaseNotifier,
        repository: Repository,
    ):
        self.config = config
        self.state = state_manager
        self.strategy = strategy
        self.risk_mgr = risk_manager
        self.order_exec = order_executor
        self.pos_mgr = position_manager
        self.market = market_data
        self.report = report_generator
        self.broker = broker
        self.notifier = notifier
        self.repo = repository

        self._total_capital: float = 0
        self._daily_loss_triggered = False

    # ══════════════════════════════════════════
    # 시스템 기동 (UC-01)
    # ══════════════════════════════════════════

    def initialize(self) -> bool:
        """
        시스템 초기화 (UC-01 기본 흐름).
        Returns: True if successful
        """
        try:
            logger.info("=" * 60)
            logger.info("ATS System Initializing...")

            # Step 3: 인증 토큰 발급
            self.broker.authenticate()

            # Step 4: 기존 포지션 로드
            active = self.pos_mgr.get_active_positions()
            logger.info("Loaded %d active positions", len(active))

            # Step 5-6: 유니버스 & OHLCV 업데이트
            universe = self.repo.get_active_universe()
            codes = [u.stock_code for u in universe]
            logger.info("Universe loaded: %d stocks", len(codes))

            self.market.update_ohlcv(codes, period=60)

            # 잔고 조회 → 총 투자금 설정
            balance = self.broker.get_balance()
            self._total_capital = balance.cash + balance.total_eval
            logger.info("Total capital: %,.0f won", self._total_capital)

            # Step 7: 상태 → READY
            self.state.transition_to(SystemState.READY)

            # Step 8: 기동 알림
            pnl_pct = (balance.total_pnl / self._total_capital * 100) if self._total_capital > 0 else 0
            self.notifier.send_message(
                f"✅ ATS 기동 완료 | 보유종목: {len(active)}개 | "
                f"평가손익: {pnl_pct:+.2f}% | 매매 대기 중"
            )

            logger.info("System READY | capital=%,.0f | positions=%d",
                         self._total_capital, len(active))
            return True

        except Exception as e:
            logger.critical("Initialization failed: %s", e, exc_info=True)
            self.state.force_error(str(e))
            self.notifier.send_message(
                f"🚨 ATS 기동 실패 | {e}", level="CRITICAL"
            )
            return False

    # ══════════════════════════════════════════
    # 매매 루프 1주기 (1분마다 호출)
    # ══════════════════════════════════════════

    def run_cycle(self):
        """
        매매 주기 1회 실행 (SAD §5.7 MainLoop.run_cycle).
        
        Phase 1: 포지션 모니터링 (청산 우선)
        Phase 2: 일일 손실 한도 체크
        Phase 3: 시그널 스캔 + 매수
        Phase 4: 미체결 주문 처리
        """
        if not self.state.is_running:
            return

        try:
            now = datetime.now()

            # ── Phase 1: 포지션 모니터링 (UC-04) ──
            if self.pos_mgr.has_active_positions():
                self._phase_monitor_positions()

            # ── Phase 2: 일일 손실 한도 (BR-R01) ──
            portfolio = self._build_portfolio()
            if self.risk_mgr.check_daily_loss_limit(portfolio):
                if not self._daily_loss_triggered:
                    self._daily_loss_triggered = True
                    self.notifier.send_message(
                        f"⚠️ 일일 손실 한도 도달 ({portfolio.daily_pnl / portfolio.total_capital:.1%}) | "
                        f"금일 신규 매매 중단 | 기존 포지션 유지",
                        level="CRITICAL",
                    )
                # 손절 모니터링은 계속하지만 신규 매수는 중단
                self.order_exec.check_pending_orders()
                return

            # MDD 체크 (BR-R02)
            if self.risk_mgr.check_mdd_limit(portfolio):
                self.notifier.send_message(
                    f"🚨 MDD 한도 도달 ({portfolio.mdd:.1%}) | 시스템 일시 정지",
                    level="CRITICAL",
                )
                self.state.transition_to(SystemState.STOPPING)
                return

            # ── Phase 3: 시그널 스캔 + 매수 (UC-02, UC-03) ──
            if self._is_buy_allowed_time(now):
                self._phase_scan_and_buy(portfolio)

            # ── Phase 4: 미체결 주문 처리 ──
            self.order_exec.check_pending_orders()

        except Exception as e:
            logger.error("Cycle error: %s", e, exc_info=True)
            # 개별 주기 에러는 시스템을 중단하지 않음 (다음 주기에 재시도)

    def _phase_monitor_positions(self):
        """Phase 1: 보유 포지션 모니터링 및 청산."""
        active = self.pos_mgr.get_active_positions()
        codes = [p.stock_code for p in active]

        # 현재가 조회
        prices = self.market.get_current_prices(codes)

        # OHLCV 캐시에 실시간 데이터 반영
        ohlcv = {}
        for code, price_data in prices.items():
            df = self.market.append_realtime_to_ohlcv(code, price_data)
            ohlcv[code] = df

        # 청산 시그널 스캔
        exit_signals = self.strategy.scan_exit_signals(active, ohlcv, prices)

        for es in exit_signals:
            pos = next((p for p in active if p.position_id == es.position_id), None)
            if pos:
                self.order_exec.execute_sell(es, pos)

        # 트레일링 최고가 갱신 (청산되지 않은 포지션)
        closed_ids = {es.position_id for es in exit_signals}
        for pos in active:
            if pos.position_id not in closed_ids:
                price_data = prices.get(pos.stock_code)
                if price_data:
                    self.pos_mgr.update_trailing_high(pos.position_id, price_data.current_price)

    def _phase_scan_and_buy(self, portfolio):
        """Phase 3: 시그널 스캔 + 매수 주문."""
        universe = self.repo.get_active_universe()
        codes = [u.stock_code for u in universe]

        # 현재가 조회 (유니버스 전체 — API 제한 고려, 배치 처리)
        prices = self.market.get_current_prices(codes)

        # OHLCV 캐시 활용
        ohlcv = {}
        for code in codes:
            df = self.market.get_ohlcv(code)
            if not df.empty and code in prices:
                df = self.market.append_realtime_to_ohlcv(code, prices[code])
            ohlcv[code] = df

        # 시그널 스캔
        signals = self.strategy.scan_entry_signals(codes, ohlcv, prices)

        if signals:
            logger.info("Entry signals found: %d stocks", len(signals))

        # 시그널별 리스크 체크 + 매수
        for signal in signals:
            # 리스크 게이트 통과 확인
            risk_result = self.risk_mgr.check_risk_gates(signal, portfolio)
            if not risk_result.passed:
                self.repo.log_trade_event(
                    "RISK_CHECK_FAILED",
                    stock_code=signal.stock_code,
                    detail={"gate": risk_result.failed_gate, "reason": risk_result.reason},
                )
                continue

            self.repo.log_trade_event(
                "RISK_CHECK_PASSED",
                stock_code=signal.stock_code,
            )

            # 매수 주문
            result = self.order_exec.execute_buy(signal, portfolio)
            if result and result.success:
                # 포트폴리오 갱신 (다음 종목 매수 시 반영)
                portfolio = self._build_portfolio()

    # ══════════════════════════════════════════
    # 장 마감 처리
    # ══════════════════════════════════════════

    def on_market_close(self):
        """장 마감 후 처리 (보유일수 증가, 리포트 생성)."""
        logger.info("Market closed - running post-market tasks")

        # 보유일수 +1
        self.pos_mgr.increment_holding_days()

        # 일일 리포트 생성 (UC-05)
        self.report.generate_daily_report(self._total_capital)

        # 일일 손실 플래그 리셋
        self._daily_loss_triggered = False

        # 캐시 클리어
        self.market.clear_cache()

        logger.info("Post-market tasks complete")

    # ══════════════════════════════════════════
    # 시스템 중지 (UC-08)
    # ══════════════════════════════════════════

    def shutdown(self):
        """시스템을 안전하게 중지한다 (UC-08)."""
        logger.info("Shutting down ATS...")

        # 미체결 주문 처리
        self.order_exec.check_pending_orders()

        active = self.pos_mgr.get_active_positions()
        pending = self.pos_mgr.get_pending_positions()

        self.notifier.send_message(
            f"⛔ ATS 중지 | 보유종목: {len(active)}개 | "
            f"미체결: {len(pending)}건"
        )

        self.state.transition_to(SystemState.STOPPED)
        logger.info("ATS shutdown complete")

    # ══════════════════════════════════════════
    # 유틸
    # ══════════════════════════════════════════

    def _is_buy_allowed_time(self, now: datetime) -> bool:
        """BR-B03, BR-B04: 매수 허용 시간대 확인."""
        sc = self.config.schedule
        buy_start = time(*map(int, sc.buy_start.split(":")))
        buy_end = time(*map(int, sc.buy_end.split(":")))
        return buy_start <= now.time() <= buy_end

    def _build_portfolio(self):
        """현재 포트폴리오 현황을 구성한다."""
        try:
            balance = self.broker.get_balance()
            return self.pos_mgr.build_portfolio(
                cash_balance=balance.cash,
                total_capital=self._total_capital,
            )
        except Exception as e:
            logger.error("Portfolio build failed: %s", e)
            return self.pos_mgr.build_portfolio(
                cash_balance=0,
                total_capital=self._total_capital,
            )
