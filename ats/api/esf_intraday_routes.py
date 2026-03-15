"""
ES-F 인트라데이 데이트레이딩 API 엔드포인트.

AMT 3-Stage + 4-Layer 스코어링 분석, Volume Profile, 세션 상태,
인트라데이 백테스트 실행.
"""

from __future__ import annotations

import asyncio
import math
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

import pandas as pd
import yfinance as yf
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from data.config_manager import ConfigManager
from infra.logger import get_logger

logger = get_logger("esf_intraday_api")

esf_router = APIRouter(tags=["esf-intraday"])

# ── 지원 티커 (인트라데이 전용) ──
ESF_TICKERS = [
    {"ticker": "ES=F", "name": "E-mini S&P 500", "multiplier": 50},
    {"ticker": "MES=F", "name": "Micro E-mini S&P 500", "multiplier": 5},
    {"ticker": "NQ=F", "name": "E-mini NASDAQ 100", "multiplier": 20},
    {"ticker": "MNQ=F", "name": "Micro E-mini NASDAQ 100", "multiplier": 2},
]

VALID_ESF_TICKERS = {t["ticker"] for t in ESF_TICKERS}

# yfinance 인트라데이 유효 기간
VALID_INTRADAY_PERIODS = {"1d", "5d", "7d", "1mo", "60d"}
VALID_INTRADAY_INTERVALS = {"1m", "2m", "5m", "15m", "30m", "1h"}

# ── Lazy strategy init ──
_strategy = None  # Optional[ESFIntradayStrategy]
_config = None


def _get_strategy():
    """ESFIntradayStrategy 지연 초기화."""
    global _strategy, _config
    if _strategy is None:
        _config = ConfigManager().load()
        from strategy.esf_intraday import ESFIntradayStrategy
        _strategy = ESFIntradayStrategy(_config)
    return _strategy


def _get_config():
    global _config
    if _config is None:
        _config = ConfigManager().load()
    return _config


# ── 캐시 (인트라데이는 3분 TTL) ──
_analysis_cache: Dict[str, dict] = {}
_analysis_cache_ts: Dict[str, float] = {}
CACHE_TTL = 180  # 3분

_backtest_in_progress = False
_backtest_cache: Optional[dict] = None
_backtest_progress: float = 0.0


# ── Request Models ──
class IntradayBacktestRequest(BaseModel):
    ticker: str = "ES=F"
    period: str = "60d"
    initial_equity: float = 10000.0
    is_micro: bool = True


# ══════════════════════════════════════════
# Helper Functions
# ══════════════════════════════════════════


def _validate_esf_ticker(ticker: str) -> None:
    """인트라데이 티커 화이트리스트 검증."""
    if ticker not in VALID_ESF_TICKERS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported ticker: {ticker}. Valid: {sorted(VALID_ESF_TICKERS)}",
        )


def _validate_intraday_period(period: str) -> None:
    """yfinance 인트라데이 period 검증."""
    if period not in VALID_INTRADAY_PERIODS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid period: {period}. Valid for intraday: {sorted(VALID_INTRADAY_PERIODS)}",
        )


def _validate_intraday_interval(interval: str) -> None:
    """yfinance 인트라데이 interval 검증."""
    if interval not in VALID_INTRADAY_INTERVALS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid interval: {interval}. Valid: {sorted(VALID_INTRADAY_INTERVALS)}",
        )


def _safe_float(v, default=0.0) -> float:
    """NaN/inf를 안전하게 처리."""
    if v is None:
        return default
    f = float(v)
    if math.isnan(f) or math.isinf(f):
        return default
    return f


def _sanitize_for_json(obj):
    """NaN/Inf를 JSON 직렬화 가능하게 변환."""
    if isinstance(obj, float):
        if math.isnan(obj):
            return None
        if math.isinf(obj):
            return 0.0
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_for_json(v) for v in obj]
    return obj


def _download_intraday_data(
    ticker: str, period: str = "60d", interval: str = "15m"
) -> pd.DataFrame:
    """yfinance로 인트라데이 OHLCV 다운로드."""
    try:
        raw = yf.download(
            ticker, period=period, interval=interval,
            auto_adjust=True, progress=False,
        )
    except Exception as e:
        logger.warning("yfinance download failed for %s: %s", ticker, e)
        return pd.DataFrame()

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


def _get_current_session() -> dict:
    """ET 기준 현재 RTH 세션 상태 판별."""
    try:
        import pytz
        et = pytz.timezone("US/Eastern")
        now_et = datetime.now(et)
    except ImportError:
        # pytz 없으면 UTC-5 근사치
        ET = timezone(timedelta(hours=-5))
        now_et = datetime.now(timezone.utc).astimezone(ET)

    hour = now_et.hour
    minute = now_et.minute
    weekday = now_et.weekday()  # 0=Mon ... 6=Sun
    time_str = now_et.strftime("%Y-%m-%d %H:%M:%S %Z")

    # 주말
    if weekday == 5 or (weekday == 6 and hour < 18):
        return {
            "is_rth": False,
            "status": "CLOSED",
            "session": "Weekend",
            "current_time_et": time_str,
        }

    # 금요일 17:00 이후
    if weekday == 4 and hour >= 17:
        return {
            "is_rth": False,
            "status": "CLOSED",
            "session": "Weekend",
            "current_time_et": time_str,
        }

    # 일일 점검: 17:00-18:00 ET
    if hour == 17:
        return {
            "is_rth": False,
            "status": "HALT",
            "session": "Daily Maintenance",
            "current_time_et": time_str,
        }

    # RTH: 09:30-16:00 ET
    rth_start = hour > 9 or (hour == 9 and minute >= 30)
    rth_end = hour < 16
    if rth_start and rth_end:
        return {
            "is_rth": True,
            "status": "RTH",
            "session": "Regular Trading Hours",
            "current_time_et": time_str,
        }

    # Globex (프리마켓/포스트마켓)
    return {
        "is_rth": False,
        "status": "GLOBEX",
        "session": "Globex Extended Hours",
        "current_time_et": time_str,
    }


# ══════════════════════════════════════════
# Endpoints
# ══════════════════════════════════════════


@esf_router.get("/esf/tickers")
async def list_esf_tickers():
    """인트라데이 지원 티커 목록."""
    return {"tickers": ESF_TICKERS}


@esf_router.get("/esf/analyze/{ticker}")
async def analyze_esf_intraday(
    ticker: str = "ES=F",
    interval: str = Query("15m", description="인트라데이 interval (1m,5m,15m,30m,1h)"),
    period: str = Query("60d", description="데이터 기간 (1d,5d,7d,1mo,60d)"),
):
    """
    ES-F 인트라데이 4-Layer 스코어 분석.

    AMT Location(30) + Z-Score(20) + Momentum(25) + Volume/Aggression(25) = 100점.
    Grade A(≥55), B(≥45), C(≥35).
    """
    _validate_esf_ticker(ticker)
    _validate_intraday_period(period)
    _validate_intraday_interval(interval)

    cache_key = f"{ticker}:{interval}:{period}"
    now = time.time()

    # 캐시 확인
    if cache_key in _analysis_cache and (now - _analysis_cache_ts.get(cache_key, 0)) < CACHE_TTL:
        return JSONResponse(
            content=_analysis_cache[cache_key],
            headers={"Cache-Control": "no-cache"},
        )

    try:
        df = _download_intraday_data(ticker, period, interval)
        if df.empty:
            raise HTTPException(status_code=404, detail=f"No intraday data for {ticker}")

        strategy = _get_strategy()
        df = strategy.calculate_indicators(df)
        if df.empty or len(df) < 2:
            raise HTTPException(status_code=404, detail=f"Insufficient data for {ticker}")

        curr = df.iloc[-1]
        current_price = float(curr["close"])

        # AMT 상태 판별
        amt_state = strategy.determine_amt_state(df)

        # 4-Layer 스코어링
        direction = strategy.determine_direction(df)
        is_long = direction == "LONG"

        l1_score, l1_signals = strategy.score_amt_location(df, is_long)
        l2_score, l2_signals = strategy.score_zscore(df, is_long)
        l3_score, l3_signals = strategy.score_momentum(df, is_long)
        l4_score, l4_signals = strategy.score_volume_aggression(df, is_long)

        total_score = l1_score + l2_score + l3_score + l4_score

        # Grade 판정
        cfg = _get_config().esf_intraday
        if total_score >= cfg.grade_a_threshold:
            grade = "A"
        elif total_score >= cfg.grade_b_threshold:
            grade = "B"
        elif total_score >= cfg.grade_c_threshold:
            grade = "C"
        else:
            grade = "D"

        # VP 데이터 (간략)
        vp_data = strategy.get_volume_profile_summary(df)

        # SL/TP
        atr = _safe_float(curr.get("atr", 0))
        sl = current_price - atr * cfg.sl_atr_mult if is_long else current_price + atr * cfg.sl_atr_mult
        tp = current_price + atr * cfg.tp_atr_mult if is_long else current_price - atr * cfg.tp_atr_mult
        rr_ratio = abs(tp - current_price) / abs(current_price - sl) if abs(current_price - sl) > 0 else 0

        result = {
            "ticker": ticker,
            "interval": interval,
            "direction": direction,
            "total_score": round(total_score, 1),
            "grade": grade,
            "signal_active": grade in ("A", "B") and direction != "NEUTRAL",
            "amt_state": amt_state,
            "layers": {
                "amt_location": {
                    "score": round(l1_score, 1),
                    "max_score": cfg.weight_amt_location,
                    "signals": l1_signals,
                },
                "zscore": {
                    "score": round(l2_score, 1),
                    "max_score": cfg.weight_zscore,
                    "signals": l2_signals,
                },
                "momentum": {
                    "score": round(l3_score, 1),
                    "max_score": cfg.weight_momentum,
                    "signals": l3_signals,
                },
                "volume_aggression": {
                    "score": round(l4_score, 1),
                    "max_score": cfg.weight_volume_aggression,
                    "signals": l4_signals,
                },
            },
            "volume_profile": vp_data,
            "indicators": {
                "price": round(current_price, 2),
                "atr": round(atr, 2),
                "rsi": round(_safe_float(curr.get("rsi", 50)), 1),
                "adx": round(_safe_float(curr.get("adx", 0)), 1),
                "macd_hist": round(_safe_float(curr.get("macd_hist", 0)), 3),
                "zscore": round(_safe_float(curr.get("zscore", 0)), 3),
                "bb_squeeze_ratio": round(_safe_float(curr.get("bb_squeeze_ratio", 1)), 3),
            },
            "entry_price": round(current_price, 2),
            "stop_loss": round(sl, 2),
            "take_profit": round(tp, 2),
            "risk_reward_ratio": round(rr_ratio, 2),
            "last_updated": curr.name.strftime("%Y-%m-%d %H:%M") if hasattr(curr.name, "strftime") else str(curr.name),
        }

        # 지표가 전부 기본값이면 캐시 저장 안 함
        ind = result["indicators"]
        has_real_data = ind["adx"] != 0 or ind["atr"] != 0 or ind["rsi"] != 50.0
        if has_real_data:
            _analysis_cache[cache_key] = result
            _analysis_cache_ts[cache_key] = now

        return JSONResponse(
            content=_sanitize_for_json(result),
            headers={"Cache-Control": "no-cache"},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("ESF intraday analysis error: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@esf_router.get("/esf/signal/{ticker}")
async def get_esf_signal(
    ticker: str = "ES=F",
    equity: float = Query(10000, description="계좌 자산 ($)"),
    is_micro: bool = Query(True, description="MES 사용 여부"),
):
    """인트라데이 매매 시그널 생성 (entry/SL/TP/contracts)."""
    _validate_esf_ticker(ticker)
    if equity <= 0:
        raise HTTPException(status_code=400, detail="equity must be positive")

    try:
        cfg = _get_config().esf_intraday
        interval = cfg.primary_interval
        df = _download_intraday_data(ticker, period="60d", interval=interval)
        if df.empty:
            raise HTTPException(status_code=404, detail=f"No data for {ticker}")

        strategy = _get_strategy()
        current_price = float(df.iloc[-1]["close"])

        df = strategy.calculate_indicators(df)
        signal = strategy.generate_intraday_signal(
            df=df,
            equity=equity,
        )

        if signal is None:
            return {"signal": None, "message": "No actionable signal"}

        return _sanitize_for_json({"signal": signal})

    except HTTPException:
        raise
    except Exception as e:
        logger.error("ESF signal generation error: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@esf_router.get("/esf/session-status")
async def esf_session_status():
    """현재 RTH 세션 상태."""
    return _get_current_session()


@esf_router.get("/esf/candles/{ticker}")
async def get_esf_candles(
    ticker: str = "ES=F",
    interval: str = Query("15m", description="인트라데이 interval (1m,5m,15m,30m,1h)"),
    period: str = Query("5d", description="데이터 기간 (1d,5d,7d,1mo,60d)"),
):
    """
    ES-F 인트라데이 OHLCV + 기술 지표 캔들 데이터.

    차트 렌더링용. calculate_indicators()로 RSI, MACD, ADX, BB, Z-Score 등 포함.
    """
    _validate_esf_ticker(ticker)
    _validate_intraday_period(period)
    _validate_intraday_interval(interval)

    cache_key = f"candles:{ticker}:{interval}:{period}"
    now = time.time()

    if cache_key in _analysis_cache and (now - _analysis_cache_ts.get(cache_key, 0)) < CACHE_TTL:
        return JSONResponse(
            content=_analysis_cache[cache_key],
            headers={"Cache-Control": "no-cache"},
        )

    try:
        df = _download_intraday_data(ticker, period, interval)
        if df.empty:
            raise HTTPException(status_code=404, detail=f"No intraday data for {ticker}")

        strategy = _get_strategy()
        df = strategy.calculate_indicators(df)
        if df.empty or len(df) < 2:
            raise HTTPException(status_code=404, detail=f"Insufficient data for {ticker}")

        candles = []
        for idx, row in df.iterrows():
            candle = {
                "datetime": idx.isoformat() if hasattr(idx, "isoformat") else str(idx),
                "open": round(_safe_float(row.get("open")), 2),
                "high": round(_safe_float(row.get("high")), 2),
                "low": round(_safe_float(row.get("low")), 2),
                "close": round(_safe_float(row.get("close")), 2),
                "volume": int(_safe_float(row.get("volume"))),
                # 지표 — 프론트 AnalyticsData 호환 필드명
                "rsi_14": round(_safe_float(row.get("rsi")), 1) if not pd.isna(row.get("rsi", float("nan"))) else None,
                "adx": round(_safe_float(row.get("adx")), 1) if not pd.isna(row.get("adx", float("nan"))) else None,
                "plus_di": round(_safe_float(row.get("plus_di")), 1) if not pd.isna(row.get("plus_di", float("nan"))) else None,
                "minus_di": round(_safe_float(row.get("minus_di")), 1) if not pd.isna(row.get("minus_di", float("nan"))) else None,
                "macd": round(_safe_float(row.get("macd_line")), 3) if not pd.isna(row.get("macd_line", float("nan"))) else None,
                "macd_signal": round(_safe_float(row.get("macd_signal")), 3) if not pd.isna(row.get("macd_signal", float("nan"))) else None,
                "macd_diff": round(_safe_float(row.get("macd_hist")), 3) if not pd.isna(row.get("macd_hist", float("nan"))) else None,
                "zscore": round(_safe_float(row.get("zscore")), 3) if not pd.isna(row.get("zscore", float("nan"))) else None,
                "atr_14": round(_safe_float(row.get("atr")), 2) if not pd.isna(row.get("atr", float("nan"))) else None,
                "bb_hband": round(_safe_float(row.get("bb_upper")), 2) if not pd.isna(row.get("bb_upper", float("nan"))) else None,
                "bb_lband": round(_safe_float(row.get("bb_lower")), 2) if not pd.isna(row.get("bb_lower", float("nan"))) else None,
                "bb_mavg": round(_safe_float(row.get("bb_middle")), 2) if not pd.isna(row.get("bb_middle", float("nan"))) else None,
                "ema_fast": round(_safe_float(row.get("ema_fast")), 2) if not pd.isna(row.get("ema_fast", float("nan"))) else None,
                "ema_mid": round(_safe_float(row.get("ema_mid")), 2) if not pd.isna(row.get("ema_mid", float("nan"))) else None,
                "ema_slow": round(_safe_float(row.get("ema_slow")), 2) if not pd.isna(row.get("ema_slow", float("nan"))) else None,
            }
            candles.append(candle)

        result = {
            "ticker": ticker,
            "interval": interval,
            "period": period,
            "count": len(candles),
            "candles": candles,
        }

        _analysis_cache[cache_key] = result
        _analysis_cache_ts[cache_key] = now

        return JSONResponse(
            content=_sanitize_for_json(result),
            headers={"Cache-Control": "no-cache"},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("ESF candles error: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@esf_router.get("/esf/volume-profile/{ticker}")
async def get_volume_profile(
    ticker: str = "ES=F",
    period: str = Query("5d", description="VP 데이터 기간"),
    interval: str = Query("15m", description="인트라데이 interval"),
):
    """Volume Profile 데이터 (POC, VAH, VAL, 노드 리스트, LVN)."""
    _validate_esf_ticker(ticker)
    _validate_intraday_period(period)
    _validate_intraday_interval(interval)

    try:
        df = _download_intraday_data(ticker, period, interval)
        if df.empty:
            raise HTTPException(status_code=404, detail=f"No data for {ticker}")

        strategy = _get_strategy()
        strategy.calculate_indicators(df)
        vp = strategy.build_volume_profile(df)

        if vp is None or (vp.poc == 0 and vp.vah == 0):
            raise HTTPException(status_code=404, detail="Insufficient data for VP calculation")

        vp_result = {
            "poc": vp.poc,
            "vah": vp.vah,
            "val": vp.val,
            "lvn_levels": vp.lvn_levels,
            "nodes": [{"price": n[0], "volume": n[1]} for n in vp.nodes],
            "node_count": len(vp.nodes),
        }
        return _sanitize_for_json(vp_result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Volume Profile error: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@esf_router.post("/esf/backtest")
async def run_esf_backtest(req: IntradayBacktestRequest):
    """인트라데이 백테스트 실행 (백그라운드)."""
    global _backtest_in_progress, _backtest_cache, _backtest_progress

    _validate_esf_ticker(req.ticker)
    _validate_intraday_period(req.period)

    if req.initial_equity <= 0:
        raise HTTPException(status_code=400, detail="initial_equity must be positive")
    if _backtest_in_progress:
        raise HTTPException(status_code=409, detail="Backtest already in progress")

    _backtest_in_progress = True
    _backtest_progress = 0.0

    def _run_sync():
        global _backtest_cache, _backtest_in_progress, _backtest_progress
        try:
            import copy
            config = copy.deepcopy(_get_config())

            def _on_progress(pct: float):
                global _backtest_progress
                _backtest_progress = pct

            from backtest.intraday_backtester import IntradayBacktester
            bt = IntradayBacktester(
                config=config,
                ticker=req.ticker,
                period=req.period,
                initial_equity=req.initial_equity,
                is_micro=req.is_micro,
                progress_callback=_on_progress,
            )
            result = bt.run()
            _backtest_cache = result
            _backtest_progress = 100.0
            return result
        except Exception as e:
            logger.error("ESF backtest error: %s", str(e), exc_info=True)
            _backtest_cache = {"error": str(e)}
            raise
        finally:
            _backtest_in_progress = False

    try:
        result = await asyncio.to_thread(_run_sync)
        return _sanitize_for_json({"status": "completed", "result": result})

    except HTTPException:
        raise
    except Exception as e:
        _backtest_in_progress = False
        raise HTTPException(status_code=500, detail=str(e))


@esf_router.get("/esf/backtest/status")
async def esf_backtest_status():
    """인트라데이 백테스트 진행 상태."""
    status = "idle"
    if _backtest_in_progress:
        status = "running"
    elif _backtest_cache is not None:
        status = "completed"

    return {
        "status": status,
        "progress": round(_backtest_progress, 1),
    }


@esf_router.get("/esf/backtest/result")
async def esf_backtest_result():
    """캐시된 인트라데이 백테스트 결과 조회."""
    if _backtest_cache is None:
        raise HTTPException(status_code=404, detail="No backtest result available")

    return _sanitize_for_json(_backtest_cache)
