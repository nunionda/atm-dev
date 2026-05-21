"""
P1-3 회귀 보호: SP500 Futures EV Engine warmup.

핵심 단언:
  - ev_min_trades 5 → 30 (충분한 표본)
  - ev_warmup_block_entries (default False) 옵션 도입
  - _check_ev_gate 4가지 분기 동작 정확성
"""
from __future__ import annotations

import pytest

from data.config_manager import ATSConfig, SP500FuturesConfig
from strategy.sp500_futures import SP500FuturesStrategy


def _make_strategy(**fc_overrides) -> SP500FuturesStrategy:
    fc = SP500FuturesConfig(**fc_overrides) if fc_overrides else SP500FuturesConfig()
    cfg = ATSConfig(sp500_futures=fc)
    return SP500FuturesStrategy(cfg)


# ──────────────────────────────────────
# 1) Config 디폴트 변경 검증
# ──────────────────────────────────────

def test_ev_min_trades_raised_to_30():
    """P1-3: ev_min_trades 5 → 30 (충분한 표본 확보)."""
    fc = SP500FuturesConfig()
    assert fc.ev_min_trades == 30


def test_ev_warmup_block_entries_defaults_false():
    """P1-3: warmup_block 디폴트 OFF (backward compat — 백테스터가 표본 채울 수 있음)."""
    fc = SP500FuturesConfig()
    assert fc.ev_warmup_block_entries is False


# ──────────────────────────────────────
# 2) _check_ev_gate 4가지 분기
# ──────────────────────────────────────

def test_ev_gate_warmup_passes_when_block_disabled():
    """표본 부족 + warmup_block=False → 통과 (백테스터 호환)."""
    strat = _make_strategy(ev_warmup_block_entries=False)
    strat._trade_history = [0.01, -0.005]  # 2 trades < 30
    assert strat._check_ev_gate() is True


def test_ev_gate_warmup_blocks_when_enabled():
    """표본 부족 + warmup_block=True → 차단 (라이브 안전)."""
    strat = _make_strategy(ev_warmup_block_entries=True)
    strat._trade_history = [0.01, -0.005] * 10  # 20 trades < 30
    assert strat._check_ev_gate() is False


def test_ev_gate_passes_when_ev_positive():
    """표본 충분 + EV > 0 → 통과."""
    strat = _make_strategy()
    # 30 trades, 20 wins (+1%), 10 losses (-0.5%) → EV = 2/3 × 0.01 - 1/3 × 0.005 ≈ 0.0050 > 0
    strat._trade_history = [0.01] * 20 + [-0.005] * 10
    assert strat._check_ev_gate() is True


def test_ev_gate_blocks_when_ev_non_positive():
    """표본 충분 + EV ≤ 0 → 차단."""
    strat = _make_strategy()
    # 30 trades, 10 wins (+0.5%), 20 losses (-1%) → EV = 1/3 × 0.005 - 2/3 × 0.01 < 0
    strat._trade_history = [0.005] * 10 + [-0.01] * 20
    assert strat._check_ev_gate() is False


def test_ev_gate_passes_at_exact_min_trades_threshold():
    """표본이 정확히 ev_min_trades(30) 이상이면 EV 평가, 미만이면 warmup 분기."""
    # 정확히 30 trades, 양수 EV
    strat = _make_strategy()
    strat._trade_history = [0.01] * 20 + [-0.005] * 10  # 30개, EV+
    assert strat._check_ev_gate() is True

    # 29 trades → warmup (block=False면 통과)
    strat._trade_history = strat._trade_history[:29]
    assert len(strat._trade_history) == 29
    assert strat._check_ev_gate() is True  # warmup_block=False default

    # warmup_block=True면 29 trades에서 차단
    strat2 = _make_strategy(ev_warmup_block_entries=True)
    strat2._trade_history = [0.01] * 29
    assert strat2._check_ev_gate() is False


# ──────────────────────────────────────
# 3) YAML override 검증
# ──────────────────────────────────────

def test_p1_3_yaml_override(tmp_path):
    """config.yaml에서 두 필드 override 가능."""
    from data.config_manager import ConfigManager

    yaml_file = tmp_path / "config.yaml"
    yaml_file.write_text("""
sp500_futures:
  ev_min_trades: 50
  ev_warmup_block_entries: true
""")
    cm = ConfigManager(
        config_path=str(yaml_file),
        env_path=str(tmp_path / ".env"),
    )
    config = cm.load()
    assert config.sp500_futures.ev_min_trades == 50
    assert config.sp500_futures.ev_warmup_block_entries is True
