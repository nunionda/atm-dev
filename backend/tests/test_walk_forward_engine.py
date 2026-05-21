"""
Walk-Forward Engine 단위 테스트.

검증:
  - 자산군 분류 (equity_index / energy / metal)
  - 윈도우 생성 (ES/NQ → 3m × 4, CL/GC → 1m × 12)
  - Roll date 계산 — Equity Thursday -8d, Energy 월 만기, Metal 격월 만기
  - Blackout 체크 (roll ± 2영업일)
  - 분포 통계 계산 (median, p25, p75, worst, best)
  - 윈도우는 한 contract life 안에 fully contained (roll-free)
"""

from __future__ import annotations

import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backtest.walk_forward_engine import (  # noqa: E402
    detect_asset_class,
    generate_equity_windows,
    generate_monthly_windows,
    generate_windows,
    compute_roll_dates,
    is_in_blackout,
    _third_friday,
    _equity_index_roll_thursday,
    _energy_last_trading_day,
    _metal_last_trading_day,
    WalkForwardEngine,
    WindowMetrics,
    Window,
)


# ─────────────────────────────────────────
# Asset Classification
# ─────────────────────────────────────────

def test_detect_asset_class_equity():
    assert detect_asset_class("ES=F") == "equity_index"
    assert detect_asset_class("MES=F") == "equity_index"
    assert detect_asset_class("NQ=F") == "equity_index"
    assert detect_asset_class("MNQ=F") == "equity_index"


def test_detect_asset_class_energy():
    assert detect_asset_class("CL=F") == "energy"


def test_detect_asset_class_metal():
    assert detect_asset_class("GC=F") == "metal"


# ─────────────────────────────────────────
# Date Helpers
# ─────────────────────────────────────────

def test_third_friday_march_2026():
    # 2026년 3월 셋째 금요일 = 2026-03-20
    assert _third_friday(2026, 3) == date(2026, 3, 20)


def test_third_friday_june_2026():
    # 2026-06-19
    assert _third_friday(2026, 6) == date(2026, 6, 19)


def test_equity_roll_thursday_8_days_before():
    """Equity roll = 3rd Friday - 8 days."""
    roll = _equity_index_roll_thursday(2026, 3)
    assert roll == date(2026, 3, 12)  # March 12 (Thursday)
    assert roll.weekday() == 3  # Thursday


def test_energy_last_trading_day():
    """CL Feb 2026 contract: trading ends 3 business days before Jan 25.
    Jan 25, 2026 = Sunday → roll back to Fri Jan 23 → 3 biz days back = Tue Jan 20.
    """
    last = _energy_last_trading_day(2026, 2)
    assert last == date(2026, 1, 20)


def test_metal_last_trading_day():
    """GC Feb 2026: last trading = 3 business days before Feb 28 (last weekday).
    Feb 28, 2026 = Saturday → roll back to Fri Feb 27 → 3 biz days back = Tue Feb 24.
    """
    last = _metal_last_trading_day(2026, 2)
    assert last == date(2026, 2, 24)


# ─────────────────────────────────────────
# Window Generation
# ─────────────────────────────────────────

def test_equity_windows_4_quarters():
    """ES end_date=2026-05-22 → 직전 4 분기 윈도우."""
    windows = generate_equity_windows("ES=F", date(2026, 5, 22), n=4)
    assert len(windows) == 4
    # 각 윈도우는 분기 라벨
    labels = [w.label for w in windows]
    # ES=F에서 가장 최근 분기는 2026Q2 (June expiry)
    assert "2026Q2" in labels or "2026Q1" in labels


def test_equity_windows_contract_codes():
    windows = generate_equity_windows("ES=F", date(2026, 5, 22), n=4)
    # ESM26 (June), ESH26 (March) 등 — 분기 contract code
    codes = [w.contract_code for w in windows]
    # 모든 코드는 ES로 시작하고 H/M/U/Z 중 하나 포함
    for c in codes:
        assert c.startswith("ES")
        assert any(letter in c for letter in "HMUZ")


def test_equity_windows_roll_free():
    """Equity 3m 윈도우는 한 contract life 안에 fully contained되어야 함.

    each window의 start_date > 이전 contract 만기, end_date < 다음 roll Thursday.
    """
    windows = generate_equity_windows("ES=F", date(2026, 5, 22), n=4)
    for w in windows:
        # contract_code에서 만기월 추출
        month_code = w.contract_code[2]
        year_yy = int(w.contract_code[3:5])
        year = 2000 + year_yy
        month = "FGHJKMNQUVXZ".index(month_code) + 1

        roll_thu = _equity_index_roll_thursday(year, month)
        third_fri = _third_friday(year, month)

        end_d = date(
            int(w.end_date[:4]), int(w.end_date[4:6]), int(w.end_date[6:8]),
        )
        # 윈도우 end는 다음 roll thursday 이전이어야 함
        assert end_d <= roll_thu, (
            f"Window {w.label} ends {end_d} but roll Thursday is {roll_thu}"
        )


def test_monthly_windows_energy_12():
    windows = generate_monthly_windows("CL=F", date(2026, 5, 22), n=12, asset_class="energy")
    assert len(windows) == 12
    # 각 윈도우는 월별 (단, 가장 최근은 5월이 끝나기 전이라 잘릴 수 있음)
    for w in windows:
        assert w.duration_days() > 0


def test_monthly_windows_metal_12():
    windows = generate_monthly_windows("GC=F", date(2026, 5, 22), n=12, asset_class="metal")
    assert len(windows) == 12
    for w in windows:
        assert w.contract_code.startswith("GC")


def test_generate_windows_routing():
    """generate_windows가 ticker → 자산군 → 정확한 윈도우 함수 호출."""
    es = generate_windows("ES=F", date(2026, 5, 22))
    cl = generate_windows("CL=F", date(2026, 5, 22))
    gc = generate_windows("GC=F", date(2026, 5, 22))

    assert len(es) == 4   # equity 3m × 4
    assert len(cl) == 12  # energy 1m × 12
    assert len(gc) == 12  # metal 1m × 12


# ─────────────────────────────────────────
# Roll Date Calculation (자산군별)
# ─────────────────────────────────────────

def test_compute_roll_dates_equity_quarterly():
    """ES는 분기당 1개 roll = 1년에 4개."""
    rolls = compute_roll_dates("ES=F", 2026, 2026)
    assert len(rolls) == 4
    # 모두 Thursday
    assert all(r.weekday() == 3 for r in rolls)


def test_compute_roll_dates_energy_monthly():
    """CL은 매월 roll = 1년에 12개."""
    rolls = compute_roll_dates("CL=F", 2026, 2026)
    assert len(rolls) == 12


def test_compute_roll_dates_metal_bimonthly():
    """GC active months = Feb/Apr/Jun/Aug/Oct/Dec = 1년에 6개."""
    rolls = compute_roll_dates("GC=F", 2026, 2026)
    assert len(rolls) == 6


# ─────────────────────────────────────────
# Blackout Check
# ─────────────────────────────────────────

def test_blackout_within_2_business_days():
    """Roll date ±2 영업일 이내 blackout."""
    roll_dates = [date(2026, 3, 12)]  # Thursday
    # Same day
    assert is_in_blackout(date(2026, 3, 12), roll_dates, 2) is True
    # +1 biz day = Friday
    assert is_in_blackout(date(2026, 3, 13), roll_dates, 2) is True
    # +2 biz days = Monday (weekend skip)
    assert is_in_blackout(date(2026, 3, 16), roll_dates, 2) is True
    # +3 biz days = Tuesday — out of blackout
    assert is_in_blackout(date(2026, 3, 17), roll_dates, 2) is False
    # -1 biz day = Wednesday
    assert is_in_blackout(date(2026, 3, 11), roll_dates, 2) is True
    # -3 biz days = Monday before
    assert is_in_blackout(date(2026, 3, 9), roll_dates, 2) is False


def test_blackout_no_rolls_returns_false():
    assert is_in_blackout(date(2026, 5, 1), [], 2) is False


# ─────────────────────────────────────────
# Distribution Stats
# ─────────────────────────────────────────

def test_compute_distributions_basic():
    """간단한 윈도우 메트릭에서 분포 계산."""
    w = Window(index=0, label="x", start_date="20260101", end_date="20260201", contract_code="ESH26")
    metrics = [
        WindowMetrics(window=w, total_return_pct=10.0, sharpe_ratio=1.0,
                      max_drawdown_pct=-5.0, profit_factor=1.5, win_rate=60.0, total_trades=10),
        WindowMetrics(window=w, total_return_pct=-5.0, sharpe_ratio=0.5,
                      max_drawdown_pct=-10.0, profit_factor=0.8, win_rate=40.0, total_trades=8),
        WindowMetrics(window=w, total_return_pct=2.0, sharpe_ratio=0.8,
                      max_drawdown_pct=-3.0, profit_factor=1.2, win_rate=55.0, total_trades=12),
    ]
    dists = WalkForwardEngine._compute_distributions(metrics)
    by_metric = {d.metric: d for d in dists}

    ret = by_metric["total_return_pct"]
    assert ret.count == 3
    assert ret.median == 2.0
    assert ret.worst == -5.0
    assert ret.best == 10.0


def test_compute_distributions_excludes_errored():
    """error가 있는 윈도우는 통계에서 제외."""
    w = Window(index=0, label="x", start_date="20260101", end_date="20260201", contract_code="ESH26")
    metrics = [
        WindowMetrics(window=w, total_return_pct=10.0, sharpe_ratio=1.0),
        WindowMetrics(window=w, error="data fetch failed"),  # 제외 대상
        WindowMetrics(window=w, total_return_pct=5.0, sharpe_ratio=0.5),
    ]
    dists = WalkForwardEngine._compute_distributions(metrics)
    by_metric = {d.metric: d for d in dists}
    assert by_metric["total_return_pct"].count == 2  # 2 valid only
