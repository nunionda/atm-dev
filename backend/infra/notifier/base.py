"""
알림 추상 클래스 (어댑터 인터페이스)
문서: ATS-SAD-001 §5.6
확장성: NFR-E04 알림 채널 추가 대비
"""

from abc import ABC, abstractmethod

from common.types import DailyReportData


class BaseNotifier(ABC):
    """
    알림 추상 클래스.
    Telegram 외에 Slack, Discord 등 추가 시 이 인터페이스를 구현한다.
    """

    @abstractmethod
    def send_message(self, message: str, level: str = "INFO") -> bool:
        """
        메시지를 발송한다.
        level: INFO, WARNING, CRITICAL
        """
        ...

    @abstractmethod
    def send_report(self, report: DailyReportData) -> bool:
        """일일 리포트를 발송한다."""
        ...
