"""
히스토리컬 백테스터 오케스트레이터.

SimulationEngine의 6-Phase 파이프라인을 히스토리컬 데이터로 구동한다.
yfinance에서 데이터를 다운로드 → CSV 캐시 → 날짜별 슬라이싱 → 엔진 실행 → 메트릭 수집.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Coroutine, Dict, Optional

from backtest.data_downloader import (
    analyze_survivorship_bias,
    download_and_cache,
    download_and_cache_batched,
)
from backtest.data_provider import HistoricalDataProvider
from backtest.metrics import ExtendedMetrics, MetricsCollector
from backtest.scenarios import BacktestScenario, create_custom_scenario, get_scenario
from infra.logger import get_logger
from simulation.engine import SimulationEngine
from simulation.watchlists import MARKET_CONFIG

logger = get_logger("backtest.historical")


class HistoricalBacktester:
    """
    SimulationEngine의 6-Phase 파이프라인을 히스토리컬 데이터로 구동하는 백테스터.

    Usage:
        bt = HistoricalBacktester(market="sp500", scenario="financial_crisis_us")
        result = bt.run()
        result.phase_stats  # Phase Funnel 통계
        result.regime_transitions  # 체제 전환 타임라인
    """

    def __init__(
        self,
        market: str,
        scenario: str = "custom",
        start_date: str = "",
        end_date: str = "",
        initial_capital: Optional[float] = None,
        cache_dir: str = "data_store/historical",
        slippage_pct: float = 0.001,
        commission_pct: float = 0.00015,
        universe: Optional[str] = None,
        rebalance_days: int = 14,
        top_n: int = 15,
        strategy_mode: str = "momentum",
        fixed_amount_per_stock: float = 0,
        disable_es2: bool = False,
    ):
        self.market = market
        self.scenario_id = scenario
        self.cache_dir = cache_dir
        self.slippage_pct = slippage_pct
        self.commission_pct = commission_pct
        self.universe_id = universe
        self.rebalance_days = rebalance_days
        self.top_n = top_n
        self.strategy_mode = strategy_mode
        self.fixed_amount_per_stock = fixed_amount_per_stock
        self.disable_es2 = disable_es2

        # 마켓 설정 로드
        if market not in MARKET_CONFIG:
            raise ValueError(f"Unknown market: {market}. Available: {list(MARKET_CONFIG.keys())}")
        self.market_cfg = MARKET_CONFIG[market]
        self.watchlist = self.market_cfg["watchlist"]
        self.capital = initial_capital or self.market_cfg["initial_capital"]
        self.currency = self.market_cfg["currency"]
        self.currency_symbol = self.market_cfg["currency_symbol"]
        self.market_label = self.market_cfg["label"]

        # 시나리오 로드
        if scenario == "custom":
            if not start_date or not end_date:
                raise ValueError("Custom scenario requires --start and --end dates (YYYYMMDD)")
            self.scenario = create_custom_scenario(start_date, end_date, [market])
        else:
            self.scenario = get_scenario(scenario)
            if market not in self.scenario.markets:
                raise ValueError(
                    f"Market '{market}' is not applicable to scenario '{scenario}'. "
                    f"Available markets: {self.scenario.markets}"
                )

        # 컴포넌트 (run()에서 초기화)
        self.engine: Optional[SimulationEngine] = None
        self.provider: Optional[HistoricalDataProvider] = None
        self.collector: Optional[MetricsCollector] = None

    @classmethod
    def from_optimal(
        cls,
        market: str,
        start_date: str,
        end_date: str,
        rebalance_days: int = 14,
        strategy_mode: str = "momentum",
    ) -> "HistoricalBacktester":
        """마켓별 최적 전략 설정으로 백테스터를 생성한다.

        OPTIMAL_STRATEGY_CONFIG (백테스트 검증 완료)를 자동 적용:
        - KOSPI: Top60 + ₩3M 고정사이징 + ES2 제거 + 강화 트레일링
        - SP500: Top60 + $3K 고정사이징 + ES2 제거 + 강화 트레일링
        - NDX: 기존 전략 유지 (ATR사이징 + ES2 활성)
        """
        from simulation.universe import OPTIMAL_STRATEGY_CONFIG

        if market not in OPTIMAL_STRATEGY_CONFIG:
            raise ValueError(
                f"No optimal config for market '{market}'. "
                f"Available: {list(OPTIMAL_STRATEGY_CONFIG.keys())}"
            )

        cfg = OPTIMAL_STRATEGY_CONFIG[market]
        return cls(
            market=market,
            scenario="custom",
            start_date=start_date,
            end_date=end_date,
            initial_capital=cfg["initial_capital"],
            universe=cfg["universe"],
            rebalance_days=rebalance_days,
            top_n=cfg["top_n"],
            strategy_mode=strategy_mode,
            fixed_amount_per_stock=cfg["fixed_amount_per_stock"],
            disable_es2=cfg["disable_es2"],
        )

    def run(self) -> ExtendedMetrics:
        """백테스트 실행. 전체 파이프라인을 순차 실행한다."""

        # 유니버스 모드 설정
        universe_constituents = None
        scanner = None
        if self.universe_id:
            from simulation.universe import UNIVERSE_CONFIG, UniverseScanner

            if self.universe_id not in UNIVERSE_CONFIG:
                raise ValueError(
                    f"Unknown universe: {self.universe_id}. "
                    f"Available: {list(UNIVERSE_CONFIG.keys())}"
                )
            ucfg = UNIVERSE_CONFIG[self.universe_id]
            universe_constituents = ucfg["constituents"]
            scanner = UniverseScanner(
                constituents=universe_constituents,
                top_n=self.top_n,
            )

        # 데이터 다운로드 대상
        download_watchlist = universe_constituents if universe_constituents else self.watchlist

        print(f"\n{'='*60}")
        print(f"  ATS HISTORICAL BACKTEST")
        print(f"{'='*60}")
        print(f"  시나리오 : {self.scenario.name}")
        print(f"  마켓     : {self.market_label}")
        print(f"  전략     : {self.strategy_mode.upper()}")
        if self.universe_id:
            print(f"  유니버스  : {self.universe_id} ({len(download_watchlist)}종목)")
            print(f"  리밸런싱  : {self.rebalance_days}거래일 주기, top {self.top_n}")
        print(f"  기간     : {_fmt_date(self.scenario.start_date)} ~ {_fmt_date(self.scenario.end_date)}")
        print(f"  워밍업   : {_fmt_date(self.scenario.warmup_start)} ~")
        print(f"  초기자본 : {self.currency_symbol}{self.capital:,.0f}")
        print(f"  종목 수  : {len(download_watchlist)}")
        print(f"  슬리피지 : {self.slippage_pct*100:.2f}%")
        print(f"  수수료   : {self.commission_pct*100:.4f}%")
        print(f"{'='*60}\n")

        # ── 1. 데이터 다운로드 / 캐시 로드 ──
        market_cache = os.path.join(self.cache_dir, self.market)
        print("📥 데이터 로드 중...")

        if universe_constituents and len(download_watchlist) > 50:
            ohlcv_map = download_and_cache_batched(
                watchlist=download_watchlist,
                start_date=self.scenario.warmup_start,
                end_date=self.scenario.end_date,
                cache_dir=market_cache,
            )
        else:
            ohlcv_map = download_and_cache(
                watchlist=download_watchlist,
                start_date=self.scenario.warmup_start,
                end_date=self.scenario.end_date,
                cache_dir=market_cache,
            )

        if not ohlcv_map:
            raise RuntimeError("No OHLCV data loaded. Check data download or cache.")
        print(f"   → {len(ohlcv_map)}/{len(download_watchlist)} 종목 로드 완료")

        # ── 1-vix. VIX 데이터 다운로드 (복합 레짐 분류 + 사이징 디스카운트용) ──
        vix_by_date: dict[str, float] = {}
        try:
            vix_wl = [{"code": "^VIX", "ticker": "^VIX", "name": "VIX"}]
            vix_cache = os.path.join(self.cache_dir, "_macro")
            vix_map = download_and_cache(
                watchlist=vix_wl,
                start_date=self.scenario.warmup_start,
                end_date=self.scenario.end_date,
                cache_dir=vix_cache,
            )
            if "^VIX" in vix_map and not vix_map["^VIX"].empty:
                vdf = vix_map["^VIX"]
                for _, row in vdf.iterrows():
                    vix_by_date[str(row["date"])] = float(row["close"])
                print(f"   → VIX 데이터 로드: {len(vix_by_date)}일")
            else:
                print("   ⚠ VIX 데이터 없음 — VIX 연동 비활성")
        except Exception as e:
            print(f"   ⚠ VIX 다운로드 실패: {e} — VIX 연동 비활성")
        self._vix_by_date = vix_by_date

        # ── 1-idx. 지수 OHLCV 다운로드 (지수 추세 기반 자동 전략 선택용) ──
        index_by_date: dict[str, dict] = {}
        try:
            from simulation.watchlists import MARKET_CONFIG
            market_cfg = MARKET_CONFIG.get(self.market, {})
            index_symbol = market_cfg.get("index_symbol", "")
            if index_symbol:
                idx_wl = [{"code": index_symbol, "ticker": index_symbol, "name": f"INDEX_{self.market}"}]
                idx_cache = os.path.join(self.cache_dir, "_macro")
                idx_map = download_and_cache(
                    watchlist=idx_wl,
                    start_date=self.scenario.warmup_start,
                    end_date=self.scenario.end_date,
                    cache_dir=idx_cache,
                )
                if index_symbol in idx_map and not idx_map[index_symbol].empty:
                    idf = idx_map[index_symbol]
                    for _, row in idf.iterrows():
                        d = str(row["date"])
                        index_by_date[d] = {
                            "open": float(row.get("open", row["close"])),
                            "high": float(row.get("high", row["close"])),
                            "low": float(row.get("low", row["close"])),
                            "close": float(row["close"]),
                            "volume": float(row.get("volume", 0)),
                        }
                    print(f"   → 지수({index_symbol}) 데이터 로드: {len(index_by_date)}일")
                else:
                    print(f"   ⚠ 지수({index_symbol}) 데이터 없음 — 지수 추세 비활성")
        except Exception as e:
            print(f"   ⚠ 지수 다운로드 실패: {e} — 지수 추세 비활성")
        self._index_by_date = index_by_date

        # ── 1a. v5: Arbitrage 전용 — Basis signal + Fixed ETF 데이터 추가 다운로드 ──
        if self.strategy_mode == "arbitrage":
            from data.config_manager import ArbitrageConfig, ConfigManager
            try:
                _cfg_mgr = ConfigManager()
                _full_cfg = _cfg_mgr.load()
                _arb_cfg = _full_cfg.arbitrage
            except Exception:
                _arb_cfg = ArbitrageConfig()

            # Basis signal instruments (ES=F, ^KS200 등)
            basis_extra: list = []
            for sig in _arb_cfg.basis_signals:
                if sig.get("market") != self.market:
                    continue
                spot_code = sig.get("spot_code", "")
                spot_t = sig.get("spot_ticker", "")
                fut_code = sig.get("futures_code", "")
                fut_t = sig.get("futures_ticker", "")
                if spot_code and spot_code not in ohlcv_map:
                    basis_extra.append({
                        "code": spot_code,
                        "ticker": spot_t or spot_code,
                        "name": f"Basis Spot ({spot_t})",
                        "sector": "BASIS",
                    })
                if fut_code and fut_t and fut_code not in ohlcv_map:
                    basis_extra.append({
                        "code": fut_code,
                        "ticker": fut_t,
                        "name": f"Basis Futures ({fut_t})",
                        "sector": "BASIS",
                    })

            # Fixed pair ETF가 download_watchlist에 없으면 추가
            etf_extra: list = []
            existing_codes = {item["code"] if isinstance(item, dict) else item for item in download_watchlist}
            existing_codes.update(ohlcv_map.keys())
            for pair_def in _arb_cfg.fixed_pairs:
                if pair_def.get("market") != self.market:
                    continue
                for suffix in ("_a", "_b"):
                    code = pair_def.get(f"code{suffix}", "")
                    ticker = pair_def.get(f"ticker{suffix}", "")
                    if code and code not in existing_codes:
                        etf_extra.append({
                            "code": code,
                            "ticker": ticker or code,
                            "name": pair_def.get(f"name{suffix}", code),
                            "sector": "ETF",
                        })
                        existing_codes.add(code)

            extra_list = basis_extra + etf_extra
            if extra_list:
                print(f"   📡 v5 Basis/ETF 추가 다운로드: {len(extra_list)}종목")
                extra_map = {}

                # Cross-market reuse: basis instruments (SPY, ES=F)는 시장 간 공유 가능
                import shutil
                for item in list(extra_list):
                    code = item["code"]
                    for other_market in ("sp500", "ndx", "kospi"):
                        if other_market == self.market:
                            continue
                        other_path = os.path.join(self.cache_dir, other_market, f"{code}.csv")
                        if os.path.exists(other_path):
                            dest = os.path.join(market_cache, f"{code}.csv")
                            shutil.copy2(other_path, dest)
                            df = load_ohlcv(code, market_cache)
                            if not df.empty and df["date"].nunique() >= 5:
                                extra_map[code] = df
                                extra_list.remove(item)
                                print(f"   ♻ {code}: reused from {other_market} cache")
                                break

                # 각 종목을 개별 다운로드 (ES=F 등 특수 티커 호환)
                for item in extra_list:
                    try:
                        single_map = download_and_cache(
                            watchlist=[item],
                            start_date=self.scenario.warmup_start,
                            end_date=self.scenario.end_date,
                            cache_dir=market_cache,
                        )
                        extra_map.update(single_map)
                    except Exception as e:
                        print(f"   ⚠ {item['code']} 다운로드 실패: {e}")
                ohlcv_map.update(extra_map)
                print(f"   → 추가 로드 완료: {len(extra_map)}/{len(extra_list) + len(extra_map)}")
            # 일별 루프에서 데이터 주입용 워치리스트 저장 (모든 고정 페어 + basis 종목)
            arb_all_codes: list = []
            for pair_def in _arb_cfg.fixed_pairs:
                if pair_def.get("market") != self.market:
                    continue
                for suffix in ("_a", "_b"):
                    code = pair_def.get(f"code{suffix}", "")
                    ticker = pair_def.get(f"ticker{suffix}", "")
                    if code:
                        arb_all_codes.append({
                            "code": code,
                            "ticker": ticker or code,
                            "name": pair_def.get(f"name{suffix}", code),
                            "sector": "ETF",
                        })
            for sig in _arb_cfg.basis_signals:
                if sig.get("market") != self.market:
                    continue
                for key_prefix, name_prefix in [("spot", "Basis Spot"), ("futures", "Basis Futures")]:
                    code = sig.get(f"{key_prefix}_code", "")
                    ticker = sig.get(f"{key_prefix}_ticker", "")
                    if code and ticker:
                        arb_all_codes.append({
                            "code": code,
                            "ticker": ticker,
                            "name": f"{name_prefix} ({ticker})",
                            "sector": "BASIS",
                        })
            self._arb_extra_watchlist = arb_all_codes
        else:
            self._arb_extra_watchlist = []

        # ── 1b. 생존자 편향 분석 ──
        self._survivorship = analyze_survivorship_bias(
            watchlist=download_watchlist,
            ohlcv_map=ohlcv_map,
            start_date=self.scenario.start_date,
            end_date=self.scenario.end_date,
        )
        score = self._survivorship["score"]
        if self._survivorship["warning"]:
            print(f"   ⚠ Survivorship Bias (score={score:.2f}): {self._survivorship['warning']}")
        else:
            print(f"   ✓ Survivorship Bias check passed (score={score:.2f})")
        print()

        # ── 2. 프로바이더 초기화 ──
        self.provider = HistoricalDataProvider(ohlcv_map)

        # 거래일 분리
        warmup_dates = self.provider.get_warmup_dates(self.scenario.start_date)
        backtest_dates = self.provider.get_dates_in_range(
            self.scenario.start_date, self.scenario.end_date
        )

        if not backtest_dates:
            raise RuntimeError(
                f"No trading dates in range {self.scenario.start_date} ~ {self.scenario.end_date}"
            )

        print(f"📅 워밍업: {len(warmup_dates)}일, 백테스트: {len(backtest_dates)}일")
        print(f"   {_fmt_date(backtest_dates[0])} ~ {_fmt_date(backtest_dates[-1])}\n")

        # ── 3. 엔진 초기화 ──
        async def _noop_event(event_type: str, data: Any) -> None:
            pass  # SSE 비활성

        # 유니버스 모드: 초기 워치리스트는 기본 워치리스트 (첫 리밸런싱에서 교체됨)
        initial_watchlist = self.watchlist

        self.engine = SimulationEngine(
            on_event=_noop_event,
            market_id=self.market,
            watchlist=initial_watchlist,
            initial_capital=self.capital,
            currency=self.currency,
            currency_symbol=self.currency_symbol,
            market_label=self.market_label,
            slippage_pct=self.slippage_pct,
            commission_pct=self.commission_pct,
            strategy_mode=self.strategy_mode,
            fixed_amount_per_stock=self.fixed_amount_per_stock,
            disable_es2=self.disable_es2,
        )
        # 백테스트 모드: 전체 거래/에퀴티 이력 보존 (truncation 비활성화)
        self.engine._replay_mode = True

        # 유니버스 모드: 엔진에 리밸런스 매니저 내장
        if scanner:
            self.engine.init_rebalance_manager(scanner, self.rebalance_days)

        # ── 4. 워밍업 (거래 없이 데이터만 주입) ──
        if warmup_dates:
            print("🔄 워밍업 진행 중 (MA200 계산용)...")
            last_warmup = warmup_dates[-1]
            self.provider.set_current_date(last_warmup)
            warmup_ohlcv = self.provider.get_ohlcv_up_to_date(self.watchlist)
            warmup_prices = self.provider.get_current_prices(self.watchlist)

            self.engine._ohlcv_cache = warmup_ohlcv
            self.engine._current_prices = warmup_prices

            # 워밍업 기간 VIX 히스토리 주입 (EMA-20 안정화)
            if self._vix_by_date:
                for wdate in warmup_dates:
                    vix_close = self._vix_by_date.get(wdate)
                    if vix_close is not None:
                        self.engine.update_vix(vix_close)

            # 워밍업 기간 지수 OHLCV 주입 (MA200 안정화)
            if self._index_by_date:
                for wdate in warmup_dates:
                    index_data = self._index_by_date.get(wdate)
                    if index_data is not None:
                        self.engine.update_index_data(wdate, index_data)

            # 초기 에쿼티/체제 설정
            self.engine._market_regime = self.engine._judge_market_regime()
            print(f"   → 워밍업 완료. 초기 체제: {self.engine._market_regime}\n")

        # ── 5. 메트릭 수집기 초기화 ──
        self.collector = MetricsCollector(
            initial_capital=self.capital,
            scenario=self.scenario,
        )

        # ── 6. 일별 루프 ──
        print("🚀 백테스트 시작...\n")
        total_days = len(backtest_dates)
        active_watchlist = self.watchlist  # 현재 활성 워치리스트
        rebal_printed = 0  # 출력 완료된 리밸런싱 이벤트 수

        for i, date in enumerate(backtest_dates):
            self.provider.set_current_date(date)

            # 일일 리셋 (일간 PnL 초기화)
            self.engine.reset_daily_state()

            # ── 리밸런싱: 전체 유니버스 OHLCV 주입 (엔진 내부에서 자동 처리) ──
            if self.engine._rebalance_mgr and self.engine._rebalance_mgr.should_rebalance():
                full_ohlcv = self.provider.get_ohlcv_up_to_date(download_watchlist)
                self.engine.set_full_universe_ohlcv(full_ohlcv)

            # 데이터 주입 + 6-Phase 실행
            day_ohlcv = self.provider.get_ohlcv_up_to_date(active_watchlist)
            day_prices = self.provider.get_current_prices(active_watchlist)

            # v5: Arbitrage 전용 — Fixed pair ETF + Basis instrument 데이터 주입
            if self.strategy_mode == "arbitrage" and hasattr(self, '_arb_extra_watchlist'):
                arb_ohlcv = self.provider.get_ohlcv_up_to_date(self._arb_extra_watchlist)
                arb_prices = self.provider.get_current_prices(self._arb_extra_watchlist)
                for code, df in arb_ohlcv.items():
                    if code not in day_ohlcv:
                        day_ohlcv[code] = df
                for code, price in arb_prices.items():
                    if code not in day_prices:
                        day_prices[code] = price

            # VIX 주입 (복합 레짐 분류 + 사이징 디스카운트)
            if self._vix_by_date:
                vix_close = self._vix_by_date.get(date)
                if vix_close is not None:
                    self.engine.update_vix(vix_close)

            # 지수 데이터 주입 (지수 추세 기반 자동 전략 선택)
            if self._index_by_date:
                index_data = self._index_by_date.get(date)
                if index_data is not None:
                    self.engine.update_index_data(date, index_data)

            self.engine.run_backtest_day(
                date=date,
                ohlcv_cache=day_ohlcv,
                current_prices=day_prices,
            )

            # 리밸런싱 진단 출력 (엔진 내부에서 실행된 리밸런싱 이벤트)
            if self.engine._rebalance_history and len(self.engine._rebalance_history) > rebal_printed:
                event = self.engine._rebalance_history[-1]
                active_watchlist = event.new_watchlist  # 워치리스트 갱신 추적
                cycle = event.cycle_number
                added = len(event.stocks_added)
                removed = len(event.stocks_removed)
                forced = len(event.positions_force_exited)
                sys.stdout.write(
                    f"\r   🔄 리밸런스 #{cycle} ({_fmt_date(date)}): "
                    f"+{added} -{removed} 종목, ES7 청산 {forced}건\n"
                )
                rebal_printed = len(self.engine._rebalance_history)

            # 메트릭 수집
            self.collector.record_daily(date, self.engine)

            # 진행률 표시
            if (i + 1) % 50 == 0 or i == total_days - 1:
                pct = (i + 1) / total_days * 100
                equity = self.engine._get_total_equity()
                regime = self.engine._market_regime
                pos_count = len([p for p in self.engine.positions.values() if p.status == "ACTIVE"])
                sys.stdout.write(
                    f"\r   [{pct:5.1f}%] {_fmt_date(date)} | "
                    f"Equity: {self.currency_symbol}{equity:,.0f} | "
                    f"Regime: {regime} | "
                    f"Pos: {pos_count} | "
                    f"Trades: {len(self.engine.closed_trades)}"
                )
                sys.stdout.flush()

        print("\n\n✅ 백테스트 완료!\n")

        # ── 7. 최종 메트릭 계산 ──
        result = self.collector.calculate_all(self.engine)

        # 생존자 편향 결과 첨부
        if hasattr(self, '_survivorship'):
            result.survivorship_score = self._survivorship["score"]
            result.survivorship_warning = self._survivorship["warning"]
            result.survivorship_details = self._survivorship.get("details", {})

        # 리밸런싱 결과 첨부
        if self.engine._rebalance_mgr:
            result.total_rebalances = self.engine._rebalance_mgr.cycle_count
            result.avg_turnover_pct = self.engine._rebalance_mgr.avg_turnover_pct

        return result


def _fmt_date(date_str: str) -> str:
    """YYYYMMDD → YYYY-MM-DD 포맷 변환."""
    if len(date_str) == 8:
        return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
    return date_str
