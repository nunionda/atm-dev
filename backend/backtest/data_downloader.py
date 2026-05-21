"""
히스토리컬 백테스트용 OHLCV 데이터 다운로더.

yfinance에서 일봉 데이터를 다운로드하고 CSV로 캐시한다.
- interval="1d" 사용 (인트라데이 제약 없음)
- 캐시가 기간을 커버하면 재다운로드 스킵
- 기존 data_loader.py의 load_ohlcv() 재사용
"""

from __future__ import annotations

import os
from typing import Dict, List

import pandas as pd
import yfinance as yf

from backtest.data_loader import load_ohlcv
from infra.logger import get_logger

logger = get_logger("backtest.downloader")

DEFAULT_CACHE_DIR = "data_store/historical"


def download_and_cache(
    watchlist: List[Dict[str, str]],
    start_date: str,
    end_date: str,
    cache_dir: str = DEFAULT_CACHE_DIR,
    force: bool = False,
) -> Dict[str, pd.DataFrame]:
    """
    yfinance에서 OHLCV 데이터를 다운로드하고 CSV로 캐시한다.

    Args:
        watchlist: [{"code": ..., "ticker": ..., "name": ...}, ...]
        start_date: YYYYMMDD (워밍업 시작일 포함)
        end_date: YYYYMMDD
        cache_dir: CSV 캐시 디렉토리
        force: True이면 캐시 무시하고 재다운로드

    Returns:
        Dict[code, DataFrame] — OHLCV 데이터 (date, open, high, low, close, volume)
    """
    os.makedirs(cache_dir, exist_ok=True)
    result: Dict[str, pd.DataFrame] = {}
    to_download: List[Dict[str, str]] = []

    # 1. 캐시 체크
    for w in watchlist:
        code = w["code"]
        csv_path = os.path.join(cache_dir, f"{code}.csv")

        if not force and os.path.exists(csv_path):
            df = load_ohlcv(code, cache_dir)
            if not df.empty:
                # 날짜 범위 커버 여부 확인
                min_date = df["date"].min()
                max_date = df["date"].max()
                if min_date <= start_date and max_date >= end_date:
                    result[code] = df
                    logger.info("Cache hit: %s (%s ~ %s)", code, min_date, max_date)
                    continue
                else:
                    logger.info(
                        "Cache partial: %s (%s~%s), need %s~%s → re-download",
                        code, min_date, max_date, start_date, end_date,
                    )

        to_download.append(w)

    if not to_download:
        logger.info("All %d stocks loaded from cache", len(result))
        return result

    # 2. yfinance 다운로드
    logger.info("Downloading %d stocks from yfinance...", len(to_download))

    # YYYYMMDD → YYYY-MM-DD (yfinance 형식)
    start_fmt = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:]}"
    end_fmt = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:]}"

    tickers = [w["ticker"] for w in to_download]

    try:
        if len(tickers) == 1:
            data = yf.download(
                tickers[0], start=start_fmt, end=end_fmt,
                interval="1d", progress=True, auto_adjust=False,
            )
            # 단일 티커: MultiIndex 없음
            if not data.empty:
                _save_single(data, to_download[0], cache_dir, result)
        else:
            data = yf.download(
                " ".join(tickers), start=start_fmt, end=end_fmt,
                interval="1d", progress=True, auto_adjust=False,
            )
            if not data.empty:
                for w in to_download:
                    _extract_and_save(data, w, cache_dir, result)
    except Exception as e:
        logger.error("yfinance bulk download failed: %s", e)
        # 개별 다운로드 폴백
        for w in to_download:
            if w["code"] not in result:
                _download_single(w, start_fmt, end_fmt, cache_dir, result)

    # 3. 벌크에서 누락된 종목 개별 다운로드
    for w in to_download:
        if w["code"] not in result:
            _download_single(w, start_fmt, end_fmt, cache_dir, result)

    logger.info(
        "Download complete: %d/%d stocks loaded",
        len(result), len(watchlist),
    )
    return result


def download_and_cache_batched(
    watchlist: List[Dict[str, str]],
    start_date: str,
    end_date: str,
    cache_dir: str = DEFAULT_CACHE_DIR,
    force: bool = False,
    batch_size: int = 50,
    delay_between_batches: float = 2.0,
) -> Dict[str, pd.DataFrame]:
    """
    대규모 유니버스용 배치 다운로드.

    50종목씩 나누어 다운로드하고, 배치 간 딜레이를 두어
    yfinance rate limit을 회피한다. 기존 download_and_cache()를 재활용.

    Args:
        watchlist: 전체 종목 리스트
        start_date: YYYYMMDD
        end_date: YYYYMMDD
        cache_dir: 캐시 디렉토리
        force: 캐시 무시 여부
        batch_size: 배치당 종목 수 (기본 50)
        delay_between_batches: 배치 간 대기 시간(초)

    Returns:
        Dict[code, DataFrame] — 전체 OHLCV 데이터
    """
    import time

    result: Dict[str, pd.DataFrame] = {}
    total = len(watchlist)
    num_batches = (total + batch_size - 1) // batch_size

    logger.info(
        "Batched download: %d stocks in %d batches (size=%d)",
        total, num_batches, batch_size,
    )

    for i in range(0, total, batch_size):
        batch = watchlist[i:i + batch_size]
        batch_num = i // batch_size + 1
        logger.info("  Batch %d/%d: %d stocks", batch_num, num_batches, len(batch))

        batch_result = download_and_cache(
            watchlist=batch,
            start_date=start_date,
            end_date=end_date,
            cache_dir=cache_dir,
            force=force,
        )
        result.update(batch_result)

        # 마지막 배치가 아니면 딜레이
        if i + batch_size < total and delay_between_batches > 0:
            time.sleep(delay_between_batches)

    logger.info(
        "Batched download complete: %d/%d stocks loaded",
        len(result), total,
    )
    return result


def _save_single(
    data: pd.DataFrame,
    w: Dict[str, str],
    cache_dir: str,
    result: Dict[str, pd.DataFrame],
):
    """단일 티커 다운로드 결과를 CSV로 저장."""
    try:
        ticker = w["ticker"]

        if isinstance(data.columns, pd.MultiIndex):
            # v5: MultiIndex 컬럼에서 해당 티커 데이터만 추출
            # yfinance v0.2.40+는 단일 티커도 MultiIndex 반환
            try:
                df = pd.DataFrame({
                    "open": data[("Open", ticker)],
                    "high": data[("High", ticker)],
                    "low": data[("Low", ticker)],
                    "close": data[("Close", ticker)],
                    "volume": data[("Volume", ticker)],
                }).dropna()
            except KeyError:
                # 티커 이름 불일치 시 level 0 flatten 폴백 (단일 티커 전용)
                df = data.copy()
                df.columns = df.columns.get_level_values(0)
                df.columns = [str(c).lower() for c in df.columns]
                # 중복 컬럼 발생 시 (멀티 티커 데이터 오진입) → 첫 번째만 유지
                if df.columns.duplicated().any():
                    df = df.loc[:, ~df.columns.duplicated()]
                df = df[["open", "high", "low", "close", "volume"]].dropna()
        else:
            df = data.copy()
            df.columns = [str(c).lower() for c in df.columns]
            df = df[["open", "high", "low", "close", "volume"]].dropna()

        if df.empty:
            logger.warning("Empty data for %s", w["code"])
            return

        # UTC → 로컬 시간대 변환 (일봉 날짜 정합성)
        if hasattr(df.index, 'tz') and df.index.tz is not None:
            df.index = df.index.tz_localize(None)

        df["date"] = df.index.strftime("%Y%m%d")
        df = df.reset_index(drop=True)
        df = df[["date", "open", "high", "low", "close", "volume"]]
        df["volume"] = df["volume"].astype(int)

        # 데이터 품질 검증: 일봉 데이터는 최소 5개 이상의 고유 날짜가 있어야 함
        unique_dates = df["date"].nunique()
        if unique_dates < 5 and len(df) > 10:
            logger.error(
                "Corrupted data for %s: %d rows but only %d unique dates (likely intraday leak). Skipping.",
                w["code"], len(df), unique_dates,
            )
            return

        csv_path = os.path.join(cache_dir, f"{w['code']}.csv")
        df.to_csv(csv_path, index=False)
        result[w["code"]] = df
        logger.info("Saved %s: %d rows (%s ~ %s)", w["code"], len(df), df["date"].iloc[0], df["date"].iloc[-1])
    except Exception as e:
        logger.error("Failed to process %s: %s", w["code"], e)


def _extract_and_save(
    data: pd.DataFrame,
    w: Dict[str, str],
    cache_dir: str,
    result: Dict[str, pd.DataFrame],
):
    """멀티 티커 벌크 다운로드에서 개별 종목 추출 및 저장."""
    try:
        ticker = w["ticker"]
        if isinstance(data.columns, pd.MultiIndex):
            stock_df = pd.DataFrame({
                "open": data[("Open", ticker)],
                "high": data[("High", ticker)],
                "low": data[("Low", ticker)],
                "close": data[("Close", ticker)],
                "volume": data[("Volume", ticker)],
            }).dropna()
        else:
            # 단일 티커가 벌크 호출에서 반환된 경우
            stock_df = data.rename(columns=str.lower)
            stock_df = stock_df[["open", "high", "low", "close", "volume"]].dropna()

        if stock_df.empty:
            logger.warning("No data for %s in bulk download", w["code"])
            return

        # UTC → 로컬 시간대 변환 (일봉 날짜 정합성)
        if hasattr(stock_df.index, 'tz') and stock_df.index.tz is not None:
            stock_df.index = stock_df.index.tz_localize(None)

        stock_df["date"] = stock_df.index.strftime("%Y%m%d")
        stock_df = stock_df.reset_index(drop=True)
        stock_df = stock_df[["date", "open", "high", "low", "close", "volume"]]
        stock_df["volume"] = stock_df["volume"].astype(int)

        csv_path = os.path.join(cache_dir, f"{w['code']}.csv")
        stock_df.to_csv(csv_path, index=False)
        result[w["code"]] = stock_df
        logger.info("Saved %s: %d rows", w["code"], len(stock_df))

    except Exception as e:
        logger.warning("Failed to extract %s from bulk: %s", w["code"], e)


def _download_single(
    w: Dict[str, str],
    start_fmt: str,
    end_fmt: str,
    cache_dir: str,
    result: Dict[str, pd.DataFrame],
):
    """개별 종목 다운로드 (벌크 실패 시 폴백)."""
    try:
        logger.info("Individual download: %s (%s)", w["code"], w["ticker"])
        data = yf.download(
            w["ticker"], start=start_fmt, end=end_fmt,
            interval="1d", progress=False, auto_adjust=False,
        )
        if not data.empty:
            _save_single(data, w, cache_dir, result)
    except Exception as e:
        logger.error("Individual download failed for %s: %s", w["code"], e)


def analyze_survivorship_bias(
    watchlist: List[Dict[str, str]],
    ohlcv_map: Dict[str, pd.DataFrame],
    start_date: str,
    end_date: str,
) -> Dict[str, object]:
    """
    생존자 편향 분석.

    각 종목의 데이터 커버리지를 분석하여 bias 점수를 산출한다.
    - 전체 기간 대비 데이터가 있는 종목 비율
    - 데이터 시작이 늦거나 중간에 빠지는 종목 탐지
    - 점수: 1.0 = bias 없음, 0.0 = 심각한 bias

    Returns:
        Dict with keys:
        - score (float): 0~1, 1.0 = bias 없음
        - warning (str): 경고 메시지 (비어있으면 양호)
        - details (dict): 종목별 커버리지 상세
    """
    total_stocks = len(watchlist)
    loaded_stocks = len(ohlcv_map)

    if total_stocks == 0:
        return {"score": 1.0, "warning": "", "details": {}}

    # 1. 종목 로드율
    load_ratio = loaded_stocks / total_stocks

    # 2. 개별 종목 커버리지 분석
    coverage_details: Dict[str, Dict[str, object]] = {}
    full_coverage_count = 0
    partial_coverage_codes: List[str] = []
    late_start_codes: List[str] = []

    for w in watchlist:
        code = w["code"]
        if code not in ohlcv_map:
            coverage_details[code] = {
                "status": "MISSING",
                "coverage_pct": 0.0,
                "data_start": "",
                "data_end": "",
            }
            continue

        df = ohlcv_map[code]
        if df.empty:
            coverage_details[code] = {
                "status": "EMPTY",
                "coverage_pct": 0.0,
                "data_start": "",
                "data_end": "",
            }
            continue

        data_start = df["date"].min()
        data_end = df["date"].max()
        data_days = len(df)

        # 기대 거래일 수 추정 (연 252일 기준)
        try:
            start_year = int(start_date[:4]) + int(start_date[4:6]) / 12
            end_year = int(end_date[:4]) + int(end_date[4:6]) / 12
            expected_days = max(int((end_year - start_year) * 252), 1)
        except (ValueError, ZeroDivisionError):
            expected_days = max(data_days, 1)

        coverage_pct = min(data_days / expected_days, 1.0)

        status = "FULL"
        if data_start > start_date:
            status = "LATE_START"
            late_start_codes.append(code)
        if coverage_pct < 0.9:
            status = "PARTIAL"
            partial_coverage_codes.append(code)
        if coverage_pct >= 0.9 and data_start <= start_date:
            full_coverage_count += 1

        coverage_details[code] = {
            "status": status,
            "coverage_pct": round(coverage_pct * 100, 1),
            "data_start": data_start,
            "data_end": data_end,
        }

    # 3. 종합 점수 계산
    # - 로드율 50% 가중, 커버리지 50% 가중
    coverage_score = full_coverage_count / max(loaded_stocks, 1)
    score = 0.5 * load_ratio + 0.5 * coverage_score
    score = round(max(0.0, min(1.0, score)), 3)

    # 4. 경고 메시지 생성
    warnings: List[str] = []
    missing_count = total_stocks - loaded_stocks
    if missing_count > 0:
        warnings.append(f"{missing_count}/{total_stocks} stocks missing data")
    if late_start_codes:
        codes_str = ", ".join(late_start_codes[:5])
        if len(late_start_codes) > 5:
            codes_str += f" +{len(late_start_codes)-5} more"
        warnings.append(f"Late start: {codes_str}")
    if partial_coverage_codes:
        codes_str = ", ".join(partial_coverage_codes[:5])
        if len(partial_coverage_codes) > 5:
            codes_str += f" +{len(partial_coverage_codes)-5} more"
        warnings.append(f"Partial coverage: {codes_str}")

    warning = "; ".join(warnings) if warnings else ""

    return {
        "score": score,
        "warning": warning,
        "details": coverage_details,
        "missing_count": missing_count,
        "late_start_count": len(late_start_codes),
        "partial_count": len(partial_coverage_codes),
        "full_coverage_count": full_coverage_count,
        "total_stocks": total_stocks,
        "loaded_stocks": loaded_stocks,
    }
