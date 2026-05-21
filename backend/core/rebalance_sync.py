"""
Rebalance → Universe 동기화 작업 (Phase A).

장 마감 후 매일 1회 (또는 수동 트리거) 실행되어:
  1. UniverseScanner로 모멘텀 BUY/HOLD/SELL 추천 생성
  2. 합집합 정책으로 target_codes 산정 (BUY top_n ∪ HOLD ∪ 현재 보유 ∪ always_active)
  3. min_universe_size_guard로 비정상 sync 거부
  4. Repository.replace_active_universe()로 원자적 미러링
  5. RebalanceSyncLog 기록

설계 노트:
  - 본 모듈은 read-side `UniverseScanner`만 호출하고 매매 엔진과는 단방향(DB) 결합.
    MainLoop은 다음 cycle에서 `repo.get_active_universe(market)`로 새 universe를 자연 흡수.
  - 백테스트는 본 Job을 호출하지 않음 — 기존 universe 그대로 사용.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from infra.db.repository import Repository
from infra.logger import get_logger

logger = get_logger("rebalance_sync")


# 마켓 → 유니버스 ID 매핑 (rebalance_routes._get_universe_config과 동일)
MARKET_UNIVERSE_MAPPING = {
    "sp500": "sp500_full",
    "ndx": "ndx_full",
    "kospi": "kospi_full",
}


class RebalanceSyncResult:
    """sync 결과 요약 (테스트·로그용)."""

    def __init__(
        self,
        market: str,
        scan_date: str,
        trigger: str,
        buy_count: int = 0,
        hold_count: int = 0,
        kept_count: int = 0,
        total_active: int = 0,
        protected_count: int = 0,
        target_codes: Optional[List[str]] = None,
        duration_ms: int = 0,
        committed: bool = False,
        rejected: bool = False,
        reject_reason: Optional[str] = None,
        error: Optional[str] = None,
    ):
        self.market = market
        self.scan_date = scan_date
        self.trigger = trigger
        self.buy_count = buy_count
        self.hold_count = hold_count
        self.kept_count = kept_count
        self.total_active = total_active
        self.protected_count = protected_count
        self.target_codes = target_codes or []
        self.duration_ms = duration_ms
        self.committed = committed
        self.rejected = rejected
        self.reject_reason = reject_reason
        self.error = error

    def to_dict(self) -> Dict[str, Any]:
        return {
            "market": self.market,
            "scan_date": self.scan_date,
            "trigger": self.trigger,
            "synced": self.total_active,
            "buy": self.buy_count,
            "hold": self.hold_count,
            "kept": self.kept_count,
            "protected": self.protected_count,
            "target_codes": self.target_codes,
            "duration_ms": self.duration_ms,
            "committed": self.committed,
            "rejected": self.rejected,
            "reject_reason": self.reject_reason,
            "error": self.error,
        }


class RebalanceSyncJob:
    """Rebalance scan → Universe 미러링 작업."""

    def __init__(
        self,
        repo: Repository,
        top_n: int = 10,
        min_universe_size: int = 3,
        always_active: Optional[List[str]] = None,
    ):
        self.repo = repo
        self.top_n = top_n
        self.min_universe_size = min_universe_size
        self.always_active = list(always_active or [])

    # ── 외부에서 active positions를 주입할 수 있게 분리 (테스트 용이) ──
    def _fetch_active_positions(self, market: str) -> Dict[str, object]:
        """현재 SimulationController의 active 포지션을 dict로 반환.

        실패해도 sync는 계속 진행 (빈 dict). DB Repository에도 fallback.
        """
        positions: Dict[str, object] = {}
        try:
            from api.app import sim_controller  # 지연 import
            engine = sim_controller.get_engine(market)
            if engine and getattr(engine, "_is_running", False):
                positions = {
                    code: pos
                    for code, pos in engine.positions.items()
                    if getattr(pos, "status", None) == "ACTIVE"
                }
        except Exception as e:
            logger.debug("sim_controller positions unavailable, fallback to DB | %s", e)
        if not positions:
            try:
                for pos in self.repo.get_active_positions():
                    positions[pos.stock_code] = pos
            except Exception as e:
                logger.warning("DB get_active_positions failed: %s", e)
        return positions

    def run(
        self,
        market: str,
        trigger: str = "AUTO",
        commit: bool = True,
        scanner_result: Optional[Dict[str, Any]] = None,
        active_positions: Optional[Dict[str, object]] = None,
    ) -> RebalanceSyncResult:
        """
        Sync 1회 실행. commit=False면 DB 변경 없이 dry-run 결과만 반환.

        Args:
            market: 'sp500' | 'ndx' | 'kospi'
            trigger: 'AUTO' | 'MANUAL'
            commit: True면 Universe DB 갱신 + 로그 기록
            scanner_result: 외부에서 미리 만든 scan 결과 (재사용)
            active_positions: 외부 주입 (테스트용)
        """
        start_ts = time.time()
        scan_date = datetime.now().strftime("%Y-%m-%d")

        try:
            # 1) 활성 포지션
            if active_positions is None:
                active_positions = self._fetch_active_positions(market)

            # 2) Scanner 결과 확보
            if scanner_result is None:
                scanner_result = self._run_scanner(market, active_positions)

            buy_list = scanner_result.get("buy", [])
            hold_list = scanner_result.get("hold", [])

            # 3) 합집합 계산: BUY top_n ∪ HOLD ∪ 현재 보유 ∪ always_active
            codes_meta: List[dict] = []
            seen: set = set()

            for item in buy_list[: self.top_n]:
                code = item.get("code")
                if code and code not in seen:
                    seen.add(code)
                    codes_meta.append(self._to_meta(item, action="BUY"))

            for item in hold_list:
                code = item.get("code")
                if code and code not in seen:
                    seen.add(code)
                    codes_meta.append(self._to_meta(item, action="HOLD"))

            # 보유 중인데 top에서 빠진 종목 ("KEEP")
            for code, pos in active_positions.items():
                if code not in seen:
                    seen.add(code)
                    codes_meta.append({
                        "stock_code": code,
                        "stock_name": getattr(pos, "stock_name", code),
                        "sector": getattr(pos, "sector", None),
                        "rebalance_action": "KEEP",
                        "rebalance_score": None,
                        "rebalance_rank": None,
                        "return_6m": None,
                    })

            # always_active 화이트리스트 (페어 ETF 등)
            for code in self.always_active:
                if code not in seen:
                    seen.add(code)
                    codes_meta.append({
                        "stock_code": code,
                        "stock_name": code,
                        "sector": None,
                        "rebalance_action": "KEEP",
                        "rebalance_score": None,
                        "rebalance_rank": None,
                        "return_6m": None,
                    })

            target_codes = [m["stock_code"] for m in codes_meta]
            buy_count = sum(1 for m in codes_meta if m["rebalance_action"] == "BUY")
            hold_count = sum(1 for m in codes_meta if m["rebalance_action"] == "HOLD")
            kept_count = sum(1 for m in codes_meta if m["rebalance_action"] == "KEEP")
            # ES2 보호 대상은 BUY+HOLD 중 return_6m이 양수 (Phase B config threshold로 좁힘)
            protected_count = sum(
                1 for m in codes_meta
                if m["rebalance_action"] in ("BUY", "HOLD")
                and (m.get("return_6m") or 0) > 0
            )

            # 4) min_universe_size guard
            if len(target_codes) < self.min_universe_size:
                result = RebalanceSyncResult(
                    market=market, scan_date=scan_date, trigger=trigger,
                    buy_count=buy_count, hold_count=hold_count, kept_count=kept_count,
                    total_active=len(target_codes), protected_count=protected_count,
                    target_codes=target_codes,
                    duration_ms=int((time.time() - start_ts) * 1000),
                    committed=False, rejected=True,
                    reject_reason=f"universe size {len(target_codes)} < min {self.min_universe_size}",
                )
                if commit:
                    self._log(result)
                logger.warning(
                    "Rebalance sync rejected | market=%s | size=%d < min=%d",
                    market, len(target_codes), self.min_universe_size,
                )
                return result

            # 5) DB 미러링
            if commit:
                self.repo.replace_active_universe(market, codes_meta)

            result = RebalanceSyncResult(
                market=market, scan_date=scan_date, trigger=trigger,
                buy_count=buy_count, hold_count=hold_count, kept_count=kept_count,
                total_active=len(target_codes), protected_count=protected_count,
                target_codes=target_codes,
                duration_ms=int((time.time() - start_ts) * 1000),
                committed=commit, rejected=False,
            )
            if commit:
                self._log(result)

            logger.info(
                "Rebalance sync OK | market=%s | BUY=%d HOLD=%d KEEP=%d | total=%d protected=%d | %dms",
                market, buy_count, hold_count, kept_count,
                len(target_codes), protected_count, result.duration_ms,
            )
            return result

        except Exception as e:
            logger.error("Rebalance sync failed | market=%s | %s", market, e, exc_info=True)
            result = RebalanceSyncResult(
                market=market, scan_date=scan_date, trigger=trigger,
                duration_ms=int((time.time() - start_ts) * 1000),
                committed=False, error=str(e),
            )
            if commit:
                self._log(result)
            return result

    # ──────────────────────────────────────
    # helpers
    # ──────────────────────────────────────

    @staticmethod
    def _to_meta(item: dict, action: str) -> dict:
        """scanner buy/hold item → Universe 메타 dict 변환."""
        return {
            "stock_code": item.get("code"),
            "stock_name": item.get("name") or item.get("code"),
            "sector": item.get("sector"),
            "rebalance_action": action,
            "rebalance_score": item.get("score"),
            "rebalance_rank": item.get("rank"),
            "return_6m": item.get("return_6m_raw"),
        }

    def _log(self, result: RebalanceSyncResult):
        try:
            self.repo.upsert_rebalance_sync_log(
                market=result.market,
                scan_date=result.scan_date,
                trigger=result.trigger,
                top_n=self.top_n,
                buy_count=result.buy_count,
                hold_count=result.hold_count,
                kept_count=result.kept_count,
                total_active=result.total_active,
                protected_count=result.protected_count,
                target_codes_json=json.dumps(result.target_codes, ensure_ascii=False),
                duration_ms=result.duration_ms,
                error=result.error,
            )
        except Exception as e:
            logger.warning("RebalanceSyncLog write failed: %s", e)

    def _run_scanner(self, market: str, active_positions: Dict[str, object]) -> Dict[str, Any]:
        """UniverseScanner를 직접 호출 (yfinance 다운로드 포함)."""
        # 지연 import — 백테스트 cold-path에서 yfinance 로드 회피
        from simulation.universe import UNIVERSE_CONFIG, UniverseScanner
        from backtest.data_downloader import download_and_cache_batched

        if market not in MARKET_UNIVERSE_MAPPING:
            raise ValueError(f"Unknown market '{market}'")
        ucfg = UNIVERSE_CONFIG[MARKET_UNIVERSE_MAPPING[market]]
        constituents = ucfg["constituents"]
        scanner_top_n = max(self.top_n, ucfg.get("top_n", 15))

        market_cache = os.path.join("data_store/historical", market)
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=420)).strftime("%Y%m%d")

        ohlcv_map = download_and_cache_batched(
            watchlist=constituents,
            start_date=start_date,
            end_date=end_date,
            cache_dir=market_cache,
            batch_size=50,
            delay_between_batches=1.0,
        )

        scanner = UniverseScanner(constituents=constituents, top_n=scanner_top_n)
        return scanner.scan_with_recommendations(
            ohlcv_map=ohlcv_map,
            current_date=end_date,
            active_positions=active_positions,
        )
