"""
백테스트용 NullNotifier — 알림을 무시한다.
"""

from common.types import DailyReportData
from infra.notifier.base import BaseNotifier


class NullNotifier(BaseNotifier):
    """모든 알림을 무시하는 Notifier 구현체."""

    def send_message(self, message: str, level: str = "INFO") -> bool:
        return True

    def send_report(self, report: DailyReportData) -> bool:
        return True
