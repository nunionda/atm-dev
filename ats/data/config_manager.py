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
    rsi_lower: int = 52
    rsi_upper: int = 78
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
    """SMC 4-Layer 스코어링 전략 설정."""
    swing_length: int = 3           # Swing Point 프랙탈 길이
    entry_threshold: int = 60       # 최소 진입 점수 (0~100)
    atr_sl_mult: float = 2.0        # ATR × 배수 = Stop Loss
    atr_tp_mult: float = 3.0        # ATR × 배수 = Take Profit
    choch_exit: bool = True         # CHoCH 발생 시 청산 여부
    ob_lookback: int = 20           # Order Block 탐색 범위 (캔들 수)
    fvg_mitigation: bool = True     # FVG 미티게이션 추적 여부
    # Layer 가중치 (합산 100)
    weight_smc: int = 40            # Layer 1: SMC Bias
    weight_bb: int = 20             # Layer 2: BB Squeeze + ATR
    weight_obv: int = 20            # Layer 3a: OBV
    weight_momentum: int = 20       # Layer 3b: ADX + MACD


@dataclass
class TierConfig:
    """개별 Tier 설정 (3-Tier 포트폴리오 배분용)."""
    ticker: str = ""
    ticker_yf: str = ""
    name: str = ""
    weight: float = 0.0
    top_n: int = 10           # tactical 전용
    rebalance_days: int = 14  # tactical 전용


@dataclass
class PortfolioAllocationConfig:
    """Tactical 전용 포트폴리오 배분 설정 (Kelly Criterion 기반).

    최적화 계산 근거 (백테스트 성과: Sharpe 2.48, WR 57.5%, PF 2.67):
      Full Kelly f* = (b×p - q)/b = 0.36
      Half-Kelly × 다각화 보정(2.2x) × 실무(0.85x) = 0.35

    투자 비율 (Kelly 30%, 자본금 1억):
      총 투자금 = 1억 × 0.30 = 3,000만
      Tactical (100%): 60종목 → 3,000만 (종목당 ~50만)
      현금: 7,000만
    """
    enabled: bool = False
    kelly_fraction: float = 0.30
    tactical: TierConfig = field(default_factory=lambda: TierConfig(
        weight=1.0, top_n=60, rebalance_days=14
    ))


@dataclass
class BreakoutRetestConfig:
    """Breakout-Retest 전략 설정 (돌파 후 리테스트 진입)."""
    # ── Phase A: Breakout Detection ──
    swing_length: int = 3              # Swing Point 프랙탈 길이
    bb_squeeze_lookback: int = 100     # BB Width 최저점 탐색 범위 (봉 수)
    bb_squeeze_ema: int = 50           # BB Width EMA 스무딩 기간
    displacement_atr_mult: float = 1.5  # Displacement 캔들 기준 (body > ATR × mult)
    obv_break_lookback: int = 20       # OBV 돌파 lookback (봉 수)
    adx_threshold: int = 25            # ADX 최소 강도
    adx_rising_bars: int = 3           # ADX 연속 상승 봉 수

    # ── Fakeout Filters ──
    min_volume_ratio: float = 1.0      # Err01: volume < MA20 × ratio → 차단
    max_wick_body_ratio: float = 1.0   # Err02: wick / body > ratio → 차단
    divergence_check: bool = True      # Err03: MACD/RSI 다이버전스 차단

    # ── Scoring Weights (합계 100) ──
    weight_structure: int = 30         # Layer 1: SMC 구조 (BOS + 유동성 스윕)
    weight_volatility: int = 20        # Layer 2: BB squeeze + ATR
    weight_volume: int = 25            # Layer 3: OBV 돌파
    weight_momentum: int = 25          # Layer 4: ADX + MACD
    breakout_threshold: int = 55       # Phase 5: 65→55 돌파 감지 확대

    # ── Phase B: Retest Entry ──
    retest_max_bars: int = 25          # Phase 5: 15→25 리테스트 대기 연장
    retest_zone_atr_buffer: float = 0.5  # Phase 5: 0.3→0.5 리테스트 존 확장
    retest_volume_decay: float = 0.8   # 풀백 거래량 < MA20 × decay
    retest_rsi_floor: int = 40         # RSI 하한
    retest_rejection_wick_ratio: float = 0.5  # 반등 캔들 하단꼬리/몸통 비율

    # ── Retest Zone Scoring ──
    use_fvg_zone: bool = True          # FVG 존 사용
    use_ob_zone: bool = True           # Order Block 존 사용
    use_breakout_level: bool = True    # 돌파 가격 레벨 사용
    fvg_zone_weight: int = 40          # FVG 근접도 가중치
    ob_zone_weight: int = 35           # OB 근접도 가중치
    level_zone_weight: int = 25        # 돌파 레벨 근접도 가중치
    retest_zone_threshold: int = 50    # 리테스트 존 최소 점수

    # ── Exit Rules ──
    atr_sl_mult: float = 1.5           # 리테스트 진입이므로 타이트 (SMC 2.0 대비)
    atr_tp_mult: float = 3.0           # R:R 최소 2:1
    choch_exit: bool = True            # CHoCH 발생 시 청산
    max_holding_days: int = 30         # 최대 보유일
    trailing_activation_pct: float = 0.05  # 트레일링 활성화 (5%)
    trailing_atr_mult: float = 2.0     # 트레일링 ATR 배수


@dataclass
class MeanReversionConfig:
    """Mean Reversion 전략 설정 (과매도 구간 평균 회귀 진입)."""
    rsi_oversold: int = 35              # RSI oversold zone (graduated scoring)
    rsi_overbought: int = 70            # RSI for mean-reversion TP
    entry_threshold: int = 50           # 최소 진입 점수 (graduated scoring으로 하향)
    adx_trending_limit: int = 25        # Phase 5: ADX > 25 = 추세장 → MR 금지 (30→25 엄격화)
    extreme_oversold_rsi: int = 28      # 극도 과매도 시 ADX 필터 무시
    atr_sl_mult: float = 1.5            # ATR × mult for SL
    volume_spike_mult: float = 1.5      # 거래량 > MA20 × mult (2.0→1.5 완화)
    consecutive_down_days: int = 2      # 최소 연속 하락일 (3→2 완화)
    max_holding_days: int = 20          # Phase 5: 최대 보유일 확대 (15→20, MR은 시간 필요)
    max_weight_pct: float = 0.10        # 종목당 최대 비중 10%
    stochastic_k_period: int = 14       # Stochastic %K
    stochastic_d_period: int = 3        # Stochastic %D
    # Layer weights (sum = 100)
    weight_signal: int = 40             # Layer 1: MR signal
    weight_volatility: int = 30         # Layer 2: Vol & volume
    weight_confirmation: int = 30       # Layer 3: Confirmation


@dataclass
class ArbitrageConfig:
    """Statistical Pairs Arbitrage 전략 설정 (Long+Short 양방향) v5."""
    correlation_lookback: int = 60       # 상관관계 계산 기간 (일)
    correlation_min: float = 0.50        # v4: 0.60→0.50 (KOSPI 상관관계 필터 완화)
    zscore_lookback: int = 20            # Z-Score 계산 기간 (일)
    zscore_entry: float = 1.5            # v4: 2.0→1.5 진입 Z-Score 완화 (진입 기회 확대)
    zscore_exit: float = 0.2             # 청산 Z-Score 임계값 (v2: 0.5→0.2, 방향성 청산)
    halflife_max: int = 40               # 최대 반감기 (v2: 20→40)
    entry_threshold: int = 60            # v4: 70→60 복원 (진입 기회 확대)
    atr_sl_mult: float = 2.0             # ATR × 배수 = Stop Loss (ADX < 20)
    atr_sl_mult_strong: float = 1.5      # ATR × 배수 (ADX ≥ 20, 강한 추세)
    adx_dynamic_threshold: int = 20      # Dynamic ATR 전환 ADX 기준
    max_holding_days: int = 20           # 최대 보유일
    max_pairs: int = 7                   # v4: 5→7 동시 보유 최대 페어 수 확대
    max_weight_per_pair: float = 0.07    # v3: 0.10→0.07 페어당 최대 비중 7% (양쪽 합산)
    trailing_activation_pct: float = 0.05  # 트레일링 활성화 5%
    correlation_decay_exit: float = 0.35 # 상관관계 하락 시 청산 (v2: 0.20→0.35)
    corr_decay_confirm_days: int = 2     # v2 신규: 상관관계 붕괴 연속 확인 일수
    pair_cooldown_days: int = 5          # v4: 10→5 쿨다운 축소 (재진입 기회 확대)
    cross_sector_pairs: bool = True      # v2 신규: 크로스섹터 페어링 허용
    # v3 신규: MDD 방어 + 수익률 개선
    arb_mdd_limit: float = 0.10          # v3: 차익거래 전용 MDD 한도 -10% (서킷브레이커)
    arb_mdd_recovery: float = 0.05       # v4 신규: DD -5% 회복 시 거래 재개
    arb_mdd_halt_max_days: int = 20      # v4 신규: MDD 차단 최대 일수 (초과 시 자동 복구)
    min_hold_days_for_tp: int = 3        # v3: Z-Score TP 최소 보유일 (즉시 청산 방지)
    warmup_buffer_days: int = 5          # v3: 첫 N거래일 진입 금지 (워밍업)
    pair_rediscovery_days: int = 3       # v4 신규: 페어 재발견 주기 (v3 하드코딩 5→설정화)
    # Layer weights (sum = 100)
    weight_correlation: int = 40         # Layer 1: 상관관계 품질
    weight_spread: int = 35              # Layer 2: 스프레드 이탈도
    weight_volume: int = 25              # Layer 3: 거래량 + EV 확인
    # v5 신규: Fixed ETF Pair Mode + Basis Gate
    use_fixed_pairs: bool = True         # v5: 고정 ETF 페어 모드 (True=고정, False=동적 발견)
    basis_gate_enabled: bool = True      # v5: 콘탱고/백워데이션 게이트 활성화
    etf_entry_threshold: int = 50        # v5: ETF 페어용 진입 임계값 (동일지수는 스코어 낮아도 OK)
    fixed_pairs: list = field(default_factory=list)    # v5: YAML에서 로드하는 고정 페어 리스트
    basis_signals: list = field(default_factory=list)  # v5: YAML에서 로드하는 basis signal 설정


@dataclass
class UniverseConfig:
    type: str = "KOSPI200"
    exclude: List[str] = field(default_factory=list)


@dataclass
class SP500FuturesConfig:
    """S&P 500 선물 매매 전략 설정."""
    # 기본 설정
    ticker: str = "ES=F"
    contract_multiplier: float = 50.0
    is_micro: bool = False

    # Z-Score 설정
    zscore_ma_period: int = 20
    zscore_std_period: int = 20
    zscore_long_threshold: float = -2.0
    zscore_short_threshold: float = 2.0

    # 추세 필터
    ma_fast: int = 10
    ma_mid: int = 20
    ma_slow: int = 50
    ma_trend: int = 200
    adx_period: int = 14
    adx_threshold: float = 25.0
    adx_strong: float = 40.0

    # MACD 설정
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9

    # RSI 설정
    rsi_period: int = 14
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0
    rsi_long_range: tuple = (40.0, 65.0)
    rsi_short_range: tuple = (35.0, 60.0)

    # 볼린저밴드
    bb_period: int = 20
    bb_std: float = 2.0
    bb_squeeze_ratio: float = 0.8

    # ATR 설정
    atr_period: int = 14
    atr_breakout_mult: float = 0.15
    atr_trend_mult: float = 1.5

    # 거래량
    volume_ma_period: int = 20
    volume_confirm_mult: float = 1.5

    # OBV
    obv_ema_fast: int = 5
    obv_ema_slow: int = 20

    # 진입 점수 임계값
    entry_threshold: float = 50.0

    # 손절 설정
    sl_atr_mult: float = 2.0
    sl_atr_mult_strong: float = 1.5
    sl_hard_pct: float = 0.03

    # 익절 설정
    tp_atr_mult: float = 3.0
    tp_rr_ratio: float = 2.0

    # 트레일링 스탑
    trailing_activation_pct: float = 0.02
    trailing_atr_mult: float = 2.0
    chandelier_atr_mult: float = 3.0

    # 최대 보유 기간
    max_holding_days: int = 20

    # 포지션 사이징 (Kelly)
    kelly_fraction: float = 0.3
    max_contracts: int = 10
    risk_per_trade_pct: float = 0.015

    # 레이어 가중치 (합계 100)
    weight_zscore: float = 25.0
    weight_trend: float = 25.0
    weight_momentum: float = 25.0
    weight_volume: float = 25.0

    # CHoCH 퇴출 확인
    choch_confirm_bars: int = 2
    choch_pnl_gate_loss: float = -0.02
    choch_pnl_gate_profit: float = 0.04

    # 페이크아웃 필터
    fakeout_min_vol_ratio: float = 0.5
    fakeout_max_wick_ratio: float = 2.0

    # 서킷브레이커
    rg1_daily_loss_limit: float = -0.03
    rg2_mdd_limit: float = -0.10

    # 거래소 서킷브레이커 (CME)
    cb_level1_pct: float = 0.07
    cb_level2_pct: float = 0.13
    cb_level3_pct: float = 0.20
    cb_overnight_limit: float = 0.07
    exchange_cb_enabled: bool = True

    # 증거금
    es_initial_margin: float = 15500.0
    es_maintenance_margin: float = 13700.0
    mes_initial_margin: float = 1550.0
    mes_maintenance_margin: float = 1370.0
    margin_call_enabled: bool = True

    # 롤오버
    roll_cost_per_contract: float = 12.50
    roll_warning_days: int = 5

    # 거래비용
    futures_slippage_per_contract: float = 12.50
    futures_commission_per_contract: float = 4.62
    es_exchange_fee: float = 1.40
    es_broker_fee: float = 0.85
    es_nfa_fee: float = 0.02
    mes_exchange_fee: float = 0.35
    mes_broker_fee: float = 0.25
    mes_nfa_fee: float = 0.02

    # 4-Layer 스코어링 임계값
    zscore_tier1: float = 3.0
    zscore_tier2: float = 2.0
    zscore_tier3: float = 1.5
    zscore_tier4: float = 1.0
    zscore_tier1_pct: float = 1.0
    zscore_tier2_pct: float = 0.8
    zscore_tier3_pct: float = 0.5
    zscore_tier4_pct: float = 0.3
    zscore_block_threshold: float = 2.0
    zscore_trend_cont_max_pct: float = 0.6
    zscore_trend_cont_min_pct: float = 0.2

    # Layer 2: 추세/구조 가중 비율
    trend_ema_full_pct: float = 0.4
    trend_ema_partial_pct: float = 0.2
    trend_ma200_pos_pct: float = 0.3
    trend_ma200_slope_pct: float = 0.3
    trend_slope_lookback: int = 5

    # Layer 3: 모멘텀 가중 비율
    momentum_macd_cross_pct: float = 0.3
    momentum_macd_hist_pct: float = 0.2
    momentum_adx_trend_pct: float = 0.3
    momentum_adx_bonus_pct: float = 0.1
    momentum_rsi_ok_pct: float = 0.2
    momentum_rsi_extreme_pct: float = 0.15

    # Layer 4: 거래량/OBV 가중 비율
    volume_surge_pct: float = 0.35
    volume_above_avg_pct: float = 0.15
    volume_above_avg_ratio: float = 1.2
    volume_obv_pct: float = 0.35
    volume_squeeze_pct: float = 0.3

    # Progressive Trailing
    trailing_tier1_pnl: float = 0.15
    trailing_tier1_atr: float = 1.5
    trailing_tier1_floor: float = -0.08
    trailing_tier2_pnl: float = 0.10
    trailing_tier2_atr: float = 2.0
    trailing_tier2_floor: float = -0.06
    trailing_tier3_pnl: float = 0.07
    trailing_tier3_atr: float = 2.5
    trailing_tier3_floor: float = -0.05
    trailing_default_atr: float = 3.0
    trailing_default_floor: float = -0.04

    # 포지션 사이징
    sizing_base_mult: float = 0.4
    sizing_max_mult: float = 1.25
    sizing_score_base: float = 60.0
    sizing_score_range: float = 40.0

    # ATR 폴백
    atr_fallback_pct: float = 0.01
    doji_body_threshold: float = 0.001

    # Market Regime
    regime_bull_entry_threshold: float = 50.0
    regime_bear_entry_threshold: float = 65.0
    regime_bull_max_holding: int = 25
    regime_bear_max_holding: int = 12
    regime_bear_sl_pct: float = 0.03
    regime_counter_bias_penalty: float = 5.0

    # EV Engine + Dynamic Kelly
    ev_lookback: int = 30
    ev_min_trades: int = 5
    kelly_min_trades: int = 10
    kelly_half_mult: float = 0.5
    kelly_max_fraction: float = 0.5

    # 연속 손절 정지
    max_consecutive_losses: int = 3


@dataclass
class ESFIntradayConfig:
    """ES-F 인트라데이 데이트레이딩 전략 설정."""
    ticker: str = "ES=F"
    contract_multiplier: float = 50.0
    is_micro: bool = True

    # 타임프레임
    primary_interval: str = "15m"
    bias_interval: str = "1h"
    rth_start: str = "09:30"
    rth_end: str = "16:00"
    eod_close_minutes_before: int = 15

    # 지표 기간
    ema_fast: int = 8
    ema_mid: int = 21
    ema_slow: int = 55
    rsi_period: int = 14
    atr_period: int = 20
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    zscore_window: int = 40
    bb_period: int = 20
    bb_std: float = 2.0
    adx_period: int = 14
    adx_threshold: float = 25.0
    volume_ma_period: int = 20

    # Volume Profile
    vp_session_bars: int = 26
    vp_lookback_sessions: int = 3
    vp_value_area_pct: float = 0.70

    # 4-Layer 스코어링 가중치
    weight_amt_location: float = 30.0
    weight_zscore: float = 20.0
    weight_momentum: float = 25.0
    weight_volume_aggression: float = 25.0

    # Grade 임계값
    grade_a_threshold: float = 50.0
    grade_b_threshold: float = 40.0
    grade_c_threshold: float = 35.0

    # AMT 파라미터
    amt_balance_ratio: float = 0.70
    amt_aggression_body_ratio: float = 0.65
    amt_aggression_vol_mult: float = 1.5
    amt_consecutive_bars: int = 3

    # 청산
    sl_hard_pct: float = 0.015
    sl_atr_mult: float = 1.5
    tp_atr_mult: float = 2.0
    trailing_activation_pct: float = 0.008
    trailing_atr_mult: float = 1.0

    # 리스크 관리
    max_daily_trades: int = 5
    max_daily_loss_dollars: float = 500.0
    max_consecutive_losses: int = 3
    risk_per_trade_pct: float = 0.01
    max_contracts: int = 5
    kelly_fraction: float = 0.3

    # 거래 비용 (MES)
    slippage_ticks: int = 1
    commission_per_contract: float = 0.62

    # 증거금 (MES)
    initial_margin: float = 1550.0
    maintenance_margin: float = 1370.0

    # RSI 범위
    rsi_long_range_min: float = 40.0
    rsi_long_range_max: float = 70.0
    rsi_short_range_min: float = 30.0
    rsi_short_range_max: float = 60.0

    # Phase C: Regime-aware scoring
    ma_alignment_bonus: float = 5.0          # MA alignment bonus (re-enabled: full alignment +5, partial +2.5)
    ma_counter_penalty: float = 0.0         # MA counter-trend penalty (keep disabled — EMA veto handles this)
    regime_bull_threshold: float = 50.0     # Grade A threshold (lowered from 55 — realistic max ~49+bonus)
    regime_neutral_threshold: float = 50.0  # Grade A threshold in NEUTRAL
    regime_bear_threshold: float = 50.0     # Grade A threshold in BEAR
    atr_expand_ratio: float = 99.0           # ATR expanding threshold (disabled — set extreme)
    atr_contract_ratio: float = 0.01        # ATR contracting threshold (disabled — set extreme)
    atr_expand_sl_mult: float = 1.0         # SL/TP multiplier when expanding (1.0 = no change)
    atr_contract_sl_mult: float = 1.0       # SL/TP multiplier when contracting (1.0 = no change)

    # Phase E: Time-of-day filter & strategy refinement
    entry_window_optimal: str = "09:30-12:59"                  # Morning session (best WR)
    entry_window_avoid: str = "12:00-12:59,14:00-15:30"        # Lunch lull + late session (100% loss)
    use_time_filter: bool = True                              # Enabled — 14시 진입 WR=0% 확인
    long_penalty_neutral: float = 0.0       # Disabled — Phase D showed degradation

    # VWATR S/R Zones
    vwatr_period: int = 20            # VWATR rolling window
    vwatr_zone_mult: float = 0.5     # Zone width = VWATR * mult
    vwatr_ma_periods: str = "9,20,50" # S/R 존 구성할 MA 기간들
    vwatr_strength_min: float = 30.0  # 최소 존 강도
    vwatr_touch_lookback: int = 50    # Touch-Reaction 분석 lookback
    vwatr_max_score: float = 8.0     # L1 서브스코어 최대
    vwatr_enabled: bool = True        # Feature flag (A/B 테스트용)


@dataclass
class BenchmarkTuningConfig:
    """P4: SPY/QQQ benchmark tuning — RG6 gate settings."""
    spy_ma200_gate: bool = True       # Enable RG6: block long strategies when index < MA200
    spy_ma200_period: int = 200       # MA period for SPY gate
    qqq_rsi_threshold: float = 45.0   # QQQ RSI threshold for bearish filter


@dataclass
class ATSConfig:
    """ATS 전체 설정 (config.yaml 매핑)."""
    system_name: str = "ATS-MomentumSwing"
    system_version: str = "1.0.0"
    log_level: str = "INFO"

    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    universe: UniverseConfig = field(default_factory=UniverseConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    smc_strategy: SMCStrategyConfig = field(default_factory=SMCStrategyConfig)
    breakout_retest: BreakoutRetestConfig = field(default_factory=BreakoutRetestConfig)
    mean_reversion: MeanReversionConfig = field(default_factory=MeanReversionConfig)
    arbitrage: ArbitrageConfig = field(default_factory=ArbitrageConfig)
    benchmark_tuning: BenchmarkTuningConfig = field(default_factory=BenchmarkTuningConfig)
    sp500_futures: SP500FuturesConfig = field(default_factory=SP500FuturesConfig)
    esf_intraday: ESFIntradayConfig = field(default_factory=ESFIntradayConfig)
    exit: ExitConfig = field(default_factory=ExitConfig)
    portfolio: PortfolioConfig = field(default_factory=PortfolioConfig)
    portfolio_allocation: PortfolioAllocationConfig = field(default_factory=PortfolioAllocationConfig)
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

        # SMC Strategy
        smc = yaml_data.get("smc_strategy", {})
        if smc:
            config.smc_strategy = SMCStrategyConfig(**{
                k: smc[k] for k in SMCStrategyConfig.__dataclass_fields__ if k in smc
            })

        # Breakout-Retest Strategy
        brt = yaml_data.get("breakout_retest", {})
        if brt:
            config.breakout_retest = BreakoutRetestConfig(**{
                k: brt[k] for k in BreakoutRetestConfig.__dataclass_fields__ if k in brt
            })

        # Mean Reversion Strategy
        mr = yaml_data.get("mean_reversion", {})
        if mr:
            config.mean_reversion = MeanReversionConfig(**{
                k: mr[k] for k in MeanReversionConfig.__dataclass_fields__ if k in mr
            })

        # Arbitrage Strategy (v5: Fixed ETF Pairs + Basis Gate)
        arb = yaml_data.get("arbitrage", {})
        if arb:
            # fixed_pairs, basis_signals는 List[Dict]이므로 일반 필드와 분리
            list_fields = {"fixed_pairs", "basis_signals"}
            scalar_fields = {
                k: arb[k] for k in ArbitrageConfig.__dataclass_fields__
                if k in arb and k not in list_fields
            }
            config.arbitrage = ArbitrageConfig(**scalar_fields)
            config.arbitrage.fixed_pairs = arb.get("fixed_pairs", [])
            config.arbitrage.basis_signals = arb.get("basis_signals", [])

        # SP500 Futures Strategy
        sp500f = yaml_data.get("sp500_futures", {})
        if sp500f:
            # tuple 필드는 별도 처리
            scalar = {
                k: sp500f[k] for k in SP500FuturesConfig.__dataclass_fields__
                if k in sp500f and k not in ("rsi_long_range", "rsi_short_range")
            }
            config.sp500_futures = SP500FuturesConfig(**scalar)
            if "rsi_long_range" in sp500f:
                config.sp500_futures.rsi_long_range = tuple(sp500f["rsi_long_range"])
            if "rsi_short_range" in sp500f:
                config.sp500_futures.rsi_short_range = tuple(sp500f["rsi_short_range"])

        # ESF Intraday Strategy
        esf = yaml_data.get("esf_intraday", {})
        if esf:
            config.esf_intraday = ESFIntradayConfig(**{
                k: esf[k] for k in ESFIntradayConfig.__dataclass_fields__ if k in esf
            })

        # P4: Benchmark Tuning (SPY MA200 gate / QQQ RSI filter)
        bt = yaml_data.get("benchmark_tuning", {})
        if bt:
            config.benchmark_tuning = BenchmarkTuningConfig(**{
                k: bt[k] for k in BenchmarkTuningConfig.__dataclass_fields__ if k in bt
            })

        # Portfolio Allocation (Tactical 전용)
        pa = yaml_data.get("portfolio_allocation", {})
        if pa:
            tactical_data = pa.get("tactical", {})
            config.portfolio_allocation = PortfolioAllocationConfig(
                enabled=pa.get("enabled", False),
                kelly_fraction=pa.get("kelly_fraction", 0.30),
                tactical=TierConfig(**{
                    k: tactical_data[k] for k in TierConfig.__dataclass_fields__ if k in tactical_data
                }),
            )

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
