"""
리밸런싱 매니저.

14거래일 주기로 UniverseScanner를 실행하여
동적 워치리스트를 갱신하고 탈락 종목을 ES7 청산 대상으로 지정한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


@dataclass
class RebalanceEvent:
    """단일 리밸런스 이벤트 기록."""

    date: str
    cycle_number: int
    stocks_added: List[str] = field(default_factory=list)
    stocks_removed: List[str] = field(default_factory=list)
    positions_force_exited: List[str] = field(default_factory=list)
    new_watchlist: List[Dict[str, str]] = field(default_factory=list)
    momentum_scores: Dict[str, float] = field(default_factory=dict)
    total_scanned: int = 0
    passed_prefilter: int = 0


class RebalanceManager:
    """
    리밸런싱 주기를 관리하고 UniverseScanner를 구동한다.

    - 14거래일(기본) 주기로 리밸런싱 실행
    - 첫 거래일에는 즉시 초기 스캔 수행 (워치리스트 시딩)
    - 탈락 종목 중 보유 포지션은 ES7 청산 대상으로 표시
    """

    def __init__(
        self,
        scanner: Any,  # UniverseScanner
        rebalance_interval: int = 14,
    ):
        self.scanner = scanner
        self.rebalance_interval = rebalance_interval

        # 상태
        self._trading_day_count: int = 0
        self._cycle_count: int = 0
        self._current_watchlist: List[Dict[str, str]] = []
        self._current_watchlist_codes: Set[str] = set()
        self._history: List[RebalanceEvent] = []
        self._is_initialized: bool = False

    def should_rebalance(self) -> bool:
        """현재 거래일에 리밸런싱이 필요한지 판단."""
        # 첫 거래일: 초기 워치리스트 시딩
        if not self._is_initialized:
            return True
        # 주기 도달
        return self._trading_day_count >= self.rebalance_interval

    def execute_rebalance(
        self,
        ohlcv_map: Dict[str, Any],
        current_date: str,
        active_positions: Dict[str, Any],
    ) -> RebalanceEvent:
        """
        리밸런싱 실행.

        1. UniverseScanner.scan() 호출 → 새 워치리스트
        2. 기존 워치리스트 대비 추가/제거 종목 파악
        3. 보유 중인 탈락 종목 → ES7 청산 대상 반환

        Returns:
            RebalanceEvent with stocks_added, stocks_removed, positions_force_exited
        """
        self._cycle_count += 1
        self._trading_day_count = 0

        # 스캔 실행
        new_watchlist = self.scanner.scan(ohlcv_map, current_date)
        new_codes = {w["code"] for w in new_watchlist}
        old_codes = self._current_watchlist_codes

        # 추가/제거 종목
        added = list(new_codes - old_codes)
        removed = list(old_codes - new_codes)

        # 보유 중인 탈락 종목 → ES7 청산 대상
        active_codes = set(active_positions.keys()) if active_positions else set()
        force_exit = list(active_codes & set(removed))

        # 모멘텀 점수 수집 (리포트용)
        scores: Dict[str, float] = {}
        for stock in new_watchlist:
            code = stock["code"]
            df = ohlcv_map.get(code)
            if df is not None and not df.empty:
                df_slice = df[df["date"] <= current_date]
                score = self.scanner._compute_momentum_score(df_slice)
                if score is not None:
                    scores[code] = round(score, 1)

        # 워치리스트 갱신
        self._current_watchlist = new_watchlist
        self._current_watchlist_codes = new_codes
        self._is_initialized = True

        event = RebalanceEvent(
            date=current_date,
            cycle_number=self._cycle_count,
            stocks_added=added,
            stocks_removed=removed,
            positions_force_exited=force_exit,
            new_watchlist=new_watchlist,
            momentum_scores=scores,
            total_scanned=len(self.scanner.constituents),
            passed_prefilter=len(new_watchlist),
        )
        self._history.append(event)

        return event

    def tick(self):
        """매 거래일 호출. 리밸런스 카운터 증가."""
        self._trading_day_count += 1

    def reset_counter(self):
        """거부 시 카운터 리셋 — 다음 주기까지 대기."""
        self._trading_day_count = 0

    def apply_scan_result(
        self,
        scan_result: list,
        active_positions: dict,
    ) -> "RebalanceEvent":
        """PAPER/LIVE: 스캔 결과를 받아 상태 변경 (메인 스레드에서 호출).

        execute_rebalance()의 상태 변경 부분만 분리한 버전.
        CPU-intensive scan()은 별도 스레드에서 실행하고,
        이 메서드는 이벤트 루프 스레드에서 호출하여 race condition을 방지한다.
        """
        new_codes = {w["code"] for w in scan_result}
        old_codes = self._current_watchlist_codes

        added = sorted(new_codes - old_codes)
        removed = sorted(old_codes - new_codes)
        force_exit = sorted(set(active_positions.keys()) & set(removed))

        # 상태 업데이트
        self._current_watchlist = scan_result
        self._current_watchlist_codes = new_codes
        self._cycle_count += 1
        self._trading_day_count = 0
        self._is_initialized = True  # 없으면 무한 리밸런스 루프

        event = RebalanceEvent(
            date="",
            cycle_number=self._cycle_count,
            stocks_added=added,
            stocks_removed=removed,
            positions_force_exited=force_exit,
            new_watchlist=scan_result,
            total_scanned=len(scan_result),
            passed_prefilter=len(scan_result),
        )
        self._history.append(event)
        return event

    def get_current_watchlist(self) -> List[Dict[str, str]]:
        """현재 활성 워치리스트 반환."""
        return self._current_watchlist

    def get_history(self) -> List[RebalanceEvent]:
        """리밸런스 이력 반환."""
        return self._history

    @property
    def cycle_count(self) -> int:
        return self._cycle_count

    @property
    def avg_turnover_pct(self) -> float:
        """평균 턴오버율 (리밸런스당 교체 비율)."""
        if not self._history or self.scanner.top_n == 0:
            return 0.0
        total_removed = sum(len(e.stocks_removed) for e in self._history)
        # 첫 리밸런스는 전체 추가이므로 제외
        events = self._history[1:] if len(self._history) > 1 else self._history
        if not events:
            return 0.0
        avg_removed = total_removed / len(events)
        return avg_removed / self.scanner.top_n * 100
