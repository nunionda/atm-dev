"""
ATS 테스트 공용 Fixture 및 Mock
문서: ATS-IMP-001 Phase 4
"""

import os
import sys
import json
import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# ats/ 디렉토리를 path에 추가 (모든 모듈은 ats/ 하위에 위치)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from common.enums import (
    OrderSide,
    OrderStatus,
    OrderType,
    PositionStatus,
    SystemState,
)
from common.types import (
    Balance,
    BalancePosition,
    DailyReportData,
    ExitSignal,
    OrderRequest,
    OrderResult,
    OrderStatusResponse,
    Portfolio,
    PriceData,
    RiskCheckResult,
    Signal,
)
from data.config_manager import (
    ATSConfig,
    ExitConfig,
    OrderConfig,
    PortfolioConfig,
    RiskConfig,
    ScheduleConfig,
    StrategyConfig,
    UniverseConfig,
)
from infra.db.connection import Database
from infra.db.models import Order, Position
from infra.db.repository import Repository


# ══════════════════════════════════════════════
# 설정 Fixtures
# ══════════════════════════════════════════════

@pytest.fixture
def config() -> ATSConfig:
    """테스트용 ATSConfig."""
    return ATSConfig(
        system_name="ATS-Test",
        system_version="1.0.0-test",
        log_level="DEBUG",
        schedule=ScheduleConfig(
            pre_market_start="08:50",
            market_open="09:00",
            buy_start="09:30",
            buy_end="15:00",
            market_close="15:30",
            report_time="15:35",
            scan_interval_sec=1,
        ),
        universe=UniverseConfig(type="KOSPI200", exclude=[]),
        strategy=StrategyConfig(
            name="MomentumSwing",
            ma_short=5,
            ma_long=20,
            macd_fast=12,
            macd_slow=26,
            macd_signal=9,
            rsi_period=14,
            rsi_lower=30,
            rsi_upper=70,
            bb_period=20,
            bb_std=2.0,
            volume_ma_period=20,
            volume_multiplier=1.5,
        ),
        exit=ExitConfig(
            stop_loss_pct=-0.03,
            take_profit_pct=0.07,
            trailing_stop_pct=-0.03,
            max_holding_days=10,
        ),
        portfolio=PortfolioConfig(
            max_positions=10,
            max_weight_per_stock=0.15,
            min_cash_ratio=0.20,
        ),
        risk=RiskConfig(
            daily_loss_limit=-0.03,
            mdd_limit=-0.10,
            max_order_amount=3_000_000,
        ),
        order=OrderConfig(
            default_buy_type="LIMIT",
            buy_timeout_min=30,
            sell_timeout_min=15,
            max_retry=3,
            retry_interval_sec=0,  # 테스트에서는 대기 없음
        ),
        kis_app_key="test_key",
        kis_app_secret="test_secret",
        kis_account_no="12345678-01",
        kis_is_paper=True,
        telegram_bot_token="test_token",
        telegram_chat_id="test_chat",
        db_path=":memory:",
    )


# ══════════════════════════════════════════════
# Database Fixtures
# ══════════════════════════════════════════════

@pytest.fixture
def database():
    """인메모리 SQLite 데이터베이스."""
    db = Database(db_path=":memory:")
    db.init_tables()
    yield db
    db.close()


@pytest.fixture
def repository(database):
    """테스트용 Repository."""
    return Repository(database)


# ══════════════════════════════════════════════
# Mock Fixtures
# ══════════════════════════════════════════════

@pytest.fixture
def mock_broker():
    """Mock Broker (BaseBroker 인터페이스)."""
    broker = MagicMock()
    broker.authenticate.return_value = "test_token_123"
    broker.is_token_valid.return_value = True

    broker.get_price.return_value = PriceData(
        stock_code="005930",
        stock_name="삼성전자",
        current_price=72000.0,
        open_price=71500.0,
        high_price=72500.0,
        low_price=71000.0,
        prev_close=71800.0,
        volume=15000000,
        change_pct=0.28,
        timestamp=datetime.now().isoformat(),
    )

    broker.place_order.return_value = OrderResult(
        success=True,
        order_id="test_order",
        broker_order_id="KIS_ORD_001",
    )

    broker.cancel_order.return_value = True

    broker.get_order_status.return_value = OrderStatusResponse(
        broker_order_id="KIS_ORD_001",
        status="FILLED",
        filled_quantity=20,
        filled_price=72000.0,
        filled_amount=1440000.0,
    )

    broker.get_balance.return_value = Balance(
        cash=8_000_000.0,
        total_eval=2_000_000.0,
        total_pnl=50_000.0,
        total_pnl_pct=2.56,
        positions=[
            BalancePosition(
                stock_code="005930",
                stock_name="삼성전자",
                quantity=20,
                avg_price=71000.0,
                current_price=72000.0,
                eval_amount=1440000.0,
                pnl=20000.0,
                pnl_pct=1.41,
            ),
        ],
    )

    return broker


@pytest.fixture
def mock_notifier():
    """Mock Notifier (BaseNotifier 인터페이스)."""
    notifier = MagicMock()
    notifier.send_message.return_value = True
    notifier.send_report.return_value = True
    return notifier


# ══════════════════════════════════════════════
# 시세 데이터 Fixtures
# ══════════════════════════════════════════════

@pytest.fixture
def sample_ohlcv() -> pd.DataFrame:
    """60일간의 샘플 OHLCV 데이터 (상승 추세 + 골든크로스 유도)."""
    import numpy as np

    np.random.seed(42)
    dates = pd.date_range("2026-01-01", periods=60, freq="B")

    # 기본 상승 추세
    base_price = 70000
    trend = np.linspace(0, 5000, 60)
    noise = np.random.normal(0, 500, 60)
    closes = base_price + trend + noise

    # 마지막 5일: 급등 (골든크로스 유발)
    closes[-5:] += 2000

    df = pd.DataFrame({
        "date": [d.strftime("%Y%m%d") for d in dates],
        "open": closes - np.random.uniform(100, 500, 60),
        "high": closes + np.random.uniform(100, 800, 60),
        "low": closes - np.random.uniform(100, 800, 60),
        "close": closes,
        "volume": np.random.randint(10_000_000, 30_000_000, 60),
    })

    return df


@pytest.fixture
def sample_ohlcv_downtrend() -> pd.DataFrame:
    """하락 추세 OHLCV (데드크로스 유발)."""
    import numpy as np

    np.random.seed(99)
    dates = pd.date_range("2026-01-01", periods=60, freq="B")

    base_price = 75000
    trend = np.linspace(0, -5000, 60)
    noise = np.random.normal(0, 300, 60)
    closes = base_price + trend + noise

    # 마지막 5일: 급락 (데드크로스 유발)
    closes[-5:] -= 2000

    df = pd.DataFrame({
        "date": [d.strftime("%Y%m%d") for d in dates],
        "open": closes + np.random.uniform(100, 300, 60),
        "high": closes + np.random.uniform(100, 600, 60),
        "low": closes - np.random.uniform(100, 600, 60),
        "close": closes,
        "volume": np.random.randint(5_000_000, 15_000_000, 60),
    })

    return df


@pytest.fixture
def sample_price_data() -> PriceData:
    """샘플 현재가 데이터."""
    return PriceData(
        stock_code="005930",
        stock_name="삼성전자",
        current_price=72000.0,
        open_price=71500.0,
        high_price=72500.0,
        low_price=71000.0,
        prev_close=71800.0,
        volume=15000000,
        change_pct=0.28,
        timestamp=datetime.now().isoformat(),
    )


@pytest.fixture
def sample_signal() -> Signal:
    """샘플 매수 시그널."""
    return Signal(
        stock_code="005930",
        stock_name="삼성전자",
        signal_type="BUY",
        primary_signals=["PS1"],
        confirmation_filters=["CF1"],
        current_price=72000.0,
        bb_upper=76000.0,
    )


@pytest.fixture
def sample_portfolio() -> Portfolio:
    """샘플 포트폴리오 (총 1천만원)."""
    return Portfolio(
        total_capital=10_000_000.0,
        cash_balance=8_000_000.0,
        active_count=2,
        daily_buy_amount=1_500_000.0,
        daily_pnl=50_000.0,
        total_value=10_050_000.0,
        mdd=-0.01,
    )


@pytest.fixture
def sample_active_position(repository) -> Position:
    """DB에 저장된 샘플 ACTIVE 포지션."""
    now = datetime.now().isoformat()
    pos = Position(
        position_id="pos_test_001",
        stock_code="005930",
        stock_name="삼성전자",
        status=PositionStatus.ACTIVE.value,
        entry_price=70000.0,
        quantity=20,
        entry_amount=1400000.0,
        entry_date=now,
        stop_loss_price=67900.0,    # 70000 × 0.97
        take_profit_price=74900.0,  # 70000 × 1.07
        trailing_high=72000.0,
        trailing_stop_price=69840.0,  # 72000 × 0.97
        holding_days=3,
        created_at=now,
        updated_at=now,
    )
    repository.create_position(pos)
    return pos
