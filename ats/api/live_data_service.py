"""
LiveDataService — 실시간 데이터 SSE 푸시 서비스.

장시간 인식 백그라운드 루프로 가격/마켓 오버뷰/레짐 변화를 SSE로 push.
- price_update: 구독된 티커 가격 (30s 장중, 300s 장외)
- market_overview: 글로벌/한국 인덱스 (60s 장중, 300s 장외)
- regime_change: 레짐 변경 시에만 발행
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any

import yfinance as yf

from simulation.event_bus import SSEEventBus
from .market_overview import get_market_overview

logger = logging.getLogger(__name__)

# Intervals (seconds)
PRICE_INTERVAL_OPEN = 30
PRICE_INTERVAL_CLOSED = 300
OVERVIEW_INTERVAL_OPEN = 60
OVERVIEW_INTERVAL_CLOSED = 300


class LiveDataService:

    def __init__(self, event_bus: SSEEventBus):
        self._event_bus = event_bus
        self._is_running = False
        self._tasks: list[asyncio.Task] = []

        # Dedup state
        self._last_prices: dict[str, float] = {}
        self._last_regime: str | None = None

        # Dynamic ticker subscriptions
        self._subscribed_tickers: set[str] = set()

    # --- Public API ---

    async def start(self):
        self._is_running = True
        self._tasks = [
            asyncio.create_task(self._price_loop()),
            asyncio.create_task(self._market_overview_loop()),
        ]
        logger.info("LiveDataService started")

    async def stop(self):
        self._is_running = False
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()
        logger.info("LiveDataService stopped")

    def subscribe_ticker(self, ticker: str):
        self._subscribed_tickers.add(ticker.upper())

    def unsubscribe_ticker(self, ticker: str):
        self._subscribed_tickers.discard(ticker.upper())

    @property
    def subscribed_tickers(self) -> set[str]:
        return self._subscribed_tickers.copy()

    # --- Market Session Detection ---

    @staticmethod
    def _is_us_market_open() -> bool:
        """US market: 09:30-16:00 ET (simplified EDT UTC-4)."""
        now = datetime.now(timezone.utc)
        et = now - timedelta(hours=4)  # EDT
        if et.weekday() >= 5:
            return False
        total_min = et.hour * 60 + et.minute
        return 570 <= total_min < 960  # 09:30 ~ 16:00

    @staticmethod
    def _is_kr_market_open() -> bool:
        """KR market: 09:00-15:30 KST (UTC+9)."""
        now = datetime.now(timezone.utc)
        kst = now + timedelta(hours=9)
        if kst.weekday() >= 5:
            return False
        total_min = kst.hour * 60 + kst.minute
        return 540 <= total_min < 930  # 09:00 ~ 15:30

    def _is_any_market_open(self) -> bool:
        return self._is_us_market_open() or self._is_kr_market_open()

    # --- Price Loop ---

    async def _price_loop(self):
        """Fetch subscribed ticker prices and publish via SSE."""
        while self._is_running:
            try:
                interval = PRICE_INTERVAL_OPEN if self._is_any_market_open() else PRICE_INTERVAL_CLOSED

                tickers = list(self._subscribed_tickers)
                if tickers:
                    await self._fetch_and_publish_prices(tickers)

                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Price loop error: %s", e)
                await asyncio.sleep(10)

    async def _fetch_and_publish_prices(self, tickers: list[str]):
        """Batch fetch prices via yfinance and publish changes."""
        try:
            data = await asyncio.to_thread(
                yf.download,
                tickers if len(tickers) > 1 else tickers[0],
                period="1d",
                interval="1m",
                progress=False,
                auto_adjust=False,
            )

            if data is None or data.empty:
                return

            now_iso = datetime.now(timezone.utc).isoformat()

            for ticker in tickers:
                try:
                    if len(tickers) == 1:
                        closes = data["Close"].dropna()
                    else:
                        close_key = ("Close", ticker)
                        if close_key not in data.columns:
                            continue
                        closes = data[close_key].dropna()

                    if len(closes) < 2:
                        continue

                    current = float(closes.iloc[-1])
                    previous = float(closes.iloc[-2])

                    # Dedup: skip if price unchanged
                    if self._last_prices.get(ticker) == current:
                        continue
                    self._last_prices[ticker] = current

                    change = current - previous
                    change_pct = (change / previous * 100) if previous != 0 else 0

                    # Volume (last bar)
                    volume = 0
                    try:
                        if len(tickers) == 1:
                            vol_series = data["Volume"].dropna()
                        else:
                            vol_series = data[("Volume", ticker)].dropna()
                        if len(vol_series) > 0:
                            volume = int(vol_series.iloc[-1])
                    except Exception:
                        pass

                    await self._event_bus.publish("price_update", {
                        "ticker": ticker,
                        "price": round(current, 4),
                        "change": round(change, 4),
                        "change_pct": round(change_pct, 2),
                        "volume": volume,
                        "timestamp": now_iso,
                    })

                except Exception as e:
                    logger.warning("Price parse error for %s: %s", ticker, e)

        except Exception as e:
            logger.error("Batch price fetch failed: %s", e)

    # --- Market Overview Loop ---

    async def _market_overview_loop(self):
        """Fetch market overview and publish via SSE."""
        while self._is_running:
            try:
                interval = OVERVIEW_INTERVAL_OPEN if self._is_any_market_open() else OVERVIEW_INTERVAL_CLOSED

                overview = await asyncio.to_thread(get_market_overview)

                if overview:
                    await self._event_bus.publish("market_overview", overview)

                    # Check regime change
                    regime_data = overview.get("regime", {})
                    new_regime = regime_data.get("regime")
                    if new_regime and new_regime != self._last_regime:
                        if self._last_regime is not None:
                            await self._event_bus.publish("regime_change", {
                                "old_regime": self._last_regime,
                                "new_regime": new_regime,
                                "score": regime_data.get("score", 0),
                                "signals": regime_data.get("signals", []),
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                            })
                        self._last_regime = new_regime

                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Market overview loop error: %s", e)
                await asyncio.sleep(10)
