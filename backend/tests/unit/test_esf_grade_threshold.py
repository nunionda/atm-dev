"""
P1-2 회귀 보호: ESF Grade Threshold Regime 차등화.

핵심 단언:
  regime_bull / regime_neutral / regime_bear threshold가 서로 다른 값으로 분화돼야 한다.
  + grade_c_threshold가 25로 낮춰져 score 25+ 봉이 grade C로 entry 가능해야 한다.

배경:
  직전 60일 ES=F intraday 백테스트는 시장이 모두 NEUTRAL regime이라 trade 수 변화 없음.
  본 fix는 다른 regime(BULL/BEAR)에서 동작 정확성을 보장하기 위한 회귀 보호 + grade B/A 등급 차이 확인.
  진입 빈도 자체 회복은 _determine_direction 로직 (P3 영역).
"""
from __future__ import annotations

import pytest

from data.config_manager import ESFIntradayConfig


def test_p1_2_thresholds_differentiated_by_regime():
    """regime별 threshold가 서로 다른 값으로 분리돼야 한다."""
    # P4-1로 NEUTRAL/BEAR 45→40, grade_c 25→20 추가 완화
    fc = ESFIntradayConfig()
    assert fc.regime_bull_threshold == 55.0, "BULL은 보수적 (55)"
    assert fc.regime_neutral_threshold == 40.0, "NEUTRAL: P4-1로 40"
    assert fc.regime_bear_threshold == 40.0, "BEAR: P4-1로 40"
    assert fc.regime_bull_threshold != fc.regime_neutral_threshold


def test_p1_2_grade_c_threshold_lowered():
    """grade_c_threshold (P4-1로 20까지 추가 완화)."""
    fc = ESFIntradayConfig()
    assert fc.grade_c_threshold == 20.0, "P4-1: grade_c 25→20"
    assert fc.grade_b_threshold == 40.0  # 직접 사용 안 됨


def test_p1_2_grade_assignment_logic():
    """
    Grade 등급 계산 정확성 (esf_intraday.py 로직 모방):
      grade_a_thr = regime별 threshold (P4-1 후: 55/40/40)
      grade_b_thr = grade_a_thr - 10
      grade_c_thr = max(grade_a_thr - 20, fc.grade_c_threshold=20)
    """
    fc = ESFIntradayConfig()

    # BULL: A=55, B=45, C=max(35, 20)=35
    grade_a = fc.regime_bull_threshold
    grade_b = grade_a - 10.0
    grade_c = max(grade_a - 20.0, fc.grade_c_threshold)
    assert grade_a == 55.0 and grade_b == 45.0 and grade_c == 35.0

    # NEUTRAL: A=40, B=30, C=max(20, 20)=20
    grade_a = fc.regime_neutral_threshold
    grade_b = grade_a - 10.0
    grade_c = max(grade_a - 20.0, fc.grade_c_threshold)
    assert grade_a == 40.0 and grade_b == 30.0 and grade_c == 20.0

    # BEAR: A=40, B=30, C=20 (NEUTRAL과 동일)
    grade_a = fc.regime_bear_threshold
    assert grade_a == 40.0


def test_p1_2_yaml_override_respected(tmp_path):
    """config.yaml에서 esf_intraday threshold override 가능해야 한다."""
    from data.config_manager import ConfigManager

    yaml_file = tmp_path / "config.yaml"
    yaml_file.write_text("""
esf_intraday:
  regime_bull_threshold: 60
  regime_neutral_threshold: 40
  regime_bear_threshold: 40
  grade_c_threshold: 20
""")
    cm = ConfigManager(
        config_path=str(yaml_file),
        env_path=str(tmp_path / ".env"),
    )
    config = cm.load()
    assert config.esf_intraday.regime_bull_threshold == 60.0
    assert config.esf_intraday.regime_neutral_threshold == 40.0
    assert config.esf_intraday.regime_bear_threshold == 40.0
    assert config.esf_intraday.grade_c_threshold == 20.0
