"""
ESF A/B 테스트 엔진 — 전략 변형 비교.

두 variant의 성과를 수집하여 통계적 유의성 검정(two-proportion z-test)을 수행하고,
승자를 선언하거나 INCONCLUSIVE로 마감한다.

참조:
  - infra/db/models.py (ESFExperiment, ESFVariant, ESFHypothesis, ESFResult)
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from infra.logger import get_logger

logger = get_logger("esf_ab_engine")


class ESFABEngine:
    """A/B 실험의 상태 확인, 결론 도출, 승자 승격을 담당한다."""

    def __init__(self, repo):
        """
        Args:
            repo: ESFJournalRepo 인스턴스 (DB 접근)
        """
        self.repo = repo

    def check_experiment_status(self, experiment_id: int) -> dict:
        """
        실험이 결론을 낼 준비가 되었는지 확인한다.

        Args:
            experiment_id: 실험 ID

        Returns:
            {ready, variant_a: {...}, variant_b: {...}, p_value, days_elapsed}
        """
        experiment = self.repo.get_experiment(experiment_id)
        if not experiment:
            logger.error("Experiment %d not found", experiment_id)
            return {"error": "experiment_not_found"}

        # ── Variant별 결과 수집 ──
        results_a = self.repo.get_variant_results(experiment["variant_a_id"])
        results_b = self.repo.get_variant_results(experiment["variant_b_id"])

        stats_a = self._compute_variant_stats(results_a)
        stats_b = self._compute_variant_stats(results_b)

        # Variant 이름 조회
        variant_a = self.repo.get_variant(experiment["variant_a_id"])
        variant_b = self.repo.get_variant(experiment["variant_b_id"])
        stats_a["name"] = variant_a["name"] if variant_a else f"variant_{experiment['variant_a_id']}"
        stats_b["name"] = variant_b["name"] if variant_b else f"variant_{experiment['variant_b_id']}"
        stats_a["variant_id"] = experiment["variant_a_id"]
        stats_b["variant_id"] = experiment["variant_b_id"]

        # ── 최소 트레이드 충족 여부 ──
        min_trades = experiment["min_trades_per_variant"] or 20
        ready = (stats_a["trades"] >= min_trades and stats_b["trades"] >= min_trades)

        # ── p-value 계산 (충분한 데이터가 있을 때) ──
        p_value = None
        if stats_a["trades"] >= 2 and stats_b["trades"] >= 2:
            _, p_value = self._two_proportion_ztest(
                stats_a["wins"], stats_a["trades"],
                stats_b["wins"], stats_b["trades"],
            )

        # ── 경과 일수 ──
        try:
            start_dt = datetime.fromisoformat(experiment["start_date"])
            days_elapsed = (datetime.now() - start_dt).days
        except (ValueError, TypeError):
            days_elapsed = 0

        result = {
            "experiment_id": experiment_id,
            "experiment_name": experiment["name"],
            "status": experiment["status"],
            "ready": ready,
            "variant_a": stats_a,
            "variant_b": stats_b,
            "p_value": round(p_value, 6) if p_value is not None else None,
            "min_trades_per_variant": min_trades,
            "days_elapsed": days_elapsed,
            "max_days": experiment["max_days"],
        }

        logger.info(
            "Experiment %d status | ready=%s | A: %d trades (WR %.1f%%) | "
            "B: %d trades (WR %.1f%%) | p=%.4f | days=%d",
            experiment_id, ready,
            stats_a["trades"], stats_a["win_rate"] * 100,
            stats_b["trades"], stats_b["win_rate"] * 100,
            p_value or 0, days_elapsed,
        )

        return result

    def conclude_experiment(self, experiment_id: int) -> dict:
        """
        실험을 비교하고 승자를 선언한다.

        Two-proportion z-test:
            p1 = wins_a / n_a, p2 = wins_b / n_b
            p_hat = (wins_a + wins_b) / (n_a + n_b)
            z = (p1 - p2) / sqrt(p_hat * (1-p_hat) * (1/n_a + 1/n_b))

        |z| > 1.96 (alpha=0.05): 유의한 차이 → 승률 높은 쪽 승리
        그 외: INCONCLUSIVE

        Returns:
            {winner, conclusion_reason, z_stat, p_value, variant_a, variant_b}
        """
        experiment = self.repo.get_experiment(experiment_id)
        if not experiment:
            return {"error": "experiment_not_found"}

        if experiment["status"] == "CONCLUDED":
            return {"error": "already_concluded", "winner_variant_id": experiment["winner_variant_id"]}

        results_a = self.repo.get_variant_results(experiment["variant_a_id"])
        results_b = self.repo.get_variant_results(experiment["variant_b_id"])

        stats_a = self._compute_variant_stats(results_a)
        stats_b = self._compute_variant_stats(results_b)

        n_a, wins_a = stats_a["trades"], stats_a["wins"]
        n_b, wins_b = stats_b["trades"], stats_b["wins"]

        # ── 최소 데이터 검증 ──
        if n_a < 2 or n_b < 2:
            reason = f"Insufficient data: A={n_a} trades, B={n_b} trades"
            self._update_experiment_conclusion(
                experiment_id, None, reason,
            )
            return {
                "winner": "INCONCLUSIVE",
                "conclusion_reason": reason,
                "z_stat": None,
                "p_value": None,
            }

        # ── Two-proportion z-test ──
        z_stat, p_value = self._two_proportion_ztest(wins_a, n_a, wins_b, n_b)

        significance = experiment.get("significance_threshold") or 0.05
        winner_variant_id = None
        conclusion_reason = ""

        if p_value is not None and p_value < significance:
            # 유의한 차이 발견
            if stats_a["win_rate"] > stats_b["win_rate"]:
                winner_variant_id = experiment["variant_a_id"]
                conclusion_reason = (
                    f"Variant A wins: WR {stats_a['win_rate']:.1%} vs {stats_b['win_rate']:.1%} "
                    f"(z={z_stat:.3f}, p={p_value:.4f} < {significance})"
                )
            else:
                winner_variant_id = experiment["variant_b_id"]
                conclusion_reason = (
                    f"Variant B wins: WR {stats_b['win_rate']:.1%} vs {stats_a['win_rate']:.1%} "
                    f"(z={z_stat:.3f}, p={p_value:.4f} < {significance})"
                )
        else:
            # PnL 기반 보조 판단 (승률 차이가 유의하지 않을 때)
            if stats_a["total_pnl"] > stats_b["total_pnl"] * 1.2:
                winner_variant_id = experiment["variant_a_id"]
                conclusion_reason = (
                    f"INCONCLUSIVE on WR (p={p_value:.4f}), but A has higher PnL: "
                    f"${stats_a['total_pnl']:.0f} vs ${stats_b['total_pnl']:.0f}"
                )
            elif stats_b["total_pnl"] > stats_a["total_pnl"] * 1.2:
                winner_variant_id = experiment["variant_b_id"]
                conclusion_reason = (
                    f"INCONCLUSIVE on WR (p={p_value:.4f}), but B has higher PnL: "
                    f"${stats_b['total_pnl']:.0f} vs ${stats_a['total_pnl']:.0f}"
                )
            else:
                conclusion_reason = (
                    f"INCONCLUSIVE: WR A={stats_a['win_rate']:.1%} vs B={stats_b['win_rate']:.1%} "
                    f"(z={z_stat:.3f}, p={p_value:.4f} >= {significance}), "
                    f"PnL A=${stats_a['total_pnl']:.0f} vs B=${stats_b['total_pnl']:.0f}"
                )

        # ── DB 업데이트 ──
        self._update_experiment_conclusion(
            experiment_id, winner_variant_id, conclusion_reason,
        )

        result = {
            "experiment_id": experiment_id,
            "winner": "INCONCLUSIVE" if winner_variant_id is None else f"variant_{winner_variant_id}",
            "winner_variant_id": winner_variant_id,
            "conclusion_reason": conclusion_reason,
            "z_stat": round(z_stat, 4) if z_stat is not None else None,
            "p_value": round(p_value, 6) if p_value is not None else None,
            "variant_a": stats_a,
            "variant_b": stats_b,
        }

        logger.info(
            "Experiment %d concluded | winner=%s | %s",
            experiment_id,
            result["winner"],
            conclusion_reason,
        )

        return result

    def auto_graduate_winner(self, experiment_id: int) -> dict:
        """
        승리한 variant를 baseline으로 승격한다.

        config.yaml을 자동 수정하지 않음 (너무 위험).
        DB에서 baseline 마킹만 수행하며, 사용자가 수동으로 설정 적용.

        Args:
            experiment_id: CONCLUDED 상태인 실험 ID

        Returns:
            승격 결과 dict
        """
        experiment = self.repo.get_experiment(experiment_id)
        if not experiment:
            return {"error": "experiment_not_found"}

        if experiment["status"] != "CONCLUDED":
            return {"error": "not_concluded", "status": experiment["status"]}

        if not experiment.get("winner_variant_id"):
            return {"error": "no_winner", "conclusion_reason": experiment.get("conclusion_reason")}

        winner_id = experiment["winner_variant_id"]
        winner_variant = self.repo.get_variant(winner_id)
        if not winner_variant:
            return {"error": "winner_variant_not_found", "variant_id": winner_id}

        # ── 1. 기존 baseline 해제 ──
        for v in self.repo.list_variants(active_only=False):
            if v["is_baseline"]:
                self.repo.update_variant(v["variant_id"], is_baseline=0)

        # ── 2. 승자를 baseline으로 마킹 ──
        self.repo.update_variant(winner_id, is_baseline=1)

        # ── 3. 파라미터 오버라이드 정보 ──
        import json
        # _to_dict already parses param_overrides_json into a dict
        overrides = winner_variant["param_overrides_json"] or {}
        if isinstance(overrides, str):
            try:
                overrides = json.loads(overrides)
            except json.JSONDecodeError:
                overrides = {}

        result = {
            "experiment_id": experiment_id,
            "graduated_variant_id": winner_id,
            "graduated_variant_name": winner_variant["name"],
            "param_overrides": overrides,
            "note": "Baseline updated in DB. Apply param_overrides to config.yaml manually.",
        }

        logger.info(
            "Variant %d (%s) graduated to baseline | overrides=%s",
            winner_id, winner_variant["name"], json.dumps(overrides),
        )

        return result

    # ══════════════════════════════════════════
    # Private helpers
    # ══════════════════════════════════════════

    def _two_proportion_ztest(
        self, wins_a: int, n_a: int, wins_b: int, n_b: int,
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        Two-proportion z-test를 수행한다.

        Args:
            wins_a: A 그룹 성공 수
            n_a: A 그룹 총 시행 수
            wins_b: B 그룹 성공 수
            n_b: B 그룹 총 시행 수

        Returns:
            (z_stat, p_value) 튜플. 계산 불가 시 (None, None).
        """
        if n_a == 0 or n_b == 0:
            return None, None

        p1 = wins_a / n_a
        p2 = wins_b / n_b
        p_hat = (wins_a + wins_b) / (n_a + n_b)

        # pooled proportion이 0 또는 1이면 분산 = 0
        if p_hat <= 0 or p_hat >= 1:
            return 0.0, 1.0

        se = math.sqrt(p_hat * (1 - p_hat) * (1 / n_a + 1 / n_b))
        if se <= 0:
            return 0.0, 1.0

        z = (p1 - p2) / se

        # Two-tailed p-value: 2 * (1 - Phi(|z|)) = erfc(|z| / sqrt(2))
        p_value = math.erfc(abs(z) / math.sqrt(2))

        return z, p_value

    def _compute_variant_stats(self, results: list) -> dict:
        """
        Variant의 결과 목록에서 통계를 계산한다.

        Args:
            results: list of result dicts

        Returns:
            {trades, wins, losses, win_rate, avg_pnl, total_pnl, sharpe}
        """
        trades = len(results)
        if trades == 0:
            return {
                "trades": 0, "wins": 0, "losses": 0,
                "win_rate": 0.0, "avg_pnl": 0.0, "total_pnl": 0.0,
                "sharpe": 0.0,
            }

        wins = sum(1 for r in results if r.get("is_win", 0))
        losses = trades - wins
        pnl_list = [r.get("pnl_dollars", 0.0) for r in results]
        total_pnl = sum(pnl_list)
        avg_pnl = total_pnl / trades
        win_rate = wins / trades

        # Sharpe 근사
        if trades >= 2:
            mean_pnl = avg_pnl
            variance = sum((p - mean_pnl) ** 2 for p in pnl_list) / (trades - 1)
            std_pnl = math.sqrt(variance) if variance > 0 else 0
            sharpe = (mean_pnl / std_pnl) if std_pnl > 0 else 0.0
        else:
            sharpe = 0.0

        return {
            "trades": trades,
            "wins": wins,
            "losses": losses,
            "win_rate": round(win_rate, 4),
            "avg_pnl": round(avg_pnl, 2),
            "total_pnl": round(total_pnl, 2),
            "sharpe": round(sharpe, 4),
        }

    def _update_experiment_conclusion(
        self,
        experiment_id: int,
        winner_variant_id: Optional[int],
        conclusion_reason: str,
    ):
        """실험 결론을 DB에 기록한다."""
        now_str = datetime.now().isoformat()
        today_str = datetime.now().strftime("%Y-%m-%d")
        self.repo.update_experiment(
            experiment_id,
            status="CONCLUDED",
            winner_variant_id=winner_variant_id,
            conclusion_reason=conclusion_reason,
            concluded_at=now_str,
            end_date=today_str,
        )
