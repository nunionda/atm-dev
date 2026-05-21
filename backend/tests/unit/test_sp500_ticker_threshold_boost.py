"""
P3-2 회귀 보호: SP500 Futures 종목별 entry_threshold boost map.

핵심 단언:
  - entry_threshold_boost_map default = {"GC=F": 10.0, "MGC=F": 10.0}
  - _get_ticker_threshold_boost(ticker) 정확 동작
  - YAML override 가능
"""
from __future__ import annotations

import pytest

from data.config_manager import ATSConfig, SP500FuturesConfig
from strategy.sp500_futures import SP500FuturesStrategy


def _make_strategy(**fc_overrides) -> SP500FuturesStrategy:
    fc = SP500FuturesConfig(**fc_overrides) if fc_overrides else SP500FuturesConfig()
    return SP500FuturesStrategy(ATSConfig(sp500_futures=fc))


# ──────────────────────────────────────
# 1) 디폴트 map
# ──────────────────────────────────────

def test_gc_boost_default_10():
    fc = SP500FuturesConfig()
    assert fc.entry_threshold_boost_map.get("GC=F") == 10.0
    assert fc.entry_threshold_boost_map.get("MGC=F") == 10.0


def test_other_tickers_default_0():
    fc = SP500FuturesConfig()
    for t in ("ES=F", "NQ=F", "CL=F", "MES=F", "MNQ=F", "MCL=F"):
        assert fc.entry_threshold_boost_map.get(t, 0.0) == 0.0


# ──────────────────────────────────────
# 2) Helper 정확성
# ──────────────────────────────────────

def test_helper_returns_boost_for_known_ticker():
    strat = _make_strategy()
    assert strat._get_ticker_threshold_boost("GC=F") == 10.0
    assert strat._get_ticker_threshold_boost("MGC=F") == 10.0


def test_helper_returns_zero_for_unknown_ticker():
    strat = _make_strategy()
    assert strat._get_ticker_threshold_boost("ES=F") == 0.0
    assert strat._get_ticker_threshold_boost("UNKNOWN=F") == 0.0
    assert strat._get_ticker_threshold_boost(None) == 0.0
    assert strat._get_ticker_threshold_boost("") == 0.0


# ──────────────────────────────────────
# 3) Map override
# ──────────────────────────────────────

def test_custom_map_overrides_default():
    strat = _make_strategy(entry_threshold_boost_map={"ES=F": 5.0, "CL=F": 8.0})
    assert strat._get_ticker_threshold_boost("ES=F") == 5.0
    assert strat._get_ticker_threshold_boost("CL=F") == 8.0
    assert strat._get_ticker_threshold_boost("GC=F") == 0.0  # 새 map엔 없음


def test_yaml_override(tmp_path):
    from data.config_manager import ConfigManager

    yaml_file = tmp_path / "config.yaml"
    yaml_file.write_text("""
sp500_futures:
  entry_threshold_boost_map:
    GC=F: 15
    SI=F: 5
""")
    cm = ConfigManager(
        config_path=str(yaml_file),
        env_path=str(tmp_path / ".env"),
    )
    config = cm.load()
    assert config.sp500_futures.entry_threshold_boost_map.get("GC=F") == 15
    assert config.sp500_futures.entry_threshold_boost_map.get("SI=F") == 5


# ──────────────────────────────────────
# 4) Source 단언: 두 호출처에서 사용
# ──────────────────────────────────────

def test_p3_2_boost_applied_at_both_call_sites():
    import inspect
    import strategy.sp500_futures as mod
    src = inspect.getsource(mod)
    # _apply_regime 직후 두 곳 모두에서 boost 가산
    count = src.count("self._get_ticker_threshold_boost")
    assert count >= 2, f"P3-2 regression: boost helper must be applied at both signal generation paths (found {count})"
