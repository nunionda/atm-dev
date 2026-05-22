"""
선물 전용 백테스터 — 단일 티커 양방향(LONG/SHORT) 시뮬레이션.

기존 HistoricalBacktester는 유니버스 기반(멀티 종목)이므로,
단일 선물 티커의 양방향 매매를 위한 경량 백테스터.

고도화:
  - 거래비용 모델링 (슬리피지 + 커미션)
  - 확장 메트릭 (Sortino, Calmar, CAGR, 연승/연패, MDD Duration)
  - 서킷브레이커 (RG1 일일 손실, RG2 MDD, 거래소 CB)
  - 증거금 시뮬레이션 (개시/유지 증거금, Margin Call)
  - 롤오버 비용 (분기별 캘린더 스프레드)
  - Monte Carlo 스트레스 테스트
"""

from __future__ import annotations

import calendar
import random
from dataclasses import dataclass, field
from datetime import datetime, date as date_type, timedelta
from typing import Callable, Dict, List, Optional

import numpy as np
import pandas as pd
import yfinance as yf

from common.types import ExitSignal, PriceData
from data.config_manager import ATSConfig, ConfigManager
from infra.logger import get_logger
from strategy.sp500_futures import SP500FuturesStrategy, FuturesPositionState

logger = get_logger("futures_backtester")


@dataclass
class FuturesPosition:
    """백테스트용 선물 포지션."""
    stock_code: str
    entry_price: float
    direction: str  # "LONG" | "SHORT"
    contracts: int = 1
    entry_date: str = ""
    holding_days: int = 0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    position_id: str = ""
    stock_name: str = ""

    def __post_init__(self):
        if not self.position_id:
            self.position_id = f"FUT-{self.stock_code}-{self.entry_date}"
        if not self.stock_name:
            self.stock_name = self.stock_code


class FuturesBacktester:
    """단일 선물 티커 백테스터."""

    def __init__(
        self,
        config: ATSConfig,
        ticker: str = "ES=F",
        start_date: str = "20240101",
        end_date: str = "20260101",
        initial_equity: float = 100000.0,
        is_micro: bool = False,
        progress_callback: Optional[Callable[[float], None]] = None,
        trend_adaptive: bool = False,
    ):
        # is_micro 설정 반영
        if is_micro:
            config.sp500_futures.is_micro = True
            config.sp500_futures.contract_multiplier = 5.0

        self.trend_adaptive = trend_adaptive
        self.strategy = SP500FuturesStrategy(config, trend_adaptive=trend_adaptive)
        self.fc = config.sp500_futures
        self.ticker = ticker
        self.start_date = start_date
        self.end_date = end_date
        self.initial_equity = initial_equity
        self.is_micro = is_micro
        self.multiplier = 5.0 if is_micro else config.sp500_futures.contract_multiplier
        self.progress_callback = progress_callback

        # 거래비용
        if is_micro:
            self.slippage_per_contract = 1.25   # Micro 1 tick
            self.commission_per_contract = 0.62  # Micro round-turn
        else:
            self.slippage_per_contract = self.fc.futures_slippage_per_contract
            self.commission_per_contract = self.fc.futures_commission_per_contract

        # 증거금
        if is_micro:
            self.initial_margin = self.fc.mes_initial_margin
            self.maintenance_margin = self.fc.mes_maintenance_margin
        else:
            self.initial_margin = self.fc.es_initial_margin
            self.maintenance_margin = self.fc.es_maintenance_margin
        self.margin_calls: List[dict] = []

        # 거래소 서킷브레이커
        self.cb_events: List[dict] = []

        # 롤오버
        self.roll_events: List[dict] = []
        self.total_roll_costs = 0.0
        self._roll_dates = self._compute_roll_dates()

        # P: MR-SHORT 별도 전략 (지연 초기화)
        self._mr_short_strategy = None

        # I (진단): 방향 결정 카운터 — SHORT 차단 원인 파악용
        self.direction_stats = {
            "bars_eval": 0,         # _determine_direction 호출 횟수
            "long_called": 0,       # 방향 LONG 반환
            "short_called": 0,      # 방향 SHORT 반환
            "neutral_called": 0,    # 방향 NEUTRAL
            "long_passed": 0,       # 4-Layer + filters 모두 통과 (실제 진입)
            "short_passed": 0,
            "long_score_avg": 0.0,
            "short_score_avg": 0.0,
            "long_score_max": 0,
            "short_score_max": 0,
            "short_blocked_by_threshold": 0,  # SHORT 방향이지만 total_score < threshold
            "short_blocked_by_filter": 0,      # SHORT 방향이지만 ATR/fakeout filter 차단
            # D (진단): regime 분포 카운트
            "regime_BULL": 0,
            "regime_NEUTRAL": 0,
            "regime_BEAR": 0,
            "regime_CRISIS": 0,
            "regime_UNKNOWN": 0,
            # R (Hedge mode): direction별 PnL 누적 (attribution)
            "long_pnl_total": 0.0,
            "short_pnl_total": 0.0,
            "long_trade_count": 0,
            "short_trade_count": 0,
            "long_win_count": 0,
            "short_win_count": 0,
        }

    # ── 롤오버 유틸리티 ──

    def _compute_roll_dates(self) -> set:
        """백테스트 기간 내 자산군별 roll date 집합 반환.

        Equity Index(ES/MES/NQ/MNQ): 분기 만기의 volume migration Thursday (3rd Fri -8일)
          ⇨ 기존 "Monday before 3rd Friday"보다 실제 유동성 이전 시점에 가깝게 정정.
        Energy(CL): 매월 last trading day (전월 25일의 3 영업일 전).
        Metal(GC): active month(Feb/Apr/Jun/Aug/Oct/Dec)의 last trading day.
        """
        from backtest.walk_forward_engine import compute_roll_dates as _calc
        start_dt = datetime.strptime(self.start_date, "%Y%m%d")
        end_dt = datetime.strptime(self.end_date, "%Y%m%d")
        rolls = _calc(self.ticker, start_dt.year - 1, end_dt.year + 1)
        return {r.isoformat() for r in rolls}

    def _get_mr_short_strategy(self):
        """P: MeanReversionShortStrategy 지연 초기화."""
        if self._mr_short_strategy is None:
            from strategy.mean_reversion_short import MeanReversionShortStrategy
            self._mr_short_strategy = MeanReversionShortStrategy(self.strategy.config if hasattr(self.strategy, 'config') else None)
        return self._mr_short_strategy

    def _record_attribution(self, direction: str, pnl_dollar: float) -> None:
        """R (Hedge mode): direction별 PnL/trade/win 카운터 누적."""
        ds = self.direction_stats
        if direction == "LONG":
            ds["long_pnl_total"] += pnl_dollar
            ds["long_trade_count"] += 1
            if pnl_dollar > 0:
                ds["long_win_count"] += 1
        elif direction == "SHORT":
            ds["short_pnl_total"] += pnl_dollar
            ds["short_trade_count"] += 1
            if pnl_dollar > 0:
                ds["short_win_count"] += 1

    def _is_in_roll_blackout(self, date_str: str, blackout_business_days: int = 2) -> bool:
        """date_str이 roll date ± N영업일 이내인지 (신규 진입 차단용)."""
        from datetime import date as date_type, datetime as dt
        from backtest.walk_forward_engine import is_in_blackout
        try:
            target = dt.fromisoformat(date_str).date() if "-" in date_str else dt.strptime(date_str, "%Y%m%d").date()
        except (ValueError, TypeError):
            return False
        roll_objs = []
        for r in self._roll_dates:
            try:
                roll_objs.append(date_type.fromisoformat(r))
            except (ValueError, TypeError):
                continue
        return is_in_blackout(target, roll_objs, blackout_business_days)

    @staticmethod
    def _third_friday(year: int, month: int) -> date_type:
        """주어진 년/월의 셋째 금요일 계산."""
        c = calendar.Calendar(firstweekday=calendar.MONDAY)
        fridays = [
            d for d in c.itermonthdays2(year, month)
            if d[0] != 0 and d[1] == calendar.FRIDAY
        ]
        return date_type(year, month, fridays[2][0])

    # ── 거래소 서킷브레이커 ──

    def _check_exchange_cb(self, close: float, prev_close: float) -> Optional[str]:
        """거래소 CB 체크. 발동 시 레벨 문자열 반환."""
        if not self.fc.exchange_cb_enabled or prev_close <= 0:
            return None
        pct_change = (close - prev_close) / prev_close
        if pct_change <= -self.fc.cb_level3_pct:
            return "LEVEL3"
        if pct_change <= -self.fc.cb_level2_pct:
            return "LEVEL2"
        if pct_change <= -self.fc.cb_level1_pct:
            return "LEVEL1"
        return None

    def run(self) -> dict:
        """백테스트 실행. metrics + equity_curve + trades 반환."""
        # 1. 데이터 다운로드 (워밍업 포함)
        start_dt = datetime.strptime(self.start_date, "%Y%m%d")
        end_dt = datetime.strptime(self.end_date, "%Y%m%d")

        warmup_start = start_dt - pd.Timedelta(days=365)

        raw = yf.download(
            self.ticker,
            start=warmup_start.strftime("%Y-%m-%d"),
            end=end_dt.strftime("%Y-%m-%d"),
            auto_adjust=False,
            progress=False,
        )

        if raw.empty:
            logger.error("No data for %s", self.ticker)
            return self._empty_result()

        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.droplevel(1)

        # 중복 컬럼 제거 (yfinance 버그 방지)
        raw = raw.loc[:, ~raw.columns.duplicated()]

        df = raw.rename(columns={
            "Open": "open", "High": "high", "Low": "low",
            "Close": "close", "Volume": "volume",
        })
        df = df[["open", "high", "low", "close", "volume"]].dropna()

        df = self.strategy.calculate_indicators(df)
        if df.empty:
            return self._empty_result()

        df_bt = df[df.index >= start_dt].copy()
        if len(df_bt) < 10:
            return self._empty_result()

        # 2. 바별 시뮬레이션
        # Q (Walk-Forward 진단): LONG/SHORT 동시 보유 허용 — positions dict.
        # 기존: 단일 position 변수 → MR-SHORT가 LONG 보유 중 진입 못해 강세장 paradox.
        # 변경: dict 키 "LONG"/"SHORT"로 분리 보유. 청산 분기 모두 outer loop로 감쌈.
        equity = self.initial_equity
        peak_equity = equity
        positions: Dict[str, FuturesPosition] = {}
        trades: List[dict] = []
        equity_curve: List[dict] = []
        total_costs = 0.0
        day_start_equity = equity  # RG1 일일 손실 추적
        prev_date_str = ""
        rg2_halt_days = 0  # RG2 서킷브레이커 쿨다운 카운터
        consec_halt_days = 0  # 연속손절 쿨다운 카운터
        RG2_COOLDOWN = 60  # 60 거래일 후 리셋
        CONSEC_COOLDOWN = 20  # 연속손절 후 20 거래일 쿨다운

        def _unrealized_total(price: float) -> float:
            """모든 보유 포지션의 unrealized PnL 합산."""
            return sum(self._unrealized_pnl(p, price) for p in positions.values())

        def _contracts_total() -> int:
            return sum(p.contracts for p in positions.values())

        total_bars = len(df_bt)
        for i, (date, row) in enumerate(df_bt.iterrows()):
            current_price = float(row["close"])
            date_str = date.strftime("%Y-%m-%d") if hasattr(date, "strftime") else str(date)

            # 진행률 보고 (50봉마다)
            if self.progress_callback and i % 50 == 0:
                self.progress_callback(i / total_bars * 100)

            # 새로운 거래일 → 일일 시작 에쿼티 갱신
            if date_str != prev_date_str:
                day_start_equity = equity + _unrealized_total(current_price)
                prev_date_str = date_str

            prev_close = float(df_bt.iloc[max(0, i - 1)]["close"])

            # ── 거래소 서킷브레이커 체크 ──
            cb_level = self._check_exchange_cb(current_price, prev_close)
            cb_block_entry = False
            if cb_level:
                self.cb_events.append({
                    "date": date_str,
                    "level": cb_level,
                    "pct_change": round((current_price - prev_close) / prev_close * 100, 2),
                })
                cb_block_entry = True  # 모든 레벨에서 신규 진입 차단

            # ── 롤오버 비용 처리 (모든 보유 포지션) ──
            if date_str in self._roll_dates and positions:
                total_contracts = _contracts_total()
                roll_cost = total_contracts * self.fc.roll_cost_per_contract
                equity -= roll_cost
                self.total_roll_costs += roll_cost
                total_costs += roll_cost
                self.roll_events.append({
                    "date": date_str,
                    "contracts": total_contracts,
                    "cost": round(roll_cost, 2),
                })

            # P4-4: BR-R02 Panic Stop — MDD 도달 시 모든 보유 포지션 즉시 청산
            if positions and peak_equity > 0:
                _pre_total = equity + _unrealized_total(current_price)
                _cur_dd = (_pre_total - peak_equity) / peak_equity
                if _cur_dd <= self.fc.rg2_mdd_limit:
                    # 강제 청산 — 모든 positions
                    for _dir_key in list(positions.keys()):
                        position = positions[_dir_key]
                        if position.direction == "LONG":
                            _pnl_points = current_price - position.entry_price
                        else:
                            _pnl_points = position.entry_price - current_price
                        _pnl_dollar = _pnl_points * position.contracts * self.multiplier
                        _exit_cost = position.contracts * (
                            self.slippage_per_contract + self.commission_per_contract / 2
                        )
                        _pnl_dollar -= _exit_cost
                        total_costs += _exit_cost
                        _pnl_pct = _pnl_points / position.entry_price if position.entry_price > 0 else 0
                        equity += _pnl_dollar
                        trades.append(self._make_trade_record(
                            position, date_str, current_price, _pnl_dollar, _pnl_pct, "MDD_PANIC_STOP",
                        ))
                        self.strategy.record_trade_result(_pnl_pct)
                        self._record_attribution(position.direction, _pnl_dollar)
                        del positions[_dir_key]
                    self.strategy._position_states.pop(self.ticker, None)
                    logger.warning(
                        "MDD_PANIC_STOP | %s | DD=%.2f%% ≤ limit %.2f%% | equity=$%.0f",
                        self.ticker, _cur_dd * 100, self.fc.rg2_mdd_limit * 100, equity,
                    )

            # 포지션 보유 중 → 청산 체크 (모든 positions outer loop)
            for dir_key in list(positions.keys()):
                position = positions[dir_key]
                position.holding_days += 1

                # ── Margin Call 체크 ──
                unrealized = self._unrealized_pnl(position, current_price)
                if self.fc.margin_call_enabled:
                    required_margin = self.maintenance_margin * position.contracts
                    if (equity + unrealized) < required_margin:
                        # Margin Call → 강제 청산
                        if position.direction == "LONG":
                            pnl_points = current_price - position.entry_price
                        else:
                            pnl_points = position.entry_price - current_price

                        pnl_dollar = pnl_points * position.contracts * self.multiplier
                        exit_cost = position.contracts * (
                            self.slippage_per_contract + self.commission_per_contract / 2
                        )
                        pnl_dollar -= exit_cost
                        total_costs += exit_cost
                        pnl_pct = pnl_points / position.entry_price if position.entry_price > 0 else 0
                        equity += pnl_dollar

                        trades.append(self._make_trade_record(
                            position, date_str, current_price, pnl_dollar, pnl_pct, "MARGIN_CALL",
                        ))
                        self._record_attribution(position.direction, pnl_dollar)
                        self.margin_calls.append({
                            "date": date_str,
                            "equity": round(equity + unrealized, 2),
                            "required": round(required_margin, 2),
                        })
                        self.strategy.record_trade_result(pnl_pct)
                        self.strategy._position_states.pop(self.ticker, None)
                        del positions[dir_key]
                        continue  # 다음 dir_key

                # ── 거래소 CB Level 2/3 → 강제 청산 ──
                if cb_level in ("LEVEL2", "LEVEL3"):
                    if position.direction == "LONG":
                        pnl_points = current_price - position.entry_price
                    else:
                        pnl_points = position.entry_price - current_price

                    pnl_dollar = pnl_points * position.contracts * self.multiplier
                    exit_cost = position.contracts * (
                        self.slippage_per_contract + self.commission_per_contract / 2
                    )
                    pnl_dollar -= exit_cost
                    total_costs += exit_cost
                    pnl_pct = pnl_points / position.entry_price if position.entry_price > 0 else 0
                    equity += pnl_dollar

                    trades.append(self._make_trade_record(
                        position, date_str, current_price, pnl_dollar, pnl_pct, f"CB_{cb_level}",
                    ))
                    self.strategy.record_trade_result(pnl_pct)
                    self._record_attribution(position.direction, pnl_dollar)
                    self.strategy._position_states.pop(self.ticker, None)
                    del positions[dir_key]
                    continue

                # ── 전략 퇴출 시그널 ──
                if True:  # position 보유 중 (이미 위에서 continue로 청산 분기 skip됨)
                    price_data = PriceData(
                        stock_code=self.ticker,
                        stock_name=self.ticker,
                        current_price=current_price,
                        open_price=float(row["open"]),
                        high_price=float(row["high"]),
                        low_price=float(row["low"]),
                        prev_close=prev_close,
                        volume=int(row.get("volume", 0)),
                        change_pct=0.0,
                        timestamp=date_str,
                    )

                    df_slice = df.loc[:date]

                    exit_signals = self.strategy.scan_exit_signals(
                        positions=[position],
                        ohlcv_data={self.ticker: df_slice},
                        current_prices={self.ticker: price_data},
                    )

                    if exit_signals:
                        exit_sig = exit_signals[0]
                        if position.direction == "LONG":
                            pnl_points = current_price - position.entry_price
                        else:
                            pnl_points = position.entry_price - current_price

                        pnl_dollar = pnl_points * position.contracts * self.multiplier

                        exit_cost = position.contracts * (
                            self.slippage_per_contract + self.commission_per_contract / 2
                        )
                        pnl_dollar -= exit_cost
                        total_costs += exit_cost

                        pnl_pct = pnl_points / position.entry_price if position.entry_price > 0 else 0
                        equity += pnl_dollar

                        trades.append(self._make_trade_record(
                            position, date_str, current_price, pnl_dollar, pnl_pct, exit_sig.exit_reason,
                        ))

                        self.strategy.record_trade_result(pnl_pct)
                        self._record_attribution(position.direction, pnl_dollar)
                        self.strategy._position_states.pop(self.ticker, None)
                        del positions[dir_key]
                        continue

            # 신규 진입 체크 — Q: LONG/SHORT 동시 보유 허용. signal.direction이
            # positions에 없으면 추가 진입 가능. 즉 LONG 보유 중 SHORT signal 진입 OK.
            # 단 RG1/RG2/CB/Roll blackout 등 진입 게이트는 그대로 적용.
            if True:
                # RG1: 일일 손실 한도
                total_value = equity
                daily_pnl_pct = (total_value - day_start_equity) / day_start_equity if day_start_equity > 0 else 0

                # RG2: MDD 한도 (쿨다운 리셋 포함)
                mdd_breached = peak_equity > 0 and (total_value - peak_equity) / peak_equity <= self.fc.rg2_mdd_limit
                if mdd_breached:
                    rg2_halt_days += 1
                    if rg2_halt_days >= RG2_COOLDOWN:
                        peak_equity = total_value
                        rg2_halt_days = 0
                        mdd_breached = False
                        self.strategy._trade_history = []
                else:
                    rg2_halt_days = 0

                # 연속손절 쿨다운
                if self.strategy._consecutive_losses >= self.strategy.fc.max_consecutive_losses:
                    consec_halt_days += 1
                    if consec_halt_days >= CONSEC_COOLDOWN:
                        self.strategy._consecutive_losses = 0
                        consec_halt_days = 0
                        self.strategy._trade_history = []
                else:
                    consec_halt_days = 0

                # Roll blackout: roll date ±2 영업일 이내 신규 진입 차단
                # (실제 유동성 이전기 spread/slippage 회피)
                roll_blackout = self._is_in_roll_blackout(date_str)

                if cb_block_entry:
                    pass  # 거래소 CB 차단
                elif roll_blackout:
                    pass  # Roll blackout 차단
                elif daily_pnl_pct <= self.fc.rg1_daily_loss_limit:
                    pass  # RG1 차단
                elif mdd_breached:
                    pass  # RG2 차단
                else:
                    # P0-2: Lookahead bias 제거 — 진입 신호는 "전봉까지의 indicators"로만 판단.
                    # 라이브: 봉 N 종료 → 신호 발생 → 봉 N+1 open에 진입 (현재 N의 close는 모름)
                    # 백테스트: df_slice를 date 직전까지로 잘라 strategy가 N-1봉 close를 사용하도록 함.
                    # 진입 가격은 현재 봉 close 유지 (≈ 다음 봉 open 가정).
                    df_slice = df.loc[df.index < date]
                    signal = self.strategy.generate_futures_signal(
                        code=self.ticker,
                        df=df_slice,
                        current_price=current_price,
                        equity=equity,
                    )

                    # P+Q+U (Walk-Forward 재설계): MR-SHORT 별도 path.
                    # Q (dict refactor): 1 ticker 1 position 제약 해제 → LONG 보유 중에도
                    # SHORT 진입 가능.
                    # T: per-ticker enable_short=False면 MR-SHORT path도 차단.
                    # U: regime_strategy_modes.mr_short 기반으로 활성/비활성 결정
                    #   - BULL: False (LONG 기회 보호, P-3 paradox 해결)
                    #   - NEUTRAL/BEAR: True (mean-reversion 적정 환경)
                    #   - CRISIS: False (극단적 하락에서 신규 진입 위험)
                    allow_short_for_ticker = self.strategy._get_ticker_override(
                        self.ticker, "enable_short", True
                    )
                    if signal is None and "SHORT" not in positions and allow_short_for_ticker:
                        rr = getattr(self.strategy, "_last_regime_result", None)
                        regime = getattr(rr, "regime", None) if rr else None
                        # U: regime별 MR-SHORT 활성 여부 조회 (default: BULL/CRISIS 제외)
                        default_mr = regime not in ("BULL", "CRISIS")
                        mr_enabled = self.strategy._get_regime_mode(
                            regime, "mr_short", default_mr
                        )
                        if mr_enabled:
                            mr_signal = self._get_mr_short_strategy().generate_short_signal(
                                ticker=self.ticker,
                                df=df_slice,
                                current_price=current_price,
                                equity=equity,
                            )
                            if mr_signal is not None:
                                signal = mr_signal
                                self.direction_stats["mr_short_passed"] = (
                                    self.direction_stats.get("mr_short_passed", 0) + 1
                                )

                    # Q: 이미 같은 방향 보유 중이면 signal 무효 (dict 키 중복 차단)
                    if signal is not None and signal.direction in positions:
                        signal = None

                    # I (진단): 방향 결정 통계 누적
                    ds = self.direction_stats
                    ds["bars_eval"] += 1
                    ls = getattr(self.strategy, "_last_long_score", 0)
                    ss = getattr(self.strategy, "_last_short_score", 0)
                    # D (진단): regime 분포
                    rr = getattr(self.strategy, "_last_regime_result", None)
                    if rr and getattr(rr, "regime", None):
                        ds[f"regime_{rr.regime}"] = ds.get(f"regime_{rr.regime}", 0) + 1
                    else:
                        ds["regime_UNKNOWN"] += 1
                    ds["long_score_max"] = max(ds["long_score_max"], ls)
                    ds["short_score_max"] = max(ds["short_score_max"], ss)
                    # rolling avg (incremental)
                    n = ds["bars_eval"]
                    ds["long_score_avg"] = ds["long_score_avg"] + (ls - ds["long_score_avg"]) / n
                    ds["short_score_avg"] = ds["short_score_avg"] + (ss - ds["short_score_avg"]) / n
                    # direction 분기
                    if ls >= 3 and ls > ss:
                        ds["long_called"] += 1
                        if signal and signal.direction == "LONG":
                            ds["long_passed"] += 1
                    elif ss >= 3 and ss > ls:
                        ds["short_called"] += 1
                        if signal and signal.direction == "SHORT":
                            ds["short_passed"] += 1
                        elif not signal:
                            # signal=None인 이유: total_score < threshold or filter
                            # 둘은 generate_futures_signal 내부 흐름으로 구분 어려움 →
                            # threshold가 가장 흔한 원인이라 추정
                            ds["short_blocked_by_threshold"] += 1
                    else:
                        ds["neutral_called"] += 1

                    if signal:
                        contracts = signal.position_size_contracts

                        # ── 증거금 검증 ──
                        if self.fc.margin_call_enabled:
                            max_affordable = int(equity // self.initial_margin) if self.initial_margin > 0 else contracts
                            contracts = min(contracts, max_affordable)
                            if contracts <= 0:
                                contracts = 0  # 증거금 부족 → 진입 불가

                        if contracts > 0:
                            entry_cost = contracts * (
                                self.slippage_per_contract + self.commission_per_contract / 2
                            )
                            equity -= entry_cost
                            total_costs += entry_cost

                            new_position = FuturesPosition(
                                stock_code=self.ticker,
                                entry_price=current_price,
                                direction=signal.direction,
                                contracts=contracts,
                                entry_date=date_str,
                                stop_loss=signal.stop_loss,
                                take_profit=signal.take_profit,
                            )
                            # 레짐 정보 저장 (trend_adaptive 모드)
                            if self.trend_adaptive and self.strategy._last_regime_result:
                                new_position._regime_at_entry = self.strategy._last_regime_result.regime
                                new_position._trend_score = self.strategy._last_regime_result.trend_score
                            else:
                                new_position._regime_at_entry = "UNKNOWN"
                                new_position._trend_score = 0

                            # Q: positions dict에 저장 (LONG/SHORT 각각)
                            positions[signal.direction] = new_position

                            state = self.strategy._get_position_state(self.ticker)
                            state.reset_for_entry(signal.direction, current_price)

            # Equity curve 기록 (Q: 모든 positions 합산)
            unrealized = _unrealized_total(current_price)
            total_value = equity + unrealized
            peak_equity = max(peak_equity, total_value)
            drawdown = (total_value - peak_equity) / peak_equity if peak_equity > 0 else 0

            total_contracts = _contracts_total()
            margin_used = total_contracts * self.initial_margin
            notional = current_price * total_contracts * self.multiplier
            eff_leverage = notional / max(total_value, 1) if total_contracts > 0 else 0.0

            equity_curve.append({
                "date": date_str,
                "total_value": round(total_value, 2),
                "equity": round(equity, 2),
                "drawdown_pct": round(drawdown * 100, 2),
                "margin_used": round(margin_used, 2),
                "effective_leverage": round(eff_leverage, 2),
            })

        # 미청산 포지션 강제 청산 (Q: 모든 positions)
        if positions and len(df_bt) > 0:
            last_row = df_bt.iloc[-1]
            last_price = float(last_row["close"])
            last_date = df_bt.index[-1].strftime("%Y-%m-%d")

            for dir_key in list(positions.keys()):
                position = positions[dir_key]
                if position.direction == "LONG":
                    pnl_points = last_price - position.entry_price
                else:
                    pnl_points = position.entry_price - last_price

                pnl_dollar = pnl_points * position.contracts * self.multiplier
                exit_cost = position.contracts * (
                    self.slippage_per_contract + self.commission_per_contract / 2
                )
                pnl_dollar -= exit_cost
                total_costs += exit_cost

                pnl_pct = pnl_points / position.entry_price if position.entry_price > 0 else 0
                equity += pnl_dollar

                trades.append(self._make_trade_record(
                    position, last_date, last_price, pnl_dollar, pnl_pct, "FORCED_CLOSE",
                ))
                self.strategy.record_trade_result(pnl_pct)
                self._record_attribution(position.direction, pnl_dollar)
                del positions[dir_key]

        # 3. Metrics 계산
        metrics = self._calculate_metrics(trades, equity_curve, total_costs)

        # 증거금/CB/롤오버 메트릭 추가
        metrics["margin_call_count"] = len(self.margin_calls)
        metrics["cb_event_count"] = len(self.cb_events)
        metrics["cb_events_detail"] = self.cb_events[:20]  # 최대 20개
        metrics["roll_count"] = len(self.roll_events)
        metrics["total_roll_costs"] = round(self.total_roll_costs, 2)

        # I (진단): 방향 통계 — SHORT 차단 원인 파악용
        ds = self.direction_stats
        metrics["direction_stats"] = {
            "bars_eval": ds["bars_eval"],
            "long_called": ds["long_called"],
            "short_called": ds["short_called"],
            "neutral_called": ds["neutral_called"],
            "long_passed": ds["long_passed"],
            "short_passed": ds["short_passed"],
            "short_blocked": ds["short_blocked_by_threshold"],
            "long_score_avg": round(ds["long_score_avg"], 2),
            "short_score_avg": round(ds["short_score_avg"], 2),
            "long_score_max": ds["long_score_max"],
            "short_score_max": ds["short_score_max"],
            "regime_dist": {
                "BULL": ds["regime_BULL"],
                "NEUTRAL": ds["regime_NEUTRAL"],
                "BEAR": ds["regime_BEAR"],
                "CRISIS": ds["regime_CRISIS"],
                "UNKNOWN": ds["regime_UNKNOWN"],
            },
            "mr_short_passed": ds.get("mr_short_passed", 0),  # P 진단
            # R (Hedge mode): direction별 attribution
            "long_pnl_total": round(ds.get("long_pnl_total", 0.0), 2),
            "short_pnl_total": round(ds.get("short_pnl_total", 0.0), 2),
            "long_trade_count": ds.get("long_trade_count", 0),
            "short_trade_count": ds.get("short_trade_count", 0),
            "long_win_rate": round(
                ds.get("long_win_count", 0) / max(ds.get("long_trade_count", 0), 1) * 100, 1
            ),
            "short_win_rate": round(
                ds.get("short_win_count", 0) / max(ds.get("short_trade_count", 0), 1) * 100, 1
            ),
        }

        # 레버리지 통계
        leverages = [e["effective_leverage"] for e in equity_curve if e["effective_leverage"] > 0]
        metrics["max_effective_leverage"] = round(max(leverages), 2) if leverages else 0.0
        margins = [e["margin_used"] for e in equity_curve if e["margin_used"] > 0]
        equities = [e["total_value"] for i, e in enumerate(equity_curve) if e["margin_used"] > 0]
        metrics["avg_margin_utilization"] = (
            round(sum(margins) / sum(equities) * 100, 1) if equities and sum(equities) > 0 else 0.0
        )

        return {
            "ticker": self.ticker,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "initial_equity": self.initial_equity,
            "final_equity": round(equity, 2),
            "trend_adaptive": self.trend_adaptive,
            "metrics": metrics,
            "equity_curve": equity_curve,
            "trades": trades,
        }

    def _make_trade_record(
        self, position: FuturesPosition, exit_date: str, exit_price: float,
        pnl_dollar: float, pnl_pct: float, exit_reason: str,
    ) -> dict:
        """트레이드 기록 생성 (regime 정보 포함)."""
        record = {
            "entry_date": position.entry_date,
            "exit_date": exit_date,
            "direction": position.direction,
            "entry_price": round(position.entry_price, 2),
            "exit_price": round(exit_price, 2),
            "contracts": position.contracts,
            "pnl_dollar": round(pnl_dollar, 2),
            "pnl_pct": round(pnl_pct * 100, 2),
            "holding_days": position.holding_days,
            "exit_reason": exit_reason,
        }
        if self.trend_adaptive:
            record["regime_at_entry"] = getattr(position, "_regime_at_entry", "UNKNOWN")
            record["trend_score"] = getattr(position, "_trend_score", 0)
        return record

    def _unrealized_pnl(self, position: Optional[FuturesPosition], current_price: float) -> float:
        if position is None:
            return 0.0
        if position.direction == "LONG":
            return (current_price - position.entry_price) * position.contracts * self.multiplier
        return (position.entry_price - current_price) * position.contracts * self.multiplier

    def _calculate_metrics(self, trades: List[dict], equity_curve: List[dict], total_costs: float) -> dict:
        """확장 성과 지표 계산."""
        if not trades:
            return self._empty_metrics()

        pnls = [t["pnl_dollar"] for t in trades]
        pnl_pcts = [t["pnl_pct"] for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]

        total_return_pct = ((self.initial_equity + sum(pnls)) / self.initial_equity - 1) * 100
        win_rate = len(wins) / len(trades) * 100 if trades else 0
        avg_win = np.mean(wins) if wins else 0
        avg_loss = abs(np.mean(losses)) if losses else 1
        profit_factor = sum(wins) / abs(sum(losses)) if losses and sum(losses) != 0 else float("inf")

        # MDD + MDD Duration
        max_dd = 0.0
        mdd_duration_days = 0
        if equity_curve:
            dd_values = [e["drawdown_pct"] for e in equity_curve]
            max_dd = min(dd_values) if dd_values else 0.0

            # MDD Duration: 고점 회복까지 최대 일수
            underwater_days = 0
            for e in equity_curve:
                if e["drawdown_pct"] < -0.01:  # underwater
                    underwater_days += 1
                    mdd_duration_days = max(mdd_duration_days, underwater_days)
                else:
                    underwater_days = 0

        # Daily returns for Sharpe/Sortino
        daily_returns = pd.Series(dtype=float)
        sharpe = 0.0
        sortino = 0.0
        if len(equity_curve) > 1:
            values = [e["total_value"] for e in equity_curve]
            daily_returns = pd.Series(values).pct_change().dropna()
            if len(daily_returns) > 0 and daily_returns.std() > 0:
                sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252)

            # Sortino (downside deviation)
            downside = daily_returns[daily_returns < 0]
            if len(downside) > 0:
                downside_std = np.sqrt(np.mean(downside ** 2))
                if downside_std > 0:
                    sortino = (daily_returns.mean() / downside_std) * np.sqrt(252)

        # CAGR + Calmar
        cagr = 0.0
        calmar = 0.0
        if len(equity_curve) > 1:
            years = len(equity_curve) / 252
            final_val = equity_curve[-1]["total_value"]
            if years > 0 and final_val > 0:
                cagr = (final_val / self.initial_equity) ** (1 / years) - 1
                if max_dd < 0:
                    calmar = cagr / abs(max_dd / 100)

        # Consecutive wins/losses
        max_consec_wins = 0
        max_consec_losses = 0
        curr_wins = 0
        curr_losses = 0
        for t in trades:
            if t["pnl_dollar"] > 0:
                curr_wins += 1
                curr_losses = 0
                max_consec_wins = max(max_consec_wins, curr_wins)
            else:
                curr_losses += 1
                curr_wins = 0
                max_consec_losses = max(max_consec_losses, curr_losses)

        # Best/worst trade
        best_trade = max(pnl_pcts) if pnl_pcts else 0
        worst_trade = min(pnl_pcts) if pnl_pcts else 0

        # 방향별 통계
        long_trades = [t for t in trades if t["direction"] == "LONG"]
        short_trades = [t for t in trades if t["direction"] == "SHORT"]
        long_wins = len([t for t in long_trades if t["pnl_dollar"] > 0])
        short_wins = len([t for t in short_trades if t["pnl_dollar"] > 0])

        # Monte Carlo
        monte_carlo = self._run_monte_carlo(daily_returns)

        result = {
            "total_return_pct": round(total_return_pct, 2),
            "sharpe_ratio": round(sharpe, 2),
            "sortino_ratio": round(sortino, 2),
            "calmar_ratio": round(calmar, 2),
            "cagr": round(cagr * 100, 2),
            "max_drawdown_pct": round(max_dd, 2),
            "mdd_duration_days": mdd_duration_days,
            "total_trades": len(trades),
            "win_rate": round(win_rate, 1),
            "profit_factor": round(profit_factor, 2) if profit_factor != float("inf") else 999.0,
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "avg_rr": round(avg_win / avg_loss, 2) if avg_loss > 0 else 0,
            "total_pnl": round(sum(pnls), 2),
            "total_costs": round(total_costs, 2),
            "long_trades": len(long_trades),
            "short_trades": len(short_trades),
            "long_win_rate": round(long_wins / len(long_trades) * 100, 1) if long_trades else 0,
            "short_win_rate": round(short_wins / len(short_trades) * 100, 1) if short_trades else 0,
            "avg_holding_days": round(np.mean([t["holding_days"] for t in trades]), 1) if trades else 0,
            "max_consecutive_wins": max_consec_wins,
            "max_consecutive_losses": max_consec_losses,
            "best_trade_pct": round(best_trade, 2),
            "worst_trade_pct": round(worst_trade, 2),
            "exit_reasons": self._count_exit_reasons(trades),
            "monte_carlo": monte_carlo,
        }

        # Trend-adaptive 모드: 레짐별 통계 추가
        if self.trend_adaptive:
            regime_stats = {}
            for t in trades:
                regime = t.get("regime_at_entry", "UNKNOWN")
                if regime not in regime_stats:
                    regime_stats[regime] = {"trades": 0, "wins": 0, "total_pnl": 0.0}
                regime_stats[regime]["trades"] += 1
                if t["pnl_dollar"] > 0:
                    regime_stats[regime]["wins"] += 1
                regime_stats[regime]["total_pnl"] += t["pnl_dollar"]

            for regime, stats in regime_stats.items():
                stats["win_rate"] = round(stats["wins"] / stats["trades"] * 100, 1) if stats["trades"] > 0 else 0
                stats["total_pnl"] = round(stats["total_pnl"], 2)

            result["regime_stats"] = regime_stats
            result["trend_adaptive"] = True

        return result

    def _run_monte_carlo(self, daily_returns: pd.Series, n_simulations: int = 1000, n_days: int = 252) -> dict:
        """Monte Carlo 부트스트랩 스트레스 테스트."""
        empty_mc = {
            "var_95": 0, "cvar_99": 0, "worst_mdd": 0, "median_return": 0, "bankruptcy_prob": 0,
            "return_distribution": [], "mdd_distribution": [],
            "return_percentiles": {"p5": 0, "p25": 0, "p50": 0, "p75": 0, "p95": 0},
        }
        if len(daily_returns) < 20:
            return empty_mc

        returns_list = daily_returns.tolist()
        final_returns = []
        max_drawdowns = []
        bankrupt_count = 0

        random.seed(42)
        for _ in range(n_simulations):
            sampled = random.choices(returns_list, k=n_days)
            equity = 1.0
            peak = 1.0
            worst_dd = 0.0

            for r in sampled:
                equity *= (1 + r)
                peak = max(peak, equity)
                dd = (equity - peak) / peak
                worst_dd = min(worst_dd, dd)

            final_returns.append(equity - 1)
            max_drawdowns.append(worst_dd)
            if equity < 0.5:
                bankrupt_count += 1

        final_returns.sort()
        max_drawdowns.sort()

        var_95_idx = max(0, int(n_simulations * 0.05) - 1)
        cvar_99_count = max(1, int(n_simulations * 0.01))
        cvar_99 = np.mean(final_returns[:cvar_99_count])

        # 분포 히스토그램 데이터 (20 bins)
        final_arr = np.array(final_returns) * 100
        mdd_arr = np.array(max_drawdowns) * 100

        ret_counts, ret_edges = np.histogram(final_arr, bins=20)
        mdd_counts, mdd_edges = np.histogram(mdd_arr, bins=20)

        return {
            "var_95": round(abs(final_returns[var_95_idx]) * 100, 2),
            "cvar_99": round(abs(cvar_99) * 100, 2),
            "worst_mdd": round(abs(min(max_drawdowns)) * 100, 2),
            "median_return": round(np.median(final_returns) * 100, 2),
            "bankruptcy_prob": round(bankrupt_count / n_simulations * 100, 2),
            "return_distribution": [
                {"bin": round(float(ret_edges[i]), 1), "count": int(ret_counts[i])}
                for i in range(len(ret_counts))
            ],
            "mdd_distribution": [
                {"bin": round(float(mdd_edges[i]), 1), "count": int(mdd_counts[i])}
                for i in range(len(mdd_counts))
            ],
            "return_percentiles": {
                "p5": round(float(np.percentile(final_arr, 5)), 2),
                "p25": round(float(np.percentile(final_arr, 25)), 2),
                "p50": round(float(np.percentile(final_arr, 50)), 2),
                "p75": round(float(np.percentile(final_arr, 75)), 2),
                "p95": round(float(np.percentile(final_arr, 95)), 2),
            },
        }

    def _count_exit_reasons(self, trades: List[dict]) -> dict:
        """청산 사유별 카운트."""
        reasons: Dict[str, int] = {}
        for t in trades:
            reason = t.get("exit_reason", "UNKNOWN")
            reasons[reason] = reasons.get(reason, 0) + 1
        return reasons

    def _empty_metrics(self) -> dict:
        return {
            "total_return_pct": 0, "sharpe_ratio": 0, "sortino_ratio": 0,
            "calmar_ratio": 0, "cagr": 0,
            "max_drawdown_pct": 0, "mdd_duration_days": 0,
            "total_trades": 0, "win_rate": 0, "profit_factor": 0,
            "avg_win": 0, "avg_loss": 0, "avg_rr": 0, "total_pnl": 0,
            "total_costs": 0,
            "long_trades": 0, "short_trades": 0,
            "long_win_rate": 0, "short_win_rate": 0,
            "avg_holding_days": 0,
            "max_consecutive_wins": 0, "max_consecutive_losses": 0,
            "best_trade_pct": 0, "worst_trade_pct": 0,
            "exit_reasons": {},
            "monte_carlo": {
                "var_95": 0, "cvar_99": 0, "worst_mdd": 0, "median_return": 0, "bankruptcy_prob": 0,
                "return_distribution": [], "mdd_distribution": [],
                "return_percentiles": {"p5": 0, "p25": 0, "p50": 0, "p75": 0, "p95": 0},
            },
            # 증거금/CB/롤오버
            "margin_call_count": 0, "max_effective_leverage": 0, "avg_margin_utilization": 0,
            "cb_event_count": 0, "cb_events_detail": [],
            "roll_count": 0, "total_roll_costs": 0,
        }

    def _empty_result(self) -> dict:
        return {
            "ticker": self.ticker,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "initial_equity": self.initial_equity,
            "final_equity": self.initial_equity,
            "metrics": self._empty_metrics(),
            "equity_curve": [],
            "trades": [],
        }
