"""
히스토리컬 데이터 프로바이더.

CSV로 로드된 전체 OHLCV 데이터를 날짜별로 슬라이싱하여
SimulationEngine에 제공한다. Lookahead bias 방지가 핵심.
"""

from __future__ import annotations

from typing import Dict, List

import pandas as pd

from infra.logger import get_logger

logger = get_logger("backtest.provider")


class HistoricalDataProvider:
    """
    히스토리컬 OHLCV 데이터를 날짜 커서 기반으로 슬라이싱.

    핵심 보장: get_ohlcv_up_to_date()는 current_date 이전 데이터만 반환.
    미래 데이터는 절대 노출하지 않는다.
    """

    def __init__(self, ohlcv_map: Dict[str, pd.DataFrame]):
        """
        Args:
            ohlcv_map: {stock_code: DataFrame} — 전체 기간 OHLCV
                       DataFrame must have 'date' column (YYYYMMDD string)
        """
        self._full_data = ohlcv_map
        self._current_date: str = ""
        self._trading_dates: List[str] = []

    def set_current_date(self, date: str):
        """날짜 커서를 이동한다."""
        self._current_date = date

    @property
    def current_date(self) -> str:
        return self._current_date

    def get_ohlcv_up_to_date(
        self,
        watchlist: List[Dict[str, str]],
    ) -> Dict[str, pd.DataFrame]:
        """
        current_date 이전 데이터만 반환한다 (Lookahead 방지).

        Returns:
            {stock_code: DataFrame} — 각 종목의 current_date 이전 OHLCV
        """
        result: Dict[str, pd.DataFrame] = {}
        for w in watchlist:
            code = w["code"]
            df = self._full_data.get(code)
            if df is None or df.empty:
                continue

            # 미래 데이터 차단: current_date 이하만
            filtered = df[df["date"] <= self._current_date].copy()
            if not filtered.empty:
                result[code] = filtered

        return result

    def get_current_prices(
        self,
        watchlist: List[Dict[str, str]],
    ) -> Dict[str, float]:
        """
        current_date의 종가를 반환한다.

        Returns:
            {stock_code: close_price}
        """
        prices: Dict[str, float] = {}
        for w in watchlist:
            code = w["code"]
            df = self._full_data.get(code)
            if df is None or df.empty:
                continue

            # current_date 정확히 매칭
            row = df[df["date"] == self._current_date]
            if not row.empty:
                prices[code] = float(row.iloc[0]["close"])

        return prices

    @property
    def trading_dates(self) -> List[str]:
        """전체 데이터에서 추출한 거래일 목록 (정렬)."""
        if not self._trading_dates:
            all_dates: set = set()
            for df in self._full_data.values():
                if not df.empty and "date" in df.columns:
                    all_dates.update(df["date"].tolist())
            self._trading_dates = sorted(all_dates)
        return self._trading_dates

    def get_dates_in_range(self, start_date: str, end_date: str) -> List[str]:
        """특정 기간의 거래일만 반환."""
        return [d for d in self.trading_dates if start_date <= d <= end_date]

    def get_warmup_dates(self, start_date: str) -> List[str]:
        """start_date 이전의 모든 거래일 (워밍업 기간)."""
        return [d for d in self.trading_dates if d < start_date]

    def stock_count(self) -> int:
        """로드된 종목 수."""
        return len(self._full_data)

    def date_range(self) -> tuple:
        """전체 데이터의 최소/최대 날짜."""
        dates = self.trading_dates
        if not dates:
            return ("", "")
        return (dates[0], dates[-1])
