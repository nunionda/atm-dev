"""
백테스트용 히스토리컬 OHLCV 데이터 로더

CSV 포맷: date,open,high,low,close,volume (date는 YYYYMMDD)
CSV 경로: {data_dir}/{stock_code}.csv
"""

from __future__ import annotations

import os
from typing import Dict, List

import pandas as pd

from infra.logger import get_logger

logger = get_logger("backtest.data_loader")


def load_ohlcv(stock_code: str, data_dir: str) -> pd.DataFrame:
    """단일 종목의 OHLCV CSV를 로드한다."""
    path = os.path.join(data_dir, f"{stock_code}.csv")
    if not os.path.exists(path):
        logger.warning("OHLCV file not found: %s", path)
        return pd.DataFrame()

    df = pd.read_csv(path, dtype={"date": str})

    # 컬럼 정규화
    df.columns = [c.strip().lower() for c in df.columns]
    required = {"date", "open", "high", "low", "close", "volume"}
    if not required.issubset(set(df.columns)):
        logger.error("Invalid CSV columns: %s (need %s)", list(df.columns), required)
        return pd.DataFrame()

    # 타입 변환
    for col in ["open", "high", "low", "close"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype(int)

    # date를 YYYYMMDD 문자열로 통일
    df["date"] = df["date"].astype(str).str.replace("-", "")

    df = df.sort_values("date").reset_index(drop=True)
    logger.info("Loaded %s: %d rows (%s ~ %s)", stock_code, len(df), df["date"].iloc[0], df["date"].iloc[-1])
    return df


def load_universe(codes: List[str], data_dir: str) -> Dict[str, pd.DataFrame]:
    """여러 종목의 OHLCV 데이터를 로드한다."""
    result = {}
    for code in codes:
        df = load_ohlcv(code, data_dir)
        if not df.empty:
            result[code] = df
    logger.info("Universe loaded: %d/%d codes", len(result), len(codes))
    return result


def get_trading_dates(
    ohlcv_map: Dict[str, pd.DataFrame],
    start_date: str,
    end_date: str,
) -> List[str]:
    """
    로드된 OHLCV 데이터에서 거래일 목록을 추출한다.
    start_date, end_date: YYYYMMDD 형식
    """
    all_dates = set()
    for df in ohlcv_map.values():
        all_dates.update(df["date"].tolist())

    # 범위 필터링
    start = start_date.replace("-", "")
    end = end_date.replace("-", "")
    filtered = sorted(d for d in all_dates if start <= d <= end)

    logger.info("Trading dates: %d days (%s ~ %s)", len(filtered),
                filtered[0] if filtered else "N/A",
                filtered[-1] if filtered else "N/A")
    return filtered
