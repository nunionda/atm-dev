"""
시세 데이터 조회 및 기술적 지표 계산 지원
문서: ATS-SAD-001 Data Access Layer
"""

from __future__ import annotations

import time as _time
from typing import Dict, List

import pandas as pd

from common.types import PriceData
from data.config_manager import ATSConfig
from infra.broker.base import BaseBroker
from infra.logger import get_logger

logger = get_logger("market_data")


class MarketDataProvider:
    """시세 데이터를 브로커 API를 통해 조회하고 캐싱한다."""

    CACHE_TTL_SECONDS = 3600  # 1시간 캐시 유효

    def __init__(self, broker: BaseBroker, config: ATSConfig):
        self.broker = broker
        self.config = config
        self._ohlcv_cache: Dict[str, pd.DataFrame] = {}
        self._cache_timestamps: Dict[str, float] = {}

    def get_price(self, stock_code: str) -> PriceData:
        """단일 종목 현재가를 조회한다."""
        return self.broker.get_price(stock_code)

    def get_current_prices(self, stock_codes: List[str]) -> Dict[str, PriceData]:
        """복수 종목의 현재가를 조회한다."""
        prices = {}
        for code in stock_codes:
            try:
                prices[code] = self.broker.get_price(code)
            except Exception as e:
                logger.warning("Price fetch failed | stock=%s | error=%s", code, e)
        return prices

    def get_ohlcv(self, stock_code: str, period: int = 60) -> pd.DataFrame:
        """일봉 OHLCV를 조회한다 (캐시 활용, TTL 1시간)."""
        now = _time.time()
        cached_at = self._cache_timestamps.get(stock_code, 0)

        if stock_code in self._ohlcv_cache and (now - cached_at) < self.CACHE_TTL_SECONDS:
            return self._ohlcv_cache[stock_code]

        df = self.broker.get_ohlcv(stock_code, period)
        if not df.empty:
            self._ohlcv_cache[stock_code] = df
            self._cache_timestamps[stock_code] = now
        return df

    def update_ohlcv(self, stock_codes: List[str], period: int = 60):
        """유니버스 전체 OHLCV를 업데이트한다 (UC-01 Step 6)."""
        success = 0
        fail = 0
        for code in stock_codes:
            try:
                df = self.broker.get_ohlcv(code, period)
                if not df.empty:
                    self._ohlcv_cache[code] = df
                    success += 1
                else:
                    fail += 1
            except Exception as e:
                fail += 1
                logger.warning("OHLCV update failed | stock=%s | error=%s", code, e)

        logger.info("OHLCV update complete | success=%d | fail=%d", success, fail)

    def clear_cache(self):
        """캐시를 초기화한다."""
        self._ohlcv_cache.clear()
        self._cache_timestamps.clear()

    def append_realtime_to_ohlcv(
        self, stock_code: str, price_data: PriceData
    ) -> pd.DataFrame:
        """
        캐시된 OHLCV에 현재 실시간 데이터를 마지막 행으로 추가/갱신한다.
        기술적 지표 계산 시 최신 데이터를 반영하기 위함.
        """
        df = self._ohlcv_cache.get(stock_code, pd.DataFrame())
        if df.empty:
            return df

        today = price_data.timestamp[:10].replace("-", "")
        new_row = {
            "date": today,
            "open": price_data.open_price,
            "high": price_data.high_price,
            "low": price_data.low_price,
            "close": price_data.current_price,
            "volume": price_data.volume,
        }

        # 오늘 날짜 행이 이미 있으면 갱신, 없으면 추가
        if not df.empty and df.iloc[-1]["date"] == today:
            df.iloc[-1] = new_row
        else:
            new_df = pd.DataFrame([new_row])
            df = pd.concat([df, new_df], ignore_index=True)

        self._ohlcv_cache[stock_code] = df
        return df
