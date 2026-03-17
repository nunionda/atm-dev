from __future__ import annotations

import asyncio
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
import pandas as pd
import numpy as np
import datetime
from datetime import timedelta
from typing import Optional
import json
import time
import logging
import requests as http_requests
from analytics.indicators import calculate_basic_indicators
import yfinance as yf
from .ticker_list import search_tickers, resolve_ticker
from .market_overview import get_market_overview

logger = logging.getLogger(__name__)

router = APIRouter()

# ── Analyze 캐시 ──────────────────────────────────────────────────────
_analyze_cache: dict[str, dict] = {}
_analyze_cache_ts: dict[str, float] = {}
ANALYZE_CACHE_TTL = 60  # 1분 (SSE가 primary, REST는 fallback)

# ── Quote 캐시 (경량 폴링용) ──────────────────────────────────────────
_quote_cache: dict[str, dict] = {}
QUOTE_CACHE_TTL = 30  # 30초 (SSE price_update와 정렬)

# ── Naver Finance 데이터 소스 (KRX 파생상품) ─────────────────────────

NAVER_TICKER_MAP = {
    "@KS200F": "FUT",       # KOSPI 200 선물 근월물
    "@KS200":  "KPI200",    # KOSPI 200 지수
    "^KS200":  "KPI200",    # KOSPI 200 지수 (yfinance alias)
}

PERIOD_TO_DAYS = {
    "1mo": 45, "3mo": 100, "6mo": 200, "1y": 380, "2y": 750, "ytd": 100,
}

def _fetch_naver_ohlcv(naver_symbol: str, days: int = 100, max_retries: int = 3) -> pd.DataFrame:
    """네이버 금융 siseJson API에서 OHLCV 일봉 데이터를 가져온다.

    최대 max_retries회 재시도, 지수 백오프 적용.
    모든 재시도 실패 시 빈 DataFrame 반환.
    """
    end = datetime.datetime.now()
    start = end - timedelta(days=days)

    url = "https://api.finance.naver.com/siseJson.naver"
    params = {
        "symbol": naver_symbol,
        "requestType": "1",
        "startTime": start.strftime("%Y%m%d"),
        "endTime": end.strftime("%Y%m%d"),
        "timeframe": "day",
    }

    last_error = None
    for attempt in range(max_retries):
        try:
            resp = http_requests.get(
                url, params=params,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=10,
            )
            resp.raise_for_status()

            text = resp.text.strip().replace("'", '"')
            raw = json.loads(text)
            if len(raw) < 2:
                raise ValueError(f"Naver returned no data for {naver_symbol}")

            rows = raw[1:]  # skip header row
            df = pd.DataFrame(rows, columns=["datetime", "open", "high", "low", "close", "volume", "_extra"])
            df = df.drop(columns=["_extra"])
            df["datetime"] = df["datetime"].astype(str).str.strip()
            # Naver returns yyyymmdd format → convert to yyyy-mm-dd for lightweight-charts
            df["datetime"] = df["datetime"].apply(
                lambda x: f"{x[:4]}-{x[4:6]}-{x[6:8]}" if len(x) == 8 and x.isdigit() else x
            )
            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            df = df.dropna(subset=["close"])

            return df

        except Exception as e:
            last_error = e
            logger.warning(
                "Naver API 요청 실패 (시도 %d/%d): %s | symbol=%s",
                attempt + 1, max_retries, e, naver_symbol,
            )
            if attempt < max_retries - 1:
                time.sleep(1.5 ** attempt)  # 1.0s, 1.5s 대기

    # 모든 재시도 실패
    logger.error("Naver API 최종 실패: %s | symbol=%s", last_error, naver_symbol)
    return pd.DataFrame()

# ── 메인 분석 엔드포인트 ─────────────────────────────────────────────

@router.get("/analyze/{ticker}")
async def analyze_ticker(ticker: str, period: str = "1mo", interval: str = "1d"):
    """
    특정 종목의 OHLCV 과거 데이터를 가져온 후 각종 기술적 지표를 계산하여 반환합니다.
    - yfinance: 글로벌 주식/지수/선물
    - Naver Finance: KRX 파생상품 (@KS200F, @KS200)
    """
    try:
        # ── 캐시 확인 ──
        cache_key = f"{ticker}:{period}:{interval}"
        now = time.time()
        if cache_key in _analyze_cache and (now - _analyze_cache_ts.get(cache_key, 0)) < ANALYZE_CACHE_TTL:
            return JSONResponse(
                content={**_analyze_cache[cache_key], "cache_ts": _analyze_cache_ts[cache_key], "cache_ttl": ANALYZE_CACHE_TTL},
                headers={"Cache-Control": "no-cache"},
            )

        # ── Naver Finance 경로 (@로 시작하는 KRX 티커) ──
        if ticker in NAVER_TICKER_MAP:
            naver_sym = NAVER_TICKER_MAP[ticker]
            days = PERIOD_TO_DAYS.get(period, 100)
            data = _fetch_naver_ohlcv(naver_sym, days)

            if data.empty:
                raise HTTPException(status_code=404, detail=f"Naver: no data for {ticker}")

            result_df = calculate_basic_indicators(data)
            records = result_df.to_dict(orient="records")
            result = {"ticker": ticker, "period": period, "interval": interval, "data": records,
                      "cache_ts": now, "cache_ttl": ANALYZE_CACHE_TTL}
            _analyze_cache[cache_key] = result
            _analyze_cache_ts[cache_key] = now
            return result

        # ── yfinance 경로 (async) ──
        ticker = resolve_ticker(ticker)

        data = await asyncio.to_thread(yf.download, ticker, period=period, interval=interval, progress=False)

        if data.empty:
            raise HTTPException(status_code=404, detail="Data not found for the given ticker")

        data.reset_index(inplace=True)

        # MultiIndex 컬럼 안전하게 평탄화 (yfinance 0.2+ auto_adjust=True)
        if isinstance(data.columns, pd.MultiIndex):
            # 단일 티커 다운로드: 첫 번째 레벨만 사용
            data.columns = [c[0] if isinstance(c, tuple) else c for c in data.columns]

        # 컬럼명 소문자 정규화 + 중복 제거
        data.columns = [str(c).lower() for c in data.columns]
        if data.columns.duplicated().any():
            data = data.loc[:, ~data.columns.duplicated()]

        data.rename(columns={'date': 'datetime'}, inplace=True)
        data['datetime'] = data['datetime'].astype(str)

        # ── yfinance가 요청과 다른 interval의 데이터를 반환하는 경우 보정 ──
        # 일봉 요청인데 장중 데이터(시간 포함)가 돌아온 경우 → 일봉으로 집계
        if interval in ('1d', '1wk', '1mo'):
            sample = str(data['datetime'].iloc[0]) if len(data) > 0 else ""
            if ' ' in sample:
                # 장중 데이터 → 날짜별 OHLCV 집계
                data['_date'] = data['datetime'].str.split(' ').str[0]
                agg = data.groupby('_date').agg({
                    'open': 'first',
                    'high': 'max',
                    'low': 'min',
                    'close': 'last',
                    'volume': 'sum',
                }).reset_index()
                agg.rename(columns={'_date': 'datetime'}, inplace=True)
                data = agg

        # OHLC 컬럼에서 NaN/null 행 제거 (yfinance 데이터 결손 방어)
        ohlc_cols = ['open', 'high', 'low', 'close']
        for col in ohlc_cols:
            if col in data.columns:
                data[col] = pd.to_numeric(data[col], errors='coerce')
        data = data.dropna(subset=[c for c in ohlc_cols if c in data.columns])

        if data.empty:
            raise HTTPException(status_code=404, detail="No valid OHLC data after cleaning")

        result_df = calculate_basic_indicators(data)

        # 지표 계산 후 NaN → None 변환 방지: OHLC는 반드시 숫자
        records = result_df.to_dict(orient='records')
        records = [
            r for r in records
            if r.get('open') is not None and r.get('close') is not None
               and not (isinstance(r.get('open'), float) and np.isnan(r['open']))
               and not (isinstance(r.get('close'), float) and np.isnan(r['close']))
        ]

        result = {
            "ticker": ticker,
            "period": period,
            "interval": interval,
            "data": records,
            "cache_ts": now,
            "cache_ttl": ANALYZE_CACHE_TTL,
        }
        _analyze_cache[cache_key] = result
        _analyze_cache_ts[cache_key] = now
        return JSONResponse(
            content=result,
            headers={"Cache-Control": "no-cache"},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"analyze_ticker({ticker}, {period}, {interval}) failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ── 경량 Quote 엔드포인트 (폴링용) ────────────────────────────────────

@router.get("/quote/{ticker}")
def get_quote(ticker: str, count: int = 5):
    """
    경량 시세 조회. 최근 N봉 OHLCV + 최신 가격만 반환 (지표 계산 없음).
    30초 TTL 인메모리 캐시로 upstream API 호출 최소화.
    폴링 클라이언트용.
    """
    count = min(max(count, 1), 60)
    cache_key = f"{ticker}:{count}"
    now = time.time()

    # 캐시 히트 체크
    cached = _quote_cache.get(cache_key)
    if cached and (now - cached["_ts"]) < QUOTE_CACHE_TTL:
        result = {**cached["data"], "cached": True, "cache_ts": cached["_ts"], "cache_ttl": QUOTE_CACHE_TTL}
        return result

    try:
        df: pd.DataFrame

        # ── Naver Finance 경로 ──
        if ticker in NAVER_TICKER_MAP:
            naver_sym = NAVER_TICKER_MAP[ticker]
            df = _fetch_naver_ohlcv(naver_sym, days=max(count * 2, 15))
            if df.empty:
                raise HTTPException(status_code=404, detail=f"No quote data for {ticker}")

        # ── yfinance 경로 ──
        else:
            resolved = resolve_ticker(ticker)
            yf_period = "3mo" if count > 10 else "1mo"
            df = yf.download(resolved, period=yf_period, interval="1d", progress=False, auto_adjust=False)
            if df.empty:
                raise HTTPException(status_code=404, detail=f"No quote data for {ticker}")

            df.reset_index(inplace=True)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [c[0].lower() for c in df.columns]
            else:
                df.columns = [c.lower() for c in df.columns]
            df.rename(columns={"date": "datetime"}, inplace=True)
            df["datetime"] = df["datetime"].astype(str)

        # 최근 N봉만 추출
        recent = df.tail(count)
        candles = []
        for _, row in recent.iterrows():
            candles.append({
                "datetime": str(row.get("datetime", "")),
                "open": float(row.get("open", 0)),
                "high": float(row.get("high", 0)),
                "low": float(row.get("low", 0)),
                "close": float(row.get("close", 0)),
                "volume": int(row.get("volume", 0)),
            })

        # 최신 가격 정보
        if len(candles) >= 2:
            last = candles[-1]
            prev = candles[-2]
            change = last["close"] - prev["close"]
            change_pct = (change / prev["close"] * 100) if prev["close"] != 0 else 0
        elif len(candles) == 1:
            last = candles[0]
            change = 0
            change_pct = 0
        else:
            raise HTTPException(status_code=404, detail="No candle data")

        result = {
            "ticker": ticker,
            "updated_at": datetime.datetime.now().isoformat(),
            "cached": False,
            "cache_ts": now,
            "cache_ttl": QUOTE_CACHE_TTL,
            "candles": candles,
            "latest": {
                "price": last["close"],
                "change": round(change, 4),
                "change_pct": round(change_pct, 4),
                "high": last["high"],
                "low": last["low"],
                "volume": last["volume"],
            },
        }

        # 캐시 저장
        _quote_cache[cache_key] = {"data": result, "_ts": now}
        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search")
def search_ticker_endpoint(q: str = ""):
    """
    종목 코드 또는 이름으로 검색합니다.
    한국어/영어 모두 지원합니다.
    """
    results = search_tickers(q)
    return {"results": results}


@router.get("/market-overview")
async def market_overview_endpoint():
    """
    주요 시장 지수 현황 및 시장 국면(Regime) 분석을 반환합니다.
    5분 캐싱 적용.
    """
    return await asyncio.to_thread(get_market_overview)
