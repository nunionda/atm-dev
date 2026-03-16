# Unified Portfolio Engine — Design Spec

**Date**: 2026-03-15
**Status**: Draft (Rev.2 — spec review 반영)
**Scope**: SimulationEngine에 리밸런싱 내장 + 3-Mode 통합 (BACKTEST/PAPER/LIVE) + KIS 브로커 연동

---

## 1. Problem Statement

현재 시스템은 3가지 실행 경로가 분리되어 있다:

- **Operations 실시간 시뮬레이션**: SimulationEngine 단독 (리밸런싱 없음)
- **Rebalance 백테스트**: HistoricalBacktester가 RebalanceManager를 오케스트레이션
- **Live Trading**: 미구현

HistoricalBacktester가 오케스트레이터 역할을 하면서 경로마다 오케스트레이터 × 리밸런서 × 엔진 조합이 늘어나는 문제가 있다. Live Trading 경로를 추가하면 또 다른 오케스트레이터가 필요해진다.

## 2. Goal

SimulationEngine 하나로 BACKTEST/PAPER/LIVE 모든 경로를 처리하는 통합 포트폴리오 엔진을 만든다.

### 전환 경로

```
시뮬레이션 수익률 확인 → Paper (모의투자) → Live (실전)
```

### 대상 마켓

- 한국 (KOSPI) + 미국 (S&P500, NASDAQ100)
- KIS API로 모두 커버 (해외주식 매매 지원)

---

## 3. Architecture

### 3.1 Engine Mode System

```python
class EngineMode(Enum):
    BACKTEST = "backtest"    # 캐시 데이터, 가상 체결
    PAPER = "paper"          # KIS 실시간 시세, 모의투자 API
    LIVE = "live"            # KIS 실시간 시세, 실전 API
```

| 동작 | BACKTEST | PAPER | LIVE |
|------|----------|-------|------|
| 데이터 소스 | 외부 주입 (HistoricalBacktester) | KIS 시세 API | KIS 시세 API |
| 주문 실행 | 가상 체결 (VirtualExecutor) | KIS 모의투자 API | KIS 실전 API |
| 리밸런싱 주기 | 14 거래일 자동 | 14 거래일 자동 | 14 거래일 + 텔레그램 승인 |
| 사이클 주기 | 즉시 (날짜 루프) | 30초 | 30초 |
| 브로드캐스트 | 없음 | SSE | SSE + 텔레그램 |

### 3.2 Engine Constructor (변경)

기존 `on_event: OnEventType` 파라미터는 유지한다. 이 콜백은 SSE 브로드캐스트에 필수이며 엔진 내부 ~30곳에서 호출된다.

```python
class SimulationEngine:
    def __init__(self, on_event: OnEventType, market_id: str,
                 mode: EngineMode = EngineMode.BACKTEST,
                 executor: OrderExecutor = None,
                 notifier: TelegramNotifier = None,
                 approver: RebalanceApprover = None,
                 universe_config: dict = None):
        self._on_event = on_event  # 기존 필수 파라미터 유지
        self._mode = mode
        self._executor = executor or VirtualExecutor()
        self._notifier = notifier
        self._approver = approver

        # 리밸런싱 내장
        self._rebalance_mgr = None
        self._rebalance_history: list[RebalanceEvent] = []
        self._pending_rebalance = None
        self._full_universe_ohlcv = None  # BACKTEST: 전체 유니버스 데이터 (별도 캐시)
        if universe_config:
            self._rebalance_mgr = RebalanceManager(
                scanner=UniverseScanner(
                    universe_config["constituents"],
                    universe_config["top_n"]
                ),
                rebalance_interval=universe_config.get("interval", 14),
            )
```

**주의**: BACKTEST 모드에서 `on_event`는 기존대로 `_noop_event` (no-op 콜백)을 전달한다.

### 3.3 Unified Architecture Diagram

```
┌─────────────────────────────────────────────────┐
│                SimulationEngine                  │
│  ┌───────────┐ ┌──────────┐ ┌────────────────┐  │
│  │ 6-Phase   │ │ Strategy │ │ Rebalance      │  │
│  │ Pipeline  │ │ Allocator│ │ Manager        │  │
│  │ (매매판단) │ │ (가중치)  │ │ (유니버스 교체) │  │
│  └───────────┘ └──────────┘ └────────────────┘  │
│  ┌───────────┐ ┌──────────┐ ┌────────────────┐  │
│  │ Regime    │ │ Risk     │ │ Rebalance      │  │
│  │ Detector  │ │ Gates    │ │ Approver       │  │
│  │ (레짐판단) │ │ (RG1-5)  │ │ (LIVE 승인)    │  │
│  └───────────┘ └──────────┘ └────────────────┘  │
│                      │                           │
│              OrderExecutor (Protocol)            │
└──────────────────────┬──────────────────────────┘
                       │
         ┌─────────────┼─────────────┐
         ▼             ▼             ▼
  VirtualExecutor  KISPaper     KISLive
  (BACKTEST)       Executor     Executor
                   (PAPER)      (LIVE)
```

### 3.4 Three Execution Paths

```
BACKTEST:
  HistoricalBacktester → 데이터 준비 → SimulationEngine(BACKTEST)
                                        └→ VirtualExecutor
                                        └→ RebalanceManager (자동)

PAPER:
  main.py paper → TradingScheduler → SimulationEngine(PAPER)
                                      └→ KISPaperExecutor
                                      └→ RebalanceManager (자동)
                                      └→ SSE 브로드캐스트

LIVE:
  main.py live → TradingScheduler → SimulationEngine(LIVE)
                                     └→ KISLiveExecutor
                                     └→ RebalanceManager + Approver
                                     └→ SSE + 텔레그램
```

---

## 4. Rebalancing Integration

### 4.1 Check Position in Cycle

exit 이후, entry 이전에 리밸런싱을 체크한다.

```python
# run_backtest_day() / _run_cycle() 공통 흐름
def _execute_day(self):
    self._update_position_prices()
    self._check_exits()              # Phase 5
    self._update_market_regime()     # Phase 0
    self._check_rebalance()          # ← NEW
    self._scan_entries()             # Phase 1-4
    self._record_equity_point()
```

### 4.2 _check_rebalance() Logic

**tick/check 순서**: 현재 코드와 동일하게 should_rebalance() → execute → tick 순서를 유지한다.
이를 변경하면 첫 리밸런싱 타이밍이 1일 어긋나 백테스트 회귀 실패 위험이 있다.

**데이터 소스**: `_ohlcv_cache`(워치리스트용)와 `_full_universe_ohlcv`(스캔용)는 별도 캐시이다.
리밸런싱 스캔은 반드시 `_full_universe_ohlcv`를 사용해야 전체 유니버스에서 종목을 선별할 수 있다.

**active_positions**: `execute_rebalance()`는 `Dict[str, Any]` (code → position)을 기대한다.

**async/sync**: PAPER/LIVE의 `_run_cycle()`은 async이므로 `_check_rebalance()`도 async로 정의한다.
BACKTEST의 `run_backtest_day()`에서는 동기 래퍼 `_check_rebalance_sync()`를 호출한다.
CPU-intensive 스캔은 `asyncio.to_thread()`로 실행하여 이벤트 루프 블로킹을 방지한다.

```python
def _check_rebalance_sync(self):
    """BACKTEST 모드 전용 (동기 실행)"""
    if not self._rebalance_mgr:
        return

    if not self._rebalance_mgr.should_rebalance():
        self._rebalance_mgr.tick()
        return

    # 전체 유니버스 데이터로 스캔
    ohlcv_for_scan = self._full_universe_ohlcv or self._ohlcv_cache
    active_positions = {
        pos.stock_code: pos for pos in self._positions.values()
        if pos.status == "ACTIVE"
    }

    event = self._rebalance_mgr.execute_rebalance(
        ohlcv_map=ohlcv_for_scan,
        current_date=self._current_date,
        active_positions=active_positions,
    )

    self._apply_rebalance(event)
    self._rebalance_mgr.tick()  # execute 후 tick (현재 순서 유지)

async def _check_rebalance_async(self):
    """PAPER/LIVE 모드 전용 (비동기 실행)"""
    if not self._rebalance_mgr:
        return

    if not self._rebalance_mgr.should_rebalance():
        self._rebalance_mgr.tick()
        return

    active_positions = {
        pos.stock_code: pos for pos in self._positions.values()
        if pos.status == "ACTIVE"
    }

    # CPU-intensive 스캔만 스레드풀에서 실행 (RebalanceManager 상태 변경은 메인 스레드)
    scan_result = await asyncio.to_thread(
        self._rebalance_mgr.scanner.scan,
        ohlcv_map=self._ohlcv_cache,
        current_date=self._current_date,
    )
    # 상태 변경은 이벤트 루프 스레드에서 실행 (race condition 방지)
    event = self._rebalance_mgr.apply_scan_result(
        scan_result=scan_result,
        active_positions=active_positions,
    )

    # LIVE: 텔레그램 승인 대기
    if self._mode == EngineMode.LIVE and self._approver:
        self._pending_rebalance = event
        await self._approver.request_approval(event, {
            "positions": active_positions,
            "equity": self._total_equity,
            "cash_ratio": self._cash / self._total_equity,
        })
        return

    # PAPER: 즉시 실행
    self._apply_rebalance(event)
    self._rebalance_mgr.tick()

def _apply_rebalance(self, event: RebalanceEvent):
    # update_watchlist() 사용 — _stock_names도 함께 갱신
    self.update_watchlist(event.new_watchlist)

    # 기존 regime 다운그레이드 퇴출 코드와 병합 (덮어쓰기 방지)
    existing_exits = getattr(self, '_rebalance_exit_codes', set())
    self._rebalance_exit_codes = existing_exits | set(event.positions_force_exited)

    if self._mode != EngineMode.BACKTEST:
        self._emit_rebalance_event(event)

    self._rebalance_history.append(event)
```

### 4.3 LIVE Approval

`RebalanceManager`에 2개 메서드를 추가한다 (현재 미존재).

```python
# RebalanceManager에 추가
def reset_counter(self):
    """거부 시 카운터 리셋 — 다음 주기까지 대기"""
    self._trading_day_count = 0

def apply_scan_result(self, scan_result, active_positions):
    """PAPER/LIVE: 스캔 결과를 받아 상태 변경 (메인 스레드에서 호출)
    execute_rebalance()의 상태 변경 부분만 분리한 버전"""
    new_codes = {w["code"] for w in scan_result}
    old_codes = self._current_watchlist_codes
    added = list(new_codes - old_codes)
    removed = list(old_codes - new_codes)
    force_exit = list(active_positions.keys() & set(removed))
    # 상태 업데이트
    self._current_watchlist = scan_result
    self._current_watchlist_codes = new_codes
    self._cycle_count += 1
    self._trading_day_count = 0
    return RebalanceEvent(
        stocks_added=added, stocks_removed=removed,
        positions_force_exited=force_exit, new_watchlist=scan_result,
    )

# SimulationEngine
def approve_rebalance(self):
    if self._pending_rebalance:
        self._apply_rebalance(self._pending_rebalance)
        self._pending_rebalance = None
        self._rebalance_mgr.tick()

def reject_rebalance(self):
    self._pending_rebalance = None
    self._rebalance_mgr.reset_counter()  # 새 메서드
```

### 4.4 SSE Rebalance Event

```python
f"{market_id}:rebalance" → {
    "status": "executed" | "pending_approval" | "rejected",
    "next_rebalance_day": 7,
    "stocks_added": [...],
    "stocks_removed": [...],
    "force_exits": [...],
    "turnover_pct": 15.3,
}
```

### 4.5 BACKTEST Data Access

**2개의 별도 캐시**를 사용한다:
- `_ohlcv_cache`: 현재 워치리스트 종목의 일별 OHLCV (매매 판단용)
- `_full_universe_ohlcv`: 전체 유니버스 OHLCV (리밸런싱 스캔용)

HistoricalBacktester가 전체 유니버스 OHLCV를 `set_full_universe_ohlcv()`로 주입한다.
`_check_rebalance_sync()`는 이 별도 캐시를 사용하여 스캔한다.

```python
# SimulationEngine에 추가
def set_full_universe_ohlcv(self, ohlcv: Dict[str, pd.DataFrame]):
    """전체 유니버스 OHLCV 주입 (BACKTEST 리밸런싱 스캔용)"""
    self._full_universe_ohlcv = ohlcv

# HistoricalBacktester에서 호출
engine.set_full_universe_ohlcv(full_universe_ohlcv)  # 110-stock 전체
engine.run_backtest_day(date, ohlcv_cache, current_prices)  # 기존 시그니처 유지
# → 내부에서 _check_rebalance_sync() → UniverseScanner.scan(_full_universe_ohlcv)
```

**주의**: `run_backtest_day(date, ohlcv_cache, current_prices)` 기존 시그니처는 유지한다.
Step 3(얇은 래퍼 리팩터) 전까지는 기존 호출 방식을 보존하여 회귀 위험을 최소화한다.

---

## 5. Order Execution Abstraction

### 5.1 OrderExecutor Protocol

```python
class OrderExecutor(Protocol):
    def submit_order(self, order: OrderRequest) -> OrderResult: ...
    def cancel_order(self, order_id: str) -> bool: ...
    def get_order_status(self, order_id: str) -> OrderStatus: ...
    def get_current_prices(self, codes: list[str]) -> dict[str, float]: ...
```

### 5.2 Implementations

| 구현체 | 모드 | 내용 |
|--------|------|------|
| VirtualExecutor | BACKTEST | 슬리피지 0.1% + 수수료 0.015% 즉시 체결. 현재 엔진 내부 로직 추출 |
| KISPaperExecutor | PAPER | KISBroker(is_paper=True) 래핑 |
| KISLiveExecutor | LIVE | KISBroker(is_paper=False) 래핑 |

### 5.3 Engine Integration

```python
def _execute_entry(self, signal):
    result = self._executor.submit_order(OrderRequest(
        code=signal.code, side="BUY",
        quantity=signal.quantity, price=signal.target_price,
    ))
    if result.filled:
        self._create_position(signal, result)

def _execute_exit(self, position, reason):
    result = self._executor.submit_order(OrderRequest(
        code=position.stock_code, side="SELL",
        quantity=position.quantity, price=position.current_price,
    ))
    if result.filled:
        self._close_position(position, result, reason)
```

### 5.4 Price Fetching (PAPER/LIVE)

```python
async def _run_cycle(self):
    if self._mode in (EngineMode.PAPER, EngineMode.LIVE):
        self._current_prices = self._executor.get_current_prices(
            [w["code"] for w in self._watchlist]
        )
    # 이하 동일
```

---

## 6. Telegram Approval Flow (LIVE Only)

### 6.1 Report Format

```
📊 리밸런싱 리포트 (2026-03-15)
━━━━━━━━━━━━━━━━━━━━━━

🔄 퇴출 종목 (3)
  INTC  -3.2% (미실현 -$480)
  BA    +1.1% (미실현 +$165)
  DIS   -0.5% (미실현 -$75)

🆕 신규 종목 (3)
  NVDA  Score 87  (모멘텀 1위)
  AVGO  Score 74  (모멘텀 3위)
  LLY   Score 71  (모멘텀 5위)

💰 예상 거래비용
  매도 3건: ~$1.47
  매수 3건: ~$2.31
  합계: ~$3.78 (자산의 0.004%)

📈 포트폴리오 변화
  종목 수: 10 → 10
  턴오버: 15.3%
  현금 비율: 32% → 29%

[✅ 승인]  [❌ 거부]  [⏰ 1시간 후]
```

### 6.2 RebalanceApprover

```python
class RebalanceApprover:
    def __init__(self, notifier: TelegramNotifier, timeout_hours=24):
        self._notifier = notifier
        self._timeout = timeout_hours
        self._pending = None

    async def request_approval(self, event, portfolio_context):
        message = self._format_report(event, portfolio_context)
        await self._notifier.send_with_buttons(message, buttons=[
            ("✅ 승인", "rebal_approve"),
            ("❌ 거부", "rebal_reject"),
            ("⏰ 1시간 후", "rebal_defer_1h"),
        ])
        self._pending = event
        self._requested_at = datetime.now()  # 타임아웃 계산용

    async def handle_callback(self, action: str, engine) -> str:
        """텔레그램 콜백 라우터가 호출. engine에 직접 작용한다."""
        if action == "rebal_approve":
            engine.approve_rebalance()
            self._pending = None
            return "approved"
        elif action == "rebal_reject":
            engine.reject_rebalance()
            self._pending = None
            return "rejected"
        elif action == "rebal_defer_1h":
            return "deferred"

    def check_timeout(self) -> bool:
        if not self._pending:
            return False
        elapsed_hours = (datetime.now() - self._requested_at).total_seconds() / 3600
        if elapsed_hours > self._timeout:
            self._pending = None
            return True
        return False
```

### 6.3 TelegramNotifier Extension

기존 `send(message)` + 추가 필요:
1. `send_with_buttons(message, buttons)` — `InlineKeyboardMarkup` JSON으로 전송
2. **Callback 수신 인프라** — 2가지 방식 중 택 1:
   - **방식 A (추천): Polling** — `python-telegram-bot` 라이브러리의 `Application.run_polling()` + `CallbackQueryHandler` 사용. FastAPI와 별도 스레드에서 실행.
   - **방식 B: Webhook** — FastAPI에 `/telegram/callback` 엔드포인트 추가. Telegram Bot API의 `setWebhook`으로 등록. 외부 접근 가능한 URL 필요 (ngrok 등).
3. **Callback 라우터** — `callback_data` ("rebal_approve" 등)를 `engine.approve_rebalance()` / `reject_rebalance()`로 매핑

현재 `python-telegram-bot>=20.0`이 이미 설치되어 있으므로 방식 A가 가장 단순하다.

---

## 7. HistoricalBacktester Refactor

### 7.1 After (Thin Wrapper)

```python
class HistoricalBacktester:
    def run(self) -> ExtendedMetrics:
        # 1. 데이터 다운로드
        ohlcv = self._download_universe_data()
        vix = self._load_vix()
        index = self._load_index()
        arb_data = self._load_arbitrage_data() if self._has_arbitrage() else None

        # 2. 엔진 생성 (리밸런싱 설정 포함)
        engine = SimulationEngine(
            on_event=_noop_event,  # BACKTEST: no-op 콜백
            market_id=self.market,
            mode=EngineMode.BACKTEST,
            executor=VirtualExecutor(),
            universe_config={
                "constituents": self.universe_constituents,
                "top_n": self.top_n,
                "interval": self.rebalance_days,
            } if self.universe_id else None,
        )

        # 3. 데이터 주입 (전체 유니버스 + VIX + Index + Arbitrage)
        engine.set_full_universe_ohlcv(ohlcv)
        engine.set_vix_data(vix)
        engine.set_index_data(index)
        if arb_data:
            engine.set_arbitrage_data(arb_data)

        # 4. 날짜 루프 (단순)
        for date in trading_days:
            engine.run_backtest_day(date, day_ohlcv, current_prices)

        # 5. 메트릭 수집 (리밸런스 통계 포함)
        result = self._collect_metrics(engine)
        if engine._rebalance_mgr:
            result.total_rebalances = engine._rebalance_mgr.cycle_count
            result.avg_turnover_pct = engine._rebalance_mgr.avg_turnover_pct
        return result
```

### 7.2 Removed from HistoricalBacktester

| 제거 항목 | 이동 위치 |
|----------|----------|
| RebalanceManager 생성 | SimulationEngine.__init__ |
| should_rebalance() 체크 | SimulationEngine._check_rebalance_sync |
| update_watchlist() 호출 | SimulationEngine._apply_rebalance |
| set_rebalance_exits() 호출 | SimulationEngine._apply_rebalance |
| 리밸런스 이벤트 추적 | SimulationEngine._rebalance_history |

### 7.3 유지되는 항목

| 항목 | 이유 |
|------|------|
| 데이터 다운로드/캐싱 | 엔진은 "데이터를 받아서 판단"만 함 |
| Arbitrage 전략 데이터 (ETF pair, basis 등) | 별도 데이터 소스 필요 |
| 날짜 루프 + 일별 데이터 슬라이싱 | 타임머신 역할 |
| 메트릭 수집 + 리밸런스 통계 | engine._rebalance_mgr 접근 |

---

## 8. Edge Cases

### 8.1 Regime Downgrade + Rebalance 동시 발생

같은 날 레짐 다운그레이드(`_reduce_positions_for_regime()`)와 리밸런싱이 모두 발생할 수 있다.
두 로직 모두 `_rebalance_exit_codes`에 퇴출 종목을 추가한다.

**해결**: `_apply_rebalance()`에서 기존 퇴출 코드에 **union** (병합)한다. 덮어쓰기 금지.

```python
# _apply_rebalance() 내부
existing_exits = getattr(self, '_rebalance_exit_codes', set())
self._rebalance_exit_codes = existing_exits | set(event.positions_force_exited)
```

**실행 순서** (run_backtest_day):
1. `_check_exits()` — 기존 퇴출 코드 처리
2. `_update_market_regime()` — 레짐 변경 감지
3. `_reduce_positions_for_regime()` — 다운그레이드 시 퇴출 코드 추가
4. `_check_rebalance()` — 리밸런싱 퇴출 코드 **병합** 추가
5. `_scan_entries()` — 새 진입 (퇴출 종목 제외)

### 8.2 PAPER/LIVE 리밸런싱 중 시세 데이터

PAPER/LIVE에서 `UniverseScanner.scan()`은 실시간 시세 기반의 OHLCV가 필요하다.
현재 워치리스트 종목만 시세를 가져오므로, 리밸런싱 스캔 시점에 전체 유니버스 시세를 가져와야 한다.

**해결**: `_check_rebalance_async()`에서 스캔 전 `executor.get_current_prices(all_constituents)`로
전체 유니버스 최신 시세를 가져온 후 스캔에 전달한다.

---

## 9. PAPER/LIVE Pipeline

### 8.1 Entry Points

```bash
python3 main.py paper --market sp500
python3 main.py live --market sp500
python3 main.py api  # 기존 시뮬레이션 + API
```

### 8.2 Boot Sequence

```python
async def start_trading(market, mode):
    config = MARKET_CONFIG[market]
    is_paper = (mode == EngineMode.PAPER)
    executor = KISPaperExecutor() if is_paper else KISLiveExecutor()
    notifier = TelegramNotifier()
    approver = RebalanceApprover(notifier) if mode == EngineMode.LIVE else None

    engine = SimulationEngine(
        market_id=market, mode=mode,
        executor=executor, notifier=notifier, approver=approver,
        universe_config={...},
    )

    scheduler = TradingScheduler(engine, market)
    scheduler.register()
    await engine.start()
```

### 8.3 Trading Scheduler

```python
class TradingScheduler:
    SCHEDULES = {
        "kospi": {
            "pre_market": "08:30",
            "market_open": "09:00",
            "market_close": "15:30",
            "post_market": "16:00",
        },
        "sp500": {
            "pre_market": "22:00",   # KST
            "market_open": "22:30",
            "market_close": "05:00",
            "post_market": "05:30",
        },
    }
```

### 8.4 Daily Report (Telegram)

```
📋 일간 리포트 (2026-03-15)
━━━━━━━━━━━━━━━━━━━━━━
💰 자산: $103,240 (+0.8%)
📊 당일 PnL: +$812
📈 포지션: 8/10
🛡️ 현금 비율: 31.2%
🔄 레짐: BULL
⚡ 매매: 매수 1 / 매도 2
📉 MDD: -3.1%
🔜 다음 리밸런싱: 7 거래일 후
```

---

## 10. Safety Mechanisms

| 장치 | 동작 |
|------|------|
| 브로커 연결 실패 | 3회 재시도 → 텔레그램 알림 + 사이클 중단 |
| 주문 체결 실패 | 미체결 5분 초과 → 취소 + 다음 사이클 재시도 |
| 비정상 시세 | 전일 대비 ±50% → 해당 종목 스킵 + 알림 |
| 시스템 재시작 | DB에서 포지션 복원 → 마지막 상태 재개 |
| LIVE 모드 진입 | 텔레그램 "LIVE 시작" 확인 메시지 필수 |
| 리밸런싱 타임아웃 | 24시간 미응답 → 자동 스킵 |

---

## 11. File Changes

### New Files

| 파일 | 목적 |
|------|------|
| `ats/core/engine_mode.py` | EngineMode enum |
| `ats/order/executor.py` | OrderExecutor Protocol + VirtualExecutor |
| `ats/order/kis_executor.py` | KISPaperExecutor, KISLiveExecutor |
| `ats/core/trading_scheduler.py` | 장 시간 스케줄러 |
| `ats/core/rebalance_approver.py` | 텔레그램 승인 플로우 |

### Modified Files

| 파일 | 변경 |
|------|------|
| `ats/simulation/engine.py` | EngineMode, RebalanceManager 내장, OrderExecutor 연동 |
| `ats/backtest/historical_engine.py` | 리밸런싱 오케스트레이션 제거, 얇은 래퍼로 축소 |
| `ats/infra/notifier/telegram_notifier.py` | 인라인 버튼 + 콜백 핸들링 추가 |
| `main.py` | `paper`, `live` 명령어 추가 |
| `ats/backtest/rebalancer.py` | `reset_counter()` 메서드 추가 |

### Moved (import 유지)

| 대상 | 처리 |
|------|------|
| `ats/backtest/rebalancer.py` | 파일 유지, SimulationEngine에서 import |

---

## 12. Implementation Steps (Bottom-Up)

각 Step마다 회귀 검증을 통과해야 다음으로 진행한다.

### Step 1: RebalanceManager를 SimulationEngine에 내장
- `_check_rebalance_sync()`, `_apply_rebalance()` 추가
- `run_backtest_day()`에 리밸런싱 체크 삽입
- 기존 `set_rebalance_exits()`를 union 방식으로 변경 (`self._rebalance_exit_codes |= codes`)
  - Step 3 전까지 HistoricalBacktester가 여전히 `set_rebalance_exits()` 호출 → 덮어쓰기 방지
- `RebalanceManager`에 `reset_counter()`, `apply_scan_result()` 메서드 추가
- HistoricalBacktester의 리밸런싱 오케스트레이션 제거
- **검증**: 기존 백테스트 결과 동일 (Sharpe 1.18, Return +28.4%, ±0.1%)

### Step 2: OrderExecutor Protocol + VirtualExecutor 분리
- 엔진 내부 가상 체결 코드를 VirtualExecutor로 추출
- 엔진이 OrderExecutor Protocol에만 의존
- **검증**: 기존 백테스트 결과 동일

### Step 3: HistoricalBacktester 얇은 래퍼로 리팩터
- 데이터 준비 + 날짜 루프 + 메트릭 수집만 남김
- 전체 유니버스 OHLCV를 엔진에 주입하는 방식으로 변경
- **검증**: 기존 백테스트 결과 동일

### Step 4: KIS Executor 구현 (Paper/Live)
- KISPaperExecutor, KISLiveExecutor 구현
- 기존 kis_broker.py 래핑
- **검증**: KIS API 연결 + 시세 조회 테스트

### Step 5: TradingScheduler + main.py paper/live
- 장 시간 스케줄러 구현
- main.py에 paper, live 명령어 추가
- **검증**: Paper 모드 종목 1개 소규모 테스트

### Step 6: RebalanceApprover + 텔레그램 확장
- 상세 리포트 + 인라인 버튼 + 콜백 핸들링
- LIVE 모드 승인 플로우 구현
- **검증**: 승인/거부/연기 E2E 테스트

### Step 7: 안전장치 + 일간 리포트
- 브로커 연결 실패, 미체결, 비정상 시세 처리
- 일간 리포트 텔레그램 자동 전송
- **검증**: PAPER 모드 2주 풀 테스트
