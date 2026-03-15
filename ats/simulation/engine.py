"""
모의투자 시뮬레이션 엔진.
yfinance에서 실시간 가격을 가져오고, 모멘텀 스윙 전략 로직으로
가상 포지션/주문/시그널을 자동 생성한다.
전략 로직은 strategy/momentum_swing.py에서 간소화하여 복제.
"""

from __future__ import annotations

import asyncio
import math
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from simulation.models import (
    SimSystemState, SimPosition, SimOrder, SimSignal,
    SimRiskMetrics, SimTradeRecord, SimEquityPoint, SimPerformanceSummary,
)

from simulation.constants import (
    WATCHLIST, OnEventType,
    REGIME_PARAMS, STOCK_REGIME_THRESHOLDS, REGIME_EXIT_PARAMS,
    BASE_KELLY, REGIME_OVERRIDES, VIX_SIZING_SCALE,
    REGIME_STRATEGY_WEIGHTS, INDEX_TREND_STRATEGY_WEIGHTS,
    REGIME_DISPLAY_NAMES, STRATEGY_DISPLAY_NAMES,
    REGIME_STRATEGY_COMPOSITION,
    INVERSE_ETFS, SAFE_HAVEN_ETFS,
    MULTI_STRATEGIES, REGIME_STRATEGY_MODES,
)


from simulation.allocator import StrategyAllocator, _compute_adx  # noqa: F401


class SimulationEngine:

    # 레짐별 최소 시그널 강도 (Fix 2: BULL 과진입 방지)
    # MR 시그널은 57-81 분포이므로 BULL 50이면 저품질만 차단
    _REGIME_MIN_STRENGTH = {"BULL": 50, "NEUTRAL": 40, "RANGE_BOUND": 45, "BEAR": 55}

    def __init__(
        self,
        on_event: OnEventType,
        market_id: str = "kospi",
        watchlist: list | None = None,
        initial_capital: float = 100_000_000.0,
        currency: str = "KRW",
        currency_symbol: str = "₩",
        market_label: str = "KOSPI 200",
        slippage_pct: float = 0.001,
        commission_pct: float = 0.00015,
        strategy_mode: str = "momentum",
        fixed_amount_per_stock: float = 0,
        disable_es2: bool = False,
    ):
        self._on_event = on_event
        self.market_id = market_id
        self._watchlist = watchlist or WATCHLIST  # 하위호환
        self.currency = currency
        self.currency_symbol = currency_symbol
        self.market_label = market_label
        self.strategy_mode = strategy_mode  # "momentum" | "smc" | "multi" | "regime_*"
        self._regime_locked = strategy_mode in REGIME_STRATEGY_MODES
        self._locked_regime = REGIME_STRATEGY_MODES.get(strategy_mode)
        self._actual_market_regime = "NEUTRAL"  # 실제 감지 레짐 (표시용, 고정 시에도 갱신)
        self.fixed_amount_per_stock = fixed_amount_per_stock  # 0이면 기존 ATR 사이징
        self.disable_es2 = disable_es2  # True면 ES2 고정 익절 비활성화

        # 트랜잭션 비용
        self.slippage_pct = slippage_pct       # 0.1% 슬리피지 (편도)
        self.commission_pct = commission_pct   # 0.015% 수수료 (편도)
        self._total_commission_paid = 0.0      # 누적 수수료

        # 전략 파라미터 (config.yaml 미러링)
        self.ma_short = 5
        self.ma_long = 20
        self.rsi_period = 14
        self.rsi_lower = 52   # CF1 RSI 하한 (CLAUDE.md Phase 3: 52-78)
        self.rsi_upper = 78   # CF1 RSI 상한
        self.volume_multiplier = 1.5
        self.stop_loss_pct = -0.05    # ES1 손절 -5% (CLAUDE.md Phase 5)
        self.take_profit_pct = 0.20   # ES2 익절 BULL 기준 (체제별 동적)
        self.trailing_stop_pct = -0.04  # ES3 기본 floor -4% (Progressive ATR)
        self.trailing_activation_pct = 0.05
        self.max_holding_days = 40    # ES5 BULL 기준 (체제별: 40/25/15)
        self.max_positions = 10
        self.max_weight = 0.15
        self.min_cash_ratio = 0.30    # BR-P03: 최소 현금 비율 30%

        # 가상 포트폴리오
        self.initial_capital = initial_capital
        self.cash = self.initial_capital
        self.positions: Dict[str, SimPosition] = {}
        self.orders: List[SimOrder] = []
        self.signals: List[SimSignal] = []
        self.risk_events: List[Dict[str, Any]] = []

        # 시장 데이터 캐시
        self._ohlcv_cache: Dict[str, pd.DataFrame] = {}
        self._current_prices: Dict[str, float] = {}
        self._stock_names: Dict[str, str] = {w["code"]: w["name"] for w in self._watchlist}

        # 성과 추적
        self.closed_trades: List[SimTradeRecord] = []
        self.equity_curve: List[SimEquityPoint] = []
        self._trade_counter = 0

        # 리플레이 모드 (truncation 비활성화)
        self._replay_mode: bool = False
        self._exit_tag_filter: Optional[str] = None  # multi-mode exit tag routing
        # Phase 3.2: 단계적 DD 대응
        self._dd_level: int = 0       # 0=정상, 1=DD>10%, 2=DD>15%, 3=DD>20%
        self._dd_sizing_mult: float = 1.0  # DD>10% 시 0.5
        # Phase 4.6: 시그널 수집 모드
        self._collect_mode: bool = False
        self._collected_signals: List[tuple] = []

        # 트래킹
        self._started_at: Optional[str] = None
        self._peak_equity = self.initial_capital
        self._daily_start_equity = self.initial_capital
        self._consecutive_stops = 0
        self._daily_trade_amount = 0.0
        self._is_running = False
        self._market_regime: str = "NEUTRAL"  # Phase 0 결과 (BULL/NEUTRAL/RANGE_BOUND/BEAR)
        self._stock_regimes: Dict[str, str] = {}   # 종목별 개별 레짐 {stock_code: regime}
        self._stock_regimes_updated: bool = False  # 사이클 내 중복 업데이트 방지
        self._prev_regime: str = "NEUTRAL"  # 레짐 전환 감지용 이전 레짐
        self._regime_candidate: str = "NEUTRAL"  # 체제 전환 후보
        self._regime_candidate_days: int = 0  # 후보 연속 일수
        self._regime_confirmation_days: int = 5  # 체제 전환 확인 필요 일수

        # VIX 상태 (복합 Regime Classifier 및 포지션 사이징)
        self._vix_level: float = 18.0  # 기본값: 보통 수준
        self._vix_ema20: float = 18.0  # 20일 EMA (스파이크 스무딩)
        self._vix_history: List[float] = []  # VIX 이력 (EMA 계산용)

        # 지수 데이터 캐시 (Index-Driven Strategy Selection)
        self._index_ohlcv: List[Dict] = []   # [{open, high, low, close, volume}, ...]
        self._index_trend: Dict = {}          # _analyze_index_trend() 결과 캐시
        self._index_trend_history: List[Dict] = []  # 추세 변경 이력 (max 20)

        self._backtest_date: Optional[str] = None  # 백테스트 시 시뮬레이션 날짜
        self._cycle_count = 0
        self._order_counter = 0
        self._signal_counter = 0
        self._event_counter = 0

        # 진단 대상 종목 (Phase Funnel 디버그 로깅)
        self._debug_tickers: set = set()  # 예: {"005930", "000660"}

        # Phase 통계 (백테스트 수집용)
        self._phase_stats = {
            "total_scans": 0,
            "phase0_bear_blocks": 0,
            "phase1_trend_rejects": 0,
            "phase2_late_rejects": 0,
            "phase3_no_primary": 0,
            "phase3_no_confirm": 0,
            "phase3_ps3_pullback": 0,
            "phase4_risk_blocks": 0,
            "entries_executed": 0,
            "es1_stop_loss": 0,
            "es2_take_profit": 0,
            "es3_trailing_stop": 0,
            "es4_dead_cross": 0,
            "es5_max_holding": 0,
            "es6_time_decay": 0,
            "es7_rebalance_exit": 0,
            "es0_emergency_stop": 0,
            "divergence_blocks": 0,
            "regime_quality_blocks": 0,
            "index_trend_updates": 0,
            # 레짐별 전략 모듈화 카운터
            "phase3_ps4_donchian": 0,
            "es_neutral_time_decay": 0,
            "es_range_box_breakout": 0,
            "es_disp_partial_sell": 0,
            "regime_pyramid_entries": 0,
            "regime_sizing_reductions": 0,
            # 종목별 레짐 통계
            "stock_regime_distribution": {},     # {regime: count} 마지막 사이클 분포
            "stock_regime_strategy_map": {},     # {"regime→strategy": count} 라우팅 이력
        }

        # 에쿼티 히스토리 (프로그레시브 트레일링 기준용)
        self._equity_history: List[float] = []

        # 리밸런스 청산 대상 (ES7)
        self._rebalance_exit_codes: set = set()

        # ── Tactical 전용 포트폴리오 배분 (Kelly Criterion) ──
        self._allocator: Optional['PortfolioAllocator'] = None

        if self.market_id == "kospi":
            try:
                from simulation.portfolio_allocator import PortfolioAllocator
                from data.config_manager import PortfolioAllocationConfig
                alloc_cfg = PortfolioAllocationConfig(
                    enabled=True,
                    kelly_fraction=0.30,
                )
                self._allocator = PortfolioAllocator(alloc_cfg)
                self.min_cash_ratio = 1.0 - alloc_cfg.kelly_fraction  # 0.70
                self.max_positions = alloc_cfg.tactical.top_n  # tactical 60종목
            except ImportError as e:
                print(f"[SimEngine:{self.market_id}] PortfolioAllocator 모듈 임포트 실패: {e}")
                self._allocator = None
            except Exception as e:
                print(f"[SimEngine:{self.market_id}] PortfolioAllocator 초기화 실패: {e} — 기본값 사용")
                self._allocator = None

        # ── 멀티 전략 / 레짐 전략 모드 초기화 ──
        self._strategy_allocator: Optional[StrategyAllocator] = None
        if self.strategy_mode == "multi" or self.strategy_mode in REGIME_STRATEGY_MODES:
            init_regime = self._locked_regime if self._regime_locked else self._market_regime
            self._strategy_allocator = StrategyAllocator(
                strategies=MULTI_STRATEGIES,
                regime=init_regime,
            )
            # 멀티/레짐 모드에서는 모든 전략의 설정을 로드
            self._init_strategy_configs(MULTI_STRATEGIES)
        else:
            # 단일 전략 모드: 해당 전략만 초기화
            self._init_strategy_configs([self.strategy_mode])

    def _init_strategy_configs(self, strategies: List[str]):
        """전략별 설정 및 상태를 초기화한다. 멀티 모드에서는 여러 전략을 동시 로드."""
        for s in strategies:
            if s == "smc" and not hasattr(self, '_smc_cfg'):
                from data.config_manager import SMCStrategyConfig
                self._smc_cfg = SMCStrategyConfig()
                self._smc_entry_threshold = self._smc_cfg.entry_threshold
                self._phase_stats.setdefault("es_smc_sl", 0)
                self._phase_stats.setdefault("es_smc_tp", 0)
                self._phase_stats.setdefault("es_choch_exit", 0)
                self._phase_stats.setdefault("smc_total_score", 0)
                self._phase_stats.setdefault("smc_entries", 0)

            elif s == "mean_reversion" and not hasattr(self, '_mr_cfg'):
                from data.config_manager import MeanReversionConfig
                self._mr_cfg = MeanReversionConfig()
                self._phase_stats.setdefault("mr_entries", 0)
                self._phase_stats.setdefault("mr_total_score", 0)
                self._phase_stats.setdefault("es_mr_sl", 0)
                self._phase_stats.setdefault("es_mr_tp", 0)
                self._phase_stats.setdefault("es_mr_bb", 0)
                self._phase_stats.setdefault("es_mr_ob", 0)

            elif s == "breakout_retest" and not hasattr(self, '_brt_cfg'):
                from data.config_manager import SMCStrategyConfig, BreakoutRetestConfig
                if not hasattr(self, '_smc_cfg'):
                    self._smc_cfg = SMCStrategyConfig()
                self._brt_cfg = BreakoutRetestConfig()
                if not hasattr(self, '_breakout_states'):
                    self._breakout_states: Dict[str, Any] = {}
                self._phase_stats.setdefault("brt_breakouts_detected", 0)
                self._phase_stats.setdefault("brt_fakeout_blocked", 0)
                self._phase_stats.setdefault("brt_retests_entered", 0)
                self._phase_stats.setdefault("brt_retests_expired", 0)
                self._phase_stats.setdefault("es_brt_sl", 0)
                self._phase_stats.setdefault("es_brt_tp", 0)
                self._phase_stats.setdefault("es_zone_break", 0)
                self._phase_stats.setdefault("es_choch_exit", 0)

            elif s == "arbitrage" and not hasattr(self, '_arb_cfg'):
                from data.config_manager import ArbitrageConfig, ConfigManager
                try:
                    _cfg_mgr = ConfigManager()
                    _full_cfg = _cfg_mgr.load()
                    self._arb_cfg = _full_cfg.arbitrage
                except Exception:
                    self._arb_cfg = ArbitrageConfig()
                cfg = self._arb_cfg
                self._arb_pairs: List[Dict] = []
                self._arb_pair_states: Dict[str, Any] = {}
                self._arb_last_discovery: str = ""
                self._arb_trade_history: List[Dict] = []
                self._arb_pair_cooldown: Dict[str, int] = {}
                self._arb_corr_decay_count: Dict[str, int] = {}
                self._arb_day_count: int = 0
                self._arb_mdd_halted: bool = False
                self._arb_mdd_halt_days: int = 0
                self._arb_fixed_pair_defs: List[Dict] = [
                    p for p in cfg.fixed_pairs if p.get("market") == self.market_id
                ]
                self._arb_basis_signals: List[Dict] = [
                    s_item for s_item in cfg.basis_signals if s_item.get("market") == self.market_id
                ]
                self._arb_basis_window_open: bool = False
                self._arb_basis_data: Dict[str, Any] = {}
                for key in ["arb_pairs_scanned", "arb_spreads_detected", "arb_correlation_rejects",
                            "arb_entries", "arb_short_entries", "arb_total_score",
                            "es_arb_sl", "es_arb_tp", "es_arb_corr",
                            "arb_basis_gate_blocks", "arb_basis_window_opens", "arb_fixed_pairs_loaded"]:
                    self._phase_stats.setdefault(key, 0)

            elif s == "defensive":
                # Defensive 전략: 별도 설정 불필요, 인버스 ETF 데이터는 런타임에 확인
                self._phase_stats.setdefault("defensive_entries", 0)
                self._phase_stats.setdefault("defensive_regime_exits", 0)

            # momentum은 별도 설정 불필요 (기본 파라미터 사용)

        # 멀티/레짐 모드 phase stats
        if self.strategy_mode == "multi" or self.strategy_mode in REGIME_STRATEGY_MODES:
            self._phase_stats.setdefault("multi_dedup_skips", 0)

    # ══════════════════════════════════════════
    # 메인 루프
    # ══════════════════════════════════════════

    async def start(self):
        self._is_running = True
        self._started_at = datetime.now().isoformat()
        self._add_risk_event("INFO", "시뮬레이션 엔진 시작 (모의투자)")

        await self._fetch_historical_data()
        self._add_risk_event("INFO", f"OHLCV 데이터 로드 완료 ({len(self._ohlcv_cache)}종목)")

        # 초기 에쿼티 포인트 기록
        self._record_equity_point()

        await self._broadcast_all()

        while self._is_running:
            try:
                await self._run_cycle()
            except Exception as e:
                print(f"[SimEngine] Cycle error: {e}")
            await asyncio.sleep(30)

    async def stop(self):
        self._is_running = False

    async def _run_cycle(self):
        self._cycle_count += 1
        await self._fetch_current_prices()
        self._update_position_prices()
        self._check_exits()

        # Phase 0: 시장 체제 매 사이클 갱신 (UI 표시용)
        self._update_market_regime()
        self._update_stock_regimes()

        if self._cycle_count % 2 == 0:
            self._scan_entries()

        # 에쿼티 커브 스냅샷 (매 10사이클 ≈ 5분)
        if self._cycle_count % 10 == 0:
            self._record_equity_point()

        await self._broadcast_all()

    # ══════════════════════════════════════════
    # 백테스트 인터페이스 (동기식)
    # ══════════════════════════════════════════

    def run_backtest_day(
        self,
        date: str,
        ohlcv_cache: Dict[str, pd.DataFrame],
        current_prices: Dict[str, float],
    ):
        """
        히스토리컬 백테스트용 동기 1일 실행.
        외부에서 OHLCV + 현재가를 주입하면 6-Phase 파이프라인이 그대로 실행된다.
        async 불필요 — asyncio.sleep, SSE broadcast 없음.
        """
        # YYYYMMDD → YYYY-MM-DD 변환하여 백테스트 날짜 설정
        if len(date) == 8:
            self._backtest_date = f"{date[:4]}-{date[4:6]}-{date[6:]}"
        else:
            self._backtest_date = date

        self._ohlcv_cache = ohlcv_cache
        self._current_prices = current_prices

        # 당일 OHLC 추출 — 갭다운 보호용
        self._daily_lows: Dict[str, float] = {}
        self._daily_highs: Dict[str, float] = {}
        self._daily_opens: Dict[str, float] = {}
        for code, df in ohlcv_cache.items():
            if df is not None and not df.empty:
                last = df.iloc[-1]
                if "low" in df.columns and pd.notna(last.get("low")):
                    self._daily_lows[code] = float(last["low"])
                if "high" in df.columns and pd.notna(last.get("high")):
                    self._daily_highs[code] = float(last["high"])
                if "open" in df.columns and pd.notna(last.get("open")):
                    self._daily_opens[code] = float(last["open"])

        # 포지션 현재가 갱신
        self._update_position_prices()

        # Phase 5: 청산 체크 (매수보다 선행)
        self._check_exits()

        # Phase 0: 시장 체제
        self._prev_regime = self._market_regime
        self._update_market_regime()

        # Phase 0.1: 종목별 개별 레짐 갱신 (7일 주기, analytics용)
        self._stock_regimes_updated = False
        self._update_stock_regimes()

        # Phase 0.5: 지수 추세 기반 전략 비중 동적 조정 (multi/레짐 모드)
        if (self.strategy_mode == "multi" or self.strategy_mode in REGIME_STRATEGY_MODES) and self._index_ohlcv:
            self._update_strategy_weights_from_index()

        # 레짐 다운그레이드 감지 → 초과 포지션 ES7 청산 대상 지정
        regime_order = {"BULL": 3, "NEUTRAL": 2, "RANGE_BOUND": 1, "BEAR": 0}
        if regime_order.get(self._market_regime, 2) < regime_order.get(self._prev_regime, 2):
            self._reduce_positions_for_regime()

        # Phase 1~4 + 매수 실행
        self._scan_entries()

        # 보유일수 증가
        for pos in self.positions.values():
            if pos.status == "ACTIVE":
                pos.days_held += 1

        # 에쿼티 기록
        self._record_equity_point()

    def reset_daily_state(self):
        """일일 PnL 리셋 (백테스트에서 매 거래일 시작 시 호출)."""
        self._daily_start_equity = self._get_total_equity()
        self._daily_trade_amount = 0.0

    def update_watchlist(self, new_watchlist: list):
        """동적 워치리스트 교체 (리밸런싱 시 호출)."""
        self._watchlist = new_watchlist
        self._stock_names = {w["code"]: w["name"] for w in new_watchlist}

    def set_rebalance_exits(self, codes: set):
        """리밸런스 탈락 종목을 ES7 청산 대상으로 지정."""
        self._rebalance_exit_codes = set(codes)

    def _get_current_date_str(self) -> str:
        """현재 날짜 문자열. 백테스트 시 시뮬레이션 날짜, 실시간 시 오늘 날짜."""
        if self._backtest_date:
            return self._backtest_date
        return datetime.now().strftime("%Y-%m-%d")

    # 시장별 거래 시간 (현지 시각 기준)
    _MARKET_HOURS = {
        "kospi":  {"open_min": 9 * 60,       "duration": 390},  # 09:00~15:30 KST (390분)
        "sp500":  {"open_min": 9 * 60 + 30,  "duration": 390},  # 09:30~16:00 ET  (390분)
        "ndx":    {"open_min": 9 * 60 + 30,  "duration": 390},  # 09:30~16:00 ET  (390분)
    }

    def _get_current_iso(self) -> str:
        """현재 ISO 타임스탬프. 백테스트 시 시뮬레이션 날짜 기반.
        주문 카운터를 활용해 시장별 거래 시간 범위에서 시간 분산."""
        if self._backtest_date:
            hours = self._MARKET_HOURS.get(self.market_id, self._MARKET_HOURS["kospi"])
            total_minutes = hours["open_min"] + (self._order_counter * 17) % hours["duration"]
            hour = total_minutes // 60
            minute = total_minutes % 60
            return f"{self._backtest_date}T{hour:02d}:{minute:02d}:00"
        return datetime.now().isoformat()

    # ══════════════════════════════════════════
    # 데이터 수집
    # ══════════════════════════════════════════

    # yfinance 세션 충돌 방지: 스레드 레벨 락 (멀티 엔진 동시 다운로드 차단)
    import threading
    _yf_thread_lock = threading.Lock()

    async def _fetch_historical_data(self):
        import yfinance as yf

        # 인버스 ETF + 안전자산 ETF 함께 다운로드 (Defensive 전략용)
        extra_items = []
        market_key = self.market_id
        if market_key == "ndx":
            market_key = "nasdaq"
        for inv_ticker in INVERSE_ETFS.get(market_key, []):
            inv_code = inv_ticker.replace(".KS", "")
            if not any(w["code"] == inv_code for w in self._watchlist):
                extra_items.append({"code": inv_code, "ticker": inv_ticker, "name": f"INV_{inv_ticker}"})
        # CRISIS 방어용 안전자산 ETF도 추가
        for item in SAFE_HAVEN_ETFS.get(market_key, []):
            sh_ticker = item["ticker"]
            sh_code = sh_ticker.replace(".KS", "")
            if not any(w["code"] == sh_code for w in self._watchlist):
                if not any(e["code"] == sh_code for e in extra_items):
                    extra_items.append({"code": sh_code, "ticker": sh_ticker, "name": item["name"]})

        all_items = list(self._watchlist) + extra_items

        BATCH_SIZE = 20
        loop = asyncio.get_event_loop()
        failed_tickers = []

        for i in range(0, len(all_items), BATCH_SIZE):
            batch = all_items[i:i + BATCH_SIZE]
            tickers_str = " ".join(w["ticker"] for w in batch)

            try:
                def _download_batch(t=tickers_str):
                    with SimulationEngine._yf_thread_lock:
                        # yfinance 내부 캐시 클리어 (마켓 간 데이터 오염 방지)
                        yf.shared._DFS.clear()
                        yf.shared._ERRORS.clear()
                        return yf.download(t, period="1y", interval="1d", progress=False)

                data = await loop.run_in_executor(None, _download_batch)
            except Exception as e:
                print(f"[SimEngine:{self.market_id}] Batch {i // BATCH_SIZE + 1} fetch failed: {e}")
                failed_tickers.extend(w["ticker"] for w in batch)
                continue

            if data.empty:
                failed_tickers.extend(w["ticker"] for w in batch)
                continue

            # 타임존 안전 처리 (Fix 6)
            if hasattr(data.index, 'tz') and data.index.tz is not None:
                if self.market_id == "kospi":
                    data.index = data.index.tz_convert("Asia/Seoul")
                data.index = data.index.tz_localize(None)

            # yfinance 캐시 오염 감지: 반환된 티커가 요청 티커와 일치하는지 확인
            batch_tickers = {w["ticker"] for w in batch}
            if isinstance(data.columns, pd.MultiIndex):
                returned_tickers = set(data.columns.get_level_values(1).unique().tolist())
                if not batch_tickers.intersection(returned_tickers):
                    print(f"[SimEngine:{self.market_id}] ⚠ 배치 데이터 오염 감지 — 개별 다운로드로 전환")
                    failed_tickers.extend(w["ticker"] for w in batch)
                    continue

            for w in batch:
                try:
                    if isinstance(data.columns, pd.MultiIndex):
                        stock_df = pd.DataFrame(
                            {
                                "open": data[("Open", w["ticker"])],
                                "high": data[("High", w["ticker"])],
                                "low": data[("Low", w["ticker"])],
                                "close": data[("Close", w["ticker"])],
                                "volume": data[("Volume", w["ticker"])],
                            }
                        ).dropna()
                    else:
                        stock_df = data.rename(columns=str.lower)

                    if stock_df.empty:
                        print(f"[SimEngine:{self.market_id}] ✗ {w['ticker']}: 0 rows after dropna (delisted?)")
                        continue
                    self._ohlcv_cache[w["code"]] = stock_df
                    self._current_prices[w["code"]] = float(stock_df["close"].iloc[-1])
                except Exception as e:
                    print(f"[SimEngine:{self.market_id}] ✗ {w['ticker']}: {type(e).__name__}: {e}")
                    failed_tickers.append(w["ticker"])

        # 실패 종목 개별 재시도 (yf.Ticker.history 사용 — _DFS 오염 회피)
        retry_items = [w for w in all_items if w["ticker"] in failed_tickers and w["code"] not in self._ohlcv_cache]
        if retry_items:
            print(f"[SimEngine:{self.market_id}] 개별 재시도: {len(retry_items)}종목")
        for idx, w in enumerate(retry_items):
            try:
                # Yahoo 레이트 리밋 회피: 10종목마다 1초 대기
                if idx > 0 and idx % 10 == 0:
                    await asyncio.sleep(1)

                def _retry_ticker(t=w["ticker"]):
                    ticker_obj = yf.Ticker(t)
                    return ticker_obj.history(period="1y", interval="1d")

                data = await loop.run_in_executor(None, _retry_ticker)
                if data is not None and not data.empty:
                    if hasattr(data.index, 'tz') and data.index.tz is not None:
                        if self.market_id == "kospi":
                            data.index = data.index.tz_convert("Asia/Seoul")
                        data.index = data.index.tz_localize(None)

                    stock_df = data.rename(columns=str.lower)
                    # history()는 'dividends', 'stock splits' 등도 포함 → OHLCV만 추출
                    ohlcv_cols = ["open", "high", "low", "close", "volume"]
                    available = [c for c in ohlcv_cols if c in stock_df.columns]
                    if len(available) >= 4:
                        stock_df = stock_df[available].dropna()
                        if not stock_df.empty:
                            self._ohlcv_cache[w["code"]] = stock_df
                            self._current_prices[w["code"]] = float(stock_df["close"].iloc[-1])
                        else:
                            print(f"[SimEngine:{self.market_id}] ✗ {w['ticker']}: 재시도 후에도 0 rows")
                    else:
                        print(f"[SimEngine:{self.market_id}] ✗ {w['ticker']}: OHLCV 컬럼 부족")
                else:
                    print(f"[SimEngine:{self.market_id}] ✗ {w['ticker']}: 재시도 후에도 데이터 없음")
            except Exception as e:
                print(f"[SimEngine:{self.market_id}] ✗ {w['ticker']}: 재시도 실패 {type(e).__name__}: {e}")

        total = len(all_items)
        loaded = len(self._ohlcv_cache)
        if loaded < total:
            print(f"[SimEngine:{self.market_id}] ⚠ 데이터 로드: {loaded}/{total}종목 ({total - loaded}종목 실패)")
        else:
            print(f"[SimEngine:{self.market_id}] 데이터 로드 완료: {loaded}/{total}종목")

    async def _fetch_current_prices(self):
        import yfinance as yf

        tickers = " ".join(w["ticker"] for w in self._watchlist)
        loop = asyncio.get_event_loop()
        try:
            data = await loop.run_in_executor(
                None,
                lambda: yf.download(tickers, period="1d", interval="1m", progress=False),
            )
            if data.empty:
                return

            for w in self._watchlist:
                try:
                    if isinstance(data.columns, pd.MultiIndex):
                        close_series = data[("Close", w["ticker"])].dropna()
                    else:
                        close_series = data["Close"].dropna()
                    if not close_series.empty:
                        self._current_prices[w["code"]] = float(close_series.iloc[-1])
                except Exception:
                    pass
        except Exception:
            pass  # 다음 사이클에 재시도

    # ══════════════════════════════════════════
    # 지표 계산 (momentum_swing.py 복제)
    # ══════════════════════════════════════════

    def _calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        from simulation.indicators import calculate_indicators
        return calculate_indicators(self, df)

    # ══════════════════════════════════════════
    # Phase 0: 시장 체제 판단 (TradingLogicFlow.md)
    # ══════════════════════════════════════════

    def _judge_market_regime(self) -> str:
        from simulation.regime import judge_market_regime
        return judge_market_regime(self)

    def _smooth_regime(self, raw_regime: str) -> str:
        from simulation.regime import smooth_regime
        return smooth_regime(self, raw_regime)

    def _update_market_regime(self):
        """레짐 감지 + 레짐 고정 모드 오버라이드.

        실제 감지 레짐은 _actual_market_regime에 보존 (UI 표시용).
        레짐 고정 모드(_regime_locked)일 때 _market_regime을 locked 값으로 덮어씀.
        """
        detected = self._judge_market_regime()
        self._actual_market_regime = detected  # 실제 감지 보존
        if self._regime_locked:
            self._market_regime = self._locked_regime  # 고정 레짐 적용
        else:
            self._market_regime = detected

    def update_vix(self, vix_value: float):
        """VIX 값 업데이트 (외부에서 주입: 백테스트 or 실시간)."""
        if vix_value <= 0:
            return
        self._vix_level = vix_value
        self._vix_history.append(vix_value)
        # 20일 EMA 계산
        if len(self._vix_history) >= 20:
            alpha = 2.0 / (20 + 1)
            self._vix_ema20 = self._vix_ema20 * (1 - alpha) + vix_value * alpha
        else:
            # 워밍업 중 — 단순 평균
            self._vix_ema20 = sum(self._vix_history) / len(self._vix_history)

    # ══════════════════════════════════════════
    # 지수 데이터 기반 자동 전략 선택
    # ══════════════════════════════════════════

    def update_index_data(self, date: str, ohlcv: Dict):
        """지수 OHLCV 데이터 주입 (백테스트/실시간 공용).

        Args:
            date: YYYYMMDD
            ohlcv: {"open": float, "high": float, "low": float, "close": float, "volume": float}
        """
        self._index_ohlcv.append(ohlcv)
        # 최대 260일 보관 (MA200 + buffer)
        if len(self._index_ohlcv) > 260:
            self._index_ohlcv = self._index_ohlcv[-260:]

    def _analyze_index_trend(self) -> Dict:
        from simulation.regime import analyze_index_trend
        return analyze_index_trend(self)

    def _update_strategy_weights_from_index(self):
        from simulation.regime import update_strategy_weights_from_index
        update_strategy_weights_from_index(self)

    def get_market_intelligence(self) -> Dict:
        """프론트엔드용 마켓 인텔리전스 데이터 반환."""
        trend_key = (self._index_trend or {}).get("trend", self._market_regime)
        return {
            "index_trend": self._index_trend or {
                "trend": "NEUTRAL", "ma_alignment": "MIXED",
                "momentum_score": 50.0, "volatility_state": "NORMAL",
                "signals": ["데이터 대기 중"],
            },
            "strategy_weights": (
                dict(self._strategy_allocator.weights)
                if self._strategy_allocator else {}
            ),
            "strategy_composition": REGIME_STRATEGY_COMPOSITION.get(
                trend_key, REGIME_STRATEGY_COMPOSITION.get("NEUTRAL", {})
            ),
            "vix_ema20": round(self._vix_ema20, 1),
            "market_regime": self._market_regime,
            "actual_market_regime": self._actual_market_regime,
            "regime_locked": self._regime_locked,
            "locked_regime": self._locked_regime,
            "trend_history": self._index_trend_history[-10:],
            "active_strategy_label": REGIME_DISPLAY_NAMES.get(
                trend_key, REGIME_DISPLAY_NAMES.get("NEUTRAL")
            ),
        }

    def _get_vix_sizing_mult(self, strategy: str = "momentum") -> float:
        from simulation.sizing import get_vix_sizing_mult
        return get_vix_sizing_mult(self._vix_ema20, strategy)

    def _reduce_positions_for_regime(self):
        """레짐 다운그레이드 시 초과 포지션을 PnL 하위부터 ES7 청산."""
        regime_params = REGIME_PARAMS.get(self._market_regime, REGIME_PARAMS["NEUTRAL"])
        max_pos = regime_params["max_positions"]
        active = [
            (code, pos) for code, pos in self.positions.items()
            if pos.status == "ACTIVE"
        ]
        if len(active) <= max_pos:
            return

        # PnL 하위부터 초과분 선택
        active_sorted = sorted(active, key=lambda x: x[1].pnl_pct)
        excess_count = len(active) - max_pos
        for code, pos in active_sorted[:excess_count]:
            self._rebalance_exit_codes.add(code)

    # ══════════════════════════════════════════
    # Phase 1: 추세 확인 (TradingLogicFlow.md)
    # ══════════════════════════════════════════

    def _confirm_trend(self, df: pd.DataFrame) -> dict:
        from simulation.indicators import confirm_trend
        return confirm_trend(df)

    # ══════════════════════════════════════════
    # Phase 2: 추세 위치 파악 (TradingLogicFlow.md)
    # ══════════════════════════════════════════

    def _estimate_trend_stage(self, df: pd.DataFrame) -> str:
        from simulation.indicators import estimate_trend_stage
        return estimate_trend_stage(df)

    # ══════════════════════════════════════════
    # Phase 2.5: 종목별 레짐 분류 (Per-Stock Regime)
    # ══════════════════════════════════════════

    def _classify_stock_regime(self, df: pd.DataFrame) -> str:
        from simulation.regime import classify_stock_regime
        return classify_stock_regime(self, df)

    def _update_stock_regimes(self, force: bool = False):
        """워치리스트 종목의 개별 레짐 갱신. 성능을 위해 7일 주기로 실행."""
        if self._stock_regimes_updated:
            return  # 이미 이번 사이클에서 갱신됨 → 스킵
        self._stock_regimes_updated = True

        # 7일 주기로만 전체 재분류 (성능 최적화)
        self._stock_regime_counter = getattr(self, "_stock_regime_counter", 0) + 1
        if not force and self._stock_regimes and self._stock_regime_counter % 7 != 1:
            return  # 캐시된 결과 사용

        for w in self._watchlist:
            code = w["code"]
            df = self._ohlcv_cache.get(code)
            if df is not None and len(df) >= 200:
                self._stock_regimes[code] = self._classify_stock_regime(df)
            else:
                self._stock_regimes[code] = "NEUTRAL"  # 데이터 부족 → 중립

        # 분포 집계 (PhaseStats)
        dist: Dict[str, int] = {}
        for regime in self._stock_regimes.values():
            dist[regime] = dist.get(regime, 0) + 1
        self._phase_stats["stock_regime_distribution"] = dist

    # ══════════════════════════════════════════
    # Phase 4: 리스크 게이트 (TradingLogicFlow.md)
    # ══════════════════════════════════════════

    def _risk_gate_check(self) -> tuple:
        from simulation.risk_gates import risk_gate_check
        return risk_gate_check(self)

    def _force_liquidate_all(self, reason: str):
        """DD>20% 시 모든 ACTIVE 포지션 강제 청산."""
        for code in list(self.positions.keys()):
            pos = self.positions[code]
            if pos.status == "ACTIVE":
                self._rebalance_exit_codes.add(code)

    def force_liquidate_all_immediate(self) -> dict:
        """사용자 긴급 청산: 모든 ACTIVE 포지션을 현재가로 즉시 청산."""
        closed = []
        codes_to_remove = []
        for code in list(self.positions.keys()):
            pos = self.positions[code]
            if pos.status == "ACTIVE":
                sell_price = pos.current_price if pos.current_price > 0 else pos.entry_price
                self._execute_sell(pos, sell_price, "FORCE_LIQUIDATE 사용자 긴급 청산", "FORCE_LIQUIDATE")
                closed.append({
                    "stock_code": pos.stock_code,
                    "stock_name": pos.stock_name,
                    "quantity": pos.quantity,
                    "sell_price": sell_price,
                    "entry_price": pos.entry_price,
                })
                codes_to_remove.append(code)
        for code in codes_to_remove:
            del self.positions[code]
        return {"positions_closed": len(closed), "details": closed}

    def _detect_bearish_divergence(self, df: pd.DataFrame, lookback: int = 10) -> bool:
        from simulation.risk_gates import detect_bearish_divergence
        return detect_bearish_divergence(df, lookback)

    def _detect_support_resistance(self, df: pd.DataFrame, lookback: int = 40) -> dict:
        from simulation.risk_gates import detect_support_resistance
        return detect_support_resistance(df, lookback)

    @staticmethod
    def _cluster_levels(levels: list, tolerance: float = 0.015) -> list:
        from simulation.risk_gates import cluster_levels
        return cluster_levels(levels, tolerance)

    # ══════════════════════════════════════════
    # 진입 시그널 스캔 (6-Phase 통합 파이프라인)
    # ══════════════════════════════════════════

    def _scan_entries(self):
        """
        전략 모드에 따라 진입 스캔 분기.
        multi: 멀티 전략 동시 실행 (레짐별 비중 기반, 자동 전환)
        regime_*: 레짐 고정 + multi 파이프라인 (개별 레짐 전략 테스트)
        momentum/smc/breakout_retest/mean_reversion/arbitrage/defensive: 단일 전략
        """
        if self.strategy_mode == "multi" or self.strategy_mode in REGIME_STRATEGY_MODES:
            return self._scan_entries_multi()
        elif self.strategy_mode == "smc":
            return self._scan_entries_smc()
        elif self.strategy_mode == "breakout_retest":
            return self._scan_entries_breakout_retest()
        elif self.strategy_mode == "mean_reversion":
            return self._scan_entries_mean_reversion()
        elif self.strategy_mode == "arbitrage":
            return self._scan_entries_arbitrage()
        elif self.strategy_mode == "defensive":
            return self._scan_entries_defensive()
        return self._scan_entries_momentum()

    def _scan_entries_multi(self):
        """
        Phase 4 리팩토링: 시그널 수집 → 종목 중복 제거 → 실행.

        1. 모든 활성 전략에서 시그널만 수집 (_collect_mode=True)
        2. 같은 종목 → 최고 strength 시그널만 선택
        3. 선택된 시그널을 전략별 예산 한도 내에서 실행
        """
        allocator = self._strategy_allocator
        if allocator is None:
            return

        # 레짐 갱신 → 전략 비중 재조정
        allocator.update_regime(self._market_regime)

        # Volatility Targeting: 일일 수익률 기록
        total_equity = self._get_total_equity()
        allocator.update_daily_return(total_equity)

        # Phase 3.1: 전략간 상관관계 갱신 (5일마다)
        if len(allocator._daily_returns) % 5 == 0:
            allocator.update_correlation()
            # Phase 7: Risk Parity 비중 갱신 (correlation과 동일 주기)
            allocator.update_risk_parity()

        # Phase 3.4: Dynamic Kelly 갱신
        allocator.update_kelly(self._vix_ema20)

        # Phase 3.1: 전략별 일일 PnL 기록
        for strategy in allocator.strategies:
            strat_pnl = sum(
                (pos.current_price - pos.entry_price) / pos.entry_price * pos.quantity * pos.entry_price
                for pos in self.positions.values()
                if pos.status == "ACTIVE" and pos.strategy_tag == strategy
            )
            allocator.record_strategy_daily_pnl(strategy, strat_pnl)

        # ── Phase 4.3: Day-start 예산 사전 계산 ──
        used_per_strategy: Dict[str, float] = {}
        pos_count_per_strategy: Dict[str, int] = {}
        for pos in self.positions.values():
            if pos.status == "ACTIVE":
                tag = pos.strategy_tag
                used_per_strategy[tag] = used_per_strategy.get(tag, 0) + pos.quantity * pos.current_price
                pos_count_per_strategy[tag] = pos_count_per_strategy.get(tag, 0) + 1

        regime_params = REGIME_PARAMS.get(self._market_regime, REGIME_PARAMS["NEUTRAL"])
        pos_dist = allocator.distribute_positions(regime_params["max_positions"])

        # 전략별 사전 예산 (고정, 실행 중 다른 전략 예산 침범 불가)
        day_budgets: Dict[str, float] = {}
        for strategy in allocator.strategies:
            weight = allocator.weights.get(strategy, 0.0)
            day_budgets[strategy] = max(0.0, total_equity * weight - used_per_strategy.get(strategy, 0.0))

        # ── 1단계: 모든 전략에서 시그널 수집 (실행 없음) ──
        self._collected_signals: List[tuple] = []  # (strategy, signal, trend_str, trend_stage, align)
        self._collect_mode = True

        sorted_strategies = sorted(
            allocator.strategies,
            key=lambda s: allocator.weights.get(s, 0),
            reverse=True,
        )

        for strategy in sorted_strategies:
            if not allocator.is_active(strategy):
                continue
            if day_budgets.get(strategy, 0) <= 0:
                continue
            max_pos = pos_dist.get(strategy, 1)
            if pos_count_per_strategy.get(strategy, 0) >= max_pos:
                continue

            original_mode = self.strategy_mode
            self.strategy_mode = strategy

            if strategy == "momentum":
                self._scan_entries_momentum()
            elif strategy == "smc":
                self._scan_entries_smc()
            elif strategy == "breakout_retest":
                self._scan_entries_breakout_retest()
            elif strategy == "mean_reversion":
                self._scan_entries_mean_reversion()
            elif strategy == "defensive":
                self._scan_entries_defensive()
            elif strategy == "volatility":
                self._scan_entries_volatility()
            elif strategy == "arbitrage":
                self._scan_entries_arbitrage()

            self.strategy_mode = original_mode

        self._collect_mode = False

        # ── 2단계: 종목별 최적 시그널 선택 ──
        # 글로벌 레짐 비중으로 라우팅 (종목별 레짐은 exit/sizing에만 사용)
        best_per_stock: Dict[str, tuple] = {}
        for sig_tuple in self._collected_signals:
            strategy, signal = sig_tuple[0], sig_tuple[1]
            code = signal.stock_code

            if code not in best_per_stock:
                best_per_stock[code] = sig_tuple
            else:
                existing_strategy = best_per_stock[code][0]
                existing_weight = allocator.weights.get(existing_strategy, 0)
                new_weight = allocator.weights.get(strategy, 0)
                # 비중 차이가 10%p 이상이면 비중 높은 전략 우선
                if new_weight > existing_weight + 0.10:
                    best_per_stock[code] = sig_tuple
                elif abs(new_weight - existing_weight) <= 0.10:
                    # 비중 비슷하면 strength 비교
                    if signal.strength > best_per_stock[code][1].strength:
                        best_per_stock[code] = sig_tuple

        dedup_skips = len(self._collected_signals) - len(best_per_stock)
        if dedup_skips > 0:
            self._phase_stats["multi_dedup_skips"] += dedup_skips

        # ── 2.5단계: 유휴 예산은 재분배하지 않음 ──
        # 미사용 예산을 재분배하면 momentum 과잉 배분 → 저품질 진입 증가
        # 비활성 전략 예산은 현금으로 유보 (자연스러운 포지션 사이징 제약)

        # ── 3단계: 선택된 시그널을 전략별 예산 한도 내에서 실행 ──
        sorted_signals = sorted(best_per_stock.values(), key=lambda x: x[1].strength, reverse=True)

        exec_count_per_strategy: Dict[str, int] = {}
        for sig_tuple in sorted_signals:
            strategy, signal, trend_str, trend_stage, align = sig_tuple
            if day_budgets.get(strategy, 0) <= 0:
                continue
            max_pos = pos_dist.get(strategy, 1)
            current_count = pos_count_per_strategy.get(strategy, 0) + exec_count_per_strategy.get(strategy, 0)
            if current_count >= max_pos:
                continue

            original_mode = self.strategy_mode
            self.strategy_mode = strategy
            self._execute_buy(signal, trend_strength=trend_str,
                             trend_stage=trend_stage, alignment_score=align)
            self.strategy_mode = original_mode

            exec_count_per_strategy[strategy] = exec_count_per_strategy.get(strategy, 0) + 1

            # 종목 레짐→전략 라우팅 이력 기록
            _sig_stock_regime = self._stock_regimes.get(signal.stock_code, self._market_regime)
            rsm = self._phase_stats["stock_regime_strategy_map"]
            rsm_key = f"{_sig_stock_regime}→{strategy}"
            rsm[rsm_key] = rsm.get(rsm_key, 0) + 1

        self._collected_signals = []

    # ── Phase 3.3: Defensive 전략 (인버스 ETF) ──

    def _scan_entries_defensive(self):
        from simulation.strategies.defensive import scan_entries
        scan_entries(self)

    def _check_exits_defensive(self):
        from simulation.strategies.defensive import check_exits
        check_exits(self)

    # ─────────────────────────────────────────────────────
    # Phase 6: Volatility Premium Strategy
    # ─────────────────────────────────────────────────────

    def _scan_entries_volatility(self):
        from simulation.strategies.volatility import scan_entries
        scan_entries(self)

    def _check_exits_volatility(self):
        from simulation.strategies.volatility import check_exits
        check_exits(self)

    def _scan_entries_momentum(self):
        from simulation.strategies.momentum import scan_entries
        scan_entries(self)

    # ══════════════════════════════════════════
    # SMC 4-Layer 진입 스캔
    # ══════════════════════════════════════════

    def _scan_entries_smc(self):
        from simulation.strategies.smc import scan_entries
        scan_entries(self)

    def _calculate_indicators_smc(self, df: pd.DataFrame) -> pd.DataFrame:
        from simulation.strategies.smc import calculate_indicators_smc
        return calculate_indicators_smc(self, df)

    def _score_smc_bias(self, df: pd.DataFrame) -> int:
        from simulation.strategies.smc import score_smc_bias
        return score_smc_bias(self, df)

    def _score_volatility(self, df: pd.DataFrame) -> int:
        from simulation.strategies.smc import score_volatility
        return score_volatility(self, df)

    def _score_obv_signal(self, df: pd.DataFrame) -> int:
        from simulation.strategies.smc import score_obv_signal
        return score_obv_signal(self, df)

    def _score_momentum_signal(self, df: pd.DataFrame) -> int:
        from simulation.strategies.smc import score_momentum_signal
        return score_momentum_signal(self, df)

    # ══════════════════════════════════════════
    # SMC 청산 로직
    # ══════════════════════════════════════════

    def _check_exits_smc(self):
        from simulation.strategies.smc import check_exits
        check_exits(self)

    # ══════════════════════════════════════════
    # Mean Reversion 지표/진입/청산 로직
    # ══════════════════════════════════════════

    def _calculate_indicators_mean_reversion(self, df: pd.DataFrame) -> pd.DataFrame:
        from simulation.strategies.mean_reversion import calculate_indicators_mean_reversion
        return calculate_indicators_mean_reversion(self, df)

    def _score_mr_signal(self, df: pd.DataFrame) -> int:
        from simulation.strategies.mean_reversion import score_mr_signal
        return score_mr_signal(self, df)

    def _score_mr_volatility(self, df: pd.DataFrame) -> int:
        from simulation.strategies.mean_reversion import score_mr_volatility
        return score_mr_volatility(self, df)

    def _score_mr_confirmation(self, df: pd.DataFrame) -> int:
        from simulation.strategies.mean_reversion import score_mr_confirmation
        return score_mr_confirmation(self, df)

    def _scan_entries_mean_reversion(self):
        from simulation.strategies.mean_reversion import scan_entries
        scan_entries(self)

    def _check_exits_mean_reversion(self):
        from simulation.strategies.mean_reversion import check_exits
        check_exits(self)

    # ══════════════════════════════════════════
    # Breakout-Retest 지표/진입/청산 로직
    # (extracted to simulation/strategies/breakout_retest.py)
    # ══════════════════════════════════════════

    def _calculate_indicators_breakout_retest(self, df: pd.DataFrame) -> pd.DataFrame:
        from simulation.strategies.breakout_retest import calculate_indicators_breakout_retest
        return calculate_indicators_breakout_retest(self, df)

    def _score_brt_structure(self, df: pd.DataFrame) -> int:
        from simulation.strategies.breakout_retest import score_brt_structure
        return score_brt_structure(self, df)

    def _score_brt_volatility(self, df: pd.DataFrame) -> int:
        from simulation.strategies.breakout_retest import score_brt_volatility
        return score_brt_volatility(self, df)

    def _score_brt_obv(self, df: pd.DataFrame) -> int:
        from simulation.strategies.breakout_retest import score_brt_obv
        return score_brt_obv(self, df)

    def _score_brt_momentum(self, df: pd.DataFrame) -> int:
        from simulation.strategies.breakout_retest import score_brt_momentum
        return score_brt_momentum(self, df)

    def _check_brt_six_conditions(self, df: pd.DataFrame) -> tuple:
        from simulation.strategies.breakout_retest import check_brt_six_conditions
        return check_brt_six_conditions(self, df)

    def _apply_brt_fakeout_filters(self, df: pd.DataFrame) -> tuple:
        from simulation.strategies.breakout_retest import apply_brt_fakeout_filters
        return apply_brt_fakeout_filters(self, df)

    def _capture_brt_retest_zones(self, df: pd.DataFrame, breakout_price: float, breakout_atr: float) -> Dict[str, Any]:
        from simulation.strategies.breakout_retest import capture_brt_retest_zones
        return capture_brt_retest_zones(self, df, breakout_price, breakout_atr)

    def _scan_entries_breakout_retest(self):
        from simulation.strategies.breakout_retest import scan_entries
        scan_entries(self)

    def _score_brt_retest_zone(self, df: pd.DataFrame, state: Dict[str, Any]) -> int:
        from simulation.strategies.breakout_retest import score_brt_retest_zone
        return score_brt_retest_zone(self, df, state)

    def _check_exits_breakout_retest(self):
        from simulation.strategies.breakout_retest import check_exits
        check_exits(self)


    # ══════════════════════════════════════════
    # Arbitrage: Statistical Pairs (Long+Short 양방향)
    # 이론 참조: futuresStrategy.md (Z-Score), BlackScholesEquation.md (IV/RV),
    #           future_trading_stratedy.md (Dynamic ATR), Kelly Criterion.md
    # ══════════════════════════════════════════

    def _discover_pairs(self) -> List[Dict]:
        from simulation.strategies.arbitrage import discover_pairs
        return discover_pairs(self)

    def _load_fixed_pairs(self) -> List[Dict]:
        from simulation.strategies.arbitrage import load_fixed_pairs
        return load_fixed_pairs(self)

    def _check_basis_gate(self) -> bool:
        from simulation.strategies.arbitrage import check_basis_gate
        return check_basis_gate(self)

    def _score_arb_correlation(self, pair: Dict) -> int:
        from simulation.strategies.arbitrage import score_arb_correlation
        return score_arb_correlation(self, pair)

    def _score_arb_spread(self, pair: Dict) -> int:
        from simulation.strategies.arbitrage import score_arb_spread
        return score_arb_spread(self, pair)

    def _score_arb_volume(self, pair: Dict) -> int:
        from simulation.strategies.arbitrage import score_arb_volume
        return score_arb_volume(self, pair)

    def _calculate_arb_ev(self, pair: Dict) -> bool:
        from simulation.strategies.arbitrage import calculate_arb_ev
        return calculate_arb_ev(self, pair)

    def _size_arb_pair(self, price_a: float, price_b: float, score: int) -> tuple:
        from simulation.strategies.arbitrage import size_arb_pair
        return size_arb_pair(self, price_a, price_b, score)

    def _scan_entries_arbitrage(self):
        from simulation.strategies.arbitrage import scan_entries
        scan_entries(self)

    def _check_exits_arbitrage(self):
        from simulation.strategies.arbitrage import check_exits
        check_exits(self)


    def _execute_buy(
        self,
        signal: SimSignal,
        trend_strength: str = "MODERATE",
        trend_stage: str = "MID",
        alignment_score: int = 3,
    ):
        # Phase 4.6: 수집 모드 — 실행하지 않고 시그널만 저장
        if getattr(self, '_collect_mode', False):
            self._collected_signals.append(
                (self.strategy_mode, signal, trend_strength, trend_stage, alignment_score)
            )
            return

        total_equity = self._get_total_equity()
        regime_params = REGIME_PARAMS.get(self._market_regime, REGIME_PARAMS["NEUTRAL"])
        price = signal.price

        # ── 멀티 전략 모드: 슬리브 체크 ──
        if self._strategy_allocator is not None:
            strategy = self.strategy_mode  # 임시 전환된 상태
            pos_count = sum(
                1 for p in self.positions.values()
                if p.status == "ACTIVE" and p.strategy_tag == strategy
            )
            max_pos = self._strategy_allocator.get_max_positions(
                strategy, regime_params["max_positions"]
            )
            if pos_count >= max_pos:
                return
            # 코어(momentum): 전체 equity 사용, 위성 전략: 슬리브 예산 제한
            if strategy != "momentum":
                used = sum(
                    p.quantity * p.current_price
                    for p in self.positions.values()
                    if p.status == "ACTIVE" and p.strategy_tag == strategy
                )
                budget = self._strategy_allocator.get_budget(strategy, total_equity, used)
                if budget <= 0:
                    return

        # Fix 2: 레짐별 시그널 품질 게이트 (BULL 과진입 방지)
        min_strength = self._REGIME_MIN_STRENGTH.get(self._market_regime, 45)
        if signal.strength < min_strength:
            self._phase_stats["regime_quality_blocks"] += 1
            return

        if self.fixed_amount_per_stock > 0:
            # ── 고정 사이징 모드: 종목당 고정 금액 ──
            quantity = int(self.fixed_amount_per_stock / price)
        else:
            # ── ATR 기반 리스크 패리티 포지션 사이징 (BR-P04: 1.5%) ──
            risk_per_trade = total_equity * 0.015

            # ATR 조회
            df = self._ohlcv_cache.get(signal.stock_code)
            atr_val = None
            if df is not None and len(df) > 14:
                if "atr" not in df.columns:
                    df = self._calculate_indicators(df.copy())
                    self._ohlcv_cache[signal.stock_code] = df
                last_atr = df.iloc[-1].get("atr")
                if pd.notna(last_atr):
                    atr_val = float(last_atr)

            if atr_val and atr_val > 0:
                stop_distance = max(atr_val, price * 0.05)  # 최소 ES1 5%
            else:
                stop_distance = price * 0.05

            raw_quantity = risk_per_trade / stop_distance

            # Phase 4.4: 사이징 승수 4개로 단순화 (기존 8개 → 4개)
            # quality: 시그널 품질 (0.6~1.3)
            quality_mult = max(0.6, min(signal.strength / 70.0, 1.3))

            # vix: 변동성 기반 스케일러 (전략별 차별화)
            current_strategy = self.strategy_mode if self.strategy_mode != "multi" else "momentum"
            vix_mult = self._get_vix_sizing_mult(current_strategy)

            # vol: 포트폴리오 변동성 타겟팅 (0.3~1.5)
            vol_mult = 1.0
            if self._strategy_allocator is not None:
                vol_mult = self._strategy_allocator.get_vol_scalar()

            # risk: DD 단계적 감축 (0.5~1.0)
            risk_mult = self._dd_sizing_mult

            # 글로벌 레짐 Kelly Fraction 기반 사이징 (종목별 레짐은 analytics용)
            # kelly_fraction / BASE_KELLY → STRONG_BULL ×1.50, BULL ×1.30, ... CRISIS ×0.50
            _regime_ov = REGIME_OVERRIDES.get(self._market_regime, {})
            kelly_f = _regime_ov.get("kelly_fraction", BASE_KELLY)
            regime_sizing = kelly_f / BASE_KELLY  # 0.75/0.5=1.5, 0.25/0.5=0.5
            if kelly_f != BASE_KELLY:
                self._phase_stats.setdefault("regime_sizing_reductions", 0)
                self._phase_stats["regime_sizing_reductions"] += 1

            quantity = int(raw_quantity * quality_mult * vix_mult * vol_mult * risk_mult * regime_sizing)

            # 최대 가중치 제한 (활성 포지션 수 기반 동적 비중)
            if self._allocator:
                active_count = sum(1 for p in self.positions.values() if p.status == "ACTIVE")
                if active_count <= 3:
                    # 소수 보유: Kelly / (보유+1) → 0: 30%, 1: 15%, 2: 10%, 3: 7.5%
                    dynamic_weight = self._allocator.config.kelly_fraction / max(active_count + 1, 2)
                    tactical_weight = min(dynamic_weight, regime_params["max_weight"])
                else:
                    tactical_weight = self._allocator.get_tactical_max_weight(total_equity)
                max_amount = total_equity * min(tactical_weight, regime_params["max_weight"])
            else:
                max_amount = total_equity * regime_params["max_weight"]

            # 멀티 모드: 위성 전략은 슬리브 예산으로 추가 제한 (코어는 제한 없음)
            if self._strategy_allocator is not None and self.strategy_mode != "momentum":
                strategy = self.strategy_mode
                used = sum(
                    p.quantity * p.current_price
                    for p in self.positions.values()
                    if p.status == "ACTIVE" and p.strategy_tag == strategy
                )
                sleeve_budget = self._strategy_allocator.get_budget(strategy, total_equity, used)
                max_amount = min(max_amount, sleeve_budget)

            if quantity * price > max_amount:
                quantity = int(max_amount / price)

        # 현금 제약 (1-2종목이면 현금 비율 완화)
        effective_cash_ratio = self.min_cash_ratio
        if self._allocator:
            active_count_cash = sum(1 for p in self.positions.values() if p.status == "ACTIVE")
            if active_count_cash <= 2:
                effective_cash_ratio = max(0.50, self.min_cash_ratio - 0.20)
        min_cash = total_equity * effective_cash_ratio
        available = self.cash - min_cash
        if available <= 0 or quantity <= 0:
            return
        if quantity * price > available:
            quantity = int(available / price)
        if quantity <= 0:
            return

        # 슬리피지 + 수수료 적용
        effective_price = price * (1 + self.slippage_pct)
        commission = quantity * effective_price * self.commission_pct
        actual_amount = quantity * effective_price + commission
        self.cash -= actual_amount
        self._daily_trade_amount += actual_amount
        self._total_commission_paid += commission

        now = self._get_current_iso()

        # ── 스케일업 처리: 기존 MR 포지션에 추가 매수 ──
        if signal.stock_code in self.positions:
            existing = self.positions[signal.stock_code]
            if existing.status == "ACTIVE" and existing.scale_count < 1:
                old_qty = existing.quantity
                eff_old_entry = existing.avg_entry_price if existing.avg_entry_price > 0 else existing.entry_price
                old_cost = old_qty * eff_old_entry
                new_cost = quantity * effective_price
                total_qty = old_qty + quantity
                avg_price = (old_cost + new_cost) / total_qty
                existing.quantity = total_qty
                existing.entry_price = round(avg_price, 2)
                existing.avg_entry_price = round(avg_price, 2)
                existing.scale_count += 1
                existing.stop_loss = round(avg_price * (1 + self.stop_loss_pct))
                existing.weight_pct = round((total_qty * existing.current_price) / total_equity * 100, 1)
                self._add_risk_event("INFO",
                    f"스케일업: {signal.stock_name} +{quantity}주 @ {self.currency_symbol}{effective_price:,.0f}")
                # 스케일업 주문 기록
                self._order_counter += 1
                self.orders.append(
                    SimOrder(
                        id=f"sim-ord-{self._order_counter:04d}",
                        stock_code=signal.stock_code,
                        stock_name=signal.stock_name,
                        side="BUY",
                        order_type="MARKET",
                        status="FILLED",
                        price=price,
                        filled_price=effective_price,
                        quantity=quantity,
                        filled_quantity=quantity,
                        created_at=now,
                        filled_at=now,
                        reason=f"MR_SCALE +{quantity}주",
                    )
                )
                if len(self.orders) > 200:
                    self.orders = self.orders[-200:]
                return

        # ── 신규 포지션 생성 ──
        pos_id = f"sim-pos-{signal.stock_code}"
        stop_loss = effective_price * (1 + self.stop_loss_pct)
        take_profit = effective_price * (1 + self.take_profit_pct)

        self.positions[signal.stock_code] = SimPosition(
            id=pos_id,
            stock_code=signal.stock_code,
            stock_name=signal.stock_name,
            status="ACTIVE",
            quantity=quantity,
            entry_price=effective_price,
            current_price=effective_price,
            pnl=0,
            pnl_pct=0,
            stop_loss=round(stop_loss),
            take_profit=round(take_profit),
            trailing_stop=round(stop_loss),
            highest_price=effective_price,
            entry_date=self._get_current_date_str(),
            days_held=0,
            weight_pct=round(actual_amount / total_equity * 100, 1),
            strategy_tag=self.strategy_mode,
            avg_entry_price=effective_price,
            entry_signal_strength=signal.strength,
            entry_regime=self._market_regime,
            entry_trend_strength=trend_strength,
            stock_regime=self._stock_regimes.get(signal.stock_code, self._market_regime),
        )

        self._order_counter += 1
        self.orders.append(
            SimOrder(
                id=f"sim-ord-{self._order_counter:04d}",
                stock_code=signal.stock_code,
                stock_name=signal.stock_name,
                side="BUY",
                order_type="LIMIT",
                status="FILLED",
                price=price,
                filled_price=effective_price,
                quantity=quantity,
                filled_quantity=quantity,
                created_at=now,
                filled_at=now,
                reason=signal.reason,
            )
        )
        if len(self.orders) > 200:
            self.orders = self.orders[-200:]

        self._add_risk_event("INFO", f"매수 체결: {signal.stock_name} {quantity}주 @ {self.currency_symbol}{price:,.0f}")

    # ══════════════════════════════════════════
    # 청산 시그널 스캔 (momentum_swing.py 복제)
    # ══════════════════════════════════════════

    def _check_exits(self):
        """전략 모드에 따라 청산 체크 분기. multi/regime_* 모드에서는 strategy_tag 기반 라우팅."""
        if self.strategy_mode == "multi" or self.strategy_mode in REGIME_STRATEGY_MODES:
            return self._check_exits_multi()
        elif self.strategy_mode == "smc":
            return self._check_exits_smc()
        elif self.strategy_mode == "breakout_retest":
            return self._check_exits_breakout_retest()
        elif self.strategy_mode == "mean_reversion":
            return self._check_exits_mean_reversion()
        elif self.strategy_mode == "arbitrage":
            return self._check_exits_arbitrage()
        elif self.strategy_mode == "defensive":
            return self._check_exits_defensive()
        return self._check_exits_momentum()

    def _check_exits_multi(self):
        """멀티 전략 모드: 각 포지션의 strategy_tag에 따라 올바른 청산 로직 라우팅."""
        # CRISIS 레짐: 비방어 포지션 즉시 청산 대상 지정
        overrides = REGIME_OVERRIDES.get(self._market_regime, {})
        if overrides.get("crisis_exit_immediate"):
            for code, pos in list(self.positions.items()):
                if pos.status == "ACTIVE" and pos.strategy_tag not in ("defensive", "volatility"):
                    self._rebalance_exit_codes.add(code)

        tags_in_use = set()
        for pos in self.positions.values():
            if pos.status == "ACTIVE":
                tags_in_use.add(pos.strategy_tag)

        for tag in tags_in_use:
            original_mode = self.strategy_mode
            self.strategy_mode = tag
            # 태그 필터 설정 — 각 exit 메서드가 해당 전략 포지션만 처리
            self._exit_tag_filter = tag

            if tag == "smc":
                self._check_exits_smc()
            elif tag == "breakout_retest":
                self._check_exits_breakout_retest()
            elif tag == "mean_reversion":
                self._check_exits_mean_reversion()
            elif tag == "arbitrage":
                self._check_exits_arbitrage()
            elif tag == "defensive":
                self._check_exits_defensive()
            elif tag == "volatility":
                self._check_exits_volatility()
            else:  # momentum (default)
                self._check_exits_momentum()

            self._exit_tag_filter = None
            self.strategy_mode = original_mode

    def _check_exits_momentum(self):
        from simulation.strategies.momentum import check_exits
        check_exits(self)

    def _execute_partial_sell(self, pos: 'SimPosition', sell_qty: int, exit_code: str):
        """포지션의 일부만 청산 (BULL 이격도 분할 청산용).
        수량만 줄이고, 잔여 포지션은 계속 유지. avg_entry_price 유지.
        """
        if sell_qty <= 0 or sell_qty >= pos.quantity:
            return
        price = pos.current_price
        if price <= 0:
            price = pos.entry_price
        effective_price = price * (1 - self.slippage_pct)
        commission = sell_qty * effective_price * self.commission_pct
        proceeds = sell_qty * effective_price - commission
        self.cash += proceeds
        self._total_commission_paid += commission

        # 포지션 수량 감소 (avg_entry_price 유지)
        old_qty = pos.quantity
        pos.quantity -= sell_qty

        self._phase_stats.setdefault("es_disp_partial_sell", 0)
        self._phase_stats["es_disp_partial_sell"] += 1

        # 주문 기록
        self._order_counter += 1
        now = self._get_current_iso()
        self.orders.append(
            SimOrder(
                id=f"sim-ord-{self._order_counter:04d}",
                stock_code=pos.stock_code,
                stock_name=pos.stock_name,
                side="SELL",
                order_type="MARKET",
                status="FILLED",
                price=price,
                filled_price=effective_price,
                quantity=sell_qty,
                filled_quantity=sell_qty,
                created_at=now,
                filled_at=now,
                reason=f"{exit_code}: 부분청산 {sell_qty}/{old_qty}주",
            )
        )

        self._add_risk_event("INFO",
            f"부분청산: {pos.stock_name} {sell_qty}/{old_qty}주 @ {self.currency_symbol}{effective_price:,.0f} ({exit_code})")

    def _execute_sell(self, pos: SimPosition, price: float, reason: str, exit_type: str):
        now = self._get_current_iso()

        # ── GAP DOWN 보호: 스탑 청산 시 fill price를 stop level로 제한 ──
        # 갭다운으로 종가가 스탑보다 훨씬 아래인 경우, 스탑가 부근에서 체결된 것으로 시뮬레이션
        if exit_type in ("STOP_LOSS", "ATR_STOP_LOSS", "EMERGENCY_STOP") and pos.side != "SHORT":
            daily_low = getattr(self, '_daily_lows', {}).get(pos.stock_code)
            daily_high = getattr(self, '_daily_highs', {}).get(pos.stock_code)
            daily_open = getattr(self, '_daily_opens', {}).get(pos.stock_code)
            eff_entry = pos.avg_entry_price if pos.avg_entry_price > 0 else pos.entry_price
            # ATR SL은 포지션의 실제 stop_loss 사용, ES0은 -10%, ES1은 -5% 하드 스탑
            if exit_type == "ATR_STOP_LOSS" and pos.stop_loss > 0:
                stop_price = pos.stop_loss
            elif exit_type == "EMERGENCY_STOP":
                stop_price = eff_entry * 0.90  # -10% 비상 스탑
            else:
                stop_price = eff_entry * (1 + self.stop_loss_pct)  # -5% 스탑
            if daily_low is not None and daily_low < stop_price:
                if daily_high is not None and daily_high >= stop_price:
                    # 장중 스탑 레벨 통과 → 스탑가에서 체결 (정상 케이스)
                    price = stop_price
                elif daily_open is not None and daily_open < stop_price:
                    # 갭다운: 시가부터 스탑 이하 → 시가에서 체결 (시장가 주문)
                    price = daily_open
                else:
                    # 시가 데이터 없을 때 → 스탑가에서 체결 (보수적)
                    price = stop_price
            elif price < stop_price:
                # 종가가 스탑 이하지만 저가는 스탑 이상 → 스탑가에서 체결
                price = stop_price

        if pos.side == "SHORT":
            # ── Short 청산 (Buy to Cover) ──
            effective_price = price * (1 + self.slippage_pct)  # 매수이므로 불리한 방향
            commission = pos.quantity * effective_price * self.commission_pct
            cost = pos.quantity * effective_price + commission
            self.cash -= cost  # 환매 비용 차감
            self._daily_trade_amount += cost
            self._total_commission_paid += commission
            pnl = (pos.entry_price - effective_price) * pos.quantity - commission
            pnl_pct_val = (pos.entry_price - effective_price) / pos.entry_price * 100
            order_side = "BUY_TO_COVER"
            action_label = "숏 청산"
        else:
            # ── Long 청산 (기존 로직) ──
            effective_price = price * (1 - self.slippage_pct)
            commission = pos.quantity * effective_price * self.commission_pct
            proceeds = pos.quantity * effective_price - commission
            self.cash += proceeds
            self._daily_trade_amount += proceeds
            self._total_commission_paid += commission
            eff_entry = pos.avg_entry_price if pos.avg_entry_price > 0 else pos.entry_price
            pnl = proceeds - (pos.quantity * eff_entry)
            pnl_pct_val = (effective_price - eff_entry) / eff_entry * 100
            order_side = "SELL"
            action_label = "매도 체결"

        self._order_counter += 1
        self.orders.append(
            SimOrder(
                id=f"sim-ord-{self._order_counter:04d}",
                stock_code=pos.stock_code,
                stock_name=pos.stock_name,
                side=order_side,
                order_type="MARKET",
                status="FILLED",
                price=price,
                filled_price=effective_price,
                quantity=pos.quantity,
                filled_quantity=pos.quantity,
                created_at=now,
                filled_at=now,
                reason=reason,
            )
        )
        if len(self.orders) > 200:
            self.orders = self.orders[-200:]

        # 청산 시그널 기록
        self._signal_counter += 1
        self.signals.append(
            SimSignal(
                id=f"sim-sig-{self._signal_counter:04d}",
                stock_code=pos.stock_code,
                stock_name=pos.stock_name,
                type=order_side,
                price=price,
                reason=reason,
                strength=80,
                detected_at=now,
            )
        )
        if len(self.signals) > 100:
            self.signals = self.signals[-100:]

        # 청산 트레이드 기록
        self._trade_counter += 1
        self.closed_trades.append(
            SimTradeRecord(
                id=f"sim-trade-{self._trade_counter:04d}",
                stock_code=pos.stock_code,
                stock_name=pos.stock_name,
                entry_date=pos.entry_date,
                exit_date=now[:10],
                entry_price=pos.entry_price,
                exit_price=effective_price,
                quantity=pos.quantity,
                pnl=round(pnl),
                pnl_pct=round(pnl_pct_val, 2),
                exit_reason=reason,
                holding_days=pos.days_held,
                strategy_tag=pos.strategy_tag,
                entry_signal_strength=pos.entry_signal_strength,
                entry_regime=pos.entry_regime,
                entry_trend_strength=pos.entry_trend_strength,
                stock_regime=pos.stock_regime,
            )
        )
        if not self._replay_mode and len(self.closed_trades) > 200:
            self.closed_trades = self.closed_trades[-200:]

        # Phase 3.4: Dynamic Kelly — 전략별 거래 결과 기록
        if self._strategy_allocator is not None:
            self._strategy_allocator.record_trade_result(pos.strategy_tag, pnl_pct_val / 100.0)

        event_type = "WARNING" if pnl < 0 else "INFO"
        self._add_risk_event(event_type, f"{action_label}: {pos.stock_name} {reason} (P&L {pnl_pct_val:+.1f}%)")

        if exit_type == "STOP_LOSS":
            self._consecutive_stops += 1
            if self._consecutive_stops >= 3:
                self._add_risk_event("HALT", f"연속 손절 {self._consecutive_stops}회 — 매매 정지")
        else:
            self._consecutive_stops = 0

    def _execute_buy_arb(self, signal: SimSignal, quantity: int, pair_id: str):
        """
        v2: Arbitrage Long leg 매수 — dollar-neutral 사이징 (BUG-6).
        _execute_buy()와 유사하지만 수량이 _size_arb_pair()에서 미리 계산됨.
        """
        total_equity = self._get_total_equity()
        price = signal.price

        if quantity <= 0 or price <= 0:
            return

        # 현금 제약
        cost = quantity * price
        min_cash = total_equity * self.min_cash_ratio
        available = self.cash - min_cash
        if available <= 0:
            return
        if cost > available:
            quantity = int(available / price)
        if quantity <= 0:
            return

        cost = quantity * price

        # 슬리피지 + 수수료
        effective_price = price * (1 + self.slippage_pct)
        commission = quantity * effective_price * self.commission_pct
        total_cost = quantity * effective_price + commission

        if total_cost > self.cash:
            quantity = int((self.cash - commission) / effective_price)
        if quantity <= 0:
            return

        total_cost = quantity * effective_price + commission
        self.cash -= total_cost
        self._daily_trade_amount += total_cost
        self._total_commission_paid += commission

        now = self._get_current_iso()
        pos_id = f"sim-long-{signal.stock_code}"

        # 스탑로스: 고정 -5% (BUG-2: Long/Short 동일)
        stop_loss = effective_price * (1 + self.stop_loss_pct)  # -5%

        self.positions[signal.stock_code] = SimPosition(
            id=pos_id,
            stock_code=signal.stock_code,
            stock_name=signal.stock_name,
            status="ACTIVE",
            quantity=quantity,
            entry_price=effective_price,
            current_price=effective_price,
            pnl=0,
            pnl_pct=0,
            stop_loss=round(stop_loss, 2),
            take_profit=0,  # Z-Score 기반 청산
            trailing_stop=round(stop_loss, 2),
            highest_price=effective_price,
            entry_date=self._get_current_date_str(),
            days_held=0,
            max_holding_days=self._arb_cfg.max_holding_days,
            weight_pct=round(total_cost / self.initial_capital * 100, 1),
            side="LONG",
            lowest_price=effective_price,
            pair_id=pair_id,
            strategy_tag=self.strategy_mode,
            entry_signal_strength=signal.strength,
            entry_regime=self._market_regime,
            entry_trend_strength="MODERATE",
            stock_regime=self._stock_regimes.get(signal.stock_code, self._market_regime),
        )

        self._order_counter += 1
        self.orders.append(
            SimOrder(
                id=f"sim-ord-{self._order_counter:04d}",
                stock_code=signal.stock_code,
                stock_name=signal.stock_name,
                side="BUY",
                order_type="MARKET",
                status="FILLED",
                price=price,
                filled_price=effective_price,
                quantity=quantity,
                filled_quantity=quantity,
                created_at=now,
                filled_at=now,
                reason=f"ARB Long: {signal.reason}",
            )
        )
        if len(self.orders) > 200:
            self.orders = self.orders[-200:]

        self._add_risk_event("INFO", f"롱 진입: {signal.stock_name} @{effective_price:,.0f} ×{quantity} (pair: {pair_id})")

    def _execute_sell_short(self, signal: SimSignal, pair_id: str, arb_quantity: int = 0):
        """Short 포지션 오픈 (공매도 진입). Arbitrage 전용. v2: dollar-neutral 사이징 (BUG-6)."""
        total_equity = self._get_total_equity()
        price = signal.price

        # v2: arb_quantity가 제공되면 사용, 아니면 기존 로직 (하위호환)
        if arb_quantity > 0:
            quantity = arb_quantity
        else:
            # 기존 fallback 사이징
            risk_per_trade = total_equity * 0.015
            df_tmp = self._ohlcv_cache.get(signal.stock_code)
            atr_tmp = None
            if df_tmp is not None and len(df_tmp) > 14:
                if "atr" not in df_tmp.columns:
                    df_tmp = self._calculate_indicators(df_tmp.copy())
                    self._ohlcv_cache[signal.stock_code] = df_tmp
                last_atr_tmp = df_tmp.iloc[-1].get("atr")
                if pd.notna(last_atr_tmp):
                    atr_tmp = float(last_atr_tmp)
            stop_dist = max(atr_tmp * self._arb_cfg.atr_sl_mult, price * 0.05) if (atr_tmp and atr_tmp > 0) else price * 0.05
            quantity = int(risk_per_trade / stop_dist)

        # 페어당 최대 비중 제한
        max_amount = total_equity * self._arb_cfg.max_weight_per_pair * 0.5
        if quantity * price > max_amount:
            quantity = int(max_amount / price)

        # 현금 제약 (Short 마진 = 매도 대금의 50% 예비)
        min_cash = total_equity * self.min_cash_ratio
        margin_required = quantity * price * 0.5
        available = self.cash - min_cash
        if available <= 0 or quantity <= 0:
            return
        if margin_required > available:
            quantity = int(available * 2 / price)
        if quantity <= 0:
            return

        # 슬리피지 + 수수료 (매도 진입)
        effective_price = price * (1 - self.slippage_pct)
        commission = quantity * effective_price * self.commission_pct
        proceeds = quantity * effective_price - commission
        self.cash += proceeds  # 매도 대금 수취
        self._daily_trade_amount += proceeds
        self._total_commission_paid += commission

        now = self._get_current_iso()
        pos_id = f"sim-short-{signal.stock_code}"

        # v2: 스탑로스 고정 -5% (BUG-2: Long과 동일, 하드 손절 최우선)
        stop_loss = effective_price * 1.05  # Short: 가격 5% 상승 시 손절

        take_profit = 0  # Z-Score 기반 청산이므로 고정 TP 없음

        self.positions[signal.stock_code] = SimPosition(
            id=pos_id,
            stock_code=signal.stock_code,
            stock_name=signal.stock_name,
            status="ACTIVE",
            quantity=quantity,
            entry_price=effective_price,
            current_price=effective_price,
            pnl=0,
            pnl_pct=0,
            stop_loss=round(stop_loss, 2),
            take_profit=round(take_profit, 2),
            trailing_stop=round(stop_loss, 2),
            highest_price=effective_price,
            entry_date=self._get_current_date_str(),
            days_held=0,
            max_holding_days=self._arb_cfg.max_holding_days,
            weight_pct=round(proceeds / self.initial_capital * 100, 1),
            side="SHORT",
            lowest_price=effective_price,
            pair_id=pair_id,
            strategy_tag=self.strategy_mode,
            entry_signal_strength=signal.strength,
            entry_regime=self._market_regime,
            entry_trend_strength="MODERATE",
            stock_regime=self._stock_regimes.get(signal.stock_code, self._market_regime),
        )

        # 매도 진입 주문 기록
        self._order_counter += 1
        self.orders.append(
            SimOrder(
                id=f"sim-ord-{self._order_counter:04d}",
                stock_code=signal.stock_code,
                stock_name=signal.stock_name,
                side="SELL_SHORT",
                order_type="MARKET",
                status="FILLED",
                price=price,
                filled_price=effective_price,
                quantity=quantity,
                filled_quantity=quantity,
                created_at=now,
                filled_at=now,
                reason=f"ARB Short: {signal.reason}",
            )
        )
        if len(self.orders) > 200:
            self.orders = self.orders[-200:]

        self._add_risk_event("INFO", f"숏 진입: {signal.stock_name} @{effective_price:,.0f} ×{quantity} (pair: {pair_id})")
        self._phase_stats["arb_short_entries"] = self._phase_stats.get("arb_short_entries", 0) + 1


    # ══════════════════════════════════════════
    # 가격 업데이트
    # ══════════════════════════════════════════

    def _update_position_prices(self):
        total_equity = self._get_total_equity()
        for code, pos in self.positions.items():
            if pos.status != "ACTIVE":
                continue
            price = self._current_prices.get(code, pos.current_price)
            pos.current_price = price

            if pos.side == "SHORT":
                # Short: 가격 하락 = 이익
                pos.pnl = (pos.entry_price - price) * pos.quantity
                pos.pnl_pct = round((pos.entry_price - price) / pos.entry_price * 100, 2)
                # Short 트레일링용 최저가 추적
                if pos.lowest_price <= 0:
                    pos.lowest_price = price
                else:
                    pos.lowest_price = min(pos.lowest_price, price)
            else:
                # Long: 가격 상승 = 이익 (기존 로직)
                pos.pnl = (price - pos.entry_price) * pos.quantity
                pos.pnl_pct = round((price - pos.entry_price) / pos.entry_price * 100, 2)

            pos.weight_pct = round(price * pos.quantity / total_equity * 100, 1) if total_equity > 0 else 0

    # ══════════════════════════════════════════
    # 상태 조회
    # ══════════════════════════════════════════

    def _get_total_equity(self) -> float:
        invested = 0
        for p in self.positions.values():
            if p.status != "ACTIVE":
                continue
            if p.side == "SHORT":
                # Short 가치: 매도 대금(entry×qty) + 미실현 손익(entry-current)×qty
                # = 2×entry×qty - current×qty (margin + unrealized PnL)
                invested += p.entry_price * p.quantity + (p.entry_price - p.current_price) * p.quantity
            else:
                invested += p.current_price * p.quantity
        return self.cash + invested

    def get_system_state(self) -> SimSystemState:
        total_equity = self._get_total_equity()
        invested = total_equity - self.cash
        daily_pnl = total_equity - self._daily_start_equity
        daily_pnl_pct = (daily_pnl / self._daily_start_equity * 100) if self._daily_start_equity > 0 else 0

        regime_params = REGIME_PARAMS.get(self._market_regime, REGIME_PARAMS["NEUTRAL"])
        mode = "REPLAY" if self._backtest_date else "PAPER"
        return SimSystemState(
            status="RUNNING" if self._is_running else "STOPPED",
            mode=mode,
            started_at=self._started_at,
            market_phase="OPEN" if self._is_running else "CLOSED",
            market_regime=self._market_regime,
            next_scan_at=None,
            total_equity=round(total_equity),
            cash=round(self.cash),
            invested=round(invested),
            daily_pnl=round(daily_pnl),
            daily_pnl_pct=round(daily_pnl_pct, 2),
            position_count=len([p for p in self.positions.values() if p.status == "ACTIVE"]),
            max_positions=regime_params["max_positions"],
        )

    def get_risk_metrics(self) -> SimRiskMetrics:
        total_equity = self._get_total_equity()
        daily_pnl_pct = (
            (total_equity - self._daily_start_equity) / self._daily_start_equity * 100
            if self._daily_start_equity > 0
            else 0
        )
        self._peak_equity = max(self._peak_equity, total_equity)
        mdd = (
            (total_equity - self._peak_equity) / self._peak_equity * 100
            if self._peak_equity > 0
            else 0
        )
        cash_ratio = (self.cash / total_equity * 100) if total_equity > 0 else 100

        is_halted = daily_pnl_pct <= -3.0 or self._consecutive_stops >= 3
        halt_reason = None
        if daily_pnl_pct <= -3.0:
            halt_reason = "일일 손실 한도 도달"
        elif self._consecutive_stops >= 3:
            halt_reason = f"연속 손절 {self._consecutive_stops}회"

        return SimRiskMetrics(
            daily_pnl_pct=round(daily_pnl_pct, 2),
            mdd=round(mdd, 2),
            cash_ratio=round(cash_ratio, 1),
            consecutive_stops=self._consecutive_stops,
            daily_trade_amount=round(self._daily_trade_amount),
            is_trading_halted=is_halted,
            halt_reason=halt_reason,
        )

    def _add_risk_event(self, event_type: str, message: str, value: float = None, limit: float = None):
        self._event_counter += 1
        self.risk_events.append(
            {
                "id": f"sim-evt-{self._event_counter:04d}",
                "type": event_type,
                "message": message,
                "value": value,
                "limit": limit,
                "timestamp": self._get_current_iso(),
            }
        )
        if len(self.risk_events) > 100:
            self.risk_events = self.risk_events[-100:]

    # ══════════════════════════════════════════
    # 성과 추적
    # ══════════════════════════════════════════

    def _record_equity_point(self):
        total_equity = self._get_total_equity()
        self._peak_equity = max(self._peak_equity, total_equity)
        # 에쿼티 모멘텀 히스토리 갱신 (최근 30일)
        self._equity_history.append(total_equity)
        if len(self._equity_history) > 30:
            self._equity_history = self._equity_history[-30:]
        dd = (
            (total_equity - self._peak_equity) / self._peak_equity * 100
            if self._peak_equity > 0
            else 0
        )
        today = self._get_current_date_str()
        # 같은 날 마지막 포인트만 유지 (덮어쓰기)
        if self.equity_curve and self.equity_curve[-1].date == today:
            self.equity_curve[-1] = SimEquityPoint(
                date=today, equity=round(total_equity), drawdown_pct=round(dd, 2)
            )
        else:
            self.equity_curve.append(
                SimEquityPoint(
                    date=today, equity=round(total_equity), drawdown_pct=round(dd, 2)
                )
            )
        if not self._replay_mode and len(self.equity_curve) > 365:
            self.equity_curve = self.equity_curve[-365:]

    def get_performance_summary(self) -> SimPerformanceSummary:
        trades = self.closed_trades
        if not trades:
            total_equity = self._get_total_equity()
            total_return = (total_equity - self.initial_capital) / self.initial_capital * 100
            return SimPerformanceSummary(
                total_return_pct=round(total_return, 2),
                max_drawdown_pct=round(
                    min((p.drawdown_pct for p in self.equity_curve), default=0), 2
                ),
            )

        wins = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl <= 0]
        total_equity = self._get_total_equity()
        total_return = (total_equity - self.initial_capital) / self.initial_capital * 100

        win_rate = len(wins) / len(trades) * 100 if trades else 0
        avg_win = sum(t.pnl_pct for t in wins) / len(wins) if wins else 0
        avg_loss = sum(t.pnl_pct for t in losses) / len(losses) if losses else 0
        total_win_amount = sum(t.pnl for t in wins)
        total_loss_amount = abs(sum(t.pnl for t in losses))
        profit_factor = (
            total_win_amount / total_loss_amount if total_loss_amount > 0 else 0
        )
        avg_holding = sum(t.holding_days for t in trades) / len(trades) if trades else 0
        best_trade = max(t.pnl_pct for t in trades) if trades else 0
        worst_trade = min(t.pnl_pct for t in trades) if trades else 0

        # 간이 Sharpe (일간 수익률 기반)
        if len(self.equity_curve) >= 2:
            returns = []
            for i in range(1, len(self.equity_curve)):
                prev = self.equity_curve[i - 1].equity
                curr = self.equity_curve[i].equity
                if prev > 0:
                    returns.append((curr - prev) / prev)
            if returns and len(returns) > 1:
                mean_r = sum(returns) / len(returns)
                std_r = (sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)) ** 0.5
                sharpe = (mean_r / std_r * math.sqrt(252)) if std_r > 0 else 0
            else:
                sharpe = 0
        else:
            sharpe = 0

        max_dd = min((p.drawdown_pct for p in self.equity_curve), default=0)

        return SimPerformanceSummary(
            total_return_pct=round(total_return, 2),
            total_trades=len(trades),
            win_rate=round(win_rate, 2),
            avg_win_pct=round(avg_win, 2),
            avg_loss_pct=round(avg_loss, 2),
            profit_factor=round(profit_factor, 2),
            sharpe_ratio=round(sharpe, 2),
            max_drawdown_pct=round(max_dd, 2),
            avg_holding_days=round(avg_holding, 1),
            best_trade_pct=round(best_trade, 2),
            worst_trade_pct=round(worst_trade, 2),
        )

    # ══════════════════════════════════════════
    # SSE 브로드캐스트
    # ══════════════════════════════════════════

    async def _broadcast_all(self):
        state = self.get_system_state()
        risk = self.get_risk_metrics()
        positions = [p.model_dump() for p in self.positions.values() if p.status == "ACTIVE"]

        prefix = self.market_id

        # system_state에 마켓 메타데이터 포함
        state_data = state.model_dump()
        state_data["market_id"] = self.market_id
        state_data["currency"] = self.currency
        state_data["currency_symbol"] = self.currency_symbol
        state_data["market_label"] = self.market_label

        # 레짐별 동적 전략 이름 (Multi 모드에서 사용)
        trend_key = (self._index_trend or {}).get("trend", self._market_regime)
        regime_label = REGIME_DISPLAY_NAMES.get(
            trend_key, REGIME_DISPLAY_NAMES.get("NEUTRAL")
        )
        state_data["active_strategy_label"] = regime_label
        state_data["strategy_display_names"] = STRATEGY_DISPLAY_NAMES
        state_data["strategy_composition"] = REGIME_STRATEGY_COMPOSITION.get(
            trend_key, REGIME_STRATEGY_COMPOSITION.get("NEUTRAL", {})
        )
        state_data["actual_market_regime"] = self._actual_market_regime
        state_data["regime_locked"] = self._regime_locked
        state_data["locked_regime"] = self._locked_regime

        await self._on_event(f"{prefix}:system_state", state_data)
        await self._on_event(f"{prefix}:positions", positions)
        await self._on_event(f"{prefix}:signals", [s.model_dump() for s in self.signals[-20:]])
        await self._on_event(f"{prefix}:orders", [o.model_dump() for o in self.orders[-50:]])
        await self._on_event(f"{prefix}:risk_metrics", risk.model_dump())
        await self._on_event(f"{prefix}:risk_events", self.risk_events[-30:])
        await self._on_event(f"{prefix}:equity_curve", [p.model_dump() for p in self.equity_curve[-200:]])
        await self._on_event(f"{prefix}:performance", self.get_performance_summary().model_dump())
