"""
Market Overview Module
Fetches major market indices and calculates market regime signals.
"""
from __future__ import annotations

import yfinance as yf
import time
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Major market indices to track (grouped)
MARKET_INDICES = [
    # === Global ===
    {"symbol": "^GSPC", "name": "S&P 500", "name_kr": "S&P 500", "group": "global"},
    {"symbol": "^IXIC", "name": "NASDAQ", "name_kr": "나스닥", "group": "global"},
    {"symbol": "^SOX", "name": "SOX", "name_kr": "반도체지수", "group": "global"},
    {"symbol": "^VIX", "name": "VIX", "name_kr": "변동성지수", "group": "global"},
    {"symbol": "DX=F", "name": "DXY", "name_kr": "달러인덱스", "group": "global"},
    # === Korean ===
    {"symbol": "^KS11", "name": "KOSPI", "name_kr": "코스피", "group": "korea"},
    {"symbol": "^KS200", "name": "KOSPI 200", "name_kr": "코스피200", "group": "korea"},
    {"symbol": "^KQ11", "name": "KOSDAQ", "name_kr": "코스닥", "group": "korea"},
    {"symbol": "091160.KS", "name": "KRX 반도체", "name_kr": "반도체(ETF)", "group": "korea"},
    {"symbol": "KRW=X", "name": "USD/KRW", "name_kr": "원/달러", "group": "korea"},
]

# Cache storage
_cache: dict = {"data": None, "timestamp": 0}
CACHE_TTL = 60  # 1 minute (SSE가 primary, REST는 fallback)


def _fetch_all_indices() -> dict[str, dict | None]:
    """Fetch latest price data for all indices in a single batch request."""
    symbols = [idx["symbol"] for idx in MARKET_INDICES]
    results: dict[str, dict | None] = {s: None for s in symbols}

    try:
        data = yf.download(symbols, period="5d", interval="1d", progress=False)
        if data.empty or len(data) < 2:
            logger.warning("Batch download returned empty or insufficient data")
            return results

        for symbol in symbols:
            try:
                close_key = ("Close", symbol)
                if close_key not in data.columns:
                    continue
                closes = data[close_key].dropna()
                if len(closes) < 2:
                    continue

                current = float(closes.iloc[-1])
                previous = float(closes.iloc[-2])
                change = current - previous
                change_pct = (change / previous) * 100 if previous != 0 else 0

                results[symbol] = {
                    "price": round(current, 2),
                    "change": round(change, 2),
                    "change_pct": round(change_pct, 2),
                }
            except Exception as e:
                logger.warning("Failed to parse %s: %s", symbol, e)

    except Exception as e:
        logger.error("Batch download failed: %s", e)

    return results


def _calculate_regime(indices: list[dict]) -> dict:
    """
    Calculate market regime based on VIX, DXY, and S&P 500.

    Rules:
    - VIX < 16 → bullish signal
    - VIX 16-25 → neutral
    - VIX > 25 → bearish signal
    - S&P 500 positive → bullish
    - DXY strongly rising → headwind for risk assets

    Score: -3 to +3 → mapped to regime
    """
    score = 0
    signals = []

    # Find indices by name
    vix = next((i for i in indices if i["symbol"] == "^VIX"), None)
    sp500 = next((i for i in indices if i["symbol"] == "^GSPC"), None)
    dxy = next((i for i in indices if i["symbol"] == "DX=F"), None)

    # VIX analysis
    if vix and vix.get("price"):
        vix_price = vix["price"]
        if vix_price < 16:
            score += 2
            signals.append("VIX 저변동 구간 (< 16)")
        elif vix_price < 20:
            score += 1
            signals.append("VIX 보통 (16-20)")
        elif vix_price < 25:
            signals.append("VIX 경계 (20-25)")
        elif vix_price < 30:
            score -= 1
            signals.append("VIX 고변동 (25-30)")
        else:
            score -= 2
            signals.append("VIX 공포구간 (> 30)")

    # S&P 500 trend
    if sp500 and sp500.get("change_pct") is not None:
        if sp500["change_pct"] > 0.5:
            score += 1
            signals.append("S&P 500 상승세")
        elif sp500["change_pct"] < -0.5:
            score -= 1
            signals.append("S&P 500 하락세")

    # DXY (strong dollar = headwind)
    if dxy and dxy.get("change_pct") is not None:
        if dxy["change_pct"] > 0.3:
            score -= 1
            signals.append("달러 강세 (위험자산 부담)")
        elif dxy["change_pct"] < -0.3:
            score += 1
            signals.append("달러 약세 (위험자산 우호적)")

    # Map score to regime
    if score >= 2:
        regime = "RISK_ON"
        label = "Risk-On"
        label_kr = "위험선호"
    elif score <= -2:
        regime = "RISK_OFF"
        label = "Risk-Off"
        label_kr = "위험회피"
    else:
        regime = "NEUTRAL"
        label = "Neutral"
        label_kr = "중립"

    return {
        "regime": regime,
        "label": label,
        "label_kr": label_kr,
        "score": score,
        "signals": signals,
    }


def get_market_overview() -> dict:
    """
    Get market overview with caching (5 min TTL).
    Returns index data + market regime.
    """
    now = time.time()

    # Return cached if fresh
    if _cache["data"] and (now - _cache["timestamp"]) < CACHE_TTL:
        return {**_cache["data"], "cache_ts": _cache["timestamp"], "cache_ttl": CACHE_TTL}

    # Fetch all indices in a single batch request
    indices = []
    fetch_results = _fetch_all_indices()

    for idx in MARKET_INDICES:
        data = fetch_results.get(idx["symbol"])
        entry = {
            "symbol": idx["symbol"],
            "name": idx["name"],
            "name_kr": idx["name_kr"],
            "group": idx.get("group", "global"),
            "price": data["price"] if data else None,
            "change": data["change"] if data else None,
            "change_pct": data["change_pct"] if data else None,
        }
        indices.append(entry)

    # Calculate regime
    regime = _calculate_regime(indices)

    result = {
        "indices": indices,
        "regime": regime,
        "updated_at": datetime.now().isoformat(),
        "cache_ts": now,
        "cache_ttl": CACHE_TTL,
    }

    # Update cache
    _cache["data"] = result
    _cache["timestamp"] = now

    return result
