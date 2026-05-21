"""
Futures Paper Trading Engine

Decision Engine "GO" → SimPosition 생성 → live tick으로 SL/TP 자동 발화 → ESFJournal 기록.

설계 원칙:
  - 모든 SL/TP/entry 값은 GO 시점에 lock-in (백엔드 /esf/analyze 응답이 canonical)
  - 상태머신: OPEN → (SL_HIT | TP_HIT | MANUAL_CLOSE) → CLOSED
  - v1: ES3 progressive trailing OFF. 추후 sp500_futures의 _check_trailing_stop 재사용
  - 1-ticker-1-OPEN 보장
  - close_position 시 ESFResultRecorder.record_result로 자동 journaling
"""
from __future__ import annotations

import threading
import uuid
from datetime import datetime
from typing import Callable, Optional

from infra.db.connection import Database
from infra.db.models import FuturesPaperPosition
from infra.logger import get_logger

logger = get_logger("futures_paper_engine")

# 컨트랙트 메타 (futuresScalpEngine.ts ASSETS와 동기화)
CONTRACT_SPEC = {
    "ES=F": {"multiplier": 50.0, "tick_value": 12.50, "tick": 0.25},
    "MES=F": {"multiplier": 5.0, "tick_value": 1.25, "tick": 0.25},
    "NQ=F": {"multiplier": 20.0, "tick_value": 5.00, "tick": 0.25},
    "MNQ=F": {"multiplier": 2.0, "tick_value": 0.50, "tick": 0.25},
}

MAX_CONCURRENT_DEFAULT = 3


class FuturesPaperEngine:
    """선물 페이퍼 포지션 라이프사이클 관리."""

    def __init__(
        self,
        database: Database,
        recorder=None,
        publish: Optional[Callable[[str, dict], None]] = None,
        max_concurrent: int = MAX_CONCURRENT_DEFAULT,
    ):
        """
        Args:
            database: SQLAlchemy Database 인스턴스
            recorder: ESFResultRecorder (close 시 자동 journaling)
            publish: 동기 publish 콜백 (event_type, data) — SSE 발행용
            max_concurrent: 동시 OPEN 포지션 한도
        """
        self.db = database
        self.recorder = recorder
        self.publish = publish or (lambda *args, **kwargs: None)
        self.max_concurrent = max_concurrent
        self._lock = threading.Lock()

    # ── Public API ────────────────────────

    def open_position(
        self,
        ticker: str,
        direction: str,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        contracts: int = 1,
        hypothesis_id: Optional[int] = None,
    ) -> dict:
        """새 페이퍼 포지션 생성. 검증 실패 시 ValueError raise.

        검증:
          - direction ∈ {LONG, SHORT}
          - SL/TP가 direction과 일관 (LONG: sl<entry<tp, SHORT: tp<entry<sl)
          - 동일 ticker OPEN 존재 시 거부
          - 전체 OPEN ≥ max_concurrent 거부
          - ticker ∈ CONTRACT_SPEC
        """
        with self._lock:
            if ticker not in CONTRACT_SPEC:
                raise ValueError(f"Unsupported futures ticker: {ticker}")
            if direction not in ("LONG", "SHORT"):
                raise ValueError(f"Invalid direction: {direction}")
            if contracts < 1:
                raise ValueError(f"contracts must be >= 1, got {contracts}")

            # SL/TP 일관성
            if direction == "LONG":
                if not (stop_loss < entry_price < take_profit):
                    raise ValueError(
                        f"LONG requires sl({stop_loss}) < entry({entry_price}) < tp({take_profit})"
                    )
            else:  # SHORT
                if not (take_profit < entry_price < stop_loss):
                    raise ValueError(
                        f"SHORT requires tp({take_profit}) < entry({entry_price}) < sl({stop_loss})"
                    )

            # 동일 ticker OPEN 검사
            if self._get_open_by_ticker(ticker) is not None:
                raise ValueError(f"OPEN position already exists for {ticker}")

            # 전체 동시 OPEN 한도
            open_count = self._count_open()
            if open_count >= self.max_concurrent:
                raise ValueError(
                    f"Max concurrent paper positions reached ({open_count}/{self.max_concurrent})"
                )

            spec = CONTRACT_SPEC[ticker]
            now = datetime.now().isoformat()
            position_id = f"fp_{uuid.uuid4().hex[:12]}"

            with self.db.get_session() as s:
                row = FuturesPaperPosition(
                    position_id=position_id,
                    ticker=ticker,
                    direction=direction,
                    contracts=contracts,
                    contract_multiplier=spec["multiplier"],
                    tick_value=spec["tick_value"],
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    status="OPEN",
                    opened_at=now,
                    last_price=entry_price,
                    last_price_at=now,
                    hypothesis_id=hypothesis_id,
                    created_at=now,
                    updated_at=now,
                )
                s.add(row)
                s.commit()
                s.refresh(row)
                result = _to_dict(row)

        logger.info(
            "Paper position OPEN | id=%s | %s %s @ %.2f | SL=%.2f TP=%.2f | hypo=%s",
            position_id, ticker, direction, entry_price, stop_loss, take_profit, hypothesis_id,
        )
        self.publish("paper_position_opened", result)
        return result

    def tick(self, ticker: str, price: float) -> list[dict]:
        """라이브 가격 업데이트. 해당 ticker의 OPEN 포지션을 SL/TP 검사.

        Returns:
            청산된 포지션의 dict 리스트 (보통 0 또는 1개)
        """
        if ticker not in CONTRACT_SPEC:
            return []

        closed = []
        with self._lock:
            with self.db.get_session() as s:
                rows = (
                    s.query(FuturesPaperPosition)
                    .filter(
                        FuturesPaperPosition.ticker == ticker,
                        FuturesPaperPosition.status == "OPEN",
                    )
                    .all()
                )

                now = datetime.now().isoformat()
                for row in rows:
                    row.last_price = price
                    row.last_price_at = now
                    row.updated_at = now

                    exit_reason = self._check_exit(row, price)
                    if exit_reason:
                        # SL_HIT/TP_HIT 트랜지션 → CLOSED는 _finalize_close에서
                        row.status = f"{exit_reason}_HIT"
                        row.exit_price = price
                        row.exit_reason = exit_reason
                        row.closed_at = now
                        closed.append(_to_dict(row))
                s.commit()

        # 락 외부에서 journaling + publish (recorder는 자체 세션 사용)
        finalized = []
        for pos in closed:
            final = self._finalize_close(pos)
            finalized.append(final)
            self.publish("paper_position_closed", final)

        return finalized

    def close_position(self, position_id: str, price: float, reason: str = "MANUAL") -> dict:
        """수동 청산. price = 현재가."""
        with self._lock:
            with self.db.get_session() as s:
                row = s.query(FuturesPaperPosition).get(position_id)
                if not row:
                    raise ValueError(f"Position not found: {position_id}")
                if row.status != "OPEN":
                    raise ValueError(f"Position {position_id} not OPEN (status={row.status})")

                now = datetime.now().isoformat()
                row.status = "MANUAL_CLOSE"
                row.exit_price = price
                row.exit_reason = reason
                row.last_price = price
                row.last_price_at = now
                row.closed_at = now
                row.updated_at = now
                s.commit()
                s.refresh(row)
                pos = _to_dict(row)

        final = self._finalize_close(pos)
        self.publish("paper_position_closed", final)
        return final

    def list_open(self) -> list[dict]:
        with self.db.get_session() as s:
            rows = (
                s.query(FuturesPaperPosition)
                .filter(FuturesPaperPosition.status == "OPEN")
                .order_by(FuturesPaperPosition.opened_at)
                .all()
            )
            return [_to_dict(r) for r in rows]

    def list_all(self, status: Optional[str] = None, limit: int = 100) -> list[dict]:
        with self.db.get_session() as s:
            q = s.query(FuturesPaperPosition)
            if status:
                q = q.filter(FuturesPaperPosition.status == status)
            rows = q.order_by(FuturesPaperPosition.opened_at.desc()).limit(limit).all()
            return [_to_dict(r) for r in rows]

    def get(self, position_id: str) -> Optional[dict]:
        with self.db.get_session() as s:
            row = s.query(FuturesPaperPosition).get(position_id)
            return _to_dict(row) if row else None

    def get_open_tickers(self) -> set[str]:
        """OPEN 포지션이 있는 ticker 목록 (live_data subscribe용)."""
        with self.db.get_session() as s:
            rows = (
                s.query(FuturesPaperPosition.ticker)
                .filter(FuturesPaperPosition.status == "OPEN")
                .distinct()
                .all()
            )
            return {r[0] for r in rows}

    def realized_pnl_today(self) -> float:
        """오늘 종료된 포지션의 누적 실현 PnL ($)."""
        today_prefix = datetime.now().strftime("%Y-%m-%d")
        with self.db.get_session() as s:
            rows = (
                s.query(FuturesPaperPosition)
                .filter(
                    FuturesPaperPosition.status.in_(["SL_HIT", "TP_HIT", "MANUAL_CLOSE", "CLOSED"]),
                    FuturesPaperPosition.closed_at.like(f"{today_prefix}%"),
                )
                .all()
            )
            return sum(_compute_pnl_dollars(r) for r in rows)

    # ── Internal ──────────────────────────

    def _get_open_by_ticker(self, ticker: str) -> Optional[dict]:
        with self.db.get_session() as s:
            row = (
                s.query(FuturesPaperPosition)
                .filter(
                    FuturesPaperPosition.ticker == ticker,
                    FuturesPaperPosition.status == "OPEN",
                )
                .first()
            )
            return _to_dict(row) if row else None

    def _count_open(self) -> int:
        with self.db.get_session() as s:
            return (
                s.query(FuturesPaperPosition)
                .filter(FuturesPaperPosition.status == "OPEN")
                .count()
            )

    @staticmethod
    def _check_exit(row: FuturesPaperPosition, price: float) -> Optional[str]:
        """SL/TP hit 검사. "SL" | "TP" | None 반환."""
        if row.direction == "LONG":
            if price <= row.stop_loss:
                return "SL"
            if price >= row.take_profit:
                return "TP"
        else:  # SHORT
            if price >= row.stop_loss:
                return "SL"
            if price <= row.take_profit:
                return "TP"
        return None

    def _finalize_close(self, pos: dict) -> dict:
        """SL_HIT/TP_HIT/MANUAL_CLOSE → CLOSED 전환 + ESFResultRecorder 호출."""
        # journaling (recorder 등록되어 있고 hypothesis_id 있을 때만)
        if self.recorder and pos.get("hypothesis_id"):
            try:
                opened = datetime.fromisoformat(pos["opened_at"])
                closed = datetime.fromisoformat(pos["closed_at"])
                holding_minutes = max(1, int((closed - opened).total_seconds() / 60))
                self.recorder.record_result(
                    hypothesis_id=pos["hypothesis_id"],
                    result_data={
                        "actual_entry_price": pos["entry_price"],
                        "actual_exit_price": pos["exit_price"],
                        "actual_direction": pos["direction"],
                        "contracts": pos["contracts"],
                        "exit_reason": pos["exit_reason"] or "MANUAL",
                        "holding_minutes": holding_minutes,
                    },
                )
            except Exception as e:
                logger.error("Auto-journaling failed for %s: %s", pos["position_id"], e)

        # 최종 CLOSED 마킹
        now = datetime.now().isoformat()
        with self.db.get_session() as s:
            row = s.query(FuturesPaperPosition).get(pos["position_id"])
            if row:
                row.status = "CLOSED"
                row.updated_at = now
                s.commit()
                s.refresh(row)
                pos = _to_dict(row)

        logger.info(
            "Paper position CLOSED | id=%s | reason=%s | exit=%.2f | PnL=$%.2f",
            pos["position_id"], pos["exit_reason"], pos["exit_price"] or 0, _compute_pnl_dict(pos),
        )
        return pos


# ── Helpers ──────────────────────────────

def _to_dict(row) -> Optional[dict]:
    if row is None:
        return None
    return {c.name: getattr(row, c.name) for c in row.__table__.columns}


def _compute_pnl_dollars(row: FuturesPaperPosition) -> float:
    if row.exit_price is None:
        return 0.0
    direction_mult = 1.0 if row.direction == "LONG" else -1.0
    return (
        (row.exit_price - row.entry_price)
        * row.contracts
        * row.contract_multiplier
        * direction_mult
    )


def _compute_pnl_dict(pos: dict) -> float:
    if pos.get("exit_price") is None:
        return 0.0
    mult = 1.0 if pos["direction"] == "LONG" else -1.0
    return (
        (pos["exit_price"] - pos["entry_price"])
        * pos["contracts"]
        * pos["contract_multiplier"]
        * mult
    )
