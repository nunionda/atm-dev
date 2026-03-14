"""
선물 매매 전용 API 엔드포인트.

4-Layer 스코어링 분석, 시그널 생성, 선물 백테스트 실행.
"""

from __future__ import annotations

import asyncio
import math
from typing import Dict, Optional

import pandas as pd
import yfinance as yf
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from data.config_manager import ConfigManager
from strategy.sp500_futures import SP500FuturesStrategy
from backtest.futures_backtester import FuturesBacktester
from infra.logger import get_logger

logger = get_logger("futures_api")

futures_router = APIRouter(tags=["futures"])

# ── 지원 티커 ──
FUTURES_TICKERS = [
    # 주가지수
    {"ticker": "ES=F", "name": "E-mini S&P 500", "multiplier": 50, "micro": "MES=F"},
    {"ticker": "NQ=F", "name": "E-mini NASDAQ 100", "multiplier": 20, "micro": "MNQ=F"},
    {"ticker": "YM=F", "name": "E-mini Dow Jones", "multiplier": 5, "micro": "MYM=F"},
    {"ticker": "RTY=F", "name": "E-mini Russell 2000", "multiplier": 50, "micro": "M2K=F"},
    # 원유
    {"ticker": "CL=F", "name": "WTI Crude Oil", "multiplier": 1000, "micro": "MCL=F"},
    {"ticker": "BZ=F", "name": "Brent Crude Oil", "multiplier": 1000, "micro": None},
    {"ticker": "MCL=F", "name": "Micro WTI Crude Oil", "multiplier": 100, "micro": None},
    # 골드/실버
    {"ticker": "GC=F", "name": "Gold", "multiplier": 100, "micro": "MGC=F"},
    {"ticker": "MGC=F", "name": "Micro Gold", "multiplier": 10, "micro": None},
    {"ticker": "SI=F", "name": "Silver", "multiplier": 5000, "micro": "SIL=F"},
    # Micro 주가지수
    {"ticker": "MES=F", "name": "Micro E-mini S&P 500", "multiplier": 5, "micro": None},
    {"ticker": "MNQ=F", "name": "Micro E-mini NASDAQ 100", "multiplier": 2, "micro": None},
    # 한국 지수 선물
    {"ticker": "^KS200", "name": "KOSPI 200", "multiplier": 250000, "micro": None},
    {"ticker": "^KQ150", "name": "KOSDAQ 150", "multiplier": 10000, "micro": None},
]

# ── Lazy strategy init ──
_strategy: Optional[SP500FuturesStrategy] = None
_config = None


def _get_strategy() -> SP500FuturesStrategy:
    global _strategy, _config
    if _strategy is None:
        _config = ConfigManager().load()
        _strategy = SP500FuturesStrategy(_config)
    return _strategy


def _get_config():
    global _config
    if _config is None:
        _config = ConfigManager().load()
    return _config


# ── 캐시 ──
_analysis_cache: Dict[str, dict] = {}
_analysis_cache_ts: Dict[str, float] = {}
CACHE_TTL = 300  # 5분 (리프레시 최적화)

_backtest_in_progress = False
_backtest_cache: Optional[dict] = None
_backtest_progress: float = 0.0

VALID_PERIODS = {"1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "max", "5d", "1d"}
VALID_TICKER_SET = {t["ticker"] for t in FUTURES_TICKERS}
# Micro 티커도 허용
VALID_TICKER_SET.update(t["micro"] for t in FUTURES_TICKERS if t.get("micro"))


def _validate_ticker(ticker: str) -> None:
    """티커 화이트리스트 검증."""
    if ticker not in VALID_TICKER_SET:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported ticker: {ticker}. Use GET /futures/tickers for valid list.",
        )


def _validate_period(period: str) -> None:
    """yfinance period 검증."""
    if period not in VALID_PERIODS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid period: {period}. Valid: {sorted(VALID_PERIODS)}",
        )


def _safe_float(v, default=0.0) -> float:
    """NaN/inf를 안전하게 처리."""
    if v is None:
        return default
    f = float(v)
    if math.isnan(f) or math.isinf(f):
        return default
    return f


def _download_futures_data(ticker: str, period: str = "1y") -> pd.DataFrame:
    """yfinance로 선물 OHLCV 다운로드."""
    raw = yf.download(ticker, period=period, auto_adjust=True, progress=False)
    if raw.empty:
        return pd.DataFrame()

    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.droplevel(1)

    # 중복 컬럼 제거 (yfinance 버그 방지)
    raw = raw.loc[:, ~raw.columns.duplicated()]

    df = raw.rename(columns={
        "Open": "open", "High": "high", "Low": "low",
        "Close": "close", "Volume": "volume",
    })
    return df[["open", "high", "low", "close", "volume"]].dropna()


# ══════════════════════════════════════════
# Endpoints
# ══════════════════════════════════════════


@futures_router.get("/futures/tickers")
async def list_futures_tickers():
    """지원 선물 티커 목록."""
    return {"tickers": FUTURES_TICKERS}


@futures_router.get("/futures/analyze/{ticker}")
async def analyze_futures(
    ticker: str = "ES=F",
    period: str = Query("1y", description="yfinance period (6mo, 1y, 2y)"),
):
    """
    선물 4-Layer 스코어 상세 분석.

    Z-Score(25) + Trend(25) + Momentum(25) + Volume(25) = 100점.
    """
    _validate_ticker(ticker)
    _validate_period(period)

    import time
    cache_key = f"{ticker}:{period}"
    now = time.time()

    # 캐시 확인
    if cache_key in _analysis_cache and (now - _analysis_cache_ts.get(cache_key, 0)) < CACHE_TTL:
        return JSONResponse(
            content=_analysis_cache[cache_key],
            headers={"Cache-Control": "no-cache"},
        )

    try:
        df = _download_futures_data(ticker, period)
        if df.empty:
            raise HTTPException(status_code=404, detail=f"No data for {ticker}")

        strategy = _get_strategy()
        df = strategy.calculate_indicators(df)
        if df.empty or len(df) < 2:
            raise HTTPException(status_code=404, detail=f"Insufficient data for {ticker}")

        curr = df.iloc[-1]
        current_price = float(curr["close"])

        # 방향 및 레짐 결정
        direction_enum = strategy._determine_direction(df)
        direction = direction_enum.value
        is_long = direction == "LONG"
        regime = strategy._determine_market_regime(df)

        # 4-Layer 스코어링
        l1_score, l1_signals = strategy._score_zscore(df, is_long)
        l2_score, l2_signals = strategy._score_trend(df, is_long)
        l3_score, l3_signals = strategy._score_momentum(df, is_long)
        l4_score, l4_signals = strategy._score_volume(df, is_long)

        total_score = l1_score + l2_score + l3_score + l4_score

        # SL/TP
        atr = _safe_float(curr.get("atr", 0))
        adx = _safe_float(curr.get("adx", 0))
        sl, tp = strategy._calculate_sl_tp(current_price, atr, is_long, adx)

        rr_ratio = abs(tp - current_price) / abs(current_price - sl) if abs(current_price - sl) > 0 else 0
        contracts = strategy._calculate_position_size(100000, current_price, sl)

        # Regime-adjusted threshold
        if regime == "BULL":
            effective_threshold = strategy.fc.regime_bull_entry_threshold
        elif regime == "BEAR":
            effective_threshold = strategy.fc.regime_bear_entry_threshold
        else:
            effective_threshold = strategy.fc.entry_threshold

        result = {
            "ticker": ticker,
            "direction": direction,
            "regime": regime,
            "total_score": round(total_score, 1),
            "entry_threshold": effective_threshold,
            "signal_active": total_score >= effective_threshold and direction != "NEUTRAL",
            "layers": {
                "zscore": {
                    "score": round(l1_score, 1),
                    "max_score": strategy.fc.weight_zscore,
                    "signals": l1_signals,
                },
                "trend": {
                    "score": round(l2_score, 1),
                    "max_score": strategy.fc.weight_trend,
                    "signals": l2_signals,
                },
                "momentum": {
                    "score": round(l3_score, 1),
                    "max_score": strategy.fc.weight_momentum,
                    "signals": l3_signals,
                },
                "volume": {
                    "score": round(l4_score, 1),
                    "max_score": strategy.fc.weight_volume,
                    "signals": l4_signals,
                },
            },
            "indicators": {
                "zscore": round(_safe_float(curr.get("zscore", 0)), 3),
                "rsi": round(_safe_float(curr.get("rsi", 50)), 1),
                "adx": round(adx, 1),
                "macd_hist": round(_safe_float(curr.get("macd_hist", 0)), 3),
                "atr": round(atr, 2),
                "bb_squeeze_ratio": round(_safe_float(curr.get("bb_squeeze_ratio", 1)), 3),
                "volume_ratio": round(
                    float(curr["volume"]) / float(curr["volume_ma"])
                    if pd.notna(curr.get("volume_ma")) and float(curr.get("volume_ma", 0)) > 0
                    else 1.0, 2
                ),
            },
            "entry_price": round(current_price, 2),
            "stop_loss": round(sl, 2),
            "take_profit": round(tp, 2),
            "risk_reward_ratio": round(rr_ratio, 2),
            "position_size_contracts": contracts,
            "last_updated": curr.name.strftime("%Y-%m-%d") if hasattr(curr.name, "strftime") else str(curr.name),
        }

        # 지표가 전부 기본값이면 캐시 저장 안 함 (yfinance 초기 로딩 실패 방지)
        ind = result["indicators"]
        has_real_data = ind["adx"] != 0 or ind["atr"] != 0 or ind["rsi"] != 50.0
        if has_real_data:
            _analysis_cache[cache_key] = result
            _analysis_cache_ts[cache_key] = now
        return JSONResponse(
            content=result,
            headers={"Cache-Control": "no-cache"},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Futures analysis error: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@futures_router.get("/futures/signal/{ticker}")
async def get_futures_signal(
    ticker: str = "ES=F",
    equity: float = Query(100000, description="계좌 자산"),
    period: str = Query("1y", description="yfinance period"),
):
    """현재 매매 시그널 생성 (FuturesSignal)."""
    _validate_ticker(ticker)
    _validate_period(period)
    if equity <= 0:
        raise HTTPException(status_code=400, detail="equity must be positive")

    try:
        df = _download_futures_data(ticker, period)
        if df.empty:
            raise HTTPException(status_code=404, detail=f"No data for {ticker}")

        strategy = _get_strategy()
        current_price = float(df.iloc[-1]["close"])

        signal = strategy.generate_futures_signal(
            code=ticker,
            df=df,
            current_price=current_price,
            equity=equity,
        )

        if signal is None:
            return {"signal": None, "message": "No actionable signal"}

        return {
            "signal": {
                "ticker": signal.ticker,
                "direction": signal.direction,
                "signal_strength": signal.signal_strength,
                "entry_price": signal.entry_price,
                "stop_loss": signal.stop_loss,
                "take_profit": signal.take_profit,
                "atr": round(signal.atr, 2),
                "z_score": round(signal.z_score, 3),
                "risk_reward_ratio": signal.risk_reward_ratio,
                "position_size_contracts": signal.position_size_contracts,
                "primary_signals": signal.primary_signals,
                "confirmation_filters": signal.confirmation_filters,
                "metadata": signal.metadata,
                "timestamp": signal.timestamp,
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Signal generation error: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@futures_router.get("/futures/quote/{ticker}")
async def get_futures_quote(ticker: str = "ES=F"):
    """현재가 + Z-Score 간략 조회."""
    _validate_ticker(ticker)

    try:
        df = _download_futures_data(ticker, period="5d")
        if df.empty:
            raise HTTPException(status_code=404, detail=f"No data for {ticker}")

        # Z-Score 계산을 위해 더 긴 기간 필요 → 캐시된 분석 결과 사용
        curr = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else curr
        change_pct = (float(curr["close"]) - float(prev["close"])) / float(prev["close"]) * 100

        return {
            "ticker": ticker,
            "price": round(float(curr["close"]), 2),
            "open": round(float(curr["open"]), 2),
            "high": round(float(curr["high"]), 2),
            "low": round(float(curr["low"]), 2),
            "volume": int(curr.get("volume", 0)),
            "change_pct": round(change_pct, 2),
            "date": curr.name.strftime("%Y-%m-%d") if hasattr(curr.name, "strftime") else str(curr.name),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@futures_router.post("/futures/backtest")
async def run_futures_backtest(
    ticker: str = Query("ES=F"),
    start_date: str = Query(..., description="YYYYMMDD"),
    end_date: str = Query(..., description="YYYYMMDD"),
    equity: float = Query(100000),
    is_micro: bool = Query(False),
    # 전략 파라미터 오버라이드 (선택)
    entry_threshold: Optional[float] = Query(None, description="진입 임계값 (0-100)"),
    sl_hard_pct: Optional[float] = Query(None, description="하드 손절 % (예: 0.05)"),
    atr_breakout_mult: Optional[float] = Query(None, description="ATR 돌파 배수"),
    max_holding_days: Optional[int] = Query(None, description="최대 보유일"),
):
    """선물 백테스트 실행. 전략 파라미터 오버라이드 지원."""
    global _backtest_in_progress, _backtest_cache

    _validate_ticker(ticker)
    if equity <= 0:
        raise HTTPException(status_code=400, detail="equity must be positive")

    # 입력 검증
    if len(start_date) != 8 or len(end_date) != 8:
        raise HTTPException(status_code=400, detail="Date format: YYYYMMDD")
    if start_date >= end_date:
        raise HTTPException(status_code=400, detail="start_date must be before end_date")
    if _backtest_in_progress:
        raise HTTPException(status_code=409, detail="Backtest already in progress")

    # 파라미터 범위 검증
    if entry_threshold is not None and not (0 <= entry_threshold <= 100):
        raise HTTPException(status_code=400, detail="entry_threshold must be 0-100")
    if sl_hard_pct is not None and not (0.001 <= sl_hard_pct <= 0.20):
        raise HTTPException(status_code=400, detail="sl_hard_pct must be 0.001-0.20")
    if atr_breakout_mult is not None and not (0.1 <= atr_breakout_mult <= 5.0):
        raise HTTPException(status_code=400, detail="atr_breakout_mult must be 0.1-5.0")
    if max_holding_days is not None and not (1 <= max_holding_days <= 252):
        raise HTTPException(status_code=400, detail="max_holding_days must be 1-252")

    _backtest_in_progress = True
    global _backtest_progress
    _backtest_progress = 0.0

    def _run_sync():
        global _backtest_cache, _backtest_in_progress, _backtest_progress
        try:
            import copy
            config = copy.deepcopy(_get_config())

            # 파라미터 오버라이드
            if entry_threshold is not None:
                config.sp500_futures.entry_threshold = entry_threshold
            if sl_hard_pct is not None:
                config.sp500_futures.sl_hard_pct = sl_hard_pct
            if atr_breakout_mult is not None:
                config.sp500_futures.atr_breakout_mult = atr_breakout_mult
            if max_holding_days is not None:
                config.sp500_futures.max_holding_days = max_holding_days

            def _on_progress(pct: float):
                global _backtest_progress
                _backtest_progress = pct

            bt = FuturesBacktester(
                config=config,
                ticker=ticker,
                start_date=start_date,
                end_date=end_date,
                initial_equity=equity,
                is_micro=is_micro,
                progress_callback=_on_progress,
            )
            result = bt.run()
            _backtest_cache = result
            _backtest_progress = 100.0
            return result
        finally:
            _backtest_in_progress = False

    try:
        result = await asyncio.to_thread(_run_sync)

        # NaN 안전 직렬화
        def _sanitize(obj):
            if isinstance(obj, float):
                if math.isnan(obj) or math.isinf(obj):
                    return 0.0
            if isinstance(obj, dict):
                return {k: _sanitize(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_sanitize(v) for v in obj]
            return obj

        return _sanitize(result)

    except HTTPException:
        raise
    except Exception as e:
        _backtest_in_progress = False
        logger.error("Futures backtest error: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@futures_router.get("/futures/backtest/status")
async def futures_backtest_status():
    """백테스트 진행 상태."""
    return {
        "in_progress": _backtest_in_progress,
        "has_result": _backtest_cache is not None,
        "progress": round(_backtest_progress, 1),
    }


@futures_router.get("/futures/backtest/result")
async def futures_backtest_result():
    """캐시된 백테스트 결과 조회."""
    if _backtest_cache is None:
        raise HTTPException(status_code=404, detail="No backtest result available")
    return _backtest_cache
