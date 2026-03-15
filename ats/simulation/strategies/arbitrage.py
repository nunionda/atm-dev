"""
Statistical Pairs Arbitrage strategy — scan_entries / check_exits.

Extracted from SimulationEngine to keep engine.py smaller.
All logic is identical; `self` is replaced with `engine`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List

import numpy as np
import pandas as pd

from simulation.models import SimSignal

if TYPE_CHECKING:
    from simulation.engine import SimulationEngine


def discover_pairs(engine: "SimulationEngine") -> List[Dict]:
    """
    워치리스트 내 페어 자동 발견 — v2.
    동일 섹터 우선 + 크로스섹터 허용 (BUG-7).
    Phase Stats 누적 (BUG-1), 쿨다운 중 페어 스킵 (BUG-3).
    """
    import itertools

    cfg = engine._arb_cfg
    watchlist = engine._watchlist
    pairs: List[Dict] = []

    # v2: 쿨다운 중 페어 키 집합 (BUG-3)
    cooldown_keys = set(engine._arb_pair_cooldown.keys())

    # ── 후보 조합 생성 ──
    combos: List[tuple] = []

    # 1) 동일 섹터 내 조합 (우선)
    sector_map: Dict[str, List[Dict]] = {}
    for w in watchlist:
        sector = w.get("sector", "")
        if sector:
            sector_map.setdefault(sector, []).append(w)

    for sector, stocks in sector_map.items():
        if len(stocks) < 2:
            continue
        for w_a, w_b in itertools.combinations(stocks, 2):
            combos.append((w_a, w_b, sector))

    # 2) 크로스섹터 조합 (v2 BUG-7)
    if cfg.cross_sector_pairs:
        all_stocks = [w for w in watchlist if w.get("sector", "")]
        for w_a, w_b in itertools.combinations(all_stocks, 2):
            if w_a.get("sector", "") != w_b.get("sector", ""):
                combos.append((w_a, w_b, "cross"))

    # v2: 누적 통계 (BUG-1) — 리셋하지 않고 += 누적
    engine._phase_stats["arb_pairs_scanned"] = (
        engine._phase_stats.get("arb_pairs_scanned", 0) + len(combos)
    )

    for w_a, w_b, sector_label in combos:
        code_a, code_b = w_a["code"], w_b["code"]

        # v2: 쿨다운 중 페어 스킵 (BUG-3)
        pair_key = f"{min(code_a,code_b)}-{max(code_a,code_b)}"
        if pair_key in cooldown_keys:
            continue

        df_a = engine._ohlcv_cache.get(code_a)
        df_b = engine._ohlcv_cache.get(code_b)

        if df_a is None or df_b is None or len(df_a) < cfg.correlation_lookback or len(df_b) < cfg.correlation_lookback:
            continue

        # 날짜 정렬 후 최근 N일 종가 추출
        close_a = df_a["close"].astype(float).tail(cfg.correlation_lookback)
        close_b = df_b["close"].astype(float).tail(cfg.correlation_lookback)

        if len(close_a) != len(close_b):
            min_len = min(len(close_a), len(close_b))
            close_a = close_a.tail(min_len).reset_index(drop=True)
            close_b = close_b.tail(min_len).reset_index(drop=True)

        if len(close_a) < 30:
            continue

        # 상관계수 체크 (v2: 0.60 threshold)
        corr = close_a.corr(close_b)
        if pd.isna(corr) or corr < cfg.correlation_min:
            engine._phase_stats["arb_correlation_rejects"] = (
                engine._phase_stats.get("arb_correlation_rejects", 0) + 1
            )
            continue

        # 스프레드 계산: log(price_A / price_B)
        spread = np.log(close_a.values / close_b.values)
        spread = spread[~np.isnan(spread)]
        if len(spread) < cfg.zscore_lookback:
            continue

        # 반감기(half-life) 계산: OLS Δspread ~ spread_lag
        spread_lag = spread[:-1]
        spread_diff = np.diff(spread)
        if len(spread_lag) < 10 or np.std(spread_lag) < 1e-10:
            continue

        try:
            beta = np.cov(spread_diff, spread_lag)[0, 1] / np.var(spread_lag)
            if beta >= 0:  # 비수렴
                continue
            halflife = -np.log(2) / beta
            if halflife > cfg.halflife_max or halflife < 1:
                continue
        except (ValueError, ZeroDivisionError):
            continue

        # 스프레드 통계
        spread_mean = float(np.mean(spread))
        spread_std = float(np.std(spread))
        if spread_std < 1e-10:
            continue

        current_zscore = (spread[-1] - spread_mean) / spread_std

        # 중복 페어 방지 (동일 섹터에서 이미 발견된 경우)
        existing_keys = {f"{min(p['code_a'],p['code_b'])}-{max(p['code_a'],p['code_b'])}" for p in pairs}
        if pair_key in existing_keys:
            continue

        pairs.append({
            "code_a": code_a,
            "code_b": code_b,
            "name_a": w_a["name"],
            "name_b": w_b["name"],
            "sector": sector_label,
            "correlation": round(float(corr), 4),
            "halflife": round(float(halflife), 1),
            "spread_mean": spread_mean,
            "spread_std": spread_std,
            "current_zscore": round(float(current_zscore), 3),
            "spread_series": spread,
            "close_a": close_a,
            "close_b": close_b,
        })

    # v2: 누적 (BUG-1)
    engine._phase_stats["arb_spreads_detected"] = (
        engine._phase_stats.get("arb_spreads_detected", 0) + len(pairs)
    )
    return pairs


def load_fixed_pairs(engine: "SimulationEngine") -> List[Dict]:
    """
    v5: 설정 기반 고정 ETF 페어 로드.
    _discover_pairs() 대체. correlation_min 필터링 없음 (사전 검증된 페어).
    """
    cfg = engine._arb_cfg
    pairs: List[Dict] = []
    cooldown_keys = set(engine._arb_pair_cooldown.keys())

    for pair_def in engine._arb_fixed_pair_defs:
        code_a = pair_def.get("code_a", "")
        code_b = pair_def.get("code_b", "")
        if not code_a or not code_b:
            continue

        # 쿨다운 체크
        pair_key = f"{min(code_a,code_b)}-{max(code_a,code_b)}"
        if pair_key in cooldown_keys:
            continue

        df_a = engine._ohlcv_cache.get(code_a)
        df_b = engine._ohlcv_cache.get(code_b)

        if df_a is None or df_b is None:
            continue
        if len(df_a) < cfg.zscore_lookback or len(df_b) < cfg.zscore_lookback:
            continue

        close_a = df_a["close"].astype(float).tail(cfg.correlation_lookback)
        close_b = df_b["close"].astype(float).tail(cfg.correlation_lookback)

        min_len = min(len(close_a), len(close_b))
        if min_len < cfg.zscore_lookback:
            continue
        close_a = close_a.tail(min_len).reset_index(drop=True)
        close_b = close_b.tail(min_len).reset_index(drop=True)

        # 상관계수 (참고용, 필터링 없음)
        corr = close_a.corr(close_b)
        if pd.isna(corr):
            corr = 0.0

        # 스프레드: log(price_A / price_B)
        spread = np.log(close_a.values / close_b.values)
        spread = spread[~np.isnan(spread)]
        if len(spread) < cfg.zscore_lookback:
            continue

        # 반감기
        spread_lag = spread[:-1]
        spread_diff = np.diff(spread)
        halflife = 10.0  # default
        if len(spread_lag) >= 10 and np.std(spread_lag) > 1e-10:
            try:
                beta = np.cov(spread_diff, spread_lag)[0, 1] / np.var(spread_lag)
                if beta < 0:
                    halflife = min(-np.log(2) / beta, cfg.halflife_max)
            except (ValueError, ZeroDivisionError):
                pass

        # 스프레드 통계
        spread_mean = float(np.mean(spread))
        spread_std = float(np.std(spread))
        if spread_std < 1e-10:
            continue

        current_zscore = (spread[-1] - spread_mean) / spread_std

        pairs.append({
            "code_a": code_a,
            "code_b": code_b,
            "name_a": pair_def.get("name_a", code_a),
            "name_b": pair_def.get("name_b", code_b),
            "sector": pair_def.get("sector", "ETF"),
            "correlation": round(float(corr), 4),
            "halflife": round(float(halflife), 1),
            "spread_mean": spread_mean,
            "spread_std": spread_std,
            "current_zscore": round(float(current_zscore), 3),
            "spread_series": spread,
            "close_a": close_a,
            "close_b": close_b,
        })

    engine._phase_stats["arb_fixed_pairs_loaded"] = (
        engine._phase_stats.get("arb_fixed_pairs_loaded", 0) + len(pairs)
    )
    engine._phase_stats["arb_spreads_detected"] = (
        engine._phase_stats.get("arb_spreads_detected", 0) + len(pairs)
    )
    return pairs


def check_basis_gate(engine: "SimulationEngine") -> bool:
    """
    v5: 콘탱고/백워데이션 Basis Gate.
    True = 차익거래 윈도우 OPEN, False = CLOSED.

    US: Basis = (ES=F − SPY) / SPY × 100 → Z-Score
    KOSPI: ^KS200 실현변동성 Z-Score 프록시
    """
    cfg = engine._arb_cfg
    if not cfg.basis_gate_enabled:
        engine._arb_basis_window_open = True
        return True

    if not engine._arb_basis_signals:
        # Basis signal 설정이 없으면 게이트 비활성 (항상 열림)
        engine._arb_basis_window_open = True
        return True

    for sig in engine._arb_basis_signals:
        spot_code = sig.get("spot_code", "")
        futures_code = sig.get("futures_code", "")
        ma_period = sig.get("basis_ma_period", 20)
        z_threshold = sig.get("basis_zscore_threshold", 1.5)
        use_premium = sig.get("use_premium_estimate", False)

        if use_premium or not futures_code:
            # KOSPI: 변동성 프록시
            spot_ticker = sig.get("spot_ticker", "")
            # ^KS200 데이터는 spot_code 또는 spot_ticker로 조회
            df_spot = engine._ohlcv_cache.get(spot_code)
            if df_spot is None:
                df_spot = engine._ohlcv_cache.get(spot_ticker)
            if df_spot is None or len(df_spot) < ma_period * 3:
                # 데이터 부족 시 게이트 열기 (거래 허용)
                engine._arb_basis_window_open = True
                return True

            close = df_spot["close"].astype(float)
            returns = close.pct_change().dropna()
            if len(returns) < ma_period:
                engine._arb_basis_window_open = True
                return True

            # 실현 변동성 (연환산)
            realized_vol = returns.rolling(ma_period).std() * np.sqrt(252)
            realized_vol = realized_vol.dropna()
            if len(realized_vol) < ma_period * 3:
                engine._arb_basis_window_open = True
                return True

            vol_ma = realized_vol.rolling(ma_period * 3).mean()
            vol_std = realized_vol.rolling(ma_period * 3).std()
            vol_ma_last = vol_ma.iloc[-1]
            vol_std_last = vol_std.iloc[-1]

            if pd.isna(vol_ma_last) or pd.isna(vol_std_last) or vol_std_last < 1e-10:
                engine._arb_basis_window_open = True
                return True

            vol_zscore = (realized_vol.iloc[-1] - vol_ma_last) / vol_std_last
            is_open = abs(float(vol_zscore)) > z_threshold

            engine._arb_basis_data = {
                "type": "volatility_proxy",
                "realized_vol": round(float(realized_vol.iloc[-1]), 4),
                "vol_zscore": round(float(vol_zscore), 3),
                "threshold": z_threshold,
                "window_open": is_open,
            }
        else:
            # US: Basis = (Futures - Spot) / Spot × 100
            df_spot = engine._ohlcv_cache.get(spot_code)
            df_futures = engine._ohlcv_cache.get(futures_code)
            if df_spot is None or df_futures is None:
                engine._arb_basis_window_open = True
                return True
            if len(df_spot) < ma_period * 2 or len(df_futures) < ma_period * 2:
                engine._arb_basis_window_open = True
                return True

            spot_close = df_spot["close"].astype(float)
            fut_close = df_futures["close"].astype(float)

            # 날짜 정렬 보장: 길이 맞추기
            min_len = min(len(spot_close), len(fut_close))
            spot_close = spot_close.tail(min_len).reset_index(drop=True)
            fut_close = fut_close.tail(min_len).reset_index(drop=True)

            # Basis 계산: (Futures - Spot) / Spot × 100
            # ES=F는 SPY의 약 10배이므로 스케일 조정
            basis = (fut_close - spot_close * 10) / (spot_close * 10) * 100

            if len(basis) < ma_period:
                engine._arb_basis_window_open = True
                return True

            basis_ma = basis.rolling(ma_period).mean()
            basis_std = basis.rolling(ma_period).std()

            basis_ma_last = basis_ma.iloc[-1]
            basis_std_last = basis_std.iloc[-1]

            if pd.isna(basis_ma_last) or pd.isna(basis_std_last) or basis_std_last < 1e-10:
                engine._arb_basis_window_open = True
                return True

            basis_zscore = (basis.iloc[-1] - basis_ma_last) / basis_std_last
            is_open = abs(float(basis_zscore)) > z_threshold

            engine._arb_basis_data = {
                "type": "futures_basis",
                "basis_pct": round(float(basis.iloc[-1]), 4),
                "basis_zscore": round(float(basis_zscore), 3),
                "threshold": z_threshold,
                "window_open": is_open,
            }

        engine._arb_basis_window_open = is_open
        if is_open:
            engine._phase_stats["arb_basis_window_opens"] = (
                engine._phase_stats.get("arb_basis_window_opens", 0) + 1
            )
        return is_open

    engine._arb_basis_window_open = True
    return True


def score_arb_correlation(engine: "SimulationEngine", pair: Dict) -> int:
    """
    Layer 1: 상관관계 품질 (0 ~ weight_correlation).
    graduated scoring + 안정성 + 추세.
    """
    cfg = engine._arb_cfg
    score = 0
    corr = pair["correlation"]

    # Graduated 상관계수 점수
    if corr > 0.85:
        score += 20
    elif corr > 0.75:
        score += 15
    elif corr > 0.70:
        score += 10

    # 상관관계 안정성: rolling 20일 std
    close_a = pair["close_a"]
    close_b = pair["close_b"]
    if len(close_a) >= 30:
        rolling_corr = close_a.rolling(20).corr(close_b).dropna()
        if len(rolling_corr) > 5:
            corr_std = float(rolling_corr.std())
            if corr_std < 0.1:
                score += 10
            elif corr_std < 0.15:
                score += 5

            # 최근 5일 corr 상승 추세
            recent_corr = rolling_corr.tail(5)
            if len(recent_corr) >= 5:
                if float(recent_corr.iloc[-1]) > float(recent_corr.iloc[0]):
                    score += 5

    return min(score, cfg.weight_correlation)


def score_arb_spread(engine: "SimulationEngine", pair: Dict) -> int:
    """
    Layer 2: 스프레드 이탈도 (0 ~ weight_spread).
    Z-Score graduated + half-life + IV/RV 비교 (BlackScholes 참조).
    """
    cfg = engine._arb_cfg
    score = 0
    zscore = abs(pair["current_zscore"])

    # Graduated Z-Score 점수
    if zscore > 2.5:
        score += 20
    elif zscore > 2.0:
        score += 15
    elif zscore > 1.5:
        score += 10

    # 반감기 보너스 (빠른 회귀 = 높은 점수)
    halflife = pair["halflife"]
    if halflife < 10:
        score += 10
    elif halflife < 20:
        score += 5

    # IV vs RV 비교 (Black-Scholes 영감): 스프레드 실현변동성 분석
    spread_series = pair["spread_series"]
    if len(spread_series) >= 60:
        # 실현변동성 (RV): 최근 20일 vs 장기 60일
        recent_rv = float(np.std(spread_series[-20:]))
        long_rv = float(np.std(spread_series[-60:]))
        if long_rv > 0 and recent_rv > long_rv:
            score += 5  # 변동성 확장 = 회귀 기회↑

    # 스프레드 극단 횟수 (반복 패턴 = 높은 신뢰)
    if len(spread_series) >= 60 and pair["spread_std"] > 0:
        historical_z = (spread_series[-60:] - pair["spread_mean"]) / pair["spread_std"]
        extreme_count = np.sum(np.abs(historical_z) > 1.5)
        if extreme_count >= 3:
            score += 5

    return min(score, cfg.weight_spread)


def score_arb_volume(engine: "SimulationEngine", pair: Dict) -> int:
    """
    Layer 3: 거래량 + EV 확인 (0 ~ weight_volume).
    EV Engine (futuresStrategy.md): EV = P(W) × Avg.W - P(L) × Avg.L > 0
    """
    cfg = engine._arb_cfg
    score = 0

    # 양쪽 종목 거래량 확인
    df_a = engine._ohlcv_cache.get(pair["code_a"])
    df_b = engine._ohlcv_cache.get(pair["code_b"])

    if df_a is not None and df_b is not None and len(df_a) >= 20 and len(df_b) >= 20:
        vol_a = float(df_a["volume"].iloc[-1])
        vol_b = float(df_b["volume"].iloc[-1])
        vol_ma_a = float(df_a["volume"].tail(20).mean())
        vol_ma_b = float(df_b["volume"].tail(20).mean())

        # 양쪽 vol > MA20
        if vol_ma_a > 0 and vol_ma_b > 0:
            if vol_a > vol_ma_a and vol_b > vol_ma_b:
                score += 10
            elif vol_a > vol_ma_a or vol_b > vol_ma_b:
                score += 5

        # 이탈 방향 종목 거래량 급증 (1.5x)
        zscore = pair["current_zscore"]
        if zscore > 0 and vol_ma_a > 0 and vol_a > vol_ma_a * 1.5:
            score += 5  # A가 고평가 → A에 거래량 급증 = 의미있는 이탈
        elif zscore < 0 and vol_ma_b > 0 and vol_b > vol_ma_b * 1.5:
            score += 5  # B가 고평가 → B에 거래량 급증

    # EV > 0 검증 (과거 유사 스프레드 회귀의 승률/손익비)
    ev_positive = calculate_arb_ev(engine, pair)
    if ev_positive:
        score += 10

    return min(score, cfg.weight_volume)


def calculate_arb_ev(engine: "SimulationEngine", pair: Dict) -> bool:
    """
    Expected Value 검증 (futuresStrategy.md).
    EV = P(W) × Avg.W - P(L) × Avg.L
    과거 스프레드 데이터에서 유사 Z-Score 진입의 가상 결과를 시뮬레이션.
    """
    spread_series = pair["spread_series"]
    if len(spread_series) < 60:
        return True  # 데이터 부족 시 통과 (보수적)

    mean = pair["spread_mean"]
    std = pair["spread_std"]
    if std < 1e-10:
        return True

    zscore_series = (spread_series - mean) / std
    entry_threshold = engine._arb_cfg.zscore_entry
    exit_threshold = engine._arb_cfg.zscore_exit

    wins = []
    losses = []

    i = 0
    while i < len(zscore_series) - 5:
        z = zscore_series[i]
        if abs(z) >= entry_threshold:
            # 진입 시뮬레이션: 이후 5~20일 내 |z| < exit_threshold 도달 여부
            direction = -1 if z > 0 else 1  # z>0이면 축소 베팅
            for j in range(1, min(21, len(zscore_series) - i)):
                future_z = zscore_series[i + j]
                pnl_z = direction * (z - future_z)  # Z-Score 변화량
                if abs(future_z) < exit_threshold:
                    wins.append(float(pnl_z))
                    break
            else:
                # 20일 내 미회귀 = 손실
                pnl_z = direction * (z - zscore_series[min(i + 20, len(zscore_series) - 1)])
                if pnl_z > 0:
                    wins.append(float(pnl_z))
                else:
                    losses.append(float(abs(pnl_z)))
            i += 10  # 겹치지 않게 점프
        else:
            i += 1

    if not wins and not losses:
        return True  # 데이터 부족

    total = len(wins) + len(losses)
    if total < 3:
        return True  # 충분하지 않으면 통과

    p_win = len(wins) / total
    avg_win = sum(wins) / len(wins) if wins else 0
    avg_loss = sum(losses) / len(losses) if losses else 0
    p_loss = 1 - p_win

    ev = p_win * avg_win - p_loss * avg_loss
    return ev > 0


def size_arb_pair(engine: "SimulationEngine", price_a: float, price_b: float, score: int) -> tuple:
    """
    v2: 페어 전용 dollar-neutral 사이징 (BUG-6).
    양쪽 동일 금액 기준. 스코어 기반 승수.
    Returns: (qty_a, qty_b)
    """
    equity = engine._get_total_equity()
    max_alloc = equity * engine._arb_cfg.max_weight_per_pair  # 10%
    half_alloc = max_alloc / 2  # 각 leg 5%

    # 스코어 기반 사이징 (0.7~1.2)
    score_mult = 0.7 + (score - 60) / 100.0 * 0.5  # 60점=0.7, 100점=0.9
    score_mult = max(0.7, min(score_mult, 1.2))

    alloc = half_alloc * score_mult

    # 현금 제약: 최소 현금 비율 유지
    min_cash = equity * engine.min_cash_ratio
    available = engine.cash - min_cash
    if available <= 0:
        return (0, 0)
    # Long 매수 + Short 마진(50%) 필요 금액
    total_needed = alloc + alloc * 0.5  # Long full + Short margin
    if total_needed > available:
        alloc = available / 1.5  # 역산

    qty_a = max(1, int(alloc / price_a)) if price_a > 0 else 0
    qty_b = max(1, int(alloc / price_b)) if price_b > 0 else 0
    return (qty_a, qty_b)


def scan_entries(engine: "SimulationEngine"):
    """
    Statistical Pairs Arbitrage 양방향 진입 스캔 — v5.
    Z-Score 기반 통계적 진입 (futuresStrategy.md 참조).
    Long + Short 동시 진입.
    v2: 쿨다운 차감, dollar-neutral 사이징, 진입 시 entry_z 저장.
    v3: 워밍업 버퍼, ARB MDD 서킷브레이커 (-10%), 최소 보유일.
    v4: MDD 복구, 진입 완화, 페어 재발견 3일, 쿨다운 5일.
    v5: Fixed ETF Pair Mode + Basis Gate (콘탱고/백워데이션).
    """
    cfg = engine._arb_cfg

    # ── v2: 쿨다운 차감 (BUG-3) ──
    expired_keys = []
    for key in list(engine._arb_pair_cooldown.keys()):
        engine._arb_pair_cooldown[key] -= 1
        if engine._arb_pair_cooldown[key] <= 0:
            expired_keys.append(key)
    for key in expired_keys:
        del engine._arb_pair_cooldown[key]

    # ── v3: 워밍업 버퍼 (첫 N거래일 진입 금지) ──
    engine._arb_day_count += 1
    if engine._arb_day_count <= cfg.warmup_buffer_days:
        return

    # ── v4: ARB MDD 서킷브레이커 + 복구 메커니즘 ──
    equity = engine._get_total_equity()
    if hasattr(engine, '_peak_equity') and engine._peak_equity > 0:
        mdd_pct = (equity - engine._peak_equity) / engine._peak_equity
        if mdd_pct <= -cfg.arb_mdd_limit:
            # MDD 한도 초과 → 신규 진입 차단
            if not engine._arb_mdd_halted:
                engine._arb_mdd_halted = True
                engine._arb_mdd_halt_days = 0
            engine._arb_mdd_halt_days += 1
            # v4: 시간 기반 자동 복구 (halt_max_days 초과 시 재개)
            halt_max = getattr(cfg, 'arb_mdd_halt_max_days', 20)
            if engine._arb_mdd_halt_days >= halt_max:
                # 현재 equity를 새 baseline으로 설정 (peak 리셋)
                engine._peak_equity = equity
                engine._arb_mdd_halted = False
                engine._arb_mdd_halt_days = 0
            else:
                return
        elif engine._arb_mdd_halted:
            engine._arb_mdd_halt_days += 1
            # v4: DD가 recovery 수준(-5%)으로 회복 OR 시간 초과
            recovery_threshold = getattr(cfg, 'arb_mdd_recovery', 0.05)
            halt_max = getattr(cfg, 'arb_mdd_halt_max_days', 20)
            if mdd_pct > -recovery_threshold or engine._arb_mdd_halt_days >= halt_max:
                if engine._arb_mdd_halt_days >= halt_max:
                    engine._peak_equity = equity
                engine._arb_mdd_halted = False
                engine._arb_mdd_halt_days = 0
            else:
                return  # 아직 recovery 미달 & 시간 미초과 → 계속 차단

    # ── v5: Basis Gate (콘탱고/백워데이션 체크) ──
    if not check_basis_gate(engine):
        engine._phase_stats["arb_basis_gate_blocks"] = (
            engine._phase_stats.get("arb_basis_gate_blocks", 0) + 1
        )
        return

    # ── Phase 0: 시장 체제 판단 ──
    engine._update_market_regime()

    # ── Phase 4: 리스크 게이트 ──
    gate_pass, gate_reason = engine._risk_gate_check()
    if not gate_pass:
        return

    # 현재 활성 페어 수 체크
    active_pair_ids = set()
    for pos in engine.positions.values():
        if pos.status == "ACTIVE" and pos.pair_id:
            active_pair_ids.add(pos.pair_id)
    if len(active_pair_ids) >= cfg.max_pairs:
        return

    # 이미 보유 중인 종목 코드
    held_codes = set(engine.positions.keys())

    # v5: 페어 발견 — use_fixed_pairs 분기
    rediscovery_days = getattr(cfg, 'pair_rediscovery_days', 3)
    current_date = engine._get_current_date_str()
    days_since_discovery = 999
    if engine._arb_last_discovery and current_date:
        try:
            from datetime import datetime as _dt
            d1 = _dt.strptime(engine._arb_last_discovery.replace("-", "")[:8], "%Y%m%d")
            d2 = _dt.strptime(current_date.replace("-", "")[:8], "%Y%m%d")
            days_since_discovery = (d2 - d1).days
        except ValueError:
            days_since_discovery = 999

    if not engine._arb_pairs or days_since_discovery >= rediscovery_days:
        if cfg.use_fixed_pairs and engine._arb_fixed_pair_defs:
            engine._arb_pairs = load_fixed_pairs(engine)
        else:
            engine._arb_pairs = discover_pairs(engine)
        engine._arb_last_discovery = current_date

    if not engine._arb_pairs:
        return

    # 스캔 누적 (BUG-1)
    engine._phase_stats["total_scans"] = engine._phase_stats.get("total_scans", 0) + 1

    # 각 페어 스코어링 및 진입
    for pair in engine._arb_pairs:
        if len(active_pair_ids) >= cfg.max_pairs:
            break

        code_a = pair["code_a"]
        code_b = pair["code_b"]

        # 이미 보유 중인 종목은 스킵
        if code_a in held_codes or code_b in held_codes:
            continue

        # v4: 실시간 Z-Score 재계산 (페어 발견 시점 값이 아닌 현재 가격 기준)
        df_a = engine._ohlcv_cache.get(code_a)
        df_b = engine._ohlcv_cache.get(code_b)
        if df_a is not None and df_b is not None and len(df_a) >= cfg.zscore_lookback and len(df_b) >= cfg.zscore_lookback:
            close_a = df_a["close"].astype(float).tail(cfg.correlation_lookback)
            close_b = df_b["close"].astype(float).tail(cfg.correlation_lookback)
            min_len = min(len(close_a), len(close_b))
            if min_len >= cfg.zscore_lookback:
                close_a = close_a.tail(min_len).reset_index(drop=True)
                close_b = close_b.tail(min_len).reset_index(drop=True)
                spread = np.log(close_a.values / close_b.values)
                spread_recent = spread[-cfg.zscore_lookback:]
                s_mean = float(np.mean(spread_recent))
                s_std = float(np.std(spread_recent))
                if s_std > 1e-10:
                    zscore = (spread[-1] - s_mean) / s_std
                else:
                    zscore = 0.0
            else:
                zscore = pair.get("current_zscore", 0)
        else:
            zscore = pair.get("current_zscore", 0)

        # Z-Score 임계값 미달 → 스킵
        if abs(zscore) < cfg.zscore_entry:
            continue

        # 3-Layer 스코어링
        score_l1 = score_arb_correlation(engine, pair)
        score_l2 = score_arb_spread(engine, pair)
        score_l3 = score_arb_volume(engine, pair)
        total_score = score_l1 + score_l2 + score_l3

        engine._phase_stats["arb_total_score"] = (
            engine._phase_stats.get("arb_total_score", 0) + total_score
        )

        # v5: 고정 페어 모드 → etf_entry_threshold 사용
        threshold = cfg.etf_entry_threshold if cfg.use_fixed_pairs else cfg.entry_threshold
        if total_score < threshold:
            continue

        # ── 양방향 진입 결정 ──
        pair_id = f"arb-{code_a}-{code_b}-{current_date}"

        if zscore > 0:
            # Z > 0: A 고평가 → Short A, B 저평가 → Long B
            long_code, long_name = code_b, pair["name_b"]
            short_code, short_name = code_a, pair["name_a"]
        else:
            # Z < 0: A 저평가 → Long A, B 고평가 → Short B
            long_code, long_name = code_a, pair["name_a"]
            short_code, short_name = code_b, pair["name_b"]

        # Long leg 가격
        long_price = engine._current_prices.get(long_code)
        short_price = engine._current_prices.get(short_code)
        if not long_price or not short_price:
            continue

        # v2: dollar-neutral 사이징 (BUG-6)
        qty_long, qty_short = size_arb_pair(engine, long_price, short_price, total_score)
        if qty_long <= 0 or qty_short <= 0:
            continue

        now = engine._get_current_iso()

        # Long leg 시그널 생성 + 매수
        engine._signal_counter += 1
        long_signal = SimSignal(
            id=f"sim-sig-{engine._signal_counter:04d}",
            stock_code=long_code,
            stock_name=long_name,
            type="BUY",
            price=long_price,
            reason=f"ARB L1:{score_l1} L2:{score_l2} L3:{score_l3} Z:{zscore:+.2f}",
            strength=total_score,
            detected_at=now,
        )
        engine.signals.append(long_signal)
        if len(engine.signals) > 100:
            engine.signals = engine.signals[-100:]

        # v2: 통일 사이징으로 매수 (BUG-6)
        engine._execute_buy_arb(long_signal, qty_long, pair_id)

        # Short leg 시그널 생성 + 공매도 진입
        engine._signal_counter += 1
        short_signal = SimSignal(
            id=f"sim-sig-{engine._signal_counter:04d}",
            stock_code=short_code,
            stock_name=short_name,
            type="SELL_SHORT",
            price=short_price,
            reason=f"ARB L1:{score_l1} L2:{score_l2} L3:{score_l3} Z:{zscore:+.2f}",
            strength=total_score,
            detected_at=now,
        )
        engine.signals.append(short_signal)
        if len(engine.signals) > 100:
            engine.signals = engine.signals[-100:]

        # v2: 통일 사이징으로 공매도 (BUG-6)
        engine._execute_sell_short(short_signal, pair_id, qty_short)

        # v2: 진입 시 entry_z 저장 (방향성 청산용, BUG-5)
        engine._arb_pair_states[pair_id] = {
            "entry_z": zscore,
            "code_a": code_a,
            "code_b": code_b,
            "entry_date": current_date,
            "initial_corr": pair["correlation"],
        }

        engine._phase_stats["arb_entries"] = engine._phase_stats.get("arb_entries", 0) + 1
        active_pair_ids.add(pair_id)
        held_codes.add(long_code)
        held_codes.add(short_code)

        engine._add_risk_event(
            "INFO",
            f"ARB 페어 진입: {long_name}(L) + {short_name}(S) | Z={zscore:+.2f} Score={total_score}",
        )


def check_exits(engine: "SimulationEngine"):
    """
    Arbitrage 양방향 청산 로직 — v4.
    우선순위 재정렬 (BUG-2), 방향성 Z-Score (BUG-5),
    상관관계 2일 연속 확인 (BUG-4), 청산 시 쿨다운 등록 (BUG-3).
    v3: Z-Score TP 최소 보유일 3일 (조기 청산 방지).

    Exit Priority:
    1. ES1: -5% 하드 손절 (Long/Short 각각 명시) — BUG-2
    2. ES_ARB_SL: Dynamic ATR SL
    3. ES_ARB_TP: 방향성 Z-Score 청산 (z 부호 전환, v3: 최소 3일 보유) — BUG-5
    4. ES_ARB_CORR: 상관관계 35% 하락 + 2일 연속 — BUG-4
    5. ES3: 트레일링 (5% 활성화)
    6. ES5: 최대 보유 20일
    """
    cfg = engine._arb_cfg
    to_close: List[str] = []
    pair_close_reasons: Dict[str, str] = {}  # pair_id → 청산 사유

    for code, pos in engine.positions.items():
        if pos.status != "ACTIVE":
            continue

        current_price = pos.current_price
        entry_price = pos.entry_price

        # PnL 계산 (side 별)
        if pos.side == "SHORT":
            pnl_pct = (entry_price - current_price) / entry_price
        else:
            pnl_pct = (current_price - entry_price) / entry_price

        exit_reason = None

        # ══ 순위 1: ES1 -5% 하드 손절 (BUG-2: 최우선, Long/Short 각각 명시) ══
        if pos.side == "SHORT":
            # Short: 가격이 진입가 대비 5% 상승하면 손절
            if current_price >= entry_price * 1.05:
                actual_loss = (entry_price - current_price) / entry_price
                exit_reason = f"ES1 Short 하드 손절 ({actual_loss*100:+.1f}%)"
                engine._phase_stats["es_arb_sl"] = engine._phase_stats.get("es_arb_sl", 0) + 1
        else:
            # Long: 가격이 진입가 대비 5% 하락하면 손절
            if current_price <= entry_price * 0.95:
                actual_loss = (current_price - entry_price) / entry_price
                exit_reason = f"ES1 Long 하드 손절 ({actual_loss*100:+.1f}%)"
                engine._phase_stats["es_arb_sl"] = engine._phase_stats.get("es_arb_sl", 0) + 1

        # ══ 순위 2: ES_ARB_SL Dynamic ATR Stop ══
        if not exit_reason:
            df = engine._ohlcv_cache.get(code)
            if df is not None and len(df) > 14:
                if "atr" not in df.columns:
                    df = engine._calculate_indicators(df.copy())
                    engine._ohlcv_cache[code] = df
                last_atr = df.iloc[-1].get("atr")
                last_adx = df.iloc[-1].get("adx")
                if pd.notna(last_atr) and float(last_atr) > 0:
                    atr_val = float(last_atr)
                    adx_val = float(last_adx) if pd.notna(last_adx) else 0
                    sl_mult = cfg.atr_sl_mult_strong if adx_val >= cfg.adx_dynamic_threshold else cfg.atr_sl_mult

                    if pos.side == "SHORT":
                        atr_stop = entry_price + atr_val * sl_mult
                        # ATR 스탑이 하드 손절보다 넓으면 하드 손절 우선 (이미 체크됨)
                        if current_price >= atr_stop and current_price < entry_price * 1.05:
                            exit_reason = f"ES_ARB_SL Short ATR×{sl_mult} ({pnl_pct*100:+.1f}%)"
                            engine._phase_stats["es_arb_sl"] = engine._phase_stats.get("es_arb_sl", 0) + 1
                    else:
                        atr_stop = entry_price - atr_val * sl_mult
                        if current_price <= atr_stop and current_price > entry_price * 0.95:
                            exit_reason = f"ES_ARB_SL Long ATR×{sl_mult} ({pnl_pct*100:+.1f}%)"
                            engine._phase_stats["es_arb_sl"] = engine._phase_stats.get("es_arb_sl", 0) + 1

        # ══ 순위 3: ES_ARB_TP 방향성 Z-Score 청산 (BUG-5, v3: 최소 보유일) ══
        if not exit_reason and pos.pair_id:
            # v3: 최소 보유일 미달 시 Z-Score TP 스킵
            days_held = getattr(pos, 'days_held', 0) or 0
            skip_zscore_tp = days_held < cfg.min_hold_days_for_tp

            for pair in engine._arb_pairs:
                pair_codes = {pair["code_a"], pair["code_b"]}
                if code in pair_codes:
                    # 실시간 Z-Score 재계산
                    df_a = engine._ohlcv_cache.get(pair["code_a"])
                    df_b = engine._ohlcv_cache.get(pair["code_b"])
                    if df_a is not None and df_b is not None:
                        close_a = df_a["close"].astype(float).tail(cfg.correlation_lookback)
                        close_b = df_b["close"].astype(float).tail(cfg.correlation_lookback)
                        min_len = min(len(close_a), len(close_b))
                        if min_len >= cfg.zscore_lookback:
                            close_a = close_a.tail(min_len).reset_index(drop=True)
                            close_b = close_b.tail(min_len).reset_index(drop=True)
                            spread = np.log(close_a.values / close_b.values)
                            spread_recent = spread[-cfg.zscore_lookback:]
                            if len(spread_recent) > 0:
                                s_mean = float(np.mean(spread_recent))
                                s_std = float(np.std(spread_recent))
                                if s_std > 1e-10:
                                    current_z = (spread[-1] - s_mean) / s_std

                                    # pair_state는 TP/CORR 양쪽에서 사용
                                    pair_state = engine._arb_pair_states.get(pos.pair_id, {})

                                    # v2: 방향성 Z-Score 청산 (BUG-5)
                                    # v3: 최소 보유일(min_hold_days_for_tp) 미달 시 스킵
                                    if not skip_zscore_tp:
                                        entry_z = pair_state.get("entry_z", 0)

                                        if entry_z > 0 and current_z <= cfg.zscore_exit:
                                            # 진입 Z>+2 → 스프레드 축소 기대 → z<0.2 이면 청산
                                            exit_reason = f"ES_ARB_TP Z 방향성 청산 (entry_z={entry_z:+.1f} → z={current_z:.2f})"
                                            engine._phase_stats["es_arb_tp"] = engine._phase_stats.get("es_arb_tp", 0) + 1
                                            if pos.pair_id:
                                                pair_close_reasons[pos.pair_id] = exit_reason
                                        elif entry_z < 0 and current_z >= -cfg.zscore_exit:
                                            # 진입 Z<-2 → 스프레드 확대 기대 → z>-0.2 이면 청산
                                            exit_reason = f"ES_ARB_TP Z 방향성 청산 (entry_z={entry_z:+.1f} → z={current_z:.2f})"
                                            engine._phase_stats["es_arb_tp"] = engine._phase_stats.get("es_arb_tp", 0) + 1
                                            if pos.pair_id:
                                                pair_close_reasons[pos.pair_id] = exit_reason

                                    # ══ 순위 4: ES_ARB_CORR 상관관계 35% 하락 + 2일 연속 (BUG-4) ══
                                    if not exit_reason:
                                        current_corr = close_a.corr(close_b)
                                        initial_corr = pair_state.get("initial_corr", pair["correlation"])
                                        if pd.notna(current_corr) and initial_corr > 0:
                                            corr_decay = (initial_corr - current_corr) / initial_corr
                                            if corr_decay >= cfg.correlation_decay_exit:
                                                # v2: 2일 연속 확인 (BUG-4)
                                                decay_key = pos.pair_id or code
                                                engine._arb_corr_decay_count[decay_key] = (
                                                    engine._arb_corr_decay_count.get(decay_key, 0) + 1
                                                )
                                                if engine._arb_corr_decay_count[decay_key] >= cfg.corr_decay_confirm_days:
                                                    exit_reason = f"ES_ARB_CORR 상관관계 붕괴 {cfg.corr_decay_confirm_days}일 연속 ({corr_decay*100:.0f}%↓)"
                                                    engine._phase_stats["es_arb_corr"] = engine._phase_stats.get("es_arb_corr", 0) + 1
                                                    if pos.pair_id:
                                                        pair_close_reasons[pos.pair_id] = exit_reason
                                            else:
                                                # 붕괴 조건 미달 → 카운트 리셋
                                                decay_key = pos.pair_id or code
                                                engine._arb_corr_decay_count[decay_key] = 0
                    break

        # ══ 순위 5: ES3 트레일링 ══
        if not exit_reason:
            if pos.side == "SHORT":
                if pnl_pct >= cfg.trailing_activation_pct:
                    pos.trailing_activated = True
                if pos.trailing_activated and pos.lowest_price > 0:
                    trail_pct = 0.04
                    trail_stop = pos.lowest_price * (1 + trail_pct)
                    if current_price >= trail_stop:
                        exit_reason = f"ES3 Short 트레일링 ({pnl_pct*100:+.1f}%)"
            else:
                if pnl_pct >= cfg.trailing_activation_pct:
                    pos.trailing_activated = True
                if pos.trailing_activated:
                    trail_pct = 0.04
                    trail_stop = pos.highest_price * (1 - trail_pct)
                    if current_price <= trail_stop:
                        exit_reason = f"ES3 Long 트레일링 ({pnl_pct*100:+.1f}%)"

        # ══ 순위 6: ES5 최대 보유 ══
        if not exit_reason and pos.days_held >= cfg.max_holding_days:
            exit_reason = f"ES5 최대 보유 {cfg.max_holding_days}일 ({pnl_pct*100:+.1f}%)"

        if exit_reason:
            exit_type = "STOP_LOSS" if pnl_pct < 0 else "TAKE_PROFIT"
            engine._execute_sell(pos, current_price, exit_reason, exit_type)
            to_close.append(code)
            if pos.pair_id:
                pair_close_reasons.setdefault(pos.pair_id, exit_reason)
                # v2: 청산 시 쿨다운 등록 (BUG-3)
                pair_state = engine._arb_pair_states.get(pos.pair_id, {})
                cd_a = pair_state.get("code_a", "")
                cd_b = pair_state.get("code_b", "")
                if cd_a and cd_b:
                    cooldown_key = f"{min(cd_a,cd_b)}-{max(cd_a,cd_b)}"
                    engine._arb_pair_cooldown[cooldown_key] = cfg.pair_cooldown_days
        else:
            # highest/lowest 갱신
            if pos.side == "SHORT":
                if pos.lowest_price <= 0 or current_price < pos.lowest_price:
                    pos.lowest_price = current_price
            else:
                if current_price > pos.highest_price:
                    pos.highest_price = current_price

    # 페어 동시 청산: 한쪽이 청산되면 반대쪽도 청산
    for pair_id, reason in pair_close_reasons.items():
        for code, pos in engine.positions.items():
            if code in to_close:
                continue
            if pos.pair_id == pair_id and pos.status == "ACTIVE":
                paired_reason = f"페어 동시 청산 ({reason})"
                pnl_pct = (pos.entry_price - pos.current_price) / pos.entry_price if pos.side == "SHORT" else (pos.current_price - pos.entry_price) / pos.entry_price
                exit_type = "STOP_LOSS" if pnl_pct < 0 else "TAKE_PROFIT"
                engine._execute_sell(pos, pos.current_price, paired_reason, exit_type)
                to_close.append(code)

    for code in to_close:
        if code in engine.positions:
            del engine.positions[code]
