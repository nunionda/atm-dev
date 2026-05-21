"""
리포트 생성 모듈
문서: ATS-SAD-001, ATS-BRD-001 UC-05
"""

from __future__ import annotations

from datetime import datetime

from common.types import DailyReportData
from infra.broker.base import BaseBroker
from infra.db.repository import Repository
from infra.logger import get_logger
from infra.notifier.base import BaseNotifier
from position.position_manager import PositionManager

logger = get_logger("report")


class ReportGenerator:
    """일일 리포트 및 백테스트 리포트를 생성한다."""

    def __init__(
        self,
        repository: Repository,
        position_manager: PositionManager,
        broker: BaseBroker,
        notifier: BaseNotifier,
    ):
        self.repo = repository
        self.pos_mgr = position_manager
        self.broker = broker
        self.notifier = notifier

    def generate_daily_report(self, total_capital: float) -> DailyReportData:
        """
        일일 리포트를 생성하고 DB에 저장, Telegram으로 발송한다.
        (UC-05 기본 흐름)
        """
        today = datetime.now().strftime("%Y-%m-%d")

        # 잔고 조회
        try:
            balance = self.broker.get_balance()
            cash = balance.cash
            total_eval = balance.total_eval
            unrealized = balance.total_pnl
        except Exception as e:
            logger.error("Balance fetch failed for report: %s", e)
            cash = 0
            total_eval = 0
            unrealized = 0

        # 당일 청산된 포지션으로 실현 손익 계산
        closed_today = self.repo.get_today_closed_positions(today)
        realized_pnl = sum(p.pnl or 0 for p in closed_today)
        win_count = sum(1 for p in closed_today if (p.pnl or 0) > 0)
        lose_count = sum(1 for p in closed_today if (p.pnl or 0) <= 0)

        # 매수/매도 건수 (orders 테이블에서 집계)
        # 간략화: closed_today 기반
        sell_count = len(closed_today)
        buy_count = len([
            p for p in self.pos_mgr.get_active_positions()
            if p.entry_date and p.entry_date.startswith(today)
        ])

        # 수익률 계산
        total_pnl = realized_pnl + unrealized
        daily_return = (total_pnl / total_capital * 100) if total_capital > 0 else 0
        total_value = cash + total_eval

        # 누적 수익률
        cumulative_return = ((total_value - total_capital) / total_capital * 100) if total_capital > 0 else 0

        # MDD 계산 (간략화: 현재 총자산 기준)
        latest = self.repo.get_latest_report()
        prev_peak = latest.total_value if latest and latest.total_value else total_capital
        peak = max(prev_peak, total_value)
        mdd = ((total_value - peak) / peak * 100) if peak > 0 else 0

        report = DailyReportData(
            trade_date=today,
            buy_count=buy_count,
            sell_count=sell_count,
            buy_amount=0,  # 상세 집계 필요 시 orders 테이블 조인
            sell_amount=0,
            realized_pnl=realized_pnl,
            unrealized_pnl=unrealized,
            total_pnl=total_pnl,
            daily_return=daily_return,
            cumulative_return=cumulative_return,
            active_positions=self.pos_mgr.active_count(),
            cash_balance=cash,
            total_value=total_value,
            mdd=mdd,
            win_count=win_count,
            lose_count=lose_count,
        )

        # DB 저장
        self.repo.save_daily_report(report)

        # Telegram 발송
        self.notifier.send_report(report)

        logger.info(
            "Daily report generated | date=%s | pnl=%.0f | return=%.2f%%",
            today, total_pnl, daily_return,
        )
        return report
