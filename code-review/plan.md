1. Context (배경)
1.1 요구사항
S&P 500 선물지수(E-mini ES / Micro MES) 계약 매매를 위한:

신호 포착 알고리즘: 4-Layer 스코어링 기반 양방향(롱/숏) 진입 시그널
진입 시그널: Z-Score 통계적 위치 + 추세/구조 + 모멘텀 + 거래량 확인
청산 시그널: 7단계 우선순위 기반 다단 청산 (익절/손절/트레일링/구조반전)

1.2 설계 원칙

기존 ATS 3-Layer 모놀리스 아키텍처 준수 (Orchestrator → Domain → Infrastructure)
BaseStrategy 추상 인터페이스 구현 (calculate_indicators / scan_entry_signals / scan_exit_signals)
모든 전략 파라미터는 config.yaml로 외부화
선물 특화: 타이트한 손절(-3%), 양방향(Long/Short), ADX 기반 동적 ATR 배수, Kelly Criterion 포지션 사이징

1.3 참조 이론

stock_theory/futuresStrategy.md: Z-Score 확률 엔진, EV(기대값) 필터, Kelly Criterion
stock_theory/future_trading_stratedy.md: ATR 돌파 필터, 동적 ATR 배수, 샹들리에 청산
CLAUDE.md §Strategy 2: SMC 4-Layer Scoring (아키텍처 참조)
CLAUDE.md §MDD Defence: 7-Layer 방어 아키텍처


2. 현재 구현 상태 (Phase 1 완료)
2.1 생성된 파일 목록
파일라인 수용도상태ats/strategy/sp500_futures.py1,130핵심 전략 (진입+청산+사이징)✅ 완료ats/strategy/base.py42전략 추상 인터페이스✅ 완료ats/common/enums.py56열거형 (ExitReason, FuturesDirection 등)✅ 완료ats/common/types.py90데이터클래스 (Signal, FuturesSignal, ExitSignal, PriceData)✅ 완료ats/common/exceptions.py21공통 예외 (ATSError, StateTransitionError 등)✅ 완료ats/data/config_manager.py240설정 데이터클래스 (SP500FuturesConfig 포함)✅ 완료ats/infra/logger.py19로깅 유틸리티✅ 완료ats/tests/test_sp500_futures.py459단위 테스트 (20건)✅ 완료config.yaml (sp500_futures 섹션)80줄 추가전략 파라미터✅ 완료
2.2 테스트 결과
✅ 20 passed / ❌ 0 failed / 총 20건
2.3 커밋/푸시 상태

브랜치: claude/sp500-trading-signals-zcZue
커밋: e15b8ad — "feat: S&P 500 선물지수 매매 신호 포착 알고리즘 구현"
푸시: ✅ 완료


3. 아키텍처 설계
3.1 전체 데이터 흐름
yfinance ("ES=F" OHLCV 일봉)
    ↓
SP500FuturesStrategy.calculate_indicators(df)
    → 24개 기술 지표 추가 (EMA×4, MACD×3, RSI, BB×5, ATR×2, ADX/DMI×3, Z-Score, Volume×2, OBV×3)
    ↓
_determine_direction(df) → LONG / SHORT / NEUTRAL
    ↓
4-Layer 스코어링 (L1 Z-Score + L2 추세 + L3 모멘텀 + L4 거래량 = 총점/100)
    ↓
필터: _check_atr_breakout() + _check_fakeout_filter()
    ↓
총점 ≥ 60 → Signal 생성 (or FuturesSignal for API)
    ↓
RiskManager.check_risk_gates(signal, portfolio) → RG1~RG4
    ↓
_calculate_position_size(equity, entry, SL) → Kelly 기반 계약 수
    ↓
OrderExecutor → Broker 주문
    ↓
포지션 모니터링 → scan_exit_signals() → 7단계 청산 cascade
3.2 클래스 다이어그램
BaseStrategy (ABC)
    ├── calculate_indicators(df) → pd.DataFrame
    ├── scan_entry_signals(codes, ohlcv, prices) → List[Signal]
    └── scan_exit_signals(positions, ohlcv, prices) → List[ExitSignal]
         │
         ▼
SP500FuturesStrategy(BaseStrategy)
    ├── config: ATSConfig
    ├── fc: SP500FuturesConfig (43개 파라미터)
    ├── _position_states: Dict[str, FuturesPositionState]
    │
    ├── [지표 계산]
    │   └── calculate_indicators(df) — 24개 지표 추가
    │       └── _calc_adx_dmi(high, low, close, period) — ADX/+DI/-DI
    │
    ├── [진입 시그널]
    │   ├── scan_entry_signals(codes, ohlcv, prices) — 유니버스 스캔
    │   ├── _evaluate_entry(code, df, prices) — 단일 종목 평가
    │   ├── generate_futures_signal(code, df, price, equity) — 상세 FuturesSignal
    │   ├── _determine_direction(df) → LONG/SHORT/NEUTRAL
    │   ├── _score_zscore(df, is_long) → (score, signals)
    │   ├── _score_trend(df, is_long) → (score, signals)
    │   ├── _score_momentum(df, is_long) → (score, signals)
    │   ├── _score_volume(df, is_long) → (score, signals)
    │   ├── _check_atr_breakout(df, is_long) → bool
    │   └── _check_fakeout_filter(df, is_long) → bool
    │
    ├── [청산 시그널]
    │   ├── scan_exit_signals(positions, ohlcv, prices)
    │   ├── _check_hard_stop(pos, price, pnl, is_long) — ES1 -3%
    │   ├── _check_atr_stop_loss(pos, price, entry, atr, adx, pnl, is_long) — ES_ATR_SL
    │   ├── _check_atr_take_profit(pos, price, entry, atr, pnl, is_long) — ES_ATR_TP
    │   ├── _check_chandelier_exit(pos, price, atr, pnl, is_long, state) — ES_CHANDELIER
    │   ├── _check_trailing_stop(pos, price, entry, atr, pnl, is_long, state) — ES3
    │   ├── _check_structure_reversal(pos, df, pnl, is_long) — ES_CHOCH
    │   └── _check_max_holding(pos, price, pnl) — ES5
    │
    ├── [포지션 사이징]
    │   ├── _calculate_sl_tp(entry, atr, is_long, adx) → (sl, tp)
    │   └── _calculate_position_size(equity, entry, sl) → contracts
    │
    └── [유틸리티]
        ├── _get_position_state(code) → FuturesPositionState
        └── clear_position_state(code)
3.3 설정 구조 (SP500FuturesConfig)
ATSConfig
  └── sp500_futures: SP500FuturesConfig (43개 파라미터)
       ├── 기본: ticker, contract_multiplier, is_micro
       ├── Z-Score: zscore_ma/std_period, long/short_threshold
       ├── 추세: ma_fast/mid/slow/trend, adx_period/threshold/strong
       ├── MACD: macd_fast/slow/signal
       ├── RSI: rsi_period, oversold/overbought, long/short_range
       ├── BB: bb_period/std, bb_squeeze_ratio
       ├── ATR: atr_period, breakout/trend_mult
       ├── 거래량: volume_ma_period, volume_confirm_mult
       ├── OBV: obv_ema_fast/slow
       ├── 진입: entry_threshold
       ├── 손절: sl_atr_mult, sl_atr_mult_strong, sl_hard_pct
       ├── 익절: tp_atr_mult, tp_rr_ratio
       ├── 트레일링: trailing_activation_pct, trailing_atr_mult, chandelier_atr_mult
       ├── 보유: max_holding_days
       ├── 사이징: kelly_fraction, max_contracts, risk_per_trade_pct
       └── 가중치: weight_zscore/trend/momentum/volume (각 25, 합 100)

4. 진입 시그널 상세 설계
4.1 방향 결정 알고리즘 (_determine_direction)
7개 지표를 종합하여 롱/숏/중립 방향을 결정한다:
long_score / short_score 시스템:

(1) MA200 위치: close > MA200 → long +2 / close < MA200 → short +2
(2) EMA 정렬: fast > mid > slow → long +2 / fast < mid < slow → short +2
(3) MACD 방향: hist > 0 → long +1 / hist < 0 → short +1
(4) Z-Score 극단: Z ≤ -2 → long +2 / Z ≥ +2 → short +2

결정: score ≥ 3 AND score > 반대 → 해당 방향
      그 외 → NEUTRAL (진입 안함)

최대 가능 점수: 7 (MA200 2 + EMA 2 + MACD 1 + Z-Score 2)
4.2 4-Layer 스코어링
Layer 1 — Z-Score 통계적 위치 (max 25점)
Z = (Close - MA20) / StdDev20

롱 진입:
  Z ≤ -3.0 → 25.0점 (극단 과매도) + "Z_EXTREME_OVERSOLD"
  Z ≤ -2.0 → 20.0점 (과매도)       + "Z_OVERSOLD"
  Z ≤ -1.5 → 12.5점 (약한 과매도)  + "Z_MILD_OVERSOLD"
  Z ≤ -1.0 →  7.5점 (평균 이하)    + "Z_BELOW_MEAN"
  Z ≥ +2.0 →  0점   (과매수 → 롱 차단)

숏 진입: (반대 방향 동일 로직)
Layer 2 — 추세/구조 (max 25점)
롱 진입:
  EMA 정배열 (fast > mid > slow) → +10점 "EMA_BULL_ALIGNED"
    또는 부분 (fast > mid)       → +5점  "EMA_PARTIAL_BULL"
  Close > MA200                   → +7.5점 "ABOVE_MA200"
  MA200 기울기 상승 (5일 비교)    → +7.5점 "MA200_RISING"

숏 진입: (역배열 동일 로직)
Layer 3 — 모멘텀 (max 25점)
롱 진입:
  MACD 골든크로스 (hist: 음→양)        → +7.5점 "MACD_BULL_CROSS"
    또는 히스토그램 상승 (hist>0, 증가) → +5.0점 "MACD_HIST_RISING"
  ADX > 25 AND +DI > -DI               → +7.5점 "ADX_BULL_TREND"
    ADX > 40                           → +2.5점 보너스 "ADX_STRONG"
  RSI 40-65 범위                       → +5.0점 "RSI_LONG_OK"
    또는 RSI < 30 (과매도 반등)        → +3.75점 "RSI_OVERSOLD_BOUNCE"

숏 진입: (데드크로스, -DI > +DI, RSI 35-60 동일 로직)
Layer 4 — 거래량/OBV (max 25점)
거래량 비율 ≥ 1.5 (MA20 대비) → +8.75점 "VOL_SURGE"
  또는 ≥ 1.2                 → +3.75점 "VOL_ABOVE_AVG"

롱: OBV EMA5 > OBV EMA20    → +8.75점 "OBV_BULL"
숏: OBV EMA5 < OBV EMA20    → +8.75점 "OBV_BEAR"

BB Squeeze Ratio < 0.8      → +7.5점  "BB_SQUEEZE"
진입 임계값
총점 = L1 + L2 + L3 + L4 (0~100)
총점 ≥ 60 → 진입 후보

+ ATR 돌파 필터: (High - PrevClose) > 0.5 × ATR (롱)
+ 페이크아웃 필터:
  - volume_ratio < 0.8 → 차단
  - upper_wick / body > 1.5 → 차단 (롱)
  - lower_wick / body > 1.5 → 차단 (숏)
4.3 시그널 데이터 구조
python# 기본 시그널 (BaseStrategy 호환)
Signal(
    stock_code="ES=F",
    stock_name="E-mini S&P 500",
    signal_type="BUY" | "SELL",  # 롱/숏
    primary_signals=["Z_OVERSOLD", "EMA_BULL_ALIGNED", ...],
    confirmation_filters=["MACD_BULL_CROSS", "VOL_SURGE", ...],
    current_price=5500.0,
    bb_upper=5600.0,
)

# 상세 선물 시그널 (API/시뮬레이션용)
FuturesSignal(
    ticker="ES=F",
    direction="LONG" | "SHORT",
    signal_strength=75,  # 총점
    entry_price=5500.0,
    stop_loss=5455.0,
    take_profit=5590.0,
    atr=30.0,
    z_score=-2.3,
    risk_reward_ratio=2.0,
    position_size_contracts=2,
    metadata={
        "l1_zscore": 20.0, "l2_trend": 25.0,
        "l3_momentum": 17.5, "l4_volume": 12.5,
        "adx": 32.0, "rsi": 45.0, ...
    },
)
```

---

## 5. 청산 시그널 상세 설계

### 5.1 7단계 우선순위 Cascade

청산 체크는 **우선순위순**으로 실행되며, 첫 번째 트리거된 조건에서 즉시 청산한다:

| 순위 | ID | 조건 | 주문유형 | 설명 |
|------|-----|------|---------|------|
| 1 | **ES1** | pnl ≤ -3% | MARKET | 하드 손절 (절대 한도, 선물 특화) |
| 2 | **ES_ATR_SL** | price ≤ entry - ATR × mult | MARKET | ATR 동적 손절 (ADX 기반 배수) |
| 3 | **ES_ATR_TP** | price ≥ entry + ATR × 3.0 | MARKET | ATR 익절 (R:R ≥ 2:1) |
| 4 | **ES_CHANDELIER** | price ≤ highest - 3×ATR | MARKET | 샹들리에 청산 (수익 보호) |
| 5 | **ES3** | trail_stop 이탈 | MARKET | 프로그레시브 트레일링 |
| 6 | **ES_CHOCH** | MACD 히스토그램 반전 | LIMIT | 구조 반전 (롱: 양→음, 숏: 음→양) |
| 7 | **ES5** | holding_days > 20 | LIMIT | 최대 보유기간 초과 |

### 5.2 동적 SL/TP 계산
```
ADX 기반 ATR 배수:
  ADX ≥ 25 (추세) → sl_mult = 1.5 (타이트)
  ADX < 25 (횡보) → sl_mult = 2.0 (느슨)

롱 SL:
  sl_atr = entry - ATR × sl_mult
  sl_hard = entry × (1 - 0.03)  # -3%
  SL = max(sl_atr, sl_hard)     # 더 가까운 것 (보수적)

롱 TP:
  TP = entry + ATR × 3.0

숏: 반대 방향 동일
```

### 5.3 프로그레시브 트레일링 (ES3)
```
활성화: pnl_pct ≥ 2% (trailing_activation_pct)

기본 trail_mult = 2.0 × ATR

PnL 구간별 타이트닝:
  pnl ≥ +6% → trail_mult = max(1.0, 2.0 - 0.5) = 1.5
  pnl ≥ +4% → trail_mult = max(1.2, 2.0 - 0.3) = 1.7
  pnl < +4% → trail_mult = 2.0 (기본)

롱 trail_stop = highest_since_entry - trail_mult × ATR
숏 trail_stop = lowest_since_entry + trail_mult × ATR
```

### 5.4 샹들리에 청산 (ES_CHANDELIER)
```
조건: 가격이 진입가 대비 수익 구간에 있을 때만 활성화

롱: chandelier_stop = highest_since_entry - 3.0 × ATR
     트리거: price ≤ chandelier_stop AND highest > entry

숏: chandelier_stop = lowest_since_entry + 3.0 × ATR
     트리거: price ≥ chandelier_stop AND lowest < entry
5.5 FuturesPositionState
python@dataclass
class FuturesPositionState:
    direction: str = "NEUTRAL"
    entry_price: float = 0.0
    highest_since_entry: float = 0.0
    lowest_since_entry: float = inf
    trailing_active: bool = False
    bars_held: int = 0
```
- 포지션별 내부 상태 추적 (`_position_states` 딕셔너리)
- `scan_exit_signals()` 호출 시 자동 업데이트
- `clear_position_state(code)` 로 청산 후 정리

---

## 6. 포지션 사이징

### 6.1 Kelly Criterion 기반
```
contracts = (Equity × risk_per_trade_pct) / (point_risk × multiplier)

여기서:
  risk_per_trade_pct = 0.015 (1.5%)
  point_risk = |entry_price - stop_loss|
  multiplier = 50.0 (E-mini) 또는 5.0 (Micro)

예시:
  Equity = $100,000
  Entry = 5,500, SL = 5,455 → point_risk = 45pt
  Risk amount = 100,000 × 0.015 = $1,500
  Dollar risk/contract = 45 × 50 = $2,250
  Contracts = 1,500 / 2,250 ≈ 0.67 → 1계약

제한: max(1, min(contracts, max_contracts=10))
6.2 E-mini vs Micro 자동 전환
pythonmultiplier = 5.0 if self.fc.is_micro else self.fc.contract_multiplier  # 50.0

7. 기술 지표 명세
7.1 calculate_indicators()가 추가하는 24개 컬럼
카테고리컬럼명계산용도EMAema_fastEMA(10)단기 추세EMAema_midEMA(20)중기 추세EMAema_slowEMA(50)장기 추세MAma_trendSMA(200)추세 방향MACDmacd_lineEMA(12) - EMA(26)모멘텀MACDmacd_signalEMA(9) of macd_line시그널MACDmacd_histmacd_line - macd_signal크로스 감지RSIrsiEWM RSI(14)과매수/과매도BBbb_upperSMA(20) + 2σ상단밴드BBbb_lowerSMA(20) - 2σ하단밴드BBbb_middleSMA(20)중심선BBbb_widthupper - lower변동성 폭BBbb_squeeze_ratiowidth / width_MA스퀴즈 감지ATRatrEMA(14) of TR변동성 측정ATRatr_pctatr / close × 100% 변동성ADXadxDX의 EWM(14)추세 강도DMIplus_di+DM 비율상승 방향DMIminus_di-DM 비율하락 방향Zzscore(close - MA20) / σ20통계적 위치Volvolume_maSMA(20) of volume평균 거래량Volvolume_ratiovolume / volume_ma거래량 비율OBVobv누적 OBV매집/분산OBVobv_ema_fastEMA(5) of OBVOBV 단기OBVobv_ema_slowEMA(20) of OBVOBV 장기
7.2 최소 데이터 요구량
pythonmin_len = max(ma_trend=200, macd_slow+macd_signal=35) + 5 = 205 봉

8. 테스트 명세
8.1 20건 단위 테스트 (TC-FUT-001 ~ TC-FUT-020)
ID카테고리테스트명검증 내용TC-FUT-001지표기술 지표 컬럼 생성24개 컬럼 존재 확인TC-FUT-002지표Z-Score 범위-10 < Z < 10TC-FUT-003스코어4-Layer 스코어 범위각 0~25, 합 0~100TC-FUT-004방향상승추세 → LONGbull OHLCV → FuturesDirection.LONGTC-FUT-005방향하락추세 → SHORTbear OHLCV → FuturesDirection.SHORTTC-FUT-006방향횡보장 방향 결정flat OHLCV → NEUTRAL or weakTC-FUT-007필터ATR 돌파 유효강한 돌파 → TrueTC-FUT-008필터페이크아웃 저거래량vol_ratio < 0.8 → FalseTC-FUT-009SL/TP롱 SL/TP 계산ADX=30 → SL=5455, TP=5590TC-FUT-010SL/TP숏 SL/TP 계산ADX=30 → SL=5545, TP=5410TC-FUT-011청산ES1 하드 손절-3.45% → ES1 MARKETTC-FUT-012청산ES_ATR_SL 동적 손절_check_atr_stop_loss 직접 검증TC-FUT-013청산ES_ATR_TP 익절_check_atr_take_profit 직접 검증TC-FUT-014청산ES_CHANDELIER 샹들리에_check_chandelier_exit 직접 검증TC-FUT-015청산ES3 트레일링 스탑_check_trailing_stop 직접 검증TC-FUT-016청산ES_CHOCH MACD 반전_check_structure_reversal 직접 검증TC-FUT-017청산ES5 최대 보유기간25일 > 20일 → ES5TC-FUT-018사이징포지션 사이징≥ 1계약, ≤ max_contractsTC-FUT-019시그널FuturesSignal 생성generate_futures_signal 검증TC-FUT-020상태HOLD (청산 없음)조건 미충족 → exits=[]
8.2 실행 방법
bash# SP500 선물 테스트만
PYTHONPATH=/home/user/atm-dev/ats python3 ats/tests/test_sp500_futures.py

# 전체 테스트 (run_tests.py에 통합 시)
python3 run_tests.py

9. config.yaml 설정 명세
yamlsp500_futures:
  # ─── 기본 ───
  ticker: "ES=F"                     # E-mini S&P 500
  contract_multiplier: 50.0          # $50/pt
  is_micro: false                    # Micro 전환 시 $5/pt

  # ─── Z-Score ───
  zscore_ma_period: 20               # Z-Score MA
  zscore_std_period: 20              # Z-Score σ
  zscore_long_threshold: -2.0        # 롱 진입 (과매도)
  zscore_short_threshold: 2.0        # 숏 진입 (과매수)

  # ─── 추세 필터 ───
  ma_fast: 10                        # EMA 단기
  ma_mid: 20                         # EMA 중기
  ma_slow: 50                        # EMA 장기
  ma_trend: 200                      # 추세 MA
  adx_period: 14
  adx_threshold: 25.0                # 추세 최소 강도
  adx_strong: 40.0                   # 강한 추세

  # ─── MACD ───
  macd_fast: 12
  macd_slow: 26
  macd_signal: 9

  # ─── RSI ───
  rsi_period: 14
  rsi_oversold: 30.0
  rsi_overbought: 70.0

  # ─── 볼린저밴드 ───
  bb_period: 20
  bb_std: 2.0
  bb_squeeze_ratio: 0.8

  # ─── ATR ───
  atr_period: 14
  atr_breakout_mult: 0.5             # 돌파 필터
  atr_trend_mult: 1.5                # 추세 진입 필터

  # ─── 거래량 ───
  volume_ma_period: 20
  volume_confirm_mult: 1.5

  # ─── OBV ───
  obv_ema_fast: 5
  obv_ema_slow: 20

  # ─── 진입 ───
  entry_threshold: 60.0              # 최소 점수 (0-100)

  # ─── 손절 ───
  sl_atr_mult: 2.0                   # ADX < 25
  sl_atr_mult_strong: 1.5            # ADX ≥ 25 (타이트)
  sl_hard_pct: 0.03                  # 하드 -3%

  # ─── 익절 ───
  tp_atr_mult: 3.0                   # 3×ATR
  tp_rr_ratio: 2.0                   # R:R ≥ 2:1

  # ─── 트레일링 ───
  trailing_activation_pct: 0.02      # +2%에서 활성화
  trailing_atr_mult: 2.0             # 트레일링 배수
  chandelier_atr_mult: 3.0           # 샹들리에 배수

  # ─── 보유 ───
  max_holding_days: 20

  # ─── 사이징 ───
  kelly_fraction: 0.3                # Half-Kelly
  max_contracts: 10
  risk_per_trade_pct: 0.015          # 1.5%/trade

  # ─── 가중치 ───
  weight_zscore: 25.0
  weight_trend: 25.0
  weight_momentum: 25.0
  weight_volume: 25.0
```

---

## 10. MDD 방어 적용 (선물 특화)

| Layer | 주식 기준 | 선물 적용 | 비고 |
|-------|----------|----------|------|
| L1 레짐 | MA200 Breadth | MA200 위/아래 + EMA 정렬 | 방향 결정에 반영 |
| L2 트렌드 | Phase 1-2 필터 | L2 추세 스코어 (25점) | ~80% 저품질 필터링 |
| L3 시그널 | Phase 3 | L3+L4 모멘텀+거래량 (50점) | 확인 시그널 |
| L4 리스크 | RG1-RG4 | 하드 손절 -3% + ATR 동적 SL | 타이트 (레버리지) |
| L5 사이징 | 1% ATR | 1.5% Kelly, 최대 10계약 | 선물 적정 사이징 |
| L6 청산 | ES1-ES5 | 7단계 (ES1→ES_ATR_SL→ES_ATR_TP→ES_CHANDELIER→ES3→ES_CHOCH→ES5) | 확장된 cascade |
| L7 트레일링 | Progressive | PnL 구간별 타이트닝 + 샹들리에 | 수익 보호 강화 |

---

## 11. 주요 파일 경로 참조

| 파일 | 라인 수 | 역할 |
|------|---------|------|
| `ats/strategy/sp500_futures.py` | 1,130 | **핵심**: 4-Layer 진입 + 7단계 청산 + Kelly 사이징 |
| `ats/strategy/base.py` | 42 | 전략 추상 인터페이스 (3개 abstract method) |
| `ats/common/enums.py` | 56 | ExitReason(9), FuturesDirection(3), SystemState(6) 등 |
| `ats/common/types.py` | 90 | Signal, FuturesSignal, ExitSignal, PriceData, Portfolio, RiskCheckResult |
| `ats/common/exceptions.py` | 21 | ATSError, StateTransitionError, ConfigError, BrokerError |
| `ats/data/config_manager.py` | 240 | SP500FuturesConfig(43 params) + ATSConfig + ConfigManager |
| `ats/infra/logger.py` | 19 | setup_logger() + get_logger() |
| `ats/tests/test_sp500_futures.py` | 459 | 20건 단위 테스트 |
| `config.yaml` (L266-345) | 80 | sp500_futures 섹션 |

---

## 12. 코드리뷰 & 이론-구현 Gap 분석 (2026-03-14)

### 12.1 코드리뷰 종합 (17건 이슈)

**전체 점수: B+ (83/100)**

| 영역 | 점수 | 비고 |
|------|------|------|
| 프론트엔드 코드 품질 | 8.5/10 | SSE/폴링 패턴 우수, 경미한 중복 |
| TypeScript 타입 안전 | 10/10 | `any` 남용 없음 |
| Hook 품질 | 9.5/10 | cleanup/AbortController 완비 |
| 테스트 커버리지 | 5.5/10 | 인프라 레이어 미테스트 |
| 설정 완전성 | 3/10 | YAML 로딩이 sp500_futures만 작동 |

#### CRITICAL (즉시 수정 필요: 2건)

| # | 파일 | 이슈 | 영향 |
|---|------|------|------|
| C1 | `main.py:28-42` | 존재하지 않는 모듈 import (core/main_loop, infra/broker 등) | 시스템 시작 불가 (ModuleNotFoundError) |
| C2 | `data/config_manager.py:228-239` | FileNotFoundError 무시 + YAML 미검증 | 설정 오류 감지 불가, 기본값으로 무경고 동작 |

#### MAJOR (백테스트/프로덕션 전 수정: 6건)

| # | 파일 | 이슈 | 영향 |
|---|------|------|------|
| M1 | `sp500_futures.py:745-754` | SL 계산 max/min 방향 혼동 | 우연히 정상 동작하지만 로직 불일치 |
| M2 | `sp500_futures.py:219,317,836` | 지표 재계산 N+1 문제 (100포지션 → ~800회/틱) | CPU/메모리 과부하 |
| M3 | `sp500_futures.py:50-58` | FuturesPositionState 인메모리 only | 재시작 시 트레일링/샹들리에 상태 소실 |
| M4 | `sp500_futures.py:237-297` | NaN 지표 무경고 0 대체 | 사일런트 오류 누적 |
| M5 | `sp500_futures.py:1027-1030` | 하드코딩 매직넘버 (PnL 티어 등) | 백테스트 파라미터 변경 불가 |
| M6 | `strategy/base.py:24-41` | positions 타입 미지정 (list) | IDE 지원/타입체크 불가 |

#### MINOR (9건 요약)

- 미사용 `field` import, 불일치 rounding, 불필요한 `.copy()`, 테스트 누락 (entry signal, boundary), 빈 `__init__.py`, Position 타입 미정의, bars_held 중복 증가 위험

### 12.2 이론-구현 Gap 분석

#### 구현 현황 매트릭스
```
✅ = 완전 구현    ⚠️ = 부분/상이    ❌ = 미구현
```

| 전략/기능 | 이론 문서 | Config | 코드 | 상태 |
|-----------|----------|--------|------|------|
| **S&P500 선물 (Z-Score)** | | | | |
| Z-Score 계산 | futuresStrategy.md | ✅ | ✅ | ✅ |
| 4-Layer 스코어링 | futuresStrategy.md | ✅ | ✅ | ✅ |
| ATR 돌파 필터 | futuresStrategy.md | ✅ | ✅ | ✅ |
| 7단계 청산 cascade | ExitStrategyIndex.md | ✅ | ✅ | ✅ |
| Expected Value 엔진 | futuresStrategy.md | ❌ | ❌ | ❌ |
| Kelly Criterion (동적) | Kelly Criterion.md | ❌ | ⚠️ 고정 | ⚠️ |
| **모멘텀 스윙 (6-Phase)** | | | | |
| Phase 0-2 필터 | alphaStrategy.md | ❌ | ❌ | ❌ |
| Phase 3 진입 (PS1+PS2, CF1+CF2) | alphaStrategy.md | ✅ | ⚠️ 선물만 | ⚠️ |
| Phase 5 ES1-ES5 청산 | ExitStrategyIndex.md | ✅ | ⚠️ ES4 단순화 | ⚠️ |
| Signal Strength 0-100 | alphaStrategy.md | ⚠️ | ❌ | ❌ |
| Progressive Trailing ES3 | mddDefenceStrategy.md | ❌ | ❌ | ❌ |
| **SMC 전략** | | | | |
| BOS/CHoCH 감지 | smcTheory.md | ✅ | ❌ | ❌ |
| 4-Layer 스코어링 | smcTheory.md | ✅ | ❌ | ❌ |
| **Breakout-Retest** | | | | |
| 2-Phase 돌파+리테스트 | CLAUDE.md | ✅ | ❌ | ❌ |
| Retest Zone 스코어링 | CLAUDE.md | ✅ | ❌ | ❌ |
| **스캘핑 (Fabio)** | | | | |
| AMT 3-Stage 필터 | scalpingPlaybook.md | ❌ | ❌ UI만 | ❌ |
| Triple-A Model | scalpingPlaybook.md | ❌ | ❌ | ❌ |
| **리스크 관리** | | | | |
| Risk Gates RG1-RG4 | mddDefenceStrategy.md | ✅ | ❌ | ❌ |
| MDD 7-Layer 방어 | mddDefenceStrategy.md | ⚠️ | ⚠️ L1,L6만 | ⚠️ |
| 레짐별 파라미터 변동 | alphaStrategy.md | ✅ | ❌ 하드코딩 | ❌ |

#### 핵심 불일치 3건

| # | 항목 | 이론 | 실제 코드/설정 | 위험 |
|---|------|------|---------------|------|
| D1 | 손절 비율 | BR-S01 = **-3%** (불변) | config `stop_loss_pct: -0.05` (**-5%**) | 백테스트 Sharpe 왜곡 |
| D2 | 리스크/트레이드 | **1%** of equity | config `risk_per_trade_pct: 0.015` (**1.5%**) | 10동시손절 = -15% > RG2한도(-10%) |
| D3 | 최대보유일 | 레짐별 (BULL 40/NEUTRAL 25/BEAR 15) | 하드코딩 `max_holding_days: 20` | 레짐 무시 |

### 12.3 설정 로딩 결함

**config_manager.py의 `load()` 메서드가 sp500_futures 섹션만 YAML에서 로딩.**

| config.yaml 섹션 | YAML 로딩 | 실제 적용 |
|------------------|----------|-----------|
| sp500_futures (35개 파라미터) | ✅ | ✅ |
| strategy (모멘텀, 10개) | ❌ | 하드코딩 기본값 |
| smc_strategy (12개) | ❌ | 하드코딩 기본값 |
| breakout_retest (24개) | ❌ | 하드코딩 기본값 |
| exit (4개) | ❌ | 하드코딩 기본값 |
| portfolio (3개) | ❌ | 하드코딩 기본값 |
| risk (3개) | ❌ | 하드코딩 기본값 |
| mean_reversion (11개) | ❌ | 구현 없음 |
| arbitrage (33개) | ❌ | 구현 없음 |

**영향**: config.yaml을 수정해도 sp500_futures 외 전략에는 효과 없음.

### 12.4 테스트 커버리지 현황

| 모듈 | 테스트 수 | 상태 |
|------|----------|------|
| common/enums.py | 4 | ✅ |
| common/types.py | 6 | ✅ |
| core/state_manager.py | 7 | ✅ |
| strategy/momentum_swing.py | 11 | ✅ |
| risk/risk_manager.py | 15 | ✅ |
| strategy/breakout_retest.py | 15 | ✅ |
| strategy/sp500_futures.py | 20 | ✅ (entry signal e2e 누락) |
| **analytics/indicators.py** | 0 | ❌ 핵심 지표 미테스트 |
| **infra/broker/kis_broker.py** | 0 | ❌ |
| **infra/db/models.py + repository.py** | 0 | ❌ |
| **api/ (전체 라우트)** | 0 | ❌ |
| **core/main_loop.py + scheduler.py** | 0 | ❌ |
| **position/position_manager.py** | 0 | ❌ |
| **order/order_executor.py** | 0 | ❌ |

### 12.5 프론트엔드 리뷰 요약

**우수 사항:**
- `any` 타입 남용 없음 (TypeScript 안전성 최상)
- 모든 Hook에 cleanup/AbortController 패턴 적용
- SSE → REST 폴링 자동 폴백

**개선 필요:**
- ScalpAnalyzer.tsx (1,658 LOC), FabioStrategy.tsx (1,613 LOC) → 컴포넌트 분리 권장
- SSE 상태 배너, 마켓 탭 버튼 등 3+ 페이지 중복
- 인라인 atom 컴포넌트(NIn, Pill, Met) → `components/common/`으로 이동 권장

---

## 13. 우선순위 액션 플랜

### Tier 1: 즉시 (트레이딩 전 필수)

| # | 액션 | 관련 이슈 | 예상 작업 |
|---|------|----------|----------|
| A1 | config_manager.py: 모든 섹션 YAML 로딩 + 에러 로깅 | C2, 12.3 | ConfigManager.load() 리팩터 |
| A2 | 손절/리스크 파라미터 이론-설정 정합성 맞춤 | D1, D2, D3 | config.yaml + 코드 수정 |
| A3 | sp500_futures.py: NaN 방어 + 로깅 | M4 | _evaluate_entry에 validation |

### Tier 2: 높음 (백테스트 전)

| # | 액션 | 관련 이슈 | 예상 작업 |
|---|------|----------|----------|
| B1 | 지표 계산 캐싱 (N+1 해결) | M2 | _indicator_cache 도입 |
| B2 | FuturesPositionState DB 연동 | M3 | DB 모델 + 저장/복원 |
| B3 | 매직넘버 → SP500FuturesConfig 이동 | M5 | dataclass 필드 추가 |
| B4 | analytics/indicators.py 테스트 추가 | 12.4 | RSI/MACD/BB/ATR 단위테스트 |

### Tier 3: 중간 (프로덕션 전)

| # | 액션 | 관련 이슈 | 예상 작업 |
|---|------|----------|----------|
| C1 | Risk Gates RG1-RG4 구현 | Gap 분석 | risk_gate_checker.py 신규 |
| C2 | Progressive Trailing ES3 (멀티티어) | Gap 분석 | 5-tier floor 시스템 |
| C3 | Phase 0-2 필터 (레짐/트렌드/스테이지) | Gap 분석 | momentum_swing.py 확장 |
| C4 | 프론트엔드 대형 파일 분리 | 12.5 | ScalpAnalyzer, FabioStrategy 리팩터 |

### Tier 4: 낮음 (향후 코드 품질)

| # | 액션 | 관련 이슈 |
|---|------|----------|
| D1 | SMC 전략: 구현 or 제거 결정 | Gap 분석 |
| D2 | Breakout-Retest: 구현 or 제거 결정 | Gap 분석 |
| D3 | Expected Value 엔진 | Gap 분석 |
| D4 | base.py 타입 힌트 강화 | M6 |
| D5 | 중복 UI 컴포넌트 추출 | 12.5 |

---

## 14. 코드리뷰 자료 정리 계획 (code-review/)

### 14.1 Context

이전 세션(§12-13)과 이번 심층 분석에서 수집한 코드리뷰 + 이론-구현 gap 분석 결과를
`code-review/` 폴더에 체계적 문서로 정리한다. git에 커밋하여 로컬(`/Users/daniel/dev/atm-dev/code-review/`)에서 pull로 확인 가능.

### 14.2 폴더 구조
```
code-review/
├── 00-summary.md                    # 종합 요약 (전체 스코어카드 + 핵심 3줄 요약)
├── 01-backend-review.md             # 백엔드 코드리뷰 (품질/보안/성능)
├── 02-frontend-review.md            # 프론트엔드 코드리뷰
├── 03-theory-gap-analysis.md        # stock_theory/ vs 구현 gap 분석
├── 04-config-audit.md               # config.yaml + config_manager.py 감사
├── 05-test-coverage.md              # 테스트 커버리지 현황 + 권장사항
└── 06-action-plan.md                # 우선순위 액션 플랜 (Tier 1~4)
14.3 각 문서 내용 명세
00-summary.md — 종합 요약

전체 점수 (영역별 10점 만점)
CRITICAL/MAJOR/MINOR 이슈 수
이론-구현 정합률 (전략별)
Top 5 즉시 조치 사항
파일 수: ~50줄

01-backend-review.md — 백엔드 코드리뷰

대상 파일: sp500_futures.py, config_manager.py, main.py, base.py, types.py
CRITICAL (4건) — 에이전트 심층 분석 반영

C1: main.py:28-42 13개 존재하지 않는 모듈 import → ModuleNotFoundError
C2: config_manager.py:226-239 YAML 로딩 sp500_futures만 작동 + FileNotFoundError 무시 (pass)
C3: sp500_futures.py:707,712,716 wick/body Division by Zero (body < 0.001 체크 후에도 나눗셈 발생)
C4: config_manager.py:222 .env 로딩 미구현 (env_path 파라미터 받지만 사용 안함)


MAJOR (12건) — 각각 파일:라인, 문제코드, 수정 제안 포함

M1: sp500_futures.py:50-57 FuturesPositionState 초기값 문제 (highest=0.0, lowest=inf)
M2: sp500_futures.py:73-74 Position state 인메모리 only → 재시작 시 소실
M3: sp500_futures.py:122-123 RSI NaN 전파 (avg_loss=0일 때)
M4: sp500_futures.py:457-487,513-548,574-620,639-659 100+ 하드코딩 매직넘버
M5: sp500_futures.py:742-743 ATR 0 폴백 1% 하드코딩
M6: sp500_futures.py:696-698 Volume ratio 임계값 0.8 과도하게 보수적
M7: sp500_futures.py:1027-1030 트레일링 멀티플라이어 하드코딩
M8: config_manager.py:232-236 9개 설정 섹션 중 1개만 로딩
M9: config_manager.py:234-236 타입 검증 없음 (문자열→숫자 무경고)
M10: main.py:67-77 KIS 시크릿 미검증
M11: base.py:36 positions 타입 list → List[Position] 필요
M12: main.py:214 backtest/engine.py 모듈 미존재


MINOR (4건) — df.iloc[-5] 범위 체크, Signal.bb_upper 설계, ATR breakout 기본값 문서화, bars_held 중복 증가
파일 수: ~250줄

02-frontend-review.md — 프론트엔드 코드리뷰

점수: 코드 품질 8.5/10, 타입 안전 8/10 (any 10건), Hook 9.5/10
우수 사항: AbortController 패턴, SSE→REST 폴백, 지수 백오프
개선 필요:

대형 파일: ScalpAnalyzer.tsx (1,658 LOC), FabioStrategy.tsx (1,613 LOC)
any 타입 10건: TechnicalChart.tsx(6), api.ts(1), useAnalyticsData.ts(1), smcZonePrimitive.ts(2)
중복 패턴: Pill/Met/Sec/NIn 컴포넌트 ScalpAnalyzer:64-92 ≡ FabioStrategy:36-83
Hardcoded URL: api.ts:42 + useSSE.ts:9 (http://localhost:8000)
SSE heartbeat 미감지: useSSE.ts — 서버 무응답 시 타임아웃 없음


보안: 하드코딩 시크릿 없음 ✅, .gitignore에 .env 포함 ✅
입력 검증: API 라우트에 Pydantic 검증 미적용 (ticker 포맷, 쿼리 파라미터)
파일 수: ~120줄

03-theory-gap-analysis.md — 이론 vs 구현 Gap

전략별 정합률 매트릭스 (✅/⚠️/❌)

SP500 선물: 90% 구현 (EV엔진/동적 Kelly 미구현)
모멘텀 스윙: 0% (Config만 존재, 코드 없음)
SMC: 0% (Config만 존재, 코드 없음)
Breakout-Retest: 0% (Config만 존재, 코드 없음)
MDD 7-Layer: 0% (Circuit breaker 미구현 — CRITICAL)


핵심 불일치 3건 (D1 손절비율, D2 리스크/트레이드, D3 최대보유일)
이론 문서 11개 리뷰 결과: 완전 구현 1개, 부분 3개, 미구현 7개
비즈니스 임팩트 평가표
파일 수: ~250줄

04-config-audit.md — 설정 감사

config_manager.py load() 결함: sp500_futures만 로딩, 나머지 9개 섹션 무시
섹션별 상태표 (YAML 존재 / 코드 로딩 / 실제 적용)
.env 미로딩 문제
타입 검증 없음: 문자열 → 숫자 변환 실패 시 무경고
수정 제안 코드 (전체 섹션 로딩 + 타입 검증 + .env 통합)
파일 수: ~120줄

05-test-coverage.md — 테스트 커버리지

현재: ~85건 (run_tests.py 43건 + test_sp500_futures.py 42건)

common/enums 4 + common/types 6 + state_manager 7 + momentum 11 + risk 15 + breakout 15 + sp500 futures 42


커버된 모듈 (7개): common, core/state, risk, momentum, breakout, sp500_futures, (base.py 간접)
미커버 모듈 (17+개): analytics/indicators, api/(전체), backtest/(전체), core/main_loop, core/scheduler, data/market_data, infra/broker, infra/db, infra/notifier, order/, position/, simulation/, smc_strategy
CRITICAL 미커버: backtest/historical_engine.py, api/app.py (SSE), infra/broker/kis_broker.py, simulation/engine.py
테스트 품질: 합성 OHLCV 데이터 ✅, boundary 테스트 ✅, 외부 의존성 mock 없음 ❌, 통합 테스트 없음 ❌
커스텀 러너: pytest 비호환 (run_tests.py는 자체 프레임워크)
파일 수: ~120줄

06-action-plan.md — 우선순위 액션 플랜

Tier 1 (즉시/트레이딩 전): config 로딩 수정, 파라미터 정합성, NaN 방어
Tier 2 (높음/백테스트 전): 지표 캐싱, 상태 DB 연동, 매직넘버 제거, 지표 테스트
Tier 3 (중간/프로덕션 전): Risk Gates, Progressive Trailing, Phase 0-2, FE 분리
Tier 4 (낮음/향후): SMC/BRT 구현 결정, EV엔진, 타입 강화, UI 추출
파일 수: ~80줄

14.4 구현 단계
Step작업소스1code-review/ 디렉토리 생성—200-summary.md 작성§12-13 + 에이전트 분석 종합301-backend-review.md 작성sp500_futures 심층 에이전트 결과402-frontend-review.md 작성프론트엔드 에이전트 결과503-theory-gap-analysis.md 작성이론 gap 에이전트 결과604-config-audit.md 작성config 에이전트 + §12.3705-test-coverage.md 작성테스트 에이전트 + §12.4806-action-plan.md 작성§13 우선순위 플랜9git commit + pushclaude/sp500-trading-signals-zcZue 브랜치
14.5 검증
bash# 파일 존재 확인
ls -la code-review/

# 마크다운 렌더링 확인 (로컬에서)
# git pull 후 /Users/daniel/dev/atm-dev/code-review/ 에서 확인

15. 향후 확장 포인트
15.1 run_tests.py 통합 (선택사항)

run_tests.py의 __main__ 섹션에 test_suite_sp500_futures() 추가
현재는 별도 파일로 독립 실행 가능

15.2 main.py 전략 선택 (선택사항)

build_application() 에서 config 기반 전략 선택 로직 추가
strategy = SP500FuturesStrategy(config=config) 로 교체 가능

15.3 백테스트 통합 (선택사항)

backtest/engine.py 확장하여 SP500 선물 백테스트 지원
yfinance로 ES=F 히스토리컬 데이터 자동 다운로드

15.4 API 엔드포인트 (선택사항)

/analyze/futures/ES=F 엔드포인트 추가
generate_futures_signal() 호출하여 실시간 분석 결과 반환


16. 검증 방법
16.1 단위 테스트
bashPYTHONPATH=/home/user/atm-dev/ats python3 ats/tests/test_sp500_futures.py
# 결과: ✅ 20 passed / ❌ 0 failed
16.2 코드 수준 검증

지표 계산: RSI 0~100, Z-Score -10~+10, ADX ≥ 0
스코어링: 각 Layer 0~25, 총점 0~100
SL/TP: 롱 SL < entry < TP, 숏 TP < entry < SL
청산 우선순위: ES1 > ES_ATR_SL > ES_ATR_TP > ES_CHANDELIER > ES3 > ES_CHOCH > ES5
포지션 사이징: 1 ≤ contracts ≤ max_contracts

16.3 통합 테스트 (향후)

yfinance로 ES=F 실제 데이터 다운로드 후 시그널 생성 검증
백테스트 엔진에서 과거 성과 검증