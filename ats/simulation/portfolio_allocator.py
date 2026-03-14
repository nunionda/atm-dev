"""
Tactical 전용 포트폴리오 배분 계산기 (Kelly Criterion 기반).

최적화 계산 근거:
  Full Kelly f* = 0.36 (WR 57.5%, PF 2.67, b=1.97)
  Half-Kelly(0.18) × 다각화 보정(2.2x) × 실무(0.85x) = 0.34 → 0.30

투자 비율 (Kelly 30%, 자본금 1억):
  총 투자금 = 1억 × 0.30 = 3,000만
  Tactical (100%): 60종목 → 3,000만 (종목당 ~50만)
  현금: 7,000만

참조: stock_theory/Kelly Criterion.md, CLAUDE.md §Kelly Criterion
"""

from __future__ import annotations

from typing import Dict

from data.config_manager import PortfolioAllocationConfig
from infra.logger import get_logger

logger = get_logger("portfolio_allocator")


class PortfolioAllocator:
    """Tactical 전용 포트폴리오 배분 계산기.

    전체 투자금을 모멘텀 스캐너 선별 종목에 균등 배분한다.
    """

    def __init__(self, config: PortfolioAllocationConfig):
        self.config = config
        logger.info(
            "PortfolioAllocator 초기화 | kelly=%.0f%% | tactical=%d종목(%.0f%%)",
            config.kelly_fraction * 100,
            config.tactical.top_n,
            config.tactical.weight * 100,
        )

    def calculate_allocations(self, total_equity: float) -> Dict[str, float]:
        """총 자본 기준 Tactical 배분 금액 산출.

        Args:
            total_equity: 전체 포트폴리오 자산 (현금 + 포지션 평가액)

        Returns:
            배분 금액 딕셔너리:
            - investable: 투자 가능 총액 (kelly_fraction 적용)
            - cash_reserve: 현금 보유 목표액
            - tactical_amount: Tactical 종목 총 목표 투자액
            - tactical_per_stock: Tactical 종목 1개당 목표 투자액
        """
        investable = total_equity * self.config.kelly_fraction
        tactical_top_n = max(self.config.tactical.top_n, 1)

        return {
            "investable": investable,
            "cash_reserve": total_equity - investable,
            "tactical_amount": investable * self.config.tactical.weight,
            "tactical_per_stock": (investable * self.config.tactical.weight) / tactical_top_n,
        }

    def get_tactical_max_weight(self, total_equity: float) -> float:
        """Tactical 종목 1개당 최대 비중(비율) 산출.

        Args:
            total_equity: 전체 포트폴리오 자산

        Returns:
            0.0 ~ 1.0 사이의 비중 비율 (e.g., 0.005 = 0.5%)
        """
        if total_equity <= 0:
            return 0.0
        alloc = self.calculate_allocations(total_equity)
        return alloc["tactical_per_stock"] / total_equity
