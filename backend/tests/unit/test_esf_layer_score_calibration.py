"""
P4-1 회귀 보호: ESF Layer score 보정.

핵심 단언:
  - L1 AMT BALANCE 시 boost: amt_max * 0.7 (이전: amt_max / 2)
  - regime_neutral_threshold = 40 (이전: 45)
  - regime_bear_threshold = 40 (이전: 45)
  - grade_c_threshold = 20 (이전: 25)
"""
from __future__ import annotations

import inspect

import pytest

from data.config_manager import ESFIntradayConfig


# ──────────────────────────────────────
# 1) Config 디폴트 갱신
# ──────────────────────────────────────

def test_p4_1_grade_c_threshold_20():
    """grade_c_threshold 25 → 20 (P4-1)."""
    fc = ESFIntradayConfig()
    assert fc.grade_c_threshold == 20.0


def test_p4_1_neutral_threshold_40():
    """NEUTRAL/BEAR regime threshold 45 → 40 (P4-1)."""
    fc = ESFIntradayConfig()
    assert fc.regime_neutral_threshold == 40.0
    assert fc.regime_bear_threshold == 40.0


def test_p4_1_bull_threshold_preserved():
    """BULL threshold는 P1-2 값 55 그대로."""
    fc = ESFIntradayConfig()
    assert fc.regime_bull_threshold == 55.0


# ──────────────────────────────────────
# 2) L1 AMT BALANCE boost 패치
# ──────────────────────────────────────

def test_p4_1_amt_balance_boost_applied():
    """_score_amt_location 함수 안 BALANCE 분기에 amt_max * 0.7 적용."""
    import strategy.esf_intraday as mod
    src = inspect.getsource(mod.ESFIntradayStrategy._score_amt_location)
    assert "amt_max * 0.7" in src, (
        "P4-1 regression: BALANCE 시 score boost (amt_max * 0.7) 필요"
    )
    # 이전 패턴 (amt_max / 2)이 BALANCE 분기에서 제거됐는지
    # 단순히 "amt_max / 2" 가 코드에 없는지 (다른 곳에서 사용 가능성 낮음)
    assert "amt_max / 2" not in src, (
        "P4-1 regression: 구 패턴 amt_max / 2 제거 (boost로 대체됨)"
    )


# ──────────────────────────────────────
# 3) YAML override 가능
# ──────────────────────────────────────

def test_p4_1_yaml_override(tmp_path):
    from data.config_manager import ConfigManager

    yaml_file = tmp_path / "config.yaml"
    yaml_file.write_text("""
esf_intraday:
  grade_c_threshold: 30
  regime_neutral_threshold: 50
""")
    cm = ConfigManager(
        config_path=str(yaml_file),
        env_path=str(tmp_path / ".env"),
    )
    config = cm.load()
    assert config.esf_intraday.grade_c_threshold == 30.0
    assert config.esf_intraday.regime_neutral_threshold == 50.0
