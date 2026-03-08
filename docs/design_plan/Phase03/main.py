#!/usr/bin/env python3
"""
ATS (Automated Trading System) 엔트리포인트
문서: ATS-SAD-001

Usage:
    python main.py start            장중 매매 시작
    python main.py status           시스템 상태 확인
    python main.py init-db          DB 초기화
    python main.py backtest         백테스트 실행 (미구현)
"""

from __future__ import annotations

import sys
import os

# 프로젝트 루트를 Python path에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.main_loop import MainLoop
from core.scheduler import Scheduler
from core.state_manager import SystemStateManager
from data.config_manager import ConfigManager
from data.market_data import MarketDataProvider
from infra.broker.kis_broker import KISBroker
from infra.db.connection import Database
from infra.db.repository import Repository
from infra.logger import setup_logger, get_logger
from infra.notifier.telegram_notifier import TelegramNotifier
from order.order_executor import OrderExecutor
from position.position_manager import PositionManager
from report.report_generator import ReportGenerator
from risk.risk_manager import RiskManager
from strategy.momentum_swing import MomentumSwingStrategy


def build_application():
    """
    의존성 주입(DI)으로 애플리케이션을 구성한다 (SAD §4.2).
    main.py에서만 구현체를 결정하고, 나머지 모듈은 인터페이스에만 의존.
    """
    # ── 설정 로드 ──
    config_manager = ConfigManager(config_path="config.yaml", env_path=".env")
    config = config_manager.load()

    # ── 로거 초기화 ──
    setup_logger(log_dir="data_store/logs", level=config.log_level)
    logger = get_logger("main")
    logger.info("Building ATS application...")

    # ── Infrastructure Layer ──

    # Database
    database = Database(db_path=config.db_path)
    database.init_tables()
    repository = Repository(database)

    # Broker Adapter (한투 API)
    broker = KISBroker(
        app_key=config.kis_app_key,
        app_secret=config.kis_app_secret,
        account_no=config.kis_account_no,
        is_paper=config.kis_is_paper,
    )

    # Notifier Adapter (Telegram)
    notifier = TelegramNotifier(
        bot_token=config.telegram_bot_token,
        chat_id=config.telegram_chat_id,
    )

    # ── Data Access Layer ──
    market_data = MarketDataProvider(broker=broker, config=config)

    # ── Domain Layer ──

    # Strategy (플러그인)
    strategy = MomentumSwingStrategy(config=config)

    # Risk Manager
    risk_manager = RiskManager(config=config)

    # Position Manager
    position_manager = PositionManager(repository=repository, config=config)

    # Order Executor
    order_executor = OrderExecutor(
        broker=broker,
        repository=repository,
        position_manager=position_manager,
        risk_manager=risk_manager,
        notifier=notifier,
        config=config,
    )

    # Report Generator
    report_generator = ReportGenerator(
        repository=repository,
        position_manager=position_manager,
        broker=broker,
        notifier=notifier,
    )

    # ── Orchestrator Layer ──
    state_manager = SystemStateManager()

    main_loop = MainLoop(
        config=config,
        state_manager=state_manager,
        strategy=strategy,
        risk_manager=risk_manager,
        order_executor=order_executor,
        position_manager=position_manager,
        market_data=market_data,
        report_generator=report_generator,
        broker=broker,
        notifier=notifier,
        repository=repository,
    )

    scheduler = Scheduler(
        config=config,
        state_manager=state_manager,
        main_loop=main_loop,
    )

    logger.info("Application built successfully")
    return scheduler, database, config


def cmd_start():
    """장중 매매 시스템을 시작한다."""
    scheduler, database, config = build_application()
    try:
        scheduler.run()
    finally:
        database.close()


def cmd_init_db():
    """데이터베이스를 초기화한다."""
    config_manager = ConfigManager()
    config = config_manager.load()
    setup_logger(level=config.log_level)

    database = Database(db_path=config.db_path)
    database.init_tables()
    print(f"✅ Database initialized: {config.db_path}")
    database.close()


def cmd_status():
    """현재 시스템 상태를 출력한다."""
    config_manager = ConfigManager()
    config = config_manager.load()

    database = Database(db_path=config.db_path)
    repo = Repository(database)

    active = repo.get_active_positions()
    pending = repo.get_pending_positions()
    latest = repo.get_latest_report()

    print("=" * 50)
    print("ATS Status")
    print("=" * 50)
    print(f"  Config: {config.strategy.name}")
    print(f"  Mode:   {'모의투자' if config.kis_is_paper else '실전투자'}")
    print(f"  Active positions: {len(active)}")
    print(f"  Pending orders:   {len(pending)}")

    if active:
        print("\n  보유 종목:")
        for p in active:
            pnl_str = f"{p.pnl_pct:+.2%}" if p.pnl_pct else "N/A"
            print(f"    {p.stock_name:12s} | {p.quantity:4d}주 | {p.entry_price:>10,.0f}원 | {pnl_str}")

    if latest:
        print(f"\n  최근 리포트 ({latest.trade_date}):")
        print(f"    일일 수익률: {latest.daily_return:+.2f}%")
        print(f"    누적 수익률: {latest.cumulative_return:+.2f}%")
        print(f"    MDD: {latest.mdd:.2f}%")

    print("=" * 50)
    database.close()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1].lower()

    commands = {
        "start": cmd_start,
        "init-db": cmd_init_db,
        "status": cmd_status,
    }

    if command in commands:
        commands[command]()
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
