"""
Phase A/B 단위 테스트 — RebalanceSyncJob + ExitGuard.

검증 시나리오 (plan §검증):
  1. test_replace_active_universe_atomic — 5 active + sync 3 → 정확히 3 active
  2. test_exit_guard_protects_winner_es2 — HOLD + return_6m>=th → True; ES1은 False
  3. test_union_includes_current_positions — top_n에 없는 보유 종목 union 포함
  4. test_min_universe_size_guard_rejects_empty_sync — 빈 결과 → rejected + log
"""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

from core.rebalance_sync import RebalanceSyncJob
from infra.db.models import Universe
from risk.exit_guard import ExitGuard


# ──────────────────────────────────────────────
# 헬퍼: Universe row 미리 채우기
# ──────────────────────────────────────────────

def _seed_universe(repo, codes_market_pairs):
    """[(code, market)] → universe 테이블 초기 active row 생성."""
    now = datetime.now().isoformat()
    with repo._session() as s:
        for code, market in codes_market_pairs:
            s.add(Universe(
                stock_code=code,
                stock_name=f"Name_{code}",
                market=market,
                is_active=1,
                updated_at=now,
            ))
        s.commit()


def _scanner_result(buy: list[dict], hold: list[dict]) -> dict:
    return {
        "buy": buy, "hold": hold, "sell": [],
        "all_scores": {},
        "scan_date": "2026-05-21",
        "total_scanned": 100,
        "passed_prefilter": 30,
    }


# ──────────────────────────────────────────────
# Test 1: replace_active_universe 원자성
# ──────────────────────────────────────────────

def test_replace_active_universe_atomic(repository):
    """5개 active 상태에서 3개로 sync → 5 deactivated, 3 activated, 최종 3 active."""
    _seed_universe(repository, [
        ("AAA", "sp500"), ("BBB", "sp500"), ("CCC", "sp500"),
        ("DDD", "sp500"), ("EEE", "sp500"),
    ])

    codes_meta = [
        {"stock_code": "AAA", "stock_name": "AAA Co", "rebalance_action": "HOLD",
         "rebalance_score": 90.0, "rebalance_rank": 1, "return_6m": 1.5},
        {"stock_code": "XXX", "stock_name": "XXX Co", "rebalance_action": "BUY",
         "rebalance_score": 85.0, "rebalance_rank": 2, "return_6m": 0.8},
        {"stock_code": "YYY", "stock_name": "YYY Co", "rebalance_action": "BUY",
         "rebalance_score": 80.0, "rebalance_rank": 3, "return_6m": 0.6},
    ]
    res = repository.replace_active_universe("sp500", codes_meta)

    assert res["deactivated"] == 5
    assert res["activated"] == 3

    active = repository.get_active_universe(market="sp500")
    assert {u.stock_code for u in active} == {"AAA", "XXX", "YYY"}

    meta = repository.get_universe_meta("XXX")
    assert meta["rebalance_action"] == "BUY"
    assert meta["return_6m"] == 0.8
    assert meta["last_synced_at"] is not None


# ──────────────────────────────────────────────
# Test 2: ExitGuard 보호 판정
# ──────────────────────────────────────────────

def test_exit_guard_protects_winner_es2(repository):
    """HOLD + return_6m>=th → ES2 보호. ES1(-10%)은 보호 우회 (별도 평가)."""
    repository.replace_active_universe("sp500", [
        {"stock_code": "AAPL", "stock_name": "Apple", "rebalance_action": "HOLD",
         "rebalance_score": 88.0, "rebalance_rank": 1, "return_6m": 0.40},
        {"stock_code": "FOO", "stock_name": "Foo Inc", "rebalance_action": "KEEP",
         "rebalance_score": None, "rebalance_rank": None, "return_6m": None},
    ])
    guard = ExitGuard(repository, protect_min_return_6m=0.0, protect_min_score=0.0)

    # HOLD 종목 → protected
    pos_apple = SimpleNamespace(stock_code="AAPL", stock_name="Apple")
    protected, reason = guard.is_es2_protected(pos_apple, market="sp500")
    assert protected is True

    # KEEP 종목 → not protected (BUY/HOLD만 보호)
    pos_foo = SimpleNamespace(stock_code="FOO", stock_name="Foo Inc")
    protected_foo, _ = guard.is_es2_protected(pos_foo, market="sp500")
    assert protected_foo is False

    # 미등록 종목 → not protected
    pos_unknown = SimpleNamespace(stock_code="NONE", stock_name="NONE")
    protected_u, _ = guard.is_es2_protected(pos_unknown, market="sp500")
    assert protected_u is False


def test_exit_guard_threshold_filters(repository):
    """protect_min_return_6m threshold 미달 시 보호 안 함."""
    repository.replace_active_universe("sp500", [
        {"stock_code": "LOW", "stock_name": "Low Returner", "rebalance_action": "BUY",
         "rebalance_score": 70.0, "rebalance_rank": 1, "return_6m": 0.05},
    ])
    guard = ExitGuard(repository, protect_min_return_6m=0.10, protect_min_score=0.0)

    pos = SimpleNamespace(stock_code="LOW", stock_name="Low Returner")
    protected, _ = guard.is_es2_protected(pos, market="sp500")
    assert protected is False  # 5% < 10% threshold


# ──────────────────────────────────────────────
# Test 3: 합집합 정책 — 현 보유는 항상 포함
# ──────────────────────────────────────────────

def test_union_includes_current_positions(repository):
    """top_n에 없는 보유 종목 NVDA가 sync 결과 union에 포함된다 (KEEP action)."""
    job = RebalanceSyncJob(repository, top_n=2, min_universe_size=1)

    # scanner는 BUY top 2만 제공
    scanner_result = _scanner_result(
        buy=[
            {"code": "AAA", "name": "AAA", "score": 90, "return_6m_raw": 1.5, "rank": 1},
            {"code": "BBB", "name": "BBB", "score": 85, "return_6m_raw": 0.8, "rank": 2},
        ],
        hold=[],
    )

    # 현재 보유 중인 NVDA는 BUY/HOLD에 없음
    active_positions = {
        "NVDA": SimpleNamespace(stock_code="NVDA", stock_name="NVIDIA", status="ACTIVE"),
    }

    result = job.run(
        market="sp500", trigger="MANUAL", commit=True,
        scanner_result=scanner_result, active_positions=active_positions,
    )

    assert result.committed is True
    assert "NVDA" in result.target_codes  # KEEP으로 union 포함
    assert "AAA" in result.target_codes
    assert "BBB" in result.target_codes
    assert result.buy_count == 2
    assert result.kept_count == 1  # NVDA가 KEEP


# ──────────────────────────────────────────────
# Test 4: min_universe_size guard
# ──────────────────────────────────────────────

def test_min_universe_size_guard_rejects(repository):
    """프리필터를 통과한 종목이 min 미만이면 sync 거부 + log 기록."""
    job = RebalanceSyncJob(repository, top_n=10, min_universe_size=5)

    scanner_result = _scanner_result(
        buy=[
            {"code": "AAA", "name": "AAA", "score": 90, "return_6m_raw": 1.5, "rank": 1},
            {"code": "BBB", "name": "BBB", "score": 85, "return_6m_raw": 0.8, "rank": 2},
        ],
        hold=[],
    )
    # active_positions도 비어 있음 → union 크기 2 < min 5

    result = job.run(
        market="sp500", trigger="MANUAL", commit=True,
        scanner_result=scanner_result, active_positions={},
    )

    assert result.rejected is True
    assert result.committed is False
    assert "min" in (result.reject_reason or "").lower()

    # 거부된 sync도 로그는 남음
    latest = repository.get_latest_rebalance_sync("sp500")
    assert latest is not None
    assert latest["total_active"] == 2

    # DB universe는 변경되지 않음 (deactivate 안 일어남)
    active = repository.get_active_universe(market="sp500")
    assert len(active) == 0  # 초기 상태와 동일 (시드 안 함)


# ──────────────────────────────────────────────
# Test 5: dry-run (commit=False) → DB 변경 없음
# ──────────────────────────────────────────────

def test_multi_market_same_ticker_no_conflict(repository):
    """SP500과 NDX가 같은 ticker(MU/AMD)를 BUY로 가져도 양쪽 모두 active 유지 (BUG-1 회귀)."""
    # SP500 sync: AAA, MU, AMD
    repository.replace_active_universe("sp500", [
        {"stock_code": "AAA", "stock_name": "AAA", "rebalance_action": "BUY",
         "rebalance_score": 90, "rebalance_rank": 1, "return_6m": 1.0},
        {"stock_code": "MU", "stock_name": "Micron", "rebalance_action": "BUY",
         "rebalance_score": 88, "rebalance_rank": 2, "return_6m": 1.2},
        {"stock_code": "AMD", "stock_name": "AMD", "rebalance_action": "BUY",
         "rebalance_score": 85, "rebalance_rank": 3, "return_6m": 0.9},
    ])
    # NDX sync: BBB, MU, AMD (같은 ticker 2개)
    repository.replace_active_universe("ndx", [
        {"stock_code": "BBB", "stock_name": "BBB", "rebalance_action": "BUY",
         "rebalance_score": 92, "rebalance_rank": 1, "return_6m": 1.5},
        {"stock_code": "MU", "stock_name": "Micron", "rebalance_action": "BUY",
         "rebalance_score": 88, "rebalance_rank": 2, "return_6m": 1.2},
        {"stock_code": "AMD", "stock_name": "AMD", "rebalance_action": "BUY",
         "rebalance_score": 85, "rebalance_rank": 3, "return_6m": 0.9},
    ])

    sp500_active = {u.stock_code for u in repository.get_active_universe(market="sp500")}
    ndx_active = {u.stock_code for u in repository.get_active_universe(market="ndx")}

    assert sp500_active == {"AAA", "MU", "AMD"}, f"SP500 lost tickers: {sp500_active}"
    assert ndx_active == {"BBB", "MU", "AMD"}, f"NDX missing tickers: {ndx_active}"

    # (stock_code, market) 페어로 메타 조회
    meta_mu_sp = repository.get_universe_meta("MU", market="sp500")
    meta_mu_ndx = repository.get_universe_meta("MU", market="ndx")
    assert meta_mu_sp is not None
    assert meta_mu_ndx is not None
    assert meta_mu_sp["market"] == "sp500"
    assert meta_mu_ndx["market"] == "ndx"


def test_dry_run_does_not_commit(repository):
    """commit=False면 result는 계산되지만 DB는 변하지 않는다."""
    _seed_universe(repository, [("OLD", "sp500")])

    job = RebalanceSyncJob(repository, top_n=2, min_universe_size=1)
    scanner_result = _scanner_result(
        buy=[
            {"code": "AAA", "name": "AAA", "score": 90, "return_6m_raw": 1.5, "rank": 1},
        ],
        hold=[],
    )
    result = job.run(
        market="sp500", trigger="MANUAL", commit=False,
        scanner_result=scanner_result, active_positions={},
    )

    assert result.committed is False
    assert result.rejected is False
    assert "AAA" in result.target_codes

    # 기존 OLD는 그대로 active
    active = repository.get_active_universe(market="sp500")
    assert {u.stock_code for u in active} == {"OLD"}

    # log도 dry-run에서는 안 남음
    assert repository.get_latest_rebalance_sync("sp500") is None
