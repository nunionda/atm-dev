"""
멀티 전략 모드용 전략별 자본 배분 관리자.
Extracted from engine.py for modularity (C2 decomposition).
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

from simulation.constants import REGIME_STRATEGY_WEIGHTS


class StrategyAllocator:
    """
    멀티 전략 모드용 전략별 자본 배분 관리자.

    각 전략에 레짐 기반 비중을 할당하고, 전략별 포지션 수/자본 한도를 관리.
    물리적 현금 풀은 단일이지만, 가상 예산(virtual budget)으로 전략 간 자본을 분리.

    Phase 3 추가:
    - Correlation Control: 전략간 rolling corr 모니터링, corr>0.4 시 비중 조정
    - Dynamic Kelly: regime + VIX + 최근 승률 반영 Kelly × 0.25
    """

    def __init__(self, strategies: List[str], regime: str = "NEUTRAL"):
        self.strategies = strategies
        self.regime = regime
        self.weights: Dict[str, float] = {}
        # Volatility Targeting 상태
        self._daily_returns: List[float] = []
        self._target_vol: float = 0.15  # 연 15% 포트폴리오 변동성
        self._vol_scalar: float = 1.0   # target_vol / realized_vol
        self._prev_equity: float = 0.0
        # Phase 7: Risk Parity 상태
        self._rp_weights: Dict[str, float] = {}  # 전략별 RP 비중
        self._rp_warmup_done: bool = False  # 데이터 충분 여부
        # Correlation Control 상태 (Phase 3.1)
        self._strategy_daily_pnl: Dict[str, List[float]] = {s: [] for s in strategies}
        self._corr_matrix: Dict[tuple, float] = {}  # (s1, s2) → rolling corr
        self._corr_adjustment: Dict[str, float] = {}  # strategy → 비중 조정 승수
        # Dynamic Kelly 상태 (Phase 3.4)
        self._strategy_wins: Dict[str, int] = {s: 0 for s in strategies}
        self._strategy_losses: Dict[str, int] = {s: 0 for s in strategies}
        self._strategy_win_pnl: Dict[str, float] = {s: 0.0 for s in strategies}
        self._strategy_loss_pnl: Dict[str, float] = {s: 0.0 for s in strategies}
        self._kelly_scalar: float = 1.0
        self._vix_ema: float = 0.0
        self._apply_regime_weights(regime)

    def _apply_regime_weights(self, regime: str):
        """레짐에 맞는 전략 비중 적용 (correlation + Risk Parity 조정 반영)."""
        weights = REGIME_STRATEGY_WEIGHTS.get(regime, REGIME_STRATEGY_WEIGHTS["NEUTRAL"])
        raw = {s: weights.get(s, 0.0) for s in self.strategies}
        # Correlation 조정 적용
        if self._corr_adjustment:
            for s in raw:
                raw[s] *= self._corr_adjustment.get(s, 1.0)
            total = sum(raw.values())
            if total > 0:
                raw = {s: w / total for s, w in raw.items()}
        # Phase 7: Risk Parity 블렌딩 (비활성화 — 모든 비율에서 성능 저하 확인)
        # RP는 momentum(핵심 전략) 비중을 과도하게 축소하여 net alpha 감소
        # if self._rp_warmup_done and self._rp_weights:
        #     blended = {}
        #     for s in self.strategies:
        #         regime_w = raw.get(s, 0.0)
        #         rp_w = self._rp_weights.get(s, regime_w)
        #         blended[s] = 0.90 * regime_w + 0.10 * rp_w
        #     total = sum(blended.values())
        #     if total > 0:
        #         raw = {s: w / total for s, w in blended.items()}
        self.weights = raw

    def update_regime(self, regime: str):
        """레짐 변경 시 비중 갱신."""
        if regime != self.regime:
            self.regime = regime
            self._apply_regime_weights(regime)

    def override_weights(self, weights: Dict[str, float]):
        """지수 추세 기반 전략 비중 오버라이드.

        INDEX_TREND_STRATEGY_WEIGHTS에서 받은 비중으로 교체.
        활성 전략에 없는 전략은 무시하고 나머지를 정규화.
        Correlation 조정도 적용.
        """
        active_weights = {}
        for strat, w in weights.items():
            if strat in self.strategies:
                active_weights[strat] = w

        if not active_weights:
            return  # 유효한 전략 없으면 무시

        # Correlation 조정 적용
        if self._corr_adjustment:
            for s in active_weights:
                active_weights[s] *= self._corr_adjustment.get(s, 1.0)

        # 정규화 (합 = 1.0)
        total = sum(active_weights.values())
        if total > 0:
            self.weights = {s: w / total for s, w in active_weights.items()}

    def is_active(self, strategy: str) -> bool:
        """해당 전략이 현재 레짐에서 활성인지."""
        return self.weights.get(strategy, 0.0) > 0.01

    def get_budget(self, strategy: str, total_equity: float, used_by_strategy: float) -> float:
        """전략의 남은 가용 자본 (가상 예산)."""
        weight = self.weights.get(strategy, 0.0)
        budget = total_equity * weight
        return max(0.0, budget - used_by_strategy)

    def get_max_positions(self, strategy: str, regime_max: int) -> int:
        """전략별 최대 포지션 수 (Largest Remainder Method)."""
        dist = self.distribute_positions(regime_max)
        return dist.get(strategy, 1)

    def distribute_positions(self, regime_max: int) -> Dict[str, int]:
        """Largest Remainder Method로 포지션 수 공정 분배.

        Phase 4.2: round() 대신 LRM 사용 — 저비중 전략 굶주림 해결.
        합계가 regime_max를 초과하지 않도록 보장.
        """
        active = {s: w for s, w in self.weights.items() if w > 0.01}
        if not active:
            return {}
        raw = {s: regime_max * w for s, w in active.items()}
        floors = {s: int(v) for s, v in raw.items()}
        remainders = {s: raw[s] - floors[s] for s in active}
        leftover = regime_max - sum(floors.values())
        for s in sorted(remainders, key=lambda k: remainders[k], reverse=True):
            if leftover <= 0:
                break
            floors[s] += 1
            leftover -= 1
        return {s: max(1, v) for s, v in floors.items()}

    def get_max_weight_for_strategy(self, strategy: str, regime_max_weight: float) -> float:
        """전략별 종목당 최대 비중. 전략 비중이 작을수록 더 집중."""
        weight = self.weights.get(strategy, 0.0)
        if weight < 0.15:
            return regime_max_weight
        return regime_max_weight

    # ── Volatility Targeting ──

    def update_daily_return(self, total_equity: float):
        """일일 수익률 기록 및 변동성 스칼라 갱신."""
        if self._prev_equity > 0:
            daily_ret = (total_equity - self._prev_equity) / self._prev_equity
            self._daily_returns.append(daily_ret)
            if len(self._daily_returns) > 60:
                self._daily_returns = self._daily_returns[-60:]
            if len(self._daily_returns) >= 20:
                recent = self._daily_returns[-20:]
                realized_vol = float(np.std(recent)) * (252 ** 0.5)
                if realized_vol > 0.001:
                    self._vol_scalar = min(1.5, max(0.3, self._target_vol / realized_vol))
                else:
                    self._vol_scalar = 1.0
        self._prev_equity = total_equity

    def get_vol_scalar(self) -> float:
        """현재 변동성 타겟팅 스칼라 (0.3 ~ 1.5)."""
        return self._vol_scalar

    # ── Phase 7: Risk Parity ──

    def update_risk_parity(self):
        """전략별 실현 변동성의 역수에 비례하는 Risk Parity 비중 계산.

        전략별 일일 PnL의 비영 일(포지션 있는 날)만 사용.
        최소 10일 데이터 필요, 2개 이상 전략에 데이터 있어야 활성화.
        """
        active_vols: Dict[str, float] = {}
        for s in self.strategies:
            pnl_series = self._strategy_daily_pnl.get(s, [])
            # 비영 일만 (포지션 있는 날의 PnL)
            nonzero = [p for p in pnl_series[-60:] if abs(p) > 0.01]
            if len(nonzero) >= 10:
                vol = float(np.std(nonzero))
                active_vols[s] = max(vol, 0.001)

        if len(active_vols) < 2:
            self._rp_warmup_done = False
            return

        # 역변동성 비중
        inv_vols = {s: 1.0 / v for s, v in active_vols.items()}
        total_iv = sum(inv_vols.values())
        self._rp_weights = {s: iv / total_iv for s, iv in inv_vols.items()}
        self._rp_warmup_done = True

        # 비중 재적용
        self._apply_regime_weights(self.regime)

    # ── Correlation Control (Phase 3.1) ──

    def record_strategy_daily_pnl(self, strategy: str, daily_pnl: float):
        """전략별 일일 PnL 기록."""
        if strategy in self._strategy_daily_pnl:
            self._strategy_daily_pnl[strategy].append(daily_pnl)
            if len(self._strategy_daily_pnl[strategy]) > 60:
                self._strategy_daily_pnl[strategy] = self._strategy_daily_pnl[strategy][-60:]

    def update_correlation(self):
        """전략간 rolling correlation 계산 및 비중 조정.

        corr > 0.4 인 페어의 고상관 전략 비중 축소, 저상관 전략 비중 확대.
        20거래일 이상 데이터 필요.
        """
        active = [s for s in self.strategies if len(self._strategy_daily_pnl.get(s, [])) >= 20]
        if len(active) < 2:
            return

        # 페어별 correlation 계산
        high_corr_strategies = set()
        for i, s1 in enumerate(active):
            for s2 in active[i + 1:]:
                pnl1 = self._strategy_daily_pnl[s1][-20:]
                pnl2 = self._strategy_daily_pnl[s2][-20:]
                if np.std(pnl1) < 1e-10 or np.std(pnl2) < 1e-10:
                    corr = 0.0
                else:
                    corr = float(np.corrcoef(pnl1, pnl2)[0, 1])
                self._corr_matrix[(s1, s2)] = corr
                if corr > 0.4:
                    high_corr_strategies.add(s1)
                    high_corr_strategies.add(s2)

        # 비중 조정: 고상관 전략 0.8x, 저상관 전략 1.2x
        self._corr_adjustment = {}
        for s in self.strategies:
            if s in high_corr_strategies:
                self._corr_adjustment[s] = 0.8
            elif len(active) > 0 and s in active:
                self._corr_adjustment[s] = 1.2
            else:
                self._corr_adjustment[s] = 1.0

        # 비중 재적용
        self._apply_regime_weights(self.regime)

    def get_corr_matrix(self) -> Dict[tuple, float]:
        """현재 전략간 상관관계 매트릭스."""
        return self._corr_matrix.copy()

    # ── Dynamic Kelly (Phase 3.4) ──

    def record_trade_result(self, strategy: str, pnl_pct: float):
        """전략별 거래 결과 기록 (Kelly 동적 조정용)."""
        if strategy not in self._strategy_wins:
            return
        if pnl_pct > 0:
            self._strategy_wins[strategy] += 1
            self._strategy_win_pnl[strategy] += pnl_pct
        else:
            self._strategy_losses[strategy] += 1
            self._strategy_loss_pnl[strategy] += abs(pnl_pct)

    def update_kelly(self, vix_ema: float):
        """Dynamic Kelly 스칼라 갱신.

        Quarter-Kelly(0.25) 기반, regime + VIX + 최근 승률 반영.
        kelly_scalar = base(0.25) × regime_mult × vix_mult × performance_mult
        """
        self._vix_ema = vix_ema
        base_kelly = 0.25  # Quarter-Kelly

        # Regime 승수
        regime_mult = {"BULL": 1.2, "NEUTRAL": 1.0, "RANGE_BOUND": 0.8, "BEAR": 0.5}.get(self.regime, 1.0)

        # VIX 승수 (VIX 높을수록 보수적)
        if vix_ema <= 16:
            vix_mult = 1.1
        elif vix_ema <= 20:
            vix_mult = 1.0
        elif vix_ema <= 25:
            vix_mult = 0.8
        elif vix_ema <= 30:
            vix_mult = 0.6
        else:
            vix_mult = 0.4

        # 최근 성과 승수 (전체 전략 합산 승률)
        total_w = sum(self._strategy_wins.values())
        total_l = sum(self._strategy_losses.values())
        total_trades = total_w + total_l
        if total_trades >= 10:
            win_rate = total_w / total_trades
            if win_rate >= 0.45:
                perf_mult = 1.1
            elif win_rate >= 0.35:
                perf_mult = 1.0
            elif win_rate >= 0.25:
                perf_mult = 0.8
            else:
                perf_mult = 0.6
        else:
            perf_mult = 1.0  # 데이터 부족 시 기본값

        self._kelly_scalar = base_kelly * regime_mult * vix_mult * perf_mult
        # 범위 제한: 0.05 ~ 0.40
        self._kelly_scalar = min(0.40, max(0.05, self._kelly_scalar))

    def get_kelly_scalar(self) -> float:
        """현재 Dynamic Kelly 스칼라 (0.05 ~ 0.40)."""
        return self._kelly_scalar


def _compute_adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14):
    """순수 pandas로 ADX, +DI, -DI 계산 (ta 라이브러리 의존 없음)."""
    plus_dm = high.diff().clip(lower=0)
    minus_dm = (-low.diff()).clip(lower=0)

    # +DM과 -DM 중 큰 쪽만 유효
    mask_plus = plus_dm <= minus_dm
    mask_minus = minus_dm <= plus_dm
    plus_dm = plus_dm.copy()
    minus_dm = minus_dm.copy()
    plus_dm[mask_plus] = 0
    minus_dm[mask_minus] = 0

    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = tr.rolling(window=period).mean()
    plus_di = 100 * (plus_dm.rolling(window=period).mean() / atr.replace(0, np.nan))
    minus_di = 100 * (minus_dm.rolling(window=period).mean() / atr.replace(0, np.nan))

    dx = (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan) * 100
    adx = dx.rolling(window=period).mean()

    return adx, plus_di, minus_di
