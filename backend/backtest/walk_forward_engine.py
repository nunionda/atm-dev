"""
Walk-Forward Backtest Engine — 자산별 contract life cycle에 맞춘 윈도우 평가.

설계:
  - Equity Index(ES/MES/NQ/MNQ): 3개월 윈도우 × 4 (분기 H/M/U/Z)
  - Commodity Monthly(CL): 1개월 윈도우 × 12 (월별 F~Z)
  - Metal Bi-monthly(GC): 1개월 윈도우 × 12 (사용자 결정: active month당 1m × 12)

각 윈도우는 하나의 contract life에 fully contained되어 yfinance =F continuous
시리즈의 roll-induced 가격 점프를 회피한다.

윈도우별로 FuturesBacktester를 호출하고, 결과 메트릭의 분포 통계
(median, p25, p75, worst, best)를 집계한다.
"""

from __future__ import annotations

import calendar
import copy
import statistics
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Callable, List, Optional

from data.config_manager import ATSConfig
from infra.logger import get_logger

logger = get_logger("walk_forward")


# ──────────────────────────────────────────────
# Asset Class Detection
# ──────────────────────────────────────────────

EQUITY_INDEX_TICKERS = {"ES=F", "MES=F", "NQ=F", "MNQ=F"}
ENERGY_TICKERS = {"CL=F", "MCL=F"}
METAL_TICKERS = {"GC=F", "MGC=F", "SI=F", "SIL=F"}


def detect_asset_class(ticker: str) -> str:
    """ticker → 'equity_index' | 'energy' | 'metal'"""
    if ticker in EQUITY_INDEX_TICKERS:
        return "equity_index"
    if ticker in ENERGY_TICKERS:
        return "energy"
    if ticker in METAL_TICKERS:
        return "metal"
    # 기본은 equity로 — 알 수 없는 ticker는 분기 cycle 가정
    return "equity_index"


# ──────────────────────────────────────────────
# Window Definitions
# ──────────────────────────────────────────────

@dataclass
class Window:
    """단일 평가 윈도우 (한 contract life 내부)."""
    index: int               # 0-based
    label: str               # 예: "2026Q1" or "2026-03"
    start_date: str          # YYYYMMDD
    end_date: str            # YYYYMMDD
    contract_code: str       # 예: "ESH26" or "CLG26"

    def duration_days(self) -> int:
        s = datetime.strptime(self.start_date, "%Y%m%d")
        e = datetime.strptime(self.end_date, "%Y%m%d")
        return (e - s).days


@dataclass
class WindowMetrics:
    """단일 윈도우 백테스트 결과 메트릭."""
    window: Window
    total_return_pct: float = 0.0
    total_pnl: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    total_trades: int = 0
    long_trades: int = 0
    short_trades: int = 0
    avg_holding_days: float = 0.0
    error: Optional[str] = None


@dataclass
class DistributionStats:
    """다중 윈도우의 분포 통계."""
    metric: str
    count: int
    median: float
    mean: float
    p25: float
    p75: float
    worst: float
    best: float


@dataclass
class WalkForwardResult:
    """전체 walk-forward 결과."""
    ticker: str
    asset_class: str
    window_size_months: int
    n_windows: int
    windows: List[WindowMetrics] = field(default_factory=list)
    distributions: List[DistributionStats] = field(default_factory=list)
    completed_at: str = ""
    errors: List[str] = field(default_factory=list)


# ──────────────────────────────────────────────
# Date Helpers
# ──────────────────────────────────────────────

def _third_friday(year: int, month: int) -> date:
    """주어진 년/월의 셋째 금요일."""
    c = calendar.Calendar(firstweekday=calendar.MONDAY)
    fridays = [
        d for d in c.itermonthdays2(year, month)
        if d[0] != 0 and d[1] == calendar.FRIDAY
    ]
    return date(year, month, fridays[2][0])


def _previous_business_day(d: date, n: int = 1) -> date:
    """N 영업일 이전 (주말 건너뜀)."""
    cur = d
    for _ in range(n):
        cur -= timedelta(days=1)
        while cur.weekday() >= 5:  # Sat=5, Sun=6
            cur -= timedelta(days=1)
    return cur


def _next_business_day(d: date, n: int = 1) -> date:
    """N 영업일 이후."""
    cur = d
    for _ in range(n):
        cur += timedelta(days=1)
        while cur.weekday() >= 5:
            cur += timedelta(days=1)
    return cur


def _equity_index_roll_thursday(year: int, month: int) -> date:
    """Equity Index volume roll day = 3rd Friday 전전주 목요일 (3rd Fri - 8일)."""
    third_fri = _third_friday(year, month)
    return third_fri - timedelta(days=8)


def _energy_last_trading_day(delivery_year: int, delivery_month: int) -> date:
    """
    Energy (CL) last trading day = delivery 전월 25일의 3 영업일 전.
    Delivery month "FEB 2026" → last trade = 2026-01-25 (or prior weekday)의 3 영업일 전.
    """
    prev_month_year = delivery_year if delivery_month > 1 else delivery_year - 1
    prev_month = delivery_month - 1 if delivery_month > 1 else 12
    anchor = date(prev_month_year, prev_month, 25)
    # 25일이 주말이면 직전 영업일
    while anchor.weekday() >= 5:
        anchor -= timedelta(days=1)
    return _previous_business_day(anchor, 3)


def _metal_last_trading_day(year: int, month: int) -> date:
    """
    Metal (GC) last trading day = 만기월 마지막 영업일의 3 영업일 전.
    """
    last_day = calendar.monthrange(year, month)[1]
    anchor = date(year, month, last_day)
    while anchor.weekday() >= 5:
        anchor -= timedelta(days=1)
    return _previous_business_day(anchor, 3)


# ──────────────────────────────────────────────
# Roll Blackout Helpers (자산군별 — Backtester에서도 재사용)
# ──────────────────────────────────────────────


def compute_roll_dates(
    ticker: str, start_year: int, end_year: int,
) -> List[date]:
    """ticker의 자산군에 맞춰 [start_year, end_year] 사이 모든 roll date를 반환.

    Equity Index: 분기(3,6,9,12) 만기의 volume migration Thursday (3rd Fri -8일)
    Energy(CL): 매월 contract last trading day
    Metal(GC): 매월(active month)의 last trading day
    """
    asset_class = detect_asset_class(ticker)
    dates: List[date] = []
    for year in range(start_year, end_year + 1):
        if asset_class == "equity_index":
            for m in EQUITY_QUARTERLY_MONTHS:
                dates.append(_equity_index_roll_thursday(year, m))
        elif asset_class == "energy":
            for m in range(1, 13):
                dates.append(_energy_last_trading_day(year, m))
        elif asset_class == "metal":
            for m in METAL_ACTIVE_MONTHS:
                dates.append(_metal_last_trading_day(year, m))
    return dates


def is_in_blackout(
    target: date, roll_dates: List[date], blackout_business_days: int = 2,
) -> bool:
    """target 날짜가 roll date ± blackout_business_days 이내인지."""
    for rd in roll_dates:
        # 양방향 N영업일
        if abs((target - rd).days) <= blackout_business_days * 2:  # 캘린더 일 기준 보수적 매핑
            # 정밀하게: 영업일 카운트
            days = 0
            cur = min(target, rd)
            stop = max(target, rd)
            while cur < stop:
                cur += timedelta(days=1)
                if cur.weekday() < 5:
                    days += 1
            if days <= blackout_business_days:
                return True
    return False


# ──────────────────────────────────────────────
# Window Generation
# ──────────────────────────────────────────────

# CME month codes
MONTH_CODES = "FGHJKMNQUVXZ"  # F=Jan, G=Feb, ..., Z=Dec
EQUITY_QUARTERLY_MONTHS = [3, 6, 9, 12]
METAL_ACTIVE_MONTHS = [2, 4, 6, 8, 10, 12]  # GC active: Feb/Apr/Jun/Aug/Oct/Dec


def _contract_code(ticker: str, year: int, month: int) -> str:
    """ESH26, CLG26 등 contract code 생성."""
    base = ticker.split("=")[0]
    yy = year % 100
    return f"{base}{MONTH_CODES[month - 1]}{yy:02d}"


def generate_equity_windows(ticker: str, end_date: date, n: int = 4) -> List[Window]:
    """
    Equity Index 분기 윈도우 — 직전 N 분기.

    각 윈도우: (이전 분기 만기 3rd Friday + 1영업일) → (다음 분기 roll Thursday − 1영업일)
    """
    windows = []
    # 현재 시점 이전의 가장 가까운 분기 만기 찾기
    current_quarter_year = end_date.year
    current_quarter_month = ((end_date.month - 1) // 3) * 3 + 3  # 3, 6, 9, 12

    # 시작점: 현재 분기의 만기 (이미 지났는지 여부 무관, 이전 분기들을 거꾸로 탐색)
    quarter_anchor_year = current_quarter_year
    quarter_anchor_month = current_quarter_month
    anchors = []
    for _ in range(n + 1):
        anchors.append((quarter_anchor_year, quarter_anchor_month))
        # 이전 분기로
        if quarter_anchor_month == 3:
            quarter_anchor_year -= 1
            quarter_anchor_month = 12
        else:
            quarter_anchor_month -= 3
    anchors.reverse()  # 가장 오래된 것부터

    for i in range(n):
        prev_year, prev_month = anchors[i]
        next_year, next_month = anchors[i + 1]

        prev_fri = _third_friday(prev_year, prev_month)
        next_roll = _equity_index_roll_thursday(next_year, next_month)

        start = _next_business_day(prev_fri, 1)
        end = _previous_business_day(next_roll, 1)

        # end_date를 넘기지 않도록 클램프
        if end > end_date:
            end = end_date

        if start >= end:
            continue

        windows.append(Window(
            index=i,
            label=f"{next_year}Q{(next_month // 3)}",
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
            contract_code=_contract_code(ticker, next_year, next_month),
        ))

    return windows


def generate_monthly_windows(
    ticker: str, end_date: date, n: int = 12, asset_class: str = "energy",
) -> List[Window]:
    """
    Monthly contract 윈도우 — 직전 N 개월.

    Energy(CL) - 매월 contract
    Metal(GC) - 격월 active이지만 1m × 12로 매월 윈도우 생성 (사용자 결정)

    각 윈도우: (이전 만기 + 1영업일) → (다음 만기 − 3영업일)
    """
    windows = []
    # 현재 시점에서 거꾸로 N개월
    months = []
    cur_year, cur_month = end_date.year, end_date.month
    for _ in range(n + 1):
        months.append((cur_year, cur_month))
        if cur_month == 1:
            cur_year -= 1
            cur_month = 12
        else:
            cur_month -= 1
    months.reverse()  # 오래된 → 최근

    for i in range(n):
        prev_year, prev_month = months[i]
        next_year, next_month = months[i + 1]

        if asset_class == "energy":
            prev_expiry = _energy_last_trading_day(prev_year, prev_month)
            next_expiry = _energy_last_trading_day(next_year, next_month)
        else:  # metal
            prev_expiry = _metal_last_trading_day(prev_year, prev_month)
            next_expiry = _metal_last_trading_day(next_year, next_month)

        start = _next_business_day(prev_expiry, 1)
        end = _previous_business_day(next_expiry, 1)

        if end > end_date:
            end = end_date
        if start >= end:
            continue

        windows.append(Window(
            index=i,
            label=f"{next_year}-{next_month:02d}",
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
            contract_code=_contract_code(ticker, next_year, next_month),
        ))

    return windows


def generate_windows(ticker: str, end_date: Optional[date] = None) -> List[Window]:
    """ticker → 자산군에 맞는 기본 윈도우 세트 생성."""
    if end_date is None:
        end_date = date.today()
    asset_class = detect_asset_class(ticker)

    if asset_class == "equity_index":
        return generate_equity_windows(ticker, end_date, n=4)
    elif asset_class == "energy":
        return generate_monthly_windows(ticker, end_date, n=12, asset_class="energy")
    elif asset_class == "metal":
        return generate_monthly_windows(ticker, end_date, n=12, asset_class="metal")
    return generate_equity_windows(ticker, end_date, n=4)


# ──────────────────────────────────────────────
# Walk-Forward Engine
# ──────────────────────────────────────────────

class WalkForwardEngine:
    """자산별 contract life cycle에 맞춘 walk-forward 백테스터."""

    def __init__(
        self,
        config: ATSConfig,
        ticker: str,
        end_date: Optional[date] = None,
        is_micro: bool = False,
        initial_equity: float = 100_000.0,
        progress_callback: Optional[Callable[[float], None]] = None,
    ):
        self.config = config
        self.ticker = ticker
        self.end_date = end_date or date.today()
        self.is_micro = is_micro
        self.initial_equity = initial_equity
        self.progress_callback = progress_callback
        self.asset_class = detect_asset_class(ticker)

    def run(self) -> WalkForwardResult:
        windows = generate_windows(self.ticker, self.end_date)
        if not windows:
            logger.warning("No windows generated for %s", self.ticker)
            return WalkForwardResult(
                ticker=self.ticker,
                asset_class=self.asset_class,
                window_size_months=3 if self.asset_class == "equity_index" else 1,
                n_windows=0,
                completed_at=datetime.now().isoformat(),
                errors=["No windows generated"],
            )

        logger.info(
            "Walk-Forward | %s | asset=%s | %d windows",
            self.ticker, self.asset_class, len(windows),
        )

        window_metrics: List[WindowMetrics] = []
        errors: List[str] = []

        from backtest.futures_backtester import FuturesBacktester

        total = len(windows)
        for i, w in enumerate(windows):
            if self.progress_callback:
                self.progress_callback(i / total)

            try:
                # 각 윈도우마다 fresh config copy
                cfg_copy = copy.deepcopy(self.config)
                bt = FuturesBacktester(
                    config=cfg_copy,
                    ticker=self.ticker,
                    start_date=w.start_date,
                    end_date=w.end_date,
                    initial_equity=self.initial_equity,
                    is_micro=self.is_micro,
                    progress_callback=None,
                )
                bt_result = bt.run()
                m = bt_result.get("metrics", {})

                window_metrics.append(WindowMetrics(
                    window=w,
                    total_return_pct=float(m.get("total_return_pct", 0.0)),
                    total_pnl=float(m.get("total_pnl", 0.0)),
                    sharpe_ratio=float(m.get("sharpe_ratio", 0.0)),
                    max_drawdown_pct=float(m.get("max_drawdown_pct", 0.0)),
                    win_rate=float(m.get("win_rate", 0.0)),
                    profit_factor=float(m.get("profit_factor", 0.0)),
                    total_trades=int(m.get("total_trades", 0)),
                    long_trades=int(m.get("long_trades", 0)),
                    short_trades=int(m.get("short_trades", 0)),
                    avg_holding_days=float(m.get("avg_holding_days", 0.0)),
                ))
                logger.info(
                    "Window %d/%d | %s | %s~%s | return=%.2f%% | trades=%d",
                    i + 1, total, w.label, w.start_date, w.end_date,
                    window_metrics[-1].total_return_pct,
                    window_metrics[-1].total_trades,
                )
            except Exception as e:
                msg = f"Window {w.label} ({w.start_date}~{w.end_date}): {e}"
                logger.error(msg, exc_info=True)
                errors.append(msg)
                window_metrics.append(WindowMetrics(window=w, error=str(e)))

        if self.progress_callback:
            self.progress_callback(1.0)

        distributions = self._compute_distributions(window_metrics)

        window_size_months = 3 if self.asset_class == "equity_index" else 1

        return WalkForwardResult(
            ticker=self.ticker,
            asset_class=self.asset_class,
            window_size_months=window_size_months,
            n_windows=len(windows),
            windows=window_metrics,
            distributions=distributions,
            completed_at=datetime.now().isoformat(),
            errors=errors,
        )

    @staticmethod
    def _compute_distributions(windows: List[WindowMetrics]) -> List[DistributionStats]:
        """완료된 윈도우들의 분포 통계 계산."""
        completed = [w for w in windows if w.error is None]
        if not completed:
            return []

        def _percentile(values: List[float], p: float) -> float:
            if not values:
                return 0.0
            s = sorted(values)
            k = (len(s) - 1) * p
            f, c = int(k), min(int(k) + 1, len(s) - 1)
            return s[f] if f == c else s[f] * (c - k) + s[c] * (k - f)

        def _stats(metric_name: str, values: List[float]) -> DistributionStats:
            return DistributionStats(
                metric=metric_name,
                count=len(values),
                median=statistics.median(values) if values else 0.0,
                mean=statistics.mean(values) if values else 0.0,
                p25=_percentile(values, 0.25),
                p75=_percentile(values, 0.75),
                worst=min(values) if values else 0.0,
                best=max(values) if values else 0.0,
            )

        return [
            _stats("total_return_pct", [w.total_return_pct for w in completed]),
            _stats("sharpe_ratio", [w.sharpe_ratio for w in completed]),
            _stats("max_drawdown_pct", [w.max_drawdown_pct for w in completed]),
            _stats("profit_factor", [w.profit_factor for w in completed]),
            _stats("win_rate", [w.win_rate for w in completed]),
            _stats("total_trades", [float(w.total_trades) for w in completed]),
        ]


def to_dict(result: WalkForwardResult) -> dict:
    """WalkForwardResult를 JSON 직렬화 가능한 dict로 변환."""
    return {
        "ticker": result.ticker,
        "asset_class": result.asset_class,
        "window_size_months": result.window_size_months,
        "n_windows": result.n_windows,
        "completed_at": result.completed_at,
        "errors": result.errors,
        "windows": [
            {
                "index": wm.window.index,
                "label": wm.window.label,
                "start_date": wm.window.start_date,
                "end_date": wm.window.end_date,
                "contract_code": wm.window.contract_code,
                "duration_days": wm.window.duration_days(),
                "total_return_pct": round(wm.total_return_pct, 2),
                "total_pnl": round(wm.total_pnl, 2),
                "sharpe_ratio": round(wm.sharpe_ratio, 3),
                "max_drawdown_pct": round(wm.max_drawdown_pct, 2),
                "win_rate": round(wm.win_rate, 1),
                "profit_factor": round(wm.profit_factor, 2),
                "total_trades": wm.total_trades,
                "long_trades": wm.long_trades,
                "short_trades": wm.short_trades,
                "avg_holding_days": round(wm.avg_holding_days, 1),
                "error": wm.error,
            }
            for wm in result.windows
        ],
        "distributions": [
            {
                "metric": d.metric,
                "count": d.count,
                "median": round(d.median, 3),
                "mean": round(d.mean, 3),
                "p25": round(d.p25, 3),
                "p75": round(d.p75, 3),
                "worst": round(d.worst, 3),
                "best": round(d.best, 3),
            }
            for d in result.distributions
        ],
    }
