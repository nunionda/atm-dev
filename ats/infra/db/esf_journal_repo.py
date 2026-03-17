"""
ESF Strategy Evolution System — Repository
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import List, Optional

from sqlalchemy import and_
from sqlalchemy.orm import Session

from infra.db.connection import Database
from infra.db.models import (
    ESFCumulativeStat,
    ESFExperiment,
    ESFHypothesis,
    ESFResult,
    ESFVariant,
)
from infra.logger import get_logger

logger = get_logger("esf_journal_repo")


def _to_dict(obj) -> dict:
    """ORM 객체 → dict 변환."""
    if obj is None:
        return None
    d = {c.name: getattr(obj, c.name) for c in obj.__table__.columns}
    # JSON 필드 파싱
    for key in ("param_overrides_json", "reasoning_json", "params_json", "conclusion_reason"):
        if key in d and d[key]:
            try:
                d[key] = json.loads(d[key])
            except (json.JSONDecodeError, TypeError):
                pass
    return d


class ESFJournalRepo:
    """ESF 전략 저널 DB CRUD."""

    def __init__(self, database: Database):
        self.db = database

    def _session(self) -> Session:
        return self.db.get_session()

    # ── Variants ──────────────────────────

    def create_variant(self, name: str, description: str = "",
                       param_overrides: dict = None, is_baseline: bool = False) -> dict:
        now = datetime.now().isoformat()
        with self._session() as s:
            v = ESFVariant(
                name=name,
                description=description,
                is_baseline=1 if is_baseline else 0,
                is_active=1,
                param_overrides_json=json.dumps(param_overrides or {}),
                created_at=now,
                updated_at=now,
            )
            s.add(v)
            s.commit()
            s.refresh(v)
            return _to_dict(v)

    def get_variant(self, variant_id: int) -> Optional[dict]:
        with self._session() as s:
            v = s.query(ESFVariant).get(variant_id)
            return _to_dict(v)

    def list_variants(self, active_only: bool = True) -> List[dict]:
        with self._session() as s:
            q = s.query(ESFVariant)
            if active_only:
                q = q.filter(ESFVariant.is_active == 1)
            return [_to_dict(v) for v in q.order_by(ESFVariant.variant_id).all()]

    def update_variant(self, variant_id: int, **kwargs) -> Optional[dict]:
        with self._session() as s:
            v = s.query(ESFVariant).get(variant_id)
            if not v:
                return None
            for key, val in kwargs.items():
                if key == "param_overrides":
                    setattr(v, "param_overrides_json", json.dumps(val))
                elif hasattr(v, key):
                    setattr(v, key, val)
            v.updated_at = datetime.now().isoformat()
            s.commit()
            s.refresh(v)
            return _to_dict(v)

    # ── Experiments ───────────────────────

    def create_experiment(self, name: str, variant_a_id: int, variant_b_id: int,
                          min_trades: int = 20, max_days: int = 30,
                          description: str = "") -> dict:
        now = datetime.now().isoformat()
        today = datetime.now().strftime("%Y-%m-%d")
        with self._session() as s:
            e = ESFExperiment(
                name=name,
                description=description,
                status="RUNNING",
                variant_a_id=variant_a_id,
                variant_b_id=variant_b_id,
                min_trades_per_variant=min_trades,
                max_days=max_days,
                start_date=today,
                created_at=now,
            )
            s.add(e)
            s.commit()
            s.refresh(e)
            return _to_dict(e)

    def get_experiment(self, experiment_id: int) -> Optional[dict]:
        with self._session() as s:
            e = s.query(ESFExperiment).get(experiment_id)
            return _to_dict(e)

    def get_active_experiment(self) -> Optional[dict]:
        with self._session() as s:
            e = s.query(ESFExperiment).filter(
                ESFExperiment.status == "RUNNING"
            ).order_by(ESFExperiment.experiment_id.desc()).first()
            return _to_dict(e)

    def update_experiment(self, experiment_id: int, **kwargs) -> Optional[dict]:
        with self._session() as s:
            e = s.query(ESFExperiment).get(experiment_id)
            if not e:
                return None
            for key, val in kwargs.items():
                if key == "conclusion_reason" and isinstance(val, dict):
                    setattr(e, key, json.dumps(val))
                elif hasattr(e, key):
                    setattr(e, key, val)
            s.commit()
            s.refresh(e)
            return _to_dict(e)

    def list_experiments(self) -> List[dict]:
        with self._session() as s:
            return [_to_dict(e) for e in
                    s.query(ESFExperiment).order_by(ESFExperiment.experiment_id.desc()).all()]

    # ── Hypotheses ────────────────────────

    def create_hypothesis(self, trade_date: str, ticker: str, direction: str,
                          entry_price: float, stop_loss: float, take_profit: float,
                          total_score: float, grade: str, confidence: float,
                          regime: str, reasoning_json: dict,
                          entry_hour_et: int = None, variant_id: int = None,
                          experiment_id: int = None, params_json: dict = None) -> dict:
        now = datetime.now().isoformat()
        with self._session() as s:
            h = ESFHypothesis(
                trade_date=trade_date,
                ticker=ticker,
                direction=direction,
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                total_score=total_score,
                grade=grade,
                confidence=confidence,
                regime=regime,
                entry_hour_et=entry_hour_et,
                variant_id=variant_id,
                experiment_id=experiment_id,
                reasoning_json=json.dumps(reasoning_json),
                params_json=json.dumps(params_json) if params_json else None,
                status="PENDING",
                created_at=now,
                updated_at=now,
            )
            s.add(h)
            s.commit()
            s.refresh(h)
            return _to_dict(h)

    def get_hypothesis(self, hypothesis_id: int) -> Optional[dict]:
        with self._session() as s:
            h = s.query(ESFHypothesis).get(hypothesis_id)
            return _to_dict(h)

    def get_hypotheses_by_date(self, trade_date: str) -> List[dict]:
        with self._session() as s:
            rows = s.query(ESFHypothesis).filter(
                ESFHypothesis.trade_date == trade_date
            ).order_by(ESFHypothesis.hypothesis_id).all()
            return [_to_dict(h) for h in rows]

    def get_hypotheses_paginated(self, offset: int = 0, limit: int = 20,
                                 direction: str = None, regime: str = None,
                                 grade: str = None, date_from: str = None,
                                 date_to: str = None) -> dict:
        with self._session() as s:
            q = s.query(ESFHypothesis)
            if direction:
                q = q.filter(ESFHypothesis.direction == direction)
            if regime:
                q = q.filter(ESFHypothesis.regime == regime)
            if grade:
                q = q.filter(ESFHypothesis.grade == grade)
            if date_from:
                q = q.filter(ESFHypothesis.trade_date >= date_from)
            if date_to:
                q = q.filter(ESFHypothesis.trade_date <= date_to)

            total = q.count()
            items = q.order_by(ESFHypothesis.trade_date.desc(), ESFHypothesis.hypothesis_id.desc()
                               ).offset(offset).limit(limit).all()
            return {"items": [_to_dict(h) for h in items], "total": total}

    def update_hypothesis_status(self, hypothesis_id: int, status: str) -> Optional[dict]:
        with self._session() as s:
            h = s.query(ESFHypothesis).get(hypothesis_id)
            if not h:
                return None
            h.status = status
            h.updated_at = datetime.now().isoformat()
            s.commit()
            s.refresh(h)
            return _to_dict(h)

    # ── Results ───────────────────────────

    def create_result(self, hypothesis_id: int, actual_entry_price: float,
                      actual_exit_price: float, actual_direction: str,
                      contracts: int, pnl_dollars: float, pnl_pct: float,
                      is_win: int, exit_reason: str, holding_minutes: int,
                      actual_high: float = None, actual_low: float = None,
                      actual_close: float = None, direction_correct: int = 0,
                      sl_hit: int = 0, tp_hit: int = 0) -> dict:
        now = datetime.now().isoformat()
        with self._session() as s:
            r = ESFResult(
                hypothesis_id=hypothesis_id,
                actual_entry_price=actual_entry_price,
                actual_exit_price=actual_exit_price,
                actual_direction=actual_direction,
                contracts=contracts,
                pnl_dollars=pnl_dollars,
                pnl_pct=pnl_pct,
                is_win=is_win,
                exit_reason=exit_reason,
                holding_minutes=holding_minutes,
                actual_high=actual_high,
                actual_low=actual_low,
                actual_close=actual_close,
                direction_correct=direction_correct,
                sl_hit=sl_hit,
                tp_hit=tp_hit,
                created_at=now,
            )
            s.add(r)
            s.commit()
            s.refresh(r)
            return _to_dict(r)

    def get_results_for_hypothesis(self, hypothesis_id: int) -> List[dict]:
        with self._session() as s:
            rows = s.query(ESFResult).filter(
                ESFResult.hypothesis_id == hypothesis_id
            ).all()
            return [_to_dict(r) for r in rows]

    def get_variant_results(self, variant_id: int) -> List[dict]:
        """variant에 연결된 모든 결과 (hypothesis join)."""
        with self._session() as s:
            rows = (
                s.query(ESFResult)
                .join(ESFHypothesis, ESFResult.hypothesis_id == ESFHypothesis.hypothesis_id)
                .filter(ESFHypothesis.variant_id == variant_id)
                .order_by(ESFResult.created_at)
                .all()
            )
            return [_to_dict(r) for r in rows]

    def get_all_results_with_hypotheses(self) -> List[dict]:
        """모든 결과 + 가설 데이터 (통계 계산용)."""
        with self._session() as s:
            rows = (
                s.query(ESFResult, ESFHypothesis)
                .join(ESFHypothesis, ESFResult.hypothesis_id == ESFHypothesis.hypothesis_id)
                .filter(ESFHypothesis.status == "CLOSED")
                .order_by(ESFHypothesis.trade_date)
                .all()
            )
            results = []
            for result, hyp in rows:
                d = _to_dict(result)
                d["direction"] = hyp.direction
                d["regime"] = hyp.regime
                d["grade"] = hyp.grade
                d["entry_hour_et"] = hyp.entry_hour_et
                d["trade_date"] = hyp.trade_date
                d["variant_id"] = hyp.variant_id
                results.append(d)
            return results

    # ── Cumulative Stats ──────────────────

    def upsert_cumulative_stat(self, dimension: str, dimension_value: str,
                               variant_id: Optional[int], stats: dict) -> None:
        now = datetime.now().isoformat()
        with self._session() as s:
            filters = [
                ESFCumulativeStat.dimension == dimension,
                ESFCumulativeStat.dimension_value == dimension_value,
            ]
            if variant_id is not None:
                filters.append(ESFCumulativeStat.variant_id == variant_id)
            else:
                filters.append(ESFCumulativeStat.variant_id.is_(None))

            existing = s.query(ESFCumulativeStat).filter(and_(*filters)).first()

            if existing:
                for key, val in stats.items():
                    if hasattr(existing, key):
                        setattr(existing, key, val)
                existing.updated_at = now
            else:
                stat = ESFCumulativeStat(
                    dimension=dimension,
                    dimension_value=dimension_value,
                    variant_id=variant_id,
                    updated_at=now,
                    **{k: v for k, v in stats.items()
                       if hasattr(ESFCumulativeStat, k)
                       and k not in ('dimension', 'dimension_value', 'variant_id', 'updated_at')},
                )
                s.add(stat)
            s.commit()

    def get_cumulative_stats(self, dimension: str = None,
                             variant_id: Optional[int] = None) -> List[dict]:
        with self._session() as s:
            q = s.query(ESFCumulativeStat)
            if dimension:
                q = q.filter(ESFCumulativeStat.dimension == dimension)
            if variant_id is not None:
                q = q.filter(ESFCumulativeStat.variant_id == variant_id)
            return [_to_dict(st) for st in q.all()]

    def get_stats_comparison(self, variant_a_id: int, variant_b_id: int) -> dict:
        return {
            "variant_a": self.get_cumulative_stats(variant_id=variant_a_id),
            "variant_b": self.get_cumulative_stats(variant_id=variant_b_id),
        }

    # ── Trends ────────────────────────────

    def get_results_for_trends(self, last_n_days: int = 30) -> List[dict]:
        """최근 N일 결과 (롤링 통계 계산용)."""
        from datetime import timedelta
        cutoff = (datetime.now() - timedelta(days=last_n_days)).strftime("%Y-%m-%d")
        with self._session() as s:
            rows = (
                s.query(ESFResult, ESFHypothesis)
                .join(ESFHypothesis, ESFResult.hypothesis_id == ESFHypothesis.hypothesis_id)
                .filter(ESFHypothesis.trade_date >= cutoff)
                .order_by(ESFHypothesis.trade_date)
                .all()
            )
            results = []
            for result, hyp in rows:
                d = _to_dict(result)
                d["trade_date"] = hyp.trade_date
                d["direction"] = hyp.direction
                d["regime"] = hyp.regime
                results.append(d)
            return results
