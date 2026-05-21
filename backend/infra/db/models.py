"""
SQLAlchemy ORM 모델 (테이블 정의)
문서: ATS-SAD-001 §10
"""

from sqlalchemy import (
    Column,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Universe(Base):
    """유니버스 종목 마스터 (SAD §10.1)

    멀티마켓 지원: PK가 (stock_code, market) 복합키.
    같은 ticker가 SP500·NDX 등 여러 마켓에 동시 존재 가능.

    Rebalance 메타 (5컬럼)는 매일 장 마감 후 RebalanceSyncJob이 마켓별로 갱신한다.
    `rebalance_action ∈ ('BUY','HOLD','KEEP')` 가 ExitGuard의 ES2 보호 판정에 사용된다.
    """
    __tablename__ = "universe"

    stock_code = Column(String(10), primary_key=True)
    market = Column(String(10), primary_key=True, default="KOSPI")
    stock_name = Column(String(50), nullable=False)
    sector = Column(String(50))
    is_active = Column(Integer, nullable=False, default=1)
    updated_at = Column(String(30), nullable=False)

    # Rebalance sync meta (nullable for backward compat)
    rebalance_action = Column(String(8))           # 'BUY' | 'HOLD' | 'KEEP'
    rebalance_score = Column(Float)                # 0~100 모멘텀 점수
    rebalance_rank = Column(Integer)               # top_n 내 순위 (1이 최고)
    return_6m = Column(Float)                      # 6개월 수익률 (0.5 = +50%)
    last_synced_at = Column(String(30))            # ISO timestamp


class RebalanceSyncLog(Base):
    """Rebalance → Universe 동기화 감사 로그 (Phase A)."""
    __tablename__ = "rebalance_sync_log"

    sync_id = Column(Integer, primary_key=True, autoincrement=True)
    market = Column(String(10), nullable=False, index=True)
    scan_date = Column(String(10), nullable=False, index=True)
    trigger = Column(String(10), nullable=False, default="AUTO")  # 'AUTO' | 'MANUAL'

    top_n = Column(Integer, default=0)
    buy_count = Column(Integer, default=0)
    hold_count = Column(Integer, default=0)
    kept_count = Column(Integer, default=0)        # 현 보유에 포함되어 유지된 종목
    total_active = Column(Integer, default=0)      # 최종 is_active=1 종목 수
    protected_count = Column(Integer, default=0)   # ES2 보호 대상 종목 수

    target_codes_json = Column(Text)               # 최종 활성화된 코드 리스트
    duration_ms = Column(Integer, default=0)
    error = Column(Text)                           # 실패 시 메시지

    created_at = Column(String(30), nullable=False, index=True)


class Position(Base):
    """매매 포지션 (SAD §10.2)"""
    __tablename__ = "positions"

    position_id = Column(String(50), primary_key=True)
    stock_code = Column(String(10), nullable=False, index=True)
    stock_name = Column(String(50), nullable=False)
    status = Column(String(20), nullable=False, default="PENDING", index=True)

    # 진입
    entry_price = Column(Float)
    quantity = Column(Integer, nullable=False)
    entry_amount = Column(Float)
    entry_date = Column(String(30), index=True)
    entry_signal = Column(Text)  # JSON

    # 청산 관리
    stop_loss_price = Column(Float)
    take_profit_price = Column(Float)
    trailing_high = Column(Float)
    trailing_stop_price = Column(Float)

    # 청산 결과
    exit_price = Column(Float)
    exit_date = Column(String(30))
    exit_reason = Column(String(10))

    # 손익
    pnl = Column(Float)
    pnl_pct = Column(Float)

    # 메타
    holding_days = Column(Integer, default=0)
    created_at = Column(String(30), nullable=False)
    updated_at = Column(String(30), nullable=False)

    # relationships
    orders = relationship("Order", backref="position", lazy="dynamic")
    trade_logs = relationship("TradeLog", backref="position", lazy="dynamic")


class Order(Base):
    """주문 이력 (SAD §10.3)"""
    __tablename__ = "orders"

    order_id = Column(String(50), primary_key=True)
    position_id = Column(String(50), ForeignKey("positions.position_id"), nullable=False, index=True)
    stock_code = Column(String(10), nullable=False)

    side = Column(String(10), nullable=False)
    order_type = Column(String(10), nullable=False)
    status = Column(String(20), nullable=False, default="SUBMITTED", index=True)

    price = Column(Float)
    quantity = Column(Integer, nullable=False)
    filled_quantity = Column(Integer, default=0)
    filled_price = Column(Float)
    filled_amount = Column(Float)

    broker_order_id = Column(String(50))
    reject_reason = Column(Text)
    retry_count = Column(Integer, default=0)

    created_at = Column(String(30), nullable=False, index=True)
    submitted_at = Column(String(30))
    filled_at = Column(String(30))
    cancelled_at = Column(String(30))


class TradeLog(Base):
    """매매 이벤트 로그 (SAD §10.4)"""
    __tablename__ = "trade_logs"

    log_id = Column(Integer, primary_key=True, autoincrement=True)
    position_id = Column(String(50), ForeignKey("positions.position_id"), index=True)
    stock_code = Column(String(10))
    event_type = Column(String(50), nullable=False, index=True)
    detail = Column(Text)  # JSON
    created_at = Column(String(30), nullable=False, index=True)


class DailyReport(Base):
    """일일 리포트 (SAD §10.5)"""
    __tablename__ = "daily_reports"

    report_id = Column(Integer, primary_key=True, autoincrement=True)
    trade_date = Column(String(10), nullable=False, unique=True)

    buy_count = Column(Integer, default=0)
    sell_count = Column(Integer, default=0)
    buy_amount = Column(Float, default=0)
    sell_amount = Column(Float, default=0)

    realized_pnl = Column(Float, default=0)
    unrealized_pnl = Column(Float, default=0)
    total_pnl = Column(Float, default=0)
    daily_return = Column(Float, default=0)
    cumulative_return = Column(Float, default=0)

    active_positions = Column(Integer, default=0)
    cash_balance = Column(Float, default=0)
    total_value = Column(Float, default=0)

    mdd = Column(Float, default=0)
    win_count = Column(Integer, default=0)
    lose_count = Column(Integer, default=0)

    created_at = Column(String(30), nullable=False)


class ConfigHistory(Base):
    """설정 변경 이력 (SAD §10.6)"""
    __tablename__ = "config_history"

    history_id = Column(Integer, primary_key=True, autoincrement=True)
    param_key = Column(String(100), nullable=False)
    old_value = Column(Text)
    new_value = Column(Text, nullable=False)
    changed_at = Column(String(30), nullable=False)


class SystemLog(Base):
    """시스템 로그 (SAD §10.7)"""
    __tablename__ = "system_logs"

    log_id = Column(Integer, primary_key=True, autoincrement=True)
    level = Column(String(10), nullable=False, index=True)
    module = Column(String(50), nullable=False)
    message = Column(Text, nullable=False)
    extra = Column(Text)  # JSON
    created_at = Column(String(30), nullable=False, index=True)


# ──────────────────────────────────────
# ESF Strategy Evolution System
# ──────────────────────────────────────

class ESFVariant(Base):
    """전략 변형 정의 — 파라미터 오버라이드 셋."""
    __tablename__ = "esf_variants"

    variant_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True)
    description = Column(Text)
    is_baseline = Column(Integer, default=0)
    is_active = Column(Integer, default=1)
    param_overrides_json = Column(Text, nullable=False, default="{}")
    created_at = Column(String(30), nullable=False)
    updated_at = Column(String(30), nullable=False)


class ESFExperiment(Base):
    """A/B 실험 — 두 변형 비교."""
    __tablename__ = "esf_experiments"

    experiment_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    status = Column(String(20), nullable=False, default="RUNNING", index=True)

    variant_a_id = Column(Integer, ForeignKey("esf_variants.variant_id"), nullable=False)
    variant_b_id = Column(Integer, ForeignKey("esf_variants.variant_id"), nullable=False)

    min_trades_per_variant = Column(Integer, default=20)
    max_days = Column(Integer, default=30)
    significance_threshold = Column(Float, default=0.05)

    winner_variant_id = Column(Integer)
    conclusion_reason = Column(Text)
    concluded_at = Column(String(30))

    start_date = Column(String(10), nullable=False)
    end_date = Column(String(10))
    created_at = Column(String(30), nullable=False)


class ESFHypothesis(Base):
    """일별 전략 가설 — 오늘의 전략 추천."""
    __tablename__ = "esf_hypotheses"

    hypothesis_id = Column(Integer, primary_key=True, autoincrement=True)
    trade_date = Column(String(10), nullable=False, index=True)
    ticker = Column(String(10), nullable=False, default="ES=F")
    variant_id = Column(Integer, ForeignKey("esf_variants.variant_id"), index=True)
    experiment_id = Column(Integer, ForeignKey("esf_experiments.experiment_id"), index=True)

    direction = Column(String(10), nullable=False)
    entry_price = Column(Float, nullable=False)
    stop_loss = Column(Float, nullable=False)
    take_profit = Column(Float, nullable=False)
    total_score = Column(Float, nullable=False)
    grade = Column(String(2), nullable=False)
    confidence = Column(Float, default=0.0)
    regime = Column(String(10), nullable=False)
    entry_hour_et = Column(Integer)

    reasoning_json = Column(Text, nullable=False)
    params_json = Column(Text)

    status = Column(String(20), nullable=False, default="PENDING", index=True)
    created_at = Column(String(30), nullable=False)
    updated_at = Column(String(30), nullable=False)


class ESFResult(Base):
    """전략 가설의 실제 결과."""
    __tablename__ = "esf_results"

    result_id = Column(Integer, primary_key=True, autoincrement=True)
    hypothesis_id = Column(Integer, ForeignKey("esf_hypotheses.hypothesis_id"), nullable=False, index=True)

    actual_entry_price = Column(Float)
    actual_exit_price = Column(Float)
    actual_direction = Column(String(10))
    contracts = Column(Integer, default=0)

    pnl_dollars = Column(Float, default=0.0)
    pnl_pct = Column(Float, default=0.0)
    is_win = Column(Integer, default=0)
    exit_reason = Column(String(30))
    holding_minutes = Column(Integer, default=0)

    actual_high = Column(Float)
    actual_low = Column(Float)
    actual_close = Column(Float)

    direction_correct = Column(Integer, default=0)
    sl_hit = Column(Integer, default=0)
    tp_hit = Column(Integer, default=0)

    created_at = Column(String(30), nullable=False)


class ESFCumulativeStat(Base):
    """누적 통계 — dimension별 집계."""
    __tablename__ = "esf_cumulative_stats"

    stat_id = Column(Integer, primary_key=True, autoincrement=True)
    dimension = Column(String(20), nullable=False, index=True)
    dimension_value = Column(String(30), nullable=False, index=True)
    variant_id = Column(Integer, index=True)

    total_trades = Column(Integer, default=0)
    wins = Column(Integer, default=0)
    losses = Column(Integer, default=0)
    win_rate = Column(Float, default=0.0)
    total_pnl = Column(Float, default=0.0)
    avg_pnl = Column(Float, default=0.0)
    sharpe_approx = Column(Float, default=0.0)
    profit_factor = Column(Float, default=0.0)
    avg_holding_minutes = Column(Float, default=0.0)
    direction_accuracy = Column(Float, default=0.0)

    updated_at = Column(String(30), nullable=False)


class FuturesPaperPosition(Base):
    """선물 페이퍼(시뮬) 포지션.

    Decision Engine "GO" 시점에 생성. backend `/esf/analyze` 응답의 stop_loss/take_profit가
    canonical로 lock-in 되며, live_data_service의 tick 루프가 가격을 모니터하여
    SL/TP hit 시 자동 청산(→ ESFResultRecorder.record_result).
    """
    __tablename__ = "futures_paper_positions"

    position_id = Column(String(50), primary_key=True)
    ticker = Column(String(10), nullable=False, index=True)
    direction = Column(String(10), nullable=False)  # LONG | SHORT

    # 계약 메타
    contracts = Column(Integer, nullable=False, default=1)
    contract_multiplier = Column(Float, nullable=False)
    tick_value = Column(Float, nullable=False)

    # 진입 (GO 시점에 lock-in)
    entry_price = Column(Float, nullable=False)
    stop_loss = Column(Float, nullable=False)
    take_profit = Column(Float, nullable=False)

    # 상태
    status = Column(String(20), nullable=False, default="OPEN", index=True)
    # OPEN | SL_HIT | TP_HIT | MANUAL_CLOSE | CLOSED

    # 청산
    exit_price = Column(Float)
    exit_reason = Column(String(20))  # "SL" | "TP" | "MANUAL"
    opened_at = Column(String(30), nullable=False, index=True)
    closed_at = Column(String(30))

    # 라이브 추적
    last_price = Column(Float)
    last_price_at = Column(String(30))

    # 가설 바인딩
    hypothesis_id = Column(Integer, ForeignKey("esf_hypotheses.hypothesis_id"), index=True)

    # ES3 progressive trailing (v2)
    trailing_high = Column(Float)
    trailing_stop = Column(Float)

    created_at = Column(String(30), nullable=False)
    updated_at = Column(String(30), nullable=False)


class ReplayResult(Base):
    """리플레이 시뮬레이션 결과 저장."""
    __tablename__ = "replay_results"

    result_id = Column(String(50), primary_key=True)
    market = Column(String(10), nullable=False, index=True)
    strategy = Column(String(20), nullable=False)
    start_date = Column(String(10), nullable=False)
    end_date = Column(String(10), nullable=False)

    # 요약 메트릭 (리스트 조회용)
    initial_capital = Column(Float, default=0.0)
    final_equity = Column(Float, default=0.0)
    total_return_pct = Column(Float, default=0.0)
    sharpe_ratio = Column(Float, default=0.0)
    max_drawdown_pct = Column(Float, default=0.0)
    total_trades = Column(Integer, default=0)
    win_rate = Column(Float, default=0.0)
    profit_factor = Column(Float, default=0.0)

    # 상세 데이터 (JSON blob)
    equity_curve_json = Column(Text)
    trades_json = Column(Text)
    metrics_json = Column(Text)

    created_at = Column(String(30), nullable=False, index=True)
