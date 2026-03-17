"""
ESF 결과 기록기 — 가설의 실제 결과 저장 + 통계 갱신.

가설(hypothesis)에 대한 실제 거래 결과를 기록하고,
전체 누적 통계를 dimension별로 재계산한다.

참조:
  - infra/db/models.py (ESFResult, ESFHypothesis, ESFCumulativeStat)
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional

from infra.logger import get_logger

logger = get_logger("esf_result_recorder")

# 티커별 포인트 밸류
POINT_VALUE = {
    "ES=F": 50.0,    # E-mini S&P 500: $50/pt
    "MES=F": 5.0,    # Micro E-mini S&P 500: $5/pt
    "NQ=F": 20.0,    # E-mini NASDAQ 100: $20/pt
    "MNQ=F": 2.0,    # Micro E-mini NASDAQ 100: $2/pt
}


class ESFResultRecorder:
    """가설 결과를 기록하고 누적 통계를 갱신한다."""

    def __init__(self, repo):
        """
        Args:
            repo: ESFJournalRepo 인스턴스 (DB 접근)
        """
        self.repo = repo

    def record_result(self, hypothesis_id: int, result_data: dict) -> dict:
        """
        가설에 대한 실제 결과를 기록한다.

        Args:
            hypothesis_id: 대상 가설 ID
            result_data: {
                actual_entry_price, actual_exit_price, actual_direction,
                contracts, exit_reason, holding_minutes,
                actual_high, actual_low, actual_close
            }

        Returns:
            기록된 결과 dict (result_id 포함)
        """
        # ── 1. 가설 검증 ──
        hypothesis = self.repo.get_hypothesis(hypothesis_id)
        if not hypothesis:
            logger.error("Hypothesis %d not found", hypothesis_id)
            return {"error": "hypothesis_not_found", "hypothesis_id": hypothesis_id}

        if hypothesis["status"] not in ("PENDING", "ACTIVE"):
            logger.warning(
                "Hypothesis %d status is %s (expected PENDING/ACTIVE)",
                hypothesis_id, hypothesis["status"],
            )
            return {"error": "invalid_status", "status": hypothesis["status"]}

        # ── 2. P&L 계산 ──
        entry = result_data.get("actual_entry_price", 0.0)
        exit_price = result_data.get("actual_exit_price", 0.0)
        contracts = result_data.get("contracts", 0)
        actual_direction = result_data.get("actual_direction", hypothesis["direction"])

        direction_mult = 1.0 if actual_direction == "LONG" else -1.0
        point_value = POINT_VALUE.get(hypothesis["ticker"], 50.0)

        pnl_dollars = (exit_price - entry) * contracts * point_value * direction_mult
        pnl_pct = ((exit_price - entry) / entry * 100.0 * direction_mult) if entry > 0 else 0.0

        is_win = 1 if pnl_dollars > 0 else 0

        # ── 3. 방향 정확도 ──
        direction_correct = 1 if actual_direction == hypothesis["direction"] else 0

        # ── 4. SL/TP 히트 판정 ──
        sl_hit = 0
        tp_hit = 0
        exit_reason = result_data.get("exit_reason", "")

        if exit_reason and "SL" in exit_reason.upper():
            sl_hit = 1
        elif exit_reason and "TP" in exit_reason.upper():
            tp_hit = 1
        else:
            # 가격 기반 판정 (exit_reason이 명확하지 않은 경우)
            actual_high = result_data.get("actual_high")
            actual_low = result_data.get("actual_low")

            if actual_direction == "LONG":
                if actual_low is not None and actual_low <= hypothesis["stop_loss"]:
                    sl_hit = 1
                if actual_high is not None and actual_high >= hypothesis["take_profit"]:
                    tp_hit = 1
            else:
                if actual_high is not None and actual_high >= hypothesis["stop_loss"]:
                    sl_hit = 1
                if actual_low is not None and actual_low <= hypothesis["take_profit"]:
                    tp_hit = 1

        # ── 5. 결과 DB 저장 ──
        result_row = self.repo.create_result(
            hypothesis_id=hypothesis_id,
            actual_entry_price=entry,
            actual_exit_price=exit_price,
            actual_direction=actual_direction,
            contracts=contracts,
            pnl_dollars=round(pnl_dollars, 2),
            pnl_pct=round(pnl_pct, 4),
            is_win=is_win,
            exit_reason=exit_reason,
            holding_minutes=result_data.get("holding_minutes", 0),
            actual_high=result_data.get("actual_high"),
            actual_low=result_data.get("actual_low"),
            actual_close=result_data.get("actual_close"),
            direction_correct=direction_correct,
            sl_hit=sl_hit,
            tp_hit=tp_hit,
        )
        result_id = result_row["result_id"]

        # ── 6. 가설 상태 업데이트 ──
        self.repo.update_hypothesis_status(hypothesis_id, "CLOSED")

        # ── 7. 누적 통계 갱신 ──
        self._refresh_cumulative_stats()

        result = result_row

        logger.info(
            "Result recorded | hypothesis=%d | result=%s | %s | PnL=$%.2f (%.2f%%) | %s",
            hypothesis_id, result_id, actual_direction,
            pnl_dollars, pnl_pct, "WIN" if is_win else "LOSS",
        )

        return result

    def record_skip(self, hypothesis_id: int, reason: str = "") -> dict:
        """
        가설을 SKIPPED로 마킹한다.

        Args:
            hypothesis_id: 대상 가설 ID
            reason: 스킵 사유

        Returns:
            업데이트된 상태 dict
        """
        hypothesis = self.repo.get_hypothesis(hypothesis_id)
        if not hypothesis:
            logger.error("Hypothesis %d not found", hypothesis_id)
            return {"error": "hypothesis_not_found"}

        self.repo.update_hypothesis_status(hypothesis_id, "SKIPPED")

        logger.info(
            "Hypothesis %d skipped | reason=%s",
            hypothesis_id, reason or "(none)",
        )

        return {
            "hypothesis_id": hypothesis_id,
            "status": "SKIPPED",
            "reason": reason,
        }

    def _refresh_cumulative_stats(self):
        """
        모든 누적 통계를 처음부터 재계산한다.

        가설 + 결과 조인 데이터에서 다차원 집계:
        - "direction": LONG, SHORT
        - "hour": entry_hour_et 값별
        - "regime": BULL, NEUTRAL, BEAR, CRISIS
        - "grade": A, B, C
        - "variant": variant_id 값별
        - "overall": "all"
        """
        # 전체 가설+결과 조인 데이터 조회
        rows = self.repo.get_all_results_with_hypotheses()
        if not rows:
            logger.debug("No hypotheses with results — skipping stat refresh")
            return

        # dimension 그룹별 데이터 수집
        groups: Dict[str, Dict[str, list]] = defaultdict(lambda: defaultdict(list))

        for row in rows:
            pnl = row.get("pnl_dollars", 0.0)
            is_win = row.get("is_win", 0)
            holding = row.get("holding_minutes", 0)
            direction_correct = row.get("direction_correct", 0)

            entry = {
                "pnl": pnl,
                "is_win": is_win,
                "holding_minutes": holding,
                "direction_correct": direction_correct,
            }

            # overall
            groups["overall"]["all"].append(entry)

            # direction
            direction = row.get("direction", "")
            if direction:
                groups["direction"][direction].append(entry)

            # hour
            hour = row.get("entry_hour_et")
            if hour is not None:
                groups["hour"][str(hour)].append(entry)

            # regime
            regime = row.get("regime", "")
            if regime:
                groups["regime"][regime].append(entry)

            # grade
            grade = row.get("grade", "")
            if grade:
                groups["grade"][grade].append(entry)

            # variant
            variant_id = row.get("variant_id")
            if variant_id is not None:
                groups["variant"][str(variant_id)].append(entry)

        # 각 그룹에 대해 통계 계산 및 upsert
        now_str = datetime.now().isoformat()

        for dimension, dim_groups in groups.items():
            for dim_value, entries in dim_groups.items():
                stat = self._compute_group_stats(entries)
                stat["dimension"] = dimension
                stat["dimension_value"] = dim_value
                stat["updated_at"] = now_str

                # variant dimension에서 variant_id 추출
                if dimension == "variant":
                    try:
                        stat["variant_id"] = int(dim_value)
                    except (ValueError, TypeError):
                        stat["variant_id"] = None
                else:
                    stat["variant_id"] = None

                self.repo.upsert_cumulative_stat(
                    dimension=stat["dimension"],
                    dimension_value=stat["dimension_value"],
                    variant_id=stat.get("variant_id"),
                    stats=stat,
                )

        logger.info(
            "Cumulative stats refreshed | %d dimensions, %d groups",
            len(groups), sum(len(g) for g in groups.values()),
        )

    def _compute_group_stats(self, entries: list) -> dict:
        """
        그룹 내 엔트리들의 집계 통계를 계산한다.

        Returns:
            {total_trades, wins, losses, win_rate, total_pnl, avg_pnl,
             sharpe_approx, profit_factor, avg_holding_minutes, direction_accuracy}
        """
        total = len(entries)
        if total == 0:
            return {
                "total_trades": 0, "wins": 0, "losses": 0,
                "win_rate": 0.0, "total_pnl": 0.0, "avg_pnl": 0.0,
                "sharpe_approx": 0.0, "profit_factor": 0.0,
                "avg_holding_minutes": 0.0, "direction_accuracy": 0.0,
            }

        wins = sum(1 for e in entries if e["is_win"])
        losses = total - wins
        pnl_list = [e["pnl"] for e in entries]
        total_pnl = sum(pnl_list)
        avg_pnl = total_pnl / total
        win_rate = wins / total

        # Sharpe 근사: mean / std
        if len(pnl_list) >= 2:
            pnl_std = float(self._std(pnl_list))
            sharpe_approx = (avg_pnl / pnl_std) if pnl_std > 0 else 0.0
        else:
            sharpe_approx = 0.0

        # Profit Factor
        gross_profit = sum(p for p in pnl_list if p > 0)
        gross_loss = abs(sum(p for p in pnl_list if p < 0))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (
            float("inf") if gross_profit > 0 else 0.0
        )

        # 평균 보유 시간
        holding_list = [e["holding_minutes"] for e in entries if e["holding_minutes"] > 0]
        avg_holding = sum(holding_list) / len(holding_list) if holding_list else 0.0

        # 방향 정확도
        dir_correct = sum(1 for e in entries if e["direction_correct"])
        direction_accuracy = dir_correct / total

        return {
            "total_trades": total,
            "wins": wins,
            "losses": losses,
            "win_rate": round(win_rate, 4),
            "total_pnl": round(total_pnl, 2),
            "avg_pnl": round(avg_pnl, 2),
            "sharpe_approx": round(sharpe_approx, 4),
            "profit_factor": round(profit_factor, 4) if profit_factor != float("inf") else 999.0,
            "avg_holding_minutes": round(avg_holding, 1),
            "direction_accuracy": round(direction_accuracy, 4),
        }

    @staticmethod
    def _std(values: list) -> float:
        """표준편차 계산 (numpy 미사용, 경량)."""
        n = len(values)
        if n < 2:
            return 0.0
        mean = sum(values) / n
        variance = sum((x - mean) ** 2 for x in values) / (n - 1)
        return math.sqrt(variance)
