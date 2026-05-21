"""
ExitGuard — ES2(익절) Winner 보호 read-only 판정 (Phase B).

매매 전략의 `scan_exit_signals()` 안에서 ES2 분기 직전에 호출되어
해당 포지션이 Rebalance "HOLD/BUY" 추천 + 6개월 수익률 임계치 이상이면
익절 시그널 발행을 보류한다.

ES1(-10% 손절), ES3(트레일링), ES4(데드크로스), ES5(MAX_HOLDING)는
**보호 우회** — 손절 안정성 보장 (CLAUDE.md BR-S01 절대 불변).

설계:
  - read-only — Repository.get_universe_meta()를 호출하기만 함
  - 60초 TTL 캐시로 매 cycle DB 부하 회피
  - 백테스트는 ExitGuard 미주입 → 전략의 `self.exit_guard` 가 None → no-op
"""
from __future__ import annotations

import time
from typing import Optional, Tuple

from infra.db.repository import Repository
from infra.logger import get_logger

logger = get_logger("exit_guard")


class ExitGuard:
    """ES2 보호 판정기."""

    PROTECTED_ACTIONS = {"BUY", "HOLD"}

    def __init__(
        self,
        repo: Repository,
        protect_min_return_6m: float = 0.0,
        protect_min_score: float = 0.0,
        cache_ttl_sec: int = 60,
    ):
        self.repo = repo
        self.protect_min_return_6m = float(protect_min_return_6m)
        self.protect_min_score = float(protect_min_score)
        self._cache_ttl = cache_ttl_sec
        self._cache: dict[str, tuple[float, set[str]]] = {}  # market -> (expires_at, codes)

    # ──────────────────────────────────────
    # 보호 종목 코드 set (60s 캐시)
    # ──────────────────────────────────────

    def get_protected_codes(self, market: Optional[str] = None) -> set[str]:
        """현 시점에서 보호 대상인 종목 코드 set을 반환 (60s TTL 캐시)."""
        cache_key = market or "_all_"
        now = time.time()
        cached = self._cache.get(cache_key)
        if cached and cached[0] > now:
            return cached[1]

        codes: set[str] = set()
        try:
            universe = self.repo.get_active_universe(market=market)
        except TypeError:
            # 구 시그니처 fallback
            universe = self.repo.get_active_universe()

        for u in universe:
            if u.rebalance_action not in self.PROTECTED_ACTIONS:
                continue
            if (u.return_6m or 0.0) < self.protect_min_return_6m:
                continue
            if (u.rebalance_score or 0.0) < self.protect_min_score:
                continue
            codes.add(u.stock_code)

        self._cache[cache_key] = (now + self._cache_ttl, codes)
        return codes

    # ──────────────────────────────────────
    # 개별 포지션 판정
    # ──────────────────────────────────────

    def is_es2_protected(self, pos, market: Optional[str] = None) -> Tuple[bool, str]:
        """
        해당 포지션이 ES2(익절) 보호 대상인지 판정.

        Returns: (protected, reason)
                 protected=True면 ES2 시그널 발행 보류
                 reason은 trade_log/notifier 디버그 메시지용
        """
        stock_code = getattr(pos, "stock_code", None)
        if not stock_code:
            return False, "no_stock_code"

        protected_codes = self.get_protected_codes(market=market)
        if stock_code not in protected_codes:
            return False, "not_in_protected"

        return True, f"rebalance_hold_market={market}"

    def invalidate_cache(self, market: Optional[str] = None):
        """sync 직후 호출하여 캐시 즉시 무효화."""
        if market is None:
            self._cache.clear()
        else:
            self._cache.pop(market, None)
            self._cache.pop("_all_", None)
