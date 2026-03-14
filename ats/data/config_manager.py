"""
ATS 설정 관리자
config.yaml + .env 로드
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class StrategyConfig:
    name: str = "MomentumSwing"
    ma_short: int = 5
    ma_long: int = 20
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    rsi_period: int = 14
    rsi_lower: float = 52.0
    rsi_upper: float = 78.0
    bb_period: int = 20
    bb_std: float = 2.0
    volume_ma_period: int = 20
    volume_multiplier: float = 1.5


@dataclass
class ExitConfig:
    stop_loss_pct: float = -0.05
    take_profit_pct: float = 0.20
    trailing_stop_pct: float = -0.04
    max_holding_days: int = 40


@dataclass
class PortfolioConfig:
    max_positions: int = 10
    max_weight_per_stock: float = 0.15
    min_cash_ratio: float = 0.30


@dataclass
class RiskConfig:
    daily_loss_limit: float = -0.05
    mdd_limit: float = -0.15
    max_order_amount: float = 3_000_000


@dataclass
class OrderConfig:
    default_buy_type: str = "LIMIT"
    buy_timeout_min: int = 30
    sell_timeout_min: int = 15
    max_retry: int = 3
    retry_interval_sec: int = 5


@dataclass
class SMCStrategyConfig:
    swing_length: int = 3
    entry_threshold: float = 60.0
    atr_sl_mult: float = 2.0
    atr_tp_mult: float = 3.0
    choch_exit: bool = True
    ob_lookback: int = 20
    fvg_mitigation: bool = True
    weight_smc: float = 40.0
    weight_bb: float = 20.0
    weight_obv: float = 20.0
    weight_momentum: float = 20.0


@dataclass
class BreakoutRetestConfig:
    swing_length: int = 3
    bb_squeeze_lookback: int = 100
    bb_squeeze_ema: int = 50
    displacement_atr_mult: float = 1.5
    obv_break_lookback: int = 20
    adx_threshold: float = 25.0
    adx_rising_bars: int = 3
    min_volume_ratio: float = 1.0
    max_wick_body_ratio: float = 1.0
    divergence_check: bool = True
    weight_structure: float = 30.0
    weight_volatility: float = 20.0
    weight_volume: float = 25.0
    weight_momentum: float = 25.0
    breakout_threshold: float = 65.0
    retest_max_bars: int = 15
    retest_zone_atr_buffer: float = 0.3
    retest_volume_decay: float = 0.8
    retest_rsi_floor: float = 40.0
    retest_rejection_wick_ratio: float = 0.5
    use_fvg_zone: bool = True
    use_ob_zone: bool = True
    use_breakout_level: bool = True
    fvg_zone_weight: float = 40.0
    ob_zone_weight: float = 35.0
    level_zone_weight: float = 25.0
    retest_zone_threshold: float = 50.0
    atr_sl_mult: float = 1.5
    atr_tp_mult: float = 3.0
    choch_exit: bool = True
    max_holding_days: int = 30
    trailing_activation_pct: float = 0.05
    trailing_atr_mult: float = 2.0


@dataclass
class SP500FuturesConfig:
    """S&P 500 선물 매매 전략 설정."""
    # 기본 설정
    ticker: str = "ES=F"
    contract_multiplier: float = 50.0   # E-mini: $50/pt, Micro: $5/pt
    is_micro: bool = False              # Micro E-mini 여부

    # Z-Score 설정
    zscore_ma_period: int = 20          # Z-Score 이동평균 기간
    zscore_std_period: int = 20         # Z-Score 표준편차 기간
    zscore_long_threshold: float = -2.0  # 롱 진입 Z-Score
    zscore_short_threshold: float = 2.0  # 숏 진입 Z-Score

    # 추세 필터
    ma_fast: int = 10                   # 단기 EMA
    ma_mid: int = 20                    # 중기 EMA
    ma_slow: int = 50                   # 장기 EMA
    ma_trend: int = 200                 # 추세 판단 MA
    adx_period: int = 14               # ADX 기간
    adx_threshold: float = 25.0        # 추세 강도 최소 ADX
    adx_strong: float = 40.0           # 강한 추세 ADX

    # MACD 설정
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9

    # RSI 설정
    rsi_period: int = 14
    rsi_oversold: float = 30.0          # 과매도 (롱 확인)
    rsi_overbought: float = 70.0        # 과매수 (숏 확인)
    rsi_long_range: tuple = (40.0, 65.0)   # 롱 진입 RSI 범위
    rsi_short_range: tuple = (35.0, 60.0)  # 숏 진입 RSI 범위

    # 볼린저밴드
    bb_period: int = 20
    bb_std: float = 2.0
    bb_squeeze_ratio: float = 0.8       # 스퀴즈 판단

    # ATR 설정
    atr_period: int = 14
    atr_breakout_mult: float = 0.5      # 돌파 필터: (High - PrevClose) > mult * ATR
    atr_trend_mult: float = 1.5         # 추세 진입: Close > PrevClose ± mult * ATR

    # 거래량
    volume_ma_period: int = 20
    volume_confirm_mult: float = 1.5    # 거래량 확인 배수

    # OBV
    obv_ema_fast: int = 5
    obv_ema_slow: int = 20

    # 진입 점수 임계값
    entry_threshold: float = 60.0       # 최소 진입 점수 (0-100)

    # 손절 설정
    sl_atr_mult: float = 2.0           # ATR 기반 손절 배수 (기본)
    sl_atr_mult_strong: float = 1.5    # 강한 추세 시 타이트 손절
    sl_hard_pct: float = 0.03          # 하드 손절 3% (선물이므로 타이트)

    # 익절 설정
    tp_atr_mult: float = 3.0           # ATR 기반 익절 배수
    tp_rr_ratio: float = 2.0           # 최소 Risk:Reward

    # 트레일링 스탑
    trailing_activation_pct: float = 0.02  # 트레일링 활성화 +2%
    trailing_atr_mult: float = 2.0        # 트레일링 ATR 배수
    chandelier_atr_mult: float = 3.0      # 샹들리에 ATR 배수 (최고가/최저가 기준)

    # 최대 보유 기간
    max_holding_days: int = 20

    # 포지션 사이징 (Kelly)
    kelly_fraction: float = 0.3         # Half-Kelly 선물용
    max_contracts: int = 10             # 최대 계약 수
    risk_per_trade_pct: float = 0.015   # 트레이드당 리스크 1.5%

    # 레이어 가중치 (합계 100)
    weight_zscore: float = 25.0         # Layer 1: Z-Score 통계적 위치
    weight_trend: float = 25.0          # Layer 2: 추세/구조
    weight_momentum: float = 25.0       # Layer 3: 모멘텀 (MACD, ADX)
    weight_volume: float = 25.0         # Layer 4: 거래량/OBV


@dataclass
class ATSConfig:
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    exit: ExitConfig = field(default_factory=ExitConfig)
    portfolio: PortfolioConfig = field(default_factory=PortfolioConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    order: OrderConfig = field(default_factory=OrderConfig)
    smc_strategy: SMCStrategyConfig = field(default_factory=SMCStrategyConfig)
    breakout_retest: BreakoutRetestConfig = field(default_factory=BreakoutRetestConfig)
    sp500_futures: SP500FuturesConfig = field(default_factory=SP500FuturesConfig)

    # System
    log_level: str = "INFO"
    db_path: str = "data_store/ats.db"

    # Secrets (from .env)
    kis_app_key: str = ""
    kis_app_secret: str = ""
    kis_account_no: str = ""
    kis_is_paper: bool = True
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""


class ConfigManager:
    def __init__(self, config_path: str = "config.yaml", env_path: str = ".env"):
        self.config_path = config_path
        self.env_path = env_path

    def load(self) -> ATSConfig:
        config = ATSConfig()
        try:
            import yaml
            with open(self.config_path) as f:
                data = yaml.safe_load(f) or {}
            if "sp500_futures" in data:
                fc = data["sp500_futures"]
                for k, v in fc.items():
                    if hasattr(config.sp500_futures, k):
                        setattr(config.sp500_futures, k, v)
        except FileNotFoundError:
            pass
        return config
