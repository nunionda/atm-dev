"""T + U unit tests.

T: per_ticker_overrides — ticker별 enable_short/long, bear/MR bypass 차단
U: regime_strategy_modes — regime별 MR-SHORT 활성/비활성, SHORT threshold 조정
"""
from __future__ import annotations

import os
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(os.path.dirname(THIS_DIR))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from data.config_manager import ATSConfig, SP500FuturesConfig
from strategy.sp500_futures import SP500FuturesStrategy


def _make_strategy() -> SP500FuturesStrategy:
    return SP500FuturesStrategy(ATSConfig())


# ─────────────────────────── T tests ───────────────────────────


def test_t_per_ticker_default_baseline_ticker_unchanged():
    """ES=F/NQ=F: override 없음 → enable_short=True (baseline)."""
    s = _make_strategy()
    assert s._get_ticker_override("ES=F", "enable_short", True) is True
    assert s._get_ticker_override("NQ=F", "enable_short", True) is True


def test_t_per_ticker_gc_cl_short_blocked():
    """GC/CL: enable_short=False default (LONG-only)."""
    s = _make_strategy()
    assert s._get_ticker_override("GC=F", "enable_short", True) is False
    assert s._get_ticker_override("CL=F", "enable_short", True) is False
    assert s._get_ticker_override("MGC=F", "enable_short", True) is False
    assert s._get_ticker_override("MCL=F", "enable_short", True) is False


def test_t_per_ticker_unknown_ticker_default():
    """알 수 없는 ticker: default 반환."""
    s = _make_strategy()
    assert s._get_ticker_override("XYZ=F", "enable_short", True) is True
    assert s._get_ticker_override(None, "enable_short", True) is True


def test_t_per_ticker_other_keys_default_to_true():
    """enable_long/bear_trend_bypass/mean_reversion_bypass는 default True."""
    s = _make_strategy()
    for tk in ("ES=F", "NQ=F", "GC=F", "CL=F"):
        assert s._get_ticker_override(tk, "enable_long", True) is True
        assert s._get_ticker_override(tk, "enable_bear_trend_bypass", True) is True
        assert s._get_ticker_override(tk, "enable_mean_reversion_bypass", True) is True


def test_t_per_ticker_yaml_style_override():
    """YAML-style override 적용: dict 직접 주입."""
    cfg = ATSConfig()
    cfg.sp500_futures.per_ticker_overrides = {
        "ES=F": {"enable_short": False, "enable_bear_trend_bypass": False},
    }
    s = SP500FuturesStrategy(cfg)
    assert s._get_ticker_override("ES=F", "enable_short", True) is False
    assert s._get_ticker_override("ES=F", "enable_bear_trend_bypass", True) is False
    # NQ는 override 없음 → default
    assert s._get_ticker_override("NQ=F", "enable_short", True) is True


# ─────────────────────────── U tests ───────────────────────────


def test_u_regime_default_bull_neutral_short_threshold():
    """BULL/NEUTRAL: SHORT threshold adj -10 (J 기존 동작)."""
    s = _make_strategy()
    assert s._get_regime_mode("BULL", "short_threshold_adj", None) == -10.0
    assert s._get_regime_mode("NEUTRAL", "short_threshold_adj", None) == -10.0


def test_u_regime_bear_stronger_short_threshold():
    """BEAR: SHORT threshold adj -15 (U 신규, trend-SHORT 우선)."""
    s = _make_strategy()
    assert s._get_regime_mode("BEAR", "short_threshold_adj", None) == -15.0


def test_u_regime_crisis_no_short_threshold_adj():
    """CRISIS: SHORT threshold adj 0 (entry 자체가 차단되므로 무의미)."""
    s = _make_strategy()
    assert s._get_regime_mode("CRISIS", "short_threshold_adj", None) == 0.0


def test_u_regime_mr_short_bull_disabled():
    """P-3 paradox: BULL에서 MR-SHORT 차단."""
    s = _make_strategy()
    assert s._get_regime_mode("BULL", "mr_short", None) is False


def test_u_regime_mr_short_neutral_bear_enabled():
    """NEUTRAL/BEAR: MR-SHORT 활성."""
    s = _make_strategy()
    assert s._get_regime_mode("NEUTRAL", "mr_short", None) is True
    assert s._get_regime_mode("BEAR", "mr_short", None) is True


def test_u_regime_mr_short_crisis_disabled():
    """CRISIS: MR-SHORT 차단."""
    s = _make_strategy()
    assert s._get_regime_mode("CRISIS", "mr_short", None) is False


def test_u_regime_unknown_returns_default():
    """알 수 없는 regime: default 반환."""
    s = _make_strategy()
    assert s._get_regime_mode("UNKNOWN", "mr_short", "fallback") == "fallback"
    assert s._get_regime_mode(None, "mr_short", "fallback") == "fallback"


def test_u_regime_yaml_style_override():
    """YAML-style override: dict 직접 주입."""
    cfg = ATSConfig()
    cfg.sp500_futures.regime_strategy_modes = {
        "BULL": {"mr_short": True, "short_threshold_adj": -20.0},  # 비정상 설정
    }
    s = SP500FuturesStrategy(cfg)
    assert s._get_regime_mode("BULL", "mr_short", None) is True
    assert s._get_regime_mode("BULL", "short_threshold_adj", None) == -20.0
    # NEUTRAL은 override 없음 → default
    assert s._get_regime_mode("NEUTRAL", "mr_short", "fallback") == "fallback"


# ─────────────────────────── V tests ───────────────────────────


def test_v_long_only_mode_default_false():
    """V: long_only_mode default False (baseline은 SHORT 허용)."""
    cfg = ATSConfig()
    assert cfg.sp500_futures.long_only_mode is False


def test_v_long_only_mode_blocks_all_short():
    """V: long_only_mode=True면 모든 ticker SHORT 차단."""
    cfg = ATSConfig()
    cfg.sp500_futures.long_only_mode = True
    s = SP500FuturesStrategy(cfg)
    # 모든 ticker (override 유무 무관) enable_short=False
    for tk in ("ES=F", "NQ=F", "GC=F", "CL=F", "XYZ=F"):
        assert s._get_ticker_override(tk, "enable_short", True) is False, \
            f"{tk}: long_only_mode=True에서 enable_short=True 반환"


def test_v_long_only_mode_other_keys_unaffected():
    """V: long_only_mode는 enable_short만 강제 False. 다른 키는 영향 없음."""
    cfg = ATSConfig()
    cfg.sp500_futures.long_only_mode = True
    s = SP500FuturesStrategy(cfg)
    # enable_long, enable_bear_trend_bypass 등은 default 유지
    assert s._get_ticker_override("ES=F", "enable_long", True) is True
    assert s._get_ticker_override("ES=F", "enable_bear_trend_bypass", True) is True
    assert s._get_ticker_override("ES=F", "enable_mean_reversion_bypass", True) is True


def test_v_long_only_mode_off_respects_per_ticker():
    """V off + T per-ticker는 그대로 동작."""
    cfg = ATSConfig()
    cfg.sp500_futures.long_only_mode = False
    s = SP500FuturesStrategy(cfg)
    assert s._get_ticker_override("ES=F", "enable_short", True) is True
    assert s._get_ticker_override("GC=F", "enable_short", True) is False  # T default
    assert s._get_ticker_override("CL=F", "enable_short", True) is False  # T default
