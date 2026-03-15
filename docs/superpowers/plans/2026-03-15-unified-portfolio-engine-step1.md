# Unified Portfolio Engine — Step 1: RebalanceManager 내장

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** SimulationEngine에 RebalanceManager를 내장하여 엔진 자체에서 리밸런싱을 수행하게 한다.

**Architecture:** `_check_rebalance_sync()` 메서드를 SimulationEngine에 추가하고, `run_backtest_day()` 내에서 regime 업데이트 후 entry 스캔 전에 호출한다. HistoricalBacktester의 리밸런싱 오케스트레이션을 제거하고, 전체 유니버스 OHLCV를 `set_full_universe_ohlcv()`로 엔진에 주입한다.

**Tech Stack:** Python 3.11+, pytest, pandas

**Spec:** `docs/superpowers/specs/2026-03-15-unified-portfolio-engine-design.md` (섹션 3.2, 4.1-4.5, 7, 8.1)

**Regression Target:** 2-year backtest (2024-01 ~ 2026-02, SP500 110-stock) → Sharpe 1.18, Return +28.4%, ±0.1%

**Spec 3.2 참고**: `universe_config` constructor 파라미터는 이 Step에서는 구현하지 않는다. 대신 `init_rebalance_manager()` 메서드로 post-construction 초기화한다. constructor 통합은 Step 3 (얇은 래퍼 리팩터)에서 수행.

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `ats/simulation/engine.py` | `_check_rebalance_sync()`, `_apply_rebalance()`, `set_full_universe_ohlcv()`, constructor 확장 |
| Modify | `ats/backtest/rebalancer.py` | `reset_counter()`, `apply_scan_result()` 메서드 추가 |
| Modify | `ats/backtest/historical_engine.py` | 리밸런싱 오케스트레이션 제거, `set_full_universe_ohlcv()` 호출 추가 |
| Create | `ats/tests/test_rebalance_integration.py` | 리밸런싱 내장 통합 테스트 |

---

## Chunk 1: RebalanceManager 메서드 추가 + 단위 테스트

### Task 1: RebalanceManager에 reset_counter() 추가

**Files:**
- Modify: `ats/backtest/rebalancer.py:125-127` (tick 메서드 뒤)
- Test: `ats/tests/test_rebalance_integration.py`

- [ ] **Step 1: 테스트 파일 생성 + reset_counter 테스트 작성**

```python
# ats/tests/test_rebalance_integration.py
"""리밸런싱 내장 통합 테스트."""
import pytest
from unittest.mock import MagicMock
from backtest.rebalancer import RebalanceManager, RebalanceEvent


class TestRebalanceManagerExtensions:
    """RebalanceManager 신규 메서드 테스트."""

    @pytest.fixture
    def scanner_mock(self):
        scanner = MagicMock()
        scanner.scan.return_value = [
            {"code": "AAPL", "ticker": "AAPL", "name": "Apple", "sector": "Tech"},
            {"code": "MSFT", "ticker": "MSFT", "name": "Microsoft", "sector": "Tech"},
        ]
        return scanner

    @pytest.fixture
    def mgr(self, scanner_mock):
        return RebalanceManager(scanner=scanner_mock, rebalance_interval=14)

    def test_reset_counter_sets_zero(self, mgr):
        """reset_counter()는 _trading_day_count를 0으로 리셋한다."""
        # 며칠 tick
        for _ in range(10):
            mgr.tick()
        assert mgr._trading_day_count == 10

        mgr.reset_counter()
        assert mgr._trading_day_count == 0

    def test_reset_counter_prevents_immediate_rebalance(self, mgr):
        """reset 후 should_rebalance()는 False (초기화 이후)."""
        # 초기화 시킴
        mgr._is_initialized = True
        mgr._trading_day_count = 14
        assert mgr.should_rebalance() is True

        mgr.reset_counter()
        assert mgr.should_rebalance() is False
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

Run: `cd /Users/daniel/dev/atm-dev && python -m pytest ats/tests/test_rebalance_integration.py::TestRebalanceManagerExtensions::test_reset_counter_sets_zero -v`
Expected: FAIL — `AttributeError: 'RebalanceManager' object has no attribute 'reset_counter'`

- [ ] **Step 3: reset_counter() 구현**

`ats/backtest/rebalancer.py` — `tick()` 메서드(line 125-127) 뒤에 추가:

```python
def reset_counter(self):
    """거부 시 카운터 리셋 — 다음 주기까지 대기."""
    self._trading_day_count = 0
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

Run: `cd /Users/daniel/dev/atm-dev && python -m pytest ats/tests/test_rebalance_integration.py::TestRebalanceManagerExtensions -v`
Expected: 2 PASSED

- [ ] **Step 5: 커밋**

```bash
cd /Users/daniel/dev/atm-dev
git add ats/backtest/rebalancer.py ats/tests/test_rebalance_integration.py
git commit -m "feat: RebalanceManager.reset_counter() 추가"
```

---

### Task 2: RebalanceManager에 apply_scan_result() 추가

**Files:**
- Modify: `ats/backtest/rebalancer.py` (reset_counter 뒤)
- Test: `ats/tests/test_rebalance_integration.py`

- [ ] **Step 1: apply_scan_result 테스트 작성**

`ats/tests/test_rebalance_integration.py` 에 추가:

```python
    def test_apply_scan_result_returns_event(self, mgr):
        """apply_scan_result()는 RebalanceEvent를 반환한다."""
        # 초기 워치리스트 설정
        mgr._current_watchlist = [
            {"code": "AAPL", "ticker": "AAPL", "name": "Apple", "sector": "Tech"},
            {"code": "INTC", "ticker": "INTC", "name": "Intel", "sector": "Tech"},
        ]
        mgr._current_watchlist_codes = {"AAPL", "INTC"}
        mgr._is_initialized = True

        # 새 스캔 결과: INTC 퇴출, MSFT 추가
        scan_result = [
            {"code": "AAPL", "ticker": "AAPL", "name": "Apple", "sector": "Tech"},
            {"code": "MSFT", "ticker": "MSFT", "name": "Microsoft", "sector": "Tech"},
        ]
        active_positions = {"INTC": MagicMock()}  # INTC에 포지션 보유 중

        event = mgr.apply_scan_result(scan_result, active_positions)

        assert isinstance(event, RebalanceEvent)
        assert "MSFT" in event.stocks_added
        assert "INTC" in event.stocks_removed
        assert "INTC" in event.positions_force_exited
        assert event.new_watchlist == scan_result

    def test_apply_scan_result_updates_state(self, mgr):
        """apply_scan_result()는 내부 상태를 업데이트한다."""
        mgr._current_watchlist_codes = {"AAPL"}
        mgr._is_initialized = True
        mgr._trading_day_count = 14
        old_cycle = mgr._cycle_count

        scan_result = [
            {"code": "MSFT", "ticker": "MSFT", "name": "Microsoft", "sector": "Tech"},
        ]

        mgr.apply_scan_result(scan_result, {})

        assert mgr._current_watchlist == scan_result
        assert mgr._current_watchlist_codes == {"MSFT"}
        assert mgr._cycle_count == old_cycle + 1
        assert mgr._trading_day_count == 0
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

Run: `cd /Users/daniel/dev/atm-dev && python -m pytest ats/tests/test_rebalance_integration.py::TestRebalanceManagerExtensions::test_apply_scan_result_returns_event -v`
Expected: FAIL — `AttributeError: 'RebalanceManager' object has no attribute 'apply_scan_result'`

- [ ] **Step 3: apply_scan_result() 구현**

`ats/backtest/rebalancer.py` — `reset_counter()` 뒤에 추가:

```python
def apply_scan_result(
    self,
    scan_result: list,
    active_positions: dict,
) -> "RebalanceEvent":
    """PAPER/LIVE: 스캔 결과를 받아 상태 변경 (메인 스레드에서 호출).

    execute_rebalance()의 상태 변경 부분만 분리한 버전.
    CPU-intensive scan()은 별도 스레드에서 실행하고,
    이 메서드는 이벤트 루프 스레드에서 호출하여 race condition을 방지한다.
    """
    new_codes = {w["code"] for w in scan_result}
    old_codes = self._current_watchlist_codes

    added = sorted(new_codes - old_codes)
    removed = sorted(old_codes - new_codes)
    force_exit = sorted(set(active_positions.keys()) & set(removed))

    # 상태 업데이트
    self._current_watchlist = scan_result
    self._current_watchlist_codes = new_codes
    self._cycle_count += 1
    self._trading_day_count = 0
    self._is_initialized = True  # 스펙 4.3에는 빠져있지만 필수 — 없으면 무한 리밸런스 루프

    event = RebalanceEvent(
        date="",
        cycle_number=self._cycle_count,
        stocks_added=added,
        stocks_removed=removed,
        positions_force_exited=force_exit,
        new_watchlist=scan_result,
        total_scanned=len(scan_result),
        passed_prefilter=len(scan_result),
    )
    self._history.append(event)
    return event
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

Run: `cd /Users/daniel/dev/atm-dev && python -m pytest ats/tests/test_rebalance_integration.py::TestRebalanceManagerExtensions -v`
Expected: 4 PASSED

- [ ] **Step 5: 커밋**

```bash
cd /Users/daniel/dev/atm-dev
git add ats/backtest/rebalancer.py ats/tests/test_rebalance_integration.py
git commit -m "feat: RebalanceManager.apply_scan_result() 추가"
```

---

### Task 3: set_rebalance_exits() union 방식 변경

**Files:**
- Modify: `ats/simulation/engine.py:1227-1229`
- Test: `ats/tests/test_rebalance_integration.py`

- [ ] **Step 1: union 동작 테스트 작성**

`ats/tests/test_rebalance_integration.py` 에 새 테스트 클래스 추가:

```python
class TestSetRebalanceExitsUnion:
    """set_rebalance_exits()가 기존 코드를 덮어쓰지 않고 병합하는지 테스트."""

    def test_union_with_existing_codes(self):
        """기존 퇴출 코드에 새 코드가 병합된다."""
        from simulation.engine import SimulationEngine

        async def noop(t, d): pass
        engine = SimulationEngine(on_event=noop, market_id="sp500")

        # 레짐 다운그레이드로 퇴출 코드 추가된 상태
        engine._rebalance_exit_codes = {"INTC", "BA"}

        # 리밸런싱으로 추가 퇴출
        engine.set_rebalance_exits({"DIS", "BA"})

        # BA는 중복, DIS는 신규 — 모두 포함되어야 함
        assert engine._rebalance_exit_codes == {"INTC", "BA", "DIS"}

    def test_union_with_empty_existing(self):
        """기존 코드가 비어있으면 새 코드만 설정된다."""
        from simulation.engine import SimulationEngine

        async def noop(t, d): pass
        engine = SimulationEngine(on_event=noop, market_id="sp500")

        engine.set_rebalance_exits({"AAPL"})
        assert engine._rebalance_exit_codes == {"AAPL"}
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

Run: `cd /Users/daniel/dev/atm-dev && python -m pytest ats/tests/test_rebalance_integration.py::TestSetRebalanceExitsUnion::test_union_with_existing_codes -v`
Expected: FAIL — `AssertionError` (현재는 덮어쓰기 방식)

- [ ] **Step 3: set_rebalance_exits() 수정**

`ats/simulation/engine.py` line 1227-1229를 변경:

```python
def set_rebalance_exits(self, codes: set):
    """리밸런스 탈락 종목을 ES7 청산 대상으로 지정 (기존 코드와 병합)."""
    self._rebalance_exit_codes |= set(codes)
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

Run: `cd /Users/daniel/dev/atm-dev && python -m pytest ats/tests/test_rebalance_integration.py::TestSetRebalanceExitsUnion -v`
Expected: 2 PASSED

- [ ] **Step 5: 기존 테스트 전체 통과 확인**

Run: `cd /Users/daniel/dev/atm-dev && python3 run_tests.py`
Expected: 43 tests passed (기존 테스트 깨지지 않음)

- [ ] **Step 6: 커밋**

```bash
cd /Users/daniel/dev/atm-dev
git add ats/simulation/engine.py ats/tests/test_rebalance_integration.py
git commit -m "fix: set_rebalance_exits() union 방식으로 변경 (덮어쓰기 방지)"
```

---

## Chunk 2: SimulationEngine 리밸런싱 내장

### Task 4: SimulationEngine constructor에 리밸런싱 속성 추가

**Files:**
- Modify: `ats/simulation/engine.py:831-940` (constructor)

- [ ] **Step 1: constructor에 리밸런싱 속성 추가**

`ats/simulation/engine.py` — `__init__` 메서드 내부, `self._rebalance_exit_codes: set = set()` (line 980) 근처에 추가:

```python
        # --- 리밸런싱 내장 (Step 1) ---
        self._rebalance_mgr = None
        self._rebalance_history: list = []
        self._pending_rebalance = None
        self._full_universe_ohlcv = None
```

- [ ] **Step 2: set_full_universe_ohlcv() 메서드 추가**

`ats/simulation/engine.py` — `set_rebalance_exits()` (line 1229) 뒤에 추가:

```python
    def set_full_universe_ohlcv(self, ohlcv: dict):
        """전체 유니버스 OHLCV 주입 (BACKTEST 리밸런싱 스캔용).

        _ohlcv_cache(워치리스트용)와 별도로 관리한다.
        리밸런싱 스캔 시 전체 유니버스에서 종목을 선별하기 위해 사용.
        """
        self._full_universe_ohlcv = ohlcv

    def init_rebalance_manager(self, scanner, rebalance_interval: int = 14):
        """리밸런스 매니저를 엔진에 내장한다.

        Args:
            scanner: UniverseScanner 인스턴스
            rebalance_interval: 리밸런싱 주기 (거래일 단위, 기본 14)
        """
        from backtest.rebalancer import RebalanceManager
        self._rebalance_mgr = RebalanceManager(
            scanner=scanner,
            rebalance_interval=rebalance_interval,
        )
```

- [ ] **Step 3: 기존 테스트 통과 확인**

Run: `cd /Users/daniel/dev/atm-dev && python3 run_tests.py`
Expected: 43 tests passed

- [ ] **Step 4: 커밋**

```bash
cd /Users/daniel/dev/atm-dev
git add ats/simulation/engine.py
git commit -m "feat: SimulationEngine에 리밸런싱 속성 및 초기화 메서드 추가"
```

---

### Task 5: _check_rebalance_sync() 및 _apply_rebalance() 구현

**Files:**
- Modify: `ats/simulation/engine.py` (set_full_universe_ohlcv 뒤)
- Test: `ats/tests/test_rebalance_integration.py`

- [ ] **Step 1: 통합 테스트 작성**

`ats/tests/test_rebalance_integration.py` 에 새 클래스 추가:

```python
class TestEngineRebalanceIntegration:
    """SimulationEngine._check_rebalance_sync() 통합 테스트."""

    @pytest.fixture
    def engine_with_rebalance(self):
        """리밸런싱이 내장된 엔진."""
        from simulation.engine import SimulationEngine
        from simulation.universe import UniverseScanner

        async def noop(t, d): pass

        engine = SimulationEngine(on_event=noop, market_id="sp500")

        # 간단한 유니버스 (3종목)
        constituents = [
            {"code": "AAPL", "ticker": "AAPL", "name": "Apple", "sector": "Tech"},
            {"code": "MSFT", "ticker": "MSFT", "name": "Microsoft", "sector": "Tech"},
            {"code": "INTC", "ticker": "INTC", "name": "Intel", "sector": "Tech"},
        ]

        scanner = MagicMock()
        scanner.scan.return_value = [
            {"code": "AAPL", "ticker": "AAPL", "name": "Apple", "sector": "Tech"},
            {"code": "MSFT", "ticker": "MSFT", "name": "Microsoft", "sector": "Tech"},
        ]

        engine.init_rebalance_manager(scanner=scanner, rebalance_interval=3)
        return engine

    def test_no_rebalance_when_not_initialized(self):
        """리밸런스 매니저가 없으면 아무것도 안 한다."""
        from simulation.engine import SimulationEngine

        async def noop(t, d): pass
        engine = SimulationEngine(on_event=noop, market_id="sp500")

        # 에러 없이 통과해야 함
        engine._check_rebalance_sync()

    def test_first_day_triggers_rebalance(self, engine_with_rebalance):
        """첫 거래일에 리밸런싱이 발동한다 (초기 워치리스트 시딩)."""
        engine = engine_with_rebalance
        engine._backtest_date = "2024-01-02"

        # 전체 유니버스 데이터 주입 (mock)
        engine._full_universe_ohlcv = {"AAPL": MagicMock(), "MSFT": MagicMock(), "INTC": MagicMock()}

        engine._check_rebalance_sync()

        # 워치리스트가 스캔 결과로 교체됨
        assert len(engine._watchlist) == 2
        codes = {w["code"] for w in engine._watchlist}
        assert codes == {"AAPL", "MSFT"}
        assert len(engine._rebalance_history) == 1

    def test_rebalance_not_triggered_before_interval(self, engine_with_rebalance):
        """주기 도달 전에는 리밸런싱 안 함."""
        engine = engine_with_rebalance
        engine._backtest_date = "2024-01-02"
        engine._full_universe_ohlcv = {"AAPL": MagicMock(), "MSFT": MagicMock()}

        # 첫 리밸런싱
        engine._check_rebalance_sync()
        assert len(engine._rebalance_history) == 1

        # 1일 후 — 아직 안 됨
        engine._check_rebalance_sync()
        assert len(engine._rebalance_history) == 1

    def test_apply_rebalance_merges_exit_codes(self, engine_with_rebalance):
        """_apply_rebalance()는 기존 퇴출 코드와 병합한다."""
        engine = engine_with_rebalance

        # 기존 레짐 다운그레이드 퇴출 코드
        engine._rebalance_exit_codes = {"BA"}

        event = RebalanceEvent(
            date="2024-01-15",
            cycle_number=1,
            positions_force_exited=["INTC"],
            new_watchlist=[
                {"code": "AAPL", "ticker": "AAPL", "name": "Apple", "sector": "Tech"},
            ],
        )

        engine._apply_rebalance(event)

        # 병합 확인
        assert engine._rebalance_exit_codes == {"BA", "INTC"}
        assert len(engine._rebalance_history) == 1
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

Run: `cd /Users/daniel/dev/atm-dev && python -m pytest ats/tests/test_rebalance_integration.py::TestEngineRebalanceIntegration::test_no_rebalance_when_not_initialized -v`
Expected: FAIL — `AttributeError: 'SimulationEngine' object has no attribute '_check_rebalance_sync'`

- [ ] **Step 3: _check_rebalance_sync() 및 _apply_rebalance() 구현**

`ats/simulation/engine.py` — `init_rebalance_manager()` 뒤에 추가:

```python
    def _check_rebalance_sync(self):
        """BACKTEST 모드 전용 리밸런싱 체크 (동기 실행).

        should_rebalance() → execute_rebalance() → tick() 순서를 유지한다.
        현재 HistoricalBacktester의 실행 순서와 동일하게 유지하여 회귀를 방지.
        """
        if not self._rebalance_mgr:
            return

        if not self._rebalance_mgr.should_rebalance():
            self._rebalance_mgr.tick()
            return

        # 전체 유니버스 데이터로 스캔 (없으면 워치리스트 데이터 폴백)
        ohlcv_for_scan = self._full_universe_ohlcv or self._ohlcv_cache
        active_positions = {
            pos.stock_code: pos for pos in self.positions.values()
            if pos.status == "ACTIVE"
        }

        event = self._rebalance_mgr.execute_rebalance(
            ohlcv_map=ohlcv_for_scan,
            current_date=self._backtest_date,
            active_positions=active_positions,
        )

        self._apply_rebalance(event)
        self._rebalance_mgr.tick()

    def _apply_rebalance(self, event):
        """리밸런싱 이벤트를 엔진에 적용한다.

        update_watchlist()를 사용하여 _stock_names도 함께 갱신.
        기존 regime 다운그레이드 퇴출 코드와 병합 (덮어쓰기 방지).
        """
        # 워치리스트 교체 + _stock_names 갱신
        self.update_watchlist(event.new_watchlist)

        # 기존 퇴출 코드와 병합
        self._rebalance_exit_codes |= set(event.positions_force_exited)

        # 이력 기록
        self._rebalance_history.append(event)
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

Run: `cd /Users/daniel/dev/atm-dev && python -m pytest ats/tests/test_rebalance_integration.py::TestEngineRebalanceIntegration -v`
Expected: 4 PASSED

- [ ] **Step 5: 전체 테스트 통과 확인**

Run: `cd /Users/daniel/dev/atm-dev && python3 run_tests.py`
Expected: 43+ tests passed

- [ ] **Step 6: 커밋**

```bash
cd /Users/daniel/dev/atm-dev
git add ats/simulation/engine.py ats/tests/test_rebalance_integration.py
git commit -m "feat: SimulationEngine._check_rebalance_sync() + _apply_rebalance() 구현"
```

---

### Task 6: run_backtest_day()에 _check_rebalance_sync() 삽입

**Files:**
- Modify: `ats/simulation/engine.py:1202-1207` (regime downgrade 후, scan_entries 전)

- [ ] **Step 1: run_backtest_day()에 리밸런싱 체크 삽입**

`ats/simulation/engine.py` — `run_backtest_day()` 내부, `_reduce_positions_for_regime()` 호출 (line ~1204) 뒤, `_scan_entries()` (line ~1207) 전에 추가:

기존:
```python
        # line ~1204
        self._reduce_positions_for_regime()
        # line ~1207
        self._scan_entries()
```

변경 후:
```python
        self._reduce_positions_for_regime()
        # 리밸런싱 체크 (regime 업데이트 후, entry 스캔 전)
        self._check_rebalance_sync()
        self._scan_entries()
```

- [ ] **Step 2: 기존 테스트 통과 확인**

Run: `cd /Users/daniel/dev/atm-dev && python3 run_tests.py`
Expected: 43+ tests passed (리밸런스 매니저 미설정 시 _check_rebalance_sync()는 즉시 리턴)

- [ ] **Step 3: 커밋**

```bash
cd /Users/daniel/dev/atm-dev
git add ats/simulation/engine.py
git commit -m "feat: run_backtest_day()에 _check_rebalance_sync() 삽입"
```

---

## Chunk 3: HistoricalBacktester 마이그레이션

### Task 7: HistoricalBacktester에서 엔진으로 리밸런싱 이관

**Files:**
- Modify: `ats/backtest/historical_engine.py:142-160` (RebalanceManager 생성)
- Modify: `ats/backtest/historical_engine.py:484-516` (daily loop 리밸런스 블록)

핵심: HistoricalBacktester에서 RebalanceManager를 직접 생성하지 않고, SimulationEngine에 내장하도록 변경한다.

- [ ] **Step 1: HistoricalBacktester — 엔진에 리밸런스 매니저 내장**

`ats/backtest/historical_engine.py` — RebalanceManager 생성 부분 (line ~142-160)을 변경:

기존 코드는 `rebalance_mgr = RebalanceManager(...)` 로 로컬 변수에 생성.

변경 후: `rebalance_mgr` 로컬 변수 대신 `self.engine.init_rebalance_manager(scanner, rebalance_interval)` 호출.

```python
# 기존: rebalance_mgr = RebalanceManager(scanner=scanner, rebalance_interval=...)
# 변경:
self.engine.init_rebalance_manager(
    scanner=scanner,
    rebalance_interval=self.rebalance_days,
)
rebalance_mgr = self.engine._rebalance_mgr  # 하위 호환용 참조
```

- [ ] **Step 2: daily loop에서 리밸런싱 오케스트레이션 제거 + OHLCV 주입 최적화**

daily loop 내 리밸런싱 블록 (line ~484-516)을 변경한다.

**핵심**: 전체 유니버스 OHLCV를 매일 갱신하면 ~14x 성능 저하. **리밸런스 직전에만** 갱신한다.
`_check_rebalance_sync()` 내부에서 리밸런싱이 필요한지 판단하고 실행하므로,
OHLCV는 `should_rebalance()` 가능성이 있을 때만 주입하면 된다.

기존:
```python
if rebalance_mgr and rebalance_mgr.should_rebalance():
    full_ohlcv = self.provider.get_ohlcv_up_to_date(download_watchlist)
    active_positions = {...}
    event = rebalance_mgr.execute_rebalance(...)
    self.engine.update_watchlist(event.new_watchlist)
    if event.positions_force_exited:
        self.engine.set_rebalance_exits(...)
# ...
if rebalance_mgr:
    rebalance_mgr.tick()
```

변경 후:
```python
# 리밸런싱은 engine.run_backtest_day() 내부의 _check_rebalance_sync()에서 자동 처리
# 전체 유니버스 OHLCV는 리밸런싱 직전에만 갱신 (성능 최적화)
if self.engine._rebalance_mgr and self.engine._rebalance_mgr.should_rebalance():
    full_ohlcv = self.provider.get_ohlcv_up_to_date(download_watchlist)
    self.engine.set_full_universe_ohlcv(full_ohlcv)
# rebalance_mgr.tick() 제거 — 엔진 내부 _check_rebalance_sync()에서 처리
```

**주의**: `set_full_universe_ohlcv()`는 `self.provider.set_current_date(date)` 호출 **이후**에 위치해야 한다 (daily loop 내부, 날짜 설정 후).

- [ ] **Step 4: 메트릭 수집 — 엔진의 리밸런스 히스토리 사용**

결과 수집 부분에서 `rebalance_mgr` 대신 `engine._rebalance_mgr` 접근:

```python
# 기존: result.total_rebalances = rebalance_mgr.cycle_count
# 변경:
if self.engine._rebalance_mgr:
    result.total_rebalances = self.engine._rebalance_mgr._cycle_count
    result.avg_turnover_pct = ...  # 기존 로직 유지
```

- [ ] **Step 5: 기존 단위 테스트 통과 확인**

Run: `cd /Users/daniel/dev/atm-dev && python3 run_tests.py`
Expected: 43+ tests passed

- [ ] **Step 6: 커밋**

```bash
cd /Users/daniel/dev/atm-dev
git add ats/backtest/historical_engine.py
git commit -m "refactor: HistoricalBacktester 리밸런싱을 SimulationEngine으로 이관"
```

---

### Task 8: 회귀 백테스트 검증

**Files:** (수정 없음 — 검증만)

- [ ] **Step 1: 2-year 백테스트 실행**

Run:
```bash
cd /Users/daniel/dev/atm-dev
python3 -c "
from backtest.historical_engine import HistoricalBacktester
bt = HistoricalBacktester.from_optimal(
    market='sp500',
    start_date='20240101',
    end_date='20260228',
)
result = bt.run()
print(f'Return: {result.total_return_pct:.1f}%')
print(f'Sharpe: {result.sharpe_ratio:.2f}')
print(f'MDD: {result.max_drawdown_pct:.1f}%')
print(f'Trades: {result.total_trades}')
print(f'Rebalances: {getattr(result, \"total_rebalances\", \"N/A\")}')
"
```

Expected:
- Return: +28.4% (±0.1%)
- Sharpe: 1.18 (±0.02)
- MDD: -9.7% (±0.2%)
- Trades: 185 (±5)

- [ ] **Step 2: 결과 확인 — 통과 시 커밋**

결과가 허용 오차 내라면:

```bash
cd /Users/daniel/dev/atm-dev
git add -A
git commit -m "verify: Step 1 회귀 검증 통과 (Sharpe X.XX, Return +XX.X%)"
```

결과가 오차 밖이면: **STOP** — 원인 분석 후 수정.

---

## 회귀 실패 시 디버깅 가이드

리밸런싱 타이밍 차이가 가장 흔한 원인이다:

1. **tick/check 순서 확인**: `_check_rebalance_sync()`에서 should_rebalance → execute → tick 순서가 기존 HistoricalBacktester와 동일한지
2. **OHLCV 데이터 범위 확인**: `_full_universe_ohlcv`가 전체 유니버스를 포함하는지 (워치리스트만 아닌지)
3. **set_rebalance_exits union 확인**: 기존 `set_rebalance_exits()`가 여전히 HistoricalBacktester에서 호출되지 않는지 (이중 호출 방지)
4. **_reduce_positions_for_regime과 리밸런싱 순서**: regime downgrade → rebalance 순서가 유지되는지
