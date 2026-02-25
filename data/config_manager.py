"""
YAML 설정 파일 관리
문서: ATS-SAD-001 §7
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional

import yaml
from dotenv import load_dotenv

from infra.logger import get_logger

logger = get_logger("config")


@dataclass
class ScheduleConfig:
    pre_market_start: str = "08:50"
    market_open: str = "09:00"
    buy_start: str = "09:30"
    buy_end: str = "15:00"
    market_close: str = "15:30"
    report_time: str = "15:35"
    scan_interval_sec: int = 60


@dataclass
class StrategyConfig:
    name: str = "MomentumSwing"
    ma_short: int = 5
    ma_long: int = 20
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    rsi_period: int = 14
    rsi_lower: int = 30
    rsi_upper: int = 70
    bb_period: int = 20
    bb_std: float = 2.0
    volume_ma_period: int = 20
    volume_multiplier: float = 1.5


@dataclass
class ExitConfig:
    stop_loss_pct: float = -0.03
    take_profit_pct: float = 0.07
    trailing_stop_pct: float = -0.03
    max_holding_days: int = 10


@dataclass
class PortfolioConfig:
    max_positions: int = 10
    max_weight_per_stock: float = 0.15
    min_cash_ratio: float = 0.20


@dataclass
class RiskConfig:
    daily_loss_limit: float = -0.03
    mdd_limit: float = -0.10
    max_order_amount: float = 3_000_000


@dataclass
class OrderConfig:
    default_buy_type: str = "LIMIT"
    buy_timeout_min: int = 30
    sell_timeout_min: int = 15
    max_retry: int = 3
    retry_interval_sec: int = 5


@dataclass
class UniverseConfig:
    type: str = "KOSPI200"
    exclude: List[str] = field(default_factory=list)


@dataclass
class ATSConfig:
    """ATS 전체 설정 (config.yaml 매핑)."""
    system_name: str = "ATS-MomentumSwing"
    system_version: str = "1.0.0"
    log_level: str = "INFO"

    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    universe: UniverseConfig = field(default_factory=UniverseConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    exit: ExitConfig = field(default_factory=ExitConfig)
    portfolio: PortfolioConfig = field(default_factory=PortfolioConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    order: OrderConfig = field(default_factory=OrderConfig)

    # .env에서 로드
    kis_app_key: str = ""
    kis_app_secret: str = ""
    kis_account_no: str = ""
    kis_is_paper: bool = True
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    db_path: str = "data_store/ats.db"


class ConfigManager:
    """설정 파일을 로드하고 관리한다. (SAD §7)"""

    def __init__(self, config_path: str = "config.yaml", env_path: str = ".env"):
        self.config_path = config_path
        self.env_path = env_path
        self._config: Optional[ATSConfig] = None

    def load(self) -> ATSConfig:
        """config.yaml + .env를 로드하여 ATSConfig 객체를 반환한다."""
        # .env 로드
        load_dotenv(self.env_path)

        # YAML 로드
        yaml_data = {}
        if os.path.exists(self.config_path):
            with open(self.config_path, "r", encoding="utf-8") as f:
                yaml_data = yaml.safe_load(f) or {}
        else:
            logger.warning("Config file not found: %s (using defaults)", self.config_path)

        # ATSConfig 구성
        system = yaml_data.get("system", {})
        config = ATSConfig(
            system_name=system.get("name", "ATS-MomentumSwing"),
            system_version=system.get("version", "1.0.0"),
            log_level=system.get("log_level", "INFO"),
        )

        # Schedule
        sched = yaml_data.get("schedule", {})
        config.schedule = ScheduleConfig(**{
            k: sched[k] for k in ScheduleConfig.__dataclass_fields__ if k in sched
        })

        # Universe
        uni = yaml_data.get("universe", {})
        config.universe = UniverseConfig(
            type=uni.get("type", "KOSPI200"),
            exclude=uni.get("exclude", []),
        )

        # Strategy
        strat = yaml_data.get("strategy", {})
        config.strategy = StrategyConfig(**{
            k: strat[k] for k in StrategyConfig.__dataclass_fields__ if k in strat
        })

        # Exit
        ex = yaml_data.get("exit", {})
        config.exit = ExitConfig(**{
            k: ex[k] for k in ExitConfig.__dataclass_fields__ if k in ex
        })

        # Portfolio
        pf = yaml_data.get("portfolio", {})
        config.portfolio = PortfolioConfig(**{
            k: pf[k] for k in PortfolioConfig.__dataclass_fields__ if k in pf
        })

        # Risk
        rsk = yaml_data.get("risk", {})
        config.risk = RiskConfig(**{
            k: rsk[k] for k in RiskConfig.__dataclass_fields__ if k in rsk
        })

        # Order
        ord_ = yaml_data.get("order", {})
        config.order = OrderConfig(**{
            k: ord_[k] for k in OrderConfig.__dataclass_fields__ if k in ord_
        })

        # .env 값 (NFR-S01: 소스코드에 포함하지 않음)
        config.kis_app_key = os.getenv("KIS_APP_KEY", "")
        config.kis_app_secret = os.getenv("KIS_APP_SECRET", "")
        config.kis_account_no = os.getenv("KIS_ACCOUNT_NO", "")
        config.kis_is_paper = os.getenv("KIS_IS_PAPER", "true").lower() == "true"
        config.telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        config.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        config.db_path = os.getenv("DB_PATH", "data_store/ats.db")

        self._config = config
        logger.info(
            "Config loaded | strategy=%s | paper=%s | max_pos=%d | stop_loss=%s",
            config.strategy.name,
            config.kis_is_paper,
            config.portfolio.max_positions,
            config.exit.stop_loss_pct,
        )
        return config

    @property
    def config(self) -> ATSConfig:
        if self._config is None:
            return self.load()
        return self._config
