"""
선물 지수 데이터 레이어 (Phase J1).

ATS 엔진이 spot 지수 (^GSPC, ^IXIC, ^KS200) 대신 선물 지수
(ES=F, NQ=F, ^KS200 — 한국은 spot index 자체가 선물 베이스)를
트래킹할 수 있도록 OHLCV + basis (선물-현물 프리미엄/디스카운트)
데이터를 통합 공급한다.

설계 결정:
1. 선물 OHLCV는 yfinance의 continuous front-month 시리즈를 사용
   (ES=F, NQ=F, YM=F 등 — 자동 롤오버 반영).
2. KOSPI200의 경우 ^KS200은 사실상 선물 만기를 추종하는 spot index이며,
   선물 만기/계약 정보는 KIS 브로커 API로 보강 (옵션).
3. basis = (futures - spot) / spot — 콘탱고(>0) / 백워데이션(<0).
   5일 SMA로 노이즈 제거.
4. 시뮬레이션 엔진의 update_index_data() 와 호환되는 OHLCV dict 포맷 반환.

Usage:
    from data.futures_data import fetch_futures_ohlcv, compute_basis_series

    df_fut = fetch_futures_ohlcv("sp500", "20240101", "20241231")
    df_spot = fetch_spot_ohlcv("sp500", "20240101", "20241231")
    basis = compute_basis_series(df_fut, df_spot, smooth=5)
"""

from __future__ import annotations

import os
from typing import Dict, List, Literal, Optional, Tuple

import pandas as pd

from backtest.data_downloader import download_and_cache
from infra.logger import get_logger

logger = get_logger("data.futures")

# ──────────────────────────────────────────────
# Market → Futures/Spot ticker mapping
# ──────────────────────────────────────────────

# 선물 컨티뉴어스 프론트 먼스 (yfinance ticker)
FUTURES_INDEX_MAP: Dict[str, str] = {
    "sp500":  "ES=F",   # E-mini S&P 500 (CME)
    "nasdaq": "NQ=F",   # E-mini Nasdaq 100 (CME)
    "ndx":    "NQ=F",   # alias
    "kospi":  "^KS200", # KOSPI 200 — Spot이지만 선물 거래 활성, basis 계산용 spot으로도 사용
}

# 동일 시장의 spot 지수 (basis 산출용 — 분모)
SPOT_INDEX_MAP: Dict[str, str] = {
    "sp500":  "^GSPC",
    "nasdaq": "^IXIC",
    "ndx":    "^IXIC",
    "kospi":  "^KS200",
}

# 계약 승수 (선물 1계약 = 인덱스 × multiplier)
# basis를 가격 단위로 변환할 때 참조용
FUTURES_MULTIPLIER: Dict[str, float] = {
    "sp500":  50.0,
    "nasdaq": 20.0,
    "ndx":    20.0,
    "kospi":  250_000.0,  # 원
}

# 통화
FUTURES_CURRENCY: Dict[str, str] = {
    "sp500":  "USD",
    "nasdaq": "USD",
    "ndx":    "USD",
    "kospi":  "KRW",
}


# ──────────────────────────────────────────────
# OHLCV fetchers
# ──────────────────────────────────────────────


def _fetch_ohlcv(ticker: str, start_date: str, end_date: str, cache_dir: str) -> pd.DataFrame:
    """공통 OHLCV 다운로드 (data_downloader 재사용)."""
    wl = [{"code": ticker, "ticker": ticker, "name": ticker}]
    cache_dir_full = os.path.join(cache_dir, "_macro")
    result = download_and_cache(
        watchlist=wl,
        start_date=start_date,
        end_date=end_date,
        cache_dir=cache_dir_full,
    )
    df = result.get(ticker, pd.DataFrame())
    return df


def fetch_futures_ohlcv(
    market: str,
    start_date: str,
    end_date: str,
    cache_dir: str = "data_store/historical",
) -> pd.DataFrame:
    """
    선물 지수 OHLCV를 다운로드한다.

    Args:
        market: "sp500" | "nasdaq" | "ndx" | "kospi"
        start_date: YYYYMMDD
        end_date: YYYYMMDD
        cache_dir: CSV 캐시 디렉토리

    Returns:
        DataFrame with columns [date, open, high, low, close, volume]
        — 빈 DataFrame 가능 (실패 시).
    """
    if market not in FUTURES_INDEX_MAP:
        raise ValueError(f"Unknown market: {market}. Available: {list(FUTURES_INDEX_MAP.keys())}")
    ticker = FUTURES_INDEX_MAP[market]
    logger.info("fetch_futures_ohlcv | market=%s | ticker=%s | %s..%s", market, ticker, start_date, end_date)
    df = _fetch_ohlcv(ticker, start_date, end_date, cache_dir)
    return df


def fetch_spot_ohlcv(
    market: str,
    start_date: str,
    end_date: str,
    cache_dir: str = "data_store/historical",
) -> pd.DataFrame:
    """
    spot 지수 OHLCV를 다운로드한다 (basis 계산 분모용).
    """
    if market not in SPOT_INDEX_MAP:
        raise ValueError(f"Unknown market: {market}. Available: {list(SPOT_INDEX_MAP.keys())}")
    ticker = SPOT_INDEX_MAP[market]
    logger.info("fetch_spot_ohlcv | market=%s | ticker=%s | %s..%s", market, ticker, start_date, end_date)
    df = _fetch_ohlcv(ticker, start_date, end_date, cache_dir)
    return df


# ──────────────────────────────────────────────
# Basis (futures - spot)
# ──────────────────────────────────────────────


def compute_basis_series(
    futures_df: pd.DataFrame,
    spot_df: pd.DataFrame,
    smooth: int = 5,
) -> pd.Series:
    """
    선물-현물 베이시스를 시계열로 산출한다.

    basis_pct = (futures_close - spot_close) / spot_close

    Args:
        futures_df: 선물 OHLCV (date, close 필수)
        spot_df: spot OHLCV (date, close 필수)
        smooth: SMA window. 0이면 raw.

    Returns:
        pd.Series indexed by date string (YYYYMMDD), values = basis_pct (smoothed)
        같은 날짜가 양쪽에 없으면 NaN.
    """
    if futures_df.empty or spot_df.empty:
        return pd.Series(dtype=float)

    f = futures_df.set_index("date")["close"].astype(float).rename("futures")
    s = spot_df.set_index("date")["close"].astype(float).rename("spot")

    merged = pd.concat([f, s], axis=1, join="inner").dropna()
    if merged.empty:
        return pd.Series(dtype=float)

    basis = (merged["futures"] - merged["spot"]) / merged["spot"]
    if smooth and smooth > 1:
        basis = basis.rolling(window=smooth, min_periods=1).mean()
    return basis


def classify_basis(value: float, threshold: float = 0.003) -> Literal["CONTANGO", "BACKWARDATION", "FLAT"]:
    """
    베이시스 한 값(%)을 3-상태로 분류.

    threshold 기본 0.3% — 0.3%를 넘어야 의미 있는 신호로 간주.
    """
    if value > threshold:
        return "CONTANGO"
    if value < -threshold:
        return "BACKWARDATION"
    return "FLAT"


def basis_signal_score(value: float, threshold: float = 0.003) -> float:
    """
    베이시스를 신호 점수로 변환 (regime 분류용).

    +10 = strong contango (bullish confirm)
    +5  = mild contango
     0  = flat
    -5  = mild backwardation
    -10 = strong backwardation (bearish hint)
    """
    if pd.isna(value):
        return 0.0
    if value > threshold * 2:
        return 10.0
    if value > threshold:
        return 5.0
    if value < -threshold * 2:
        return -10.0
    if value < -threshold:
        return -5.0
    return 0.0


# ──────────────────────────────────────────────
# Engine-compatible OHLCV dict producer
# ──────────────────────────────────────────────


def to_index_by_date(df: pd.DataFrame) -> Dict[str, Dict[str, float]]:
    """
    DataFrame을 SimulationEngine.update_index_data() 가 받는 dict 포맷으로 변환.

    Returns:
        {"YYYYMMDD": {"open": .., "high": .., "low": .., "close": .., "volume": ..}, ...}
    """
    result: Dict[str, Dict[str, float]] = {}
    if df.empty:
        return result
    for _, row in df.iterrows():
        d = str(row["date"])
        try:
            result[d] = {
                "open":   float(row.get("open", row["close"])),
                "high":   float(row.get("high", row["close"])),
                "low":    float(row.get("low", row["close"])),
                "close":  float(row["close"]),
                "volume": float(row.get("volume", 0)),
            }
        except (KeyError, ValueError, TypeError):
            continue
    return result


def fetch_index_payload(
    market: str,
    start_date: str,
    end_date: str,
    source: Literal["spot", "futures"] = "futures",
    cache_dir: str = "data_store/historical",
) -> Tuple[Dict[str, Dict[str, float]], pd.Series]:
    """
    SimulationEngine에 주입할 인덱스 OHLCV + basis series를 한 번에 산출.

    Args:
        market: "sp500" | "nasdaq" | "ndx" | "kospi"
        start_date / end_date: YYYYMMDD
        source: "futures" — ES=F/NQ=F/^KS200; "spot" — ^GSPC/^IXIC/^KS200
        cache_dir: 캐시 디렉토리

    Returns:
        (index_by_date dict, basis pd.Series)
        — index_by_date는 엔진의 update_index_data() 가 받는 포맷.
        — basis는 항상 (futures - spot)/spot 으로 계산 (source 무관).
        — KOSPI는 spot=futures여서 basis가 항상 0이 됨.
    """
    fut_df = fetch_futures_ohlcv(market, start_date, end_date, cache_dir=cache_dir)
    spot_df = fetch_spot_ohlcv(market, start_date, end_date, cache_dir=cache_dir)

    # source에 따라 엔진 주입 OHLCV 결정
    if source == "futures":
        primary_df = fut_df if not fut_df.empty else spot_df
    else:
        primary_df = spot_df if not spot_df.empty else fut_df

    index_by_date = to_index_by_date(primary_df)
    basis = compute_basis_series(fut_df, spot_df, smooth=5)
    return index_by_date, basis


# ──────────────────────────────────────────────
# Contract roll metadata (placeholder for future expansion)
# ──────────────────────────────────────────────

# Futures 만기 캘린더 — 분기 만기 (3, 6, 9, 12월 셋째 금요일)
# yfinance ES=F/NQ=F는 자동 roll된 continuous series를 제공하므로
# 일반 백테스트에는 충분. 정밀한 roll-yield 분석이 필요할 경우 확장.
FUTURES_QUARTERLY_MONTHS: List[int] = [3, 6, 9, 12]


def get_next_expiration(date_str: str, market: str) -> Optional[str]:
    """
    주어진 날짜의 다음 선물 만기일(분기 셋째 금요일)을 추정.

    Args:
        date_str: YYYYMMDD
        market: 시장 (currently same logic for all markets — quarterly)

    Returns:
        YYYYMMDD 또는 None
    """
    try:
        dt = pd.Timestamp(date_str)
    except Exception:
        return None

    for offset in range(0, 13):
        candidate = dt + pd.DateOffset(months=offset)
        if candidate.month not in FUTURES_QUARTERLY_MONTHS:
            continue
        # 해당 월의 셋째 금요일 산출
        first_day = pd.Timestamp(year=candidate.year, month=candidate.month, day=1)
        # 첫 주 금요일까지의 일수 (월요일=0, 일요일=6, 금요일=4)
        first_friday_offset = (4 - first_day.weekday()) % 7
        third_friday = first_day + pd.Timedelta(days=first_friday_offset + 14)
        if third_friday >= dt:
            return third_friday.strftime("%Y%m%d")
    return None
