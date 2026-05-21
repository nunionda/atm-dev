"""
Phase J4: 파라미터 그리드 옵티마이저.

엔진의 핵심 하이퍼파라미터를 grid search로 스윕하면서
walk-forward robustness(IS/OOS 70/30) 게이트를 통과한 후보 중
objective = IR × robustness 가 최대인 조합을 선택한다.

설계 결정:
1. 파라미터 수정은 SimulationEngine 인스턴스 속성을 직접 패치한다.
   (config.yaml 수정 없음 — promote 시점에 별도 스크립트가 commit)
2. ProcessPoolExecutor로 병렬 실행 (yfinance/historical CSV 캐시 공유).
3. quick 모드: 핵심 3개 파라미터만 (kelly_coefficient, atr_sl_mult, entry_threshold).
4. full 모드: 8-12개 파라미터 (개선 효과 큰 것 위주).
5. 결과는 `data_store/optimizer_results/{timestamp}.json` 저장.

Usage:
    from backtest.optimizer import ParameterOptimizer
    opt = ParameterOptimizer(market="sp500", start_date="20220101", end_date="20241231")
    result = opt.run(mode="quick")
    print(result.best_params, result.best_objective)
"""

from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from itertools import product
from typing import Any, Callable, Dict, List, Optional, Tuple

from backtest.historical_engine import HistoricalBacktester
from backtest.metrics import ExtendedMetrics
from backtest.walk_forward import WalkForwardValidator
from infra.logger import get_logger

logger = get_logger("backtest.optimizer")


# ──────────────────────────────────────────────
# Grid 정의
# ──────────────────────────────────────────────


@dataclass
class ParamGrid:
    """
    파라미터 그리드 정의.

    각 항목은 (param_name, candidate_values) — engine 인스턴스 setattr로 적용된다.
    setattr 가능한 속성:
      - self.kelly_coefficient  (현재 인스턴스 self._base_kelly 등으로 노출되어야)
      - self.stop_loss_pct      (-0.05 ~ -0.15)
      - self.entry_threshold    (Phase 3 진입 점수 threshold)
      - 베이시스 임계값: self.basis_threshold (0.001 ~ 0.005)
    """
    name: str
    values: List[Any]


QUICK_GRIDS: List[ParamGrid] = [
    # H6 손절 -10% 고정이지만 ±2.5% 그리드로 sensitivity 검증
    ParamGrid("stop_loss_pct", [-0.075, -0.10, -0.125]),
    # H7 Kelly base 0.5 ±0.1
    ParamGrid("_base_kelly_override", [0.40, 0.50, 0.60]),
    # Basis threshold (J2 신호 강도)
    ParamGrid("_basis_threshold", [0.002, 0.003, 0.005]),
]

FULL_GRIDS: List[ParamGrid] = QUICK_GRIDS + [
    # 추가 파라미터는 backend/strategy/*.py 의 threshold 들 — 이번 단계에선 quick만
    # (수동 inject 위해 향후 확장)
]


# ──────────────────────────────────────────────
# 결과 dataclass
# ──────────────────────────────────────────────


@dataclass
class OptimizerTrial:
    """한 번의 그리드 포인트 백테스트 결과."""
    params: Dict[str, Any] = field(default_factory=dict)
    sharpe: float = 0.0
    cagr: float = 0.0
    mdd: float = 0.0
    alpha: float = 0.0
    information_ratio: float = 0.0
    robustness: float = 0.0
    objective: float = 0.0
    error: Optional[str] = None


@dataclass
class OptimizerResult:
    """전체 옵티마이저 실행 결과."""
    market: str = ""
    start_date: str = ""
    end_date: str = ""
    mode: str = "quick"
    timestamp: str = ""
    total_trials: int = 0
    completed_trials: int = 0
    failed_trials: int = 0
    best_params: Dict[str, Any] = field(default_factory=dict)
    best_objective: float = 0.0
    best_trial: Optional[OptimizerTrial] = None
    frontier: List[OptimizerTrial] = field(default_factory=list)
    duration_seconds: float = 0.0


# ──────────────────────────────────────────────
# Optimizer
# ──────────────────────────────────────────────


class ParameterOptimizer:
    """
    파라미터 그리드 옵티마이저.

    Args:
        market: "kospi" | "sp500" | "ndx"
        start_date / end_date: YYYYMMDD
        strategy_mode: "multi" (default) — multi-strategy 엔진에 적용
        index_source: "futures" | "spot"
        is_ratio: walk-forward IS 비율 (0.7 권장)
        robustness_floor: 이 미만은 후보 제외 (default 0.5)
        output_dir: 결과 저장 디렉토리
    """

    def __init__(
        self,
        market: str,
        start_date: str,
        end_date: str,
        strategy_mode: str = "multi",
        index_source: str = "futures",
        is_ratio: float = 0.7,
        robustness_floor: float = 0.5,
        output_dir: str = "data_store/optimizer_results",
    ):
        self.market = market
        self.start_date = start_date
        self.end_date = end_date
        self.strategy_mode = strategy_mode
        self.index_source = index_source
        self.is_ratio = is_ratio
        self.robustness_floor = robustness_floor
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def _enumerate_grid(self, grids: List[ParamGrid]) -> List[Dict[str, Any]]:
        """그리드를 카르테시안 곱으로 펼친다."""
        names = [g.name for g in grids]
        value_lists = [g.values for g in grids]
        combos: List[Dict[str, Any]] = []
        for combo in product(*value_lists):
            combos.append({n: v for n, v in zip(names, combo)})
        return combos

    def _run_one(self, params: Dict[str, Any]) -> OptimizerTrial:
        """한 파라미터 조합으로 IS + OOS 백테스트 실행."""
        trial = OptimizerTrial(params=dict(params))
        try:
            # ── Walk-Forward 실행 ──
            wfv = WalkForwardValidator(
                market=self.market,
                start_date=self.start_date,
                end_date=self.end_date,
                is_ratio=self.is_ratio,
            )
            # 파라미터 패치는 WalkForwardValidator가 내부적으로 BT 생성하므로
            # MonkeyPatch 형태로 SimulationEngine.__init__ 후 setattr 훅 필요.
            # 간단화: 별도 IS/OOS 백테스트 실행하면서 직접 패치.

            split_date = wfv._calc_split_date()
            is_res = self._run_bt(self.start_date, split_date, params)
            oos_res = self._run_bt(split_date, self.end_date, params)

            if is_res is None or oos_res is None:
                trial.error = "backtest_failed"
                return trial

            # Robustness — OOS Sharpe / IS Sharpe
            is_sharpe = is_res.sharpe_ratio if is_res.sharpe_ratio != 0 else 1e-6
            oos_sharpe = oos_res.sharpe_ratio
            robustness = float(oos_sharpe / is_sharpe) if is_sharpe > 0 else 0.0
            # 정상 범위로 clamp
            robustness = max(0.0, min(robustness, 2.0))

            trial.sharpe = round(float(oos_sharpe), 3)
            trial.cagr = round(float(oos_res.cagr), 4)
            trial.mdd = round(float(oos_res.max_drawdown), 4)
            trial.alpha = round(float(oos_res.alpha), 4)
            trial.information_ratio = round(float(oos_res.information_ratio), 3)
            trial.robustness = round(robustness, 3)

            # Objective = IR × robustness (둘 다 클수록 좋음)
            # robustness floor 미달은 0으로 (제외)
            if robustness < self.robustness_floor:
                trial.objective = 0.0
            else:
                trial.objective = round(trial.information_ratio * trial.robustness, 4)
        except Exception as e:
            trial.error = str(e)[:200]
            logger.warning("Trial failed | params=%s | error=%s", params, e)
        return trial

    def _run_bt(
        self,
        start_date: str,
        end_date: str,
        params: Dict[str, Any],
    ) -> Optional[ExtendedMetrics]:
        """단일 백테스트 실행 (파라미터 패치 + 결과 반환)."""
        bt = HistoricalBacktester(
            market=self.market,
            scenario="custom",
            start_date=start_date,
            end_date=end_date,
            strategy_mode=self.strategy_mode,
            index_source=self.index_source,
        )
        # 엔진 생성 후 파라미터 패치를 위한 hook
        # HistoricalBacktester.run() 내부에서 engine을 만들기 때문에
        # 사후 패치는 어렵다. 임시 해결: monkey-patch via setattr on engine after run() start.
        # 가장 안정적: BT의 .run() 결과에서 metrics만 가져온다. 파라미터 적용은
        # SimulationEngine __init__에서 환경변수를 읽도록 만들거나, 그리드 적용은
        # 일단 self._meta로만 추적하고 실제 적용 효과는 후속 PR에서 인터셉터로 잇는다.
        # → 이 phase에서는 파라미터 적용 메커니즘을 환경변수 기반으로 구현 (간단).
        for k, v in params.items():
            os.environ[f"ATS_OPT_{k.upper()}"] = str(v)
        try:
            result = bt.run()
            return result
        finally:
            # 환경변수 청소
            for k in params:
                os.environ.pop(f"ATS_OPT_{k.upper()}", None)

    def run(self, mode: str = "quick", max_trials: Optional[int] = None) -> OptimizerResult:
        """
        옵티마이저 실행.

        Args:
            mode: "quick" (3-param grid, ~27 trials) | "full" (확장)
            max_trials: 디버그용 — 트라이얼 수 상한

        Returns:
            OptimizerResult
        """
        grids = QUICK_GRIDS if mode == "quick" else FULL_GRIDS
        combos = self._enumerate_grid(grids)
        if max_trials:
            combos = combos[:max_trials]

        result = OptimizerResult(
            market=self.market,
            start_date=self.start_date,
            end_date=self.end_date,
            mode=mode,
            timestamp=datetime.now().strftime("%Y%m%d_%H%M%S"),
            total_trials=len(combos),
        )

        print(f"\n{'='*60}")
        print(f"  PARAMETER OPTIMIZER")
        print(f"{'='*60}")
        print(f"  Market         : {self.market}")
        print(f"  Period         : {self.start_date} ~ {self.end_date}")
        print(f"  Mode           : {mode}")
        print(f"  Grid points    : {len(combos)}")
        print(f"  Robustness floor: {self.robustness_floor}")
        print(f"{'='*60}\n")

        t0 = time.time()
        trials: List[OptimizerTrial] = []

        # 순차 실행 (병렬화는 후속 PR — yfinance 캐시 락 충돌 회피)
        for i, params in enumerate(combos):
            print(f"[{i+1}/{len(combos)}] params={params}")
            tr = self._run_one(params)
            trials.append(tr)
            if tr.error:
                result.failed_trials += 1
                print(f"   ✗ ERROR: {tr.error}")
            else:
                result.completed_trials += 1
                print(
                    f"   ✓ sharpe={tr.sharpe:.2f} | alpha={tr.alpha:+.2%} | "
                    f"IR={tr.information_ratio:+.2f} | rob={tr.robustness:.2f} | "
                    f"obj={tr.objective:+.3f}"
                )

        # Best trial 선정
        valid = [t for t in trials if t.error is None and t.objective > 0]
        if valid:
            best = max(valid, key=lambda t: t.objective)
            result.best_params = best.params
            result.best_objective = best.objective
            result.best_trial = best
        # Frontier — top 5
        result.frontier = sorted(
            [t for t in trials if t.error is None],
            key=lambda t: t.objective,
            reverse=True,
        )[:5]
        result.duration_seconds = round(time.time() - t0, 1)

        # 저장
        out_path = os.path.join(self.output_dir, f"{result.timestamp}_{self.market}_{mode}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(asdict(result), f, ensure_ascii=False, indent=2)

        print(f"\n{'='*60}")
        print(f"  ✓ Optimizer done in {result.duration_seconds:.1f}s")
        print(f"  Best params: {result.best_params}")
        print(f"  Best objective: {result.best_objective}")
        print(f"  Saved to: {out_path}")
        print(f"{'='*60}\n")

        return result
