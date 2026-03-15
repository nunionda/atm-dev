"""
리스크 관리 모듈
문서: ATS-SAD-001 §5.3, ATS-BRD-001 §3.3~3.4

리스크 게이트: RG1(종목수) → RG2(비중) → RG3(일매매한도) → RG4(볼린저밴드)
리스크 한도:   BR-R01(일일-5%) → BR-R02(MDD-15%)
"""

from __future__ import annotations

from common.types import Portfolio, RiskCheckResult, Signal
from data.config_manager import ATSConfig
from infra.logger import get_logger

logger = get_logger("risk_manager")


class RiskManager:
    """
    리스크 게이트와 한도를 관리한다.
    모든 매수 주문 전에 check_risk_gates()를 호출해야 한다.
    """

    def __init__(self, config: ATSConfig):
        self.config = config
        self.pc = config.portfolio  # PortfolioConfig
        self.rc = config.risk       # RiskConfig

    def check_risk_gates(self, signal: Signal, portfolio: Portfolio) -> RiskCheckResult:
        """
        리스크 게이트 RG1~RG4를 순차 체크한다 (BRD §2.3.3).
        하나라도 실패하면 매수를 거부한다.
        """
        # ── RG1: 포트폴리오 여유 (최대 보유 종목수) ──
        if portfolio.active_count >= self.pc.max_positions:
            reason = f"보유종목 한도 초과 ({portfolio.active_count}/{self.pc.max_positions})"
            logger.info("RG1 FAIL | %s | %s", signal.stock_code, reason)
            return RiskCheckResult(passed=False, failed_gate="RG1", reason=reason)

        # ── RG2: 종목 비중 한도 ──
        # 기존 보유 비중 + 신규 매수 예정 비중이 한도를 초과하는지 체크
        if portfolio.total_capital > 0:
            existing_weight = 0.0
            if hasattr(portfolio, 'position_weights') and portfolio.position_weights:
                existing_weight = portfolio.position_weights.get(signal.stock_code, 0.0)
            new_buy_weight = self.pc.max_weight_per_stock  # 1회 매수 최대 비중
            total_weight = existing_weight + new_buy_weight
            if total_weight > self.pc.max_weight_per_stock:
                reason = f"종목 비중 초과 (기존 {existing_weight:.1%} + 신규 {new_buy_weight:.1%} = {total_weight:.1%} > {self.pc.max_weight_per_stock:.1%})"
                logger.info("RG2 FAIL | %s | %s", signal.stock_code, reason)
                return RiskCheckResult(passed=False, failed_gate="RG2", reason=reason)

        # ── RG3: 일일 매매금액 한도 ──
        buy_amount = portfolio.total_capital * self.pc.max_weight_per_stock
        if self.rc.max_order_amount > 0:
            if portfolio.daily_buy_amount + buy_amount > self.rc.max_order_amount * self.pc.max_positions:
                reason = f"일일 매매금액 한도 초과"
                logger.info("RG3 FAIL | %s | %s", signal.stock_code, reason)
                return RiskCheckResult(passed=False, failed_gate="RG3", reason=reason)

        # ── RG4: 볼린저밴드 상단 미도달 ──
        if signal.bb_upper and signal.current_price >= signal.bb_upper:
            reason = f"볼린저밴드 상단 도달 (price={signal.current_price:.0f} >= BB상단={signal.bb_upper:.0f})"
            logger.info("RG4 FAIL | %s | %s", signal.stock_code, reason)
            return RiskCheckResult(passed=False, failed_gate="RG4", reason=reason)

        logger.info("Risk gates PASSED | %s (%s)", signal.stock_name, signal.stock_code)
        return RiskCheckResult(passed=True)

    def check_daily_loss_limit(self, portfolio: Portfolio) -> bool:
        """
        BR-R01: 일일 총 손실 -5% 체크.
        Returns: True이면 매매 중단 필요.
        """
        if portfolio.total_capital <= 0:
            return False
        daily_pnl_pct = portfolio.daily_pnl / portfolio.total_capital
        if daily_pnl_pct <= self.rc.daily_loss_limit:
            logger.critical(
                "DAILY LOSS LIMIT HIT | pnl=%.2f%% | limit=%.2f%%",
                daily_pnl_pct * 100, self.rc.daily_loss_limit * 100,
            )
            return True
        return False

    def check_mdd_limit(self, portfolio: Portfolio) -> bool:
        """
        BR-R02: MDD -15% 체크.
        Returns: True이면 시스템 일시 정지 필요.
        """
        if portfolio.mdd <= self.rc.mdd_limit:
            logger.critical(
                "MDD LIMIT HIT | mdd=%.2f%% | limit=%.2f%%",
                portfolio.mdd * 100, self.rc.mdd_limit * 100,
            )
            return True
        return False

    def check_max_order_amount(self, amount: float) -> bool:
        """BR-R04: 1회 주문 최대 금액 체크. True면 거부."""
        if amount > self.rc.max_order_amount:
            logger.warning(
                "Order amount exceeds limit | amount=%.0f > limit=%.0f",
                amount, self.rc.max_order_amount,
            )
            return True
        return False

    def calculate_buy_quantity(
        self, current_price: float, portfolio: Portfolio
    ) -> int:
        """
        매수 수량을 계산한다 (BRD §2.7).
        매수금액 = 총투자금 × 종목당비중(15%)
        매수수량 = 매수금액 ÷ 현재가 (소수점 버림)
        """
        if current_price <= 0:
            return 0

        buy_amount = portfolio.total_capital * self.pc.max_weight_per_stock

        # 현금 잔고 확인 (BR-P03 최소 현금 비율 30% 유지)
        min_cash = portfolio.total_capital * self.pc.min_cash_ratio
        available_cash = portfolio.cash_balance - min_cash
        if available_cash <= 0:
            logger.info("Insufficient cash after min_cash_ratio reserve")
            return 0

        buy_amount = min(buy_amount, available_cash)

        # 1회 최대 주문금액 체크 (BR-R04)
        buy_amount = min(buy_amount, self.rc.max_order_amount)

        quantity = int(buy_amount / current_price)  # 소수점 버림
        return max(quantity, 0)
