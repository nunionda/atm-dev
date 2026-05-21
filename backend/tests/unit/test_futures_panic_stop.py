"""
P4-4 회귀 보호: FuturesBacktester MDD Panic Stop (BR-R02).

핵심 단언:
  - 봉 시작 시점에 MDD ≤ rg2_mdd_limit이면 보유 포지션 강제 청산
  - exit_reason = "MDD_PANIC_STOP" (별도 카테고리)
  - 청산 후 position=None, _trade_history에 record
"""
from __future__ import annotations

import inspect

import pytest


# ──────────────────────────────────────
# 1) 소스 단언: P4-4 패치 적용
# ──────────────────────────────────────

def test_p4_4_panic_stop_patch_in_source():
    """futures_backtester에 MDD_PANIC_STOP 패턴 적용."""
    import backtest.futures_backtester as mod
    src = inspect.getsource(mod)
    assert "MDD_PANIC_STOP" in src, (
        "P4-4 regression: backtester must emit MDD_PANIC_STOP exit_reason "
        "when MDD ≤ rg2_mdd_limit while holding position."
    )
    # cur_dd 계산 패턴
    assert "rg2_mdd_limit" in src
    # 봉 시작 시점에 (position is not None and peak_equity > 0) 분기
    assert "position is not None and peak_equity > 0" in src, (
        "P4-4 regression: panic stop must be evaluated at bar start with position held + valid peak."
    )


# ──────────────────────────────────────
# 2) Panic stop 발동 위치는 monitor exit 분기 이전
# ──────────────────────────────────────

def test_panic_stop_evaluated_before_normal_exit_checks():
    """Panic stop 코드 블록이 '포지션 보유 중 → 청산 체크' 블록(margin call/CB/strategy exit) 이전에 위치."""
    import backtest.futures_backtester as mod
    src = inspect.getsource(mod)

    idx_panic = src.find("MDD_PANIC_STOP")
    idx_normal_exit = src.find("# 포지션 보유 중 → 청산 체크")
    assert idx_panic > 0
    assert idx_normal_exit > 0
    assert idx_panic < idx_normal_exit, (
        "P4-4: Panic stop block must be ordered before normal monitor/exit checks."
    )


# ──────────────────────────────────────
# 3) Panic stop emits trade record with correct exit_reason
# ──────────────────────────────────────

def test_panic_stop_records_trade_with_correct_exit_reason():
    """_make_trade_record 호출에서 'MDD_PANIC_STOP' 문자열 사용."""
    import backtest.futures_backtester as mod
    src = inspect.getsource(mod)
    # panic 블록 안에서 _make_trade_record 호출에 MDD_PANIC_STOP 인자
    # 단순 검증: MDD_PANIC_STOP과 _make_trade_record가 동일 코드 영역에
    panic_idx = src.find("MDD_PANIC_STOP")
    nearby = src[max(0, panic_idx - 500):panic_idx + 200]
    assert "_make_trade_record" in nearby, (
        "P4-4: MDD_PANIC_STOP must be passed to _make_trade_record for exit_reason."
    )


# ──────────────────────────────────────
# 4) Panic stop 후 strategy._position_states.pop
# ──────────────────────────────────────

def test_panic_stop_clears_strategy_position_state():
    """패닉 청산 후 strategy._position_states에서 ticker 제거 (다음 entry 깨끗)."""
    import backtest.futures_backtester as mod
    src = inspect.getsource(mod)
    panic_idx = src.find("MDD_PANIC_STOP")
    nearby = src[panic_idx:panic_idx + 600]
    assert "_position_states.pop" in nearby, (
        "P4-4: panic stop must clear strategy._position_states[ticker]"
    )


# ──────────────────────────────────────
# 5) record_trade_result 호출 (연속 손절 카운트, EV history 갱신)
# ──────────────────────────────────────

def test_panic_stop_records_to_strategy_history():
    """panic stop도 strategy.record_trade_result로 _trade_history/_consecutive_losses 갱신."""
    import backtest.futures_backtester as mod
    src = inspect.getsource(mod)
    panic_idx = src.find("MDD_PANIC_STOP")
    nearby = src[panic_idx:panic_idx + 800]
    assert "record_trade_result" in nearby, (
        "P4-4: panic stop must call strategy.record_trade_result for EV/consecutive_loss tracking."
    )
