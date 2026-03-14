"""
Walk-Forward Validation.

전체 기간을 In-Sample(IS) / Out-of-Sample(OOS) 로 분할하여
전략 robustness를 검증한다.

Usage:
    python -m backtest.run --market sp500 --start 20200101 --end 20241231 --walk-forward
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from backtest.historical_engine import HistoricalBacktester
from backtest.metrics import ExtendedMetrics


@dataclass
class WalkForwardResult:
    """Walk-Forward 검증 결과."""

    # 설정
    full_start: str = ""
    full_end: str = ""
    is_ratio: float = 0.7
    split_date: str = ""  # IS/OOS 분할일

    # IS 결과
    is_result: Optional[ExtendedMetrics] = None

    # OOS 결과
    oos_result: Optional[ExtendedMetrics] = None

    # Robustness 비율
    sharpe_robustness: float = 0.0   # OOS Sharpe / IS Sharpe
    return_robustness: float = 0.0   # OOS CAGR / IS CAGR
    win_rate_robustness: float = 0.0 # OOS WinRate / IS WinRate
    overall_robustness: float = 0.0  # 종합 (3개 평균)

    # 판정
    verdict: str = ""  # ROBUST, MARGINAL, OVERFIT


class WalkForwardValidator:
    """
    Walk-Forward Validation 실행기.

    전체 기간을 IS(기본 70%) / OOS(30%)로 분할하여
    두 구간을 독립 백테스트한 뒤 성능 비율을 비교한다.

    Robustness Ratio > 0.5 → ROBUST
    0.3~0.5 → MARGINAL
    < 0.3 → OVERFIT
    """

    def __init__(
        self,
        market: str,
        start_date: str,
        end_date: str,
        is_ratio: float = 0.7,
        initial_capital: Optional[float] = None,
        slippage_pct: float = 0.001,
        commission_pct: float = 0.00015,
    ):
        self.market = market
        self.start_date = start_date
        self.end_date = end_date
        self.is_ratio = is_ratio
        self.initial_capital = initial_capital
        self.slippage_pct = slippage_pct
        self.commission_pct = commission_pct

    def _calc_split_date(self) -> str:
        """IS/OOS 분할일을 계산한다 (YYYYMMDD)."""
        from datetime import datetime, timedelta

        start = datetime.strptime(self.start_date, "%Y%m%d")
        end = datetime.strptime(self.end_date, "%Y%m%d")
        total_days = (end - start).days
        is_days = int(total_days * self.is_ratio)
        split = start + timedelta(days=is_days)
        return split.strftime("%Y%m%d")

    def run(self) -> WalkForwardResult:
        """Walk-Forward 검증 실행."""
        split_date = self._calc_split_date()

        print(f"\n{'='*60}")
        print(f"  WALK-FORWARD VALIDATION")
        print(f"{'='*60}")
        print(f"  전체 기간  : {_fmt(self.start_date)} ~ {_fmt(self.end_date)}")
        print(f"  IS/OOS 비율 : {self.is_ratio:.0%} / {1-self.is_ratio:.0%}")
        print(f"  분할일     : {_fmt(split_date)}")
        print(f"{'='*60}\n")

        # 1. In-Sample 백테스트
        print("📊 [1/2] In-Sample 백테스트...")
        is_bt = HistoricalBacktester(
            market=self.market,
            scenario="custom",
            start_date=self.start_date,
            end_date=split_date,
            initial_capital=self.initial_capital,
            slippage_pct=self.slippage_pct,
            commission_pct=self.commission_pct,
        )
        is_result = is_bt.run()

        # 2. Out-of-Sample 백테스트
        # OOS 시작일 = 분할일 다음 날
        from datetime import datetime, timedelta
        oos_start = (datetime.strptime(split_date, "%Y%m%d") + timedelta(days=1)).strftime("%Y%m%d")

        print("\n📊 [2/2] Out-of-Sample 백테스트...")
        oos_bt = HistoricalBacktester(
            market=self.market,
            scenario="custom",
            start_date=oos_start,
            end_date=self.end_date,
            initial_capital=self.initial_capital,
            slippage_pct=self.slippage_pct,
            commission_pct=self.commission_pct,
        )
        oos_result = oos_bt.run()

        # 3. Robustness 계산
        result = WalkForwardResult(
            full_start=self.start_date,
            full_end=self.end_date,
            is_ratio=self.is_ratio,
            split_date=split_date,
            is_result=is_result,
            oos_result=oos_result,
        )

        # Sharpe robustness
        if is_result.sharpe_ratio != 0:
            result.sharpe_robustness = oos_result.sharpe_ratio / is_result.sharpe_ratio
        elif oos_result.sharpe_ratio > 0:
            result.sharpe_robustness = 1.0  # IS=0이면 OOS가 양수면 개선된 것

        # Return robustness (CAGR)
        if is_result.cagr != 0:
            result.return_robustness = oos_result.cagr / is_result.cagr
        elif oos_result.cagr > 0:
            result.return_robustness = 1.0

        # Win rate robustness
        if is_result.win_rate > 0:
            result.win_rate_robustness = oos_result.win_rate / is_result.win_rate
        elif oos_result.win_rate > 0:
            result.win_rate_robustness = 1.0

        # 종합 robustness (3개 평균, 음수는 0으로 클램프)
        ratios = [
            max(result.sharpe_robustness, 0),
            max(result.return_robustness, 0),
            max(result.win_rate_robustness, 0),
        ]
        result.overall_robustness = sum(ratios) / len(ratios) if ratios else 0

        # 판정
        if result.overall_robustness >= 0.5:
            result.verdict = "ROBUST"
        elif result.overall_robustness >= 0.3:
            result.verdict = "MARGINAL"
        else:
            result.verdict = "OVERFIT"

        return result


def print_walk_forward_summary(result: WalkForwardResult, currency_symbol: str = "$"):
    """Walk-Forward 결과를 콘솔에 출력한다."""
    is_r = result.is_result
    oos_r = result.oos_result

    if not is_r or not oos_r:
        print("  ❌ Walk-Forward 결과 없음")
        return

    verdict_icon = {"ROBUST": "✅", "MARGINAL": "⚠️", "OVERFIT": "❌"}.get(result.verdict, "❓")

    print(f"\n{'='*70}")
    print(f"  WALK-FORWARD VALIDATION RESULT")
    print(f"{'='*70}")
    print(f"  전체 기간   : {_fmt(result.full_start)} ~ {_fmt(result.full_end)}")
    print(f"  분할일      : {_fmt(result.split_date)} (IS {result.is_ratio:.0%} / OOS {1-result.is_ratio:.0%})")
    print(f"{'='*70}")

    print(f"\n  {'Metric':<20}{'In-Sample':>14}{'Out-of-Sample':>14}{'Robustness':>12}")
    print(f"  {'─'*58}")
    print(f"  {'총수익률':<20}{is_r.total_return:>+13.2%}{oos_r.total_return:>+14.2%}{result.return_robustness:>11.2f}x")
    print(f"  {'CAGR':<20}{is_r.cagr:>+13.2%}{oos_r.cagr:>+14.2%}")
    print(f"  {'Sharpe':<20}{is_r.sharpe_ratio:>13.2f}{oos_r.sharpe_ratio:>14.2f}{result.sharpe_robustness:>11.2f}x")
    print(f"  {'Sortino':<20}{is_r.sortino_ratio:>13.2f}{oos_r.sortino_ratio:>14.2f}")
    print(f"  {'MDD':<20}{is_r.max_drawdown:>+13.2%}{oos_r.max_drawdown:>+14.2%}")
    print(f"  {'거래 수':<20}{is_r.total_trades:>13d}{oos_r.total_trades:>14d}")
    print(f"  {'승률':<20}{is_r.win_rate:>12.1%}{oos_r.win_rate:>13.1%}{result.win_rate_robustness:>11.2f}x")
    print(f"  {'PF':<20}{is_r.profit_factor:>13.2f}{oos_r.profit_factor:>14.2f}")
    print(f"  {'최종자산':<20}{currency_symbol}{is_r.final_value:>11,.0f}{currency_symbol}{oos_r.final_value:>12,.0f}")

    print(f"\n  {'─'*58}")
    print(f"  종합 Robustness : {result.overall_robustness:.2f}")
    print(f"  판정            : {verdict_icon} {result.verdict}")

    if result.verdict == "ROBUST":
        print(f"  → 전략이 OOS에서도 IS 성능의 50%+ 유지. 실전 배치 가능.")
    elif result.verdict == "MARGINAL":
        print(f"  → OOS 성능 하락 있으나 수용 가능 범위. 추가 검증 권장.")
    else:
        print(f"  → OOS 성능이 IS 대비 크게 하락. 과적합 위험.")

    print(f"\n{'='*70}\n")


def _fmt(date_str: str) -> str:
    """YYYYMMDD → YYYY-MM-DD."""
    if len(date_str) == 8:
        return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
    return date_str
