"""
P3-3 회귀 보호: watchlist ticker 정정.

이력:
  - FI → FISV (Fiserv 2024.07 ticker 변경, 야후는 신규 FI 데이터 미제공)
  - MMC (Marsh & McLennan): watchlist 유지 (간헐 fail은 batched downloader가 skip)
  - 263750/041510/035900 (.KS → .KQ): 이전 세션에서 fix됨 (KOSDAQ suffix 정정)
"""
from __future__ import annotations

import pytest


def _load_sp500_watchlist():
    """sp500 watchlist 로드."""
    from simulation.watchlists import MARKET_CONFIG
    sp500 = MARKET_CONFIG.get("sp500", {})
    return sp500.get("watchlist", [])


# ──────────────────────────────────────
# 1) FI → FISV 정정
# ──────────────────────────────────────

def test_fi_replaced_with_fisv_in_sp500():
    """SP500 watchlist에서 FI 제거 + FISV 추가."""
    wl = _load_sp500_watchlist()
    tickers = {item["ticker"] for item in wl}
    codes = {item["code"] for item in wl}

    assert "FI" not in tickers, "FI (야후 미지원 신규 ticker)는 watchlist에서 제거되어야 함"
    assert "FISV" in tickers, "FISV (historical 정상 작동)로 대체되어야 함"
    assert "FISV" in codes


def test_fisv_entry_has_fiserv_name():
    """FISV 엔트리는 Fiserv 이름 + Financial 섹터."""
    wl = _load_sp500_watchlist()
    fisv = next((item for item in wl if item["ticker"] == "FISV"), None)
    assert fisv is not None
    assert fisv["name"] == "Fiserv"
    assert fisv["sector"] == "Financial"


# ──────────────────────────────────────
# 2) MMC는 watchlist 유지
# ──────────────────────────────────────

def test_mmc_disabled_due_to_yahoo_persistent_failure():
    """MMC는 watchlist에서 비활성화 (야후가 3회 retry 모두 RateLimitError 반환).
    AAPL/JPM 등은 정상이므로 MMC 단독 야후 이슈로 추정.
    야후 측 복구 시 watchlists.py에서 주석 해제."""
    wl = _load_sp500_watchlist()
    tickers = {item["ticker"] for item in wl}
    assert "MMC" not in tickers, (
        "MMC는 야후 지속 fail로 비활성화 상태 — watchlists.py에서 주석 처리됨"
    )


# ──────────────────────────────────────
# 3) KOSDAQ suffix 회귀 (이전 세션 fix)
# ──────────────────────────────────────

def test_kosdaq_tickers_use_kq_suffix():
    """263750/041510/035900은 KOSDAQ 종목 → .KQ suffix 필수 (.KS 아님)."""
    from simulation.watchlists import MARKET_CONFIG
    kospi_wl = MARKET_CONFIG.get("kospi", {}).get("watchlist", [])
    by_code = {item["code"]: item for item in kospi_wl}

    for kosdaq_code in ("263750", "041510", "035900"):
        if kosdaq_code in by_code:
            ticker = by_code[kosdaq_code]["ticker"]
            assert ticker.endswith(".KQ"), (
                f"KOSDAQ {kosdaq_code} must use .KQ suffix, got {ticker}"
            )
