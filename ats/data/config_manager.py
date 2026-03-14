"""
ATS 설정 관리자
config.yaml + .env 로드
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


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
    atr_breakout_mult: float = 0.15     # 돌파 필터: (High - PrevClose) > mult * ATR (일일봉 최적화)
    atr_trend_mult: float = 1.5         # 추세 진입: Close > PrevClose ± mult * ATR

    # 거래량
    volume_ma_period: int = 20
    volume_confirm_mult: float = 1.5    # 거래량 확인 배수

    # OBV
    obv_ema_fast: int = 5
    obv_ema_slow: int = 20

    # 진입 점수 임계값
    entry_threshold: float = 50.0       # 최소 진입 점수 (0-100, 일일봉 최적화)

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
    # CHoCH 퇴출 확인
    choch_confirm_bars: int = 2
    choch_pnl_gate_loss: float = -0.02
    choch_pnl_gate_profit: float = 0.04
    # 페이크아웃 필터
    fakeout_min_vol_ratio: float = 0.5   # 일일봉 최적화 (기존 0.8)
    fakeout_max_wick_ratio: float = 2.0   # 일일봉 최적화 (기존 1.5)
    # 서킷브레이커 (시스템 레벨)
    rg1_daily_loss_limit: float = -0.03
    rg2_mdd_limit: float = -0.10

    # 거래소 서킷브레이커 (CME, sp500_futures.md Section 5)
    cb_level1_pct: float = 0.07        # -7% → 거래 중단
    cb_level2_pct: float = 0.13        # -13% → 거래 중단
    cb_level3_pct: float = 0.20        # -20% → 당일 종결
    cb_overnight_limit: float = 0.07   # 야간 ±7%
    exchange_cb_enabled: bool = True

    # 증거금 (sp500_futures.md Section 3)
    es_initial_margin: float = 15500.0      # ES 개시증거금
    es_maintenance_margin: float = 13700.0   # ES 유지증거금
    mes_initial_margin: float = 1550.0       # MES 개시증거금
    mes_maintenance_margin: float = 1370.0   # MES 유지증거금
    margin_call_enabled: bool = True         # 증거금 시뮬레이션 토글

    # 롤오버 (sp500_futures.md Section 9)
    roll_cost_per_contract: float = 12.50    # 캘린더 스프레드 비용 추정
    roll_warning_days: int = 5               # 롤 접근 경고 일수

    # 거래비용
    futures_slippage_per_contract: float = 12.50
    futures_commission_per_contract: float = 4.62
    # 비용 세분화
    es_exchange_fee: float = 1.40
    es_broker_fee: float = 0.85
    es_nfa_fee: float = 0.02
    mes_exchange_fee: float = 0.35
    mes_broker_fee: float = 0.25
    mes_nfa_fee: float = 0.02

    # ── 4-Layer 스코어링 임계값 (T1: 매직넘버 config화) ──

    # Layer 1: Z-Score 티어별 임계값
    zscore_tier1: float = 3.0       # 극단 (만점)
    zscore_tier2: float = 2.0       # 강한
    zscore_tier3: float = 1.5       # 약한
    zscore_tier4: float = 1.0       # 평균 부근
    zscore_tier1_pct: float = 1.0   # 만점 비율
    zscore_tier2_pct: float = 0.8
    zscore_tier3_pct: float = 0.5
    zscore_tier4_pct: float = 0.3
    zscore_block_threshold: float = 2.0  # 반대 방향 차단 임계값
    zscore_trend_cont_max_pct: float = 0.6  # 추세추종 보간 상한 (Z=-1 근처)
    zscore_trend_cont_min_pct: float = 0.2  # 추세추종 보간 하한 (Z=+1.5 근처)

    # Layer 2: 추세/구조 가중 비율
    trend_ema_full_pct: float = 0.4     # EMA 완전 정배열/역배열
    trend_ema_partial_pct: float = 0.2  # EMA 부분 정배열/역배열
    trend_ma200_pos_pct: float = 0.3    # MA200 위/아래
    trend_ma200_slope_pct: float = 0.3  # MA200 기울기
    trend_slope_lookback: int = 5       # MA200 기울기 계산 봉수

    # Layer 3: 모멘텀 가중 비율
    momentum_macd_cross_pct: float = 0.3    # MACD 크로스
    momentum_macd_hist_pct: float = 0.2     # MACD 히스토그램 상승/하락
    momentum_adx_trend_pct: float = 0.3     # ADX + DI 확인
    momentum_adx_bonus_pct: float = 0.1     # ADX 강한 추세 보너스
    momentum_rsi_ok_pct: float = 0.2        # RSI 적정 범위
    momentum_rsi_extreme_pct: float = 0.15  # RSI 극단 (과매수/과매도 반등)

    # Layer 4: 거래량/OBV 가중 비율
    volume_surge_pct: float = 0.35       # 거래량 서지
    volume_above_avg_pct: float = 0.15   # 거래량 평균 초과
    volume_above_avg_ratio: float = 1.2  # 평균 초과 판단 비율
    volume_obv_pct: float = 0.35         # OBV 추세
    volume_squeeze_pct: float = 0.3      # BB 스퀴즈

    # ── Progressive Trailing 4-tier (T2: CLAUDE.md 사양) ──
    trailing_tier1_pnl: float = 0.15     # ≥15% PnL
    trailing_tier1_atr: float = 1.5      # ATR 배수 (타이트)
    trailing_tier1_floor: float = -0.08  # 최소 floor -8%
    trailing_tier2_pnl: float = 0.10     # ≥10% PnL
    trailing_tier2_atr: float = 2.0      # ATR 배수
    trailing_tier2_floor: float = -0.06  # 최소 floor -6%
    trailing_tier3_pnl: float = 0.07     # ≥7% PnL
    trailing_tier3_atr: float = 2.5      # ATR 배수
    trailing_tier3_floor: float = -0.05  # 최소 floor -5%
    trailing_default_atr: float = 3.0    # 기본 ATR 배수
    trailing_default_floor: float = -0.04  # 기본 floor -4%

    # 포지션 사이징 (스코어 비례)
    sizing_base_mult: float = 0.4        # 최소 배수 (60점)
    sizing_max_mult: float = 1.25        # 최대 배수 (100점)
    sizing_score_base: float = 60.0      # 기준 점수
    sizing_score_range: float = 40.0     # 점수 범위 (100-60)

    # ATR 폴백
    atr_fallback_pct: float = 0.01       # ATR 0일 때 가격의 1%

    # 도지 캔들 임계값
    doji_body_threshold: float = 0.001   # 도지 판단 body 최소값

    # ── Market Regime (Phase 2) ──
    regime_bull_entry_threshold: float = 50.0    # BULL 시 진입 임계값 (일일봉 최적화)
    regime_bear_entry_threshold: float = 65.0    # BEAR 시 진입 임계값
    regime_bull_max_holding: int = 25            # BULL 시 최대 보유일
    regime_bear_max_holding: int = 12            # BEAR 시 최대 보유일
    regime_bear_sl_pct: float = 0.03             # BEAR 시 하드 손절
    regime_counter_bias_penalty: float = 5.0     # 역추세 진입 페널티 점수

    # ── EV Engine + Dynamic Kelly (Phase 3) ──
    ev_lookback: int = 30              # EV 계산 이력 수
    ev_min_trades: int = 5             # EV 게이트 활성 최소 트레이드
    kelly_min_trades: int = 10         # Dynamic Kelly 최소 트레이드
    kelly_half_mult: float = 0.5       # Half-Kelly 안전 계수
    kelly_max_fraction: float = 0.5    # Kelly 최대값

    # ── 연속 손절 정지 (Phase 4A) ──
    max_consecutive_losses: int = 3    # 연속 손절 시 진입 차단


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

        # 1. .env 로딩
        self._load_env(config)

        # 2. YAML 로딩
        try:
            import yaml
            with open(self.config_path) as f:
                data = yaml.safe_load(f) or {}
        except FileNotFoundError:
            logger.warning("config.yaml not found at %s, using defaults", self.config_path)
            return config

        # 3. 전체 섹션 매핑 로딩
        section_map = {
            "strategy": config.strategy,
            "exit": config.exit,
            "portfolio": config.portfolio,
            "risk": config.risk,
            "order": config.order,
            "smc_strategy": config.smc_strategy,
            "breakout_retest": config.breakout_retest,
            "sp500_futures": config.sp500_futures,
        }

        for section_name, section_obj in section_map.items():
            if section_name in data and isinstance(data[section_name], dict):
                self._apply_section(section_obj, data[section_name], section_name)

        # 4. system 레벨 설정
        if "system" in data and isinstance(data["system"], dict):
            if "log_level" in data["system"]:
                config.log_level = str(data["system"]["log_level"])

        # 5. 4-Layer 가중치 합계 검증
        self._validate_weights(config)

        return config

    def _load_env(self, config: ATSConfig) -> None:
        """Load secrets from .env file."""
        if os.path.exists(self.env_path):
            try:
                from dotenv import load_dotenv
                load_dotenv(self.env_path)
            except ImportError:
                logger.debug("python-dotenv not installed, reading env vars directly")

        config.kis_app_key = os.getenv("KIS_APP_KEY", "")
        config.kis_app_secret = os.getenv("KIS_APP_SECRET", "")
        config.kis_account_no = os.getenv("KIS_ACCOUNT_NO", "")
        config.kis_is_paper = os.getenv("KIS_IS_PAPER", "true").lower() == "true"
        config.telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        config.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        config.db_path = os.getenv("DB_PATH", config.db_path)

        # M10: 실전 모드에서 필수 시크릿 누락 시 경고
        if not config.kis_is_paper:
            for field in ["kis_app_key", "kis_app_secret", "kis_account_no"]:
                if not getattr(config, field):
                    logger.error("LIVE MODE: %s is required but empty!", field)

    @staticmethod
    def _apply_section(obj: object, values: dict, section_name: str) -> None:
        """Apply YAML values to dataclass with type coercion and warnings."""
        for k, v in values.items():
            if not hasattr(obj, k):
                logger.warning("[%s] Unknown config key: %s (ignored)", section_name, k)
                continue

            current = getattr(obj, k)
            expected_type = type(current)

            try:
                if expected_type == bool:
                    if isinstance(v, bool):
                        casted = v
                    else:
                        casted = str(v).lower() in ("true", "1", "yes")
                elif expected_type == int:
                    casted = int(v)
                elif expected_type == float:
                    casted = float(v)
                elif expected_type == tuple and isinstance(v, list):
                    casted = tuple(v)
                else:
                    casted = v
                setattr(obj, k, casted)
            except (ValueError, TypeError) as e:
                logger.error(
                    "[%s] Type error for %s: expected %s, got %s (%s)",
                    section_name, k, expected_type.__name__, type(v).__name__, e,
                )

    @staticmethod
    def _validate_weights(config: ATSConfig) -> None:
        """Validate that layer weights sum to ~100."""
        fc = config.sp500_futures
        layer_sum = fc.weight_zscore + fc.weight_trend + fc.weight_momentum + fc.weight_volume
        if abs(layer_sum - 100.0) > 0.1:
            logger.warning(
                "SP500 futures 4-Layer weights sum to %.1f (expected 100.0): "
                "zscore=%.1f, trend=%.1f, momentum=%.1f, volume=%.1f",
                layer_sum, fc.weight_zscore, fc.weight_trend,
                fc.weight_momentum, fc.weight_volume,
            )
