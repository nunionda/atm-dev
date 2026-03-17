"""
ESF 전략 가설 생성기 — 오늘의 전략 추천.

ESFIntradayStrategy의 기존 분석 파이프라인을 래핑하여
일별 가설(hypothesis)을 생성하고 DB에 저장한다.
A/B 실험 시 variant별 파라미터 오버라이드를 적용.

참조:
  - strategy/esf_intraday.py (ESFIntradayStrategy)
  - strategy/trend_regime_detector.py (detect_regime)
  - infra/db/models.py (ESFHypothesis, ESFVariant)
"""

from __future__ import annotations

import copy
import json
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd
import pytz
import yfinance as yf

from data.config_manager import ATSConfig
from infra.logger import get_logger

logger = get_logger("esf_hypothesis_generator")

ET = pytz.timezone("America/New_York")


class ESFHypothesisGenerator:
    """ESFIntradayStrategy를 래핑하여 일별 가설을 생성한다."""

    def __init__(self, config: ATSConfig, repo):
        """
        Args:
            config: ATSConfig 인스턴스
            repo: ESFJournalRepo 인스턴스 (DB 접근)
        """
        self.config = config
        self.repo = repo

    def generate_daily_hypothesis(
        self,
        ticker: str = "ES=F",
        variant_id: Optional[int] = None,
        experiment_id: Optional[int] = None,
    ) -> dict:
        """
        오늘의 전략 가설을 생성한다.

        1. variant_id가 있으면 config를 deep-copy 후 param_overrides 적용
        2. ESFIntradayStrategy 인스턴스 생성
        3. 최신 데이터 다운로드 및 분석 실행
        4. 시그널에서 direction, entry_price, SL, TP, score, grade, regime 추출
        5. reasoning dict 구성
        6. DB에 가설 저장
        7. 가설 dict 반환

        Args:
            ticker: 대상 티커 (ES=F, MES=F 등)
            variant_id: 전략 변형 ID (None이면 baseline)
            experiment_id: A/B 실험 ID (None이면 단독 가설)

        Returns:
            hypothesis dict (hypothesis_id, direction, entry_price 등)
        """
        # ── 1. Config 오버라이드 ──
        if variant_id is not None:
            effective_config = self._apply_variant_overrides(self.config, variant_id)
        else:
            effective_config = self.config

        # ── 2. 전략 인스턴스 생성 ──
        from strategy.esf_intraday import ESFIntradayStrategy
        strategy = ESFIntradayStrategy(effective_config)

        # ── 3. 데이터 다운로드 ──
        df = self._download_data(ticker)
        if df.empty:
            logger.warning("No data for %s — cannot generate hypothesis", ticker)
            return {"error": "no_data", "ticker": ticker}

        # ── 4. 지표 계산 + 시그널 생성 ──
        df = strategy.calculate_indicators(df.copy())
        if df.empty:
            logger.warning("Indicator calculation failed for %s", ticker)
            return {"error": "indicator_failed", "ticker": ticker}

        signal = strategy.generate_intraday_signal(df)
        if signal is None:
            logger.info("No signal generated for %s (below threshold)", ticker)
            return {"error": "no_signal", "ticker": ticker}

        # ── 5. 레짐 감지 ──
        from strategy.trend_regime_detector import detect_regime
        regime_result = detect_regime(df)

        # ── 6. Reasoning 구성 ──
        meta = signal.metadata or {}
        reasoning = {
            "l1_amt_location": meta.get("l1_amt_location", 0),
            "l2_zscore": meta.get("l2_zscore", 0),
            "l3_momentum": meta.get("l3_momentum", 0),
            "l4_volume_aggression": meta.get("l4_volume_aggression", 0),
            "market_state": meta.get("market_state", ""),
            "market_state_score": meta.get("market_state_score", 0),
            "location_zone": meta.get("location_zone", ""),
            "aggression_detected": meta.get("aggression_detected", False),
            "regime_components": meta.get("regime_components", {}),
            "ma_alignment": meta.get("ma_alignment", ""),
            "ma_bonus": meta.get("ma_bonus", 0),
            "regime_bonus": meta.get("regime_bonus", 0),
            "fabio_model": meta.get("fabio_model", ""),
            "rsi": meta.get("rsi", 50),
            "adx": meta.get("adx", 0),
            "macd_hist": meta.get("macd_hist", 0),
            "z_score": signal.z_score,
            "vp_poc": meta.get("vp_poc", 0),
            "vp_vah": meta.get("vp_vah", 0),
            "vp_val": meta.get("vp_val", 0),
        }

        # ── 7. Confidence = total_score / 100 (0~1 범위) ──
        confidence = min(max(signal.signal_strength / 100.0, 0.0), 1.0)

        # ── 8. 현재 시각 (ET) ──
        now_et = datetime.now(ET)
        entry_hour_et = now_et.hour

        # ── 9. 파라미터 스냅샷 (variant 추적용) ──
        params_snapshot = {}
        if variant_id is not None:
            variant = self.repo.get_variant(variant_id)
            if variant:
                params_snapshot = variant["param_overrides_json"] or {}

        # ── 10. DB 저장 ──
        trade_date = now_et.strftime("%Y-%m-%d")

        hypothesis = self.repo.create_hypothesis(
            trade_date=trade_date,
            ticker=ticker,
            direction=signal.direction,
            entry_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            total_score=signal.signal_strength,
            grade=meta.get("grade", "C"),
            confidence=round(confidence, 4),
            regime=regime_result.regime,
            reasoning_json=reasoning,
            entry_hour_et=entry_hour_et,
            variant_id=variant_id,
            experiment_id=experiment_id,
            params_json=params_snapshot if params_snapshot else None,
        )
        hypothesis_id = hypothesis["hypothesis_id"]

        result = {
            "hypothesis_id": hypothesis_id,
            "trade_date": trade_date,
            "ticker": ticker,
            "direction": signal.direction,
            "entry_price": signal.entry_price,
            "stop_loss": signal.stop_loss,
            "take_profit": signal.take_profit,
            "total_score": signal.signal_strength,
            "grade": meta.get("grade", "C"),
            "confidence": round(confidence, 4),
            "regime": regime_result.regime,
            "reasoning": reasoning,
            "risk_reward_ratio": signal.risk_reward_ratio,
            "contracts": signal.position_size_contracts,
            "primary_signals": signal.primary_signals,
            "confirmation_filters": signal.confirmation_filters,
        }

        logger.info(
            "Hypothesis generated | id=%s | %s %s @ %.2f | grade=%s | score=%.0f | regime=%s",
            hypothesis_id, signal.direction, ticker, signal.entry_price,
            meta.get("grade", "C"), signal.signal_strength, regime_result.regime,
        )

        return result

    def generate_ab_hypotheses(
        self,
        ticker: str,
        experiment_id: int,
    ) -> list:
        """
        활성 실험의 두 variant에 대해 가설을 생성한다.

        Args:
            ticker: 대상 티커
            experiment_id: A/B 실험 ID

        Returns:
            [hypothesis_a, hypothesis_b] 리스트
        """
        experiment = self.repo.get_experiment(experiment_id)
        if not experiment:
            logger.error("Experiment %d not found", experiment_id)
            return []

        if experiment["status"] != "RUNNING":
            logger.warning("Experiment %d is not RUNNING (status=%s)",
                           experiment_id, experiment["status"])
            return []

        results = []
        for vid in [experiment["variant_a_id"], experiment["variant_b_id"]]:
            hypothesis = self.generate_daily_hypothesis(
                ticker=ticker,
                variant_id=vid,
                experiment_id=experiment_id,
            )
            results.append(hypothesis)

        logger.info(
            "A/B hypotheses generated | experiment=%d | variants=[%d, %d]",
            experiment_id, experiment["variant_a_id"], experiment["variant_b_id"],
        )

        return results

    def _apply_variant_overrides(self, config: ATSConfig, variant_id: int) -> ATSConfig:
        """
        Config를 deep-copy 후 variant의 param_overrides를 적용한다.

        Args:
            config: 원본 ATSConfig
            variant_id: 변형 ID

        Returns:
            오버라이드가 적용된 ATSConfig 복사본
        """
        copied = copy.deepcopy(config)

        variant = self.repo.get_variant(variant_id)
        if not variant:
            logger.warning("Variant %d not found — using baseline config", variant_id)
            return copied

        # _to_dict already parses param_overrides_json into a dict
        overrides = variant["param_overrides_json"] or {}
        if isinstance(overrides, str):
            try:
                overrides = json.loads(overrides)
            except json.JSONDecodeError:
                logger.error("Invalid JSON in variant %d param_overrides", variant_id)
                return copied

        # ESFIntradayConfig 필드에 오버라이드 적용
        applied = []
        for key, value in overrides.items():
            if hasattr(copied.esf_intraday, key):
                old_val = getattr(copied.esf_intraday, key)
                setattr(copied.esf_intraday, key, value)
                applied.append(f"{key}: {old_val} -> {value}")
            else:
                logger.warning("Unknown override key: %s (skipped)", key)

        if applied:
            logger.info(
                "Variant %d (%s) overrides applied: %s",
                variant_id, variant["name"], ", ".join(applied),
            )

        return copied

    def _download_data(self, ticker: str) -> pd.DataFrame:
        """
        yfinance에서 15m 인트라데이 데이터를 다운로드한다.

        intraday_backtester.py의 _download_data()와 동일한 패턴.
        """
        logger.info("Downloading %s, period=60d, interval=15m", ticker)
        try:
            raw = yf.download(
                ticker,
                period="60d",
                interval="15m",
                auto_adjust=False,
                progress=False,
            )
        except Exception as e:
            logger.error("yfinance download failed: %s", e)
            return pd.DataFrame()

        if raw.empty:
            logger.error("No data for %s", ticker)
            return pd.DataFrame()

        # MultiIndex 컬럼 처리
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.droplevel(1)

        # 중복 컬럼 제거
        raw = raw.loc[:, ~raw.columns.duplicated()]

        df = raw.rename(columns={
            "Open": "open", "High": "high", "Low": "low",
            "Close": "close", "Volume": "volume",
        })

        # Adj Close 제거 (auto_adjust=False)
        cols = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
        df = df[cols].dropna()

        if df.empty:
            return df

        # UTC -> ET 변환
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        df.index = df.index.tz_convert(ET)

        return df
