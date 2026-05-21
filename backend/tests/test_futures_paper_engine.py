"""
FuturesPaperEngine 라이프사이클 단위 테스트.

검증:
  - GO 시점 SL/TP lock-in
  - tick → SL/TP 자동 발화 (LONG/SHORT × SL/TP = 4가지)
  - close 시 ESFResultRecorder.record_result 호출
  - 동일 ticker 1-OPEN 강제
  - max_concurrent 3 강제
  - 방향 disagreement는 라우트 단에서 차단 (엔진 자체는 ValueError raise)
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from infra.db.connection import Database  # noqa: E402
from infra.db.models import ESFHypothesis  # noqa: E402
from simulation.futures_paper_engine import FuturesPaperEngine, CONTRACT_SPEC  # noqa: E402


@pytest.fixture
def db():
    database = Database(db_path=":memory:")
    database.init_tables()
    yield database
    database.close()


def _create_hypothesis(db: Database, hypothesis_id: int, ticker: str = "ES=F",
                       direction: str = "LONG", entry: float = 5000.0,
                       sl: float = 4990.0, tp: float = 5020.0) -> int:
    """FK 충족용 ESFHypothesis row 생성."""
    now = datetime.now().isoformat()
    with db.get_session() as s:
        h = ESFHypothesis(
            hypothesis_id=hypothesis_id,
            trade_date=datetime.now().strftime("%Y-%m-%d"),
            ticker=ticker,
            direction=direction,
            entry_price=entry,
            stop_loss=sl,
            take_profit=tp,
            total_score=60.0,
            grade="B",
            confidence=0.65,
            regime="NEUTRAL",
            reasoning_json="{}",
            status="ACTIVE",
            created_at=now,
            updated_at=now,
        )
        s.add(h)
        s.commit()
        return h.hypothesis_id


@pytest.fixture
def recorder():
    """ESFResultRecorder mock — record_result 호출 추적."""
    r = MagicMock()
    r.record_result = MagicMock(return_value={"result_id": 1})
    return r


@pytest.fixture
def published():
    """publish 콜백 호출 캡처."""
    calls = []

    def cb(event_type, data):
        calls.append((event_type, data))

    cb.calls = calls
    return cb


@pytest.fixture
def engine(db, recorder, published):
    return FuturesPaperEngine(
        database=db, recorder=recorder, publish=published, max_concurrent=3,
    )


# ─────────────────────────────────────────
# 1. SL/TP lock-in
# ─────────────────────────────────────────

def test_open_position_locks_sl_tp(engine, db):
    _create_hypothesis(db, 42)
    pos = engine.open_position(
        ticker="ES=F", direction="LONG",
        entry_price=5000.0, stop_loss=4990.0, take_profit=5020.0,
        contracts=1, hypothesis_id=42,
    )
    assert pos["status"] == "OPEN"
    assert pos["entry_price"] == 5000.0
    assert pos["stop_loss"] == 4990.0
    assert pos["take_profit"] == 5020.0
    assert pos["hypothesis_id"] == 42
    assert pos["contract_multiplier"] == CONTRACT_SPEC["ES=F"]["multiplier"]
    assert pos["tick_value"] == CONTRACT_SPEC["ES=F"]["tick_value"]


def test_open_position_validates_long_sl_tp_order(engine):
    """LONG: sl < entry < tp가 아니면 reject."""
    with pytest.raises(ValueError, match="LONG"):
        engine.open_position(
            ticker="ES=F", direction="LONG",
            entry_price=5000.0, stop_loss=5010.0,  # sl > entry
            take_profit=5020.0,
        )


def test_open_position_validates_short_sl_tp_order(engine):
    """SHORT: tp < entry < sl가 아니면 reject."""
    with pytest.raises(ValueError, match="SHORT"):
        engine.open_position(
            ticker="ES=F", direction="SHORT",
            entry_price=5000.0, stop_loss=5010.0,
            take_profit=5020.0,  # tp > entry
        )


def test_open_position_rejects_unsupported_ticker(engine):
    with pytest.raises(ValueError, match="Unsupported"):
        engine.open_position(
            ticker="AAPL", direction="LONG",
            entry_price=200.0, stop_loss=195.0, take_profit=210.0,
        )


# ─────────────────────────────────────────
# 2. Tick triggers SL/TP — 4 combinations
# ─────────────────────────────────────────

def test_tick_triggers_sl_long(engine, db, recorder):
    _create_hypothesis(db, 1)
    engine.open_position(
        ticker="ES=F", direction="LONG",
        entry_price=5000.0, stop_loss=4990.0, take_profit=5020.0,
        contracts=1, hypothesis_id=1,
    )
    # 가격이 SL 아래로 → SL_HIT
    closed = engine.tick("ES=F", 4985.0)
    assert len(closed) == 1
    pos = closed[0]
    assert pos["status"] == "CLOSED"
    assert pos["exit_reason"] == "SL"
    assert pos["exit_price"] == 4985.0
    recorder.record_result.assert_called_once()


def test_tick_triggers_tp_long(engine, db, recorder):
    _create_hypothesis(db, 2)
    engine.open_position(
        ticker="ES=F", direction="LONG",
        entry_price=5000.0, stop_loss=4990.0, take_profit=5020.0,
        contracts=1, hypothesis_id=2,
    )
    closed = engine.tick("ES=F", 5025.0)
    assert len(closed) == 1
    assert closed[0]["exit_reason"] == "TP"
    recorder.record_result.assert_called_once()


def test_tick_triggers_sl_short(engine, db, recorder):
    _create_hypothesis(db, 3, direction="SHORT", sl=5010.0, tp=4980.0)
    engine.open_position(
        ticker="ES=F", direction="SHORT",
        entry_price=5000.0, stop_loss=5010.0, take_profit=4980.0,
        contracts=1, hypothesis_id=3,
    )
    # SHORT의 SL은 entry 위 → 가격 상승 시 hit
    closed = engine.tick("ES=F", 5015.0)
    assert len(closed) == 1
    assert closed[0]["exit_reason"] == "SL"


def test_tick_triggers_tp_short(engine, db, recorder):
    _create_hypothesis(db, 4, direction="SHORT", sl=5010.0, tp=4980.0)
    engine.open_position(
        ticker="ES=F", direction="SHORT",
        entry_price=5000.0, stop_loss=5010.0, take_profit=4980.0,
        contracts=1, hypothesis_id=4,
    )
    closed = engine.tick("ES=F", 4975.0)
    assert len(closed) == 1
    assert closed[0]["exit_reason"] == "TP"


def test_tick_in_range_no_close(engine, db, recorder):
    _create_hypothesis(db, 5)
    engine.open_position(
        ticker="ES=F", direction="LONG",
        entry_price=5000.0, stop_loss=4990.0, take_profit=5020.0,
        contracts=1, hypothesis_id=5,
    )
    closed = engine.tick("ES=F", 5005.0)  # SL/TP 사이
    assert closed == []
    recorder.record_result.assert_not_called()
    # last_price 갱신만
    open_pos = engine.list_open()[0]
    assert open_pos["last_price"] == 5005.0


# ─────────────────────────────────────────
# 3. close_position → journal 자동 호출
# ─────────────────────────────────────────

def test_close_records_journal_result(engine, db, recorder):
    _create_hypothesis(db, 99)
    pos = engine.open_position(
        ticker="ES=F", direction="LONG",
        entry_price=5000.0, stop_loss=4990.0, take_profit=5020.0,
        contracts=2, hypothesis_id=99,
    )
    final = engine.close_position(pos["position_id"], price=5008.0, reason="MANUAL")
    assert final["status"] == "CLOSED"
    assert final["exit_reason"] == "MANUAL"
    recorder.record_result.assert_called_once()
    args, kwargs = recorder.record_result.call_args
    assert kwargs["hypothesis_id"] == 99
    assert kwargs["result_data"]["actual_entry_price"] == 5000.0
    assert kwargs["result_data"]["actual_exit_price"] == 5008.0
    assert kwargs["result_data"]["contracts"] == 2
    assert kwargs["result_data"]["exit_reason"] == "MANUAL"


def test_close_no_hypothesis_skips_journal(engine, recorder):
    """hypothesis_id 없으면 journaling 호출하지 않음."""
    pos = engine.open_position(
        ticker="ES=F", direction="LONG",
        entry_price=5000.0, stop_loss=4990.0, take_profit=5020.0,
        hypothesis_id=None,
    )
    engine.close_position(pos["position_id"], price=5008.0, reason="MANUAL")
    recorder.record_result.assert_not_called()


# ─────────────────────────────────────────
# 4. 1-OPEN per ticker
# ─────────────────────────────────────────

def test_one_open_per_ticker_enforced(engine, db):
    _create_hypothesis(db, 1)
    _create_hypothesis(db, 2)
    engine.open_position(
        ticker="ES=F", direction="LONG",
        entry_price=5000.0, stop_loss=4990.0, take_profit=5020.0,
        hypothesis_id=1,
    )
    with pytest.raises(ValueError, match="already exists"):
        engine.open_position(
            ticker="ES=F", direction="LONG",
            entry_price=5100.0, stop_loss=5090.0, take_profit=5120.0,
            hypothesis_id=2,
        )


def test_can_reopen_same_ticker_after_close(engine, db):
    _create_hypothesis(db, 1)
    _create_hypothesis(db, 2, direction="SHORT", sl=5110.0, tp=5080.0)
    pos = engine.open_position(
        ticker="ES=F", direction="LONG",
        entry_price=5000.0, stop_loss=4990.0, take_profit=5020.0,
        hypothesis_id=1,
    )
    engine.close_position(pos["position_id"], price=5008.0)
    # 청산 후 동일 ticker 재진입 가능
    new_pos = engine.open_position(
        ticker="ES=F", direction="SHORT",
        entry_price=5100.0, stop_loss=5110.0, take_profit=5080.0,
        hypothesis_id=2,
    )
    assert new_pos["status"] == "OPEN"


# ─────────────────────────────────────────
# 5. max_concurrent 3
# ─────────────────────────────────────────

def test_max_concurrent_3(engine, db):
    for hid in (1, 2, 3, 4):
        _create_hypothesis(db, hid)
    engine.open_position(
        ticker="ES=F", direction="LONG",
        entry_price=5000.0, stop_loss=4990.0, take_profit=5020.0, hypothesis_id=1,
    )
    engine.open_position(
        ticker="MES=F", direction="LONG",
        entry_price=5000.0, stop_loss=4990.0, take_profit=5020.0, hypothesis_id=2,
    )
    engine.open_position(
        ticker="NQ=F", direction="LONG",
        entry_price=17000.0, stop_loss=16950.0, take_profit=17100.0, hypothesis_id=3,
    )
    # 4번째는 거부
    with pytest.raises(ValueError, match="Max concurrent"):
        engine.open_position(
            ticker="MNQ=F", direction="LONG",
            entry_price=17000.0, stop_loss=16950.0, take_profit=17100.0, hypothesis_id=4,
        )


# ─────────────────────────────────────────
# 6. publish 콜백 호출
# ─────────────────────────────────────────

def test_publish_called_on_open_and_close(engine, db, published):
    _create_hypothesis(db, 1)
    pos = engine.open_position(
        ticker="ES=F", direction="LONG",
        entry_price=5000.0, stop_loss=4990.0, take_profit=5020.0, hypothesis_id=1,
    )
    assert any(c[0] == "paper_position_opened" for c in published.calls)

    engine.close_position(pos["position_id"], price=5008.0)
    assert any(c[0] == "paper_position_closed" for c in published.calls)


# ─────────────────────────────────────────
# 7. get_open_tickers / realized_pnl_today
# ─────────────────────────────────────────

def test_get_open_tickers(engine, db):
    _create_hypothesis(db, 1)
    _create_hypothesis(db, 2, ticker="NQ=F", direction="SHORT", entry=17000.0, sl=17050.0, tp=16900.0)
    engine.open_position(
        ticker="ES=F", direction="LONG",
        entry_price=5000.0, stop_loss=4990.0, take_profit=5020.0, hypothesis_id=1,
    )
    engine.open_position(
        ticker="NQ=F", direction="SHORT",
        entry_price=17000.0, stop_loss=17050.0, take_profit=16900.0, hypothesis_id=2,
    )
    assert engine.get_open_tickers() == {"ES=F", "NQ=F"}


def test_realized_pnl_today(engine, db):
    _create_hypothesis(db, 1)
    pos1 = engine.open_position(
        ticker="ES=F", direction="LONG",
        entry_price=5000.0, stop_loss=4990.0, take_profit=5020.0, contracts=1, hypothesis_id=1,
    )
    # TP hit at tick price 5025 → +$1250 (25pt × 50 × 1)
    engine.tick("ES=F", 5025.0)
    pnl = engine.realized_pnl_today()
    assert pnl == pytest.approx(1250.0, abs=0.01)
