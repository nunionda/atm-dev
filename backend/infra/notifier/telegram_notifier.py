"""
Telegram 알림 구현체
문서: ATS-SAD-001 §13
"""

from __future__ import annotations

import requests

from common.types import DailyReportData
from infra.logger import get_logger
from infra.notifier.base import BaseNotifier

logger = get_logger("telegram")

# 레벨별 이모지 매핑
LEVEL_EMOJI = {
    "INFO": "ℹ️",
    "WARNING": "⚠️",
    "CRITICAL": "🚨",
}


class TelegramNotifier(BaseNotifier):
    """Telegram Bot API를 통한 알림 발송."""

    BASE_URL = "https://api.telegram.org/bot{token}"

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.api_url = self.BASE_URL.format(token=bot_token)
        logger.info("TelegramNotifier initialized | chat_id=%s", chat_id)

    def send_message(self, message: str, level: str = "INFO") -> bool:
        """메시지를 Telegram으로 발송한다."""
        emoji = LEVEL_EMOJI.get(level, "ℹ️")
        full_message = f"{emoji} {message}"

        try:
            resp = requests.post(
                f"{self.api_url}/sendMessage",
                json={
                    "chat_id": self.chat_id,
                    "text": full_message,
                    "parse_mode": "HTML",
                },
                timeout=10,
            )
            resp.raise_for_status()
            logger.debug("Telegram sent | level=%s | len=%d", level, len(message))
            return True
        except requests.RequestException as e:
            logger.error("Telegram send failed: %s", e)
            return False

    def send_report(self, report: DailyReportData) -> bool:
        """일일 리포트를 포맷팅하여 발송한다. (SAD §13.1)"""
        win_total = report.win_count + report.lose_count
        win_rate = (report.win_count / win_total * 100) if win_total > 0 else 0

        text = (
            f"📊 <b>ATS 일일 리포트 ({report.trade_date})</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"매수: {report.buy_count}건 | 매도: {report.sell_count}건\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"실현 손익: {report.realized_pnl:+,.0f}원\n"
            f"평가 손익: {report.unrealized_pnl:+,.0f}원\n"
            f"총 손익: {report.total_pnl:+,.0f}원\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"일일 수익률: {report.daily_return:+.2f}%\n"
            f"누적 수익률: {report.cumulative_return:+.2f}%\n"
            f"MDD: {report.mdd:.2f}%\n"
            f"승률: {win_rate:.1f}% ({report.win_count}승 {report.lose_count}패)\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"보유 종목: {report.active_positions}개\n"
            f"현금 잔고: {report.cash_balance:,.0f}원\n"
            f"총 자산: {report.total_value:,.0f}원\n"
        )

        return self.send_message(text, level="INFO")
