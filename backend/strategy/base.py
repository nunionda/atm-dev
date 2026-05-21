"""
전략 추상 클래스 (플러그인 인터페이스)
문서: ATS-SAD-001 §5.2
확장성: NFR-E01 전략 추가 용이
"""

from abc import ABC, abstractmethod
from typing import List, Optional

import pandas as pd

from common.types import ExitSignal, Signal


class BaseStrategy(ABC):
    """
    전략 추상 클래스.
    새로운 매매 전략을 추가할 때 이 인터페이스를 구현한다.

    Optional `exit_guard` / `market_id`:
        Phase B Rebalance Winner 보호 기능. MainLoop이 라이브 환경에서만
        `set_exit_guard(eg, market_id)` 로 주입한다. 백테스트는 주입 안 함 → no-op.
        각 전략의 `scan_exit_signals()` 내부 ES2(익절) 분기 직전에
        `if self.exit_guard and self.exit_guard.is_es2_protected(pos, self.market_id)[0]: continue`
        한 줄을 끼워 사용한다.
    """

    # 인스턴스 attribute 기본값 (subclass __init__에서 override 가능)
    exit_guard = None
    market_id: Optional[str] = None

    def set_exit_guard(self, exit_guard, market_id: Optional[str] = None) -> None:
        """ExitGuard 주입 (라이브에서만 호출)."""
        self.exit_guard = exit_guard
        self.market_id = market_id

    @abstractmethod
    def scan_entry_signals(
        self,
        universe_codes: List[str],
        ohlcv_data: dict[str, pd.DataFrame],
        current_prices: dict,
    ) -> List[Signal]:
        """
        매수 시그널을 스캔한다 (UC-02).
        Returns: 시그널 강도 내림차순 정렬된 Signal 리스트
        """
        ...

    @abstractmethod
    def scan_exit_signals(
        self,
        positions: list,
        ohlcv_data: dict[str, pd.DataFrame],
        current_prices: dict,
    ) -> List[ExitSignal]:
        """
        청산 시그널을 스캔한다 (UC-04).
        Returns: ExitSignal 리스트 (우선순위대로 하나만 반환)
        """
        ...

    @abstractmethod
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """기술적 지표를 계산하여 DataFrame에 컬럼을 추가한다."""
        ...
